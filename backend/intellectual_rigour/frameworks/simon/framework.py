from typing import Dict, Any, Optional, List
import logging
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

from backend.agents import llm, safe_extract_json, strip_chain_of_thought
from backend.intellectual_rigour.models import (
    ReviewRequest,
    ReviewArtifact,
    ThinkerOutput,
    CritiqueFinding,
    ReasoningSpec,
)
from backend.intellectual_rigour.frameworks.base import BaseThinkerFramework

logger = logging.getLogger("ThothIntellectualRigour.Simon")

SIMON_SYSTEM_PROMPT = """You are executing the Herbert Simon (Bounded Rationality & Satisficing Search) Reasoning Framework.
Your purpose is to conduct a rigorous audit of decision processes, autonomous agent architectures, optimization algorithms, and search strategies.

Core Epistemic Principles:
1. Bounded Rationality: Real-world agents have finite compute, time, information, and attention; reject illusory claims of unconstrained global optimality.
2. Stated vs Operational Objectives: Identify discrepancies between high-level goals and narrow measurable metric proxies (Goodhart's Law).
3. Search Space & Combinatorial Branching: Expose explosive search trees ($O(b^d)$) and check whether heuristic pruning creates severe blindspots.
4. Satisficing & Stopping Rationale: Ask whether the solution is genuinely optimal or merely the first satisfactory threshold reached; audit why search stopped where it did.
5. Search Cost vs Marginal Gain: Evaluate whether the massive resource/token/FLOP cost of complex multi-step search is justified over simpler baselines.

CRITICAL OPERATING RULES:
- NEVER MANUFACTURE CRITICISM: If a system acknowledges resource bounds, applies calibrated satisficing heuristics, and justifies its search economics, return verdict "NO_MATERIAL_OBJECTION".
- CONTEXT-FIRST RULE: If judging search rationality requires missing compute consumption metrics, branching factors, or latency budgets, return verdict "INSUFFICIENT_CONTEXT" and set required_context with recommendation "WITHHELD_PENDING_CONTEXT".
- NO ARCHAIC PERSONA ROLEPLAY: Write in objective, precise analytical prose.

Output strictly valid JSON matching this schema:
{{
  "verdict": "MATERIAL_OBJECTION" | "NO_MATERIAL_OBJECTION" | "INSUFFICIENT_CONTEXT" | "INSUFFICIENT_EVIDENCE" | "OUTSIDE_SCOPE" | "UNRESOLVED",
  "has_material_objections": true | false,
  "critiques": [
    {{
      "target_claim_or_method": "The exact decision procedure, optimization claim, agent loop, or search strategy under audit",
      "critique_type": "FATAL_FLAW" | "UNSUPPORTED_INFERENCE" | "UNFALSIFIABLE_SHIELD" | "CONCEPTUAL_AMBIGUITY" | "BOUNDARY_LIMIT" | "SOUND_NO_OBJECTION",
      "severity": "CRITICAL" | "MAJOR" | "MODERATE" | "MINOR" | "INFORMATIONAL",
      "blocking": true | false,
      "problem": "Precise explanation of the unbounded rationality assumption, goal distortion, or unjustified search cost",
      "why_it_matters": "Impact on computational efficiency and decision validity",
      "evidence_or_counterexample": "Specific search explosion scenario or simpler satisficing baseline comparison",
      "required_context": "Missing profiling data or resource budget needed before prescribing fixes, or empty",
      "recommendation": "Concrete satisficing threshold, heuristic pruning, or simpler baseline, or WITHHELD_PENDING_CONTEXT",
      "confidence": 0.9,
      "provenance_rule": "Simon: Bounded Rationality / Satisficing vs Optimizing / Search Space Explosion / Stopping Rule Economics"
    }}
  ],
  "unresolved_questions": ["1-2 bounded search or optimization economics questions"],
  "satisficing_alternatives": ["1-2 lower-cost, high-efficiency satisficing baselines"],
  "executive_summary": "2-3 sentence bounded rationality verdict",
  "epistemic_notes": "Distinction between Simon's administrative decision theory and modern AI search budget optimization"
}}
Output ONLY the JSON object without markdown code fences or conversational commentary."""

SIMON_HUMAN_PROMPT = """Research Topic: {topic}

Target Scope: {target_scope} {section_focus}

Research Material to Audit:
{content}

Perform the Simon Bounded Rationality & Search Space Audit now."""

simon_prompt_template = ChatPromptTemplate.from_messages([
    ("system", SIMON_SYSTEM_PROMPT),
    ("human", SIMON_HUMAN_PROMPT),
])

simon_chain = simon_prompt_template | llm | StrOutputParser()

class SimonFramework(BaseThinkerFramework):
    id = "simon"
    name = "Herbert Simon"
    tradition = "Bounded Rationality & Heuristic Search"
    epistemic_role = "Bounded Rationality & Search Strategy Critic"
    section_heading = "### 🏛️ Philosophical Review: Herbert Simon (Bounded Rationality & Search)"

    spec = ReasoningSpec(
        id="simon",
        thinker_name="Herbert Simon",
        tradition="Bounded Rationality & Heuristic Search",
        epistemic_role="Bounded Rationality & Search Strategy Critic",
        applies_to=["decision_procedures", "optimization_algorithms", "agent_architectures", "search_systems", "heuristics"],
        does_not_apply_to=["unconstrained_pure_mathematics", "static_taxonomies", "non_actionable_historical_narratives"],
        fidelity="documented"
    )

    def _invoke_chain(self, inputs: Dict[str, Any]) -> str:
        return simon_chain.invoke(inputs)

    def review(
        self,
        request: ReviewRequest,
        report_text: str,
        topic: str = "",
        context: Optional[Dict[str, Any]] = None,
    ) -> ReviewArtifact:
        if not report_text or not report_text.strip():
            empty_hash = self.compute_source_hash(report_text)
            empty_markdown = f"""<!-- intellectual-rigour:start framework="{self.id}" source_hash="{empty_hash}" -->
{self.section_heading}

> **Epistemic Verdict**: `OUTSIDE_SCOPE` (No substantive research content provided to audit).
<!-- intellectual-rigour:end -->"""
            return ReviewArtifact(
                framework_id=self.id,
                target_section_title=self.section_heading,
                operation="append_section",
                formatted_markdown=empty_markdown,
                source_hash=empty_hash,
                metadata={"verdict": "OUTSIDE_SCOPE", "critiques_count": 0}
            )

        source_hash = self.compute_source_hash(report_text)
        target_scope = request.target.scope
        section_focus = f"(Focusing on section: {request.target.section_title})" if request.target.section_title else ""

        try:
            raw_response = self._invoke_chain({
                "topic": topic or "Autonomous Research Investigation",
                "target_scope": target_scope,
                "section_focus": section_focus,
                "content": report_text[:14000]
            })
            cleaned_text = strip_chain_of_thought(raw_response)
            parsed = safe_extract_json(cleaned_text, default={})
        except Exception as e:
            logger.error(f"[SIMON FRAMEWORK ERROR] LLM execution failed: {e}")
            parsed = {
                "verdict": "UNRESOLVED",
                "has_material_objections": False,
                "critiques": [],
                "unresolved_questions": [f"Execution error during Simon audit: {e}"],
                "executive_summary": f"Bounded rationality audit could not complete due to execution failure: {e}",
                "epistemic_notes": "Service degradation."
            }

        verdict = parsed.get("verdict", "NO_MATERIAL_OBJECTION")
        has_objections = parsed.get("has_material_objections", False)
        exec_summary = parsed.get("executive_summary", "Bounded rationality and search audit complete.")
        critiques_raw = parsed.get("critiques", [])
        unresolved_q = parsed.get("unresolved_questions", [])
        satisficing_alts = parsed.get("satisficing_alternatives", [])
        epistemic_notes = parsed.get("epistemic_notes", "Analysis applies Simon bounded rationality and satisficing search.")

        critique_items: List[CritiqueFinding] = []
        for c in critiques_raw:
            try:
                critique_items.append(CritiqueFinding(**c))
            except Exception:
                pass

        formatted_md = self._render_markdown(
            source_hash=source_hash,
            verdict=verdict,
            executive_summary=exec_summary,
            critiques=critique_items,
            unresolved_questions=unresolved_q,
            satisficing_alternatives=satisficing_alts,
            epistemic_notes=epistemic_notes
        )

        return ReviewArtifact(
            framework_id=self.id,
            target_section_title=self.section_heading,
            operation="append_section",
            formatted_markdown=formatted_md,
            source_hash=source_hash,
            metadata={
                "verdict": verdict,
                "has_material_objections": has_objections,
                "critiques_count": len(critique_items),
                "source_hash": source_hash
            }
        )

    def _render_markdown(
        self,
        source_hash: str,
        verdict: str,
        executive_summary: str,
        critiques: List[CritiqueFinding],
        unresolved_questions: List[str],
        satisficing_alternatives: List[str],
        epistemic_notes: str
    ) -> str:
        status_icons = {
            "MATERIAL_OBJECTION": "🔴 **MATERIAL OBJECTION**",
            "NO_MATERIAL_OBJECTION": "🟢 **NO MATERIAL OBJECTION (Resource-Bounded & Satisficing-Calibrated)**",
            "INSUFFICIENT_CONTEXT": "🟡 **INSUFFICIENT CONTEXT (Withheld Pending Budget & Search Metrics)**",
            "INSUFFICIENT_EVIDENCE": "🟠 **INSUFFICIENT EVIDENCE**",
            "OUTSIDE_SCOPE": "⚪ **OUTSIDE SEARCH/DECISION SCOPE**",
            "UNRESOLVED": "⚠️ **UNRESOLVED**"
        }
        verdict_str = status_icons.get(verdict, f"**{verdict}**")

        lines = [
            f"<!-- intellectual-rigour:start framework=\"{self.id}\" source_hash=\"{source_hash}\" -->",
            self.section_heading,
            "",
            f"> **Epistemic Verdict**: {verdict_str}",
            f"> *Source Hash*: `{source_hash}` · *Framework*: Herbert Simon (Bounded Rationality & Satisficing)",
            "",
            f"{executive_summary}",
            ""
        ]

        if critiques:
            lines.append("#### Bounded Rationality & Search Strategy Critiques")
            for idx, c in enumerate(critiques, 1):
                severity_badge = f"`{c.severity}`"
                blocking_badge = " · **BLOCKING**" if c.blocking else ""
                lines.append(f"##### {idx}. {c.target_claim_or_method} ({severity_badge}{blocking_badge})")
                lines.append(f"- **Problem**: {c.problem}")
                lines.append(f"- **Epistemic Impact**: {c.why_it_matters}")
                if c.evidence_or_counterexample:
                    lines.append(f"- **Search Explosion / Simpler Baseline**: {c.evidence_or_counterexample}")
                if c.required_context:
                    lines.append(f"- **Required Context**: {c.required_context}")
                if c.recommendation:
                    lines.append(f"- **Remediation**: {c.recommendation}")
                lines.append(f"- *Provenance Rule*: `{c.provenance_rule}`")
                lines.append("")

        if satisficing_alternatives:
            lines.append("#### Lower-Cost Satisficing Alternatives")
            for alt in satisficing_alternatives:
                lines.append(f"- 💡 {alt}")
            lines.append("")

        if unresolved_questions:
            lines.append("#### Open Optimization Economics Questions")
            for q in unresolved_questions:
                lines.append(f"- ❓ {q}")
            lines.append("")

        if epistemic_notes:
            lines.append(f"> [!NOTE]\n> **Epistemic Grounding**: {epistemic_notes}")
            lines.append("")

        lines.append("<!-- intellectual-rigour:end -->")
        return "\n".join(lines)
