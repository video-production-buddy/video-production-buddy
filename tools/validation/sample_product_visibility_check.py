"""Sample sub-stage product-visibility validator.

Asset-director picks 2-3 scenes for the sample preview. The asset-director.md
sample sub-stage rule states the sample MUST include at least one scene where
the advertised product (or another brand-mandatory element) is visible — even
if the creative concept hides the product until a late-stage reveal.

This validator enforces that rule by substring-matching the bible's
brand_constraints.mandatory_elements against the selected scenes'
description / non-negated visual_constraint / scene_type fields.

Used by:
  - asset-director.md sample sub-stage (call before assembling the sample
    preview clip; if FAIL, swap in a product-visible scene before generating)
  - CLI ad-hoc:
        python -m tools.validation.sample_product_visibility_check \
            projects/<project-name> scene-1 scene-2

The check is heuristic — it operates on free-form prose. WARN is returned when
a partial overlap is detected but no full-keyword match is found; FAIL when
the selection contains no scene plausibly showing a mandatory element.
"""

from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path
from typing import Any

from tools.base_tool import (
    BaseTool,
    Determinism,
    ExecutionMode,
    ResourceProfile,
    ToolResult,
    ToolRuntime,
    ToolStability,
    ToolTier,
)
from tools.validation._scene_scope import validate_scene_id_list


_STOPWORDS = {
    "no", "the", "a", "an", "and", "or", "of", "in", "on", "at", "for",
    "with", "to", "by", "from", "into", "onto", "as", "must", "appear",
    "appears", "visible", "include", "included", "element", "elements",
}
PRODUCT_VISIBLE_VALUES = {"background", "partial", "hero", "detail", "packshot"}

_NEGATED_VISUAL_CONSTRAINT_RE = re.compile(
    r"\b(?:do not|don't|dont|never)\s+"
    r"(?:show|reveal|display|feature|include|surface|frame)\b"
    r"|\b(?:not|without)\s+"
    r"(?:showing|revealing|displaying|featuring|including|framing)\b"
    r"|\bnot\s+(?:yet\s+)?"
    r"(?:visible|shown|revealed|displayed|featured|included)\b"
    r"|\bno\s+(?:product|brand|logo|device|phone|wordmark|packshot)\b"
    r"|\b(?:hide|conceal|withhold)\b"
    r"|\b(?:keep|kept|remain|remains|stays?|still)\s+"
    r"(?:it|the\s+)?(?:product|brand|logo|device|phone|wordmark|packshot)?\s*"
    r"(?:hidden|concealed|obscured|masked)\b"
    r"|\b(?:hidden|concealed|obscured|masked)\s+until\b"
    r"|\b(?:obscure|obscured|mask|masked)\s+(?:the\s+)?"
    r"(?:product|brand|logo|device|phone|wordmark|packshot)\b"
    r"|\b(?:defer|delay|save)\s+(?:the\s+)?"
    r"(?:product|brand|logo|device|phone|reveal|appearance|hero)\b",
    re.IGNORECASE,
)


def _load_artifact(project_dir: Path, name: str) -> dict[str, Any]:
    path = project_dir / "artifacts" / name
    if not path.exists():
        raise FileNotFoundError(f"missing artifact: {path}")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _extract_keywords(element: str) -> list[str]:
    """Pull content-bearing words out of a mandatory-element prose phrase.

    Mandatory elements are written as natural-language declarations like
    'OPPO wordmark in final frame' or 'Hasselblad orange dot visible on the
    device'. We extract the proper nouns and topical keywords (skipping a
    small stopword list) for substring matching against scene descriptions.
    """
    # Drop bracketed/quoted noise like 'Tagline "For everyone who sees."'.
    cleaned = re.sub(r"['\"][^'\"]*['\"]", " ", element)
    # Tokenise on non-alphanumerics; preserve hyphenated tokens.
    tokens = re.findall(r"[A-Za-z][A-Za-z0-9-]+", cleaned)
    # Strip stopwords + short tokens (< 3 chars). Lowercase for matching.
    return [t for t in tokens if len(t) >= 3 and t.lower() not in _STOPWORDS]


def _visibility_evidence_from_text(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    if _NEGATED_VISUAL_CONSTRAINT_RE.search(value):
        return ""
    return value


def _visibility_evidence_from_visual_constraint(scene: dict[str, Any]) -> str:
    return _visibility_evidence_from_text(scene.get("visual_constraint", "") or "")


def _keyword_hit(keyword: str, text: str) -> bool:
    pattern = rf"(?<![A-Za-z0-9-]){re.escape(keyword.lower())}(?![A-Za-z0-9-])"
    return bool(re.search(pattern, text))


def _scene_text(scene: dict[str, Any]) -> str:
    """Concatenate the prose fields where a mandatory element might appear."""
    parts = [
        _visibility_evidence_from_text(scene.get("description", "")),
        _visibility_evidence_from_visual_constraint(scene),
        scene.get("scene_type", ""),
        scene.get("type", ""),
    ]
    parts.extend(scene.get("texture_keywords", []) or [])
    parts.append(_visibility_evidence_from_text(scene.get("overlay_notes", "") or ""))
    return " ".join(p for p in parts if p).lower()


def _is_product_visible_scene(scene: dict[str, Any]) -> bool:
    return (
        scene.get("product_visibility") in PRODUCT_VISIBLE_VALUES
        or scene.get("product_reference_required") is True
    )


def check_sample_visibility(
    bible: dict[str, Any],
    scene_plan: dict[str, Any],
    selected_scene_ids: list[str],
) -> dict[str, Any]:
    """Validate that the selected sample scenes show a brand-mandatory element.

    Returns:
        {
          "status": "PASS" | "WARN" | "FAIL",
          "selected_scene_ids": [...],
          "mandatory_elements": [...],
          "matches": [{scene_id, matched_element, keywords_hit}, ...],
          "issues": [...]
        }
    """
    brand_constraints = bible.get("brand_constraints", {}) or {}
    mandatory = list(brand_constraints.get("mandatory_elements", []) or [])
    issues: list[str] = []
    selected_scene_ids, scene_id_issues, usable_scene_ids = validate_scene_id_list(
        selected_scene_ids,
        "selected_scene_ids",
    )
    issues.extend(scene_id_issues)
    if not usable_scene_ids:
        return {
            "status": "FAIL",
            "selected_scene_ids": [],
            "mandatory_elements": mandatory,
            "matches": [],
            "partial_hits": [],
            "issues": issues,
        }

    if not selected_scene_ids:
        issues.append(
            "selected_scene_ids must contain at least one scene before the "
            "sample preview can be assembled."
        )

    scenes_by_id: dict[str, dict[str, Any]] = {
        s["id"]: s for s in scene_plan.get("scenes", []) if s.get("id")
    }
    selected_scenes = [scenes_by_id[sid] for sid in selected_scene_ids if sid in scenes_by_id]
    missing_ids = [sid for sid in selected_scene_ids if sid not in scenes_by_id]
    for sid in missing_ids:
        issues.append(f"Selected scene id '{sid}' not found in scene_plan.scenes[].")

    product_visible_scene_ids = [
        scene["id"]
        for scene in scenes_by_id.values()
        if _is_product_visible_scene(scene)
    ]
    selected_product_visible_scene_ids = [
        scene["id"]
        for scene in selected_scenes
        if _is_product_visible_scene(scene)
    ]
    if product_visible_scene_ids and not selected_product_visible_scene_ids:
        issues.append(
            "The scene_plan contains product-visible scenes, but none of the "
            "selected sample scenes are marked product-visible. The asset-director.md "
            "sample sub-stage rule requires at least one product-visible scene in "
            "the sample."
        )
    has_blocking_selection_issue = (
        bool(missing_ids)
        or bool(scene_id_issues)
        or (bool(product_visible_scene_ids) and not selected_product_visible_scene_ids)
    )

    if not mandatory:
        status = "FAIL" if issues else "PASS"
        if not issues:
            if product_visible_scene_ids:
                issues.append(
                    "Sample selection includes a product-visible scene by "
                    "scene_plan.product_visibility annotation."
                )
            else:
                issues.append(
                    "production_bible.brand_constraints.mandatory_elements is empty; "
                    "no visibility check applicable. Sample sub-stage may proceed "
                    "with any scene selection."
                )
        return {
            "status": status,
            "selected_scene_ids": selected_scene_ids,
            "mandatory_elements": [],
            "matches": [],
            "partial_hits": [],
            "issues": issues,
        }

    matches: list[dict[str, Any]] = []
    partial_hits: list[dict[str, Any]] = []

    for scene in selected_scenes:
        text = _scene_text(scene)
        if not text:
            continue
        for element in mandatory:
            keywords = _extract_keywords(element)
            if not keywords:
                continue
            keyword_hits = [k for k in keywords if _keyword_hit(k, text)]
            # FULL match: at least 2 distinct content keywords from the element appear.
            # Single-keyword overlap is a partial signal, not a real visibility match.
            if len(keyword_hits) >= 2:
                matches.append({
                    "scene_id": scene["id"],
                    "matched_element": element,
                    "keywords_hit": keyword_hits,
                })
            elif len(keyword_hits) == 1:
                partial_hits.append({
                    "scene_id": scene["id"],
                    "matched_element": element,
                    "keywords_hit": keyword_hits,
                })

    if has_blocking_selection_issue:
        status = "FAIL"
    elif product_visible_scene_ids and selected_product_visible_scene_ids:
        status = "PASS"
    elif matches:
        status = "PASS"
    elif partial_hits:
        status = "WARN"
        issues.append(
            "No full keyword match for any mandatory element in the selected sample "
            "scenes — only partial overlaps. The sample may technically include the "
            "product but the substring check is not confident. Asset-director should "
            "either pick a scene with stronger product visibility or proceed with "
            "documented uncertainty."
        )
    else:
        status = "FAIL"
        issues.append(
            "None of the selected sample scenes describe any brand-mandatory element. "
            "The asset-director.md sample sub-stage rule requires at least one "
            "product-visible scene in the sample. Swap in a scene that mentions the "
            "product, brand, or another mandatory_elements entry before assembling "
            "the sample preview."
        )

    return {
        "status": status,
        "selected_scene_ids": selected_scene_ids,
        "mandatory_elements": mandatory,
        "matches": matches,
        "partial_hits": partial_hits,
        "issues": issues,
    }


def check_project(project_dir: Path, selected_scene_ids: list[str]) -> dict[str, Any]:
    bible = _load_artifact(project_dir, "production_bible.json")
    scene_plan = _load_artifact(project_dir, "scene_plan.json")
    return check_sample_visibility(bible, scene_plan, selected_scene_ids)


class SampleProductVisibilityCheck(BaseTool):
    name = "sample_product_visibility_check"
    version = "0.1.0"
    tier = ToolTier.CORE
    capability = "validation"
    provider = "openmontage"
    stability = ToolStability.PRODUCTION
    execution_mode = ExecutionMode.SYNC
    determinism = Determinism.DETERMINISTIC
    runtime = ToolRuntime.LOCAL
    resource_profile = ResourceProfile(cpu_cores=1, ram_mb=64, disk_mb=1, network_required=False)
    capabilities = [
        "validate_ad_video_sample_product_visibility",
        "validate_brand_mandatory_element_in_sample",
    ]
    best_for = [
        "checking that an ad-video sample includes a product-visible or brand-mandatory scene",
        "blocking chronological samples that hide the product until too late",
    ]
    input_schema = {
        "type": "object",
        "properties": {
            "project_dir": {"type": "string"},
            "production_bible": {"type": "object"},
            "bible": {"type": "object"},
            "scene_plan": {"type": "object"},
            "selected_scene_ids": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["selected_scene_ids"],
        "anyOf": [
            {"required": ["project_dir", "selected_scene_ids"]},
            {"required": ["production_bible", "scene_plan", "selected_scene_ids"]},
            {"required": ["bible", "scene_plan", "selected_scene_ids"]},
        ],
    }
    output_schema = {
        "type": "object",
        "required": [
            "status",
            "selected_scene_ids",
            "mandatory_elements",
            "matches",
            "partial_hits",
            "issues",
        ],
    }
    user_visible_verification = [
        "Confirm the sample preview includes at least one product-visible or brand-mandatory scene",
    ]

    def execute(self, inputs: dict[str, Any]) -> ToolResult:
        started = time.time()
        try:
            selected_scene_ids = inputs["selected_scene_ids"]
            project_dir = inputs.get("project_dir")
            if isinstance(project_dir, str) and project_dir.strip():
                verdict = check_project(Path(project_dir), selected_scene_ids)
            else:
                bible = inputs.get("production_bible") or inputs.get("bible")
                if not isinstance(bible, dict):
                    raise ValueError(
                        "Missing production_bible or bible; sample visibility "
                        "checks must use the canonical production_bible unless "
                        "project_dir is provided."
                    )
                verdict = check_sample_visibility(bible, inputs["scene_plan"], selected_scene_ids)
        except Exception as exc:
            return ToolResult(success=False, error=str(exc), duration_seconds=round(time.time() - started, 2))

        success = verdict.get("status") != "FAIL"
        return ToolResult(
            success=success,
            data=verdict,
            error=json.dumps(verdict.get("issues", []), sort_keys=True) if not success else None,
            duration_seconds=round(time.time() - started, 2),
        )


def _cli(argv: list[str]) -> int:
    if len(argv) < 3:
        print(
            "usage: python -m tools.validation.sample_product_visibility_check "
            "<project-dir> <scene_id> [<scene_id> ...]",
            file=sys.stderr,
        )
        return 2
    project_dir = Path(argv[1]).resolve()
    selected = argv[2:]
    if not project_dir.exists():
        print(f"error: project dir not found: {project_dir}", file=sys.stderr)
        return 2
    verdict = check_project(project_dir, selected)
    print(json.dumps(verdict, indent=2))
    return 0 if verdict["status"] != "FAIL" else 1


if __name__ == "__main__":
    raise SystemExit(_cli(sys.argv))
