"""
THOTH Server-Side Binary PDF Compilation Engine
Phase 6 — Deliverable A: Advanced PDF Compilation & Publication Pipeline.

Supports dual rendering pipelines:
1. LaTeX compilation (`pdflatex`/`xelatex`) with bibliography and mathematics.
2. Pure-Python ReportLab rendering for self-contained, dependency-free academic PDF publication.

Includes strict binary validation (%PDF- bytes, pypdf page count), temporary directory isolation,
argument-array subprocess execution, and comprehensive compilation error diagnostics.
"""

from __future__ import annotations

import datetime
import hashlib
import io
import os
import shutil
import subprocess
import tempfile
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

import pypdf

from backend.core.logging import get_logger

logger = get_logger("PDFCompiler")


class PDFEngine(str, Enum):
    AUTO = "auto"
    LATEX = "latex"
    PDFLATEX = "pdflatex"
    REPORTLAB = "reportlab"


class PDFCompilerError(Exception):
    """Base exception for PDF compilation failures."""
    def __init__(self, message: str, stage: str = "compilation", details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.stage = stage
        self.details = details or {}


class MissingEngineError(PDFCompilerError):
    """Raised when the requested PDF compiler binary or library is not installed."""
    def __init__(self, message: str, engine: str):
        super().__init__(message, stage="engine_detection", details={"engine": engine})
        self.engine = engine


class CompilationTimeoutError(PDFCompilerError):
    """Raised when PDF compilation exceeds the time budget."""
    def __init__(self, message: str, timeout_seconds: float):
        super().__init__(message, stage="execution", details={"timeout_seconds": timeout_seconds})
        self.timeout_seconds = timeout_seconds


class InvalidPDFOutputError(PDFCompilerError):
    """Raised when the compilation output is empty, malformed, or invalid PDF binary."""
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message, stage="validation", details=details or {})


def find_latex_executable(binary_name: str = "pdflatex") -> Optional[str]:
    """
    Locates the LaTeX executable safely without shell invocation.
    Searches standard PATH and common TeX distributions (TeXLive, MacTeX).
    """
    standard = shutil.which(binary_name)
    if standard and os.path.isfile(standard) and os.access(standard, os.X_OK):
        return standard

    candidates = [
        f"/opt/homebrew/bin/{binary_name}",
        f"/usr/local/bin/{binary_name}",
        f"/Library/TeX/texbin/{binary_name}",
        f"/usr/bin/{binary_name}",
    ]
    for path in candidates:
        if os.path.isfile(path) and os.access(path, os.X_OK):
            return path
    return None


def validate_pdf_bytes(pdf_bytes: bytes) -> Tuple[bool, int, Dict[str, Any]]:
    """
    Validates that the output is non-empty, contains valid %PDF- magic bytes,
    and can be parsed by pypdf to determine page count.
    """
    if not pdf_bytes:
        raise InvalidPDFOutputError("Compiled PDF output is empty (0 bytes).")

    if not pdf_bytes.startswith(b"%PDF-"):
        raise InvalidPDFOutputError(
            "Compiled file missing '%PDF-' header signature.",
            details={"prefix_bytes": str(pdf_bytes[:16])}
        )

    try:
        reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
        page_count = len(reader.pages)
        if page_count < 1:
            raise InvalidPDFOutputError("Compiled PDF contains 0 pages.")
        return True, page_count, {"is_encrypted": reader.is_encrypted}
    except Exception as e:
        if isinstance(e, InvalidPDFOutputError):
            raise
        raise InvalidPDFOutputError(f"Failed to parse PDF binary structure: {e}") from e


def compile_latex_to_pdf(
    latex_source: str,
    timeout_seconds: float = 30.0,
    latex_engine: str = "pdflatex",
) -> Tuple[bytes, Dict[str, Any]]:
    """
    Compiles a LaTeX document string into binary PDF using pdflatex or xelatex.
    Enforces isolated temporary working directory and safe argument arrays.
    """
    exe_path = find_latex_executable(latex_engine)
    if not exe_path:
        raise MissingEngineError(
            f"LaTeX engine '{latex_engine}' is not available on this system. "
            "Install MacTeX, TeXLive, or use engine='reportlab'.",
            engine=latex_engine,
        )

    with tempfile.TemporaryDirectory(prefix="thoth_latex_") as tmpdir:
        tex_path = os.path.join(tmpdir, "document.tex")
        with open(tex_path, "w", encoding="utf-8") as f:
            f.write(latex_source)

        cmd = [
            exe_path,
            "-interaction=nonstopmode",
            "-halt-on-error",
            f"-output-directory={tmpdir}",
            tex_path,
        ]

        start_time = datetime.datetime.now(datetime.timezone.utc)
        try:
            # First pass
            proc = subprocess.run(
                cmd,
                cwd=tmpdir,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
            )
            # Second pass for cross-references / toc if first pass succeeds
            if proc.returncode == 0:
                proc = subprocess.run(
                    cmd,
                    cwd=tmpdir,
                    capture_output=True,
                    text=True,
                    timeout=timeout_seconds,
                )
        except subprocess.TimeoutExpired as e:
            raise CompilationTimeoutError(
                f"LaTeX compilation timed out after {timeout_seconds}s.",
                timeout_seconds=timeout_seconds,
            ) from e

        out_pdf_path = os.path.join(tmpdir, "document.pdf")
        if proc.returncode != 0 or not os.path.isfile(out_pdf_path):
            log_tail = proc.stdout[-1500:] if proc.stdout else proc.stderr[-1500:]
            raise PDFCompilerError(
                f"LaTeX compilation failed with exit code {proc.returncode}.\nDiagnostics:\n{log_tail}",
                stage="latex_compilation",
                details={"exit_code": proc.returncode, "stdout_tail": log_tail},
            )

        with open(out_pdf_path, "rb") as f:
            pdf_bytes = f.read()

        is_valid, page_count, val_meta = validate_pdf_bytes(pdf_bytes)
        duration_ms = (datetime.datetime.now(datetime.timezone.utc) - start_time).total_seconds() * 1000

        meta = {
            "engine": latex_engine,
            "engine_path": exe_path,
            "page_count": page_count,
            "file_size_bytes": len(pdf_bytes),
            "sha256": hashlib.sha256(pdf_bytes).hexdigest(),
            "compilation_duration_ms": round(duration_ms, 2),
            **val_meta,
        }
        return pdf_bytes, meta


def compile_reportlab_to_pdf(revision: Dict[str, Any]) -> Tuple[bytes, Dict[str, Any]]:
    """
    Renders publication-ready PDF using pure-Python ReportLab library.
    Generates article structure: Title, metadata, sections, tables, and bibliography.
    """
    try:
        from reportlab.lib.colors import HexColor
        from reportlab.lib.pagesizes import letter
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import inch
        from reportlab.platypus import (
            HRFlowable,
            KeepTogether,
            PageBreak,
            Paragraph,
            SimpleDocTemplate,
            Spacer,
            Table,
            TableStyle,
        )
    except ImportError as e:
        raise MissingEngineError("ReportLab is not installed in current environment.", engine="reportlab") from e

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        leftMargin=0.75 * inch,
        rightMargin=0.75 * inch,
        topMargin=0.75 * inch,
        bottomMargin=0.75 * inch,
    )

    styles = getSampleStyleSheet()

    # Custom academic typography styles
    primary_color = HexColor("#1A365D")   # Deep navy
    neutral_dark = HexColor("#2D3748")    # Charcoal body
    accent_color = HexColor("#2B6CB0")    # Blue
    light_bg = HexColor("#F7FAFC")        # Warm subtle off-white
    border_color = HexColor("#E2E8F0")

    title_style = ParagraphStyle(
        "ManuscriptTitle",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=20,
        leading=24,
        textColor=primary_color,
        spaceAfter=10,
    )

    subtitle_style = ParagraphStyle(
        "ManuscriptSubtitle",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=10,
        leading=14,
        textColor=HexColor("#718096"),
        spaceAfter=15,
    )

    h1_style = ParagraphStyle(
        "ManuscriptH1",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=13,
        leading=17,
        textColor=primary_color,
        spaceBefore=14,
        spaceAfter=6,
        keepWithNext=True,
    )

    h2_style = ParagraphStyle(
        "ManuscriptH2",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=11,
        leading=15,
        textColor=accent_color,
        spaceBefore=10,
        spaceAfter=4,
        keepWithNext=True,
    )

    body_style = ParagraphStyle(
        "ManuscriptBody",
        parent=styles["Normal"],
        fontName="Times-Roman",
        fontSize=10,
        leading=14,
        textColor=neutral_dark,
        spaceAfter=8,
    )

    abstract_style = ParagraphStyle(
        "ManuscriptAbstract",
        parent=styles["Normal"],
        fontName="Times-Italic",
        fontSize=9.5,
        leading=13.5,
        textColor=HexColor("#4A5568"),
        leftIndent=15,
        rightIndent=15,
        spaceAfter=10,
    )

    table_cell_style = ParagraphStyle(
        "TableCell",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8.5,
        leading=11,
        textColor=neutral_dark,
    )

    table_header_style = ParagraphStyle(
        "TableHeader",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=8.5,
        leading=11,
        textColor=HexColor("#FFFFFF"),
    )

    story = []

    # Title & Metadata
    title = revision.get("title") or "Research Manuscript"
    story.append(Paragraph(title, title_style))

    version = revision.get("version", 1)
    created_at = revision.get("created_at") or datetime.datetime.now(datetime.timezone.utc).isoformat()
    meta_line = f"Revision v{version} &bull; Generated: {created_at[:10]} &bull; THOTH Research Workspace"
    story.append(Paragraph(meta_line, subtitle_style))
    story.append(HRFlowable(width="100%", thickness=1, color=border_color, spaceAfter=12))

    # Author notes / Context
    if revision.get("author_notes"):
        story.append(Paragraph("<b>Revision Notes:</b> " + str(revision["author_notes"]), subtitle_style))

    # Abstract Section
    sections = revision.get("sections") or {}
    if "abstract" in sections and sections["abstract"]:
        story.append(Paragraph("Abstract", h1_style))
        story.append(Paragraph(str(sections["abstract"]), abstract_style))
        story.append(Spacer(1, 8))

    # Body Sections
    section_order = ["introduction", "background", "methods", "results", "evidence_synthesis", "discussion", "limitations", "conclusion"]
    # Also include any custom section keys not in standard order
    other_keys = [k for k in sections.keys() if k.lower() not in section_order and k.lower() != "abstract"]
    full_order = section_order + other_keys

    for sec_key in full_order:
        sec_content = sections.get(sec_key)
        if not sec_content:
            continue
        heading_title = sec_key.replace("_", " ").title()
        story.append(Paragraph(heading_title, h1_style))
        # Handle string or paragraphs
        if isinstance(sec_content, list):
            for para in sec_content:
                story.append(Paragraph(str(para), body_style))
        else:
            paragraphs = str(sec_content).split("\n\n")
            for para in paragraphs:
                if para.strip():
                    story.append(Paragraph(para.strip(), body_style))
        story.append(Spacer(1, 6))

    # Evidence Matrix Table (if available)
    evidence_matrix = revision.get("evidence_matrix") or {}
    studies = evidence_matrix.get("studies") or []
    if studies:
        story.append(KeepTogether([
            Paragraph("Synthesized Evidence Matrix", h1_style),
            Paragraph("Appraised empirical investigations supporting or qualifying claims in this manuscript.", subtitle_style),
        ]))
        table_data = [[
            Paragraph("Study / Citation", table_header_style),
            Paragraph("Design", table_header_style),
            Paragraph("Sample / Dataset", table_header_style),
            Paragraph("Stance", table_header_style),
            Paragraph("Key Findings", table_header_style),
        ]]
        for s in studies[:15]: # Display up to 15 key studies
            title_s = s.get("title", "Untitled")[:40]
            authors_s = ", ".join(s.get("authors", [])[:2]) or "Unknown"
            cite_str = f"<b>{title_s}</b><br/><i>{authors_s}</i>"
            design_str = str(s.get("study_design", "empirical"))
            sample_str = str(s.get("sample_or_dataset", "N/A"))[:25]
            stance_str = str(s.get("hypothesis_relation", "NEUTRAL"))
            findings_str = "; ".join(s.get("key_findings", []))[:60] or "Synthesized finding"

            table_data.append([
                Paragraph(cite_str, table_cell_style),
                Paragraph(design_str, table_cell_style),
                Paragraph(sample_str, table_cell_style),
                Paragraph(f"<code>{stance_str}</code>", table_cell_style),
                Paragraph(findings_str, table_cell_style),
            ])

        col_widths = [1.8 * inch, 1.1 * inch, 1.2 * inch, 0.9 * inch, 2.0 * inch]
        t = Table(table_data, colWidths=col_widths, repeatRows=1)
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), primary_color),
            ("TEXTCOLOR", (0, 0), (-1, 0), HexColor("#FFFFFF")),
            ("ALIGN", (0, 0), (-1, -1), "LEFT"),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [light_bg, HexColor("#FFFFFF")]),
            ("GRID", (0, 0), (-1, -1), 0.5, border_color),
        ]))
        story.append(t)
        story.append(Spacer(1, 10))

    # Claims & Dialectic Status
    claims = revision.get("claims") or []
    if claims:
        story.append(Paragraph("Evaluated Claims & Evidence Grounding", h1_style))
        for c in claims:
            c_text = c.get("claim_text") or ""
            c_status = c.get("evidence_status") or "UNVERIFIED"
            c_conf = c.get("confidence", 0.0)
            status_color = "#276749" if c_status == "SUPPORTED" else ("#C53030" if c_status == "CHALLENGED" else "#B7791F")
            claim_html = f"&bull; <b>[{c_status}]</b> (Conf: {c_conf:.2f}): {c_text}"
            story.append(Paragraph(claim_html, body_style))
        story.append(Spacer(1, 6))

    # References / Bibliography
    references = revision.get("references") or []
    if references:
        story.append(Paragraph("References", h1_style))
        for i, ref in enumerate(references, 1):
            ref_title = ref.get("title") or "Untitled Source"
            ref_authors = ", ".join(ref.get("authors") or []) or "Unknown Authors"
            ref_year = ref.get("published_year") or ref.get("year") or ""
            year_str = f" ({ref_year})" if ref_year else ""
            ref_doi = f" DOI: {ref['doi']}" if ref.get("doi") else ""
            ref_entry = f"[{i}] {ref_authors}{year_str}. <i>{ref_title}</i>.{ref_doi}"
            story.append(Paragraph(ref_entry, body_style))

    # Build document
    start_time = datetime.datetime.now(datetime.timezone.utc)
    doc.build(story)
    pdf_bytes = buffer.getvalue()

    is_valid, page_count, val_meta = validate_pdf_bytes(pdf_bytes)
    duration_ms = (datetime.datetime.now(datetime.timezone.utc) - start_time).total_seconds() * 1000

    meta = {
        "engine": "reportlab",
        "page_count": page_count,
        "file_size_bytes": len(pdf_bytes),
        "sha256": hashlib.sha256(pdf_bytes).hexdigest(),
        "compilation_duration_ms": round(duration_ms, 2),
        **val_meta,
    }
    return pdf_bytes, meta


def compile_manuscript_to_pdf(
    revision: Dict[str, Any],
    engine: str = "auto",
    latex_source: Optional[str] = None,
    output_path: Optional[str] = None,
) -> Tuple[bytes, Dict[str, Any]]:
    """
    Main entry point for server-side binary PDF compilation.
    Resolves requested engine, executes compilation, validates binary output,
    and optionally writes to an output path.
    """
    selected_engine = engine.lower()

    if selected_engine in ("latex", "pdflatex"):
        if not latex_source:
            from backend.workspace.exporter import export_to_latex
            latex_source, _ = export_to_latex(revision)
        pdf_bytes, meta = compile_latex_to_pdf(latex_source, latex_engine="pdflatex")

    elif selected_engine == "reportlab":
        pdf_bytes, meta = compile_reportlab_to_pdf(revision)

    elif selected_engine in ("auto", "default"):
        # Auto mode: try pdflatex if available, fallback to ReportLab
        pdflatex_exe = find_latex_executable("pdflatex")
        if pdflatex_exe:
            try:
                if not latex_source:
                    from backend.workspace.exporter import export_to_latex
                    latex_source, _ = export_to_latex(revision)
                pdf_bytes, meta = compile_latex_to_pdf(latex_source, latex_engine="pdflatex")
            except Exception as e:
                logger.warning(f"LaTeX auto-compilation failed ({e}); falling back to ReportLab.")
                pdf_bytes, meta = compile_reportlab_to_pdf(revision)
                meta["fallback_from"] = "pdflatex"
                meta["fallback_reason"] = str(e)
        else:
            pdf_bytes, meta = compile_reportlab_to_pdf(revision)

    else:
        raise MissingEngineError(f"Unsupported PDF engine '{engine}'. Must be 'auto', 'latex', or 'reportlab'.", engine=engine)

    if output_path:
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        with open(output_path, "wb") as f:
            f.write(pdf_bytes)
        meta["output_path"] = output_path

    return pdf_bytes, meta
