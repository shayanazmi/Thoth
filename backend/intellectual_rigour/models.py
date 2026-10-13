from typing import List, Dict, Any, Optional, Literal
from pydantic import BaseModel, Field

class ReviewTarget(BaseModel):
    scope: Literal["WHOLE_REPORT", "SECTION", "CLAIM"] = "WHOLE_REPORT"
    section_title: Optional[str] = None
    claim_text: Optional[str] = None

class ReviewRequest(BaseModel):
    query: str
    target: ReviewTarget = Field(default_factory=ReviewTarget)
    force_reevaluation: bool = False
    additional_context: Dict[str, Any] = Field(default_factory=dict)

class CritiqueFinding(BaseModel):
    target_claim_or_method: str = Field(description="The specific claim, inference, or method inspected.")
    critique_type: Literal[
        "FATAL_FLAW",
        "UNSUPPORTED_INFERENCE",
        "UNFALSIFIABLE_SHIELD",
        "CONCEPTUAL_AMBIGUITY",
        "BOUNDARY_LIMIT",
        "SOUND_NO_OBJECTION",
    ] = "SOUND_NO_OBJECTION"
    severity: Literal["CRITICAL", "MAJOR", "MODERATE", "MINOR", "INFORMATIONAL"] = "MODERATE"
    blocking: bool = Field(default=False, description="True if the objection invalidates core conclusions.")
    problem: str = Field(description="Clear explanation of the detected problem or sound condition.")
    why_it_matters: str = Field(description="Epistemic impact on conclusion reliability.")
    evidence_or_counterexample: str = Field(default="", description="Specific citation, contradiction, or counterexample.")
    required_context: str = Field(default="", description="Missing information required before prescribing solutions.")
    recommendation: str = Field(default="WITHHELD_PENDING_CONTEXT", description="Concrete actionable remedy, or WITHHELD if context is missing.")
    confidence: float = Field(default=0.85, ge=0.0, le=1.0)
    provenance_rule: str = Field(description="The formal reasoning rule applied (e.g. Popper: Risky Predictions).")

class ThinkerOutput(BaseModel):
    framework_id: str
    thinker_name: str
    verdict: Literal[
        "MATERIAL_OBJECTION",
        "NO_MATERIAL_OBJECTION",
        "INSUFFICIENT_CONTEXT",
        "INSUFFICIENT_EVIDENCE",
        "OUTSIDE_SCOPE",
        "UNRESOLVED",
    ]
    has_material_objections: bool = False
    critiques: List[CritiqueFinding] = Field(default_factory=list)
    unresolved_questions: List[str] = Field(default_factory=list)
    confidence: float = Field(default=0.9, ge=0.0, le=1.0)
    formatted_markdown_section: str = Field(description="The complete render-ready markdown section.")
    source_hash: str = Field(description="Deterministic 12-char SHA-256 hash of the target source text.")
    epistemic_notes: str = Field(default="", description="Distinction between historical doctrine and modern adaptation.")

class ReviewArtifact(BaseModel):
    framework_id: str
    target_section_title: str
    operation: Literal["append_section", "replace_section", "create_standalone_doc"] = "append_section"
    formatted_markdown: str
    source_hash: str
    metadata: Dict[str, Any] = Field(default_factory=dict)

class ReasoningSpec(BaseModel):
    id: str
    thinker_name: str
    tradition: str
    epistemic_role: str
    applies_to: List[str]
    does_not_apply_to: List[str]
    fidelity: Literal["documented", "strongly_reconstructed", "modern_adaptation"]
