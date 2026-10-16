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
| **Phase 4** | Reproducible Literature Reviews | Completed | **ACCEPT** | 12 PRISMA review & evidence synthesis tests passing (`test_prisma_review_and_evidence_synthesis.py`). PRISMA 2020 flow accounting, mathematical invariant verification, criteria-grounded screening ledger, retrieval failure vs eligibility distinction, multi-report study grouping, study appraisal matrix, dialectic contradiction mapping with Phase 3.2 counter-evidence, SQLite persistence, and REST API verified. |
| **Phase 5** | Persistent Research Workspace & Manuscript Engine | Completed | **ACCEPT** | 11 workspace & manuscript engine tests passing (`test_project_workspace_and_manuscript_engine.py`). Project-scoped persistence connecting ideas, briefs, PRISMA review ledgers, evidence matrices, and reports; non-destructive multi-revision drafts with collision guards; multi-format export engine (academic Markdown, LaTeX, verified BibTeX, and publication-ready HTML); and record-level drill-down & bidirectional claim-to-study traceability verified. |
| **Phase 6** | Advanced PDF Compilation, Snowballing Search & Production Collaboration | Next Milestone | **PENDING** | Automated binary PDF generation (via WeasyPrint/XeLaTeX), recursive citation snowballing with decay heuristics, and collaborative multi-tenant sync. |


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

---

### Phase 4: Reproducible Literature Reviews (PRISMA Flow & Evidence Screening)
- **Status:** **ACCEPT**
- **Original Unmet Criterion:**
  1. Record explicit, mathematically coherent PRISMA 2020 literature-review flow counts across databases, deduplication, screening, retrieval, eligibility, and included studies without fabricated totals or count leaks.
  2. Implement an inspectable, criteria-grounded screening decision ledger preserving brief criteria, rationales, specific exclusion reasons, and a strict distinction between retrieval failures (`NOT_RETRIEVED`) and eligibility exclusions (`EXCLUDED`).
  3. Support human reviewer audit operations (confirmations, overrides, audit notes, and reviewer attribution).
  4. Build a traceable study appraisal matrix (design archetype, baseline controls, reproducibility artifacts, statistical validation, limitations, and hypothesis stance) and dialectic contradiction mapping directly incorporating Phase 3.2 counter-evidence.
  5. Integrate flow accounting and evidence matrices into the pipeline, drafted reports, and REST API.
- **Implementation Changes:**
  - [backend/intellectual_rigour/prisma.py](file:///Users/shayanazmi/college/project%20based%20learning%20/langchain/thoth/backend/intellectual_rigour/prisma.py):
    - Defined domain models: `ReviewProtocol`, `ScreeningStage` (`TITLE_ABSTRACT`, `FULL_TEXT_ELIGIBILITY`), `ScreeningDisposition` (`INCLUDED`, `EXCLUDED`, `UNRESOLVED`, `NOT_RETRIEVED`), `ReviewerType` (`AI_RECOMMENDED`, `REVIEWER_CONFIRMED`), `HypothesisRelation` (`SUPPORTS`, `CHALLENGES`, `QUALIFIES`, `NEUTRAL`), `ScreeningDecision`, `StudyAppraisal`, `ContradictionEntry`, `EvidenceMatrix`, `PRISMAFlowCounts`, and `PRISMAReviewLedger`.
    - Implemented `PRISMAFlowCounts.verify_accounting_integrity()` enforcing mathematical invariants across review stages.
    - Implemented `group_sources_into_studies()` linking multiple reports/preprints to underlying studies by DOI, arXiv ID, or normalized title.
    - Implemented `screen_source_title_abstract()` grounded in brief selection criteria and topical indicators.
    - Implemented `screen_source_full_text()` enforcing the crucial distinction between retrieval failures (`NOT_RETRIEVED` for paywalls, 403, network errors, empty extractions) and methodological exclusions (`EXCLUDED` for missing baseline controls).
    - Implemented `appraise_included_study()` extracting study design archetypes, baseline controls, code/data reproducibility artifacts, significance validation, author-reported limitations, and hypothesis stance.
    - Implemented `map_contradictions()` pairing supporting and challenging studies (including Phase 3.2 counter-evidence) and identifying substantive divergences (design divergence, distribution shifts) and empirical resolution requirements.
    - Implemented `generate_prisma_mermaid_diagram()` producing valid Mermaid flowchart markdown.
    - Implemented `run_prisma_review_workflow()` driving end-to-end execution.
  - [backend/memory/db.py](file:///Users/shayanazmi/college/project%20based%20learning%20/langchain/thoth/backend/memory/db.py):
    - Added tables `prisma_reviews` and `screening_decisions` with indexes and foreign keys in `init_db()`.
    - Implemented CRUD helpers: `save_prisma_review_db`, `get_prisma_review_db`, `list_prisma_reviews_db`, `save_screening_decision_db`, `get_screening_decision_db`, `list_screening_decisions_db`, `update_screening_decision_db`.
    - Made `save_brief_db` and `save_prisma_review_db` safe against missing optional fields and foreign key order dependencies.
  - [backend/pipeline.py](file:///Users/shayanazmi/college/project%20based%20learning%20/langchain/thoth/backend/pipeline.py):
    - Added `prisma_review`, `screening_decisions`, `evidence_matrix`, and `prisma_mermaid` to `ResearchState`.
    - Implemented `prisma_node(state: ResearchState) -> dict`.
    - Enhanced `writer_node` to inject PRISMA flow accounting, the evidence appraisal table, and dialectic contradictions into the synthesis context, and automatically append the PRISMA Mermaid diagram and evidence table to the final report.
  - [backend/orchestrator.py](file:///Users/shayanazmi/college/project%20based%20learning%20/langchain/thoth/backend/orchestrator.py):
    - Added `PRISMA` to `ResearchFSMState`.
    - Added `prisma_node` execution and yielded streaming event `"prisma"` between the scraping and drafting phases.
  - [backend/api/routes_prisma.py](file:///Users/shayanazmi/college/project%20based%20learning%20/langchain/thoth/backend/api/routes_prisma.py):
    - Exposed REST endpoints:
      - `GET /api/prisma/reviews`
      - `GET /api/prisma/reviews/{id}`
      - `POST /api/prisma/reviews`
      - `GET /api/prisma/reviews/{id}/decisions`
      - `POST /api/prisma/reviews/{id}/decisions/{id}/confirm`
      - `GET /api/prisma/reviews/{id}/evidence-matrix`
      - `GET /api/prisma/reviews/{id}/mermaid`
  - [backend/main.py](file:///Users/shayanazmi/college/project%20based%20learning%20/langchain/thoth/backend/main.py):
    - Registered `prisma_router` under prefix `/api/prisma`.
  - [backend/tests/test_prisma_review_and_evidence_synthesis.py](file:///Users/shayanazmi/college/project%20based%20learning%20/langchain/thoth/backend/tests/test_prisma_review_and_evidence_synthesis.py):
    - 12 comprehensive unit, integration, and API tests validating mathematical invariants, inflation detection, Mermaid rendering, multi-report study grouping, criteria-grounded screening, retrieval failure vs eligibility distinction, study appraisal, dialectic contradiction mapping, SQLite persistence, autonomous end-to-end workflow execution, and REST API endpoints.
  - [Makefile](file:///Users/shayanazmi/college/project%20based%20learning%20/langchain/thoth/Makefile):
    - Included `backend/tests/test_prisma_review_and_evidence_synthesis.py` in the canonical `test:` target.
- **Observed Test Evidence:**
  - `pytest backend/tests/test_prisma_review_and_evidence_synthesis.py`: 12 passed in 0.89s (Exit Code: 0).
  - Canonical suite `make test`: **266 passed, 33 subtests passed in 47.98s (Exit Code: 0)**.
  - Verification check `make lint`: All core modules imported successfully (Exit Code: 0).

---

### Phase 5: Persistent Research Workspace & Manuscript Engine (Current Milestone)
- **Status:** **ACCEPT**
- **Original Unmet Criterion:** Making research artifacts belong to a coherent, persistent research project rather than temporary state; turning research synthesis into a structured, editable, versioned manuscript whose claims remain connected to sources; providing reliable multi-format export (academic Markdown, LaTeX, verified BibTeX, and publication-ready HTML); and connecting review-flow information and evidence matrices to underlying records.
- **Implementation Changes:**
  - [backend/memory/db.py](file:///Users/shayanazmi/college/project%20based%20learning%20/langchain/thoth/backend/memory/db.py):
    - Added tables in `init_db()`:
      - `research_projects` (project_id, title, description, session_id, status, metadata_json, created_at, updated_at).
      - `manuscripts` (manuscript_id, project_id, title, current_version, brief_id, review_id, created_at, updated_at).
      - `manuscript_revisions` (revision_id, manuscript_id, version, title, author_notes, sections_json, claims_json, references_json, evidence_matrix_json, diff_summary_json, created_at).
      - `manuscript_claims` (claim_id, manuscript_id, revision_id, section, claim_text, evidence_status, supporting_sources_json, counter_sources_json, confidence, reasoning, uncertainties, created_at).
      - `manuscript_exports` (export_id, manuscript_id, version, format, content, metadata_json, created_at).
    - Database migrations adding `project_id` foreign keys to `research_briefs`, `research_ideas`, `prisma_reviews`, and `reports`.
    - CRUD helpers: `save_project_db`, `get_project_db`, `list_projects_db`, `delete_project_db`, `associate_artifact_to_project_db`, `save_manuscript_db`, `get_manuscript_db`, `list_manuscripts_db`, `save_manuscript_revision_db`, `get_manuscript_revision_db`, `list_manuscript_revisions_db`, `save_manuscript_claim_db`, `save_manuscript_claims_batch_db`, `list_manuscript_claims_db`, `save_manuscript_export_db`, `get_manuscript_export_db`, `list_manuscript_exports_db`.
  - [backend/workspace/project.py](file:///Users/shayanazmi/college/project%20based%20learning%20/langchain/thoth/backend/workspace/project.py):
    - Core workspace aggregation: `load_project_workspace` unites project metadata, associated ideas (with revision lineage), briefs, PRISMA reviews (protocol, flow counts, evidence matrix), reports, manuscripts, and export records.
    - Session boundary enforcement: `verify_project_access` guards against cross-session data bleeding.
  - [backend/workspace/manuscript.py](file:///Users/shayanazmi/college/project%20based%20learning%20/langchain/thoth/backend/workspace/manuscript.py):
    - Structured academic draft representation: `create_manuscript`, `create_manuscript_from_brief_and_review` (auto-populating abstract, introduction, PRISMA methodology, evidence-based results, dialectical discussion, limitations, and references).
    - Non-destructive revision engine: `save_manuscript_revision` snapshots draft versions without overwriting historical records.
    - Collision & stale edit prevention: verifies `base_version` before saving revisions.
    - Fine-grained claim diff engine: compares section content, claims (wording changes vs evidence changes vs status changes), and citation additions/removals.
    - Counter-evidence qualification engine: `propose_claim_qualifications_from_evidence` detects relevant counter-evidence and proposes status qualifications (`SUPPORTED` -> `QUALIFIED`) without silent rewriting.
  - [backend/workspace/exporter.py](file:///Users/shayanazmi/college/project%20based%20learning%20/langchain/thoth/backend/workspace/exporter.py):
    - Shared manuscript representation exporting to Markdown, LaTeX, BibTeX, and HTML.
    - Academic Markdown: YAML frontmatter, section structure, GFM evidence matrix table, claim-level evidential ledger, and citation keys (`[@key]`).
    - Compilable LaTeX: Article documentclass, special character escaping (`%`, `&`, `_`, `$`, `#`, `{`, `}`), `booktabs` tables, in-text `\cite{...}`, and embedded bibliography.
    - Authentic BibTeX: generated strictly from stored metadata without fabricating missing DOIs or journals; unverified records clearly labeled.
    - Publication-grade HTML: Semantic HTML5 article structure, XSS protection via `html.escape`, interactive `#ref-...` anchor links, and status badges.
    - Export artifact integrity: all exported artifacts saved in database and linked to specific manuscript revision.
  - [backend/workspace/traceability.py](file:///Users/shayanazmi/college/project%20based%20learning%20/langchain/thoth/backend/workspace/traceability.py):
    - Study drill-down: `drill_down_study_record` resolves study rows to individual reports, screening decisions with criteria and passages, appraisal metrics, dialectic contradictions, and referencing manuscript claims.
    - Review flow node drill-down: `get_flow_node_records` resolves nodes (`identification`, `screening`, `screened_excluded`, `eligibility`, `included_studies`) directly to stored records.
    - Bidirectional claim traceability: `get_claim_traceability` links manuscript claims directly to underlying studies and counter-evidence.
  - [backend/api/routes_workspace.py](file:///Users/shayanazmi/college/project%20based%20learning%20/langchain/thoth/backend/api/routes_workspace.py):
    - REST endpoints for projects (`/api/projects`), manuscripts (`/api/manuscripts`), revisions (`/api/manuscripts/{id}/revisions`), exports (`/api/manuscripts/{id}/export`, `/api/exports/{id}`), and traceability (`/api/traceability/studies/{id}`, `/api/traceability/flow-nodes/{review_id}/{node_id}`, `/api/traceability/claims/{id}`).
  - [backend/main.py](file:///Users/shayanazmi/college/project%20based%20learning%20/langchain/thoth/backend/main.py):
    - Registered `workspace_router`.
  - [backend/tests/test_project_workspace_and_manuscript_engine.py](file:///Users/shayanazmi/college/project%20based%20learning%20/langchain/thoth/backend/tests/test_project_workspace_and_manuscript_engine.py):
    - 11 comprehensive tests validating project CRUD, workspace aggregation and lineage, manuscript instantiation from PRISMA reviews, multi-revision evolution with diff tracking, stale edit collision guards, counter-evidence qualification proposals, multi-format exports (Markdown, LaTeX, BibTeX, HTML), study drill-down, review flow records, bidirectional claim navigation, and REST API endpoints.
  - [Makefile](file:///Users/shayanazmi/college/project%20based%20learning%20/langchain/thoth/Makefile):
    - Added `backend/tests/test_project_workspace_and_manuscript_engine.py` to `test:` target; added workspace modules to `lint:` target.
- **Observed Test Evidence:**
  - `pytest backend/tests/test_project_workspace_and_manuscript_engine.py`: **11 passed in 1.72s (Exit Code: 0)**.
  - Canonical suite `make test`: **277 passed, 33 subtests passed in 50.80s across 17 test suites (Exit Code: 0)**.
  - Verification check `make lint`: All core modules imported successfully (Exit Code: 0).
- **Explicit Documented Limitations:**
  - Direct binary PDF compilation via local headless LaTeX (e.g. `pdflatex` / `xelatex`) or `weasyprint` depends on system binary installations; THOTH validates generated LaTeX and HTML structures deterministically and stores reproducible source snapshots in the export ledger.

---

## 3. Next Milestone: Phase 6 — Advanced PDF Compilation, Snowballing Search & Production Collaboration

### Objective
Advance THOTH into an autonomous, collaborative research companion by integrating server-side binary PDF compilation, recursive citation snowballing with decay heuristics, and multi-tenant synchronization.

### Required Capabilities
1. **Server-Side Binary PDF Generation**: Compilation of publication-ready PDFs from verified LaTeX/HTML templates using headless renderers (WeasyPrint / XeLaTeX) with customizable academic style sheets.
2. **Recursive Citation Snowballing**: Forward and backward citation retrieval with configurable stopping criteria (citation counts, search depth, marginal semantic decay) to discover seminal literature.
3. **Collaborative Multi-Tenant Sync**: Enterprise workspace synchronization between local SQLite stores and cloud Postgres (Supabase) preserving fine-grained audit ledgers and human approval barriers.


