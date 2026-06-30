from __future__ import annotations

import pytest

from tools.audio.elevenlabs_tts import ElevenLabsTTS
from tools.graphics.flux_image import FluxImage
from tools.graphics.google_imagen import GoogleImagen
from tools.graphics.grok_image import GrokImage
from tools.graphics.openai_image import OpenAIImage
from tools.graphics.recraft_image import RecraftImage
from tools.graphics.wanx_image import WanxImage
from tools.video.grok_video import GrokVideo
from tools.video.runway_video import RunwayVideo
from tools.video.wan_video_api import WanVideoAPI


def _default_option_id(options: list[dict[str, object]]) -> object:
    for option in options:
        if option.get("default") is True:
            return option.get("id")
    raise AssertionError("No default model option found")


def test_refreshed_model_catalog_defaults_are_current() -> None:
    assert _default_option_id(OpenAIImage.model_options) == "gpt-image-2"
    assert _default_option_id(GoogleImagen.model_options) == "gemini-3-pro-image"
    assert _default_option_id(FluxImage.model_options) == "flux-2-pro"
    assert _default_option_id(RecraftImage.model_options) == "v4.1"
    assert _default_option_id(GrokImage.model_options) == "grok-imagine-image-quality"
    assert _default_option_id(GrokVideo.model_options) == "grok-imagine-video"
    assert _default_option_id(WanxImage.model_options) == "wan2.7-image-pro"
    assert _default_option_id(RunwayVideo.model_options) == "seedance2"
    assert _default_option_id(ElevenLabsTTS.model_options) == "eleven_v3"


def test_wanx_runtime_default_promotes_qwen_when_workspace_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DASHSCOPE_API_KEY", "test-key")
    monkeypatch.setenv("DASHSCOPE_WORKSPACE_ID", "ws-test")

    info = WanxImage().get_info()

    assert info["input_schema"]["properties"]["model"]["default"] == "qwen-image-2.0-pro"
    assert _default_option_id(info["model_options"]) == "qwen-image-2.0-pro"


def test_wanx_runtime_default_stays_key_only_without_workspace(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DASHSCOPE_API_KEY", "test-key")
    monkeypatch.delenv("DASHSCOPE_WORKSPACE_ID", raising=False)
    monkeypatch.delenv("BAILIAN_WORKSPACE_ID", raising=False)
    monkeypatch.delenv("DASHSCOPE_QWEN_IMAGE_ENDPOINT", raising=False)
    monkeypatch.delenv("BAILIAN_QWEN_IMAGE_ENDPOINT", raising=False)
    monkeypatch.delenv("DASHSCOPE_QWEN_IMAGE_BASE_URL", raising=False)
    monkeypatch.delenv("DASHSCOPE_BASE_HTTP_API_URL", raising=False)
    monkeypatch.delenv("BAILIAN_BASE_HTTP_API_URL", raising=False)

    info = WanxImage().get_info()

    assert info["input_schema"]["properties"]["model"]["default"] == "wan2.7-image-pro"
    assert _default_option_id(info["model_options"]) == "wan2.7-image-pro"


def test_bailian_video_operation_defaults_use_happyhorse_1_1() -> None:
    defaults = {
        option["id"]
        for option in WanVideoAPI.model_options
        if option.get("default_for_operations")
    }

    assert {"happyhorse-1.1-t2v", "happyhorse-1.1-i2v", "happyhorse-1.1-r2v"} <= defaults
    assert "happyhorse-1.0-video-edit" in defaults
