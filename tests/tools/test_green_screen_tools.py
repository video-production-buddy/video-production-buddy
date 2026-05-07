from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from tools.video.green_screen_composite import GreenScreenComposite
from tools.video.green_screen_processor import GreenScreenProcessor


def test_green_screen_processor_rejects_unknown_method(monkeypatch, tmp_path: Path):
    input_path = tmp_path / "input.mp4"
    input_path.write_bytes(b"stub-video")
    output_path = tmp_path / "out.mp4"
    tool = GreenScreenProcessor()
    monkeypatch.setattr(
        tool,
        "_probe_video",
        lambda _path: {"duration": 1.0, "width": 640, "height": 360, "fps": 30.0},
    )
    monkeypatch.setattr(tool, "_extract_frames", lambda *args, **kwargs: 1)
    monkeypatch.setattr(tool, "_process_rembg", lambda *args, **kwargs: True)
    monkeypatch.setattr(tool, "_reconstruct_video", lambda *args, **kwargs: output_path.write_bytes(b"out"))

    result = tool.execute(
        {
            "input_path": str(input_path),
            "output_path": str(output_path),
            "method": "not-a-real-method",
        }
    )

    assert not result.success
    assert "Unknown method" in (result.error or "")


def test_green_screen_processor_idempotency_key_includes_output_path():
    tool = GreenScreenProcessor()
    base = {
        "input_path": "input.mp4",
        "output_path": "out-a.mp4",
        "method": "chromakey",
        "fps": 15,
        "bg_color": "#0E172A",
        "max_frames": 0,
    }

    assert tool.idempotency_key(base) != tool.idempotency_key({**base, "output_path": "out-b.mp4"})


def test_green_screen_composite_rejects_unknown_layout():
    speaker = Image.new("RGB", (32, 32), (0, 0, 0))
    background = Image.new("RGB", (32, 32), (255, 255, 255))

    with pytest.raises(ValueError, match="Unknown layout"):
        GreenScreenComposite()._composite_frame(
            speaker,
            background,
            np.array([0, 0, 0]),
            layout="not-a-real-layout",
            speaker_scale=0.65,
            bg_shift_up=0,
            out_w=32,
            out_h=32,
        )


def test_green_screen_composite_idempotency_key_includes_output_and_audio_source():
    tool = GreenScreenComposite()
    base = {
        "speaker_path": "speaker.mp4",
        "background_path": "background.mp4",
        "output_path": "out-a.mp4",
        "original_audio_path": "audio-a.mp4",
        "layout": "news_anchor",
        "speaker_scale": 0.65,
        "bg_shift_up": 300,
        "bg_color_hex": "#0E172A",
    }
    variants = [
        {"output_path": "out-b.mp4"},
        {"original_audio_path": "audio-b.mp4"},
    ]

    base_key = tool.idempotency_key(base)

    for variant in variants:
        assert tool.idempotency_key({**base, **variant}) != base_key
