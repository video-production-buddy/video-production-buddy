"""GenUI gate evidence validator.

Checks whether a project has the ui_interaction_journal evidence required by a
pipeline checkpoint or by an explicit list of GenUI gates.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any

from lib.checkpoint import filter_genui_required_gates_for_checkpoint
from lib.genui.journal import genui_required_gate_evidence_report
from lib.pipeline_loader import (
    get_genui_required_gates_for_checkpoint,
    load_pipeline,
)
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


def _project_id_from_dir(project_dir: Path, explicit_project_id: Any = None) -> str:
    project_id = str(explicit_project_id or "").strip()
    if project_id:
        return project_id
    if not project_dir.name:
        raise ValueError("project_id is required when project_dir has no name")
    return project_dir.name


def _dedupe_gates(gates: list[dict[str, Any] | str]) -> list[dict[str, Any] | str]:
    seen: set[tuple[str, str]] = set()
    deduped: list[dict[str, Any] | str] = []
    for gate in gates:
        if isinstance(gate, str):
            separator = ":" if ":" in gate else "."
            parts = gate.split(separator, 1)
            key = (
                parts[0].strip() if len(parts) == 2 else "",
                parts[1].strip() if len(parts) == 2 else "",
            )
        else:
            key = (str(gate.get("stage") or "").strip(), str(gate.get("gate") or "").strip())
        if key in seen:
            continue
        seen.add(key)
        deduped.append(gate)
    return deduped


def _load_project_artifact_context(project_dir: Path) -> dict[str, Any]:
    artifact_dir = project_dir / "artifacts"
    artifacts: dict[str, Any] = {}
    for artifact_name in ("production_proposal", "decision_log", "asset_manifest"):
        path = artifact_dir / f"{artifact_name}.json"
        if not path.exists():
            continue
        artifacts[artifact_name] = load_strict_json_object(
            path,
            context=f"GenUI evidence artifact context {path}",
        )
    return artifacts


def check_genui_evidence(
    project_dir: Path,
    *,
    pipeline_type: str,
    checkpoint_stage: str | None = None,
    required_gates: list[dict[str, Any] | str] | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    """Return a checkpoint-ready verdict for required GenUI evidence."""
    gates: list[dict[str, Any] | str] = []
    if checkpoint_stage:
        manifest = load_pipeline(pipeline_type)
        manifest_gates = get_genui_required_gates_for_checkpoint(
            manifest,
            checkpoint_stage,
        )
        manifest_gates = filter_genui_required_gates_for_checkpoint(
            manifest_gates,
            checkpoint_stage=checkpoint_stage,
            pipeline_type=pipeline_type,
            artifacts=_load_project_artifact_context(project_dir),
        )
        gates.extend(manifest_gates)
    gates.extend(required_gates or [])
    gates = _dedupe_gates(gates)

    project_id_value = _project_id_from_dir(project_dir, project_id)
    if not gates:
        return {
            "status": "PASS",
            "can_complete_checkpoint": True,
            "project_id": project_id_value,
            "pipeline_type": pipeline_type,
            "checkpoint_stage": checkpoint_stage,
            "required_gates": [],
            "evidence": [],
            "issues": [],
            "message": "No GenUI evidence gates are required for this check.",
        }

    report = genui_required_gate_evidence_report(
        project_dir,
        project_id=project_id_value,
        pipeline_type=pipeline_type,
        required_gates=gates,
    )
    return {
        **report,
        "status": "PASS" if report["ok"] else "FAIL",
        "can_complete_checkpoint": bool(report["ok"]),
        "checkpoint_stage": checkpoint_stage,
    }


class GenUIEvidenceCheck(BaseTool):
    name = "genui_evidence_check"
    version = "0.1.0"
    tier = ToolTier.CORE
    capability = "validation"
    provider = "video_production_buddy"
    stability = ToolStability.BETA
    execution_mode = ExecutionMode.SYNC
    determinism = Determinism.DETERMINISTIC
    runtime = ToolRuntime.LOCAL
    resource_profile = ResourceProfile(cpu_cores=1, ram_mb=64, disk_mb=1, network_required=False)
    idempotency_key_fields = [
        "project_dir",
        "project_id",
        "pipeline_type",
        "checkpoint_stage",
        "required_gates",
    ]
    capabilities = [
        "validate_genui_gate_evidence",
        "preflight_checkpoint_genui_requirements",
        "validate_ui_interaction_journal",
        "detect_agent_native_ui_bypass",
    ]
    supports = {
        "manifest_declared_gates": True,
        "explicit_required_gates": True,
        "canonical_writes": False,
        "side_effect_free": True,
    }
    best_for = [
        "preflighting whether a checkpoint can complete its GenUI-required gates",
        "listing missing ui_session_response/ui_surface_response evidence before checkpoint writes",
        "checking whether CLI fallback evidence documents a real GenUI failure or user-declined browser path",
    ]
    not_good_for = [
        "creating GenUI sessions",
        "validating canonical video-production artifacts unrelated to GenUI interaction evidence",
    ]
    side_effects = []
    input_schema = {
        "type": "object",
        "required": ["project_dir", "pipeline_type"],
        "properties": {
            "project_dir": {"type": "string"},
            "project_id": {"type": "string"},
            "pipeline_type": {"type": "string"},
            "checkpoint_stage": {"type": "string"},
            "required_gates": {
                "type": "array",
                "items": {
                    "oneOf": [
                        {"type": "string"},
                        {
                            "type": "object",
                            "required": ["stage", "gate"],
                            "properties": {
                                "stage": {"type": "string"},
                                "gate": {"type": "string"},
                            },
                            "additionalProperties": True,
                        },
                    ]
                },
            },
        },
        "anyOf": [
            {"required": ["checkpoint_stage"]},
            {"required": ["required_gates"]},
        ],
    }
    output_schema = {
        "type": "object",
        "required": [
            "status",
            "can_complete_checkpoint",
            "project_id",
            "pipeline_type",
            "required_gates",
            "evidence",
            "issues",
        ],
        "properties": {
            "status": {"type": "string", "enum": ["PASS", "FAIL"]},
            "can_complete_checkpoint": {"type": "boolean"},
            "project_id": {"type": "string"},
            "pipeline_type": {"type": "string"},
            "checkpoint_stage": {"type": ["string", "null"]},
            "required_gates": {"type": "array", "items": {"type": "object"}},
            "evidence": {"type": "array", "items": {"type": "object"}},
            "issues": {"type": "array", "items": {"type": "object"}},
            "message": {"type": "string"},
        },
    }
    artifact_schema = {
        "reads": ["ui_interaction_journal", "ui_session_response", "ui_surface_response"],
        "canonical_writes": False,
    }
    user_visible_verification = [
        "Run before completing a checkpoint with GenUI-required gates.",
        "PASS means each required gate has a valid GenUI response or explicit GenUI fallback evidence.",
        "FAIL means the checkpoint should not be completed until missing evidence is resolved.",
    ]

    def execute(self, inputs: dict[str, Any]) -> ToolResult:
        started = time.time()
        try:
            project_dir = Path(str(inputs["project_dir"])).resolve()
            verdict = check_genui_evidence(
                project_dir,
                project_id=inputs.get("project_id"),
                pipeline_type=str(inputs["pipeline_type"]),
                checkpoint_stage=inputs.get("checkpoint_stage"),
                required_gates=inputs.get("required_gates"),
            )
        except Exception as exc:
            return ToolResult(
                success=False,
                error=str(exc),
                duration_seconds=round(time.time() - started, 2),
            )

        success = verdict.get("status") == "PASS"
        return ToolResult(
            success=success,
            data=verdict,
            error=(
                json.dumps(verdict.get("issues", []), sort_keys=True, allow_nan=False)
                if not success
                else None
            ),
            duration_seconds=round(time.time() - started, 2),
        )


def _cli(argv: list[str]) -> int:
    if len(argv) != 4:
        print(
            "usage: python -m tools.validation.genui_evidence_check "
            "<project-dir> <pipeline-type> <checkpoint-stage>",
            file=sys.stderr,
        )
        return 2
    project_dir = Path(argv[1]).resolve()
    if not project_dir.exists():
        print(f"error: project dir not found: {project_dir}", file=sys.stderr)
        return 2
    verdict = check_genui_evidence(
        project_dir,
        pipeline_type=argv[2],
        checkpoint_stage=argv[3],
    )
    print(json.dumps(verdict, indent=2, allow_nan=False))
    return 0 if verdict["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(_cli(sys.argv))
