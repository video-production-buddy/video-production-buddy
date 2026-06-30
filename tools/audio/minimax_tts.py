"""MiniMax (Hailuo) text-to-speech via the native MiniMax platform API.

Supports the Speech 2.8 flagship (speech-2.8-hd / speech-2.8-turbo) plus the
2.6 and 02 series as fallbacks. Synchronous HTTP synthesis; audio returned as a
hex-encoded payload. Uses MINIMAX_API_KEY directly.

Endpoint: POST {base}/t2a_v2
Auth:     Authorization: Bearer MINIMAX_API_KEY
Docs:     https://platform.minimax.io/docs/api-reference/speech-t2a-http

Base host defaults to the China-mainland host (consistent with minimax_music);
override with the MINIMAX_API_BASE env var, e.g. https://api.minimax.io/v1.
"""

from __future__ import annotations

import os
import time
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
from tools.output_paths import require_explicit_output_path

_DEFAULT_API_BASE = "https://api.minimaxi.com/v1"

# ── Model registry ─────────────────────────────────────────────────────────────
_MODELS: dict[str, dict[str, Any]] = {
    # Speech 2.8 — latest flagship (HD = studio-grade; Turbo = low-latency)
    "speech-2.8-hd": {
        "name": "MiniMax Speech 2.8 HD",
        "quality": "highest",
        "speed": "medium",
        "cost_per_char": 0.00002,
    },
    "speech-2.8-turbo": {
        "name": "MiniMax Speech 2.8 Turbo",
        "quality": "high",
        "speed": "fast",
        "cost_per_char": 0.000014,
    },
    # Speech 2.6 (previous generation)
    "speech-2.6-hd": {
        "name": "MiniMax Speech 2.6 HD",
        "quality": "high",
        "speed": "medium",
        "cost_per_char": 0.000018,
    },
    "speech-2.6-turbo": {
        "name": "MiniMax Speech 2.6 Turbo",
        "quality": "high",
        "speed": "fast",
        "cost_per_char": 0.000012,
    },
    # Speech 02 (legacy, kept for backward compat)
    "speech-02-hd": {
        "name": "MiniMax Speech 02 HD (legacy)",
        "quality": "high",
        "speed": "medium",
        "cost_per_char": 0.000015,
    },
}

# Representative system voice_ids (300+ exist; these are stable, commonly used).
# Full list: https://platform.minimax.io/docs/api-reference/speech-t2a-http
VOICES: dict[str, str] = {
    "Calm_Woman": "female, calm — studio default for narration",
    "English_energetic_Woman": "female, energetic English",
    "English_magnetic_Man": "male, magnetic English baritone",
    "female-shaonv": "female, gentle Mandarin — 少女",
    "male-qn-qingse": "male, clear Mandarin — 青涩青年",
    "presenter_male": "male, presenter — 新闻播报",
    "audiobook_man_1": "male, warm — 有声书",
}


def _api_base() -> str:
    return os.environ.get("MINIMAX_API_BASE", _DEFAULT_API_BASE).rstrip("/")


def _audio_length_seconds(extra_info: dict[str, Any]) -> float | None:
    raw_length = extra_info.get("audio_length")
    if raw_length is None:
        return None
    try:
        return round(float(raw_length) / 1000.0, 2)
    except (TypeError, ValueError):
        return None


class MinimaxTTS(BaseTool):
    name = "minimax_tts"
    version = "0.1.0"
    tier = ToolTier.VOICE
    capability = "tts"
    provider = "minimax"
    stability = ToolStability.BETA
    execution_mode = ExecutionMode.SYNC
    determinism = Determinism.STOCHASTIC
    runtime = ToolRuntime.API

    dependencies = ["env:MINIMAX_API_KEY"]
    install_instructions = (
        "Set the MINIMAX_API_KEY environment variable:\n"
        "  export MINIMAX_API_KEY=your_key_here\n"
        "Get a key from Account > API Keys in the MiniMax API Platform:\n"
        "  https://platform.minimax.io/docs/guides/quickstart-preparation\n"
        "For the overseas host, also set MINIMAX_API_BASE=https://api.minimax.io/v1"
    )
    fallback_tools = ["cosyvoice_tts", "openai_tts", "google_tts"]
    agent_skills = ["text-to-speech"]

    capabilities = ["text_to_speech", "voice_selection", "multilingual"]
    supports = {
        "voice_cloning": False,  # cloning is a separate API; this tool uses system voices
        "multilingual": True,
        "offline": False,
        "native_audio": True,
        "speed_control": True,
        "pitch_control": True,
    }
    best_for = [
        "studio-grade narration via speech-2.8-hd (benchmark-leading TTS quality)",
        "low-latency voice via speech-2.8-turbo for fast iteration",
        "multilingual narration (40 languages incl. Chinese and English)",
        "second TTS provider on MINIMAX_API_KEY when CosyVoice/OpenAI are unavailable",
    ]
    not_good_for = ["fully offline production", "voice cloning (use the MiniMax Voice Cloning API)"]
    model_options = build_model_options(
        _MODELS,
        field="model",
        default="speech-2.8-hd",
        cost_units={"cost_per_char": "per_char"},
    )

    input_schema = {
        "type": "object",
        "required": ["text", "output_path"],
        "properties": {
            "text": {
                "type": "string",
                "description": "Text to convert to speech (max 10,000 chars per request)",
            },
            "voice": {
                "type": "string",
                "default": "Calm_Woman",
                "description": (
                    "System voice_id. Representative: Calm_Woman, English_energetic_Woman, "
                    "English_magnetic_Man, female-shaonv, male-qn-qingse, presenter_male, "
                    "audiobook_man_1. 300+ voices exist — see MiniMax T2A docs."
                ),
            },
            "model": {
                "type": "string",
                "enum": list(_MODELS.keys()),
                "default": "speech-2.8-hd",
                "description": "speech-2.8-hd (default, studio-grade). -turbo: low-latency. 2.6/02: fallbacks.",
            },
            "speed": {
                "type": "number",
                "default": 1.0,
                "minimum": 0.5,
                "maximum": 2.0,
                "description": "Speech speed multiplier",
            },
            "pitch": {
                "type": "integer",
                "default": 0,
                "minimum": -12,
                "maximum": 12,
                "description": "Pitch adjustment in semitones (-12..12)",
            },
            "format": {
                "type": "string",
                "enum": ["mp3", "wav", "pcm", "flac"],
                "default": "mp3",
            },
            "sample_rate": {
                "type": "integer",
                "enum": [16000, 24000, 32000, 44100],
                "default": 32000,
            },
            "bitrate": {
                "type": "integer",
                "enum": [32000, 64000, 128000, 256000],
                "default": 128000,
            },
            "output_path": {"type": "string"},
        },
    }
    output_schema = {
        "type": "object",
        "required": [
            "provider",
            "model",
            "model_name",
            "voice",
            "voice_description",
            "text_length",
            "audio_length_s",
            "format",
            "output",
            "output_path",
        ],
        "properties": {
            "provider": {"type": "string", "const": "minimax"},
            "model": {"type": "string", "enum": list(_MODELS.keys())},
            "model_name": {"type": "string"},
            "voice": {"type": "string"},
            "voice_description": {"type": "string"},
            "text_length": {"type": "integer", "minimum": 0},
            "audio_length_s": {"type": ["number", "null"]},
            "format": {"type": "string", "enum": ["mp3", "wav", "pcm", "flac"]},
            "output": {"type": "string"},
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
        "pitch",
        "format",
        "sample_rate",
        "bitrate",
        "output_path",
    ]
    side_effects = ["writes audio file to output_path", "calls MiniMax platform API"]
    user_visible_verification = ["Inspect transcript alignment, duration, and waveform metrics for natural speech quality"]

    def _get_api_key(self) -> str | None:
        return os.environ.get("MINIMAX_API_KEY")

    def get_status(self) -> ToolStatus:
        if self._get_api_key():
            return ToolStatus.AVAILABLE
        return ToolStatus.UNAVAILABLE

    def estimate_cost(self, inputs: dict[str, Any]) -> float:
        model = inputs.get("model", "speech-2.8-hd")
        cost_per_char = _MODELS.get(model, _MODELS["speech-2.8-hd"])["cost_per_char"]
        return round(len(inputs.get("text", "")) * cost_per_char, 5)

    def execute(self, inputs: dict[str, Any]) -> ToolResult:
        model = inputs.get("model", "speech-2.8-hd")
        if model not in _MODELS:
            return ToolResult(success=False, error=f"Unsupported model {model!r}.")

        output_path, output_error = require_explicit_output_path(
            inputs, self.name, artifact_label="generated speech audio"
        )
        if output_error:
            return output_error

        api_key = self._get_api_key()
        if not api_key:
            return ToolResult(success=False, error="MINIMAX_API_KEY not set. " + self.install_instructions)

        import requests

        text = inputs["text"]
        fmt = inputs.get("format", "mp3")
        payload = {
            "model": model,
            "text": text,
            "voice_setting": {
                "voice_id": inputs.get("voice", "Calm_Woman"),
                "speed": inputs.get("speed", 1.0),
                "vol": 1.0,
                "pitch": inputs.get("pitch", 0),
            },
            "audio_setting": {
                "sample_rate": inputs.get("sample_rate", 32000),
                "bitrate": inputs.get("bitrate", 128000),
                "format": fmt,
                "channel": 1,
            },
        }

        start = time.time()
        try:
            resp = requests.post(
                f"{_api_base()}/t2a_v2",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=120,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            return ToolResult(success=False, error=f"MiniMax TTS request failed: {exc}")

        base_resp = data.get("base_resp", {})
        if base_resp.get("status_code", 0) != 0:
            return ToolResult(
                success=False,
                error=f"MiniMax API error {base_resp.get('status_code')}: {base_resp.get('status_msg')}",
            )

        audio_hex = data.get("data", {}).get("audio", "")
        if not audio_hex:
            return ToolResult(success=False, error=f"No audio in MiniMax response: {data}")

        try:
            audio_bytes = bytes.fromhex(audio_hex)
        except ValueError as exc:
            return ToolResult(success=False, error=f"Failed to decode MiniMax audio (hex): {exc}")

        assert output_path is not None
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(audio_bytes)

        extra = data.get("extra_info", {})
        audio_length_s = _audio_length_seconds(extra)

        return ToolResult(
            success=True,
            data={
                "provider": self.provider,
                "model": model,
                "model_name": _MODELS[model]["name"],
                "voice": inputs.get("voice", "Calm_Woman"),
                "voice_description": VOICES.get(inputs.get("voice", "Calm_Woman"), ""),
                "text_length": len(text),
                "audio_length_s": audio_length_s,
                "format": fmt,
                "output": str(output_path),
                "output_path": str(output_path),
            },
            artifacts=[str(output_path)],
            cost_usd=self.estimate_cost(inputs),
            duration_seconds=round(time.time() - start, 2),
            model=model,
        )
