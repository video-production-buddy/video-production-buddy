from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest

from tools.audio.audio_mixer import AudioMixer
from tools.base_tool import ToolStatus
from tools.capture.screen_recorder import ScreenRecorder
from tools.capture.screen_capture_selector import ScreenCaptureSelector
from tools.character.character_animation import (
    ActionTimelineCompiler,
    CharacterAnimationReviewer,
    CharacterRigRenderer,
    CharacterSpecGenerator,
    PoseLibraryBuilder,
    SvgRigBuilder,
)
from tools.compliance.compliance_check import ComplianceCheck
from tools.enhancement.eye_enhance import EyeEnhance
from tools.graphics.code_snippet import CodeSnippet
from tools.graphics.diagram_gen import DiagramGen
from tools.graphics.math_animate import MathAnimate


def test_screen_recorder_reports_ffmpeg_failure_even_if_partial_file_exists(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_path = tmp_path / "recording.mp4"

    def fake_run(cmd: list[str], *args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        if cmd[0] == "ffmpeg":
            output_path.write_bytes(b"partial mp4")
            return subprocess.CompletedProcess(
                cmd,
                1,
                stdout="",
                stderr="x11grab input failed",
            )
        if cmd[0] == "ffprobe":
            return subprocess.CompletedProcess(cmd, 0, stdout="1280,720\n", stderr="")
        raise AssertionError(f"unexpected command: {cmd}")

    monkeypatch.setattr("tools.capture.screen_recorder.platform.system", lambda: "Linux")
    monkeypatch.setattr("tools.capture.screen_recorder.subprocess.run", fake_run)
    monkeypatch.setenv("DISPLAY", ":0.0")

    result = ScreenRecorder().execute(
        {
            "output_path": str(output_path),
            "duration_seconds": 1,
            "capture_audio": False,
        }
    )

    assert result.success is False
    assert "ffmpeg" in (result.error or "").lower()
    assert "x11grab input failed" in (result.error or "")


@pytest.mark.parametrize(
    "variant",
    [
        {"output_path": "recording-a.mp4"},
        {"duration_seconds": 90},
        {"fps": 60},
        {"capture_audio": False},
        {"region": {"x": 10, "y": 20, "width": 640, "height": 360}},
        {"screen_index": 1},
    ],
)
def test_screen_recorder_idempotency_key_includes_capture_parameters(
    variant: dict[str, object],
) -> None:
    tool = ScreenRecorder()
    base = {
        "output_path": "recording.mp4",
        "duration_seconds": 30,
        "fps": 30,
        "capture_audio": True,
        "region": {"x": 0, "y": 0, "width": 1280, "height": 720},
        "screen_index": 0,
    }

    assert tool.idempotency_key(base) != tool.idempotency_key({**base, **variant})


@pytest.mark.parametrize(
    ("base", "variant"),
    [
        (
            {
                "operation": "duck",
                "primary_audio": "speech-a.wav",
                "secondary_audio": "music.wav",
                "duck_level": -12,
            },
            {"output_path": "ducked-a.wav"},
        ),
        (
            {
                "operation": "duck",
                "primary_audio": "speech-a.wav",
                "secondary_audio": "music.wav",
                "duck_level": -12,
            },
            {"primary_audio": "speech-b.wav"},
        ),
        (
            {
                "operation": "full_mix",
                "tracks": [
                    {"path": "speech.wav", "role": "speech"},
                    {"path": "music.wav", "role": "music"},
                ],
                "ducking": {"enabled": True},
                "normalize": True,
                "target_lufs": -16,
                "target_total_duration_seconds": 30,
            },
            {"target_total_duration_seconds": 15},
        ),
        (
            {
                "operation": "duck",
                "primary_audio": "speech.wav",
                "secondary_audio": "music.wav",
                "music_volume_schedule": [{"t_seconds": 0, "gain_db": -12}],
            },
            {"music_volume_schedule": [{"t_seconds": 0, "gain_db": -3}]},
        ),
        (
            {
                "operation": "segmented_music",
                "video_path": "assembled.mp4",
                "music_path": "music-a.mp3",
                "segments": [{"start": 0, "end": 5}],
                "music_volume": 0.2,
                "fade_duration": 0.5,
            },
            {"segments": [{"start": 5, "end": 10}]},
        ),
    ],
)
def test_audio_mixer_idempotency_key_includes_all_output_shaping_inputs(
    base: dict[str, object],
    variant: dict[str, object],
) -> None:
    tool = AudioMixer()

    assert tool.idempotency_key(base) != tool.idempotency_key({**base, **variant})


def test_default_character_timeline_uses_default_design_character_id() -> None:
    character_design = CharacterSpecGenerator().execute({}).data["character_design"]
    default_character_id = character_design["characters"][0]["id"]
    scene_plan = {
        "version": "1.0",
        "scenes": [
            {
                "id": "scene-1",
                "start_seconds": 0,
                "end_seconds": 2,
                "description": "Default character reacts to a small discovery.",
            }
        ],
    }

    timeline = ActionTimelineCompiler().execute({"scene_plan": scene_plan}).data["action_timeline"]
    action_character_ids = {
        action["character_id"]
        for scene in timeline["scenes"]
        for action in scene["actions"]
    }

    assert action_character_ids == {default_character_id}


@pytest.mark.parametrize(
    ("tool", "base", "variant"),
    [
        (
            CharacterSpecGenerator(),
            {
                "characters": [{"id": "mouse", "required_actions": ["idle"]}],
                "brief": "A mouse learns to share.",
                "style": {"visual_style": "flat"},
            },
            {"output_path": "character-design-a.json"},
        ),
        (
            CharacterSpecGenerator(),
            {
                "characters": [{"id": "mouse", "required_actions": ["idle"]}],
                "brief": "A mouse learns to share.",
                "style": {"visual_style": "flat"},
            },
            {"brief": "A bird learns to share."},
        ),
        (
            SvgRigBuilder(),
            {
                "character_design": {
                    "characters": [{"id": "mouse", "required_actions": ["idle"]}]
                }
            },
            {"output_path": "rig-plan-a.json"},
        ),
        (
            SvgRigBuilder(),
            {
                "character_design": {
                    "characters": [{"id": "mouse", "required_actions": ["idle"]}]
                }
            },
            {
                "character_design": {
                    "characters": [{"id": "bird", "required_actions": ["wing_flap"]}]
                }
            },
        ),
        (
            PoseLibraryBuilder(),
            {
                "rig_plan": {
                    "characters": [
                        {"character_id": "mouse", "required_actions": ["idle"]}
                    ]
                }
            },
            {"output_path": "pose-library-a.json"},
        ),
        (
            PoseLibraryBuilder(),
            {
                "rig_plan": {
                    "characters": [
                        {"character_id": "mouse", "required_actions": ["idle"]}
                    ]
                }
            },
            {
                "rig_plan": {
                    "characters": [
                        {"character_id": "mouse", "required_actions": ["gesture"]}
                    ]
                }
            },
        ),
        (
            ActionTimelineCompiler(),
            {
                "scene_plan": {
                    "scenes": [
                        {
                            "id": "scene-1",
                            "start_seconds": 0,
                            "end_seconds": 2,
                            "description": "Mouse notices a seed.",
                        }
                    ]
                },
                "character_ids": ["mouse"],
                "fps": 24,
            },
            {"output_path": "action-timeline-a.json"},
        ),
        (
            ActionTimelineCompiler(),
            {
                "scene_plan": {
                    "scenes": [
                        {
                            "id": "scene-1",
                            "start_seconds": 0,
                            "end_seconds": 2,
                            "description": "Mouse notices a seed.",
                        }
                    ]
                },
                "character_ids": ["mouse"],
                "fps": 24,
            },
            {"character_ids": ["bird"]},
        ),
        (
            CharacterRigRenderer(),
            {
                "action_timeline": {
                    "scenes": [
                        {
                            "id": "scene-1",
                            "end_seconds": 2,
                            "actions": [{"character_id": "mouse"}],
                        }
                    ]
                },
                "rig_plan": {"characters": [{"character_id": "mouse"}]},
                "pose_library": {"characters": [{"character_id": "mouse"}]},
                "render_video": False,
                "duration_seconds": 2,
                "fps": 12,
            },
            {"output_path": "preview-a.html"},
        ),
        (
            CharacterRigRenderer(),
            {
                "action_timeline": {
                    "scenes": [
                        {
                            "id": "scene-1",
                            "end_seconds": 2,
                            "actions": [{"character_id": "mouse"}],
                        }
                    ]
                },
                "rig_plan": {"characters": [{"character_id": "mouse"}]},
                "pose_library": {"characters": [{"character_id": "mouse"}]},
                "render_video": False,
                "duration_seconds": 2,
                "fps": 12,
            },
            {"workspace_path": "character-hyperframes-a"},
        ),
        (
            CharacterRigRenderer(),
            {
                "action_timeline": {
                    "scenes": [
                        {
                            "id": "scene-1",
                            "end_seconds": 2,
                            "actions": [{"character_id": "mouse"}],
                        }
                    ]
                },
                "rig_plan": {"characters": [{"character_id": "mouse"}]},
                "pose_library": {"characters": [{"character_id": "mouse"}]},
                "render_video": False,
                "duration_seconds": 2,
                "fps": 12,
            },
            {"fps": 24},
        ),
        (
            CharacterAnimationReviewer(),
            {
                "rig_plan": {"characters": [{"joints": {"head": {}}}]},
                "pose_library": {"characters": [{"poses": {"idle": {}}}]},
                "action_timeline": {"scenes": [{"actions": [{"pose": "idle"}]}]},
                "preview_path": "preview-a.html",
                "review_level": "static",
                "browser_preview_checked": False,
                "frame_samples_checked": False,
            },
            {"output_path": "character-review-a.json"},
        ),
        (
            CharacterAnimationReviewer(),
            {
                "rig_plan": {"characters": [{"joints": {"head": {}}}]},
                "pose_library": {"characters": [{"poses": {"idle": {}}}]},
                "action_timeline": {"scenes": [{"actions": [{"pose": "idle"}]}]},
                "preview_path": "preview-a.html",
                "review_level": "static",
                "browser_preview_checked": False,
                "frame_samples_checked": False,
            },
            {"review_level": "final", "frame_samples_checked": True},
        ),
    ],
)
def test_character_animation_idempotency_keys_include_contract_inputs(
    tool,
    base: dict[str, object],
    variant: dict[str, object],
) -> None:
    assert tool.idempotency_key(base) != tool.idempotency_key({**base, **variant})


def test_compliance_structured_presence_invalid_min_count_returns_tool_error() -> None:
    checkpoint = {
        "id": "CP-PRESENCE",
        "check_type": "presence",
        "evaluation_method": "structural",
        "criterion": "structured criteria should drive this check",
        "failure_action": "revise",
        "structured": {
            "kind": "presence",
            "terms": ["brand mark"],
            "min_count": "two",
        },
    }

    try:
        result = ComplianceCheck().execute(
            {
                "stage_output": {"scenes": [{"description": "brand mark appears"}]},
                "checkpoint": checkpoint,
            }
        )
    except Exception as exc:  # pragma: no cover - assertion path documents bug shape
        pytest.fail(f"execute raised instead of returning ToolResult: {exc}")

    assert result.success is False
    assert "min_count" in (result.error or "")


def test_eye_enhance_status_degraded_when_only_ffmpeg_fallback_is_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(EyeEnhance, "_has_mediapipe", lambda self: False)
    monkeypatch.setattr(EyeEnhance, "_has_opencv", lambda self: False)
    monkeypatch.setattr(EyeEnhance, "check_dependencies", lambda self: None)

    assert EyeEnhance().get_status() == ToolStatus.DEGRADED


@pytest.mark.parametrize(
    ("tool", "base", "variant"),
    [
        (
            CodeSnippet(),
            {
                "code": "print('hello')",
                "language": "python",
                "theme": "monokai",
                "font_size": 20,
                "line_numbers": True,
                "padding": 40,
            },
            {"title": "example.py"},
        ),
        (
            CodeSnippet(),
            {
                "code": "print('hello')",
                "language": "python",
                "theme": "monokai",
                "font_size": 20,
                "line_numbers": True,
                "padding": 40,
            },
            {"output_path": "snippet-a.png"},
        ),
        (
            DiagramGen(),
            {
                "diagram_type": "boxes",
                "boxes": [{"label": "Input"}, {"label": "Output"}],
                "connections": [],
                "theme": "dark",
                "width": 1200,
                "height": 800,
            },
            {"output_path": "diagram-a.png"},
        ),
        (
            DiagramGen(),
            {
                "diagram_type": "boxes",
                "boxes": [{"label": "Input"}, {"label": "Output"}],
                "connections": [],
                "theme": "dark",
                "width": 1200,
                "height": 800,
            },
            {"connections": [{"from": 0, "to": 1, "label": "flow"}]},
        ),
        (
            MathAnimate(),
            {
                "scene_code": "class Demo(Scene):\n    def construct(self):\n        pass",
                "scene_name": "Demo",
                "quality": "low",
                "format": "mp4",
            },
            {"format": "gif"},
        ),
        (
            MathAnimate(),
            {
                "scene_code": "class Demo(Scene):\n    def construct(self):\n        pass",
                "scene_name": "Demo",
                "quality": "low",
                "format": "mp4",
            },
            {"output_path": "math-a.mp4"},
        ),
    ],
)
def test_graphics_idempotency_keys_include_output_shaping_inputs(
    tool: Any,
    base: dict[str, object],
    variant: dict[str, object],
) -> None:
    assert tool.idempotency_key(base) != tool.idempotency_key({**base, **variant})


def test_code_snippet_honors_forced_width_and_keys_it(tmp_path: Path) -> None:
    tool = CodeSnippet()
    base = {
        "code": "print('hello')",
        "language": "python",
        "theme": "monokai",
        "font_size": 20,
        "line_numbers": True,
        "padding": 40,
        "width": 320,
    }

    result = tool.execute({**base, "output_path": str(tmp_path / "snippet.png")})

    assert result.success, result.error
    assert result.data["width"] == 320
    assert tool.idempotency_key(base) != tool.idempotency_key({**base, "width": 640})


def test_diagram_gen_mermaid_cli_fails_when_expected_output_is_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_path = tmp_path / "diagram.png"
    tool = DiagramGen()

    monkeypatch.setattr(DiagramGen, "_has_mermaid", lambda self: True)
    monkeypatch.setattr(DiagramGen, "run_command", lambda *args, **kwargs: object())

    result = tool.execute(
        {
            "diagram_type": "mermaid",
            "definition": "graph TD\n  A[Start] --> B[End]",
            "output_path": str(output_path),
        }
    )

    assert result.success is False
    assert str(output_path) in (result.error or "")


def test_screen_capture_selector_status_requires_installed_capture_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class MissingFFmpegProvider:
        def get_status(self) -> ToolStatus:
            return ToolStatus.UNAVAILABLE

    class MissingCapProvider:
        def get_status(self) -> ToolStatus:
            return ToolStatus.AVAILABLE

        def execute(self, inputs: dict[str, object]) -> Any:
            return type(
                "Result",
                (),
                {"success": True, "data": {"installed": False, "running": False}},
            )()

    monkeypatch.setattr(
        ScreenCaptureSelector,
        "_providers",
        lambda self: {"ffmpeg": MissingFFmpegProvider(), "cap": MissingCapProvider()},
    )

    assert ScreenCaptureSelector().get_status() == ToolStatus.UNAVAILABLE


def test_math_animate_preview_quality_defaults_to_gif_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_which(command: str) -> str | None:
        if command == "manim":
            return "/usr/bin/manim"
        return None

    def fake_run(
        cmd: list[str],
        *args: Any,
        **kwargs: Any,
    ) -> subprocess.CompletedProcess[str]:
        media_dir = Path(kwargs["cwd"]) / "media" / "videos" / "scene" / "480p15"
        media_dir.mkdir(parents=True)
        (media_dir / "Demo.gif").write_bytes(b"gif89a")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr("tools.graphics.math_animate.shutil.which", fake_which)
    monkeypatch.setattr("tools.graphics.math_animate.subprocess.run", fake_run)

    result = MathAnimate().execute(
        {
            "scene_code": "class Demo(Scene):\n    def construct(self):\n        pass",
            "quality": "preview",
            "output_path": str(tmp_path / "preview.gif"),
        }
    )

    assert result.success, result.error
    assert result.data["format"] == "gif"
    assert Path(result.data["output"]).suffix == ".gif"
