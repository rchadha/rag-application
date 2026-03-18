# Product Ideas & Roadmap

## What We Have Today

- RAG over SEC filings + earnings calls + daily news for any stock ticker
- Clean REST API (AWS Lambda + API Gateway) that any frontend can call
- Multi-company ready via Pinecone namespaces (just ingest a new ticker)
- Sentiment scoring on news articles (VADER)
- Evaluation framework for retrieval quality (cross-encoder eval)

---

## Who Would Pay For This

### 1. Retail Investors / Individual Traders (~$20-50/mo)
- People who want to research stocks before investing but don't want to read 200-page SEC filings
- "Chat with NVIDIA's 10-K" is genuinely useful for someone deciding whether to buy

### 2. Financial Analysts at Small Firms (~$100-300/mo)
- Junior analysts spend hours reading filings — this speeds up their workflow
- Competitive differentiation vs Bloomberg (which costs $24K/year)

### 3. Finance Students / MBA Programs (~$15-30/mo)
- Research tool for learning fundamental analysis

---

## What's Missing Before You Can Sell It

1. **Multi-company support** — only NVDA is indexed today; need to let users pick or request companies
2. **User authentication** — no concept of accounts, API keys per user, or usage limits
3. **More tickers** — value increases significantly with 50+ companies covered
4. **Conversation memory** — each query is stateless; no follow-up questions across turns
5. **Better answer quality** — responses could cite specific filing dates and quote exact passages
6. **Data freshness indicator** — users need to know when data was last updated

---

## Realistic Path to $1K MRR

1. **Pick a niche** — don't do "all stocks", start with AI/semiconductor companies (NVDA, AMD, INTC, TSMC, QCOM) — 5-10 companies indexed well
2. **Build a waitlist landing page** — validate demand before building more
3. **Freemium model** — 3 free queries/day, charge for unlimited access
4. **Target retail investors on Reddit** — r/investing, r/stocks, r/wallstreetbets — they are already the demographic

---

## Competitive Landscape

Existing players include Perplexity Finance and various AI finance tools, but none combine:
- Deep RAG over specific SEC filings
- Earnings call transcripts
- Daily news with sentiment

The angle is **depth over breadth** — better answers on fewer companies rather than shallow answers on everything.

---

## Technical Gaps to Address

### Short Term
- [ ] Ingest more tickers (AMD, INTC, TSMC, QCOM)
- [ ] Add data freshness metadata to API responses
- [ ] Add conversation history support (pass prior turns in context)

### Medium Term
- [ ] User authentication (NextAuth or Clerk)
- [ ] Per-user API keys and usage tracking
- [ ] Rate limiting and usage quotas
- [ ] Admin dashboard for monitoring ingestion and query volume

### Long Term
- [ ] Automated daily ingestion pipeline (AWS EventBridge cron → Lambda)
- [ ] User-requested company coverage
- [ ] Answer quality improvements (exact citations, filing dates in responses)
- [ ] Pricing page and payment integration (Stripe)
