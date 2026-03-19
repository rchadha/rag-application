# Cross-Encoder Evaluation Results

This document captures the first before-and-after evaluation of cross-encoder reranking on the SEC retrieval pipeline.

## Setup

- Corpus: `sec_filings_nvda`
- Retriever: Chroma + `text-embedding-3-small`
- Baseline: dense retrieval only
- Reranker candidates: top `10`
- Final context size: top `3`
- Evaluation set: [evals/sec_retrieval_eval.json](/Users/rchadha/Documents/projects/p/rag-application/evals/sec_retrieval_eval.json)
- Questions evaluated: `8`

## Metrics

Metrics are source-level retrieval metrics:

- `Hit@1`: correct source appears first
- `Hit@3`: correct source appears somewhere in top 3
- `MRR`: mean reciprocal rank of the first relevant source

## Results

### Baseline: dense retrieval only

- `Hit@1 = 0.875`
- `Hit@3 = 0.875`
- `MRR = 0.875`

### Cross-encoder: `cross-encoder/ms-marco-MiniLM-L-6-v2`

- `Hit@1 = 0.750`
- `Hit@3 = 0.875`
- `MRR = 0.8125`

Outcome:

- no improvement over baseline
- weaker top-rank accuracy than dense retrieval alone

### Cross-encoder: `cross-encoder/ms-marco-MiniLM-L-12-v2`

- `Hit@1 = 0.750`
- `Hit@3 = 0.875`
- `MRR = 0.7917`

Outcome:

- also worse than baseline on this SEC set

### Cross-encoder: `BAAI/bge-reranker-base`

- `Hit@1 = 0.750`
- `Hit@3 = 1.000`
- `MRR = 0.8333`

Outcome:

- lower top-1 precision than the dense baseline
- better top-3 coverage than the dense baseline
- recovered one question the baseline missed entirely in the top 3

## What Improved

The `BAAI/bge-reranker-base` model improved retrieval coverage for:

- `What did NVIDIA say about legal proceedings?`

Dense baseline:

- failed to return the expected `2025-11-19 10-Q` source in the top 3

Reranked result:

- moved the expected source into rank 3

This matters for RAG because the answer generator sees the top retrieved context, not just the top 1 item.

## What Got Worse

The same `BAAI/bge-reranker-base` reranker hurt top-1 ranking for:

- `What did NVIDIA say about supply and capacity constraints?`

Dense baseline:

- expected source was at rank 1

Reranked result:

- expected source dropped to rank 3

## Interpretation

The main takeaway is:

**A cross-encoder did not automatically outperform the dense baseline.**

For this project:

- the dense baseline is already strong on the current 8-question SEC evaluation set
- generic MS MARCO rerankers underperformed
- `BAAI/bge-reranker-base` improved top-3 recall, but reduced top-1 precision

This suggests:

- if your goal is best first result, the current dense baseline is stronger
- if your goal is better coverage across the final context window, `BAAI/bge-reranker-base` is promising

## Recommendation

Current recommendation:

- keep the cross-encoder **optional**, not enabled by default
- use `BAAI/bge-reranker-base` as the preferred experimental reranker
- expand the evaluation set before enabling reranking globally

## Why It May Matter More Later

This first evaluation was run on a relatively clean SEC-only corpus.

That matters because:

- SEC filings are structured
- language is formal and repetitive
- dense retrieval already performs well on this kind of content

The value of a cross-encoder may increase once the application adds noisier corpora such as:

- financial news
- blogs or commentary
- social media posts
- market sentiment snippets

In those settings, retrieval gets harder because:

- multiple documents may discuss the same topic with different phrasing
- low-signal or tangential content appears more often
- social content is short, informal, and often ambiguous

In a mixed-source RAG system, a cross-encoder can become more useful because it reranks competing candidates across different content types and may help surface the most query-relevant evidence.

So the current conclusion is not:

- "cross-encoders are not useful"

The better conclusion is:

- "cross-encoders were not a clear win on the current SEC-only corpus, but they may become much more valuable once the retrieval problem becomes noisier and more heterogeneous."

---

## Evaluation 2: Finnhub News Corpus (`news`)

### Setup

- Corpus: `news` (Finnhub news articles for NVDA, ingested via Pinecone)
- Vector store: Pinecone + `text-embedding-3-small`
- Reranker: `BAAI/bge-reranker-base`
- Retriever candidates: top `10`
- Final context size: top `3`
- Evaluation set: [evals/news_retrieval_eval.json](/Users/rchadha/Documents/projects/p/rag-application/evals/news_retrieval_eval.json)
- Questions evaluated: `8`

### Results

#### Baseline: dense retrieval only

- `Hit@1 = 1.000`
- `Hit@3 = 1.000`
- `MRR = 1.000`

#### Cross-encoder: `BAAI/bge-reranker-base`

- `Hit@1 = 0.625`
- `Hit@3 = 0.875`
- `MRR = 0.750`

Outcome:

- dense baseline was **perfect** on all 8 questions
- reranker degraded performance across every metric
- stronger regression than observed on the SEC corpus

### What Got Worse

The reranker failed on 3 of 8 questions:

**Q: "What is the demand outlook for NVIDIA AI data center products?"**
- Baseline: expected source at rank 1 (vector score 0.849)
- Reranked: non-expected article pushed to rank 1 (rerank score 0.944), expected source dropped to rank 2

**Q: "How is NVIDIA competing against AMD and Intel?"**
- Baseline: expected source at rank 1
- Reranked: a closely-related but non-expected article pushed to rank 1 (rerank scores nearly identical at 0.00073 vs 0.00070 — effectively random at that scale)

**Q: "What has Jensen Huang announced recently?"**
- Baseline: expected sources at ranks 1, 2, 3
- Reranked: all three expected sources evicted from top 3 entirely — completely different articles promoted (rerank scores 0.986, 0.895, 0.427)
- This is the worst single-question regression observed across both evaluations

### Why the Regression is Worse on News

The SEC corpus is dense, structured, and long-form. Each chunk carries enough signal for the reranker to make confident relevance judgements.

News articles are short headlines and summaries. The reranker saw short, overlapping text — many articles about NVDA are topically similar — making rerank scores noisy and unreliable. The dense retrieval model (`text-embedding-3-small`) had already done the hard work well; the reranker introduced noise on top.

The "Jensen Huang" failure is a good example: the reranker promoted articles with high surface relevance to the query but that were not the specific sources the dense retriever had correctly identified.

### Combined Conclusion Across Both Corpora

| Corpus | Baseline Hit@1 | Reranked Hit@1 | Verdict |
|--------|---------------|----------------|---------|
| SEC filings | 0.875 | 0.750 | reranker hurt top-1 |
| Finnhub news | **1.000** | **0.625** | reranker hurt top-1 significantly |

Across both structured (SEC) and unstructured (news) corpora, `BAAI/bge-reranker-base` did not improve retrieval and in both cases reduced top-1 precision. The degradation was more severe on the news corpus, where the dense baseline was already perfect.

This is not evidence that cross-encoders are universally ineffective. The likely causes here are:

- Short document length in the news corpus reduces reranker signal quality
- High topical overlap across news articles makes fine-grained reranking harder
- `BAAI/bge-reranker-base` is a general-purpose model not tuned for financial news

A domain-fine-tuned reranker or a larger model may perform differently. But the current evidence across two corpora is consistent: **the dense baseline should remain the default**.

---

## Commands Used

Baseline query:

```bash
./rag-application/bin/python query_data.py "What risk factors did NVIDIA mention?"
```

Reranked query:

```bash
./rag-application/bin/python query_data.py --use-reranker "What risk factors did NVIDIA mention?"
```

Evaluation run:

```bash
./rag-application/bin/python evaluate_cross_encoder.py
```

To test a different reranker:

```bash
CROSS_ENCODER_MODEL_NAME=BAAI/bge-reranker-base ./rag-application/bin/python evaluate_cross_encoder.py
```

## Blog-Friendly Framing

A credible summary for a LinkedIn post would be:

- We added cross-encoder reranking to a RAG pipeline over NVIDIA SEC filings.
- We did not assume it would help; we measured it.
- On our first labeled SEC evaluation set, dense retrieval was already strong.
- Two generic MS MARCO rerankers made top-1 ranking worse.
- A BGE reranker improved top-3 coverage from `87.5%` to `100%`, but reduced top-1 precision.
- The lesson was not "cross-encoders always help"; it was "observability and evaluation prevented us from shipping a regression."

---

## Evaluation 3: Hybrid Retrieval (BM25 + Dense) with Cross-Encoder Reranking

### Motivation

A commonly cited "production-ready RAG" pattern recommends combining two retrieval strategies:

1. **Vector semantic search** — understands intent and meaning
2. **BM25 keyword search** — handles exact terms, ticker symbols, and specific phrases semantic search may miss
3. **Cross-encoder reranking** — rescores the merged candidate pool for final precision

The hypothesis: the reranker failed in Evaluations 1 and 2 because the dense-only candidate pool was too narrow. Give the reranker a more diverse candidate pool (dense + BM25), and it should be able to do its job better.

This evaluation tests that hypothesis on the same two corpora.

---

### Implementation: Reciprocal Rank Fusion (RRF)

Pinecone's native hybrid search requires `dotproduct` metric. Our existing index uses `cosine`, so we implemented hybrid retrieval in-application using **Reciprocal Rank Fusion** — no index rebuild, no re-embedding, zero API cost.

**How it works:**

1. Dense search returns top-k results ranked by vector similarity
2. BM25 keyword search runs locally against a corpus index saved from Pinecone metadata
3. RRF merges both lists: score = `Σ 1 / (60 + rank_i)` for each retriever a document appears in
4. Documents that rank highly in **both** lists float to the top — agreement across retrievers is rewarded

The BM25 corpus was built with `python patch_sparse_vectors.py` — it reads existing vector metadata from Pinecone, extracts text, and saves it locally. No OpenAI calls, no re-indexing.

**Four retrieval modes evaluated:**

| Mode | Dense | BM25 | Reranker |
|---|:---:|:---:|:---:|
| `dense` | ✓ | | |
| `dense_reranked` | ✓ | | ✓ |
| `hybrid` | ✓ | ✓ | |
| `hybrid_reranked` | ✓ | ✓ | ✓ |

---

### Results: SEC Filings Corpus (`sec_filings_nvda`)

- Corpus: 974 chunks from NVIDIA SEC filings
- Embedding: `text-embedding-3-small`
- Reranker: `BAAI/bge-reranker-base`
- Eval set: 8 questions

| Mode | Hit@1 | Hit@3 | MRR |
|---|---|---|---|
| `dense` | **0.875** | **0.875** | **0.875** |
| `dense_reranked` | 0.625 | 0.875 | 0.729 |
| `hybrid` | 0.625 | 0.875 | 0.729 |
| `hybrid_reranked` | 0.125 | 0.875 | 0.438 |

**Outcome: dense baseline wins. Every advanced strategy degraded performance.**

---

### Results: Finnhub News Corpus (`news`)

- Corpus: ~1,100 news articles (grown since Evaluation 2 — 148 new articles added)
- Embedding: `text-embedding-3-small`
- Reranker: `BAAI/bge-reranker-base`
- Eval set: 8 questions
- Note: the baseline dropped from 1.000 (Eval 2) to 0.625 due to corpus growth — larger corpus, denser overlap, harder retrieval

| Mode | Hit@1 | Hit@3 | MRR |
|---|---|---|---|
| `dense` | **0.625** | **1.000** | **0.812** |
| `dense_reranked` | 0.500 | 0.875 | 0.688 |
| `hybrid` | 0.500 | 1.000 | 0.708 |
| `hybrid_reranked` | 0.375 | 0.875 | 0.625 |

**Outcome: dense baseline wins again. Hybrid improved Hit@3 parity but hurt Hit@1. Adding the reranker on top made it worse.**

---

### Combined Summary: Three Evaluations, Four Approaches

| Corpus | dense Hit@1 | dense_reranked | hybrid | hybrid_reranked |
|---|---|---|---|---|
| SEC filings | **0.875** | 0.625 | 0.625 | 0.125 |
| Finnhub news | **0.625** | 0.500 | 0.500 | 0.375 |

The dense baseline won on top-1 precision in every single comparison across both corpora and all three evaluation rounds.

---

### Why Hybrid + Reranking Didn't Help Here

**1. The corpus characteristics work against BM25**

SEC filings are formal, structured, and long-form. `text-embedding-3-small` was trained on exactly this kind of text and already captures meaning well. BM25 on this corpus adds noise — many chunks contain the same legal boilerplate, and keyword overlap does not correlate well with relevance.

News articles are short (headline + summary), topically overlapping, and repetitive. BM25 scores are noisy when many articles share the same keywords.

**2. RRF introduction of BM25 candidates dilutes a strong signal**

When dense retrieval already returns the right document at rank 1, mixing in BM25's top-k — which may include less relevant chunks — can push the correct answer down. RRF rewards documents that appear in both lists, but if the correct document only appears in the dense list (BM25 ranked something else first), it loses ground.

**3. The reranker has less to work with when given noisy candidates**

In Evaluations 1–2, reranking was applied to a clean dense top-10. In Evaluation 3, it was applied to a hybrid top-10 that may include lower-quality BM25 candidates. The reranker doesn't know which retriever found each document — it just sees (query, chunk) pairs. With a noisier input pool, it makes more mistakes.

---

### What This Tells Us

The advice to "add hybrid search and a reranker" is common. It is also frequently correct — but not universally. The benefit depends on:

- **Query type**: queries with specific symbols, dates, or proper nouns benefit more from BM25. Open-ended questions about intent or strategy benefit from dense.
- **Corpus type**: short, overlapping documents (news, social) are harder for BM25. Long-form structured documents (SEC filings) are harder for BM25 to differentiate.
- **Baseline quality**: if your dense model is already strong on your domain, adding BM25 may introduce more noise than signal.

**The more important lesson is about process, not outcome.** Without an evaluation framework, it would have been easy to ship hybrid retrieval + reranking believing the "advanced RAG" playbook guaranteed improvement. It doesn't. We measured, and the measurements told us not to ship it — at least not for these corpora and this embedding model.

---

### When Hybrid + Reranking Would Likely Help

- Queries containing specific ticker symbols (e.g. `$NVDA`, `AMD`) where BM25 would give those exact tokens strong weight
- Mixed-language or domain-shifted queries where dense embeddings struggle
- A corpus where the dense baseline is weak (Hit@1 < 0.5) — there is more headroom for BM25 to contribute
- With a **domain-fine-tuned** reranker (not a general MS MARCO or BGE model)
- With a **larger reranker candidate pool** (k=20–50 instead of k=10), giving the reranker more diverse options

---

### Commands

Build BM25 corpus index (one-time, free):
```bash
python patch_sparse_vectors.py --namespace sec_filings_nvda
python patch_sparse_vectors.py --namespace news
```

Run full 4-mode evaluation:
```bash
python evaluate_cross_encoder.py --dataset sec --mode all
python evaluate_cross_encoder.py --dataset news --mode all
```

Run a single mode:
```bash
python evaluate_cross_encoder.py --dataset sec --mode hybrid
```

