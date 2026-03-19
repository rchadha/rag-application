#!/usr/bin/env python3
"""
Migrate from cosine index to dotproduct index with BM25 sparse vectors.

Why dotproduct?
  Pinecone's native hybrid search (sparse + dense) requires dotproduct metric.
  Cosine indexes reject queries that include sparse_vector.

Why dotproduct doesn't hurt dense-only search quality?
  OpenAI embeddings are L2-normalised (unit vectors). For unit vectors,
  dotproduct(a, b) == cosine_similarity(a, b) exactly. Rankings are identical.

What this script does:
  1. Fetches all vectors from the existing cosine index (dense values + metadata)
  2. Fits BM25Encoder on each namespace corpus and saves to bm25_models/
  3. Deletes the cosine index
  4. Creates a new dotproduct index with the same name and dimension
  5. Upserts all vectors with both dense + sparse values

No re-embedding. No OpenAI API calls. Existing dense vectors are reused.

Usage:
  python migrate_to_hybrid_index.py
  python migrate_to_hybrid_index.py --dry-run   # show what would happen, no changes
"""

import argparse
import json
import os
import time
from pathlib import Path

from dotenv import load_dotenv
from pinecone import Pinecone, ServerlessSpec
from pinecone_text.sparse import BM25Encoder

load_dotenv()

PINECONE_INDEX_NAME = os.environ.get("PINECONE_INDEX_NAME", "rag-application")
BM25_MODELS_DIR = Path("bm25_models")
DIMENSION = 1536
CLOUD = "aws"
REGION = "us-east-1"

NAMESPACES = ["sec_filings_nvda", "earnings_calls_nvda", "news", "social"]


def fetch_namespace(index, namespace: str) -> list[dict]:
    """Fetch all vectors from a namespace, including dense values and metadata."""
    print(f"  Listing IDs in '{namespace}'...")
    all_ids = []
    for batch in index.list(namespace=namespace):
        all_ids.extend(batch)

    if not all_ids:
        print(f"  No vectors found in '{namespace}', skipping")
        return []

    print(f"  Fetching {len(all_ids)} vectors in batches...")
    vectors = []
    batch_size = 200
    for i in range(0, len(all_ids), batch_size):
        batch_ids = all_ids[i : i + batch_size]
        response = index.fetch(ids=batch_ids, namespace=namespace)
        for vec_id, vec_data in response.vectors.items():
            text = vec_data.metadata.get("text", "")
            if not text:
                continue
            vectors.append({
                "id": vec_id,
                "values": vec_data.values,
                "metadata": dict(vec_data.metadata),
                "text": text,
                "source": vec_data.metadata.get("source", vec_id),
            })
        if (i // batch_size + 1) % 5 == 0:
            print(f"    Fetched {min(i + batch_size, len(all_ids))}/{len(all_ids)}")

    print(f"  Fetched {len(vectors)} vectors with text")
    return vectors


def build_bm25_and_sparse(vectors: list[dict], namespace: str) -> tuple[BM25Encoder, list[dict]]:
    """Fit BM25Encoder on corpus, return encoder + sparse vectors per document."""
    texts = [v["text"] for v in vectors]
    ids = [v["id"] for v in vectors]
    sources = [v["source"] for v in vectors]

    print(f"  Fitting BM25Encoder on {len(texts)} documents...")
    encoder = BM25Encoder()
    encoder.fit(texts)

    BM25_MODELS_DIR.mkdir(exist_ok=True)

    # Save corpus for local BM25 search at query time
    corpus_path = BM25_MODELS_DIR / f"{namespace}_corpus.json"
    with open(corpus_path, "w") as f:
        json.dump({"ids": ids, "texts": texts, "sources": sources}, f)
    print(f"  Saved corpus index to {corpus_path}")

    sparse_vectors = encoder.encode_documents(texts)
    return encoder, sparse_vectors


def upsert_with_sparse(index, vectors: list[dict], sparse_vectors: list[dict], namespace: str):
    """Upsert vectors with both dense and sparse values into the new index."""
    print(f"  Upserting {len(vectors)} vectors with dense + sparse to '{namespace}'...")
    batch_size = 100
    upserted = 0
    for i in range(0, len(vectors), batch_size):
        batch_vecs = vectors[i : i + batch_size]
        batch_sparse = sparse_vectors[i : i + batch_size]

        to_upsert = [
            {
                "id": v["id"],
                "values": v["values"],
                "sparse_values": {
                    "indices": s["indices"],
                    "values": s["values"],
                },
                "metadata": v["metadata"],
            }
            for v, s in zip(batch_vecs, batch_sparse)
        ]
        index.upsert(vectors=to_upsert, namespace=namespace)
        upserted += len(batch_vecs)

    print(f"  Upserted {upserted} vectors")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Show plan without making changes")
    args = parser.parse_args()

    pc = Pinecone(api_key=os.environ["PINECONE_API_KEY"])

    # --- Step 1: Fetch everything from the existing cosine index ---
    print(f"\n{'[DRY RUN] ' if args.dry_run else ''}Step 1: Fetching all vectors from cosine index")
    old_index = pc.Index(PINECONE_INDEX_NAME)
    stats = old_index.describe_index_stats()

    all_namespace_data: dict[str, list[dict]] = {}
    total_vectors = 0
    for namespace in NAMESPACES:
        ns_stats = stats.namespaces.get(namespace, {})
        count = ns_stats.get("vector_count", 0)
        if count == 0:
            print(f"  '{namespace}': empty, skipping")
            continue
        print(f"\n  Namespace: {namespace} ({count} vectors)")
        vectors = fetch_namespace(old_index, namespace)
        if vectors:
            all_namespace_data[namespace] = vectors
            total_vectors += len(vectors)

    print(f"\nTotal vectors to migrate: {total_vectors}")

    if args.dry_run:
        print("\n[DRY RUN] Would delete cosine index, create dotproduct index, and re-upsert.")
        print("Run without --dry-run to execute.")
        return

    # --- Step 2: Build BM25 sparse vectors for each namespace ---
    print("\nStep 2: Fitting BM25 and generating sparse vectors")
    namespace_sparse: dict[str, list[dict]] = {}
    for namespace, vectors in all_namespace_data.items():
        print(f"\n  Namespace: {namespace}")
        _, sparse = build_bm25_and_sparse(vectors, namespace)
        namespace_sparse[namespace] = sparse

    # --- Step 3: Delete cosine index ---
    print(f"\nStep 3: Deleting cosine index '{PINECONE_INDEX_NAME}'...")
    pc.delete_index(PINECONE_INDEX_NAME)
    print("  Deleted. Waiting for deletion to complete...")
    time.sleep(10)

    # --- Step 4: Create new dotproduct index ---
    print(f"\nStep 4: Creating dotproduct index '{PINECONE_INDEX_NAME}'...")
    pc.create_index(
        name=PINECONE_INDEX_NAME,
        dimension=DIMENSION,
        metric="dotproduct",
        spec=ServerlessSpec(cloud=CLOUD, region=REGION),
    )

    print("  Waiting for index to be ready...")
    while not pc.describe_index(PINECONE_INDEX_NAME).status["ready"]:
        time.sleep(3)
    print("  Index ready.")

    # --- Step 5: Re-upsert all namespaces with dense + sparse ---
    print("\nStep 5: Upserting vectors with dense + sparse values")
    new_index = pc.Index(PINECONE_INDEX_NAME)
    for namespace, vectors in all_namespace_data.items():
        print(f"\n  Namespace: {namespace}")
        upsert_with_sparse(new_index, vectors, namespace_sparse[namespace], namespace)

    print("\nMigration complete.")
    print(f"Index '{PINECONE_INDEX_NAME}' now uses dotproduct metric with BM25 sparse vectors.")
    print("Run the evaluation next:")
    print("  python evaluate_cross_encoder.py --dataset sec --mode all")


if __name__ == "__main__":
    main()
