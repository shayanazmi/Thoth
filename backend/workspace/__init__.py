"""
THOTH Workspace Package
Phase 5: Persistent Research Workspace & Manuscript Engine
"""

from backend.workspace.project import (
    ResearchProject,
    ProjectWorkspace,
    create_project,
    get_project,
    list_projects,
    associate_artifact,
    load_project_workspace,
)

from backend.workspace.manuscript import (
    Manuscript,
    ManuscriptRevision,
    ManuscriptClaim,
    create_manuscript,
    create_manuscript_from_brief_and_review,
    save_manuscript_revision,
    get_manuscript,
    get_manuscript_revision,
    list_manuscripts,
    list_manuscript_revisions,
    propose_claim_qualifications_from_evidence,
)

from backend.workspace.exporter import (
    ExportFormat,
    ExportResult,
    export_manuscript,
    export_to_markdown,
    export_to_latex,
    export_to_bibtex,
    export_to_html,
)

from backend.workspace.traceability import (
    StudyDetail,
    DrillDownResult,
    drill_down_study_record,
    get_claim_traceability,
    get_flow_node_records,
)

__all__ = [
    "ResearchProject",
    "ProjectWorkspace",
    "create_project",
    "get_project",
    "list_projects",
    "associate_artifact",
    "load_project_workspace",
    "Manuscript",
    "ManuscriptRevision",
    "ManuscriptClaim",
    "create_manuscript",
    "create_manuscript_from_brief_and_review",
    "save_manuscript_revision",
    "get_manuscript",
    "get_manuscript_revision",
    "list_manuscripts",
    "list_manuscript_revisions",
    "propose_claim_qualifications_from_evidence",
    "ExportFormat",
    "ExportResult",
    "export_manuscript",
    "export_to_markdown",
    "export_to_latex",
    "export_to_bibtex",
    "export_to_html",
    "StudyDetail",
    "DrillDownResult",
    "drill_down_study_record",
    "get_claim_traceability",
    "get_flow_node_records",
]
