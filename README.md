# Thoth · The Divine Scribe
### Autonomous Multi-Agent Academic Research & Synthesis Engine

<div align="center">

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![LangGraph](https://img.shields.io/badge/orchestration-LangGraph-orange.svg)](https://github.com/langchain-ai/langgraph)
[![NVIDIA NIM](https://img.shields.io/badge/inference-NVIDIA%20NIM-76B900.svg)](https://build.nvidia.com)
[![FastAPI](https://img.shields.io/badge/backend-FastAPI-009688.svg)](https://fastapi.tiangolo.com)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**Thoth** is an autonomous multi-agent research and synthesis engine that discovers, scrapes, cross-verifies, and synthesizes complex scientific literature into structured, publication-grade intelligence reports — served through a real-time streaming web studio.

</div>

---

## Table of Contents

- [Vision & Problem](#vision--problem)
- [Architecture](#architecture)
- [Agent Pipeline](#agent-pipeline)
- [Chatbot Modes](#chatbot-modes)
- [Tech Stack](#tech-stack)
- [Repository Structure](#repository-structure)
- [Getting Started](#getting-started)
- [Environment Configuration](#environment-configuration)
- [Known Issues & Roadmap](#known-issues--roadmap)

---

## Vision & Problem

Standard LLM generation hallucinates. Standard RAG does shallow top-k vector retrieval without verifying claims or tracing cross-domain connections.

**Thoth** resolves this by splitting the research process into a **deterministic, cyclic self-correcting LangGraph state machine**:

1. **Live Scholarly Retrieval** — arXiv, Semantic Scholar, PubMed, Europe PMC, Tavily
2. **Citation Graph Expansion (Snowball)** — forward/backward reference traversal
3. **Deterministic DOM Scraping** — BeautifulSoup full-text extraction
4. **SLM Truth Guard** — claim-by-claim factual verification against retrieved sources
5. **LLM-as-Judge Critic** — 5-dimension rubric scoring (Faithfulness, Relevance, Completeness, Evidence Quality, Clarity)
6. **Self-Correcting Replan Loop** — routes failed drafts back to the Writer with critic feedback
7. **Obsidian Vault Indexer** — bidirectional `[[wikilinks]]`, SQLite metadata, knowledge graph

---

## Architecture

```
User Query
    │
    ▼
┌──────────────────────────────────────┐
│         FastAPI SSE Gateway          │
│  (web_server.py · sse_starlette)     │
└──────────┬───────────────────────────┘
           │
    ┌──────▼──────┐
    │  Intent     │  fast_chat  ──► Llama-3.1-8B (direct, <500ms)
    │  Router     │
    │             │  deep_research ──► 8-Agent Swarm (below)
    └─────────────┘

8-Agent Swarm (LangGraph StateGraph):
┌─────────┐   ┌──────────┐   ┌────────┐   ┌────────┐
│ SEARCH  │──►│ SNOWBALL │──►│ SCRAPE │──►│ WRITER │
└─────────┘   └──────────┘   └────────┘   └───┬────┘
                                               │
                                    ┌──────────┴──────────┐
                                    ▼                     ▼
                               ┌─────────┐          ┌─────────┐
                               │VERIFIER │          │ CRITIC  │
                               └────┬────┘          └────┬────┘
                                    └────────┬───────────┘
                                             ▼
                                    Score ≥ 7.0? ──Yes──► VAULT
                                         │
                                        No
                                         │
                                    Attempt < 2? ──Yes──► WRITER
                                         │
                                        No
                                         ▼
                                    VAULT (best draft)
```

---

## Agent Pipeline

| Step | Agent | Model | Purpose |
|------|-------|-------|---------|
| 1 | **Search** | — | arXiv + Semantic Scholar + PubMed + EuropePMC |
| 1.5 | **Snowball** | — | Citation graph expansion |
| 2 | **Scrape** | — | Full-text DOM extraction (concurrent) |
| 3 | **Writer** | Nemotron-30B | Synthesis report drafting |
| 4 | **Verifier (Truth Guard)** | Llama-3.1-8B | Claim-by-claim source verification |
| 5 | **Critic** | Nemotron-30B | 5-dimension rubric scoring |
| 6 | **Replan** | LangGraph | Routes back to Writer if score < 7 |
| 7 | **Vault** | — | Obsidian MD + SQLite persistence |

---

## Chatbot Modes

| Mode | Trigger | Model | Latency |
|------|---------|-------|---------|
| **Chat** (default) | Type anything | Llama-3.1-8B | < 500ms |
| **Deep Research** | Click 🔬 button | Full 8-agent swarm (Nemotron-30B) | 3–10 min |
| **Web Probe** | Mode menu | Llama-3.1-8B + Tavily | ~5s |
| **Vault QA** | Mode menu | Llama-3.1-8B + SQLite | ~2s |
| **Expand Report** | Mode menu | Nemotron-30B | ~30s |

Chat is the **default**. Deep Research is **explicit opt-in** via the 🔬 toggle button.

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Orchestration | LangGraph (cyclic StateGraph) |
| Primary LLM | NVIDIA NIM — `nvidia/llama-3.1-nemotron-70b` |
| Fast SLM | NVIDIA NIM — `meta/llama-3.1-8b-instruct` |
| Fallback LLM | Groq — `llama-3.3-70b-versatile` |
| Embeddings | `sentence-transformers/all-MiniLM-L6-v2` (local) |
| Web Server | FastAPI + sse_starlette (SSE streaming) |
| Frontend | Vanilla JS + CSS (Alpine-free, no framework) |
| Animations | Anime.js (3D parallax, accordions) |
| Icons | Lucide |
| Evaluation | deepeval (local offline mode) |
| Vault | Obsidian-compatible Markdown + SQLite |
| Search | arXiv API, Semantic Scholar, PubMed, EuropePMC, Tavily |

---

## Repository Structure

```
thoth/
├── backend/
│   ├── agents.py          # LangGraph node implementations (Search, Snowball, Scrape, Writer, Verifier, Critic, Vault)
│   ├── orchestrator.py    # LangGraph StateGraph definition & conditional edge routing
│   ├── pipeline.py        # High-level pipeline runner & session memory
│   ├── scholarly.py       # Multi-source scholarly search & scraping (arXiv, PubMed, EuropePMC, Tavily)
│   ├── dispatcher.py      # Fast-path conversational router (chat vs research intent)
│   ├── telemetry.py       # DeepEval local tracing (offline mode, no cloud key needed)
│   └── eval/              # Evaluation harness (metrics, datasets, runner)
│       ├── metrics.py
│       ├── datasets.py
│       └── runner.py
├── web/
│   ├── index.html         # Research Studio single-page app
│   ├── css/styles.css     # Full design system (dark mode, glassmorphism, tokens)
│   └── js/
│       ├── app.js         # Chat engine, SSE stream parser, mode routing
│       └── animations.js  # Anime.js 3D parallax & micro-animations
├── vault/
│   ├── topics/            # Generated research reports (Obsidian MD, .gitignored)
│   └── sources/           # Scraped source documents (Obsidian MD, .gitignored)
├── scripts/
│   ├── run_evals.py
│   └── run_multiturn_simulation.py
├── tests/                 # DeepEval test suites
├── web_server.py          # FastAPI app — SSE endpoints (/api/research/stream, /api/followup/stream)
├── run_web.py             # One-click launcher (uvicorn + auto browser open)
├── .env.example           # Environment variable template
├── requirements.txt
└── README.md
```

---

## Getting Started

### Prerequisites
- Python 3.10+
- NVIDIA NIM API key (free tier available at [build.nvidia.com](https://build.nvidia.com))
- Optionally: Groq API key (fallback LLM), Tavily API key (web search)

### Installation

```bash
git clone <your-repo-url>
cd thoth

python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

pip install -r requirements.txt
```

### Environment Setup

```bash
cp .env.example .env
# Edit .env and add your API keys
```

### Run

```bash
./venv/bin/python run_web.py
```

Opens automatically at `http://127.0.0.1:8000`.

---

## Environment Configuration

See [`.env.example`](.env.example) for all variables. Key ones:

| Variable | Required | Purpose |
|----------|----------|---------|
| `NVIDIA_API_KEY` | ✅ Yes | Primary LLM (Nemotron-30B, Llama-8B) |
| `GROQ_API_KEY` | ⚠️ Recommended | Fallback LLM when NVIDIA times out |
| `TAVILY_API_KEY` | Optional | Web search agent |
| `SEMANTIC_SCHOLAR_API_KEY` | Optional | Higher rate limits on S2 |

> **Note:** Confident AI / DeepEval cloud tracing is **not required**. Thoth runs deepeval in local offline mode automatically.

---

## Known Issues & Roadmap

See [`TODO.md`](TODO.md) for the full tracked issue list and planned improvements.
