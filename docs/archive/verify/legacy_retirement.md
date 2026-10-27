# Retiring the legacy pipeline: walkthrough (25 Oct 2026)

**What moved** to `docs/archive/legacy_code/pipeline_v1/` (paths kept; see its README):
- the old FSM pipeline (`orchestrator.py`, `pipeline.py`);
- six unused routers (research, followup, brainstorm, ideas, prisma, vault);
- the heuristic idea detector, plus the pipeline-only rigour modules (lightweight_scan, originality, prisma, snowball, clustering, thinker_hook) and `reports/status.py`;
- dead code: `models/`, `repositories/*_repo.py`, `core/auth.py`, `core/rate_limit.py`;
- the evaluation suites that measured the old pipeline, and `frontend/lib` + `frontend/components`;
- scenario tests S1–S3.

**Behaviour changes**
- The conductor offers only the **trial** and the **systematic review**. The "scan" offer is gone: the trial is the lightweight check. An older saved "scan" offer, if accepted, opens the trial.
- `/api/chat/stream` handles conductor turns and explicit `idea_promotion`. `approval`, `step_accept` and `brief_id` turns get `error {retired: true}` and start nothing.
- The UI no longer sends those shapes. Old projects still display what the retired pipeline saved (plan cards, step logs, the old check/review/draft panels). Their Approve button now says the plan can't run and points to Check.
- `make` drops the `eval`, `diagnostics`, `test-ui` and `test-legacy-all` targets.
- Correction: `backend/backend` is a symlink that `backend/main.py` creates on purpose (Railway deploys rooted at `/backend`). It is not junk; it is gitignored and recreated at startup.

**Checks**
- `make test-vision`: **57 passed, 1 skipped**. The new S19 covers:
  - every endpoint the UI calls is served;
  - the shell, modules and styles load;
  - the retired routes are gone, unreferenced by the UI, and not importable;
  - the archive holds them;
  - an ordinary message gets a reply;
  - the retired request shapes start nothing;
  - the conductor offers only trial and review;
  - an idea persists only on explicit promotion.
- `make lint`: all core modules import.
- Browser (:8001, live NIM):
  - a home-page hunch got a conductor reply with a quick look at 5 papers;
  - `/hypothesis` then Check produced the trial plan card, and nothing ran without approval;
  - a project shaped like a pipeline-era one rendered its old cards, and Approve answered honestly;
  - the demo tour replayed chapters 0–II;
  - there were no console errors throughout.
