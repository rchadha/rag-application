#!/usr/bin/env python3
"""
Download NVIDIA narrative filing text (10-K, 10-Q, 8-K) for the last year.

Outputs:
    sec_filings_nvda/
        2025-05-28_10-Q_0001045810-25-0000xx.txt
        ...

Usage:
    python download_nvda_filings.py
"""

from __future__ import annotations

import json
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional

import requests
from bs4 import BeautifulSoup

# --- CONFIG ---
TICKER = "NVDA"
FORMS_TO_KEEP = {"10-K", "10-Q", "8-K"}
LOOKBACK_DAYS = 365
OUTPUT_DIR = Path("sec_filings_nvda")

# Replace with your real org/email to comply with SEC guidance.
HEADERS = {
    "User-Agent": "MyRagApp dev@example.com",
    "Accept-Encoding": "gzip, deflate",
}

SEC_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SEC_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
SEC_ARCHIVES_BASE = "https://www.sec.gov/Archives/edgar/data"


def get_json(url: str) -> dict:
    resp = requests.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    return resp.json()


def normalize_whitespace(text: str) -> str:
    text = text.replace("\xa0", " ")
    text = re.sub(r"\r", "\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def ticker_to_cik(ticker: str) -> str:
    data = get_json(SEC_TICKERS_URL)
    ticker = ticker.upper()

    for _, record in data.items():
        if record.get("ticker", "").upper() == ticker:
            return str(record["cik_str"]).zfill(10)

    raise ValueError(f"Ticker not found in SEC mapping: {ticker}")


def load_company_submissions(cik: str) -> dict:
    return get_json(SEC_SUBMISSIONS_URL.format(cik=cik))


def build_filing_url(cik: str, accession_number: str, primary_document: str) -> str:
    cik_no_leading_zeros = str(int(cik))
    accession_no_dashes = accession_number.replace("-", "")
    return f"{SEC_ARCHIVES_BASE}/{cik_no_leading_zeros}/{accession_no_dashes}/{primary_document}"


def parse_recent_filings(submissions: dict) -> List[Dict]:
    recent = submissions.get("filings", {}).get("recent", {})
    keys = [
        "accessionNumber",
        "filingDate",
        "form",
        "primaryDocument",
        "primaryDocDescription",
    ]

    row_count = len(recent.get("accessionNumber", []))
    filings = []
    for i in range(row_count):
        filing = {k: recent.get(k, [None] * row_count)[i] for k in keys}
        filings.append(filing)
    return filings


def filter_last_year_filings(filings: List[Dict], forms_to_keep: set[str], lookback_days: int) -> List[Dict]:
    cutoff = datetime.now(timezone.utc).date() - timedelta(days=lookback_days)
    kept = []

    for filing in filings:
        form = filing.get("form")
        filing_date_str = filing.get("filingDate")
        primary_document = filing.get("primaryDocument")

        if form not in forms_to_keep:
            continue
        if not filing_date_str or not primary_document:
            continue

        filing_date = datetime.strptime(filing_date_str, "%Y-%m-%d").date()
        if filing_date >= cutoff:
            kept.append(filing)

    return kept


def html_to_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")

    # Remove scripts/styles and some boilerplate elements
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    text = soup.get_text("\n")
    return normalize_whitespace(text)


def safe_filename(value: str) -> str:
    return re.sub(r'[^A-Za-z0-9._-]+', "_", value)


def download_filing_text(url: str) -> str:
    resp = requests.get(url, headers=HEADERS, timeout=60)
    resp.raise_for_status()

    content_type = resp.headers.get("Content-Type", "").lower()
    body = resp.text

    # Most primary documents are HTML, but this still works reasonably for plain text.
    if "html" in content_type or "<html" in body[:1000].lower():
        return html_to_text(body)
    return normalize_whitespace(body)


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print(f"Resolving ticker {TICKER} -> CIK ...")
    cik = ticker_to_cik(TICKER)
    print(f"CIK: {cik}")

    print("Loading company submissions ...")
    submissions = load_company_submissions(cik)
    company_name = submissions.get("name", TICKER)

    filings = parse_recent_filings(submissions)
    filings = filter_last_year_filings(filings, FORMS_TO_KEEP, LOOKBACK_DAYS)

    print(f"Found {len(filings)} filings in the last {LOOKBACK_DAYS} days.")

    manifest = []

    for filing in filings:
        accession = filing["accessionNumber"]
        filing_date = filing["filingDate"]
        form = filing["form"]
        primary_document = filing["primaryDocument"]

        filing_url = build_filing_url(cik, accession, primary_document)
        print(f"Downloading {filing_date} {form} {filing_url}")

        try:
            text = download_filing_text(filing_url)

            filename = safe_filename(f"{filing_date}_{form}_{accession}.txt")
            output_path = OUTPUT_DIR / filename

            header = (
                f"Company: {company_name}\n"
                f"Ticker: {TICKER}\n"
                f"CIK: {cik}\n"
                f"Form: {form}\n"
                f"Filing date: {filing_date}\n"
                f"Accession number: {accession}\n"
                f"Source URL: {filing_url}\n"
                f"{'=' * 80}\n\n"
            )

            output_path.write_text(header + text, encoding="utf-8")

            manifest.append(
                {
                    "company": company_name,
                    "ticker": TICKER,
                    "cik": cik,
                    "form": form,
                    "filing_date": filing_date,
                    "accession_number": accession,
                    "primary_document": primary_document,
                    "source_url": filing_url,
                    "output_file": str(output_path),
                }
            )

            # Be polite to SEC infrastructure.
            time.sleep(0.3)

        except Exception as e:
            print(f"Failed for {accession}: {e}")

    manifest_path = OUTPUT_DIR / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    print(f"\nDone. Saved files to: {OUTPUT_DIR.resolve()}")
    print(f"Manifest: {manifest_path.resolve()}")


if __name__ == "__main__":
    main()