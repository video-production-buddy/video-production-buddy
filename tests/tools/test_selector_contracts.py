from __future__ import annotations

import jsonschema
import pytest

from tools.audio.tts_selector import TTSSelector
from tools.base_tool import ToolResult, ToolStatus
from tools.graphics.image_selector import ImageSelector
from tools.video.video_selector import VideoSelector


class _AvailableProvider:
    def __init__(self, name: str, provider: str = "fake-provider") -> None:
        self.name = name
        self.provider = provider
        self.agent_skills = ["media-generation"]
        self.best_for = ["generated assets"]
        self.calls: list[dict[str, object]] = []
        self.input_schema = {
            "properties": {
                "prompt": {"type": "string"},
                "text": {"type": "string"},
                "output_path": {"type": "string"},
            }
        }
        self.supports = {"image_to_video": True}

    def get_status(self) -> ToolStatus:
        return ToolStatus.AVAILABLE

    def get_info(self) -> dict[str, object]:
        return {
            "name": self.name,
            "provider": self.provider,
            "stability": "production",
            "runtime": "api",
            "agent_skills": self.agent_skills,
            "usage_location": __file__,
            "best_for": self.best_for,
            "supports": self.supports,
        }

    def estimate_cost(self, _inputs: dict[str, object]) -> float:
        return 0.0

    def execute(self, inputs: dict[str, object]) -> ToolResult:
        self.calls.append(dict(inputs))
        output_path = str(inputs["output_path"])
        return ToolResult(
            success=True,
            data={"output": output_path, "output_path": output_path},
            artifacts=[output_path],
        )


class _BrokenStatusProvider(_AvailableProvider):
    def get_status(self) -> ToolStatus:
        raise RuntimeError(f"{self.name} status backend unavailable")


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


def test_selectors_require_project_output_path_before_provider_discovery(monkeypatch) -> None:
    cases = [
        (TTSSelector(), {"text": "Narration line."}),
        (ImageSelector(), {"prompt": "Product key visual"}),
        (VideoSelector(), {"prompt": "Product launch shot"}),
    ]

    for selector, inputs in cases:

        def fail_provider_discovery(selector_name: str = selector.name):
            raise AssertionError(
                f"{selector_name} discovered providers before output_path validation"
            )

        monkeypatch.setattr(selector, "_providers", fail_provider_discovery)

        result = selector.execute(inputs)

        assert result.success is False
        assert "output_path is required" in (result.error or "")
        assert "projects/<project-name>/" in (result.error or "")


def test_selector_rank_mode_reports_degraded_status_when_provider_status_fails(
    monkeypatch,
) -> None:
    selector = VideoSelector()
    broken = _BrokenStatusProvider("broken_video_provider", provider="broken")
    monkeypatch.setattr(selector, "_providers", lambda: [broken])

    result = selector.execute({"prompt": "cinematic product launch", "operation": "rank"})

    assert result.success is True
    assert result.data["rankings"][0]["tool_name"] == "broken_video_provider"
    assert result.data["rankings"][0]["status"] == "degraded"
    assert result.data["rankings"][0]["reliability"] == 0.4


def test_selector_generation_success_payload_matches_output_schema(monkeypatch) -> None:
    selector = ImageSelector()
    provider = _AvailableProvider("image_provider", provider="selected")
    monkeypatch.setattr(selector, "_providers", lambda: [provider])

    result = selector.execute(
        {
            "prompt": "Generate a product image.",
            "preferred_provider": "selected",
            "allowed_providers": ["selected"],
            "output_path": "projects/demo/assets/images/selector-image.png",
        }
    )

    assert result.success is True
    assert result.data["selected_tool"] == "image_provider"
    assert result.data["selected_provider"] == "selected"
    assert result.data["required_agent_skills"] == ["media-generation"]
    assert result.data["output_path"] == "projects/demo/assets/images/selector-image.png"
    jsonschema.validate(instance=result.data, schema=selector.output_schema)
