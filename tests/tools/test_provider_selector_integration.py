from __future__ import annotations

from pathlib import Path

import jsonschema
import pytest

from lib.config_model import (
    VideoProductionBuddyConfig,
)
from tools.base_tool import ToolResult
from lib.scoring import ProviderScore
from tools.audio.openai_tts import OpenAITTS
from tools.audio.tts_selector import TTSSelector
from tools.graphics.image_selector import ImageSelector
from tools.graphics.wanx_image import WanxImage
from tools.tool_registry import registry
from tools.video.video_selector import VideoSelector
from tools.video.wan_video_api import WanVideoAPI


class _AvailableProviderTool:
    def __init__(self, name: str, provider: str = "same-provider") -> None:
        self.name = name
        self.provider = provider
        self.best_for = []
        self.agent_skills = []
        self.input_schema = {"properties": {"prompt": {"type": "string"}}}
        self.supports = {}
        self.model_options: list[dict[str, object]] = []
        self.calls: list[dict[str, object]] = []
        self.cost_calls: list[dict[str, object]] = []
        self.runtime_calls: list[dict[str, object]] = []

    def get_status(self):
        from tools.base_tool import ToolStatus

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

    def execute(self, inputs: dict[str, object]) -> ToolResult:
        self.calls.append(dict(inputs))
        return ToolResult(success=True, data={"inputs": inputs})

    def estimate_cost(self, inputs: dict[str, object]) -> float:
        self.cost_calls.append(dict(inputs))
        model = inputs.get("model") or inputs.get("model_variant")
        return 4.5 if model == "gen4.5" else 0.1

    def estimate_runtime(self, inputs: dict[str, object]) -> float:
        self.runtime_calls.append(dict(inputs))
        model = inputs.get("model") or inputs.get("model_variant")
        return 45.0 if model == "gen4.5" else 10.0


class _BrokenStatusProviderTool(_AvailableProviderTool):
    def get_status(self):
        raise RuntimeError(f"{self.name} status backend unavailable")


def _component_has_skill_source(component) -> bool:
    if component.source_type == "local":
        return (component.source_path / "SKILL.md").exists()
    return bool(component.url)


def test_selector_schemas_require_output_path_for_generation_but_not_rank() -> None:
    cases = [
        (TTSSelector(), {"text": "Narration line."}),
        (ImageSelector(), {"prompt": "Product key visual"}),
        (VideoSelector(), {"prompt": "Product launch shot"}),
    ]

    for selector, generation_inputs in cases:
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(instance=generation_inputs, schema=selector.input_schema)

        rank_inputs = {**generation_inputs, "operation": "rank"}
        jsonschema.validate(instance=rank_inputs, schema=selector.input_schema)


def test_selector_schemas_expose_model_override_fields() -> None:
    assert "model_variant" in VideoSelector().input_schema["properties"]
    assert "model" in ImageSelector().input_schema["properties"]
    assert "model_id" in TTSSelector().input_schema["properties"]


def test_image_selector_maps_edit_inputs_to_wanx_contract(monkeypatch, tmp_path):
    monkeypatch.setenv("DASHSCOPE_API_KEY", "test-key")
    registry.clear()
    registry.discover()
    assert registry.get("wanx_image").get_status().value == "available"
    source = tmp_path / "source.png"
    source.write_bytes(b"not-a-real-png")
    captured: dict[str, object] = {}

    def fake_execute(self: WanxImage, inputs: dict[str, object]) -> ToolResult:
        captured.update(inputs)
        return ToolResult(success=True, data={"output": "ok.png"})

    monkeypatch.setattr(WanxImage, "execute", fake_execute)

    result = ImageSelector().execute(
        {
            "prompt": "Keep the product, change the background",
            "generation_mode": "edit",
            "image_path": str(source),
            "preferred_provider": "bailian",
            "allowed_providers": ["bailian"],
            "output_path": "projects/demo/assets/images/edited-product.png",
        }
    )

    assert result.success
    assert captured["operation"] == "image_editing"
    assert captured["base_image_path"] == str(source)
    assert captured["output_path"] == "projects/demo/assets/images/edited-product.png"


def test_video_selector_passes_local_reference_path_to_wan_api_without_fal_upload(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("DASHSCOPE_API_KEY", "test-key")
    registry.clear()
    registry.discover()
    assert registry.get("wan_video_api").get_status().value == "available"
    source = tmp_path / "frame.png"
    source.write_bytes(b"not-a-real-png")
    captured: dict[str, object] = {}

    def fail_upload(_path: str) -> str:
        raise AssertionError("Bailian accepts local image_path; fal upload is wrong")

    def fake_execute(self: WanVideoAPI, inputs: dict[str, object]) -> ToolResult:
        captured.update(inputs)
        return ToolResult(success=True, data={"output_path": "ok.mp4"})

    monkeypatch.setattr("tools.video._shared.upload_image_fal", fail_upload)
    monkeypatch.setattr(WanVideoAPI, "execute", fake_execute)

    result = VideoSelector().execute(
        {
            "prompt": "Animate the product frame",
            "operation": "image_to_video",
            "reference_image_path": str(source),
            "preferred_provider": "bailian",
            "allowed_providers": ["bailian"],
            "output_path": "projects/demo/assets/video/product-frame.mp4",
        }
    )

    assert result.success
    assert captured["image_path"] == str(source)
    assert captured["output_path"] == "projects/demo/assets/video/product-frame.mp4"


def test_video_selector_applies_env_model_preference(monkeypatch):
    selector = VideoSelector()
    provider = _AvailableProviderTool("video_provider", provider="selected")
    provider.input_schema = {
        "properties": {
            "prompt": {"type": "string"},
            "output_path": {"type": "string"},
            "model_variant": {"type": "string"},
        }
    }

    monkeypatch.setenv("VPB_VIDEO_GENERATION_PROVIDER", "selected")
    monkeypatch.setenv("VPB_VIDEO_GENERATION_MODEL", "fast")
    monkeypatch.setattr(selector, "_providers", lambda: [provider])
    monkeypatch.setattr(
        "lib.scoring.rank_providers",
        lambda candidates, _ctx: [
            ProviderScore(tool_name=tool.name, provider=tool.provider, task_fit=1.0)
            for tool in candidates
        ],
    )

    result = selector.execute(
        {
            "prompt": "Cinematic launch shot",
            "output_path": "projects/demo/assets/video/preferred.mp4",
        }
    )

    assert result.success
    assert provider.calls[0]["model_variant"] == "fast"
    assert provider.calls[0]["output_path"] == "projects/demo/assets/video/preferred.mp4"


def test_video_selector_env_provider_overrides_explicit_auto(monkeypatch):
    selector = VideoSelector()
    selected = _AvailableProviderTool("selected_video", provider="selected")
    fallback = _AvailableProviderTool("fallback_video", provider="fallback")

    monkeypatch.setenv("VPB_VIDEO_GENERATION_PROVIDER", "selected")
    monkeypatch.setattr(selector, "_providers", lambda: [selected, fallback])
    monkeypatch.setattr(
        "lib.scoring.rank_providers",
        lambda candidates, _ctx: [
            ProviderScore(tool_name="fallback_video", provider="fallback", task_fit=1.0),
            ProviderScore(tool_name="selected_video", provider="selected", task_fit=0.1),
        ],
    )

    result = selector.execute(
        {
            "prompt": "Cinematic launch shot",
            "preferred_provider": "auto",
            "output_path": "projects/demo/assets/video/preferred.mp4",
        }
    )

    assert result.success
    assert selected.calls
    assert not fallback.calls


def test_video_selector_explicit_provider_ignores_env_model_default(
    monkeypatch,
):
    selector = VideoSelector()
    runway = _AvailableProviderTool("runway_video", provider="runway")
    runway.input_schema = {
        "properties": {
            "prompt": {"type": "string"},
            "output_path": {"type": "string"},
            "model": {"type": "string"},
        }
    }
    runway.model_options = [
        {"id": "gen4.5", "field": "model", "default": False}
    ]
    seedance = _AvailableProviderTool("seedance_video", provider="seedance")
    seedance.model_options = [
        {"id": "standard", "field": "model_variant", "default": True}
    ]

    monkeypatch.setenv("VPB_VIDEO_GENERATION_ALLOWED_PROVIDERS", "seedance")
    monkeypatch.setenv("VPB_VIDEO_GENERATION_MODEL", "MiniMax-Hailuo-2.3")
    monkeypatch.setattr(selector, "_providers", lambda: [runway, seedance])
    monkeypatch.setattr(
        "lib.scoring.rank_providers",
        lambda candidates, _ctx: [
            ProviderScore(tool_name=tool.name, provider=tool.provider, task_fit=1.0)
            for tool in candidates
        ],
    )

    result = selector.execute(
        {
            "prompt": "Cinematic launch shot",
            "preferred_provider": "runway",
            "output_path": "projects/demo/assets/video/runway.mp4",
        }
    )

    assert result.success
    assert runway.calls
    assert "model" not in runway.calls[0]
    assert "preferred_provider" not in runway.calls[0]
    assert "allowed_providers" not in runway.calls[0]
    assert not seedance.calls
    assert result.data["selected_provider"] == "runway"


def test_video_selector_explicit_provider_honors_explicit_model_alias(monkeypatch):
    selector = VideoSelector()
    runway = _AvailableProviderTool("runway_video", provider="runway")
    runway.input_schema = {
        "properties": {
            "prompt": {"type": "string"},
            "output_path": {"type": "string"},
            "model": {"type": "string"},
        }
    }
    runway.model_options = [
        {"id": "gen4.5", "field": "model", "default": False}
    ]
    seedance = _AvailableProviderTool("seedance_video", provider="seedance")
    seedance.model_options = [
        {"id": "standard", "field": "model_variant", "default": True}
    ]

    monkeypatch.setenv("VPB_VIDEO_GENERATION_MODEL", "MiniMax-Hailuo-2.3")
    monkeypatch.setattr(selector, "_providers", lambda: [runway, seedance])
    monkeypatch.setattr(
        "lib.scoring.rank_providers",
        lambda candidates, _ctx: [
            ProviderScore(tool_name=tool.name, provider=tool.provider, task_fit=1.0)
            for tool in candidates
        ],
    )

    result = selector.execute(
        {
            "prompt": "Cinematic launch shot",
            "preferred_provider": "runway",
            "model": "gen4.5",
            "output_path": "projects/demo/assets/video/runway.mp4",
        }
    )

    assert result.success
    assert runway.calls[0]["model"] == "gen4.5"
    assert "model_variant" not in runway.calls[0]
    assert not seedance.calls


def test_video_selector_model_only_env_preference_filters_matching_provider(monkeypatch):
    selector = VideoSelector()
    selected = _AvailableProviderTool("selected_video", provider="selected")
    selected.input_schema = {
        "properties": {
            "prompt": {"type": "string"},
            "output_path": {"type": "string"},
            "model_variant": {"type": "string"},
        }
    }
    selected.model_options = [
        {"id": "fast", "field": "model_variant", "default": True}
    ]
    fallback = _AvailableProviderTool("fallback_video", provider="fallback")
    fallback.input_schema = selected.input_schema
    fallback.model_options = [
        {"id": "slow", "field": "model_variant", "default": True}
    ]

    monkeypatch.setenv("VPB_VIDEO_GENERATION_MODEL", "fast")
    monkeypatch.setattr(selector, "_providers", lambda: [selected, fallback])
    monkeypatch.setattr(
        "lib.scoring.rank_providers",
        lambda candidates, _ctx: [
            ProviderScore(tool_name="fallback_video", provider="fallback", task_fit=1.0),
            ProviderScore(tool_name="selected_video", provider="selected", task_fit=0.1),
        ],
    )

    result = selector.execute(
        {
            "prompt": "Cinematic launch shot",
            "output_path": "projects/demo/assets/video/preferred.mp4",
        }
    )

    assert result.success
    assert selected.calls[0]["model_variant"] == "fast"
    assert not fallback.calls


def test_video_selector_filters_explicit_model_alias_before_ranking(monkeypatch):
    selector = VideoSelector()
    selected = _AvailableProviderTool("runway_like", provider="runway")
    selected.input_schema = {
        "properties": {
            "prompt": {"type": "string"},
            "output_path": {"type": "string"},
            "model": {"type": "string"},
        }
    }
    selected.model_options = [
        {"id": "gen4.5", "field": "model", "default": False}
    ]
    fallback = _AvailableProviderTool("other_video", provider="fallback")
    fallback.input_schema = selected.input_schema
    fallback.model_options = [
        {"id": "seedance2", "field": "model", "default": True}
    ]

    monkeypatch.setattr(selector, "_providers", lambda: [selected, fallback])
    monkeypatch.setattr(
        "lib.scoring.rank_providers",
        lambda candidates, _ctx: [
            ProviderScore(tool_name=tool.name, provider=tool.provider, task_fit=1.0)
            for tool in candidates
        ],
    )

    result = selector.execute(
        {
            "prompt": "Cinematic launch shot",
            "model": "gen4.5",
            "output_path": "projects/demo/assets/video/runway.mp4",
        }
    )

    assert result.success
    assert selected.calls[0]["model"] == "gen4.5"
    assert "model_variant" not in selected.calls[0]
    assert not fallback.calls


def test_video_selector_estimates_with_provider_adapted_model_field(monkeypatch):
    selector = VideoSelector()
    selected = _AvailableProviderTool("runway_like", provider="runway")
    selected.input_schema = {
        "properties": {
            "prompt": {"type": "string"},
            "output_path": {"type": "string"},
            "model": {"type": "string"},
            "duration": {"type": "integer"},
        }
    }
    selected.model_options = [
        {"id": "gen4.5", "field": "model", "default": False}
    ]

    monkeypatch.setenv("VPB_VIDEO_GENERATION_MODEL", "gen4.5")
    monkeypatch.setattr(selector, "_providers", lambda: [selected])
    monkeypatch.setattr(
        "lib.scoring.rank_providers",
        lambda candidates, _ctx: [
            ProviderScore(tool_name=tool.name, provider=tool.provider, task_fit=1.0)
            for tool in candidates
        ],
    )

    assert selector.estimate_cost({"prompt": "Cinematic launch shot"}) == 4.5
    assert selector.estimate_runtime({"prompt": "Cinematic launch shot"}) == 45.0
    assert selected.cost_calls[0]["model"] == "gen4.5"
    assert "model_variant" not in selected.cost_calls[0]
    assert selected.runtime_calls[0]["model"] == "gen4.5"
    assert "model_variant" not in selected.runtime_calls[0]


def test_image_selector_explicit_model_beats_env_model_preference(monkeypatch):
    selector = ImageSelector()
    provider = _AvailableProviderTool("image_provider", provider="selected")
    provider.input_schema = {
        "properties": {
            "prompt": {"type": "string"},
            "output_path": {"type": "string"},
            "model": {"type": "string"},
        }
    }

    monkeypatch.setenv("VPB_IMAGE_GENERATION_PROVIDER", "selected")
    monkeypatch.setenv("VPB_IMAGE_GENERATION_MODEL", "configured-model")
    monkeypatch.setattr(selector, "_providers", lambda: [provider])
    monkeypatch.setattr(
        "lib.scoring.rank_providers",
        lambda candidates, _ctx: [
            ProviderScore(tool_name=tool.name, provider=tool.provider, task_fit=1.0)
            for tool in candidates
        ],
    )

    result = selector.execute(
        {
            "prompt": "Product key visual",
            "model": "explicit-model",
            "output_path": "projects/demo/assets/images/preferred.png",
        }
    )

    assert result.success
    assert provider.calls[0]["model"] == "explicit-model"


def test_image_selector_relaxes_env_text_to_image_model_for_edit_requests(monkeypatch):
    selector = ImageSelector()
    generation_only = _AvailableProviderTool("flux_image", provider="flux")
    generation_only.input_schema = {
        "properties": {
            "prompt": {"type": "string"},
            "model": {"type": "string"},
            "output_path": {"type": "string"},
        }
    }
    generation_only.model_options = [
        {"id": "flux-2-pro", "field": "model", "default": True}
    ]
    edit_provider = _AvailableProviderTool("wanx_image", provider="bailian")
    edit_provider.supports = {"image_edit": True}
    edit_provider.input_schema = {
        "properties": {
            "prompt": {"type": "string"},
            "operation": {"type": "string"},
            "base_image_path": {"type": "string"},
            "output_path": {"type": "string"},
        }
    }
    edit_provider.model_options = [
        {"id": "qwen-image-2.0-pro", "field": "model", "default": True}
    ]

    monkeypatch.setenv("VPB_IMAGE_GENERATION_MODEL", "flux-2-pro")
    monkeypatch.setattr(selector, "_providers", lambda: [generation_only, edit_provider])
    monkeypatch.setattr(
        "lib.scoring.rank_providers",
        lambda candidates, _ctx: [
            ProviderScore(tool_name=tool.name, provider=tool.provider, task_fit=1.0)
            for tool in candidates
        ],
    )

    result = selector.execute(
        {
            "prompt": "Keep the product, change the background",
            "generation_mode": "edit",
            "image_path": "projects/demo/reference_assets/product.png",
            "output_path": "projects/demo/assets/images/edited.png",
        }
    )

    assert result.success
    assert generation_only.calls == []
    assert edit_provider.calls[0]["operation"] == "image_editing"
    assert edit_provider.calls[0]["base_image_path"] == (
        "projects/demo/reference_assets/product.png"
    )
    assert "model" not in edit_provider.calls[0]


def test_video_selector_selects_highest_ranked_tool_when_provider_has_multiple_tools(monkeypatch):
    selector = VideoSelector()
    low = _AvailableProviderTool("low_ranked_tool")
    high = _AvailableProviderTool("high_ranked_tool")

    def fake_rank(_candidates, _task_context):
        return [
            ProviderScore(tool_name="high_ranked_tool", provider="same-provider", task_fit=1.0),
            ProviderScore(tool_name="low_ranked_tool", provider="same-provider", task_fit=0.1),
        ]

    monkeypatch.setattr("lib.scoring.rank_providers", fake_rank)

    selected, score = selector._select_best_tool(
        {"prompt": "cinematic product launch"},
        [low, high],
        selector._prepare_task_context({"prompt": "cinematic product launch"}),
    )

    assert selected is high
    assert score.tool_name == "high_ranked_tool"


def test_video_selector_allows_concrete_tool_names_in_normal_selection(monkeypatch):
    selector = VideoSelector()
    allowed = _AvailableProviderTool("seedance_video", provider="seedance")
    blocked = _AvailableProviderTool("seedance_replicate", provider="seedance")

    def fake_rank(candidates, _task_context):
        return [
            ProviderScore(tool_name=tool.name, provider=tool.provider, task_fit=1.0 - idx / 10)
            for idx, tool in enumerate(candidates)
        ]

    monkeypatch.setattr("lib.scoring.rank_providers", fake_rank)

    selected, score = selector._select_best_tool(
        {
            "prompt": "cinematic product launch",
            "allowed_providers": ["seedance_video"],
        },
        [allowed, blocked],
        selector._prepare_task_context({"prompt": "cinematic product launch"}),
    )

    assert selected is allowed
    assert score.tool_name == "seedance_video"


def test_image_selector_selects_highest_ranked_tool_when_provider_has_multiple_tools(monkeypatch):
    selector = ImageSelector()
    low = _AvailableProviderTool("low_ranked_image")
    high = _AvailableProviderTool("high_ranked_image")

    def fake_rank(_candidates, _task_context):
        return [
            ProviderScore(tool_name="high_ranked_image", provider="same-provider", task_fit=1.0),
            ProviderScore(tool_name="low_ranked_image", provider="same-provider", task_fit=0.1),
        ]

    monkeypatch.setattr("lib.scoring.rank_providers", fake_rank)

    selected, score = selector._select_best_tool(
        {"prompt": "product key visual"},
        [low, high],
        selector._prepare_task_context({"prompt": "product key visual"}),
    )

    assert selected is high
    assert score.tool_name == "high_ranked_image"


def test_tts_selector_selects_highest_ranked_tool_when_provider_has_multiple_tools(monkeypatch):
    selector = TTSSelector()
    low = _AvailableProviderTool("low_ranked_voice")
    high = _AvailableProviderTool("high_ranked_voice")

    def fake_rank(_candidates, _task_context):
        return [
            ProviderScore(tool_name="high_ranked_voice", provider="same-provider", task_fit=1.0),
            ProviderScore(tool_name="low_ranked_voice", provider="same-provider", task_fit=0.1),
        ]

    monkeypatch.setattr("lib.scoring.rank_providers", fake_rank)

    selected, score = selector._select_best_tool(
        {"text": "Narration"},
        [low, high],
        selector._prepare_task_context({"text": "Narration"}),
    )

    assert selected is high
    assert score.tool_name == "high_ranked_voice"


@pytest.mark.parametrize(
    ("selector", "artifact_key", "artifact_path"),
    [
        (
            ImageSelector(),
            "image",
            "projects/demo/assets/images/selector-image.png",
        ),
        (
            VideoSelector(),
            "video",
            "projects/demo/assets/video/selector-video.mp4",
        ),
    ],
)
def test_media_selector_generation_success_payload_matches_output_schema(
    selector,
    artifact_key: str,
    artifact_path: str,
    monkeypatch,
):
    provider = _AvailableProviderTool(f"{selector.name}_provider", provider="selected")
    provider.agent_skills = ["media-generation"]
    provider.best_for = [f"{artifact_key} generation"]
    provider.input_schema = {
        "properties": {
            "prompt": {"type": "string"},
            "output_path": {"type": "string"},
        }
    }

    def fake_execute(inputs: dict[str, object]) -> ToolResult:
        provider.calls.append(dict(inputs))
        return ToolResult(
            success=True,
            data={
                "provider": "selected",
                "output": artifact_path,
                "output_path": artifact_path,
            },
            artifacts=[artifact_path],
        )

    monkeypatch.setattr(provider, "execute", fake_execute)
    monkeypatch.setattr(selector, "_providers", lambda: [provider])
    monkeypatch.setattr(
        "lib.scoring.rank_providers",
        lambda candidates, _ctx: [
            ProviderScore(tool_name=tool.name, provider=tool.provider, task_fit=1.0)
            for tool in candidates
        ],
    )

    output_properties = selector.output_schema["properties"]
    assert {
        "output",
        "output_path",
        "selected_tool",
        "selected_provider",
        "selection_reason",
        "provider_score",
        "selected_tool_agent_skills",
        "required_agent_skills",
        "selected_tool_usage_location",
        "selected_tool_best_for",
        "alternatives_considered",
    } <= set(output_properties)

    result = selector.execute(
        {
            "prompt": f"Generate a {artifact_key} asset.",
            "preferred_provider": "selected",
            "allowed_providers": ["selected"],
            "output_path": artifact_path,
        }
    )

    assert result.success is True
    assert result.data["selected_tool"] == provider.name
    assert result.data["selected_provider"] == "selected"
    assert result.data["required_agent_skills"] == ["media-generation"]
    assert result.data["selected_tool_best_for"] == [f"{artifact_key} generation"]
    assert result.data["output_path"] == artifact_path
    assert result.artifacts == [artifact_path]
    jsonschema.validate(instance=result.data, schema=selector.output_schema)


@pytest.mark.parametrize(
    ("selector", "inputs"),
    [
        (ImageSelector(), {"prompt": "Product render", "operation": "rank"}),
        (VideoSelector(), {"prompt": "Product clip", "operation": "rank"}),
    ],
)
def test_media_selector_rank_success_payload_matches_output_schema(
    selector,
    inputs: dict[str, object],
    monkeypatch,
):
    provider = _AvailableProviderTool(f"{selector.name}_provider", provider="selected")
    monkeypatch.setattr(selector, "_providers", lambda: [provider])
    monkeypatch.setattr(
        "lib.scoring.rank_providers",
        lambda candidates, _ctx: [
            ProviderScore(tool_name=tool.name, provider=tool.provider, task_fit=1.0)
            for tool in candidates
        ],
    )

    output_properties = selector.output_schema["properties"]
    assert {
        "rankings",
        "explanation",
        "normalized_task_context",
    } <= set(output_properties)

    result = selector.execute(inputs)

    assert result.success is True
    assert result.data["rankings"][0]["tool_name"] == provider.name
    jsonschema.validate(instance=result.data, schema=selector.output_schema)


def test_selectors_skip_providers_when_status_check_fails(monkeypatch):
    selector_cases = [
        (VideoSelector(), {"prompt": "cinematic product launch"}),
        (ImageSelector(), {"prompt": "product key visual"}),
        (TTSSelector(), {"text": "Narration"}),
    ]

    for selector, inputs in selector_cases:
        broken = _BrokenStatusProviderTool(f"{selector.name}_broken")
        available = _AvailableProviderTool(f"{selector.name}_available")

        def fake_rank(candidates, _task_context):
            return [
                ProviderScore(tool_name=tool.name, provider=tool.provider, task_fit=1.0 - idx / 10)
                for idx, tool in enumerate(candidates)
            ]

        monkeypatch.setattr("lib.scoring.rank_providers", fake_rank)

        selected, score = selector._select_best_tool(
            inputs,
            [broken, available],
            selector._prepare_task_context(inputs),
        )

        assert selected is available
        assert score.tool_name == available.name


def test_selectors_require_project_output_path_before_provider_execution(monkeypatch):
    selector_cases = [
        (VideoSelector(), {"prompt": "cinematic product launch"}),
        (ImageSelector(), {"prompt": "product key visual"}),
        (TTSSelector(), {"text": "Narration"}),
    ]

    for selector, inputs in selector_cases:
        provider = _AvailableProviderTool(f"{selector.name}_available")
        if selector.name == "tts_selector":
            provider.input_schema = {"properties": {"text": {"type": "string"}, "output_path": {"type": "string"}}}
        else:
            provider.input_schema = {"properties": {"prompt": {"type": "string"}, "output_path": {"type": "string"}}}
        monkeypatch.setattr(selector, "_providers", lambda provider=provider: [provider])
        monkeypatch.setattr(
            "lib.scoring.rank_providers",
            lambda candidates, _ctx: [
                ProviderScore(tool_name=tool.name, provider=tool.provider, task_fit=1.0)
                for tool in candidates
            ],
        )

        result = selector.execute(inputs)

        assert not result.success
        assert "output_path is required" in (result.error or "")
        assert provider.calls == []


def test_selectors_require_missing_output_path_before_provider_discovery(monkeypatch):
    selector_cases = [
        (VideoSelector(), {"prompt": "cinematic product launch"}),
        (ImageSelector(), {"prompt": "product key visual"}),
        (TTSSelector(), {"text": "Narration"}),
    ]

    for selector, inputs in selector_cases:

        def fail_provider_discovery(selector_name=selector.name):
            raise AssertionError(
                f"{selector_name} discovered providers before output_path validation"
            )

        monkeypatch.setattr(selector, "_providers", fail_provider_discovery)

        result = selector.execute(inputs)

        assert not result.success
        assert "output_path is required" in (result.error or "")
        assert "projects/<project-name>/" in (result.error or "")


def test_selectors_reject_invalid_output_path_before_provider_discovery(monkeypatch):
    selector_cases = [
        (VideoSelector(), {"prompt": "cinematic product launch", "output_path": "clip.mp4"}),
        (ImageSelector(), {"prompt": "product key visual", "output_path": "image.png"}),
        (TTSSelector(), {"text": "Narration", "output_path": "voice.mp3"}),
    ]

    for selector, inputs in selector_cases:
        def fail_provider_discovery(selector_name=selector.name):
            raise AssertionError(f"{selector_name} discovered providers before output_path validation")

        monkeypatch.setattr(selector, "_providers", fail_provider_discovery)

        result = selector.execute(inputs)

        assert not result.success
        assert "output_path" in (result.error or "")
        assert "projects/<project-name>/" in (result.error or "")


def test_selector_rank_mode_reports_degraded_status_when_provider_status_fails(monkeypatch):
    selector = VideoSelector()
    broken = _BrokenStatusProviderTool("broken_video_provider", provider="broken")
    monkeypatch.setattr(selector, "_providers", lambda: [broken])

    result = selector.execute({"prompt": "cinematic product launch", "operation": "rank"})

    assert result.success
    assert result.data["rankings"][0]["tool_name"] == "broken_video_provider"
    assert result.data["rankings"][0]["status"] == "degraded"


def test_selector_rank_serialization_uses_status_values():
    score = ProviderScore(tool_name="ranked_tool", provider="same-provider")
    candidate = _AvailableProviderTool("ranked_tool")

    assert VideoSelector()._serialize_rankings([candidate], [score])[0]["status"] == "available"
    assert ImageSelector()._serialize_rankings([candidate], [score])[0]["status"] == "available"
    assert TTSSelector()._serialize_rankings([candidate], [score])[0]["status"] == "available"


def test_selector_idempotency_keys_include_routing_and_generation_inputs():
    selector_cases = [
        (
            VideoSelector(),
            {
                "prompt": "Animate the approved product frame",
                "operation": "image_to_video",
                "preferred_provider": "auto",
                "allowed_providers": ["seedance"],
                "model_variant": "standard",
                "reference_image_path": "projects/demo/reference_assets/product_a.png",
                "aspect_ratio": "16:9",
                "duration": "5",
                "resolution": "720p",
            },
            [
                {"prompt": "Animate the alternate product frame"},
                {"operation": "reference_to_video"},
                {"allowed_providers": ["wan_video_api"]},
                {"model_variant": "fast"},
                {"model": "gen4.5"},
                {"reference_image_path": "projects/demo/reference_assets/product_b.png"},
                {"duration": "10"},
                {"resolution": "1080p"},
                {"output_path": "projects/demo/assets/video/selector-a.mp4"},
            ],
        ),
        (
            ImageSelector(),
            {
                "prompt": "Product key visual",
                "generation_mode": "edit",
                "preferred_provider": "auto",
                "allowed_providers": ["bailian"],
                "model": "wan2.7-image-pro",
                "image_path": "projects/demo/reference_assets/product_a.png",
                "width": 1024,
                "height": 1024,
                "seed": 123,
            },
            [
                {"prompt": "Product key visual alternate"},
                {"generation_mode": "generate"},
                {"allowed_providers": ["openai"]},
                {"model": "wan2.7-image"},
                {"image_path": "projects/demo/reference_assets/product_b.png"},
                {"width": 1536},
                {"seed": 456},
                {"output_path": "projects/demo/assets/images/selector-a.png"},
            ],
        ),
        (
            TTSSelector(),
            {
                "text": "A concise narration line.",
                "preferred_provider": "auto",
                "allowed_providers": ["openai"],
                "voice_id": "voice-a",
                "model_id": "model-a",
                "output_format": "mp3_44100_128",
                "instructions": "Warm, restrained delivery.",
                "speed": 1.0,
            },
            [
                {"text": "A different narration line."},
                {"allowed_providers": ["elevenlabs"]},
                {"voice_id": "voice-b"},
                {"model_id": "model-b"},
                {"output_format": "wav"},
                {"instructions": "Urgent trailer delivery."},
                {"speed": 0.9},
                {"output_path": "projects/demo/assets/audio/selector-a.mp3"},
            ],
        ),
    ]

    for selector, base, variants in selector_cases:
        base_key = selector.idempotency_key(base)
        for variant in variants:
            assert selector.idempotency_key({**base, **variant}) != base_key


def test_video_selector_rank_respects_allowed_providers(monkeypatch):
    selector = VideoSelector()
    allowed = _AvailableProviderTool("allowed_video", provider="allowed")
    blocked = _AvailableProviderTool("blocked_video", provider="blocked")
    monkeypatch.setattr(selector, "_providers", lambda: [allowed, blocked])

    result = selector.execute(
        {"prompt": "cinematic launch", "operation": "rank", "allowed_providers": ["allowed"]}
    )

    assert result.success
    assert [item["tool_name"] for item in result.data["rankings"]] == ["allowed_video"]


def test_video_selector_rank_filters_candidates_by_requested_operation(monkeypatch):
    selector = VideoSelector()
    text_only = _AvailableProviderTool("text_only_video", provider="text-only")
    image_capable = _AvailableProviderTool("image_capable_video", provider="image-capable")
    image_capable.supports = {"image_to_video": True}
    monkeypatch.setattr(selector, "_providers", lambda: [text_only, image_capable])

    def fake_rank(candidates, _task_context):
        return [
            ProviderScore(tool_name=tool.name, provider=tool.provider, task_fit=1.0)
            for tool in candidates
        ]

    monkeypatch.setattr("lib.scoring.rank_providers", fake_rank)

    result = selector.execute(
        {
            "prompt": "Animate the product frame",
            "operation": "rank",
            "target_operation": "image_to_video",
        }
    )

    assert result.success
    assert [item["tool_name"] for item in result.data["rankings"]] == [
        "image_capable_video"
    ]


def test_video_selector_generation_alternatives_match_requested_operation(monkeypatch):
    selector = VideoSelector()
    text_only = _AvailableProviderTool("text_only_video", provider="text-only")
    primary = _AvailableProviderTool("primary_image_video", provider="primary")
    alternative = _AvailableProviderTool("alternative_image_video", provider="alternative")
    primary.supports = {"image_to_video": True}
    alternative.supports = {"image_to_video": True}
    monkeypatch.setattr(selector, "_providers", lambda: [text_only, primary, alternative])

    def fake_rank(candidates, _task_context):
        order = {
            "primary_image_video": 1.0,
            "alternative_image_video": 0.8,
            "text_only_video": 0.6,
        }
        return [
            ProviderScore(tool_name=tool.name, provider=tool.provider, task_fit=order[tool.name])
            for tool in sorted(candidates, key=lambda tool: order[tool.name], reverse=True)
        ]

    monkeypatch.setattr("lib.scoring.rank_providers", fake_rank)

    result = selector.execute(
        {
            "prompt": "Animate the product frame",
            "operation": "image_to_video",
            "output_path": "projects/demo/assets/video/product-frame.mp4",
        }
    )

    assert result.success
    assert result.data["selected_tool"] == "primary_image_video"
    assert result.data["alternatives_considered"] == ["alternative_image_video"]


def test_video_selector_refuses_image_to_video_when_no_provider_supports_references(
    monkeypatch,
):
    selector = VideoSelector()
    text_only = _AvailableProviderTool("text_only_video", provider="text-only")
    monkeypatch.setattr(selector, "_providers", lambda: [text_only])

    result = selector.execute(
        {
            "prompt": "Animate the product frame",
            "operation": "image_to_video",
            "output_path": "projects/demo/assets/video/product-frame.mp4",
        }
    )

    assert result.success is False
    assert result.error == "No image_to_video video provider available."


def test_image_selector_rank_respects_allowed_providers(monkeypatch):
    selector = ImageSelector()
    allowed = _AvailableProviderTool("allowed_image", provider="allowed")
    blocked = _AvailableProviderTool("blocked_image", provider="blocked")
    monkeypatch.setattr(selector, "_providers", lambda: [allowed, blocked])

    result = selector.execute(
        {"prompt": "product render", "operation": "rank", "allowed_providers": ["allowed"]}
    )

    assert result.success
    assert [item["tool_name"] for item in result.data["rankings"]] == ["allowed_image"]


def test_tts_selector_rank_respects_allowed_providers(monkeypatch):
    selector = TTSSelector()
    allowed = _AvailableProviderTool("allowed_voice", provider="allowed")
    blocked = _AvailableProviderTool("blocked_voice", provider="blocked")
    monkeypatch.setattr(selector, "_providers", lambda: [allowed, blocked])

    result = selector.execute(
        {"text": "Narration", "operation": "rank", "allowed_providers": ["allowed"]}
    )

    assert result.success
    assert [item["tool_name"] for item in result.data["rankings"]] == ["allowed_voice"]


def test_tts_selector_reports_openai_layer3_skill(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    registry.clear()
    registry.discover()
    assert registry.get("openai_tts").get_status().value == "available"

    def fake_execute(self: OpenAITTS, inputs: dict[str, object]) -> ToolResult:
        return ToolResult(success=True, data={"output_path": str(tmp_path / "voice.mp3")})

    monkeypatch.setattr(OpenAITTS, "execute", fake_execute)

    result = TTSSelector().execute(
        {
            "text": "A concise narration line.",
            "preferred_provider": "openai",
            "allowed_providers": ["openai"],
            "output_path": "projects/demo/assets/audio/voice.mp3",
        }
    )

    assert result.success
    assert result.data["selected_tool"] == "openai_tts"
    assert result.data["required_agent_skills"] == ["text-to-speech"]


def test_screen_capture_selector_reports_registered_fallback_tools():
    from lib.agent_components import load_manifest

    registry.clear()
    registry.discover()

    selector = registry.get("screen_capture_selector")
    assert selector is not None

    assert set(selector.fallback_tools) == {"screen_recorder", "cap_recorder"}
    assert all(registry.get(name) is not None for name in selector.fallback_tools)

    repo_root = Path(__file__).resolve().parent.parent.parent
    manifest = load_manifest(repo_root / ".agents" / "components.yaml", repo_root=repo_root)
    for skill in selector.agent_skills:
        component = manifest.components.get(skill)
        assert component is not None
        assert _component_has_skill_source(component)


def test_registered_tool_agent_skills_resolve_to_project_layer3_skills():
    from lib.agent_components import load_manifest

    registry.clear()
    registry.discover()

    repo_root = Path(__file__).resolve().parent.parent.parent
    manifest = load_manifest(repo_root / ".agents" / "components.yaml", repo_root=repo_root)
    missing = []
    for tool_name in sorted(registry.list_all()):
        tool = registry.get(tool_name)
        for skill in tool.agent_skills:
            component = manifest.components.get(skill)
            if component is None:
                missing.append(f"{tool_name}:{skill}")
                continue
            if not _component_has_skill_source(component):
                missing.append(f"{tool_name}:{skill}")

    assert missing == []
