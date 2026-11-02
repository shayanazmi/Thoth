# Frontend

Vanilla ES modules and CSS, **no build step**: the backend serves this folder at `/`.

| Path | What it holds |
|---|---|
| `index.html` | The shell: sidebar, journey, conversation, research file, intro |
| `js/main.js` | Boot, home, journey, layout, theme |
| `js/chat.js` | The conversation and slash commands |
| `js/store.js`, `js/api.js` | Project state in the browser, and the API client |
| `js/workspace.js` | The research file panels |
| `js/thinkers.js`, `hypothesis.js`, `trial.js`, `review.js`, `design.js`, `proposal.js` | One module per stage |
| `js/intro-cinema.js`, `js/motion.js` | The cinematic intro and the motion system |
| `styles/` | `tokens.css` (Obsidian & Gold palette, motion tokens), `app.css`, `folio.css`, `motion.css`, `components.css` |
| `assets/` | The bust, scales, logo, favicon and social preview |
| `scripted/` | The optional guided demo ([README](scripted/README.md)); delete the folder to remove it |

Conventions: CSS tokens only (no hard-coded colours), storage access wrapped in `try/catch`, and every animation
respects `prefers-reduced-motion`. UI modules are served with `Cache-Control: no-cache`, so a reload never mixes
old and new modules.

---

<sub>Thoth · Developed by Shayan Azmi</sub>
