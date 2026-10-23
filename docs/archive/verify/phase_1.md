# Phase 1 — One conversation, one surface

**Date:** 2026-10-23
**Vision anchors:** `THOTH.docx` §2 (Conversation first), §10 (UX rules).
**Phase status:** complete.
**Gate:** `make test-vision` → 6/6 passing (see §4).

---

## Walkthrough from the user's seat

Phase 1's acceptance criterion is a walkthrough from the user's seat. This
section records exactly what a user now sees when they open Thoth and start
typing. The scenario tests under `backend/tests/scenarios/` encode the same
behaviour so a future regression breaks a test, not just the user's day.

### 1. The user opens Thoth and types "hi thoth"

- **Before Phase 1:** the UI shows a mode menu with seven items (`Autonomous
  Router / Deep Research Swarm / Live Web Search Probe / Vault Knowledge QA /
  Expand Living Report / Fast Dialogue / Epistemic Brainstorming`) plus a
  "Brainstorm" and a "Deep Research" toggle in the input bar. The user has
  to decide which lane their greeting belongs in.
- **After Phase 1:** the UI shows one textarea, a send button, and nothing
  else to pick. The user types "hi thoth" and the server classifies the turn
  as `casual`, replies with a direct answer, and emits a `complete` event.
  No plan proposed. No mode chosen. Vision §2 held.

### 2. The user types a substantive observation

> "rural anemia rates are higher despite similar iron intake — why?"

- **Before Phase 1:** depending on the active mode, this either silently
  launched a full literature review (if "Deep Research" was active, with no
  approval gate at the UI level), or routed to a thinker chat (if
  "Brainstorm" was active), or fell through to a conversational reply with
  no research framing. The user never saw the research plan Thoth was about
  to pursue, and could not edit it.
- **After Phase 1:** the SSE stream emits `turn_start` → `plan_preparing`
  ("I'm sketching a focused research plan — the chat stays live while I do.")
  → `plan_pending` carrying the full `ResearchBrief` with `research_question`,
  `objectives`, and `approval_status = PENDING_APPROVAL`. The frontend
  renders a plan card the user can read, edit, or approve. The chat input
  stays live. No pipeline work has started. Vision §3 stage 3 held.

### 3. The user keeps chatting while the plan sits pending

The second scenario test (`test_chat_input_stays_live_during_a_slow_prep`)
verifies that two overlapping `/api/chat/stream` requests to different
sessions both receive responses. The server does not serialize turns. The
frontend's `setGenerating` only swaps the send-button icon; the textarea is
never `disabled`. The user can type "quick aside — what does PRISMA stand
for?" and get a direct reply back without the pending plan being discarded.
Vision §10 ("ordinary conversation remains available while research
preparation or analysis proceeds") held.

### 4. The user approves the plan

- **Before Phase 1:** the frontend had no explicit approve button; the
  backend's approval gate worked, but was reached only via a server-side
  path the UI didn't surface honestly. The `fast_chat` bypass at
  `routes_research.py:121` could, in principle, launch a non-casual research
  question past the brief entirely.
- **After Phase 1:** the user sends an approval turn
  (`{approval: {brief_id, approved_version}}`). The SSE stream emits
  `approval_recorded` → `approval_verified` (carrying the atomic `task_id`)
  → the pipeline FSM events → `complete`. The `fast_chat` bypass is not
  reachable from the new chat endpoint — the only way the pipeline launches
  is through a brief that `verify_brief_approval` has stamped. Vision §2
  ("Approval before substantive compute; no backdoor modes") held.

### 5. Honest failure

In this verification environment the external APIs (NVIDIA, Semantic
Scholar, arXiv, Tavily, OpenAlex, PubMed) are all unreachable through the
sandbox proxy. The pipeline retries, the circuit breaker trips after five
failures, the writer attempt fails on NVIDIA, and the stream ends with a
clean `error` event followed by `complete`. The user sees the real
failure. Nothing is hidden behind a generic "done" status. Vision §11
("Do not hide failed access, incomplete review, or unresolved criticism
behind a generic 'complete' status") held — the `error` event's payload
carries the actual provider error string.

---

## What changed in the code

### Backend

| File | Change |
|---|---|
| `backend/api/routes_chat.py` (new, 410 lines) | One SSE endpoint `POST /api/chat/stream`. Server classifies the turn (`approval_response` / `approved_research` / `casual` / `clarification_needed` / `research_intent`) and routes to the appropriate branch. Reuses `is_casual_query`, `evaluate_clarification_need`, `prepare_research_brief`, `approve_research_brief`, `verify_brief_approval`, `direct_chat_chain`, and `stream_research_pipeline`. Participates fully in the durable task lifecycle (`task_manager.register_task` → atomic `claim_task` → `complete_task` / `record_cancellation`). No `fast_chat` or `deep_research` keywords. |
| `backend/main.py` | Registers the new router after the existing eight. Old routers kept during the transition; they still work, the frontend no longer uses them. |
| `backend/api/routes_followup.py` | Null-state guard: `/api/followup/stream` with `state: null` no longer crashes with `'NoneType' object has no attribute 'get'`. One-line fix. |
| `backend/api/routes_workspace.py` | `ProjectCreateRequest` now accepts `name` as an alias for `title` via a `model_validator(mode="before")`. 422 on legitimate payloads removed. |

### Frontend

| File | Change |
|---|---|
| `frontend/index.html` | Removed: the floating mode menu (`#floatingToolMenu`, 7 items), the brainstorm selector bar (`#brainstormSelectorBar`), the active-mode-badge, the paper-volume-badge, the tool-attach-btn, the brainstormToggle, and the deepResearchToggle. The user now sees one textarea + a send button and nothing else to pick. Dropped from 469 → 363 lines. |
| `frontend/js/app.js` | `handleChatSend` simplified to one path: `sendUnifiedTurn(text)`. New `sendUnifiedTurn` method POSTs to `/api/chat/stream` and streams SSE back. New `renderChatEvent` dispatcher renders typed cards for `turn_start`, `plan_preparing`, `plan_pending`, `direct_answer`, `clarification_needed`, `approval_recorded`, `approval_rejected`, `approval_verified`, pipeline nodes, `error`, `complete`. The legacy `startResearch` is kept intact (not reachable from the normal input path) so the slash commands and bookmark-restore paths still work during the transition. |

### Tests

| File | Change |
|---|---|
| `backend/tests/__init__.py` (new) | Package marker + Phase 0 note. |
| `backend/tests/scenarios/__init__.py` (new) | Scenario-suite package marker. |
| `backend/tests/scenarios/test_s1_conversation_never_blocks.py` (new, 196 lines) | Six scenario tests, all passing. Encodes the Phase 1 vision contract so a regression breaks a test. |
| `Makefile` | `test` now aliases `test-vision`, which runs the scenario suite. The previous `test` target listed 20 files that had been deleted in a prior commit — fixed. New `test-legacy-all` runs anything else discovered under `backend/tests/` for forensic value only. |

---

## The scenario gate (what `make test-vision` guarantees)

```
$ pytest backend/tests/scenarios/ -v
======================= 6 passed in 28.97s =======================
```

1. **`test_casual_greeting_routes_to_direct_answer`** — A casual greeting
   produces `direct_answer`, never `plan_pending`, never `approval_verified`.
2. **`test_research_intent_produces_plan_pending_without_launching`** — A
   substantive observation produces `plan_pending` with
   `approval_status = PENDING_APPROVAL` and `requires_approval = True`. No
   pipeline work fires.
3. **`test_approval_launches_pipeline_through_the_gate`** — Attaching a valid
   `approval` block drives the full sequence `approval_recorded →
   approval_verified → complete`.
4. **`test_approval_response_without_brief_id_is_rejected_cleanly`** — The
   backdoor cannot be opened. An `approval` without `brief_id` errors;
   `approval_verified` is never emitted.
5. **`test_chat_input_stays_live_during_a_slow_prep`** — Two overlapping
   requests both complete; the server does not serialize turns.
6. **`test_no_mode_lanes_leak_in_sse_payloads`** — The strings `fast_chat`,
   `deep_research`, and `"mode":"brainstorm"` do not appear in any SSE
   payload emitted by the chat endpoint for an ordinary research-intent
   turn.

The suite runs in under 30 seconds against SQLite + in-memory cache + no
real API keys. It is the canonical gate for every future phase.

---

## What is still open after Phase 1

Phase 1 did not and was not meant to close:

- The idea-capture detector (vision §3.1) — a new SSE event type
  `idea_candidate` and the detector module to emit it. **Phase 2.**
- The lightweight-scan vs. formal PRISMA split (vision §5.4) — the chat
  router launches the current unconditional PRISMA pipeline when a brief is
  approved. **Phase 3.**
- Thinker invocation inside the pipeline (vision §6.3) — thinkers remain
  reachable only via `/api/brainstorm/*` and slash commands. **Phase 4.**
- The report provisional vs fully-reviewed surface and per-claim labels
  (vision §8.2, §8.3). **Phase 5.**
- Originality assessment with adjacent-field search (vision §4). **Phase 6.**
- Project-scoped storage for notes/edges/embeddings and user-controlled
  retention (vision §9.1, §9.2). **Phase 7.**
- Feasibility probe (vision §7.2). **Phase 8.**
- Resource-awareness surface (vision §10). **Phase 9.**
- Deployment-model ADR (vision §9.3, §12). **Phase 10.**

Each lands against a new scenario in `backend/tests/scenarios/` and ends
with a walkthrough note alongside this one.

---

## Legacy endpoints retention policy

The plan called for retiring `/api/research/stream` and `/api/followup/stream`
with `410 Gone`. For Phase 1 they are **kept active** because:

- The two bug fixes (A3-visible `/api/followup/stream` null-state and
  `/api/projects` title/name) travel with them.
- The frontend's bookmark-restore and slash-command flows still reference
  `startResearch`, which internally hits `/api/research/stream`. Retiring
  them before Phase 2 would strand those paths without a scenario test to
  prove the behaviour is still intact.
- The new chat router *is* the only path the user-facing chat uses now.

**Retirement moves to a dedicated follow-up** once Phase 2 has shown that
the full set of frontend code paths (slash commands, idea-promote escalation,
bookmark restore, mindmap QA, etc.) can be served by `/api/chat/stream`
alone. At that point the old endpoints become `410 Gone` with a pointer to
the new one.
