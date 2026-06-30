"""Capability-level optional text generation selector."""

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


class TextSelector(BaseTool):
    name = "text_selector"
    version = "0.1.0"
    tier = ToolTier.GENERATE
    capability = "text_generation"
    provider = "selector"
    stability = ToolStability.BETA
    runtime = ToolRuntime.API
    install_instructions = (
        "Routes optional billed text helper calls. Use `make models-list "
        "CAPABILITY=text_generation` to inspect provider/model choices."
    )
    agent_skills = ["text-generation"]

    capabilities = ["chat", "text_generation", "provider_selection"]
    supports = {
        "user_preference_routing": True,
        "model_preference_routing": True,
    }
    best_for = [
        "Selecting between configured optional text-generation helpers",
        "Honoring VPB_TEXT_GENERATION_* defaults from .env",
    ]
    not_good_for = [
        "Replacing the primary agent reasoning loop",
        "Silently making billed LLM calls without user approval",
    ]
    side_effects = [
        "delegates optional text response write to output_path",
        "routes approved text generation to provider",
    ]
    idempotency_key_fields = [
        "messages",
        "system",
        "prompt",
        "model",
        "temperature",
        "max_tokens",
        "output_path",
        "preferred_provider",
        "allowed_providers",
        "operation",
    ]

    input_schema = {
        "type": "object",
        "properties": {
            "messages": {"type": "array", "items": {"type": "object"}},
            "system": {"type": "string"},
            "prompt": {"type": "string"},
            "model": {
                "type": "string",
                "description": "Provider-specific text model from make models-list.",
            },
            "temperature": {"type": "number", "minimum": 0.0, "maximum": 2.0},
            "max_tokens": {"type": "integer", "minimum": 1},
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
                "enum": ["generate", "rank"],
                "default": "generate",
            },
        },
        "anyOf": [
            {"required": ["messages"]},
            {"required": ["prompt"]},
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
            return ToolResult(success=False, error="No text generation provider available.")

        return annotate_result(
            tool.execute(provider_inputs(inputs, tool)),
            tool=tool,
            score=score,
            candidates=candidates,
        )

    def _prepare_task_context(self, inputs: dict[str, Any]) -> dict[str, Any]:
        from lib.scoring import normalize_task_context

        prompt = inputs.get("prompt", "")
        if not prompt and inputs.get("messages"):
            prompt = " ".join(
                str(message.get("content", ""))
                for message in inputs.get("messages", [])
                if isinstance(message, dict)
            )
        return normalize_task_context(
            inputs.get("task_context", {}),
            prompt=prompt,
            capability=self.capability,
            operation=inputs.get("operation", "generate"),
        )
