# Phase 0.A5 — Vision §3 journey walkthrough

**Date:** 2026-10-23
**Vision reference:** `THOTH.docx` §3 "The end-to-end research journey"
**Method:** Each of the ten vision stages was mapped to the running system via (a) code trace, (b) TestClient probe (A3), (c) call-graph confirmation (A4), and (d) the earlier Explore agent's dynamic-reachability findings.

Each stage below is marked **WORKS** / **DIVERGES** / **MISSING**.

---

## Stage 1 — Open conversation

**Vision:** "The user may begin with curiosity, an observation, a discussion, or no predefined research question."

**Current reality:**
- `is_casual_query` in `routes_research.py:52-93` detects greetings, help, thanks, farewells with regex patterns.
- A casual turn routes to `direct_chat_chain.invoke` — bypasses the research pipeline.
- Non-casual turns go through mandate synthesis + brief preparation + approval gate.

**Status:** **DIVERGES.** The *backend* can handle open conversation, but the *frontend* presents mode toggles (`brainstormToggle`, `deepResearchToggle` in `frontend/index.html:356,360`) and a floating mode menu (`index.html:246-296`) that force the user to choose a lane. Vision §2 ("Conversation first") requires the opposite — the system infers depth, the user never picks.

**Phase 1 of the plan addresses this.**

---

## Stage 2 — Recognise a promising direction

**Vision:** "Thoth notices a potentially meaningful research idea and briefly explains why it may be worth investigating."

**Current reality:** No code anywhere auto-detects a research direction mid-conversation. The idea lifecycle (`routes_ideas.py` + `conversation/idea.py`) is purely user-driven — a POST to `/api/ideas/tentative` is required to even create a candidate, and only the frontend ever makes that call. Grep confirmed on the earlier Explore pass: zero non-test callers of `create_tentative_idea` beyond the explicit HTTP route.

**Status:** **MISSING** (critical vision gap).

**Phase 2 of the plan addresses this.**

---

## Stage 3 — Prepare without blocking

**Vision:** "Thoth prepares a focused research question and preliminary review plan while the user continues the conversation. Preparation must not freeze the interface or interrupt thinking."

**Current reality:**
- Backend: `POST /api/research/brief/prepare` runs synchronously, returns a `PENDING_APPROVAL` brief in one request. The brief lifecycle is clean.
- Frontend: the SSE consumer in `js/app.js:676-770` (`startResearch`) keeps the chat textarea live (`setGenerating` only swaps the send icon, verified in A3). The chat input is **not** gated during a run.

**Status:** **MOSTLY WORKS** on the backend, **the UX fallout is cosmetic** — a "preparing a research plan" affordance that is clearly non-blocking in the UI copy is missing. The behaviour is right; the frame around it isn't.

**Phase 1 of the plan tightens the UX frame.**

---

## Stage 4 — Seek approval for substantial work

**Vision:** "When the plan is ready, Thoth presents it and waits for approval before launching the literature review."

**Current reality:**
- Hard gate at `routes_research.py:193-249`. A `POST /api/research/stream` without an approved brief emits an `approval_barrier` SSE event + `complete` and never spawns a worker thread. Verified live in A3.
- `verify_brief_approval` in `conversation/brief.py:556-612` checks `status == APPROVED`, `approved_version == version`, and optional `expected_version`. Prior approvals auto-invalidate on substantive edits.
- Durable task lifecycle: `research_tasks` table + atomic SQL claim + orphan reconciliation at startup. Verified booting in A1.

**Status:** **WORKS** on the main path. **Caveat:** the `mode == "fast_chat"` bypass flagged in the plan (phase 1) has not been empirically triggered yet, but the code path at `routes_research.py:121` is real. Phase 1 removes it.

---

## Stage 5 — Brainstorm with evidence and perspectives

**Vision:** "The user and Thoth continue examining assumptions, connections, explanations, and objections, including relevant intellectual frameworks."

**Current reality:**
- `/api/brainstorm/match` + `/api/brainstorm/chat` + `/api/brainstorm/thinkers` work — verified in A3 (fallback to heuristic Popper when NVIDIA was unreachable; honest fail-open).
- But the ten frameworks are **not** invoked anywhere inside `backend/orchestrator.py` or `backend/pipeline.py`. They are reachable only via (i) the `/api/brainstorm/*` endpoints and (ii) a slash-command branch in the followup turn (`pipeline.py:1308-1310, 1673-1674`).
- A research run therefore does not consult a thinker when drafting, critiquing, or synthesizing — unless the user explicitly invokes `/aristotle`, `/popper` etc. in a follow-up.

**Status:** **DIVERGES** from vision §6.3 ("Thinkers integrated across brainstorming, hypothesis formulation, literature interpretation, and critical review").

**Phase 4 of the plan addresses this with an `invoke_thinker_when_useful` helper gated on `attack_surface` detection.**

---

## Stage 6 — Run a literature review

**Vision §5.4:** "Early brainstorming should use a lightweight literature scan. When Thoth recognises that an idea is becoming a serious research question, formal report, or manuscript, it should recommend a PRISMA-aligned review and obtain approval."

**Current reality:**
- `prisma_node` is called unconditionally at `orchestrator.py:391-393`. Every research run through `stream_research_pipeline` runs the full PRISMA 2020 flow: title/abstract screening, full-text eligibility, evidence matrix, flow counts.
- No lightweight-scan code path exists. No separation of exploratory scan from formal review. The user never approves a review — it just happens.

**Status:** **DIVERGES.** The *rigour* is correct — PRISMA is implemented honestly with real flow accounting. The *tempo* is wrong — vision wants fast scan first, formal review on approval.

**Phase 3 of the plan addresses this with a new `lightweight_scan.py` module and FSM gating.**

---

## Stage 7 — Return to brainstorming

**Vision:** "Explain what the literature establishes, challenge or refine the original idea, identify unresolved questions, and continue thinking from the new understanding."

**Current reality:**
- `/api/followup/stream` is the mechanism. It accepts a prior `state`, a `user_query`, and routes through the followup pipeline.
- **Real bug found in A3:** passing `state=None` crashes with `'NoneType' object has no attribute 'get'`. The follow-up entrypoint assumes state is a dict.

**Status:** **PARTIALLY WORKS.** The pipeline exists; the entry needs a guard. Phase 1 fixes this incidentally when the chat router absorbs the followup path.

---

## Stage 8 — Refine one main hypothesis

**Vision §7.1:** "Thoth should help refine one primary hypothesis at a time. It can consider relevant alternative explanations when they materially affect the investigation, but should not automatically generate multiple independent research branches."

**Current reality:**
- `research_ideas` schema (`memory/db.py:129-166`) supports `TENTATIVE → PROMOTED → REVISED → ABANDONED` with `parent_idea_id` and `revision_version` for lineage.
- `routes_ideas.py` has `/revise`, `/abandon`, `/propose-revision`, `/counter-evidence-plan` — all round-tripped and persisted.
- Nothing in the code enforces "one primary hypothesis at a time". The user is free to create many parallel ideas on one project. The pipeline does not branch automatically, but the backend offers no explicit guardrail.

**Status:** **MOSTLY WORKS.** The one-hypothesis-at-a-time constraint is implicit (the pipeline operates on one brief at a time) rather than explicit. No code generates automatic parallel branches, so the vision isn't actively violated — but a user action could create them. **Low priority for correction; monitor during Phase 2.**

---

## Stage 9 — Design the study

**Vision §7.2:** "Thoth should assess feasibility alongside intellectual merit. When useful, it should search for real datasets, repositories, tools, or other resources and verify what is actually accessible."

**Current reality:** Nothing in the pipeline probes the external world for the specific resources a proposed study requires. The writer node produces a design in prose; no code validates whether the datasets named exist, whether the tools are available, whether the repositories are reachable.

**Status:** **MISSING.**

**Phase 8 of the plan addresses this with a new `backend/workspace/feasibility.py` module.**

---

## Stage 10 — Develop reports and a manuscript

**Vision §8:** Reports with claim-level status labels (`supported` / `contradicted` / `uncertain` / `insufficiently_assessed`); provisional vs. fully-reviewed distinction; PDF export only on approval.

**Current reality:**
- Manuscript engine exists: `manuscripts`, `manuscript_revisions`, `manuscript_claims`, `manuscript_exports` tables all live. `/api/manuscripts/*` endpoints work (verified A3, including the journal-presets list).
- `extraction_quality` propagates honestly through to the bibliography — never upgraded. Confirmed by Explore agent and code trace.
- Truth Guard entailment checks exist in `integrity_gate.py` (overgeneralization, direction inversion, causal leap, predicate drift).
- **But:** there is no report-level `provisional | fully_reviewed` status surfaced through the API. There is no per-claim four-label enum exposed to the frontend. The frontend renders a single "complete" state.
- **PDF export** is server-side (dual-engine `pdflatex` + ReportLab) — but there is **no approval barrier** before the PDF is produced. Any POST to `/api/manuscripts/{id}/export` with the right body generates one. Vision §11 requires explicit approval.

**Status:** **DIVERGES.** The data model and most of the plumbing exist. The honest-status surface and the export approval gate do not.

**Phase 5 of the plan addresses this (per-claim labels, report-level status, PDF watermark + approval).**

---

## Summary table

| Vision §3 stage | Status | Fixed in plan phase |
|---|---|---|
| 1. Open conversation | DIVERGES (UX modes impose lanes) | Phase 1 |
| 2. Recognise a promising direction | MISSING (no auto-detection) | Phase 2 |
| 3. Prepare without blocking | MOSTLY WORKS (UX frame missing) | Phase 1 |
| 4. Seek approval | WORKS (one bypass to close) | Phase 1 |
| 5. Brainstorm with thinkers | DIVERGES (thinkers severed from pipeline) | Phase 4 |
| 6. Lightweight scan vs formal PRISMA | DIVERGES (always runs full PRISMA) | Phase 3 |
| 7. Return to brainstorming | PARTIALLY WORKS (null-state crash) | Phase 1 incidentally |
| 8. Refine one main hypothesis | MOSTLY WORKS (no explicit guard) | Monitor |
| 9. Design the study | MISSING (no feasibility probe) | Phase 8 |
| 10. Reports & manuscript | DIVERGES (binary status, PDF without approval) | Phase 5 |

Also missing but not in the §3 journey (noted in plan separately):

- **§4 Originality assessment with adjacent-field search** → Phase 6.
- **§9.1 Project-scoped paper storage** (notes/edges/embeddings globally namespaced) → Phase 7.
- **§10 Resource-awareness surface** (no cost estimates on approvals) → Phase 9.
- **§12 Deployment model** (open decision) → Phase 10.

## Verdict

The scaffolding is denser than the user's "nothing works" statement implied, but the vision mismatch is real. Of the ten §3 stages:

- **1 fully works** (Stage 4, with one bypass to close)
- **4 work on the backend but diverge on UX or integration** (Stages 1, 5, 6, 10)
- **2 mostly work with small bugs or missing guards** (Stages 3, 7, 8)
- **3 are missing** (Stages 2, 9, plus §4 originality off-journey)

Every gap in this table maps to a phase in the plan.
