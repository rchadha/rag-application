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
