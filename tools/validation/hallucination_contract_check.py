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
from tools.validation.asset_contract import (
    PRODUCT_VISIBLE_VALUES,
    SOURCED_ASSET_SOURCE_TOOLS,
    SOURCED_ASSET_SUBTYPES,
    VISUAL_ASSET_TYPES,
)
from tools.validation._scene_scope import validate_scene_id_list


WAIVER_DECISION_CATEGORY = "hallucination_review_waiver"
WAIVER_SELECTED_VALUES = {"waive", "waiver", "human_waiver"}
GENERATED_ASSET_SUBTYPES = {"generated", "ai_generated", "synthetic"}
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
    return load_strict_json_object(path, context=f"artifact {path}")


def _load_decision_log(project_dir: Path) -> dict[str, Any] | None:
    for path in (
        project_dir / "decision_log.json",
        project_dir / "artifacts" / "decision_log.json",
    ):
        if path.exists():
            return load_strict_json_object(path, context=f"decision log {path}")
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
    # _scene_has_generated_visual_scope already checks type=="generated"
    # and _required_assets_generate_visuals, so those don't need repeating.
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
    # Scene has generated visual scope and no product-specific markers —
    # it's high risk because generated visuals can hallucinate.
    return True


def _scene_checks(scene: dict[str, Any]) -> list[dict[str, Any]]:
    checks = scene.get("hallucination_checks")
    if not isinstance(checks, list):
        return []
    return [check for check in checks if isinstance(check, dict)]


def _asset_has_sourced_provenance(asset: dict[str, Any]) -> bool:
    subtype = _normalized_token(asset.get("subtype"))
    source_tool = _normalized_token(asset.get("source_tool"))
    return bool(
        subtype in SOURCED_ASSET_SUBTYPES
        or source_tool in SOURCED_ASSET_SOURCE_TOOLS
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
    generated_scene_ids: list[str] | None = None,
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
    asset_scope = "full"
    generated_visual_asset_scene_ids = _generated_visual_asset_scene_ids(asset_manifest)
    scene_ids_in_plan = {
        scene.get("id")
        for scene in scene_plan.get("scenes", []) or []
        if isinstance(scene, dict) and scene.get("id")
    }
    for asset in asset_manifest.get("assets", []) or []:
        if not isinstance(asset, dict):
            continue
        scene_id = asset.get("scene_id")
        if (
            isinstance(scene_id, str)
            and scene_id not in scene_ids_in_plan
            and asset.get("type") in VISUAL_ASSET_TYPES
            and not _asset_has_sourced_provenance(asset)
            and _asset_has_generated_provenance(asset)
        ):
            asset_id = asset.get("id", "<unknown>")
            issues.append(
                f"Generated visual asset {asset_id} references scene_id={scene_id!r}, "
                "but that scene id was not found in scene_plan.scenes[]."
            )

    all_high_risk_scenes: dict[str, dict[str, Any]] = {}
    for scene in scene_plan.get("scenes", []) or []:
        if not isinstance(scene, dict):
            continue
        scene_id = scene.get("id", "<unknown>")
        if _scene_is_high_risk(
            scene,
            has_generated_visual_asset=scene_id in generated_visual_asset_scene_ids,
        ):
            all_high_risk_scenes[scene_id] = scene

    high_risk_scenes = all_high_risk_scenes
    generated_scene_id_set: set[str] | None = None
    if generated_scene_ids is not None:
        asset_scope = "generated_scene_ids"
        generated_scene_ids, scene_id_issues, usable_scene_ids = validate_scene_id_list(
            generated_scene_ids,
            "generated_scene_ids",
        )
        issues.extend(scene_id_issues)
        if usable_scene_ids:
            generated_scene_id_set = set(generated_scene_ids)
            missing_scene_ids = sorted(generated_scene_id_set - scene_ids_in_plan)
            for scene_id in missing_scene_ids:
                issues.append(
                    f"Generated scene id {scene_id!r} was not found in scene_plan.scenes[]."
                )
            high_risk_scenes = {
                scene_id: scene
                for scene_id, scene in all_high_risk_scenes.items()
                if scene_id in generated_scene_id_set
            }
            if all_high_risk_scenes and not high_risk_scenes:
                issues.append(
                    "generated_scene_ids was provided for a scoped hallucination "
                    "review, but it does not include any high-risk generated scene "
                    "from scene_plan.scenes[]. Generated samples must include at "
                    "least one high-risk generated scene so hallucination checks can "
                    "be inspected before sample approval."
                )
        else:
            high_risk_scenes = {}

    scene_check_map: dict[str, dict[str, dict[str, Any]]] = {}

    for scene_id, scene in high_risk_scenes.items():
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
                if check_id in by_id:
                    issues.append(
                        f"High-risk generated scene {scene_id} has duplicate "
                        f"hallucination check id {check_id!r}; check ids must "
                        "be unique so asset review verdicts map unambiguously."
                    )
                    continue
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
        seen_verdict_ids: set[str] = set()
        for verdict in verdicts:
            check_id = verdict.get("check_id")
            if not isinstance(check_id, str) or not check_id:
                continue
            if check_id in seen_verdict_ids:
                issues.append(
                    f"Generated visual asset {asset_id} has duplicate "
                    f"hallucination_review verdict id {check_id!r}; verdict "
                    "ids must be unique for scene check auditability."
                )
            seen_verdict_ids.add(check_id)

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
            "asset_scope": asset_scope,
        },
    }


def check_project(
    project_dir: Path,
    generated_scene_ids: list[str] | None = None,
) -> dict[str, Any]:
    production_bible = _load_artifact(project_dir, "production_bible.json")
    scene_plan = _load_artifact(project_dir, "scene_plan.json")
    asset_manifest = _load_artifact(project_dir, "asset_manifest.json")
    decision_log = _load_decision_log(project_dir)
    return check_hallucination_contract(
        production_bible,
        scene_plan,
        asset_manifest,
        decision_log,
        generated_scene_ids=generated_scene_ids,
    )


class HallucinationContractCheck(BaseTool):
    name = "hallucination_contract_check"
    version = "0.1.0"
    tier = ToolTier.CORE
    capability = "validation"
    provider = "video_production_buddy"
    stability = ToolStability.PRODUCTION
    execution_mode = ExecutionMode.SYNC
    determinism = Determinism.DETERMINISTIC
    runtime = ToolRuntime.LOCAL
    resource_profile = ResourceProfile(cpu_cores=1, ram_mb=128, disk_mb=1, network_required=False)
    idempotency_key_fields = [
        "project_dir",
        "production_bible",
        "scene_plan",
        "asset_manifest",
        "decision_log",
        "generated_scene_ids",
    ]
    capabilities = [
        "validate_ad_video_hallucination_contract",
        "validate_truth_contract_threading",
        "validate_generated_asset_keyframe_review",
        "block_hallucination_flags_before_compose",
    ]
    best_for = [
        "blocking ad-video compose when high-risk generated assets lack hallucination review",
        "checking user-approved hallucination-review waiver decisions",
    ]
    input_schema = {
        "type": "object",
        "properties": {
            "project_dir": {"type": "string"},
            "production_bible": {"type": "object"},
            "scene_plan": {"type": "object"},
            "asset_manifest": {"type": "object"},
            "decision_log": {"type": "object"},
            "generated_scene_ids": {"type": "array", "items": {"type": "string"}},
        },
        "anyOf": [
            {"required": ["project_dir"]},
            {"required": ["production_bible", "scene_plan", "asset_manifest"]},
        ],
    }
    output_schema = {
        "type": "object",
        "required": ["status", "issues", "warnings", "summary"],
        "properties": {
            "status": {"type": "string", "enum": ["PASS", "WARN", "FAIL"]},
            "issues": {"type": "array"},
            "warnings": {"type": "array"},
            "summary": {"type": "object"},
        },
    }
    user_visible_verification = [
        "Review start/mid/end keyframes for high-risk generated video assets",
        "Surface WARN verdicts and user-approved waivers before asset approval",
    ]

    def execute(self, inputs: dict[str, Any]) -> ToolResult:
        started = time.time()
        try:
            generated_scene_ids = inputs.get("generated_scene_ids")
            project_dir = inputs.get("project_dir")
            if isinstance(project_dir, str) and project_dir.strip():
                verdict = check_project(
                    Path(project_dir),
                    generated_scene_ids=generated_scene_ids,
                )
            else:
                verdict = check_hallucination_contract(
                    inputs["production_bible"],
                    inputs["scene_plan"],
                    inputs["asset_manifest"],
                    inputs.get("decision_log"),
                    generated_scene_ids=generated_scene_ids,
                )
        except Exception as exc:
            return ToolResult(success=False, error=str(exc), duration_seconds=round(time.time() - started, 2))

        success = verdict.get("status") != "FAIL"
        return ToolResult(
            success=success,
            data=verdict,
            error=json.dumps(verdict.get("issues", []), sort_keys=True, allow_nan=False) if not success else None,
            duration_seconds=round(time.time() - started, 2),
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
    print(json.dumps(verdict, indent=2, allow_nan=False))
    return 0 if verdict["status"] != "FAIL" else 1


if __name__ == "__main__":
    raise SystemExit(_cli(sys.argv))
