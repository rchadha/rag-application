import os
import re
from typing import Any

from dotenv import load_dotenv
from langchain_pinecone import PineconeVectorStore
from langchain_openai import OpenAIEmbeddings

try:
    from sentence_transformers import CrossEncoder
    _RERANKER_AVAILABLE = True
except ImportError:
    _RERANKER_AVAILABLE = False

load_dotenv()

PINECONE_INDEX_NAME = os.environ.get("PINECONE_INDEX_NAME", "rag-application")
EMBEDDING_MODEL_NAME = "text-embedding-3-small"
CROSS_ENCODER_MODEL_NAME = os.getenv(
    "CROSS_ENCODER_MODEL_NAME",
    "BAAI/bge-reranker-base",
)

COLLECTIONS = {
    "sec": "sec_filings_nvda",
    "earnings": "earnings_calls_nvda",
    "social": "social",
    "news": "news",
}

_reranker = None


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


def retrieve_candidates(query_text: str, dataset: str = "sec", candidate_k: int = 10):
    db = PineconeVectorStore(
        index_name=PINECONE_INDEX_NAME,
        namespace=get_collection_name(dataset),
        embedding=_get_embedding_function(),
    )
    results = db.similarity_search_with_relevance_scores(query_text, k=candidate_k)

    candidates = []
    for rank, (doc, score) in enumerate(results, start=1):
        candidates.append(
            {
                "rank": rank,
                "doc": doc,
                "source": doc.metadata.get("source", "unknown"),
                "content": normalize_text(doc.page_content),
                "vector_score": float(score),
            }
        )
    return candidates


def rerank_candidates(query_text: str, candidates: list[dict], final_k: int = 3):
    if not candidates:
        return []

    reranker = _get_reranker()
    pairs = [(query_text, candidate["content"]) for candidate in candidates]
    rerank_scores = reranker.predict(pairs)

    reranked = []
    for candidate, rerank_score in zip(candidates, rerank_scores):
        updated = dict(candidate)
        updated["rerank_score"] = float(rerank_score)
        reranked.append(updated)

    reranked.sort(key=lambda item: item["rerank_score"], reverse=True)
    return reranked[:final_k]


def get_top_results(
    query_text: str,
    dataset: str = "sec",
    candidate_k: int = 10,
    final_k: int = 3,
    use_reranker: bool = False,
):
    candidates = retrieve_candidates(query_text, dataset=dataset, candidate_k=candidate_k)
    if use_reranker:
        return rerank_candidates(query_text, candidates, final_k=final_k)
    return candidates[:final_k]
