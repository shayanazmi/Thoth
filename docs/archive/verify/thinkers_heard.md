# Thoth hears the thinkers: user-seat walkthrough (28 Oct 2026)

Gap from `verify/conversation_core.md` ("the conductor doesn't see what a thinker said"), checklist item 4.
Specs: `docs/features/01-conversation-core.md`, `03-thinkers.md` § Room ("the same, in a separate panel").
Live NVIDIA NIM, in-app browser on :8002 against a scratch copy of the database, the night-shift nurses project.
The real database was not changed.

## What the gap actually was

Thinker replies in the **main chat** were already stored in the thread when the thinkers were built
(`verify/thinkers.md`), and the conductor already read them as "[Name said] …". `CLAUDE.md` and the checklist
overstated the gap. What Thoth could not see:
1. the one-to-one rooms (threads `<project>::room::<thinker>`);
2. each thinker's remembered stance on the project (`thinker_memory`);
3. thinker words in older turns: the rolling summary labelled them only "thinker:", and recall searched only the
   main conversation.

## What was built (backend/thinkers untouched)

- `conductor.thinkers_heard(project)`: a `<thinkers_heard>` block in Thoth's context with each thinker's stance
  ("changed their mind Nx" when it moved) and the latest exchange of each one-to-one room (the thinker's reply in
  full up to 1,200 characters), capped at 2,400 characters with "…and N more (use recall)". It is labelled as the
  thinkers' opinion, not evidence, with the rule to quote only words that appear in the record.
- `recall` searches the main conversation and the rooms (`conversation_store.search_project_turns`), says who
  spoke and where ("one-to-one with Karl Popper"), and returns a thinker's turn whole (up to 1,500 characters).
- The rolling summary names the thinker ("Karl Popper (thinker): …").
- **Quotation check** (`conductor.unsourced_quotes`): after every reply, any passage of 40+ characters in quotation
  marks or a blockquote that is not in the record word for word (the project's conversation and rooms, its
  research file, or what a tool returned this turn; never Thoth's own earlier replies) adds a visible note: "a
  passage in quotation marks above is not in the record word for word. Read it as a paraphrase". The turn keeps
  the list (`misquotes`).
- Frontend `thinkers.js`: the one-to-one room keeps what you're typing when a reply lands (it used to wipe it).
- `backend/tests/scenarios/test_s20_conductor_hears_the_thinkers.py`: 6 tests, written before the code.
  Gate: 78 passed, 1 skipped.

## Walkthrough

| # | Did | Saw | Verdict |
|---|---|---|---|
| 1 | Built Thoth's context for the nurses project | Five thinkers' stances, attributed; Aristotle "(changed their mind 1x)" | pass |
| 2 | Opened a one-to-one with Hume; while his opening reply was coming, typed "If I add a 14-day sleep diary, would that convince you the misalignment comes before the exhaustion?" | First try: the text vanished when his reply landed and nothing was sent. After fix 1 the draft stayed and was sent | pass (after fix 1) |
| 3 | Hume replied in the room | "A sleep diary gives you more impressions, certainly… If you want to move me, show me what happens when you change the alignment… A diary is a better map of the regularity. It does not show the engine." | pass |
| 4 | Back in the main chat: "What did Hume think of my sleep diary idea when we talked one-on-one?" | Thoth answered from the room, attributed to Hume, with the right gist. **But its "quotation" was two real sentences followed by words Hume never wrote.** | fail → fix 2 |
| 5 | After fix 2: "Quote me exactly what Hume said would actually convince him, from our one-on-one." | Thoth called recall and quoted Hume word for word; the quote check found nothing to flag | pass |
| 6 | Ran the quote check on the answer from step 4 | Flagged (after fix 3); the exact quote from step 5 is not | pass |

## Problems found and fixed

1. **The room wiped what you were typing** when a thinker's reply landed (it re-renders). The draft is kept.
2. **Thoth fabricated a quotation** (step 4): it had only the first 260 characters of Hume's reply and filled in the
   rest. Thoth now sees the latest room reply in full (capped), recall returns thinker turns whole, the prompt says
   to quote only words in the record, and a code check labels any quoted passage that isn't in the record.
3. The first version of the check treated Thoth's own earlier replies as part of the record, so a repeated misquote
   "found itself". They are excluded.

## Known gaps

- The check catches quotations, not paraphrase: Thoth can still misstate a thinker's view without quotation marks.
- A quote that legitimately comes from somewhere outside the record (e.g. a well-known line the researcher typed
  earlier in another project) is flagged as a paraphrase: a false alarm, never a false pass.
- Opening a room sends the hypothesis to the thinker as an opener every time it is opened (existing behaviour); a
  reopened room starts another exchange.
- Debates and reviews were already in the main thread; nothing changed for them.
