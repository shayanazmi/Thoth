# Thoth · TODO & Known Issues
> Last updated: August 2026 · Status key: 🔴 Bug · 🟡 Degraded · 🟢 Working · 🔵 Planned

---

## 🟢 Resolved Critical Issues

### 1. Search Query Bloat — Sanitization & Query Protection (Resolved)
- **Fix:** Added `_sanitize_academic_query()` in `backend/scholarly.py` to strip multiline paragraphs, markdown noise, and distill queries to concise, high-signal academic keywords before querying arXiv, EuropePMC, PubMed, Semantic Scholar, and OpenAlex.

### 2. Groq Fallback Model Name (Resolved)
- **Fix:** Updated `backend/agents.py` fallback to use universally supported Groq models (`llama-3.1-8b-instant` default, with `GROQ_FALLBACK_MODEL` environment variable support).

### 3. Token Budget Truncation (Resolved)
- **Fix:** Expanded `DEFAULT_TOKEN_BUDGET["retrieved_notes"]` to 16,000 tokens and introduced dedicated `RESEARCH_WRITER_TOKEN_BUDGET["retrieved_notes"]` (32,000 tokens) in `backend/memory/session.py` and `backend/pipeline.py` so the Writer receives full scraped papers without starving context.

### 4. Hero Launch Casual Routing (Resolved)
- **Fix:** Added regex greeting check in `handleHeroLaunch()` in `web/js/app.js` to route casual greetings ("hi", "hello") directly to fast chat instead of triggering the 8-agent swarm.

---

### 5. Snowball Agent Multi-Corpus ID Resolution (Resolved)
- **Fix:** Enhanced `_normalize_s2_id()` in `backend/scholarly.py` to recognize and format `ARXIV:`, `DOI:`, and `CorpusId:` prefixes. Prioritized ArXiv IDs over pseudo-DOIs and enabled automatic fallback to OpenAlex related works if Semantic Scholar is rate-limited.

### 6. NVIDIA NIM LLM Lifecycle & Timeout Handling (Resolved)
- **Fix:** Migrated primary verifier LLM to `nvidia/nemotron-3.5-lightning-30b-a3b` with `enable_thinking: False` and temperature 0.1, with resilient Groq fallback and timeout protection.

### 7. Verifier Plausible Inference Tier (Resolved)
- **Fix:** Refined `verifier_prompt` in `backend/agents.py` to distinguish hard factual contradictions (which are penalized) from valid high-level domain synthesis and logical extensions (which are preserved and validated).

### 8. HuggingFace Rate Limiting on Startup (Resolved)
- **Fix:** Added `HF_TOKEN` support to `SentenceTransformer` lazy loader in `backend/memory/index.py` and documented it in `.env.example`.

### 9. Persistent SQLite Query & Scraped Content Cache (Resolved)
- **Fix:** Added `http_cache` table and `get_cached_response` / `set_cached_response` utilities in `backend/memory/db.py` to cache repeated search queries and paper scrapes.

---

## 🟡 Under Active Development & Planned Features

## 🔵 Planned Features & Architectural Milestones

### 9. The "Pantheon of Rigor": Adversarial Peer-Review Board (High Priority)
**Vision & Philosophy:** Modern academic publishing and arXiv are flooded with low-quality,
jargon-heavy, regurgitated papers with zero genuine novelty ("complicated technical bullshit").
To ensure Thoth-generated intelligence reports and identified knowledge gaps reach publication-grade
standards for top-tier **Q1 Scopus, Nature, ACM, and IEEE journals**, we are implementing an
adversarial peer-review tribunal composed of specialized personality agents representing history's
greatest scientific and philosophical minds:

- **Richard Feynman (First-Principles Clarity & Anti-Jargon Razor)**:
  - *Lens:* Relentlessly attacks obfuscated math and hollow academic jargon.
  - *Evaluation:* "Can this mechanism be explained simply from first principles? Is there real physical/operational substance, or is complexity being used as camouflage?"
  
- **Socrates (The Elenctic Inquisitor & Assumption Destroyer)**:
  - *Lens:* Cross-examines all foundational axioms, definitions, and implicit assumptions.
  - *Evaluation:* "Why is this assumed to be true? What hidden bias or circular reasoning exists in this hypothesis?"

- **Alan Turing (Computational Rigor & Algorithmic Provability)**:
  - *Lens:* Mathematical soundness, computability, algorithmic complexity, and formal proof bounds.
  - *Evaluation:* "Is this computationally tractable? Does the proposed algorithm genuinely solve the complexity, or merely displace it?"

- **Albert Einstein (Paradigmatic Shift & Thought-Experiment Stress-Tester)**:
  - *Lens:* Evaluates true scientific novelty vs incremental hyper-parameter tweaking.
  - *Evaluation:* "Does this hypothesis move the frontier of science? How does it hold under extreme limit cases and Gedankenexperiments (thought experiments)?"

- **Plato & Aristotle (Ontological Coherence & Taxonomy Architect)**:
  - *Lens:* Structural categorization, theoretical completeness, and universal conceptual alignment.
  - *Evaluation:* "Does this proposed taxonomy violate known domain ontologies or introduce incoherent abstractions?"

**Execution Pipeline Integration:**
- The Pantheon runs as an **Adversarial Gate** in the LangGraph Replan loop between the Writer and the Vault.
- Every report must pass a **Novelty & Rigor Consensus Score**. If Feynman flags excessive jargon or Socrates flags ungrounded assumptions, the draft is rejected and routed back with structured de-jargonizing and evidence-grounding directives.

---

### 10. Streaming Writer Output to UI (High Priority)
Use NVIDIA NIM streaming API for the Writer node. Stream tokens to the UI in real-time
so the user sees the report being written word-by-word instead of waiting 3–5 min for
the full batch.

### 11. Persistent Cross-Session Vault QA (Medium)
Index all vault notes into a persistent vector store (ChromaDB or FAISS) that survives
server restarts. Currently Vault QA only queries the current session's notes.

### 10. Source Relevance Pre-Filtering (Resolved)
- **Fix:** Added `rank_sources_by_relevance()` using normalized SentenceTransformer embeddings in `backend/scholarly.py` and integrated into `scrape_node` in `backend/pipeline.py` to pre-filter off-topic sources before scraping.

### 11. Expand Report — Append vs Replace (Resolved)
- **Fix:** Updated `web/js/app.js` and `backend/pipeline.py` to seamlessly append new synthesized sections to the right-hand report pane and chat bubble simultaneously.

### 12. Application Launcher Modernization (Resolved)
- **Fix:** Replaced legacy Streamlit forwarding stub in root `app.py` with direct Uvicorn launcher booting `web_server:app` on port 8000.

### 13. One-Click Report Export Toolbar, BibTeX/APA Citation Generators & Wikilinks (Resolved)
- **Fix:** Added export toolbar (Copy Markdown, Download `.md`, Export PDF, Word count & read time), automated BibTeX / APA citation copiers, and interactive Obsidian `[[wikilink]]` badge navigators in `web/js/app.js` and `web/css/styles.css`.

---

## 🟡 Under Active Development & Planned Features

## 🔵 Planned Features & Architectural Milestones

### 9. The "Pantheon of Rigor": Adversarial Peer-Review Board (On Hold - Research Pending)
**Vision & Philosophy:** Modern academic publishing and arXiv are flooded with low-quality,
jargon-heavy, regurgitated papers with zero genuine novelty ("complicated technical bullshit").
To ensure Thoth-generated intelligence reports and identified knowledge gaps reach publication-grade
standards for top-tier **Q1 Scopus, Nature, ACM, and IEEE journals**, we are implementing an
adversarial peer-review tribunal composed of specialized personality agents representing history's
greatest scientific and philosophical minds:
- Richard Feynman (Anti-Jargon Razor)
- Socrates (Assumption Destroyer)
- Alan Turing (Algorithmic Provability)
- Albert Einstein (Paradigmatic Shift & Gedankenexperiments)
- Plato & Aristotle (Ontological Coherence)
*(Note: Explicitly held ON HOLD until research and formulation are completed)*

---

## ✅ Resolved (August 2026 Session)

- SSE stream not rendering → Fixed: sse_starlette sends CRLF (\r\n\r\n), not LF (\n\n). Added buffer.replace(/\r\n/g, '\n') before split in app.js.
- "hi" triggering 8-agent swarm → Fixed: Default mode = fast_chat. Research requires explicit button toggle.
- Browser caching stale app.js → Fixed: Version bumped to ?v=3.5 in index.html.
- Confident AI warning spam → Fixed: logging.getLogger("confident").setLevel(CRITICAL).
- Casual queries mis-routed to research → Fixed: handleChatSend() simplified routing.
- Report export toolbar & BibTeX/APA copy → Added one-click Markdown/PDF export and citation generators.
- Interactive Obsidian wikilinks → Added clickable badges in report and chat feeds.
