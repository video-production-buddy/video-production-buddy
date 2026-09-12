"""Contracts for evidence-backed contextual review of Technical QC findings."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import jsonschema
import pytest
import yaml

from schemas.artifacts import validate_artifact


ROOT = Path(__file__).resolve().parent.parent.parent
FINAL_REVIEW_SCHEMA = ROOT / "schemas" / "artifacts" / "final_review.schema.json"
CONTEXT_SKILL = ROOT / "skills" / "meta" / "technical-qc-review.md"
REVIEWER_SKILL = ROOT / "skills" / "meta" / "reviewer.md"


def _review_with_context(*, status: str = "pass", unresolved_count: int = 0) -> dict:
    return {
        "version": "1.0",
        "output_path": "renders/final.mp4",
        "status": status,
        "checks": {
            "technical_probe": {},
            "visual_spotcheck": {},
            "audio_spotcheck": {},
            "promise_preservation": {},
            "subtitle_check": {},
            "technical_qc_review": {
                "outputs": [
                    {
                        "output_path": "renders/final.mp4",
                        "report_path": "artifacts/technical_qc.json",
                        "scan_status": "pass_with_warnings",
                        "warning_count": 1,
                        "findings": [
                            {
                                "code": "freeze_segment",
                                "source": "technical_qc",
                                "start_seconds": 28.0,
                                "end_seconds": 31.0,
                                "disposition": "intentional",
                                "reason": "Matches the approved static end-card hold.",
                                "evidence_refs": [
                                    "assets/qc_evidence/freeze-28/frame_29_5s.jpg"
                                ],
                                "context_refs": ["edit_decisions.cuts[end-card]"],
                                "recommended_action": "none",
                            }
                        ],
                        "supplemental_checks": [],
                        "unresolved_count": unresolved_count,
                    }
                ],
                "unresolved_count": unresolved_count,
            },
        },
    }


@pytest.fixture(scope="module")
def final_review_schema() -> dict:
    return json.loads(FINAL_REVIEW_SCHEMA.read_text(encoding="utf-8"))


def test_final_review_accepts_evidence_backed_intentional_finding(
    final_review_schema: dict,
) -> None:
    jsonschema.validate(_review_with_context(), final_review_schema)


def test_contextual_finding_requires_evidence_and_artifact_context(
    final_review_schema: dict,
) -> None:
    review = _review_with_context()
    output_review = review["checks"]["technical_qc_review"]["outputs"][0]
    finding = output_review["findings"][0]
    finding["evidence_refs"] = []

    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(review, final_review_schema)

    finding["evidence_refs"] = ["assets/qc_evidence/frame.jpg"]
    finding["context_refs"] = []
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(review, final_review_schema)


def test_passing_review_rejects_unresolved_contextual_findings(
    final_review_schema: dict,
) -> None:
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(
            _review_with_context(unresolved_count=1),
            final_review_schema,
        )

    jsonschema.validate(
        _review_with_context(status="revise", unresolved_count=1),
        final_review_schema,
    )


def test_same_measurement_can_receive_different_contextual_dispositions(
    final_review_schema: dict,
) -> None:
    intentional = _review_with_context()
    jsonschema.validate(intentional, final_review_schema)

    defect = deepcopy(intentional)
    defect["status"] = "revise"
    contextual_review = defect["checks"]["technical_qc_review"]
    contextual_review["unresolved_count"] = 1
    output_review = contextual_review["outputs"][0]
    output_review["unresolved_count"] = 1
    finding = output_review["findings"][0]
    finding.update(
        {
            "disposition": "defect",
            "reason": "The frozen interval interrupts a cut marked motion_required.",
            "context_refs": ["scene_plan.scenes[motion-demo]"],
            "recommended_action": "re_render",
        }
    )
    jsonschema.validate(defect, final_review_schema)

    defect["status"] = "pass"
    contextual_review["unresolved_count"] = 0
    output_review["unresolved_count"] = 0
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(defect, final_review_schema)


def test_talking_head_pass_requires_context_review_and_output_coverage() -> None:
    review = _review_with_context()
    render_report = {
        "version": "1.0",
        "outputs": [
            {
                "path": "renders/final.mp4",
                "format": "mp4",
                "resolution": "1080x1920",
                "duration_seconds": 31.0,
            }
        ],
    }
    validate_artifact(
        "final_review",
        review,
        pipeline_type="talking-head",
        related_artifacts={"render_report": render_report},
    )

    missing = deepcopy(review)
    del missing["checks"]["technical_qc_review"]
    with pytest.raises(jsonschema.ValidationError, match="technical_qc_review"):
        validate_artifact("final_review", missing, pipeline_type="talking-head")

    wrong_output = deepcopy(review)
    wrong_output["checks"]["technical_qc_review"]["outputs"][0][
        "output_path"
    ] = "renders/other.mp4"
    with pytest.raises(jsonschema.ValidationError, match="exactly cover"):
        validate_artifact(
            "final_review",
            wrong_output,
            pipeline_type="talking-head",
            related_artifacts={"render_report": render_report},
        )

    with pytest.raises(jsonschema.ValidationError, match="final_review output_path"):
        validate_artifact(
            "final_review",
            wrong_output,
            pipeline_type="talking-head",
        )


def test_talking_head_multi_output_uses_render_report_as_coverage_source() -> None:
    review = _review_with_context()
    review["checks"]["technical_qc_review"]["outputs"].append(
        {
            "output_path": "renders/final-square.mp4",
            "variant": "1:1",
            "report_path": "artifacts/technical_qc_square.json",
            "scan_status": "pass",
            "warning_count": 0,
            "findings": [],
            "supplemental_checks": [],
            "unresolved_count": 0,
        }
    )
    render_report = {
        "version": "1.0",
        "outputs": [
            {
                "path": "renders/final.mp4",
                "format": "mp4",
                "resolution": "1080x1920",
                "duration_seconds": 31.0,
            },
            {
                "path": "renders/final-square.mp4",
                "variant": "1:1",
                "format": "mp4",
                "resolution": "1080x1080",
                "duration_seconds": 31.0,
            },
        ],
    }

    validate_artifact(
        "final_review",
        review,
        pipeline_type="talking-head",
        related_artifacts={"render_report": render_report},
    )


def test_context_review_rejects_incomplete_or_reversed_time_ranges() -> None:
    review = _review_with_context(status="revise")
    finding = review["checks"]["technical_qc_review"]["outputs"][0]["findings"][0]
    del finding["end_seconds"]

    with pytest.raises(jsonschema.ValidationError, match="both start_seconds"):
        validate_artifact("final_review", review, pipeline_type="talking-head")

    finding["end_seconds"] = 20.0
    with pytest.raises(jsonschema.ValidationError, match="greater than or equal"):
        validate_artifact("final_review", review, pipeline_type="talking-head")


def test_context_review_is_backward_compatible_outside_passing_qc_pipelines() -> None:
    review = _review_with_context(status="revise")
    del review["checks"]["technical_qc_review"]

    validate_artifact("final_review", review, pipeline_type="ad-video")
    validate_artifact("final_review", review, pipeline_type="talking-head")
    review["status"] = "pass"
    validate_artifact("final_review", review, pipeline_type="slideshow")


def test_context_review_counts_unresolved_findings_consistently() -> None:
    review = _review_with_context(status="revise", unresolved_count=0)
    finding = review["checks"]["technical_qc_review"]["outputs"][0]["findings"][0]
    finding.update(
        {
            "disposition": "uncertain",
            "reason": "The available frames do not establish whether the hold is intended.",
            "recommended_action": "human_review",
        }
    )

    with pytest.raises(jsonschema.ValidationError, match="unresolved_count"):
        validate_artifact("final_review", review, pipeline_type="talking-head")

    output_review = review["checks"]["technical_qc_review"]["outputs"][0]
    output_review["unresolved_count"] = 1
    review["checks"]["technical_qc_review"]["unresolved_count"] = 1
    validate_artifact("final_review", review, pipeline_type="talking-head")


def test_context_review_covers_every_canonical_warning() -> None:
    review = _review_with_context(status="revise")
    output_review = review["checks"]["technical_qc_review"]["outputs"][0]
    output_review["warning_count"] = 2

    with pytest.raises(jsonschema.ValidationError, match="warning_count"):
        validate_artifact("final_review", review, pipeline_type="talking-head")

    output_review["scan_status"] = "pass"
    output_review["warning_count"] = 1
    with pytest.raises(jsonschema.ValidationError, match="scan_status='pass'"):
        validate_artifact("final_review", review, pipeline_type="talking-head")


def test_context_review_matches_render_variant_after_normalization() -> None:
    review = _review_with_context()
    output_review = review["checks"]["technical_qc_review"]["outputs"][0]
    output_review["variant"] = " primary "
    render_report = {
        "version": "1.0",
        "outputs": [
            {
                "path": "renders/final.mp4",
                "variant": "primary",
                "format": "mp4",
                "resolution": "1080x1920",
                "duration_seconds": 31.0,
            }
        ],
    }
    validate_artifact(
        "final_review",
        review,
        pipeline_type="talking-head",
        related_artifacts={"render_report": render_report},
    )

    output_review["variant"] = "landscape"
    with pytest.raises(jsonschema.ValidationError, match="variant must match"):
        validate_artifact(
            "final_review",
            review,
            pipeline_type="talking-head",
            related_artifacts={"render_report": render_report},
        )


def test_supplemental_diagnostic_requires_capability_extension_provenance(
    final_review_schema: dict,
) -> None:
    review = _review_with_context(status="revise", unresolved_count=1)
    supplemental = {
        "purpose": "Inspect a project-specific repeated-frame pattern.",
        "method": "project_script",
        "lifecycle": "project_only",
        "artifact_ref": "artifacts/repeated_frame_diagnostic.json",
        "decision_log_ref": "artifacts/decision_log.json#ext-001",
        "result": "inconclusive",
        "limitations": "The heuristic does not establish editorial intent.",
    }
    output_review = review["checks"]["technical_qc_review"]["outputs"][0]
    output_review["supplemental_checks"] = [supplemental]
    jsonschema.validate(review, final_review_schema)

    broken = deepcopy(review)
    del broken["checks"]["technical_qc_review"]["outputs"][0][
        "supplemental_checks"
    ][0]["decision_log_ref"]
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(broken, final_review_schema)

    wrong_lifecycle = deepcopy(review)
    wrong_lifecycle["checks"]["technical_qc_review"]["outputs"][0][
        "supplemental_checks"
    ][0]["lifecycle"] = "shared"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(wrong_lifecycle, final_review_schema)


def test_context_skill_enforces_hybrid_boundary() -> None:
    text = CONTEXT_SKILL.read_text(encoding="utf-8").lower()

    for required in (
        "hard-code measurement, not creative meaning",
        "defect",
        "intentional",
        "uncertain",
        "visual_qa",
        "capability-extension.md",
        "project_only",
        "do not promote",
        "never override",
        "sole basis",
    ):
        assert required in text

    reviewer = REVIEWER_SKILL.read_text(encoding="utf-8")
    assert "skills/meta/technical-qc-review.md" in reviewer
    assert "technical_qc_review.outputs[]" in reviewer


@pytest.mark.parametrize(
    ("manifest_name", "required_skill", "director_name"),
    [
        (
            "ad-video.yaml",
            "skills/meta/technical-qc-review.md",
            "ad-video/compose-director.md",
        ),
        (
            "talking-head.yaml",
            "meta/technical-qc-review",
            "talking-head/compose-director.md",
        ),
    ],
)
def test_existing_qc_pipelines_require_context_review_skill(
    manifest_name: str,
    required_skill: str,
    director_name: str,
) -> None:
    manifest = yaml.safe_load(
        (ROOT / "pipeline_defs" / manifest_name).read_text(encoding="utf-8")
    )
    assert required_skill in manifest["required_skills"]

    compose = next(stage for stage in manifest["stages"] if stage["name"] == "compose")
    assert any(
        "technical_qc_review" in criterion
        for criterion in compose["success_criteria"]
    )

    director = (ROOT / "skills" / "pipelines" / director_name).read_text(
        encoding="utf-8"
    )
    assert "skills/meta/technical-qc-review.md" in director
    assert "technical_qc_review" in director
