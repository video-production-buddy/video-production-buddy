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

from schemas.artifacts import (
    ARTIFACT_NAMES,
    FORMAT_CHECKER,
    load_strict_json_object,
    validate_artifact,
)

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
    "research.intake": "intake_brief",
    "research.brief_enrichment": "enriched_brief",
    "research.intelligence": "intelligence_brief",
    "proposal.bible": "production_bible",
    "proposal.idea": "idea_options",
    "proposal.technical_proposal": "production_proposal",
    "script": "script",
    "scene_plan": "scene_plan",
    "assets": "asset_manifest",
    "edit": "edit_decisions",
    "compose": "render_report",
    "publish": "publish_log",
}

AD_VIDEO_STAGE_ALIASES = {
    "intake": "research.intake",
    "brief_enrichment": "research.brief_enrichment",
    "intelligence": "research.intelligence",
    "bible": "proposal.bible",
    "idea": "proposal.idea",
    "proposal": "proposal.technical_proposal",
}

AD_VIDEO_REVERSE_STAGE_ALIASES = {
    normalized: legacy for legacy, normalized in AD_VIDEO_STAGE_ALIASES.items()
}


def _normalize_stage_for_pipeline(stage: str, pipeline_type: str | None) -> str:
    if pipeline_type == "ad-video":
        return AD_VIDEO_STAGE_ALIASES.get(stage, stage)
    return stage


def _canonical_artifact_for_stage(stage: str, pipeline_type: str | None) -> str:
    """Return the canonical artifact name for a stage in its pipeline context."""
    stage = _normalize_stage_for_pipeline(stage, pipeline_type)
    if pipeline_type == "ad-video":
        return AD_VIDEO_CANONICAL_STAGE_ARTIFACTS[stage]

    if pipeline_type not in (None, LEGACY_PIPELINE_TYPE):
        from lib.pipeline_loader import get_stage_definition, load_pipeline

        manifest = load_pipeline(pipeline_type)
        stage_def = get_stage_definition(manifest, stage)
        if stage_def is not None:
            for artifact_name in stage_def.get("produces", []):
                if artifact_name in ARTIFACT_NAMES:
                    return artifact_name

    return CANONICAL_STAGE_ARTIFACTS[stage]


def _manifest_required_outputs_for_stage(
    stage: str, pipeline_type: str | None
) -> list[str]:
    """Return schema-backed outputs declared by the stage manifest."""
    if pipeline_type in (None, LEGACY_PIPELINE_TYPE):
        return []
    stage = _normalize_stage_for_pipeline(stage, pipeline_type)

    from lib.pipeline_loader import get_stage_definition, load_pipeline

    manifest = load_pipeline(pipeline_type)
    stage_def = get_stage_definition(manifest, stage)
    if stage_def is None:
        return []

    return [
        artifact_name
        for artifact_name in stage_def.get("produces", [])
        if artifact_name in ARTIFACT_NAMES
    ]


def _manifest_genui_required_gates_for_stage(
    stage: str,
    pipeline_type: str | None,
) -> list[dict[str, str]]:
    if pipeline_type in (None, LEGACY_PIPELINE_TYPE):
        return []
    stage = _normalize_stage_for_pipeline(stage, pipeline_type)

    from lib.pipeline_loader import (
        get_genui_required_gates_for_checkpoint,
        load_pipeline,
    )

    manifest = load_pipeline(pipeline_type)
    return get_genui_required_gates_for_checkpoint(manifest, stage)


# Additional artifacts that may be produced alongside canonical ones.
# These are not stage-defining but are required by governance contracts.
SUPPLEMENTARY_ARTIFACTS = {
    "source_media_review",  # Required before first planning stage when user media exists
    "final_review",         # Required by compose stage before presenting to user
    "video_analysis_brief", # Reference-video grounding artifact carried alongside stages
    "product_identity_reference",  # Required alongside ad-video asset manifests
}

REQUIRED_SUPPLEMENTARY_STAGE_ARTIFACTS = {
    ("ad-video", "proposal.technical_proposal"): ("decision_log",),
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

    try:
        from lib.pipeline_loader import load_pipeline_readonly, get_stage_order
        manifest = load_pipeline_readonly(pipeline_type)
        return get_stage_order(manifest)
    except (FileNotFoundError, Exception):
        # Graceful fallback: return all known stages in canonical order
        return list(STAGES)

CHECKPOINT_SCHEMA_PATH = (
    Path(__file__).resolve().parent.parent
    / "schemas"
    / "checkpoints"
    / "checkpoint.schema.json"
)

# Canonical project root. Checkpoints, artifacts, and the project marker all
# live under PROJECTS_DIR/<project_id>/ — this is the location the Backlot
# board watches. Callers may still pass a different pipeline_dir (tests do),
# but production runs should use the default.
from lib.paths import PROJECTS_DIR  # noqa: E402  (single source of truth)

PROJECT_MARKER_FILENAME = "project.json"
HISTORY_DIRNAME = "history"


class CheckpointValidationError(ValueError):
    """Raised when a checkpoint or its canonical artifacts are invalid."""


@lru_cache(maxsize=1)
def _load_checkpoint_schema() -> dict[str, Any]:
    return load_strict_json_object(CHECKPOINT_SCHEMA_PATH, context="checkpoint schema")


def _decision_option_ids(decision: dict[str, Any]) -> set[str]:
    options = decision.get("options_considered")
    if not isinstance(options, list):
        return set()
    return {
        option.get("option_id")
        for option in options
        if isinstance(option, dict) and isinstance(option.get("option_id"), str)
    }


def _effective_ad_video_music_strategy(artifacts: dict[str, Any] | None) -> str | None:
    """Return the latest approved ad-video music strategy in checkpoint context."""
    if not isinstance(artifacts, dict):
        return None

    production_proposal = artifacts.get("production_proposal")
    strategy = (
        production_proposal.get("music_strategy")
        if isinstance(production_proposal, dict)
        else None
    )

    decision_log = artifacts.get("decision_log")
    decisions = decision_log.get("decisions") if isinstance(decision_log, dict) else None
    if not isinstance(decisions, list):
        return strategy if isinstance(strategy, str) else None

    for decision in decisions:
        if not isinstance(decision, dict):
            continue
        selected = decision.get("selected")
        if (
            decision.get("category") == "music_strategy_selection"
            and decision.get("user_visible") is True
            and decision.get("user_approved") is True
            and isinstance(selected, str)
            and selected in _decision_option_ids(decision)
        ):
            strategy = selected

    return strategy if isinstance(strategy, str) else None


def _ad_video_assets_music_review_required(artifacts: dict[str, Any] | None) -> bool:
    """Whether the assets checkpoint needs music approval/evidence."""
    return _effective_ad_video_music_strategy(artifacts) != "none"


def filter_genui_required_gates_for_checkpoint(
    gates: list[dict[str, str]],
    *,
    checkpoint_stage: str,
    pipeline_type: str | None,
    artifacts: dict[str, Any] | None = None,
) -> list[dict[str, str]]:
    """Apply artifact-aware exceptions to manifest-declared GenUI gates."""
    if (
        pipeline_type == "ad-video"
        and checkpoint_stage == "assets"
        and not _ad_video_assets_music_review_required(artifacts)
    ):
        return [
            gate
            for gate in gates
            if not (
                gate.get("stage") == "assets"
                and gate.get("gate") == "music_review"
            )
        ]
    return gates


def _validate_artifacts_for_stage(
    stage: str,
    status: str,
    artifacts: dict[str, Any],
    pipeline_type: str | None = None,
) -> None:
    required_artifact = _canonical_artifact_for_stage(stage, pipeline_type)
    required_artifacts = [required_artifact]
    required_artifacts.extend(
        _manifest_required_outputs_for_stage(stage, pipeline_type)
    )
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
        and stage == "proposal.technical_proposal"
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
                if category == "render_runtime_selection":
                    runtime_options = _decision_option_ids(decision)
                    required_runtime_options = {"remotion", "hyperframes"}
                    missing_runtime_options = sorted(
                        required_runtime_options - runtime_options
                    )
                    if missing_runtime_options:
                        raise CheckpointValidationError(
                            "Ad-video proposal checkpoint "
                            "render_runtime_selection decision must include "
                            "Remotion and HyperFrames in options_considered; "
                            f"missing: {missing_runtime_options}"
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
                validation_context={
                    "checkpoint_stage": stage,
                    "checkpoint_status": status,
                },
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
    artifacts = checkpoint.get("artifacts")
    status = checkpoint.get("status")
    stage = checkpoint.get("stage")
    pipeline_type = checkpoint.get("pipeline_type")

    final_review_required = "final_review" in set(
        _manifest_required_outputs_for_stage(stage, pipeline_type)
        if isinstance(stage, str)
        else ()
    ) or "final_review" in REQUIRED_SUPPLEMENTARY_STAGE_ARTIFACTS.get(
        (pipeline_type or "", stage or ""),
        (),
    )

    if (
        stage == "compose"
        and status in {"completed", "awaiting_human"}
        and final_review_required
    ):
        final_review = (
            artifacts.get("final_review") if isinstance(artifacts, dict) else None
        )
        if not isinstance(final_review, dict) or final_review.get("status") != "pass":
            raise CheckpointValidationError(
                "Completed compose checkpoint requires "
                "final_review.status == 'pass'"
            )

    if (
        pipeline_type == "ad-video"
        and stage == "publish"
        and status in {"completed", "awaiting_human"}
    ):
        final_review = (
            artifacts.get("final_review") if isinstance(artifacts, dict) else None
        )
        if not isinstance(final_review, dict) or final_review.get("status") != "pass":
            raise CheckpointValidationError(
                "Completed ad-video publish checkpoint requires "
                "final_review.status == 'pass'"
            )

        render_report = (
            artifacts.get("render_report") if isinstance(artifacts, dict) else None
        )
        if not isinstance(render_report, dict):
            raise CheckpointValidationError(
                "Completed ad-video publish checkpoint requires render_report "
                "so publish_log can be validated against rendered outputs"
            )

    if (
        pipeline_type != "ad-video"
        or stage != "assets"
        or status != "completed"
    ):
        return

    ep_state = _checkpoint_ep_state(checkpoint)
    artifacts = checkpoint.get("artifacts")
    required_true_flags = ["sample_approved", "asset_review_approved"]
    if _ad_video_assets_music_review_required(
        artifacts if isinstance(artifacts, dict) else None
    ):
        required_true_flags.append("music_review_approved")
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
    if isinstance(stage, str):
        normalized_stage = _normalize_stage_for_pipeline(stage, pipeline_type)
        if normalized_stage != stage:
            checkpoint = dict(checkpoint)
            checkpoint["stage"] = normalized_stage
            stage = normalized_stage

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
        jsonschema.validate(
            instance=checkpoint,
            schema=_load_checkpoint_schema(),
            format_checker=FORMAT_CHECKER,
        )
    except jsonschema.ValidationError as exc:
        location = ".".join(str(part) for part in exc.path)
        location_suffix = f" at {location}" if location else ""
        raise CheckpointValidationError(
            f"Checkpoint failed schema validation{location_suffix}: {exc.message}"
        ) from exc


def _checkpoint_path(pipeline_dir: Path, project_id: str, stage: str) -> Path:
    return pipeline_dir / project_id / f"checkpoint_{stage}.json"


def _legacy_checkpoint_path(
    pipeline_dir: Path,
    project_id: str,
    stage: str,
) -> Path | None:
    legacy_stage = AD_VIDEO_REVERSE_STAGE_ALIASES.get(stage)
    if legacy_stage is None:
        return None
    return _checkpoint_path(pipeline_dir, project_id, legacy_stage)


def init_project(
    project_id: str,
    *,
    title: str,
    pipeline_type: str,
    pipeline_dir: Optional[Path] = None,
    style_playbook: Optional[str] = None,
) -> Path:
    """Initialize a project workspace with the canonical layout + marker file.

    Creates projects/<project_id>/ with the standard subdirectories and writes
    project.json — the marker the Backlot board uses to render a project's
    identity and stage rail before the first checkpoint exists.

    Idempotent: re-running preserves the original created_at and merges fields.
    Returns the project directory.
    """
    base = pipeline_dir or PROJECTS_DIR
    project_dir = base / project_id
    for sub in (
        "artifacts",
        "assets/images",
        "assets/video",
        "assets/audio",
        "assets/music",
        "renders",
    ):
        (project_dir / sub).mkdir(parents=True, exist_ok=True)

    marker_path = project_dir / PROJECT_MARKER_FILENAME
    marker: dict[str, Any] = {}
    if marker_path.exists():
        try:
            with open(marker_path) as f:
                marker = json.load(f)
        except (json.JSONDecodeError, OSError):
            marker = {}

    marker.setdefault("version", "1.0")
    marker.setdefault("created_at", datetime.now(timezone.utc).isoformat())
    marker["project_id"] = project_id
    marker["title"] = title
    marker["pipeline_type"] = pipeline_type
    if style_playbook is not None:
        marker["style_playbook"] = style_playbook

    with open(marker_path, "w") as f:
        json.dump(marker, f, indent=2)

    return project_dir


def _stage_requires_approval(pipeline_type: Optional[str], stage: str) -> Optional[bool]:
    """Read human_approval_default for a stage from its pipeline manifest.

    Returns None when the stage isn't declared in the manifest or no
    pipeline_type was given — the caller then falls back to the value the
    agent passed in.

    A *provided but unknown* pipeline_type raises: a typo must not silently
    disable gate enforcement (fail-closed, not fail-open). Other manifest
    load failures are logged and fall back — a corrupt manifest shouldn't
    strand an otherwise-valid run, but the degradation must be visible.
    """
    if not pipeline_type or pipeline_type == "unknown":
        return None
    from lib.pipeline_loader import get_stage_human_approval_default, load_pipeline_readonly
    try:
        manifest = load_pipeline_readonly(pipeline_type)
    except FileNotFoundError:
        raise CheckpointValidationError(
            f"Unknown pipeline_type {pipeline_type!r} — cannot resolve gate "
            f"policy for stage {stage!r}. Check the spelling against "
            f"pipeline_defs/*.yaml."
        )
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning(
            "Gate policy unavailable for pipeline %r (%s) — falling back to "
            "the caller's human_approval_required flag.", pipeline_type, exc,
        )
        return None
    return get_stage_human_approval_default(manifest, stage)


def _archive_superseded_checkpoint(path: Path, stage: str) -> None:
    """Copy an existing checkpoint into history/ before it is overwritten.

    Preserves the full run record: stage re-runs (script v1 → v2) and gate
    transitions (awaiting_human → completed) remain reconstructable. Repeated
    in_progress refreshes are NOT archived — they are partial-progress
    heartbeats, not versions.

    Archiving is best-effort and must never crash a checkpoint write: the
    Backlot watcher may hold the file open (Windows denies renames of open
    files), so we copy rather than move, and swallow archival I/O failures.
    """
    if not path.exists():
        return
    try:
        with open(path) as f:
            existing = json.load(f)
    except (json.JSONDecodeError, OSError):
        existing = {}
    if existing.get("status") == "in_progress":
        return

    try:
        import shutil
        stamp = str(existing.get("timestamp", ""))
        safe_stamp = "".join(c for c in stamp if c.isalnum()) or f"{path.stat().st_mtime_ns}"
        history_dir = path.parent / HISTORY_DIRNAME
        history_dir.mkdir(parents=True, exist_ok=True)
        target = history_dir / f"checkpoint_{stage}_{safe_stamp}.json"
        if target.exists():
            target = history_dir / f"checkpoint_{stage}_{safe_stamp}_{path.stat().st_mtime_ns}.json"
        shutil.copyfile(path, target)
    except OSError:
        import logging
        logging.getLogger(__name__).warning(
            "Could not archive superseded checkpoint %s to history/", path
        )


def _decision_log_path(pipeline_dir: Path, project_id: str) -> Path:
    return pipeline_dir / project_id / "decision_log.json"


def _assert_strict_json_serializable(payload: Any, context: str) -> None:
    try:
        json.dumps(payload, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise CheckpointValidationError(
            f"{context} must be strict JSON serializable: {exc}"
        ) from exc


def _load_checkpoint_object(path: Path, context: str) -> dict[str, Any]:
    try:
        return load_strict_json_object(path, context=context)
    except ValueError as exc:
        raise CheckpointValidationError(str(exc)) from exc


def _validate_manifest_genui_evidence_for_checkpoint(
    pipeline_dir: Path,
    project_id: str,
    *,
    stage: str,
    status: str,
    pipeline_type: str | None,
    artifacts: dict[str, Any] | None,
) -> None:
    if status != "completed":
        return
    gates = _manifest_genui_required_gates_for_stage(stage, pipeline_type)
    gates = filter_genui_required_gates_for_checkpoint(
        gates,
        checkpoint_stage=stage,
        pipeline_type=pipeline_type,
        artifacts=artifacts,
    )
    if not gates:
        return

    from lib.genui.journal import genui_required_gate_evidence_report

    report = genui_required_gate_evidence_report(
        pipeline_dir / project_id,
        project_id=project_id,
        pipeline_type=pipeline_type or LEGACY_PIPELINE_TYPE,
        required_gates=gates,
    )
    if report["ok"]:
        return

    missing = [
        f"{issue.get('stage')}.{issue.get('gate')}"
        for issue in report.get("issues", [])
    ]
    raise CheckpointValidationError(
        f"Completed {pipeline_type or LEGACY_PIPELINE_TYPE} checkpoint "
        f"{stage!r} requires GenUI evidence for gate(s): {missing}. "
        "Run registry tool genui_evidence_check for details, or use "
        "`python -m tools.validation.genui_evidence_check "
        f"{pipeline_dir / project_id} {pipeline_type or LEGACY_PIPELINE_TYPE} {stage}`."
    )


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
        existing = _load_checkpoint_object(path, f"decision log {path}")
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
        json.dump(existing, f, indent=2, allow_nan=False)


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
    # Backfill a missing pipeline_type from the project marker so that
    # omitting the kwarg doesn't quietly bypass gate enforcement.
    if not pipeline_type:
        marker = None
        marker_path = pipeline_dir / project_id / PROJECT_MARKER_FILENAME
        if marker_path.exists():
            try:
                with open(marker_path) as f:
                    marker = json.load(f)
            except (json.JSONDecodeError, OSError):
                marker = None
        if isinstance(marker, dict) and marker.get("pipeline_type"):
            pipeline_type = marker["pipeline_type"]

    valid_stages = (
        set(get_pipeline_stages(pipeline_type)) if pipeline_type
        else ALL_KNOWN_STAGES
    )
    if stage not in valid_stages:
        raise ValueError(
            f"Invalid stage: {stage!r} for pipeline {pipeline_type!r}. "
            f"Valid stages: {sorted(valid_stages)}"
        )

    # --- Gate enforcement (GI-4) ---
    # The pipeline manifest is the binding source of truth for whether a stage
    # gates on human approval; a caller may gate MORE strictly (e.g. a
    # manual_all checkpoint policy) but never less. A gated stage can only be
    # written "completed" with explicit evidence of approval
    # (human_approved=True). Skipping a gate is a hard error.
    #
    # Enforcement happens at write time only: pre-existing checkpoints written
    # before gating (or by hand) still read as completed — deliberate
    # back-compat so in-flight and legacy projects keep resuming.
    manifest_gate = _stage_requires_approval(pipeline_type, stage)
    gated = bool(manifest_gate) or human_approval_required
    if gated:
        human_approval_required = True
        if status == "completed" and not human_approved:
            gate_source = (
                f"human_approval_default: true in the {pipeline_type!r} manifest"
                if manifest_gate
                else "human_approval_required=True was passed by the caller"
            )
            raise CheckpointValidationError(
                f"GATE VIOLATION: stage {stage!r} requires human approval "
                f"({gate_source}) but status='completed' was written without "
                f"human_approved=True. Correct protocol: write "
                f"status='awaiting_human', present the artifact summary to the "
                f"user, END YOUR TURN, and only after the user approves "
                f"re-write with status='completed', human_approved=True."
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
    _validate_manifest_genui_evidence_for_checkpoint(
        pipeline_dir,
        project_id,
        stage=stage,
        status=status,
        pipeline_type=pipeline_type,
        artifacts=artifacts,
    )
    _assert_strict_json_serializable(checkpoint, "Checkpoint")

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
    # Serialize to a temp file first so a mid-write failure (disk full,
    # unserializable metadata) can never leave the stage with a truncated
    # current checkpoint; then archive the superseded file and swap in the
    # new one atomically.
    tmp_path = path.with_suffix(".json.tmp")
    with open(tmp_path, "w") as f:
        json.dump(checkpoint, f, indent=2)
    # Preserve run history: a superseded completed/awaiting_human checkpoint
    # is copied to history/ (stage versioning, gate audit trail, replay).
    _archive_superseded_checkpoint(path, stage)
    import os
    os.replace(tmp_path, path)

    return path


def read_checkpoint(
    pipeline_dir: Path,
    project_id: str,
    stage: str,
    *,
    pipeline_type: Optional[str] = None,
) -> Optional[dict[str, Any]]:
    """Read a checkpoint file. Returns None if not found."""
    normalized_stage = _normalize_stage_for_pipeline(stage, pipeline_type)
    candidate_paths: list[Path] = []
    if normalized_stage != stage:
        candidate_paths.append(_checkpoint_path(pipeline_dir, project_id, normalized_stage))
    candidate_paths.append(_checkpoint_path(pipeline_dir, project_id, stage))
    if pipeline_type is None and stage in AD_VIDEO_STAGE_ALIASES:
        candidate_paths.append(
            _checkpoint_path(pipeline_dir, project_id, AD_VIDEO_STAGE_ALIASES[stage])
        )
    legacy_path = _legacy_checkpoint_path(pipeline_dir, project_id, normalized_stage)
    if legacy_path is not None:
        candidate_paths.append(legacy_path)

    path = next((candidate for candidate in candidate_paths if candidate.exists()), None)
    if path is None:
        return None
    checkpoint = _load_checkpoint_object(path, f"checkpoint {path}")
    checkpoint_pipeline_type = checkpoint.get("pipeline_type") or pipeline_type
    if isinstance(checkpoint.get("stage"), str):
        checkpoint["stage"] = _normalize_stage_for_pipeline(
            checkpoint["stage"],
            checkpoint_pipeline_type,
        )
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

    checkpoint = _load_checkpoint_object(
        checkpoints[0],
        f"checkpoint {checkpoints[0]}",
    )
    pipeline_type = checkpoint.get("pipeline_type")
    if isinstance(checkpoint.get("stage"), str):
        checkpoint["stage"] = _normalize_stage_for_pipeline(
            checkpoint["stage"],
            pipeline_type,
        )
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
        if not cp or cp.get("status") != "completed":
            continue
        if pipeline_type and cp.get("pipeline_type") != pipeline_type:
            continue
        if cp:
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
