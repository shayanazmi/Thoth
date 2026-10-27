# Demo tour, intro, motion and palette: user-seat walkthrough (25 Oct 2026)

## What changed

- **Palette: Obsidian & Gold.**
  - Token values were rewritten in `frontend/styles/tokens.css`; the token names are unchanged.
  - Dark is the default. Papyrus/lapis is the light theme, chosen with the toggle or when the OS asks for light on a first visit.
  - Hardcoded colours in `folio.css`/`app.css` now go through tokens.
- **Motion** (`js/motion.js`, `styles/motion.css`):
  - Scenes (View Transitions with a fallback):
    - home → project irises open;
    - project → home closes;
    - the theme switch is a circular reveal;
    - Chat/Split/File layouts morph.
  - Entrances play once, through `fresh()`. Previously every emit re-ran `settle` on every message. Covered:
    - chat cards;
    - a gold outline around new approval cards;
    - workspace page turns;
    - the journey moon on arrival;
    - the ruling ceremony (letterbox dip, seal drop, ripple, verdict written in).
- **Intro** (`js/intro-cinema.js`):
  - Gold dust forms the Ink-moon mark, the bust appears under raking light, then three title cards, then the ask on a gold scale beam.
  - The question's letters fly into the moon and the app irises open.
  - Skippable; reduced motion shows a still ask card.
  - `?intro=lantern` plays the old intro. The ink intro is archived in `docs/archive/legacy_code/intro_v2/`.
- **Guided tour** (`frontend/scripted/`, optional; see its README):
  - Ten chapters, played as a film or stepped through.
  - Scripted mode replays a recorded real run; Live mode coaches you against the real backend.
  - Includes "Your turn" beats, a chapter library, reels, a glossary, quick checks, resume, and a finale.
- **Optional by design:** the cinematic intro always plays and the demo never replaces it. People start the demo only with the **Try the demo** button on the landing page. `?demo` links are developer tools and wait for the intro to finish.
- **Core coupling:**
  - one guarded `import('/scripted/index.js')` in `main.js`;
  - `backend/main.py` mounts `/scripted` if the folder exists.

## Recording (real run, nurses hunch, 25 Oct 2026, ~35 min)

Recorded with `?demo&live&record&autopilot`. I clicked every approval gate myself. Outcomes, as recorded and not edited:

| Chapter | Real outcome |
|---|---|
| Prologue / I | Answers with general-knowledge claims marked unchecked. No idea card appeared, so that beat is skipped (`when`). A notebook proposal card appeared instead. |
| II | Council of 10 thinkers, each answering independently |
| III | Hypothesis pinned (v1), edited (v2) |
| IV | Trial plan with 4 sub-claims. Effort shown before approval: ~15 papers, 5–10 min, ~33 calls. |
| V | 15 witnesses, 3 read in full. **Insufficient evidence.** A chat aside was answered mid-run (conversation never blocks). |
| VI | Systematic review in Auto mode: 26 identified, 25 screened, 10 sought, 8 not retrieved, **0 included** |
| VII | 3 candidate designs; the prospective within-shift cohort was chosen |
| VIII | Outline of 9 sections, approved, written. Reviewer found a FATAL problem in Methods and revised it. Status **Provisional**, 7/9 sections, 11 open items. The export dialog warns PROVISIONAL and was cancelled. |
| IX | UI only (slash menu, layouts, theme, sidebar) |

`fixtures/nurses/` is about 1.8 MB, with no raw project ids (normalised to `{pid}`). The `cities` and `trust` hunches are not recorded; the picker says "Coming soon" for them.

## Checks done

- `make test-vision`: 69 passed, 1 skipped. No backend behaviour changed.
- `?demo&branch=nurses&autoplay`: full replay from prologue to finale in about 3½ minutes, with no `/api/*` calls (fetch is answered by `net.js`). The badge reads "Scripted demo · replaying a real run recorded 2026-10-25".
- Exit:
  - the demo project, its localStorage key and the fetch patch are all removed;
  - the previous project, theme, layout and saved preferences are restored.
- Deep link `?demo&branch=nurses&chapter=5`: the trial stream is rebuilt through `jumpFrom` and the ruling lands.
- Deletion test: with `frontend/scripted/` moved away and the server restarted, there was no tour UI and no `/tour`, and the app was normal. The only trace was one 404 for `/scripted/index.js`.
- Intro: phases verified (dust → mark → bust → cards → ask). The particle canvas was checked with a timer-driven frame shim because the background browser pane does not run `requestAnimationFrame`.

## Known limits / not verified

- Screenshots from the hidden browser pane lag behind the real render. CSS animations and View Transitions were checked by computed state and `getAnimations()`, not by eye at 60 fps.
- The narrow (<1200px) layout overlays the workspace on top of chat, so some spotlight targets sit under the overlay. It is best viewed at 1440×900.
- There are no scenario tests for the frontend tour (the gate is backend-only).
