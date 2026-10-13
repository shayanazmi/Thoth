from abc import ABC, abstractmethod
import hashlib
import re
from typing import Dict, Any, Optional

from backend.intellectual_rigour.models import (
    ReviewRequest,
    ReviewArtifact,
    ThinkerOutput,
    ReasoningSpec,
)

def strip_existing_intellectual_rigour_blocks(markdown_text: str) -> str:
    if not markdown_text:
        return ""

    cleaned = re.sub(
        r"<!--\s*intellectual-rigour:.*?-->.*?<!--\s*intellectual-rigour:end\s*-->",
        "",
        markdown_text,
        flags=re.DOTALL | re.IGNORECASE,
    )

    cleaned = re.sub(
        r"###\s+🏛️\s+Philosophical Review:.*?(?=\n#{1,3}\s+|\Z)",
        "",
        cleaned,
        flags=re.DOTALL,
    )
    return cleaned.strip()

class BaseThinkerFramework(ABC):
    id: str
    name: str
    tradition: str
    epistemic_role: str
    section_heading: str
    spec: ReasoningSpec

    def compute_source_hash(self, source_text: str) -> str:
        cleaned = strip_existing_intellectual_rigour_blocks(source_text)
        return hashlib.sha256(cleaned.encode("utf-8")).hexdigest()[:12]

    @abstractmethod
    def review(
        self,
        request: ReviewRequest,
        report_text: str,
        topic: str = "",
        context: Optional[Dict[str, Any]] = None,
    ) -> ReviewArtifact:
        pass
