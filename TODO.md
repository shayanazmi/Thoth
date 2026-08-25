# Thoth · TODO & Known Issues
> Last updated: August 2026 · Status key: 🔴 Bug · 🟡 Degraded · 🟢 Working · 🔵 Planned

---

## 🔴 Critical Bugs (Fix First)

### 1. Search Query Bloat — Wrong Query Passed to Search Agent
**File:** `backend/agents.py` / `backend/orchestrator.py` (search node)
**Symptom:** After the Writer runs, the query string gets replaced with the full report text.
The Snowball agent then sends the entire report as a search query, returning garbage results
(e.g., a CERN physics paper for an alopecia query).
**Root Cause:** `state["query"]` or `state["report"]` is mutated/overwritten before the
second retrieval pass. The original topic is lost.
**Fix:** Lock the original topic into `state["original_topic"]` at graph entry. Use that
as the immutable search anchor throughout all retrieval nodes — never overwrite it.

---

### 2. Groq Fallback Model Does Not Exist
**File:** LLM config in `backend/agents.py` or `backend/pipeline.py`
**Symptom:**
  ERROR: Fallback provider (Groq): 'The model llama-3.3-70b-versatile does not exist'
**Fix:** Update to a valid Groq model. Check https://console.groq.com/docs/models.
Current valid options: `llama3-70b-8192`, `mixtral-8x7b-32768`, `gemma2-9b-it`.

---

### 3. Token Budget Truncation Too Aggressive
**File:** `backend/memory/` (session memory)
**Symptom:** WARNING: Truncating text slice from 73509 to 2500 tokens.
**Impact:** Writer has almost no source text. Explains low Faithfulness scores (3.0/10).
**Fix:** Raise limit to 16k–32k tokens. Use keyword-overlap extraction instead of blind
head-truncation so the most relevant paragraphs are preserved.

---

### 4. Hero Launch Bypasses Mode Routing
**File:** `web/js/app.js` → handleHeroLaunch()
**Symptom:** Landing page hero prompt always calls startResearch() — even for casual greetings.
**Fix:** Add casual query check before launching the swarm. Or rename the hero box to
"Research Topic" to set expectations.

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

## 🔵 Planned Features

### 9. Streaming Writer Output to UI (High Priority)
Use NVIDIA NIM streaming API for the Writer node. Stream tokens to the UI in real-time
so the user sees the report being written word-by-word instead of waiting 3–5 min for
the full batch.

### 10. Persistent Cross-Session Vault QA (Medium)
Index all vault notes into a persistent vector store (ChromaDB or FAISS) that survives
server restarts. Currently Vault QA only queries the current session's notes.

### 11. Source Relevance Pre-Filtering (Medium)
Add cosine similarity check between paper abstract and original topic before adding
to scrape queue. Filters out off-topic papers before they waste scrape budget.

### 12. Expand Report — Append vs Replace (Low)
"Expand Report" mode should append the new section to the existing report,
not replace the whole report panel. UI needs a merge/append render path.

### 13. Remove/Replace Streamlit stub app.py (Low)
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
