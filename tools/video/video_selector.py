"""Capability-level video selector that routes between generation and stock providers.

Provider discovery is automatic — any BaseTool with capability="video_generation"
is picked up from the registry.  Adding a new video provider requires only creating
the tool file in tools/video/; no changes to this selector are needed.
"""

from __future__ import annotations

import os
from typing import Mapping

from lib.model_preferences import apply_model_preferences, filter_model_candidates
from tools.base_tool import BaseTool, ToolResult, ToolRuntime, ToolStability, ToolStatus, ToolTier
from tools.status_utils import (
    is_tool_available,
    safe_tool_info,
    safe_tool_provider,
    safe_tool_status,
)
from tools.output_paths import require_explicit_output_path


class VideoSelector(BaseTool):
    name = "video_selector"
    version = "0.3.0"
    tier = ToolTier.GENERATE
    capability = "video_generation"
    provider = "selector"
    stability = ToolStability.BETA
    runtime = ToolRuntime.HYBRID
    install_instructions = (
        "Routes to discovered video providers. Use provider_menu_summary() to see "
        "configured cloud, local, and stock video options plus setup steps."
    )
    agent_skills = ["ai-video-gen", "create-video", "ltx2"]

    capabilities = [
        "text_to_video", "image_to_video", "stock_video",
        "provider_selection", "search_video", "download_video",
    ]
    supports = {
        "user_preference_routing": True,
        "offline_fallback": True,
        "reference_image": True,
        "stock_fallback": True,
    }
    best_for = [
        "preflight routing",
        "user-facing recommendation flows",
        "switching between cloud, local, and stock video tools",
    ]
    side_effects = ["delegates generated or sourced video write to output_path"]
    idempotency_key_fields = [
        "prompt",
        "preferred_provider",
        "allowed_providers",
        "model_variant",
        "model",
        "operation",
        "target_operation",
        "aspect_ratio",
        "duration",
        "reference_image_path",
        "reference_image_url",
        "reference_image_urls",
        "reference_image_paths",
        "image_url",
        "resolution",
        "output_path",
        "workflow_path",
    ]

    input_schema = {
        "type": "object",
        "required": ["prompt"],
        "properties": {
            "prompt": {"type": "string"},
            "preferred_provider": {
                "type": "string",
                "description": "Provider name or 'auto'. Valid values are discovered at runtime from the registry.",
                "default": "auto",
            },
            "model_variant": {
                "type": "string",
                "description": (
                    "Provider-specific model variant. Valid values are reported by "
                    "provider_menu_summary()['model_choices'] for the selected tool."
                ),
            },
            "model": {
                "type": "string",
                "description": (
                    "Alias for providers whose advertised model choice field is "
                    "'model' instead of 'model_variant'."
                ),
            },
            "allowed_providers": {"type": "array", "items": {"type": "string"}},
            "operation": {
                "type": "string",
                "enum": ["text_to_video", "image_to_video", "reference_to_video", "rank"],
                "default": "text_to_video",
            },
            "target_operation": {
                "type": "string",
                "enum": ["text_to_video", "image_to_video", "reference_to_video"],
                "description": (
                    "Generation operation to rank for when operation='rank'. "
                    "Without this, rank mode defaults to text_to_video."
                ),
                "default": "text_to_video",
            },
            "aspect_ratio": {
                "type": "string",
                "enum": ["16:9", "9:16", "1:1"],
                "default": "16:9",
                "description": "Video aspect ratio. Passed through to the selected provider.",
            },
            "duration": {
                "type": "string",
                "description": "Duration hint (e.g., '5', '10'). Passed through to the selected provider.",
            },
            "reference_image_path": {
                "type": "string",
                "description": "Local path to a reference image for image_to_video. Auto-uploaded if the provider requires a URL.",
            },
            "reference_image_url": {
                "type": "string",
                "description": "URL of a reference image for image_to_video.",
            },
            "reference_image_urls": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Reference image URLs for providers that support reference-conditioned video.",
            },
            "reference_image_paths": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Local reference image paths for providers that support reference-conditioned video.",
            },
            "image_url": {
                "type": "string",
                "description": "Alias for reference_image_url (used by some providers like Kling via fal.ai).",
            },
            "resolution": {
                "type": "string",
                "description": "Resolution hint for providers that support named output resolutions.",
            },
            "workflow_json": {
                "type": "string",
                "description": (
                    "Optional full ComfyUI workflow JSON. Routes to a custom-workflow-capable "
                    "provider (e.g. comfyui_video) based on server availability, not bundled "
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
        """Auto-discover video generation providers from the registry."""
        from tools.tool_registry import registry
        registry.ensure_discovered()
        return [t for t in registry.get_by_capability("video_generation")
                if t.name != self.name]

    @property
    def fallback_tools(self) -> list[str]:
        """Dynamically built from discovered providers + image_selector as last resort."""
        return [t.name for t in self._providers()] + ["image_selector"]

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

    def estimate_cost(self, inputs: dict[str, object]) -> float:
        original_inputs = dict(inputs)
        inputs = apply_model_preferences(original_inputs, self.capability)
        providers = self._providers()
        inputs = self._relax_incompatible_env_model_default(
            original_inputs, inputs, providers
        )
        candidates = self._filter_candidates(inputs, providers)
        if not candidates:
            return 0.0
        tool, _ = self._select_best_tool(inputs, candidates, self._prepare_task_context(inputs))
        if tool is None:
            return 0.0
        adapted, _ = self._provider_inputs(inputs, tool)
        return tool.estimate_cost(adapted)

    def estimate_runtime(self, inputs: dict[str, object]) -> float:
        original_inputs = dict(inputs)
        inputs = apply_model_preferences(original_inputs, self.capability)
        providers = self._providers()
        inputs = self._relax_incompatible_env_model_default(
            original_inputs, inputs, providers
        )
        candidates = self._operation_candidates(inputs, providers)
        if not candidates:
            return 0.0
        tool, _ = self._select_best_tool(inputs, candidates, self._prepare_task_context(inputs))
        if tool is None:
            return 0.0
        adapted, _ = self._provider_inputs(inputs, tool)
        return tool.estimate_runtime(adapted)

    def idempotency_key(self, inputs: dict[str, object]) -> str:
        return super().idempotency_key(
            apply_model_preferences(dict(inputs), self.capability)
        )

    def execute(self, inputs: dict[str, object]) -> ToolResult:
        from lib.scoring import rank_providers

        original_inputs = dict(inputs)
        inputs = apply_model_preferences(original_inputs, self.capability)
        if inputs.get("operation") != "rank":
            _, output_error = require_explicit_output_path(
                inputs, self.name, artifact_label="generated video"
            )
            if output_error:
                return output_error

        providers = self._providers()
        inputs = self._relax_incompatible_env_model_default(
            original_inputs, inputs, providers
        )
        task_context = self._prepare_task_context(inputs)
        requested_operation = self._requested_generation_operation(inputs)
        candidates = self._operation_candidates(inputs, providers)

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
        task_context = self._prepare_task_context(inputs)
        tool, score = self._select_best_tool(inputs, candidates, task_context)
        if tool is None:
            if requested_operation in {"image_to_video", "reference_to_video"}:
                return ToolResult(
                    success=False,
                    error=f"No {requested_operation} video provider available.",
                )
            return ToolResult(success=False, error="No video generation provider available.")

        _, output_error = require_explicit_output_path(
            inputs, self.name, artifact_label="generated video"
        )
        if output_error:
            return output_error

        adapted, adaptation_error = self._provider_inputs(
            inputs,
            tool,
            allow_upload=True,
        )
        if adaptation_error:
            return ToolResult(success=False, error=adaptation_error)

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
        inputs: dict[str, object],
        candidates: list[BaseTool],
        task_context: dict[str, object],
    ) -> tuple[BaseTool | None, object]:
        """Select the best provider using scored ranking.

        Respects preferred_provider and environment hints as tie-breakers,
        but the scoring engine drives the primary selection.
        """
        from lib.scoring import rank_providers, ProviderScore

        preferred = inputs.get("preferred_provider", "auto")
        candidates = _allowed_candidates(inputs, candidates)
        candidates = self._operation_candidates(inputs, candidates)

        env_hint = os.environ.get("VIDEO_GEN_LOCAL_MODEL", "").lower()
        env_map = {
            "wan2.1-1.3b": "wan",
            "wan2.1-14b": "wan",
            "hunyuan-1.5": "hunyuan",
            "ltx2-local": "ltx",
            "cogvideo-5b": "cogvideo",
            "cogvideo-2b": "cogvideo",
        }
        if preferred == "auto" and env_hint in env_map:
            preferred = env_map[env_hint]

        rankings = rank_providers(candidates, task_context)

        # Build lookup by concrete tool name. Multiple tools can share a
        # provider label, so mapping provider -> first tool would discard the
        # scorer's per-tool ranking.
        available_by_name: dict[str, BaseTool] = {}
        for tool in candidates:
            if self._tool_selectable(tool, inputs):
                available_by_name[tool.name] = tool

        # If a preferred provider is explicitly requested and available,
        # boost it to the top unless its score is drastically worse.
        if preferred != "auto":
            for score in rankings:
                if score.provider == preferred or score.tool_name == preferred:
                    tool = available_by_name.get(score.tool_name)
                    if tool is not None:
                        return tool, score
            return None, None

        # Return the highest-scored available provider
        for score in rankings:
            tool = available_by_name.get(score.tool_name)
            if tool is not None:
                return tool, score

        return None, None

    def _prepare_task_context(self, inputs: dict[str, object]) -> dict[str, object]:
        from lib.scoring import normalize_task_context

        return normalize_task_context(
            inputs.get("task_context", {}),
            prompt=str(inputs.get("prompt", "")),
            capability=self.capability,
            operation=self._requested_generation_operation(inputs),
        )

    def _relax_incompatible_env_model_default(
        self,
        original_inputs: dict[str, object],
        inputs: dict[str, object],
        candidates: list[BaseTool],
    ) -> dict[str, object]:
        """Drop an env-only model default when it conflicts with the operation."""
        if "model_variant" in original_inputs or "model" in original_inputs:
            return inputs

        model = _selector_model_value(inputs)
        if model is None:
            return inputs

        operation_candidates = self._filter_candidates(inputs, candidates)
        if filter_model_candidates(inputs, self.capability, operation_candidates):
            return inputs

        operation = self._requested_generation_operation(inputs)
        if not _model_known_but_incompatible(model, operation, operation_candidates):
            return inputs

        relaxed = dict(inputs)
        relaxed.pop("model_variant", None)
        relaxed.pop("model", None)
        if self._operation_candidates(relaxed, candidates):
            return relaxed
        return inputs

    def _provider_inputs(
        self,
        inputs: dict[str, object],
        tool: BaseTool,
        *,
        allow_upload: bool = False,
    ) -> tuple[dict[str, object], str | None]:
        """Map selector-level video fields to the selected provider schema."""
        adapted = dict(inputs)
        tool_props = getattr(tool, "input_schema", {}).get("properties", {})

        # Stock tools use query while generated-video providers use prompt.
        if "query" in tool_props and "query" not in adapted:
            adapted["query"] = adapted.get("prompt", "")

        if (
            "model" in tool_props
            and "model" not in adapted
            and "model_variant" in adapted
        ):
            adapted["model"] = adapted["model_variant"]
        if (
            "model_variant" in tool_props
            and "model_variant" not in adapted
            and "model" in adapted
        ):
            adapted["model_variant"] = adapted["model"]
        for model_key in ("model", "model_variant"):
            if model_key in adapted and model_key not in tool_props:
                adapted.pop(model_key)

        if adapted.get("operation") == "image_to_video":
            if adapted.get("reference_image_url") and "image_url" in tool_props:
                adapted.setdefault("image_url", adapted["reference_image_url"])

            if adapted.get("reference_image_path"):
                # Prefer a provider's native local-path input. Only generation
                # execution may upload to fal.ai for providers that require URLs.
                if "image_path" in tool_props:
                    adapted.setdefault("image_path", adapted["reference_image_path"])
                elif (
                    allow_upload
                    and "reference_image_path" not in tool_props
                    and "image_url" in tool_props
                ):
                    try:
                        from tools.video._shared import upload_image_fal

                        adapted["image_url"] = upload_image_fal(
                            adapted["reference_image_path"]
                        )
                    except Exception as exc:
                        return adapted, f"Failed to upload reference image: {exc}"

        if adapted.get("operation") == "reference_to_video" and "ref_images" in tool_props:
            ref_images = []
            ref_images.extend(adapted.get("reference_image_urls") or [])
            ref_images.extend(adapted.get("reference_image_paths") or [])
            if ref_images:
                adapted["ref_images"] = ref_images

        adapted.pop("preferred_provider", None)
        adapted.pop("allowed_providers", None)
        return adapted, None

    @staticmethod
    def _rank_inputs(inputs: dict[str, object]) -> dict[str, object]:
        rank_inputs = dict(inputs)
        rank_inputs["operation"] = inputs.get("target_operation", "text_to_video")
        return rank_inputs

    @staticmethod
    def _tool_context_payload(tool: BaseTool) -> dict[str, object]:
        info = safe_tool_info(tool)
        return {
            "selected_tool_agent_skills": info.get("agent_skills", []),
            "required_agent_skills": info.get("agent_skills", []),
            "selected_tool_usage_location": info.get("usage_location"),
            "selected_tool_best_for": info.get("best_for", []),
            "selected_tool_model_options": info.get("model_options", []),
        }

    def _serialize_rankings(self, candidates: list[BaseTool], rankings: list[object]) -> list[dict[str, object]]:
        tool_by_name = {tool.name: tool for tool in candidates}
        serialized: list[dict[str, object]] = []
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

    def _filter_candidates(
        self,
        inputs: dict[str, object],
        candidates: list[BaseTool],
    ) -> list[BaseTool]:
        # A caller-supplied custom workflow is provider-specific (ComfyUI graph
        # JSON). Route it only to custom-workflow-capable providers whose server
        # is reachable; bundled-model readiness is irrelevant in that case.
        if self._has_custom_workflow(inputs):
            return [t for t in candidates if self._custom_workflow_eligible(t, inputs)]

        operation = self._requested_generation_operation(inputs)
        if operation == "rank":
            operation = inputs.get("target_operation", "text_to_video")

        filtered: list[BaseTool] = []
        matched_operation = False
        for tool in candidates:
            supports = getattr(tool, "supports", {})
            props = getattr(tool, "input_schema", {}).get("properties", {})

            if operation == "image_to_video":
                if supports.get("image_to_video") or "image_url" in props or "reference_image_url" in props:
                    matched_operation = True
                    if self._operation_ready(tool, "image_to_video"):
                        filtered.append(tool)
                continue

            if operation == "reference_to_video":
                if supports.get("reference_to_video") or "reference_image_urls" in props:
                    matched_operation = True
                    filtered.append(tool)
                continue

            matched_operation = True
            if self._operation_ready(tool, str(operation)):
                filtered.append(tool)

        return filtered

    def _operation_candidates(
        self,
        inputs: dict[str, object],
        candidates: list[BaseTool],
    ) -> list[BaseTool]:
        return filter_model_candidates(
            inputs,
            self.capability,
            self._filter_candidates(inputs, candidates),
        )

    @staticmethod
    def _requested_generation_operation(inputs: dict[str, object]) -> str:
        operation = str(inputs.get("operation", "text_to_video"))
        if operation == "rank":
            return str(inputs.get("target_operation", "text_to_video"))
        return operation

    @staticmethod
    def _operation_ready(tool: BaseTool, operation: str) -> bool:
        checker = getattr(tool, "is_operation_available", None)
        if not callable(checker):
            return True
        return bool(checker(operation))

    @staticmethod
    def _has_custom_workflow(inputs: dict[str, object]) -> bool:
        return bool(inputs.get("workflow_json") or inputs.get("workflow_path"))

    def _custom_workflow_eligible(self, tool: BaseTool, inputs: dict[str, object]) -> bool:
        """Whether a tool can run the caller-supplied custom workflow."""
        if not self._has_custom_workflow(inputs):
            return False
        if not inputs.get("output_node"):
            return False
        supports = getattr(tool, "supports", {})
        if not supports.get("custom_workflow"):
            return False
        return tool.get_status() != ToolStatus.UNAVAILABLE

    def _tool_selectable(self, tool: BaseTool, inputs: dict[str, object]) -> bool:
        """Select AVAILABLE tools, plus reachable custom-workflow providers."""
        if is_tool_available(tool):
            return True
        return self._custom_workflow_eligible(tool, inputs)


def _allowed_candidates(
    inputs: dict[str, object],
    candidates: list[BaseTool],
) -> list[BaseTool]:
    allowed = set(inputs.get("allowed_providers") or [])
    if not allowed:
        return candidates
    return [
        tool for tool in candidates
        if safe_tool_provider(tool) in allowed or tool.name in allowed
    ]


def _selector_model_value(inputs: dict[str, object]) -> str | None:
    for field in ("model_variant", "model"):
        value = inputs.get(field)
        if value is not None:
            value = str(value).strip()
            if value:
                return value
    return None


def _model_known_but_incompatible(
    model: str,
    operation: str,
    candidates: list[BaseTool],
) -> bool:
    known = False
    compatible = False
    for tool in candidates:
        for option in getattr(tool, "model_options", None) or []:
            if not isinstance(option, Mapping):
                continue
            if str(option.get("field") or "model_variant") not in {
                "model_variant",
                "model",
            }:
                continue
            if str(option.get("id")) != model:
                continue
            known = True
            if _model_option_supports_operation(option, operation):
                compatible = True
    return known and not compatible


def _model_option_supports_operation(
    option: Mapping[str, object],
    operation: str,
) -> bool:
    option_operation = option.get("operation")
    if option_operation and str(option_operation) != operation:
        return False

    supports = option.get("supports")
    if isinstance(supports, Mapping):
        if supports.get(operation) is False:
            return False
        if operation == "text_to_video" and supports.get("supports_t2v") is False:
            return False
        if operation == "image_to_video" and supports.get("supports_i2v") is False:
            return False

    return True
