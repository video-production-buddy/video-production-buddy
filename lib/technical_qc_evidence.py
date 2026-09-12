"""Bind saved Technical QC measurements to a render, without judging intent."""

from __future__ import annotations

from collections import Counter
import hashlib
import math
from pathlib import Path
from typing import Any

import jsonschema


def media_sha256(path: Path) -> str:
    """Hash media in bounded memory (also supported on Python 3.10)."""
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _project_file(reference: str, project_dir: Path) -> Path:
    """Resolve project-relative, projects/<id>/..., or in-project absolute refs."""
    root = project_dir.resolve()
    path = Path(reference.replace("\\", "/"))
    if not path.is_absolute():
        if path.parts[:2] == ("projects", root.name):
            path = Path(*path.parts[2:])
        path = root / path
    path = path.resolve()
    if not path.is_relative_to(root):
        raise ValueError("technical_qc references must remain within the project")
    if not path.is_file():
        raise ValueError(f"technical_qc evidence file is missing: {reference}")
    return path


def _warning_key(finding: dict[str, Any], duration: float) -> tuple:
    code = finding["code"]
    start, end = finding.get("start_seconds"), finding.get("end_seconds")
    if start is not None or end is not None or code in {
        "black_segment", "freeze_segment", "silence_segment",
    }:
        if not all(
            isinstance(value, (int, float))
            and not isinstance(value, bool)
            and math.isfinite(value)
            for value in (start, end)
        ) or not 0 <= start <= end <= duration:
            raise ValueError("technical_qc warning intervals must lie within the render duration")
    return code, start, end


def validate_saved_technical_qc(final_review: dict[str, Any], project_dir: Path) -> None:
    """Validate saved reports after the final_review structural checks pass.

    JSON fields in final_review are copies, not the source of truth. Only saved
    tool reports are loaded here; caller-supplied related artifacts cannot stand
    in for them. Editorial dispositions remain the agent's responsibility.
    """
    # Local imports keep the tool's hashing helper independent of tool discovery
    # and avoid importing artifact validation while that module is initializing.
    from schemas.artifacts import load_strict_json_object
    from tools.analysis.technical_qc import TechnicalQC

    seen_reports: set[Path] = set()
    seen_outputs: set[Path] = set()
    try:
        for reviewed in final_review["checks"]["technical_qc_review"]["outputs"]:
            report_path = _project_file(reviewed["report_path"], project_dir)
            output_path = _project_file(reviewed["output_path"], project_dir)
            if report_path in seen_reports or output_path in seen_outputs:
                raise ValueError("technical_qc reports and outputs must be distinct after path resolution")
            seen_reports.add(report_path)
            seen_outputs.add(output_path)
            report = load_strict_json_object(report_path, context="technical_qc report")
            jsonschema.validate(report, TechnicalQC.output_schema)

            issues = report["issues"]
            counts = Counter(issue["severity"] for issue in issues)
            if report["status"] == "fail" or not report["passed"] or counts["error"]:
                raise ValueError("technical_qc canonical report contains a deterministic failure")
            summary = report["summary"]
            if summary["total_issues"] != len(issues) or any(
                summary[f"{severity}_count"] != counts[severity]
                for severity in ("error", "warning", "info")
            ):
                raise ValueError("technical_qc canonical summary does not match its issues")
            expected_status = "pass_with_warnings" if counts["warning"] else "pass"
            if report["status"] != expected_status or reviewed["scan_status"] != report["status"]:
                raise ValueError("technical_qc scan_status must match the canonical report")
            if reviewed["warning_count"] != counts["warning"]:
                raise ValueError("technical_qc warning_count must match the canonical report")

            requested, completed = set(report["checks_requested"]), set(report["checks_run"])
            skipped = report["checks_skipped"]
            # An explicitly silent delivery has no audio stream to analyze.
            # Other skipped scans (including failed requested scans) block PASS.
            allowed_skips = {
                item["check"] for item in skipped
                if item["check"] in {"silence", "audio_loudness"}
                and report["media"]["has_audio"] is False
                and report.get("expected", {}).get("has_audio") is False
                and item["reason"] == "input has no audio stream"
            }
            if (
                not requested
                or requested != completed | allowed_skips
                or completed & allowed_skips
                or any(item["check"] not in allowed_skips for item in skipped)
            ):
                raise ValueError("technical_qc requested scans must complete before PASS")
            if not report["media"].get("video_codec"):
                raise ValueError("technical_qc canonical report must contain a video stream")

            if _project_file(report["input"], project_dir) != output_path:
                raise ValueError("technical_qc report input must match the reviewed output")
            if "report_path" in report and _project_file(report["report_path"], project_dir) != report_path:
                raise ValueError("technical_qc report_path must match the saved report")
            if not report.get("input_sha256"):
                raise ValueError("technical_qc report lacks input_sha256; rerun technical_qc")
            if report["input_sha256"] != media_sha256(output_path):
                raise ValueError("technical_qc report is stale for this render; rerun technical_qc")

            duration = report["media"]["duration"]
            canonical_warnings = Counter(
                _warning_key(issue, duration) for issue in issues if issue["severity"] == "warning"
            )
            dispositions = Counter(
                _warning_key(finding, duration) for finding in reviewed["findings"]
                if finding["source"] == "technical_qc"
            )
            if dispositions != canonical_warnings:
                raise ValueError("technical_qc findings must match canonical warnings one-to-one by code and interval")
    except (OSError, ValueError, RuntimeError, jsonschema.ValidationError) as exc:
        raise jsonschema.ValidationError(f"technical_qc evidence validation failed: {exc}") from exc
