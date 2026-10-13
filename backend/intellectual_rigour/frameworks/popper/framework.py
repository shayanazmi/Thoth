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

logger = logging.getLogger("ThothIntellectualRigour.Popper")

POPPER_SYSTEM_PROMPT = """You are executing the Karl Popper (Critical Rationalism & Falsification) Reasoning Framework.
Your purpose is to conduct a rigorous, objective methodological audit of research claims, theories, and empirical methodologies.

Core Epistemic Principles:
1. Asymmetry of Falsification: No number of positive results can prove a general conjecture true, but one valid counterexample or failed prediction refutes it.
2. Demarcation & Falsifiability: A scientific claim must specify what observable empirical outcome would count against it.
3. Risky Predictions: Claims gain corroboration only by surviving severe, risky tests that could have failed.
4. Ad-Hoc Protective Immunization: Flag any attempt to explain away failures or shield claims through post-hoc excuses without increasing testable empirical content.
5. Corroboration vs Truth: Theories that withstand severe testing are tentatively corroborated, never proven as final truths.

CRITICAL OPERATING RULES:
- NEVER MANUFACTURE CRITICISM: If the research claims are clearly testable, backed by severe empirical controls, and free of ad-hoc shields, you MUST return verdict "NO_MATERIAL_OBJECTION" with an empty or SOUND critiques list.
- CONTEXT-FIRST RULE: If judging a claim requires unavailable raw datasets, ablation specifics, or baseline configurations, return verdict "INSUFFICIENT_CONTEXT" and set required_context. Set recommendation to "WITHHELD_PENDING_CONTEXT".
- NO ARCHAIC PERSONA ROLEPLAY: Write in objective, precise analytical prose.

Output strictly valid JSON matching this schema:
{{
  "verdict": "MATERIAL_OBJECTION" | "NO_MATERIAL_OBJECTION" | "INSUFFICIENT_CONTEXT" | "INSUFFICIENT_EVIDENCE" | "OUTSIDE_SCOPE" | "UNRESOLVED",
  "has_material_objections": true | false,
  "critiques": [
    {{
      "target_claim_or_method": "The exact claim or methodology under test",
      "critique_type": "FATAL_FLAW" | "UNSUPPORTED_INFERENCE" | "UNFALSIFIABLE_SHIELD" | "CONCEPTUAL_AMBIGUITY" | "BOUNDARY_LIMIT" | "SOUND_NO_OBJECTION",
      "severity": "CRITICAL" | "MAJOR" | "MODERATE" | "MINOR" | "INFORMATIONAL",
      "blocking": true | false,
      "problem": "Precise explanation of the falsifiability or methodological issue",
      "why_it_matters": "Impact on empirical reliability",
      "evidence_or_counterexample": "Contradictory literature/data or N/A",
      "required_context": "Missing empirical data needed before prescribing fixes, or empty",
      "recommendation": "Concrete actionable refutation test or WITHHELD_PENDING_CONTEXT",
      "confidence": 0.9,
      "provenance_rule": "Popper: Demarcation / Risky Predictions / Ad-Hoc Immunization"
    }}
  ],
  "unresolved_questions": ["1-2 critical refutation questions"],
  "potential_falsifying_experiments": ["1-2 concrete experiments that could refute the claims"],
  "executive_summary": "2-3 sentence methodological verdict",
  "epistemic_notes": "Distinction between historical doctrine and modern adaptation"
}}
Output ONLY the JSON object without markdown code fences or conversational commentary."""

POPPER_HUMAN_PROMPT = """Research Topic: {topic}

Target Scope: {target_scope} {section_focus}

Research Material to Audit:
{content}

Perform the Popperian Falsification Audit now."""

popper_prompt_template = ChatPromptTemplate.from_messages([
    ("system", POPPER_SYSTEM_PROMPT),
    ("human", POPPER_HUMAN_PROMPT),
])

popper_chain = popper_prompt_template | llm | StrOutputParser()

class PopperFramework(BaseThinkerFramework):
    id = "popper"
    name = "Karl Popper"
    tradition = "Critical Rationalism"
    epistemic_role = "Adversarial Falsification Critic"
    section_heading = "### 🏛️ Philosophical Review: Karl Popper (Critical Rationalism)"

    spec = ReasoningSpec(
        id="popper",
        thinker_name="Karl Popper",
        tradition="Critical Rationalism",
        epistemic_role="Adversarial Falsification Critic",
        applies_to=["empirical_hypotheses", "scientific_theories", "causal_claims", "quantitative_models", "methodology"],
        does_not_apply_to=["purely_normative_ethics", "tautological_definitions", "mathematical_axioms"],
        fidelity="documented"
    )

    def _invoke_chain(self, inputs: Dict[str, Any]) -> str:
        return popper_chain.invoke(inputs)

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
            logger.error(f"[POPPER FRAMEWORK ERROR] LLM execution failed: {e}")
            parsed = {
                "verdict": "UNRESOLVED",
                "has_material_objections": False,
                "critiques": [],
                "unresolved_questions": [f"Execution error during falsification audit: {e}"],
                "executive_summary": f"Falsification audit could not complete due to execution failure: {e}",
                "epistemic_notes": "Service degradation."
            }

        verdict = parsed.get("verdict", "NO_MATERIAL_OBJECTION")
        has_objections = parsed.get("has_material_objections", False)
        exec_summary = parsed.get("executive_summary", "Methodological audit complete.")
        critiques_raw = parsed.get("critiques", [])
        unresolved_q = parsed.get("unresolved_questions", [])
        potential_falsifiers = parsed.get("potential_falsifying_experiments", [])
        epistemic_notes = parsed.get("epistemic_notes", "Analysis applies Critical Rationalism principles.")

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
            potential_falsifiers=potential_falsifiers,
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
        potential_falsifiers: List[str],
        epistemic_notes: str
    ) -> str:
        status_icons = {
            "MATERIAL_OBJECTION": "🔴 **MATERIAL OBJECTION**",
            "NO_MATERIAL_OBJECTION": "🟢 **NO MATERIAL OBJECTION (Corroborated Under Tested Scope)**",
            "INSUFFICIENT_CONTEXT": "🟡 **INSUFFICIENT CONTEXT (Withheld Pending Data)**",
            "INSUFFICIENT_EVIDENCE": "🟠 **INSUFFICIENT EVIDENCE**",
            "OUTSIDE_SCOPE": "⚪ **OUTSIDE EMPIRICAL SCOPE**",
            "UNRESOLVED": "⚠️ **UNRESOLVED**"
        }
        verdict_str = status_icons.get(verdict, f"**{verdict}**")

        lines = [
            f"<!-- intellectual-rigour:start framework=\"{self.id}\" source_hash=\"{source_hash}\" -->",
            self.section_heading,
            "",
            f"> **Methodological Verdict**: {verdict_str}",
            f"> *Source Hash*: `{source_hash}` · *Framework*: Karl Popper (Falsification & Critical Rationalism)",
            "",
            f"{executive_summary}",
            ""
        ]

        if critiques:
            lines.append("#### Falsification Audit & Critique Findings")
            for idx, c in enumerate(critiques, 1):
                severity_badge = f"`{c.severity}`"
                blocking_badge = " · **BLOCKING**" if c.blocking else ""
                lines.append(f"##### {idx}. {c.target_claim_or_method} ({severity_badge}{blocking_badge})")
                lines.append(f"- **Problem**: {c.problem}")
                lines.append(f"- **Epistemic Impact**: {c.why_it_matters}")
                if c.evidence_or_counterexample:
                    lines.append(f"- **Contradictory Evidence / Counterexample**: {c.evidence_or_counterexample}")
                if c.required_context:
                    lines.append(f"- **Required Context**: {c.required_context}")
                if c.recommendation:
                    lines.append(f"- **Proposed Refutation Test**: {c.recommendation}")
                lines.append(f"- *Provenance Rule*: `{c.provenance_rule}`")
                lines.append("")

        if potential_falsifiers:
            lines.append("#### Decisive Refutation Experiments")
            for exp in potential_falsifiers:
                lines.append(f"- 🧪 {exp}")
            lines.append("")

        if unresolved_questions:
            lines.append("#### Open Critical Questions")
            for q in unresolved_questions:
                lines.append(f"- ❓ {q}")
            lines.append("")

        if epistemic_notes:
            lines.append(f"> [!NOTE]\n> **Epistemic Grounding**: {epistemic_notes}")
            lines.append("")

        lines.append("<!-- intellectual-rigour:end -->")
        return "\n".join(lines)
