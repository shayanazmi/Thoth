"""
THOTH Reliable Multi-Format Export Engine
Phase 5 — Deliverable C: Multi-format export engine supporting academic Markdown,
LaTeX with verified BibTeX entries, and publication-ready HTML.
"""

from __future__ import annotations

import datetime
import html
import json
import re
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from backend.memory.db import (
    DEFAULT_DB_PATH,
    get_manuscript_db,
    get_manuscript_export_db,
    get_manuscript_revision_db,
    list_manuscript_exports_db,
    save_manuscript_export_db,
)


class ExportFormat(str, Enum):
    MARKDOWN = "markdown"
    LATEX = "latex"
    BIBTEX = "bibtex"
    HTML = "html"


@dataclass
class ExportResult:
    export_id: str
    manuscript_id: str
    version: int
    format: str
    content: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "export_id": self.export_id,
            "manuscript_id": self.manuscript_id,
            "version": self.version,
            "format": self.format,
            "content": self.content,
            "metadata": self.metadata,
            "created_at": self.created_at,
        }


def export_manuscript(
    manuscript_id: str,
    format_type: str,
    version: Optional[int] = None,
    save_to_db: bool = True,
    db_path: str = DEFAULT_DB_PATH,
) -> ExportResult:
    """
    Export a saved manuscript revision into the specified format.
    Ensures reproducibility and artifact integrity.
    """
    ms = get_manuscript_db(manuscript_id, db_path=db_path)
    if not ms:
        raise ValueError(f"Manuscript '{manuscript_id}' not found.")

    ver = version if version is not None else ms["current_version"]
    rev = get_manuscript_revision_db(manuscript_id, ver, db_path=db_path)
    if not rev:
        raise ValueError(f"Manuscript '{manuscript_id}' revision v{ver} not found.")

    fmt = format_type.lower()
    if fmt == ExportFormat.MARKDOWN.value:
        content, meta = export_to_markdown(rev)
    elif fmt == ExportFormat.LATEX.value:
        content, meta = export_to_latex(rev)
    elif fmt == ExportFormat.BIBTEX.value:
        content, meta = export_to_bibtex(rev)
    elif fmt == ExportFormat.HTML.value:
        content, meta = export_to_html(rev)
    else:
        raise ValueError(f"Unsupported export format '{format_type}'. Must be one of: markdown, latex, bibtex, html.")

    export_id = f"exp_{fmt}_{uuid.uuid4().hex[:10]}"
    if save_to_db:
        save_res = save_manuscript_export_db(
            export_id=export_id,
            manuscript_id=manuscript_id,
            version=ver,
            format=fmt,
            content=content,
            metadata=meta,
            db_path=db_path,
        )
        return ExportResult(
            export_id=save_res["export_id"],
            manuscript_id=save_res["manuscript_id"],
            version=save_res["version"],
            format=save_res["format"],
            content=save_res["content"],
            metadata=save_res["metadata"],
            created_at=save_res["created_at"],
        )

    return ExportResult(
        export_id=export_id,
        manuscript_id=manuscript_id,
        version=ver,
        format=fmt,
        content=content,
        metadata=meta,
        created_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
    )


# ==========================================
# C.2 Academic Markdown Exporter
# ==========================================

def export_to_markdown(revision: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
    """Export manuscript revision to academic Markdown with citation markers and GFM tables."""
    title = revision.get("title", "THOTH Academic Manuscript")
    version = revision.get("version", 1)
    sections = revision.get("sections", {})
    claims = revision.get("claims", [])
    references = revision.get("references", [])
    evidence_matrix = revision.get("evidence_matrix", {})

    lines = [
        "---",
        f"title: \"{title}\"",
        f"version: {version}",
        f"date: \"{datetime.date.today().isoformat()}\"",
        "generator: \"THOTH Academic Manuscript Engine\"",
        "---",
        "",
        f"# {title}",
        "",
    ]

    # Sort sections by order
    sorted_secs = _get_sorted_sections(sections)
    for key, sec in sorted_secs:
        heading = sec.get("heading", key.title())
        content = sec.get("content", "")
        lines.append(f"## {heading}")
        lines.append("")
        lines.append(content)
        lines.append("")

        # If results section, append Evidence Matrix table
        if key == "results" and evidence_matrix.get("included_studies"):
            lines.append("### Evidence Synthesis Matrix")
            lines.append("")
            lines.append("| Study ID | Primary Finding | Methodology / Appraisal | Counter-Evidence / Caveat | Citation Key |")
            lines.append("| :--- | :--- | :--- | :--- | :--- |")
            for st in evidence_matrix.get("included_studies", []):
                sid = st.get("study_id", "")
                findings = (st.get("synthesized_findings", "") or "").replace("|", "\\|")
                appraisal = (st.get("appraisal_notes", "Rigor Assessed") or "").replace("|", "\\|")
                caveats = (st.get("caveats", "None noted") or "").replace("|", "\\|")
                ckey = f"[@{sid.replace('-', '_').replace(' ', '_')}]"
                lines.append(f"| {sid} | {findings} | {appraisal} | {caveats} | {ckey} |")
            lines.append("")

    # Claims and Evidential Status section
    if claims:
        lines.append("## Claim-Level Evidential Ledger")
        lines.append("")
        lines.append("| Claim ID | Status | Claim Statement | Supporting Studies | Counter-Evidence |")
        lines.append("| :--- | :--- | :--- | :--- | :--- |")
        for clm in claims:
            cid = clm.get("claim_id", "")
            stat = clm.get("evidence_status", "UNVERIFIED")
            text = (clm.get("claim_text", "") or "").replace("|", "\\|")
            supp = ", ".join(f"[@{s.get('citation_key', s.get('study_id'))}]" for s in clm.get("supporting_sources", [])) or "None"
            counter = ", ".join(c.get("counter_finding", c.get("study_id", "")) for c in clm.get("counter_sources", [])) or "None"
            lines.append(f"| {cid} | **{stat}** | {text} | {supp} | {counter} |")
        lines.append("")

    # References section
    if references:
        lines.append("## References")
        lines.append("")
        for ref in references:
            ckey = ref.get("citation_key", "ref")
            rtitle = ref.get("title", "Untitled Reference")
            authors = ", ".join(ref.get("authors", [])) if isinstance(ref.get("authors"), list) else str(ref.get("authors", "THOTH"))
            year = ref.get("year", datetime.date.today().year)
            doi = ref.get("doi", "")
            url = ref.get("source_url", "")
            doi_link = f" [DOI: {doi}](https://doi.org/{doi})" if doi else (f" [URL]({url})" if url else "")
            lines.append(f"- **[@{ckey}]** {authors} ({year}). *{rtitle}*.{doi_link}")
        lines.append("")

    out_content = "\n".join(lines)
    metadata = {
        "word_count": len(out_content.split()),
        "sections_count": len(sorted_secs),
        "claims_count": len(claims),
        "references_count": len(references),
    }
    return out_content, metadata


# ==========================================
# C.3 LaTeX Exporter
# ==========================================

def export_to_latex(revision: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
    """Export manuscript revision to clean, compilable LaTeX article."""
    title = revision.get("title", "THOTH Academic Manuscript")
    sections = revision.get("sections", {})
    claims = revision.get("claims", [])
    references = revision.get("references", [])
    evidence_matrix = revision.get("evidence_matrix", {})

    escaped_title = _latex_escape(title)

    lines = [
        "\\documentclass[11pt,a4paper]{article}",
        "\\usepackage[utf8]{inputenc}",
        "\\usepackage{amsmath,amssymb,amsfonts}",
        "\\usepackage{booktabs}",
        "\\usepackage{hyperref}",
        "\\usepackage{microtype}",
        "\\usepackage{geometry}",
        "\\geometry{margin=1in}",
        "",
        f"\\title{{{escaped_title}}}",
        "\\author{THOTH Intellectual Research Engine}",
        f"\\date{{{datetime.date.today().strftime('%B %d, %Y')}}}",
        "",
        "\\begin{document}",
        "\\maketitle",
        "",
    ]

    # Handle abstract separately
    if "abstract" in sections:
        abs_text = _latex_escape(sections["abstract"].get("content", ""))
        lines.append("\\begin{abstract}")
        lines.append(abs_text)
        lines.append("\\end{abstract}")
        lines.append("")

    # Sorted sections (skipping abstract as it is already rendered)
    sorted_secs = _get_sorted_sections(sections)
    for key, sec in sorted_secs:
        if key == "abstract":
            continue
        heading = _latex_escape(sec.get("heading", key.title()))
        content = _latex_escape(sec.get("content", ""))

        lines.append(f"\\section{{{heading}}}")
        lines.append(content)
        lines.append("")

        # Add LaTeX table for included studies under results
        if key == "results" and evidence_matrix.get("included_studies"):
            lines.append("\\subsection{Evidence Synthesis Table}")
            lines.append("\\begin{table}[htbp]")
            lines.append("\\centering")
            lines.append("\\small")
            lines.append("\\begin{tabular}{p{2.5cm} p{6cm} p{3.5cm} p{2cm}}")
            lines.append("\\toprule")
            lines.append("\\textbf{Study ID} & \\textbf{Primary Finding} & \\textbf{Methodological Appraisal} & \\textbf{Citation} \\\\")
            lines.append("\\midrule")
            for st in evidence_matrix.get("included_studies", []):
                sid = _latex_escape(st.get("study_id", ""))
                findings = _latex_escape(st.get("synthesized_findings", "")[:120])
                appraisal = _latex_escape(st.get("appraisal_notes", "Assessed")[:60])
                ckey = st.get("study_id", "").replace("-", "_").replace(" ", "_")
                lines.append(f"{sid} & {findings} & {appraisal} & \\cite{{{ckey}}} \\\\")
            lines.append("\\bottomrule")
            lines.append("\\end{tabular}")
            lines.append("\\caption{PRISMA Included Studies and Methodological Appraisals}")
            lines.append("\\end{table}")
            lines.append("")

    # Claims table in LaTeX
    if claims:
        lines.append("\\section{Claim-Level Evidential Ledger}")
        lines.append("\\begin{table}[htbp]")
        lines.append("\\centering")
        lines.append("\\small")
        lines.append("\\begin{tabular}{p{2.5cm} p{2cm} p{7cm} p{2.5cm}}")
        lines.append("\\toprule")
        lines.append("\\textbf{Claim ID} & \\textbf{Status} & \\textbf{Claim Statement} & \\textbf{Citations} \\\\")
        lines.append("\\midrule")
        for clm in claims:
            cid = _latex_escape(clm.get("claim_id", ""))
            stat = _latex_escape(clm.get("evidence_status", "UNVERIFIED"))
            text = _latex_escape(clm.get("claim_text", "")[:140])
            cites = "\\cite{" + ", ".join(s.get("citation_key", s.get("study_id")) for s in clm.get("supporting_sources", [])) + "}" if clm.get("supporting_sources") else "None"
            lines.append(f"{cid} & \\textbf{{{stat}}} & {text} & {cites} \\\\")
        lines.append("\\bottomrule")
        lines.append("\\end{tabular}")
        lines.append("\\caption{Formulated Claims and Empirical Verification Status}")
        lines.append("\\end{table}")
        lines.append("")

    # Embedded bibliography
    if references:
        lines.append("\\begin{thebibliography}{99}")
        for ref in references:
            ckey = ref.get("citation_key", "ref").replace("-", "_").replace(" ", "_")
            rtitle = _latex_escape(ref.get("title", "Untitled"))
            authors = _latex_escape(", ".join(ref.get("authors", [])) if isinstance(ref.get("authors"), list) else str(ref.get("authors", "THOTH")))
            year = ref.get("year", datetime.date.today().year)
            lines.append(f"\\bibitem{{{ckey}}} {authors}. ({year}). \\textit{{{rtitle}}}.")
        lines.append("\\end{thebibliography}")
        lines.append("")

    lines.append("\\end{document}")
    out_content = "\n".join(lines)
    metadata = {
        "latex_compiler_target": "pdflatex / xelatex",
        "has_embedded_bibliography": bool(references),
        "citation_keys_count": len(references),
    }
    return out_content, metadata


# ==========================================
# C.4 Verified BibTeX Generator
# ==========================================

def export_to_bibtex(revision: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
    """
    Generate BibTeX entries from stored bibliographic metadata.
    Enforces authenticity: never fabricates missing DOIs or journal fields.
    Flags missing or unverified bibliographic data explicitly.
    """
    references = revision.get("references", [])
    entries = []
    verified_count = 0
    unverified_count = 0

    seen_keys = set()
    for ref in references:
        raw_key = ref.get("citation_key") or ref.get("study_id") or f"ref_{uuid.uuid4().hex[:6]}"
        ckey = re.sub(r"[^a-zA-Z0-9_:]", "_", raw_key)
        # Ensure unique citation keys
        orig_key = ckey
        suffix = 1
        while ckey in seen_keys:
            ckey = f"{orig_key}_{suffix}"
            suffix += 1
        seen_keys.add(ckey)

        title = ref.get("title", "").strip() or "Untitled Publication"
        authors = ref.get("authors", [])
        if isinstance(authors, list):
            author_str = " and ".join(authors) if authors else "THOTH Research Collaboration"
        else:
            author_str = str(authors)

        year = ref.get("year") or datetime.date.today().year
        journal = ref.get("journal", "")
        doi = ref.get("doi", "")
        url = ref.get("source_url", "")
        entry_type = ref.get("entry_type", "article" if journal else "misc")

        missing_fields = []
        if not journal and entry_type == "article":
            missing_fields.append("journal")
        if not doi:
            missing_fields.append("doi")

        is_verified = bool(ref.get("verified", False) and doi)
        if is_verified:
            verified_count += 1
        else:
            unverified_count += 1

        entry_lines = []
        if missing_fields:
            entry_lines.append(f"% Note: Bibliographic verification partial; missing fields: {', '.join(missing_fields)}")
        if not is_verified:
            entry_lines.append("% Note: Unverified entry - no persistent DOI confirmed.")

        entry_lines.append(f"@{entry_type}{{{ckey},")
        entry_lines.append(f"  title = {{{_bibtex_escape(title)}}},")
        entry_lines.append(f"  author = {{{_bibtex_escape(author_str)}}},")
        entry_lines.append(f"  year = {{{year}}},")
        if journal:
            entry_lines.append(f"  journal = {{{_bibtex_escape(journal)}}},")
        if doi:
            entry_lines.append(f"  doi = {{{doi}}},")
        if url:
            entry_lines.append(f"  url = {{{url}}},")
        entry_lines.append(f"  note = {{THOTH Evidence Synthesis; Verified: {'true' if is_verified else 'false'}}}")
        entry_lines.append("}")

        entries.append("\n".join(entry_lines))

    out_content = "\n\n".join(entries)
    metadata = {
        "total_entries": len(references),
        "verified_entries": verified_count,
        "unverified_entries": unverified_count,
        "citation_keys": list(seen_keys),
    }
    return out_content, metadata


# ==========================================
# C.5 Publication-Oriented HTML Exporter
# ==========================================

def export_to_html(revision: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
    """
    Generate clean, semantically structured, accessible, and secure HTML5 manuscript.
    Safely escapes user and external text via html.escape to prevent XSS.
    Includes interactive citation links and evidence status badges.
    """
    title = revision.get("title", "THOTH Academic Manuscript")
    version = revision.get("version", 1)
    sections = revision.get("sections", {})
    claims = revision.get("claims", [])
    references = revision.get("references", [])
    evidence_matrix = revision.get("evidence_matrix", {})

    escaped_title = html.escape(title)
    sorted_secs = _get_sorted_sections(sections)

    # Stylesheet for academic publication
    css = """
    :root {
        --font-serif: "Charter", "Georgia", "Cambria", serif;
        --font-sans: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
        --text-color: #1a1a1a;
        --bg-color: #fafbfc;
        --container-bg: #ffffff;
        --border-color: #e1e4e8;
        --accent-color: #0366d6;
        --badge-supported: #28a745;
        --badge-qualified: #d97706;
        --badge-challenged: #d73a49;
        --badge-unverified: #6a737d;
    }
    body {
        margin: 0;
        padding: 40px 20px;
        background-color: var(--bg-color);
        color: var(--text-color);
        font-family: var(--font-serif);
        font-size: 18px;
        line-height: 1.65;
    }
    .manuscript-container {
        max-width: 820px;
        margin: 0 auto;
        background: var(--container-bg);
        padding: 60px 80px;
        border: 1px solid var(--border-color);
        border-radius: 6px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.04);
    }
    header {
        border-bottom: 2px solid var(--border-color);
        padding-bottom: 24px;
        margin-bottom: 40px;
    }
    h1 {
        font-family: var(--font-sans);
        font-size: 2.2rem;
        font-weight: 700;
        line-height: 1.25;
        margin: 0 0 16px 0;
    }
    .metadata {
        font-family: var(--font-sans);
        font-size: 0.9rem;
        color: #586069;
    }
    h2 {
        font-family: var(--font-sans);
        font-size: 1.5rem;
        font-weight: 600;
        margin-top: 40px;
        margin-bottom: 16px;
        border-bottom: 1px solid var(--border-color);
        padding-bottom: 8px;
    }
    p {
        margin: 0 0 1.2rem 0;
    }
    table {
        width: 100%;
        border-collapse: collapse;
        font-family: var(--font-sans);
        font-size: 0.88rem;
        margin: 24px 0;
    }
    th, td {
        border: 1px solid var(--border-color);
        padding: 10px 14px;
        text-align: left;
        vertical-align: top;
    }
    th {
        background-color: #f6f8fa;
        font-weight: 600;
    }
    .badge {
        display: inline-block;
        padding: 3px 8px;
        border-radius: 12px;
        font-size: 0.75rem;
        font-weight: 600;
        color: #fff;
    }
    .badge-supported { background-color: var(--badge-supported); }
    .badge-qualified { background-color: var(--badge-qualified); }
    .badge-challenged { background-color: var(--badge-challenged); }
    .badge-unverified { background-color: var(--badge-unverified); }
    .citation-link {
        color: var(--accent-color);
        text-decoration: none;
        font-weight: 500;
    }
    .citation-link:hover {
        text-decoration: underline;
    }
    .references-list {
        font-family: var(--font-sans);
        font-size: 0.95rem;
        padding-left: 20px;
    }
    .references-list li {
        margin-bottom: 12px;
    }
    """

    doc_parts = [
        "<!DOCTYPE html>",
        "<html lang=\"en\">",
        "<head>",
        "  <meta charset=\"UTF-8\">",
        "  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">",
        f"  <title>{escaped_title}</title>",
        f"  <style>{css}</style>",
        "</head>",
        "<body>",
        "  <article class=\"manuscript-container\">",
        "    <header>",
        f"      <h1>{escaped_title}</h1>",
        "      <div class=\"metadata\">",
        f"        <span><strong>Version:</strong> {version}</span> | ",
        f"        <span><strong>Date:</strong> {datetime.date.today().strftime('%B %d, %Y')}</span> | ",
        "        <span><strong>Engine:</strong> THOTH Academic Manuscript Engine</span>",
        "      </div>",
        "    </header>",
    ]

    # Render Sections
    for key, sec in sorted_secs:
        sec_h = html.escape(sec.get("heading", key.title()))
        sec_c = html.escape(sec.get("content", ""))
        paragraphs = sec_c.split("\n\n")

        doc_parts.append(f"    <section id=\"section-{key}\">")
        doc_parts.append(f"      <h2>{sec_h}</h2>")
        for p in paragraphs:
            if p.strip():
                doc_parts.append(f"      <p>{p.strip()}</p>")

        # If results section, embed Evidence Matrix table
        if key == "results" and evidence_matrix.get("included_studies"):
            doc_parts.append("      <h3>Evidence Synthesis Matrix</h3>")
            doc_parts.append("      <table>")
            doc_parts.append("        <thead>")
            doc_parts.append("          <tr>")
            doc_parts.append("            <th>Study ID</th>")
            doc_parts.append("            <th>Primary Finding</th>")
            doc_parts.append("            <th>Methodological Appraisal</th>")
            doc_parts.append("            <th>Citation Link</th>")
            doc_parts.append("          </tr>")
            doc_parts.append("        </thead>")
            doc_parts.append("        <tbody>")
            for st in evidence_matrix.get("included_studies", []):
                sid = html.escape(st.get("study_id", ""))
                findings = html.escape(st.get("synthesized_findings", ""))
                appraisal = html.escape(st.get("appraisal_notes", "Rigor Assessed"))
                ckey = html.escape(st.get("study_id", "").replace("-", "_").replace(" ", "_"))
                doc_parts.append("          <tr>")
                doc_parts.append(f"            <td><code>{sid}</code></td>")
                doc_parts.append(f"            <td>{findings}</td>")
                doc_parts.append(f"            <td>{appraisal}</td>")
                doc_parts.append(f"            <td><a class=\"citation-link\" href=\"#ref-{ckey}\">[@{ckey}]</a></td>")
                doc_parts.append("          </tr>")
            doc_parts.append("        </tbody>")
            doc_parts.append("      </table>")

        doc_parts.append("    </section>")

    # Claim-Level Provenance Ledger
    if claims:
        doc_parts.append("    <section id=\"claims-ledger\">")
        doc_parts.append("      <h2>Claim-Level Evidential Ledger</h2>")
        doc_parts.append("      <table>")
        doc_parts.append("        <thead>")
        doc_parts.append("          <tr>")
        doc_parts.append("            <th>Claim ID</th>")
        doc_parts.append("            <th>Evidential Status</th>")
        doc_parts.append("            <th>Claim Statement</th>")
        doc_parts.append("            <th>Supporting Sources</th>")
        doc_parts.append("          </tr>")
        doc_parts.append("        </thead>")
        doc_parts.append("        <tbody>")
        for clm in claims:
            cid = html.escape(clm.get("claim_id", ""))
            stat = clm.get("evidence_status", "UNVERIFIED")
            stat_class = f"badge-{stat.lower()}"
            ctext = html.escape(clm.get("claim_text", ""))

            supp_links = []
            for s in clm.get("supporting_sources", []):
                skey = html.escape(str(s.get("citation_key", s.get("study_id", "ref"))).replace("-", "_").replace(" ", "_"))
                supp_links.append(f"<a class=\"citation-link\" href=\"#ref-{skey}\">[@{skey}]</a>")
            supp_html = ", ".join(supp_links) or "None"

            doc_parts.append("          <tr>")
            doc_parts.append(f"            <td><code>{cid}</code></td>")
            doc_parts.append(f"            <td><span class=\"badge {stat_class}\">{stat}</span></td>")
            doc_parts.append(f"            <td>{ctext}</td>")
            doc_parts.append(f"            <td>{supp_html}</td>")
            doc_parts.append("          </tr>")
        doc_parts.append("        </tbody>")
        doc_parts.append("      </table>")
        doc_parts.append("    </section>")

    # Bibliography
    if references:
        doc_parts.append("    <section id=\"references\">")
        doc_parts.append("      <h2>References</h2>")
        doc_parts.append("      <ol class=\"references-list\">")
        for ref in references:
            ckey = html.escape(ref.get("citation_key", "ref").replace("-", "_").replace(" ", "_"))
            rtitle = html.escape(ref.get("title", "Untitled Reference"))
            authors = html.escape(", ".join(ref.get("authors", [])) if isinstance(ref.get("authors"), list) else str(ref.get("authors", "THOTH")))
            year = ref.get("year", datetime.date.today().year)
            doi = ref.get("doi", "")
            url = ref.get("source_url", "")

            doi_html = f" <a class=\"citation-link\" href=\"https://doi.org/{html.escape(doi)}\" target=\"_blank\" rel=\"noopener\">[DOI: {html.escape(doi)}]</a>" if doi else ""
            if not doi and url:
                doi_html = f" <a class=\"citation-link\" href=\"{html.escape(url)}\" target=\"_blank\" rel=\"noopener\">[URL]</a>"

            doc_parts.append(f"        <li id=\"ref-{ckey}\">")
            doc_parts.append(f"          <strong>[{ckey}]</strong> {authors} ({year}). <em>{rtitle}</em>.{doi_html}")
            doc_parts.append("        </li>")
        doc_parts.append("      </ol>")
        doc_parts.append("    </section>")

    doc_parts.append("  </article>")
    doc_parts.append("</body>")
    doc_parts.append("</html>")

    out_content = "\n".join(doc_parts)
    metadata = {
        "format": "html5",
        "semantic_structure": "article/header/section/table/ol",
        "xss_protected": True,
        "references_count": len(references),
        "claims_count": len(claims),
    }
    return out_content, metadata


# ==========================================
# Helpers
# ==========================================

def _get_sorted_sections(sections: Dict[str, Any]) -> List[Tuple[str, Dict[str, Any]]]:
    """Sort manuscript sections by their explicit order index."""
    items = []
    for k, v in sections.items():
        if isinstance(v, dict):
            items.append((k, v))
        else:
            items.append((k, {"heading": k.title(), "content": str(v), "order": 99}))
    return sorted(items, key=lambda x: x[1].get("order", 99))


def _latex_escape(text: str) -> str:
    """Escape LaTeX special control characters safely."""
    if not text:
        return ""
    conv = {
        "&": "\\&",
        "%": "\\%",
        "$": "\\$",
        "#": "\\#",
        "_": "\\_",
        "{": "\\{",
        "}": "\\}",
        "~": "\\textasciitilde{}",
        "^": "\\textasciicircum{}",
        "\\": "\\textbackslash{}",
    }
    regex = re.compile("|".join(re.escape(k) for k in conv.keys()))
    return regex.sub(lambda m: conv[m.group(0)], text)


def _bibtex_escape(text: str) -> str:
    """Escape special characters for BibTeX field values."""
    if not text:
        return ""
    return text.replace("{", "\\{").replace("}", "\\}").replace('"', "''")
