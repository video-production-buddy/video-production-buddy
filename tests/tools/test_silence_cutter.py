from __future__ import annotations

from pathlib import Path

from tools.video.silence_cutter import SilenceCutter


class _RecordingSilenceCutter(SilenceCutter):
    def __init__(self) -> None:
        super().__init__()
        self.concat_list_bodies: list[str] = []

    def run_command(self, cmd, *args, **kwargs):
        if "-f" in cmd and "concat" in cmd:
            list_path = Path(cmd[cmd.index("-i") + 1])
            self.concat_list_bodies.append(list_path.read_text(encoding="utf-8"))
        out = Path(cmd[-1])
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"stub-output")

        class _Result:
            stdout = "{}"
            stderr = ""

        return _Result()


def test_jump_cut_escapes_single_quotes_in_concat_list(tmp_path: Path):
    input_path = tmp_path / "input.mp4"
    input_path.write_bytes(b"stub-video")
    output_path = tmp_path / "work'space" / "out.mp4"
    tool = _RecordingSilenceCutter()

    result = tool._render_jump_cut(
        input_path,
        output_path,
        [{"start": 0.0, "end": 1.0}],
        "libx264",
        18,
    )

    assert result.success, result.error
    assert "work'\\''space" in tool.concat_list_bodies[0]


def test_speed_up_escapes_single_quotes_in_concat_list(tmp_path: Path):
    input_path = tmp_path / "input.mp4"
    input_path.write_bytes(b"stub-video")
    output_path = tmp_path / "work'space" / "out.mp4"
    tool = _RecordingSilenceCutter()

    result = tool._render_speed_up(
        input_path,
        output_path,
        silences=[{"start": 1.0, "end": 2.0}],
        speech_segments=[{"start": 0.0, "end": 1.0}],
        total_duration=2.0,
        speed_factor=6.0,
        codec="libx264",
        crf=18,
    )

    assert result.success, result.error
    assert "work'\\''space" in tool.concat_list_bodies[0]


def test_silence_cutter_idempotency_key_includes_output_and_render_parameters():
    tool = SilenceCutter()
    base = {
        "input_path": "talking-head.mp4",
        "output_path": "out-a.mp4",
        "mode": "speed_up",
        "silence_threshold_db": -35,
        "min_silence_duration": 0.5,
        "padding_seconds": 0.08,
        "silence_speed_factor": 6.0,
        "codec": "libx264",
        "crf": 18,
    }
    variants = [
        {"output_path": "out-b.mp4"},
        {"silence_speed_factor": 8.0},
        {"codec": "libx265"},
        {"crf": 23},
    ]

    base_key = tool.idempotency_key(base)

    for variant in variants:
        assert tool.idempotency_key({**base, **variant}) != base_key
