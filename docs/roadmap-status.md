# THOTH — Official Roadmap Status & Verification Ledger

**Last Updated:** 2026-10-16  
**Governing Vision:** THOTH Master Product Vision & Autonomous Execution Directive (v3.0)  
**Authoritative Location:** `docs/roadmap-status.md`

---

## 1. Executive Summary & Delivery Matrix

| Phase | Title | Status | Acceptance Decision | Key Evidential Verification |
| :--- | :--- | :--- | :--- | :--- |
| **Phase 0** | Safe Baseline Establishment | Baseline Stage | **ACCEPT** | Workspace clean; `db/store.db` & `vault/` preserved; symlinks checked. |
| **Phase 1** | Source-to-Publication Integrity | Completed | **ACCEPT WITH LIMITATIONS** | 16-case adversarial suite passing (`test_evidence_audit_and_correctness_gate.py`). Caution banners on unverified reports; strict locator & passage checks. |
| **Phase 2** | Secure Research Handoff | Completed | **ACCEPT** | 26 durable task lifecycle & approval invariant tests passing. Server-side approval barrier, SQLite atomic deduplication, cooperative cancellation verified. |
| **Phase 3.1** | Persistent Idea & Hypothesis Lifecycle | Completed | **ACCEPT** | 8 lifecycle & promotion barrier tests passing (`test_idea_hypothesis_lifecycle.py`). Promotion barrier enforced, immutable revision lineage preserved, brief integration connected. |
| **Phase 3.2** | Thinker Dialectic Convergence & Objection Translation | Completed | **ACCEPT** | 7 dialectic & counter-evidence tests passing (`test_thinker_dialectic_and_counter_evidence.py`). Framework-specific query generation across 10 thinkers, objection-to-query translation, SQLite brief persistence, agency-preserving hypothesis revision proposals, and search node counter-evidence tagging verified. |
| **Phase 4** | Reproducible Literature Reviews | Next Milestone | **PENDING** | PRISMA flow data, systematic screening decisions (inclusion/exclusion criteria), source appraisal audit trails, and synthesis traceability. |
| **Phase 5** | Persistent Research Workspace & Manuscript Engine | Roadmap | **PENDING** | Dependent on Phases 1–4. Project-scoped retention, versioned drafts, multi-format exports. |

---

## 2. Phase-by-Phase Status & Acceptance Records

### Phase 0: Baseline Stage (Safe Baseline Establishment)
- **Status:** **ACCEPT**
- **Objective:** Establish workspace invariants, verify uncommitted changes, identify database boundaries (`db/store.db`) and user vault files (`vault/`), and ensure zero data destruction.
- **Verification Evidence:**
  - `git status --short` verified before every phase modification.
  - Isolated temporary databases (`:memory:` or `tempfile.mkdtemp()`) utilized in all test fixtures.
  - Verified symlink behavior (`backend/backend` created by `backend/main.py`) kept intact.
  - Production store `db/store.db` and user research repository `vault/` preserved unmodified.

---

### Phase 1: Close Source-to-Publication Integrity
- **Status:** **ACCEPT WITH LIMITATIONS**
- **Original Unmet Criterion:** Source provenance, extraction failure disclosures, and claim-to-evidence relationships must survive end-to-end execution through final publication without unverified reports masquerading as validated evidence.
- **Implementation Changes:**
  - [backend/intellectual_rigour/integrity_gate.py](file:///Users/shayanazmi/college/project%20based%20learning%20/langchain/thoth/backend/intellectual_rigour/integrity_gate.py): Fixed `verify_passage_locator` to fail closed on unindexed sources; enforced passage-containment check so citations must reside inside the cited passage; added overgeneralization and missing predicate checks in `evaluate_claim_support`.
  - [backend/ingestion.py](file:///Users/shayanazmi/college/project%20based%20learning%20/langchain/thoth/backend/ingestion.py): Propagated `extraction_quality` to bounded evidence passages to prevent partial extractions from claiming full-text verification.
  - [backend/orchestrator.py](file:///Users/shayanazmi/college/project%20based%20learning%20/langchain/thoth/backend/orchestrator.py): Scraped metadata merged into source records; reports failing claim verification receive an automated markdown caution banner (`> [!CAUTION] Research Integrity Gate`).
  - [backend/tests/test_evidence_audit_and_correctness_gate.py](file:///Users/shayanazmi/college/project%20based%20learning%20/langchain/thoth/backend/tests/test_evidence_audit_and_correctness_gate.py): Implemented 16 deterministic adversarial test cases covering quotation vs conclusion mismatches, contradictory results, causal leaps, locator fabrication, claim drift, snippet-only boundaries, and overgeneralization.
- **Observed Test Evidence:**
  - `pytest backend/tests/test_evidence_audit_and_correctness_gate.py`: 16 passed in 0.92s (Exit Code: 0).
- **Explicit Documented Limitations:**
  - Automated claim support analysis operates deterministically with heuristics and language model assessments. Novel conceptual metaphors or subtle qualitative nuances require human scholarly appraisal. The system clearly labels automated verification status and never manufactures certainty.

---

### Phase 2: Secure the Research Handoff & Durable Task Lifecycle
- **Status:** **ACCEPT**
- **Original Unmet Criterion:** Server-enforced research approval barrier, brief version binding, active task deduplication across processes, and durable task state persistence across application restarts.
- **Implementation Changes:**
  - [backend/conversation/brief.py](file:///Users/shayanazmi/college/project%20based%20learning%20/langchain/thoth/backend/conversation/brief.py): `ResearchTaskManager` backed by SQLite; server-enforced approval gate; cooperative cancellation events.
  - [backend/memory/db.py](file:///Users/shayanazmi/college/project%20based%20learning%20/langchain/thoth/backend/memory/db.py): Table `research_tasks` with unique active index `(brief_id, brief_version)` on states `('QUEUED', 'RUNNING')`; atomic claim and transition functions; crash recovery reconciliation.
- **Observed Test Evidence:**
  - `pytest backend/tests/test_research_mandate_and_approval.py backend/tests/test_audit_forensic_invariants.py backend/tests/test_task_lifecycle_persistence.py`: 26 passed in 40.60s (Exit Code: 0).

---

### Phase 3.1: Persistent Idea & Hypothesis Artifact Lifecycle (Current Milestone)
- **Status:** **ACCEPT**
- **Original Unmet Criterion:** Connecting informal conversational thinking to persistent research development requires:
  1. Ideas and hypotheses must be persistable as first-class research artifacts.
  2. Promotion barrier: Tentative ideas formulated during conversation or thinker sparring must NOT be persisted as formal research artifacts without explicit user confirmation.
  3. Immutable revision lineage: Revisions to hypotheses must never silently overwrite intellectual history; ancestor versions must remain preserved and traceable.
  4. Integration with research briefs: Briefs must bind to promoted ideas, inherit hypotheses and thinker context, and reject unpromoted tentative ideas.
- **Implementation Changes:**
  - [backend/memory/db.py](file:///Users/shayanazmi/college/project%20based%20learning%20/langchain/thoth/backend/memory/db.py):
    - Created table `research_ideas` with columns `idea_id`, `session_id`, `title`, `description`, `hypothesis`, `status` (`TENTATIVE`, `PROMOTED`, `REVISED`, `ABANDONED`), `thinker_id`, `thinker_critique`, `unresolved_objections_json`, `parent_idea_id`, `revision_version`, `revision_notes`, `brief_id`, `created_at`, `updated_at`.
    - Added migration in `init_db()` adding `idea_id` to `research_briefs`.
    - Implemented database helper methods: `save_idea_db`, `get_idea_db`, `list_ideas_db`, `get_idea_history_db`.
  - [backend/conversation/idea.py](file:///Users/shayanazmi/college/project%20based%20learning%20/langchain/thoth/backend/conversation/idea.py):
    - Implemented core domain lifecycle module with `IdeaStatus` and `ResearchIdea` models.
    - Implemented `create_tentative_idea` (starts with `TENTATIVE`).
    - Implemented `promote_idea_to_artifact` enforcing `user_approved=True` barrier before status moves to `PROMOTED`.
    - Implemented `revise_idea` creating a child revision (incrementing `revision_version`, pointing to `parent_idea_id`) and marking the parent as `REVISED` without altering parent hypothesis text.
    - Implemented `abandon_idea` preventing further revision or promotion.
    - Implemented `attach_idea_to_brief` ensuring tentative ideas cannot attach to formal research briefs.
    - Implemented `get_idea_history` reconstructing the full chronological ancestor/descendant tree.
  - [backend/conversation/brief.py](file:///Users/shayanazmi/college/project%20based%20learning%20/langchain/thoth/backend/conversation/brief.py):
    - Added `idea_id` field to `ResearchBrief`.
    - Updated `prepare_research_brief` to accept `idea_id`: validates that the idea exists and is `PROMOTED` (failing closed with `ValueError` on tentative ideas), inherits hypothesis, thinker context, and unresolved objections, and binds mutual references.
    - Added `idea_id` to `substantive_keys` in `update_research_brief`.
  - [backend/api/routes_ideas.py](file:///Users/shayanazmi/college/project%20based%20learning%20/langchain/thoth/backend/api/routes_ideas.py):
    - Exposed REST endpoints:
      - `POST /api/ideas/tentative`
      - `POST /api/ideas/{id}/promote`
      - `POST /api/ideas/{id}/revise`
      - `POST /api/ideas/{id}/abandon`
      - `GET /api/ideas/{id}`
      - `GET /api/ideas/{id}/history`
      - `GET /api/ideas`
  - [backend/main.py](file:///Users/shayanazmi/college/project%20based%20learning%20/langchain/thoth/backend/main.py):
    - Registered `ideas_router` under prefix `/api/ideas`.
  - [backend/tests/test_idea_hypothesis_lifecycle.py](file:///Users/shayanazmi/college/project%20based%20learning%20/langchain/thoth/backend/tests/test_idea_hypothesis_lifecycle.py):
    - 8 comprehensive tests validating tentative status, promotion barrier enforcement, promotion success, revision immutability and lineage tree retrieval, brief rejection of tentative ideas, brief inheritance of promoted ideas, abandonment invariants, and full REST API workflows.
  - [Makefile](file:///Users/shayanazmi/college/project%20based%20learning%20/langchain/thoth/Makefile):
    - Included `backend/tests/test_idea_hypothesis_lifecycle.py` in the canonical `test:` target.
- **Observed Test Evidence:**
  - `pytest backend/tests/test_idea_hypothesis_lifecycle.py`: 8 passed in 0.78s (Exit Code: 0).
  - Canonical suite `make test`: **247 passed, 33 subtests passed in 43.04s (Exit Code: 0)**.
  - Verification check `make lint`: All core modules imported successfully (Exit Code: 0).

---

### Phase 3.2: Thinker Dialectic Convergence & Objection Translation
- **Status:** **ACCEPT**
- **Original Unmet Criterion:**
  1. Translating substantive thinker sparring objections and falsification criteria into explicit counter-evidence search parameters.
  2. Integrating counter-evidence search parameters directly into the literature review search planner and pipeline.
  3. Generating inspectable hypothesis revision recommendations grounded in discovered counter-evidence while strictly preserving user agency without silent mutations.
- **Implementation Changes:**
  - [backend/intellectual_rigour/counter_evidence.py](file:///Users/shayanazmi/college/project%20based%20learning%20/langchain/thoth/backend/intellectual_rigour/counter_evidence.py):
    - Implemented framework-specific counter-evidence query generators and falsification criteria for all 10 philosophical archetypes (Popper, Hume, Box, Kuhn, Simon, Bacon, Aristotle, Descartes, Darwin, Turing).
    - Implemented objection translation engine extracting targeted phrases and keywords into specific scholarly queries.
    - Implemented `generate_hypothesis_revision_proposal` constructing candidate revision options (scoped applicability, mechanistic qualification, falsifiable boundaries) and empirical boundary conditions without modifying the stored hypothesis.
  - [backend/conversation/brief.py](file:///Users/shayanazmi/college/project%20based%20learning%20/langchain/thoth/backend/conversation/brief.py):
    - Added `counter_evidence_queries` and `falsification_criteria` to `ResearchBrief` model and `from_mandate`.
    - Updated `prepare_research_brief` to automatically synthesize a `CounterEvidencePlan` from thinker context / unresolved objections when briefs are formulated.
    - Added `counter_evidence_queries` and `falsification_criteria` to `substantive_keys` in `update_research_brief`.
  - [backend/memory/db.py](file:///Users/shayanazmi/college/project%20based%20learning%20/langchain/thoth/backend/memory/db.py):
    - Added columns `counter_evidence_queries_json` and `falsification_criteria_json` to `research_briefs` table schema and runtime migrations in `init_db()`.
    - Updated `save_brief_db`, `get_brief_db`, and `list_briefs_db` to persist and load counter-evidence fields across restarts.
  - [backend/orchestrator.py](file:///Users/shayanazmi/college/project%20based%20learning%20/langchain/thoth/backend/orchestrator.py):
    - Updated `create_initial_state` to forward `counter_evidence_queries` and `falsification_criteria` from brief data into `ResearchState`.
  - [backend/pipeline.py](file:///Users/shayanazmi/college/project%20based%20learning%20/langchain/thoth/backend/pipeline.py):
    - Added `counter_evidence_queries` and `falsification_criteria` to `ResearchState`.
    - Updated `search_node` to execute targeted queries for counter-evidence and tag resulting `cumulative_sources` with `relation="counter_evidence"`.
  - [backend/conversation/idea.py](file:///Users/shayanazmi/college/project%20based%20learning%20/langchain/thoth/backend/conversation/idea.py):
    - Added `version` property and serialization alias to `ResearchIdea` matching `revision_version`.
  - [backend/api/routes_ideas.py](file:///Users/shayanazmi/college/project%20based%20learning%20/langchain/thoth/backend/api/routes_ideas.py):
    - Exposed REST endpoints:
      - `POST /api/ideas/{id}/counter-evidence-plan`
      - `POST /api/ideas/{id}/propose-revision`
  - [backend/tests/test_thinker_dialectic_and_counter_evidence.py](file:///Users/shayanazmi/college/project%20based%20learning%20/langchain/thoth/backend/tests/test_thinker_dialectic_and_counter_evidence.py):
    - 7 comprehensive tests verifying all 10 framework query templates, objection-to-query translation, brief auto-planning, SQLite persistence across reloads, agency-preserving hypothesis revision proposals, search node counter-evidence query execution and source candidate relation tagging, and FastAPI REST endpoints.
  - [Makefile](file:///Users/shayanazmi/college/project%20based%20learning%20/langchain/thoth/Makefile):
    - Added `backend/tests/test_thinker_dialectic_and_counter_evidence.py` to canonical `test:` target.
- **Observed Test Evidence:**
  - `pytest backend/tests/test_thinker_dialectic_and_counter_evidence.py`: 7 passed in 0.95s (Exit Code: 0).
  - Canonical suite `make test`: **254 passed, 33 subtests passed in 46.90s (Exit Code: 0)**.
  - Verification check `make lint`: All core modules imported successfully (Exit Code: 0).

---

## 3. Next Milestone: Phase 4 — Reproducible Literature Reviews (PRISMA Flow & Evidence Screening)

### Objective
Advance from initial search and single-document retrieval to systematic, verifiable evidence synthesis adhering to reproducible literature review principles (PRISMA flow tracking, inclusion/exclusion filtering, and screening auditability).

### Required Capabilities
1. **PRISMA Flow Tracking**: Record explicit counts and identifiers across review stages: *Identified* (databases, registries) -> *Deduplicated* -> *Screened* (title/abstract) -> *Assessed for Eligibility* (full text) -> *Included* in synthesis.
2. **Explicit Screening Decisions**: Record why candidate papers were included or excluded based on brief `selection_criteria` and constraints.
3. **Appraisal & Contradiction Mapping**: In synthesis reports, provide an auditable evidence matrix contrasting supporting studies against counter-evidence studies tagged during retrieval.
4. **Exportable Audit Trail**: Persist the review protocol, search strings, database timestamps, and screening ledger for reproducible export.

### Acceptance Criteria for Phase 4
- The pipeline produces a structured PRISMA ledger with counts and explicit inclusion/exclusion rationales matching brief selection criteria.
- Full regression suite remains green without performance or schema regressions.

