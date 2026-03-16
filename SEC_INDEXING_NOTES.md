# SEC Indexing Notes

This document captures the SEC filing ingestion and indexing setup added to this project so it can be reviewed or extended later.

## Goal

Index downloaded NVIDIA SEC filings into Chroma without rebuilding the old AWS Lambda corpus.

## What Changed

### 1. SEC filings were downloaded and stored locally

Downloaded NVIDIA filings were moved into:

`data/sec_filings_nvda`

These include `.txt` versions of recent `10-K`, `10-Q`, and `8-K` filings plus a manifest file.

### 2. Chroma now uses a dedicated SEC collection

The project now indexes SEC data into a separate Chroma collection:

`sec_filings_nvda`

This keeps the SEC corpus logically separate from any past or future datasets.

### 3. Indexing now targets SEC `.txt` files

[create_database.py](/Users/rchadha/Documents/projects/p/rag-application/create_database.py) now:

- loads `.txt` files from `data/sec_filings_nvda`
- splits them into chunks
- adds metadata per chunk
- rebuilds only the `sec_filings_nvda` collection

It no longer targets the AWS Lambda documentation flow.

### 4. Querying now reads from the SEC collection

[query_data.py](/Users/rchadha/Documents/projects/p/rag-application/query_data.py) now queries:

`sec_filings_nvda`

This means the existing query path is currently pointed at SEC data rather than AWS Lambda docs.

### 5. Embedding model was updated

The embedding model was made explicit in both indexing and querying:

`text-embedding-3-small`

Reason:

- newer than older implicit defaults
- cheaper than `text-embedding-3-large`
- a good fit for RAG over financial filings

## Chunking Decision

For SEC filings, chunking was updated to:

- `chunk_size = 1200`
- `chunk_overlap = 200`

Why:

- SEC filings are long, dense documents
- the old `300 / 100` setup was too small and likely to split important context too aggressively
- larger chunks are better for sections like risk factors, MD&A, and business overview

This is still character-based chunking, not token-based chunking.

## Metadata Added To Chunks

Each chunk gets metadata such as:

- `dataset`
- `chunk_id`
- `ticker`
- `form_type`
- `filing_date`
- `accession_number`
- `source`

These values are derived from the filing filename when possible.

## Commands Used

### Download SEC filings

Run with the project virtualenv:

```bash
./rag-application/bin/python data/download-sec-public-data.py
```

### Build the SEC Chroma index

```bash
./rag-application/bin/python create_database.py
```

### Query the SEC collection

```bash
./rag-application/bin/python query_data.py "What risk factors did NVIDIA mention?"
```

## Indexing Result

Latest successful SEC indexing run:

- loaded `13` SEC filing documents
- split into `974` chunks
- rebuilt Chroma collection `sec_filings_nvda`

## Current Caveat

Some SEC text appears noisy because the downloaded filing text includes machine-readable inline XBRL and table-like content.

This means retrieval may still return some low-value chunks unless the preprocessing is improved.

## Good Next Steps

Potential future improvements:

- section-aware SEC chunking using headings like `PART I`, `PART II`, `Item 1A`, `Item 7`
- stripping or downweighting inline XBRL-heavy content
- richer metadata filters in retrieval
- separate query modes for SEC filings vs other corpora

## LangSmith Observability

Minimal LangSmith tracing was added for observability around:

- SEC indexing runs
- retrieval during queries
- answer generation during queries

To enable it, add this to `.env`:

```env
LANGSMITH_TRACING=true
LANGSMITH_API_KEY="your-langsmith-api-key"
LANGSMITH_PROJECT="rag-application-sec"
```

Tracing is selective and optional. If the env vars are not set, the app behavior remains unchanged.
