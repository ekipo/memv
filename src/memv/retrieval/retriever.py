"""Hybrid retrieval combining vector and text search."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from memv.models import RetrievalResult, SemanticKnowledge
from memv.protocols import EmbeddingClient, KnowledgeStore
from memv.storage import TextIndex, VectorIndex

if TYPE_CHECKING:
    from memv.cache import EmbeddingCache


class Retriever:
    """
    Hybrid retriever combining vector similarity and text search.

    Searches knowledge statements and returns unified results with RRF fusion.
    """

    def __init__(
        self,
        knowledge_store: KnowledgeStore,
        vector_index: VectorIndex,
        text_index: TextIndex,
        embedding_client: EmbeddingClient | None = None,
        embedding_cache: EmbeddingCache | None = None,
        default_min_score: float | None = None,
    ):
        self.knowledge = knowledge_store
        self.vector_index = vector_index
        self.text_index = text_index
        self.embedder = embedding_client
        self._embedding_cache = embedding_cache
        self.default_min_score = default_min_score

    async def retrieve(
        self,
        query: str,
        user_id: str,
        top_k: int = 10,
        vector_weight: float = 0.5,
        min_score: float | None = None,
        allow_empty: bool = False,
        at_time: datetime | None = None,
        include_expired: bool = False,
    ) -> RetrievalResult:
        """
        Retrieve relevant knowledge for a query.

        Args:
            query: Search query text
            user_id: Filter results to this user only (required for privacy)
            top_k: Number of results to return
            vector_weight: Weight for vector vs text (0-1, where 0.5 is balanced)
            min_score: Minimum normalized relevance score (0-1): None disables filtering or uses instance default_min_score
            allow_empty: If True, return no results when all are below threshold; otherwise (default) return at least one
            at_time: If provided, filter knowledge by validity at this event time
            include_expired: If True, include superseded (expired) records

        Returns:
            RetrievalResult containing knowledge statements with scores.
        """
        if top_k < 1:
            raise ValueError(f"top_k must be >= 1, got {top_k}")
        if not (0.0 <= vector_weight <= 1.0):
            raise ValueError(f"vector_weight must be between 0.0 and 1.0, got {vector_weight}")
        if min_score is not None and (min_score < 0.0 or min_score > 1.0):
            raise ValueError(f"min_score must be >= 0.0 and <= 1.0, got {min_score}")

        if self.embedder is None:
            raise RuntimeError("Embedding client required for retrieval")

        # 1. Embed query (with caching)
        query_embedding = None
        if self._embedding_cache is not None:
            query_embedding = self._embedding_cache.get(query)

        if query_embedding is None:
            query_embedding = await self.embedder.embed(query)
            if self._embedding_cache is not None:
                self._embedding_cache.set(query, query_embedding)

        # 2. Search knowledge (filtered by user_id)
        scored_knowledge = await self._search_knowledge(
            query=query,
            query_embedding=query_embedding,
            top_k=top_k,
            vector_weight=vector_weight,
            user_id=user_id,
            min_score=min_score if min_score is not None else self.default_min_score,
            allow_empty=allow_empty,
            at_time=at_time,
            include_expired=include_expired,
        )
        if not scored_knowledge:
            return RetrievalResult()

        retrieved_knowledge, scores = zip(*scored_knowledge, strict=True)
        return RetrievalResult(
            retrieved_knowledge=list(retrieved_knowledge),
            scores=list(scores),
        )

    async def _search_knowledge(
        self,
        query: str,
        query_embedding: list[float],
        top_k: int,
        vector_weight: float,
        user_id: str,
        min_score: float | None = None,
        allow_empty: bool = False,
        at_time: datetime | None = None,
        include_expired: bool = False,
    ) -> list[tuple[SemanticKnowledge, float]]:
        """Search knowledge using hybrid vector + text search, filtered by user_id."""
        # Vector search (filtered by user_id)
        vector_ids = await self.vector_index.search(query_embedding, top_k=top_k * 3, user_id=user_id)

        # Text search (BM25) (filtered by user_id)
        text_ids = await self.text_index.search(query, top_k=top_k * 3, user_id=user_id)

        # RRF fusion
        fused = self._rrf_fusion(vector_ids, text_ids, vector_weight=vector_weight)

        # Fetch full objects (deduplicated) with temporal filtering
        results: list[tuple[SemanticKnowledge, float]] = []
        seen: set[UUID] = set()
        for kid, score in fused:
            if kid in seen:
                continue
            if len(results) >= top_k:
                break

            k = await self.knowledge.get(kid)
            if k:
                # Apply temporal filtering
                if not self._passes_temporal_filter(k, at_time, include_expired):
                    continue
                results.append((k, score))
                seen.add(kid)

        # Apply score threshold filtering
        if min_score is not None and results:
            filtered = [(k, s) for k, s in results if s >= min_score]
            if not filtered and not allow_empty:
                filtered = [results[0]]  # keep best result
            results = filtered

        return results

    def _passes_temporal_filter(
        self,
        knowledge: SemanticKnowledge,
        at_time: datetime | None,
        include_expired: bool,
    ) -> bool:
        """Check if knowledge passes temporal filtering criteria."""
        # Filter by transaction time (expired_at)
        if not include_expired and not knowledge.is_current():
            return False

        # Filter by event time (valid_at/invalid_at)
        if at_time is not None and not knowledge.is_valid_at(at_time):
            return False

        return True

    def _rrf_fusion(
        self,
        vector_ids: list[UUID],
        text_ids: list[UUID],
        vector_weight: float = 0.5,
        k: int = 60,  # RRF constant
    ) -> list[tuple[UUID, float]]:
        """
        Reciprocal Rank Fusion.

        RRF score = vector_weight * (1/(k + rank_vector)) +
                    (1 - vector_weight) * (1/(k + rank_text))

        k=60 is standard from literature.

        Returns:
            List of (knowledge_id, normalized score [0,1]) tuples, sorted by score descending
        """
        scores: dict[UUID, float] = {}

        # Vector contributions
        for rank, uid in enumerate(vector_ids):
            scores[uid] = scores.get(uid, 0.0) + vector_weight * (1 / (k + rank + 1))

        # Text contributions
        text_weight = 1.0 - vector_weight
        for rank, uid in enumerate(text_ids):
            scores[uid] = scores.get(uid, 0.0) + text_weight * (1 / (k + rank + 1))

        # Sort by score descending
        max_score = 1.0 / (k + 1)
        sorted_results = sorted(scores.items(), key=lambda item: item[1], reverse=True)
        return [(uid, raw / max_score) for uid, raw in sorted_results]
