"""
Daily ingestion pipeline for news and social media content.

Sources:
  - Finnhub     → company news articles         → namespace "news"
  - Reddit      → posts from finance subreddits  → namespace "social"

Reddit uses the public JSON API (no credentials required, ~60 req/min limit).

Usage:
  python ingest_social.py --ticker NVDA --company "NVIDIA"
  python ingest_social.py --ticker AAPL --company "Apple" --days 3
  python ingest_social.py --ticker MSFT --company "Microsoft" --sources reddit
  python ingest_social.py --ticker NVDA --company "NVIDIA" --sources news,reddit

Cron / Lambda:
  Fully self-contained, exits with code 0 on success.
  Required env vars: OPENAI_API_KEY, PINECONE_API_KEY
  Optional env vars: FINNHUB_API_KEY (for news source)
"""

import argparse
import hashlib
import os
import time
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
SOCIAL_NAMESPACE = "social"

REDDIT_USER_AGENT = "rag-application/1.0 (financial research tool)"
REDDIT_FINANCE_SUBREDDITS = [
    "investing",
    "stocks",
    "wallstreetbets",
    "SecurityAnalysis",
    "StockMarket",
]

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
        "sentiment_compound": round(scores["compound"], 4),
        "sentiment_label": _sentiment_label(scores["compound"]),
    }


def _make_id(*parts: str) -> str:
    """Deterministic MD5 ID — prevents duplicate upserts on re-runs."""
    return hashlib.md5("|".join(parts).encode()).hexdigest()


# ---------------------------------------------------------------------------
# Finnhub News
# ---------------------------------------------------------------------------

def fetch_finnhub_news(ticker: str, company: str, days: int = 1) -> list[Document]:
    api_key = os.environ.get("FINNHUB_API_KEY", "")
    if not api_key:
        print("  FINNHUB_API_KEY not set — skipping Finnhub news")
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
        print(f"  Warning: Finnhub fetch failed for {ticker}: {e}")
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
        docs.append(Document(
            page_content=text,
            metadata={
                "source": f"finnhub/{ticker}/{article_id}",
                "ticker": ticker,
                "company": company,
                "platform": "finnhub",
                "article_id": article_id,
                "url": article.get("url", ""),
                "publisher": article.get("source", ""),
                "published_at": published_at,
                **sentiment,
            },
        ))

    print(f"  Fetched {len(docs)} Finnhub news articles for {ticker}")
    return docs


# ---------------------------------------------------------------------------
# Reddit (public JSON API — no credentials required)
# ---------------------------------------------------------------------------

def _fetch_subreddit_posts(subreddit: str, query: str, time_filter: str = "week") -> list[dict]:
    """Fetch posts from a subreddit matching a search query."""
    url = f"https://www.reddit.com/r/{subreddit}/search.json"
    params = {
        "q": query,
        "sort": "new",
        "limit": 25,
        "t": time_filter,
        "restrict_sr": "on",
    }
    headers = {"User-Agent": REDDIT_USER_AGENT}

    try:
        response = requests.get(url, params=params, headers=headers, timeout=10)
        response.raise_for_status()
        return response.json().get("data", {}).get("children", [])
    except Exception as e:
        print(f"  Warning: Reddit fetch failed for r/{subreddit}: {e}")
        return []


def fetch_reddit_posts(ticker: str, company: str, days: int = 1) -> list[Document]:
    """
    Fetch recent Reddit posts mentioning the ticker across finance subreddits.
    Uses the public Reddit JSON API — no auth required.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    time_filter = "day" if days <= 1 else "week" if days <= 7 else "month"

    # Deduplicate across subreddits by post ID
    seen_ids: set[str] = set()
    docs: list[Document] = []

    for subreddit in REDDIT_FINANCE_SUBREDDITS:
        posts = _fetch_subreddit_posts(subreddit, ticker, time_filter=time_filter)
        time.sleep(0.5)  # Respect Reddit rate limits (~60 req/min)

        for post in posts:
            data = post.get("data", {})
            post_id = data.get("id", "")
            if not post_id or post_id in seen_ids:
                continue

            # Filter by recency
            created_utc = data.get("created_utc", 0)
            created_at = datetime.fromtimestamp(created_utc, tz=timezone.utc)
            if created_at < cutoff:
                continue

            title = data.get("title", "").strip()
            selftext = data.get("selftext", "").strip()
            # Strip Reddit's [removed] placeholder text
            if selftext in ("[removed]", "[deleted]"):
                selftext = ""
            text = f"{title}\n\n{selftext}".strip() if selftext else title
            if not text:
                continue

            seen_ids.add(post_id)
            sentiment = _score_sentiment(text)
            docs.append(Document(
                page_content=text,
                metadata={
                    "source": f"reddit/{post_id}",
                    "ticker": ticker,
                    "company": company,
                    "platform": "reddit",
                    "post_id": post_id,
                    "subreddit": f"r/{subreddit}",
                    "url": f"https://www.reddit.com{data.get('permalink', '')}",
                    "author": data.get("author", ""),
                    "upvotes": data.get("score", 0),
                    "num_comments": data.get("num_comments", 0),
                    "published_at": created_at.isoformat(),
                    **sentiment,
                },
            ))

    print(f"  Fetched {len(docs)} Reddit posts for {ticker} across {len(REDDIT_FINANCE_SUBREDDITS)} subreddits")
    return docs


# ---------------------------------------------------------------------------
# Upsert to Pinecone (with deduplication)
# ---------------------------------------------------------------------------

def upsert_documents(docs: list[Document], namespace: str) -> int:
    """Upsert documents to Pinecone, skipping any that already exist. Returns count upserted."""
    if not docs:
        print(f"  No documents to upsert to namespace '{namespace}'")
        return 0

    texts = [doc.page_content for doc in docs]
    metadatas = [doc.metadata for doc in docs]
    ids = [_make_id(namespace, meta.get("source", str(i))) for i, meta in enumerate(metadatas)]

    # Pre-check existing IDs to avoid paying for redundant embeddings
    pc = Pinecone(api_key=os.environ["PINECONE_API_KEY"])
    index = pc.Index(PINECONE_INDEX_NAME)
    fetch_response = index.fetch(ids=ids, namespace=namespace)
    existing_ids = set(fetch_response.vectors.keys())

    new_indices = [i for i, id_ in enumerate(ids) if id_ not in existing_ids]
    if not new_indices:
        print(f"  All {len(docs)} documents already indexed in '{namespace}', skipping")
        return 0

    skipped = len(docs) - len(new_indices)
    if skipped:
        print(f"  Skipping {skipped} already-indexed, embedding {len(new_indices)} new docs")

    new_texts = [texts[i] for i in new_indices]
    new_metadatas = [metadatas[i] for i in new_indices]
    new_ids = [ids[i] for i in new_indices]

    store = PineconeVectorStore(
        index_name=PINECONE_INDEX_NAME,
        namespace=namespace,
        embedding=OpenAIEmbeddings(model=EMBEDDING_MODEL_NAME),
    )
    store.add_texts(texts=new_texts, metadatas=new_metadatas, ids=new_ids)
    print(f"  Upserted {len(new_ids)} new documents to namespace '{namespace}'")
    return len(new_ids)


# ---------------------------------------------------------------------------
# Entrypoint (also importable as a module for Lambda/cron wrappers)
# ---------------------------------------------------------------------------

def run_ingestion(ticker: str, company: str, days: int = 1, sources: list | None = None) -> dict:
    """
    Run ingestion for a single company. Returns counts per source.
    Safe to call from another script or Lambda handler.
    """
    if sources is None:
        sources = ["news", "reddit"]

    ticker = ticker.upper()
    results = {}

    print(f"\n=== {ticker} ({company}) | last {days} day(s) | sources: {', '.join(sources)} ===")

    if "news" in sources:
        print("\n[Finnhub News]")
        news_docs = fetch_finnhub_news(ticker, company, days=days)
        results["news"] = upsert_documents(news_docs, NEWS_NAMESPACE)

    if "reddit" in sources:
        print("\n[Reddit]")
        reddit_docs = fetch_reddit_posts(ticker, company, days=days)
        results["reddit"] = upsert_documents(reddit_docs, SOCIAL_NAMESPACE)

    return results


def main():
    parser = argparse.ArgumentParser(description="Ingest news and social data into Pinecone")
    parser.add_argument("--ticker", required=True, help="Stock ticker (e.g. NVDA)")
    parser.add_argument("--company", required=True, help="Company name (e.g. NVIDIA)")
    parser.add_argument("--days", type=int, default=1, help="Days back to fetch (default: 1)")
    parser.add_argument(
        "--sources",
        default="news,reddit",
        help="Comma-separated sources: news,reddit (default: all)",
    )
    args = parser.parse_args()

    sources = [s.strip() for s in args.sources.split(",") if s.strip()]
    counts = run_ingestion(args.ticker, args.company, days=args.days, sources=sources)

    total = sum(counts.values())
    print(f"\nDone. {total} new documents indexed: {counts}")


if __name__ == "__main__":
    main()
