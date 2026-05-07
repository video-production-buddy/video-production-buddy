#!/usr/bin/env python3
"""QA Test 04: Audio mixing — full_mix, ducking, TTS format detection.

Run:  python -m pytest tests/qa/test_04_audio_mix.py -v
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from lib.env_loader import load_env

load_env()

from tools.audio.audio_mixer import AudioMixer
from tools.audio.cosyvoice_tts import CosyVoiceTTS

OUT = Path(__file__).parent / "output"
OUT.mkdir(exist_ok=True)


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _gen_sine(path: Path, duration: int = 5, frequency: int = 440) -> Path:
    """Generate a sine-wave MP3 fixture if it doesn't already exist."""
    if path.exists():
        return path
    subprocess.run(
        [
            "ffmpeg", "-y", "-f", "lavfi",
            "-i", f"sine=frequency={frequency}:duration={duration}",
            "-ar", "44100", "-ac", "1", str(path),
        ],
        capture_output=True,
        check=True,
    )
    return path


def _gen_noise(path: Path, duration: int = 15) -> Path:
    """Generate pink-noise MP3 fixture if it doesn't already exist."""
    if path.exists():
        return path
    subprocess.run(
        [
            "ffmpeg", "-y", "-f", "lavfi",
            "-i", f"anoisesrc=d={duration}:c=pink",
            "-ar", "44100", "-ac", "1", str(path),
        ],
        capture_output=True,
        check=True,
    )
    return path


def _probe_codec(path: Path) -> str:
    """Return codec_name of the first audio stream, or empty string on error."""
    proc = subprocess.run(
        [
            "ffprobe", "-v", "quiet", "-print_format", "json",
            "-show_streams", str(path),
        ],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        return ""
    data = json.loads(proc.stdout)
    streams = data.get("streams", [])
    return streams[0].get("codec_name", "") if streams else ""


@pytest.fixture(scope="module")
def speech_file() -> Path:
    return _gen_sine(OUT / "tts_fixture.mp3", duration=8, frequency=440)


@pytest.fixture(scope="module")
def music_file() -> Path:
    return _gen_noise(OUT / "music_fixture.mp3", duration=15)


@pytest.fixture(scope="module")
def mixer() -> AudioMixer:
    return AudioMixer()


# ── Pattern B2: full_mix result must include duration_seconds ─────────────────

def test_full_mix_result_includes_duration_seconds(mixer, speech_file, music_file):
    """full_mix ToolResult.data must contain a positive duration_seconds float."""
    out = OUT / "test_full_mix_duration.aac"
    result = mixer.execute({
        "operation": "full_mix",
        "tracks": [
            {"path": str(speech_file), "role": "speech", "start_seconds": 0},
            {"path": str(music_file), "role": "music", "volume": 0.15},
        ],
        "ducking": {"enabled": True, "music_volume_during_speech": 0.15},
        "normalize": True,
        "output_path": str(out),
    })
    assert result.success, f"full_mix failed: {result.error}"
    dur = result.data.get("duration_seconds")
    assert dur is not None, "duration_seconds missing from full_mix result"
    assert isinstance(dur, float), f"duration_seconds is not float: {type(dur)}"
    assert dur > 0, f"duration_seconds is non-positive: {dur}"


def test_full_mix_produces_valid_audio(mixer, speech_file, music_file):
    """full_mix output must be a valid audio file with a known codec."""
    out = OUT / "test_full_mix_codec.aac"
    result = mixer.execute({
        "operation": "full_mix",
        "tracks": [
            {"path": str(speech_file), "role": "speech"},
            {"path": str(music_file), "role": "music", "volume": 0.15},
        ],
        "output_path": str(out),
    })
    assert result.success, f"full_mix failed: {result.error}"
    assert out.exists(), "Output file not created"
    codec = _probe_codec(out)
    assert codec != "", f"ffprobe returned empty codec for {out}"


def test_full_mix_duration_within_tolerance(mixer, speech_file, music_file):
    """Mix duration must cover at least the full speech track.

    With sidechaincompress, the effective output ends when the sidechain (speech)
    ends. The invariant is: duration >= speech_duration (8s) - 1s tolerance.
    In production, narration spans the full video so the mix covers the full target.
    """
    out = OUT / "test_full_mix_tolerance.aac"
    result = mixer.execute({
        "operation": "full_mix",
        "tracks": [
            {"path": str(speech_file), "role": "speech"},   # 8s
            {"path": str(music_file), "role": "music", "volume": 0.15},  # 15s
        ],
        "output_path": str(out),
    })
    assert result.success, f"full_mix failed: {result.error}"
    dur = result.data.get("duration_seconds")
    assert dur is not None
    # Must cover at least the speech (8s - 1s tolerance)
    assert dur >= 7.0, f"Mix duration {dur:.2f}s is shorter than speech track (8s)"
    # Must not run longer than the music track + 1s buffer
    assert dur <= 16.0, f"Mix duration {dur:.2f}s exceeds expected ceiling (16s)"


# ── Pattern B: _duck() sidechaincompress (label split fix) ────────────────────

def test_duck_operation_succeeds(mixer, speech_file, music_file):
    """duck operation must succeed without filter-graph label errors."""
    out = OUT / "test_duck.aac"
    result = mixer.execute({
        "operation": "duck",
        "primary_audio": str(speech_file),
        "secondary_audio": str(music_file),
        "duck_level": -12,
        "output_path": str(out),
    })
    assert result.success, f"duck failed: {result.error}"
    assert out.exists()


# ── Pattern B2: sidechaincompress fallback still produces output ───────────────

def test_sidechaincompress_fallback(mixer, speech_file, music_file):
    """When sidechaincompress fails, full_mix must fall back to fixed-volume mix."""
    out = OUT / "test_full_mix_fallback.aac"

    original_run = mixer.run_command

    def failing_run(cmd, **kwargs):
        if "sidechaincompress" in " ".join(str(c) for c in cmd):
            raise RuntimeError("sidechaincompress: filter not available (simulated)")
        return original_run(cmd, **kwargs)

    with patch.object(mixer, "run_command", side_effect=failing_run):
        result = mixer.execute({
            "operation": "full_mix",
            "tracks": [
                {"path": str(speech_file), "role": "speech"},
                {"path": str(music_file), "role": "music", "volume": 0.15},
            ],
            "output_path": str(out),
        })

    assert result.success, f"fallback mix failed: {result.error}"
    assert out.exists(), "Fallback output not created"
    dur = result.data.get("duration_seconds")
    assert dur is not None, "Fallback result missing duration_seconds"
    assert dur > 0


# ── Pattern A: TTS format detection (_ensure_audio_format) ────────────────────

def test_tts_format_detection_transcodes_wav_to_mp3():
    """_ensure_audio_format must transcode WAV-content bytes to MP3 on disk."""
    with tempfile.TemporaryDirectory() as tmpdir:
        wav_src = Path(tmpdir) / "source.wav"
        subprocess.run(
            [
                "ffmpeg", "-y", "-f", "lavfi",
                "-i", "sine=frequency=440:duration=2",
                "-ar", "16000", "-ac", "1", str(wav_src),
            ],
            capture_output=True,
            check=True,
        )
        wav_bytes = wav_src.read_bytes()
        assert wav_bytes[:4] == b"RIFF" and wav_bytes[8:12] == b"WAVE", \
            "Test fixture is not WAV"

        out_mp3 = Path(tmpdir) / "output.mp3"
        actual_fmt = CosyVoiceTTS._ensure_audio_format(wav_bytes, "mp3", out_mp3)

        assert actual_fmt == "wav", f"Expected actual_fmt='wav', got '{actual_fmt}'"
        assert out_mp3.exists(), "MP3 output not created"
        codec = _probe_codec(out_mp3)
        assert codec == "mp3", f"Output codec is '{codec}', expected 'mp3'"


def test_tts_format_detection_passthrough_when_format_matches():
    """_ensure_audio_format must write bytes directly when format already matches."""
    with tempfile.TemporaryDirectory() as tmpdir:
        mp3_src = Path(tmpdir) / "source.mp3"
        subprocess.run(
            [
                "ffmpeg", "-y", "-f", "lavfi",
                "-i", "sine=frequency=440:duration=1",
                "-ar", "16000", "-ac", "1", "-acodec", "libmp3lame", str(mp3_src),
            ],
            capture_output=True,
            check=True,
        )
        mp3_bytes = mp3_src.read_bytes()

        out_mp3 = Path(tmpdir) / "output.mp3"
        actual_fmt = CosyVoiceTTS._ensure_audio_format(mp3_bytes, "mp3", out_mp3)

        assert actual_fmt == "mp3", f"Expected actual_fmt='mp3', got '{actual_fmt}'"
        assert out_mp3.exists()
        assert out_mp3.read_bytes() == mp3_bytes, "Passthrough wrote different bytes"


# ── Legacy functional tests (kept as smoke tests) ─────────────────────────────

def test_basic_mix_succeeds(mixer, speech_file, music_file):
    """mix operation with two tracks must succeed."""
    out = OUT / "mix_basic.wav"
    result = mixer.execute({
        "operation": "mix",
        "tracks": [
            {"path": str(speech_file), "role": "speech", "volume": 1.0},
            {"path": str(music_file), "role": "music", "volume": 0.3},
        ],
        "normalize": True,
        "output_path": str(out),
    })
    assert result.success, f"mix failed: {result.error}"
    assert out.exists()


def test_mix_with_fades_succeeds(mixer, speech_file, music_file):
    """mix with fade_in/fade_out parameters must succeed."""
    out = OUT / "mix_fades.wav"
    result = mixer.execute({
        "operation": "mix",
        "tracks": [
            {"path": str(speech_file), "role": "speech", "fade_in_seconds": 0.5},
            {"path": str(music_file), "role": "music", "volume": 0.25,
             "fade_in_seconds": 1.0, "fade_out_seconds": 2.0},
        ],
        "normalize": True,
        "output_path": str(out),
    })
    assert result.success, f"mix with fades failed: {result.error}"


# ── Standalone runner ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
