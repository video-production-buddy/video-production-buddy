from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from tools.video.remotion_caption_burn import RemotionCaptionBurn


def test_remotion_caption_burn_ffmpeg_fallback_escapes_single_quotes(tmp_path: Path):
    input_path = tmp_path / "input.mp4"
    input_path.write_bytes(b"stub-video")
    output_path = tmp_path / "work'space" / "out.mp4"
    tool = RemotionCaptionBurn()
    captured: dict[str, str] = {}

    def fake_run_command(cmd, *args, **kwargs):
        captured["vf"] = cmd[cmd.index("-vf") + 1]
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"captioned")

    tool.run_command = fake_run_command  # type: ignore[method-assign]

    result = tool._render_ffmpeg(
        str(input_path),
        str(output_path),
        [{"word": "Hello", "startMs": 0, "endMs": 500}],
    )

    assert result.success, result.error
    assert "work\\'space" in captured["vf"]


def test_remotion_caption_burn_ffmpeg_fallback_returns_tool_result_on_failure(tmp_path: Path):
    input_path = tmp_path / "input.mp4"
    input_path.write_bytes(b"stub-video")
    output_path = tmp_path / "out.mp4"
    tool = RemotionCaptionBurn()

    def failing_run_command(*args, **kwargs):
        raise RuntimeError("ffmpeg failed")

    tool.run_command = failing_run_command  # type: ignore[method-assign]

    result = tool._render_ffmpeg(
        str(input_path),
        str(output_path),
        [{"word": "Hello", "startMs": 0, "endMs": 500}],
    )

    assert not result.success
    assert "ffmpeg failed" in (result.error or "")
    assert not list(tmp_path.glob("_tmp_captions_*.srt"))


def test_remotion_caption_burn_idempotency_key_includes_output_and_caption_options():
    tool = RemotionCaptionBurn()
    base = {
        "input_path": "input.mp4",
        "output_path": "out-a.mp4",
        "segments": [{"text": "Hello", "start": 0, "end": 1}],
        "srt_path": "subs-a.srt",
        "words_per_page": 4,
        "font_size": 52,
        "highlight_color": "#22D3EE",
        "corrections": {"helo": "hello"},
        "overlays": [{"type": "text_card", "text": "A"}],
        "force_ffmpeg": False,
    }
    variants = [
        {"output_path": "out-b.mp4"},
        {"words_per_page": 6},
        {"font_size": 60},
        {"highlight_color": "#FFFFFF"},
        {"corrections": {"helo": "HELLO"}},
        {"overlays": [{"type": "text_card", "text": "B"}]},
        {"force_ffmpeg": True},
    ]

    base_key = tool.idempotency_key(base)

    for variant in variants:
        assert tool.idempotency_key({**base, **variant}) != base_key


def test_remotion_caption_burn_props_use_public_relative_video_src(tmp_path: Path):
    input_path = tmp_path / "source clip.mp4"
    input_path.write_bytes(b"stub-video")
    output_path = tmp_path / "captioned.mp4"
    remotion_root = tmp_path / "remotion-composer"
    (remotion_root / "public").mkdir(parents=True)

    tool = RemotionCaptionBurn()
    tool._find_remotion_root = lambda: remotion_root  # type: ignore[method-assign]

    def fake_run_command(cmd, *args, **kwargs):
        if "-show_entries" in cmd and "format=duration" in cmd:
            return SimpleNamespace(stdout="2.0\n")
        if "-show_entries" in cmd and "stream=width,height" in cmd:
            return SimpleNamespace(stdout="1280x720\n")
        output_path.write_bytes(b"rendered")
        return SimpleNamespace(stdout="")

    tool.run_command = fake_run_command  # type: ignore[method-assign]

    result = tool._render_remotion(
        str(input_path),
        str(output_path),
        [{"word": "Hello", "startMs": 0, "endMs": 500}],
        words_per_page=4,
        font_size=52,
        highlight_color="#22D3EE",
    )

    assert result.success, result.error
    props_path = remotion_root / "public" / "demo-props" / "caption-burn-source clip.json"
    props = json.loads(props_path.read_text(encoding="utf-8"))
    assert props["videoSrc"] == "talking-head/source clip.mp4"
    assert not props["videoSrc"].startswith("public/")
