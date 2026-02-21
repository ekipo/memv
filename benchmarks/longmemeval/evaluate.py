"""Stage 3: LLM-judge evaluation of LongMemEval search results."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import time
from pathlib import Path

logger = logging.getLogger(__name__)

RESULTS_DIR = Path(__file__).parent.parent / "results"

# --- Type-specific judge prompts (adapted from Nemori/Zep LongMemEval evals) ---

TEMPORAL_REASONING_PROMPT = """I will give you a question, a correct answer, and a response from a model. Please answer yes if the response contains the correct answer. Otherwise, answer no. If the response is equivalent to the correct answer or contains all the intermediate steps to get the correct answer, you should also answer yes. If the response only contains a subset of the information required by the answer, answer no. In addition, do not penalize off-by-one errors for the number of days. If the question asks for the number of days/weeks/months, etc., and the model makes off-by-one errors (e.g., predicting 19 days when the answer is 18), the model's response is still correct.

<QUESTION>
{question}
</QUESTION>
<CORRECT ANSWER>
{gold_answer}
</CORRECT ANSWER>
<RESPONSE>
{response}
</RESPONSE>"""

KNOWLEDGE_UPDATE_PROMPT = """I will give you a question, a correct answer, and a response from a model. Please answer yes if the response contains the correct answer. Otherwise, answer no. If the response contains some previous information along with an updated answer, the response should be considered as correct as long as the updated answer is the required answer.

<QUESTION>
{question}
</QUESTION>
<CORRECT ANSWER>
{gold_answer}
</CORRECT ANSWER>
<RESPONSE>
{response}
</RESPONSE>"""

SINGLE_SESSION_PREFERENCE_PROMPT = """I will give you a question, a rubric for desired personalized response, and a response from a model. Please answer yes if the response satisfies the desired response. Otherwise, answer no. The model does not need to reflect all the points in the rubric. The response is correct as long as it recalls and utilizes the user's personal information correctly.

<QUESTION>
{question}
</QUESTION>
<RUBRIC>
{gold_answer}
</RUBRIC>
<RESPONSE>
{response}
</RESPONSE>"""

DEFAULT_PROMPT = """I will give you a question, a correct answer, and a response from a model. Please answer yes if the response contains the correct answer. Otherwise, answer no. If the response is equivalent to the correct answer or contains all the intermediate steps to get the correct answer, you should also answer yes. If the response only contains a subset of the information required by the answer, answer no.

<QUESTION>
{question}
</QUESTION>
<CORRECT ANSWER>
{gold_answer}
</CORRECT ANSWER>
<RESPONSE>
{response}
</RESPONSE>"""

SYSTEM_PROMPT = "You are an expert grader. Respond with ONLY 'yes' or 'no'."

PROMPTS_BY_TYPE = {
    "temporal-reasoning": TEMPORAL_REASONING_PROMPT,
    "knowledge-update": KNOWLEDGE_UPDATE_PROMPT,
    "single-session-preference": SINGLE_SESSION_PREFERENCE_PROMPT,
}


async def evaluate_single(
    llm_client,
    question: str,
    gold_answer: str,
    response: str,
    question_type: str,
) -> bool:
    """Evaluate a single question-response pair using LLM judge."""
    template = PROMPTS_BY_TYPE.get(question_type, DEFAULT_PROMPT)
    prompt = template.format(question=question, gold_answer=gold_answer, response=response)
    full_prompt = f"{SYSTEM_PROMPT}\n\n{prompt}"

    try:
        result = await llm_client.generate(full_prompt)
        return result.strip().lower().startswith("yes")
    except Exception as e:
        logger.error("Evaluation failed: %s", e)
        return False


async def run(
    run_name: str = "baseline",
    llm_client=None,
    max_concurrent: int = 10,
):
    """Run evaluation on search results.

    Args:
        run_name: Name for this benchmark run (must match search stage).
        llm_client: LLMClient instance for LLM-judge.
        max_concurrent: Max concurrent LLM calls.
    """
    if llm_client is None:
        raise RuntimeError("llm_client is required.")

    run_dir = RESULTS_DIR / run_name
    search_path = run_dir / "search.json"
    if not search_path.exists():
        raise FileNotFoundError(f"No search results at {search_path}. Run search stage first.")

    data = json.loads(search_path.read_text(encoding="utf-8"))
    print(f"LongMemEval Evaluate | run={run_name} questions={len(data)}")

    # Evaluate with concurrency control
    semaphore = asyncio.Semaphore(max_concurrent)

    async def eval_with_semaphore(item: dict) -> tuple[bool, dict]:
        async with semaphore:
            if item.get("error"):
                return False, item
            is_correct = await evaluate_single(
                llm_client,
                item["question"],
                item["answer"],
                item["response"],
                item.get("question_type", "default"),
            )
            return is_correct, item

    tasks = [eval_with_semaphore(item) for item in data]
    results = await asyncio.gather(*tasks)

    # Aggregate scores
    type_stats: dict[str, dict[str, int]] = {}
    total_correct = 0
    total_count = 0
    scored_items = []

    for is_correct, item in results:
        qtype = item.get("question_type", "unknown")
        if qtype not in type_stats:
            type_stats[qtype] = {"correct": 0, "total": 0}

        type_stats[qtype]["total"] += 1
        total_count += 1

        if is_correct:
            type_stats[qtype]["correct"] += 1
            total_correct += 1

        scored_items.append(
            {
                "question_id": item["question_id"],
                "question_type": item.get("question_type"),
                "is_correct": is_correct,
                "question": item["question"],
                "gold_answer": item["answer"],
                "response": item["response"],
            }
        )

    # Calculate accuracies
    overall_accuracy = total_correct / total_count if total_count > 0 else 0
    accuracy_by_type = {}
    for qtype, stats in sorted(type_stats.items()):
        acc = stats["correct"] / stats["total"] if stats["total"] > 0 else 0
        accuracy_by_type[qtype] = {
            "correct": stats["correct"],
            "total": stats["total"],
            "accuracy": round(acc, 4),
        }

    scores = {
        "run_name": run_name,
        "total_questions": total_count,
        "correct_answers": total_correct,
        "overall_accuracy": round(overall_accuracy, 4),
        "accuracy_by_type": accuracy_by_type,
        "evaluation_timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "scored_items": scored_items,
    }

    # Print summary
    print(f"\n{'=' * 50}")
    print(f"Overall: {total_correct}/{total_count} = {overall_accuracy:.1%}")
    print(f"{'=' * 50}")
    for qtype, stats in sorted(accuracy_by_type.items()):
        print(f"  {qtype}: {stats['correct']}/{stats['total']} = {stats['accuracy']:.1%}")
    print(f"{'=' * 50}")

    # Save
    output_path = run_dir / "scores.json"
    output_path.write_text(json.dumps(scores, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nScores saved to {output_path}")

    return scores


def _make_llm_client():
    from memv.llm.pydantic_ai import PydanticAIAdapter

    return PydanticAIAdapter()


def main():
    parser = argparse.ArgumentParser(description="LongMemEval Stage 3: Evaluation")
    parser.add_argument("--run-name", default="baseline", help="Name for this run")
    parser.add_argument("--max-concurrent", type=int, default=10, help="Max concurrent LLM calls")
    args = parser.parse_args()

    llm_client = _make_llm_client()
    asyncio.run(run(run_name=args.run_name, llm_client=llm_client, max_concurrent=args.max_concurrent))


if __name__ == "__main__":
    main()
