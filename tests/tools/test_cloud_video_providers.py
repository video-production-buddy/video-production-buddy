from __future__ import annotations

import jsonschema
import pytest

from lib.scoring import ProviderScore
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
from tools.video.video_selector import VideoSelector
from tools.video.veo_video import VeoVideo
from tools.video.wan_video_api import WanVideoAPI


def _configure_provider_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FAL_KEY", "test-fal-key")
    monkeypatch.setenv("MINIMAX_API_KEY", "test-minimax-key")
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


def test_minimax_fast_rejects_text_to_video_before_network(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_provider_env(monkeypatch)
    monkeypatch.setattr("requests.post", _fail_network)

    result = MiniMaxVideo().execute(
        {
            "prompt": "A product hero shot",
            "operation": "text_to_video",
            "model_variant": "MiniMax-Hailuo-2.3-Fast",
            "output_path": "projects/demo/assets/video/minimax-fast.mp4",
        }
    )

    assert isinstance(result, ToolResult)
    assert not result.success
    assert "does not support text_to_video" in (result.error or "")
    assert "MiniMax-Hailuo-2.3" in (result.error or "")


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
        WanVideoAPI(),
    ],
)
@pytest.mark.parametrize(
    "output_path",
    [
        None,
        "provider-output.mp4",
        "/tmp/provider-output.mp4",
    ],
)
def test_cloud_video_requires_project_output_path_before_network(
    monkeypatch: pytest.MonkeyPatch,
    tool,
    output_path: str | None,
) -> None:
    _configure_provider_env(monkeypatch)
    calls: list[object] = []

    def fake_post(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("network called before output_path validation")

    monkeypatch.setattr("requests.post", fake_post)

    inputs = {"prompt": "A product hero shot"}
    if output_path is not None:
        inputs["output_path"] = output_path

    result = tool.execute(inputs)

    assert isinstance(result, ToolResult)
    assert not result.success
    assert "output_path" in (result.error or "")
    assert "projects/<project-name>/" in (result.error or "")
    assert calls == []


@pytest.mark.parametrize(
    ("tool", "env_vars"),
    [
        (GrokVideo(), ("XAI_API_KEY",)),
        (HeyGenVideo(), ("HEYGEN_API_KEY",)),
        (KlingVideo(), ("FAL_KEY", "FAL_AI_API_KEY")),
        (MiniMaxVideo(), ("MINIMAX_API_KEY",)),
        (HiggsFieldVideo(), ("HIGGSFIELD_KEY", "HIGGSFIELD_API_KEY", "HIGGSFIELD_API_SECRET")),
        (PexelsVideo(), ("PEXELS_API_KEY",)),
        (PixabayVideo(), ("PIXABAY_API_KEY",)),
        (RunwayVideo(), ("RUNWAY_API_KEY", "RUNWAYML_API_SECRET")),
        (SeedanceReplicate(), ("REPLICATE_API_TOKEN",)),
        (SeedanceVideo(), ("FAL_KEY", "FAL_AI_API_KEY")),
        (VeoVideo(), ("FAL_KEY", "FAL_AI_API_KEY")),
        (LTXVideoModal(), ("MODAL_LTX2_ENDPOINT_URL",)),
        (WanVideoAPI(), ("DASHSCOPE_API_KEY",)),
    ],
)
def test_cloud_video_rejects_non_project_output_path_before_credentials(
    monkeypatch: pytest.MonkeyPatch,
    tool,
    env_vars: tuple[str, ...],
) -> None:
    for env_var in env_vars:
        monkeypatch.delenv(env_var, raising=False)

    result = tool.execute(
        {"prompt": "A product hero shot", "output_path": "provider-output.mp4"}
    )

    assert isinstance(result, ToolResult)
    assert not result.success
    assert "output_path" in (result.error or "")
    assert "projects/<project-name>/" in (result.error or "")


@pytest.mark.parametrize(
    ("tool", "minimal_inputs"),
    [
        (GrokVideo(), {"prompt": "A product hero shot"}),
        (HeyGenVideo(), {"prompt": "A product hero shot"}),
        (HiggsFieldVideo(), {"prompt": "A product hero shot"}),
        (KlingVideo(), {"prompt": "A product hero shot"}),
        (MiniMaxVideo(), {"prompt": "A product hero shot"}),
        (PexelsVideo(), {"query": "product b-roll"}),
        (PixabayVideo(), {"query": "product b-roll"}),
        (RunwayVideo(), {"prompt": "A product hero shot"}),
        (SeedanceReplicate(), {"prompt": "A product hero shot"}),
        (SeedanceVideo(), {"prompt": "A product hero shot"}),
        (VeoVideo(), {"prompt": "A product hero shot"}),
        (LTXVideoModal(), {"prompt": "A product hero shot"}),
        (WanVideoAPI(), {"prompt": "A product hero shot"}),
    ],
)
def test_cloud_video_schemas_require_output_path(tool, minimal_inputs: dict[str, object]) -> None:
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance=minimal_inputs, schema=tool.input_schema)


class _FakeResponse:
    def __init__(
        self,
        payload: dict | None = None,
        content: bytes = b"fake mp4",
        headers: dict[str, str] | None = None,
    ) -> None:
        self._payload = payload or {}
        self.content = content
        self.headers = headers or {}
        self.ok = True
        self.status_code = 200
        self.text = ""

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


def _assert_output_schema_matches_payload(
    tool,
    payload: dict[str, object],
    expected_properties: set[str],
) -> None:
    output_properties = tool.output_schema["properties"]
    assert expected_properties <= set(output_properties)
    jsonschema.validate(instance=payload, schema=tool.output_schema)


@pytest.mark.parametrize("tool", [MiniMaxVideo(), VeoVideo(), LTXVideoModal(), HeyGenVideo()])
def test_cloud_video_success_payload_includes_output_path_and_format(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
    tool,
) -> None:
    _configure_provider_env(monkeypatch)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("time.sleep", lambda _seconds: None)

    def fake_post(*_args, **_kwargs):
        if isinstance(tool, HeyGenVideo):
            return _FakeResponse({"data": {"execution_id": "execution-1"}})
        if isinstance(tool, LTXVideoModal):
            return _FakeResponse(content=b"fake mp4", headers={"content-type": "video/mp4"})
        if isinstance(tool, MiniMaxVideo):
            # Native MiniMax create-task contract: {task_id, base_resp}.
            return _FakeResponse(
                {"task_id": "task-1", "base_resp": {"status_code": 0, "status_msg": "success"}}
            )
        return _FakeResponse(
            {
                "status_url": "https://queue.example.test/status",
                "response_url": "https://queue.example.test/response",
            }
        )

    def fake_get(url, *_args, **_kwargs):
        if isinstance(tool, MiniMaxVideo):
            if "/query/video_generation" in url:
                return _FakeResponse(
                    {
                        "task_id": "task-1",
                        "status": "Success",
                        "file_id": "file-1",
                        "base_resp": {"status_code": 0, "status_msg": "success"},
                    }
                )
            if "/files/retrieve" in url:
                return _FakeResponse(
                    {
                        "file": {"download_url": "https://cdn.example.test/out.mp4"},
                        "base_resp": {"status_code": 0, "status_msg": "success"},
                    }
                )
            if url == "https://cdn.example.test/out.mp4":
                return _FakeResponse(content=b"fake mp4")
            raise AssertionError(f"unexpected GET {url}")
        if url == "https://queue.example.test/status":
            return _FakeResponse({"status": "COMPLETED"})
        if url == "https://queue.example.test/response":
            return _FakeResponse({"video": {"url": "https://cdn.example.test/out.mp4"}})
        if url == "https://cdn.example.test/out.mp4":
            return _FakeResponse(content=b"fake mp4")
        raise AssertionError(f"unexpected GET {url}")

    monkeypatch.setattr(
        "tools.video._shared.poll_heygen",
        lambda _execution_id, _api_key, timeout=600: "https://cdn.example.test/out.mp4",
    )
    monkeypatch.setattr("requests.post", fake_post)
    monkeypatch.setattr("requests.get", fake_get)

    output_path = f"projects/demo/assets/video/{tool.name}.mp4"
    result = tool.execute({"prompt": "A product hero shot", "output_path": str(output_path)})

    assert result.success
    assert result.data["output_path"] == output_path
    assert result.data["format"] == "mp4"
    expected_properties = {"provider", "prompt", "operation", "output", "output_path", "format"}
    if isinstance(tool, MiniMaxVideo):
        expected_properties |= {
            "model",
            "model_name",
            "duration",
            "resolution",
            "file_size_bytes",
        }
    elif isinstance(tool, VeoVideo):
        expected_properties |= {"model", "has_audio", "file_size_bytes"}
    elif isinstance(tool, LTXVideoModal):
        expected_properties |= {
            "provider_name",
            "mode",
            "width",
            "height",
            "num_frames",
            "fps",
            "duration_seconds",
        }
    else:
        expected_properties |= {
            "provider_variant",
            "provider_name",
            "mode",
            "aspect_ratio",
            "execution_id",
        }
    _assert_output_schema_matches_payload(tool, result.data, expected_properties)


def test_seedance_replicate_success_payload_includes_operation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    _configure_provider_env(monkeypatch)
    monkeypatch.chdir(tmp_path)
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

    output_path = "projects/demo/assets/video/seedance-replicate.mp4"
    result = SeedanceReplicate().execute(
        {"prompt": "A product hero shot", "output_path": output_path}
    )

    assert result.success
    assert result.data["output_path"] == output_path
    assert result.data["format"] == "mp4"
    assert result.data["operation"] == "text_to_video"
    _assert_output_schema_matches_payload(
        SeedanceReplicate(),
        result.data,
        {
            "provider",
            "gateway",
            "model",
            "prompt",
            "operation",
            "variant",
            "aspect_ratio",
            "resolution",
            "generate_audio",
            "seed",
            "output",
            "output_path",
            "format",
            "file_size_bytes",
        },
    )


def test_grok_text_defaults_use_supported_legacy_model_and_720p_cost() -> None:
    tool = GrokVideo()

    payload = tool._build_payload({"prompt": "A product hero shot"})

    assert payload["model"] == "grok-imagine-video"
    assert payload["aspect_ratio"] == "16:9"
    assert payload["resolution"] == "720p"
    assert tool.estimate_cost({"prompt": "A product hero shot"}) == pytest.approx(0.4)


def test_grok_image_to_video_defaults_to_15_at_1080p() -> None:
    tool = GrokVideo()

    payload = tool._build_payload(
        {
            "prompt": "Animate the approved product frame",
            "operation": "image_to_video",
            "image_url": "https://example.test/product.png",
        }
    )

    assert payload["model"] == "grok-imagine-video-1.5"
    assert payload["resolution"] == "1080p"


def test_grok_rejects_15_for_text_to_video_before_network(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    _configure_provider_env(monkeypatch)
    monkeypatch.chdir(tmp_path)
    calls: list[object] = []

    def fake_post(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("network should not be called for unsupported Grok model")

    monkeypatch.setattr("requests.post", fake_post)

    result = GrokVideo().execute(
        {
            "prompt": "A product hero shot",
            "model": "grok-imagine-video-1.5",
            "output_path": "projects/demo/assets/video/grok-text.mp4",
        }
    )

    assert not result.success
    assert "text_to_video requires model='grok-imagine-video'" in (result.error or "")
    assert calls == []


@pytest.mark.parametrize("tool", [KlingVideo(), RunwayVideo(), HiggsFieldVideo(), GrokVideo()])
def test_direct_cloud_video_success_payload_matches_output_schema(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
    tool,
) -> None:
    _configure_provider_env(monkeypatch)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("time.sleep", lambda _seconds: None)

    download_url = f"https://cdn.example.test/{tool.name}.mp4"
    status_url = f"https://queue.example.test/{tool.name}/status"
    response_url = f"https://queue.example.test/{tool.name}/response"

    def fake_post(*_args, **_kwargs):
        if isinstance(tool, RunwayVideo):
            return _FakeResponse({"id": "task-1"})
        if isinstance(tool, HiggsFieldVideo):
            return _FakeResponse({"id": "generation-1", "status_url": status_url})
        if isinstance(tool, GrokVideo):
            return _FakeResponse({"request_id": "request-1"})
        return _FakeResponse({"status_url": status_url, "response_url": response_url})

    def fake_get(url, *_args, **_kwargs):
        if url == status_url:
            return _FakeResponse({"status": "COMPLETED", "output_url": download_url})
        if url == response_url:
            return _FakeResponse({"video": {"url": download_url}})
        if url == "https://api.dev.runwayml.com/v1/tasks/task-1":
            return _FakeResponse({"status": "SUCCEEDED", "output": [download_url]})
        if url == "https://api.x.ai/v1/videos/request-1":
            return _FakeResponse({"status": "done", "video": {"url": download_url}})
        if url == download_url:
            return _FakeResponse(content=b"fake direct cloud mp4")
        raise AssertionError(f"unexpected GET {url}")

    monkeypatch.setattr("requests.post", fake_post)
    monkeypatch.setattr("requests.get", fake_get)

    output_path = f"projects/demo/assets/video/{tool.name}.mp4"
    result = tool.execute({"prompt": "A product hero shot", "output_path": output_path})

    assert result.success, result.error
    assert result.data["output_path"] == output_path
    assert result.data["format"] == "mp4"
    assert (tmp_path / output_path).read_bytes() == b"fake direct cloud mp4"

    expected_properties = {
        "provider",
        "model",
        "prompt",
        "operation",
        "output",
        "output_path",
        "format",
        "file_size_bytes",
    }
    if isinstance(tool, (KlingVideo, HiggsFieldVideo)):
        expected_properties |= {"aspect_ratio"}
    elif isinstance(tool, RunwayVideo):
        expected_properties |= {"ratio", "task_id"}
    else:
        expected_properties |= {"request_id"}
    _assert_output_schema_matches_payload(tool, result.data, expected_properties)


def test_grok_reference_to_video_uses_legacy_reference_model_by_default(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    _configure_provider_env(monkeypatch)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("time.sleep", lambda _seconds: None)
    captured: dict[str, object] = {}
    download_url = "https://cdn.example.test/grok-reference.mp4"

    def fake_post(*args, **kwargs):
        captured["url"] = args[0]
        captured["json"] = kwargs["json"]
        return _FakeResponse({"request_id": "request-1"})

    def fake_get(url, *_args, **_kwargs):
        if url == "https://api.x.ai/v1/videos/request-1":
            return _FakeResponse({"status": "done", "video": {"url": download_url}})
        if url == download_url:
            return _FakeResponse(content=b"fake grok reference mp4")
        raise AssertionError(f"unexpected GET {url}")

    monkeypatch.setattr("requests.post", fake_post)
    monkeypatch.setattr("requests.get", fake_get)

    output_path = "projects/demo/assets/video/grok-reference.mp4"
    result = GrokVideo().execute(
        {
            "prompt": "Keep the product identity consistent",
            "operation": "reference_to_video",
            "reference_image_urls": ["https://example.test/product.png"],
            "output_path": output_path,
        }
    )

    assert result.success, result.error
    assert result.data["model"] == "grok-imagine-video"
    assert captured["json"]["model"] == "grok-imagine-video"
    assert captured["json"]["reference_images"] == [
        {"url": "https://example.test/product.png"}
    ]


def test_grok_model_options_expose_reference_operation_support() -> None:
    options = {option["id"]: option for option in GrokVideo.model_options}

    assert options["grok-imagine-video-1.5"]["supports"] == {
        "text_to_video": False,
        "image_to_video": True,
        "reference_to_video": False,
    }
    assert options["grok-imagine-video"]["supports"]["reference_to_video"] is True


def test_runway_seedance_default_omits_unsupported_watermark(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    _configure_provider_env(monkeypatch)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("time.sleep", lambda _seconds: None)
    captured: dict[str, object] = {}
    download_url = "https://cdn.example.test/runway.mp4"

    def fake_post(*args, **kwargs):
        captured["url"] = args[0]
        captured["json"] = kwargs["json"]
        return _FakeResponse({"id": "task-1"})

    def fake_get(url, *_args, **_kwargs):
        if url == "https://api.dev.runwayml.com/v1/tasks/task-1":
            return _FakeResponse({"status": "SUCCEEDED", "output": [download_url]})
        if url == download_url:
            return _FakeResponse(content=b"fake runway mp4")
        raise AssertionError(f"unexpected GET {url}")

    monkeypatch.setattr("requests.post", fake_post)
    monkeypatch.setattr("requests.get", fake_get)

    result = RunwayVideo().execute(
        {
            "prompt": "A product hero shot",
            "output_path": "projects/demo/assets/video/runway.mp4",
        }
    )

    assert result.success, result.error
    assert captured["json"]["model"] == "seedance2"
    assert "watermark" not in captured["json"]


def test_video_selector_uses_grok_reference_default_when_env_t2v_model_conflicts(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    _configure_provider_env(monkeypatch)
    monkeypatch.setenv("VPB_VIDEO_GENERATION_PROVIDER", "grok")
    monkeypatch.setenv("VPB_VIDEO_GENERATION_MODEL", "grok-imagine-video-1.5")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("time.sleep", lambda _seconds: None)

    selector = VideoSelector()
    monkeypatch.setattr(selector, "_providers", lambda: [GrokVideo()])
    monkeypatch.setattr(
        "lib.scoring.rank_providers",
        lambda candidates, _ctx: [
            ProviderScore(tool_name=tool.name, provider=tool.provider, task_fit=1.0)
            for tool in candidates
        ],
    )

    captured: dict[str, object] = {}
    download_url = "https://cdn.example.test/grok-reference.mp4"

    def fake_post(*args, **kwargs):
        captured["url"] = args[0]
        captured["json"] = kwargs["json"]
        return _FakeResponse({"request_id": "request-1"})

    def fake_get(url, *_args, **_kwargs):
        if url == "https://api.x.ai/v1/videos/request-1":
            return _FakeResponse({"status": "done", "video": {"url": download_url}})
        if url == download_url:
            return _FakeResponse(content=b"fake grok reference mp4")
        raise AssertionError(f"unexpected GET {url}")

    monkeypatch.setattr("requests.post", fake_post)
    monkeypatch.setattr("requests.get", fake_get)

    output_path = "projects/demo/assets/video/grok-reference.mp4"
    result = selector.execute(
        {
            "prompt": "Keep the product identity consistent",
            "operation": "reference_to_video",
            "reference_image_urls": ["https://example.test/product.png"],
            "output_path": output_path,
        }
    )

    assert result.success, result.error
    assert result.data["model"] == "grok-imagine-video"
    assert captured["json"]["model"] == "grok-imagine-video"


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


@pytest.mark.parametrize(
    ("tool", "env_var", "base"),
    [
        (
            PexelsVideo(),
            "PEXELS_API_KEY",
            {"query": "city b-roll", "orientation": "landscape", "size": "large"},
        ),
        (
            PixabayVideo(),
            "PIXABAY_API_KEY",
            {"query": "city b-roll", "video_type": "film", "category": "business"},
        ),
    ],
)
@pytest.mark.parametrize(
    "output_path",
    [
        None,
        "stock-video.mp4",
        "/tmp/stock-video.mp4",
    ],
)
def test_stock_video_requires_project_output_path_before_network(
    monkeypatch: pytest.MonkeyPatch,
    tool,
    env_var: str,
    base: dict[str, object],
    output_path: str | None,
) -> None:
    monkeypatch.setenv(env_var, "test-key")
    calls: list[object] = []

    def fake_get(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("network called before stock output_path validation")

    monkeypatch.setattr("requests.get", fake_get)

    inputs = dict(base)
    if output_path is not None:
        inputs["output_path"] = output_path

    result = tool.execute(inputs)

    assert isinstance(result, ToolResult)
    assert not result.success
    assert "output_path" in (result.error or "")
    assert "projects/<project-name>/" in (result.error or "")
    assert calls == []


@pytest.mark.parametrize(
    ("tool", "env_var", "search_payload", "download_url"),
    [
        (
            PexelsVideo(),
            "PEXELS_API_KEY",
            {
                "total_results": 1,
                "videos": [
                    {
                        "id": 123,
                        "duration": 5,
                        "url": "https://www.pexels.com/video/123/",
                        "user": {"name": "Pexels Creator"},
                        "video_files": [
                            {
                                "quality": "hd",
                                "width": 1920,
                                "height": 1080,
                                "fps": 30,
                                "link": "https://cdn.example.test/pexels.mp4",
                            }
                        ],
                    }
                ],
            },
            "https://cdn.example.test/pexels.mp4",
        ),
        (
            PixabayVideo(),
            "PIXABAY_API_KEY",
            {
                "total": 1,
                "hits": [
                    {
                        "id": 456,
                        "duration": 5,
                        "pageURL": "https://pixabay.com/videos/456/",
                        "tags": "city,b-roll",
                        "user": "Pixabay Creator",
                        "videos": {
                            "large": {
                                "url": "https://cdn.example.test/pixabay.mp4",
                                "width": 1920,
                                "height": 1080,
                            }
                        },
                    }
                ],
            },
            "https://cdn.example.test/pixabay.mp4",
        ),
    ],
)
def test_stock_video_success_payload_includes_output_path(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
    tool,
    env_var: str,
    search_payload: dict[str, object],
    download_url: str,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(env_var, "test-key")

    def fake_get(url, *_args, **_kwargs):
        if url == download_url:
            return _FakeResponse(content=b"fake stock video")
        return _FakeResponse(search_payload)

    monkeypatch.setattr("requests.get", fake_get)

    output_path = f"projects/demo/assets/video/{tool.name}.mp4"
    result = tool.execute({"query": "city b-roll", "output_path": output_path})

    assert result.success is True
    assert result.data["output"] == output_path
    assert result.data["output_path"] == output_path
    assert result.artifacts == [output_path]
    assert (tmp_path / output_path).read_bytes() == b"fake stock video"
    output_properties = tool.output_schema["properties"]
    expected_properties = {
        "provider",
        "video_id",
        "user",
        "duration_seconds",
        "width",
        "height",
        "query",
        "output",
        "output_path",
        "total_results",
        "results_returned",
        "license",
    }
    if tool.name == "pexels_video":
        expected_properties |= {"fps", "quality", "pexels_url"}
    else:
        expected_properties |= {"tags", "page_url"}
    assert expected_properties <= set(output_properties)
    jsonschema.validate(instance=result.data, schema=tool.output_schema)


@pytest.mark.parametrize(
    ("tool", "base", "variants"),
    [
        (
            PexelsVideo(),
            {
                "query": "city b-roll",
                "orientation": "landscape",
                "size": "large",
                "page": 1,
                "output_path": "stock.mp4",
            },
            [
                {"min_duration": 4},
                {"max_duration": 12},
                {"preferred_quality": "sd"},
            ],
        ),
        (
            PixabayVideo(),
            {
                "query": "city b-roll",
                "video_type": "film",
                "category": "business",
                "page": 1,
                "output_path": "stock.mp4",
            },
            [
                {"min_duration": 4},
                {"max_duration": 12},
                {"preferred_quality": "medium"},
                {"editors_choice": True},
                {"safesearch": False},
            ],
        ),
    ],
)
def test_stock_video_idempotency_key_includes_search_result_shaping_inputs(
    tool,
    base,
    variants,
) -> None:
    base_key = tool.idempotency_key(base)

    for variant in variants:
        assert tool.idempotency_key({**base, **variant}) != base_key


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
