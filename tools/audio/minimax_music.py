"""MiniMax music generation via MiniMax platform API.

Supports music-2.6 (text-to-music with optional lyrics) and music-cover
(reference-audio cover generation). Synchronous — no polling required.

Endpoint: POST https://api.minimaxi.com/v1/music_generation
Auth:     Authorization: Bearer MINIMAX_API_KEY
Docs:     https://platform.minimaxi.com/docs/api-reference/music-generation
"""

from __future__ import annotations

import base64
import binascii
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
from tools.output_paths import require_explicit_output_path

_API_URL = "https://api.minimaxi.com/v1/music_generation"

_MODELS: dict[str, dict[str, Any]] = {
    "music-2.6": {
        "name": "MiniMax Music 2.6",
        "supports_lyrics": True,
        "supports_instrumental": True,
        "supports_cover": False,
        "cost_per_generation": 0.10,
        "tier": "paid",
    },
    "music-cover": {
        "name": "MiniMax Music Cover",
        "supports_lyrics": False,
        "supports_instrumental": False,
        "supports_cover": True,
        "cost_per_generation": 0.10,
        "tier": "paid",
    },
    "music-2.6-free": {
        "name": "MiniMax Music 2.6 (Free)",
        "supports_lyrics": True,
        "supports_instrumental": True,
        "supports_cover": False,
        "cost_per_generation": 0.0,
        "tier": "free",
    },
    "music-cover-free": {
        "name": "MiniMax Music Cover (Free)",
        "supports_lyrics": False,
        "supports_instrumental": False,
        "supports_cover": True,
        "cost_per_generation": 0.0,
        "tier": "free",
    },
}


class MinimaxMusic(BaseTool):
    name = "minimax_music"
    version = "0.1.0"
    tier = ToolTier.GENERATE
    capability = "music_generation"
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
        "Note: music-2.6 and music-cover require a paid Token Plan."
    )
    fallback_tools = ["suno_music"]
    agent_skills = ["music"]

    capabilities = [
        "generate_background_music",
        "generate_song",
        "generate_instrumental",
        "music_cover",
    ]
    supports = {
        "instrumental": True,
        "vocals": True,
        "custom_lyrics": True,
        "lyrics_optimizer": True,
        "cover_generation": True,
        "style_control": True,
        "long_form": False,
    }
    best_for = [
        "high-quality background music from a style/mood description",
        "full songs with structured lyrics ([Verse]/[Chorus]/[Bridge])",
        "AI-generated cover versions of reference audio",
        "fast synchronous generation — no polling wait",
        "instrumental tracks for video narration scoring",
    ]
    not_good_for = [
        "tracks longer than ~3 minutes",
        "sound effects (use ElevenLabs SFX instead)",
        "offline generation",
    ]

    input_schema = {
        "type": "object",
        "required": ["prompt", "output_path"],
        "properties": {
            "prompt": {
                "type": "string",
                "description": (
                    "Music style/mood/scene description (max 2000 chars). "
                    "Example: 'upbeat electronic pop, energetic, futuristic, driving beat'. "
                    "Also used as the style hint when generating a cover."
                ),
            },
            "lyrics": {
                "type": "string",
                "description": (
                    "Song lyrics with structural tags. "
                    "Supported tags: [Verse], [Chorus], [Bridge], [Outro], [Intro]. "
                    "Max 3500 chars. Omit for instrumental or to use lyrics_optimizer."
                ),
            },
            "model": {
                "type": "string",
                "enum": list(_MODELS.keys()),
                "default": "music-2.6",
                "description": "music-2.6/music-cover require paid plan; *-free tiers work for all.",
            },
            "is_instrumental": {
                "type": "boolean",
                "default": True,
                "description": "True = no vocals. Only for music-2.6/* models.",
            },
            "lyrics_optimizer": {
                "type": "boolean",
                "default": False,
                "description": "Auto-generate lyrics from the prompt. music-2.6 only. Ignored if lyrics provided.",
            },
            "audio_url": {
                "type": "string",
                "description": "Reference audio URL for cover models (6s–6min, max 50 MB).",
            },
            "audio_path": {
                "type": "string",
                "description": "Local reference audio path for cover models (auto base64-encoded).",
            },
            "format": {
                "type": "string",
                "enum": ["mp3", "wav", "pcm"],
                "default": "mp3",
            },
            "sample_rate": {
                "type": "integer",
                "enum": [16000, 24000, 32000, 44100],
                "default": 44100,
            },
            "bitrate": {
                "type": "integer",
                "enum": [32000, 64000, 128000, 256000],
                "default": 256000,
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
            "prompt",
            "is_instrumental",
            "music_duration_ms",
            "music_duration_s",
            "format",
            "output",
            "output_path",
        ],
        "properties": {
            "provider": {"type": "string", "const": "minimax"},
            "model": {"type": "string", "enum": list(_MODELS.keys())},
            "model_name": {"type": "string"},
            "prompt": {"type": "string"},
            "is_instrumental": {"type": "boolean"},
            "music_duration_ms": {"type": ["number", "null"]},
            "music_duration_s": {"type": ["number", "null"]},
            "format": {"type": "string", "enum": ["mp3", "wav", "pcm"]},
            "output": {"type": "string"},
            "output_path": {"type": "string"},
        },
    }

    resource_profile = ResourceProfile(
        cpu_cores=1, ram_mb=256, vram_mb=0, disk_mb=100, network_required=True
    )
    retry_policy = RetryPolicy(max_retries=2, retryable_errors=["rate_limit", "timeout"])
    idempotency_key_fields = [
        "prompt",
        "lyrics",
        "model",
        "is_instrumental",
        "lyrics_optimizer",
        "audio_url",
        "audio_path",
        "format",
        "sample_rate",
        "bitrate",
        "output_path",
    ]
    side_effects = ["writes audio file to output_path", "calls MiniMax API"]
    user_visible_verification = ["Inspect audio metadata, duration, tags, and waveform metrics for mood, style, and quality fit"]

    def _get_api_key(self) -> str | None:
        return os.environ.get("MINIMAX_API_KEY")

    def get_status(self) -> ToolStatus:
        if self._get_api_key():
            return ToolStatus.AVAILABLE
        return ToolStatus.UNAVAILABLE

    def estimate_cost(self, inputs: dict[str, Any]) -> float:
        model = inputs.get("model", "music-2.6")
        return _MODELS.get(model, _MODELS["music-2.6"])["cost_per_generation"]

    def execute(self, inputs: dict[str, Any]) -> ToolResult:
        model = inputs.get("model", "music-2.6")
        if model not in _MODELS:
            return ToolResult(success=False, error=f"Unsupported model {model!r}.")
        model_meta = _MODELS[model]
        fmt = inputs.get("format", "mp3")

        output_path, output_error = require_explicit_output_path(
            inputs, self.name, artifact_label="generated music audio"
        )
        if output_error:
            return output_error
        assert output_path is not None

        api_key = self._get_api_key()
        if not api_key:
            return ToolResult(
                success=False,
                error="MINIMAX_API_KEY not set. " + self.install_instructions,
            )

        start = time.time()

        import requests

        payload: dict[str, Any] = {
            "model": model,
            "output_format": "url",  # prefer URL over hex for efficiency
            "audio_setting": {
                "sample_rate": inputs.get("sample_rate", 44100),
                "bitrate": inputs.get("bitrate", 256000),
                "format": fmt,
            },
        }

        # ── Mode: cover ────────────────────────────────────────────────────────
        if model_meta["supports_cover"]:
            payload["prompt"] = inputs["prompt"]
            ref_b64 = self._file_to_b64(inputs.get("audio_path"))
            if ref_b64:
                payload["audio_base64"] = ref_b64
            elif inputs.get("audio_url"):
                payload["audio_url"] = inputs["audio_url"]
            else:
                return ToolResult(
                    success=False,
                    error=f"Cover model '{model}' requires audio_url or audio_path.",
                )

        # ── Mode: text-to-music ────────────────────────────────────────────────
        else:
            payload["prompt"] = inputs["prompt"]
            instrumental = inputs.get("is_instrumental", True)
            payload["is_instrumental"] = instrumental

            if not instrumental:
                lyrics = inputs.get("lyrics", "")
                if lyrics:
                    payload["lyrics"] = lyrics
                elif inputs.get("lyrics_optimizer", False):
                    payload["lyrics_optimizer"] = True
                # if neither, the API will generate without vocal content

        try:
            resp = requests.post(
                _API_URL,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=300,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            return ToolResult(success=False, error=f"MiniMax music request failed: {exc}")

        base_resp = data.get("base_resp", {})
        if base_resp.get("status_code", 0) != 0:
            return ToolResult(
                success=False,
                error=f"MiniMax API error {base_resp.get('status_code')}: {base_resp.get('status_msg')}",
            )

        music_data = data.get("data", {})
        if music_data.get("status") not in (2, None):
            return ToolResult(
                success=False,
                error=f"MiniMax music status unexpected: {music_data.get('status')}",
            )

        audio_ref = music_data.get("audio", "")
        if not audio_ref:
            return ToolResult(success=False, error=f"No audio in MiniMax response: {data}")

        try:
            audio_bytes = self._resolve_audio(audio_ref, fmt)
        except Exception as exc:
            return ToolResult(success=False, error=f"Failed to retrieve audio: {exc}")

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(audio_bytes)

        extra = data.get("extra_info", {})
        dur_ms = extra.get("music_duration")
        return ToolResult(
            success=True,
            data={
                "provider": self.provider,
                "model": model,
                "model_name": model_meta["name"],
                "prompt": inputs["prompt"],
                "is_instrumental": inputs.get("is_instrumental", True),
                "music_duration_ms": dur_ms,
                "music_duration_s": round(dur_ms / 1000, 2) if dur_ms else None,
                "format": fmt,
                "output": str(output_path),
                "output_path": str(output_path),
            },
            artifacts=[str(output_path)],
            cost_usd=self.estimate_cost(inputs),
            duration_seconds=round(time.time() - start, 2),
            model=model,
        )

    def _resolve_audio(self, audio_ref: str, fmt: str) -> bytes:
        """Resolve audio from URL or hex string."""
        import requests as req

        # If it looks like a URL, download it
        if audio_ref.startswith("http"):
            resp = req.get(audio_ref, timeout=120)
            resp.raise_for_status()
            return resp.content

        # Otherwise treat as hex-encoded audio
        try:
            return binascii.unhexlify(audio_ref)
        except Exception:
            raise ValueError(f"audio field is neither a URL nor valid hex (len={len(audio_ref)})")

    def _file_to_b64(self, path_str: str | None) -> str | None:
        if not path_str:
            return None
        path = Path(path_str)
        if not path.exists():
            return None
        return base64.b64encode(path.read_bytes()).decode()
