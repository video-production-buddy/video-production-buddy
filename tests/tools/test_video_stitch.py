from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest

from tools.video.video_stitch import VideoStitch


class _RecordingVideoStitch(VideoStitch):
    def __init__(self) -> None:
        super().__init__()
        self.commands: list[list[str]] = []

    def run_command(self, cmd, *args, **kwargs):
        self.commands.append(list(cmd))

        class _Result:
            stdout = "{}"
            stderr = ""

        return _Result()


def test_video_stitch_rejects_unknown_media_profile_during_normalization():
    tool = VideoStitch()

    with pytest.raises(ValueError, match="Unknown profile"):
        tool._resolve_normalization_target(
            {"profile": "not-a-real-profile"},
            [{"width": 640, "height": 360, "fps": 24}],
        )


def test_video_stitch_idempotency_key_includes_output_and_render_parameters():
    tool = VideoStitch()
    base = {
        "operation": "stitch",
        "clips": ["a.mp4", "b.mp4"],
        "output_path": "out-a.mp4",
        "transition": "crossfade",
        "transition_duration": 0.5,
        "auto_normalize": True,
        "target_resolution": "640x360",
        "target_fps": 24,
        "codec": "libx264",
        "crf": 23,
        "preset": "medium",
        "profile": "generic_hd",
        "layout": "picture_in_picture",
        "pip_position": "bottom_right",
        "pip_scale": 0.3,
        "pip_margin": 10,
    }
    variants = [
        {"output_path": "out-b.mp4"},
        {"transition_duration": 1.0},
        {"auto_normalize": False},
        {"target_resolution": "1280x720"},
        {"target_fps": 30},
        {"codec": "libx265"},
        {"crf": 18},
        {"preset": "slow"},
        {"profile": "youtube_landscape"},
        {"pip_position": "top_left"},
        {"pip_scale": 0.4},
        {"pip_margin": 24},
    ]

    base_key = tool.idempotency_key(base)

    for variant in variants:
        assert tool.idempotency_key({**base, **variant}) != base_key


@pytest.mark.parametrize("operation", ["stitch", "preview_stitch", "spatial"])
def test_video_stitch_schemas_require_two_clips_for_composition_operations(
    operation: str,
):
    canonical_schema = json.loads(
        (
            Path(__file__).resolve().parents[2]
            / "schemas"
            / "tools"
            / "video_stitch.schema.json"
        ).read_text(encoding="utf-8")
    )
    instance = {"operation": operation, "clips": ["one.mp4"]}
    if operation == "spatial":
        instance["layout"] = "side_by_side"

    for schema in (canonical_schema, VideoStitch.input_schema):
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(instance=instance, schema=schema)


def test_stitch_cut_escapes_single_quotes_in_concat_list_paths(tmp_path: Path):
    clip = tmp_path / "clip's intro.mp4"
    clip.write_bytes(b"placeholder")
    other = tmp_path / "other.mp4"
    other.write_bytes(b"placeholder")
    output = tmp_path / "out.mp4"
    temp_dir = tmp_path / ".stitch_tmp"
    temp_dir.mkdir()
    temp_files: list[Path] = []
    tool = _RecordingVideoStitch()

    tool._stitch_cut([str(clip), str(other)], output, temp_dir, temp_files)

    concat_list = temp_dir / "concat_list.txt"
    body = concat_list.read_text(encoding="utf-8")
    assert "clip'\\''s intro.mp4" in body
