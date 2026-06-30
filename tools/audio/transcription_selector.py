"""Capability-level speech transcription selector."""

from __future__ import annotations

from typing import Any

from lib.model_preferences import apply_model_preferences
from tools.base_tool import BaseTool, ToolResult, ToolRuntime, ToolStability, ToolTier
from tools.selector_utils import (
    annotate_result,
    available_status,
    provider_inputs,
    providers_for_capability,
    selectable_candidates,
    select_best_tool,
    serialize_rankings,
)


class TranscriptionSelector(BaseTool):
    name = "transcription_selector"
    version = "0.1.0"
    tier = ToolTier.VOICE
    capability = "transcription"
    provider = "selector"
    stability = ToolStability.BETA
    runtime = ToolRuntime.HYBRID
    install_instructions = (
        "Routes to discovered transcription providers. Use `make models-list "
        "CAPABILITY=transcription` to inspect provider/model choices."
    )
    agent_skills = ["speech-to-text"]

    capabilities = ["transcription", "provider_selection"]
    supports = {
        "user_preference_routing": True,
        "model_preference_routing": True,
    }
    best_for = [
        "Selecting between configured speech-to-text providers",
        "Honoring VPB_TRANSCRIPTION_* defaults from .env",
    ]
    side_effects = ["delegates optional transcript write to output_path"]
    idempotency_key_fields = [
        "audio_url",
        "audio_path",
        "model",
        "output_path",
        "preferred_provider",
        "allowed_providers",
        "operation",
    ]

    input_schema = {
        "type": "object",
        "properties": {
            "audio_url": {"type": "string"},
            "audio_path": {"type": "string"},
            "model": {
                "type": "string",
                "description": "Provider-specific transcription model from make models-list.",
            },
            "output_path": {"type": "string"},
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
                "enum": ["transcribe", "rank"],
                "default": "transcribe",
            },
        },
        "anyOf": [
            {"required": ["audio_url"]},
            {"required": ["audio_path"]},
            {"properties": {"operation": {"const": "rank"}}, "required": ["operation"]},
        ],
    }
    output_schema = {
        "type": "object",
        "properties": {
            "output": {"type": ["string", "null"]},
            "output_path": {"type": ["string", "null"]},
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

        tool, score = select_best_tool(
            inputs, self.capability, candidates, task_context
        )
        if tool is None:
            return ToolResult(success=False, error="No transcription provider available.")

        return annotate_result(
            tool.execute(provider_inputs(inputs, tool)),
            tool=tool,
            score=score,
            candidates=candidates,
        )

    def _prepare_task_context(self, inputs: dict[str, Any]) -> dict[str, Any]:
        from lib.scoring import normalize_task_context

        return normalize_task_context(
            inputs.get("task_context", {}),
            prompt=str(inputs.get("audio_url") or inputs.get("audio_path") or ""),
            capability=self.capability,
            operation=inputs.get("operation", "transcribe"),
        )
