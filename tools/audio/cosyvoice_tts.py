"""Bailian TTS via Alibaba Cloud Bailian / DashScope API.

Supports qwen3-tts-flash and qwen3-tts-instruct-flash via the native DashScope
multimodal endpoint, and CosyVoice v3 models via the OpenAI-compatible
audio/speech endpoint.
Both use DASHSCOPE_API_KEY.
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

# ── Endpoints ─────────────────────────────────────────────────────────────────
# qwen3-tts-* uses the native multimodal generation endpoint.
_QWEN_TTS_URL = (
    "https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation"
)
# CosyVoice models work via the OpenAI-compatible audio/speech endpoint.
_COSYVOICE_URL = (
    "https://dashscope.aliyuncs.com/compatible-mode/v1/audio/speech"
)

# ── Model registry ─────────────────────────────────────────────────────────────
_MODELS: dict[str, dict[str, Any]] = {
    # Qwen3 TTS (newest, fastest)
    "qwen3-tts-flash": {
        "name": "Qwen3 TTS Flash",
        "family": "qwen",
        "quality": "high",
        "speed": "fast",
        "cost_per_char": 0.000014,
    },
    "qwen3-tts-instruct-flash": {
        "name": "Qwen3 TTS Instruct Flash",
        "family": "qwen",
        "quality": "high",
        "speed": "fast",
        "cost_per_char": 0.000014,
        "note": "Supports 'instructions' parameter for delivery style control",
    },
    # CosyVoice v3 (international: v3-flash/plus; China mainland: v3.5-flash/plus also available)
    "cosyvoice-v3-flash": {
        "name": "CosyVoice v3 Flash",
        "family": "cosyvoice",
        "quality": "high",
        "speed": "fast",
        "cost_per_char": 0.000014,
    },
    "cosyvoice-v3-plus": {
        "name": "CosyVoice v3 Plus",
        "family": "cosyvoice",
        "quality": "highest",
        "speed": "medium",
        "cost_per_char": 0.000020,
    },
    # CosyVoice v2 (legacy, kept for backward compat)
    "cosyvoice-v2": {
        "name": "CosyVoice v2 (legacy)",
        "family": "cosyvoice",
        "quality": "medium",
        "speed": "medium",
        "cost_per_char": 0.000010,
    },
}

# qwen3-tts-* voices (English names, verified against live API)
QWEN_VOICES: dict[str, str] = {
    "Cherry": "female, warm",
    "Ethan": "male, steady",
    "Serena": "female, gentle",
    "Dylan": "male, warm",
    "Kai": "male, clear",
}

# CosyVoice voices (used by cosyvoice-v3-* and cosyvoice-v2)
COSYVOICE_VOICES: dict[str, str] = {
    "longanyang": "male, warm — 龙安阳 (CosyVoice v3 default)",
    "longxiaochun": "female, gentle — 龙小淳",
    "longxiaoxia": "female, energetic — 龙小夏",
    "longxiaobai": "male, steady — 龙小白",
    "longxiaocheng": "male, deep — 龙小诚",
    "longxiaoman": "female, slow — 龙小慢",
    "longxiaoxuan": "female, bright — 龙小炫",
}

# Combined for schema description
VOICES: dict[str, str] = {**QWEN_VOICES, **COSYVOICE_VOICES}


class CosyVoiceTTS(BaseTool):
    name = "cosyvoice_tts"
    version = "0.3.0"
    tier = ToolTier.VOICE
    capability = "tts"
    provider = "bailian"
    stability = ToolStability.BETA
    execution_mode = ExecutionMode.SYNC
    determinism = Determinism.STOCHASTIC
    runtime = ToolRuntime.API

    dependencies = ["env:DASHSCOPE_API_KEY"]
    install_instructions = (
        "Set the DASHSCOPE_API_KEY environment variable:\n"
        "  export DASHSCOPE_API_KEY=your_key_here\n"
        "Get a key at https://bailian.console.aliyun.com/\n"
        "Enable the desired TTS model in the Bailian console model list."
    )
    fallback = "google_tts"
    fallback_tools = ["google_tts", "piper_tts"]
    agent_skills = ["text-to-speech"]

    capabilities = ["text_to_speech", "voice_selection", "chinese_language"]
    supports = {
        "voice_cloning": False,
        "multilingual": True,
        "offline": False,
        "native_audio": True,
        "chinese_optimized": True,
    }
    best_for = [
        "Chinese-language narration with natural Mandarin pronunciation",
        "English narration for Chinese-style productions — Dylan (warm baritone), Ethan (steady), Kai (clear)",
        "bilingual Chinese/English video production",
        "first fallback when ElevenLabs is unavailable — uses DASHSCOPE_API_KEY already set for Wan video generation",
        "fast low-cost TTS via qwen3-tts-flash",
        "delivery-controlled ad narration via qwen3-tts-instruct-flash",
    ]
    not_good_for = ["fully offline production", "voice clone matching"]

    input_schema = {
        "type": "object",
        "required": ["text"],
        "properties": {
            "text": {"type": "string", "description": "Text to convert to speech"},
            "voice": {
                "type": "string",
                "default": "Cherry",
                "description": (
                    "Voice name. qwen3-tts-*: Cherry, Ethan, Serena, Dylan, Kai. "
                    "cosyvoice-*: longanyang, longxiaochun, longxiaoxia, longxiaobai, etc."
                ),
            },
            "model": {
                "type": "string",
                "default": "qwen3-tts-flash",
                "enum": list(_MODELS.keys()),
            },
            "speed": {
                "type": "number",
                "default": 1.0,
                "minimum": 0.5,
                "maximum": 2.0,
                "description": "Speech speed multiplier (speech_rate for CosyVoice)",
            },
            "language_type": {
                "type": "string",
                "default": "auto",
                "enum": [
                    "auto", "Chinese", "English", "German", "Italian",
                    "Portuguese", "Spanish", "Japanese", "Korean", "French", "Russian",
                ],
                "description": "Language hint for qwen3-tts models",
            },
            "instructions": {
                "type": "string",
                "description": "Delivery style instructions (qwen3-tts-instruct-flash only, max 1600 tokens)",
            },
            "format": {
                "type": "string",
                "default": "mp3",
                "enum": ["mp3", "wav"],
            },
            "output_path": {"type": "string"},
        },
    }

    resource_profile = ResourceProfile(
        cpu_cores=1, ram_mb=256, vram_mb=0, disk_mb=50, network_required=True
    )
    retry_policy = RetryPolicy(max_retries=2, retryable_errors=["rate_limit", "timeout"])
    idempotency_key_fields = [
        "text",
        "voice",
        "model",
        "speed",
        "language_type",
        "instructions",
        "format",
        "output_path",
    ]
    side_effects = ["writes audio file to output_path", "calls Bailian/DashScope API"]
    user_visible_verification = ["Listen to generated audio for natural speech quality"]

    def _get_api_key(self) -> str | None:
        return os.environ.get("DASHSCOPE_API_KEY")

    def get_status(self) -> ToolStatus:
        if self._get_api_key():
            return ToolStatus.AVAILABLE
        return ToolStatus.UNAVAILABLE

    def estimate_cost(self, inputs: dict[str, Any]) -> float:
        model = inputs.get("model", "qwen3-tts-flash")
        cost_per_char = _MODELS.get(model, _MODELS["qwen3-tts-flash"])["cost_per_char"]
        return round(len(inputs.get("text", "")) * cost_per_char, 5)

    def execute(self, inputs: dict[str, Any]) -> ToolResult:
        api_key = self._get_api_key()
        if not api_key:
            return ToolResult(
                success=False,
                error="DASHSCOPE_API_KEY not set. " + self.install_instructions,
            )

        start = time.time()
        model = inputs.get("model", "qwen3-tts-flash")
        if model not in _MODELS:
            return ToolResult(success=False, error=f"Unsupported model {model!r}.")
        family = _MODELS[model].get("family", "qwen")

        # Honor self.retry_policy. Retry on exceptions whose str(exc) contains
        # any retryable_errors pattern as a substring; surface non-retryable
        # errors immediately. Backoff doubles each attempt.
        # Future: lift into BaseTool as a template-method so every tool with a
        # non-zero retry_policy retries automatically.
        max_attempts = self.retry_policy.max_retries + 1
        for attempt in range(max_attempts):
            try:
                if family == "qwen":
                    result = self._generate_qwen(inputs, api_key, model)
                else:
                    result = self._generate_cosyvoice(inputs, api_key, model)
                result.duration_seconds = round(time.time() - start, 2)
                result.cost_usd = self.estimate_cost(inputs)
                return result
            except Exception as exc:
                err = str(exc)
                is_retryable = any(pat in err for pat in self.retry_policy.retryable_errors)
                if not is_retryable or attempt >= max_attempts - 1:
                    return ToolResult(success=False, error=f"Bailian TTS failed: {exc}")
                time.sleep(self.retry_policy.backoff_seconds * (2 ** attempt))

        # Defensive: every path above returns; reaching here means a logic bug.
        return ToolResult(success=False, error="Bailian TTS failed: retry loop exhausted unexpectedly")

    @staticmethod
    def _ensure_audio_format(content: bytes, fmt: str, output_path: Path) -> str:
        """Write audio bytes to output_path, transcoding if the content format doesn't match fmt.

        TTS APIs sometimes return WAV (RIFF header) regardless of the requested format.
        This helper detects the actual container from magic bytes and transcodes via FFmpeg
        when there is a mismatch, so the output file extension always matches its content.

        Returns the actual detected format of the received bytes (may differ from fmt).
        """
        import subprocess
        import tempfile

        is_wav = len(content) >= 12 and content[:4] == b"RIFF" and content[8:12] == b"WAVE"
        actual_fmt = "wav" if is_wav else fmt

        if actual_fmt != fmt:
            tmp = tempfile.NamedTemporaryFile(suffix=f".{actual_fmt}", delete=False)
            try:
                tmp.write(content)
                tmp.flush()
                tmp.close()
                codec = "libmp3lame" if fmt == "mp3" else "copy"
                subprocess.run(
                    ["ffmpeg", "-y", "-i", tmp.name,
                     "-acodec", codec, "-b:a", "192k", str(output_path)],
                    check=True,
                    capture_output=True,
                )
            finally:
                Path(tmp.name).unlink(missing_ok=True)
        else:
            output_path.write_bytes(content)

        return actual_fmt

    def _generate_qwen(self, inputs: dict[str, Any], api_key: str, model: str) -> ToolResult:
        """qwen3-tts-* via native DashScope multimodal-generation endpoint.

        Response: output.audio.url (presigned OSS download) or output.audio.data (base64).
        Voices: Cherry, Ethan, Serena, Dylan, Kai.
        """
        import requests

        text = inputs["text"]
        voice = inputs.get("voice", "Cherry")
        speed = inputs.get("speed", 1.0)
        fmt = inputs.get("format", "mp3")
        instructions = inputs.get("instructions")

        if instructions and "instruct" not in model:
            raise ValueError(
                "instructions require qwen3-tts-instruct-flash; "
                f"selected model {model!r} would ignore delivery instructions"
            )

        parameters: dict[str, Any] = {
            "voice": voice,
            "speech_rate": speed,
        }
        lang = inputs.get("language_type", "auto")
        if lang != "auto":
            parameters["language_type"] = lang
        if instructions:
            parameters["instructions"] = instructions

        payload = {
            "model": model,
            "input": {"text": text},
            "parameters": parameters,
        }

        resp = requests.post(
            _QWEN_TTS_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=120,
        )
        resp.raise_for_status()
        data = resp.json()

        audio_info = data.get("output", {}).get("audio", {})
        audio_url = audio_info.get("url", "")
        audio_b64 = audio_info.get("data", "")

        output_path = Path(inputs.get("output_path", f"qwen_tts_output.{fmt}"))
        output_path.parent.mkdir(parents=True, exist_ok=True)

        if audio_url:
            # Download from presigned OSS URL
            dl = requests.get(audio_url, timeout=60)
            dl.raise_for_status()
            content = dl.content
        elif audio_b64:
            import base64
            content = base64.b64decode(audio_b64)
        else:
            raise ValueError(f"No audio in response: {data}")

        actual_fmt = self._ensure_audio_format(content, fmt, output_path)

        return ToolResult(
            success=True,
            data={
                "provider": self.provider,
                "model": model,
                "model_name": _MODELS[model]["name"],
                "voice": voice,
                "voice_description": VOICES.get(voice, voice),
                "text_length": len(text),
                "output": str(output_path),
                "format": fmt,
                "actual_api_format": actual_fmt,
            },
            artifacts=[str(output_path)],
            model=model,
        )

    def _generate_cosyvoice(self, inputs: dict[str, Any], api_key: str, model: str) -> ToolResult:
        """cosyvoice-* via OpenAI-compatible audio/speech endpoint.

        The endpoint returns raw PCM/WAV bytes regardless of the requested format.
        _ensure_audio_format detects the actual container from magic bytes and
        transcodes via FFmpeg so the output file extension always matches its content.
        """
        import requests

        text = inputs["text"]
        voice = inputs.get("voice", "longanyang")
        speed = inputs.get("speed", 1.0)
        fmt = inputs.get("format", "mp3")

        payload: dict[str, Any] = {
            "model": model,
            "input": text,
            "voice": voice,
        }
        if speed != 1.0:
            payload["speed"] = speed

        resp = requests.post(
            _COSYVOICE_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=120,
        )
        resp.raise_for_status()

        content = resp.content
        output_path = Path(inputs.get("output_path", f"cosyvoice_output.{fmt}"))
        output_path.parent.mkdir(parents=True, exist_ok=True)

        actual_fmt = self._ensure_audio_format(content, fmt, output_path)

        return ToolResult(
            success=True,
            data={
                "provider": self.provider,
                "model": model,
                "model_name": _MODELS[model]["name"],
                "voice": voice,
                "voice_description": VOICES.get(voice, voice),
                "text_length": len(text),
                "output": str(output_path),
                "format": fmt,
                "actual_api_format": actual_fmt,
            },
            artifacts=[str(output_path)],
            model=model,
        )
