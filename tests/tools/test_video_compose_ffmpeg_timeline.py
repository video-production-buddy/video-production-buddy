from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from styles.playbook_loader import load_playbook
from tools.validation.scene_fidelity_check import check_plan, load_registry
from tools.video.remotion_caption_burn import RemotionCaptionBurn
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


def test_ffmpeg_compose_escapes_single_quotes_in_concat_list(monkeypatch, tmp_path):
    source = tmp_path / "source.mp4"
    source.write_bytes(b"stub-video")
    quoted_dir = tmp_path / "work'space"
    output = quoted_dir / "out.mp4"
    concat_list_body: dict[str, str] = {}

    composer = VideoCompose()
    monkeypatch.setattr(composer, "_has_audio_stream", lambda _path: False)

    def fake_run_command(cmd, *args, **kwargs):
        if "-f" in cmd and "concat" in cmd:
            list_path = Path(cmd[cmd.index("-i") + 1])
            concat_list_body["body"] = list_path.read_text(encoding="utf-8")
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
                        "in_seconds": 0.0,
                        "out_seconds": 1.0,
                    }
                ],
            },
            "output_path": str(output),
        }
    )

    assert result.success, result.error
    assert "work'\\''space" in concat_list_body["body"]


def test_ffmpeg_compose_escapes_single_quotes_in_subtitle_filter(monkeypatch, tmp_path):
    source = tmp_path / "source.mp4"
    source.write_bytes(b"stub-video")
    subtitle_dir = tmp_path / "subtitle's"
    subtitle_dir.mkdir()
    subtitle = subtitle_dir / "subs.ass"
    subtitle.write_text("[Script Info]\n", encoding="utf-8")
    output = tmp_path / "out.mp4"
    captured_filters: list[str] = []

    composer = VideoCompose()
    monkeypatch.setattr(composer, "_has_audio_stream", lambda _path: False)

    def fake_run_command(cmd, *args, **kwargs):
        if "-vf" in cmd:
            captured_filters.append(cmd[cmd.index("-vf") + 1])
        out = Path(cmd[-1])
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"stub-output")
        return SimpleNamespace(stdout="")

    monkeypatch.setattr(composer, "run_command", fake_run_command)

    result = composer.execute(
        {
            "operation": "compose",
            "subtitle_path": str(subtitle),
            "edit_decisions": {
                "version": "1.0",
                "render_runtime": "ffmpeg",
                "cuts": [
                    {
                        "id": "cut-1",
                        "source": str(source),
                        "in_seconds": 0.0,
                        "out_seconds": 1.0,
                    }
                ],
            },
            "output_path": str(output),
        }
    )

    assert result.success, result.error
    assert any("subtitle\\'s" in vf for vf in captured_filters)


def test_burn_subtitles_escapes_single_quotes_in_subtitle_filter(monkeypatch, tmp_path):
    input_path = tmp_path / "input.mp4"
    input_path.write_bytes(b"stub-video")
    subtitle_dir = tmp_path / "subtitle's"
    subtitle_dir.mkdir()
    subtitle = subtitle_dir / "subs.ass"
    subtitle.write_text("[Script Info]\n", encoding="utf-8")
    output_path = tmp_path / "out.mp4"
    captured: dict[str, str] = {}
    composer = VideoCompose()

    def fake_run_command(cmd, *args, **kwargs):
        captured["vf"] = cmd[cmd.index("-vf") + 1]
        output_path.write_bytes(b"subtitled")
        return SimpleNamespace(stdout="")

    monkeypatch.setattr(composer, "run_command", fake_run_command)

    result = composer.execute(
        {
            "operation": "burn_subtitles",
            "input_path": str(input_path),
            "subtitle_path": str(subtitle),
            "output_path": str(output_path),
        }
    )

    assert result.success, result.error
    assert "subtitle\\'s" in captured["vf"]


def test_video_compose_idempotency_key_includes_output_and_render_inputs():
    composer = VideoCompose()
    base = {
        "operation": "compose",
        "input_path": "input.mp4",
        "output_path": "out-a.mp4",
        "edit_decisions": {"cuts": [{"source": "a.mp4", "in_seconds": 0, "out_seconds": 1}]},
        "asset_manifest": {"assets": [{"id": "a", "path": "a.mp4"}]},
        "audio_path": "mix-a.wav",
        "subtitle_path": "subs-a.ass",
        "subtitle_style": {"font_size": 24},
        "profile": "youtube_landscape",
        "options": {"subtitle_burn": True},
        "codec": "libx264",
        "crf": 23,
        "preset": "medium",
    }
    variants = [
        {"output_path": "out-b.mp4"},
        {"asset_manifest": {"assets": [{"id": "a", "path": "other.mp4"}]}},
        {"audio_path": "mix-b.wav"},
        {"subtitle_path": "subs-b.ass"},
        {"subtitle_style": {"font_size": 30}},
        {"profile": "tiktok"},
        {"options": {"subtitle_burn": False}},
        {"codec": "libx265"},
        {"crf": 18},
        {"preset": "slow"},
    ]

    base_key = composer.idempotency_key(base)

    for variant in variants:
        assert composer.idempotency_key({**base, **variant}) != base_key


def test_ffmpeg_compose_rejects_unknown_media_profile(monkeypatch, tmp_path):
    source = tmp_path / "source.mp4"
    source.write_bytes(b"stub-video")
    composer = VideoCompose()
    monkeypatch.setattr(composer, "_has_audio_stream", lambda _path: False)

    def fake_run_command(cmd, *args, **kwargs):
        out = Path(cmd[-1])
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"stub-output")
        return SimpleNamespace(stdout="")

    monkeypatch.setattr(composer, "run_command", fake_run_command)

    result = composer.execute(
        {
            "operation": "compose",
            "profile": "not-a-real-profile",
            "edit_decisions": {
                "version": "1.0",
                "render_runtime": "ffmpeg",
                "cuts": [
                    {
                        "id": "cut-1",
                        "source": str(source),
                        "in_seconds": 0.0,
                        "out_seconds": 1.0,
                    }
                ],
            },
            "output_path": str(tmp_path / "out.mp4"),
        }
    )

    assert not result.success
    assert "Unknown profile" in (result.error or "")


def test_video_compose_encode_rejects_unknown_media_profile(monkeypatch, tmp_path):
    source = tmp_path / "source.mp4"
    source.write_bytes(b"stub-video")
    composer = VideoCompose()
    monkeypatch.setattr(composer, "run_command", lambda *args, **kwargs: None)

    result = composer.execute(
        {
            "operation": "encode",
            "input_path": str(source),
            "profile": "not-a-real-profile",
            "output_path": str(tmp_path / "encoded.mp4"),
        }
    )

    assert not result.success
    assert "Unknown profile" in (result.error or "")


def test_remotion_failure_guidance_uses_pnpm_lockfile(monkeypatch, tmp_path):
    composer = VideoCompose()
    monkeypatch.setattr(composer, "_remotion_available", lambda: True)
    monkeypatch.setattr(composer, "_pre_compose_validation", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        composer,
        "_remotion_render",
        lambda _inputs: SimpleNamespace(success=False, error="render failed"),
    )

    result = composer.execute(
        {
            "operation": "render",
            "edit_decisions": {
                "version": "1.0",
                "renderer_family": "explainer-data",
                "render_runtime": "remotion",
                "cuts": [
                    {
                        "id": "cut-1",
                        "type": "text_card",
                        "source": "remotion:text_card",
                        "text": "Locked Remotion",
                        "in_seconds": 0,
                        "out_seconds": 1,
                    }
                ],
            },
            "asset_manifest": {"version": "1.0", "assets": []},
            "output_path": str(tmp_path / "out.mp4"),
        }
    )

    assert not result.success
    assert "pnpm install --frozen-lockfile" in (result.error or "")
    assert "&& npm install" not in (result.error or "")


def test_remotion_caption_burn_install_instructions_use_pnpm_lockfile():
    instructions = RemotionCaptionBurn.install_instructions

    assert "pnpm install --frozen-lockfile" in instructions
    assert "npm install in remotion-composer" not in instructions


def test_render_output_path_rejects_project_artifacts_dir():
    composer = VideoCompose()
    repo_root = Path(__file__).resolve().parents[2]
    output_path = repo_root / "projects" / "contract-test" / "artifacts" / "final.mp4"

    returned_path, error = composer._required_render_output_path(
        {"output_path": str(output_path)},
        "render",
    )

    assert returned_path is None
    assert error is not None
    assert not error.success
    assert "projects/<project-name>/renders/" in (error.error or "")


def test_render_output_path_accepts_project_renders_dir():
    composer = VideoCompose()
    repo_root = Path(__file__).resolve().parents[2]
    output_path = repo_root / "projects" / "contract-test" / "renders" / "final.mp4"

    returned_path, error = composer._required_render_output_path(
        {"output_path": str(output_path)},
        "render",
    )

    assert error is None
    assert returned_path == output_path


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


def test_ffmpeg_compose_does_not_burn_disabled_subtitles(monkeypatch, tmp_path):
    source = tmp_path / "source.mp4"
    source.write_bytes(b"stub-video")
    subtitle = tmp_path / "subtitles.ass"
    subtitle.write_text(
        "[Script Info]\nPlayResX: 1920\nPlayResY: 1080\n", encoding="utf-8"
    )
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
                        "in_seconds": 0.0,
                        "out_seconds": 2.0,
                    }
                ],
                "subtitles": {"enabled": False, "source": str(subtitle)},
            },
            "output_path": str(output),
        }
    )

    assert result.success, result.error
    assert not any(
        "subtitles=" in str(part) for command in commands for part in command
    )


def test_ffmpeg_render_resolves_subtitle_asset_id_before_compose(monkeypatch, tmp_path):
    source = tmp_path / "source.mp4"
    source.write_bytes(b"stub-video")
    subtitle = tmp_path / "subtitles.ass"
    subtitle.write_text(
        "[Script Info]\nPlayResX: 1920\nPlayResY: 1080\n", encoding="utf-8"
    )
    output = tmp_path / "out.mp4"
    captured: dict[str, object] = {}

    composer = VideoCompose()
    monkeypatch.setattr(composer, "_pre_compose_validation", lambda *args, **kwargs: None)

    def fake_compose(inputs):
        captured.update(inputs)
        return SimpleNamespace(success=True, error=None, data={}, artifacts=[])

    monkeypatch.setattr(composer, "_compose", fake_compose)

    result = composer.execute(
        {
            "operation": "render",
            "edit_decisions": {
                "version": "1.0",
                "renderer_family": "cinematic-trailer",
                "render_runtime": "ffmpeg",
                "cuts": [
                    {
                        "id": "cut-1",
                        "source": "video-1",
                        "in_seconds": 0.0,
                        "out_seconds": 2.0,
                    }
                ],
                "subtitles": {"enabled": True, "source": "subtitle-1"},
            },
            "asset_manifest": {
                "version": "1.0",
                "assets": [
                    {
                        "id": "video-1",
                        "type": "video",
                        "path": str(source),
                        "source_tool": "fixture",
                        "scene_id": "scene-1",
                    },
                    {
                        "id": "subtitle-1",
                        "type": "subtitle",
                        "path": str(subtitle),
                        "source_tool": "subtitle_gen",
                        "scene_id": "global",
                    },
                ],
            },
            "output_path": str(output),
        }
    )

    assert result.success, result.error
    assert captured["subtitle_path"] == str(subtitle)


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


def test_video_compose_derives_theme_from_schema_v2_playbook_fields():
    theme = VideoCompose._build_theme_from_playbook("anime-ghibli", None)

    assert theme is not None
    assert theme["headingFont"] == "Noto Serif JP"
    assert theme["bodyFont"] == "Noto Sans"
    assert theme["mutedTextColor"] == "#8B9A7E"
    assert theme["chartColors"][:3] == ["#A8E6CF", "#FFB347", "#FF6B9D"]
    assert theme["transitionDuration"] == 1.0


def test_video_compose_derives_theme_from_ad_brand_playbook():
    theme = VideoCompose._build_theme_from_playbook("ad-brand", None)

    assert theme is not None
    assert theme["primaryColor"] == "#1A1A2E"
    assert theme["accentColor"] == "#E94560"
    assert theme["headingFont"] == "Inter"
    assert theme["bodyFont"] == "Inter"
    assert theme["chartColors"][:3] == ["#E94560", "#0F3460", "#533483"]
    assert theme["transitionDuration"] == 0.2


def test_video_compose_derives_subtitle_font_from_playbook_body_font():
    style = VideoCompose._resolve_subtitle_style(
        explicit_style=None,
        edit_decisions=None,
        playbook=load_playbook("anime-ghibli"),
    )

    assert style["font"] == "Noto Sans"
    assert style["primary_color"] == "#F5F0E8"


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
