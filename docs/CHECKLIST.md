# Thoth: what we set out to do, what's done, what's left

> Written 27 Oct 2026. One page that tracks the whole redesign as a checklist.
> The spec is `THOTH/THOTH.docx`. The designs are `docs/features/00-10`. Evidence for every ticked box is a
> user-seat walkthrough in `docs/archive/verify/`. Current open gaps are also kept in `docs/SYSTEM_STATE.md`.
> Gate: `make test-vision` → 83 passed, 1 skipped (the live-model test), as of 28 Oct 2026.

Legend: `[x]` done and walked through · `[~]` partly done · `[ ]` not started.

---

## 1. What we set out to do

**North star (the owner's words):** Thoth should not merely answer questions a researcher already knows how to
ask. It should help people discover which questions are worth asking, understand what existing scholarship
establishes, and investigate what might meaningfully add to that knowledge.

Thoth plays three roles at once: a **conversational companion**, a **rigorous investigator** and a
**research-development partner**.

### The journey a user should live (vision §3)

1. Open conversation, with no formal prompt needed.
2. Thoth recognises a promising direction.
3. It prepares heavier work without blocking the chat.
4. It asks for approval before substantial work, showing an estimate.
5. The user brainstorms with thinkers.
6. A lightweight scan, or a formal PRISMA review when it's worth it.
7. Back to brainstorming with what was found.
8. Refine one main hypothesis.
9. Design a study that fits the user's real resources.
10. A report or proposal with an honest status (provisional until reviewed).

### Guardrails that must hold everywhere (vision §11)

- Never fabricate citations, counts, access, methods, results or originality.
- Never present abstract-level reading as full-text reading.
- Never call anything complete while critical review is unresolved: use provisional plus explicit gaps.
- Never call an idea original because a model said so. Never invent a gap to keep a project going.
- No PDF export without explicit approval.
- Criticism is severity-gated with bounded retries; no single thinker has a veto.

### The redesign, as feature specs (`docs/features/`)

| # | Feature | Journey stages |
|---|---|---|
| 01 | Conversation core (conductor, memory, offers) | 1-4, 7 |
| 02 | Threads, projects and the living research file | all (storage, §9-10) |
| 03 | Thinkers as co-authors | 5 |
| 04 | Hypothesis: main + rivals, strength markers | 8 |
| 05 | Literature: Librarian, Reader, systematic review | 6 |
| 06 | The trial: hypothesis on trial, papers as witnesses | 6 |
| 07 | Study design with feasibility | 9 |
| 08 | Research proposal: Writer, Verifier, Reviewer | 10 |
| 09 | Agents and prompts (one model map, one prompt shape) | all |
| 10 | UI revamp | all |

---

## 2. Status by feature

### 01 · Conversation core — built (`verify/conversation_core.md`)
- [x] One conductor per chat turn; proposes notebook entries; offers heavy work but never starts it
- [x] General-knowledge claims marked "unchecked"
- [x] Thread memory and rolling summaries on the server
- [x] Thoth hears the thinkers: one-to-one rooms and stances in its context, recall across rooms, named thinkers in summaries, and quotations checked against the record (28 Oct, `verify/thinkers_heard.md`)
- [ ] Paraphrase of a thinker is not checked (only quotations are)

### 02 · Threads, projects, research file — first slice built (`verify/projects_on_server.md`)
- [~] Versioned research-file sections on the server (`notebook_sections`: question, hypothesis, design, proposal …)
- [x] Question, hypothesis versions, rivals and the conversation on the server; a second browser rebuilds the project (27 Oct)
- [ ] Chat cards (trial plan, reviews, proposals) still only in the browser
- [x] Thread → Project when a hypothesis is accepted; sidebar shows Projects and Threads (27 Oct)
- [ ] Per-section status and project status = the weakest required section
- [x] Autopilot / Co-pilot switch with per-step overrides (sub-claims, proposal applied; screening stored, not wired) (27 Oct, `verify/modes_live_work_stop.md`)
- [x] Live-work header (elapsed vs estimate, papers, model calls) and **Stop** that keeps finished work, for the trial (27 Oct)
- [ ] Stop for the proposal, the systematic review and re-analysis; the screening override in the review panel
- [x] Delete with a count confirmation, leaving nothing in any table the project owns (27 Oct)
- [ ] Vault notes and legacy `workspace/` manuscripts are not part of the delete yet
- [ ] An `activity` table so live work can be replayed (the mode is a notebook entry; no `projects` table was needed)
- [x] Scenario `test_s11_thread_promotion_and_retention.py` + walkthrough

### 03 · Thinkers — built (`verify/thinkers.md`)
- [x] Approved roster of ten, dossiers, personas, memory per project
- [x] Modes: council, one-to-one, debate, independent blind review
- [x] Reviews used by the design, the trial verdict and the proposal
- [~] Blind-attribution drift test (live, long; runs from the parent session)

### 04 · Hypothesis — built (`verify/hypothesis.md`)
- [x] Hypothesis pinned above the chat, with version history (client-side)
- [x] Sub-claims split by the Analyst, editable; editing re-analyses every matrix row (25 Oct)
- [x] Four strength markers on the card, quoted from the hypothesis (two named constructs needed for a trial; comparison, scope, falsifier flagged if missing) (27 Oct)
- [x] Rivals on the server: park, retire, swap in; re-map the latest trial's library (no search, no Reader) (27 Oct)
- [x] Every trial tied to its hypothesis version; an old verdict labelled "for v1; it is now v2" (27 Oct)
- [x] Scenario `test_s13_hypothesis_versions_and_rivals.py` + walkthrough
- [ ] The Judge is given the computed markers (today it names missing ones from its own reading)
- [ ] Writer and Designer check that the trial they use is for the current version
- [x] Every version keeps why it changed: reason, trigger, evidence, what was known then; the original motivation with its question (29 Oct, S25, `verify/revision_history_and_design_loop.md`)

### 05 · Literature and systematic review — built (`verify/trial.md`, `verify/systematic_review.md`)
- [x] Librarian strategy, OpenAlex + Europe PMC, open-access full text, honest access badges
- [x] Hypothesis-blind Reader with provenance on every field; "Upload PDF to complete"; add by DOI
- [x] Systematic review: protocol → approval → search → screening; PRISMA counts only from recorded decisions
- [x] Europe PMC tightened to titles and abstracts, off-topic records dropped and counted (25 Oct)
- [x] Review at scale: budget on the protocol card, paged OpenAlex / Europe PMC / Semantic Scholar, every request logged with its cost (29 Oct, S23, `verify/evidence_depth.md`)
- [x] Recorded stopping rules (exhausted, budget, K irrelevant in a row, citation saturation, full-text budget, errors, Stop); limitations stated (29 Oct)
- [x] Citation searching in rounds, counted apart in the PRISMA flow; Stop and Continue (29 Oct)
- [ ] A review can be revised and re-screened
- [ ] A not-retrieved review record can take an uploaded PDF
- [ ] Borderline off-topic papers still get in (e.g. intimate-partner violence among night-shift nurses)

### 06 · The trial — built (`verify/trial.md`)
- [x] Plan with an estimate; runs once, only on approval
- [x] Live matrix, witness weights, "I say", case for and against, GRADE-style verdict, originality guardrails
- [x] Papers the fallback model read are re-read by the primary model (25 Oct; tested, not yet seen live)
- [x] Thinker reviews of the verdict (25 Oct)
- [x] Each paper appraised with the checklist for its design (RoB 2, JBI, MMAT, SANRA, core); weight = design × access × appraisal; the Judge rates down for risk of bias (29 Oct, S24)
- [x] Citation neighbours of the strongest witnesses checked for prior work; closest prior work named by id; coverage stated on every verdict (29 Oct)
- [ ] Older trials keep fallback-read papers flagged (the fetched text isn't stored, so they can't be re-read)
- [ ] Speed: ~1 analysed paper per minute on the free tier (15 papers ≈ 8-10 min)

### 07 · Study design — built (`verify/study_design.md`)
- [x] Resources form; 2-3 candidate designs from the trial's lessons; feasibility labels
- [x] Code guardrails: witness-cited measures, no causal claims from non-causal designs, stated assumptions
- [x] Choose with your own notes; thinker critique
- [x] Unsourced claims flagged: appeals to unnamed studies, effect sizes with no witness and no "assumed" (28 Oct, `verify/design_revision.md`)
- [x] A design-level FATAL from the peer Reviewer goes back to the Design tab: one revised design, changes per finding, what's still open (28 Oct)
- [x] Designs keep the trial their witness ids come from; proposal sections are marked stale when the design changes (28 Oct)
- [ ] Revise the design from thinker critiques (today: only from the peer Reviewer's findings)
- [x] Regenerate all stale sections in one step after choosing a new design, then re-review; a finding no longer raised is recorded as resolved by that design version (29 Oct, S26)

### 08 · Research proposal — built (`verify/proposal.md`)
- [x] Editable outline → approval with an estimate → sections from the research file only
- [x] Verifier per sentence (soften / remove / flag), Reviewer with at most 2 revision rounds, thinker concerns answered
- [x] Provisional vs reviewed with explicit open items; references from cited witnesses only; Markdown export watermarked
- [ ] Fallback-checked claims labelled but not treated as weaker in the status
- [ ] The uncited-claim check is a word-matching heuristic
- [ ] PDF / Word export (with approval)
- [x] The recall-windows FATAL went round the loop and is recorded as resolved by design v2 (29 Oct); the new design drew 3 new design FATALs, so the proposal stays provisional, honestly
- [x] An advisory (not a gap) when the literature review rests on a scan rather than a systematic review

### 09 · Agents and prompts — built
- [x] One prompt shape and shared preamble; model map in `ROLE_MODELS`; `_served_by` recorded on every record
- [x] Extraction roles run with hidden reasoning off; `MODEL_SLOTS` caps concurrency at 4

### 10 · UI revamp — built (`verify/ui_v2.md`, `verify/demo_tour.md`)
- [x] Journey layout, workspace tabs, in-page dialogs, intro, recorded demo tour
- [ ] Only the nurses example is recorded for the demo
- [ ] No frontend tests
- [ ] Accessibility review pass on the built UI

### Cross-cutting
- [x] Old pipeline and dead code retired to `docs/archive/legacy_code/pipeline_v1/` (`verify/legacy_retirement.md`)
- [ ] Vault notes are global, not project-scoped (vision §9)
- [ ] Resource awareness: a session cost counter (vision §10)
- [ ] Deployment model decision, ADR-005 (vision §12)
- [ ] Review what's left of the older thinker engine (`intellectual_rigour/frameworks/`) and `workspace/` manuscripts

---

## 3. The loop (how each remaining item gets done)

Run this once per unchecked item, one item in flight at a time:

1. **Pick** the top unchecked item from the order below. Open its spec in `docs/features/` and the vision section.
2. **Write the scenario test first** in `backend/tests/scenarios/` with stubbed models. It encodes the user-seat
   criterion and must fail before the change.
3. **Build** the smallest change that makes it pass. New tables go into SQLite and a Postgres migration together.
   No live model calls while the parent session's long live test runs.
4. **Gate**: `make test-vision` must be green.
5. **Walk it through in the browser** from the user's seat. Use a scratch copy of the DB when the step would change
   the real nurses project. Fix what you find, re-run the gate.
6. **Record**: walkthrough in `docs/archive/verify/`, stamp `docs/SYSTEM_STATE.md`, tick the box here, update
   `CLAUDE.md` if the gate count or the map changed.
7. **Hand back** to the owner for review and commit (agents never push).

### Suggested order

1. ~~**02 · Projects on the server** (state out of localStorage, thread → project, delete with counts).~~ Done 27 Oct.
2. ~~**04 · Hypothesis versions, rivals and strength markers**~~ Done 27 Oct.
3. ~~**02 · Autopilot / Co-pilot switch, live-work header and Stop.**~~ Done 27 Oct (trial; see gaps).
4. ~~**01 · Thinker replies into the conductor's memory.**~~ Done 28 Oct.
5. ~~**07 → 08 · Send a design-level FATAL back to the Design tab**; source-check design assumptions.~~ Done 28 Oct.
6. **05 · Systematic review: revise and re-screen; PDF for not-retrieved records.**
7. **08 · Weigh fallback-checked claims; PDF/Word export with approval.**
8. **Cross-cutting: project-scoped vault, cost counter, ADR-005, legacy review.**
9. **10 · Frontend tests, accessibility pass, more demo recordings.**
