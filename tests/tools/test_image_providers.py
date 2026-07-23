from __future__ import annotations

import base64
import builtins
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import jsonschema
import pytest

from lib.scoring import ProviderScore
from tools.base_tool import ToolResult, ToolStatus
from tools.graphics.atlascloud_image import AtlasCloudImage
from tools.graphics.flux_image import FluxImage
from tools.graphics.google_imagen import GoogleImagen
from tools.graphics.grok_image import GrokImage
from tools.graphics.image_gen import ImageGen
from tools.graphics.image_selector import ImageSelector
from tools.graphics.local_diffusion import LocalDiffusion
from tools.graphics.openai_image import OpenAIImage
from tools.graphics.pexels_image import PexelsImage
from tools.graphics.pixabay_image import PixabayImage
from tools.graphics.recraft_image import RecraftImage
from tools.graphics.wanx_image import WanxImage


class _FakeImageProvider:
    def __init__(
        self,
        name: str,
        provider: str,
        props: dict[str, object] | None = None,
        supports: dict[str, object] | None = None,
    ) -> None:
        self.name = name
        self.provider = provider
        self.best_for: list[str] = []
        self.agent_skills: list[str] = []
        self.input_schema = {"properties": props or {"prompt": {"type": "string"}}}
        self.supports = supports or {}
        self.calls: list[dict[str, object]] = []

    def get_status(self) -> ToolStatus:
        return ToolStatus.AVAILABLE

    def get_info(self) -> dict[str, object]:
        return {
            "name": self.name,
            "provider": self.provider,
            "agent_skills": self.agent_skills,
            "usage_location": __file__,
            "best_for": self.best_for,
            "supports": self.supports,
        }

    def estimate_cost(self, _inputs: dict[str, object]) -> float:
        return 0.0

    def execute(self, inputs: dict[str, object]) -> ToolResult:
        self.calls.append(dict(inputs))
        return ToolResult(success=True, data={"output": "fake.png"})


def _rank_as(*providers: _FakeImageProvider):
    return [
        ProviderScore(tool_name=tool.name, provider=tool.provider, task_fit=1.0 - idx / 10)
        for idx, tool in enumerate(providers)
    ]


def test_image_selector_allows_concrete_tool_names_in_normal_selection(monkeypatch):
    selector = ImageSelector()
    allowed = _FakeImageProvider("wanx_image", "bailian")
    blocked = _FakeImageProvider("flux_image", "flux")

    monkeypatch.setattr("lib.scoring.rank_providers", lambda _candidates, _ctx: _rank_as(allowed))

    selected, score = selector._select_best_tool(
        {"prompt": "product key visual", "allowed_providers": ["wanx_image"]},
        [allowed, blocked],
        selector._prepare_task_context({"prompt": "product key visual"}),
    )

    assert selected is allowed
    assert score.tool_name == "wanx_image"


def test_image_selector_does_not_drop_edit_request_when_no_edit_provider(monkeypatch):
    selector = ImageSelector()
    plain = _FakeImageProvider("plain_image", "plain")
    monkeypatch.setattr(selector, "_providers", lambda: [plain])
    monkeypatch.setattr("lib.scoring.rank_providers", lambda candidates, _ctx: _rank_as(*candidates))

    result = selector.execute(
        {
            "prompt": "Keep the product and replace the background",
            "generation_mode": "edit",
            "image_url": "https://example.test/product.png",
            "allowed_providers": ["plain"],
            "output_path": "projects/demo/assets/images/edited.png",
        }
    )

    assert not result.success
    assert "edit" in (result.error or "").lower()
    assert plain.calls == []


def test_image_selector_preserves_primary_image_for_multi_reference_edits(monkeypatch):
    selector = ImageSelector()
    edit_provider = _FakeImageProvider(
        "wanx_image",
        "bailian",
        props={
            "prompt": {"type": "string"},
            "operation": {"type": "string"},
            "ref_images": {"type": "array"},
        },
        supports={"image_edit": True, "multiple_reference_images": True},
    )
    monkeypatch.setattr(selector, "_providers", lambda: [edit_provider])
    monkeypatch.setattr("lib.scoring.rank_providers", lambda candidates, _ctx: _rank_as(*candidates))

    result = selector.execute(
        {
            "prompt": "Combine the product and style references",
            "generation_mode": "edit",
            "image_url": "https://example.test/product.png",
            "image_urls": ["https://example.test/style.png"],
            "allowed_providers": ["bailian"],
            "output_path": "projects/demo/assets/images/composite.png",
        }
    )

    assert result.success
    assert edit_provider.calls[0]["operation"] == "multi_image_reference"
    assert edit_provider.calls[0]["ref_images"] == [
        "https://example.test/product.png",
        "https://example.test/style.png",
    ]


def test_wanx_rejects_unknown_operation_before_network(monkeypatch):
    monkeypatch.setenv("DASHSCOPE_API_KEY", "test-key")
    calls: list[object] = []

    def fake_post(*args: object, **kwargs: object) -> object:
        calls.append((args, kwargs))
        raise AssertionError("network should not be called for unsupported operations")

    monkeypatch.setattr("requests.post", fake_post)

    result = WanxImage().execute({"prompt": "product hero", "operation": "not_real"})

    assert not result.success
    assert "Unsupported operation" in (result.error or "")
    assert calls == []


def test_grok_rejects_unknown_generation_mode_before_network(monkeypatch):
    monkeypatch.setenv("XAI_API_KEY", "test-key")
    calls: list[object] = []

    def fake_post(*args: object, **kwargs: object) -> object:
        calls.append((args, kwargs))
        raise AssertionError("network should not be called for unsupported generation modes")

    monkeypatch.setattr("requests.post", fake_post)

    result = GrokImage().execute({"prompt": "product hero", "generation_mode": "not_real"})

    assert not result.success
    assert "Unsupported generation_mode" in (result.error or "")
    assert calls == []


@pytest.mark.parametrize(
    "inputs",
    [
        {"prompt": "product hero image"},
        {"prompt": "product hero image", "output_path": "grok_image.png"},
        {"prompt": "product hero image", "output_path": "/tmp/grok_image.png"},
    ],
)
def test_grok_requires_project_output_path_before_network(
    inputs: dict[str, object],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("XAI_API_KEY", "test-key")
    calls: list[object] = []

    def fake_post(*args: object, **kwargs: object) -> object:
        calls.append((args, kwargs))
        raise AssertionError("network should not be called for invalid output_path")

    monkeypatch.setattr("requests.post", fake_post)

    result = GrokImage().execute(inputs)

    assert not result.success
    assert "output_path" in (result.error or "")
    assert "projects/<project-name>/" in (result.error or "")
    assert calls == []


@pytest.mark.parametrize(
    "inputs",
    [
        {"prompt": "product hero image"},
        {"prompt": "product hero image", "output_path": "wanx_image.png"},
        {"prompt": "product hero image", "output_path": "/tmp/wanx_image.png"},
    ],
)
def test_wanx_requires_project_output_path_before_network(
    inputs: dict[str, object],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DASHSCOPE_API_KEY", "test-key")
    calls: list[object] = []

    def fake_post(*args: object, **kwargs: object) -> object:
        calls.append((args, kwargs))
        raise AssertionError("network should not be called for invalid output_path")

    monkeypatch.setattr("requests.post", fake_post)

    result = WanxImage().execute(inputs)

    assert not result.success
    assert "output_path" in (result.error or "")
    assert "projects/<project-name>/" in (result.error or "")
    assert calls == []


@pytest.mark.parametrize(
    ("tool", "inputs", "env_vars"),
    [
        (FluxImage(), {"prompt": "product hero image", "output_path": "flux.png"}, ("FAL_KEY", "FAL_AI_API_KEY")),
        (
            AtlasCloudImage(),
            {"prompt": "product hero image", "output_path": "atlascloud.png"},
            ("ATLASCLOUD_API_KEY",),
        ),
        (GoogleImagen(), {"prompt": "product hero image", "output_path": "imagen.png"}, ("GOOGLE_API_KEY", "GEMINI_API_KEY")),
        (GrokImage(), {"prompt": "product hero image", "output_path": "grok.png"}, ("XAI_API_KEY",)),
        (OpenAIImage(), {"prompt": "product hero image", "output_path": "openai.png"}, ("OPENAI_API_KEY",)),
        (PexelsImage(), {"query": "product photography", "output_path": "pexels.jpg"}, ("PEXELS_API_KEY",)),
        (PixabayImage(), {"query": "product photography", "output_path": "pixabay.jpg"}, ("PIXABAY_API_KEY",)),
        (RecraftImage(), {"prompt": "product hero image", "output_path": "recraft.png"}, ("FAL_KEY", "FAL_AI_API_KEY")),
        (WanxImage(), {"prompt": "product hero image", "output_path": "wanx.png"}, ("DASHSCOPE_API_KEY",)),
    ],
)
def test_api_image_generators_reject_non_project_output_path_before_credentials(
    tool: Any,
    inputs: dict[str, object],
    env_vars: tuple[str, ...],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for env_var in env_vars:
        monkeypatch.delenv(env_var, raising=False)

    result = tool.execute(inputs)

    assert not result.success
    assert "output_path" in (result.error or "")
    assert "projects/<project-name>/" in (result.error or "")


def test_google_imagen_service_account_file_is_advertised_available(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    key_file = tmp_path / "service-account.json"
    key_file.write_text("{}", encoding="utf-8")
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", str(key_file))

    tool = GoogleImagen()
    assert tool.get_status() == ToolStatus.AVAILABLE
    info = tool.get_info()
    assert (
        info["input_schema"]["properties"]["model"]["default"]
        == "imagen-4.0-generate-001"
    )
    defaults = [
        option["id"]
        for option in info["model_options"]
        if option.get("default") is True
    ]
    assert defaults == ["imagen-4.0-generate-001"]
    model_ids = [option["id"] for option in info["model_options"]]
    assert model_ids == [
        "imagen-4.0-ultra-generate-001",
        "imagen-4.0-generate-001",
        "imagen-4.0-fast-generate-001",
    ]
    assert info["input_schema"]["properties"]["model"]["enum"] == model_ids


def test_google_imagen_service_account_default_uses_vertex_model(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    key_file = tmp_path / "service-account.json"
    key_file.write_text("{}", encoding="utf-8")
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", str(key_file))
    monkeypatch.setattr(
        "tools.graphics.google_imagen.get_access_token",
        lambda: ("test-token", "test-project"),
    )
    captured: dict[str, object] = {}

    def fake_post(*args: object, **kwargs: object) -> SimpleNamespace:
        captured["url"] = args[0]
        captured["headers"] = kwargs["headers"]
        captured["json"] = kwargs["json"]
        return SimpleNamespace(
            json=lambda: {"predictions": [{"bytesBase64Encoded": _image_bytes_b64()}]},
            raise_for_status=lambda: None,
        )

    monkeypatch.setattr("requests.post", fake_post)

    result = GoogleImagen().execute(
        {
            "prompt": "product hero image",
            "output_path": "projects/demo/assets/images/google-vertex.png",
        }
    )

    assert result.success
    assert result.data["model"] == "imagen-4.0-generate-001"
    assert "aiplatform.googleapis.com" in str(captured["url"])
    assert captured["json"] == {
        "instances": [{"prompt": "product hero image"}],
        "parameters": {"sampleCount": 1, "aspectRatio": "1:1"},
    }


def test_google_imagen_gemini_request_carries_image_parameters(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GOOGLE_API_KEY", "test-key")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    calls: list[dict[str, object]] = []

    def fake_post(*args: object, **kwargs: object) -> SimpleNamespace:
        calls.append(
            {
                "url": args[0],
                "headers": kwargs["headers"],
                "json": kwargs["json"],
            }
        )
        return SimpleNamespace(
            json=lambda: {
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {
                                    "inlineData": {
                                        "data": _image_bytes_b64(),
                                        "mimeType": "image/png",
                                    }
                                }
                            ]
                        }
                    }
                ]
            },
            raise_for_status=lambda: None,
        )

    monkeypatch.setattr("requests.post", fake_post)

    result = GoogleImagen().execute(
        {
            "prompt": "product hero image",
            "aspect_ratio": "16:9",
            "output_path": "projects/demo/assets/images/google-gemini.png",
        }
    )

    assert result.success
    assert result.data["images_generated"] == 1
    assert len(calls) == 1
    assert calls[0]["url"] == "https://generativelanguage.googleapis.com/v1beta/interactions"
    assert calls[0]["json"] == {
        "model": "gemini-3-pro-image",
        "input": "product hero image",
        "response_format": {
            "type": "image",
            "mime_type": "image/png",
            "aspect_ratio": "16:9",
        },
    }


def test_google_imagen_gemini_rejects_multiple_images_before_network(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GOOGLE_API_KEY", "test-key")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    def fail_post(*_args: object, **_kwargs: object) -> SimpleNamespace:
        raise AssertionError("Gemini multi-image validation should run before HTTP")

    monkeypatch.setattr("requests.post", fail_post)

    result = GoogleImagen().execute(
        {
            "prompt": "product hero image",
            "number_of_images": 2,
            "output_path": "projects/demo/assets/images/google-gemini.png",
        }
    )

    assert not result.success
    assert "number_of_images=1" in (result.error or "")


def test_google_imagen_gemini_interactions_steps_response_writes_image(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GOOGLE_API_KEY", "test-key")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    def fake_post(*_args: object, **_kwargs: object) -> SimpleNamespace:
        return SimpleNamespace(
            json=lambda: {
                "id": "interaction-1",
                "status": "completed",
                "steps": [
                    {
                        "type": "model_output",
                        "content": [
                            {
                                "type": "image",
                                "data": _image_bytes_b64(),
                                "mime_type": "image/png",
                            }
                        ],
                    }
                ],
                "object": "interaction",
                "model": "gemini-3-pro-image",
            },
            raise_for_status=lambda: None,
        )

    monkeypatch.setattr("requests.post", fake_post)

    output_path = "projects/demo/assets/images/google-gemini-steps.png"
    result = GoogleImagen().execute(
        {
            "prompt": "product hero image",
            "output_path": output_path,
        }
    )

    assert result.success, result.error
    assert result.data["images_generated"] == 1
    assert result.data["output_path"] == output_path
    assert (tmp_path / output_path).read_bytes() == b"png"


@pytest.mark.parametrize(
    ("tool", "env_var", "base"),
    [
        (
            PexelsImage(),
            "PEXELS_API_KEY",
            {"query": "product photography", "orientation": "landscape", "size": "large"},
        ),
        (
            PixabayImage(),
            "PIXABAY_API_KEY",
            {"query": "product photography", "image_type": "photo", "orientation": "horizontal"},
        ),
    ],
)
@pytest.mark.parametrize(
    "output_path",
    [
        None,
        "stock-image.jpg",
        "/tmp/stock-image.jpg",
    ],
)
def test_stock_image_requires_project_output_path_before_network(
    tool: Any,
    env_var: str,
    base: dict[str, object],
    output_path: str | None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(env_var, "test-key")
    calls: list[object] = []

    def fake_get(*args: object, **kwargs: object) -> object:
        calls.append((args, kwargs))
        raise AssertionError("network should not be called for invalid output_path")

    monkeypatch.setattr("requests.get", fake_get)

    inputs = dict(base)
    if output_path is not None:
        inputs["output_path"] = output_path

    result = tool.execute(inputs)

    assert not result.success
    assert "output_path" in (result.error or "")
    assert "projects/<project-name>/" in (result.error or "")
    assert calls == []


def test_wanx_multi_reference_rejects_missing_local_paths_before_network(monkeypatch):
    monkeypatch.setenv("DASHSCOPE_API_KEY", "test-key")
    calls: list[object] = []

    def fake_post(*args: object, **kwargs: object) -> object:
        calls.append((args, kwargs))
        raise AssertionError("network should not be called for missing reference files")

    monkeypatch.setattr("requests.post", fake_post)

    result = WanxImage().execute(
        {
            "prompt": "product hero",
            "operation": "multi_image_reference",
            "model": "wan2.7-image-pro",
            "ref_images": ["/tmp/does-not-exist-video-production-buddy.png"],
            "output_path": "projects/demo/assets/images/wanx-missing-ref.png",
        }
    )

    assert not result.success
    assert "not found" in (result.error or "").lower()
    assert calls == []


def test_local_diffusion_status_requires_torch_runtime_dependency(monkeypatch):
    real_import = builtins.__import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "diffusers":
            return object()
        if name == "torch":
            raise ImportError("No module named torch")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    assert LocalDiffusion().get_status() == ToolStatus.UNAVAILABLE


def test_legacy_image_gen_requires_project_output_path_before_client_creation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    calls: list[str] = []

    class FakeOpenAI:
        def __init__(self) -> None:
            calls.append("client")
            raise AssertionError("OpenAI client should not be created for invalid output_path")

    monkeypatch.setitem(sys.modules, "openai", type("OpenAIModule", (), {"OpenAI": FakeOpenAI})())

    result = ImageGen().execute({"prompt": "product hero image", "provider": "openai"})

    assert result.success is False
    assert "output_path" in (result.error or "")
    assert "projects/<project-name>/" in (result.error or "")
    assert calls == []


def test_local_diffusion_requires_project_output_path_before_dependency_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    def fake_status(self: LocalDiffusion) -> ToolStatus:
        calls.append("status")
        return ToolStatus.UNAVAILABLE

    monkeypatch.setattr(LocalDiffusion, "get_status", fake_status)

    result = LocalDiffusion().execute({"prompt": "product hero image"})

    assert result.success is False
    assert "output_path" in (result.error or "")
    assert "projects/<project-name>/" in (result.error or "")
    assert calls == []


def _image_bytes_b64() -> str:
    return base64.b64encode(b"png").decode("ascii")


@pytest.mark.parametrize(
    ("tool", "env_var", "fake_post"),
    [
        (
            FluxImage(),
            "FAL_KEY",
            lambda: SimpleNamespace(
                json=lambda: {"images": [{"url": "https://example.test/flux.png"}], "seed": 123},
                raise_for_status=lambda: None,
            ),
        ),
        (
            RecraftImage(),
            "FAL_KEY",
            lambda: SimpleNamespace(
                json=lambda: {"images": [{"url": "https://example.test/recraft.png"}]},
                raise_for_status=lambda: None,
            ),
        ),
        (
            GoogleImagen(),
            "GOOGLE_API_KEY",
            lambda: SimpleNamespace(
                json=lambda: {"predictions": [{"bytesBase64Encoded": _image_bytes_b64()}]},
                raise_for_status=lambda: None,
            ),
        ),
        (
            GrokImage(),
            "XAI_API_KEY",
            lambda: SimpleNamespace(
                json=lambda: {"data": [{"b64_json": _image_bytes_b64()}]},
                raise_for_status=lambda: None,
            ),
        ),
    ],
)
def test_api_image_success_payload_includes_output_path(
    tool: Any,
    env_var: str,
    fake_post: Any,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    output_path = f"projects/demo/assets/images/{tool.name}.png"

    monkeypatch.setenv(env_var, "test-key")
    monkeypatch.setattr("requests.post", lambda *args, **kwargs: fake_post())
    monkeypatch.setattr(
        "requests.get",
        lambda *args, **kwargs: SimpleNamespace(
            content=b"png",
            raise_for_status=lambda: None,
        ),
    )

    result = tool.execute({"prompt": "product hero image", "output_path": output_path})

    assert result.success
    assert result.data["output_path"] == output_path
    assert result.artifacts[0] == output_path


@pytest.mark.parametrize(
    ("tool", "env_var", "fake_post", "expected_properties"),
    [
        (
            FluxImage(),
            "FAL_KEY",
            lambda: SimpleNamespace(
                json=lambda: {
                    "images": [{"url": "https://example.test/flux.png"}],
                    "seed": 123,
                },
                raise_for_status=lambda: None,
            ),
            {"provider", "model", "prompt", "output", "output_path", "seed"},
        ),
        (
            RecraftImage(),
            "FAL_KEY",
            lambda: SimpleNamespace(
                json=lambda: {"images": [{"url": "https://example.test/recraft.png"}]},
                raise_for_status=lambda: None,
            ),
            {"provider", "model", "prompt", "output", "output_path"},
        ),
        (
            GoogleImagen(),
            "GOOGLE_API_KEY",
            lambda: SimpleNamespace(
                json=lambda: {
                    "predictions": [{"bytesBase64Encoded": _image_bytes_b64()}]
                },
                raise_for_status=lambda: None,
            ),
            {
                "provider",
                "model",
                "prompt",
                "aspect_ratio",
                "output",
                "output_path",
                "images_generated",
            },
        ),
        (
            GrokImage(),
            "XAI_API_KEY",
            lambda: SimpleNamespace(
                json=lambda: {"data": [{"b64_json": _image_bytes_b64()}]},
                raise_for_status=lambda: None,
            ),
            {
                "provider",
                "model",
                "prompt",
                "generation_mode",
                "output",
                "output_path",
                "outputs",
                "images_generated",
            },
        ),
    ],
)
def test_api_image_success_payload_matches_output_schema(
    tool: Any,
    env_var: str,
    fake_post: Any,
    expected_properties: set[str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    output_path = f"projects/demo/assets/images/{tool.name}-schema.png"

    monkeypatch.setenv(env_var, "test-key")
    monkeypatch.setattr("requests.post", lambda *args, **kwargs: fake_post())
    monkeypatch.setattr(
        "requests.get",
        lambda *args, **kwargs: SimpleNamespace(
            content=b"png",
            raise_for_status=lambda: None,
        ),
    )

    output_properties = tool.output_schema["properties"]
    assert expected_properties <= set(output_properties)

    result = tool.execute({"prompt": "product hero image", "output_path": output_path})

    assert result.success is True
    assert result.artifacts[0] == output_path
    jsonschema.validate(instance=result.data, schema=tool.output_schema)


def test_openai_image_success_payload_includes_output_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    output_path = "projects/demo/assets/images/openai.png"

    class FakeOpenAI:
        def __init__(self) -> None:
            self.images = SimpleNamespace(
                generate=lambda **kwargs: SimpleNamespace(
                    data=[SimpleNamespace(b64_json=_image_bytes_b64())]
                )
            )

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=FakeOpenAI))

    result = OpenAIImage().execute(
        {"prompt": "product hero image", "output_path": output_path}
    )

    assert result.success
    assert result.data["output_path"] == output_path
    assert result.artifacts == [output_path]


def test_openai_image_success_payload_matches_output_schema(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    output_path = "projects/demo/assets/images/openai-schema.png"

    class FakeOpenAI:
        def __init__(self) -> None:
            self.images = SimpleNamespace(
                generate=lambda **kwargs: SimpleNamespace(
                    data=[SimpleNamespace(b64_json=_image_bytes_b64())]
                )
            )

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=FakeOpenAI))

    output_properties = OpenAIImage.output_schema["properties"]
    assert {"provider", "model", "prompt", "output", "output_path"} <= set(
        output_properties
    )

    result = OpenAIImage().execute(
        {"prompt": "product hero image", "output_path": output_path}
    )

    assert result.success is True
    assert result.artifacts == [output_path]
    jsonschema.validate(instance=result.data, schema=OpenAIImage.output_schema)


def test_legacy_image_gen_success_payload_includes_output_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    output_path = "projects/demo/assets/images/legacy.png"

    class FakeOpenAI:
        def __init__(self) -> None:
            self.images = SimpleNamespace(
                generate=lambda **kwargs: SimpleNamespace(
                    data=[SimpleNamespace(b64_json=_image_bytes_b64())]
                )
            )

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=FakeOpenAI))

    result = ImageGen().execute(
        {
            "prompt": "product hero image",
            "provider": "openai",
            "output_path": output_path,
        }
    )

    assert result.success
    assert result.data["output_path"] == output_path
    assert result.artifacts == [output_path]


def test_legacy_image_gen_success_payload_matches_output_schema(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    output_path = "projects/demo/assets/images/legacy-schema.png"

    class FakeOpenAI:
        def __init__(self) -> None:
            self.images = SimpleNamespace(
                generate=lambda **kwargs: SimpleNamespace(
                    data=[SimpleNamespace(b64_json=_image_bytes_b64())]
                )
            )

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=FakeOpenAI))

    output_properties = ImageGen.output_schema["properties"]
    assert {"provider", "prompt", "output", "output_path", "model", "seed"} <= set(
        output_properties
    )

    result = ImageGen().execute(
        {
            "prompt": "product hero image",
            "provider": "openai",
            "output_path": output_path,
        }
    )

    assert result.success is True
    assert result.artifacts == [output_path]
    jsonschema.validate(instance=result.data, schema=ImageGen.output_schema)


def test_local_diffusion_success_payload_includes_output_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    output_path = "projects/demo/assets/images/local.png"

    class FakeImage:
        def save(self, path: str) -> None:
            Path(path).write_bytes(b"png")

    class FakePipeline:
        @classmethod
        def from_pretrained(cls, *args: object, **kwargs: object) -> "FakePipeline":
            return cls()

        def to(self, device: str) -> "FakePipeline":
            return self

        def __call__(self, *args: object, **kwargs: object) -> SimpleNamespace:
            return SimpleNamespace(images=[FakeImage()])

    fake_torch = SimpleNamespace(
        float16=object(),
        float32=object(),
        cuda=SimpleNamespace(is_available=lambda: False),
        Generator=lambda device=None: SimpleNamespace(
            manual_seed=lambda seed: SimpleNamespace(seed=seed)
        ),
    )

    monkeypatch.setattr(LocalDiffusion, "get_status", lambda self: ToolStatus.AVAILABLE)
    monkeypatch.setitem(sys.modules, "torch", fake_torch)
    monkeypatch.setitem(
        sys.modules,
        "diffusers",
        SimpleNamespace(StableDiffusionPipeline=FakePipeline),
    )

    result = LocalDiffusion().execute(
        {"prompt": "product hero image", "output_path": output_path}
    )

    assert result.success
    assert result.data["output_path"] == output_path
    assert result.artifacts == [output_path]


def test_local_diffusion_success_payload_matches_output_schema(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    output_path = "projects/demo/assets/images/local-schema.png"

    class FakeImage:
        def save(self, path: str) -> None:
            Path(path).write_bytes(b"png")

    class FakePipeline:
        @classmethod
        def from_pretrained(cls, *args: object, **kwargs: object) -> "FakePipeline":
            return cls()

        def to(self, device: str) -> "FakePipeline":
            return self

        def __call__(self, *args: object, **kwargs: object) -> SimpleNamespace:
            return SimpleNamespace(images=[FakeImage()])

    fake_torch = SimpleNamespace(
        float16=object(),
        float32=object(),
        cuda=SimpleNamespace(is_available=lambda: False),
        Generator=lambda device=None: SimpleNamespace(
            manual_seed=lambda seed: SimpleNamespace(seed=seed)
        ),
    )

    monkeypatch.setattr(LocalDiffusion, "get_status", lambda self: ToolStatus.AVAILABLE)
    monkeypatch.setitem(sys.modules, "torch", fake_torch)
    monkeypatch.setitem(
        sys.modules,
        "diffusers",
        SimpleNamespace(StableDiffusionPipeline=FakePipeline),
    )

    output_properties = LocalDiffusion.output_schema["properties"]
    assert {"provider", "model", "prompt", "output", "output_path"} <= set(
        output_properties
    )

    result = LocalDiffusion().execute(
        {"prompt": "product hero image", "output_path": output_path}
    )

    assert result.success is True
    assert result.artifacts == [output_path]
    jsonschema.validate(instance=result.data, schema=LocalDiffusion.output_schema)


@pytest.mark.parametrize(
    ("tool", "env_var", "search_payload"),
    [
        (
            PexelsImage(),
            "PEXELS_API_KEY",
            {
                "photos": [
                    {
                        "id": 101,
                        "src": {"large2x": "https://example.test/pexels.jpg"},
                        "photographer": "Author",
                        "width": 1280,
                        "height": 720,
                    }
                ],
                "total_results": 1,
            },
        ),
        (
            PixabayImage(),
            "PIXABAY_API_KEY",
            {
                "hits": [
                    {
                        "id": 202,
                        "largeImageURL": "https://example.test/pixabay.jpg",
                        "user": "Author",
                        "imageWidth": 1280,
                        "imageHeight": 720,
                    }
                ],
                "total": 1,
            },
        ),
    ],
)
def test_stock_image_success_payload_includes_output_path(
    tool: Any,
    env_var: str,
    search_payload: dict[str, object],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    output_path = f"projects/demo/assets/images/{tool.name}.jpg"
    calls = 0

    def fake_get(*args: object, **kwargs: object) -> SimpleNamespace:
        nonlocal calls
        calls += 1
        if calls == 1:
            return SimpleNamespace(
                json=lambda: search_payload,
                raise_for_status=lambda: None,
            )
        return SimpleNamespace(content=b"jpg", raise_for_status=lambda: None)

    monkeypatch.setenv(env_var, "test-key")
    monkeypatch.setattr("requests.get", fake_get)

    result = tool.execute({"query": "product photography", "output_path": output_path})

    assert result.success
    assert result.data["output_path"] == output_path
    assert result.artifacts == [output_path]


@pytest.mark.parametrize(
    ("tool", "env_var", "search_payload", "expected_properties"),
    [
        (
            PexelsImage(),
            "PEXELS_API_KEY",
            {
                "photos": [
                    {
                        "id": 101,
                        "src": {"large2x": "https://example.test/pexels.jpg"},
                        "photographer": "Author",
                        "photographer_url": "https://example.test/author",
                        "alt": "Product on a desk",
                        "width": 1280,
                        "height": 720,
                        "url": "https://example.test/photo",
                    }
                ],
                "total_results": 1,
            },
            {
                "provider",
                "photo_id",
                "photographer",
                "photographer_url",
                "alt",
                "width",
                "height",
                "query",
                "output",
                "output_path",
                "total_results",
                "results_returned",
                "license",
                "pexels_url",
            },
        ),
        (
            PixabayImage(),
            "PIXABAY_API_KEY",
            {
                "hits": [
                    {
                        "id": 202,
                        "largeImageURL": "https://example.test/pixabay.jpg",
                        "user": "Author",
                        "tags": "product, desk",
                        "imageWidth": 1280,
                        "imageHeight": 720,
                        "pageURL": "https://example.test/photo",
                    }
                ],
                "total": 1,
            },
            {
                "provider",
                "image_id",
                "user",
                "tags",
                "image_width",
                "image_height",
                "query",
                "output",
                "output_path",
                "total_results",
                "results_returned",
                "license",
                "page_url",
            },
        ),
    ],
)
def test_stock_image_success_payload_matches_output_schema(
    tool: Any,
    env_var: str,
    search_payload: dict[str, object],
    expected_properties: set[str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    output_path = f"projects/demo/assets/images/{tool.name}-schema.jpg"
    calls = 0

    def fake_get(*args: object, **kwargs: object) -> SimpleNamespace:
        nonlocal calls
        calls += 1
        if calls == 1:
            return SimpleNamespace(
                json=lambda: search_payload,
                raise_for_status=lambda: None,
            )
        return SimpleNamespace(content=b"jpg", raise_for_status=lambda: None)

    monkeypatch.setenv(env_var, "test-key")
    monkeypatch.setattr("requests.get", fake_get)

    output_properties = tool.output_schema["properties"]
    assert expected_properties <= set(output_properties)

    result = tool.execute({"query": "product photography", "output_path": output_path})

    assert result.success is True
    assert (tmp_path / output_path).read_bytes() == b"jpg"
    assert result.artifacts == [output_path]
    jsonschema.validate(instance=result.data, schema=tool.output_schema)


def test_wanx_success_payload_includes_output_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    output_path = "projects/demo/assets/images/wanx.png"

    monkeypatch.setenv("DASHSCOPE_API_KEY", "test-key")
    monkeypatch.setenv("DASHSCOPE_WORKSPACE_ID", "ws-test")
    monkeypatch.setenv("DASHSCOPE_REGION", "ap-southeast-1")
    captured: dict[str, object] = {}

    def fake_post(*args, **kwargs):
        captured["url"] = args[0]
        captured["headers"] = kwargs["headers"]
        captured["json"] = kwargs["json"]
        return SimpleNamespace(
            json=lambda: {
                "output": {
                    "choices": [
                        {
                            "message": {
                                "content": [
                                    {"image": "https://example.test/wanx.png"}
                                ]
                            }
                        }
                    ],
                    "seed": 123,
                }
            },
            raise_for_status=lambda: None,
        )

    monkeypatch.setattr("requests.post", fake_post)

    def fake_download(
        self: WanxImage,
        results: list[dict[str, object]],
        base_output_path: str,
        model: str,
    ) -> list[str]:
        path = Path(base_output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"png")
        return [str(path)]

    monkeypatch.setattr(WanxImage, "_download_images", fake_download)

    result = WanxImage().execute({"prompt": "product hero", "output_path": output_path})

    assert result.success
    assert result.data["output_path"] == output_path
    assert result.artifacts == [output_path]
    assert captured["url"] == (
        "https://ws-test.ap-southeast-1.maas.aliyuncs.com"
        "/api/v1/services/aigc/multimodal-generation/generation"
    )
    assert "X-DashScope-Async" not in captured["headers"]
    assert captured["json"]["model"] == "qwen-image-2.0-pro"


def test_wanx_explicit_qwen_requires_workspace_endpoint_before_network(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DASHSCOPE_API_KEY", "test-key")
    for env_var in (
        "DASHSCOPE_WORKSPACE_ID",
        "BAILIAN_WORKSPACE_ID",
        "DASHSCOPE_QWEN_IMAGE_ENDPOINT",
        "BAILIAN_QWEN_IMAGE_ENDPOINT",
        "DASHSCOPE_QWEN_IMAGE_BASE_URL",
        "DASHSCOPE_BASE_HTTP_API_URL",
        "BAILIAN_BASE_HTTP_API_URL",
    ):
        monkeypatch.delenv(env_var, raising=False)
    calls: list[object] = []

    def fake_post(*args: object, **kwargs: object) -> object:
        calls.append((args, kwargs))
        raise AssertionError("network should not be called without Qwen workspace")

    monkeypatch.setattr("requests.post", fake_post)

    result = WanxImage().execute(
        {
            "prompt": "product hero",
            "model": "qwen-image-2.0-pro",
            "output_path": "projects/demo/assets/images/wanx.png",
        }
    )

    assert not result.success
    assert "DASHSCOPE_WORKSPACE_ID" in (result.error or "")
    assert calls == []


def test_wanx_key_only_default_uses_wan27_endpoint(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    output_path = "projects/demo/assets/images/wanx-key-only.png"
    monkeypatch.setenv("DASHSCOPE_API_KEY", "test-key")
    for env_var in (
        "DASHSCOPE_WORKSPACE_ID",
        "BAILIAN_WORKSPACE_ID",
        "DASHSCOPE_QWEN_IMAGE_ENDPOINT",
        "BAILIAN_QWEN_IMAGE_ENDPOINT",
        "DASHSCOPE_QWEN_IMAGE_BASE_URL",
        "DASHSCOPE_BASE_HTTP_API_URL",
        "BAILIAN_BASE_HTTP_API_URL",
    ):
        monkeypatch.delenv(env_var, raising=False)
    captured: dict[str, object] = {}

    def fake_post(*args: object, **kwargs: object) -> SimpleNamespace:
        captured["url"] = args[0]
        captured["headers"] = kwargs["headers"]
        captured["json"] = kwargs["json"]
        return SimpleNamespace(
            json=lambda: {"output": {"task_id": "task-1"}},
            raise_for_status=lambda: None,
        )

    monkeypatch.setattr("requests.post", fake_post)
    monkeypatch.setattr(
        WanxImage,
        "_poll_task",
        lambda self, task_id, api_key, api_style: (
            "SUCCEEDED",
            [{"url": "https://example.test/wanx.png", "seed": 123}],
        ),
    )

    def fake_download(
        self: WanxImage,
        results: list[dict[str, object]],
        base_output_path: str,
        model: str,
    ) -> list[str]:
        path = Path(base_output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"png")
        return [str(path)]

    monkeypatch.setattr(WanxImage, "_download_images", fake_download)

    result = WanxImage().execute({"prompt": "product hero", "output_path": output_path})

    assert result.success
    assert result.data["model"] == "wan2.7-image-pro"
    assert captured["url"].endswith("/services/aigc/image-generation/generation")
    assert captured["json"]["model"] == "wan2.7-image-pro"


def test_wanx_success_payload_matches_output_schema(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    output_path = "projects/demo/assets/images/wanx-schema.png"

    monkeypatch.setenv("DASHSCOPE_API_KEY", "test-key")
    monkeypatch.setenv("DASHSCOPE_WORKSPACE_ID", "ws-test")
    monkeypatch.setattr(
        "requests.post",
        lambda *args, **kwargs: SimpleNamespace(
            json=lambda: {
                "output": {
                    "choices": [
                        {
                            "message": {
                                "content": [
                                    {"image": "https://example.test/wanx.png"}
                                ]
                            }
                        }
                    ],
                    "seed": 123,
                }
            },
            raise_for_status=lambda: None,
        ),
    )

    def fake_download(
        self: WanxImage,
        results: list[dict[str, object]],
        base_output_path: str,
        model: str,
    ) -> list[str]:
        path = Path(base_output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"png")
        return [str(path)]

    monkeypatch.setattr(WanxImage, "_download_images", fake_download)

    output_properties = WanxImage.output_schema["properties"]
    assert {
        "provider",
        "model",
        "model_name",
        "operation",
        "prompt",
        "size",
        "n",
        "output",
        "output_path",
        "outputs",
        "seed",
    } <= set(output_properties)

    result = WanxImage().execute({"prompt": "product hero", "output_path": output_path})

    assert result.success is True
    assert result.artifacts == [output_path]
    jsonschema.validate(instance=result.data, schema=WanxImage.output_schema)


@pytest.mark.parametrize(
    "tool_cls",
    [
        FluxImage,
        GoogleImagen,
        GrokImage,
        ImageGen,
        LocalDiffusion,
        OpenAIImage,
        RecraftImage,
        WanxImage,
    ],
)
def test_legacy_image_generator_schemas_require_output_path(
    tool_cls: type[Any],
) -> None:
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(
            instance={"prompt": "product hero image"},
            schema=tool_cls.input_schema,
        )


@pytest.mark.parametrize(
    "tool_cls",
    [PexelsImage, PixabayImage],
)
def test_stock_image_schemas_require_output_path(tool_cls: type[Any]) -> None:
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(
            instance={"query": "product photography"},
            schema=tool_cls.input_schema,
        )


@pytest.mark.parametrize(
    ("tool", "base", "variant"),
    [
        (
            FluxImage(),
            {"prompt": "hero", "width": 1024, "height": 1024, "model": "flux-pro/v1.1"},
            {"output_path": "flux-a.png"},
        ),
        (
            FluxImage(),
            {"prompt": "hero", "width": 1024, "height": 1024, "model": "flux-pro/v1.1"},
            {"negative_prompt": "text artifacts"},
        ),
        (
            GoogleImagen(),
            {"prompt": "hero", "model": "imagen-4.0-generate-001"},
            {"output_path": "imagen-a.png"},
        ),
        (
            GoogleImagen(),
            {"prompt": "hero", "model": "imagen-4.0-generate-001"},
            {"width": 1344, "height": 768},
        ),
        (
            GrokImage(),
            {"prompt": "hero", "generation_mode": "edit", "model": "grok-imagine-image"},
            {"output_path": "grok-a.png"},
        ),
        (
            GrokImage(),
            {"prompt": "hero", "generation_mode": "edit", "model": "grok-imagine-image"},
            {"image_url": "https://example.test/product-a.png"},
        ),
        (
            ImageGen(),
            {"prompt": "hero", "width": 1024, "height": 1024, "provider": "openai"},
            {"output_path": "imagegen-a.png"},
        ),
        (
            ImageGen(),
            {"prompt": "hero", "width": 1024, "height": 1024, "provider": "openai"},
            {"negative_prompt": "text artifacts"},
        ),
        (
            LocalDiffusion(),
            {"prompt": "hero", "width": 512, "height": 512, "model": "sd"},
            {"output_path": "local-diffusion-a.png"},
        ),
        (
            LocalDiffusion(),
            {"prompt": "hero", "width": 512, "height": 512, "model": "sd"},
            {"guidance_scale": 9.0},
        ),
        (
            OpenAIImage(),
            {"prompt": "hero", "model": "gpt-image-1", "size": "1024x1024", "quality": "high"},
            {"output_path": "openai-image-a.png"},
        ),
        (
            OpenAIImage(),
            {"prompt": "hero", "model": "gpt-image-1", "size": "1024x1024", "quality": "high"},
            {"n": 2},
        ),
        (
            PexelsImage(),
            {"query": "city", "orientation": "landscape", "size": "large", "page": 1},
            {"output_path": "pexels-a.jpg"},
        ),
        (
            PexelsImage(),
            {"query": "city", "orientation": "landscape", "size": "large", "page": 1},
            {"download_size": "medium"},
        ),
        (
            PixabayImage(),
            {"query": "city", "image_type": "photo", "orientation": "horizontal", "page": 1},
            {"output_path": "pixabay-a.jpg"},
        ),
        (
            PixabayImage(),
            {"query": "city", "image_type": "photo", "orientation": "horizontal", "page": 1},
            {"colors": "blue"},
        ),
        (
            RecraftImage(),
            {"prompt": "logo", "model": "v4", "style": "icon", "image_size": "square"},
            {"output_path": "recraft-a.png"},
        ),
        (
            RecraftImage(),
            {"prompt": "logo", "model": "v4", "style": "icon", "image_size": "square"},
            {"colors": ["#ff0000", "#0000ff"]},
        ),
        (
            WanxImage(),
            {
                "prompt": "hero",
                "model": "wan2.7-image-pro",
                "operation": "multi_image_reference",
                "size": "1024*1024",
                "n": 1,
            },
            {"ref_images": ["https://example.test/product-a.png"]},
        ),
        (
            WanxImage(),
            {
                "prompt": "hero",
                "model": "wan2.7-image-pro",
                "operation": "text_to_image",
                "size": "1024*1024",
                "n": 1,
            },
            {"output_path": "wanx-a.png"},
        ),
    ],
)
def test_image_provider_idempotency_keys_include_asset_shaping_inputs(
    tool: Any,
    base: dict[str, object],
    variant: dict[str, object],
):
    assert tool.idempotency_key(base) != tool.idempotency_key({**base, **variant})
