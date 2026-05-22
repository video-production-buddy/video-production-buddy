"""Professional knowledge alignment checks for ad-video planning artifacts."""

from __future__ import annotations

from typing import Any


SCRIPT_TARGETS = {"hook", "build", "reveal", "cta_brand"}
VISUAL_TARGETS = {"scene_plan", "visual", "pacing", "format"}


def _lower(value: Any) -> str:
    return str(value or "").strip().lower()


def _alignment_block(production_bible: dict[str, Any]) -> dict[str, Any] | None:
    intelligence = production_bible.get("intelligence") if isinstance(production_bible, dict) else None
    if not isinstance(intelligence, dict):
        return None
    block = intelligence.get("knowledge_alignment")
    return block if isinstance(block, dict) else None


def _alignment_entries(production_bible: dict[str, Any]) -> list[dict[str, Any]]:
    block = _alignment_block(production_bible)
    if block is None:
        return []
    entries = block.get("alignments", [])
    return entries if isinstance(entries, list) else []


def _selected_card_ids(production_bible: dict[str, Any]) -> list[str]:
    block = _alignment_block(production_bible)
    if block is None:
        return []
    selected = block.get("selected_card_ids", [])
    if not isinstance(selected, list):
        return []
    return [str(card_id).strip() for card_id in selected if str(card_id).strip()]


def _card_id(entry: dict[str, Any]) -> str:
    return str(entry.get("card_id") or "").strip()


def _entry_ref(entry: dict[str, Any]) -> str:
    card_id = _card_id(entry)
    return f"knowledge_alignment:{card_id}" if card_id else ""


def _script_usage_ref(entry: dict[str, Any]) -> str:
    script_usage = entry.get("script_usage") or {}
    if isinstance(script_usage, dict) and script_usage.get("source_ref"):
        return str(script_usage["source_ref"])
    return ""


def _knowledge_ref_consistency_issues(entry: dict[str, Any]) -> list[dict[str, Any]]:
    expected_ref = _entry_ref(entry)
    card_id = _card_id(entry)
    if not card_id:
        return [
            {
                "kind": "missing_knowledge_card_id",
                "card_id": entry.get("card_id"),
                "field": "card_id",
                "expected_ref": expected_ref,
            }
        ]

    issues: list[dict[str, Any]] = []
    for field, actual_ref in (
        ("source_ref", str(entry.get("source_ref") or "").strip()),
        ("script_usage.source_ref", _script_usage_ref(entry)),
    ):
        if actual_ref != expected_ref:
            issues.append(
                {
                    "kind": "inconsistent_knowledge_source_ref",
                    "card_id": card_id,
                    "field": field,
                    "expected_ref": expected_ref,
                    "actual_ref": actual_ref,
                }
            )
    return issues


def _section_keys(section: dict[str, Any]) -> set[str]:
    keys = {
        _lower(section.get("id")),
        _lower(section.get("beat")),
        _lower(section.get("label")),
    }
    return {key for key in keys if key}


def _section_has_ref(section: dict[str, Any], expected_ref: str) -> bool:
    if not expected_ref:
        return False
    if str(section.get("source_ref") or "").strip() == expected_ref:
        return True
    source_refs = section.get("source_refs") or []
    if not isinstance(source_refs, list):
        return False
    return expected_ref in {str(ref).strip() for ref in source_refs}


def _required_script_sections(entry: dict[str, Any]) -> list[str]:
    script_usage = entry.get("script_usage") or {}
    if isinstance(script_usage, dict):
        explicit = script_usage.get("required_section_ids") or []
        if isinstance(explicit, list) and explicit:
            return [_lower(item) for item in explicit if _lower(item)]

    target = _lower(entry.get("target_beat"))
    if target in SCRIPT_TARGETS:
        return [target]
    if target == "multi":
        return sorted(SCRIPT_TARGETS)
    return []


def check_script_knowledge_alignment(
    production_bible: dict[str, Any],
    script: dict[str, Any],
) -> dict[str, Any]:
    """Check selected professional knowledge refs reach required script sections."""
    issues: list[dict[str, Any]] = []
    sections = script.get("sections", []) if isinstance(script, dict) else []
    if not isinstance(sections, list):
        sections = []

    for entry in _alignment_entries(production_bible):
        expected_ref = _entry_ref(entry)
        for beat in _required_script_sections(entry):
            matching = [
                section
                for section in sections
                if isinstance(section, dict) and beat in _section_keys(section)
            ]
            if not matching:
                issues.append(
                    {
                        "kind": "missing_required_knowledge_script_section",
                        "card_id": entry.get("card_id"),
                        "beat": beat,
                        "expected_ref": expected_ref,
                    }
                )
                continue
            if not any(_section_has_ref(section, expected_ref) for section in matching):
                issues.append(
                    {
                        "kind": "missing_knowledge_source_ref",
                        "card_id": entry.get("card_id"),
                        "beat": beat,
                        "expected_ref": expected_ref,
                    }
                )

    return {
        "ok": not issues,
        "issues": issues,
        "summary": {
            "alignments_checked": len(_alignment_entries(production_bible)),
            "sections_checked": len(sections),
        },
    }


def _entry_requires_scene_alignment(entry: dict[str, Any]) -> bool:
    scene_usage = entry.get("scene_usage") or {}
    if isinstance(scene_usage, dict) and scene_usage.get("required") is True:
        return True
    targets = entry.get("application_targets") or []
    return isinstance(targets, list) and any(_lower(target) in VISUAL_TARGETS for target in targets)


def _scene_refs(scene: dict[str, Any]) -> set[str]:
    refs = scene.get("knowledge_alignment_refs") or []
    if not isinstance(refs, list):
        return set()
    return {str(ref).strip() for ref in refs if str(ref).strip()}


def _scene_has_instruction(scene: dict[str, Any]) -> bool:
    return bool(str(scene.get("knowledge_alignment_notes") or "").strip())


def check_scene_plan_knowledge_alignment(
    production_bible: dict[str, Any],
    scene_plan: dict[str, Any],
) -> dict[str, Any]:
    """Check selected professional knowledge has observable scene-plan use."""
    issues: list[dict[str, Any]] = []
    scenes = scene_plan.get("scenes", []) if isinstance(scene_plan, dict) else []
    if not isinstance(scenes, list):
        scenes = []

    for entry in _alignment_entries(production_bible):
        if not _entry_requires_scene_alignment(entry):
            continue

        expected_ref = _entry_ref(entry)
        scene_usage = entry.get("scene_usage") or {}
        required_count = 1
        if isinstance(scene_usage, dict):
            required_count = int(scene_usage.get("required_scene_count") or 1)
        required_count = max(1, required_count)

        matching = [
            scene
            for scene in scenes
            if isinstance(scene, dict)
            and expected_ref in _scene_refs(scene)
        ]
        instructed = [scene for scene in matching if _scene_has_instruction(scene)]

        if len(instructed) < required_count:
            issues.append(
                {
                    "kind": "missing_scene_knowledge_alignment",
                    "card_id": entry.get("card_id"),
                    "expected_ref": expected_ref,
                    "required_scene_count": required_count,
                    "matched_scene_count": len(instructed),
                }
            )

    return {
        "ok": not issues,
        "issues": issues,
        "summary": {
            "alignments_checked": len(_alignment_entries(production_bible)),
            "scenes_checked": len(scenes),
        },
    }


def check_ad_video_planning_knowledge_alignment(
    production_bible: dict[str, Any],
    script: dict[str, Any],
    scene_plan: dict[str, Any],
) -> dict[str, Any]:
    """Check selected professional knowledge survives bible to script/scenes.

    Also guards against vacuous pass: when the knowledge_alignment block
    is entirely missing from production_bible.intelligence, the pipeline
    skipped the alignment step. An explicit empty block
    (``selected_card_ids: [], alignments: []``) is valid — it means
    selection ran but no card qualified. A missing block is not.
    """
    script_report = check_script_knowledge_alignment(production_bible, script)
    scene_report = check_scene_plan_knowledge_alignment(production_bible, scene_plan)
    entries = _alignment_entries(production_bible)
    aligned_card_ids = {_card_id(entry) for entry in entries if _card_id(entry)}
    consistency_issues = [
        issue
        for entry in entries
        for issue in _knowledge_ref_consistency_issues(entry)
    ]

    issues: list[dict[str, Any]] = []

    block = _alignment_block(production_bible)
    if block is None:
        issues.append({
            "kind": "knowledge_alignment_block_missing",
            "artifact": "production_bible",
        })
    elif "selected_card_ids" not in block:
        issues.append({
            "kind": "knowledge_alignment_selection_skipped",
            "artifact": "production_bible",
        })

    issues.extend(
        {
            "kind": "missing_selected_knowledge_alignment",
            "card_id": card_id,
            "artifact": "production_bible",
        }
        for card_id in _selected_card_ids(production_bible)
        if card_id not in aligned_card_ids
    )
    issues.extend({**issue, "artifact": "production_bible"} for issue in consistency_issues)
    issues.extend({**issue, "artifact": "script"} for issue in script_report.get("issues", []))
    issues.extend({**issue, "artifact": "scene_plan"} for issue in scene_report.get("issues", []))

    return {
        "ok": not issues,
        "issues": issues,
        "script": script_report,
        "scene_plan": scene_report,
        "summary": {
            "selected_cards_checked": len(_selected_card_ids(production_bible)),
            "alignments_checked": len(entries),
            "script_sections_checked": script_report.get("summary", {}).get("sections_checked", 0),
            "scenes_checked": scene_report.get("summary", {}).get("scenes_checked", 0),
        },
    }
