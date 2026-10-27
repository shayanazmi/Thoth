"""Reader (docs/features/05 § paper record; prompt in 09 § Reader).

Builds a neutral record of one paper WITHOUT seeing the hypothesis. Provenance is enforced in code: a
field can only claim full-text provenance if full text was actually read, and a result without a locator
is dropped.
"""
from __future__ import annotations

import re
from typing import Any, Dict

from backend.research.llm import call_json

DESIGNS = {"rct", "quasi_experimental", "cohort_prospective", "cohort_retrospective", "case_control", "cross_sectional",
           "qualitative", "mixed_methods", "narrative_review", "systematic_review", "meta_analysis", "modelling"}
PROVENANCE = {"from_full_text", "from_abstract", "not_reported", "not_accessible"}
FIELDS = ("aim", "design", "setting", "population", "sample_size")

PROMPT = """ROLE
You are Thoth's Reader. Extract a neutral record of ONE paper. You are not told the hypothesis, on purpose:
report what the paper says, not what anyone hopes it says.

METHOD
1. Check what text you actually have (access level below). That caps what you can report.
2. Fill each field from the text. Copy numbers exactly. Note where each came from.
3. For every result, give a locator a reader could find: section name, table/figure number, page or paragraph.
4. Note limitations the authors state. Separately, note design limitations you see, labelled as yours.

OUTPUT (JSON). Every simple field is {"value": ..., "provenance": P} where
P is one of "from_full_text", "from_abstract", "not_reported", "not_accessible".
{"aim": {...}, "design": {...}, "setting": {...}, "population": {...}, "sample_size": {...},
 "measures": [{"construct": str, "instrument": str, "how_measured": str, "self_report_or_objective": str, "provenance": P}],
 "analysis": {"methods": str, "controls": str, "provenance": P},
 "results": [{"finding": str, "numbers": str, "locator": str, "provenance": P}],
 "limitations_stated": [str], "limitations_noticed_by_reader": [str]}

RULES
- With abstract_only, most method fields are "not_reported". That is the correct answer. Never fill them from
  what similar studies usually do.
- "design" value is one of: rct, quasi_experimental, cohort_prospective, cohort_retrospective, case_control,
  cross_sectional, qualitative, mixed_methods, narrative_review, systematic_review, meta_analysis, modelling,
  other:<name>. Use systematic_review ONLY if the paper reports a systematic search and selection method
  (databases, criteria, a flow of records); a review without that is narrative_review.
  If the paper does not say, use provenance "not_reported".
- A result without a locator is not a result. Leave it out."""


def _fix_prov(p: Any, access: str) -> str:
    p = p if p in PROVENANCE else "not_reported"
    if p == "from_full_text" and access != "full_text":
        return "from_abstract" if access == "abstract_only" else "not_accessible"
    return p


def enforce(record: Dict[str, Any], access: str) -> Dict[str, Any]:
    """Make the record honest about what was read, whatever the model returned."""
    out: Dict[str, Any] = {}
    for f in FIELDS:
        v = record.get(f) if isinstance(record.get(f), dict) else {"value": record.get(f), "provenance": "not_reported"}
        prov = _fix_prov(v.get("provenance"), access)
        value = v.get("value") if prov not in ("not_reported", "not_accessible") else None
        out[f] = {"value": value, "provenance": prov}
    d = str(out["design"]["value"] or "").lower().strip()
    if d and d not in DESIGNS and not d.startswith("other:"):
        out["design"]["value"] = f"other:{d}"
    out["measures"] = [{**m, "provenance": _fix_prov(m.get("provenance"), access)} for m in record.get("measures") or [] if isinstance(m, dict)]
    a = record.get("analysis") if isinstance(record.get("analysis"), dict) else {}
    out["analysis"] = {"methods": a.get("methods") or "", "controls": a.get("controls") or "", "provenance": _fix_prov(a.get("provenance"), access)}
    out["results"] = [{**r, "provenance": _fix_prov(r.get("provenance"), access)}
                      for r in record.get("results") or [] if isinstance(r, dict) and str(r.get("locator") or "").strip()]
    out["limitations_stated"] = [str(x) for x in record.get("limitations_stated") or []][:8]
    out["limitations_noticed_by_reader"] = [str(x) for x in record.get("limitations_noticed_by_reader") or []][:6]
    out["access"] = access
    out["read_by"] = str(record.get("_served_by") or "")
    return out


SECTION_KEEP = re.compile(r"\b(abstract|introduction|background|method|material|participant|design|sample|measure|"
                          r"instrument|analys|result|finding|discussion|limitation|conclusion)", re.I)
SECTION_DROP = re.compile(r"\b(references?|bibliography|acknowledg|funding|conflicts? of interest|author contributions?|"
                          r"supplementary|data availability|ethics)", re.I)
READER_CHARS = 16000


def focus(text: str, limit: int = READER_CHARS) -> str:
    """Keep the parts of a paper a reader needs (methods, results, limitations) within a budget.
    Long full texts were slow and hit rate limits; references and front matter carry no findings."""
    if len(text) <= limit:
        return text
    parts = re.split(r"\n(?=## )", text)
    if len(parts) < 3:
        return text[:limit]
    kept = [p for p in parts if SECTION_KEEP.search(p[:80]) and not SECTION_DROP.search(p[:80])] or parts
    out, used = [], 0
    for p in kept:
        take = p[: max(0, limit - used)]
        if take:
            out.append(take)
            used += len(take)
    return "\n".join(out)


PRIMARY = "nemotron-3-ultra"


def read_by_fallback(record: Dict[str, Any]) -> bool:
    """The record says a model other than the primary read it (the fallback answered during a rate limit)."""
    by = str((record or {}).get("read_by") or "")
    return bool(by) and PRIMARY not in by


async def read(meta: Dict[str, Any], text: str, access: str, primary_only: bool = False) -> Dict[str, Any]:
    text = focus(text)
    human = (f"<access_level>{access}</access_level>\n"
             f"<metadata>{meta.get('title')} ({meta.get('year')}). {', '.join(meta.get('authors') or [])}. {meta.get('venue') or ''}</metadata>\n"
             f"<untrusted>\n{text}\n</untrusted>")
    raw = await call_json("reader:primary" if primary_only else "reader", PROMPT, human, default={}) or {}
    return enforce(raw if isinstance(raw, dict) else {}, access)
