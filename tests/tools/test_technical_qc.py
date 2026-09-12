from __future__ import annotations

import json
import hashlib
from pathlib import Path
from types import SimpleNamespace

import jsonschema
import pytest

from tools.analysis.technical_qc import TechnicalQC
from tools.tool_registry import ToolRegistry


def _probe_payload(*, has_audio: bool = True, has_video: bool = True) -> str:
    streams = []
    if has_video:
        streams.append(
            {
                "codec_type": "video",
                "width": 1920,
                "height": 1080,
                "pix_fmt": "yuv420p",
                "codec_name": "h264",
                "r_frame_rate": "30/1",
            }
        )
    if has_audio:
        streams.append(
            {
                "codec_type": "audio",
                "codec_name": "aac",
                "sample_rate": "48000",
                "channels": 2,
            }
        )
    return json.dumps(
        {
            "format": {"duration": "10.0", "size": "2097152"},
            "streams": streams,
        }
    )


def _runner(
    *,
    has_audio: bool = True,
    has_video: bool = True,
    black_output: str = "",
    freeze_output: str = "",
    silence_output: str = "",
    loudness_output: str = "I: -16.0 LUFS\nLRA: 4.0 LU\nPeak: -1.0 dBFS",
    calls: list[list[str]] | None = None,
):
    def fake_run_command(self, cmd, *args, **kwargs):
        if calls is not None:
            calls.append(cmd)
        if cmd[0] == "ffprobe":
            return SimpleNamespace(
                stdout=_probe_payload(
                    has_audio=has_audio,
                    has_video=has_video,
                ),
                stderr="",
            )
        command_text = " ".join(cmd)
        outputs: list[str] = []
        if "blackdetect=" in command_text:
            outputs.append(black_output)
        if "freezedetect=" in command_text:
            outputs.append(freeze_output)
        if "silencedetect=" in command_text:
            outputs.append(silence_output)
        if "ebur128=peak=true" in command_text:
            outputs.append(loudness_output)
        if outputs:
            return SimpleNamespace(stdout="", stderr="\n".join(outputs))
        raise AssertionError(f"Unexpected command: {cmd}")

    return fake_run_command


def test_technical_qc_contract_and_registry_discovery() -> None:
    info = TechnicalQC().get_info()
    assert info["name"] == "technical_qc"
    assert info["capability"] == "analysis"
    assert info["provider"] == "ffmpeg"
    assert info["runtime"] == "local"
    assert info["dependencies"] == ["cmd:ffmpeg", "cmd:ffprobe"]

    registry = ToolRegistry()
    registry.discover()
    assert registry.get("technical_qc") is not None


def test_changed_input_during_scan_preserves_existing_report(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    media = Path("projects/scan/renders/final.mp4")
    media.parent.mkdir(parents=True)
    media.write_bytes(b"original video")
    report = Path("projects/scan/artifacts/technical_qc.json")
    report.parent.mkdir(parents=True)
    report.write_text("previous report")
    runner = _runner()

    def replace_input(self, cmd, *args, **kwargs):
        if cmd[0] == "ffprobe":
            media.write_bytes(b"replaced video")
        return runner(self, cmd, *args, **kwargs)

    monkeypatch.setattr(TechnicalQC, "run_command", replace_input)
    result = TechnicalQC().execute({"input_path": str(media), "report_path": str(report)})
    assert not result.success
    assert "input changed during scan" in result.error
    assert report.read_text() == "previous report"


def test_technical_qc_clean_file_matches_output_schema(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    input_path = tmp_path / "render.mp4"
    input_path.write_bytes(b"video")
    calls: list[list[str]] = []
    monkeypatch.setattr(TechnicalQC, "run_command", _runner(calls=calls))

    result = TechnicalQC().execute({"input_path": str(input_path)})

    assert result.success is True
    assert result.data["status"] == "pass"
    assert result.data["passed"] is True
    assert result.data["input_sha256"] == hashlib.sha256(b"video").hexdigest()
    assert result.data["issues"] == []
    assert result.data["checks_run"] == [
        "container",
        "black_frames",
        "freeze_frames",
        "silence",
        "audio_loudness",
    ]
    assert result.data["checks_skipped"] == []
    assert result.data["metrics"]["audio_loudness"] == {
        "integrated_lufs": -16.0,
        "loudness_range_lu": 4.0,
        "true_peak_dbfs": -1.0,
    }
    ffmpeg_calls = [cmd for cmd in calls if cmd[0] == "ffmpeg"]
    assert len(ffmpeg_calls) == 2
    assert all(command[-1] == "-" for command in ffmpeg_calls)
    jsonschema.validate(instance=result.data, schema=TechnicalQC.output_schema)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(
            instance={**result.data, "unexpected": True},
            schema=TechnicalQC.output_schema,
        )


def test_technical_qc_reports_intervals_and_loudness_warnings(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    input_path = tmp_path / "render.mp4"
    input_path.write_bytes(b"video")
    monkeypatch.setattr(
        TechnicalQC,
        "run_command",
        _runner(
            black_output=(
                "[blackdetect @ 0x1] black_start:1 black_end:2.5 "
                "black_duration:1.5"
            ),
            freeze_output=(
                "[freezedetect @ 0x1] lavfi.freezedetect.freeze_start: 3\n"
                "[freezedetect @ 0x1] lavfi.freezedetect.freeze_duration: 2.25\n"
                "[freezedetect @ 0x1] lavfi.freezedetect.freeze_end: 5.25"
            ),
            silence_output=(
                "[silencedetect @ 0x1] silence_start: 6\n"
                "[silencedetect @ 0x1] silence_end: 9 | silence_duration: 3"
            ),
            loudness_output="I: -40.0 LUFS\nLRA: 2.0 LU\nPeak: 0.0 dBFS",
        ),
    )

    result = TechnicalQC().execute({"input_path": str(input_path)})

    assert result.success is True
    assert result.data["status"] == "pass_with_warnings"
    assert result.data["passed"] is True
    assert result.data["summary"] == {
        "total_issues": 5,
        "error_count": 0,
        "warning_count": 5,
        "info_count": 0,
    }
    assert {issue["code"] for issue in result.data["issues"]} == {
        "black_segment",
        "freeze_segment",
        "silence_segment",
        "audio_too_quiet",
        "audio_clipping_risk",
    }
    assert result.data["metrics"]["freeze_segments"] == [
        {
            "start_seconds": 3.0,
            "end_seconds": 5.25,
            "duration_seconds": 2.25,
        }
    ]
    jsonschema.validate(instance=result.data, schema=TechnicalQC.output_schema)


def test_technical_qc_profile_mismatch_fails_report(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    input_path = tmp_path / "render.mp4"
    input_path.write_bytes(b"video")
    monkeypatch.setattr(TechnicalQC, "run_command", _runner())

    result = TechnicalQC().execute(
        {
            "input_path": str(input_path),
            "checks": ["container"],
            "expected": {"width": 1080, "height": 1920, "has_audio": True},
        }
    )

    assert result.success is True
    assert result.data["status"] == "fail"
    assert result.data["passed"] is False
    assert result.data["summary"]["error_count"] == 2
    assert {issue["code"] for issue in result.data["issues"]} == {
        "width_mismatch",
        "height_mismatch",
    }
    jsonschema.validate(instance=result.data, schema=TechnicalQC.output_schema)


def test_technical_qc_validates_extended_delivery_profile(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    input_path = tmp_path / "render.mp4"
    input_path.write_bytes(b"video")
    monkeypatch.setattr(TechnicalQC, "run_command", _runner())

    result = TechnicalQC().execute(
        {
            "input_path": str(input_path),
            "checks": ["container"],
            "expected": {
                "frame_rate": 25,
                "video_codec": "hevc",
                "audio_codec": "mp3",
                "audio_channels": 1,
                "audio_sample_rate": 44100,
                "max_file_size_mb": 1,
            },
        }
    )

    assert result.success is True
    assert result.data["status"] == "fail"
    assert {issue["code"] for issue in result.data["issues"]} == {
        "frame_rate_mismatch",
        "video_codec_mismatch",
        "audio_codec_mismatch",
        "audio_channels_mismatch",
        "audio_sample_rate_mismatch",
        "file_size_too_large",
    }
    assert result.data["media"]["frame_rate"] == 30.0
    assert result.data["media"]["sample_rate"] == 48000
    assert result.data["media"]["file_size_bytes"] == 2097152
    assert result.data["media"]["file_size_mb"] == 2.097
    jsonschema.validate(instance=result.data, schema=TechnicalQC.output_schema)


def test_technical_qc_skips_audio_checks_without_audio_stream(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    input_path = tmp_path / "silent-render.mp4"
    input_path.write_bytes(b"video")
    calls: list[list[str]] = []
    monkeypatch.setattr(
        TechnicalQC,
        "run_command",
        _runner(has_audio=False, calls=calls),
    )

    result = TechnicalQC().execute({"input_path": str(input_path)})

    assert result.success is True
    assert result.data["status"] == "pass_with_warnings"
    assert result.data["checks_run"] == [
        "container",
        "black_frames",
        "freeze_frames",
    ]
    assert result.data["checks_skipped"] == [
        {"check": "silence", "reason": "input has no audio stream"},
        {"check": "audio_loudness", "reason": "input has no audio stream"},
    ]
    assert [issue["code"] for issue in result.data["issues"]] == [
        "audio_stream_missing"
    ]
    assert not any("silencedetect=" in " ".join(cmd) for cmd in calls)
    assert not any("ebur128=" in " ".join(cmd) for cmd in calls)


def test_technical_qc_accepts_intentionally_silent_video(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    input_path = tmp_path / "intentional-silent-render.mp4"
    input_path.write_bytes(b"video")
    monkeypatch.setattr(
        TechnicalQC,
        "run_command",
        _runner(has_audio=False),
    )

    result = TechnicalQC().execute(
        {
            "input_path": str(input_path),
            "expected": {"has_audio": False},
        }
    )

    assert result.success is True
    assert result.data["status"] == "pass"
    assert result.data["passed"] is True
    assert result.data["issues"] == []
    assert [item["check"] for item in result.data["checks_skipped"]] == [
        "silence",
        "audio_loudness",
    ]


def test_technical_qc_fails_when_required_audio_is_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    input_path = tmp_path / "missing-audio.mp4"
    input_path.write_bytes(b"video")
    monkeypatch.setattr(
        TechnicalQC,
        "run_command",
        _runner(has_audio=False),
    )

    result = TechnicalQC().execute(
        {
            "input_path": str(input_path),
            "checks": ["container"],
            "expected": {"has_audio": True},
        }
    )

    assert result.success is True
    assert result.data["status"] == "fail"
    assert result.data["passed"] is False
    assert [issue["code"] for issue in result.data["issues"]] == [
        "audio_presence_mismatch"
    ]


def test_technical_qc_fails_when_video_stream_is_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    input_path = tmp_path / "audio-only.mp4"
    input_path.write_bytes(b"audio")
    monkeypatch.setattr(
        TechnicalQC,
        "run_command",
        _runner(has_video=False),
    )

    result = TechnicalQC().execute({"input_path": str(input_path)})

    assert result.success is True
    assert result.data["status"] == "fail"
    assert result.data["passed"] is False
    assert [issue["code"] for issue in result.data["issues"]] == [
        "video_stream_missing"
    ]
    assert [item["check"] for item in result.data["checks_skipped"]] == [
        "black_frames",
        "freeze_frames",
    ]


def test_technical_qc_writes_project_scoped_json_report(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    input_path = tmp_path / "render.mp4"
    input_path.write_bytes(b"video")
    report_path = Path("projects/demo/artifacts/technical_qc.json")
    monkeypatch.setattr(TechnicalQC, "run_command", _runner())

    result = TechnicalQC().execute(
        {
            "input_path": str(input_path),
            "checks": ["container"],
            "report_path": str(report_path),
        }
    )

    assert result.success is True
    assert result.data["report_path"] == report_path.as_posix()
    assert result.artifacts == [report_path.as_posix()]
    saved = json.loads(report_path.read_text(encoding="utf-8"))
    assert saved == result.data
    assert report_path.read_bytes().endswith(b"\n")
    jsonschema.validate(instance=saved, schema=TechnicalQC.output_schema)


@pytest.mark.parametrize(
    "report_path",
    ["technical_qc.json", "projects/demo/artifacts/technical_qc.txt"],
)
def test_technical_qc_rejects_invalid_report_path_before_probe(
    report_path: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    input_path = tmp_path / "render.mp4"
    input_path.write_bytes(b"video")
    command_calls: list[list[str]] = []
    monkeypatch.setattr(
        TechnicalQC,
        "run_command",
        lambda self, cmd, *args, **kwargs: command_calls.append(cmd),
    )

    result = TechnicalQC().execute(
        {"input_path": str(input_path), "report_path": report_path}
    )

    assert result.success is False
    assert "report_path" in (result.error or "")
    assert command_calls == []


def test_technical_qc_schema_and_runtime_config_validation() -> None:
    jsonschema.validate(
        instance={"input_path": "render.mp4"},
        schema=TechnicalQC.input_schema,
    )
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(
            instance={
                "input_path": "render.mp4",
                "thresholds": {"min_black_duration_seconds": 0},
            },
            schema=TechnicalQC.input_schema,
        )
    with pytest.raises(ValueError, match="min_integrated_lufs"):
        TechnicalQC._resolve_config(
            {
                "thresholds": {
                    "min_integrated_lufs": -8,
                    "max_integrated_lufs": -35,
                }
            }
        )
    with pytest.raises(ValueError, match="container check"):
        TechnicalQC._resolve_config(
            {"checks": ["black_frames"], "expected": {"width": 1920}}
        )
    with pytest.raises(ValueError, match="min_duration"):
        TechnicalQC._resolve_config(
            {"expected": {"min_duration": 10, "max_duration": 5}}
        )
    with pytest.raises(ValueError, match="max_integrated_lufs"):
        TechnicalQC._resolve_config(
            {"thresholds": {"max_integrated_lufs": 1}}
        )


def test_technical_qc_rejects_non_finite_probe_duration(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    input_path = tmp_path / "broken.mp4"
    input_path.write_bytes(b"video")
    monkeypatch.setattr(
        TechnicalQC,
        "run_command",
        lambda self, cmd, *args, **kwargs: SimpleNamespace(
            stdout=json.dumps({"format": {"duration": "NaN", "size": "1"}}),
            stderr="",
        ),
    )

    result = TechnicalQC().execute({"input_path": str(input_path)})

    assert result.success is False
    assert "invalid media duration" in (result.error or "")


def test_technical_qc_interval_parser_closes_trailing_interval_at_media_end() -> None:
    assert TechnicalQC._parse_intervals(
        "[silencedetect @ 0x1] silence_start: 7.5",
        "silence",
        10.0,
    ) == [
        {
            "start_seconds": 7.5,
            "end_seconds": 10.0,
            "duration_seconds": 2.5,
        }
    ]


def test_technical_qc_parses_ntsc_frame_rate() -> None:
    assert TechnicalQC._parse_frame_rate("30000/1001") == 29.97
    assert TechnicalQC._parse_frame_rate("0/0") is None


def test_technical_qc_keeps_partial_report_when_one_ffmpeg_scan_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    input_path = tmp_path / "render.mp4"
    input_path.write_bytes(b"video")

    def fake_run_command(self, cmd, *args, **kwargs):
        if cmd[0] == "ffprobe":
            return SimpleNamespace(stdout=_probe_payload(), stderr="")
        if "blackdetect=" in " ".join(cmd):
            raise RuntimeError("video filter unavailable")
        return SimpleNamespace(
            stdout="",
            stderr="I: -16.0 LUFS\nLRA: 4.0 LU\nPeak: -1.0 dBFS",
        )

    monkeypatch.setattr(TechnicalQC, "run_command", fake_run_command)

    result = TechnicalQC().execute({"input_path": str(input_path)})

    assert result.success is True
    assert result.data["status"] == "fail"
    assert result.data["passed"] is False
    assert result.data["summary"]["error_count"] == 2
    assert result.data["checks_run"] == [
        "container",
        "silence",
        "audio_loudness",
    ]
    assert [item["check"] for item in result.data["checks_skipped"]] == [
        "black_frames",
        "freeze_frames",
    ]
    assert [issue["code"] for issue in result.data["issues"]] == [
        "technical_check_failed",
        "technical_check_failed",
    ]


def test_technical_qc_rejects_decoder_errors_even_with_zero_exit(tmp_path, monkeypatch):
    input_path = tmp_path / "corrupt.mp4"
    input_path.write_bytes(b"video")
    monkeypatch.setattr(TechnicalQC, "run_command", _runner(
        black_output="[h264] [error] Error submitting packet to decoder: Invalid data"
    ))
    result = TechnicalQC().execute({"input_path": str(input_path)})
    assert result.success
    assert result.data["status"] == "fail"
    assert "black_frames" not in result.data["checks_run"]
    assert "freeze_frames" not in result.data["checks_run"]


@pytest.mark.parametrize("summary", [
    "", "I: -16.0 LUFS\nLRA: 0.0 LU", "I: nan LUFS\nPeak: -1.0 dBFS",
    "I: -16.0 LUFS\nSummary:\nI: nan LUFS\nPeak: -1.0 dBFS",
    "Peak: -1.0 dBFS\nSummary:\nI: -16.0 LUFS\nPeak: nan dBFS",
    "Peak: -inf dBFS\nSummary:\nI: -16.0 LUFS",
    "I: -16.0 LUFS\nPeak: -1.0 dBFS\nSummary:\n",
    "I: -16.0 LUFS\nI: 1e999 LUFS\nPeak: -1.0 dBFS",
    "Summary:\nI: -16.0 LUFS\nPeak: -1e999 dBFS",
])
def test_technical_qc_fails_incomplete_loudness_summary(tmp_path, monkeypatch, summary):
    input_path = tmp_path / "render.mp4"
    input_path.write_bytes(b"video")
    monkeypatch.setattr(TechnicalQC, "run_command", _runner(loudness_output=summary))
    result = TechnicalQC().execute({"input_path": str(input_path), "checks": ["audio_loudness"]})
    assert result.success
    assert result.data["passed"] is False
    assert result.data["checks_run"] == []
    assert result.data["checks_skipped"][0]["check"] == "audio_loudness"


def test_technical_qc_parses_exponents_and_keeps_intervals_consistent():
    intervals = TechnicalQC._parse_intervals(
        "silence_start: 2.08333e-05\nsilence_end: 4 | silence_duration: 3.99998",
        "silence", 4.0,
    )
    assert intervals == [{"start_seconds": 0.0, "end_seconds": 4.0, "duration_seconds": 4.0}]
    assert TechnicalQC._parse_intervals(
        "freeze_start: -0.5\nfreeze_end: 10\nfreeze_duration: 10.5", "freeze", 4.0
    ) == [{"start_seconds": 0.0, "end_seconds": 4.0, "duration_seconds": 4.0}]


def test_technical_qc_accepts_measured_digital_silence_peak(tmp_path, monkeypatch):
    input_path = tmp_path / "silent.mp4"
    input_path.write_bytes(b"video")
    monkeypatch.setattr(TechnicalQC, "run_command", _runner(
        loudness_output="Summary:\nI: -70.0 LUFS\nLRA: 0.0 LU\nPeak: -inf dBFS"
    ))
    result = TechnicalQC().execute({"input_path": str(input_path), "checks": ["audio_loudness"]})
    assert result.success
    assert result.data["checks_run"] == ["audio_loudness"]
    assert not result.data["checks_skipped"]
    assert not any(issue["code"] == "audio_loudness_unavailable" for issue in result.data["issues"])


def test_decode_validation_does_not_treat_filename_as_error_level():
    from lib.ffmpeg_validation import require_clean_decode

    require_clean_decode("[info] Input #0, mov, from 'projects/demo/[error]/clip.mp4':")
    require_clean_decode("[info] title: concealing playback errors in an instructional video")
    with pytest.raises(ValueError, match="FFmpeg decoding failed"):
        require_clean_decode("[h264 @ 0x123] [warning] concealing 80 DC, 80 AC, 80 MV errors in P frame")
