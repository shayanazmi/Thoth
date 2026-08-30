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

## 🟡 Degraded — Working But Needs Improvement

### 5. Snowball Agent Finds 0 New Papers
**Symptom:** "Snowballing discovered 0 new connected papers." on every run.
**Likely Cause:** Paper IDs from Step 1 aren't in the format Semantic Scholar's
references API expects (CorpusId vs raw ID).
**Fix:** Log exact API calls. Add fallback: try /citations endpoint if /references returns 0.

### 6. NVIDIA NIM Timeout on Writer Attempt 2+
**Symptom:** Read timed out (120s) on second Writer pass.
**Fix:** Increase Writer-specific timeout to 240s. Or implement streaming generation
so partial output is captured even on timeout.

### 7. Verifier Over-Flags Logical Inferences
**Symptom:** Claims like "FAIR principles can be applied to alopecia" marked invalid
even when they are reasonable logical extensions, not hallucinations.
**Fix:** Add a "plausible inference" tier in the verifier prompt. Only hard-flag:
(a) claims that contradict source material, (b) fabricated specific numbers/statistics.

### 8. HuggingFace Rate Limiting on Startup
**Symptom:** 20+ HTTP HEAD requests to HuggingFace on every server start (unauthenticated).
**Fix:** Add HF_TOKEN to .env.example. Pass it when initializing sentence-transformers.

---

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

### 12. Source Relevance Pre-Filtering (Medium)
Add cosine similarity check between paper abstract and original topic before adding
to scrape queue. Filters out off-topic papers before they waste scrape budget.

### 13. Expand Report — Append vs Replace (Low)
"Expand Report" mode should append the new section to the existing report,
not replace the whole report panel. UI needs a merge/append render path.

### 14. Remove/Replace Streamlit stub app.py (Low)
The root-level app.py is a 518-byte Streamlit stub that no longer reflects the
architecture. Delete it or update it to forward users to the FastAPI server.

---

## ✅ Resolved (August 2026 Session)

- SSE stream not rendering → Fixed: sse_starlette sends CRLF (\r\n\r\n), not LF (\n\n).
  Added buffer.replace(/\r\n/g, '\n') before split in app.js.
- "hi" triggering 8-agent swarm → Fixed: Default mode = fast_chat. Research requires
  explicit button toggle.
- Browser caching stale app.js → Fixed: Version bumped to ?v=3.4 in index.html.
- Confident AI warning spam → Fixed: logging.getLogger("confident").setLevel(CRITICAL).
- Casual queries mis-routed to research → Fixed: handleChatSend() simplified routing.
