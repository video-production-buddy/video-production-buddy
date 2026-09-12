"""Deterministic whole-file technical quality control for rendered videos.

The tool detects delivery problems that are common in generated video without
making aesthetic decisions: invalid media/profile metadata, black sections,
long frozen sections, silence, unsafe integrated loudness, and clipping risk.
Black/freeze/silence findings are warnings by default because they can be
intentional editorial choices; invalid containers and explicit profile
mismatches are errors.
"""

from __future__ import annotations

import json
import math
import re
import time
from fractions import Fraction
from pathlib import Path
from typing import Any

from lib.ffmpeg_validation import STRICT_DECODE_ARGS, require_clean_decode
from lib.technical_qc_evidence import media_sha256
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
from tools.output_paths import (
    portable_output_path,
    require_optional_project_sidecar_path,
)


_NUMBER_PATTERN = r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?(?![\w.+-])"

DEFAULT_CHECKS = [
    "container",
    "black_frames",
    "freeze_frames",
    "silence",
    "audio_loudness",
]

DEFAULT_THRESHOLDS = {
    "min_black_duration_seconds": 1.0,
    "black_pixel_threshold": 0.10,
    "black_picture_ratio_threshold": 0.98,
    "min_freeze_duration_seconds": 2.0,
    "freeze_noise_db": -60.0,
    "min_silence_duration_seconds": 2.0,
    "silence_noise_db": -50.0,
    "min_integrated_lufs": -35.0,
    "max_integrated_lufs": -8.0,
    "clipping_true_peak_dbfs": -0.1,
}

_INTERVAL_SCHEMA = {
    "type": "object",
    "required": ["start_seconds", "end_seconds", "duration_seconds"],
    "additionalProperties": False,
    "properties": {
        "start_seconds": {"type": "number", "minimum": 0},
        "end_seconds": {"type": "number", "minimum": 0},
        "duration_seconds": {"type": "number", "minimum": 0},
    },
}

_NULLABLE_NUMBER = {"type": ["number", "null"]}


class TechnicalQC(BaseTool):
    """Scan a final render and return machine-readable technical evidence."""

    name = "technical_qc"
    version = "0.1.1"
    tier = ToolTier.CORE
    capability = "analysis"
    provider = "ffmpeg"
    stability = ToolStability.EXPERIMENTAL
    execution_mode = ExecutionMode.SYNC
    determinism = Determinism.DETERMINISTIC
    runtime = ToolRuntime.LOCAL

    dependencies = ["cmd:ffmpeg", "cmd:ffprobe"]
    install_instructions = "Install FFmpeg: https://ffmpeg.org/download.html"
    agent_skills = ["ffmpeg"]

    capabilities = [
        "technical_qc",
        "detect_black_frames",
        "detect_freeze_frames",
        "detect_silence",
        "measure_integrated_loudness",
        "validate_media_profile",
    ]
    supports = {
        "local_offline": True,
        "structured_report": True,
        "custom_thresholds": True,
        "partial_checks": True,
    }
    best_for = [
        "checking a final render before delivery or publish",
        "locating black, frozen, or silent intervals in generated video",
        "validating output metadata and audio loudness without API costs",
    ]
    not_good_for = [
        "aesthetic, narrative, or brand review",
        "deciding whether an intentional pause or freeze is creatively correct",
    ]

    input_schema = {
        "type": "object",
        "required": ["input_path"],
        "properties": {
            "input_path": {
                "type": "string",
                "description": "Path to the rendered video to inspect.",
            },
            "checks": {
                "type": "array",
                "minItems": 1,
                "uniqueItems": True,
                "items": {
                    "type": "string",
                    "enum": DEFAULT_CHECKS,
                },
                "description": "Checks to run. Defaults to every supported check.",
            },
            "expected": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "width": {"type": "integer", "minimum": 1},
                    "height": {"type": "integer", "minimum": 1},
                    "min_duration": {"type": "number", "minimum": 0},
                    "max_duration": {"type": "number", "minimum": 0},
                    "pixel_format": {"type": "string"},
                    "has_audio": {"type": "boolean"},
                    "frame_rate": {
                        "type": "number",
                        "exclusiveMinimum": 0,
                        "description": (
                            "Expected frames per second; NTSC rates use a "
                            "0.05 fps tolerance."
                        ),
                    },
                    "video_codec": {
                        "type": "string",
                        "description": (
                            "Expected ffprobe codec_name, for example h264 "
                            "(not libx264)."
                        ),
                    },
                    "audio_codec": {
                        "type": "string",
                        "description": "Expected ffprobe audio codec_name, for example aac.",
                    },
                    "audio_channels": {"type": "integer", "minimum": 1},
                    "audio_sample_rate": {"type": "integer", "minimum": 1},
                    "max_file_size_mb": {"type": "number", "minimum": 0},
                },
                "description": (
                    "Optional required media properties. The container check must "
                    "be enabled when expectations are supplied."
                ),
            },
            "thresholds": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "min_black_duration_seconds": {
                        "type": "number",
                        "exclusiveMinimum": 0,
                        "default": 1.0,
                    },
                    "black_pixel_threshold": {
                        "type": "number",
                        "minimum": 0,
                        "maximum": 1,
                        "default": 0.10,
                    },
                    "black_picture_ratio_threshold": {
                        "type": "number",
                        "minimum": 0,
                        "maximum": 1,
                        "default": 0.98,
                    },
                    "min_freeze_duration_seconds": {
                        "type": "number",
                        "exclusiveMinimum": 0,
                        "default": 2.0,
                    },
                    "freeze_noise_db": {
                        "type": "number",
                        "minimum": -100,
                        "maximum": 0,
                        "default": -60.0,
                    },
                    "min_silence_duration_seconds": {
                        "type": "number",
                        "exclusiveMinimum": 0,
                        "default": 2.0,
                    },
                    "silence_noise_db": {
                        "type": "number",
                        "minimum": -100,
                        "maximum": 0,
                        "default": -50.0,
                    },
                    "min_integrated_lufs": {
                        "type": "number",
                        "minimum": -100,
                        "maximum": 0,
                        "default": -35.0,
                    },
                    "max_integrated_lufs": {
                        "type": "number",
                        "minimum": -100,
                        "maximum": 0,
                        "default": -8.0,
                    },
                    "clipping_true_peak_dbfs": {
                        "type": "number",
                        "minimum": -20,
                        "maximum": 0,
                        "default": -0.1,
                    },
                },
                "description": (
                    "Optional conservative detection thresholds. Unspecified "
                    "values use the tool defaults."
                ),
            },
            "report_path": {
                "type": "string",
                "description": (
                    "Optional .json sidecar path under projects/<project-name>/"
                    "artifacts/..., assets/..., or renders/..."
                ),
            },
        },
        "additionalProperties": False,
    }

    output_schema = {
        "type": "object",
        "required": [
            "input",
            "status",
            "passed",
            "checks_requested",
            "checks_run",
            "checks_skipped",
            "thresholds",
            "summary",
            "issues",
            "media",
            "metrics",
        ],
        "properties": {
            "input": {"type": "string"},
            "input_sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
            "expected": {"type": "object"},
            "status": {
                "type": "string",
                "enum": ["pass", "pass_with_warnings", "fail"],
            },
            "passed": {"type": "boolean"},
            "checks_requested": {
                "type": "array",
                "items": {"type": "string", "enum": DEFAULT_CHECKS},
            },
            "checks_run": {
                "type": "array",
                "items": {"type": "string", "enum": DEFAULT_CHECKS},
            },
            "checks_skipped": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["check", "reason"],
                    "additionalProperties": False,
                    "properties": {
                        "check": {"type": "string", "enum": DEFAULT_CHECKS},
                        "reason": {"type": "string"},
                    },
                },
            },
            "thresholds": {
                "type": "object",
                "required": list(DEFAULT_THRESHOLDS),
                "additionalProperties": False,
                "properties": {
                    name: {"type": "number"} for name in DEFAULT_THRESHOLDS
                },
            },
            "summary": {
                "type": "object",
                "required": [
                    "total_issues",
                    "error_count",
                    "warning_count",
                    "info_count",
                ],
                "additionalProperties": False,
                "properties": {
                    "total_issues": {"type": "integer", "minimum": 0},
                    "error_count": {"type": "integer", "minimum": 0},
                    "warning_count": {"type": "integer", "minimum": 0},
                    "info_count": {"type": "integer", "minimum": 0},
                },
            },
            "issues": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["code", "severity", "message"],
                    "additionalProperties": False,
                    "properties": {
                        "code": {"type": "string"},
                        "severity": {
                            "type": "string",
                            "enum": ["error", "warning", "info"],
                        },
                        "message": {"type": "string"},
                        "check": {"type": "string", "enum": DEFAULT_CHECKS},
                        "start_seconds": {"type": "number", "minimum": 0},
                        "end_seconds": {"type": "number", "minimum": 0},
                        "duration_seconds": {"type": "number", "minimum": 0},
                        "value": {"type": "number"},
                        "threshold": {"type": "number"},
                    },
                },
            },
            "media": {
                "type": "object",
                "required": [
                    "duration",
                    "file_size_bytes",
                    "file_size_mb",
                    "has_audio",
                ],
                "additionalProperties": False,
                "properties": {
                    "duration": {"type": "number", "minimum": 0},
                    "file_size_bytes": {"type": "integer", "minimum": 0},
                    "file_size_mb": {"type": "number", "minimum": 0},
                    "has_audio": {"type": "boolean"},
                    "width": {"type": ["integer", "null"], "minimum": 1},
                    "height": {"type": ["integer", "null"], "minimum": 1},
                    "pixel_format": {"type": ["string", "null"]},
                    "video_codec": {"type": ["string", "null"]},
                    "frame_rate": {"type": ["number", "null"], "minimum": 0},
                    "audio_codec": {"type": ["string", "null"]},
                    "sample_rate": {"type": ["integer", "null"], "minimum": 0},
                    "channels": {"type": ["integer", "null"], "minimum": 0},
                },
            },
            "metrics": {
                "type": "object",
                "required": [
                    "black_segments",
                    "freeze_segments",
                    "silence_segments",
                    "audio_loudness",
                ],
                "additionalProperties": False,
                "properties": {
                    "black_segments": {
                        "type": "array",
                        "items": _INTERVAL_SCHEMA,
                    },
                    "freeze_segments": {
                        "type": "array",
                        "items": _INTERVAL_SCHEMA,
                    },
                    "silence_segments": {
                        "type": "array",
                        "items": _INTERVAL_SCHEMA,
                    },
                    "audio_loudness": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "integrated_lufs": _NULLABLE_NUMBER,
                            "loudness_range_lu": _NULLABLE_NUMBER,
                            "true_peak_dbfs": _NULLABLE_NUMBER,
                        },
                    },
                },
            },
            "report_path": {"type": "string"},
        },
        "additionalProperties": False,
    }

    resource_profile = ResourceProfile(
        cpu_cores=2,
        ram_mb=512,
        vram_mb=0,
        disk_mb=20,
        network_required=False,
    )
    idempotency_key_fields = [
        "input_path",
        "checks",
        "expected",
        "thresholds",
        "report_path",
    ]
    side_effects = ["optionally writes a JSON sidecar to report_path"]
    user_visible_verification = [
        "Inspect every reported interval and confirm whether it is intentional",
        "Watch the final render because technical QC does not judge aesthetics",
    ]

    def estimate_cost(self, inputs: dict[str, Any]) -> float:
        return 0.0

    def execute(self, inputs: dict[str, Any]) -> ToolResult:
        input_path = Path(inputs["input_path"])
        if not input_path.is_file():
            return ToolResult(success=False, error=f"Input not found: {input_path}")

        start = time.time()
        try:
            checks, thresholds = self._resolve_config(inputs)
            report_path, report_error = require_optional_project_sidecar_path(
                inputs,
                "report_path",
                self.name,
                artifact_label="technical-QC report",
            )
            if report_error:
                return report_error
            if report_path is not None and report_path.suffix.lower() != ".json":
                return ToolResult(
                    success=False,
                    error="technical_qc: report_path must use the .json extension",
                )

            input_sha256 = media_sha256(input_path)
            media = self._probe(input_path)
            data = self._build_report(
                input_path,
                checks,
                thresholds,
                inputs.get("expected", {}),
                media,
            )
            if media_sha256(input_path) != input_sha256:
                return ToolResult(success=False, error="technical_qc: input changed during scan; rerun the scan")
            data["input_sha256"] = input_sha256
            data["expected"] = dict(inputs.get("expected", {}))

            artifacts: list[str] = []
            if report_path is not None:
                portable_report_path = portable_output_path(report_path)
                data["report_path"] = portable_report_path
                report_path.parent.mkdir(parents=True, exist_ok=True)
                report_path.write_text(
                    json.dumps(data, indent=2, allow_nan=False) + "\n",
                    encoding="utf-8",
                )
                artifacts.append(portable_report_path)

            return ToolResult(
                success=True,
                data=data,
                artifacts=artifacts,
                duration_seconds=round(time.time() - start, 2),
            )
        except Exception as exc:
            return ToolResult(success=False, error=f"Technical QC failed: {exc}")

    def _build_report(
        self,
        input_path: Path,
        checks: list[str],
        thresholds: dict[str, float],
        expected: dict[str, Any],
        media: dict[str, Any],
    ) -> dict[str, Any]:
        duration = float(media.get("duration", 0.0))
        has_video = bool(media.get("video_codec"))
        has_audio = bool(media.get("has_audio"))
        issues: list[dict[str, Any]] = []
        checks_run: list[str] = []
        checks_skipped: list[dict[str, str]] = []
        metrics: dict[str, Any] = {
            "black_segments": [],
            "freeze_segments": [],
            "silence_segments": [],
            "audio_loudness": {},
        }

        if "container" in checks:
            checks_run.append("container")
            issues.extend(self._profile_issues(media, expected))
        if not has_video:
            issues.append(
                self._issue(
                    "video_stream_missing",
                    "error",
                    "No video stream was found in the input file.",
                    check="container",
                )
            )

        video_checks = [
            check
            for check in ("black_frames", "freeze_frames")
            if check in checks
        ]
        if video_checks and has_video:
            self._run_video_checks(
                input_path,
                duration,
                video_checks,
                thresholds,
                metrics,
                issues,
                checks_run,
                checks_skipped,
            )
        elif video_checks:
            for check in video_checks:
                self._skip(checks_skipped, check, "input has no video stream")

        audio_checks = [
            check
            for check in ("silence", "audio_loudness")
            if check in checks
        ]
        if audio_checks and has_audio:
            self._run_audio_checks(
                input_path,
                duration,
                audio_checks,
                thresholds,
                metrics,
                issues,
                checks_run,
                checks_skipped,
            )
        elif audio_checks:
            if "has_audio" not in expected:
                issues.append(
                    self._issue(
                        "audio_stream_missing",
                        "warning",
                        "No audio stream was found; audio checks were skipped.",
                        check="container",
                    )
                )
            for check in audio_checks:
                self._skip(checks_skipped, check, "input has no audio stream")

        counts = {
            severity: sum(1 for issue in issues if issue["severity"] == severity)
            for severity in ("error", "warning", "info")
        }
        status = (
            "fail"
            if counts["error"]
            else "pass_with_warnings"
            if counts["warning"]
            else "pass"
        )
        return {
            "input": portable_output_path(input_path),
            "status": status,
            "passed": status != "fail",
            "checks_requested": checks,
            "checks_run": checks_run,
            "checks_skipped": checks_skipped,
            "thresholds": thresholds,
            "summary": {
                "total_issues": len(issues),
                "error_count": counts["error"],
                "warning_count": counts["warning"],
                "info_count": counts["info"],
            },
            "issues": issues,
            "media": media,
            "metrics": metrics,
        }

    def _run_video_checks(
        self,
        input_path: Path,
        duration: float,
        checks: list[str],
        thresholds: dict[str, float],
        metrics: dict[str, Any],
        issues: list[dict[str, Any]],
        checks_run: list[str],
        checks_skipped: list[dict[str, str]],
    ) -> None:
        filters: list[str] = []
        if "black_frames" in checks:
            filters.append(
                "blackdetect="
                f"d={thresholds['min_black_duration_seconds']}:"
                f"pix_th={thresholds['black_pixel_threshold']}:"
                f"pic_th={thresholds['black_picture_ratio_threshold']}"
            )
        if "freeze_frames" in checks:
            filters.append(
                "freezedetect="
                f"n={thresholds['freeze_noise_db']}dB:"
                f"d={thresholds['min_freeze_duration_seconds']}"
            )
        try:
            result = self.run_command(
                [
                    "ffmpeg",
                    "-hide_banner",
                    "-nostats",
                    "-nostdin",
                    *STRICT_DECODE_ARGS,
                    "-i",
                    str(input_path),
                    "-map",
                    "0:v:0",
                    "-vf",
                    ",".join(filters),
                    "-an",
                    "-f",
                    "null",
                    "-",
                ],
                timeout=600,
            )
            require_clean_decode(result.stderr or "")
        except Exception as exc:
            for check in checks:
                self._record_failure(check, exc, issues, checks_skipped)
            return

        output = result.stderr or ""
        if "black_frames" in checks:
            checks_run.append("black_frames")
            segments = self._parse_intervals(output, "black", duration)
            metrics["black_segments"] = segments
            issues.extend(
                self._interval_issues(
                    "black_segment",
                    "black_frames",
                    "Black section detected",
                    segments,
                )
            )
        if "freeze_frames" in checks:
            checks_run.append("freeze_frames")
            segments = self._parse_intervals(output, "freeze", duration)
            metrics["freeze_segments"] = segments
            issues.extend(
                self._interval_issues(
                    "freeze_segment",
                    "freeze_frames",
                    "Frozen section detected",
                    segments,
                )
            )

    def _run_audio_checks(
        self,
        input_path: Path,
        duration: float,
        checks: list[str],
        thresholds: dict[str, float],
        metrics: dict[str, Any],
        issues: list[dict[str, Any]],
        checks_run: list[str],
        checks_skipped: list[dict[str, str]],
    ) -> None:
        filters: list[str] = []
        if "silence" in checks:
            filters.append(
                "silencedetect="
                f"n={thresholds['silence_noise_db']}dB:"
                f"d={thresholds['min_silence_duration_seconds']}"
            )
        if "audio_loudness" in checks:
            filters.append("ebur128=peak=true")
        try:
            result = self.run_command(
                [
                    "ffmpeg",
                    "-hide_banner",
                    "-nostats",
                    "-nostdin",
                    *STRICT_DECODE_ARGS,
                    "-i",
                    str(input_path),
                    "-map",
                    "0:a:0",
                    "-af",
                    ",".join(filters),
                    "-vn",
                    "-f",
                    "null",
                    "-",
                ],
                timeout=600,
            )
            require_clean_decode(result.stderr or "")
        except Exception as exc:
            for check in checks:
                self._record_failure(check, exc, issues, checks_skipped)
            return

        output = result.stderr or ""
        if "silence" in checks:
            checks_run.append("silence")
            segments = self._parse_intervals(output, "silence", duration)
            metrics["silence_segments"] = segments
            issues.extend(
                self._interval_issues(
                    "silence_segment",
                    "silence",
                    "Silent section detected",
                    segments,
                )
            )
        if "audio_loudness" in checks:
            loudness = self._parse_loudness(output)
            metrics["audio_loudness"] = loudness
            if loudness["integrated_lufs"] is None or (
                loudness["true_peak_dbfs"] is None
                and self._loudness_value(output, "Peak", "dBFS") != -math.inf
            ):
                reason = "FFmpeg completed but reported incomplete loudness/true-peak evidence"
                self._skip(checks_skipped, "audio_loudness", reason)
                issues.append(
                    self._issue(
                        "audio_loudness_unavailable",
                        "error",
                        reason + ".",
                        check="audio_loudness",
                    )
                )
            else:
                checks_run.append("audio_loudness")
                self._append_loudness_issues(issues, loudness, thresholds)

    def _probe(self, input_path: Path) -> dict[str, Any]:
        result = self.run_command(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration,size:stream=width,height,codec_name,pix_fmt,"
                "r_frame_rate,sample_rate,channels,codec_type",
                "-of",
                "json",
                str(input_path),
            ]
        )
        probe_data = json.loads(result.stdout)
        video_stream = next(
            (
                stream
                for stream in probe_data.get("streams", [])
                if stream.get("codec_type") == "video"
            ),
            None,
        )
        audio_stream = next(
            (
                stream
                for stream in probe_data.get("streams", [])
                if stream.get("codec_type") == "audio"
            ),
            None,
        )
        format_info = probe_data.get("format", {})
        duration = float(format_info.get("duration", 0))
        file_size_bytes = int(format_info.get("size", 0))
        if not math.isfinite(duration) or duration < 0:
            raise ValueError("ffprobe returned an invalid media duration")
        if file_size_bytes < 0:
            raise ValueError("ffprobe returned an invalid media size")

        info: dict[str, Any] = {
            "duration": duration,
            "file_size_bytes": file_size_bytes,
            "file_size_mb": round(file_size_bytes / 1_000_000, 3),
            "has_audio": audio_stream is not None,
        }
        if video_stream:
            info.update(
                {
                    "width": video_stream.get("width"),
                    "height": video_stream.get("height"),
                    "pixel_format": video_stream.get("pix_fmt"),
                    "video_codec": video_stream.get("codec_name"),
                    "frame_rate": self._parse_frame_rate(
                        video_stream.get("r_frame_rate")
                    ),
                }
            )
        if audio_stream:
            info.update(
                {
                    "audio_codec": audio_stream.get("codec_name"),
                    "sample_rate": self._parse_optional_int(
                        audio_stream.get("sample_rate")
                    ),
                    "channels": audio_stream.get("channels"),
                }
            )
        return info

    @staticmethod
    def _profile_issues(
        media: dict[str, Any],
        expected: dict[str, Any],
    ) -> list[dict[str, Any]]:
        issues: list[dict[str, Any]] = []
        comparisons = [
            ("width", "width_mismatch", "Width"),
            ("height", "height_mismatch", "Height"),
            ("pixel_format", "pixel_format_mismatch", "Pixel format"),
            ("has_audio", "audio_presence_mismatch", "Audio presence"),
            ("video_codec", "video_codec_mismatch", "Video codec"),
            ("audio_codec", "audio_codec_mismatch", "Audio codec"),
        ]
        for field, code, label in comparisons:
            if field in expected and media.get(field) != expected[field]:
                issues.append(
                    TechnicalQC._issue(
                        code,
                        "error",
                        f"{label}: expected {expected[field]!r}, got {media.get(field)!r}.",
                        check="container",
                    )
                )
        if (
            "min_duration" in expected
            and media["duration"] < expected["min_duration"]
        ):
            issues.append(
                TechnicalQC._issue(
                    "duration_too_short",
                    "error",
                    (
                        f"Duration {media['duration']:.3f}s is below the expected "
                        f"minimum {expected['min_duration']}s."
                    ),
                    check="container",
                )
            )
        if (
            "max_duration" in expected
            and media["duration"] > expected["max_duration"]
        ):
            issues.append(
                TechnicalQC._issue(
                    "duration_too_long",
                    "error",
                    (
                        f"Duration {media['duration']:.3f}s exceeds the expected "
                        f"maximum {expected['max_duration']}s."
                    ),
                    check="container",
                )
            )
        if "frame_rate" in expected:
            actual_frame_rate = media.get("frame_rate")
            if actual_frame_rate is None or not math.isclose(
                actual_frame_rate,
                expected["frame_rate"],
                abs_tol=0.05,
            ):
                issues.append(
                    TechnicalQC._issue(
                        "frame_rate_mismatch",
                        "error",
                        (
                            f"Frame rate: expected {expected['frame_rate']!r}, "
                            f"got {actual_frame_rate!r}."
                        ),
                        check="container",
                    )
                )
        if (
            "audio_channels" in expected
            and media.get("channels") != expected["audio_channels"]
        ):
            issues.append(
                TechnicalQC._issue(
                    "audio_channels_mismatch",
                    "error",
                    (
                        f"Audio channels: expected {expected['audio_channels']!r}, "
                        f"got {media.get('channels')!r}."
                    ),
                    check="container",
                )
            )
        if (
            "audio_sample_rate" in expected
            and media.get("sample_rate") != expected["audio_sample_rate"]
        ):
            issues.append(
                TechnicalQC._issue(
                    "audio_sample_rate_mismatch",
                    "error",
                    (
                        "Audio sample rate: expected "
                        f"{expected['audio_sample_rate']!r}, "
                        f"got {media.get('sample_rate')!r}."
                    ),
                    check="container",
                )
            )
        if (
            "max_file_size_mb" in expected
            and media["file_size_bytes"]
            > expected["max_file_size_mb"] * 1_000_000
        ):
            issues.append(
                TechnicalQC._issue(
                    "file_size_too_large",
                    "error",
                    (
                        f"File size {media['file_size_mb']:.3f} MB exceeds the "
                        f"expected maximum {expected['max_file_size_mb']} MB."
                    ),
                    check="container",
                )
            )
        return issues

    @staticmethod
    def _resolve_config(
        inputs: dict[str, Any],
    ) -> tuple[list[str], dict[str, float]]:
        checks = inputs.get("checks", DEFAULT_CHECKS)
        if not isinstance(checks, list) or not checks:
            raise ValueError("checks must be a non-empty list")
        if len(checks) != len(set(checks)):
            raise ValueError("checks must not contain duplicates")
        unknown = sorted(set(checks) - set(DEFAULT_CHECKS))
        if unknown:
            raise ValueError("unknown checks: " + ", ".join(unknown))
        if inputs.get("expected") and "container" not in checks:
            raise ValueError("container check is required when expected values are set")

        expected = inputs.get("expected", {})
        if not isinstance(expected, dict):
            raise ValueError("expected must be an object")
        for name in (
            "min_duration",
            "max_duration",
            "frame_rate",
            "max_file_size_mb",
        ):
            if name not in expected:
                continue
            value = expected[name]
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(float(value))
                or value < 0
            ):
                raise ValueError(
                    f"expected.{name} must be a finite non-negative number"
                )
        if expected.get("frame_rate") == 0:
            raise ValueError("expected.frame_rate must be greater than zero")
        if (
            "min_duration" in expected
            and "max_duration" in expected
            and expected["min_duration"] > expected["max_duration"]
        ):
            raise ValueError(
                "expected.min_duration must not exceed expected.max_duration"
            )

        overrides = inputs.get("thresholds", {})
        if not isinstance(overrides, dict):
            raise ValueError("thresholds must be an object")
        unknown_thresholds = sorted(set(overrides) - set(DEFAULT_THRESHOLDS))
        if unknown_thresholds:
            raise ValueError(
                "unknown thresholds: " + ", ".join(unknown_thresholds)
            )
        thresholds = {**DEFAULT_THRESHOLDS, **overrides}
        for name, value in thresholds.items():
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f"{name} must be a finite number")
            if not math.isfinite(float(value)):
                raise ValueError(f"{name} must be a finite number")
            thresholds[name] = float(value)

        for name in (
            "min_black_duration_seconds",
            "min_freeze_duration_seconds",
            "min_silence_duration_seconds",
        ):
            if thresholds[name] <= 0:
                raise ValueError(f"{name} must be greater than zero")
        for name in (
            "black_pixel_threshold",
            "black_picture_ratio_threshold",
        ):
            if not 0 <= thresholds[name] <= 1:
                raise ValueError(f"{name} must be between 0 and 1")
        for name in ("freeze_noise_db", "silence_noise_db"):
            if not -100 <= thresholds[name] <= 0:
                raise ValueError(f"{name} must be between -100 and 0")
        for name in ("min_integrated_lufs", "max_integrated_lufs"):
            if not -100 <= thresholds[name] <= 0:
                raise ValueError(f"{name} must be between -100 and 0")
        if thresholds["min_integrated_lufs"] >= thresholds["max_integrated_lufs"]:
            raise ValueError(
                "min_integrated_lufs must be less than max_integrated_lufs"
            )
        if not -20 <= thresholds["clipping_true_peak_dbfs"] <= 0:
            raise ValueError(
                "clipping_true_peak_dbfs must be between -20 and 0"
            )
        return list(checks), thresholds

    @staticmethod
    def _parse_frame_rate(value: Any) -> float | None:
        if value in (None, "", "0/0"):
            return None
        try:
            rate = float(Fraction(str(value)))
        except (ValueError, ZeroDivisionError):
            return None
        if not math.isfinite(rate) or rate < 0:
            return None
        return round(rate, 3)

    @staticmethod
    def _parse_optional_int(value: Any) -> int | None:
        if value in (None, ""):
            return None
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return None
        return parsed if parsed >= 0 else None

    @staticmethod
    def _parse_intervals(
        output: str,
        prefix: str,
        media_duration: float,
    ) -> list[dict[str, float]]:
        starts = [
            float(value)
            for value in re.findall(
                rf"(?:lavfi\.)?{prefix}_start:\s*({_NUMBER_PATTERN})",
                output,
            )
        ]
        ends = [
            float(value)
            for value in re.findall(
                rf"(?:lavfi\.)?{prefix}_end:\s*({_NUMBER_PATTERN})",
                output,
            )
        ]
        durations = [
            float(value)
            for value in re.findall(
                rf"(?:lavfi\.)?{prefix}_duration:\s*({_NUMBER_PATTERN})",
                output,
            )
        ]
        segments: list[dict[str, float]] = []
        for index, start in enumerate(starts):
            if index < len(ends):
                end = ends[index]
            elif index < len(durations):
                end = start + durations[index]
            else:
                end = max(media_duration, start)
            if not math.isfinite(start) or not math.isfinite(end):
                raise ValueError(f"Invalid {prefix} interval timestamp")
            start = round(min(max(start, 0.0), media_duration), 3)
            end = round(min(max(end, start), media_duration), 3)
            segments.append(
                {
                    "start_seconds": start,
                    "end_seconds": end,
                    "duration_seconds": round(end - start, 3),
                }
            )
        return segments

    @staticmethod
    def _loudness_value(output: str, label: str, unit: str) -> float | None:
        # A progress sample must never stand in for a missing/invalid final
        # measurement. Include non-finite tokens so they cannot be skipped in
        # favor of an earlier finite match.
        summary = output.rsplit("Summary:", 1)[-1]
        values = re.findall(rf"\b{label}:\s*(\S+)\s+{unit}\b", summary)
        try:
            if not values:
                return None
            value = float(values[-1])
            # Only the explicit digital-silence token is meaningful infinity;
            # numeric overflow such as -1e999 is missing measurement evidence.
            if not math.isfinite(value) and values[-1].lower() != "-inf":
                return None
            return value
        except ValueError:
            return None

    @classmethod
    def _parse_loudness(cls, output: str) -> dict[str, float | None]:
        def final_finite(label: str, unit: str) -> float | None:
            value = cls._loudness_value(output, label, unit)
            return round(value, 2) if value is not None and math.isfinite(value) else None

        return {
            "integrated_lufs": final_finite("I", "LUFS"),
            "loudness_range_lu": final_finite("LRA", "LU"),
            "true_peak_dbfs": final_finite("Peak", "dBFS"),
        }

    @staticmethod
    def _interval_issues(
        code: str,
        check: str,
        label: str,
        segments: list[dict[str, float]],
    ) -> list[dict[str, Any]]:
        return [
            TechnicalQC._issue(
                code,
                "warning",
                (
                    f"{label} from {segment['start_seconds']:.3f}s to "
                    f"{segment['end_seconds']:.3f}s "
                    f"({segment['duration_seconds']:.3f}s)."
                ),
                check=check,
                **segment,
            )
            for segment in segments
        ]

    @staticmethod
    def _append_loudness_issues(
        issues: list[dict[str, Any]],
        loudness: dict[str, float | None],
        thresholds: dict[str, float],
    ) -> None:
        integrated = loudness["integrated_lufs"]
        if integrated is not None and integrated < thresholds["min_integrated_lufs"]:
            issues.append(
                TechnicalQC._issue(
                    "audio_too_quiet",
                    "warning",
                    f"Integrated loudness is very low ({integrated:.2f} LUFS).",
                    check="audio_loudness",
                    value=integrated,
                    threshold=thresholds["min_integrated_lufs"],
                )
            )
        if integrated is not None and integrated > thresholds["max_integrated_lufs"]:
            issues.append(
                TechnicalQC._issue(
                    "audio_too_loud",
                    "warning",
                    f"Integrated loudness is very high ({integrated:.2f} LUFS).",
                    check="audio_loudness",
                    value=integrated,
                    threshold=thresholds["max_integrated_lufs"],
                )
            )
        true_peak = loudness["true_peak_dbfs"]
        if (
            true_peak is not None
            and true_peak >= thresholds["clipping_true_peak_dbfs"]
        ):
            issues.append(
                TechnicalQC._issue(
                    "audio_clipping_risk",
                    "warning",
                    f"True peak is close to full scale ({true_peak:.2f} dBFS).",
                    check="audio_loudness",
                    value=true_peak,
                    threshold=thresholds["clipping_true_peak_dbfs"],
                )
            )

    @staticmethod
    def _issue(
        code: str,
        severity: str,
        message: str,
        **evidence: Any,
    ) -> dict[str, Any]:
        return {
            "code": code,
            "severity": severity,
            "message": message,
            **evidence,
        }

    @staticmethod
    def _skip(
        skipped: list[dict[str, str]],
        check: str,
        reason: str,
    ) -> None:
        skipped.append({"check": check, "reason": reason})

    @staticmethod
    def _record_failure(
        check: str,
        error: Exception,
        issues: list[dict[str, Any]],
        skipped: list[dict[str, str]],
    ) -> None:
        reason = f"FFmpeg check failed: {error}"
        TechnicalQC._skip(skipped, check, reason)
        issues.append(
            TechnicalQC._issue(
                "technical_check_failed",
                "error",
                reason,
                check=check,
            )
        )
