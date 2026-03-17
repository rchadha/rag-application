#!/usr/bin/env python3
"""
Download NVIDIA earnings call transcripts from Financial Modeling Prep.

Outputs:
    earnings_calls_nvda/
        2025-11-20_q3_earnings_call.txt
        ...

Usage:
    python download-earnings-calls.py
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()

TICKER = "NVDA"
OUTPUT_DIR = Path("earnings_calls_nvda")
DATES_API_URL = "https://financialmodelingprep.com/stable/earning-call-transcript-dates"
TRANSCRIPT_API_URL = "https://financialmodelingprep.com/stable/earning-call-transcript"
API_KEY_ENV = "FMP_API_KEY"


def normalize_whitespace(text: str) -> str:
    text = text.replace("\xa0", " ")
    text = re.sub(r"\r\n?", "\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def safe_filename(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", value)


def get_api_key() -> str:
    api_key = os.getenv(API_KEY_ENV)
    if not api_key:
        raise ValueError(f"Missing {API_KEY_ENV} in environment")
    return api_key


def get_json(url: str, params: dict):
    response = requests.get(url, params=params, timeout=60)
    response.raise_for_status()
    return response.json()


def fetch_transcript_dates(ticker: str, api_key: str):
    return get_json(
        DATES_API_URL,
        {
            "symbol": ticker,
            "apikey": api_key,
        },
    )


def fetch_transcript(ticker: str, year: int, quarter: int, api_key: str):
    return get_json(
        TRANSCRIPT_API_URL,
        {
            "symbol": ticker,
            "year": year,
            "quarter": quarter,
            "apikey": api_key,
        },
    )


def build_filename(call_date: str, quarter: int) -> str:
    return safe_filename(f"{call_date}_q{quarter}_earnings_call.txt")


def build_header(transcript: dict) -> str:
    return (
        f"Company: {transcript.get('symbol', TICKER)}\n"
        f"Ticker: {transcript.get('symbol', TICKER)}\n"
        f"Date: {transcript.get('date', 'unknown')}\n"
        f"Quarter: {transcript.get('quarter', 'unknown')}\n"
        f"Year: {transcript.get('year', 'unknown')}\n"
        f"{'=' * 80}\n\n"
    )


def main() -> None:
    api_key = get_api_key()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print(f"Loading earnings call dates for {TICKER}...")
    transcript_dates = fetch_transcript_dates(TICKER, api_key)
    print(f"Fetched {len(transcript_dates)} transcript date records")

    manifest = []

    for record in transcript_dates:
        year = record.get("year")
        quarter = record.get("quarter")
        call_date = record.get("date")

        if year is None or quarter is None or not call_date:
            continue

        print(f"Downloading transcript for {call_date} Q{quarter} {year}")
        transcript_payload = fetch_transcript(TICKER, int(year), int(quarter), api_key)

        if not transcript_payload:
            continue

        transcript = transcript_payload[0] if isinstance(transcript_payload, list) else transcript_payload
        content = normalize_whitespace(transcript.get("content", ""))
        if not content:
            continue

        filename = build_filename(call_date, int(quarter))
        output_path = OUTPUT_DIR / filename
        header = build_header(transcript)
        output_path.write_text(header + content, encoding="utf-8")

        manifest.append(
            {
                "ticker": transcript.get("symbol", TICKER),
                "date": call_date,
                "quarter": quarter,
                "year": year,
                "output_file": str(output_path),
            }
        )

        print(f"Saved {output_path.name}")

    manifest_path = OUTPUT_DIR / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    print(f"\nDone. Saved files to: {OUTPUT_DIR.resolve()}")
    print(f"Manifest: {manifest_path.resolve()}")


if __name__ == "__main__":
    main()
