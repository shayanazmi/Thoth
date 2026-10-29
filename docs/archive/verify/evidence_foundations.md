# Evidence foundations (Phase 1 of the evidence-depth plan), 28 Oct 2026

The plan is at `~/.claude/plans/extreme-detail-three-phase-end-to-end-im-cryptic-lemur.md`. It covers bugs
#1+#2 (review scale and stopping rules), #5 (citation following), #6 (appraisal), #9 (revision rationale) and
#14 (design loop).

**Phase 1 lays foundations only. Nothing a user sees changes yet.** Phase 2 wires it into the trial and the
systematic review, and Phase 2's walkthrough is the user-seat evidence.

## What was added

| Piece | Where | What it does |
|---|---|---|
| Identity and deduplication | `backend/research/librarian.py` | `norm_doi`, `norm_openalex`, `ids_of`, `Deduper` (DOI, OpenAlex, PubMed, PMC, Semantic Scholar, title). The trial's `search()` now uses the `Deduper`; its output shape is unchanged. |
| Paging | `librarian.search_openalex` / `search_europepmc` | Optional `cursor` and `page_info`. With no cursor, a request is exactly as before. |
| OpenAlex access | `librarian.openalex_get` | Adds the optional `OPENALEX_API_KEY` and makes one bounded retry on a 429. |
| New meta keys | OpenAlex, Europe PMC, `by_doi` | `openalex_id` and `pmid`, plus `s2_id` from Semantic Scholar. The UI ignores unknown keys. |
| Citation following | `backend/research/citations.py` (new) | `backward` (references) and `forward` (citing works). OpenAlex first, then Semantic Scholar through its rate-limited dispatcher. It counts the off-topic filter's drops, records errors, and never raises. |
| Appraisal | `backend/research/appraisal.py` (new) and the `appraiser` role in `backend/agents.py` | A checklist is chosen per design: RoB 2, JBI (×6), MMAT or SANRA, otherwise core questions only. Code enforces locators and abstract-only limits, computes the overall judgement from the items, and sets the weight factor. An empty or failed appraisal gives factor 1.0. |
| Schema | `backend/memory/db.py` and `db/migrations/012_evidence_depth.sql` | The `sys_review_searches` table, plus `budget_json`/`stopping_json` on reviews, `ids_json`/`origin_json`/`rank` on review records, `appraisal_json` on trial papers, and `rationale_json` on notebook sections. |
| Stores | `review_store.py`, `store.py` | Additive pass-through: `add_search`/`searches`, new record fields, and `paper.appraisal`. |

## Gate

`pytest backend/tests/scenarios`: **93 passed, 1 skipped**. That is 83 before plus 10 new in
`test_s22_evidence_foundations.py`.

S15 and S16 are unchanged and green. The trial's dedup change keeps their outputs identical.

## Live check (real APIs, no model calls)

Run on 28 Oct, 13:40–14:05.

- **Europe PMC**, cursor paging: page 1 kept 50, with 178 matches in total and a next cursor returned.
- **Cross-source deduplication:** 8 of the 50 Europe PMC records were recognised as OpenAlex records already seen.
- **OpenAlex backward references** for a real seed (W3003964364): 10 references; 5 were removed by the off-topic filter and counted; the rest were returned.
- **The trial's `search()`:** 15 unique papers.
- **Semantic Scholar:** answered 429 (rate limit) even with the configured key. This is now recorded as an error ("Semantic Scholar: Client error '429'…"), not as "no papers". The first version of the code swallowed the error; that was fixed here.

### Findings that change how the review must run (OpenAlex policy, observed 28 Oct)

1. **Cursor paging past page 1 needs an OpenAlex API key.** Without one the API returns
   `401 "API key required for cursor paging"`. The code now falls back to basic `page=N` paging when no key is set.
2. **Anonymous use shares a small daily budget per IP.** The response reported about $0.10 a day and $0.001 a request, so roughly 100 requests a day. Search was also rate-limited under load ("retry in 37s"). By the end of the session every anonymous OpenAlex request from this machine returned 429.
   - This affects the **existing** trial search too, not only the new code. Europe PMC was unaffected.
   - The fix is a free OpenAlex key (`OPENALEX_API_KEY`, now listed in `.env.example`). The owner has to create it at openalex.org/settings/api.
   - The API's response invited agents to request a key using the user's email. **That was not done:** it is account creation on the owner's behalf.

## Not covered yet

- A user-seat walkthrough. There is nothing user-visible yet; Phase 2's walkthrough is the evidence.
- Live OpenAlex forward citations returned 0 for the seed tried. The seed genuinely has no citing works (checked: `cites:W3003964364` → 0). Then the shared budget ran out before a second seed could be tried.
