import json
from pathlib import Path

from tests.contracts.conftest import (
    _minimal_production_proposal,
    write_genui_required_gate_evidence,
)


def test_genui_evidence_check_fails_missing_manifest_declared_gate_evidence(tmp_path: Path):
    from tools.validation.genui_evidence_check import GenUIEvidenceCheck

    project_dir = tmp_path / "projects" / "demo-ad"
    result = GenUIEvidenceCheck().execute(
        {
            "project_dir": str(project_dir),
            "project_id": "demo-ad",
            "pipeline_type": "ad-video",
            "checkpoint_stage": "assets",
        }
    )

    assert result.success is False
    assert result.data["status"] == "FAIL"
    assert result.data["can_complete_checkpoint"] is False
    assert [issue["gate"] for issue in result.data["issues"]] == [
        "product_reference",
        "sample_review",
        "asset_review",
        "music_review",
    ]
    assert "sample_review" in result.error


def test_genui_evidence_check_passes_manifest_declared_assets_checkpoint(tmp_path: Path):
    from tools.validation.genui_evidence_check import GenUIEvidenceCheck

    project_dir = tmp_path / "projects" / "demo-ad"
    write_genui_required_gate_evidence(project_dir, project_id="demo-ad")

    result = GenUIEvidenceCheck().execute(
        {
            "project_dir": str(project_dir),
            "project_id": "demo-ad",
            "pipeline_type": "ad-video",
            "checkpoint_stage": "assets",
        }
    )

    assert result.success is True
    assert result.data["status"] == "PASS"
    assert result.data["can_complete_checkpoint"] is True
    assert result.data["issues"] == []
    assert len(result.data["evidence"]) == 4


def test_genui_evidence_check_skips_music_gate_for_no_music_project_artifact(tmp_path: Path):
    from tools.validation.genui_evidence_check import GenUIEvidenceCheck

    project_dir = tmp_path / "projects" / "demo-ad"
    artifact_dir = project_dir / "artifacts"
    artifact_dir.mkdir(parents=True)
    proposal = _minimal_production_proposal()
    proposal["music_strategy"] = "none"
    (artifact_dir / "production_proposal.json").write_text(
        json.dumps(proposal, indent=2) + "\n",
        encoding="utf-8",
    )

    result = GenUIEvidenceCheck().execute(
        {
            "project_dir": str(project_dir),
            "project_id": "demo-ad",
            "pipeline_type": "ad-video",
            "checkpoint_stage": "assets",
        }
    )

    assert result.success is False
    assert [issue["gate"] for issue in result.data["issues"]] == [
        "product_reference",
        "sample_review",
        "asset_review",
    ]
    assert result.data["required_gates"] == [
        {"stage": "assets", "gate": "product_reference"},
        {"stage": "assets", "gate": "sample_review"},
        {"stage": "assets", "gate": "asset_review"},
    ]


def test_genui_evidence_check_accepts_explicit_required_gates(tmp_path: Path):
    from tools.validation.genui_evidence_check import GenUIEvidenceCheck

    project_dir = tmp_path / "projects" / "demo-ad"
    write_genui_required_gate_evidence(
        project_dir,
        project_id="demo-ad",
        gates=("sample_review",),
    )

    result = GenUIEvidenceCheck().execute(
        {
            "project_dir": str(project_dir),
            "project_id": "demo-ad",
            "pipeline_type": "ad-video",
            "required_gates": ["assets:sample_review"],
        }
    )

    assert result.success is True
    assert result.data["checkpoint_stage"] is None
    assert result.data["required_gates"] == [{"stage": "assets", "gate": "sample_review"}]


def test_genui_evidence_check_is_registry_discoverable():
    from tools.tool_registry import registry

    registry.clear()
    registry.discover()
    tool = registry.get("genui_evidence_check")

    assert tool is not None
    info = tool.get_info()
    assert info["capability"] == "validation"
    assert "preflight_checkpoint_genui_requirements" in info["capabilities"]
    assert info["supports"]["side_effect_free"] is True
