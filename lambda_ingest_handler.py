"""
AWS Lambda handler for scheduled social media and news ingestion.

Triggered by EventBridge Scheduler on a daily cron.
Reads which companies to ingest from the INGEST_TICKERS environment variable
or from the EventBridge event payload.

Environment variables (set in Terraform):
  INGEST_TICKERS   - JSON array of {ticker, company} objects
                     e.g. '[{"ticker":"NVDA","company":"NVIDIA"},{"ticker":"AMD","company":"AMD"}]'
  INGEST_DAYS      - How many days back to fetch (default: 1)
  INGEST_SOURCES   - Comma-separated sources: news,reddit (default: all)
  PROJECT_NAME     - Used to build Secrets Manager paths (default: rag-application)
  AWS_REGION       - AWS region for Secrets Manager (default: us-east-1)

Secrets Manager (fetched at runtime):
  {PROJECT_NAME}/openai-api-key
  {PROJECT_NAME}/pinecone-api-key
  {PROJECT_NAME}/finnhub-api-key

EventBridge event payload (optional — overrides env vars):
  {
    "tickers": [{"ticker": "NVDA", "company": "NVIDIA"}],
    "days": 1,
    "sources": "news,reddit"
  }
"""

import json
import os

import boto3
from botocore.exceptions import ClientError

from ingest_social import run_ingestion

_secrets_loaded = False


def _load_secrets() -> None:
    """Fetch API keys from Secrets Manager on first invocation."""
    global _secrets_loaded
    if _secrets_loaded:
        return

    project = os.environ.get("PROJECT_NAME", "rag-application")
    region = os.environ.get("AWS_REGION", "us-east-1")
    client = boto3.client("secretsmanager", region_name=region)

    secret_map = {
        f"{project}/openai-api-key": "OPENAI_API_KEY",
        f"{project}/pinecone-api-key": "PINECONE_API_KEY",
        f"{project}/finnhub-api-key": "FINNHUB_API_KEY",
    }

    for secret_name, env_key in secret_map.items():
        if os.environ.get(env_key):
            continue
        try:
            response = client.get_secret_value(SecretId=secret_name)
            secret = response.get("SecretString", "")
            try:
                os.environ[env_key] = json.loads(secret)
            except (json.JSONDecodeError, TypeError):
                os.environ[env_key] = secret
        except ClientError as e:
            print(f"Warning: could not fetch secret {secret_name}: {e}")

    _secrets_loaded = True


def _default_tickers() -> list[dict]:
    """Parse INGEST_TICKERS env var, falling back to NVDA."""
    raw = os.environ.get("INGEST_TICKERS", "")
    if raw:
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            print(f"Warning: INGEST_TICKERS is not valid JSON: {raw!r}")
    return [{"ticker": "NVDA", "company": "NVIDIA"}]


def handler(event: dict, context) -> dict:
    """
    Lambda entrypoint.

    EventBridge passes the schedule event; the payload can optionally
    contain tickers/days/sources overrides.
    """
    _load_secrets()

    # Allow EventBridge payload to override env defaults
    tickers = event.get("tickers") or _default_tickers()
    days = int(event.get("days") or os.environ.get("INGEST_DAYS", "1"))
    sources_raw = event.get("sources") or os.environ.get("INGEST_SOURCES", "news,reddit")
    sources = [s.strip() for s in sources_raw.split(",") if s.strip()]

    print(f"Ingestion job starting — tickers: {tickers}, days: {days}, sources: {sources}")

    total_indexed = 0
    results = {}
    errors = []

    for entry in tickers:
        ticker = entry.get("ticker", "").upper()
        company = entry.get("company", ticker)
        if not ticker:
            continue
        try:
            counts = run_ingestion(ticker, company, days=days, sources=sources)
            results[ticker] = counts
            total_indexed += sum(counts.values())
        except Exception as e:
            print(f"Error ingesting {ticker}: {e}")
            errors.append({"ticker": ticker, "error": str(e)})

    summary = {
        "tickers_processed": len(results),
        "total_new_documents": total_indexed,
        "results": results,
    }
    if errors:
        summary["errors"] = errors

    print(f"Ingestion complete: {summary}")
    return summary
