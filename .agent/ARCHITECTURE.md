# 📐 Agent Architecture Quick Reference

## 1. Production Monorepo Stack
- **Web:** Railway Static / Nginx Container. Connects to Supabase Auth (`SUPABASE_ANON_KEY`) and makes authenticated REST / SSE calls to the backend (`API_BASE_URL`).
- **Backend:** FastAPI on Railway. Verifies Supabase JWTs, coordinates research agents, manages PostgreSQL repositories with RLS, and reads/writes Redis cache.
- **Database:** Supabase PostgreSQL with `pgvector` for embeddings and Row Level Security for multi-tenant isolation.
- **Cache:** Redis for sub-2ms HTTP query caching and token-bucket API rate limits.
- **Inference Providers:** Primary: NVIDIA NIM (`nemotron-3.5-lightning-30b-a3b`). Fallbacks: Groq (`gpt-oss-120b`, `gpt-oss-20b`) → OpenAI (`gpt-4o`).

## 2. Multi-Agent Data Pipeline
```
Query Input
   │
   ▼
Intent Router ──[casual/greeting]──▶ Direct Chat Response (Fast Path)
   │
[substantive research]
   ▼
1. Search Agent (ArXiv + Semantic Scholar + Tavily)
   │
2. Snowball Agent (Recursive Citation Traversal)
   │
3. Reader Agent (Scrape & Clean Markdown Extraction)
   │
4. Scribe Agent (Evidence-Backed Report Synthesis)
   │
5. Truth Guard (SLM Atomic Claim Verification)
   │
6. Critic Agent (LLM-as-Judge 4-Dimension Rubric Scoring)
   │
7. Mindmap Node (Hierarchical Conceptual Decomposition)
   │
8. Vault Node (Relational & Vector Knowledge Graph Indexing)
```

## 3. Thinker Desks
The 10 epistemological frameworks in `backend/intellectual_rigour/frameworks/` provide specialized intellectual sparring, critique, and synthesis:
- `aristotle`: Deductive certainty & categoricals
- `bacon`: Empirical observation & inductive tables
- `descartes`: Radical doubt & foundational axioms
- `hume`: Empiricist skepticism & causation testing
- `darwin`: Evolutionary variation & hypothesis survival
- `popper`: Falsificationism & refutation experiments
- `kuhn`: Paradigm anomaly detection
- `simon`: Bounded rationality & satisficing
- `turing`: Computability & procedural state machines
- `box`: Pragmatic modeling ("all models are wrong")
