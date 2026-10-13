import os
import re
import yaml
import importlib
import logging
from typing import Dict, Any, Optional, Tuple, List, Union

from backend.intellectual_rigour.models import ReviewRequest, ReviewTarget
from backend.intellectual_rigour.frameworks.base import BaseThinkerFramework

logger = logging.getLogger("ThothIntellectualRigour.Registry")

_DEFAULT_YAML_PATH = os.path.join(os.path.dirname(__file__), "thinkers.yaml")
_LOADED_FRAMEWORKS: Dict[str, BaseThinkerFramework] = {}
_ALIAS_MAP: Dict[str, str] = {}

def load_registry(yaml_path: str = _DEFAULT_YAML_PATH) -> Dict[str, BaseThinkerFramework]:
    global _LOADED_FRAMEWORKS, _ALIAS_MAP

    if _LOADED_FRAMEWORKS:
        return _LOADED_FRAMEWORKS

    if not os.path.exists(yaml_path):
        logger.warning(f"[REGISTRY] Config file {yaml_path} not found. Instantiating built-in Popper fallback.")
        from backend.intellectual_rigour.frameworks.popper.framework import PopperFramework
        pf = PopperFramework()
        _LOADED_FRAMEWORKS["popper"] = pf
        _ALIAS_MAP["/popper"] = "popper"
        _ALIAS_MAP["/falsification"] = "popper"
        return _LOADED_FRAMEWORKS

    try:
        with open(yaml_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        thinkers_dict = data.get("thinkers", {})
        for thinker_id, info in thinkers_dict.items():
            if info.get("status") != "active":
                continue

            class_module = info.get("class_module")
            class_name = info.get("class_name")
            if class_module and class_name:
                mod = importlib.import_module(class_module)
                cls_ = getattr(mod, class_name)
                instance = cls_()
                _LOADED_FRAMEWORKS[thinker_id] = instance

                for alias in info.get("aliases", []):
                    clean_alias = alias.lower().strip()
                    _ALIAS_MAP[clean_alias] = thinker_id
                    if not clean_alias.startswith("/"):
                        _ALIAS_MAP[f"/{clean_alias}"] = thinker_id

    except Exception as e:
        logger.error(f"[REGISTRY LOAD ERROR] Failed to load thinkers from {yaml_path}: {e}")
        from backend.intellectual_rigour.frameworks.popper.framework import PopperFramework
        pf = PopperFramework()
        _LOADED_FRAMEWORKS["popper"] = pf
        _ALIAS_MAP["/popper"] = "popper"

    for s_alias in ["/rigour", "/rigor", "/philosophical-review", "/intellectual-rigour"]:
        _ALIAS_MAP[s_alias] = "rigour_synthesis"

    return _LOADED_FRAMEWORKS

def get_framework(thinker_id: str) -> Optional[BaseThinkerFramework]:
    registry = load_registry()
    return registry.get(thinker_id.lower().strip())

def resolve_thinker_command(query: str) -> Optional[Tuple[Union[BaseThinkerFramework, str], ReviewRequest]]:
    if not query or not isinstance(query, str):
        return None

    clean = query.strip()
    registry = load_registry()

    parts = clean.split()
    if not parts:
        return None

    cmd_candidate = parts[0].lower().strip()
    cmd_clean = cmd_candidate.strip(",.:;!?()[]\"'")

    thinker_id = _ALIAS_MAP.get(cmd_candidate) or _ALIAS_MAP.get(cmd_clean)
    matched_idx = 0 if thinker_id else -1

    if not thinker_id:
        for idx, token in enumerate(parts):
            token_clean = token.lower().strip(",.:;!?()[]\"'")
            if token_clean.startswith("/") and token_clean in _ALIAS_MAP:
                thinker_id = _ALIAS_MAP[token_clean]
                matched_idx = idx
                break

    if not thinker_id:
        return None

    args_tokens = [p for i, p in enumerate(parts) if i != matched_idx]
    args_text = " ".join(args_tokens)

    if thinker_id == "rigour_synthesis":
        req = ReviewRequest(
            query=query,
            target=ReviewTarget(scope="WHOLE_REPORT"),
            force_reevaluation="--force" in args_text or "-f" in args_text
        )
        return "rigour_synthesis", req

    if thinker_id not in registry:
        return None

    framework = registry[thinker_id]

    force = "--force" in args_text or "-f" in args_text
    args_cleaned = re.sub(r"--force|-f", "", args_text).strip()

    target_scope = "WHOLE_REPORT"
    target_section = None

    target_match = re.search(r'--target=["\']?([^"\']+)["\']?', clean, re.IGNORECASE)
    if target_match:
        target_section = target_match.group(1).strip()
        target_scope = "SECTION"
    else:
        section_keywords = ["methodology", "findings", "key findings", "introduction", "conclusion", "abstract", "model", "benchmarks", "definitions"]
        for kw in section_keywords:
            if re.search(rf"\b{kw}\b", args_cleaned, re.IGNORECASE):
                target_section = kw.title()
                target_scope = "SECTION"
                break

    request = ReviewRequest(
        query=query,
        target=ReviewTarget(
            scope=target_scope,
            section_title=target_section
        ),
        force_reevaluation=force
    )

    return framework, request

def list_registered_thinkers() -> List[Dict[str, Any]]:
    registry = load_registry()
    out = []
    for tid, fw in registry.items():
        out.append({
            "id": fw.id,
            "name": fw.name,
            "tradition": fw.tradition,
            "epistemic_role": fw.epistemic_role,
            "section_heading": fw.section_heading,
        })
    return out
