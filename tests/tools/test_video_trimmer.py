from __future__ import annotations

from pathlib import Path

from tools.video.video_trimmer import VideoTrimmer


class _RecordingVideoTrimmer(VideoTrimmer):
    def __init__(self) -> None:
        super().__init__()
        self.concat_list_body: str | None = None
        self.commands: list[list[str]] = []

    def run_command(self, cmd, *args, **kwargs):
        self.commands.append(list(cmd))
        if "-f" in cmd and "concat" in cmd:
            list_path = Path(cmd[cmd.index("-i") + 1])
            self.concat_list_body = list_path.read_text(encoding="utf-8")

        class _Result:
            stdout = "{}"
            stderr = ""

        return _Result()


def test_video_trimmer_concat_missing_segment_reports_missing_input(tmp_path: Path):
    tool = VideoTrimmer()
    missing = tmp_path / "missing.mp4"

    result = tool.execute(
        {
            "operation": "concat",
            "segments": [{"input_path": str(missing)}],
            "output_path": str(tmp_path / "out.mp4"),
        }
    )

    assert not result.success
    assert f"Segment input not found: {missing}" in (result.error or "")


def test_video_trimmer_concat_escapes_single_quotes_in_file_list(tmp_path: Path):
    clip = tmp_path / "clip's intro.mp4"
    clip.write_bytes(b"placeholder")
    other = tmp_path / "other.mp4"
    other.write_bytes(b"placeholder")
    tool = _RecordingVideoTrimmer()

    result = tool.execute(
        {
            "operation": "concat",
            "segments": [
                {"input_path": str(clip)},
                {"input_path": str(other)},
            ],
            "output_path": str(tmp_path / "out.mp4"),
        }
    )

    assert result.success
    assert tool.concat_list_body is not None
    assert "clip'\\''s intro.mp4" in tool.concat_list_body


def test_video_trimmer_idempotency_key_includes_outputs_and_operation_parameters():
    tool = VideoTrimmer()
    base = {
        "operation": "cut",
        "input_path": "input.mp4",
        "output_path": "out-a.mp4",
        "start_seconds": 1,
        "end_seconds": 3,
        "speed_factor": 1.0,
        "codec": "copy",
        "segments": [{"input_path": "a.mp4"}, {"input_path": "b.mp4"}],
    }
    variants = [
        {"output_path": "out-b.mp4"},
        {"codec": "libx264"},
        {"segments": [{"input_path": "b.mp4"}, {"input_path": "a.mp4"}]},
    ]

    base_key = tool.idempotency_key(base)

    for variant in variants:
        assert tool.idempotency_key({**base, **variant}) != base_key
