# Phase 0.A2 — Honest test-suite audit

**Date:** 2026-10-23
**Finding:** **No pytest test suites exist on disk.** The entire `backend/tests/` directory was deleted in the last commit on `main`.

## Evidence

Last three commits on `main`:

```
606da82 feat(working-model): integrate PRISMA flow, living manuscript UI, and remove test suites
d9cf7b2 feat(phase-7): implement semantic literature clustering, citation topology & journal formatting engine
fa38d0a feat(phase6): implement PDF publication pipeline, citation snowballing, and production collaboration
```

The commit title itself says **"remove test suites"**. The git diff summary lists `delete mode 100644 backend/tests/test_*.py` for every suite the `Makefile`'s `test:` target names, including (but not limited to):

- `test_pure_functions.py`
- `test_db.py`
- `test_ui_adapter.py`
- `test_schemas.py`
- `test_dispatcher.py`
- `test_all_ten_frameworks.py`
- `test_claim_evidence_integrity.py`
- `test_document_ingestion.py`
- `test_research_mandate_and_approval.py`
- `test_audit_forensic_invariants.py`
- `test_task_lifecycle_persistence.py`
- `test_evidence_provenance_and_verification.py`
- `test_evidence_audit_and_correctness_gate.py`
- `test_idea_hypothesis_lifecycle.py`
- `test_thinker_dialectic_and_counter_evidence.py`
- `test_prisma_review_and_evidence_synthesis.py`
- `test_project_workspace_and_manuscript_engine.py`
- `test_phase6_pdf_snowball_and_collaboration.py`
- `test_phase7_clustering_and_journal_engine.py`
- `test_working_model_core_journey.py`

Current state of `backend/tests/`:

```
backend/tests/
└── __pycache__/
    ├── test_first_turn_hypothesis_escalation.cpython-310-pytest-9.1.1.pyc  (ghost)
    └── test_vault_notes_contract.cpython-310-pytest-9.1.1.pyc              (ghost)
```

Only two `.pyc` artefacts remain, and neither corresponds to any file named in the `Makefile`. They are historical bytecode from tests that no longer exist in source form.

Running the canonical gate:

```
$ pytest backend/tests/test_pure_functions.py ...
ERROR: file or directory not found: backend/tests/test_pure_functions.py
no tests ran in 0.00s
```

## Consequence for all prior status claims

The following documents all cite test counts (223, 308, 520, etc.) that correspond to commit `d9cf7b2` or earlier, before the deletion. They are **not evidence of current behaviour**:

- `docs/roadmap-status.md`
- `THOTH/THOTH_COMPREHENSIVE_ALIGNMENT_AUDIT.md`
- `README.md` ("`[![Tests](https://img.shields.io/badge/tests-223%20passed-brightgreen...`")
- `Makefile` targets `test`, `test-all`, `test-ui`

Treating any of these as evidence of a working system is category-error. The system has **zero pytest tests on disk**.

## What still exists

Eleven files under `backend/evals/`:

| File | Nature |
|---|---|
| `test_actionable_followups.py` | Live-LLM eval, not a unit test |
| `test_adversarial_continuity.py` | Live-LLM eval |
| `test_conversation_to_research.py` | Live-LLM eval |
| `test_end_to_end_user_journey.py` | Live-LLM eval |
| `test_nvidia_models.py` | Provider connectivity probe |
| `test_persona_simulations.py` | Live-LLM eval |
| `test_phase7_end_to_end_validation.py` | Live-LLM eval |
| `test_relevance_and_expansion.py` | Live-LLM eval |
| `test_server_live_endpoints.py` | HTTP probe |
| `test_snowballing.py` | Live-LLM eval |
| `test_specific_models.py` | Provider probe |

These require live API keys (`NVIDIA_API_KEY`, `TAVILY_API_KEY`, etc.) and real external calls. They are evaluation benchmarks, not unit tests. They would not be a trustworthy gate for development.

## Verdict

- **Make `test` target: broken (every file listed is missing).**
- **No automated verification layer exists in the current working tree.** Every behavioural claim in the repo is unverified by anything inside the repo.
- The plan's Phase 1+ scenario tests (`backend/tests/scenarios/*`) will be **the first real tests this project has had in its current form.**

## Implication for the plan

Phase 0 was premised on classifying existing tests as honest / mock-shell / broken. There is nothing to classify. Phase 0 simplifies: we assert instead that any phase that touches behaviour must introduce its own scenario test, and `make test-vision` (defined in the plan's cross-phase section) is the only gate we trust going forward.

The `Makefile`'s legacy `test` target will be rewritten in Phase 0.A7 to either (a) remove the stale references or (b) delegate to `test-vision` once that target exists. Nothing silently "passes" today.
