import json
import os
import pickle
import re
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from langchain_pinecone import PineconeVectorStore
from langchain_openai import OpenAIEmbeddings

try:
    from sentence_transformers import CrossEncoder
    _RERANKER_AVAILABLE = True
except ImportError:
    _RERANKER_AVAILABLE = False

try:
    from rank_bm25 import BM25Okapi
    _BM25_AVAILABLE = True
except ImportError:
    _BM25_AVAILABLE = False

load_dotenv()

PINECONE_INDEX_NAME = os.environ.get("PINECONE_INDEX_NAME", "rag-application")
EMBEDDING_MODEL_NAME = "text-embedding-3-small"
CROSS_ENCODER_MODEL_NAME = os.getenv("CROSS_ENCODER_MODEL_NAME", "BAAI/bge-reranker-base")
BM25_MODELS_DIR = Path("bm25_models")

COLLECTIONS = {
    "sec": "sec_filings_nvda",
    "earnings": "earnings_calls_nvda",
    "social": "social",
    "news": "news",
}

_reranker = None
_bm25_indexes: dict[str, tuple] = {}  # namespace → (BM25Okapi, ids, texts)


def normalize_text(text: Any) -> str:
    if isinstance(text, list):
        text = " ".join(text)
    return re.sub(r"\s+", " ", str(text)).strip()


def get_collection_name(dataset: str) -> str:
    return COLLECTIONS.get(dataset, COLLECTIONS["sec"])


def _get_embedding_function() -> OpenAIEmbeddings:
    return OpenAIEmbeddings(model=EMBEDDING_MODEL_NAME)


def _get_reranker():
    global _reranker
    if not _RERANKER_AVAILABLE:
        raise ImportError("sentence-transformers is not installed. Run: pip install sentence-transformers")
    if _reranker is None:
        _reranker = CrossEncoder(CROSS_ENCODER_MODEL_NAME)
    return _reranker


def _get_bm25_index(namespace: str) -> tuple:
    """
    Load BM25 index for a namespace. Returns (BM25Okapi, sources_list, texts_list).
    Requires patch_sparse_vectors.py to have been run first.
    """
    if not _BM25_AVAILABLE:
        raise ImportError("rank_bm25 is not installed. Run: pip install rank_bm25")

    if namespace not in _bm25_indexes:
        corpus_path = BM25_MODELS_DIR / f"{namespace}_corpus.json"
        if not corpus_path.exists():
            raise FileNotFoundError(
                f"BM25 corpus not found at {corpus_path}. "
                f"Run: python patch_sparse_vectors.py --namespace {namespace}"
            )
        with open(corpus_path) as f:
            corpus = json.load(f)

        texts = corpus["texts"]
        sources = corpus.get("sources", corpus["ids"])  # fall back to ids if sources missing
        tokenized = [t.lower().split() for t in texts]
        bm25 = BM25Okapi(tokenized)
        _bm25_indexes[namespace] = (bm25, sources, texts)

    return _bm25_indexes[namespace]


# ---------------------------------------------------------------------------
# Retrieval modes
# ---------------------------------------------------------------------------

def retrieve_candidates(query_text: str, dataset: str = "sec", candidate_k: int = 10):
    """Dense-only retrieval via Pinecone vector similarity."""
    db = PineconeVectorStore(
        index_name=PINECONE_INDEX_NAME,
        namespace=get_collection_name(dataset),
        embedding=_get_embedding_function(),
    )
    results = db.similarity_search_with_relevance_scores(query_text, k=candidate_k)

    candidates = []
    for rank, (doc, score) in enumerate(results, start=1):
        candidates.append({
            "rank": rank,
            "doc": doc,
            "source": doc.metadata.get("source", "unknown"),
            "content": normalize_text(doc.page_content),
            "vector_score": float(score),
        })
    return candidates


def retrieve_bm25_candidates(query_text: str, dataset: str = "sec", candidate_k: int = 10):
    """
    BM25 keyword search over the local corpus saved by patch_sparse_vectors.py.
    Returns candidates in the same shape as retrieve_candidates().
    """
    namespace = get_collection_name(dataset)
    bm25, sources, texts = _get_bm25_index(namespace)

    tokenized_query = query_text.lower().split()
    scores = bm25.get_scores(tokenized_query)

    top_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:candidate_k]

    candidates = []
    for rank, idx in enumerate(top_indices, start=1):
        candidates.append({
            "rank": rank,
            "source": sources[idx],
            "content": normalize_text(texts[idx]),
            "bm25_score": float(scores[idx]),
        })
    return candidates


def _reciprocal_rank_fusion(
    dense_results: list[dict],
    bm25_results: list[dict],
    k: int = 60,
    top_n: int = 10,
) -> list[dict]:
    """
    Merge two ranked lists using Reciprocal Rank Fusion (RRF).

    RRF score = Σ 1/(k + rank_i)  where k=60 is the standard smoothing constant.

    A document ranked #1 in both lists scores higher than one ranked #1 in only
    one list — it rewards consistent agreement across retrievers. Documents that
    appear in only one list still contribute their single-list RRF score.
    """
    rrf_scores: dict[str, float] = {}
    doc_data: dict[str, dict] = {}

    # Index dense results by source (the authoritative document identifier)
    for rank, doc in enumerate(dense_results, start=1):
        key = doc["source"]
        rrf_scores[key] = rrf_scores.get(key, 0) + 1 / (k + rank)
        doc_data[key] = dict(doc, dense_rank=rank)

    # Merge BM25 results — add to score if already seen, else create new entry
    for rank, doc in enumerate(bm25_results, start=1):
        key = doc["source"]
        rrf_scores[key] = rrf_scores.get(key, 0) + 1 / (k + rank)
        if key in doc_data:
            doc_data[key]["bm25_rank"] = rank
            doc_data[key]["bm25_score"] = doc.get("bm25_score")
        else:
            doc_data[key] = dict(doc, bm25_rank=rank)

    merged = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)[:top_n]
    results = []
    for new_rank, (key, rrf_score) in enumerate(merged, start=1):
        entry = dict(doc_data[key])
        entry["rank"] = new_rank
        entry["rrf_score"] = round(rrf_score, 6)
        results.append(entry)

    return results


def retrieve_hybrid_candidates(
    query_text: str,
    dataset: str = "sec",
    candidate_k: int = 10,
):
    """
    Hybrid retrieval: merge dense (semantic) + BM25 (keyword) results via RRF.

    Neither retriever alone sees the full picture:
    - Dense search excels at semantic/intent matching
    - BM25 excels at exact keyword matching (ticker symbols, proper nouns, dates)
    RRF rewards documents that rank highly in both, surfacing the most
    consistently relevant results.
    """
    dense = retrieve_candidates(query_text, dataset=dataset, candidate_k=candidate_k)
    bm25 = retrieve_bm25_candidates(query_text, dataset=dataset, candidate_k=candidate_k)
    return _reciprocal_rank_fusion(dense, bm25, top_n=candidate_k)


def rerank_candidates(query_text: str, candidates: list[dict], final_k: int = 3):
    """Cross-encoder reranking: evaluates (query, chunk) pairs for precise relevance."""
    if not candidates:
        return []

    reranker = _get_reranker()
    pairs = [(query_text, candidate["content"]) for candidate in candidates]
    rerank_scores = reranker.predict(pairs)

    reranked = [dict(c, rerank_score=float(s)) for c, s in zip(candidates, rerank_scores)]
    reranked.sort(key=lambda item: item["rerank_score"], reverse=True)
    return reranked[:final_k]


def get_top_results(
    query_text: str,
    dataset: str = "sec",
    candidate_k: int = 10,
    final_k: int = 3,
    use_reranker: bool = False,
    use_hybrid: bool = False,
    hybrid_alpha: float = 0.75,  # kept for API compatibility, not used in RRF
):
    if use_hybrid:
        candidates = retrieve_hybrid_candidates(query_text, dataset=dataset, candidate_k=candidate_k)
    else:
        candidates = retrieve_candidates(query_text, dataset=dataset, candidate_k=candidate_k)

    if use_reranker:
        return rerank_candidates(query_text, candidates, final_k=final_k)
    return candidates[:final_k]
