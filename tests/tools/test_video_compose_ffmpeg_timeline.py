from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from tools.validation.scene_fidelity_check import check_plan, load_registry
from tools.video.video_compose import VideoCompose


def test_ffmpeg_compose_uses_source_in_seconds_for_source_seek(monkeypatch, tmp_path):
    source = tmp_path / "source.mp4"
    source.write_bytes(b"stub-video")
    output = tmp_path / "out.mp4"
    commands: list[list[str]] = []

    composer = VideoCompose()
    monkeypatch.setattr(composer, "_has_audio_stream", lambda _path: False)

    def fake_run_command(cmd, *args, **kwargs):
        commands.append(list(cmd))
        out = Path(cmd[-1])
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"stub-output")
        return SimpleNamespace(stdout="")

    monkeypatch.setattr(composer, "run_command", fake_run_command)

    result = composer.execute(
        {
            "operation": "compose",
            "edit_decisions": {
                "version": "1.0",
                "render_runtime": "ffmpeg",
                "cuts": [
                    {
                        "id": "cut-1",
                        "source": str(source),
                        "in_seconds": 12.0,
                        "out_seconds": 14.5,
                        "source_in_seconds": 1.25,
                    }
                ],
            },
            "output_path": str(output),
        }
    )

    assert result.success, result.error
    trim_cmd = commands[0]
    assert trim_cmd[trim_cmd.index("-ss") + 1] == "1.25"
    assert trim_cmd[trim_cmd.index("-t") + 1] == "2.5"


def test_ffmpeg_compose_normalizes_segments_to_selected_profile(monkeypatch, tmp_path):
    source = tmp_path / "source.mp4"
    source.write_bytes(b"stub-video")
    output = tmp_path / "out.mp4"
    commands: list[list[str]] = []

    composer = VideoCompose()
    monkeypatch.setattr(composer, "_has_audio_stream", lambda _path: False)

    def fake_run_command(cmd, *args, **kwargs):
        commands.append(list(cmd))
        out = Path(cmd[-1])
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"stub-output")
        return SimpleNamespace(stdout="")

    monkeypatch.setattr(composer, "run_command", fake_run_command)

    result = composer.execute(
        {
            "operation": "compose",
            "profile": "tiktok",
            "edit_decisions": {
                "version": "1.0",
                "render_runtime": "ffmpeg",
                "cuts": [
                    {
                        "id": "cut-1",
                        "source": str(source),
                        "in_seconds": 0.0,
                        "out_seconds": 2.0,
                    }
                ],
            },
            "output_path": str(output),
        }
    )

    assert result.success, result.error
    trim_cmd = commands[0]
    vf = trim_cmd[trim_cmd.index("-filter:v") + 1]
    assert "scale=1080:1920:force_original_aspect_ratio=decrease" in vf
    assert "pad=1080:1920:(ow-iw)/2:(oh-ih)/2:color=black" in vf
    assert "fps=30" in vf


def test_scene_fidelity_accepts_plain_media_cut_without_component_type():
    registry = load_registry()

    report = check_plan(
        {
            "version": "1.0",
            "render_runtime": "ffmpeg",
            "cuts": [
                {
                    "id": "cut-1",
                    "source": "projects/example/assets/video/clip.mp4",
                    "in_seconds": 0,
                    "out_seconds": 2,
                    "maps_to_beat": "hook",
                }
            ],
        },
        registry,
    )

    assert report["ok"], report["issues"]


def test_scene_fidelity_blocks_overlapping_source_reuse():
    registry = load_registry()

    report = check_plan(
        {
            "version": "1.0",
            "render_runtime": "ffmpeg",
            "cuts": [
                {
                    "id": "cut-1",
                    "source": "projects/example/assets/video/clip.mp4",
                    "in_seconds": 0.0,
                    "out_seconds": 2.0,
                    "source_in_seconds": 0.0,
                    "maps_to_beat": "hook",
                },
                {
                    "id": "cut-2",
                    "source": "projects/example/assets/video/clip.mp4",
                    "in_seconds": 2.0,
                    "out_seconds": 4.0,
                    "source_in_seconds": 1.0,
                    "maps_to_beat": "build",
                },
            ],
        },
        registry,
    )

    assert not report["ok"]
    assert report["issues"][0]["kind"] == "overlapping_source_reuse"
    assert report["issues"][0]["scene_id"] == "cut-2"


def test_scene_fidelity_blocks_remotion_source_reuse_without_source_in_seconds():
    registry = load_registry()

    report = check_plan(
        {
            "version": "1.0",
            "render_runtime": "remotion",
            "cuts": [
                {
                    "id": "cut-1",
                    "source": "projects/example/assets/video/clip.mp4",
                    "in_seconds": 0.0,
                    "out_seconds": 2.0,
                    "maps_to_beat": "hook",
                },
                {
                    "id": "cut-2",
                    "source": "projects/example/assets/video/clip.mp4",
                    "in_seconds": 2.0,
                    "out_seconds": 4.0,
                    "maps_to_beat": "build",
                },
            ],
        },
        registry,
    )

    assert not report["ok"]
    assert report["issues"][0]["kind"] == "overlapping_source_reuse"
    assert report["issues"][0]["scene_id"] == "cut-2"
    assert report["issues"][0]["source_range_seconds"] == [0.0, 2.0]


def test_scene_fidelity_allows_non_overlapping_source_reuse():
    registry = load_registry()

    report = check_plan(
        {
            "version": "1.0",
            "render_runtime": "ffmpeg",
            "cuts": [
                {
                    "id": "cut-1",
                    "source": "projects/example/assets/video/clip.mp4",
                    "in_seconds": 0.0,
                    "out_seconds": 2.0,
                    "source_in_seconds": 0.0,
                    "maps_to_beat": "hook",
                },
                {
                    "id": "cut-2",
                    "source": "projects/example/assets/video/clip.mp4",
                    "in_seconds": 2.0,
                    "out_seconds": 4.0,
                    "source_in_seconds": 2.0,
                    "maps_to_beat": "build",
                },
            ],
        },
        registry,
    )

    assert report["ok"], report["issues"]


def test_scene_fidelity_allows_reused_still_image_in_remotion_cuts():
    registry = load_registry()

    report = check_plan(
        {
            "version": "1.0",
            "render_runtime": "remotion",
            "cuts": [
                {
                    "id": "cut-1",
                    "source": "projects/example/assets/images/packshot.png",
                    "in_seconds": 0.0,
                    "out_seconds": 2.0,
                    "maps_to_beat": "hook",
                },
                {
                    "id": "cut-2",
                    "source": "projects/example/assets/images/packshot.png",
                    "in_seconds": 2.0,
                    "out_seconds": 4.0,
                    "maps_to_beat": "cta",
                },
            ],
        },
        registry,
    )

    assert report["ok"], report["issues"]


def test_video_compose_precompose_blocks_overlapping_source_reuse():
    composer = VideoCompose()

    result = composer._pre_compose_validation(
        {
            "version": "1.0",
            "render_runtime": "ffmpeg",
            "renderer_family": "cinematic-trailer",
            "cuts": [
                {
                    "id": "cut-1",
                    "source": "projects/example/assets/video/clip.mp4",
                    "in_seconds": 0.0,
                    "out_seconds": 2.0,
                    "source_in_seconds": 0.0,
                    "maps_to_beat": "hook",
                },
                {
                    "id": "cut-2",
                    "source": "projects/example/assets/video/clip.mp4",
                    "in_seconds": 2.0,
                    "out_seconds": 4.0,
                    "source_in_seconds": 1.0,
                    "maps_to_beat": "build",
                },
            ],
        },
        [
            {
                "id": "cut-1",
                "source": "projects/example/assets/video/clip.mp4",
                "in_seconds": 0.0,
                "out_seconds": 2.0,
                "source_in_seconds": 0.0,
                "maps_to_beat": "hook",
            },
            {
                "id": "cut-2",
                "source": "projects/example/assets/video/clip.mp4",
                "in_seconds": 2.0,
                "out_seconds": 4.0,
                "source_in_seconds": 1.0,
                "maps_to_beat": "build",
            },
        ],
    )

    assert result is not None
    assert not result.success
    assert "overlapping cut 'cut-1'" in result.error


def test_video_compose_accepts_subtitle_style_string_from_schema():
    style = VideoCompose._resolve_subtitle_style(
        explicit_style=None,
        edit_decisions={
            "version": "1.0",
            "render_runtime": "ffmpeg",
            "subtitles": {
                "enabled": True,
                "style": "sentence",
                "font": "DejaVu Sans",
                "font_size": 24,
            },
            "cuts": [],
        },
        playbook=None,
    )

    assert style["font"] == "DejaVu Sans"
    assert style["font_size"] == 24


def test_video_compose_converts_hex_subtitle_colors_to_ass_override():
    force_style = VideoCompose._build_subtitle_style(
        {
            "font": "DejaVu Sans",
            "font_size": 24,
            "primary_color": "#FFFFFF",
            "outline_color": "#000000",
        }
    )

    assert "PrimaryColour=&H00FFFFFF" in force_style
    assert "OutlineColour=&H00000000" in force_style
    assert "#FFFFFF" not in force_style


def test_video_compose_converts_css_alpha_hex_subtitle_color_to_ass_transparency():
    force_style = VideoCompose._build_subtitle_style(
        {
            "primary_color": "#00000000",
            "outline_color": "#33669980",
            "back_color": "#FFFFFF40",
        }
    )

    assert "PrimaryColour=&HFF000000" in force_style
    assert "OutlineColour=&H7F996633" in force_style
    assert "BackColour=&HBFFFFFFF" in force_style
