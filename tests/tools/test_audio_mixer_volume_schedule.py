"""Audio mixer Path B integration: music_volume_schedule drives a time-varying
volume envelope on the music track in place of static sidechain ducking.

These tests intercept ``run_command`` so they do not require a working FFmpeg
binary or any sample audio. The full FFmpeg roundtrip is exercised by the
end-to-end integration test in test_audio_mixer_volume_schedule_e2e.py.
"""

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from tools.audio.audio_mixer import AudioMixer


def _capture_ffmpeg_cmd(tool: AudioMixer, inputs: dict) -> list[str]:
    """Invoke the tool with run_command mocked; return the cmd list it would have run."""
    captured: list[list[str]] = []

    def fake_run_command(cmd, **kwargs):
        captured.append(cmd)
        class _Stub:
            returncode = 0
            stdout = ""
            stderr = ""
        return _Stub()

    with patch.object(tool, "run_command", side_effect=fake_run_command):
        result = tool.execute(inputs)
    assert result.success, f"tool failed: {result.error}"
    assert captured, "no ffmpeg command was constructed"
    return captured[-1]


def _capture_full_mix_ffmpeg_cmd(tool: AudioMixer, inputs: dict) -> list[str]:
    """Capture a full_mix command without requiring FFmpeg to create output."""
    captured: list[list[str]] = []

    def fake_run_command(cmd, **kwargs):
        captured.append(cmd)
        class _Stub:
            returncode = 0
            stdout = ""
            stderr = ""
        return _Stub()

    with (
        patch.object(tool, "run_command", side_effect=fake_run_command),
        patch.object(tool, "_probe_audio_duration", return_value=10.0),
    ):
        result = tool.execute(inputs)
    assert result.success, f"tool failed: {result.error}"
    assert captured, "no ffmpeg command was constructed"
    return captured[-1]


def test_duck_without_schedule_uses_legacy_sidechaincompress():
    """Sanity: when no music_volume_schedule is provided, the existing
    sidechaincompress path is unchanged."""
    tool = AudioMixer()
    cmd = _capture_ffmpeg_cmd(tool, {
        "operation": "duck",
        "primary_audio": "speech.wav",
        "secondary_audio": "music.wav",
        "duck_level": -18,
        "output_path": "out.wav",
    })
    fc = " ".join(cmd)
    assert "sidechaincompress" in fc, f"legacy path must use sidechaincompress, got: {fc}"
    assert "eval=frame" not in fc, "schedule path should not be triggered without schedule input"


def _make_placeholder_inputs(tmp_path):
    """Create empty placeholder WAVs so the existence guard passes in mocked tests."""
    speech = tmp_path / "speech.wav"
    music = tmp_path / "music.wav"
    speech.write_bytes(b"")
    music.write_bytes(b"")
    return str(speech), str(music)


def test_duck_with_schedule_emits_time_varying_volume_filter(tmp_path):
    """Path B: a music_volume_schedule input replaces sidechaincompress with a
    deterministic time-varying volume envelope."""
    tool = AudioMixer()
    speech, music = _make_placeholder_inputs(tmp_path)
    schedule = [
        {"t_seconds": 0.0, "gain_db": 0.0},
        {"t_seconds": 1.7, "gain_db": 0.0},
        {"t_seconds": 2.0, "gain_db": -18.0},
        {"t_seconds": 8.0, "gain_db": -18.0},
        {"t_seconds": 8.3, "gain_db": 0.0},
    ]
    cmd = _capture_ffmpeg_cmd(tool, {
        "operation": "duck",
        "primary_audio": speech,
        "secondary_audio": music,
        "music_volume_schedule": schedule,
        "output_path": str(tmp_path / "out.wav"),
    })
    fc = " ".join(cmd)
    assert "eval=frame" in fc, f"schedule path requires eval=frame for per-frame volume, got: {fc}"
    assert "volume=" in fc, f"expected a volume filter, got: {fc}"
    assert "sidechaincompress" not in fc, (
        f"schedule path must replace sidechaincompress, but it is still present: {fc}"
    )


def test_full_mix_with_schedule_emits_time_varying_music_volume_filter(tmp_path):
    """Path B schedule must be honored by the compose-facing full_mix operation."""
    tool = AudioMixer()
    speech, music = _make_placeholder_inputs(tmp_path)
    schedule = [
        {"t_seconds": 0.0, "gain_db": 0.0},
        {"t_seconds": 2.0, "gain_db": -18.0},
        {"t_seconds": 8.0, "gain_db": -18.0},
    ]
    cmd = _capture_full_mix_ffmpeg_cmd(tool, {
        "operation": "full_mix",
        "tracks": [
            {"path": speech, "role": "speech", "start_seconds": 0},
            {"path": music, "role": "music", "volume": 0.2},
        ],
        "music_volume_schedule": schedule,
        "output_path": str(tmp_path / "full-mix.wav"),
    })
    fc = " ".join(cmd)
    assert "eval=frame" in fc, f"full_mix schedule path requires eval=frame, got: {fc}"
    assert "volume=" in fc, f"expected a volume filter, got: {fc}"
    assert "sidechaincompress" not in fc, (
        f"full_mix schedule path must replace sidechaincompress, got: {fc}"
    )


def test_duck_with_empty_schedule_falls_through_to_legacy():
    """An explicitly empty schedule is the same as not providing one — legacy path."""
    tool = AudioMixer()
    cmd = _capture_ffmpeg_cmd(tool, {
        "operation": "duck",
        "primary_audio": "speech.wav",
        "secondary_audio": "music.wav",
        "music_volume_schedule": [],
        "output_path": "out.wav",
    })
    fc = " ".join(cmd)
    assert "sidechaincompress" in fc, "empty schedule must fall through to legacy path"


def test_duck_schedule_filter_includes_input_paths_and_output(tmp_path):
    """The constructed command must reference both input files and the output path."""
    tool = AudioMixer()
    speech = tmp_path / "speech-fixture.wav"
    music = tmp_path / "music-fixture.wav"
    out = tmp_path / "duck-out.wav"
    speech.write_bytes(b"")
    music.write_bytes(b"")
    cmd = _capture_ffmpeg_cmd(tool, {
        "operation": "duck",
        "primary_audio": str(speech),
        "secondary_audio": str(music),
        "music_volume_schedule": [
            {"t_seconds": 0.0, "gain_db": 0.0},
            {"t_seconds": 5.0, "gain_db": -18.0},
        ],
        "output_path": str(out),
    })
    assert str(speech) in cmd
    assert str(music) in cmd
    assert str(out) in cmd


def test_duck_schedule_emits_amix_to_combine_speech_and_ducked_music(tmp_path):
    """Schedule path must still mix speech with the (now schedule-ducked) music."""
    tool = AudioMixer()
    speech, music = _make_placeholder_inputs(tmp_path)
    cmd = _capture_ffmpeg_cmd(tool, {
        "operation": "duck",
        "primary_audio": speech,
        "secondary_audio": music,
        "music_volume_schedule": [{"t_seconds": 0.0, "gain_db": -10.0}],
        "output_path": str(tmp_path / "out.wav"),
    })
    fc = " ".join(cmd)
    assert "amix" in fc, f"schedule path must still mix speech+music, got: {fc}"


def test_duck_schedule_returns_clean_error_on_missing_input_file(tmp_path):
    """When the speech or music input doesn't exist, audio_mixer must fail with
    a structured ToolResult error — not let subprocess raise an opaque exception."""
    tool = AudioMixer()
    missing_speech = tmp_path / "does-not-exist.wav"
    out = tmp_path / "out.wav"

    result = tool.execute({
        "operation": "duck",
        "primary_audio": str(missing_speech),
        "secondary_audio": str(missing_speech),  # both missing
        "music_volume_schedule": [{"t_seconds": 0.0, "gain_db": -10.0}],
        "output_path": str(out),
    })
    assert result.success is False
    err = (result.error or "").lower()
    # Require an explicit 'not found' message — not the opaque
    # subprocess.CalledProcessError dump that incidentally contains a /tmp path.
    assert "not found" in err, (
        f"expected explicit 'not found' file-existence error, got: {result.error!r}"
    )
    assert "ffmpeg" not in err, (
        f"error should be raised before invoking ffmpeg, got subprocess dump: {result.error!r}"
    )
