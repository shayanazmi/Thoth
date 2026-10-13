<div align="center">

<img src="web/assets/thoth_logo.png" alt="Thoth Logo" width="130" style="border-radius: 20px; box-shadow: 0 10px 30px rgba(201, 154, 107, 0.35); margin-bottom: 12px;"/>

# THOTH · THE DIVINE SCRIBE
### Autonomous Multi-Agent Academic Intelligence & Epistemic Synthesis Studio

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg?style=flat-square&logo=python&logoColor=white)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/backend-FastAPI-009688.svg?style=flat-square&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Railway](https://img.shields.io/badge/deploy-Railway-0B0D0E.svg?style=flat-square&logo=railway&logoColor=white)](https://railway.app)
[![Supabase](https://img.shields.io/badge/auth%20%26%20db-Supabase-3ECF8E.svg?style=flat-square&logo=supabase&logoColor=white)](https://supabase.com)
[![Redis](https://img.shields.io/badge/caching-Redis-DC382D.svg?style=flat-square&logo=redis&logoColor=white)](https://redis.io)
[![Tests Passing](https://img.shields.io/badge/tests-360%20passing-brightgreen.svg?style=flat-square)](tests/)

**Thoth** is an autonomous multi-agent academic research intelligence engine. It combines recursive scholarly retrieval (ArXiv, Semantic Scholar, Tavily), dual-key claim-evidence provenance verification, 10 epistemic philosopher reasoning desks, a persistent knowledge vault graph, and an interactive celestial research studio.

<br/>

<img src="web/assets/thoth_hero.jpg" alt="Thoth Studio Preview" width="850" style="border-radius: 12px; box-shadow: 0 10px 30px rgba(0, 0, 0, 0.6);"/>

</div>

---

## ⚡ Quickstart (5 Commands Max)

```bash
git clone https://github.com/shayanazmi/Thoth.git && cd Thoth
python3 -m venv venv && source venv/bin/activate
pip install -r backend/requirements.txt
cp .env.example .env  # Add your NVIDIA_API_KEY and TAVILY_API_KEY
python -m uvicorn web_server:app --port 8000
```
Open **`http://localhost:8000`** in your browser to launch the studio.

---

## 🏛️ System Architecture

```mermaid
flowchart LR
    Client["Client Browser<br/>(Research Studio)"]
    
    subgraph Railway["Railway Cloud Platform"]
        Web["Web Service<br/>(Railway Static / SPA)"]
        Backend["Backend Service<br/>(FastAPI Orchestrator)"]
        Redis[("Redis Add-on<br/>(Cache & Rate Limits)")]
    end

    subgraph SupabaseCloud["Supabase Managed Platform"]
        SupaAuth["Supabase Auth<br/>(GoTrue JWT)"]
        SupaDB[("PostgreSQL DB<br/>(pgvector + RLS)")]
    end

    Client -->|HTTPS| Web
    Client -->|Session Auth| SupaAuth
    Client -->|Bearer JWT + SSE| Backend

    Backend -->|Cache Query / Rate Check| Redis
    Backend -->|Verify JWT / Persist Graph| SupaDB
```

---

## 📚 Documentation Index

All technical, operational, and architectural documentation is maintained in [`docs/`](docs/):

- 🏛️ **[System Architecture](docs/architecture.md):** In-depth component breakdown, multi-agent pipeline, and data contracts.
- 🛠️ **[Local Setup & Development](docs/setup.md):** Local setup, venv configuration, Supabase, Redis, and testing.
- 🔑 **[Environment Variables](docs/env-vars.md):** Full configuration matrix, defaults, and secret rules.
- 🔐 **[Authentication Flow](docs/auth-flow.md):** Supabase GoTrue Auth, client session handling, and backend JWT validation.
- 🗄️ **[Database Schema & Migration](docs/database-schema.md):** PostgreSQL DDL, `pgvector` indexing, and Row Level Security (RLS).
- ⚡ **[Caching & Rate Limiting](docs/caching.md):** Redis key namespaces, TTL policies, and fail-open in-memory fallback.
- 🚀 **[Railway Deployment Guide](docs/deployment.md):** Multi-service Railway configuration, containerfiles, and networking.
- 🛡️ **[API Limit & Vendor Resilience](docs/api-limits.md):** Token bucket limits, backoff strategies, and 3-tier LLM failover.
- 📖 **[Operations Runbook](docs/runbook.md):** Health endpoints (`/health`, `/ready`), incident response, and diagnostics.
- 📑 **[Architecture Decision Records](docs/decisions/):** ADR-001 (Monorepo), ADR-002 (Supabase), ADR-003 (Redis), ADR-004 (Decoupled Web).

---

## 🧩 The 10 Epistemic Frameworks

Thoth incorporates 10 classical and scientific frameworks into its critique and sparring tribunal:

| Thinker | Core Epistemic Angle | Operational Role in Thoth |
| :--- | :--- | :--- |
| **Aristotle** | Deductive Certainty | Formal categorical taxonomy & syllogistic validation |
| **Bacon** | Inductive Empiricism | Systematic elimination of preconceptions & idols |
| **Descartes** | Foundational Doubt | Radical methodological skepticism & decomposition |
| **Hume** | Empiricist Skepticism | Rigorous challenge to inductive inference & correlation |
| **Darwin** | Evolutionary Selection | Competitive variation & hypothesis fitness testing |
| **Popper** | Critical Falsification | Aggressive search for counterexamples & disproof |
| **Kuhn** | Paradigm Dynamics | Detection of scientific anomalies & framework limits |
| **Simon** | Bounded Rationality | Computational constraint audit & heuristic satisficing |
| **Turing** | Computability | Operational state-machine testing & algorithmicity |
| **Box** | Pragmatic Fallibilism | Model usefulness verification ("All models are wrong...") |

---

## 🧪 Testing & Verification

```bash
# Run unit & schema tests
pytest tests/test_schemas.py tests/test_pure_functions.py -v

# Run 7-layer system diagnostic
python scripts/dev/diagnostic_test.py
```

---

## 📜 License
Released under the [MIT License](LICENSE).
