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

logger = logging.getLogger("ThothIntellectualRigour.Aristotle")

ARISTOTLE_SYSTEM_PROMPT = """You are executing the Aristotle (Categorical Inquiry, Logic & Explanatory Causes) Reasoning Framework.
Your purpose is to conduct a rigorous, objective conceptual and logical analysis of research claims and definitions.

Core Epistemic Principles:
1. Definition by Genus & Differentia: Central constructs must have unambiguous boundaries, clear parent categories, and explicit essential properties.
2. Category Rigour: Detect category errors, level mixing (e.g. micro vs macro), and false equivalence.
3. Deductive Syllogistic Validity: Major claims must follow necessarily from explicit premises without equivocation, hidden assumptions, or circularity.
4. Explanatory Adequacy (Four Causes): Verify whether the research accounts for material substrate, formal architecture, efficient mechanism, and functional objective.
5. Non-Contradiction: Contradictory assertions within assumptions, data, or conclusions invalidate theoretical soundness.

CRITICAL OPERATING RULES:
- NEVER MANUFACTURE CRITICISM: If concepts are clearly defined and inferences follow validly, return verdict "NO_MATERIAL_OBJECTION".
- CONTEXT-FIRST RULE: If judging an inference requires unstated baseline definitions or formal axioms missing from context, return verdict "INSUFFICIENT_CONTEXT" and set required_context with recommendation "WITHHELD_PENDING_CONTEXT".
- NO ARCHAIC PERSONA ROLEPLAY: Write in objective, precise analytical prose.

Output strictly valid JSON matching this schema:
{{
  "verdict": "MATERIAL_OBJECTION" | "NO_MATERIAL_OBJECTION" | "INSUFFICIENT_CONTEXT" | "INSUFFICIENT_EVIDENCE" | "OUTSIDE_SCOPE" | "UNRESOLVED",
  "has_material_objections": true | false,
  "critiques": [
    {{
      "target_claim_or_method": "The exact construct, definition, or deductive step under review",
      "critique_type": "FATAL_FLAW" | "UNSUPPORTED_INFERENCE" | "UNFALSIFIABLE_SHIELD" | "CONCEPTUAL_AMBIGUITY" | "BOUNDARY_LIMIT" | "SOUND_NO_OBJECTION",
      "severity": "CRITICAL" | "MAJOR" | "MODERATE" | "MINOR" | "INFORMATIONAL",
      "blocking": true | false,
      "problem": "Precise explanation of the category error, definitional ambiguity, or logical invalidity",
      "why_it_matters": "Impact on conceptual soundness and inference validity",
      "evidence_or_counterexample": "Contradictory premise or equivocation example",
      "required_context": "Missing axiomatic context needed before prescribing fixes, or empty",
      "recommendation": "Concrete formulation of genus/differentia or valid syllogism, or WITHHELD_PENDING_CONTEXT",
      "confidence": 0.9,
      "provenance_rule": "Aristotle: Genus-Differentia / Non-Contradiction / Syllogistic Validity / Four Causes"
    }}
  ],
  "unresolved_questions": ["1-2 fundamental definitional or ontological questions"],
  "clarified_definitions": ["1-2 clarified genus-differentia definitions"],
  "executive_summary": "2-3 sentence logical and conceptual verdict",
  "epistemic_notes": "Distinction between classical essentialism and modern ontology typing"
}}
Output ONLY the JSON object without markdown code fences or conversational commentary."""

ARISTOTLE_HUMAN_PROMPT = """Research Topic: {topic}

Target Scope: {target_scope} {section_focus}

Research Material to Audit:
{content}

Perform the Aristotelian Categorical & Logical Audit now."""

aristotle_prompt_template = ChatPromptTemplate.from_messages([
    ("system", ARISTOTLE_SYSTEM_PROMPT),
    ("human", ARISTOTLE_HUMAN_PROMPT),
])

aristotle_chain = aristotle_prompt_template | llm | StrOutputParser()

class AristotleFramework(BaseThinkerFramework):
    id = "aristotle"
    name = "Aristotle"
    tradition = "Classical Logic & Essentialist Categorization"
    epistemic_role = "Conceptual & Logical Structure Critic"
    section_heading = "### 🏛️ Philosophical Review: Aristotle (Categorical Logic & Causality)"

    spec = ReasoningSpec(
        id="aristotle",
        thinker_name="Aristotle",
        tradition="Classical Logic & Essentialist Categorization",
        epistemic_role="Conceptual & Logical Structure Critic",
        applies_to=["definitions", "theoretical_foundations", "taxonomies", "deductive_arguments", "explanatory_models"],
        does_not_apply_to=["unstructured_raw_data", "heuristic_statistical_noise", "purely_numerical_curve_fitting"],
        fidelity="documented"
    )

    def _invoke_chain(self, inputs: Dict[str, Any]) -> str:
        return aristotle_chain.invoke(inputs)

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
            logger.error(f"[ARISTOTLE FRAMEWORK ERROR] LLM execution failed: {e}")
            parsed = {
                "verdict": "UNRESOLVED",
                "has_material_objections": False,
                "critiques": [],
                "unresolved_questions": [f"Execution error during Aristotelian audit: {e}"],
                "executive_summary": f"Categorical audit could not complete due to execution failure: {e}",
                "epistemic_notes": "Service degradation."
            }

        verdict = parsed.get("verdict", "NO_MATERIAL_OBJECTION")
        has_objections = parsed.get("has_material_objections", False)
        exec_summary = parsed.get("executive_summary", "Logical and conceptual audit complete.")
        critiques_raw = parsed.get("critiques", [])
        unresolved_q = parsed.get("unresolved_questions", [])
        clarified_defs = parsed.get("clarified_definitions", [])
        epistemic_notes = parsed.get("epistemic_notes", "Analysis applies Aristotelian categorical logic.")

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
            clarified_definitions=clarified_defs,
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
        clarified_definitions: List[str],
        epistemic_notes: str
    ) -> str:
        status_icons = {
            "MATERIAL_OBJECTION": "🔴 **MATERIAL OBJECTION**",
            "NO_MATERIAL_OBJECTION": "🟢 **NO MATERIAL OBJECTION (Logically & Conceptually Sound)**",
            "INSUFFICIENT_CONTEXT": "🟡 **INSUFFICIENT CONTEXT (Withheld Pending Axiomatic Data)**",
            "INSUFFICIENT_EVIDENCE": "🟠 **INSUFFICIENT EVIDENCE**",
            "OUTSIDE_SCOPE": "⚪ **OUTSIDE CATEGORICAL SCOPE**",
            "UNRESOLVED": "⚠️ **UNRESOLVED**"
        }
        verdict_str = status_icons.get(verdict, f"**{verdict}**")

        lines = [
            f"<!-- intellectual-rigour:start framework=\"{self.id}\" source_hash=\"{source_hash}\" -->",
            self.section_heading,
            "",
            f"> **Epistemic Verdict**: {verdict_str}",
            f"> *Source Hash*: `{source_hash}` · *Framework*: Aristotle (Categorical Logic & Four Causes)",
            "",
            f"{executive_summary}",
            ""
        ]

        if critiques:
            lines.append("#### Categorical & Syllogistic Critiques")
            for idx, c in enumerate(critiques, 1):
                severity_badge = f"`{c.severity}`"
                blocking_badge = " · **BLOCKING**" if c.blocking else ""
                lines.append(f"##### {idx}. {c.target_claim_or_method} ({severity_badge}{blocking_badge})")
                lines.append(f"- **Problem**: {c.problem}")
                lines.append(f"- **Epistemic Impact**: {c.why_it_matters}")
                if c.evidence_or_counterexample:
                    lines.append(f"- **Counterexample / Equivocation**: {c.evidence_or_counterexample}")
                if c.required_context:
                    lines.append(f"- **Required Context**: {c.required_context}")
                if c.recommendation:
                    lines.append(f"- **Remediation**: {c.recommendation}")
                lines.append(f"- *Provenance Rule*: `{c.provenance_rule}`")
                lines.append("")

        if clarified_definitions:
            lines.append("#### Reconstructed Definitions (Genus & Differentia)")
            for d in clarified_definitions:
                lines.append(f"- 📐 {d}")
            lines.append("")

        if unresolved_questions:
            lines.append("#### Foundational Ontological Questions")
            for q in unresolved_questions:
                lines.append(f"- ❓ {q}")
            lines.append("")

        if epistemic_notes:
            lines.append(f"> [!NOTE]\n> **Epistemic Grounding**: {epistemic_notes}")
            lines.append("")

        lines.append("<!-- intellectual-rigour:end -->")
        return "\n".join(lines)
