# Operational Algorithm: Box Model-Criticism & Diagnostic Loop

```text
INPUT: Quantitative Model M, Empirical Data D, Intended Purpose P
OUTPUT: Structured ThinkerOutput & ReviewArtifact

STEP 1: EXPOSE MODEL ASSUMPTIONS & SIMPLIFICATIONS
  - Extract all explicit and implicit assumptions: linearity, normality, stationarity, i.i.d., parameter constraints.
  - State the explicit operational purpose P for which M is deployed.

STEP 2: RESIDUAL & ERROR STRUCTURE ANALYSIS
  - Examine prediction errors:
      Residuals = Observations - Predictions
  - Classify residual distribution:
      - Random Gaussian Noise: Model captures signal.
      - Structured / Correlated Error: Systematic misspecification.
      - Regime-Specific Breakdown: Model fails in specific sub-domains.

STEP 3: STRESS-TESTING & SENSITIVITY AUDIT
  - Perturb inputs, inject noise, and test stability under slight parameter adjustments.
  - Assess whether minor distribution shifts cause disproportionate output collapse.

STEP 4: BOUNDARY DELINEATION
  - Pinpoint the exact parameter or data regime where model reliability degrades below utility threshold.

STEP 5: COMPETING MODEL & PARSIMONY EVALUATION
  - Compare M against simpler, more parsimonious alternatives (e.g. linear baseline vs. deep overparameterized model).
  - Check whether complexity is justified by significant out-of-sample performance gains.

STEP 6: FITNESS FOR PURPOSE CHECK
  - Evaluate: "Is this model useful for its stated decision or predictive goal despite its known approximation errors?"

STEP 7: CONTEXT-FIRST ASSIGNMENT & OUTPUT
  - If residual distributions, validation loss curves, or perturbation test data are missing:
      verdict = INSUFFICIENT_CONTEXT
      recommendation = WITHHELD_PENDING_CONTEXT
  - If structured residuals, catastrophic boundary failures, or unjustified complexity undermine utility:
      verdict = MATERIAL_OBJECTION
  - If the model is parsimonious, well-calibrated, and clearly bounded:
      verdict = NO_MATERIAL_OBJECTION
```
