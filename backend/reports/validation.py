import re

def validate_report_structure(markdown_text: str) -> bool:
    if not markdown_text or not markdown_text.strip():
        return False

    text = markdown_text.strip()

    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) < 3:
            return False

    fence_count = len(re.findall(r"^```", text, re.MULTILINE))
    if fence_count % 2 != 0:
        return False

    if len(text) < 10:
        return False

    return True
