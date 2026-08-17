import os
import re
import datetime
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
import yaml

DEFAULT_VAULT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "vault"))
VALID_SUBFOLDERS = ["topics", "entities", "sources", "sessions"]


@dataclass
class Note:
    """
    Structured representation of a markdown note with YAML frontmatter.
    """
    note_id: str
    note_type: str
    content: str
    frontmatter: Dict[str, Any] = field(default_factory=dict)
    file_path: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "note_id": self.note_id,
            "type": self.note_type,
            "content": self.content,
            "frontmatter": self.frontmatter,
            "file_path": self.file_path,
        }


def extract_links(content: str) -> List[str]:
    """
    Parses and returns all [[wikilink]] target note IDs referenced within content.
    """
    if not content:
        return []
    links = re.findall(r"\[\[([^\]]+)\]\]", content)
    # Deduplicate while preserving order
    seen = set()
    deduped = []
    for link in links:
        cleaned = link.strip()
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            deduped.append(cleaned)
    return deduped


def _validate_claims_citations(note_id: str, content: str):
    """
    Enforces that any line inside a Claims section must end with a [[source-note-id]] citation.
    Raises ValueError if an uncited claim is encountered.
    """
    if not content:
        return

    lines = content.splitlines()
    in_claims_section = False

    for line_num, line in enumerate(lines, 1):
        stripped = line.strip()

        # Check if entering or exiting a markdown section
        header_match = re.match(r"^#{1,6}\s+(.*)$", stripped)
        if header_match:
            header_title = header_match.group(1).strip().lower()
            if "claim" in header_title:
                in_claims_section = True
                continue
            else:
                in_claims_section = False
                continue

        if in_claims_section and stripped:
            # Skip divider lines or pure markdown formatting if not claim text
            if stripped.startswith("---") or stripped.startswith("==="):
                continue
            
            # A valid claim line must end with a wikilink citation like [[source-id]]
            # We strip trailing formatting like bolding or list markers
            has_citation = bool(re.search(r"\[\[[^\]]+\]\]\s*$", stripped))
            if not has_citation:
                raise ValueError(
                    f"Uncited claim in note '{note_id}' at line {line_num}: '{stripped}'. "
                    f"All lines in a Claims section must end with a [[source-note-id]] citation reference."
                )


def write_note(
    note_id: str,
    note_type: str,
    content: str,
    frontmatter: Optional[Dict[str, Any]] = None,
    vault_dir: str = DEFAULT_VAULT_DIR
) -> str:
    """
    Writes a markdown file with YAML frontmatter followed by markdown body.
    Enforces claim citation integrity.
    """
    # Enforce claim citation references
    _validate_claims_citations(note_id, content)

    # Normalize note_type and directory
    clean_type = note_type.lower().strip()
    subfolder = clean_type if clean_type in VALID_SUBFOLDERS else "topics"
    target_dir = os.path.join(vault_dir, subfolder)
    os.makedirs(target_dir, exist_ok=True)

    # Build default frontmatter
    fm = dict(frontmatter or {})
    fm.setdefault("type", clean_type)
    fm.setdefault("created", datetime.datetime.now(datetime.timezone.utc).isoformat())
    fm.setdefault("confidence", 1.0)
    fm.setdefault("sources", extract_links(content))

    # Format YAML frontmatter
    fm_yaml = yaml.dump(fm, default_flow_style=False, sort_keys=False).strip()
    file_content = f"---\n{fm_yaml}\n---\n\n{content.strip()}\n"

    # Write file
    file_path = os.path.join(target_dir, f"{note_id}.md")
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(file_content)

    return file_path


def read_note(note_id: str, vault_dir: str = DEFAULT_VAULT_DIR) -> Note:
    """
    Locates and reads a note by note_id across vault subfolders,
    parsing frontmatter and body into a Note object.
    """
    target_file = None

    # Search in all valid subfolders as well as root
    search_dirs = [os.path.join(vault_dir, sub) for sub in VALID_SUBFOLDERS] + [vault_dir]
    for directory in search_dirs:
        candidate_path = os.path.join(directory, f"{note_id}.md")
        if os.path.isfile(candidate_path):
            target_file = candidate_path
            break

    if not target_file:
        raise FileNotFoundError(f"Note '{note_id}' not found in vault '{vault_dir}'.")

    with open(target_file, "r", encoding="utf-8") as f:
        raw_text = f.read()

    # Parse YAML frontmatter
    frontmatter = {}
    content = raw_text

    fm_match = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", raw_text, re.DOTALL)
    if fm_match:
        fm_raw, body_raw = fm_match.groups()
        try:
            frontmatter = yaml.safe_load(fm_raw) or {}
        except Exception:
            frontmatter = {}
        content = body_raw.strip()

    note_type = frontmatter.get("type", "topics")

    return Note(
        note_id=note_id,
        note_type=note_type,
        content=content,
        frontmatter=frontmatter,
        file_path=target_file,
    )


def list_notes(
    note_type: Optional[str] = None,
    vault_dir: str = DEFAULT_VAULT_DIR
) -> List[str]:
    """
    Lists note IDs in the vault, optionally filtered by note_type.
    """
    if not os.path.exists(vault_dir):
        return []

    note_ids = []
    if note_type:
        clean_type = note_type.lower().strip()
        search_dirs = [os.path.join(vault_dir, clean_type)]
    else:
        search_dirs = [os.path.join(vault_dir, sub) for sub in VALID_SUBFOLDERS] + [vault_dir]

    for directory in search_dirs:
        if os.path.isdir(directory):
            for fname in os.listdir(directory):
                if fname.endswith(".md"):
                    note_id = fname[:-3]
                    if note_id not in note_ids:
                        note_ids.append(note_id)

    return sorted(note_ids)


def audit_vault_notes_citations(
    cutoff_iso: str = "2026-08-17T19:22:00",
    vault_dir: str = DEFAULT_VAULT_DIR
) -> List[Dict[str, Any]]:
    """
    Audits existing vault topic notes for citations created before the verified attribution fix.
    Flags notes whose claims may have been assigned via legacy index round-robin logic.
    """
    flagged = []
    all_topic_ids = list_notes(note_type="topics", vault_dir=vault_dir)

    for nid in all_topic_ids:
        note = read_note(nid, vault_dir=vault_dir)
        if not note:
            continue

        created_str = note.frontmatter.get("created", "")
        # Check if note has a claims section with wikilinks
        claims = []
        in_claims = False
        for line in (note.content or "").splitlines():
            stripped = line.strip()
            if stripped.startswith("#") and "claim" in stripped.lower():
                in_claims = True
                continue
            elif stripped.startswith("#"):
                in_claims = False
                continue

            if in_claims and stripped and "[[" in stripped and "]]" in stripped:
                claims.append(stripped)

        # Flag if created before cutoff timestamp or if created timestamp is missing
        is_legacy = False
        if not created_str or created_str < cutoff_iso:
            is_legacy = True

        if is_legacy and claims:
            flagged.append({
                "note_id": nid,
                "created": created_str or "UNKNOWN",
                "claims_count": len(claims),
                "claims": claims,
                "flagged_for_review": True,
                "reason": "Created before supporting_source_id fix; claim wikilinks may have used round-robin rotation."
            })

    return flagged
