"""Product identity reference consistency validator.

This deterministic check runs before product-visible generated video clips are
accepted into the ad-video asset manifest. It verifies that every scene declared
as product-visible has either:

* an approved product_identity_reference used by generated visual assets, or
* an explicit user-approved risk waiver with text_only_waived conditioning.

CLI usage:
    python -m tools.validation.product_identity_consistency_check projects/<name>
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


REFERENCE_SOURCE_TYPES = {"user_provided", "generated", "external_url"}
RISK_WAIVER_DECISION_CATEGORY = "product_identity_reference_selection"
RISK_WAIVER_SELECTED_VALUE = "risk_accepted"


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


def _reference_path(reference: dict[str, Any]) -> str | None:
    return reference.get("selected_reference_image_path") or reference.get("selected_reference_url")


def _approval_is_present(reference: dict[str, Any]) -> bool:
    approval = reference.get("user_approval") or {}
    return (
        reference.get("approval_status") == "approved"
        and approval.get("approved") is True
        and bool(approval.get("approved_by"))
        and bool(approval.get("approved_at"))
    )


def _risk_waiver_is_approved(reference: dict[str, Any]) -> bool:
    waiver = reference.get("risk_waiver") or {}
    return (
        reference.get("source_type") == "risk_accepted"
        and reference.get("approval_status") == "approved"
        and waiver.get("user_approved") is True
        and bool(waiver.get("approved_by"))
        and bool(waiver.get("approved_at"))
    )


def _reference_is_approved(reference: dict[str, Any]) -> bool:
    source_type = reference.get("source_type")
    if source_type in REFERENCE_SOURCE_TYPES:
        return (
            _approval_is_present(reference)
            and bool(reference.get("reference_id"))
            and bool(_reference_path(reference))
        )
    if source_type == "risk_accepted":
        return _risk_waiver_is_approved(reference)
    if source_type == "not_applicable":
        return reference.get("approval_status") == "not_required"
    return False


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


def _normalized_token(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip().lower().replace("-", "_").replace(" ", "_")


def _asset_has_sourced_provenance(asset: dict[str, Any]) -> bool:
    subtype = _normalized_token(asset.get("subtype"))
    source_tool = _normalized_token(asset.get("source_tool"))
    return bool(
        subtype in SOURCED_ASSET_SUBTYPES
        or source_tool in SOURCED_ASSET_SOURCE_TOOLS
        or asset.get("original_url")
        or asset.get("license")
    )


def _risk_waiver_decision_is_approved(
    decision_log: dict[str, Any] | None,
    decision_id: str | None,
) -> bool:
    decision = _find_decision(decision_log, decision_id)
    if not isinstance(decision, dict):
        return False
    options = decision.get("options_considered")
    option_ids: set[str] = set()
    if isinstance(options, list):
        option_ids = {
            option.get("option_id")
            for option in options
            if isinstance(option, dict)
        }
    selected = decision.get("selected")
    return bool(
        decision.get("category") == RISK_WAIVER_DECISION_CATEGORY
        and decision.get("user_visible") is True
        and decision.get("user_approved") is True
        and selected == RISK_WAIVER_SELECTED_VALUE
        and selected in option_ids
    )


def _product_visible_scenes(scene_plan: dict[str, Any]) -> list[dict[str, Any]]:
    visible = []
    for scene in scene_plan.get("scenes", []) or []:
        product_visibility = scene.get("product_visibility", "none")
        reference_required = scene.get("product_reference_required") is True
        if reference_required or product_visibility in PRODUCT_VISIBLE_VALUES:
            visible.append(scene)
    return visible


def _visual_assets_for_scene(
    asset_manifest: dict[str, Any],
    scene_id: str,
) -> list[dict[str, Any]]:
    return [
        asset
        for asset in asset_manifest.get("assets", []) or []
        if asset.get("scene_id") == scene_id and asset.get("type") in VISUAL_ASSET_TYPES
    ]


def _scene_ids_in_plan(scene_plan: dict[str, Any]) -> set[str]:
    return {
        scene.get("id")
        for scene in scene_plan.get("scenes", []) or []
        if isinstance(scene, dict) and scene.get("id")
    }


def _conditioning_issue_for_reference(
    asset: dict[str, Any],
    reference: dict[str, Any],
) -> str | None:
    conditioning = asset.get("product_identity_conditioning")
    asset_id = asset.get("id", "<unknown>")
    if not conditioning:
        return (
            f"Asset {asset_id} belongs to a product-visible scene but has no "
            "product_identity_conditioning metadata."
        )

    mode = conditioning.get("conditioning_mode")
    source_type = reference.get("source_type")
    if source_type == "risk_accepted":
        if mode != "text_only_waived":
            return (
                f"Asset {asset_id} uses conditioning_mode={mode!r} but the "
                "product_identity_reference is a risk_accepted waiver; record "
                "text_only_waived with waiver_decision_id."
            )
        if not conditioning.get("waiver_decision_id"):
            return (
                f"Asset {asset_id} records text_only_waived without "
                "waiver_decision_id."
            )
        expected_decision_id = (reference.get("risk_waiver") or {}).get("decision_id")
        if expected_decision_id and conditioning.get("waiver_decision_id") != expected_decision_id:
            return (
                f"Asset {asset_id} records waiver_decision_id="
                f"{conditioning.get('waiver_decision_id')!r}, expected "
                f"{expected_decision_id!r} from product_identity_reference.risk_waiver."
            )
        return None

    if mode == "text_only_waived":
        return (
            f"Asset {asset_id} is text_only_waived even though an approved product "
            "identity reference exists."
        )

    reference_id = reference.get("reference_id")
    if conditioning.get("approved_reference_id") != reference_id:
        return (
            f"Asset {asset_id} records approved_reference_id="
            f"{conditioning.get('approved_reference_id')!r}, expected {reference_id!r}."
        )

    expected_path = _reference_path(reference)
    if conditioning.get("approved_reference_path") != expected_path:
        return (
            f"Asset {asset_id} records approved_reference_path="
            f"{conditioning.get('approved_reference_path')!r}, expected {expected_path!r}."
        )

    return None


def check_product_identity_consistency(
    product_identity_reference: dict[str, Any],
    scene_plan: dict[str, Any],
    asset_manifest: dict[str, Any],
    decision_log: dict[str, Any] | None = None,
    generated_scene_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Validate product-visible scene conditioning against an approved reference.

    The decision_log is required when product-visible assets rely on a
    risk_accepted waiver, because that waiver must be backed by an explicit
    user-approved product_identity_reference_selection decision.

    When generated_scene_ids is provided, missing-asset checks are scoped to
    those selected/generated scene ids. This is used by the sample approval gate,
    where asset_manifest intentionally contains only sample assets while
    scene_plan still contains the full ad.
    """
    issues: list[str] = []
    warnings: list[str] = []
    product_visible_scenes = _product_visible_scenes(scene_plan)
    asset_required_scenes = product_visible_scenes
    asset_scope = "full"
    scene_ids_in_plan = _scene_ids_in_plan(scene_plan)
    for asset in asset_manifest.get("assets", []) or []:
        if not isinstance(asset, dict):
            continue
        scene_id = asset.get("scene_id")
        if (
            isinstance(scene_id, str)
            and scene_id not in scene_ids_in_plan
            and asset.get("type") in VISUAL_ASSET_TYPES
        ):
            asset_id = asset.get("id", "<unknown>")
            issues.append(
                f"Visual asset {asset_id} references scene_id={scene_id!r}, "
                "but that scene id was not found in scene_plan.scenes[]."
            )

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
            asset_required_scenes = [
                scene
                for scene in product_visible_scenes
                if scene.get("id") in generated_scene_id_set
            ]
            if product_visible_scenes and not asset_required_scenes:
                issues.append(
                    "generated_scene_ids was provided for a scoped product identity "
                    "check, but it does not include any product-visible scene from "
                    "scene_plan.scenes[]. Product-visible samples must include at "
                    "least one scene with product_visibility/product_reference_required "
                    "so product identity conditioning can be inspected."
                )
        else:
            asset_required_scenes = []
    conditioned_assets_checked = 0

    if not product_visible_scenes:
        if product_identity_reference.get("source_type") == "not_applicable":
            return {
                "status": "FAIL" if issues else "PASS",
                "issues": issues,
                "warnings": [],
                "summary": {
                    "product_visible_scenes": 0,
                    "asset_required_product_visible_scenes": 0,
                    "conditioned_assets_checked": 0,
                    "asset_scope": asset_scope,
                },
            }
        warnings.append(
            "No product-visible scenes were declared, but product_identity_reference "
            f"source_type={product_identity_reference.get('source_type')!r}. Verify the "
            "scene_plan product_visibility annotations are intentional."
        )
        return {
            "status": "FAIL" if issues else "WARN",
            "issues": issues,
            "warnings": warnings,
            "summary": {
                "product_visible_scenes": 0,
                "asset_required_product_visible_scenes": 0,
                "conditioned_assets_checked": 0,
                "asset_scope": asset_scope,
            },
        }

    source_type = product_identity_reference.get("source_type")
    if source_type == "not_applicable":
        issues.append(
            "Product-visible scenes require an approved product identity reference "
            "or explicit user-approved risk waiver; source_type is not_applicable."
        )
    elif source_type == "risk_accepted":
        if not _risk_waiver_is_approved(product_identity_reference):
            issues.append(
                "Product-visible scenes use a risk_accepted strategy, but the risk "
                "waiver is not explicitly user-approved."
            )
        waiver_decision_id = (product_identity_reference.get("risk_waiver") or {}).get("decision_id")
        if not _risk_waiver_decision_is_approved(decision_log, waiver_decision_id):
            issues.append(
                "Product-visible scenes use a risk_accepted strategy, but decision_log "
                "has no matching user-approved product_identity_reference_selection "
                f"decision with selected='risk_accepted' for decision_id={waiver_decision_id!r}."
            )
    elif source_type in REFERENCE_SOURCE_TYPES:
        if not _reference_is_approved(product_identity_reference):
            issues.append(
                "Product-visible scenes require an approved product identity reference "
                "with selected reference path/URL and user_approval metadata."
            )
    else:
        issues.append(f"Unknown product_identity_reference.source_type={source_type!r}.")

    for scene in asset_required_scenes:
        scene_id = scene.get("id", "<unknown>")
        visual_assets = _visual_assets_for_scene(asset_manifest, scene_id)
        if not visual_assets:
            issues.append(
                f"Product-visible scene {scene_id} has no generated visual asset in "
                "asset_manifest.assets[]."
            )
            continue

        for asset in visual_assets:
            if _asset_has_sourced_provenance(asset):
                continue
            conditioned_assets_checked += 1
            issue = _conditioning_issue_for_reference(asset, product_identity_reference)
            if issue:
                issues.append(issue)
                continue

            conditioning = asset.get("product_identity_conditioning") or {}
            verdict = conditioning.get("fidelity_verdict")
            asset_id = asset.get("id", "<unknown>")
            if verdict == "FLAG":
                issues.append(
                    f"Asset {asset_id} has fidelity_verdict=FLAG against the approved "
                    "product identity reference."
                )
            elif verdict in {"WARN", "NOT_CHECKED"}:
                warnings.append(
                    f"Asset {asset_id} has fidelity_verdict={verdict}; asset review "
                    "must inspect product consistency before compose."
                )

    status = "FAIL" if issues else ("WARN" if warnings else "PASS")
    return {
        "status": status,
        "issues": issues,
        "warnings": warnings,
        "summary": {
            "product_visible_scenes": len(product_visible_scenes),
            "asset_required_product_visible_scenes": len(asset_required_scenes),
            "conditioned_assets_checked": conditioned_assets_checked,
            "asset_scope": asset_scope,
        },
    }


def check_project(
    project_dir: Path,
    generated_scene_ids: list[str] | None = None,
) -> dict[str, Any]:
    reference = _load_artifact(project_dir, "product_identity_reference.json")
    scene_plan = _load_artifact(project_dir, "scene_plan.json")
    asset_manifest = _load_artifact(project_dir, "asset_manifest.json")
    decision_log = _load_decision_log(project_dir)
    return check_product_identity_consistency(
        reference,
        scene_plan,
        asset_manifest,
        decision_log,
        generated_scene_ids=generated_scene_ids,
    )


class ProductIdentityConsistencyCheck(BaseTool):
    name = "product_identity_consistency_check"
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
        "product_identity_reference",
        "scene_plan",
        "asset_manifest",
        "decision_log",
        "generated_scene_ids",
    ]
    capabilities = [
        "validate_product_identity_reference",
        "validate_product_visible_asset_conditioning",
        "validate_product_identity_sample_scope",
    ]
    best_for = [
        "checking product-visible ad-video scenes against approved product references",
        "blocking text-only product generation unless a user-approved risk waiver exists",
    ]
    input_schema = {
        "type": "object",
        "properties": {
            "project_dir": {"type": "string"},
            "product_identity_reference": {"type": "object"},
            "scene_plan": {"type": "object"},
            "asset_manifest": {"type": "object"},
            "decision_log": {"type": "object"},
            "generated_scene_ids": {"type": "array", "items": {"type": "string"}},
        },
        "anyOf": [
            {"required": ["project_dir"]},
            {"required": ["product_identity_reference", "scene_plan", "asset_manifest"]},
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
        "Inspect product-visible sample and hero scenes against the approved reference",
        "Surface WARN fidelity verdicts before compose",
    ]

    def execute(self, inputs: dict[str, Any]) -> ToolResult:
        started = time.time()
        try:
            generated_scene_ids = inputs.get("generated_scene_ids")
            project_dir = inputs.get("project_dir")
            if isinstance(project_dir, str) and project_dir.strip():
                verdict = check_project(Path(project_dir), generated_scene_ids=generated_scene_ids)
            else:
                verdict = check_product_identity_consistency(
                    inputs["product_identity_reference"],
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
    if len(argv) < 2:
        print(
            "usage: python -m tools.validation.product_identity_consistency_check "
            "<project-dir> [generated_scene_id ...]",
            file=sys.stderr,
        )
        return 2
    project_dir = Path(argv[1]).resolve()
    if not project_dir.exists():
        print(f"error: project dir not found: {project_dir}", file=sys.stderr)
        return 2
    generated_scene_ids = argv[2:] or None
    verdict = check_project(project_dir, generated_scene_ids)
    print(json.dumps(verdict, indent=2, allow_nan=False))
    return 0 if verdict["status"] != "FAIL" else 1


if __name__ == "__main__":
    raise SystemExit(_cli(sys.argv))
