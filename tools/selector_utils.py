"""Shared helpers for capability-level provider selectors."""

from __future__ import annotations

from typing import Any

from lib.model_preferences import filter_model_candidates
from tools.base_tool import BaseTool
from tools.status_utils import (
    is_tool_available,
    safe_tool_info,
    safe_tool_provider,
    safe_tool_status,
)


def providers_for_capability(capability: str, selector_name: str) -> list[BaseTool]:
    """Return provider tools for a capability, excluding selector tools."""
    from tools.tool_registry import registry

    registry.ensure_discovered()
    return [
        tool for tool in registry.get_by_capability(capability)
        if tool.name != selector_name and safe_tool_provider(tool) != "selector"
    ]


def available_status(candidates: list[BaseTool]):
    """Report available when at least one candidate provider is available."""
    from tools.base_tool import ToolStatus

    if any(is_tool_available(tool) for tool in candidates):
        return ToolStatus.AVAILABLE
    return ToolStatus.UNAVAILABLE


def allowed_candidates(
    inputs: dict[str, Any],
    candidates: list[BaseTool],
) -> list[BaseTool]:
    """Filter candidates by provider or concrete tool-name shortlist."""
    allowed = set(inputs.get("allowed_providers") or [])
    if not allowed:
        return candidates
    return [
        tool for tool in candidates
        if safe_tool_provider(tool) in allowed or tool.name in allowed
    ]


def selectable_candidates(
    inputs: dict[str, Any],
    capability: str,
    candidates: list[BaseTool],
) -> list[BaseTool]:
    """Apply provider shortlist and model compatibility filters."""
    return filter_model_candidates(
        inputs,
        capability,
        allowed_candidates(inputs, candidates),
    )


def select_best_tool(
    inputs: dict[str, Any],
    capability: str,
    candidates: list[BaseTool],
    task_context: dict[str, Any],
) -> tuple[BaseTool | None, object]:
    """Select an available provider, honoring explicit provider preference."""
    from lib.scoring import rank_providers

    preferred = inputs.get("preferred_provider", "auto")
    filtered = selectable_candidates(inputs, capability, candidates)
    rankings = rank_providers(filtered, task_context)

    available_by_name: dict[str, BaseTool] = {}
    for tool in filtered:
        if is_tool_available(tool):
            available_by_name[tool.name] = tool

    if preferred != "auto":
        for score in rankings:
            if score.provider == preferred or score.tool_name == preferred:
                tool = available_by_name.get(score.tool_name)
                if tool is not None:
                    return tool, score
        return None, None

    for score in rankings:
        tool = available_by_name.get(score.tool_name)
        if tool is not None:
            return tool, score

    return None, None


def provider_inputs(
    inputs: dict[str, Any],
    tool: BaseTool,
    *,
    strip_keys: tuple[str, ...] = (
        "operation",
        "preferred_provider",
        "allowed_providers",
        "task_context",
    ),
) -> dict[str, Any]:
    """Strip selector-only fields and pass through fields declared by a provider."""
    adapted = dict(inputs)
    for key in strip_keys:
        adapted.pop(key, None)

    properties = getattr(tool, "input_schema", {}).get("properties", {})
    if not properties:
        return adapted
    return {key: value for key, value in adapted.items() if key in properties}


def tool_context_payload(tool: BaseTool) -> dict[str, Any]:
    """Return selector metadata about the chosen provider."""
    info = safe_tool_info(tool)
    return {
        "selected_tool_agent_skills": info.get("agent_skills", []),
        "required_agent_skills": info.get("agent_skills", []),
        "selected_tool_usage_location": info.get("usage_location"),
        "selected_tool_best_for": info.get("best_for", []),
        "selected_tool_model_options": info.get("model_options", []),
    }


def annotate_result(
    result,
    *,
    tool: BaseTool,
    score: object,
    candidates: list[BaseTool],
):
    """Attach common selector metadata to a successful provider result."""
    if result.success:
        result.data.setdefault("selected_tool", tool.name)
        selected_provider = safe_tool_provider(tool)
        result.data["selected_provider"] = selected_provider
        result.data["selection_reason"] = (
            score.explain()
            if score
            else f"Selected {selected_provider} ({tool.name})"
        )
        if score:
            result.data["provider_score"] = score.to_dict()
        result.data.update(tool_context_payload(tool))
        result.data["alternatives_considered"] = [
            candidate.name for candidate in candidates
            if candidate.name != tool.name and is_tool_available(candidate)
        ]
    return result


def serialize_rankings(
    candidates: list[BaseTool],
    rankings: list[object],
) -> list[dict[str, Any]]:
    """Render rankings with provider metadata for user-facing rank mode."""
    tool_by_name = {tool.name: tool for tool in candidates}
    serialized: list[dict[str, Any]] = []
    for score in rankings:
        item = score.to_dict()
        tool = tool_by_name.get(score.tool_name)
        if tool:
            info = safe_tool_info(tool)
            item["agent_skills"] = info.get("agent_skills", [])
            item["usage_location"] = info.get("usage_location")
            item["best_for"] = info.get("best_for", [])
            item["supports"] = info.get("supports", {})
            item["model_options"] = info.get("model_options", [])
            item["status"] = safe_tool_status(tool).value
        serialized.append(item)
    return serialized
