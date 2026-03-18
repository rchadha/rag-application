#!/usr/bin/env python3

import argparse
import json
from pathlib import Path

from retrieval import CROSS_ENCODER_MODEL_NAME, EMBEDDING_MODEL_NAME, get_top_results

EVAL_SETS = {
    "sec": Path("evals/sec_retrieval_eval.json"),
    "news": Path("evals/news_retrieval_eval.json"),
}
RESULTS_PATH = Path("evals/cross_encoder_results.json")


def first_relevant_rank(results: list[dict], expected_sources: list[str]) -> int | None:
    for index, result in enumerate(results, start=1):
        source = result["source"]
        if any(expected in source for expected in expected_sources):
            return index
    return None


def score_run(eval_items: list[dict], use_reranker: bool):
    scored_items = []

    for item in eval_items:
        results = get_top_results(
            item["question"],
            dataset=item["dataset"],
            candidate_k=10,
            final_k=3,
            use_reranker=use_reranker,
        )
        rank = first_relevant_rank(results, item["expected_sources"])
        hit_at_1 = 1 if rank == 1 else 0
        hit_at_3 = 1 if rank is not None and rank <= 3 else 0
        mrr = 0 if rank is None else 1 / rank

        scored_items.append(
            {
                "question": item["question"],
                "dataset": item["dataset"],
                "expected_sources": item["expected_sources"],
                "rank": rank,
                "hit_at_1": hit_at_1,
                "hit_at_3": hit_at_3,
                "mrr": mrr,
                "results": [
                    {
                        "source": result["source"],
                        "vector_score": result.get("vector_score"),
                        "rerank_score": result.get("rerank_score"),
                    }
                    for result in results
                ],
            }
        )

    return scored_items


def summarize(items: list[dict]):
    count = len(items)
    return {
        "questions": count,
        "hit_at_1": sum(item["hit_at_1"] for item in items) / count,
        "hit_at_3": sum(item["hit_at_3"] for item in items) / count,
        "mrr": sum(item["mrr"] for item in items) / count,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", choices=["sec", "news"], default="sec")
    args = parser.parse_args()

    eval_set_path = EVAL_SETS[args.dataset]
    results_path = Path(f"evals/cross_encoder_results_{args.dataset}.json")

    eval_items = json.loads(eval_set_path.read_text(encoding="utf-8"))
    baseline = score_run(eval_items, use_reranker=False)
    reranked = score_run(eval_items, use_reranker=True)

    payload = {
        "dataset": args.dataset,
        "embedding_model": EMBEDDING_MODEL_NAME,
        "cross_encoder_model": CROSS_ENCODER_MODEL_NAME,
        "baseline_summary": summarize(baseline),
        "reranked_summary": summarize(reranked),
        "baseline": baseline,
        "reranked": reranked,
    }

    results_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"\nDataset: {args.dataset}")
    print("Baseline:")
    print(json.dumps(payload["baseline_summary"], indent=2))
    print("Reranked:")
    print(json.dumps(payload["reranked_summary"], indent=2))


if __name__ == "__main__":
    main()
