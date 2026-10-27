# Research proposal: user-seat walkthrough (25 Oct 2026)

Feature: `docs/features/08-writing.md`. Live NVIDIA NIM, in-app browser on :8001 (this session's own server;
:8000 belonged to a parallel session), the night-shift nurses project (completed trial with 15 witnesses, a
chosen prospective-cohort design, resources on file).

## What was built

- `backend/research/writer.py`: Writer role (prompt from doc 09). Tailors the 10-section outline, then writes ONE
  section at a time from the research file only: the latest completed trial (witnesses numbered W1.. as the
  Judge and Designer numbered them), the verdict, gaps and originality, the chosen design, resources, hypothesis,
  question and the researcher's own "I say" text. Each section gets a tailored view of the file (the full file is
  ~75 KB; the literature sections get ~36 KB, the rest less). Code guardrails: no references list from the
  Writer; no authors/DOIs in its input; a section whose material is missing (no design, no trial, no resources)
  gets a `[GAP: …]`; "Expected outcomes" without a refuting result gets a `[GAP]`; witness ids written into the
  prose become evidence markers.
- `backend/research/verifier.py`: per sentence, deterministic checks first (cited witness exists; its record has
  readable content; numbers appear in the record, via `integrity_gate.verify_quantitative_claim` plus a plain
  number check; `{{file:…}}` markers point at something that exists), then the model judges entailment with the
  doc 09 labels. Labels must agree (only `supports` may keep a sentence as written). Unsupported sentences are
  softened or removed and every removal is listed; factual-looking sentences with no marker are flagged
  "uncited"; if the model can't be reached the sentence is flagged "not checked", never reported verified.
- `backend/research/reviewer.py`: FATAL / MAJOR / MINOR with quoted passages, each placed in the section that
  contains the passage (the named section wins if several do). A FATAL is never dropped.
- `backend/research/proposal.py`: the pipeline and status. FATAL → Writer revises that section → Verifier →
  Reviewer again, at most 2 rounds; sections with the researcher's edits are never revised automatically.
  Thinker reviews via `backend/thinkers/modes.review`; critical concerns (and reviews that couldn't be sorted
  into concerns) stay open until answered; a reply is recorded in the proposal state and as a conversation turn.
  Status is `reviewed` only with every section written and verified, no uncited/unchecked sentences or GAPs,
  a current review with no FATAL, at least one thinker review and no open critical concern; otherwise
  `provisional` with the explicit list. References come from `generate_deterministic_bibliography`, fed only
  the witnesses a surviving sentence cites. Markdown export, watermarked when provisional.
- Storage: versioned notebook sections `proposal` (outline, approval, review, thinker concerns, exports) and
  `proposal_section:<key>` (draft with markers, author, verification). No new table. The conductor sees one
  status line for the proposal instead of the full sections.
- `backend/api/routes_proposal.py`: outline (no heavy work), outline edit, write (SSE, `approve: true`
  required, with an estimate), section edit / regenerate (409 if it has your edits, unless `overwrite`) /
  verify, review (JSON and SSE), thinkers, answer, export (`approve: true` required; PDF/DOCX → 501).
- Roles in `ROLE_MODELS`: `writer`, `verifier`, `reviewer`, all Ultra with hidden reasoning off.
- Frontend `proposal.js` in the Draft tab: outline editor (rename, re-purpose, ↑/↓, remove, add; references
  fixed last) with the estimate next to "Approve and write"; live per-section status; sections rendered with
  author–year citations, softened sentences highlighted (hover shows the original and why), uncited/unchecked
  sentences wavy-underlined, GAPs in red, "Removed unsupported claims" per section; Edit / Regenerate / Verify
  per section; Reviewer findings; thinker reviews with Answer; status header (Verifier / Reviewer / thinker
  counts, open items); Export. All prompts are in-page `<dialog>`s. Chat cards: outline plan and progress.
  "Write the proposal" is offered after choosing a design.
- `backend/tests/scenarios/test_s18_proposal_gates.py`: 8 tests, stubbed models. Gate: 59 passed, 1 skipped.

## Walkthrough

| # | Did | Saw | Verdict |
|---|---|---|---|
| 1 | Opened Draft on the nurses project | "No proposal yet", with ✓ Hypothesis, ✓ Trial with 15 witnesses, ✓ Chosen study design | pass |
| 2 | Draft an outline | ~20 s: 10 sections with project-specific purposes (e.g. "drawing on the floor paper (W3, cross-sectional, low certainty…)"); estimate "9 sections · about 5-11 min · about 55-111 model calls · free tier"; chat card "nothing is written until you approve" | pass (after fix 1) |
| 3 | Moved "Research question and hypothesis" up to follow the background; Approve and write | Sections went *writing… → verified* one at a time (~1 min each, ~10 min total); all 9 written | pass |
| 4 | Read the Verifier's work | 22 claims checked, 15 kept, 4 softened, 3 removed. Softened: W1 "induced misalignment increases mood vulnerability" → "was associated with decreased mood and well-being" (causal leap). Removed: "W15 notes sleep quality correlates with burnout" (predicate drift: W15's record has no sleep-quality data; the sentence echoed the Judge's summary, not the paper). Flagged as uncited: "Night-shift nurses' emotional exhaustion has been repeatedly observed across independent samples…" | pass |
| 5 | Peer Reviewer (first run) | The free tier answered 429 throughout; the fallback's answer wasn't a review. Recorded as "couldn't be reached; no review was made up"; status stayed provisional | pass (honest), then fix 4 |
| 6 | Ran the peer Reviewer again | Review 1: FATAL in Methods ("biweekly waves use overlapping recall periods… cannot establish temporal precedence") → Methods revised; review 2: FATAL again → revised again (×2); review 3: still FATAL. Stopped after 2 rounds: **1 FATAL · 3 MAJOR · 3 MINOR open → provisional**. All 7 findings' passages were found in the text | pass |
| 7 | Asked thinkers to review it | Popper, Hume, Nightingale, all *objecting*: 5 critical and 4 serious concerns (e.g. Hume: both variables come from the same two-week recall window). Status: "Thinkers 0 answered · 5 open" | pass |
| 8 | Answered Hume's temporal-ordering concern in the dialog (add a 14-day daily diary; stop claiming temporal precedence from the waves) | Reply shown under the concern; "1 answered · 4 open"; still provisional | pass |
| 9 | Edited Title and abstract (added the daily diary to the title) | "your edits · not verified"; review marked "out of date"; chat offered "Verify now" | pass |
| 10 | Regenerate on the edited section | Dialog "Replace your edits to 'Title and abstract'?" with a red "Replace my edits"; cancelled, edits kept | pass |
| 11 | Verify now | "your edits · verified"; noticed the edit had lost its `{{file:…}}` provenance (fix 7) | pass |
| 12 | Export without approval (direct API call) | 403 | pass |
| 13 | Export… → "Export with PROVISIONAL watermark" | Markdown download, 35 KB: a PROVISIONAL banner listing the 13 open items, author–year citations, no witness ids or markers left, footer watermark; References = the 8 of 15 witnesses still cited, with DOIs and access badges | pass |

## Problems found and fixed

1. **"Draft an outline" refused with "Pin a hypothesis first"** while the panel showed ✓ Hypothesis: the button
   checked the browser's locally pinned hypothesis, and this browser had none (it was pinned in another). It now
   trusts the server's research file.
2. **The Writer wrote witness ids into the prose** ("the floor paper (W3, cross-sectional, …)"), which would
   reach the export as a meaningless "W3". The prompt now forbids it; ids in parentheses become evidence markers
   (so they are checked); remaining ids render as narrative citations ("Merikanto et al. (2022)").
3. **False "uncited" flags** on the working title, hypothesis restatements and "**Falsifier**: If …" lines
   (they contain "study" or "associated"). The heuristic no longer counts "study" alone, and skips sentences about
   the proposal itself (hypothesis, sub-claims, conditionals, labelled lines). Title and abstract went from 4
   flags to 0 on re-verification.
4. **One rate-limited Reviewer call meant no review.** The Reviewer now retries once after 20 s. The panel
   offered no way to re-run a failed review; it now shows "Run the peer Reviewer" whenever there is no
   current review.
5. **No live progress during review loops** (a single JSON call, minutes long). Added `/api/proposal/review/stream`,
   sharing the write stream's live handler.
6. **Stale state after a reload.** The whole project object, including the proposal and transient flags
   (`loading`, `running`), is saved to localStorage; after a reload the panel showed the stale copy, and a flag
   saved mid-run could leave it stuck. Transient UI state is now module memory, and the proposal is fetched
   fresh once per page load.
7. **Editing lost provenance.** The text shown for editing dropped `{{file:verdict}}` markers, so sentences
   resting on the research file lost their source after an edit. Stored text now keeps them; only rendering
   for readers strips them (pinned by an S18 assertion).
8. The chat progress card showed "0/9 sections" until the end; it now counts as sections arrive. The FATAL
   for a passage that appears in several sections was placed in the first; the named section now wins (found
   in a stubbed run on a scratch copy of the database). Identical "Popper's critical concern is unanswered"
   lines now quote each concern. The export dialog's "PDF and Word come later" line was missing for
   provisional proposals.

## Known gaps

- Two of nine sections and 7 of 22 Verifier checks were served by the fallback (`gpt-oss-20b`) under 429s. Records
  say so (`written_by`, `checked_by`), and the section shows a "fallback model" badge, but the status does not
  treat fallback-checked claims as weaker.
- The Reviewer's FATAL is about the chosen design itself, which the Writer must not change, so revising the
  Methods prose cannot close it. The honest outcome is "provisional". A "revise the design from the review" step
  (back to the Design tab) does not exist yet.
- Writing took ~10 minutes against an estimate of 5-11. The review loop adds ~5 more.
- The uncited-claim heuristic is lexical; it will miss some uncited claims and still flag some framing sentences.
  Flags are shown, not removed.
- The Verifier checks a softened sentence's numbers but does not re-run entailment on the softened wording.
- Multi-witness sentences are judged against the combined records, so the citation lists every cited witness
  even if only one supports the sentence.
- Thinker reviews do not go stale when sections change (by design: answering a concern by editing the
  proposal must not reopen it). A fresh review can be asked for at any time.
- Export is Markdown only; PDF/DOCX return 501.
- Re-running the review from the panel was exercised with the JSON endpoint; the SSE variant is covered by S18
  but was not run live (it would have cost another ~5 minutes of rate-limited calls).
