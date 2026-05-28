"""Checkpoint writer/reader for pipeline state persistence.

Each stage writes a checkpoint after completion. The orchestrator uses
checkpoints to resume pipelines and to present state at human checkpoints.
"""

from __future__ import annotations

import json
from functools import lru_cache
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import jsonschema

from schemas.artifacts import ARTIFACT_NAMES, validate_artifact

# All known stages across all pipelines (used only for artifact name lookup).
ALL_KNOWN_STAGES = frozenset([
    "research", "proposal", "idea", "script", "scene_plan",
    "assets", "edit", "compose", "publish",
    "intake", "brief_enrichment", "intelligence", "bible",
])

# Backward-compatible alias — existing code / tests that import STAGES still work.
# New code should use get_pipeline_stages(pipeline_type) instead.
STAGES = ["research", "proposal", "idea", "script", "scene_plan",
          "assets", "edit", "compose", "publish"]
LEGACY_PIPELINE_TYPE = "unknown"

CANONICAL_STAGE_ARTIFACTS = {
    "research": "research_brief",
    "proposal": "proposal_packet",
    "idea": "brief",
    "script": "script",
    "scene_plan": "scene_plan",
    "assets": "asset_manifest",
    "edit": "edit_decisions",
    "compose": "render_report",
    "publish": "publish_log",
}

AD_VIDEO_CANONICAL_STAGE_ARTIFACTS = {
    "intake": "intake_brief",
    "brief_enrichment": "enriched_brief",
    "intelligence": "intelligence_brief",
    "bible": "production_bible",
    "idea": "idea_options",
    "proposal": "production_proposal",
    "script": "script",
    "scene_plan": "scene_plan",
    "assets": "asset_manifest",
    "edit": "edit_decisions",
    "compose": "render_report",
    "publish": "publish_log",
}


def _canonical_artifact_for_stage(stage: str, pipeline_type: str | None) -> str:
    """Return the canonical artifact name for a stage in its pipeline context."""
    if pipeline_type == "ad-video":
        return AD_VIDEO_CANONICAL_STAGE_ARTIFACTS[stage]

    if pipeline_type not in (None, LEGACY_PIPELINE_TYPE):
        from lib.pipeline_loader import load_pipeline

        manifest = load_pipeline(pipeline_type)
        for stage_def in manifest.get("stages", []):
            if stage_def.get("name") != stage:
                continue
            for artifact_name in stage_def.get("produces", []):
                if artifact_name in ARTIFACT_NAMES:
                    return artifact_name
            break

    return CANONICAL_STAGE_ARTIFACTS[stage]

# Additional artifacts that may be produced alongside canonical ones.
# These are not stage-defining but are required by governance contracts.
SUPPLEMENTARY_ARTIFACTS = {
    "source_media_review",  # Required before first planning stage when user media exists
    "final_review",         # Required by compose stage before presenting to user
    "video_analysis_brief", # Reference-video grounding artifact carried alongside stages
    "product_identity_reference",  # Required alongside ad-video asset manifests
}

REQUIRED_SUPPLEMENTARY_STAGE_ARTIFACTS = {
    ("ad-video", "proposal"): ("decision_log",),
    ("ad-video", "assets"): (
        "product_identity_reference",
        "production_proposal",
        "production_bible",
        "script",
        "scene_plan",
        "decision_log",
    ),
    ("ad-video", "edit"): ("production_proposal", "asset_manifest", "scene_plan"),
    ("ad-video", "compose"): (
        "final_review",
        "production_proposal",
        "production_bible",
    ),
    ("ad-video", "publish"): (
        "final_review",
        "production_proposal",
        "production_bible",
    ),
}


def get_pipeline_stages(pipeline_type: str | None) -> list[str]:
    """Return the ordered stage list for a specific pipeline.

    Falls back to STAGES (deterministic canonical order) only when pipeline_type
    is not provided or uses the legacy "unknown" sentinel.

    Previous versions used a set intersection here, which produced
    nondeterministic ordering. The fallback now uses a stable list. Explicit
    pipeline names must load successfully; typos should fail fast instead of
    resuming the wrong stage order.
    """
    if pipeline_type in (None, LEGACY_PIPELINE_TYPE):
        # Deterministic canonical fallback — sorted to ensure stable ordering
        import logging
        logging.getLogger(__name__).warning(
            "get_pipeline_stages called without a concrete pipeline_type — "
            "using canonical fallback order. Pass pipeline_type for correctness."
        )
        return list(STAGES)

    from lib.pipeline_loader import load_pipeline, get_stage_order
    manifest = load_pipeline(pipeline_type)
    return get_stage_order(manifest)

CHECKPOINT_SCHEMA_PATH = (
    Path(__file__).resolve().parent.parent
    / "schemas"
    / "checkpoints"
    / "checkpoint.schema.json"
)


class CheckpointValidationError(ValueError):
    """Raised when a checkpoint or its canonical artifacts are invalid."""


@lru_cache(maxsize=1)
def _load_checkpoint_schema() -> dict[str, Any]:
    with open(CHECKPOINT_SCHEMA_PATH) as f:
        return json.load(f)


def _validate_artifacts_for_stage(
    stage: str,
    status: str,
    artifacts: dict[str, Any],
    pipeline_type: str | None = None,
) -> None:
    required_artifact = _canonical_artifact_for_stage(stage, pipeline_type)
    required_artifacts = [required_artifact]
    required_artifacts.extend(
        REQUIRED_SUPPLEMENTARY_STAGE_ARTIFACTS.get((pipeline_type or "", stage), ())
    )
    missing_artifacts = [
        artifact_name
        for artifact_name in dict.fromkeys(required_artifacts)
        if artifact_name not in artifacts
    ]
    if status in {"completed", "awaiting_human"} and missing_artifacts:
        raise CheckpointValidationError(
            f"Stage {stage!r} with status {status!r} must include "
            f"required artifact(s) {missing_artifacts!r}"
        )

    if (
        pipeline_type == "ad-video"
        and stage == "proposal"
        and status in {"completed", "awaiting_human"}
    ):
        decision_log = artifacts.get("decision_log")
        decisions = decision_log.get("decisions") if isinstance(decision_log, dict) else None
        if not isinstance(decisions, list):
            raise CheckpointValidationError(
                "Ad-video proposal checkpoint must include decision_log.decisions"
            )
        required_categories = {
            "music_strategy_selection",
            "render_runtime_selection",
            "product_identity_reference_selection",
        }
        approved_categories = {
            decision.get("category")
            for decision in decisions
            if isinstance(decision, dict) and decision.get("user_approved") is True
        }
        missing_categories = sorted(required_categories - approved_categories)
        if missing_categories:
            raise CheckpointValidationError(
                "Ad-video proposal checkpoint decision_log must include "
                f"user-approved decisions for: {missing_categories}"
            )

        production_proposal = artifacts.get("production_proposal")
        if isinstance(production_proposal, dict):
            latest_approved_decisions = {
                decision.get("category"): decision
                for decision in decisions
                if isinstance(decision, dict) and decision.get("user_approved") is True
            }
            for category, proposal_field in (
                ("music_strategy_selection", "music_strategy"),
                ("render_runtime_selection", "render_runtime"),
                ("product_identity_reference_selection", "product_reference_strategy"),
            ):
                decision = latest_approved_decisions.get(category)
                selected = decision.get("selected") if isinstance(decision, dict) else None
                expected = production_proposal.get(proposal_field)
                if selected != expected:
                    raise CheckpointValidationError(
                        "Ad-video proposal checkpoint decision_log "
                        f"{category!r} selected {selected!r}, but "
                        f"production_proposal.{proposal_field} is {expected!r}"
                    )

    for artifact_name, artifact_data in artifacts.items():
        if artifact_name not in ARTIFACT_NAMES:
            continue
        if not isinstance(artifact_data, dict):
            raise CheckpointValidationError(
                f"Artifact {artifact_name!r} must be a JSON object matching its schema"
            )
        try:
            validate_artifact(
                artifact_name,
                artifact_data,
                pipeline_type=pipeline_type,
                related_artifacts=artifacts,
            )
        except Exception as exc:
            raise CheckpointValidationError(
                f"Artifact {artifact_name!r} failed schema validation: {exc}"
            ) from exc


def _checkpoint_ep_state(checkpoint: dict[str, Any]) -> dict[str, Any]:
    metadata = checkpoint.get("metadata")
    if not isinstance(metadata, dict):
        return {}
    ep_state = metadata.get("ep_state")
    if isinstance(ep_state, dict):
        return ep_state
    ep_state = metadata.get("EP_STATE")
    if isinstance(ep_state, dict):
        return ep_state
    return metadata


def _verdict_details(verdict: dict[str, Any]) -> str:
    issues = verdict.get("issues")
    if not isinstance(issues, list):
        return ""
    return "; ".join(str(issue) for issue in issues[:3])


def _raise_on_failed_assets_validator(
    validator_name: str,
    verdict: dict[str, Any],
    *,
    allow_warn: bool = False,
) -> None:
    allowed = {"PASS"}
    if allow_warn:
        allowed.add("WARN")
    if verdict.get("status") in allowed:
        return

    details = _verdict_details(verdict)
    suffix = f": {details}" if details else ""
    raise CheckpointValidationError(
        f"Completed ad-video assets checkpoint {validator_name} failed{suffix}"
    )


def _validate_ad_video_assets_cross_stage_contract(artifacts: dict[str, Any]) -> None:
    """Run asset-stage validators that require upstream context artifacts."""
    from tools.validation.hallucination_contract_check import (
        check_hallucination_contract,
    )
    from tools.validation.product_identity_consistency_check import (
        check_product_identity_consistency,
    )
    from tools.validation.provider_consistency_check import check_provider_consistency

    production_proposal = artifacts["production_proposal"]
    production_bible = artifacts["production_bible"]
    script = artifacts["script"]
    scene_plan = artifacts["scene_plan"]
    asset_manifest = artifacts["asset_manifest"]
    product_identity_reference = artifacts["product_identity_reference"]
    decision_log = artifacts["decision_log"]

    provider_verdict = check_provider_consistency(
        production_proposal,
        asset_manifest,
        decision_log,
        script=script,
    )
    _raise_on_failed_assets_validator(
        "provider_consistency_check",
        provider_verdict,
    )

    product_identity_verdict = check_product_identity_consistency(
        product_identity_reference,
        scene_plan,
        asset_manifest,
        decision_log,
    )
    _raise_on_failed_assets_validator(
        "product_identity_consistency_check",
        product_identity_verdict,
        allow_warn=True,
    )

    hallucination_verdict = check_hallucination_contract(
        production_bible,
        scene_plan,
        asset_manifest,
        decision_log,
    )
    _raise_on_failed_assets_validator(
        "hallucination_contract_check",
        hallucination_verdict,
        allow_warn=True,
    )


def _validate_ad_video_checkpoint_gate_state(checkpoint: dict[str, Any]) -> None:
    """Validate ad-video gate state that belongs to the checkpoint snapshot."""
    if (
        checkpoint.get("pipeline_type") == "ad-video"
        and checkpoint.get("stage") in {"compose", "publish"}
        and checkpoint.get("status") in {"completed", "awaiting_human"}
    ):
        artifacts = checkpoint.get("artifacts")
        final_review = (
            artifacts.get("final_review") if isinstance(artifacts, dict) else None
        )
        if not isinstance(final_review, dict) or final_review.get("status") != "pass":
            raise CheckpointValidationError(
                "Completed ad-video compose/publish checkpoint requires "
                "final_review.status == 'pass'"
            )

        if checkpoint.get("stage") == "publish":
            render_report = (
                artifacts.get("render_report") if isinstance(artifacts, dict) else None
            )
            if not isinstance(render_report, dict):
                raise CheckpointValidationError(
                    "Completed ad-video publish checkpoint requires render_report "
                    "so publish_log can be validated against rendered outputs"
                )

    if (
        checkpoint.get("pipeline_type") != "ad-video"
        or checkpoint.get("stage") != "assets"
        or checkpoint.get("status") != "completed"
    ):
        return

    ep_state = _checkpoint_ep_state(checkpoint)
    required_true_flags = (
        "sample_approved",
        "asset_review_approved",
        "music_review_approved",
    )
    missing_or_false = [
        flag
        for flag in required_true_flags
        if ep_state.get(flag) is not True
    ]
    if missing_or_false:
        raise CheckpointValidationError(
            "Completed ad-video assets checkpoint must include "
            "metadata.ep_state approval flags set to true: "
            f"{missing_or_false}"
        )

    artifacts = checkpoint.get("artifacts")
    reference = artifacts.get("product_identity_reference") if isinstance(artifacts, dict) else None
    if not isinstance(reference, dict):
        return

    source_type = reference.get("source_type")
    approval_status = reference.get("approval_status")
    if source_type in {"user_provided", "generated", "external_url"}:
        if approval_status != "approved":
            raise CheckpointValidationError(
                "Completed ad-video assets checkpoint product_identity_reference "
                f"must be approved; got approval_status={approval_status!r}"
            )
    elif source_type == "risk_accepted":
        if approval_status != "approved":
            raise CheckpointValidationError(
                "Completed ad-video assets checkpoint risk_accepted "
                "product_identity_reference must be approved"
            )
    elif source_type == "not_applicable":
        if approval_status != "not_required":
            raise CheckpointValidationError(
                "Completed ad-video assets checkpoint not_applicable "
                "product_identity_reference must have approval_status='not_required'"
            )

    _validate_ad_video_assets_cross_stage_contract(artifacts)


def validate_checkpoint(checkpoint: dict[str, Any]) -> None:
    """Validate checkpoint structure and canonical artifact payloads.

    Uses pipeline_type (if present) to resolve the valid stage list.
    Falls back to ALL_KNOWN_STAGES when pipeline_type is absent.
    """
    stage = checkpoint.get("stage")
    status = checkpoint.get("status")
    artifacts = checkpoint.get("artifacts")
    pipeline_type = checkpoint.get("pipeline_type")

    valid_stages = (
        set(get_pipeline_stages(pipeline_type)) if pipeline_type
        else ALL_KNOWN_STAGES
    )

    if not isinstance(stage, str) or stage not in valid_stages:
        raise CheckpointValidationError(
            f"Invalid stage: {stage!r} for pipeline {pipeline_type!r}. "
            f"Valid stages: {sorted(valid_stages)}"
        )
    if not isinstance(status, str):
        raise CheckpointValidationError(f"Invalid status: {status!r}")
    if not isinstance(artifacts, dict):
        raise CheckpointValidationError("Checkpoint artifacts must be a dictionary")

    _validate_artifacts_for_stage(stage, status, artifacts, pipeline_type)
    _validate_ad_video_checkpoint_gate_state(checkpoint)

    try:
        jsonschema.validate(instance=checkpoint, schema=_load_checkpoint_schema())
    except jsonschema.ValidationError as exc:
        raise CheckpointValidationError(f"Checkpoint failed schema validation: {exc.message}") from exc


def _checkpoint_path(pipeline_dir: Path, project_id: str, stage: str) -> Path:
    return pipeline_dir / project_id / f"checkpoint_{stage}.json"


def _decision_log_path(pipeline_dir: Path, project_id: str) -> Path:
    return pipeline_dir / project_id / "decision_log.json"


def _merge_decision_log(
    pipeline_dir: Path, project_id: str, new_log: dict[str, Any]
) -> None:
    """Append new decisions to the project-level decision log.

    Each stage may produce decisions. This function merges them into a
    single cumulative file so reviewers and the bench can inspect the
    full audit trail.
    """
    path = _decision_log_path(pipeline_dir, project_id)
    if path.exists():
        with open(path) as f:
            existing = json.load(f)
    else:
        existing = {
            "version": "1.0",
            "project_id": project_id,
            "decisions": [],
        }

    existing_ids = {d["decision_id"] for d in existing.get("decisions", [])}
    for decision in new_log.get("decisions", []):
        if decision.get("decision_id") not in existing_ids:
            existing["decisions"].append(decision)

    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(existing, f, indent=2)


def write_checkpoint(
    pipeline_dir: Path,
    project_id: str,
    stage: str,
    status: str,
    artifacts: dict[str, Any],
    *,
    pipeline_type: Optional[str] = None,
    style_playbook: Optional[str] = None,
    checkpoint_policy: str = "guided",
    human_approval_required: bool = False,
    human_approved: bool = False,
    review: Optional[dict] = None,
    cost_snapshot: Optional[dict] = None,
    error: Optional[str] = None,
    metadata: Optional[dict] = None,
) -> Path:
    """Write a checkpoint file for a pipeline stage."""
    valid_stages = (
        set(get_pipeline_stages(pipeline_type)) if pipeline_type
        else ALL_KNOWN_STAGES
    )
    if stage not in valid_stages:
        raise ValueError(
            f"Invalid stage: {stage!r} for pipeline {pipeline_type!r}. "
            f"Valid stages: {sorted(valid_stages)}"
        )

    checkpoint = {
        "version": "1.0",
        "project_id": project_id,
        "pipeline_type": pipeline_type or LEGACY_PIPELINE_TYPE,
        "stage": stage,
        "status": status,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "checkpoint_policy": checkpoint_policy,
        "human_approval_required": human_approval_required,
        "human_approved": human_approved,
        "artifacts": artifacts,
    }
    if style_playbook is not None:
        checkpoint["style_playbook"] = style_playbook
    if review is not None:
        checkpoint["review"] = review
    if cost_snapshot is not None:
        checkpoint["cost_snapshot"] = cost_snapshot
    if error is not None:
        checkpoint["error"] = error
    if metadata is not None:
        checkpoint["metadata"] = metadata

    # Validate before any side effect such as merging decision_log.json. This
    # prevents rejected checkpoints from leaving a corrupted cumulative log.
    validate_checkpoint(checkpoint)

    # Merge decision_log: if this checkpoint carries new decisions,
    # append them to the project-level decision log file, then write the
    # reference back into relevant artifacts so downstream consumers can find it.
    if "decision_log" in artifacts and isinstance(artifacts["decision_log"], dict):
        _merge_decision_log(pipeline_dir, project_id, artifacts["decision_log"])
        log_ref = str(_decision_log_path(pipeline_dir, project_id))

        # Write decision_log_ref into proposal/render artifacts when present.
        for artifact_key in ("proposal_packet", "production_proposal", "render_report"):
            if artifact_key in artifacts and isinstance(artifacts[artifact_key], dict):
                plan_or_top = artifacts[artifact_key]
                # proposal_packet stores it under production_plan
                if artifact_key == "proposal_packet":
                    plan = plan_or_top.get("production_plan")
                    if isinstance(plan, dict):
                        plan["decision_log_ref"] = log_ref
                else:
                    plan_or_top["decision_log_ref"] = log_ref

    validate_checkpoint(checkpoint)

    path = _checkpoint_path(pipeline_dir, project_id, stage)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(checkpoint, f, indent=2)

    return path


def read_checkpoint(
    pipeline_dir: Path, project_id: str, stage: str
) -> Optional[dict[str, Any]]:
    """Read a checkpoint file. Returns None if not found."""
    path = _checkpoint_path(pipeline_dir, project_id, stage)
    if not path.exists():
        return None
    with open(path) as f:
        checkpoint = json.load(f)
    validate_checkpoint(checkpoint)
    return checkpoint


def get_latest_checkpoint(
    pipeline_dir: Path, project_id: str
) -> Optional[dict[str, Any]]:
    """Find the most recent checkpoint for a project (by file mtime)."""
    project_dir = pipeline_dir / project_id
    if not project_dir.exists():
        return None

    checkpoints = sorted(
        project_dir.glob("checkpoint_*.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not checkpoints:
        return None

    with open(checkpoints[0]) as f:
        checkpoint = json.load(f)
    validate_checkpoint(checkpoint)
    return checkpoint


def get_completed_stages(
    pipeline_dir: Path, project_id: str, pipeline_type: str | None = None
) -> list[str]:
    """Return list of stages that have a completed checkpoint.

    When pipeline_type is provided, only checks stages defined in that
    pipeline's manifest — preventing false positives from leftover
    checkpoints of a different pipeline type.
    """
    stages_to_check = get_pipeline_stages(pipeline_type)
    completed = []
    for stage in stages_to_check:
        cp = read_checkpoint(pipeline_dir, project_id, stage)
        if cp and cp.get("status") == "completed":
            completed.append(stage)
    return completed


def get_next_stage(
    pipeline_dir: Path, project_id: str, pipeline_type: str | None = None
) -> Optional[str]:
    """Determine the next stage to run based on completed checkpoints.

    Uses pipeline-specific stage order so that pipelines with different
    stage sequences (e.g. cinematic vs explainer) progress correctly.
    """
    stages = get_pipeline_stages(pipeline_type) if pipeline_type else STAGES
    completed = set(get_completed_stages(pipeline_dir, project_id, pipeline_type))
    for stage in stages:
        if stage not in completed:
            return stage
    return None
