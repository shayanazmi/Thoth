# The guided tour (`frontend/scripted/`)

A cinematic, step-through tour of Thoth that runs over the real app. It goes from a stray thought to the
thinkers, a hypothesis, the trial, a systematic review, a study design and a drafted proposal, then shows
how to use the app.

**Delete this folder and the tour is gone.**
- `js/main.js` imports `/scripted/index.js` once and ignores a failure.
- `backend/main.py` mounts the folder only if it exists.
- No other file refers to it.

## Play it

| URL | What happens |
|---|---|
| **Try the demo** button on the landing page | How people start it. The cinematic intro always plays first and is never replaced. |
| `/?demo` | Developer link: opens the hunch picker once the intro has finished. |
| `/?demo&branch=nurses&chapter=5` | Jumps straight into a chapter. Chapters are 0–9. |
| `/?demo&reel=gate` | Plays a short reel: `gate`, `thinkers`, `trial`, `draft` or `howto`. |
| `/?demo&autoplay&clean` | A clean film for screen recording: no controls, and "Your turn" beats resolve themselves. |
| `/?demo&live` | Live mode against your real backend. The tour explains each step and waits for you. It never clicks for you. |

**Keys:**
- Space: play / pause
- →: skip the current hold
- ←: previous chapter
- Esc: close a sheet or exit

**Scripted mode** replays a recording of a **real run**: nothing is invented, and a badge says so the whole time. Any request the recording doesn't contain gets an honest "not recorded, switch to Live" answer.

**Exiting:**
- Scripted: the demo project is removed, and your previous project, theme and layout come back.
- Live: you stay in the real project you made.

## Files

| File | Role |
|---|---|
| `index.js` | `install()`: the landing-page "Try the demo" button, and the developer `?demo` params |
| `director.js` | Film engine: chapters, steps, camera/spotlight, captions, beats, control bar, library, quiz, finale, Live coach mode, recording cuts |
| `tour.js` | Screenplay (data only): `CHAPTERS`, `REELS`, `GLOSSARY`, `QUIZ` |
| `net.js` | `replay()` answers `/api/*` from fixtures, rebuilding SSE streams with compressed real timing; `record()` tees real traffic into a tape |
| `progress.js` | Watched chapters, resume point, speed, captions (localStorage, best effort) |
| `branches.json` | The three hunches and their inputs (follow-up, hypothesis, resources) |
| `tour.css` | Every tour surface |
| `fixtures/<branch>/` | `manifest.json` + `chNN.json`. Each chapter has a project snapshot at its start plus the calls made during it. |

## Record (or re-record) a hunch

Fixtures must come from a real run. Never hand-write papers, verdicts or counts.

1. Start the backend with real keys: `make dev`.
2. Start a sink that writes posted recordings into `fixtures/`, for example a tiny HTTP server on `127.0.0.1:8765` that saves `{manifest, files}` to `fixtures/<branch>/`.
3. Open `/?demo&live&record&autopilot&branch=<id>&sink=http://127.0.0.1:8765/`.
   - **autopilot** types and clicks for you, **except at approval gates**: you approve each costly step yourself.
   - The tape is sent after every chapter, and it is also available as `window.__thothRecording`.
4. Reload `/?demo`. The hunch is no longer "Coming soon".

Back-end event shapes can change over time. If a chapter misbehaves on replay, re-record it.
