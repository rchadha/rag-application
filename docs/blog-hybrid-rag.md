# I Tried the "Production-Ready RAG" Playbook. Here's What Actually Happened.

I've been building a RAG application over NVIDIA's SEC filings and earnings call transcripts. The idea is simple: let users ask natural language questions and get answers grounded in the actual filings, not hallucinated summaries.

After getting the basics working, I started reading about how to make retrieval better. One article I came across described a pattern that's become almost standard advice in the RAG community:

> *"To graduate from a simple demo to a production-ready system, implement Hybrid Retrieval (vector search + BM25 keyword search) combined with Cross-Encoder Reranking. This consistently and dramatically improves precision."*

That sounded reasonable to me. So I built it. Then I measured it. Then I got surprised — in both directions.

---

## What I Had Before

My baseline system was straightforward:

1. Chunk NVIDIA's 10-K and 10-Q filings into ~1000 token segments
2. Embed each chunk using OpenAI's `text-embedding-3-small`
3. Store in Pinecone
4. At query time: embed the question, find the top 10 most similar chunks by cosine similarity, pass the top 3 to GPT-4 as context

This is what most RAG tutorials end with. It worked reasonably well. But I wanted to know: how well, exactly? And could I do better?

---

## Setting Up an Evaluation Framework First

Before trying anything "advanced", I did something that turned out to be the most important decision in this whole exercise: **I built an evaluation set before touching the retrieval code.**

I wrote 8 questions that a real user might ask about NVIDIA's filings, and for each question I manually identified which source document should be retrieved. Things like:

- *"What did NVIDIA say about supply and capacity constraints?"* → expected source: the November 2025 10-Q
- *"What risk factors did NVIDIA mention?"* → expected sources: three different 10-Qs
- *"How did NVIDIA describe its accelerated computing platform?"* → expected source: the 2026 10-K

Then I defined three metrics:

- **Hit@1** — did the correct document appear as the top result?
- **Hit@3** — did it appear anywhere in the top 3 results?
- **MRR** (Mean Reciprocal Rank) — on average, how early did the correct document appear?

This setup lets me compare any two retrieval approaches objectively. Without it, I'd just be guessing whether something got "better."

---

## Phase 1: Testing Cross-Encoder Reranking Alone

A cross-encoder reranker works differently from the initial vector search. Instead of comparing a single query embedding against thousands of document embeddings in one shot, it takes each (query, document) pair and evaluates them together through a transformer model. It's slower, but in theory more accurate because it can model the interaction between the query and the document directly.

The standard pattern:
1. Dense retrieval gives you top 10 candidates (fast)
2. Cross-encoder rescores all 10 by reading the full query + chunk together (slower but smarter)
3. Return the top 3 from the reranked list

I used `BAAI/bge-reranker-base`, a well-regarded open-source reranker.

**Results on SEC filings:**

| Approach | Hit@1 | Hit@3 | MRR |
|---|---|---|---|
| Dense baseline | **0.875** | 0.875 | **0.875** |
| Dense + Reranker | 0.625 | **1.000** | 0.771 |

The reranker made top-1 precision *worse*. Hit@1 dropped from 87.5% to 62.5%.

There was one silver lining: Hit@3 improved to 100%. The reranker found the document the baseline was missing — it just shuffled the top rankings in a way that hurt precision for other questions.

My theory: the reranker is working with too narrow a candidate pool. If the dense top-10 doesn't include the right document, the reranker has nothing to work with. What if I give it a more diverse set of candidates by combining two different retrieval methods?

---

## Phase 2: Proper Hybrid Retrieval — Dense + BM25

This is the core of the "production-ready" recommendation. The idea is that two retrieval strategies complement each other:

- **Dense semantic search** understands *intent* — "what did NVIDIA say about competitive risk" finds relevant chunks even if they don't use those exact words
- **BM25 keyword search** handles *exact terms* — ticker symbols like `$NVDA`, product names like `H100`, specific dates, or precise phrases that semantic search might treat as similar to other terms

Combining them gives you candidates that either retriever alone would miss.

### The Implementation

Pinecone's native hybrid search requires an index with `dotproduct` metric. My existing index used `cosine` — and these two metrics are not interchangeable in Pinecone's query API.

The good news: **I didn't need to re-embed anything.** Pinecone stores the dense vector values alongside metadata. I could fetch all 974 vectors, add BM25 sparse vectors to each one, then migrate to a new `dotproduct` index — reusing the exact same dense embeddings. Zero OpenAI API calls.

```python
# Fetch existing vectors including their dense float values
response = index.fetch(ids=batch_ids, namespace=namespace)
for vec_id, vec_data in response.vectors.items():
    vectors.append({
        "id": vec_id,
        "values": vec_data.values,     # reuse existing dense embeddings
        "text": vec_data.metadata["text"],
    })

# Fit BM25 on corpus text, generate sparse vectors
encoder = BM25Encoder()
encoder.fit([v["text"] for v in vectors])
sparse_vectors = encoder.encode_documents([v["text"] for v in vectors])

# Upsert to new dotproduct index with BOTH dense + sparse
index.upsert(vectors=[{
    "id": v["id"],
    "values": v["values"],          # original dense embedding unchanged
    "sparse_values": sparse,        # new BM25 sparse vector
    "metadata": v["metadata"],
} for v, sparse in zip(vectors, sparse_vectors)])
```

One thing worth knowing: **dotproduct with unit-normalized vectors is mathematically identical to cosine similarity.** OpenAI embeddings are already unit-normalized, so switching to `dotproduct` doesn't change the quality of dense-only queries at all. You get hybrid search capability without any degradation to existing behavior.

At query time, both vectors are scaled by `alpha` to control the blend:

```python
def retrieve_hybrid(query, alpha=0.75):
    dense_vector = embedding_model.embed_query(query)
    sparse_vector = bm25_encoder.encode_queries(query)

    # Scale: alpha=0.75 means 75% semantic, 25% keyword
    scaled_dense = [v * alpha for v in dense_vector]
    scaled_sparse = {
        "indices": sparse_vector["indices"],
        "values": [v * (1 - alpha) for v in sparse_vector["values"]],
    }

    return pinecone_index.query(
        vector=scaled_dense,
        sparse_vector=scaled_sparse,
        top_k=10,
    )
```

---

## The Results

Running all four modes on the SEC corpus:

| Mode | Hit@1 | Hit@3 | MRR |
|---|---|---|---|
| Dense (baseline) | 0.875 | 0.875 | 0.875 |
| Dense + Reranker | 0.625 | 1.000 | 0.771 |
| **Hybrid** | **0.875** | **1.000** | **0.917** |
| Hybrid + Reranker | 0.750 | 0.875 | 0.792 |

Hybrid retrieval matched the dense baseline on Hit@1 while improving Hit@3 to 100% and MRR from 0.875 to 0.917. That's a meaningful improvement — better coverage and better average ranking with no regression on top-1 precision.

The hypothesis held: hybrid gave the reranker better raw material. But interestingly, the reranker still didn't improve things further — `hybrid_reranked` actually dropped from `hybrid`. The reranker seems to be introducing more noise than signal even with the richer candidate pool.

**On the news corpus (1,100+ Finnhub articles), the picture is different:**

| Mode | Hit@1 | Hit@3 | MRR |
|---|---|---|---|
| Dense (baseline) | **0.625** | **1.000** | **0.812** |
| Dense + Reranker | 0.500 | 0.875 | 0.688 |
| Hybrid | 0.500 | 0.875 | 0.688 |
| Hybrid + Reranker | 0.375 | 0.875 | 0.625 |

Dense wins across the board on news. Hybrid didn't help here, and the reranker hurt in both modes.

---

## Why Did Hybrid Help on SEC but Not News?

The difference comes down to document characteristics.

**SEC filings are long-form and structured.** Each chunk is several paragraphs. BM25 can meaningfully differentiate between chunks — one chunk discusses supply chain risk, another discusses data center strategy, and the keyword distributions are genuinely different. Combining BM25's keyword signal with dense semantic signal finds better candidates.

**News articles are short and topically overlapping.** A headline plus a 3-sentence summary. Hundreds of articles all containing "NVIDIA", "H100", "data center", "Jensen Huang". BM25 can barely differentiate between them because the keyword distributions are nearly identical across the whole corpus. It introduces candidates that look keyword-relevant but aren't actually the best match for the query's intent.

**Why the reranker still didn't help even with hybrid candidates:** The reranker is a general-purpose model (`BAAI/bge-reranker-base`) trained on MS MARCO web search queries. It wasn't fine-tuned for financial documents. On short, topically similar news articles, its confidence scores cluster close together — the difference between rank 1 and rank 3 in reranker score might be 0.001 — and at that resolution, the rankings are effectively random.

---

## What I Actually Learned

**1. The techniques in the playbook are real. The claim that they "consistently and dramatically improve precision" is not.**

Hybrid retrieval genuinely improved my SEC corpus results. The reranker genuinely improved Hit@3 in Phase 1. These are real tools that work. But whether they help on *your* data depends on your corpus, your query patterns, and your baseline.

**2. Corpus characteristics determine which techniques help.**

- Long-form, structured documents → hybrid retrieval more likely to help (BM25 can differentiate)
- Short, overlapping documents → dense alone is probably better (BM25 adds noise)
- Strong dense baseline → reranker has little room to improve and may hurt
- Weak dense baseline → reranker has more room and may be worth trying

**3. Evaluation is not optional — it's the work.**

Without a labeled eval set, I would have shipped hybrid + reranker for both corpora because it "felt" like an improvement. It would have been a regression on news. Measurement is what prevents shipping regressions disguised as features.

**4. "Advanced" and "better" are not the same thing.**

The reranker never improved Hit@1 across any combination I tried. That's a real finding about this specific setup — not evidence that rerankers are useless, but evidence that this reranker on this corpus needs either a larger candidate pool, a domain fine-tuned model, or a different query distribution.

---

## What I'd Try Next

- **Larger eval set** — 8 questions is a starting point, not a definitive answer
- **Queries with specific terms** — BM25's strength is exact keyword matching; I never tested queries like "What did NVIDIA say about H100 SXM5 supply in Q3 FY2026?" where BM25 should clearly outperform dense
- **Domain fine-tuned reranker** — a reranker trained on financial Q&A would likely make better decisions on these documents
- **Larger candidate pool** — k=20 or k=50 before reranking, giving the cross-encoder more to work with

I'll measure all of those too before shipping any of them.

---

## The Takeaway

The advice to add hybrid retrieval and a cross-encoder reranker is genuinely good advice — for the right corpus. The mistake is treating it as universally applicable.

The thing that actually makes a RAG system production-ready isn't the sophistication of the retrieval strategy. It's knowing, with evidence, whether your retrieval strategy is working. That requires an evaluation framework built before you start optimizing.

Write the questions first. Measure before and after every change. Let the numbers tell you what to ship.

---

*The full evaluation code, migration script, and results are in the project repo. Four retrieval modes, two corpora, reproducible with a single command.*
