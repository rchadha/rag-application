# How I Built a Production RAG Application on AWS — Architecture Deep Dive

If you've been following along with my work on building a Retrieval-Augmented Generation (RAG) application for financial analysis, you've seen me experiment with hybrid retrieval, cross-encoder reranking, and automated data ingestion. This post steps back and explains the full architecture — how all the pieces connect, why I made certain choices, and what the system actually looks like end to end.

The application answers natural language questions about NVIDIA using four data sources: SEC filings, earnings call transcripts, financial news, and social media content. Let's walk through it layer by layer.

---

## The Big Picture

At a high level, the system has two independent flows:

1. **Ingestion flow** — data gets collected, chunked, embedded, and stored in a vector database
2. **Query flow** — a user question triggers retrieval, then generation, then a response

These two flows share the vector database (Pinecone) but are otherwise completely separate. You can run ingestion without touching the query API, and vice versa.

```
INGESTION FLOW
──────────────
Local files (SEC, Earnings) ──────────────────────┐
                                                   ▼
Finnhub News API ──► ingest_social.py ──► Pinecone (vector DB)
                                                   ▲
                                         (4 namespaces)

QUERY FLOW
──────────
User ──► Next.js (Vercel) ──► API Gateway ──► Lambda ──► Flask app
                                                              │
                                                    retrieval.py (Pinecone search)
                                                              │
                                                    query_data.py (GPT-4o)
                                                              │
                                        Answer + Sources ◄────┘
```

---

## Layer 1: The Vector Database (Pinecone)

Everything revolves around a single Pinecone index called `rag-application`. Rather than creating separate indexes per data source, I use **namespaces** to isolate the four datasets:

| Namespace | Contents | Chunk Size |
|---|---|---|
| `sec_filings_nvda` | NVIDIA 10-K, 10-Q, and other SEC filings | 1200 chars, 200 overlap |
| `earnings_calls_nvda` | Earnings call transcripts | 800 chars, 120 overlap |
| `news` | Finnhub financial news articles | Article-level (no chunking) |
| `social` | Social media content | Post-level |

The different chunk sizes are intentional. SEC filings are dense and technical — larger chunks preserve more context. Earnings calls have natural paragraph breaks and more conversational language, so smaller chunks work better. News articles are short enough to embed whole.

Every vector was generated using OpenAI's `text-embedding-3-small` model (1536 dimensions). It's cheap, fast, and good enough for financial text.

---

## Layer 2: Data Ingestion

### Static Data — SEC Filings and Earnings Calls

`create_database.py` handles the one-time batch indexing of structured documents:

1. Load `.txt` or `.docx` files from a local `data/` directory
2. Split into chunks using LangChain's `RecursiveCharacterTextSplitter`
3. Extract metadata from filenames (date, form type, quarter, accession number)
4. Delete the existing namespace and re-index from scratch
5. Track the entire run in LangSmith for observability

This is a manual, run-once operation. You update it when new filings are released.

### Dynamic Data — News (Daily)

`ingest_social.py` is the automated ingestion pipeline. It hits the Finnhub company news API, runs each article through VADER sentiment analysis, and upserts to the `news` namespace.

The smart part is deduplication: before generating any OpenAI embeddings, the pipeline computes deterministic MD5 IDs for each article, fetches which IDs already exist in Pinecone, and only embeds the new ones. This saves API costs on repeat runs.

```python
# Pseudo-code of the dedup logic
ids = [md5(f"news|{source}") for source in article_sources]
existing = pinecone_index.fetch(ids).vectors.keys()
new_articles = [a for a in articles if its_id not in existing]
# Only call OpenAI embeddings for new_articles
```

Each news document gets enriched metadata: ticker symbol, company name, publisher, publish timestamp, and sentiment scores (compound score + label: positive/neutral/negative).

---

## Layer 3: Retrieval

`retrieval.py` handles all vector search logic. The main function is `get_top_results()`:

1. Convert the user's query text into an embedding using `text-embedding-3-small`
2. Run similarity search against the appropriate Pinecone namespace
3. Optionally rerank the top-10 candidates using a cross-encoder (`BAAI/bge-reranker-base`)
4. Return the top-k results with scores

The cross-encoder reranker is loaded lazily — it's a ~500MB model, so it only loads on first use and stays cached in Lambda memory for subsequent calls.

The `dataset` parameter routes to the right namespace:
- `sec` → `sec_filings_nvda`
- `earnings` → `earnings_calls_nvda`
- `news` → `news`
- `social` → `social`

---

## Layer 4: Generation

`query_data.py` takes the retrieved documents and calls GPT-4o to generate an answer.

The prompt is deliberately strict — it instructs the model to answer **only from the provided context**. This is the core RAG contract: the model shouldn't hallucinate from its training data; it should synthesize what was retrieved.

```python
PROMPT = """
Answer the question based only on the following context:
{context}

Answer the question based on the above context: {question}
"""
```

The response includes:
- The generated answer
- Source document references
- Per-result retrieval scores (vector score + optional rerank score)

The entire query pipeline is traced in LangSmith, which captures the query, retrieved context, prompt, and response for debugging and evaluation.

---

## Layer 5: The API

`app.py` is a Flask application with two endpoints:

```
GET  /health   → {"status": "healthy"}
POST /query    → {"response": "...", "sources": [...], "retrieval": [...]}
```

The `/query` endpoint accepts:
```json
{
  "query": "What was NVIDIA's revenue in Q3 2024?",
  "dataset": "sec",
  "use_reranker": false
}
```

On startup in Lambda, the app lazily loads API keys from AWS Secrets Manager. This is a **cold start optimization** — the keys are only fetched once per Lambda container lifecycle, not on every request.

CORS is enabled globally, so the API can be called from any frontend origin.

---

## Layer 6: Deployment

### Container Image

The application runs as a Docker container based on AWS's official Lambda Python 3.13 image. The container includes all Python dependencies plus pre-downloaded NLTK data (required by the chunking pipeline).

```dockerfile
FROM public.ecr.aws/lambda/python:3.13
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN python -c "import nltk; nltk.download('punkt')..."
COPY *.py ./
CMD ["lambda_handler.handler"]
```

The `lambda_handler.py` file is a one-liner that wraps the Flask app using `apig-wsgi`, which translates API Gateway HTTP events into WSGI requests:

```python
from apig_wsgi import make_lambda_handler
from app import app

handler = make_lambda_handler(app)
```

This means the same Flask app can run locally (`python app.py`) or inside Lambda without any code changes.

### AWS Infrastructure (Terraform)

All infrastructure is managed as code with Terraform:

- **ECR** — Docker image registry, keeps the last 10 images, scans on push
- **Lambda** — 1024MB memory, 120s timeout (generous for cold starts with the reranker model)
- **API Gateway HTTP API** — catch-all route `$default` proxies everything to Lambda
- **Secrets Manager** — stores OpenAI and Pinecone API keys
- **CloudWatch Logs** — Lambda logs retained for 7 days
- **IAM** — Lambda execution role with least-privilege access to Secrets Manager

### CI/CD (GitHub Actions)

On every push to `main`:

1. Run Python linting (flake8)
2. Build the Docker image
3. Push to ECR with both `latest` and the commit SHA as tags
4. Update the Lambda function to use the new image

Authentication uses OIDC (OpenID Connect) — no long-lived AWS credentials stored in GitHub Secrets. GitHub Actions assumes an IAM role via a short-lived token, which is the recommended approach.

On every pull request, Terraform plan runs automatically and posts the infrastructure diff as a PR comment.

---

## Observability

Two tools handle observability:

**LangSmith** traces the entire RAG pipeline — indexing runs and query executions. For each query, you can see exactly what was retrieved, what the prompt looked like, and what GPT-4o returned. This is invaluable for debugging when the answer quality degrades.

**CloudWatch Logs** captures all Lambda logs including cold start times, secret loading, Pinecone query latency, and any errors.

---

## Layer 7: The Frontend (Next.js on Vercel)

The backend API is consumed by a Next.js application deployed on Vercel. It calls the API Gateway URL directly — there's no middleware proxy in between.

### What the UI Does

The interface is a chat application with four dataset tabs across the top: **News**, **Social Sentiment**, **SEC Filings**, and **Earnings Calls**. Each tab maps directly to the `dataset` parameter in the `/query` API request.

A few UI details worth noting from the design:

- **Data freshness labels** — each tab shows whether the data is live ("Updated today") or static ("Historical"). This sets user expectations correctly: the news and social tabs reflect recent ingestion, while SEC and earnings call data is updated manually when new filings are released.
- **Source metadata** — each tab shows a short description of where the data comes from and how often it updates. For example, the Social Sentiment tab shows post counts and lists the Reddit communities being monitored (r/investing, r/stocks, r/wallstreetbets).
- **Chat interface** — user messages appear as bubbles on the right; AI responses appear on the left with source attribution at the bottom. Each response shows which dataset it came from and an expandable "N sources" link showing the retrieved documents.
- **Usage counter** — "2/50 free queries used" — there's a per-user query limit baked into the frontend, which protects against runaway API Gateway + OpenAI costs.

### How Vercel Connects to AWS

The Next.js app stores the API Gateway URL as a Vercel environment variable (`NEXT_PUBLIC_API_URL` or similar). On each query, the browser makes a direct POST to that URL:

```
Browser → API Gateway (us-east-1) → Lambda → Flask → Pinecone + OpenAI
```

Because the Flask app has CORS enabled globally, the browser can call the API Gateway URL directly without a same-origin proxy. This keeps the architecture simple — Vercel handles the frontend hosting and CDN, AWS handles all the compute and data.

### Deployment

Vercel deploys automatically on every push to the frontend repo's main branch — similar to how GitHub Actions handles the backend. The two repos deploy independently, which means you can update the backend API without touching the frontend, as long as the request/response contract stays the same.

---

## Architecture Decisions and Trade-offs

**Why Lambda instead of a long-running server?**
The query volume is low and unpredictable. Lambda scales to zero when idle, meaning the cost is near-zero during quiet periods. The trade-off is cold starts — the first request after idle takes 3-5 seconds while the container initializes and secrets load. For a personal or low-traffic application, this is an acceptable trade-off.

**Why a single Pinecone index with namespaces instead of multiple indexes?**
Pinecone's free tier allows one index. Namespaces give logical separation without the cost of multiple indexes. The routing is handled in application code, which keeps infrastructure simple.

**Why not store embeddings in a managed service like RDS with pgvector?**
Pinecone handles the approximate nearest neighbor search efficiently and is fully managed. The operational overhead of running a database with pgvector would outweigh the cost savings at this scale.

**Why Flask instead of FastAPI?**
Flask is simpler for a small API surface. The `apig-wsgi` adapter works well with Flask. FastAPI would add async support and automatic OpenAPI docs, but neither is needed here.

---

## Data Flow Summary

To make it concrete, here's what happens when a user asks: *"What were NVIDIA's main risk factors in their 2023 10-K?"*

1. User types a question in the Next.js UI and selects the "SEC Filings" tab
2. The browser sends a POST request directly to the API Gateway URL with `{"query": "...", "dataset": "sec"}`
3. API Gateway triggers the Lambda function
4. Flask receives the request via `apig-wsgi`
5. `app.py` calls `_load_secrets()` (no-op if already loaded)
6. `query_data.py` calls `get_top_results()` in `retrieval.py`
7. `retrieval.py` embeds the query with `text-embedding-3-small`
8. Pinecone returns top-3 similar chunks from `sec_filings_nvda` namespace
9. `query_data.py` formats the chunks into a prompt and calls GPT-4o
10. The response is returned with sources and retrieval scores
11. The Next.js UI renders the answer with the dataset label and source count
12. LangSmith captures the full trace for observability

Total latency on a warm Lambda: ~2-4 seconds (dominated by the OpenAI API calls).

---

## What's Next

The current architecture handles the core RAG use case well, but there are natural next evolution points: a proper frontend, query caching for repeated questions, and expanding the ingestion pipeline to cover more tickers beyond NVIDIA.

The foundation — containerized Lambda, Terraform-managed infrastructure, LangSmith observability, and a clean separation between ingestion and query — is solid enough to extend without a rewrite.
