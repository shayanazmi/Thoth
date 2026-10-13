# 🪶 Thoth: Autonomous Research Intelligence Studio — Project Context

## 1. What is Thoth?
**Thoth** (The Divine Scribe of Ma'at) is a production-grade autonomous multi-agent research intelligence system. Named after the ancient Egyptian deity of wisdom, science, truth, and equilibrium, Thoth is built to perform exhaustive, deep academic and technological research while eliminating hallucinations, bias, and epistemic drift.

## 2. Core Pillars
1. **Multi-Agent Recursive Research:**
   - Coordinated swarm of specialized agents: Searcher, Snowballer, Reader/Scraper, Scribe, Verifier, Critic, Mindmap Generator, and Vault Indexer.
2. **Dual-Key Provenance & Grounding:**
   - Every substantive claim must cite a verified source URL and extracted text passage.
   - SLM Truth Guard verifies atomic assertions before reports are published.
3. **10 Epistemological Frameworks:**
   - Embeds classical and modern theories of knowledge into reasoning desks:
     - Aristotle (Deduction & Categories)
     - Bacon (Inductive Empiricism)
     - Descartes (Foundational Doubt)
     - Hume (Skepticism & Causation)
     - Darwin (Evolutionary Hypothesis Testing)
     - Popper (Falsificationism)
     - Kuhn (Paradigm Shift Analysis)
     - Simon (Bounded Rationality)
     - Turing (Computability & Operationalism)
     - Box (Fallibilism & Pragmatic Modeling)
4. **Persistent Knowledge Vault Graph:**
   - Bi-directional knowledge graph linking sources, atomic notes, topics, and claims with typed semantic edges (`cites`, `supports`, `contradicts`, `part_of`, `defines`, `related`).
5. **Production Monorepo Topology:**
   - **Frontend:** Independent static / SPA service on Railway.
   - **Backend:** FastAPI Uvicorn service on Railway.
   - **Auth & DB:** Supabase (Auth, PostgreSQL with RLS, pgvector).
   - **Cache & Limits:** Redis (Railway add-on) for sub-millisecond query caching and token-bucket rate limiting.

## 3. Directory Map
```
thoth/
├── .agent/              # Agent context, architecture specs, rules & workflows
├── .agents/             # Mirror workspace customization root
├── docs/                # Architecture, setup, auth, database, caching, deployment, runbooks, ADRs
│   ├── archive/         # Preserved chat transcripts and historical notes
│   └── decisions/       # Architecture Decision Records
├── web/                 # Decoupled frontend client (Railway service)
│   ├── components/      # Modular UI components
│   ├── pages/           # View layouts
│   ├── lib/             # Supabase client (anon key only), API wrapper, config
│   ├── styles/          # Modern luxury dark-mode CSS
│   └── assets/          # Emblem, bust, scales, hero imagery
├── backend/             # Layered API, pipeline & services (Railway service)
│   ├── api/             # FastAPI routes (/api/research, /api/followup, /api/brainstorm, /api/vault)
│   ├── services/        # Orchestration, pipeline nodes, scholarly retrieval, thinker sparring
│   ├── repositories/    # Supabase PostgreSQL persistence (sessions, reports, vault)
│   ├── core/            # Config, Supabase JWT auth, Redis cache, rate limiting, logging, errors
│   ├── models/          # Pydantic v2 schemas
│   ├── intellectual_rigour/ # 10 Thinker framework specifications & matcher
│   ├── conversation/    # Escalation intent, research mandate synthesis, clarification
│   ├── memory/          # Vault graph, session memory, indexers
│   └── supabase/        # SQL migrations (RLS, pgvector) & seed data
├── scripts/             # Categorized utilities
│   ├── dev/             # 7-layer diagnostic test, local runner
│   ├── db/              # Migrations and seeders
│   ├── ops/             # Cache flush, health verification
│   └── eval/            # Pipeline evaluations & simulations
├── evals/               # Evaluation sandbox, persona simulations, benchmarks
├── tests/               # 360+ pytest integration and unit tests
└── archive/             # Preserved reference repositories & legacy assets
```
