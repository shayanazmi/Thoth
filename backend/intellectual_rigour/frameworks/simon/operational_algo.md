# Operational Algorithm: Simon Bounded Rationality & Search Space Audit

```text
INPUT: Decision Process / Optimization Procedure / Agent Architecture P
OUTPUT: Structured ThinkerOutput & ReviewArtifact

STEP 1: OBJECTIVE CLARIFICATION
  - Separate stated global objective from the actual operational/measurable proxy.
  - Detect goal distortion (Goodhart's / Campbell's Law).

STEP 2: SEARCH SPACE & COMBINATORIAL MAPPING
  - Characterize decision variables, branching factors, and search tree depth.
  - Determine whether exhaustive optimization is physically impossible ($O(b^d)$).

STEP 3: RESOURCE BOUNDS & BUDGET AUDIT
  - Quantify explicit limits: compute cycles, memory, latency budget, token context, financial cost.
  - Reject ungrounded claims of global optimality that ignore resource limits.

STEP 4: SEARCH STRATEGY & HEURISTICS EVALUATION
  - Examine heuristic guidance (greedy, beam search, A*, MCTS, reinforcement learning policy).
  - Assess whether heuristics introduce severe systemic blind spots or local optima traps.

STEP 5: STOPPING RULE AUDIT
  - Why does the algorithm terminate where it does?
  - Is the stopping criterion an explicit satisficing aspiration threshold, or an arbitrary timeout/iteration cutoff?

STEP 6: SIMPLER SATISFICING ALTERNATIVE SEARCH
  - Formulate a simpler, lower-cost baseline (e.g. heuristic rules, linear model, greedy search) and evaluate if the complex system justifies its massive search cost.

STEP 7: CONTEXT-FIRST ASSIGNMENT & OUTPUT
  - If search branching statistics, resource consumption metrics, or stopping criteria are missing:
      verdict = INSUFFICIENT_CONTEXT
      recommendation = WITHHELD_PENDING_CONTEXT
  - If an algorithm claims global optimization while masking combinatorial explosion, or fails to justify search costs:
      verdict = MATERIAL_OBJECTION
  - If bounded rationality is embraced, heuristics are calibrated, and satisficing stopping rules are explicit:
      verdict = NO_MATERIAL_OBJECTION
```
