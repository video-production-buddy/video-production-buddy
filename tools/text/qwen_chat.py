"""Qwen large-language-model chat via Alibaba Cloud Bailian / DashScope.

OpenAI-compatible Chat Completions endpoint. Drives the latest Qwen text models
(qwen3.7-max flagship, qwen3.7-plus balanced, qwen3.6-flash low-cost). Uses
DASHSCOPE_API_KEY.

Endpoint: POST https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions
Auth:     Authorization: Bearer DASHSCOPE_API_KEY

This is a standalone capability tool — the agent (harness) remains the primary
reasoner; this tool is for ad-hoc text sub-tasks the agent chooses to route to a
billed LLM call (e.g. bulk script polishing, translation, summarization). It is
NOT auto-wired into any pipeline stage.
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any

from tools.base_tool import (
    BaseTool,
    Determinism,
    ExecutionMode,
    ResourceProfile,
    RetryPolicy,
    ToolResult,
    ToolRuntime,
    ToolStability,
    ToolStatus,
    ToolTier,
)
from tools.model_options import build_model_options
from tools.output_paths import require_optional_project_sidecar_path

_CHAT_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"

_MODELS: dict[str, dict[str, Any]] = {
    "qwen3.7-max": {
        "name": "Qwen3.7 Max",
        "quality": "highest",
        "speed": "medium",
        "context": 262144,
        "note": "Strongest reasoning / complex tasks (flagship)",
    },
    "qwen3.7-plus": {
        "name": "Qwen3.7 Plus",
        "quality": "high",
        "speed": "medium",
        "context": 1000000,
        "note": "Balanced capability/cost; 1M context; tool calling",
    },
    "qwen3.6-flash": {
        "name": "Qwen3.6 Flash",
        "quality": "medium",
        "speed": "fast",
        "context": 1000000,
        "note": "High-throughput, low-cost",
    },
    "qwen3-coder-plus": {
        "name": "Qwen3 Coder Plus",
        "quality": "high",
        "speed": "medium",
        "context": 262144,
        "note": "Code / agentic coding",
    },
}


class QwenChat(BaseTool):
    name = "qwen_chat"
    version = "0.1.0"
    tier = ToolTier.GENERATE
    capability = "text_generation"
    provider = "bailian"
    stability = ToolStability.BETA
    execution_mode = ExecutionMode.SYNC
    determinism = Determinism.STOCHASTIC
    runtime = ToolRuntime.API

    dependencies = ["env:DASHSCOPE_API_KEY"]
    install_instructions = (
        "Set the DASHSCOPE_API_KEY environment variable:\n"
        "  export DASHSCOPE_API_KEY=your_key_here\n"
        "Get a key at https://bailian.console.aliyun.com/"
    )
    fallback_tools = ["minimax_chat"]
    agent_skills = ["text-generation"]

    capabilities = ["chat", "text_generation", "summarization", "translation", "tool_calling"]
    supports = {
        "streaming": False,
        "tool_calling": True,
        "multimodal": False,
        "long_context": True,
        "offline": False,
    }
    best_for = [
        "Ad-hoc text sub-tasks routed to a billed Qwen call (script polish, translation, summarization)",
        "Long-context document/script analysis via qwen3.7-plus (1M tokens)",
        "Strongest reasoning via qwen3.7-max",
        "Code generation via qwen3-coder-plus",
    ]
    not_good_for = [
        "Replacing the agent's own reasoning (the harness is the primary reasoner)",
        "Multimodal image/video understanding (use qwen_vl instead)",
    ]
    model_options = build_model_options(
        _MODELS,
        field="model",
        default="qwen3.7-plus",
        include_keys=("quality", "speed", "context", "note"),
    )

    input_schema = {
        "type": "object",
        "anyOf": [
            {"required": ["messages"]},
            {"required": ["prompt"]},
        ],
        "properties": {
            "messages": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["role", "content"],
                    "properties": {
                        "role": {"type": "string", "enum": ["system", "user", "assistant"]},
                        "content": {"type": "string"},
                    },
                },
                "description": "OpenAI-style chat messages. Alternative to system+prompt.",
            },
            "system": {
                "type": "string",
                "description": "Optional system prompt (used when building messages from system+prompt)",
            },
            "prompt": {
                "type": "string",
                "description": "User prompt (alternative to passing full messages)",
            },
            "model": {
                "type": "string",
                "enum": list(_MODELS.keys()),
                "default": "qwen3.7-plus",
            },
            "temperature": {"type": "number", "default": 0.7, "minimum": 0.0, "maximum": 2.0},
            "max_tokens": {"type": "integer", "default": 4096, "minimum": 1},
            "output_path": {
                "type": "string",
                "description": "Optional project-scoped path to write the response text (e.g. .../artifacts/x.md).",
            },
        },
    }
    output_schema = {
        "type": "object",
        "required": [
            "provider",
            "model",
            "model_name",
            "text",
            "prompt_tokens",
            "completion_tokens",
            "total_tokens",
            "output",
            "output_path",
        ],
        "properties": {
            "provider": {"type": "string"},
            "model": {"type": "string", "enum": list(_MODELS.keys())},
            "model_name": {"type": "string"},
            "text": {"type": "string"},
            "prompt_tokens": {"type": ["integer", "null"]},
            "completion_tokens": {"type": ["integer", "null"]},
            "total_tokens": {"type": ["integer", "null"]},
            "output": {"type": ["string", "null"]},
            "output_path": {"type": ["string", "null"]},
        },
    }

    resource_profile = ResourceProfile(
        cpu_cores=1, ram_mb=256, vram_mb=0, disk_mb=10, network_required=True
    )
    retry_policy = RetryPolicy(max_retries=2, retryable_errors=["rate_limit", "timeout"])
    idempotency_key_fields = ["messages", "system", "prompt", "model", "temperature", "max_tokens", "output_path"]
    side_effects = ["calls Bailian/DashScope Chat Completions API", "optionally writes response text to output_path"]
    user_visible_verification = ["Read the generated text for relevance, accuracy, and tone fit"]

    def _get_api_key(self) -> str | None:
        return os.environ.get("DASHSCOPE_API_KEY")

    def get_status(self) -> ToolStatus:
        if self._get_api_key():
            return ToolStatus.AVAILABLE
        return ToolStatus.UNAVAILABLE

    def estimate_cost(self, inputs: dict[str, Any]) -> float:
        # Rough: ~$0.002 per 1k output tokens for plus-tier; used only for budget display.
        out_tokens = inputs.get("max_tokens", 4096)
        return round(out_tokens / 1000 * 0.002, 5)

    def execute(self, inputs: dict[str, Any]) -> ToolResult:
        model = inputs.get("model", "qwen3.7-plus")
        if model not in _MODELS:
            return ToolResult(success=False, error=f"Unsupported model {model!r}.")

        output_path, output_error = require_optional_project_sidecar_path(
            inputs, "output_path", self.name, artifact_label="chat response"
        )
        if output_error:
            return output_error

        messages = self._build_messages(inputs)
        if isinstance(messages, ToolResult):
            return messages

        api_key = self._get_api_key()
        if not api_key:
            return ToolResult(success=False, error="DASHSCOPE_API_KEY not set. " + self.install_instructions)

        import requests

        start = time.time()
        payload = {
            "model": model,
            "messages": messages,
            "temperature": inputs.get("temperature", 0.7),
            "max_tokens": inputs.get("max_tokens", 4096),
        }
        try:
            resp = requests.post(
                _CHAT_URL,
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json=payload,
                timeout=180,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            return ToolResult(success=False, error=f"Qwen chat request failed: {exc}")

        text = self._extract_text(data)
        if text is None:
            return ToolResult(success=False, error=f"No completion in response: {data}")

        out_str: str | None = None
        if output_path is not None:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(text, encoding="utf-8")
            out_str = str(output_path)

        usage = data.get("usage", {})
        return ToolResult(
            success=True,
            data={
                "provider": self.provider,
                "model": model,
                "model_name": _MODELS[model]["name"],
                "text": text,
                "prompt_tokens": usage.get("prompt_tokens"),
                "completion_tokens": usage.get("completion_tokens"),
                "total_tokens": usage.get("total_tokens"),
                "output": out_str,
                "output_path": out_str,
            },
            artifacts=[out_str] if out_str else [],
            cost_usd=self.estimate_cost(inputs),
            duration_seconds=round(time.time() - start, 2),
            model=model,
        )

    @staticmethod
    def _build_messages(inputs: dict[str, Any]) -> list[dict[str, str]] | ToolResult:
        messages = inputs.get("messages")
        if messages:
            return list(messages)
        prompt = inputs.get("prompt")
        if not prompt:
            return ToolResult(
                success=False, error="qwen_chat requires either 'messages' or 'prompt'."
            )
        msgs: list[dict[str, str]] = []
        system = inputs.get("system")
        if system:
            msgs.append({"role": "system", "content": system})
        msgs.append({"role": "user", "content": prompt})
        return msgs

    @staticmethod
    def _extract_text(data: dict[str, Any]) -> str | None:
        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            return None
