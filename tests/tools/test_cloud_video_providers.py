from __future__ import annotations

import pytest

from tools.base_tool import ToolResult
from tools.video.grok_video import GrokVideo
from tools.video.heygen_video import HeyGenVideo
from tools.video.higgsfield_video import HiggsFieldVideo
from tools.video.kling_video import KlingVideo
from tools.video.ltx_video_modal import LTXVideoModal
from tools.video.minimax_video import MiniMaxVideo
from tools.video.pexels_video import PexelsVideo
from tools.video.pixabay_video import PixabayVideo
from tools.video.runway_video import RunwayVideo
from tools.video.seedance_replicate import SeedanceReplicate
from tools.video.seedance_video import SeedanceVideo
from tools.video.veo_video import VeoVideo
from tools.video.wan_video_api import WanVideoAPI


def _configure_provider_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FAL_KEY", "test-fal-key")
    monkeypatch.setenv("RUNWAY_API_KEY", "test-runway-key")
    monkeypatch.setenv("HIGGSFIELD_KEY", "test-higgs-key:test-higgs-secret")
    monkeypatch.setenv("REPLICATE_API_TOKEN", "test-replicate-token")
    monkeypatch.setenv("XAI_API_KEY", "test-xai-key")
    monkeypatch.setenv("HEYGEN_API_KEY", "test-heygen-key")
    monkeypatch.setenv("MODAL_LTX2_ENDPOINT_URL", "https://modal.example.test/ltx")


def _fail_network(*_args, **_kwargs):
    raise AssertionError("network called before local input validation")


@pytest.mark.parametrize(
    "tool",
    [
        KlingVideo(),
        MiniMaxVideo(),
        RunwayVideo(),
        HiggsFieldVideo(),
        SeedanceReplicate(),
    ],
)
def test_cloud_video_image_to_video_requires_image_before_network(
    monkeypatch: pytest.MonkeyPatch,
    tool,
) -> None:
    _configure_provider_env(monkeypatch)
    monkeypatch.setattr("requests.post", _fail_network)

    result = tool.execute(
        {"prompt": "Animate the approved product frame", "operation": "image_to_video"}
    )

    assert isinstance(result, ToolResult)
    assert not result.success
    assert "image_to_video requires" in (result.error or "")


@pytest.mark.parametrize(
    "tool",
    [
        KlingVideo(),
        MiniMaxVideo(),
        RunwayVideo(),
        HiggsFieldVideo(),
        SeedanceReplicate(),
        SeedanceVideo(),
        VeoVideo(),
        GrokVideo(),
        HeyGenVideo(),
        LTXVideoModal(),
    ],
)
def test_cloud_video_rejects_unknown_operation_before_network(
    monkeypatch: pytest.MonkeyPatch,
    tool,
) -> None:
    _configure_provider_env(monkeypatch)
    monkeypatch.setattr("requests.post", _fail_network)

    result = tool.execute(
        {"prompt": "A product hero shot", "operation": "video_editing"}
    )

    assert isinstance(result, ToolResult)
    assert not result.success
    assert "Unknown operation" in (result.error or "")


class _FakeResponse:
    def __init__(self, payload: dict | None = None, content: bytes = b"fake mp4") -> None:
        self._payload = payload or {}
        self.content = content
        self.ok = True
        self.status_code = 200
        self.text = ""

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


@pytest.mark.parametrize("tool", [MiniMaxVideo(), VeoVideo()])
def test_cloud_video_success_payload_includes_output_path_and_format(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
    tool,
) -> None:
    _configure_provider_env(monkeypatch)
    monkeypatch.setattr("time.sleep", lambda _seconds: None)

    def fake_post(*_args, **_kwargs):
        return _FakeResponse(
            {
                "status_url": "https://queue.example.test/status",
                "response_url": "https://queue.example.test/response",
            }
        )

    def fake_get(url, *_args, **_kwargs):
        if url == "https://queue.example.test/status":
            return _FakeResponse({"status": "COMPLETED"})
        if url == "https://queue.example.test/response":
            return _FakeResponse({"video": {"url": "https://cdn.example.test/out.mp4"}})
        if url == "https://cdn.example.test/out.mp4":
            return _FakeResponse(content=b"fake mp4")
        raise AssertionError(f"unexpected GET {url}")

    monkeypatch.setattr("requests.post", fake_post)
    monkeypatch.setattr("requests.get", fake_get)

    output_path = tmp_path / f"{tool.name}.mp4"
    result = tool.execute({"prompt": "A product hero shot", "output_path": str(output_path)})

    assert result.success
    assert result.data["output_path"] == str(output_path)
    assert result.data["format"] == "mp4"


def test_seedance_replicate_success_payload_includes_operation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    _configure_provider_env(monkeypatch)
    monkeypatch.setattr("time.sleep", lambda _seconds: None)

    def fake_post(*_args, **_kwargs):
        return _FakeResponse(
            {
                "status": "succeeded",
                "output": "https://cdn.example.test/seedance.mp4",
                "input": {"seed": 123},
            }
        )

    def fake_get(url, *_args, **_kwargs):
        if url == "https://cdn.example.test/seedance.mp4":
            return _FakeResponse(content=b"fake mp4")
        raise AssertionError(f"unexpected GET {url}")

    monkeypatch.setattr("requests.post", fake_post)
    monkeypatch.setattr("requests.get", fake_get)

    output_path = tmp_path / "seedance-replicate.mp4"
    result = SeedanceReplicate().execute(
        {"prompt": "A product hero shot", "output_path": str(output_path)}
    )

    assert result.success
    assert result.data["output_path"] == str(output_path)
    assert result.data["format"] == "mp4"
    assert result.data["operation"] == "text_to_video"


@pytest.mark.parametrize(
    ("tool", "image_field"),
    [
        (KlingVideo(), "image_url"),
        (MiniMaxVideo(), "image_url"),
        (RunwayVideo(), "image_url"),
        (HiggsFieldVideo(), "image_url"),
        (SeedanceReplicate(), "image_url"),
        (VeoVideo(), "image_url"),
        (GrokVideo(), "image_url"),
        (HeyGenVideo(), "reference_image_url"),
        (LTXVideoModal(), "reference_image_url"),
    ],
)
def test_cloud_video_idempotency_key_includes_conditioning_image(
    tool,
    image_field: str,
) -> None:
    base = {
        "prompt": "Animate the approved product frame",
        "operation": "image_to_video",
        image_field: "https://example.test/a.png",
    }
    changed = dict(base, **{image_field: "https://example.test/b.png"})

    assert tool.idempotency_key(base) != tool.idempotency_key(changed)

    output_base = {**base, "output_path": "clips/provider-a.mp4"}
    output_changed = {**output_base, "output_path": "clips/provider-b.mp4"}

    assert tool.idempotency_key(output_base) != tool.idempotency_key(output_changed)


@pytest.mark.parametrize(
    ("tool", "base"),
    [
        (
            PexelsVideo(),
            {"query": "city b-roll", "orientation": "landscape", "size": "large", "page": 1},
        ),
        (
            PixabayVideo(),
            {"query": "city b-roll", "video_type": "film", "category": "business", "page": 1},
        ),
    ],
)
def test_stock_video_provider_idempotency_key_includes_output_path(tool, base) -> None:
    assert tool.idempotency_key({**base, "output_path": "stock-a.mp4"}) != tool.idempotency_key(
        {**base, "output_path": "stock-b.mp4"}
    )


def test_wan_video_api_idempotency_key_includes_output_path() -> None:
    tool = WanVideoAPI()
    base = {
        "prompt": "A cinematic product launch shot",
        "operation": "text_to_video",
        "model_variant": "wan2.6-t2v",
    }

    assert tool.idempotency_key({**base, "output_path": "wan-a.mp4"}) != tool.idempotency_key(
        {**base, "output_path": "wan-b.mp4"}
    )
