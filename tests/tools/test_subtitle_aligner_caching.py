"""TDD regression test for WhisperModel caching across segments.

Until this fix, `_align_segment` re-instantiated `WhisperModel` on every call.
A 6-segment ad loaded the model from disk 6 times — the load is the expensive
step and dominates wall-clock time. This test pins that the model is loaded
exactly once for N segments of the same (model_size, device, compute_type).
"""

from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock


def _install_fake_faster_whisper(monkeypatch) -> MagicMock:
    """Inject a stand-in `faster_whisper` module exposing a Mock WhisperModel.

    `_align_segment` does `from faster_whisper import WhisperModel` lazily, so
    putting the fake module into sys.modules before the call lets us observe
    init+transcribe behavior without loading anything from disk.
    """
    fake_pkg = types.ModuleType("faster_whisper")
    whisper_model_cls = MagicMock(name="WhisperModel")

    def _segments_for(audio_path, **kwargs):
        # Return (segments_iter, info). Each "segment" has a `.words` iterable
        # whose items have .word / .start / .end. The aligner offsets these by
        # segment.start_offset_seconds. We give one word per call so the test
        # stays focused on instantiation count, not transcription correctness.
        word = MagicMock(word="hello", start=0.0, end=0.5)
        seg = MagicMock(words=[word])
        return iter([seg]), MagicMock()

    whisper_model_cls.return_value.transcribe.side_effect = _segments_for
    fake_pkg.WhisperModel = whisper_model_cls
    monkeypatch.setitem(sys.modules, "faster_whisper", fake_pkg)
    return whisper_model_cls


class TestSubtitleAlignerCaching:
    """The model load is the hot path; re-loading per segment is the bug."""

    def test_single_model_load_across_segments(self, monkeypatch, tmp_path):
        # Arrange — fake WhisperModel that records every instantiation.
        whisper_model_cls = _install_fake_faster_whisper(monkeypatch)
        from tools.audio import subtitle_aligner

        # Drop any cache state left by prior tests in this process so the
        # call_count assertion below reflects this test's loads only.
        if hasattr(subtitle_aligner, "_clear_model_cache"):
            subtitle_aligner._clear_model_cache()

        segments = [
            subtitle_aligner.Segment(
                audio_path=f"/tmp/audio_synth_n{i:02d}.mp3",
                text=f"segment {i}",
                start_offset_seconds=float(i) * 1.0,
            )
            for i in range(3)
        ]

        # Act
        subtitle_aligner.align(
            segments,
            output_path=tmp_path / "out.ass",
            model_size="base",
        )

        # Assert — three segments, one model instantiation.
        assert whisper_model_cls.call_count == 1, (
            f"WhisperModel must be instantiated once per (model_size, device, "
            f"compute_type) tuple; got {whisper_model_cls.call_count} loads "
            f"for 3 segments"
        )
        # And transcribe should still be called once per segment.
        instance = whisper_model_cls.return_value
        assert instance.transcribe.call_count == 3, (
            f"expected 1 transcribe call per segment (3 total); "
            f"got {instance.transcribe.call_count}"
        )

    def test_different_model_size_triggers_new_load(self, monkeypatch, tmp_path):
        # Arrange — same fake. Two segments at "base", one at "tiny".
        whisper_model_cls = _install_fake_faster_whisper(monkeypatch)
        from tools.audio import subtitle_aligner

        if hasattr(subtitle_aligner, "_clear_model_cache"):
            subtitle_aligner._clear_model_cache()

        seg_a = subtitle_aligner.Segment(
            audio_path="/tmp/audio_synth_a.mp3",
            text="alpha",
            start_offset_seconds=0.0,
        )
        seg_b = subtitle_aligner.Segment(
            audio_path="/tmp/audio_synth_b.mp3",
            text="bravo",
            start_offset_seconds=2.0,
        )

        # Act — call align twice with different model sizes.
        subtitle_aligner.align([seg_a, seg_b], output_path=tmp_path / "base.ass", model_size="base")
        subtitle_aligner.align([seg_a], output_path=tmp_path / "tiny.ass", model_size="tiny")

        # Assert — two distinct (model_size,...) tuples, two loads.
        assert whisper_model_cls.call_count == 2, (
            f"different model_size must trigger a fresh load; "
            f"got {whisper_model_cls.call_count} (expected 2)"
        )


def test_ass_timestamp_rounding_carries_to_next_minute():
    from tools.audio import subtitle_aligner

    assert subtitle_aligner._format_ass_time(59.999) == "0:01:00.00"
    assert subtitle_aligner._format_ass_time(3661.235) == "1:01:01.24"
