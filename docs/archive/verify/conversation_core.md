# Conversation core: user-seat walkthrough (24 Oct 2026)

Feature: `docs/features/01-conversation-core.md` (+ notebook proposals from 02).
Run in the in-app browser against `uvicorn backend.main:app` on :8000, live NVIDIA NIM
(`nemotron-3-ultra-550b-a55b`), fresh project.

| # | User did | Thoth did | Verdict |
|---|---|---|---|
| 1 | "why do night-shift nurses burn out more?" | 36 words: general-knowledge answer underlined with a **check** link, then one question ("more than whom?"). No plan card. | pass |
| 2 | "day-shift nurses in the same hospitals… sleep at the wrong time" | Proposed a research question (card: Accept / Edit / Not now) + one short question (less / worse / wrong-time sleep) | pass |
| 3 | Accept | Question pinned above the chat; written server-side as notebook `question` v1 | pass |
| 4 | States hypothesis | Hypothesis proposal restating the claim faithfully (after a prompt fix, below) | pass |
| 5 | Accept, then "yes, check it" | quick_look: 5 papers, labelled "abstracts only"; reply cites them | pass, after fix |
| 6 | "I want to see what the wider literature says" | Offer card: Lightweight literature scan, scope / time / model calls, "nothing starts until you say so" | pass |
| 7 | Plan it | Existing plan card (plan v1) with **Approve and run**. No run started. | pass |
| — | Browser console | no errors | pass |

## Problems found and fixed during the walkthrough

1. **Literature dumps** (first smoke run): `quick_look` on the opening message, 300-word reviews in reply to
   musing, no proposals, offered to "pull full text". Fixed in the prompt (v1.1 in doc 09).
2. **Unfaithful proposal**: the hypothesis proposal added "rather than sleep duration or quality alone", which the user
   never said. Prompt now requires a faithful restatement.
3. **Gap from five abstracts**: after a quick look it said "That's the gap your hypothesis targets".
   Prompt now says five abstracts are a glimpse; report what these papers show and offer a scan.

## Not covered / known gaps

- Thinker replies (`/api/brainstorm/chat`) are not yet written to server-side turn memory, so the
  conductor doesn't see what a thinker said unless the client includes it in `chat_turns` on a new thread.
- The project is still created on the first message (not promoted at hypothesis acceptance, per 02).
- Replies arrive whole (5-10s), not token-streamed.
- `offer_step` offers only `scan` and `systematic_review`; trial / design / proposal arrive with features 06-08.
- The pinned question + hypothesis header gets tall on a phone and covers part of the chat.
