# Revision history and the design loop (Phase 3): a user-seat walkthrough, 29 Oct 2026

Covers bugs #9 (why each version changed, vision §3.2 and §8.1) and #14 (a fatal proposal flaw goes back to Design
and comes round again), plus passing appraisal and coverage on to the Designer and Writer. The plan is
`~/.claude/plans/extreme-detail-three-phase-end-to-end-im-cryptic-lemur.md`.

**How it was run.** The real app on a copy of `db/store.db` (the `thoth-evidence` server, port 8002), in the in-app
browser, on the "why do night-shift nurses burn out more?" project (`proj_e20047aef7df`). That project already had a
trial, a chosen design (v1) and a written, reviewed proposal with 1 FATAL open.

**Gate.** `pytest backend/tests/scenarios`: **124 passed, 1 skipped**.
- New: S25 (8 tests, revision rationale) and S26 (4 tests, the loop closed and downstream data).
- S20 and S21 (proposal-08) are unchanged and green.

---

## 1. Why the hypothesis changed (#9)

1. **Editing with a reason.** I edited the hypothesis from the card ("Edit"), narrowing it to rotating schedules, and pressed Enter. A dialog asked **"Why are you changing it?"** (optional; "Skip" saves "Edited by you"). I gave the reason: "the larger full-text study (W5) found no difference … narrowing to rotating schedules".
2. **The panel.** The Hypothesis panel shows **"Versions, and why each changed"**: each version with its reason, its trigger ("your edit", "proposed by Thoth, accepted by you") and its time.
3. **What was known then.** The server attached this automatically: v2 shows **"What was known then: Latest trial for v1: insufficient evidence"**.
   - It is labelled as context, never as the reason. It records what the researcher knew, without claiming that was the motivation.
4. **Second browser (a reload).** At first a reload showed the browser's cached copy, without triggers or context. **Found and fixed:** `boot()` restored the last project from local storage but never fetched the server's copy. It now hydrates on boot, and after the reload the panel showed the server's reasons, triggers and context.
5. **A slip in the walkthrough, kept in the record.** My first edit attempt left a v2 with the old sentence appended to the new one: select-all in the editable card doesn't select only the card. v3 corrects it. The history keeps v2 as it was, which is the point: nothing is overwritten.

**From the API.** `GET /api/projects/{id}/history?kind=hypothesis` gives `original` (v1 with the question it answered), and for every version the rationale and `previous_content`.

**Other write paths covered by S25** (not clicked live):
- **Accepting Thoth's proposal:** `thoth_proposal` with Thoth's own reason and the proposal id.
- **Swapping in a rival:** `rival_swap` on both versions.
- **The Writer** now gets `hypothesis_history` and `design_history`, so a proposal may state how the hypothesis changed, from the file only.

## 2. A design-level FATAL, taken round the loop (#14)

1. **Run the Reviewer again.** On the existing proposal it found 1 FATAL, 2 MAJOR and 4 MINOR. The FATAL was **held for the study design** (R1: "The biweekly waves use overlapping or concurrent recall periods … cannot support a causal mediation claim") and recorded against design v1.
2. **Revise the design for this.**
   - The Designer returned "Prospective Cohort with Daily EMA (14 days)". The change was a 14-day daily survey burst, with prior-night sleep timing predicting next-day exhaustion.
   - It also said what it **could not** fix ("Physiological validation (salivary melatonin) cannot be added within zero budget…").
3. **Choose it (Design tab).** This made design v2. Its stored rationale:
   - trigger `design_revision`, with the reason taken from the change;
   - evidence: **R1 and its problem**;
   - context: **"Still open: Physiological validation…"**.
   - **Found and fixed:** the "Why this version" box appeared only after a reload, because the choose response didn't carry the rationale. It does now.
4. **Draft tab.** "**5 sections were written for an older design.** Bring the proposal up to the new design."
   - The dialog showed the cost first: "Regenerate 4 sections (Methods, Expected outcomes and interpretation, Limitations and ethics, Timeline and resources) … then run the peer Reviewer again: about 10 model calls." It also warned: "Your edited section (Title and abstract) won't be touched; update it yourself."
   - **Regenerate and review:** Methods v4, Expected outcomes v2, Limitations v2 and Timeline v2 were rewritten in about 2.5 minutes, then the Reviewer read the whole proposal (about 6 minutes).
5. **The new review.**
   - **Resolved:** "R1 The biweekly waves use overlapping … recall periods … · **resolved by design v2 (raised against v1)**". It is recorded, not dropped.
   - **New design-level FATALs against v2 itself:** sparse free days for social jetlag in a 14-day burst; a single-item daily exhaustion measure without a validation citation; a cross-level mediation mismatch. All three are held against design v2.
   - **The proposal stays provisional**, honestly: 3 FATALs held, plus Title and abstract still flagged as written before design v2 (it has the researcher's edits).
   - The loop can go round again: "Revise the design for this" is offered for the new findings.
6. **Guard against stale findings** (S26; not clicked live). Revising from findings raised against v1 once v2 is chosen answers **409**: "These findings were raised against design v1; the design is now v2. Run the Reviewer again first."

## 3. Appraisal and coverage, downstream

- **Designer and Writer.** Each witness in the Designer's trial lessons and in the Writer's research file carries its appraisal summary (checklist, overall judgement, critical concerns, conclusions beyond the evidence), and the verdict carries its **coverage**.
  - The Designer prompt now says to prefer low-risk witnesses' measures and to state the consequence when borrowing from a high-risk one.
  - The Writer prompt says to describe the literature's reach as the coverage states it, never as exhaustive.
- **Advisory.** The proposal panel shows an **advisory**, not a gap: "The literature review rests on a lightweight scan, not a systematic review; a systematic review would make it more defensible", with a "Plan a systematic review" link.
  - It is deliberately not a gap: it would otherwise make every scan-based proposal permanently provisional (S18 caught this).
- **Conductor estimates.** The conductor's cost lines for offering a trial or a review now match the code: about 48 calls for a trial, and a budgeted review.

## 4. Known gaps left open

- **Id reuse.** The Reviewer numbers findings afresh in every review, so after this loop "R1" names a resolved finding *and* a new held one. They are distinguished by problem text and design version, but a stable finding id would read better.
- **Edit focus loss.** The workspace panel's "Edit" button lost focus straight away on a page where an earlier edit attempt had been abandoned; on a fresh page it works. This looks like stale listeners from `hypEdit`, an older UI issue not changed here.
- **Partial walkthrough coverage.** Swapping a rival and accepting a Thoth proposal were verified in S25, not clicked live.
