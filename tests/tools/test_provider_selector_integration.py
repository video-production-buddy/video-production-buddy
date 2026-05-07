from __future__ import annotations

from pathlib import Path

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
        self.input_schema = {"properties": {"prompt": {"type": "string"}}}
        self.supports = {}

    def get_status(self):
        from tools.base_tool import ToolStatus

        return ToolStatus.AVAILABLE

    def get_info(self) -> dict[str, object]:
        return {
            "name": self.name,
            "provider": self.provider,
            "agent_skills": [],
            "usage_location": __file__,
            "best_for": self.best_for,
            "supports": self.supports,
        }

    def execute(self, inputs: dict[str, object]) -> ToolResult:
        return ToolResult(success=True, data={"inputs": inputs})


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
        }
    )

    assert result.success
    assert captured["operation"] == "image_editing"
    assert captured["base_image_path"] == str(source)


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
        }
    )

    assert result.success
    assert captured["image_path"] == str(source)


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
                "reference_image_path": "projects/demo/reference_assets/product_a.png",
                "aspect_ratio": "16:9",
                "duration": "5",
                "resolution": "720p",
            },
            [
                {"prompt": "Animate the alternate product frame"},
                {"operation": "reference_to_video"},
                {"allowed_providers": ["wan_video_api"]},
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
                "image_path": "projects/demo/reference_assets/product_a.png",
                "width": 1024,
                "height": 1024,
                "seed": 123,
            },
            [
                {"prompt": "Product key visual alternate"},
                {"generation_mode": "generate"},
                {"allowed_providers": ["openai"]},
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
            },
            [
                {"text": "A different narration line."},
                {"allowed_providers": ["elevenlabs"]},
                {"voice_id": "voice-b"},
                {"model_id": "model-b"},
                {"output_format": "wav"},
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
        {"prompt": "Animate the product frame", "operation": "image_to_video"}
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
        {"prompt": "Animate the product frame", "operation": "image_to_video"}
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
        assert skill in manifest.components
        assert (manifest.agents_dir / skill / "SKILL.md").exists()


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
            skill_path = manifest.agents_dir / component.name / "SKILL.md"
            if not skill_path.exists():
                missing.append(f"{tool_name}:{skill}")

    assert missing == []
