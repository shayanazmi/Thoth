# UI v2: the journey (build steps 1–3 of `docs/UI_REVAMP_PLAN.md`, plus thinkers)

**Date:** 2026-10-24
**Plan:** `docs/UI_REVAMP_PLAN.md` v3 (brand: "the honest scribe"; journey Explore → Thinkers → Hypothesis → Check → Review → Draft).
**Old UI:** moved with `git mv` to `docs/archive/legacy_code/ui_v1/`.

## Walkthrough from the user's seat (observed live, real APIs, desktop 1440×900)

1. **Home.** The mark, "What's been on your mind?", one input, five doors (Brainstorm · Talk to a thinker · Check a hypothesis · Literature review · Draft) and recent projects. No marketing copy.
2. Typed *"Why do night-shift nurses report more burnout despite similar workloads?"* A project was created (`POST /api/projects`). The conversation showed an **idea card** (contradiction trigger: *Make it the hypothesis · Save to ideas · Not now*) and a compact **plan card** with its effort estimate. The workspace opened on **Ideas**. On the moon-phase journey path, **Thinkers** and **Hypothesis** glowed as available.
3. Clicked the **Thinkers** stage. The **council** gathered: ten real one-line takes from a single LLM call (new `/api/brainstorm/council`). The chat shows three; all ten are in the Thinkers panel with *Talk · Alone · Debate*.
4. **Talk** with Popper. A banner showed "Talking with Karl Popper · Back to Thoth". His Popperian challenge asked for operational definitions. I replied with definitions and a claim. Popper's reply ended with a **Use as hypothesis** chip (from the backend's escalation proposal).
5. **Use as hypothesis.** The hypothesis card pinned under the journey path ("Proposed in a thinker conversation · refined after Karl Popper (v1)", ◀ v1 ▶). The workspace switched to the **Hypothesis** page: statement, original motivation (kept unchanged), what would prove it wrong, versions. **Check** glowed.
6. **Check the evidence** → plan card → **Approve and run**. During the run:
   - Journey current = Check; workspace "Checking…".
   - An inline step line in the chat and the **activity timeline**: started → searched (15 sources) → scan (15 papers, abstracts only) → draft 1 → Truth Guard INCOMPLETE → critic 7.0/10 → draft 2 → … → status.
   - Total about 3 minutes.
7. **Check finished** card: *"Unclear: the evidence read is mixed or insufficient · no close prior work found in the searches run · provisional"*, with *Open the check · Run a formal review · Refine with the council*. The **Check** view shows:
   - verdict first, labelled "Based on a lightweight scan: titles and abstracts only";
   - what the evidence leaves open;
   - Supports / Challenges / Unclear columns;
   - originality with adjacent-field searches and limits;
   - the 15 papers with reading-depth badges.
   **Review** glowed.
8. **Reload:** the whole project (conversation, hypothesis, check results) was restored from browser storage. Light and dark both checked. **Phone (375px):** compact journey pill ("Check · 4 of 6"), two-line hypothesis card that expands on tap, bottom bar Chat · Hypothesis · Workspace.

## What changed

| Area | Change |
|---|---|
| `frontend/index.html` | New shell: sidebar · journey top bar · conversation · workspace · bottom bar; marked + DOMPurify (pinned cdnjs) |
| `frontend/styles/tokens.css`, `app.css` | Two-ink palette (ink, red-ochre rubric, papyrus / night indigo, moon silver), claim colours kept separate; Newsreader / IBM Plex; responsive (≥1200 three columns, tablet slide-over, phone single column) |
| `frontend/js/util.js` | Escaping, sanitised markdown, mark, moon phases, placeholder busts, ink-stroke progress |
| `frontend/js/api.js` | CRLF-safe SSE client for `/api/chat/stream` |
| `frontend/js/store.js` | Per-project state saved in the browser; hypothesis versions; journey stage logic |
| `frontend/js/chat.js` | Stream events → compact cards; chips; heavy cards for costly steps; inline step summaries; slash commands with autocomplete; hypothesis card with versions and inline edit |
| `frontend/js/thinkers.js` | Join the chat, council, debate (two rounds each, Thoth moderates), one-on-one room |
| `frontend/js/workspace.js` | Stage-aware panels (Ideas, Thinkers, Hypothesis, Check, Review, Draft), pin, activity timeline |
| `frontend/js/main.js` | Boot, projects sidebar, home and doors, journey path, theme toggle, phone bottom bar |
| `backend/api/routes_brainstorm.py` | New `POST /api/brainstorm/council`: one LLM call for all thinkers; falls back to each thinker's standard opening question |
| `backend/agents.py` | Casual-chat voice: Socratic first, then colleague, then companion; no "divine scribe" persona |

## Not built yet (from the plan)

- 3D thinker busts (initial-letter placeholders for now) and the cinematic intro (step 8).
- PRISMA view beyond flow counts: decisions table, custom columns, export, paper reader (step 5).
- Draft editor with evidence drawer and tracked changes (step 6); the Draft panel is read-only.
- Research Map and message branching (step 7).
- Projects: conversations live in the browser (not yet on the server); starred chats; PDF attachments.
- Formal review via the new UI was not re-run in this walkthrough (the backend path was verified on 23 Oct).

## Issues seen that belong to the later workflow work

- The brief's "falsification criteria" sometimes contain a thinker's questions; the UI shows only the first three clean statements.
- Report claims carry labels but no source IDs, so "evidence for/against" lists claims rather than papers.
