"""Qwen ASR via Alibaba Cloud Bailian / DashScope API.

Supports qwen3-asr-flash via the native DashScope multimodal-generation endpoint.
Input: audio URL or local file path. Output: transcribed text.

Endpoint: /api/v1/services/aigc/multimodal-generation/generation
Request: input.messages[0].content = [{"audio": url_or_b64}]
Response: output.choices[0].message.content[0].text
"""

from __future__ import annotations

import base64
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

_ASR_URL = (
    "https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation"
)

_MODELS: dict[str, dict[str, Any]] = {
    "qwen3-asr-flash": {
        "name": "Qwen3 ASR Flash",
        "quality": "high",
        "speed": "fast",
        "cost_per_hour": 0.68,
        "multilingual": True,
    },
}


class QwenASR(BaseTool):
    name = "qwen_asr"
    version = "0.1.0"
    tier = ToolTier.VOICE
    capability = "transcription"
    provider = "bailian"
    stability = ToolStability.BETA
    execution_mode = ExecutionMode.SYNC
    determinism = Determinism.DETERMINISTIC
    runtime = ToolRuntime.API

    dependencies = ["env:DASHSCOPE_API_KEY"]
    install_instructions = (
        "Set the DASHSCOPE_API_KEY environment variable:\n"
        "  export DASHSCOPE_API_KEY=your_key_here\n"
        "Get a key at https://bailian.console.aliyun.com/\n"
        "Enable qwen3-asr-flash in the Bailian console model list."
    )
    fallback = None
    fallback_tools = []
    agent_skills = ["speech-to-text"]

    capabilities = ["transcription", "multilingual_asr", "chinese_asr"]
    supports = {
        "multilingual": True,
        "chinese_optimized": True,
        "offline": False,
        "speaker_diarization": False,
        "word_timestamps": False,
    }
    best_for = [
        "Fast Chinese and multilingual audio transcription",
        "Low-latency speech-to-text for video pipeline narration review",
        "Batch transcription via URL-referenced audio files",
    ]
    not_good_for = ["speaker diarization", "word-level timestamps"]
    model_options = build_model_options(
        _MODELS,
        field="model",
        default="qwen3-asr-flash",
        cost_units={"cost_per_hour": "per_hour"},
        include_keys=("quality", "speed", "multilingual"),
    )

    input_schema = {
        "type": "object",
        "anyOf": [
            {"required": ["audio_url"]},
            {"required": ["audio_path"]},
        ],
        "properties": {
            "audio_url": {
                "type": "string",
                "minLength": 1,
                "description": "URL of the audio file to transcribe (mp3, wav, m4a, etc.)",
            },
            "audio_path": {
                "type": "string",
                "minLength": 1,
                "description": "Local audio file path (auto base64-encoded, used if audio_url not given)",
            },
            "model": {
                "type": "string",
                "default": "qwen3-asr-flash",
                "enum": list(_MODELS.keys()),
            },
            "output_path": {
                "type": "string",
                "description": (
                    "Optional project-scoped path to write the transcript as a .txt "
                    "sidecar, e.g. projects/<project-name>/artifacts/transcript.txt"
                ),
            },
        },
    }
    output_schema = {
        "type": "object",
        "required": [
            "provider",
            "model",
            "transcript",
            "language",
            "output",
            "output_path",
        ],
        "properties": {
            "provider": {"type": "string"},
            "model": {"type": "string", "enum": list(_MODELS.keys())},
            "transcript": {"type": "string"},
            "language": {"type": ["string", "null"]},
            "output": {"type": ["string", "null"]},
            "output_path": {"type": ["string", "null"]},
        },
    }

    resource_profile = ResourceProfile(
        cpu_cores=1, ram_mb=128, vram_mb=0, disk_mb=10, network_required=True
    )
    retry_policy = RetryPolicy(max_retries=2, retryable_errors=["rate_limit", "timeout"])
    idempotency_key_fields = ["audio_url", "audio_path", "model", "output_path"]
    side_effects = ["calls Bailian/DashScope API", "optionally writes transcript to output_path"]
    user_visible_verification = ["Read transcript for accuracy and completeness"]

    def _get_api_key(self) -> str | None:
        return os.environ.get("DASHSCOPE_API_KEY")

    def get_status(self) -> ToolStatus:
        if self._get_api_key():
            return ToolStatus.AVAILABLE
        return ToolStatus.UNAVAILABLE

    def estimate_cost(self, inputs: dict[str, Any]) -> float:
        return 0.0  # per-hour pricing; duration unknown at estimate time

    def execute(self, inputs: dict[str, Any]) -> ToolResult:
        output_path, output_error = require_optional_project_sidecar_path(
            inputs,
            "output_path",
            self.name,
            artifact_label="transcript output",
        )
        if output_error:
            return output_error

        validated_inputs = dict(inputs)
        if output_path is not None:
            validated_inputs["output_path"] = str(output_path)

        api_key = self._get_api_key()
        if not api_key:
            return ToolResult(
                success=False,
                error="DASHSCOPE_API_KEY not set. " + self.install_instructions,
            )

        start = time.time()
        model = validated_inputs.get("model", "qwen3-asr-flash")

        audio_ref = validated_inputs.get("audio_url") or ""
        if not audio_ref and validated_inputs.get("audio_path"):
            audio_ref = self._file_to_b64(validated_inputs["audio_path"]) or ""
        if not audio_ref:
            return ToolResult(success=False, error="audio_url or audio_path required")

        try:
            result = self._transcribe(validated_inputs, api_key, model, audio_ref)
        except Exception as exc:
            return ToolResult(success=False, error=f"Qwen ASR failed: {exc}")

        result.duration_seconds = round(time.time() - start, 2)
        return result

    def _transcribe(
        self, inputs: dict[str, Any], api_key: str, model: str, audio_ref: str
    ) -> ToolResult:
        import requests

        payload = {
            "model": model,
            "input": {
                "messages": [
                    {
                        "role": "user",
                        "content": [{"audio": audio_ref}],
                    }
                ]
            },
        }

        resp = requests.post(
            _ASR_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=120,
        )
        resp.raise_for_status()
        data = resp.json()

        transcript = (
            data.get("output", {})
            .get("choices", [{}])[0]
            .get("message", {})
            .get("content", [{}])[0]
            .get("text", "")
        )
        if not transcript:
            raise ValueError(f"No transcript in response: {data}")

        output_path_str = inputs.get("output_path")
        if output_path_str:
            out = Path(output_path_str)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(transcript, encoding="utf-8")

        annotations = (
            data.get("output", {})
            .get("choices", [{}])[0]
            .get("message", {})
            .get("annotations", [])
        )
        lang = next((a.get("language") for a in annotations if a.get("type") == "audio_info"), None)

        artifacts = [output_path_str] if output_path_str else []
        return ToolResult(
            success=True,
            data={
                "provider": self.provider,
                "model": model,
                "transcript": transcript,
                "language": lang,
                "output": output_path_str,
                "output_path": output_path_str,
            },
            artifacts=artifacts,
            model=model,
        )

    def _file_to_b64(self, path_str: str | None) -> str | None:
        if not path_str:
            return None
        path = Path(path_str)
        if not path.exists():
            return None
        suffix = path.suffix.lower().lstrip(".")
        mime_map = {
            "mp3": "audio/mpeg",
            "wav": "audio/wav",
            "m4a": "audio/mp4",
            "flac": "audio/flac",
            "ogg": "audio/ogg",
        }
        mime = mime_map.get(suffix, "audio/mpeg")
        return f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode()}"
