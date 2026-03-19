import json
import os
import re
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from langchain_pinecone import PineconeVectorStore
from langchain_openai import OpenAIEmbeddings
from pinecone import Pinecone
from pinecone_text.sparse import BM25Encoder

try:
    from sentence_transformers import CrossEncoder
    _RERANKER_AVAILABLE = True
except ImportError:
    _RERANKER_AVAILABLE = False

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
_bm25_encoders: dict[str, BM25Encoder] = {}


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


def _get_bm25_encoder(namespace: str) -> BM25Encoder:
    """Load the fitted BM25Encoder for a namespace (cached in memory)."""
    if namespace not in _bm25_encoders:
        corpus_path = BM25_MODELS_DIR / f"{namespace}_corpus.json"
        if not corpus_path.exists():
            raise FileNotFoundError(
                f"BM25 corpus not found at {corpus_path}. "
                f"Run: python migrate_to_hybrid_index.py"
            )
        with open(corpus_path) as f:
            corpus = json.load(f)

        encoder = BM25Encoder()
        encoder.fit(corpus["texts"])
        _bm25_encoders[namespace] = encoder

    return _bm25_encoders[namespace]


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


def retrieve_hybrid_candidates(
    query_text: str,
    dataset: str = "sec",
    candidate_k: int = 10,
    alpha: float = 0.75,
):
    """
    Hybrid retrieval using Pinecone native sparse-dense search.

    Encodes the query with both:
      - OpenAI embeddings (dense) — captures semantic intent
      - BM25Encoder (sparse) — captures exact keyword matches

    alpha controls the blend sent to Pinecone:
      1.0 = pure dense, 0.0 = pure BM25, 0.75 = recommended starting point

    Requires dotproduct index (migrate_to_hybrid_index.py) with sparse vectors
    already stored alongside each dense vector.
    """
    namespace = get_collection_name(dataset)
    embedding_fn = _get_embedding_function()
    bm25 = _get_bm25_encoder(namespace)

    # Encode query with both models
    dense_vector = embedding_fn.embed_query(query_text)
    sparse_vector = bm25.encode_queries(query_text)

    # Scale by alpha — Pinecone adds the two scores at query time
    scaled_dense = [v * alpha for v in dense_vector]
    scaled_sparse = {
        "indices": sparse_vector["indices"],
        "values": [v * (1 - alpha) for v in sparse_vector["values"]],
    }

    pc = Pinecone(api_key=os.environ["PINECONE_API_KEY"])
    index = pc.Index(PINECONE_INDEX_NAME)
    response = index.query(
        vector=scaled_dense,
        sparse_vector=scaled_sparse,
        top_k=candidate_k,
        namespace=namespace,
        include_metadata=True,
    )

    candidates = []
    for rank, match in enumerate(response.matches, start=1):
        candidates.append({
            "rank": rank,
            "source": match.metadata.get("source", "unknown"),
            "content": normalize_text(match.metadata.get("text", "")),
            "vector_score": float(match.score),
        })
    return candidates


def rerank_candidates(query_text: str, candidates: list[dict], final_k: int = 3):
    """Cross-encoder reranking: scores each (query, chunk) pair together."""
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
    hybrid_alpha: float = 0.75,
):
    if use_hybrid:
        candidates = retrieve_hybrid_candidates(
            query_text, dataset=dataset, candidate_k=candidate_k, alpha=hybrid_alpha
        )
    else:
        candidates = retrieve_candidates(query_text, dataset=dataset, candidate_k=candidate_k)

    if use_reranker:
        return rerank_candidates(query_text, candidates, final_k=final_k)
    return candidates[:final_k]
