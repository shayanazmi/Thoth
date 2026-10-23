# Migration & Handoff Note

> This file exists for one purpose: to make sure a new Claude session
> (Claude Code CLI, a new claude.ai thread, or any other surface) can
> pick up Thoth exactly where the previous one left off, with no detail
> missing. Last updated **23 Oct 2026**, post Phase 2.

## Where authority lives

| What | Where | Trust level |
|---|---|---|
| Product vision | `THOTH.docx` (also `THOTH/THOTH.docx`) | **Only trusted spec.** |
| Working context | `/CLAUDE.md` | Primary; always loaded by Claude Code. |
| Current scorecard + next phase | `docs/SYSTEM_STATE.md` | Live. |
| Honest observations | `docs/archive/verify/BASELINE.md` + `A1..A6` + `phase_1.md` + `phase_2.md` | Live. |
| The approved plan driving all phases | `docs/PLAN.md` (full plan in-repo) | Live. |
| Short pointer files | `.agents/*.md`, `.agent/*.md` | Live. |
| Everything else in the repo | `README.md`, `docs/roadmap-status.md`, `THOTH/*_AUDIT.md`, `docs/architecture.md`, `docs/decisions/ADR-*.md` | **Historical/untrusted.** Useful as a map of the code; not evidence of behaviour. |

## State as of this writing

- **Phases complete:** 0 (baseline), 1 (unified chat surface), 2 (idea
  capture: detect → suggest → promote).
- **Vision §3 journey:** 5 of 10 stages closed.
- **Gate:** `make test-vision` → **14/14 passing** in ~39s.
- **Phase 3 (next):** lightweight scan vs formal PRISMA. Vision §5.4.
- **Everything is on disk under `/Users/shayanazmi/college/project based learning /langchain/thoth/`.** Nothing has been pushed to git by this session; the owner handles remote operations.

## Open bug fixes that have landed

- `/api/followup/stream` null-state crash — guarded.
- `/api/projects` body contract — now accepts `name` as alias for `title`.
- `make test` target — rewritten to alias `make test-vision` (the previous
  target referenced 20 files that had been deleted on `main`).

## New surfaces introduced this session

- **Backend:** `backend/api/routes_chat.py` (unified `/api/chat/stream`),
  `backend/conversation/idea_detector.py` (Phase 2 detector).
- **Frontend:** `frontend/js/app.js:sendUnifiedTurn` + `renderChatEvent`
  dispatcher; mode UI stripped from `frontend/index.html`.
- **Tests:** `backend/tests/scenarios/test_s1_conversation_never_blocks.py`,
  `backend/tests/scenarios/test_s2_idea_detect_suggest_promote.py`.
- **Docs:** this file, `docs/SYSTEM_STATE.md`,
  `docs/archive/verify/BASELINE.md` + Phase-0 trail + Phase-1/2 walkthroughs,
  refreshed `.agents/` and `.agent/` pointers.

## For a new Claude Code session, start here

Read in order (≈ 45 minutes to full fluency):

1. `THOTH.docx` — the vision. All of it.
2. `/CLAUDE.md` — especially §0, §0b, §1, §2, §8, §9.
3. `docs/archive/verify/BASELINE.md` — honest baseline, 5 minutes.
4. `docs/archive/verify/phase_1.md`, `phase_2.md` — what shipped, 10 minutes.
5. `docs/SYSTEM_STATE.md` — scorecard and next phase, 2 minutes.

Then run the gate:

```bash
make test-vision        # must return 14/14 green
```

If the committed `venv/` is a dangling symlink on your platform
(see `/CLAUDE.md` §5 for the macOS→Linux specifics), rebuild it:

```bash
rm -rf venv
python3 -m venv venv
./venv/bin/pip install -r backend/requirements.txt pytest pytest-asyncio pytest-subtests httpx
```

Then pick up Phase 3 from `docs/PLAN.md` — the full plan, in-repo.

## Things to not do (common failure modes)

- **Do not update** `README.md`, `docs/roadmap-status.md`, or the
  alignment audit. They are historical artefacts.
- **Do not revive** the deleted mock-heavy `backend/tests/*.py` suites.
  The `scenarios/` directory is the honest replacement.
- **Do not re-introduce mode toggles** in the frontend (Fast Chat /
  Deep Research / Brainstorm). The vision rejects them; the test
  `test_no_mode_lanes_leak_in_sse_payloads` would fail.
- **Do not call `stream_research_pipeline` directly from a new router.**
  Route through `backend/api/routes_chat.py`'s `_run_pipeline` so the
  approval barrier and task lifecycle participation stay intact.
- **Do not push to git.** The owner handles that.
