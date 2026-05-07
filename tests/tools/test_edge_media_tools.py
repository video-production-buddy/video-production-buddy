from __future__ import annotations

import builtins
from pathlib import Path
import types
from typing import Any

import pytest

from tools.audio.audio_enhance import AudioEnhance
from tools.avatar.lip_sync import LipSync
from tools.avatar.talking_head import TalkingHead
from tools.capture.cap_recorder import CapRecorder
from tools.enhancement.bg_remove import BgRemove
from tools.enhancement.color_grade import ColorGrade
from tools.enhancement.eye_enhance import EyeEnhance
from tools.enhancement.face_enhance import FaceEnhance
from tools.enhancement.face_restore import FaceRestore
from tools.enhancement.upscale import Upscale
from tools.base_tool import ToolStatus
from tools.subtitle.subtitle_gen import SubtitleGen


def test_cap_pick_latest_accepts_exact_output_file_path(tmp_path, monkeypatch):
    recordings_root = tmp_path / "cap"
    source = recordings_root / "session-1" / "output" / "result.mp4"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"cap-recording")
    requested_output = tmp_path / "picked.mp4"

    monkeypatch.setattr(
        "tools.capture.cap_recorder._find_cap_recordings_dir",
        lambda: recordings_root,
    )

    result = CapRecorder().execute(
        {"operation": "pick_latest", "output_dir": str(requested_output)}
    )

    assert result.success
    assert result.data["output_path"] == str(requested_output)
    assert requested_output.read_bytes() == b"cap-recording"


def test_talking_head_schema_does_not_offer_unimplemented_musetalk():
    model_schema = TalkingHead.input_schema["properties"]["model"]

    assert "musetalk" not in model_schema["enum"]


def test_lip_sync_rejects_unknown_model_before_checkpoint_lookup(tmp_path, monkeypatch):
    wav2lip_dir = tmp_path / "wav2lip"
    wav2lip_dir.mkdir()
    video_path = tmp_path / "source.mp4"
    audio_path = tmp_path / "voice.wav"
    video_path.write_bytes(b"video")
    audio_path.write_bytes(b"audio")
    monkeypatch.setenv("WAV2LIP_PATH", str(wav2lip_dir))

    result = LipSync().execute(
        {
            "video_path": str(video_path),
            "audio_path": str(audio_path),
            "model": "not-a-real-model",
        }
    )

    assert not result.success
    assert "Unknown model" in (result.error or "")


def test_lip_sync_status_respects_declared_ffmpeg_dependency(tmp_path, monkeypatch):
    wav2lip_dir = tmp_path / "wav2lip"
    wav2lip_dir.mkdir()
    monkeypatch.setenv("WAV2LIP_PATH", str(wav2lip_dir))
    monkeypatch.setattr("tools.base_tool.shutil.which", lambda command: None)

    assert LipSync().get_status() == ToolStatus.UNAVAILABLE


def test_face_restore_status_requires_cv2_runtime_dependency(monkeypatch):
    original_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name in {"gfpgan", "torch"}:
            return types.SimpleNamespace()
        if name == "cv2":
            raise ImportError("cv2 missing")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    assert FaceRestore().get_status() == ToolStatus.UNAVAILABLE


@pytest.mark.parametrize(
    ("tool", "present_module", "missing_module"),
    [
        (BgRemove(), "rembg", "PIL"),
        (Upscale(), "realesrgan", "torch"),
    ],
)
def test_enhancement_status_respects_all_declared_dependencies(
    tool: Any,
    present_module: str,
    missing_module: str,
    monkeypatch: pytest.MonkeyPatch,
):
    original_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == present_module:
            return types.SimpleNamespace()
        if name == missing_module:
            raise ImportError(f"{missing_module} missing")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    assert tool.get_status() == ToolStatus.UNAVAILABLE


@pytest.mark.parametrize(
    ("tool", "base", "variant"),
    [
        (
            SubtitleGen(),
            {
                "segments": [
                    {
                        "start": 0.0,
                        "end": 1.0,
                        "text": "Cloud code",
                        "words": [
                            {"word": "Cloud", "start": 0.0, "end": 0.4},
                            {"word": "code", "start": 0.4, "end": 1.0},
                        ],
                    }
                ],
                "format": "srt",
                "max_words_per_cue": 8,
            },
            {"output_path": "captions-a.srt"},
        ),
        (
            SubtitleGen(),
            {
                "segments": [
                    {
                        "start": 0.0,
                        "end": 1.0,
                        "text": "Cloud code",
                        "words": [
                            {"word": "Cloud", "start": 0.0, "end": 0.4},
                            {"word": "code", "start": 0.4, "end": 1.0},
                        ],
                    }
                ],
                "format": "srt",
                "max_words_per_cue": 8,
            },
            {"corrections": {"cloud": "Claude"}},
        ),
        (
            FaceEnhance(),
            {"input_path": "speaker.mp4", "preset": "sharpen"},
            {"codec": "libx265"},
        ),
        (
            ColorGrade(),
            {"input_path": "scene.mp4", "profile": "neutral", "intensity": 1.0},
            {"custom_vf": "eq=brightness=0.1"},
        ),
        (
            AudioEnhance(),
            {"input_path": "voice.wav", "preset": "clean_speech"},
            {"audio_bitrate": "96k"},
        ),
        (
            FaceRestore(),
            {"input_path": "face.png", "model": "CodeFormer", "fidelity": 0.5, "upscale": 2},
            {"bg_upsampler": True},
        ),
        (
            FaceRestore(),
            {"input_path": "face.png", "model": "CodeFormer", "fidelity": 0.5, "upscale": 2},
            {"output_path": "restored-a.png"},
        ),
        (
            BgRemove(),
            {"input_path": "subject.png", "model": "u2net", "alpha_matting": False},
            {"output_path": "subject-a.png"},
        ),
        (
            Upscale(),
            {
                "input_path": "small.png",
                "scale": 4,
                "model": "RealESRGAN_x4plus",
                "face_enhance": False,
                "denoise_strength": 0.5,
            },
            {"output_path": "large-a.png"},
        ),
        (
            TalkingHead(),
            {
                "image_path": "face.png",
                "audio_path": "voice.wav",
                "model": "sadtalker",
                "expression_scale": 1.0,
                "still_mode": False,
            },
            {"output_path": "talking-head-a.mp4"},
        ),
        (
            TalkingHead(),
            {
                "image_path": "face.png",
                "audio_path": "voice.wav",
                "model": "sadtalker",
                "expression_scale": 1.0,
                "still_mode": False,
            },
            {"preprocess": "full"},
        ),
        (
            LipSync(),
            {
                "video_path": "speaker.mp4",
                "audio_path": "voice.wav",
                "model": "wav2lip",
                "face_padding": [0, 10, 0, 0],
                "resize_factor": 1,
            },
            {"output_path": "lipsync-a.mp4"},
        ),
    ],
)
def test_edge_media_idempotency_keys_include_output_shaping_inputs(
    tool: Any,
    base: dict[str, object],
    variant: dict[str, object],
):
    assert tool.idempotency_key(base) != tool.idempotency_key({**base, **variant})


def test_subtitle_timestamps_carry_when_rounding_to_next_second():
    assert SubtitleGen._ts_srt(1.9996) == "00:00:02,000"
    assert SubtitleGen._ts_vtt(1.9996) == "00:00:02.000"


def test_subtitle_gen_malformed_word_timing_returns_tool_error(tmp_path: Path) -> None:
    try:
        result = SubtitleGen().execute(
            {
                "segments": [
                    {
                        "text": "broken timing",
                        "start": 0.0,
                        "end": 1.0,
                        "words": [{"word": "broken"}],
                    }
                ],
                "output_path": str(tmp_path / "broken.srt"),
            }
        )
    except Exception as exc:  # pragma: no cover - documents current bug shape
        pytest.fail(f"execute raised instead of returning ToolResult: {exc}")

    assert result.success is False
    assert "timestamp" in (result.error or "").lower()


def test_color_grade_zero_intensity_uses_noop_filter():
    assert ColorGrade()._build_filter({"profile": "cinematic_warm", "intensity": 0.0}) == "null"


def test_color_grade_missing_lut_path_returns_tool_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    input_path = tmp_path / "scene.mp4"
    input_path.write_bytes(b"video")
    output_path = tmp_path / "graded.mp4"
    monkeypatch.setattr(ColorGrade, "run_command", lambda *args, **kwargs: output_path.write_bytes(b"graded"))

    result = ColorGrade().execute(
        {
            "input_path": str(input_path),
            "output_path": str(output_path),
            "lut_path": str(tmp_path / "missing.cube"),
        }
    )

    assert result.success is False
    assert "LUT not found" in (result.error or "")


def test_color_grade_escapes_single_quotes_in_lut_filter_path(tmp_path: Path):
    lut_dir = tmp_path / "look's"
    lut_dir.mkdir()
    lut_path = lut_dir / "grade.cube"
    lut_path.write_text("LUT", encoding="utf-8")

    vf = ColorGrade()._build_filter({"lut_path": str(lut_path)})

    assert "look\\'s" in vf


def test_face_enhance_rejects_unknown_preset_in_multi_preset_list(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    input_path = tmp_path / "speaker.mp4"
    input_path.write_bytes(b"video")
    output_path = tmp_path / "enhanced.mp4"
    monkeypatch.setattr(FaceEnhance, "run_command", lambda *args, **kwargs: output_path.write_bytes(b"enhanced"))

    result = FaceEnhance().execute(
        {
            "input_path": str(input_path),
            "output_path": str(output_path),
            "presets": ["sharpen", "not-a-real-preset"],
        }
    )

    assert result.success is False
    assert "Unknown preset" in (result.error or "")


def test_bg_remove_rejects_unknown_model_before_rembg_call(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    input_path = tmp_path / "subject.png"
    input_path.write_bytes(b"image")
    output_path = tmp_path / "subject-nobg.png"
    original_import = builtins.__import__

    class FakeImage:
        size = (1, 1)

        def save(self, path: str) -> None:
            Path(path).write_bytes(b"image")

    fake_image_module = types.SimpleNamespace(open=lambda path: FakeImage())

    def fake_import(name, *args, **kwargs):
        if name == "rembg":
            return types.SimpleNamespace(remove=lambda image, **kwargs: FakeImage())
        if name == "PIL":
            return types.SimpleNamespace(Image=fake_image_module)
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    result = BgRemove().execute(
        {
            "input_path": str(input_path),
            "output_path": str(output_path),
            "model": "not-a-real-model",
        }
    )

    assert result.success is False
    assert "Unknown model" in (result.error or "")


def test_upscale_rejects_unknown_model_before_upsampler(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    input_path = tmp_path / "small.png"
    input_path.write_bytes(b"image")
    output_path = tmp_path / "large.png"

    def fake_upscale_image(self, *args: Any, **kwargs: Any):
        output_path.write_bytes(b"large")
        return {"output_width": 16, "output_height": 16}

    monkeypatch.setattr(Upscale, "_upscale_image", fake_upscale_image)

    result = Upscale().execute(
        {
            "input_path": str(input_path),
            "output_path": str(output_path),
            "model": "not-a-real-model",
        }
    )

    assert result.success is False
    assert "Unknown model" in (result.error or "")


def test_upscale_rejects_unknown_scale_before_upsampler(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    input_path = tmp_path / "small.png"
    input_path.write_bytes(b"image")
    output_path = tmp_path / "large.png"

    def fake_upscale_image(self, *args: Any, **kwargs: Any):
        output_path.write_bytes(b"large")
        return {"output_width": 16, "output_height": 16}

    monkeypatch.setattr(Upscale, "_upscale_image", fake_upscale_image)

    result = Upscale().execute(
        {
            "input_path": str(input_path),
            "output_path": str(output_path),
            "scale": 3,
        }
    )

    assert result.success is False
    assert "Unknown scale" in (result.error or "")


def test_face_restore_rejects_unknown_model_before_restorer_load(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    input_path = tmp_path / "face.png"
    input_path.write_bytes(b"image")
    output_path = tmp_path / "restored.png"
    original_import = builtins.__import__

    class FakeRestorer:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        def enhance(self, *args: Any, **kwargs: Any):
            return None, [object()], object()

    fake_cv2 = types.SimpleNamespace(
        IMREAD_COLOR=1,
        imread=lambda *args, **kwargs: object(),
        imwrite=lambda path, img: (Path(path).write_bytes(b"restored"), True)[1],
    )

    def fake_import(name, *args, **kwargs):
        if name == "cv2":
            return fake_cv2
        if name == "gfpgan":
            return types.SimpleNamespace(GFPGANer=FakeRestorer)
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    result = FaceRestore().execute(
        {
            "input_path": str(input_path),
            "output_path": str(output_path),
            "model": "not-a-real-model",
        }
    )

    assert result.success is False
    assert "Unknown model" in (result.error or "")


def test_eye_enhance_rejects_unknown_operation_before_fallback_render(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    input_path = tmp_path / "speaker.mp4"
    input_path.write_bytes(b"video")
    output_path = tmp_path / "eyes.mp4"

    monkeypatch.setattr(EyeEnhance, "_has_mediapipe", lambda self: False)
    monkeypatch.setattr(EyeEnhance, "_has_opencv", lambda self: False)
    monkeypatch.setattr(EyeEnhance, "run_command", lambda *args, **kwargs: output_path.write_bytes(b"eyes"))

    result = EyeEnhance().execute(
        {
            "input_path": str(input_path),
            "output_path": str(output_path),
            "operations": ["dark_circles", "not-a-real-operation"],
        }
    )

    assert result.success is False
    assert "Unknown operation" in (result.error or "")


def test_eye_enhance_idempotency_key_includes_output_and_encoding_parameters():
    tool = EyeEnhance()
    base = {
        "input_path": "speaker.mp4",
        "operations": ["dark_circles"],
        "dark_circle_intensity": 0.4,
        "eye_brighten_intensity": 0.3,
        "sharpen_intensity": 0.2,
        "output_path": "eyes-a.mp4",
        "codec": "libx264",
        "crf": 18,
    }

    base_key = tool.idempotency_key(base)
    for variant in (
        {"output_path": "eyes-b.mp4"},
        {"codec": "libx265"},
        {"crf": 22},
    ):
        assert tool.idempotency_key({**base, **variant}) != base_key


def test_eye_enhance_ffmpeg_fallback_uses_requested_codec(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    input_path = tmp_path / "speaker.mp4"
    input_path.write_bytes(b"video")
    output_path = tmp_path / "eyes.mp4"
    captured_cmd: list[str] = []

    monkeypatch.setattr(EyeEnhance, "_has_mediapipe", lambda self: False)
    monkeypatch.setattr(EyeEnhance, "_has_opencv", lambda self: False)

    def fake_run_command(self: EyeEnhance, cmd: list[str], **kwargs: Any):
        captured_cmd[:] = cmd
        output_path.write_bytes(b"eyes")

    monkeypatch.setattr(EyeEnhance, "run_command", fake_run_command)

    result = EyeEnhance().execute(
        {
            "input_path": str(input_path),
            "output_path": str(output_path),
            "codec": "libx265",
            "crf": 22,
        }
    )

    assert result.success
    assert captured_cmd[captured_cmd.index("-c:v") + 1] == "libx265"


@pytest.mark.parametrize(
    ("tool", "input_name", "extra_inputs"),
    [
        (FaceEnhance(), "speaker.mp4", {"preset": "sharpen"}),
        (ColorGrade(), "scene.mp4", {"profile": "neutral"}),
        (AudioEnhance(), "voice.wav", {"preset": "normalize_only"}),
        (EyeEnhance(), "speaker.mp4", {}),
    ],
)
def test_ffmpeg_enhancement_tools_fail_when_expected_output_is_missing(
    tool: Any,
    input_name: str,
    extra_inputs: dict[str, object],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    input_path = tmp_path / input_name
    output_path = tmp_path / "enhanced.mp4"
    input_path.write_bytes(b"media")

    def fake_run_command(*args: Any, **kwargs: Any):
        return object()

    monkeypatch.setattr(type(tool), "run_command", fake_run_command)
    if isinstance(tool, EyeEnhance):
        monkeypatch.setattr(EyeEnhance, "_has_mediapipe", lambda self: False)
        monkeypatch.setattr(EyeEnhance, "_has_opencv", lambda self: False)

    result = tool.execute(
        {
            "input_path": str(input_path),
            "output_path": str(output_path),
            **extra_inputs,
        }
    )

    assert result.success is False
    assert "output" in (result.error or "").lower()
    assert str(output_path) in (result.error or "")


def test_face_restore_fails_when_cv2_write_does_not_create_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    input_path = tmp_path / "face.png"
    output_path = tmp_path / "restored.png"
    input_path.write_bytes(b"image")
    original_import = builtins.__import__

    class FakeRestorer:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        def enhance(self, *args: Any, **kwargs: Any):
            return None, [object()], object()

    fake_cv2 = types.SimpleNamespace(
        IMREAD_COLOR=1,
        imread=lambda *args, **kwargs: object(),
        imwrite=lambda *args, **kwargs: False,
    )

    def fake_import(name, *args, **kwargs):
        if name == "cv2":
            return fake_cv2
        if name == "gfpgan":
            return types.SimpleNamespace(GFPGANer=FakeRestorer)
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    result = FaceRestore().execute(
        {"input_path": str(input_path), "output_path": str(output_path)}
    )

    assert result.success is False
    assert str(output_path) in (result.error or "")


def test_upscale_fails_when_cv2_image_write_does_not_create_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    input_path = tmp_path / "small.png"
    output_path = tmp_path / "upscaled.png"
    input_path.write_bytes(b"image")
    original_import = builtins.__import__

    class FakeImage:
        shape = (12, 16, 3)

    class FakeUpsampler:
        def enhance(self, *args: Any, **kwargs: Any):
            return FakeImage(), None

    fake_cv2 = types.SimpleNamespace(
        IMREAD_UNCHANGED=-1,
        imread=lambda *args, **kwargs: object(),
        imwrite=lambda *args, **kwargs: False,
    )

    def fake_import(name, *args, **kwargs):
        if name == "cv2":
            return fake_cv2
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    monkeypatch.setattr(
        Upscale,
        "_build_upsampler",
        lambda self, *args, **kwargs: FakeUpsampler(),
    )

    result = Upscale().execute({"input_path": str(input_path), "output_path": str(output_path)})

    assert result.success is False
    assert str(output_path) in (result.error or "")


def test_upscale_video_fails_when_ffmpeg_extracts_no_frames(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    input_path = tmp_path / "clip.mp4"
    output_path = tmp_path / "upscaled.mp4"
    input_path.write_bytes(b"video")
    original_import = builtins.__import__

    fake_cv2 = types.SimpleNamespace()

    def fake_import(name, *args, **kwargs):
        if name == "cv2":
            return fake_cv2
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    monkeypatch.setattr(Upscale, "_get_video_fps", lambda self, path: 24.0)
    monkeypatch.setattr(Upscale, "_build_upsampler", lambda self, *args, **kwargs: object())
    monkeypatch.setattr(Upscale, "run_command", lambda *args, **kwargs: object())

    result = Upscale().execute({"input_path": str(input_path), "output_path": str(output_path)})

    assert result.success is False
    assert "frame" in (result.error or "").lower()
