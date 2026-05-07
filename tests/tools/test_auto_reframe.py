from __future__ import annotations

from pathlib import Path

from tools.base_tool import ToolResult
from tools.video.auto_reframe import AutoReframe


def test_auto_reframe_rejects_unknown_target_aspect(monkeypatch, tmp_path: Path):
    input_path = tmp_path / "input.mp4"
    input_path.write_bytes(b"stub-video")
    output_path = tmp_path / "out.mp4"
    tool = AutoReframe()
    monkeypatch.setattr(tool, "_get_video_info", lambda _path: (1920, 1080, 30.0))
    monkeypatch.setattr(tool, "_get_face_data", lambda *args, **kwargs: [])

    def fake_render(*args, **kwargs):
        output_path.write_bytes(b"stub-output")
        return ToolResult(success=True)

    monkeypatch.setattr(tool, "_render_static_crop", fake_render)

    result = tool.execute(
        {
            "input_path": str(input_path),
            "output_path": str(output_path),
            "target_aspect": "not-a-real-aspect",
        }
    )

    assert not result.success
    assert "Unknown target_aspect" in (result.error or "")


def test_auto_reframe_matching_aspect_writes_requested_output_path(tmp_path: Path, monkeypatch):
    input_path = tmp_path / "input.mp4"
    input_path.write_bytes(b"already-portrait")
    output_path = tmp_path / "out.mp4"
    tool = AutoReframe()
    monkeypatch.setattr(tool, "_get_video_info", lambda _path: (1080, 1920, 30.0))

    result = tool.execute(
        {
            "input_path": str(input_path),
            "output_path": str(output_path),
            "target_aspect": "portrait",
        }
    )

    assert result.success, result.error
    assert result.artifacts == [str(output_path)]
    assert output_path.read_bytes() == b"already-portrait"


def test_auto_reframe_idempotency_key_includes_output_and_render_parameters():
    tool = AutoReframe()
    base = {
        "input_path": "input.mp4",
        "output_path": "out-a.mp4",
        "target_aspect": "portrait",
        "target_width": 1080,
        "target_height": 1920,
        "face_tracking_json": "faces-a.json",
        "smoothing_window": 15,
        "face_padding": 0.4,
        "sample_fps": 5,
        "codec": "libx264",
        "crf": 18,
    }
    variants = [
        {"output_path": "out-b.mp4"},
        {"face_tracking_json": "faces-b.json"},
        {"sample_fps": 10},
        {"codec": "libx265"},
        {"crf": 23},
    ]

    base_key = tool.idempotency_key(base)

    for variant in variants:
        assert tool.idempotency_key({**base, **variant}) != base_key


def test_auto_reframe_dynamic_crop_escapes_single_quotes_in_sendcmd_path(tmp_path: Path):
    input_path = tmp_path / "input.mp4"
    input_path.write_bytes(b"stub-video")
    output_path = tmp_path / "work'space" / "out.mp4"
    tool = AutoReframe()
    captured: dict[str, str] = {}

    def fake_run_command(cmd, *args, **kwargs):
        captured["vf"] = cmd[cmd.index("-vf") + 1]
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"reframed")

    tool.run_command = fake_run_command  # type: ignore[method-assign]

    result = tool._render_dynamic_crop(
        input_path,
        output_path,
        crop_xs=[10, 20, 30],
        crop_ys=[5, 15, 25],
        crop_w=100,
        crop_h=100,
        out_w=200,
        out_h=200,
        fps=30.0,
        codec="libx264",
        crf=18,
    )

    assert result.success, result.error
    assert "work\\'space" in captured["vf"]
