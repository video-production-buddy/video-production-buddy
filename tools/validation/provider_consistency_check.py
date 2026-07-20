"""Ad-video provider/model consistency validator.

Checks that assets reflect provider choices locked at proposal, and that
provider/model substitutions are backed by a visible user-approved decision.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any

from schemas.artifacts import load_strict_json_object
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
from tools.validation.asset_contract import VISUAL_ASSET_TYPES


EXPECTED_TTS_TOOLS = {
    "qwen3": "cosyvoice_tts",
    "openai": "openai_tts",
    "minimax": "minimax_tts",
}

MUSIC_SOURCE_TOOLS_BY_STRATEGY = {
    "generative_loose": {"minimax_music", "music_gen", "suno_music"},
    "library_locked": {"music_library"},
    "search_align": {"freesound_music", "pixabay_music"},
}

ALIGNMENT_REQUIRED_MUSIC_STRATEGIES = {"library_locked", "search_align"}
MAX_MUSIC_ALIGNMENT_DRIFT_SECONDS = 0.5
BUDGET_OVERAGE_APPROVAL_OPTIONS = {
    "approve-overage",
    "approve_overage",
    "approve-budget-overage",
    "approve_budget_overage",
    "increase-budget",
    "increase_budget",
}


def _load_artifact(project_dir: Path, name: str) -> dict[str, Any]:
    path = project_dir / "artifacts" / name
    if not path.exists():
        raise FileNotFoundError(f"missing artifact: {path}")
    return load_strict_json_object(path, context=f"artifact {path}")


def _load_decision_log(project_dir: Path) -> dict[str, Any] | None:
    for path in (
        project_dir / "decision_log.json",
        project_dir / "artifacts" / "decision_log.json",
    ):
        if path.exists():
            return load_strict_json_object(path, context=f"decision log {path}")
    return None


def _option_ids(decision: dict[str, Any]) -> set[str]:
    options = decision.get("options_considered")
    if not isinstance(options, list):
        return set()
    return {
        option.get("option_id")
        for option in options
        if isinstance(option, dict) and isinstance(option.get("option_id"), str)
    }


def _find_approved_substitution(
    decision_log: dict[str, Any] | None,
    *,
    categories: set[str],
    selected_candidates: set[str],
) -> dict[str, Any] | None:
    if not isinstance(decision_log, dict):
        return None

    decisions = decision_log.get("decisions")
    if not isinstance(decisions, list):
        return None

    for decision in reversed(decisions):
        if not isinstance(decision, dict):
            continue
        selected = decision.get("selected")
        if (
            decision.get("category") in categories
            and decision.get("user_visible") is True
            and decision.get("user_approved") is True
            and isinstance(selected, str)
            and selected in selected_candidates
            and selected in _option_ids(decision)
        ):
            return decision
    return None


def _find_approved_decision(
    decision_log: dict[str, Any] | None,
    *,
    categories: set[str],
) -> dict[str, Any] | None:
    if not isinstance(decision_log, dict):
        return None

    decisions = decision_log.get("decisions")
    if not isinstance(decisions, list):
        return None

    for decision in reversed(decisions):
        if not isinstance(decision, dict):
            continue
        selected = decision.get("selected")
        if (
            decision.get("category") in categories
            and decision.get("user_visible") is True
            and decision.get("user_approved") is True
            and isinstance(selected, str)
            and selected in _option_ids(decision)
        ):
            return decision
    return None


def _find_approved_budget_overage_decision(
    decision_log: dict[str, Any] | None,
) -> dict[str, Any] | None:
    decision = _find_approved_decision(
        decision_log,
        categories={"budget_tradeoff"},
    )
    if not decision:
        return None

    selected = decision.get("selected")
    if selected in BUDGET_OVERAGE_APPROVAL_OPTIONS:
        return decision
    return None


def _find_approved_music_strategy_change(
    decision_log: dict[str, Any] | None,
    *,
    actual_tool: str | None,
) -> tuple[dict[str, Any], str] | None:
    """Return an approved strategy change whose selected strategy allows the tool."""
    if not isinstance(actual_tool, str) or not actual_tool.strip():
        return None
    if not isinstance(decision_log, dict):
        return None

    decisions = decision_log.get("decisions")
    if not isinstance(decisions, list):
        return None

    for decision in reversed(decisions):
        if not isinstance(decision, dict):
            continue
        selected = decision.get("selected")
        if (
            decision.get("category") == "music_strategy_selection"
            and decision.get("user_visible") is True
            and decision.get("user_approved") is True
            and isinstance(selected, str)
            and selected in _option_ids(decision)
            and actual_tool in MUSIC_SOURCE_TOOLS_BY_STRATEGY.get(selected, set())
        ):
                return decision, selected
    return None


def _find_approved_music_strategy_selection(
    decision_log: dict[str, Any] | None,
    *,
    selected_strategy: str,
) -> tuple[dict[str, Any], str] | None:
    """Return an approved visible decision selecting a specific music strategy."""
    if not isinstance(decision_log, dict):
        return None

    decisions = decision_log.get("decisions")
    if not isinstance(decisions, list):
        return None

    for decision in reversed(decisions):
        if not isinstance(decision, dict):
            continue
        selected = decision.get("selected")
        if (
            decision.get("category") == "music_strategy_selection"
            and decision.get("user_visible") is True
            and decision.get("user_approved") is True
            and selected == selected_strategy
            and selected in _option_ids(decision)
        ):
            return decision, selected
    return None


def _assets_by_type(asset_manifest: dict[str, Any], asset_type: str) -> list[dict[str, Any]]:
    assets = asset_manifest.get("assets")
    if not isinstance(assets, list):
        return []
    return [
        asset
        for asset in assets
        if isinstance(asset, dict) and asset.get("type") == asset_type
    ]


def _narration_assets(asset_manifest: dict[str, Any]) -> list[dict[str, Any]]:
    assets = asset_manifest.get("assets")
    if not isinstance(assets, list):
        return []
    return [
        asset
        for asset in assets
        if isinstance(asset, dict)
        and (
            asset.get("type") == "narration"
            or (
                asset.get("type") == "audio"
                and "narr" in str(asset.get("id") or asset.get("path") or "").lower()
            )
        )
    ]


def _script_section_ids(script: dict[str, Any] | None) -> list[str]:
    if not isinstance(script, dict):
        return []

    sections = script.get("sections")
    if not isinstance(sections, list):
        return []

    section_ids: list[str] = []
    for section in sections:
        if not isinstance(section, dict):
            continue
        section_id = section.get("id")
        if isinstance(section_id, str) and section_id.strip():
            section_ids.append(section_id.strip())
    return section_ids


def _narration_file_entries(asset_manifest: dict[str, Any]) -> list[dict[str, Any]]:
    narration_files = asset_manifest.get("narration_files")
    if not isinstance(narration_files, list):
        return []
    return [entry for entry in narration_files if isinstance(entry, dict)]


def _validate_narration_inventory(
    asset_manifest: dict[str, Any],
    narration_assets: list[dict[str, Any]],
    *,
    script: dict[str, Any] | None = None,
) -> list[str]:
    """Validate that narration files are auditable and cover script sections."""
    issues: list[str] = []
    narration_files = _narration_file_entries(asset_manifest)
    section_ids = _script_section_ids(script)

    if not narration_assets:
        if narration_files:
            issues.append(
                "asset_manifest.narration_files is present but "
                "asset_manifest.assets[] has no auditable narration asset "
                "entries with source_tool/model; provider consistency cannot "
                "verify production_proposal.audio_contract."
            )
        else:
            issues.append(
                "production_proposal.audio_contract is locked but "
                "asset_manifest.assets[] has no narration asset entries with "
                "source_tool/model; provider consistency cannot verify TTS "
                "output."
            )
        return issues

    if section_ids and not narration_files:
        issues.append(
            "script.sections requires asset_manifest.narration_files entries "
            "for every section before compose; no narration_files inventory "
            "was provided."
        )
        return issues

    narration_asset_paths = {
        asset.get("path").strip()
        for asset in narration_assets
        if isinstance(asset.get("path"), str) and asset.get("path").strip()
    }
    narration_file_paths: set[str] = set()
    narration_file_sections: set[str] = set()
    for idx, entry in enumerate(narration_files):
        section_id = entry.get("section_id")
        if isinstance(section_id, str) and section_id.strip():
            narration_file_sections.add(section_id.strip())

        file_path = entry.get("file")
        if isinstance(file_path, str) and file_path.strip():
            normalized_file = file_path.strip()
            narration_file_paths.add(normalized_file)
            if normalized_file not in narration_asset_paths:
                issues.append(
                    "asset_manifest.narration_files"
                    f"[{idx}].file {normalized_file!r} must have a matching "
                    "auditable asset_manifest.assets[] entry with "
                    "type='narration' (or narration audio), source_tool, and "
                    "model."
                )
        else:
            issues.append(
                f"asset_manifest.narration_files[{idx}].file must be non-empty."
            )

    if section_ids:
        expected_sections = set(section_ids)
        missing_sections = sorted(expected_sections - narration_file_sections)
        if missing_sections:
            issues.append(
                "asset_manifest.narration_files must include every "
                "script.sections[].id before compose; missing "
                + ", ".join(repr(section_id) for section_id in missing_sections)
            )

        extra_sections = sorted(narration_file_sections - expected_sections)
        if extra_sections:
            issues.append(
                "asset_manifest.narration_files contains section_id value(s) "
                "not present in script.sections[].id: "
                + ", ".join(repr(section_id) for section_id in extra_sections)
            )

    return issues


def _drift_approval_candidates(
    source_tool: str | None,
    model: str | None,
    *,
    source_tool_matches: bool,
    model_matches: bool,
) -> set[str]:
    """Return decision selections that authorize the exact provider/model drift."""
    pair = (
        f"{source_tool}:{model}"
        if isinstance(source_tool, str)
        and source_tool.strip()
        and isinstance(model, str)
        and model.strip()
        else None
    )
    candidates: set[str] = set()

    if not source_tool_matches and not model_matches:
        if pair:
            candidates.add(pair)
    elif not source_tool_matches:
        if isinstance(source_tool, str) and source_tool.strip():
            candidates.add(source_tool)
        if pair:
            candidates.add(pair)
    elif not model_matches:
        if isinstance(model, str) and model.strip():
            candidates.add(model)
        if pair:
            candidates.add(pair)

    return candidates


def _visual_provider_locks(production_proposal: dict[str, Any]) -> list[dict[str, Any]]:
    visual_contract = production_proposal.get("visual_contract")
    if not isinstance(visual_contract, dict):
        return []
    locks = visual_contract.get("visual_asset_provider_locks")
    if not isinstance(locks, list):
        return []
    return [lock for lock in locks if isinstance(lock, dict)]


def _visual_asset_provider_matches_lock(
    asset: dict[str, Any],
    locks: list[dict[str, Any]],
) -> bool:
    asset_type = asset.get("type")
    source_tool = asset.get("source_tool")
    model = asset.get("model")
    for lock in locks:
        if lock.get("asset_type") != asset_type:
            continue
        if lock.get("source_tool") != source_tool:
            continue
        locked_model = lock.get("model")
        if isinstance(locked_model, str) and locked_model.strip():
            if model != locked_model:
                continue
        return True
    return False


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _validate_music_alignment(
    asset: dict[str, Any],
    *,
    music_strategy: str,
    asset_index: int,
) -> list[str]:
    """Validate beat/drop alignment evidence for strict music strategies."""
    if music_strategy not in ALIGNMENT_REQUIRED_MUSIC_STRATEGIES:
        return []

    prefix = f"music_assets[{asset_index}]"
    alignment = asset.get("music_alignment")
    if not isinstance(alignment, dict):
        expected = (
            "timing_sidecar_path"
            if music_strategy == "library_locked"
            else "beat_detection_report or beat_detection_report_path"
        )
        return [
            f"{prefix} uses music_strategy={music_strategy!r} and must include "
            f"asset_manifest.assets[].music_alignment with {expected}, "
            "target_peak_seconds, selected_peak_seconds, aligned_peak_seconds, "
            "and drift_seconds before compose."
        ]

    issues: list[str] = []
    alignment_strategy = alignment.get("strategy")
    if alignment_strategy != music_strategy:
        issues.append(
            f"{prefix}.music_alignment.strategy must equal "
            f"production_proposal.music_strategy={music_strategy!r}; got "
            f"{alignment_strategy!r}."
        )

    numeric_fields = (
        "target_peak_seconds",
        "selected_peak_seconds",
        "aligned_peak_seconds",
        "drift_seconds",
    )
    for field in numeric_fields:
        if not _is_number(alignment.get(field)):
            issues.append(
                f"{prefix}.music_alignment.{field} must be a numeric "
                "timestamp/drift value."
            )

    target_peak = alignment.get("target_peak_seconds")
    aligned_peak = alignment.get("aligned_peak_seconds")
    drift = alignment.get("drift_seconds")
    if _is_number(drift):
        if abs(float(drift)) > MAX_MUSIC_ALIGNMENT_DRIFT_SECONDS:
            issues.append(
                f"{prefix}.music_alignment.drift_seconds={float(drift):.3f} "
                "exceeds the +/-"
                f"{MAX_MUSIC_ALIGNMENT_DRIFT_SECONDS:.1f}s tolerance required "
                f"for music_strategy={music_strategy!r}."
            )
        if _is_number(target_peak) and _is_number(aligned_peak):
            calculated_drift = float(aligned_peak) - float(target_peak)
            if abs(calculated_drift - float(drift)) > 0.05:
                issues.append(
                    f"{prefix}.music_alignment.drift_seconds must match "
                    "aligned_peak_seconds - target_peak_seconds within 0.05s."
                )

    if music_strategy == "library_locked":
        sidecar = alignment.get("timing_sidecar_path")
        if not isinstance(sidecar, str) or not sidecar.strip():
            issues.append(
                f"{prefix}.music_alignment.timing_sidecar_path is required "
                "for music_strategy='library_locked'."
            )
    elif music_strategy == "search_align":
        report = alignment.get("beat_detection_report")
        report_path = alignment.get("beat_detection_report_path")
        has_report_path = isinstance(report_path, str) and bool(report_path.strip())
        has_report = isinstance(report, dict) and bool(report)
        if not has_report and not has_report_path:
            issues.append(
                f"{prefix}.music_alignment.beat_detection_report or "
                "beat_detection_report_path is required for "
                "music_strategy='search_align'."
            )
        if has_report:
            drops = report.get("drop_seconds")
            if not isinstance(drops, list) or not any(_is_number(drop) for drop in drops):
                issues.append(
                    f"{prefix}.music_alignment.beat_detection_report must include "
                    "non-empty numeric drop_seconds for search_align."
                )

    return issues


def check_provider_consistency(
    production_proposal: dict[str, Any],
    asset_manifest: dict[str, Any],
    decision_log: dict[str, Any] | None = None,
    *,
    script: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate proposal-locked provider/model choices against actual assets."""
    issues: list[str] = []
    approved_substitutions: list[dict[str, Any]] = []
    approved_budget_overage_decision: str | None = None

    audio_contract = production_proposal.get("audio_contract") or {}
    locked_voice_provider = audio_contract.get("voice_provider")
    locked_voice_model = audio_contract.get("voice_model")
    expected_tts_tool = EXPECTED_TTS_TOOLS.get(str(locked_voice_provider or ""))

    narration_assets = _narration_assets(asset_manifest)
    if isinstance(audio_contract, dict) and audio_contract:
        issues.extend(
            _validate_narration_inventory(
                asset_manifest,
                narration_assets,
                script=script,
            )
        )

    for idx, asset in enumerate(narration_assets):
        actual_tool = asset.get("source_tool")
        actual_model = asset.get("model")
        tool_matches = (
            expected_tts_tool is None
            or actual_tool == expected_tts_tool
        )
        model_matches = (
            locked_voice_model is None
            or actual_model == locked_voice_model
        )
        if tool_matches and model_matches:
            continue

        decision = _find_approved_substitution(
            decision_log,
            categories={"provider_selection", "voice_selection"},
            selected_candidates=_drift_approval_candidates(
                actual_tool,
                actual_model,
                source_tool_matches=tool_matches,
                model_matches=model_matches,
            ),
        )
        if decision:
            approved_substitutions.append(
                {
                    "kind": "narration_provider_model",
                    "asset_id": asset.get("id"),
                    "decision_id": decision.get("decision_id"),
                    "selected": decision.get("selected"),
                    "source_tool": actual_tool,
                    "model": actual_model,
                }
            )
            continue

        issues.append(
            "Narration provider/model drift requires a user-visible approved "
            "provider_selection or voice_selection decision: "
            f"production_proposal.audio_contract.voice_provider="
            f"{locked_voice_provider!r}, voice_model={locked_voice_model!r}, "
            f"expected source_tool={expected_tts_tool!r}; assets[{idx}] "
            f"uses source_tool={actual_tool!r}, model={actual_model!r}."
        )

    visual_locks = _visual_provider_locks(production_proposal)
    visual_assets = [
        asset
        for asset in asset_manifest.get("assets", []) or []
        if isinstance(asset, dict) and asset.get("type") in VISUAL_ASSET_TYPES
    ]
    for idx, asset in enumerate(visual_assets):
        if _visual_asset_provider_matches_lock(asset, visual_locks):
            continue

        actual_tool = asset.get("source_tool")
        actual_model = asset.get("model")
        matching_tool_lock = any(
            lock.get("asset_type") == asset.get("type")
            and lock.get("source_tool") == actual_tool
            for lock in visual_locks
        )
        matching_model_lock = any(
            lock.get("asset_type") == asset.get("type")
            and lock.get("model") == actual_model
            for lock in visual_locks
            if isinstance(lock.get("model"), str) and lock.get("model").strip()
        )
        decision = _find_approved_substitution(
            decision_log,
            categories={"provider_selection"},
            selected_candidates=_drift_approval_candidates(
                actual_tool,
                actual_model,
                source_tool_matches=matching_tool_lock,
                model_matches=matching_model_lock,
            ),
        )
        if decision:
            approved_substitutions.append(
                {
                    "kind": "visual_provider_model",
                    "asset_id": asset.get("id"),
                    "decision_id": decision.get("decision_id"),
                    "selected": decision.get("selected"),
                    "source_tool": actual_tool,
                    "model": actual_model,
                }
            )
            continue

        issues.append(
            "Visual provider/model drift requires a user-visible approved "
            "provider_selection decision: "
            "production_proposal.visual_contract.visual_asset_provider_locks "
            f"does not allow assets[{idx}] source_tool={actual_tool!r}, "
            f"model={actual_model!r}, type={asset.get('type')!r}."
        )

    music_strategy = production_proposal.get("music_strategy", "generative_loose")
    music_assets = _assets_by_type(asset_manifest, "music")
    music_file = asset_manifest.get("music_file")
    if not music_assets and not music_file:
        no_music_decision = _find_approved_music_strategy_selection(
            decision_log,
            selected_strategy="none",
        )
        if music_strategy != "none" and no_music_decision:
            decision, selected_strategy = no_music_decision
            approved_substitutions.append(
                {
                    "kind": "music_strategy",
                    "asset_id": None,
                    "decision_id": decision.get("decision_id"),
                    "selected": decision.get("selected"),
                    "locked_strategy": music_strategy,
                    "selected_strategy": selected_strategy,
                    "source_tool": None,
                    "model": None,
                }
            )
        elif music_strategy != "none":
            issues.append(
                f"production_proposal.music_strategy={music_strategy!r} requires "
                "a music asset or music_file before compose."
            )
    elif music_file and not music_assets:
        issues.append(
            "asset_manifest.music_file is present but assets[] has no "
            "auditable music entry with source_tool/model; provider consistency "
            f"cannot verify production_proposal.music_strategy={music_strategy!r}."
        )
    else:
        allowed_music_tools = (
            MUSIC_SOURCE_TOOLS_BY_STRATEGY.get(str(music_strategy), set())
            if music_strategy != "none"
            else set()
        )
        for idx, asset in enumerate(music_assets):
            actual_tool = asset.get("source_tool")
            actual_model = asset.get("model")
            if music_strategy != "none" and actual_tool in allowed_music_tools:
                issues.extend(
                    _validate_music_alignment(
                        asset,
                        music_strategy=str(music_strategy),
                        asset_index=idx,
                    )
                )
                continue

            if music_strategy == "none" and not _find_approved_music_strategy_change(
                decision_log,
                actual_tool=actual_tool,
            ):
                issues.append(
                    "production_proposal.music_strategy='none' but asset_manifest "
                    "contains a music asset or music_file. Do not mix background "
                    "music unless the proposal/music decision explicitly opts in."
                )
                continue

            strategy_decision = _find_approved_music_strategy_change(
                decision_log,
                actual_tool=actual_tool,
            )
            if strategy_decision:
                decision, selected_strategy = strategy_decision
                issues.extend(
                    _validate_music_alignment(
                        asset,
                        music_strategy=selected_strategy,
                        asset_index=idx,
                    )
                )
                approved_substitutions.append(
                    {
                        "kind": "music_strategy",
                        "asset_id": asset.get("id"),
                        "decision_id": decision.get("decision_id"),
                        "selected": decision.get("selected"),
                        "locked_strategy": music_strategy,
                        "selected_strategy": selected_strategy,
                        "source_tool": actual_tool,
                        "model": actual_model,
                    }
                )
                continue

            issues.append(
                "Music source path drift changes the locked music strategy and "
                "requires a user-visible approved music_strategy_selection "
                "decision selecting a strategy that allows the actual source: "
                f"production_proposal.music_strategy={music_strategy!r} "
                f"allows source_tool={sorted(allowed_music_tools)!r}; "
                f"music_assets[{idx}] uses source_tool={actual_tool!r}, "
                f"model={actual_model!r}."
            )

    approved_budget = production_proposal.get("approved_budget_usd")
    total_cost = asset_manifest.get("total_cost_usd")
    if (
        isinstance(approved_budget, (int, float))
        and isinstance(total_cost, (int, float))
        and float(total_cost) > float(approved_budget) + 0.005
    ):
        decision = _find_approved_budget_overage_decision(decision_log)
        if decision:
            approved_budget_overage_decision = decision.get("decision_id")
        else:
            issues.append(
                "asset_manifest.total_cost_usd exceeds "
                "production_proposal.approved_budget_usd "
                f"({float(total_cost):.4f} > {float(approved_budget):.4f}); "
                "continuing requires a user-visible approved budget_tradeoff "
                "decision before compose whose selected option is an explicit "
                "overage approval such as 'approve-overage'."
            )

    status = "PASS" if not issues else "FAIL"
    return {
        "status": status,
        "locked_voice_provider": locked_voice_provider,
        "locked_voice_model": locked_voice_model,
        "expected_tts_tool": expected_tts_tool,
        "narration_assets_checked": len(narration_assets),
        "narration_files_checked": len(_narration_file_entries(asset_manifest)),
        "script_sections_checked": len(_script_section_ids(script)),
        "visual_assets_checked": len(visual_assets),
        "music_assets_checked": len(music_assets),
        "approved_substitutions": approved_substitutions,
        "approved_budget_overage_decision": approved_budget_overage_decision,
        "issues": issues,
    }


def check_project(project_dir: Path) -> dict[str, Any]:
    proposal = _load_artifact(project_dir, "production_proposal.json")
    asset_manifest = _load_artifact(project_dir, "asset_manifest.json")
    decision_log = _load_decision_log(project_dir)
    try:
        script = _load_artifact(project_dir, "script.json")
    except FileNotFoundError:
        script = None
    return check_provider_consistency(
        proposal,
        asset_manifest,
        decision_log,
        script=script,
    )


class ProviderConsistencyCheck(BaseTool):
    name = "provider_consistency_check"
    version = "0.1.0"
    tier = ToolTier.CORE
    capability = "validation"
    provider = "video_production_buddy"
    stability = ToolStability.PRODUCTION
    execution_mode = ExecutionMode.SYNC
    determinism = Determinism.DETERMINISTIC
    runtime = ToolRuntime.LOCAL
    resource_profile = ResourceProfile(cpu_cores=1, ram_mb=64, disk_mb=1, network_required=False)
    idempotency_key_fields = [
        "project_dir",
        "production_proposal",
        "asset_manifest",
        "decision_log",
        "script",
    ]
    capabilities = [
        "validate_asset_provider_locks",
        "detect_silent_tts_provider_swap",
        "validate_music_strategy_assets",
        "validate_provider_selection_decision",
        "validate_approved_budget_not_exceeded",
        "validate_visual_asset_provider_locks",
        "validate_music_strategy_source_path",
        "validate_music_alignment_evidence",
        "validate_music_strategy_selection_decision",
        "validate_narration_section_coverage",
    ]
    best_for = [
        "blocking silent narration provider/model substitutions before compose",
        "blocking missing or unauditable narration inventories before compose",
        "blocking silent image/video provider/model substitutions before compose",
        "blocking music source substitutions that change production_proposal.music_strategy without a visible strategy decision",
        "ensuring no-music proposals do not accidentally publish with background music",
        "blocking asset spending above the approved proposal budget without a visible budget decision",
        "blocking library/search music beds that lack auditable drop alignment evidence",
    ]
    input_schema = {
        "type": "object",
        "properties": {
            "project_dir": {"type": "string"},
            "production_proposal": {"type": "object"},
            "asset_manifest": {"type": "object"},
            "decision_log": {"type": "object"},
            "script": {"type": "object"},
        },
        "anyOf": [
            {"required": ["project_dir"]},
            {"required": ["production_proposal", "asset_manifest"]},
        ],
    }
    output_schema = {
        "type": "object",
        "required": [
            "status",
            "narration_assets_checked",
            "visual_assets_checked",
            "music_assets_checked",
            "narration_files_checked",
            "script_sections_checked",
            "approved_substitutions",
            "issues",
        ],
        "properties": {
            "status": {"type": "string", "enum": ["PASS", "FAIL"]},
            "locked_voice_provider": {"type": ["string", "null"]},
            "locked_voice_model": {"type": ["string", "null"]},
            "expected_tts_tool": {"type": ["string", "null"]},
            "narration_assets_checked": {"type": "integer", "minimum": 0},
            "narration_files_checked": {"type": "integer", "minimum": 0},
            "script_sections_checked": {"type": "integer", "minimum": 0},
            "visual_assets_checked": {"type": "integer", "minimum": 0},
            "music_assets_checked": {"type": "integer", "minimum": 0},
            "approved_substitutions": {"type": "array", "items": {"type": "object"}},
            "approved_budget_overage_decision": {"type": ["string", "null"]},
            "issues": {"type": "array", "items": {"type": "string"}},
        },
    }
    user_visible_verification = [
        "Confirm assets use proposal-locked narration provider/model unless a user-approved provider decision exists",
        "Confirm every script section has an auditable narration file and matching narration asset entry",
        "Confirm visual assets use proposal-locked image/video providers unless a user-approved provider decision exists",
        "Confirm music assets follow production_proposal.music_strategy unless a user-approved music_strategy_selection decision changes the strategy",
        "Confirm music assets match production_proposal.music_strategy",
        "Confirm library_locked/search_align music assets include music_alignment evidence within +/-0.5s drift",
        "Confirm asset_manifest.total_cost_usd does not exceed production_proposal.approved_budget_usd unless a visible approved budget_tradeoff decision exists",
    ]

    def execute(self, inputs: dict[str, Any]) -> ToolResult:
        started = time.time()
        try:
            project_dir = inputs.get("project_dir")
            if isinstance(project_dir, str) and project_dir.strip():
                verdict = check_project(Path(project_dir))
            else:
                verdict = check_provider_consistency(
                    inputs["production_proposal"],
                    inputs["asset_manifest"],
                    inputs.get("decision_log"),
                    script=inputs.get("script"),
                )
        except Exception as exc:
            return ToolResult(success=False, error=str(exc), duration_seconds=round(time.time() - started, 2))

        success = verdict.get("status") == "PASS"
        return ToolResult(
            success=success,
            data=verdict,
            error=json.dumps(verdict.get("issues", []), sort_keys=True, allow_nan=False) if not success else None,
            duration_seconds=round(time.time() - started, 2),
        )


def _cli(argv: list[str]) -> int:
    if len(argv) != 2:
        print(
            "usage: python -m tools.validation.provider_consistency_check "
            "<project-dir>",
            file=sys.stderr,
        )
        return 2
    project_dir = Path(argv[1]).resolve()
    if not project_dir.exists():
        print(f"error: project dir not found: {project_dir}", file=sys.stderr)
        return 2
    verdict = check_project(project_dir)
    print(json.dumps(verdict, indent=2, allow_nan=False))
    return 0 if verdict["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(_cli(sys.argv))
