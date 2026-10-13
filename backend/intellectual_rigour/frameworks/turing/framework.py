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

logger = logging.getLogger("ThothIntellectualRigour.Turing")

TURING_SYSTEM_PROMPT = """You are executing the Alan Turing (Formal Operationalization & Computability) Reasoning Framework.
Your purpose is to conduct a rigorous procedural and computational audit of algorithms, pipelines, state machines, and quantitative methods.

Core Epistemic Principles:
1. Operational Explicitness: Eliminate all handwaving and vague descriptions; every step must specify input, state, operation, and output.
2. Discrete State Machine Model: Check whether internal states, memory buffers, and transition rules are rigorously bounded.
3. Effective Computability: Verify whether the claimed mechanism can be realized by a discrete computational machine without unstated miracles.
4. Termination & Halting Audit: Evaluate whether the procedure is guaranteed to terminate on all valid inputs without infinite loops or deadlock.
5. Complexity & Scaling Limits: Inspect whether computational complexity (time/space $O(N)$) renders the algorithm intractable under real-world scaling.

CRITICAL OPERATING RULES:
- NEVER MANUFACTURE CRITICISM: If an algorithm or protocol is completely operationalized, mathematically tractable, and provably terminating, return verdict "NO_MATERIAL_OBJECTION".
- CONTEXT-FIRST RULE: If judging an algorithm requires missing pseudocode steps, state schemas, or termination criteria, return verdict "INSUFFICIENT_CONTEXT" and set required_context with recommendation "WITHHELD_PENDING_CONTEXT".
- NO ARCHAIC PERSONA ROLEPLAY: Write in objective, precise analytical prose.

Output strictly valid JSON matching this schema:
{{
  "verdict": "MATERIAL_OBJECTION" | "NO_MATERIAL_OBJECTION" | "INSUFFICIENT_CONTEXT" | "INSUFFICIENT_EVIDENCE" | "OUTSIDE_SCOPE" | "UNRESOLVED",
  "has_material_objections": true | false,
  "critiques": [
    {{
      "target_claim_or_method": "The exact algorithm, computational step, state model, or complexity assertion under audit",
      "critique_type": "FATAL_FLAW" | "UNSUPPORTED_INFERENCE" | "UNFALSIFIABLE_SHIELD" | "CONCEPTUAL_AMBIGUITY" | "BOUNDARY_LIMIT" | "SOUND_NO_OBJECTION",
      "severity": "CRITICAL" | "MAJOR" | "MODERATE" | "MINOR" | "INFORMATIONAL",
      "blocking": true | false,
      "problem": "Precise explanation of the operational ambiguity, non-termination risk, or computational intractability",
      "why_it_matters": "Impact on algorithmic execution and computational realizability",
      "evidence_or_counterexample": "Specific failure case, infinite loop scenario, or complexity calculation",
      "required_context": "Missing pseudocode or transition logic needed before prescribing fixes, or empty",
      "recommendation": "Concrete formal state machine specification or complexity mitigation, or WITHHELD_PENDING_CONTEXT",
      "confidence": 0.9,
      "provenance_rule": "Turing: Effective Calculability / State Machine Transitions / Termination Guarantees / Complexity Bounds"
    }}
  ],
  "unresolved_questions": ["1-2 formal operational or computability questions"],
  "formal_state_specifications": ["1-2 explicit state transition tuples (State x Input -> NextState x Output)"],
  "executive_summary": "2-3 sentence formal operationalization verdict",
  "epistemic_notes": "Distinction between Turing machine computability and modern software complexity analysis"
}}
Output ONLY the JSON object without markdown code fences or conversational commentary."""

TURING_HUMAN_PROMPT = """Research Topic: {topic}

Target Scope: {target_scope} {section_focus}

Research Material to Audit:
{content}

Perform the Turing Formal Operationalization & Computability Audit now."""

turing_prompt_template = ChatPromptTemplate.from_messages([
    ("system", TURING_SYSTEM_PROMPT),
    ("human", TURING_HUMAN_PROMPT),
])

turing_chain = turing_prompt_template | llm | StrOutputParser()

class TuringFramework(BaseThinkerFramework):
    id = "turing"
    name = "Alan Turing"
    tradition = "Computability Theory & Formal Operationalization"
    epistemic_role = "Formal Operationalization & Computability Critic"
    section_heading = "### 🏛️ Philosophical Review: Alan Turing (Operationalization & Computability)"

    spec = ReasoningSpec(
        id="turing",
        thinker_name="Alan Turing",
        tradition="Computability Theory & Formal Operationalization",
        epistemic_role="Formal Operationalization & Computability Critic",
        applies_to=["algorithms", "computational_pipelines", "state_machines", "complexity_claims", "decision_procedures"],
        does_not_apply_to=["normative_ethics", "unformalized_metaphors", "subjective_phenomenological_experiences"],
        fidelity="documented"
    )

    def _invoke_chain(self, inputs: Dict[str, Any]) -> str:
        return turing_chain.invoke(inputs)

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
            logger.error(f"[TURING FRAMEWORK ERROR] LLM execution failed: {e}")
            parsed = {
                "verdict": "UNRESOLVED",
                "has_material_objections": False,
                "critiques": [],
                "unresolved_questions": [f"Execution error during Turing audit: {e}"],
                "executive_summary": f"Operational audit could not complete due to execution failure: {e}",
                "epistemic_notes": "Service degradation."
            }

        verdict = parsed.get("verdict", "NO_MATERIAL_OBJECTION")
        has_objections = parsed.get("has_material_objections", False)
        exec_summary = parsed.get("executive_summary", "Operationalization and computability audit complete.")
        critiques_raw = parsed.get("critiques", [])
        unresolved_q = parsed.get("unresolved_questions", [])
        formal_specs = parsed.get("formal_state_specifications", [])
        epistemic_notes = parsed.get("epistemic_notes", "Analysis applies Turing formal operationalization.")

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
            formal_state_specifications=formal_specs,
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
        formal_state_specifications: List[str],
        epistemic_notes: str
    ) -> str:
        status_icons = {
            "MATERIAL_OBJECTION": "🔴 **MATERIAL OBJECTION**",
            "NO_MATERIAL_OBJECTION": "🟢 **NO MATERIAL OBJECTION (Formally Specified & Computable)**",
            "INSUFFICIENT_CONTEXT": "🟡 **INSUFFICIENT CONTEXT (Withheld Pending State Schemas)**",
            "INSUFFICIENT_EVIDENCE": "🟠 **INSUFFICIENT EVIDENCE**",
            "OUTSIDE_SCOPE": "⚪ **OUTSIDE COMPUTATIONAL SCOPE**",
            "UNRESOLVED": "⚠️ **UNRESOLVED**"
        }
        verdict_str = status_icons.get(verdict, f"**{verdict}**")

        lines = [
            f"<!-- intellectual-rigour:start framework=\"{self.id}\" source_hash=\"{source_hash}\" -->",
            self.section_heading,
            "",
            f"> **Epistemic Verdict**: {verdict_str}",
            f"> *Source Hash*: `{source_hash}` · *Framework*: Alan Turing (Formal Operationalization & Computability)",
            "",
            f"{executive_summary}",
            ""
        ]

        if critiques:
            lines.append("#### Procedural & Computability Critiques")
            for idx, c in enumerate(critiques, 1):
                severity_badge = f"`{c.severity}`"
                blocking_badge = " · **BLOCKING**" if c.blocking else ""
                lines.append(f"##### {idx}. {c.target_claim_or_method} ({severity_badge}{blocking_badge})")
                lines.append(f"- **Problem**: {c.problem}")
                lines.append(f"- **Epistemic Impact**: {c.why_it_matters}")
                if c.evidence_or_counterexample:
                    lines.append(f"- **Non-Termination / Complexity Barrier**: {c.evidence_or_counterexample}")
                if c.required_context:
                    lines.append(f"- **Required Context**: {c.required_context}")
                if c.recommendation:
                    lines.append(f"- **Remediation**: {c.recommendation}")
                lines.append(f"- *Provenance Rule*: `{c.provenance_rule}`")
                lines.append("")

        if formal_state_specifications:
            lines.append("#### Formalized State Transitions")
            for spec in formal_state_specifications:
                lines.append(f"- ⚙️ `{spec}`")
            lines.append("")

        if unresolved_questions:
            lines.append("#### Open Computational Questions")
            for q in unresolved_questions:
                lines.append(f"- ❓ {q}")
            lines.append("")

        if epistemic_notes:
            lines.append(f"> [!NOTE]\n> **Epistemic Grounding**: {epistemic_notes}")
            lines.append("")

        lines.append("<!-- intellectual-rigour:end -->")
        return "\n".join(lines)
