"""Pipeline manifest loader.

Loads and validates pipeline YAML manifests from pipeline_defs/.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

import yaml
import jsonschema

from schemas.artifacts import load_strict_json_object

PIPELINE_DEFS_DIR = Path(__file__).resolve().parent.parent / "pipeline_defs"
SCHEMA_PATH = (
    Path(__file__).resolve().parent.parent
    / "schemas"
    / "pipelines"
    / "pipeline_manifest.schema.json"
)


from functools import lru_cache


@lru_cache(maxsize=8)
def _load_manifest_schema_cached(schema_path: str) -> dict:
    return load_strict_json_object(Path(schema_path), context="pipeline manifest schema")


def _load_manifest_schema() -> dict:
    return _load_manifest_schema_cached(str(SCHEMA_PATH))


def _sub_stage_is_checkpoint_unit(sub_stage: dict[str, Any]) -> bool:
    """Whether a sub-stage is a resumable execution unit.

    Existing sample/preview sub-stages are descriptive workflow steps. A child
    gate becomes a checkpoint unit when it owns execution behavior: a skill,
    artifacts, or an explicit checkpoint flag.
    """
    return bool(
        sub_stage.get("skill")
        or sub_stage.get("produces")
        or sub_stage.get("required_artifacts_in")
        or "checkpoint_required" in sub_stage
    )


def _iter_artifact_units(manifest: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    """Return manifest units that participate in artifact dependency ordering."""
    units: list[tuple[str, dict[str, Any]]] = []
    for stage in manifest.get("stages", []):
        stage_name = stage.get("name")
        if stage.get("required_artifacts_in") or stage.get("produces"):
            units.append((stage_name, stage))
        for sub_stage in stage.get("sub_stages", []):
            if sub_stage.get("required_artifacts_in") or sub_stage.get("produces"):
                units.append((f"{stage_name}.{sub_stage.get('name')}", sub_stage))
    return units


def _resolve_stage_unit(
    manifest: dict[str, Any],
    stage_name: str,
) -> dict[str, Any] | None:
    """Resolve a top-level stage or dotted child-gate id to its manifest block."""
    if "." in stage_name:
        parent_name, sub_stage_name = stage_name.split(".", 1)
        for stage in manifest.get("stages", []):
            if stage.get("name") != parent_name:
                continue
            for sub_stage in stage.get("sub_stages", []):
                if sub_stage.get("name") == sub_stage_name:
                    return sub_stage
            return None
    for stage in manifest.get("stages", []):
        if stage.get("name") == stage_name:
            return stage
    return None


def get_stage_definition(manifest: dict, stage_name: str) -> dict[str, Any] | None:
    """Return the manifest block for a top-level stage or dotted child gate."""
    return _resolve_stage_unit(manifest, stage_name)


def _validate_manifest_semantics(manifest: dict[str, Any]) -> None:
    """Validate cross-field manifest rules that JSON Schema cannot express."""
    seen_stages: set[str] = set()
    for stage in manifest.get("stages", []):
        stage_name = stage.get("name")
        if stage_name in seen_stages:
            raise ValueError(f"Duplicate stage name in pipeline manifest: {stage_name!r}")
        seen_stages.add(stage_name)
        seen_sub_stages: set[str] = set()
        for sub_stage in stage.get("sub_stages", []):
            sub_stage_raw_name = sub_stage.get("name")
            if sub_stage_raw_name in seen_sub_stages:
                raise ValueError(
                    f"Duplicate sub-stage name in pipeline manifest stage "
                    f"{stage_name!r}: {sub_stage_raw_name!r}"
                )
            seen_sub_stages.add(sub_stage_raw_name)

    produced_artifacts: set[str] = set()
    for unit_name, unit in _iter_artifact_units(manifest):
        for artifact_name in unit.get("required_artifacts_in", []):
            if artifact_name not in produced_artifacts:
                raise ValueError(
                    f"Stage {unit_name!r} requires artifact {artifact_name!r} "
                    "before any prior stage produces it"
                )
        produced_artifacts.update(unit.get("produces", []))


@lru_cache(maxsize=64)
def _load_pipeline_cached(name: str, defs_dir_key: str) -> dict[str, Any]:
    """Cached manifest load. Treat the returned dict as READ-ONLY."""
    return load_pipeline(name, Path(defs_dir_key) if defs_dir_key else None)


def load_pipeline_readonly(name: str, defs_dir: Optional[Path] = None) -> dict[str, Any]:
    """Load a manifest through a cache. The result MUST NOT be mutated.

    Manifests are immutable within a run; hot paths (gate checks on every
    checkpoint write, board state derivation) should use this instead of
    re-parsing YAML + re-validating the schema each call.
    """
    return _load_pipeline_cached(name, str(defs_dir) if defs_dir else "")


def load_pipeline(name: str, defs_dir: Optional[Path] = None) -> dict[str, Any]:
    """Load and validate a pipeline manifest by name.

    Args:
        name: Pipeline name (without .yaml extension).
        defs_dir: Override directory for pipeline definitions.

    Returns:
        Validated pipeline manifest dict.
    """
    if (
        not name
        or name in {".", ".."}
        or "/" in name
        or "\\" in name
        or Path(name).suffix
    ):
        raise ValueError(
            "Pipeline name must be a manifest stem, not a path or filename"
        )
    defs_dir = defs_dir or PIPELINE_DEFS_DIR
    path = defs_dir / f"{name}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"Pipeline manifest not found: {path}")

    with open(path) as f:
        manifest = yaml.safe_load(f)

    schema = _load_manifest_schema()
    jsonschema.validate(instance=manifest, schema=schema)
    _validate_manifest_semantics(manifest)

    return manifest


def list_pipelines(defs_dir: Optional[Path] = None) -> list[str]:
    """List all available pipeline manifest names."""
    defs_dir = defs_dir or PIPELINE_DEFS_DIR
    return [p.stem for p in defs_dir.glob("*.yaml")]


def _condition_is_active(condition: Optional[str], context: Optional[dict[str, Any]]) -> bool:
    """Evaluate a simple manifest condition against runtime context."""
    if not condition:
        return True
    if not context:
        return False
    return bool(context.get(condition))


def get_reference_input_config(manifest: dict) -> dict[str, Any]:
    """Return reference-input configuration, defaulting to disabled."""
    return manifest.get("reference_input", {}) or {}


def pipeline_supports_reference_input(manifest: dict) -> bool:
    """Whether the manifest declares support for reference-video input."""
    return bool(get_reference_input_config(manifest).get("supported", False))


def get_stage_sub_stages(
    manifest: dict,
    stage_name: str,
    *,
    context: Optional[dict[str, Any]] = None,
    include_inactive: bool = True,
) -> list[dict[str, Any]]:
    """Return sub-stage definitions for a stage.

    By default this returns all declared sub-stages so agents can inspect the
    full workflow shape. Pass ``include_inactive=False`` with context to filter
    to active sub-stages only.
    """
    for stage in manifest["stages"]:
        if stage["name"] != stage_name:
            continue
        sub_stages = list(stage.get("sub_stages", []))
        if include_inactive:
            return sub_stages
        return [
            sub_stage
            for sub_stage in sub_stages
            if _condition_is_active(sub_stage.get("condition"), context)
        ]
    return []


def get_stage_order(
    manifest: dict,
    *,
    include_sub_stages: bool = False,
    context: Optional[dict[str, Any]] = None,
) -> list[str]:
    """Extract the ordered list of stage names from a manifest.

    ``include_sub_stages=True`` exposes declarative sample/preview units to the
    agent without turning them into mandatory checkpoint stages. Sub-stages are
    emitted as ``<stage>.<sub_stage>``.
    """
    order: list[str] = []
    for stage in manifest["stages"]:
        order.append(stage["name"])
        if not include_sub_stages:
            continue
        for sub_stage in get_stage_sub_stages(
            manifest,
            stage["name"],
            context=context,
            include_inactive=context is None,
        ):
            order.append(f"{stage['name']}.{sub_stage['name']}")
    return order


def get_checkpoint_stage_order(
    manifest: dict,
    *,
    context: Optional[dict[str, Any]] = None,
) -> list[str]:
    """Return ordered resumable units for checkpoints and resume.

    Top-level stages remain the public pipeline shape. A top-level stage with
    artifact-producing child gates is represented by those dotted child units
    for precise checkpoint/resume behavior.
    """
    order: list[str] = []
    for stage in manifest["stages"]:
        checkpoint_children = [
            sub_stage
            for sub_stage in get_stage_sub_stages(
                manifest,
                stage["name"],
                context=context,
                include_inactive=context is None,
            )
            if _sub_stage_is_checkpoint_unit(sub_stage)
        ]
        if checkpoint_children:
            order.extend(
                f"{stage['name']}.{sub_stage['name']}"
                for sub_stage in checkpoint_children
            )
        else:
            order.append(stage["name"])
    return order


def get_checkpoint_stage_units(
    manifest: dict,
    *,
    context: Optional[dict[str, Any]] = None,
) -> list[dict[str, Any]]:
    """Return checkpoint units with parent/child metadata for UI surfaces."""
    units: list[dict[str, Any]] = []
    for unit_name in get_checkpoint_stage_order(manifest, context=context):
        unit = _resolve_stage_unit(manifest, unit_name)
        if unit is None:
            continue
        top_level_stage, separator, sub_stage = unit_name.partition(".")
        units.append(
            {
                "name": unit_name,
                "stage": top_level_stage,
                **({"sub_stage": sub_stage} if separator else {}),
                "definition": unit,
            }
        )
    return units


def get_required_tools(manifest: dict) -> set[str]:
    """Collect manifest-declared tools for preflight and capability audits."""
    tools: set[str] = set()
    tool_fields = (
        "required_tools",
        "optional_tools",
        "preferred_tools",
        "fallback_tools",
        "tools_available",
    )
    for stage in manifest["stages"]:
        for field in tool_fields:
            tools.update(stage.get(field, []))
        for sub_stage in stage.get("sub_stages", []):
            for field in tool_fields:
                tools.update(sub_stage.get(field, []))
    for production_mode in manifest.get("production_modes", []):
        tools.update(production_mode.get("required_tools", []))
        tools.update(production_mode.get("optional_tools", []))
    tools.update(get_reference_input_config(manifest).get("analysis_tools", []))
    return tools


def get_stage_skill(manifest: dict, stage_name: str) -> Optional[str]:
    """Get the skill path for an instruction-driven stage."""
    unit = _resolve_stage_unit(manifest, stage_name)
    return unit.get("skill") if unit else None


def get_stage_human_approval_default(manifest: dict, stage_name: str) -> Optional[bool]:
    """Whether a stage gates on human approval. None if the stage isn't declared.

    This is the single lookup used by gate enforcement (lib/checkpoint.py)
    and the Backlot board — keep them reading the same field the same way.
    """
    for stage in manifest["stages"]:
        if stage["name"] == stage_name:
            return bool(stage.get("human_approval_default", False))
    return None


def get_stage_review_focus(manifest: dict, stage_name: str) -> list[str]:
    """Get the review focus items for a stage."""
    unit = _resolve_stage_unit(manifest, stage_name)
    return unit.get("review_focus", []) if unit else []


def _genui_gate_from_unit(
    *,
    stage_name: str,
    unit_name: str,
    unit: dict[str, Any],
) -> dict[str, str] | None:
    if unit.get("genui_evidence_required") is not True:
        return None
    gate = str(unit.get("genui_evidence_gate") or unit_name)
    return {"stage": stage_name, "gate": gate}


def get_genui_required_gates_for_checkpoint(
    manifest: dict,
    checkpoint_stage: str,
) -> list[dict[str, str]]:
    """Return GenUI evidence gates required before completing a checkpoint.

    Top-level checkpoint stages collect their own requirement plus any child
    sub-stage requirements. Dotted checkpoint units collect only the targeted
    child gate.
    """
    unit = _resolve_stage_unit(manifest, checkpoint_stage)
    if unit is None:
        return []

    if "." in checkpoint_stage:
        parent_name, child_name = checkpoint_stage.split(".", 1)
        gate = _genui_gate_from_unit(
            stage_name=parent_name,
            unit_name=child_name,
            unit=unit,
        )
        return [gate] if gate else []

    gates: list[dict[str, str]] = []
    gate = _genui_gate_from_unit(
        stage_name=checkpoint_stage,
        unit_name=checkpoint_stage,
        unit=unit,
    )
    if gate:
        gates.append(gate)
    for sub_stage in unit.get("sub_stages", []):
        sub_gate = _genui_gate_from_unit(
            stage_name=checkpoint_stage,
            unit_name=str(sub_stage.get("name") or ""),
            unit=sub_stage,
        )
        if sub_gate:
            gates.append(sub_gate)
    return gates


# ---------------------------------------------------------------------------
# Capability-Extension Enforcement
# ---------------------------------------------------------------------------

class ExtensionNotPermitted(PermissionError):
    """Raised when a capability extension is used but not permitted by the pipeline."""


def check_extension_permitted(
    manifest: dict,
    extension_type: str,
) -> None:
    """Enforce that a capability extension is permitted by the pipeline manifest.

    Args:
        manifest: Loaded pipeline manifest dict.
        extension_type: One of 'custom_scripts', 'custom_playbooks',
                        'custom_skills', 'custom_tools'.

    Raises:
        ExtensionNotPermitted: If the extension is not allowed.
    """
    valid_extensions = {"custom_scripts", "custom_playbooks", "custom_skills", "custom_tools"}
    if extension_type not in valid_extensions:
        raise ValueError(
            f"Unknown extension type {extension_type!r}. "
            f"Valid types: {sorted(valid_extensions)}"
        )

    extensions = manifest.get("extensions", {})
    if not extensions.get(extension_type, False):
        raise ExtensionNotPermitted(
            f"Pipeline {manifest.get('name', 'unknown')!r} does not permit "
            f"{extension_type}. Set extensions.{extension_type}: true in the "
            f"pipeline manifest to allow this."
        )


def get_permitted_extensions(manifest: dict) -> dict[str, bool]:
    """Return the extension permission flags for a pipeline."""
    defaults = {
        "custom_scripts": False,
        "custom_playbooks": False,
        "custom_skills": False,
        "custom_tools": False,
    }
    extensions = manifest.get("extensions", {})
    return {k: extensions.get(k, v) for k, v in defaults.items()}
