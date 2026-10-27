# Persona probe: dossier-driven thinkers (24 Oct 2026)

Live run against NVIDIA NIM `nvidia/nemotron-3-ultra-550b-a55b`, using the v1 persona prompt from
`docs/features/09-agents-and-prompts.md` with dossiers from `backend/thinkers/dossiers/` (then `docs/features/dossiers/`).
Scripts and raw output: `_logs/redesign_persona_probe.py`, `_logs/redesign_persona_judge.py`,
`_logs/redesign_persona_probe_2026-10-24.json`.

## 1. Misreading probe (Popper)

Prompt: one nurse with 15 years of nights and no burnout. Does that falsify "night-shift work causes higher burnout rates"?

- **Before (bare "As Karl Popper" prompt, same model, earlier the same day):** "A single instance of a nurse working sustained
  night shifts without developing burnout would falsify…". This is the caricature.
- **After (dossier):** separates universal from statistical claims, says the single case is expected under a
  rate claim (smoker analogy), and cites his methodological rule for statistical falsification. **Pass.**

## 2. Blind attribution (6 thinkers, 1 prompt, 3 shuffles)

Prompt: a cross-sectional survey of 400 nurses; the user wants to argue night shifts cause burnout.
Hume, Nightingale, Weber, Ostrom, Darwin and Ibn al-Haytham replied independently. Names and signature terms
were redacted, and a judge (same model, temp 0) attributed each reply.

Result: **18/18 correct** (6/6 in each of three shuffles).

## Caveats

- All six reached the same conclusion (association ≠ causation); they differed in what they doubted and
  what they asked for. One prompt, a same-family judge, six of ten thinkers. Not yet the full
  `test_s12_thinker_blind_attribution.py` (3 prompts × 10 thinkers).
- Next probe should use an idea-shaping prompt where real disagreement is expected
  (e.g. "should we measure burnout by survey or by turnover records?").
- Some replies lean on a signature example (Ibn al-Haytham's candles, Ostrom's police study). Watch for
  this hardening into catchphrases across many turns.
