"""Capability-level image selector that routes between generation and stock providers.

Provider discovery is automatic — any BaseTool with capability="image_generation"
is picked up from the registry.  Adding a new image provider requires only creating
the tool file in tools/graphics/; no changes to this selector are needed.
"""

from __future__ import annotations

from typing import Any

from lib.model_preferences import apply_model_preferences, filter_model_candidates
from tools.base_tool import BaseTool, ToolResult, ToolRuntime, ToolStability, ToolStatus, ToolTier
from tools.status_utils import (
    is_tool_available,
    safe_tool_info,
    safe_tool_provider,
    safe_tool_status,
)
from tools.output_paths import require_explicit_output_path


class ImageSelector(BaseTool):
    name = "image_selector"
    version = "0.2.0"
    tier = ToolTier.GENERATE
    capability = "image_generation"
    provider = "selector"
    stability = ToolStability.BETA
    runtime = ToolRuntime.HYBRID
    install_instructions = (
        "Routes to discovered image providers. Use provider_menu_summary() to see "
        "configured generators, stock sources, and per-provider setup steps."
    )
    agent_skills = ["flux-best-practices", "bfl-api"]

    capabilities = [
        "generate_image", "search_image", "download_image",
        "provider_selection", "text_to_image", "stock_image",
    ]
    supports = {
        "user_preference_routing": True,
        "offline_fallback": True,
        "stock_fallback": True,
    }
    best_for = [
        "preflight routing — pick the best image provider for the task",
        "switching between generated and stock images",
        "automatic fallback when preferred provider is unavailable",
    ]
    side_effects = ["delegates generated or sourced image write to output_path"]
    idempotency_key_fields = [
        "prompt",
        "negative_prompt",
        "width",
        "height",
        "seed",
        "n",
        "aspect_ratio",
        "resolution",
        "generation_mode",
        "image_url",
        "image_path",
        "image_urls",
        "image_paths",
        "output_path",
        "preferred_provider",
        "allowed_providers",
        "model",
        "operation",
    ]

    input_schema = {
        "type": "object",
        "required": ["prompt"],
        "properties": {
            "prompt": {
                "type": "string",
                "description": "Image description (used as prompt for generation or query for stock)",
            },
            "negative_prompt": {
                "type": "string",
                "description": "What to avoid in the generated image. Passed to providers that support it.",
            },
            "width": {"type": "integer", "description": "Image width in pixels"},
            "height": {"type": "integer", "description": "Image height in pixels"},
            "seed": {"type": "integer", "description": "Random seed for reproducibility (generation providers only)"},
            "n": {"type": "integer", "description": "Number of image variations to request when supported."},
            "aspect_ratio": {
                "type": "string",
                "description": "Aspect ratio hint for providers that support ratio-based generation.",
            },
            "resolution": {
                "type": "string",
                "description": "Resolution tier for providers that support named resolutions.",
            },
            "generation_mode": {
                "type": "string",
                "enum": ["generate", "edit"],
                "default": "generate",
                "description": "Use 'edit' when providing one or more source images.",
            },
            "image_url": {"type": "string", "description": "Single source image URL for edit-capable providers."},
            "image_path": {"type": "string", "description": "Single local source image path for edit-capable providers."},
            "image_urls": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Multiple source image URLs for compositing edits.",
            },
            "image_paths": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Multiple local source image paths for compositing edits.",
            },
            "preferred_provider": {
                "type": "string",
                "description": "Provider name or 'auto'. Valid values are discovered at runtime from the registry.",
                "default": "auto",
            },
            "model": {
                "type": "string",
                "description": (
                    "Provider-specific image model. Valid values are reported by "
                    "provider_menu_summary()['model_choices'] for the selected tool."
                ),
            },
            "allowed_providers": {
                "type": "array",
                "items": {"type": "string"},
            },
            "operation": {
                "type": "string",
                "enum": ["generate", "rank"],
                "default": "generate",
                "description": "Operation mode. 'rank' returns scored provider rankings without generating.",
            },
            "workflow_json": {
                "type": "string",
                "description": (
                    "Optional full ComfyUI workflow JSON. Routes to a custom-workflow-capable "
                    "provider (e.g. comfyui_image) based on server availability, not bundled "
                    "model readiness. Requires output_node."
                ),
            },
            "workflow_path": {
                "type": "string",
                "description": (
                    "Optional path to a ComfyUI workflow JSON file. Routes to a custom-workflow-"
                    "capable provider based on server availability. Requires output_node."
                ),
            },
            "output_node": {
                "type": "string",
                "description": "ComfyUI output node ID for a custom workflow_json/workflow_path.",
            },
            "workflow_name": {
                "type": "string",
                "description": "Optional human-readable provenance label for a custom workflow.",
            },
            "workflow_model": {
                "type": "string",
                "description": "Optional model/provenance label for a custom workflow.",
            },
            "workflow_model_stack": {
                "type": "array",
                "items": {"type": "object"},
                "description": "Optional provenance metadata for custom workflow dependencies.",
            },
            "output_path": {"type": "string"},
        },
        "anyOf": [
            {"required": ["output_path"]},
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
            "rankings": {
                "type": "array",
                "items": {"type": "object"},
            },
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
        """Auto-discover image generation providers from the registry."""
        from tools.tool_registry import registry
        registry.ensure_discovered()
        return [t for t in registry.get_by_capability("image_generation")
                if t.name != self.name]

    @property
    def fallback_tools(self) -> list[str]:
        """Dynamically built from discovered providers."""
        return [t.name for t in self._providers()]

    @property
    def provider_matrix(self) -> dict[str, dict[str, str]]:
        """Built at runtime from each provider's best_for field."""
        matrix = {}
        for tool in self._providers():
            info = safe_tool_info(tool)
            best_for = info.get("best_for") or []
            strength = ", ".join(best_for) if best_for else str(info.get("name", tool.name))
            matrix[safe_tool_provider(tool)] = {"tool": tool.name, "strength": strength}
        return matrix

    def get_status(self) -> ToolStatus:
        if any(is_tool_available(tool) for tool in self._providers()):
            return ToolStatus.AVAILABLE
        return ToolStatus.UNAVAILABLE

    def estimate_cost(self, inputs: dict[str, Any]) -> float:
        original_inputs = dict(inputs)
        inputs = apply_model_preferences(original_inputs, self.capability)
        candidates = self._providers()
        inputs = self._relax_incompatible_env_model_default(
            original_inputs,
            inputs,
            candidates,
        )
        if not candidates:
            return 0.0
        tool, _ = self._select_best_tool(inputs, candidates, self._prepare_task_context(inputs))
        return tool.estimate_cost(inputs) if tool else 0.0

    def idempotency_key(self, inputs: dict[str, Any]) -> str:
        return super().idempotency_key(
            apply_model_preferences(dict(inputs), self.capability)
        )

    def execute(self, inputs: dict[str, Any]) -> ToolResult:
        import logging
        from lib.scoring import rank_providers

        original_inputs = dict(inputs)
        inputs = apply_model_preferences(original_inputs, self.capability)
        if inputs.get("operation") != "rank":
            _, output_error = require_explicit_output_path(
                inputs, self.name, artifact_label="generated image"
            )
            if output_error:
                return output_error

        logger = logging.getLogger(__name__)
        providers = self._providers()
        inputs = self._relax_incompatible_env_model_default(
            original_inputs,
            inputs,
            providers,
        )
        task_context = self._prepare_task_context(inputs)
        wants_edit = self._wants_edit(inputs)
        candidates = self._filter_candidates(inputs, providers)

        # Rank mode — return scored provider rankings without generating
        if inputs.get("operation") == "rank":
            candidates = _allowed_candidates(inputs, candidates)
            rankings = rank_providers(candidates, task_context)
            return ToolResult(
                success=True,
                data={
                    "rankings": self._serialize_rankings(candidates, rankings),
                    "explanation": "\n".join(r.explain() for r in rankings[:5]),
                    "normalized_task_context": task_context,
                },
            )

        # Normal generation — use scored selection
        tool, score = self._select_best_tool(inputs, candidates, task_context)
        if tool is None:
            if wants_edit:
                return ToolResult(success=False, error="No edit-capable image provider available.")
            return ToolResult(success=False, error="No image provider available.")

        _, output_error = require_explicit_output_path(
            inputs, self.name, artifact_label="generated image"
        )
        if output_error:
            return output_error

        # Adapt input keys: stock tools use 'query' while generators use 'prompt'
        adapted = dict(inputs)
        if hasattr(tool, 'input_schema'):
            props = tool.input_schema.get("properties", {})
            if "query" in props and "query" not in adapted:
                adapted["query"] = adapted.get("prompt", "")

        # Strip selector-only keys that downstream tools don't understand
        adapted.pop("preferred_provider", None)
        adapted.pop("allowed_providers", None)

        if hasattr(tool, 'input_schema'):
            props = tool.input_schema.get("properties", {})
            operation = adapted.get("operation")
            if operation == "generate" and "operation" in props:
                adapted["operation"] = "text_to_image"

            if adapted.get("generation_mode") == "edit":
                ref_images = []
                has_extra_refs = bool(adapted.get("image_urls") or adapted.get("image_paths"))
                if has_extra_refs:
                    if adapted.get("image_url"):
                        ref_images.append(adapted["image_url"])
                    if adapted.get("image_path"):
                        ref_images.append(adapted["image_path"])
                ref_images.extend(adapted.get("image_urls") or [])
                ref_images.extend(adapted.get("image_paths") or [])

                if ref_images and "ref_images" in props:
                    adapted["ref_images"] = ref_images
                    adapted["operation"] = "multi_image_reference"
                else:
                    if adapted.get("image_url") and "base_image_url" in props:
                        adapted["base_image_url"] = adapted["image_url"]
                    if adapted.get("image_path") and "base_image_path" in props:
                        adapted["base_image_path"] = adapted["image_path"]
                    if "operation" in props:
                        adapted["operation"] = "image_editing"

            adapted.pop("generation_mode", None)

        # Pass through generation params only to tools that accept them.
        if hasattr(tool, 'input_schema'):
            props = tool.input_schema.get("properties", {})
            stripped = []
            for passthrough_key in (
                "negative_prompt",
                "width",
                "height",
                "seed",
                "n",
                "aspect_ratio",
                "resolution",
                "generation_mode",
                "image_url",
                "image_path",
                "image_urls",
                "image_paths",
                "model",
                "workflow_json",
                "workflow_path",
                "output_node",
                "workflow_name",
                "workflow_model",
                "workflow_model_stack",
            ):
                if passthrough_key in adapted and passthrough_key not in props:
                    stripped.append(f"{passthrough_key}={adapted.pop(passthrough_key)}")
            if stripped:
                logger.warning(
                    "image_selector: stripped unsupported params for %s: %s",
                    tool.name, ", ".join(stripped),
                )

        result = tool.execute(adapted)
        if result.success:
            result.data.setdefault("selected_tool", tool.name)
            selected_provider = safe_tool_provider(tool)
            result.data["selected_provider"] = selected_provider
            result.data["selection_reason"] = score.explain() if score else f"Selected {selected_provider} ({tool.name})"
            if score:
                result.data["provider_score"] = score.to_dict()
            result.data.update(self._tool_context_payload(tool))
            result.data["alternatives_considered"] = [
                t.name for t in candidates
                if t.name != tool.name and self._tool_selectable(t, inputs)
            ]
        return result

    def _select_best_tool(
        self,
        inputs: dict[str, Any],
        candidates: list[BaseTool],
        task_context: dict[str, Any],
    ) -> tuple[BaseTool | None, object]:
        """Select the best provider using scored ranking."""
        from lib.scoring import rank_providers

        preferred = inputs.get("preferred_provider", "auto")
        candidates = _allowed_candidates(inputs, candidates)
        candidates = self._filter_candidates(inputs, candidates)

        rankings = rank_providers(candidates, task_context)

        available_by_name: dict[str, BaseTool] = {}
        for tool in candidates:
            if self._tool_selectable(tool, inputs):
                available_by_name[tool.name] = tool

        if preferred != "auto":
            for score_item in rankings:
                if score_item.provider == preferred or score_item.tool_name == preferred:
                    tool = available_by_name.get(score_item.tool_name)
                    if tool is not None:
                        return tool, score_item
            return None, None

        for score_item in rankings:
            tool = available_by_name.get(score_item.tool_name)
            if tool is not None:
                return tool, score_item

        return None, None

    def _prepare_task_context(self, inputs: dict[str, Any]) -> dict[str, Any]:
        from lib.scoring import normalize_task_context

        return normalize_task_context(
            inputs.get("task_context", {}),
            prompt=inputs.get("prompt", ""),
            capability=self.capability,
            operation=inputs.get("generation_mode", inputs.get("operation", "generate")),
        )

    @staticmethod
    def _tool_context_payload(tool: BaseTool) -> dict[str, Any]:
        info = safe_tool_info(tool)
        return {
            "selected_tool_agent_skills": info.get("agent_skills", []),
            "required_agent_skills": info.get("agent_skills", []),
            "selected_tool_usage_location": info.get("usage_location"),
            "selected_tool_best_for": info.get("best_for", []),
            "selected_tool_model_options": info.get("model_options", []),
        }

    def _serialize_rankings(self, candidates: list[BaseTool], rankings: list[object]) -> list[dict[str, Any]]:
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

    @staticmethod
    def _wants_edit(inputs: dict[str, Any]) -> bool:
        return (
            inputs.get("generation_mode") == "edit"
            or inputs.get("image_url")
            or inputs.get("image_path")
            or inputs.get("image_urls")
            or inputs.get("image_paths")
        )

    def _filter_candidates(self, inputs: dict[str, Any], candidates: list[BaseTool]) -> list[BaseTool]:
        # A caller-supplied custom workflow is provider-specific (ComfyUI graph
        # JSON). Route it only to custom-workflow-capable providers whose server
        # is reachable; bundled-model readiness is irrelevant in that case.
        if self._has_custom_workflow(inputs):
            return [t for t in candidates if self._custom_workflow_eligible(t, inputs)]

        return filter_model_candidates(
            inputs,
            self.capability,
            self._capability_candidates(inputs, candidates),
        )

    def _relax_incompatible_env_model_default(
        self,
        original_inputs: dict[str, Any],
        inputs: dict[str, Any],
        candidates: list[BaseTool],
    ) -> dict[str, Any]:
        """Drop an env-only image model default when it blocks edit routing."""
        if "model" in original_inputs or not self._wants_edit(inputs):
            return inputs

        model = _selector_model_value(inputs)
        if model is None:
            return inputs

        edit_candidates = self._capability_candidates(inputs, candidates)
        if not edit_candidates:
            return inputs
        if filter_model_candidates(inputs, self.capability, edit_candidates):
            return inputs

        relaxed = dict(inputs)
        relaxed.pop("model", None)
        if self._capability_candidates(relaxed, candidates):
            return relaxed
        return inputs

    def _capability_candidates(
        self,
        inputs: dict[str, Any],
        candidates: list[BaseTool],
    ) -> list[BaseTool]:
        wants_edit = self._wants_edit(inputs)
        if not wants_edit:
            return list(candidates)

        filtered: list[BaseTool] = []
        for tool in candidates:
            props = getattr(tool, "input_schema", {}).get("properties", {})
            supports = getattr(tool, "supports", {})
            if supports.get("image_edit") or any(
                key in props for key in (
                    "image",
                    "images",
                    "image_url",
                    "image_path",
                    "image_urls",
                    "image_paths",
                    "base_image_url",
                    "base_image_path",
                    "ref_images",
                )
            ):
                filtered.append(tool)
        return filtered
        return filtered

    @staticmethod
    def _has_custom_workflow(inputs: dict[str, Any]) -> bool:
        return bool(inputs.get("workflow_json") or inputs.get("workflow_path"))

    def _custom_workflow_eligible(self, tool: BaseTool, inputs: dict[str, Any]) -> bool:
        """Whether a tool can run the caller-supplied custom workflow."""
        if not self._has_custom_workflow(inputs):
            return False
        if not inputs.get("output_node"):
            return False
        supports = getattr(tool, "supports", {})
        if not supports.get("custom_workflow"):
            return False
        return tool.get_status() != ToolStatus.UNAVAILABLE

    def _tool_selectable(self, tool: BaseTool, inputs: dict[str, Any]) -> bool:
        """Select AVAILABLE tools, plus reachable custom-workflow providers."""
        if is_tool_available(tool):
            return True
        return self._custom_workflow_eligible(tool, inputs)


def _allowed_candidates(
    inputs: dict[str, Any],
    candidates: list[BaseTool],
) -> list[BaseTool]:
    allowed = set(inputs.get("allowed_providers") or [])
    if not allowed:
        return candidates
    return [
        tool for tool in candidates
        if safe_tool_provider(tool) in allowed or tool.name in allowed
    ]


def _selector_model_value(inputs: dict[str, Any]) -> str | None:
    value = inputs.get("model")
    if value is None:
        return None
    value = str(value).strip()
    return value or None
