"""Regression coverage for PR #13 at the saved-report/checkpoint boundary."""

from copy import deepcopy
import json
from pathlib import Path
import shutil
import subprocess

import jsonschema
import pytest

from lib.checkpoint import CheckpointValidationError, read_checkpoint, write_checkpoint
from schemas.artifacts import validate_artifact
from tests.contracts.test_ad_video_chain_integrity import _valid_final_review
from tests.contracts.test_technical_qc_context_review import _review_with_context
from tests.tools.test_technical_qc import _runner
from tools.analysis.technical_qc import TechnicalQC


@pytest.fixture
def saved_review(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    project = tmp_path / "projects" / "qc-test"
    media = project / "renders" / "final.mp4"
    media.parent.mkdir(parents=True)
    media.write_bytes(b"original video")
    report_path = project / "artifacts" / "technical_qc.json"
    monkeypatch.setattr(
        TechnicalQC, "run_command",
        _runner(freeze_output=(
            "lavfi.freezedetect.freeze_start: 3\n"
            "lavfi.freezedetect.freeze_duration: 2\n"
            "lavfi.freezedetect.freeze_end: 5\n"
        )),
    )
    result = TechnicalQC().execute({
        "input_path": str(media), "report_path": str(report_path),
    })
    assert result.success, result.error
    review = _review_with_context()
    finding = review["checks"]["technical_qc_review"]["outputs"][0]["findings"][0]
    finding.update(start_seconds=3.0, end_seconds=5.0)
    render = {"version": "1.0", "outputs": [{
        "path": "renders/final.mp4", "format": "mp4",
        "resolution": "1920x1080", "duration_seconds": 10.0,
    }]}
    return project, review, render, result.data


def _save_report(project, report):
    (project / "artifacts" / "technical_qc.json").write_text(json.dumps(report))


def _validate(project, review, render):
    validate_artifact(
        "final_review", review, pipeline_type="talking-head",
        related_artifacts={"render_report": render},
        validation_context={"project_dir": project},
    )


def _write(project, review, render, *, status="awaiting_human"):
    return write_checkpoint(
        project.parent, project.name, "compose", status,
        {"render_report": render, "final_review": review},
        pipeline_type="talking-head", human_approved=status == "completed",
    )


def test_saved_report_can_reach_compose_and_be_read(saved_review):
    project, review, render, _ = saved_review
    _validate(project, review, render)
    path = _write(project, review, render)
    assert path.exists()
    assert read_checkpoint(project.parent, project.name, "compose")["status"] == "awaiting_human"


@pytest.mark.parametrize("status", ["awaiting_human", "completed"])
def test_failed_canonical_scan_cannot_be_declared_passing(saved_review, status):
    project, review, render, report = saved_review
    report.update(status="fail", passed=False)
    report["issues"].append({"code": "width_mismatch", "severity": "error", "message": "Wrong width"})
    report["summary"].update(error_count=1, total_issues=2)
    _save_report(project, report)
    with pytest.raises(jsonschema.ValidationError, match="canonical.*fail"):
        _validate(project, review, render)
    with pytest.raises(CheckpointValidationError, match="canonical.*fail"):
        _write(project, review, render, status=status)
    assert not (project / "checkpoint_compose.json").exists()


@pytest.mark.parametrize("change", ["missing", "invalid_json", "empty_report", "missing_fingerprint", "stale_media"])
def test_missing_invalid_or_stale_report_is_rejected(saved_review, change):
    project, review, render, report = saved_review
    path = project / "artifacts" / "technical_qc.json"
    if change == "missing":
        path.unlink()
    elif change == "invalid_json":
        path.write_text("{broken")
    elif change == "empty_report":
        path.write_text("{}")
    elif change == "missing_fingerprint":
        report.pop("input_sha256", None)
        _save_report(project, report)
    else:
        (project / "renders" / "final.mp4").write_bytes(b"replacement video")
    with pytest.raises(CheckpointValidationError, match="technical_qc"):
        _write(project, review, render)


@pytest.mark.parametrize("reference", ["../outside.json", "/tmp/outside-qc-report.json"])
def test_reports_cannot_escape_project(saved_review, reference):
    project, review, render, _ = saved_review
    review["checks"]["technical_qc_review"]["outputs"][0]["report_path"] = reference
    with pytest.raises(CheckpointValidationError, match="within.*project"):
        _write(project, review, render)


def test_symlink_report_cannot_escape_project(saved_review, tmp_path):
    project, review, render, report = saved_review
    outside = tmp_path / "outside.json"
    outside.write_text(json.dumps(report))
    path = project / "artifacts" / "technical_qc.json"
    path.unlink()
    path.symlink_to(outside)
    with pytest.raises(CheckpointValidationError, match="within.*project"):
        _write(project, review, render)


def test_wrong_media_report_is_rejected(saved_review):
    project, review, render, report = saved_review
    other = project / "renders" / "other.mp4"
    other.write_bytes(b"original video")
    report["input"] = str(other)
    _save_report(project, report)
    with pytest.raises(CheckpointValidationError, match="input.*output"):
        _write(project, review, render)


def test_duplicate_disposition_cannot_hide_another_warning(saved_review):
    project, review, render, report = saved_review
    report["issues"].append({"code": "silence_segment", "severity": "warning", "message": "Silence", "start_seconds": 6.0, "end_seconds": 7.0})
    report["summary"].update(warning_count=2, total_issues=2)
    _save_report(project, report)
    output = review["checks"]["technical_qc_review"]["outputs"][0]
    output["warning_count"] = 2
    output["findings"].append(deepcopy(output["findings"][0]))
    with pytest.raises(CheckpointValidationError, match="one-to-one"):
        _write(project, review, render)


@pytest.mark.parametrize("change", ["warning_count", "missing_check", "unexpected_skip", "missing_times", "wrong_times"])
def test_copied_counts_checks_and_intervals_match_canonical_report(saved_review, change):
    project, review, render, report = saved_review
    output = review["checks"]["technical_qc_review"]["outputs"][0]
    if change == "warning_count":
        output.update(scan_status="pass", warning_count=0, findings=[])
    elif change == "missing_check":
        report["checks_run"].remove("freeze_frames")
    elif change == "unexpected_skip":
        report["checks_run"].remove("audio_loudness")
        report["checks_skipped"].append({"check": "audio_loudness", "reason": "failed"})
    elif change == "missing_times":
        output["findings"][0].pop("start_seconds")
        output["findings"][0].pop("end_seconds")
    else:
        output["findings"][0].update(start_seconds=300.0, end_seconds=310.0)
    _save_report(project, report)
    with pytest.raises(CheckpointValidationError, match="technical_qc"):
        _write(project, review, render)


def test_project_and_repo_relative_paths_resolve_without_cwd(saved_review, monkeypatch, tmp_path):
    project, review, render, report = saved_review
    report["input"] = f"projects/{project.name}/renders/final.mp4"
    report["report_path"] = f"projects/{project.name}/artifacts/technical_qc.json"
    _save_report(project, report)
    monkeypatch.chdir(tmp_path)
    _write(project, review, render)


@pytest.mark.parametrize("explicit_outputs", [False, True])
def test_primary_output_always_belongs_to_reviewed_outputs(saved_review, explicit_outputs):
    project, review, render, _ = saved_review
    if explicit_outputs:
        review["reviewed_outputs"] = [{
            "path": "renders/final.mp4", "variant": "primary",
            "duration_seconds": 10.0, "resolution": "1920x1080",
        }]
    review["output_path"] = "renders/unreviewed.mp4"
    with pytest.raises(jsonschema.ValidationError, match="output_path"):
        _validate(project, review, render)


def test_intentional_black_is_allowed_but_missing_or_unresolved_black_is_not():
    review = _valid_final_review()
    review["checks"]["visual_spotcheck"]["black_frames_detected"] = True
    output = review["checks"]["technical_qc_review"]["outputs"][0]
    finding = deepcopy(_review_with_context()["checks"]["technical_qc_review"]["outputs"][0]["findings"][0])
    finding.update(code="black_segment", start_seconds=0.0, end_seconds=0.5,
                   reason="Approved opening black beat; adjacent frames inspected.",
                   context_refs=["edit_decisions.cuts[opening-black]"])
    output.update(scan_status="pass_with_warnings", warning_count=1, findings=[finding])
    validate_artifact("final_review", review, pipeline_type="ad-video")
    for disposition in ("defect", "uncertain"):
        finding["disposition"] = disposition
        with pytest.raises(jsonschema.ValidationError):
            validate_artifact("final_review", review, pipeline_type="ad-video")
    output.update(scan_status="pass", warning_count=0, findings=[])
    with pytest.raises(jsonschema.ValidationError, match="black_frames_detected"):
        validate_artifact("final_review", review, pipeline_type="ad-video")


def test_intentional_ad_black_requires_its_saved_canonical_report(saved_review, monkeypatch):
    project, _, _, _ = saved_review
    monkeypatch.setattr(TechnicalQC, "run_command", _runner(
        black_output="black_start:0 black_end:0.5 black_duration:0.5",
    ))
    result = TechnicalQC().execute({
        "input_path": str(project / "renders" / "final.mp4"),
        "report_path": str(project / "artifacts" / "technical_qc.json"),
    })
    assert result.success and result.data["summary"]["warning_count"] == 1
    review = _valid_final_review()
    review["checks"]["visual_spotcheck"]["black_frames_detected"] = True
    finding = deepcopy(_review_with_context()["checks"]["technical_qc_review"]["outputs"][0]["findings"][0])
    finding.update(code="black_segment", start_seconds=0.0, end_seconds=0.5)
    review["checks"]["technical_qc_review"]["outputs"][0].update(
        report_path="artifacts/technical_qc.json", scan_status="pass_with_warnings",
        warning_count=1, findings=[finding],
    )
    validate_artifact("final_review", review, pipeline_type="ad-video",
                      validation_context={"project_dir": project})
    (project / "artifacts" / "technical_qc.json").unlink()
    with pytest.raises(jsonschema.ValidationError, match="missing"):
        validate_artifact("final_review", review, pipeline_type="ad-video",
                          validation_context={"project_dir": project})


def test_all_derivative_outputs_need_their_own_saved_report(saved_review):
    project, review, render, _ = saved_review
    (project / "renders" / "square.mp4").write_bytes(b"square video")
    output = deepcopy(review["checks"]["technical_qc_review"]["outputs"][0])
    output.update(output_path="renders/square.mp4", report_path="artifacts/qc_square.json")
    review["checks"]["technical_qc_review"]["outputs"].append(output)
    render["outputs"].append({"path": "renders/square.mp4", "format": "mp4", "resolution": "1080x1080", "duration_seconds": 10.0})
    with pytest.raises(CheckpointValidationError, match="qc_square.json"):
        _write(project, review, render)
    result = TechnicalQC().execute({"input_path": str(project / "renders" / "square.mp4"), "report_path": str(project / "artifacts" / "qc_square.json")})
    assert result.success, result.error
    _write(project, review, render)


@pytest.mark.parametrize("status", ["revise", "fail"])
def test_nonpassing_review_can_record_failure_without_saved_report(saved_review, status):
    project, review, render, _ = saved_review
    (project / "artifacts" / "technical_qc.json").unlink()
    review["status"] = status
    _write(project, review, render, status="in_progress")


@pytest.mark.parametrize("approved_silent", [False, True])
def test_only_explicit_silent_delivery_allows_audio_scans_to_be_skipped(saved_review, monkeypatch, approved_silent):
    project, review, render, _ = saved_review
    monkeypatch.setattr(TechnicalQC, "run_command", _runner(has_audio=False))
    result = TechnicalQC().execute({
        "input_path": str(project / "renders" / "final.mp4"),
        "report_path": str(project / "artifacts" / "technical_qc.json"),
        "expected": {"has_audio": False} if approved_silent else {},
    })
    assert result.success, result.error
    output = review["checks"]["technical_qc_review"]["outputs"][0]
    if approved_silent:
        output.update(scan_status="pass", warning_count=0, findings=[])
        _write(project, review, render)
    else:
        finding = output["findings"][0]
        finding.update(code="audio_stream_missing")
        finding.pop("start_seconds")
        finding.pop("end_seconds")
        with pytest.raises(CheckpointValidationError, match="requested scans"):
            _write(project, review, render)


def test_rejected_review_preserves_existing_checkpoint_and_decision_log(saved_review):
    project, review, render, report = saved_review
    path = _write(project, review, render)
    original = path.read_bytes()
    decision_log = project / "decision_log.json"
    decision_log.write_text('{"decisions": []}')
    report["status"] = "fail"
    _save_report(project, report)
    with pytest.raises(CheckpointValidationError):
        _write(project, review, render)
    assert path.read_bytes() == original
    assert decision_log.read_text() == '{"decisions": []}'
    # Historical records are still readable after a new render/scan fails.
    assert read_checkpoint(project.parent, project.name, "compose") is not None


@pytest.mark.ffmpeg
@pytest.mark.parametrize("mismatch", [False, True])
def test_real_ffmpeg_report_gates_checkpoint(tmp_path, monkeypatch, mismatch):
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        pytest.skip("FFmpeg/ffprobe required")
    monkeypatch.chdir(tmp_path)
    project = tmp_path / "projects" / "real-qc"
    media = project / "renders" / "final.mp4"
    media.parent.mkdir(parents=True)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=s=160x90:r=24:d=1", "-c:v", "libx264", str(media)], check=True, capture_output=True, timeout=30)
    result = TechnicalQC().execute({"input_path": str(media), "checks": ["container"], "expected": {"width": 1920 if mismatch else 160, "height": 90}, "report_path": str(project / "artifacts" / "technical_qc.json")})
    assert result.success, result.error
    review = _review_with_context()
    review["checks"]["technical_qc_review"]["outputs"][0].update(scan_status="pass", warning_count=0, findings=[])
    render = {"version": "1.0", "outputs": [{"path": "renders/final.mp4", "format": "mp4", "resolution": "160x90", "duration_seconds": 1.0}]}
    if mismatch:
        with pytest.raises(CheckpointValidationError, match="canonical.*fail"):
            _write(project, review, render)
    else:
        _write(project, review, render)
