# 08 · Writing: the research proposal

> Vision: §3 stage 10, §8 (honest report status), §11 (never fabricate; no PDF export without approval).

## What the owner wants

- The end product is a **research proposal**. Thoth can't run experiments, so there are no results to report.
- Drafting is **outline first, then section by section**. Each section can be edited and regenerated on its own.
- Before a proposal can be called **reviewed** (not provisional), it must pass the **citation Verifier**,
  the **peer Reviewer**, and **thinker reviews**.

## What's wrong today

One `writer_prompt` produces the same five sections for every run, adds its own citations, and is then
graded by `critic_chain` on the same model. Findings, gaps and drafting get mixed together.

## Design

### Proposal structure (default; editable outline)

1. Title and abstract
2. Background and rationale (from the matrix: floor and ceiling papers)
3. Literature review (from the trial: per sub-claim verdicts, stances, conflicts explained)
4. Gap and contribution (only gaps tied to witnesses; originality verdict quoted honestly)
5. Research question and hypothesis (with strength markers)
6. Methods (from 07: design, measures, sample, analysis plan, threats to validity)
7. Expected outcomes and how each would be interpreted (including the outcome that refutes the hypothesis)
8. Limitations and ethics
9. Timeline and resources
10. References (generated deterministically from cited sources by `generate_deterministic_bibliography`)

### Pipeline (Feynman-style separation)

```
outline (Writer)  ──user approves──▶  section k (Writer, evidence-only, no citations)
                                          │
                                          ▼
                                    Verifier: attach citations; check each source supports the exact
                                    claim; remove or flag unsupported claims; record removals
                                          │
                                          ▼
                       (all sections done) Reviewer: FATAL / MAJOR / MINOR with quoted passages
                                          │  FATAL → Writer revises the section → Verifier again (max 2 loops)
                                          ▼
                                    Thinker reviews (independent): critical concerns must be ANSWERED
                                          │  (a response written into the proposal or a reply on record)
                                          ▼
                                    status = reviewed, otherwise provisional + explicit gap list
```

- The Writer **only** uses the research file: matrix cells, the user's "I say" text, verdicts and design.
  It never adds new facts.
- The Verifier reuses `integrity_gate.py`'s entailment checks (`evaluate_claim_support`, locator checks).
  A citation is valid only if the passage supports the exact wording.
- Loops are bounded (max 2 revision rounds). After that, unresolved FATALs keep the proposal provisional;
  they are never silently dropped.
- The user's edits to a section are preserved. Regenerating a section asks first if it has user edits.
- PDF/DOCX export only with explicit approval. A provisional proposal exports with a `PROVISIONAL` watermark.

### Status surface

The proposal header shows: `provisional` or `reviewed`, the Verifier summary (claims checked / removed /
flagged), the Reviewer counts (FATAL/MAJOR/MINOR open), and the thinker concerns (answered / open).

## Agents

Writer, Verifier, Reviewer: [09](09-agents-and-prompts.md#writer). All on Ultra; the Verifier's URL/locator
checks are deterministic code first, with the model used only for entailment judgements.

## Walkthrough (acceptance)

1. From a project with a trial and design, start the proposal → an outline appears; reorder one section, approve.
2. Sections are written one at a time; every factual sentence has a citation after the Verifier pass.
3. Plant an unsupported claim (test fixture) → the Verifier removes it, and it's listed under "Removed unsupported claims".
4. The Reviewer flags a FATAL → the section is revised → the FATAL is closed, or it stays open with the status provisional.
5. A thinker raises a critical concern → the status stays provisional until the user answers it.
6. Export without approval is impossible; a provisional export is watermarked.

Scenario test: `test_s18_proposal_gates.py`.

## Build note (25 Oct 2026)

Built: `backend/research/{writer,verifier,reviewer,proposal}.py`, `backend/api/routes_proposal.py`,
`frontend/js/proposal.js` (Draft tab), roles `writer` / `verifier` / `reviewer` in `ROLE_MODELS` (Ultra, hidden
reasoning off). State lives in versioned notebook sections (`proposal`, `proposal_section:<key>`); no new table.
Walkthrough: `docs/archive/verify/proposal.md`. Scenario test: `test_s18_proposal_gates.py` (8 tests).

Departures from the design above, and why:
- Evidence markers: besides `{{w:W3}}` and `{{cell:W3.subclaim2}}`, the Writer may use `{{file:verdict}}` (also
  `gaps`, `originality`, `design`, `resources`, `hypothesis`, `question`) for sentences resting on the research
  file rather than a paper. These are checked to exist, not for entailment. The app shows citations as `[W3]`,
  so an edited section can be verified again; readers see author–year.
- The Verifier does not call `evaluate_claim_support`: its heuristics expect scraped-source records with
  passages, while a witness here is a structured record (results with locators, analyst reading, abstract).
  It reuses `verify_quantitative_claim` for numbers and `generate_deterministic_bibliography` for references;
  entailment is the model's job, one sentence per call.
- A factual-looking sentence without a marker is flagged "uncited" (kept, visible, keeps the proposal
  provisional) rather than removed: the detector is lexical and removing on it would delete framing sentences.
- `[GAP]` markers keep the proposal provisional: they are missing content.
- The Reviewer retries once after a pause; it runs automatically after writing and on request (JSON or SSE).
- Thinker reviews: an unstructured review (no envelope) counts as a concern that must be answered.
- Export is Markdown only for now (approval required; provisional is watermarked).

