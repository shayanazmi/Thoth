# Thoth Agentic Evaluation Suite

This directory contains the automated evaluation framework, benchmarks, and simulation test harnesses for the Thoth Multi-Agent Research Platform.

---

## 1. Overview & Architecture

Thoth evaluates autonomous research outputs across multiple dimensions:
- **Groundedness & Faithfulness**: Verifying that all generated claims trace back to cited primary academic sources (arXiv, Semantic Scholar, OpenAlex).
- **Hallucination Prevention**: Detecting unsupported claims and hallucinations using adversarial prompts.
- **Conversational Continuity**: Evaluating context retention, token budget adherence, and graceful escalation from casual chat to full research.
- **Multi-Turn Personas**: Simulating academic personas (skeptical researcher, graduate student, interdisciplinary theorist) across multi-turn interactions.

Evals can run in two modes:
1. **Offline Mode (Default / CI)**: Uses deterministic heuristics or mocked judge models for fast, zero-cost regression testing.
2. **Live Mode**: Uses LLM-as-a-Judge (`ThothJudgeModel` backed by OpenAI or NVIDIA models) with DeepEval metrics.

---

## 2. Directory Structure

```
evals/
├── run_production_evals.py             # Main DeepEval production evaluation runner
├── production_eval_results.json        # Baseline test run results
├── test_phase7_end_to_end_validation.py # End-to-end pipeline validation
├── test_persona_simulations.py         # Multi-turn persona simulations
├── test_adversarial_continuity.py      # Stress testing conversational continuity
├── test_conversation_to_research.py    # Testing escalation from chat to research
├── test_end_to_end_user_journey.py     # Full lifecycle simulation
├── test_actionable_followups.py        # Follow-up suggestion quality
├── test_relevance_and_expansion.py     # Query expansion & relevance benchmarking
├── test_snowballing.py                 # Citation graph snowballing tests
├── test_server_live_endpoints.py       # Live SSE streaming endpoint tests
├── test_nvidia_models.py               # NVIDIA endpoint connectivity tests
├── list_nvidia_models.py               # Inspect available remote models
└── .deepeval/                          # DeepEval run logs and telemetry cache
```

---

## 3. Running Evaluations

### Running the Production Eval Suite (DeepEval)
```bash
# Run in offline mode (using offline judge mock)
python evals/run_production_evals.py

# Run in live mode (requires API keys in .env)
python evals/run_production_evals.py --live
```

### Running Multi-Turn Simulations
```bash
# Run simulation suite from scripts/eval/
python scripts/eval/run_multiturn_simulation.py --max_simulations 5

# Run with live judge and save JSON output
python scripts/eval/run_multiturn_simulation.py --live --save_json evals/simulation_results.json
```

### Running Specific Scenario Tests
```bash
# Test persona simulations
pytest evals/test_persona_simulations.py -v

# Test adversarial dialogue continuity
pytest evals/test_adversarial_continuity.py -v

# Test escalation pipeline
pytest evals/test_conversation_to_research.py -v

# Test citation snowballing logic
pytest evals/test_snowballing.py -v
```

---

## 4. Evaluation Metrics

| Metric | Target | Description |
|---|---|---|
| **Faithfulness** | $\ge 0.85$ | Are factual claims strictly grounded in retrieved papers? |
| **Answer Relevancy** | $\ge 0.80$ | Does the response directly address the research query? |
| **Hallucination** | $\le 0.10$ | Frequency of fabricated citations or statistics. |
| **Conversational Coherence** | $\ge 0.85$ | Smooth context handover across multi-turn exchanges. |
| **Escalation Accuracy** | $\ge 0.95$ | Correct classification of casual banter vs. research mandate. |
