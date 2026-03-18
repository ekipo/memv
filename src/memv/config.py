"""Configuration dataclass for AgentMemory."""

from dataclasses import dataclass


@dataclass
class MemoryConfig:
    """Configuration for Memory system.

    Provides centralized configuration with sensible defaults.
    Can be passed to Memory() or individual params can be overridden.

    Example:
        ```python
        config = MemoryConfig(
            max_statements_for_prediction=5,
            enable_episode_merging=False,
        )
        memory = Memory(config=config, embedding_client=embedder, llm_client=llm)
        ```
    """

    # Database
    db_path: str = ".db/memory.db"
    embedding_dimensions: int = 1536

    # Processing triggers
    auto_process: bool = False
    batch_threshold: int = 10
    max_retries: int = 1

    # Segmentation
    segmentation_threshold: int = 20
    time_gap_minutes: int = 30
    use_legacy_segmentation: bool = False

    # Episode merging
    enable_episode_merging: bool = True
    merge_similarity_threshold: float = 0.9

    # Knowledge deduplication
    enable_knowledge_dedup: bool = True
    knowledge_dedup_threshold: float = 0.8

    # Prediction-calibrate
    max_statements_for_prediction: int = 10

    # Embedding cache
    enable_embedding_cache: bool = True
    embedding_cache_size: int = 1000
    embedding_cache_ttl_seconds: int = 600

    # Retrieval
    default_min_score: float | None = None

    def __post_init__(self):
        if self.embedding_dimensions < 1:
            raise ValueError(f"embedding_dimensions must be >= 1, got {self.embedding_dimensions}")
        if self.batch_threshold < 1:
            raise ValueError(f"batch_threshold must be >= 1, got {self.batch_threshold}")
        if self.segmentation_threshold < 1:
            raise ValueError(f"segmentation_threshold must be >= 1, got {self.segmentation_threshold}")
        if self.time_gap_minutes <= 0:
            raise ValueError(f"time_gap_minutes must be > 0, got {self.time_gap_minutes}")
        if not (0.0 <= self.merge_similarity_threshold <= 1.0):
            raise ValueError(f"merge_similarity_threshold must be between 0.0 and 1.0, got {self.merge_similarity_threshold}")
        if not (0.0 <= self.knowledge_dedup_threshold <= 1.0):
            raise ValueError(f"knowledge_dedup_threshold must be between 0.0 and 1.0, got {self.knowledge_dedup_threshold}")
        if self.max_statements_for_prediction < 1:
            raise ValueError(f"max_statements_for_prediction must be >= 1, got {self.max_statements_for_prediction}")
        if self.embedding_cache_size < 1:
            raise ValueError(f"embedding_cache_size must be >= 1, got {self.embedding_cache_size}")
        if self.embedding_cache_ttl_seconds <= 0:
            raise ValueError(f"embedding_cache_ttl_seconds must be > 0, got {self.embedding_cache_ttl_seconds}")
        if self.default_min_score is not None and self.default_min_score < 0.0:
            raise ValueError(f"default_min_score must be >= 0.0, got {self.default_min_score}")
