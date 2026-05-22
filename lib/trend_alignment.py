"""Trend selection and downstream alignment checks for ad-video.

These helpers keep trend usage observable without turning the agent-first
pipeline into a Python orchestrator. Director skills still decide the creative
application, while these pure checks make stale, unsafe, or unthreaded trend
usage easy to catch in tests and review gates.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from lib.trend_recency import dedupe_trends, filter_stale_trends


SCRIPT_TARGETS = {"hook", "build"}
VISUAL_TARGETS = {"scene_plan", "visual", "pacing"}
SELECTABLE_SENTIMENTS = {"positive", "neutral"}


def _lower(value: Any) -> str:
    return str(value or "").strip().lower()


def _trend_id(trend: dict[str, Any]) -> str:
    return str(trend.get("trend_id") or trend.get("signal") or "").strip()


def _is_selectable_for_alignment(trend: dict[str, Any]) -> bool:
    trend_type = _lower(trend.get("trend_type"))
    sentiment = _lower(trend.get("sentiment")) or "neutral"
    brand_safety = _lower(trend.get("brand_safety")) or "safe"

    if sentiment == "unknown" and trend_type == "platform_format_norm":
        sentiment = "neutral"

    return sentiment in SELECTABLE_SENTIMENTS and brand_safety == "safe"


def select_trends_for_alignment(
    trends: list[dict[str, Any]],
    *,
    now: date,
    max_items: int | None = None,
) -> list[dict[str, Any]]:
    """Return fresh, deduped, brand-safe positive/neutral trend records.

    Research may retain stale, negative, cautionary, or unsafe trend records for
    context, but bible-director must not select them into creative guidance.
    Missing sentiment/safety is treated as neutral/safe for legacy brief
    compatibility. Explicitly unknown sentiment is excluded unless the record is
    marked as a safe platform_format_norm rather than an engagement signal.
    """
    fresh_selectable = [
        trend
        for trend in filter_stale_trends(trends, now=now)
        if _is_selectable_for_alignment(trend)
    ]
    selected = dedupe_trends(fresh_selectable)
    if max_items is None:
        return selected
    return selected[:max(0, max_items)]


def _alignment_block(production_bible: dict[str, Any]) -> dict[str, Any] | None:
    intelligence = production_bible.get("intelligence") if isinstance(production_bible, dict) else None
    if not isinstance(intelligence, dict):
        return None
    block = intelligence.get("trend_alignment")
    return block if isinstance(block, dict) else None


def _alignment_entries(production_bible: dict[str, Any]) -> list[dict[str, Any]]:
    block = _alignment_block(production_bible)
    if block is None:
        return []
    entries = block.get("alignments", [])
    return entries if isinstance(entries, list) else []


def _selected_trend_ids(production_bible: dict[str, Any]) -> list[str]:
    block = _alignment_block(production_bible)
    if block is None:
        return []
    selected = block.get("selected_trend_ids", [])
    if not isinstance(selected, list):
        return []
    return [str(trend_id).strip() for trend_id in selected if str(trend_id).strip()]


def _entry_ref(entry: dict[str, Any]) -> str:
    script_usage = entry.get("script_usage") or {}
    if isinstance(script_usage, dict) and script_usage.get("source_ref"):
        return str(script_usage["source_ref"])
    return f"trend_alignment:{entry.get('trend_id')}"


def _section_keys(section: dict[str, Any]) -> set[str]:
    keys = {
        _lower(section.get("id")),
        _lower(section.get("beat")),
        _lower(section.get("label")),
    }
    return {key for key in keys if key}


def _section_has_ref(section: dict[str, Any], expected_ref: str) -> bool:
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


def check_script_trend_alignment(
    production_bible: dict[str, Any],
    script: dict[str, Any],
) -> dict[str, Any]:
    """Check selected trend refs are propagated into required script sections."""
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
                issues.append({
                    "kind": "missing_required_script_section",
                    "trend_id": entry.get("trend_id"),
                    "beat": beat,
                    "expected_ref": expected_ref,
                })
                continue
            if not any(_section_has_ref(section, expected_ref) for section in matching):
                issues.append({
                    "kind": "missing_trend_source_ref",
                    "trend_id": entry.get("trend_id"),
                    "beat": beat,
                    "expected_ref": expected_ref,
                })

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
    if isinstance(targets, list) and any(_lower(target) in VISUAL_TARGETS for target in targets):
        return True
    return False


def _scene_refs(scene: dict[str, Any]) -> set[str]:
    refs = scene.get("trend_alignment_refs") or []
    if not isinstance(refs, list):
        return set()
    return {str(ref).strip() for ref in refs if str(ref).strip()}


def _scene_has_instruction(scene: dict[str, Any]) -> bool:
    return bool(str(scene.get("trend_alignment_notes") or "").strip())


def check_scene_plan_trend_alignment(
    production_bible: dict[str, Any],
    scene_plan: dict[str, Any],
) -> dict[str, Any]:
    """Check selected visual/pacing trends have at least one aligned scene."""
    issues: list[dict[str, Any]] = []
    scenes = scene_plan.get("scenes", []) if isinstance(scene_plan, dict) else []
    if not isinstance(scenes, list):
        scenes = []

    for entry in _alignment_entries(production_bible):
        if not _entry_requires_scene_alignment(entry):
            continue

        expected_ref = _entry_ref(entry)
        fallback_ref = _trend_id(entry)
        scene_usage = entry.get("scene_usage") or {}
        required_count = 1
        if isinstance(scene_usage, dict):
            required_count = int(scene_usage.get("required_scene_count") or 1)
        required_count = max(1, required_count)

        matching = [
            scene
            for scene in scenes
            if isinstance(scene, dict)
            and (
                expected_ref in _scene_refs(scene)
                or (fallback_ref and fallback_ref in _scene_refs(scene))
            )
        ]
        instructed = [scene for scene in matching if _scene_has_instruction(scene)]

        if len(instructed) < required_count:
            issues.append({
                "kind": "missing_scene_trend_alignment",
                "trend_id": entry.get("trend_id"),
                "expected_ref": expected_ref,
                "required_scene_count": required_count,
                "matched_scene_count": len(instructed),
            })

    return {
        "ok": not issues,
        "issues": issues,
        "summary": {
            "alignments_checked": len(_alignment_entries(production_bible)),
            "scenes_checked": len(scenes),
        },
    }


def check_ad_video_planning_trend_alignment(
    production_bible: dict[str, Any],
    script: dict[str, Any],
    scene_plan: dict[str, Any],
) -> dict[str, Any]:
    """Check selected trend guidance survives from bible to script and scenes.

    Also guards against vacuous pass: when the trend_alignment block is
    entirely missing from production_bible.intelligence, the pipeline
    skipped the alignment step. An explicit empty block
    (``selected_trend_ids: [], alignments: []``) is valid — it means
    selection ran but nothing qualified. A missing block is not.
    """
    script_report = check_script_trend_alignment(production_bible, script)
    scene_report = check_scene_plan_trend_alignment(production_bible, scene_plan)
    entries = _alignment_entries(production_bible)
    aligned_trend_ids = {_trend_id(entry) for entry in entries if _trend_id(entry)}
    issues: list[dict[str, Any]] = []

    block = _alignment_block(production_bible)
    if block is None:
        issues.append({
            "kind": "trend_alignment_block_missing",
            "artifact": "production_bible",
        })
    elif "selected_trend_ids" not in block:
        issues.append({
            "kind": "trend_alignment_selection_skipped",
            "artifact": "production_bible",
        })

    issues.extend(
        {
            "kind": "missing_selected_trend_alignment",
            "trend_id": trend_id,
            "artifact": "production_bible",
        }
        for trend_id in _selected_trend_ids(production_bible)
        if trend_id not in aligned_trend_ids
    )
    issues.extend(
        {**issue, "artifact": "script"}
        for issue in script_report.get("issues", [])
    )
    issues.extend(
        {**issue, "artifact": "scene_plan"}
        for issue in scene_report.get("issues", [])
    )
    return {
        "ok": not issues,
        "issues": issues,
        "script": script_report,
        "scene_plan": scene_report,
        "summary": {
            "selected_trends_checked": len(_selected_trend_ids(production_bible)),
            "alignments_checked": len(entries),
            "script_sections_checked": script_report.get("summary", {}).get("sections_checked", 0),
            "scenes_checked": scene_report.get("summary", {}).get("scenes_checked", 0),
        },
    }
