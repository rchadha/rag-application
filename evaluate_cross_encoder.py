#!/usr/bin/env python3

import argparse
import json
from pathlib import Path

from retrieval import CROSS_ENCODER_MODEL_NAME, EMBEDDING_MODEL_NAME, get_top_results

EVAL_SETS = {
    "sec": Path("evals/sec_retrieval_eval.json"),
    "news": Path("evals/news_retrieval_eval.json"),
}

MODES = {
    "dense":           dict(use_hybrid=False, use_reranker=False),
    "dense_reranked":  dict(use_hybrid=False, use_reranker=True),
    "hybrid":          dict(use_hybrid=True,  use_reranker=False),
    "hybrid_reranked": dict(use_hybrid=True,  use_reranker=True),
}


def first_relevant_rank(results: list[dict], expected_sources: list[str]) -> int | None:
    for index, result in enumerate(results, start=1):
        source = result["source"]
        if any(expected in source for expected in expected_sources):
            return index
    return None


def score_run(eval_items: list[dict], use_reranker: bool, use_hybrid: bool):
    scored_items = []
    for item in eval_items:
        results = get_top_results(
            item["question"],
            dataset=item["dataset"],
            candidate_k=10,
            final_k=3,
            use_reranker=use_reranker,
            use_hybrid=use_hybrid,
        )
        rank = first_relevant_rank(results, item["expected_sources"])
        scored_items.append({
            "question": item["question"],
            "dataset": item["dataset"],
            "expected_sources": item["expected_sources"],
            "rank": rank,
            "hit_at_1": 1 if rank == 1 else 0,
            "hit_at_3": 1 if (rank is not None and rank <= 3) else 0,
            "mrr": 0 if rank is None else 1 / rank,
            "results": [
                {
                    "source": r["source"],
                    "vector_score": r.get("vector_score"),
                    "rerank_score": r.get("rerank_score"),
                }
                for r in results
            ],
        })
    return scored_items


def summarize(items: list[dict]) -> dict:
    count = len(items)
    return {
        "questions": count,
        "hit_at_1": round(sum(i["hit_at_1"] for i in items) / count, 4),
        "hit_at_3": round(sum(i["hit_at_3"] for i in items) / count, 4),
        "mrr":      round(sum(i["mrr"]      for i in items) / count, 4),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", choices=["sec", "news"], default="sec")
    parser.add_argument(
        "--mode",
        choices=list(MODES.keys()) + ["all"],
        default="all",
        help="Which retrieval mode(s) to evaluate",
    )
    args = parser.parse_args()

    eval_items = json.loads(EVAL_SETS[args.dataset].read_text(encoding="utf-8"))
    modes_to_run = list(MODES.keys()) if args.mode == "all" else [args.mode]

    payload = {
        "dataset": args.dataset,
        "embedding_model": EMBEDDING_MODEL_NAME,
        "cross_encoder_model": CROSS_ENCODER_MODEL_NAME,
    }

    print(f"\nDataset: {args.dataset}  |  {len(eval_items)} questions\n")
    print(f"{'Mode':<20} {'Hit@1':>6} {'Hit@3':>6} {'MRR':>6}")
    print("-" * 42)

    for mode in modes_to_run:
        kwargs = MODES[mode]
        scored = score_run(eval_items, **kwargs)
        summary = summarize(scored)
        payload[f"{mode}_summary"] = summary
        payload[f"{mode}_detail"] = scored
        print(f"{mode:<20} {summary['hit_at_1']:>6.3f} {summary['hit_at_3']:>6.3f} {summary['mrr']:>6.3f}")

    results_path = Path(f"evals/cross_encoder_results_{args.dataset}.json")
    results_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"\nResults saved to {results_path}")


if __name__ == "__main__":
    main()
