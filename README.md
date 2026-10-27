<div align="center">

<img src="frontend/assets/thoth_logo.png" alt="Thoth" width="120"/>

# Thoth

**A research companion that helps you find the question worth asking, and records honestly what the evidence shows.**

</div>

Start with a hunch. Thoth talks it through with you and brings in historical thinkers to argue with it.
It then helps you pin one hypothesis, puts that hypothesis on trial against the literature, runs a systematic
review, designs a study you can actually run, and drafts a research proposal. Along the way it says plainly
what it could not verify.

- **Nothing costly runs without your approval.** Every trial, review and draft shows its plan and cost first.
- **Honest about reading depth.** An abstract is never passed off as the full paper.
- **Never falsely complete.** Drafts stay *provisional* until open gaps are closed.

## Run it

```bash
make setup     # venv, dependencies, .env from .env.example
               # add NVIDIA_API_KEY and TAVILY_API_KEY to .env for real runs
make dev       # http://localhost:8000
```

On the landing page, **Try the demo** plays a recorded real run of the whole journey in about three minutes.

## Test

```bash
make test-vision
```

## Where things are

- **Spec:** `THOTH/THOTH.docx`
- **Working context:** folder map, rules and current state are in [`CLAUDE.md`](CLAUDE.md)
- **Status:** [`docs/SYSTEM_STATE.md`](docs/SYSTEM_STATE.md)
- **Feature specs:** [`docs/features/`](docs/features/README.md)
- **Walkthroughs (evidence):** [`docs/archive/verify/`](docs/archive/verify/)
