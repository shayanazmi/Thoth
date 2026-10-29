# 05 · Literature: finding and reading papers

> **Built (first version) 24 Oct 2026** as part of the trial: see [`docs/archive/verify/trial.md`](../archive/verify/trial.md).
> The systematic-review tier (protocol, Screener, Auto / Human-in-the-loop, PRISMA flow) was rebuilt on 25 Oct 2026:
> see [`docs/archive/verify/systematic_review.md`](../archive/verify/systematic_review.md). The scan tier still uses the older pipeline.

> Vision: §5 (lightweight scan vs formal PRISMA), §11 (never present abstract-level inspection as
> full-text analysis).

## What the owner wants

- Three tiers: ① quick look, ② scan, ③ systematic review.
- **Every paper gets its full details**, not "title and abstract, and the rest of the paper is missing".
- PRISMA can run fully automatic or with a human in the loop (project switch, 02).
- Users can upload PDFs and paste a DOI / arXiv ID / URL.

## Tiers

| Tier | Trigger | Size | Approval | Output |
|---|---|---|---|---|
| ① Quick look | Conductor tool, **Check this** | ~5 papers | none | A short cited answer in chat; papers added to the thread library |
| ② Scan | User action / accepted offer | ~20-40 papers | one, with estimate | Library + a first-pass matrix (06), labelled with each row's access level |
| ③ Systematic review | User action, after a protocol | as many as the protocol yields | protocol approval + estimate | PRISMA 2020 flow, screening log, full-text matrix, risk-of-bias notes |

Each tier has its **own output shape**. None of them produces the old five-section report.

## The paper record (what "full details" means)

The **Reader** builds this for every paper, *without seeing the hypothesis*, so the record is neutral and
reusable:

| Group | Fields |
|---|---|
| Identity | title, authors, year, venue, DOI / arXiv / PMID, links, citation count |
| Access | `full_text | partial | abstract_only | inaccessible`, plus the text source (arXiv, PMC, Unpaywall OA, S2 PDF, user upload) |
| Study | question/aim, design (RCT, cohort, cross-sectional, qualitative, review…), setting, population, sample size |
| Measures | each construct → how it was operationalised (instrument, scale, items, objective vs self-report) |
| Analysis | methods, controls/covariates, statistical approach |
| Results | main findings with numbers **and page/section locators** |
| Limitations | as stated by the authors, plus design limitations the Reader notices (marked as Reader's) |
| Provenance | for each field, `from_full_text | from_abstract | not_reported | not_accessible` |

Rule: a field that can't be filled says `not reported in abstract` or `not accessible`. It is never
inferred. `extraction_quality` from `ingestion.py` carries through end to end and is never upgraded
downstream (the rule in `CLAUDE.md`).

### Getting full text (in order)

1. arXiv PDF / HTML
2. PubMed Central OA (Europe PMC full-text XML)
3. Unpaywall / OpenAlex `best_oa_location`
4. Semantic Scholar `openAccessPdf`
5. User upload (PDF) → parsed (try `nvidia/nemotron-parse`, with `pypdf` as fallback)

If all of these fail, the paper is `abstract_only`, the record shows **Upload PDF to complete**, and its
witness weight is lowered (06).

## Agents

| Agent | Job | Model |
|---|---|---|
| **Librarian** | Turns the question into a search strategy (PICO/PEO concepts, synonyms, databases), runs searches, dedupes, snowballs citations, fetches full text | Lightning (query gen) + code |
| **Reader** | Builds the neutral paper record above, field by field, with locators | Ultra (accuracy matters here; Lightning when a paper is abstract-only) |
| **Screener** | Systematic review only: applies the protocol's inclusion and exclusion criteria with a reason per decision | Lightning for title/abstract screening, Ultra for full-text screening |

Existing code reused: `scholarly.py` (arXiv, S2, OpenAlex, Europe PMC, PubMed, snowballing),
`ingestion.py` (access badges), `intellectual_rigour/prisma.py` (screening, flow counts, Mermaid diagram).

## Systematic review (PRISMA 2020)

1. **Protocol** (drafted by the Librarian, approved by the user): question in PICO/PEO form,
   databases, search strings, date range, inclusion and exclusion criteria, outcomes.
2. **Search + dedupe** → identification counts.
3. **Title/abstract screening** by the Screener. Co-pilot: the user audits each decision (keyboard-fast
   include/exclude/maybe); Autopilot: decisions are applied, with disagreement-prone ones (confidence < 0.7) queued for later audit.
4. **Full-text retrieval + screening** → reports sought, not retrieved, assessed, and excluded with reasons.
5. **Included studies** → Reader records → the trial matrix (06).
6. **PRISMA flow diagram** generated from real counts only (never estimated).

### As built (29 Oct 2026): scale, stopping rules, citation searching

- **Budget**, set on the protocol card before approval: 300 database records, 200 citation records, 2 citation
  rounds, stop after 50 irrelevant in a row, 30 full texts. The estimate follows it (`POST /api/review/estimate`).
  `POST /api/review/{id}/budget` raises it later.
- **Identification**: OpenAlex (100 a page; cursor paging needs `OPENALEX_API_KEY`), Europe PMC (cursorMark) and
  Semantic Scholar relevance search (offset paging; a spent key falls back to the anonymous pool). Every request is a
  row in `sys_review_searches`: query, page, returned, new, total, cost and error.
- **Stopping rules**, recorded in `sys_reviews.stopping_json` and shown as "Why the search stopped":
  - `source_exhausted`, `budget_reached`, `source_error`;
  - `consecutive_irrelevant` (keyword records only, in relevance order; overriding a decision inside the run supersedes it);
  - `citation_saturation`, `citation_rounds_max`, `citation_budget_reached`, `citation_off`;
  - `ft_budget`, `user_stop`.
  An entry is never deleted, only superseded.
- **Citation searching**: references and citing works of the records that passed title/abstract screening
  (`backend/research/citations.py`), screened like any record and counted apart ("identified by citation searching").
- **Stop and Continue**: re-entrant by stage and stored cursors. A review left running by a crash is `stopped` and can
  be continued.
- **Synthesis**: the trial is tied to the hypothesis version, carries the review's coverage and limitations to the
  Judge, and is never rewritten. A raised budget makes a new trial.
- Evidence: `docs/archive/verify/evidence_depth.md`; tests S22, S23.

## Live view

Papers stream into the library with their access badges; the Reader's progress shows per row. See 02 "Live work".

## Prompts

[09 § Librarian](09-agents-and-prompts.md#librarian), [§ Reader](09-agents-and-prompts.md#reader),
[§ Screener](09-agents-and-prompts.md#screener).

## Walkthrough (acceptance)

1. Run a scan → each paper card shows design, sample, measures and results, with a provenance tag per field.
2. A paywalled paper shows `abstract only`, "not reported in abstract" cells, and **Upload PDF**. Upload
   it, and the cells fill from full text with locators.
3. Paste a DOI → the paper is fetched and added with its record.
4. A systematic review in Co-pilot: the protocol is approved, screening decisions are auditable, and the
   PRISMA counts add up and match the log.
5. Grep the record store: no field is marked `from_full_text` on a paper whose access is `abstract_only`.

Scenario tests: `test_s14_paper_record_provenance.py`, `test_s15_prisma_counts_match_log.py`.
