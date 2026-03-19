#!/usr/bin/env python3
"""
Build BM25 corpus index for hybrid retrieval.

This script:
  1. Lists all vector IDs in a namespace
  2. Fetches vectors in batches to extract corpus text + source from metadata
  3. Saves corpus to bm25_models/{namespace}_corpus.json (used at query time)

The corpus JSON is what powers local BM25 keyword search in retrieval.py.
No re-embedding — existing dense vectors are untouched. OpenAI API not called.

Usage:
  python patch_sparse_vectors.py --namespace sec_filings_nvda
  python patch_sparse_vectors.py --namespace news
  python patch_sparse_vectors.py --namespace all
"""

import argparse
import json
import os
from pathlib import Path

from dotenv import load_dotenv
from pinecone import Pinecone

load_dotenv()

PINECONE_INDEX_NAME = os.environ.get("PINECONE_INDEX_NAME", "rag-application")
BM25_MODELS_DIR = Path("bm25_models")
NAMESPACES = ["sec_filings_nvda", "earnings_calls_nvda", "news", "social"]


def fetch_all_vectors(index, namespace: str) -> dict[str, dict]:
    """Fetch all vectors from a namespace. LangChain stores page_content in metadata['text']."""
    print(f"  Listing vector IDs in namespace '{namespace}'...")
    all_ids = []
    for id_batch in index.list(namespace=namespace):
        all_ids.extend(id_batch)

    if not all_ids:
        print(f"  No vectors found in namespace '{namespace}'")
        return {}

    print(f"  Found {len(all_ids)} vectors. Fetching in batches...")
    vectors = {}
    batch_size = 200
    for i in range(0, len(all_ids), batch_size):
        batch = all_ids[i : i + batch_size]
        response = index.fetch(ids=batch, namespace=namespace)
        for vec_id, vec_data in response.vectors.items():
            text = vec_data.metadata.get("text", "")
            if text:
                vectors[vec_id] = {
                    "text": text,
                    "source": vec_data.metadata.get("source", vec_id),
                    "metadata": vec_data.metadata,
                }
        if (i // batch_size + 1) % 5 == 0:
            print(f"    Fetched {min(i + batch_size, len(all_ids))}/{len(all_ids)}")

    print(f"  Fetched {len(vectors)} vectors with text")
    return vectors


def build_corpus_index(vectors: dict, namespace: str) -> None:
    """Save corpus texts and sources for local BM25 search."""
    ids = list(vectors.keys())
    texts = [vectors[i]["text"] for i in ids]
    sources = [vectors[i]["source"] for i in ids]

    BM25_MODELS_DIR.mkdir(exist_ok=True)
    corpus_path = BM25_MODELS_DIR / f"{namespace}_corpus.json"
    with open(corpus_path, "w") as f:
        json.dump({"ids": ids, "texts": texts, "sources": sources}, f)
    print(f"  Saved corpus index ({len(texts)} docs) to {corpus_path}")


def patch_namespace(index, namespace: str) -> None:
    print(f"\n=== Building BM25 corpus for namespace: {namespace} ===")
    vectors = fetch_all_vectors(index, namespace)
    if not vectors:
        return
    build_corpus_index(vectors, namespace)
    print(f"  Done.")


def main():
    parser = argparse.ArgumentParser(description="Build BM25 corpus index for hybrid retrieval")
    parser.add_argument(
        "--namespace",
        default="sec_filings_nvda",
        help="Namespace to index, or 'all' for all namespaces",
    )
    args = parser.parse_args()

    pc = Pinecone(api_key=os.environ["PINECONE_API_KEY"])
    index = pc.Index(PINECONE_INDEX_NAME)

    namespaces = NAMESPACES if args.namespace == "all" else [args.namespace]
    for ns in namespaces:
        patch_namespace(index, ns)

    print("\nAll done. Run the evaluation next:")
    print("  python evaluate_cross_encoder.py --dataset sec --mode all")


if __name__ == "__main__":
    main()
