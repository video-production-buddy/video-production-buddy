"""Artifact schema loading and validation utilities."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import jsonschema

SCHEMA_DIR = Path(__file__).parent

ARTIFACT_NAMES = [
    "user_request",
    "research_brief",
    "proposal_packet",
    "brief",
    "intake_brief",
    "enriched_brief",
    "intelligence_brief",
    "production_bible",
    "idea_options",
    "production_proposal",
    "product_identity_reference",
    "script",
    "character_design",
    "rig_plan",
    "pose_library",
    "scene_plan",
    "action_timeline",
    "asset_manifest",
    "edit_decisions",
    "render_report",
    "publish_log",
    "review",
    "cost_log",
    "decision_log",
    "ui_form_config",
    "ui_response",
    "source_media_review",
    "final_review",
    "character_qa_report",
    "video_analysis_brief",
]


def load_schema(name: str) -> dict:
    """Load a JSON schema by artifact name."""
    path = SCHEMA_DIR / f"{name}.schema.json"
    if not path.exists():
        raise FileNotFoundError(f"Schema not found: {path}")
    with open(path) as f:
        return json.load(f)


def _validate_ad_video_script(data: dict[str, Any]) -> None:
    """Enforce ad-video script requirements that need pipeline context."""
    required_voice_performance = [
        "emotion",
        "intonation",
        "rhythm",
        "pace",
        "pause_after_seconds",
    ]
    for idx, section in enumerate(data.get("sections", []) or []):
        section_id = section.get("id", f"section-{idx}")
        speaker_directions = section.get("speaker_directions")
        if not isinstance(speaker_directions, str) or not speaker_directions.strip():
            raise jsonschema.ValidationError(
                "ad-video script section "
                f"{section_id!r} must include non-empty speaker_directions"
            )

        voice_performance = section.get("voice_performance")
        if not isinstance(voice_performance, dict):
            raise jsonschema.ValidationError(
                "ad-video script section "
                f"{section_id!r} must include voice_performance"
            )

        missing = [
            field
            for field in required_voice_performance
            if field not in voice_performance
        ]
        if missing:
            raise jsonschema.ValidationError(
                "ad-video script section "
                f"{section_id!r} voice_performance missing fields: {missing}"
            )


def _is_ad_video_script(data: dict[str, Any], pipeline_type: str | None) -> bool:
    if pipeline_type == "ad-video":
        return True
    if pipeline_type is not None:
        return False
    if data.get("pipeline") == "ad-video":
        return True
    metadata = data.get("metadata") or {}
    if isinstance(metadata, dict) and metadata.get("pipeline") == "ad-video":
        return True
    return data.get("style_mode") in {"animated", "cinematic"}


def validate_artifact(
    name: str,
    data: dict[str, Any],
    *,
    pipeline_type: str | None = None,
) -> None:
    """Validate artifact data against its schema. Raises on failure."""
    schema = load_schema(name)
    jsonschema.validate(instance=data, schema=schema)
    if name == "script" and _is_ad_video_script(data, pipeline_type):
        _validate_ad_video_script(data)


def list_schemas() -> list[str]:
    """List all available artifact schema names."""
    return [p.stem.replace(".schema", "") for p in SCHEMA_DIR.glob("*.schema.json")]
