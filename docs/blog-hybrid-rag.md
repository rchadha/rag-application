# I Tried the "Production-Ready RAG" Playbook. Here's What Actually Happened.

I've been building a RAG application over NVIDIA's SEC filings and earnings call transcripts. The idea is simple: let users ask natural language questions and get answers grounded in the actual filings, not hallucinated summaries.

After getting the basics working, I started reading about how to make retrieval better. One article I came across described a pattern that's become almost standard advice in the RAG community:

> *"To graduate from a simple demo to a production-ready system, implement Hybrid Retrieval (vector search + BM25 keyword search) combined with Cross-Encoder Reranking. This consistently and dramatically improves precision."*

That sounded reasonable to me. So I built it. Then I measured it. Then I got surprised.

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

## Phase 1: Testing Cross-Encoder Reranking

A cross-encoder reranker works differently from the initial vector search. Instead of comparing a single query embedding against thousands of document embeddings in one shot, it takes each (query, document) pair and evaluates them together through a transformer model. It's slower, but in theory more accurate because it can model the interaction between the query and the document directly.

The standard pattern:
1. Dense retrieval gives you top 10 candidates (fast)
2. Cross-encoder rescores all 10 by reading the full query + chunk together (slower but smarter)
3. Return the top 3 from the reranked list

I used `BAAI/bge-reranker-base`, which is a well-regarded open-source reranker.

**The results:**

| Approach | Hit@1 | Hit@3 | MRR |
|---|---|---|---|
| Dense baseline | **0.875** | 0.875 | **0.875** |
| Dense + Reranker | 0.625 | **1.000** | 0.771 |

The reranker actually made top-1 precision *worse*. Hit@1 dropped from 87.5% to 62.5%.

There was one silver lining: Hit@3 improved from 87.5% to 100%. The reranker did find that one question the baseline was missing in the top 3 — it just shuffled the rankings in a way that hurt the #1 slot for other questions.

My instinct at this point was: maybe the reranker is working with too narrow a candidate pool. If the right document wasn't in the dense top 10, the reranker can't help. What if I give it better raw material?

---

## Phase 2: Adding Hybrid Retrieval (BM25 + Dense + RRF)

This is where the "production-ready" advice comes in. The idea is:

- Dense semantic search is great at understanding *intent* ("what did NVIDIA say about their competitive position") but sometimes misses documents that contain the exact keywords the user typed
- BM25 keyword search is great at exact matches (ticker symbols, specific product names, dates) but doesn't understand meaning
- Combining them gives you the strengths of both

**The implementation challenge:** Pinecone's native hybrid search (sparse + dense vectors) requires an index with `dotproduct` metric. My existing index uses `cosine`. Rebuilding the index would mean re-embedding 974 document chunks and paying for those OpenAI API calls again.

Instead, I implemented hybrid retrieval using **Reciprocal Rank Fusion (RRF)** entirely in Python. No Pinecone changes, no re-embedding, zero API cost.

Here's how RRF works:

```python
def reciprocal_rank_fusion(dense_results, bm25_results, k=60):
    scores = {}

    for rank, doc in enumerate(dense_results, start=1):
        scores[doc["source"]] = scores.get(doc["source"], 0) + 1 / (k + rank)

    for rank, doc in enumerate(bm25_results, start=1):
        scores[doc["source"]] = scores.get(doc["source"], 0) + 1 / (k + rank)

    return sorted(scores.items(), key=lambda x: x[1], reverse=True)
```

The `k=60` is a standard smoothing constant. The formula means: a document ranked #1 in both lists scores roughly `2 / 61 = 0.033`, while a document ranked #1 in only one list scores `1 / 61 = 0.016`. Documents that both retrievers agree on float to the top.

For the BM25 side, I used the `rank_bm25` Python library. I fetched all existing document texts from Pinecone metadata (they're stored there by LangChain) and built a local BM25 index — no external service needed.

**The results across all 4 modes:**

| Mode | Hit@1 | Hit@3 | MRR |
|---|---|---|---|
| Dense (baseline) | **0.875** | 0.875 | **0.875** |
| Dense + Reranker | 0.625 | 0.875 | 0.729 |
| Hybrid RRF | 0.625 | 0.875 | 0.729 |
| Hybrid RRF + Reranker | 0.125 | 0.875 | 0.438 |

The dense baseline won. On every metric that matters for a user getting the right answer first.

I also ran the same evaluation on my Finnhub news corpus (about 1,100 financial news articles):

| Mode | Hit@1 | Hit@3 | MRR |
|---|---|---|---|
| Dense (baseline) | **0.625** | **1.000** | **0.812** |
| Dense + Reranker | 0.500 | 0.875 | 0.688 |
| Hybrid RRF | 0.500 | 1.000 | 0.708 |
| Hybrid RRF + Reranker | 0.375 | 0.875 | 0.625 |

Same story. Dense wins.

---

## Why Didn't It Work?

After sitting with this for a while, I think the answer comes down to **corpus characteristics**.

**On the SEC filings:** These documents are formal, structured, and long-form. `text-embedding-3-small` was trained on exactly this kind of text. The dense retriever already has strong semantic understanding of legal and financial language. BM25 over SEC filings adds noise — every chunk contains the same boilerplate words ("NVIDIA", "fiscal year", "risk factors") so keyword scores don't discriminate well between relevant and irrelevant chunks.

**On the news corpus:** Articles are short, and many of them are topically similar — lots of articles mention "NVIDIA H100" or "data center demand" without being the most relevant to any specific question. BM25 latches onto the keyword overlap without understanding which article is actually about the query's intent.

**On the reranker failing on top of hybrid:** The reranker got a worse set of candidates to work with. When I diluted the clean dense top-10 with BM25 results that included lower-quality matches, the reranker had to pick from a noisier pool — and it made more mistakes as a result.

The hypothesis was right in theory: the reranker needs better raw material. But the BM25 didn't provide better material for *this specific corpus type*. It provided different material, and different turned out to be worse.

---

## What I Actually Learned

**1. Dense retrieval on a good embedding model is hard to beat on structured text.**

If your documents are formal, professional, and consistently written — SEC filings, legal contracts, technical documentation, academic papers — a good embedding model probably already captures what matters. BM25 is less likely to help and may hurt.

**2. Hybrid retrieval is more valuable when queries are lexically specific.**

If users are likely to search for exact ticker symbols (`$NVDA`), product version numbers (`H100 SXM5`), or proper nouns that embeddings might treat as semantically similar to other names, BM25 would add real value. My eval questions were intentionally conceptual ("what did NVIDIA say about...") which plays to dense's strengths.

**3. Evaluation is not optional — it's the work.**

If I hadn't built the eval framework before adding the reranker, I would have shipped a regression. The "advanced technique" felt like an improvement because I was implementing something more sophisticated. But sophisticated ≠ better. Measurement is the only thing that tells you which it is.

**4. The result that looks like failure is the result that teaches you something.**

Every blog post you read about RAG shows the technique working. This one doesn't. But I now have a precise, repeatable understanding of what my retrieval system does on my specific data. That's more valuable than a technique that made a number go up once and I don't understand why.

---

## What I'd Try Next

I'm not done with this. There are specific conditions under which I'd expect hybrid + reranking to help:

- A **larger eval set** (8 questions isn't much — some of these effects could be noise)
- Questions that include **specific entity names or dates** — BM25 should shine there
- A **domain-fine-tuned reranker** (the BGE and MS MARCO models are general-purpose; a reranker fine-tuned on financial Q&A could behave differently)
- **Larger candidate pool** before reranking (top 20 or 50 instead of top 10)

But I'll measure those too before shipping any of them.

---

## The Takeaway

The "production-ready RAG" playbook is real advice. Hybrid retrieval and cross-encoder reranking do help — in the right context. But "the right context" is something you can only know by measuring on your own data, with your own queries, against your own quality bar.

If there's one thing worth adding to your RAG project before you add any advanced retrieval technique, it's an evaluation dataset. Write 20 questions. Identify expected sources. Run it before and after every change.

That's the thing that actually makes a system production-ready.

---

*The full evaluation code, results, and implementation are in the project repo. The BM25 corpus indexer, the RRF implementation, and the 4-mode evaluation script are all there if you want to run this on your own data.*
