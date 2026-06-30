"""Capability-level music generation selector."""

from __future__ import annotations

from typing import Any

from lib.model_preferences import apply_model_preferences
from tools.base_tool import BaseTool, ToolResult, ToolRuntime, ToolStability, ToolTier
from tools.output_paths import require_explicit_output_path
from tools.selector_utils import (
    annotate_result,
    available_status,
    provider_inputs,
    providers_for_capability,
    selectable_candidates,
    select_best_tool,
    serialize_rankings,
)


class MusicSelector(BaseTool):
    name = "music_selector"
    version = "0.1.0"
    tier = ToolTier.GENERATE
    capability = "music_generation"
    provider = "selector"
    stability = ToolStability.BETA
    runtime = ToolRuntime.HYBRID
    install_instructions = (
        "Routes to discovered music providers. Use `make models-list "
        "CAPABILITY=music_generation` to inspect provider/model choices."
    )
    agent_skills = ["music", "sound-effects"]

    capabilities = ["music_generation", "provider_selection"]
    supports = {
        "user_preference_routing": True,
        "model_preference_routing": True,
    }
    best_for = [
        "Selecting between configured music providers",
        "Honoring VPB_MUSIC_GENERATION_* defaults from .env",
    ]
    side_effects = ["delegates generated music audio write to output_path"]
    idempotency_key_fields = [
        "prompt",
        "lyrics",
        "style",
        "title",
        "model",
        "duration_seconds",
        "is_instrumental",
        "instrumental",
        "audio_path",
        "audio_url",
        "output_path",
        "preferred_provider",
        "allowed_providers",
        "operation",
    ]

    input_schema = {
        "type": "object",
        "properties": {
            "prompt": {"type": "string"},
            "lyrics": {"type": "string"},
            "style": {"type": "string"},
            "title": {"type": "string"},
            "model": {
                "type": "string",
                "description": "Provider-specific music model from make models-list.",
            },
            "duration_seconds": {"type": "number", "minimum": 1},
            "is_instrumental": {"type": "boolean"},
            "instrumental": {"type": "boolean"},
            "custom_mode": {"type": "boolean"},
            "lyrics_optimizer": {"type": "boolean"},
            "audio_url": {"type": "string"},
            "audio_path": {"type": "string"},
            "format": {"type": "string"},
            "sample_rate": {"type": "integer"},
            "bitrate": {"type": "integer"},
            "preferred_provider": {
                "type": "string",
                "default": "auto",
                "description": "Provider name, concrete tool name, or 'auto'.",
            },
            "allowed_providers": {
                "type": "array",
                "items": {"type": "string"},
            },
            "operation": {
                "type": "string",
                "enum": ["generate", "rank"],
                "default": "generate",
            },
            "output_path": {"type": "string"},
        },
        "anyOf": [
            {"required": ["prompt", "output_path"]},
            {"properties": {"operation": {"const": "rank"}}, "required": ["operation"]},
        ],
    }
    output_schema = {
        "type": "object",
        "properties": {
            "output": {"type": "string"},
            "output_path": {"type": "string"},
            "selected_tool": {"type": "string"},
            "selected_provider": {"type": "string"},
            "selection_reason": {"type": "string"},
            "provider_score": {"type": "object"},
            "selected_tool_agent_skills": {
                "type": "array",
                "items": {"type": "string"},
            },
            "required_agent_skills": {
                "type": "array",
                "items": {"type": "string"},
            },
            "selected_tool_usage_location": {"type": ["string", "null"]},
            "selected_tool_best_for": {
                "type": "array",
                "items": {"type": "string"},
            },
            "selected_tool_model_options": {
                "type": "array",
                "items": {"type": "object"},
            },
            "alternatives_considered": {
                "type": "array",
                "items": {"type": "string"},
            },
            "rankings": {"type": "array", "items": {"type": "object"}},
            "explanation": {"type": "string"},
            "normalized_task_context": {"type": "object"},
        },
        "anyOf": [
            {
                "required": [
                    "selected_tool",
                    "selected_provider",
                    "selection_reason",
                    "output_path",
                    "alternatives_considered",
                ],
            },
            {
                "required": [
                    "rankings",
                    "explanation",
                    "normalized_task_context",
                ],
            },
        ],
    }

    def _providers(self) -> list[BaseTool]:
        return providers_for_capability(self.capability, self.name)

    @property
    def fallback_tools(self) -> list[str]:
        return [tool.name for tool in self._providers()]

    def get_status(self):
        return available_status(self._providers())

    def estimate_cost(self, inputs: dict[str, Any]) -> float:
        inputs = apply_model_preferences(dict(inputs), self.capability)
        tool, _ = select_best_tool(
            inputs,
            self.capability,
            self._providers(),
            self._prepare_task_context(inputs),
        )
        return tool.estimate_cost(provider_inputs(inputs, tool)) if tool else 0.0

    def idempotency_key(self, inputs: dict[str, Any]) -> str:
        return super().idempotency_key(
            apply_model_preferences(dict(inputs), self.capability)
        )

    def execute(self, inputs: dict[str, Any]) -> ToolResult:
        from lib.scoring import rank_providers

        inputs = apply_model_preferences(dict(inputs), self.capability)
        task_context = self._prepare_task_context(inputs)
        candidates = self._providers()

        if inputs.get("operation") == "rank":
            filtered = selectable_candidates(inputs, self.capability, candidates)
            rankings = rank_providers(filtered, task_context)
            return ToolResult(
                success=True,
                data={
                    "rankings": serialize_rankings(filtered, rankings),
                    "explanation": "\n".join(r.explain() for r in rankings[:5]),
                    "normalized_task_context": task_context,
                },
            )

        _, output_error = require_explicit_output_path(
            inputs, self.name, artifact_label="generated music audio"
        )
        if output_error:
            return output_error

        tool, score = select_best_tool(
            inputs, self.capability, candidates, task_context
        )
        if tool is None:
            return ToolResult(success=False, error="No music generation provider available.")

        return annotate_result(
            tool.execute(_provider_inputs(inputs, tool)),
            tool=tool,
            score=score,
            candidates=candidates,
        )

    def _prepare_task_context(self, inputs: dict[str, Any]) -> dict[str, Any]:
        from lib.scoring import normalize_task_context

        return normalize_task_context(
            inputs.get("task_context", {}),
            prompt=inputs.get("prompt", ""),
            capability=self.capability,
            operation=inputs.get("operation", "generate"),
        )


def _provider_inputs(inputs: dict[str, Any], tool: BaseTool) -> dict[str, Any]:
    adapted = dict(inputs)
    properties = getattr(tool, "input_schema", {}).get("properties", {})
    if (
        "instrumental" in properties
        and "instrumental" not in adapted
        and "is_instrumental" in adapted
    ):
        adapted["instrumental"] = adapted["is_instrumental"]
    if (
        "is_instrumental" in properties
        and "is_instrumental" not in adapted
        and "instrumental" in adapted
    ):
        adapted["is_instrumental"] = adapted["instrumental"]
    return provider_inputs(adapted, tool)
