"""Ad-video hallucination contract validator.

This deterministic gate checks the structural parts of the ad-video
hallucination-mitigation flow:

* production_bible carries a truth_contract,
* high-risk generated scenes declare hallucination_checks,
* generated visual assets for those scenes carry keyframe review metadata,
* blocker FLAG verdicts stop progress, and
* waivers are backed by an explicit user-approved decision_log entry.

The semantic judgment still belongs to the reviewing agent/human inspecting
keyframes. This module verifies that the judgment was recorded and that known
blockers cannot silently reach compose/publish.

CLI usage:
    python -m tools.validation.hallucination_contract_check projects/<name>
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


PRODUCT_VISIBLE_VALUES = {"background", "partial", "hero", "detail", "packshot"}
VISUAL_ASSET_TYPES = {"image", "video", "animation"}
NON_GENERATED_SCENE_TYPES = {"text_card", "transition", "diagram", "screen_recording"}
WAIVER_DECISION_CATEGORY = "hallucination_review_waiver"
WAIVER_SELECTED_VALUES = {"waive", "waiver", "human_waiver"}
GENERATED_ASSET_SUBTYPES = {"generated", "ai_generated", "synthetic"}
SOURCED_ASSET_SUBTYPES = {
    "source",
    "sourced",
    "provided",
    "user_provided",
    "stock",
    "recorded",
    "library",
}
TRUTH_CONTRACT_SECTIONS = {
    "objective_facts",
    "physical_constraints",
    "product_geometry_rules",
    "motion_coherence_rules",
    "values_guardrails",
}


def _load_artifact(project_dir: Path, name: str) -> dict[str, Any]:
    path = project_dir / "artifacts" / name
    if not path.exists():
        raise FileNotFoundError(f"missing artifact: {path}")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _load_decision_log(project_dir: Path) -> dict[str, Any] | None:
    for path in (
        project_dir / "decision_log.json",
        project_dir / "artifacts" / "decision_log.json",
    ):
        if path.exists():
            with open(path, encoding="utf-8") as f:
                return json.load(f)
    return None


def _truth_contract_issues(production_bible: dict[str, Any]) -> list[str]:
    truth_contract = production_bible.get("truth_contract")
    if not isinstance(truth_contract, dict):
        return [
            "production_bible.truth_contract is missing; bible-director must "
            "write objective facts, physical constraints, product geometry, "
            "motion coherence, and values guardrails before scene planning."
        ]

    issues: list[str] = []
    for section in sorted(TRUTH_CONTRACT_SECTIONS):
        rules = truth_contract.get(section)
        if not isinstance(rules, list) or not rules:
            issues.append(
                f"production_bible.truth_contract.{section} must contain at least one rule."
            )
    return issues


def _required_assets_generate_visuals(scene: dict[str, Any]) -> bool:
    for asset in scene.get("required_assets", []) or []:
        if not isinstance(asset, dict):
            continue
        asset_type = asset.get("type")
        source = asset.get("source")
        if source == "generate" and asset_type in VISUAL_ASSET_TYPES:
            return True
    return False


def _normalized_token(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip().lower().replace("-", "_").replace(" ", "_")


def _scene_has_generated_visual_scope(
    scene: dict[str, Any],
    *,
    has_generated_visual_asset: bool = False,
) -> bool:
    return (
        has_generated_visual_asset
        or scene.get("type") == "generated"
        or _required_assets_generate_visuals(scene)
    )


def _scene_is_high_risk(
    scene: dict[str, Any],
    *,
    has_generated_visual_asset: bool = False,
) -> bool:
    if not _scene_has_generated_visual_scope(
        scene,
        has_generated_visual_asset=has_generated_visual_asset,
    ):
        return False

    product_visibility = scene.get("product_visibility", "none")
    if product_visibility in PRODUCT_VISIBLE_VALUES:
        return True
    if scene.get("product_reference_required") is True:
        return True
    if scene.get("type") == "generated":
        return True
    if (
        scene.get("motion_required") is True
        and scene.get("type") not in NON_GENERATED_SCENE_TYPES
        and _required_assets_generate_visuals(scene)
    ):
        return True
    return False


def _scene_checks(scene: dict[str, Any]) -> list[dict[str, Any]]:
    checks = scene.get("hallucination_checks")
    if not isinstance(checks, list):
        return []
    return [check for check in checks if isinstance(check, dict)]


def _asset_has_sourced_provenance(asset: dict[str, Any]) -> bool:
    subtype = _normalized_token(asset.get("subtype"))
    return bool(
        subtype in SOURCED_ASSET_SUBTYPES
        or asset.get("original_url")
        or asset.get("license")
    )


def _asset_has_generated_provenance(asset: dict[str, Any]) -> bool:
    subtype = _normalized_token(asset.get("subtype"))
    if subtype in GENERATED_ASSET_SUBTYPES:
        return True
    return bool(
        isinstance(asset.get("product_identity_conditioning"), dict)
        or asset.get("prompt")
        or asset.get("seed") is not None
        or asset.get("model")
    )


def _asset_is_generated_visual(asset: dict[str, Any], scene: dict[str, Any]) -> bool:
    if asset.get("type") not in VISUAL_ASSET_TYPES:
        return False
    if _asset_has_sourced_provenance(asset):
        return False
    return _asset_has_generated_provenance(asset) or _required_assets_generate_visuals(scene)


def _generated_visual_asset_scene_ids(asset_manifest: dict[str, Any]) -> set[str]:
    scene_ids: set[str] = set()
    for asset in asset_manifest.get("assets", []) or []:
        if not isinstance(asset, dict):
            continue
        scene_id = asset.get("scene_id")
        if (
            isinstance(scene_id, str)
            and asset.get("type") in VISUAL_ASSET_TYPES
            and not _asset_has_sourced_provenance(asset)
            and _asset_has_generated_provenance(asset)
        ):
            scene_ids.add(scene_id)
    return scene_ids


def _selected_option_is_waiver(decision: dict[str, Any]) -> bool:
    selected = decision.get("selected")
    selected_token = _normalized_token(selected)
    if selected_token in WAIVER_SELECTED_VALUES:
        return True

    options = decision.get("options_considered")
    if not isinstance(options, list):
        return False
    for option in options:
        if not isinstance(option, dict) or option.get("option_id") != selected:
            continue
        return (
            _normalized_token(option.get("option_id")) in WAIVER_SELECTED_VALUES
            or _normalized_token(option.get("label")) in WAIVER_SELECTED_VALUES
        )
    return False


def _decision_is_user_approved(decision: dict[str, Any] | None) -> bool:
    return bool(
        isinstance(decision, dict)
        and decision.get("category") == WAIVER_DECISION_CATEGORY
        and decision.get("user_visible") is True
        and decision.get("user_approved") is True
        and _selected_option_is_waiver(decision)
    )


def _find_decision(decision_log: dict[str, Any] | None, decision_id: str | None) -> dict[str, Any] | None:
    if not decision_id or not isinstance(decision_log, dict):
        return None
    decisions = decision_log.get("decisions")
    if not isinstance(decisions, list):
        return None
    for decision in reversed(decisions):
        if isinstance(decision, dict) and decision.get("decision_id") == decision_id:
            return decision
    return None


def _waiver_decision_id(review: dict[str, Any]) -> str | None:
    decision_id = review.get("waiver_decision_id")
    if isinstance(decision_id, str) and decision_id:
        return decision_id

    action = review.get("regeneration_action") or {}
    decision_id = action.get("decision_id")
    if isinstance(decision_id, str) and decision_id:
        return decision_id
    return None


def _review_has_waiver(review: dict[str, Any]) -> bool:
    if review.get("status") == "WAIVED":
        return True
    action = review.get("regeneration_action") or {}
    if action.get("action") == "human_waiver":
        return True
    for verdict in review.get("check_verdicts", []) or []:
        if isinstance(verdict, dict) and verdict.get("status") == "WAIVED":
            return True
    return False


def check_hallucination_contract(
    production_bible: dict[str, Any],
    scene_plan: dict[str, Any],
    asset_manifest: dict[str, Any],
    decision_log: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate the ad-video hallucination review contract.

    Returns a verdict dict:
        {
          "status": "PASS" | "WARN" | "FAIL",
          "issues": [<str>, ...],
          "warnings": [<str>, ...],
          "summary": {...},
        }
    """
    issues = _truth_contract_issues(production_bible)
    warnings: list[str] = []
    waivers = 0
    reviewed_assets = 0

    high_risk_scenes: dict[str, dict[str, Any]] = {}
    scene_check_map: dict[str, dict[str, dict[str, Any]]] = {}
    generated_visual_asset_scene_ids = _generated_visual_asset_scene_ids(asset_manifest)

    for scene in scene_plan.get("scenes", []) or []:
        if not isinstance(scene, dict):
            continue
        scene_id = scene.get("id", "<unknown>")
        if not _scene_is_high_risk(
            scene,
            has_generated_visual_asset=scene_id in generated_visual_asset_scene_ids,
        ):
            continue

        high_risk_scenes[scene_id] = scene
        checks = _scene_checks(scene)
        if not checks:
            issues.append(
                f"High-risk generated scene {scene_id} has no hallucination_checks; "
                "scene-director must derive checks from production_bible.truth_contract."
            )
            scene_check_map[scene_id] = {}
            continue

        by_id: dict[str, dict[str, Any]] = {}
        for check in checks:
            check_id = check.get("check_id")
            if isinstance(check_id, str) and check_id:
                by_id[check_id] = check
        scene_check_map[scene_id] = by_id

    for asset in asset_manifest.get("assets", []) or []:
        if not isinstance(asset, dict):
            continue
        scene_id = asset.get("scene_id")
        if scene_id not in high_risk_scenes:
            continue
        if not _asset_is_generated_visual(asset, high_risk_scenes[scene_id]):
            continue

        generated_visual_asset_scene_ids.add(scene_id)
        asset_id = asset.get("id", "<unknown>")
        review = asset.get("hallucination_review")
        if not isinstance(review, dict):
            issues.append(
                f"Generated visual asset {asset_id} for high-risk scene {scene_id} "
                "has no hallucination_review."
            )
            continue

        reviewed_assets += 1
        status = review.get("status")
        if status in {None, "NOT_REVIEWED"}:
            issues.append(
                f"Generated visual asset {asset_id} is not reviewed "
                f"(hallucination_review.status={status!r})."
            )

        keyframes = review.get("keyframe_paths") or []
        if asset.get("type") == "video" and len(keyframes) < 3:
            issues.append(
                f"Video asset {asset_id} must record start/mid/end keyframes under "
                "hallucination_review.keyframe_paths."
            )
        elif len(keyframes) < 1:
            issues.append(
                f"Visual asset {asset_id} must record at least one reviewed keyframe path."
            )

        if status == "FLAG":
            issues.append(
                f"Generated visual asset {asset_id} has hallucination_review.status=FLAG."
            )
        elif status == "WARN":
            warnings.append(
                f"Generated visual asset {asset_id} has hallucination_review.status=WARN; "
                "surface it during asset review."
            )

        expected_checks = scene_check_map.get(scene_id, {})
        verdicts = [
            verdict
            for verdict in review.get("check_verdicts", []) or []
            if isinstance(verdict, dict)
        ]
        verdict_ids = {
            verdict.get("check_id")
            for verdict in verdicts
            if isinstance(verdict.get("check_id"), str)
        }
        missing_verdicts = sorted(set(expected_checks) - verdict_ids)
        if missing_verdicts:
            issues.append(
                f"Generated visual asset {asset_id} is missing hallucination_review "
                f"verdicts for scene checks: {missing_verdicts}."
            )

        for verdict in verdicts:
            check_id = verdict.get("check_id", "<unknown>")
            check_status = verdict.get("status")
            severity = verdict.get("severity") or expected_checks.get(
                check_id, {}
            ).get("severity")
            if check_status == "FLAG":
                issues.append(
                    f"Generated visual asset {asset_id} has FLAG verdict for "
                    f"hallucination check {check_id} (severity={severity!r})."
                )
            elif check_status == "WARN":
                warnings.append(
                    f"Generated visual asset {asset_id} has WARN verdict for "
                    f"hallucination check {check_id}; surface it during asset review."
                )

        if _review_has_waiver(review):
            waivers += 1
            decision_id = _waiver_decision_id(review)
            decision = _find_decision(decision_log, decision_id)
            if not _decision_is_user_approved(decision):
                issues.append(
                    f"Generated visual asset {asset_id} records a hallucination-review "
                    f"waiver, but decision_log has no user-approved waiver decision "
                    f"with category {WAIVER_DECISION_CATEGORY!r} "
                    "and a selected waiver option "
                    f"for decision_id={decision_id!r}."
                )
            else:
                warnings.append(
                    f"Generated visual asset {asset_id} uses a user-approved "
                    f"hallucination-review waiver ({decision_id})."
                )

    for scene_id in sorted(high_risk_scenes):
        if scene_id not in generated_visual_asset_scene_ids:
            issues.append(
                f"High-risk generated scene {scene_id} has no generated visual asset "
                "in asset_manifest.assets[]."
            )

    status_out = "FAIL" if issues else ("WARN" if warnings else "PASS")
    return {
        "status": status_out,
        "issues": issues,
        "warnings": warnings,
        "summary": {
            "high_risk_scenes": len(high_risk_scenes),
            "reviewed_assets": reviewed_assets,
            "waivers": waivers,
        },
    }


def check_project(project_dir: Path) -> dict[str, Any]:
    production_bible = _load_artifact(project_dir, "production_bible.json")
    scene_plan = _load_artifact(project_dir, "scene_plan.json")
    asset_manifest = _load_artifact(project_dir, "asset_manifest.json")
    decision_log = _load_decision_log(project_dir)
    return check_hallucination_contract(
        production_bible,
        scene_plan,
        asset_manifest,
        decision_log,
    )


def _cli(argv: list[str]) -> int:
    if len(argv) != 2:
        print(
            "usage: python -m tools.validation.hallucination_contract_check "
            "<project-dir>",
            file=sys.stderr,
        )
        return 2
    project_dir = Path(argv[1]).resolve()
    if not project_dir.exists():
        print(f"error: project dir not found: {project_dir}", file=sys.stderr)
        return 2
    verdict = check_project(project_dir)
    print(json.dumps(verdict, indent=2))
    return 0 if verdict["status"] != "FAIL" else 1


if __name__ == "__main__":
    raise SystemExit(_cli(sys.argv))
