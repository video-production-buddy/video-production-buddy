"""End-to-end FFmpeg integration test for Path B duck schedule.

Synthesizes a constant-amplitude sine tone for "music" and a separate sine
for "speech", runs the schedule-driven duck path, and reads back the rendered
output with FFmpeg's ``volumedetect`` to verify the music gain envelope
actually matches the schedule. Complements the mocked unit tests in
tests/tools/test_audio_mixer_volume_schedule.py.

Skipped when ffmpeg is not on PATH.
"""

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from lib.intensity_curve import sample_volume_schedule
from tools.audio.audio_mixer import AudioMixer


pytestmark = pytest.mark.skipif(
    shutil.which("ffmpeg") is None,
    reason="ffmpeg not installed",
)


def _synthesize_tone(path: Path, freq: int, duration: float, amplitude: float = 0.5) -> None:
    """Generate a constant-amplitude sine tone WAV at ``path``."""
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi",
        "-i", f"sine=frequency={freq}:duration={duration}:sample_rate=44100",
        "-af", f"volume={amplitude}",
        "-ac", "1",
        str(path),
    ]
    subprocess.run(cmd, capture_output=True, check=True)


def _measure_rms_in_window(path: Path, start: float, end: float) -> float:
    """Return the RMS amplitude of ``path`` between ``start`` and ``end`` seconds.

    Uses ``volumedetect`` after trimming to the window. Returns linear amplitude
    (0..1), derived from the ``mean_volume`` dB readout.
    """
    cmd = [
        "ffmpeg", "-hide_banner",
        "-i", str(path),
        "-af", f"atrim={start}:{end},volumedetect",
        "-vn", "-f", "null", "-",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    for line in proc.stderr.splitlines():
        if "mean_volume:" in line:
            db_str = line.split("mean_volume:")[1].strip().split()[0]
            return 10.0 ** (float(db_str) / 20.0)
    raise RuntimeError(f"volumedetect did not report mean_volume:\n{proc.stderr}")


def test_schedule_envelope_renders_to_real_audio(tmp_path: Path):
    """A 3-step duck schedule on a constant tone produces a measurable envelope."""
    speech = tmp_path / "speech.wav"
    music = tmp_path / "music.wav"
    out = tmp_path / "ducked.wav"

    # Near-silent "speech" so it doesn't contaminate the music gain measurement
    # via amix mixing.
    _synthesize_tone(speech, freq=200, duration=10.0, amplitude=0.001)
    # 10s of constant 440 Hz tone at 0.5 amplitude.
    _synthesize_tone(music, freq=440, duration=10.0, amplitude=0.5)

    schedule = [
        {"t_seconds": 0.0,  "gain_db": 0.0},
        {"t_seconds": 2.7,  "gain_db": 0.0},
        {"t_seconds": 3.0,  "gain_db": -18.0},
        {"t_seconds": 7.0,  "gain_db": -18.0},
        {"t_seconds": 7.3,  "gain_db": 0.0},
    ]

    tool = AudioMixer()
    result = tool.execute({
        "operation": "duck",
        "primary_audio": str(speech),
        "secondary_audio": str(music),
        "music_volume_schedule": schedule,
        "output_path": str(out),
    })
    assert result.success, f"audio_mixer failed: {result.error}"
    assert out.exists() and out.stat().st_size > 0, "output WAV not produced"

    # Sample windows OUTSIDE narration → music near full volume.
    # Sample window INSIDE narration → music ducked to ~-18 dB → ~0.126 linear.
    pre_rms  = _measure_rms_in_window(out, 1.0, 2.5)
    duck_rms = _measure_rms_in_window(out, 4.0, 6.5)
    post_rms = _measure_rms_in_window(out, 8.0, 9.5)

    expected_ratio = sample_volume_schedule(schedule, 5.0) / sample_volume_schedule(schedule, 1.5)
    actual_ratio = duck_rms / pre_rms

    # Allow generous tolerance (±30%) — RMS over windows with edges, plus
    # a tiny silent-speech contribution, plus volumedetect rounding.
    assert actual_ratio == pytest.approx(expected_ratio, rel=0.30), (
        f"schedule duck depth not honored: pre_rms={pre_rms:.4f}, duck_rms={duck_rms:.4f}, "
        f"post_rms={post_rms:.4f}, actual_ratio={actual_ratio:.3f}, expected~{expected_ratio:.3f}"
    )

    # Post-window must recover (within 30% of the pre-window level).
    assert post_rms == pytest.approx(pre_rms, rel=0.30), (
        f"music did not recover after duck window: pre={pre_rms:.4f}, post={post_rms:.4f}"
    )
