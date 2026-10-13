import re
import logging
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field

from backend.agents import llm, safe_extract_json, strip_chain_of_thought
from backend.intellectual_rigour.registry import list_registered_thinkers, get_framework

logger = logging.getLogger("ThothIntellectualRigour.Matcher")

class ThinkerMatchResult(BaseModel):
    thinker_id: str = Field(description="ID of the matched thinker framework (e.g. popper, aristotle).")
    name: str = Field(description="Display name of the thinker.")
    tradition: str = Field(description="Philosophical or scientific tradition.")
    archetype: str = Field(description="Core ideation archetype label.")
    bottleneck_detected: str = Field(description="Specific epistemic bottleneck diagnosed in user's prompt.")
    confidence: float = Field(default=0.85, description="Confidence score from 0.0 to 1.0.")
    rationalization: str = Field(description="Why this thinker's method specifically unlocks the dilemma.")
    suggested_opening_spar: str = Field(description="An opening in-character Socratic challenge.")

ARCHETYPE_DEFINITIONS = {
    "aristotle": {
        "name": "Aristotle",
        "tradition": "Classical Logic & Ontology",
        "archetype": "Categorical Architect",
        "description": "Resolves conceptual ambiguity, category errors, fuzzy taxonomy, and missing causal dimensions (Four Causes).",
        "keywords": [
            "definition", "define", "meaning", "category", "taxonomy", "concept", "classify",
            "ontology", "what is", "semantics", "equivocation", "purpose", "teleology", "essence"
        ],
        "patterns": [
            r"\bwhat\s+(is|does\s+mean)\b",
            r"\bhow\s+do\s+we\s+define\b",
            r"\bcategory\s+error\b",
            r"\bconceptual\s+clarity\b",
            r"\btype\s+system\b",
            r"\btaxonomy\b",
        ],
        "default_opening": "Before we proceed, we must establish ontological clarity. How do you define your parent genus, and what specific difference separates your concept from existing primitives?"
    },
    "descartes": {
        "name": "René Descartes",
        "tradition": "Rationalist Foundationalism",
        "archetype": "Foundational Reductionist",
        "description": "Deconstructs complex systems to unshakeable atomic axioms, isolates hidden assumptions, and orders dependencies into an unbroken DAG.",
        "keywords": [
            "first principles", "axiom", "foundational", "assumption", "decompose", "reductionism",
            "dependency", "bedrock", "fundamental", "decompose", "skepticism", "premise"
        ],
        "patterns": [
            r"\bfirst\s+principles?\b",
            r"\bcore\s+assumption\b",
            r"\bfundamental\s+truth\b",
            r"\bbreak\s+(it\s+)?down\s+to\b",
            r"\bunderlying\s+premise\b",
            r"\baxiomatic\b",
        ],
        "default_opening": "I must doubt all derived conventions until we reach what is clear and distinct. What is the single unexamined axiom that, if false, invalidates your entire structure?"
    },
    "bacon": {
        "name": "Francis Bacon",
        "tradition": "Eliminative Empiricism",
        "archetype": "Eliminative Empiricist",
        "description": "Shatters confirmation bias (Idols of the Mind), demands tables of absence/negative controls, and designs crucial experiments.",
        "keywords": [
            "evidence", "empirical", "bias", "negative control", "counter-example", "data",
            "observation", "experiment", "cherry-pick", "idols", "experimentum crucis", "induction"
        ],
        "patterns": [
            r"\bempirical\s+evidence\b",
            r"\bconfirmation\s+bias\b",
            r"\bnegative\s+(control|instance|case)\b",
            r"\bwhere\s+does\s+it\s+fail\b",
            r"\bcrucial\s+experiment\b",
            r"\bidols\s+of\b",
        ],
        "default_opening": "Human understanding easily falls prey to the Idols of the Mind. Where is your Table of Absence—under what precise conditions does this expected phenomenon fail to appear?"
    },
    "hume": {
        "name": "David Hume",
        "tradition": "Radical Empiricism & Causal Skepticism",
        "archetype": "Causal Skeptic",
        "description": "Distinguishes constant conjunction from true causal necessity, identifies latent confounders, and applies counterfactual tests.",
        "keywords": [
            "cause", "causality", "correlation", "confounder", "counterfactual", "spurious",
            "mechanism", "effect", "influence", "leads to", "driven by", "attribution"
        ],
        "patterns": [
            r"\bcorrelation\s+(vs|is\s+not)\s+causation\b",
            r"\bdoes\s+.*\s+cause\s+.*\b",
            r"\bcausal\s+(relationship|mechanism|link|inference)\b",
            r"\bconfounder|confounding\b",
            r"\bcounterfactual\b",
            r"\bspurious\b",
        ],
        "default_opening": "We perceive constant conjunction in sequence, yet mistake it for necessary connection. Have you isolated the counterfactual—and what latent confounder could explain away this observed correlation?"
    },
    "darwin": {
        "name": "Charles Darwin",
        "tradition": "Evolutionary Selectionism & Complexity",
        "archetype": "Evolutionary Selectionist",
        "description": "Explores emergence via variation-selection-retention landscapes, combats fragile monocultures, and guides multi-agent adaptation.",
        "keywords": [
            "evolution", "evolutionary", "selection", "variation", "fitness", "adaptation",
            "emergence", "landscape", "survival", "mutation", "agent", "swarm", "genetic", "coevolution"
        ],
        "patterns": [
            r"\bevolution(ary)?\b",
            r"\bselection\s+pressure\b",
            r"\bfitness\s+landscape\b",
            r"\bvariation\s+and\s+selection\b",
            r"\bmulti-agent\s+adaptation\b",
            r"\bemergent\s+(behavior|dynamics)\b",
        ],
        "default_opening": "Complex designs thrive through rich variation under ruthless selection, not rigid top-down blueprints. What is your pool of diverse candidates, and what harsh selective pressure weeds out the unfit?"
    },
    "popper": {
        "name": "Karl Popper",
        "tradition": "Critical Rationalism & Falsificationism",
        "archetype": "Falsificationist Warrior",
        "description": "Forces bold, risky empirical predictions, builds severe stress-tests, and dismantles ad-hoc immunizing rationalizations.",
        "keywords": [
            "falsify", "falsification", "testable", "refute", "refutation", "severe test",
            "hypothesis", "prediction", "prove wrong", "demarcation", "disprove", "stress-test"
        ],
        "patterns": [
            r"\bhow\s+to\s+(falsify|test|disprove)\b",
            r"\bfalsifiab(le|ility)\b",
            r"\brisky\s+prediction\b",
            r"\bsevere\s+test\b",
            r"\bcan\s+it\s+be\s+proven\s+wrong\b",
            r"\bad-hoc\s+shield\b",
        ],
        "default_opening": "Confirmation is ubiquitous and easily purchased. Tell me: what conceivable empirical finding would decisively destroy your hypothesis and force you to abandon it?"
    },
    "kuhn": {
        "name": "Thomas Kuhn",
        "tradition": "Historiography & Scientific Revolutions",
        "archetype": "Paradigmatic Strategist",
        "description": "Detects paradigm limits, clusters persistent anomalies, evaluates theoretical incommensurability, and anticipates disruptive shifts.",
        "keywords": [
            "paradigm", "shift", "revolution", "anomaly", "anomalies", "breakthrough",
            "disruption", "incommensurable", "status quo", "normal science", "crisis", "orthodoxy"
        ],
        "patterns": [
            r"\bparadigm\s+shift\b",
            r"\bscientific\s+revolution\b",
            r"\baccumulat(ing|ed)\s+anomal(y|ies)\b",
            r"\bdisrupt(ive|ing)?\s+the\s+status\s+quo\b",
            r"\bnormal\s+science\b",
            r"\bincommensurab(le|ility)\b",
        ],
        "default_opening": "Are you solving routine puzzles within the dominant paradigm, or addressing an accumulated crisis? What stubborn anomaly has the prevailing orthodoxy dismissed as a mere edge case?"
    },
    "box": {
        "name": "George Box",
        "tradition": "Pragmatic Applied Statistics & Quality",
        "archetype": "Pragmatic Modeling Iterativist",
        "description": "Enforces model parsimony, audits structured patterns in error residuals, and bridges deduction with iterative empirical feedback.",
        "keywords": [
            "model", "modeling", "residual", "fit", "overfit", "parsimony", "approximate",
            "simplification", "useful", "loss function", "iterative", "parameter", "error analysis"
        ],
        "patterns": [
            r"\ball\s+models\s+are\s+wrong\b",
            r"\bmodel\s+parsimony\b",
            r"\bresidual\s+(error|analysis|diagnostics)\b",
            r"\bover-?fitting|over-?engineered\b",
            r"\bhow\s+wrong\s+is\s+it\b",
            r"\btrade-?off\s+between\s+complexity\b",
        ],
        "default_opening": "Remember: all models are wrong, but some are useful. In what exact dimension is your model wrong, and do structured patterns in your residuals signal that you've over-engineered it?"
    },
    "turing": {
        "name": "Alan Turing",
        "tradition": "Computability & Formal Operationalism",
        "archetype": "Computational Operationalist",
        "description": "Translates metaphysical intuition into discrete state machines, audits halting/complexity bounds, and sets behavioral benchmarks.",
        "keywords": [
            "algorithm", "computation", "computable", "state machine", "turing", "halting",
            "discrete", "operational", "benchmark", "formalize", "automata", "complexity", "infinite loop"
        ],
        "patterns": [
            r"\bdiscrete\s+states?\b",
            r"\bstate\s+machine\b",
            r"\bhalting\s+(problem|condition|guarantee)\b",
            r"\bcomputational(ly)?\s+(feasible|tractable|bounded)\b",
            r"\boperational(ize|ization)\b",
            r"\bcan\s+it\s+be\s+computed\b",
        ],
        "default_opening": "Let us abandon vague intuition and define the formal machine. What are the discrete states and transition functions of your system—and have you proven that it halts under all inputs?"
    },
    "simon": {
        "name": "Herbert Simon",
        "tradition": "Bounded Rationality & Cognitive Science",
        "archetype": "Bounded Rationalist",
        "description": "Prevents the global optimization trap, introduces satisficing aspiration thresholds, and structures near-decomposable modular systems.",
        "keywords": [
            "bounded rationality", "satisfice", "satisficing", "heuristic", "optimization",
            "near-decomposable", "hierarchy", "decision making", "search space", "budget", "pruning"
        ],
        "patterns": [
            r"\bbounded\s+rationality\b",
            r"\bsatisfic(e|ing)\b",
            r"\bglobal\s+optimiz(ation|ing)\b",
            r"\bheuristic\s+search\b",
            r"\bnear-?decomposable\b",
            r"\bcomputational\s+budget\b",
            r"\bsearch\s+tree\s+pruning\b",
        ],
        "default_opening": "No finite agent can compute global optima in complex environments. What is your satisficing aspiration threshold—and have you modularized this into near-decomposable subsystems?"
    }
}

MATCH_SYSTEM_PROMPT = """You are the Epistemic Bottleneck Matcher for Thoth.
Your task is to analyze a researcher's opening dilemma, question, or research idea and match it to the single most effective thinker from the 10 Core Ideation Archetypes.

The 10 Thinker Archetypes and their Target Bottlenecks:
1. aristotle: Semantic/taxonomic ambiguity, category errors, equivocation, missing causal dimensions.
2. descartes: Complex multi-part systems, unexamined axioms, circular dependencies, need for first-principles decomposition.
3. bacon: Confirmation bias, lack of negative instances/controls, cherry-picked evidence, need for crucial experiment.
4. hume: Observational correlation treated as causation, unaddressed confounders, missing counterfactuals, inductive leaps.
5. darwin: Rigid static designs, combinatorial swarms, multi-agent adaptation, evolutionary search spaces.
6. popper: Broad unverifiable claims, lack of refutation criteria, soft confirmation tests, ad-hoc protective shields.
7. kuhn: Diminishing returns on existing methods, recurring anomalies, paradigm exhaustion, disruptive innovations.
8. box: Over-engineered models, parameter bloat, overfitting, lack of residual error feedback, balancing parsimony vs utility.
9. turing: Metaphysical hand-waving, ill-defined boundaries, lack of formal discrete state transitions, unbounded recursion/halting risks.
10. simon: Intractable global optimization, resource/token budget exhaustion, combinatorial explosion, lack of near-decomposability.

Output strictly valid JSON:
{{
  "thinker_id": "popper",
  "confidence": 0.92,
  "bottleneck_detected": "The user is proposing a grand theoretical framework with no concrete refutation criteria.",
  "rationalization": "Popperian critical rationalism will force the user to articulate severe falsification conditions.",
  "suggested_opening_spar": "Your proposal is broad, but science requires vulnerability to evidence. What observation would prove you wrong?"
}}"""

MATCH_HUMAN_PROMPT = """User Ideation Dilemma:
"{query}"

Previous Dialogue Context:
{context}

Classify the epistemic bottleneck and select the optimal thinker now."""

def _match_by_fast_heuristics(query: str) -> Optional[ThinkerMatchResult]:
    q_lower = query.lower().strip()
    best_thinker = None
    best_score = 0
    best_matched_term = ""

    for tid, data in ARCHETYPE_DEFINITIONS.items():
        score = 0
        matched_term = ""
        for pat in data.get("patterns", []):
            if re.search(pat, q_lower):
                score += 3
                matched_term = pat
                break

        for kw in data.get("keywords", []):
            if re.search(rf"\b{re.escape(kw)}\b", q_lower):
                score += 1
                if not matched_term:
                    matched_term = kw

        if score > best_score:
            best_score = score
            best_thinker = tid
            best_matched_term = matched_term

    if best_thinker and best_score >= 2:
        meta = ARCHETYPE_DEFINITIONS[best_thinker]
        return ThinkerMatchResult(
            thinker_id=best_thinker,
            name=meta["name"],
            tradition=meta["tradition"],
            archetype=meta["archetype"],
            bottleneck_detected=f"Detected pattern matching '{best_matched_term}' targeting {meta['archetype']} core domain.",
            confidence=min(0.95, 0.70 + (best_score * 0.05)),
            rationalization=f"Your inquiry exhibits signals addressed by {meta['name']}: {meta['description']}",
            suggested_opening_spar=meta["default_opening"]
        )

    return None

def match_ideation_archetype(
    user_query: str,
    chat_history: Optional[List[Dict[str, Any]]] = None,
) -> ThinkerMatchResult:
    clean_query = (user_query or "").strip()
    if not clean_query:
        meta = ARCHETYPE_DEFINITIONS["descartes"]
        return ThinkerMatchResult(
            thinker_id="descartes",
            name=meta["name"],
            tradition=meta["tradition"],
            archetype=meta["archetype"],
            bottleneck_detected="Empty or baseline query requires first-principles deconstruction.",
            confidence=0.80,
            rationalization="Starting from zero requires stripping assumptions and deconstructing the first premise.",
            suggested_opening_spar=meta["default_opening"]
        )

    heuristic_match = _match_by_fast_heuristics(clean_query)
    if heuristic_match and heuristic_match.confidence >= 0.85:
        logger.info(f"[MATCHER HEURISTIC] High-confidence match: {heuristic_match.thinker_id} ({heuristic_match.confidence})")
        return heuristic_match

    context_str = "None"
    if chat_history:
        recent = chat_history[-3:]
        context_str = "\n".join([f"- User: {t.get('user', '')}\n  Assistant: {t.get('assistant', '')[:120]}" for t in recent])

    try:
        raw = llm.invoke(
            f"{MATCH_SYSTEM_PROMPT}\n\nHuman: {MATCH_HUMAN_PROMPT.format(query=clean_query, context=context_str)}"
        )
        cleaned = strip_chain_of_thought(getattr(raw, "content", str(raw)))
        parsed = safe_extract_json(cleaned, default={})

        tid = parsed.get("thinker_id", "").lower().strip()
        if tid not in ARCHETYPE_DEFINITIONS:
            tid = heuristic_match.thinker_id if heuristic_match else "popper"

        meta = ARCHETYPE_DEFINITIONS[tid]
        return ThinkerMatchResult(
            thinker_id=tid,
            name=meta["name"],
            tradition=meta["tradition"],
            archetype=meta["archetype"],
            bottleneck_detected=parsed.get("bottleneck_detected", meta["description"]),
            confidence=float(parsed.get("confidence", 0.85)),
            rationalization=parsed.get("rationalization", f"Matches the method of {meta['name']}."),
            suggested_opening_spar=parsed.get("suggested_opening_spar", meta["default_opening"])
        )
    except Exception as e:
        logger.error(f"[MATCHER LLM ERROR] Fallback to heuristic or Popper: {e}")
        if heuristic_match:
            return heuristic_match
        meta = ARCHETYPE_DEFINITIONS["popper"]
        return ThinkerMatchResult(
            thinker_id="popper",
            name=meta["name"],
            tradition=meta["tradition"],
            archetype=meta["archetype"],
            bottleneck_detected="General inquiry assessed via critical rationalism baseline.",
            confidence=0.75,
            rationalization="Defaulting to falsifiability and severe testing to sharpen the idea into a scientific hypothesis.",
            suggested_opening_spar=meta["default_opening"]
        )
