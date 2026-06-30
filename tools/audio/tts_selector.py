"""Capability-level text-to-speech selector that chooses among provider tools.

Provider discovery is automatic — any BaseTool with capability="tts"
is picked up from the registry.  Adding a new TTS provider requires only creating
the tool file in tools/audio/; no changes to this selector are needed.
"""

from __future__ import annotations

from typing import Any

from lib.model_preferences import apply_model_preferences, filter_model_candidates
from tools.base_tool import BaseTool, ToolResult, ToolRuntime, ToolStability, ToolTier, ToolStatus
from tools.status_utils import (
    is_tool_available,
    safe_tool_info,
    safe_tool_provider,
    safe_tool_status,
)
from tools.output_paths import require_explicit_output_path


class TTSSelector(BaseTool):
    name = "tts_selector"
    version = "0.2.0"
    tier = ToolTier.VOICE
    capability = "tts"
    provider = "selector"
    stability = ToolStability.BETA
    runtime = ToolRuntime.HYBRID
    install_instructions = (
        "Routes to discovered TTS providers. Use provider_menu_summary() to see "
        "which local/API voices are configured and each provider's setup steps."
    )
    agent_skills = ["text-to-speech", "elevenlabs", "doubao-tts"]

    capabilities = [
        "text_to_speech",
        "provider_selection",
    ]
    supports = {
        "user_preference_routing": True,
        "offline_fallback": True,
        "multilingual": True,
    }
    best_for = [
        "preflight tool selection",
        "user-facing recommendation flows",
    ]
    side_effects = ["delegates generated speech audio write to output_path"]
    idempotency_key_fields = [
        "text",
        "voice_id",
        "model_id",
        "stability",
        "similarity_boost",
        "style",
        "output_format",
        "instructions",
        "speed",
        "output_path",
        "preferred_provider",
        "allowed_providers",
        "operation",
    ]

    input_schema = {
        "type": "object",
        "required": ["text"],
        "properties": {
            "text": {"type": "string"},
            "voice_id": {
                "type": "string",
                "description": "Provider-specific voice ID. Passed through to the selected TTS provider.",
            },
            "model_id": {
                "type": "string",
                "description": "TTS model to use (e.g. eleven_v3). Passed through to provider.",
            },
            "stability": {
                "type": "number", "minimum": 0, "maximum": 1,
                "description": "Voice stability (ElevenLabs). Lower = more expressive.",
            },
            "similarity_boost": {
                "type": "number", "minimum": 0, "maximum": 1,
                "description": "Voice similarity boost (ElevenLabs).",
            },
            "style": {
                "type": "number", "minimum": 0, "maximum": 1,
                "description": "Style exaggeration (ElevenLabs). Higher = more expressive.",
            },
            "instructions": {
                "type": "string",
                "description": "Provider-level delivery instructions for expressive narration when supported.",
            },
            "speaking_rate": {
                "type": "number",
                "minimum": 0.25,
                "maximum": 2.0,
                "description": "Google-style speakingRate control. Use speed for OpenAI/ElevenLabs-style controls.",
            },
            "speed": {
                "type": "number",
                "minimum": 0.25,
                "maximum": 4.0,
                "description": "Alias for speaking speed used by some providers.",
            },
            "pitch": {
                "type": "number",
                "minimum": -50,
                "maximum": 50,
                "description": "Provider-specific pitch control. Google TTS accepts -20..20; HeyGen-style providers may accept wider ranges.",
            },
            "input_type": {
                "type": "string",
                "enum": ["text", "ssml"],
                "default": "text",
                "description": "Use 'ssml' only when the selected provider supports tags such as <break>.",
            },
            "voice_performance": {
                "type": "object",
                "description": "Structured voice-performance plan or section delivery cues from the script artifact.",
            },
            "sample_mode": {
                "type": "boolean",
                "default": False,
                "description": "True when generating an approval sample before batch narration.",
            },
            "output_format": {
                "type": "string",
                "description": "Audio output format (e.g. mp3_44100_128). Passed through to provider.",
            },
            "instructions": {
                "type": "string",
                "description": "Optional delivery instructions passed through to providers that support them.",
            },
            "speed": {
                "type": "number",
                "minimum": 0.25,
                "maximum": 4.0,
                "description": "Speech speed multiplier passed through to providers that support it.",
            },
            "preferred_provider": {
                "type": "string",
                "description": "Provider name or 'auto'. Valid values are discovered at runtime from the registry.",
                "default": "auto",
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
        """Auto-discover TTS providers from the registry."""
        from tools.tool_registry import registry
        registry.ensure_discovered()
        return [t for t in registry.get_by_capability("tts")
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
        inputs = apply_model_preferences(dict(inputs), self.capability)
        candidates = self._providers()
        if not candidates:
            return 0.0
        tool, _ = self._select_best_tool(inputs, candidates, self._prepare_task_context(inputs))
        return tool.estimate_cost(self._provider_inputs(inputs, tool)) if tool else 0.0

    def idempotency_key(self, inputs: dict[str, Any]) -> str:
        return super().idempotency_key(
            apply_model_preferences(dict(inputs), self.capability)
        )

    def execute(self, inputs: dict[str, Any]) -> ToolResult:
        from lib.scoring import rank_providers

        inputs = apply_model_preferences(dict(inputs), self.capability)
        if inputs.get("operation") != "rank":
            _, output_error = require_explicit_output_path(
                inputs, self.name, artifact_label="generated speech audio"
            )
            if output_error:
                return output_error

        task_context = self._prepare_task_context(inputs)
        candidates = self._providers()

        # Rank mode — return scored provider rankings without generating
        if inputs.get("operation") == "rank":
            candidates = filter_model_candidates(
                inputs,
                self.capability,
                _allowed_candidates(inputs, candidates),
            )
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
            return ToolResult(success=False, error="No TTS provider available.")

        _, output_error = require_explicit_output_path(
            inputs, self.name, artifact_label="generated speech audio"
        )
        if output_error:
            return output_error

        result = tool.execute(self._provider_inputs(inputs, tool))
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
                if t.name != tool.name and is_tool_available(t)
            ]
        return result

    def _select_best_tool(
        self,
        inputs: dict[str, Any],
        candidates: list[BaseTool],
        task_context: dict[str, Any],
    ) -> tuple[BaseTool | None, object]:
        """Select the best TTS provider using scored ranking."""
        from lib.scoring import rank_providers

        preferred = inputs.get("preferred_provider", "auto")
        candidates = filter_model_candidates(
            inputs,
            self.capability,
            _allowed_candidates(inputs, candidates),
        )

        rankings = rank_providers(candidates, task_context)

        available_by_name: dict[str, BaseTool] = {}
        for tool in candidates:
            if is_tool_available(tool):
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

    def _provider_inputs(self, inputs: dict[str, Any], tool: BaseTool) -> dict[str, Any]:
        """Map selector-level fields to the selected provider's declared schema."""
        properties = getattr(tool, "input_schema", {}).get("properties", {})
        adapted = dict(inputs)

        if "voice" in properties and "voice" not in adapted and "voice_id" in adapted:
            adapted["voice"] = adapted["voice_id"]
        if "model" in properties and "model" not in adapted and "model_id" in adapted:
            adapted["model"] = adapted["model_id"]
        if "resource_id" in properties and "resource_id" not in adapted and "model_id" in adapted:
            adapted["resource_id"] = adapted["model_id"]

        output_format = adapted.get("output_format")
        if isinstance(output_format, str):
            if "format" in properties and "format" not in adapted:
                adapted["format"] = _format_for_provider(output_format)
            if "audio_encoding" in properties and "audio_encoding" not in adapted:
                adapted["audio_encoding"] = _audio_encoding_for_provider(output_format)

        return {key: value for key, value in adapted.items() if key in properties}

    def _prepare_task_context(self, inputs: dict[str, Any]) -> dict[str, Any]:
        from lib.scoring import normalize_task_context

        return normalize_task_context(
            inputs.get("task_context", {}),
            prompt=inputs.get("text", ""),
            capability=self.capability,
            operation=inputs.get("operation", "generate"),
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
                item["model_options"] = info.get("model_options", [])
                item["status"] = safe_tool_status(tool).value
            serialized.append(item)
        return serialized


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


def _format_for_provider(output_format: str) -> str:
    normalized = output_format.lower()
    if normalized.startswith("mp3"):
        return "mp3"
    if normalized.startswith("pcm"):
        return "pcm"
    if normalized in {"wav", "ogg_opus", "ogg"}:
        return normalized
    return normalized.split("_", 1)[0]


def _audio_encoding_for_provider(output_format: str) -> str:
    normalized = output_format.lower()
    if normalized.startswith("mp3"):
        return "MP3"
    if normalized.startswith("pcm") or normalized == "wav":
        return "LINEAR16"
    if normalized in {"ogg", "ogg_opus"}:
        return "OGG_OPUS"
    return output_format.upper()
