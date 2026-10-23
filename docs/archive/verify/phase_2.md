# Phase 2 — Idea capture: detect, suggest, promote

**Date:** 2026-10-23
**Vision anchor:** `THOTH.docx` §3.1 ("Idea capture: detect, suggest, then promote").
**Phase status:** complete.
**Gate:** `make test-vision` → 14/14 passing across S1 + S2 scenarios.

---

## Walkthrough from the user's seat

### Before Phase 2

The idea lifecycle existed in the backend (`research_ideas` table, `TENTATIVE / PROMOTED / REVISED / ABANDONED` states) but **no code anywhere detected a promising direction mid-conversation**. The only way an idea was ever created was for the user to explicitly POST `/api/ideas/tentative` — which no part of the frontend did on its own. Vision §3.1's "detect, suggest, then promote" was pure dead letter.

A user who typed *"rural anemia rates are higher despite similar iron intake — why?"* got a research-plan card and nothing else. Thoth never said "this looks like a direction worth capturing." The idea network stayed empty forever.

### After Phase 2

The same observation now produces, within the same SSE stream:

```
turn_start      kind=research_intent
idea_candidate  trigger=contradiction  (title + hypothesis + rationale)
plan_preparing  "I'm sketching a focused research plan..."
plan_pending    brief v1 PENDING_APPROVAL
complete
```

The `idea_candidate` card renders alongside the plan. It is a **suggestion**, not a database row:

- No `research_ideas` row is created at this point.
- The chat stays live.
- Approving the plan is a separate action from promoting the idea.
- Dismissing the suggestion leaves no trace.

If the user clicks **Promote to idea network**, the frontend sends an `idea_promotion` turn carrying `{title, hypothesis, rationale}`. The server creates the idea with `TENTATIVE` status and immediately promotes it to `PROMOTED` in one atomic server-side action (`create_tentative_idea → promote_idea_to_artifact`). The user sees `✓ Added **<title>** to your idea network.`

### What vision §3.1 required and how Phase 2 delivered it

| Vision §3.1 clause | Phase 2 behaviour | Evidence |
|---|---|---|
| "Thoth should identify potentially meaningful ideas during conversation" | New `backend/conversation/idea_detector.py` runs on every `research_intent` turn | Scenario `test_sharp_observation_emits_candidate_without_persisting` |
| "but it should be conservative about declaring them valuable" | Negative pre-filter + 20-char min length + 5 narrow trigger patterns + heuristic-only confidence 0.55 | Scenario `test_mundane_turns_do_not_emit_idea_candidate[*]` — 4 mundane turns, none emit |
| "committing them to the persistent research structure" is a separate step | SSE emits a *suggestion*, no DB write; promotion requires an explicit `idea_promotion` turn | Scenario asserts `_count_ideas == 0` after detection |
| "obtains the user's approval" before promotion | `promote_idea_to_artifact(idea_id, user_approved=True)` guard preserved end-to-end | Scenario `test_idea_promotion_persists_as_promoted` |
| "Thoth must explain the rationale for promoting a direction" | Candidate payload carries `rationale` + `trigger_label` naming one of the five vision §4.1 categories | Candidate contract fields `rationale`, `trigger`, `trigger_label` |
| "The network should not become a stream of random AI-generated suggestions" | Detector refuses to fire on casual, definition-lookup, thanks, slash-command, under-20-char turns | 4 parameterised negative scenarios |
| "Connections should be based on meaningful reasoning or evidence, not superficial similarity" | **No edges created automatically.** Idea-to-idea edges are deferred to Phase 3+ where they can be grounded on evidence. | No `idea_edges` writes in Phase 2 code |

---

## The five triggers (vision §4.1)

The detector classifies each turn against the five categories vision §4.1 names as what might constitute an original contribution:

| Trigger key | Vision §4.1 category | Example phrasing the pattern catches |
|---|---|---|
| `new_explanation` | "A genuinely new explanation or mechanism" | "what if…", "I suspect…", "maybe the reason is…" |
| `overlooked_link` | "An overlooked relationship or meaningful connection" | "connect X and Y", "borrow from information theory", "cross-disciplinary parallel" |
| `contradiction` | "A contradiction or inconsistency in existing evidence" | "higher despite similar X", "unexpected result", "anomaly / paradox" |
| `different_lens` | "A different perspective, interpretation, or methodology" | "reframe", "viewed as", "not just X but also Y" |
| `method_reveal` | "A method or analytical approach that reveals something previous approaches did not" | "if we measured…", "cleaner protocol", "method misses…" |

Each trigger is a regex pre-filter, deliberately loose. When it fires, a short LLM step (opt-in via `use_llm=True`) can refine the title/hypothesis/rationale; on LLM failure or opt-out, the heuristic candidate is emitted directly, confidence 0.55. The hypothesis is **always** faithful to the user's own wording — Thoth does not strengthen the claim.

---

## What changed in the code

### Backend

| File | Change |
|---|---|
| `backend/conversation/idea_detector.py` (new, 372 lines) | The whole detector: five trigger categories, regex pre-filter, negative filter, heuristic `IdeaCandidate` builder, opt-in LLM refinement with strict JSON rubric, fail-open on every path. |
| `backend/api/routes_chat.py` | New `TurnKind.IDEA_PROMOTION`. Classifier recognises `idea_promotion` body block (highest precedence). `_run_research_intent` now calls `detect_promising_direction(use_llm=False)` and emits an `idea_candidate` SSE card before `plan_preparing`. New `_run_idea_promotion` branch calls `create_tentative_idea → promote_idea_to_artifact(user_approved=True)` and emits `idea_promoted` (or `error` on malformed payload). |

### Frontend

| File | Change |
|---|---|
| `frontend/js/app.js` | `renderChatEvent` handles two new card types: `idea_candidate` (renders a "Promote to idea network" + "Not now" pair of buttons with the detector's title/trigger/rationale) and `idea_promoted` (confirmation). New `promoteIdeaCandidate(title, hypothesis, rationale)` and `dismissIdeaCandidate()` methods. The chat input is never disabled around these cards; vision §10 holds. |

### Tests

| File | Change |
|---|---|
| `backend/tests/scenarios/test_s2_idea_detect_suggest_promote.py` (new, 198 lines) | Eight scenarios: 4 parametrised negative turns + 1 positive detection + 1 promotion + 1 malformed promotion rejection + 1 independence (plan approval does not auto-promote). All passing. |
| `backend/tests/scenarios/test_s1_conversation_never_blocks.py` | Fixture isolation hardened — reloads cache-pinned modules (`backend.memory.db`, `backend.conversation.brief`, `backend.conversation.idea`) so each test lands on its own `tmp_path` DB. Previously tests implicitly shared `DEFAULT_DB_PATH` from the first-imported state. |

---

## Scenario gate (what `make test-vision` guarantees after Phase 2)

```
$ pytest backend/tests/scenarios/ -v
======================= 14 passed in 38.51s =======================
```

The six S1 Phase 1 tests still pass. New S2 Phase 2 tests:

1. **`test_mundane_turns_do_not_emit_idea_candidate[hi there]`**
2. **`test_mundane_turns_do_not_emit_idea_candidate[thanks for that]`**
3. **`test_mundane_turns_do_not_emit_idea_candidate[what is PRISMA?]`**
4. **`test_mundane_turns_do_not_emit_idea_candidate[/popper]`** — casual, thanks, definition lookup, and slash command all fail to trigger the detector.
5. **`test_sharp_observation_emits_candidate_without_persisting`** — the vision rubric fires on a contradiction phrasing, carries a non-empty rationale, lists `status: "tentative"`, and does **not** write a row.
6. **`test_idea_promotion_persists_as_promoted`** — an explicit `idea_promotion` turn produces an `idea_promoted` event and exactly one row in `/api/ideas`, status `PROMOTED`.
7. **`test_idea_promotion_without_required_fields_is_rejected`** — malformed promotion is cleanly rejected, no row created.
8. **`test_approving_plan_does_not_auto_promote_detected_idea`** — approving the plan is independent of promoting the idea. Vision §3.1 "two separate actions" preserved.

---

## What is still open after Phase 2

- **Lightweight-scan vs formal PRISMA split** (vision §5.4) — still runs full PRISMA unconditionally on brief approval. **Phase 3.**
- **Thinkers inside the research pipeline** (vision §6.3) — still reachable only via `/api/brainstorm` and slash commands on the followup turn. **Phase 4.**
- **Report provisional vs fully-reviewed status + per-claim labels** (vision §8). **Phase 5.**
- **Originality assessment with adjacent-field search** (vision §4). **Phase 6.**
- **Project-scoped storage for notes / edges / embeddings + retention UX** (vision §9.1, §9.2). **Phase 7.**
- **Feasibility probe on study designs** (vision §7.2). **Phase 8.**
- **Resource-awareness surface** (vision §10). **Phase 9.**
- **Deployment-model ADR** (vision §9.3, §12). **Phase 10.**

Each closes with a new scenario file in `backend/tests/scenarios/` and a walkthrough alongside this one.

### Deferred inside Phase 2

- **Idea-to-idea typed edges** (`refines`, `contradicts`, `related_to`, `superseded_by`). Vision §3.1 permits these but requires they be "based on meaningful reasoning or evidence, not superficial similarity." Fulfilling that cleanly needs the lightweight-scan output and the originality probe, so the edge creation lives naturally in Phase 3 and Phase 6 node insertions. Phase 2 ships the detect-and-promote lifecycle without the typed network; promoted ideas sit as independent rows.
- **LLM-assisted detector refinement.** The detector supports an opt-in LLM step via `use_llm=True`, but the chat router calls it with `use_llm=False` by default so the suggestion arrives in a few milliseconds without a provider call. A Phase 2.5 or Phase 4 enhancement can switch the default on once the budget surface (Phase 9) is live and the user can see the cost of running the LLM-refined detector on every turn.
