from __future__ import annotations

import builtins
from typing import Any

import pytest

from lib.scoring import ProviderScore
from tools.base_tool import ToolResult, ToolStatus
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
