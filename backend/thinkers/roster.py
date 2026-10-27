"""The thinker roster (docs/features/thinker-roster.md, approved 24 Oct 2026).

Each thinker's mind lives in ``dossiers/<id>.md``: the single source of truth for the persona.
This module only lists who is on the roster and parses the dossier sections.
"""
from __future__ import annotations

import os
import re
from functools import lru_cache
from typing import Dict, List, Optional

DOSSIER_DIR = os.path.join(os.path.dirname(__file__), "dossiers")

# Order is the order shown to users. "brings" is the one line from the roster decision.
ROSTER: List[Dict[str, str]] = [
    {"id": "aristotle", "name": "Aristotle", "years": "384–322 BCE",
     "brings": "What is the thing? Definitions, kinds, and four kinds of explanation."},
    {"id": "ibn_al_haytham", "name": "Ibn al-Haytham", "years": "c. 965 – c. 1040",
     "brings": "Doubt towards authorities; checking claims by controlled, repeatable test."},
    {"id": "hume", "name": "David Hume", "years": "1711–1776",
     "brings": "What do we actually observe, and what are we adding? Causation and evidence."},
    {"id": "darwin", "name": "Charles Darwin", "years": "1809–1882",
     "brings": "Patient accumulation, variation, mechanism, and the facts against your own view."},
    {"id": "nightingale", "name": "Florence Nightingale", "years": "1820–1910",
     "brings": "Numbers as moral instruments: compare like with like, then change things."},
    {"id": "weber", "name": "Max Weber", "years": "1864–1920",
     "brings": "What the action means to the people doing it; ideal types; many causes."},
    {"id": "popper", "name": "Karl Popper", "years": "1902–1994",
     "brings": "What would show you wrong? Bold conjectures and severe tests."},
    {"id": "kuhn", "name": "Thomas Kuhn", "years": "1922–1996",
     "brings": "Which framework are you inside, and what does it stop you seeing?"},
    {"id": "simon", "name": "Herbert Simon", "years": "1916–2001",
     "brings": "Real people decide with limited information; design for how things actually work."},
    {"id": "ostrom", "name": "Elinor Ostrom", "years": "1933–2012",
     "brings": "Field evidence against tidy models; the rules people build for themselves."},
]
ROSTER_IDS = [t["id"] for t in ROSTER]

PERSONA_SECTIONS = (
    "Life and problems", "What you cared about", "How your thinking moved",
    "Temperament and voice", "Commitments and revisions", "Blind spots",
)


def get(thinker_id: str) -> Optional[Dict[str, str]]:
    key = (thinker_id or "").lower().lstrip("/")
    return next((t for t in ROSTER if t["id"] == key), None)


@lru_cache(maxsize=None)
def dossier(thinker_id: str) -> Dict[str, str]:
    """Dossier sections keyed by heading."""
    with open(os.path.join(DOSSIER_DIR, f"{thinker_id}.md"), encoding="utf-8") as f:
        text = f.read()
    parts = re.split(r"^## (.+)$", text, flags=re.M)
    return {parts[i].strip(): parts[i + 1].strip() for i in range(1, len(parts) - 1, 2)}


def territory(thinker_id: str) -> str:
    """The 'Close:' line of the dossier's Territory section, for the conductor's suggestions."""
    text = dossier(thinker_id).get("Territory", "")
    m = re.search(r"Close:\s*(.+?)(?:\s+Far:|$)", text, flags=re.S)
    return " ".join((m.group(1) if m else text).split())


def _unwrap(text: str) -> str:
    """Join hard-wrapped lines inside paragraphs and list items, keeping list starts and blank lines."""
    return re.sub(r"\n(?!\n|\s*- |\s*\d+\. )[ \t]*", " ", text)


def profile(thinker_id: str) -> Dict[str, object]:
    """What the user sees when they tap a thinker's bust: the dossier itself, which is written in the
    second person because it is the brief the thinker is given."""
    t = get(thinker_id)
    d = {k: _unwrap(v) for k, v in dossier(thinker_id).items()}
    return {
        **t,
        "life": d.get("Life and problems", ""),
        "cared_about": d.get("What you cared about", ""),
        "how_they_thought": d.get("How your thinking moved", ""),
        "temperament": d.get("Temperament and voice", ""),
        "blind_spots": d.get("Blind spots", ""),
        "territory": d.get("Territory", ""),
        "sources": d.get("Sources", ""),
    }
