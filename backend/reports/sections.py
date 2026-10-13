from dataclasses import dataclass
import re
from typing import List, Optional

@dataclass
class MarkdownSection:
    title: str
    level: int
    start_line: int
    end_line: int
    heading_raw: str
    body: str

def find_markdown_sections(markdown_text: str) -> List[MarkdownSection]:
    if not markdown_text:
        return []

    lines = markdown_text.splitlines()
    sections: List[MarkdownSection] = []
    heading_pattern = re.compile(r"^(#{1,6})\s+(.+)$")

    current_title = ""
    current_level = 0
    current_heading_raw = ""
    current_start = -1
    current_body_lines: List[str] = []
    in_code_block = False

    for idx, line in enumerate(lines):
        stripped = line.strip()

        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_code_block = not in_code_block
            if current_start != -1:
                current_body_lines.append(line)
            continue

        match = heading_pattern.match(stripped) if not in_code_block else None
        if match:
            if current_start != -1:
                sections.append(
                    MarkdownSection(
                        title=current_title,
                        level=current_level,
                        start_line=current_start,
                        end_line=idx - 1,
                        heading_raw=current_heading_raw,
                        body="\n".join(current_body_lines),
                    )
                )

            current_level = len(match.group(1))
            current_title = match.group(2).strip()
            current_heading_raw = line
            current_start = idx
            current_body_lines = []
        else:
            if current_start != -1:
                current_body_lines.append(line)

    if current_start != -1:
        sections.append(
            MarkdownSection(
                title=current_title,
                level=current_level,
                start_line=current_start,
                end_line=len(lines) - 1,
                heading_raw=current_heading_raw,
                body="\n".join(current_body_lines),
            )
        )

    return sections

def find_matching_section(
    sections: List[MarkdownSection],
    target_title: str,
) -> Optional[MarkdownSection]:
    if not sections or not target_title:
        return None

    clean_target = re.sub(r"[#*_`]", "", target_title).strip().lower()

    for sec in sections:
        clean_sec = re.sub(r"[#*_`]", "", sec.title).strip().lower()
        if clean_sec == clean_target:
            return sec

    for sec in sections:
        clean_sec = re.sub(r"[#*_`]", "", sec.title).strip().lower()
        if clean_target in clean_sec or clean_sec in clean_target:
            return sec

    return None
