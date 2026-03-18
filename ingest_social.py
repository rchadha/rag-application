"""
Daily ingestion pipeline for news content.

Sources:
  - Finnhub (company news API)

Upserts to Pinecone namespace:
  - "news" (Finnhub articles)

Usage:
  python ingest_social.py --ticker NVDA --company "NVIDIA"
  python ingest_social.py --ticker AAPL --company "Apple" --days 3
"""

import argparse
import hashlib
import os
from datetime import datetime, timezone, timedelta

import requests
from dotenv import load_dotenv
from langchain_core.documents import Document
from langchain_openai import OpenAIEmbeddings
from langchain_pinecone import PineconeVectorStore
from pinecone import Pinecone
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

load_dotenv()

PINECONE_INDEX_NAME = os.environ.get("PINECONE_INDEX_NAME", "rag-application")
EMBEDDING_MODEL_NAME = "text-embedding-3-small"
NEWS_NAMESPACE = "news"

_analyzer = None


def _get_sentiment_analyzer() -> SentimentIntensityAnalyzer:
    global _analyzer
    if _analyzer is None:
        _analyzer = SentimentIntensityAnalyzer()
    return _analyzer


def _sentiment_label(compound: float) -> str:
    if compound >= 0.05:
        return "positive"
    if compound <= -0.05:
        return "negative"
    return "neutral"


def _score_sentiment(text: str) -> dict:
    analyzer = _get_sentiment_analyzer()
    scores = analyzer.polarity_scores(text)
    return {
        "sentiment_compound": scores["compound"],
        "sentiment_label": _sentiment_label(scores["compound"]),
    }


def _make_id(*parts: str) -> str:
    """Deterministic MD5 ID to avoid duplicate upserts."""
    return hashlib.md5("|".join(parts).encode()).hexdigest()


# ---------------------------------------------------------------------------
# Finnhub News
# ---------------------------------------------------------------------------

def fetch_finnhub_news(ticker: str, company: str, days: int = 1) -> list[Document]:
    api_key = os.environ.get("FINNHUB_API_KEY", "")
    if not api_key:
        print("Warning: FINNHUB_API_KEY not set, skipping news ingestion")
        return []

    today = datetime.now(timezone.utc).date()
    from_date = (today - timedelta(days=days)).isoformat()
    to_date = today.isoformat()

    url = "https://finnhub.io/api/v1/company-news"
    params = {"symbol": ticker, "from": from_date, "to": to_date, "token": api_key}

    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        articles = response.json()
    except Exception as e:
        print(f"Warning: Finnhub fetch failed for {ticker}: {e}")
        return []

    docs = []
    for article in articles:
        headline = article.get("headline", "").strip()
        summary = article.get("summary", "").strip()
        text = f"{headline}\n\n{summary}".strip() if summary else headline
        if not text:
            continue

        article_id = str(article.get("id", ""))
        published_at = datetime.fromtimestamp(
            article.get("datetime", 0), tz=timezone.utc
        ).isoformat()

        sentiment = _score_sentiment(text)
        doc = Document(
            page_content=text,
            metadata={
                "source": f"finnhub/{ticker}/{article_id}",
                "ticker": ticker.upper(),
                "company": company,
                "platform": "finnhub",
                "article_id": article_id,
                "url": article.get("url", ""),
                "publisher": article.get("source", ""),
                "published_at": published_at,
                **sentiment,
            },
        )
        docs.append(doc)

    print(f"Fetched {len(docs)} Finnhub news articles for {ticker}")
    return docs


# ---------------------------------------------------------------------------
# Upsert to Pinecone
# ---------------------------------------------------------------------------

def upsert_documents(docs: list[Document], namespace: str) -> None:
    if not docs:
        print(f"No documents to upsert to namespace '{namespace}'")
        return

    texts = [doc.page_content for doc in docs]
    metadatas = [doc.metadata for doc in docs]
    ids = [_make_id(namespace, meta.get("source", str(i))) for i, meta in enumerate(metadatas)]

    # Check which IDs already exist in Pinecone before generating embeddings
    pc = Pinecone(api_key=os.environ["PINECONE_API_KEY"])
    index = pc.Index(PINECONE_INDEX_NAME)
    fetch_response = index.fetch(ids=ids, namespace=namespace)
    existing_ids = set(fetch_response.vectors.keys())

    new_indices = [i for i, id_ in enumerate(ids) if id_ not in existing_ids]
    if not new_indices:
        print(f"All {len(docs)} documents already exist in namespace '{namespace}', skipping embeddings")
        return

    skipped = len(docs) - len(new_indices)
    if skipped:
        print(f"Skipping {skipped} already-indexed documents, embedding {len(new_indices)} new ones")

    new_texts = [texts[i] for i in new_indices]
    new_metadatas = [metadatas[i] for i in new_indices]
    new_ids = [ids[i] for i in new_indices]

    embedding_fn = OpenAIEmbeddings(model=EMBEDDING_MODEL_NAME)
    store = PineconeVectorStore(
        index_name=PINECONE_INDEX_NAME,
        namespace=namespace,
        embedding=embedding_fn,
    )
    store.add_texts(texts=new_texts, metadatas=new_metadatas, ids=new_ids)
    print(f"Upserted {len(new_ids)} new documents to namespace '{namespace}'")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Ingest news data into Pinecone")
    parser.add_argument("--ticker", required=True, help="Stock ticker symbol (e.g. NVDA)")
    parser.add_argument("--company", required=True, help="Company name (e.g. NVIDIA)")
    parser.add_argument("--days", type=int, default=1, help="How many days back to fetch (default: 1)")
    args = parser.parse_args()

    ticker = args.ticker.upper()
    company = args.company
    days = args.days

    print(f"\n=== Ingesting news for {ticker} ({company}), last {days} day(s) ===\n")

    news_docs = fetch_finnhub_news(ticker, company, days=days)
    upsert_documents(news_docs, NEWS_NAMESPACE)

    print(f"\nDone. {len(news_docs)} news articles ingested.")


if __name__ == "__main__":
    main()
