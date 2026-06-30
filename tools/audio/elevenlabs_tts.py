"""ElevenLabs text-to-speech provider tool."""

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
from tools.output_paths import require_explicit_output_path


class ElevenLabsTTS(BaseTool):
    name = "elevenlabs_tts"
    version = "0.1.0"
    tier = ToolTier.VOICE
    capability = "tts"
    provider = "elevenlabs"
    stability = ToolStability.EXPERIMENTAL
    execution_mode = ExecutionMode.SYNC
    determinism = Determinism.STOCHASTIC
    runtime = ToolRuntime.API

    dependencies = ["env:ELEVENLABS_API_KEY"]
    install_instructions = (
        "Set the ELEVENLABS_API_KEY environment variable:\n"
        "  export ELEVENLABS_API_KEY=your_key_here\n"
        "Get a key at https://elevenlabs.io"
    )
    fallback = "openai_tts"
    fallback_tools = ["openai_tts", "piper_tts"]
    agent_skills = ["elevenlabs", "text-to-speech"]

    capabilities = [
        "text_to_speech",
        "voice_selection",
        "ssml_support",
        "pronunciation_control",
    ]
    supports = {
        "voice_cloning": True,
        "multilingual": True,
        "offline": False,
        "native_audio": True,
    }
    best_for = [
        "high-quality narration",
        "voice-sensitive spokesperson videos",
        "multilingual spoken delivery",
    ]
    not_good_for = [
        "fully offline production",
        "privacy-constrained local-only workflows",
    ]
    model_options = [
        {
            "id": "eleven_v3",
            "name": "Eleven v3",
            "field": "model_id",
            "default": True,
            "quality": "highest",
            "speed": "medium",
            "release_stage": "current_sota",
            "last_verified": "2026-06-28",
            "source_url": "https://elevenlabs.io/docs/overview/models",
        },
        {
            "id": "eleven_multilingual_v2",
            "name": "Eleven Multilingual v2",
            "field": "model_id",
            "default": False,
            "quality": "high",
            "speed": "medium",
            "release_stage": "legacy_stable",
            "last_verified": "2026-06-28",
            "source_url": "https://elevenlabs.io/docs/overview/models",
        },
        {
            "id": "eleven_flash_v2_5",
            "name": "Eleven Flash v2.5",
            "field": "model_id",
            "default": False,
            "quality": "good",
            "speed": "fast",
            "release_stage": "current_fast",
            "last_verified": "2026-06-28",
            "source_url": "https://elevenlabs.io/docs/overview/models",
        },
        {
            "id": "eleven_turbo_v2_5",
            "name": "Eleven Turbo v2.5",
            "field": "model_id",
            "default": False,
            "quality": "high",
            "speed": "fast",
            "release_stage": "current_fast",
            "last_verified": "2026-06-28",
            "source_url": "https://elevenlabs.io/docs/overview/models",
        },
    ]

    input_schema = {
        "type": "object",
        "required": ["text", "output_path"],
        "properties": {
            "text": {"type": "string", "description": "Text to convert to speech"},
            "voice_id": {
                "type": "string",
                "description": "ElevenLabs voice ID (default: Rachel)",
            },
            "model_id": {
                "type": "string",
                "enum": [
                    "eleven_v3",
                    "eleven_multilingual_v2",
                    "eleven_flash_v2_5",
                    "eleven_turbo_v2_5",
                ],
                "default": "eleven_v3",
                "description": "TTS model to use",
            },
            "stability": {
                "type": "number",
                "default": 0.5,
                "minimum": 0,
                "maximum": 1,
            },
            "similarity_boost": {
                "type": "number",
                "default": 0.75,
                "minimum": 0,
                "maximum": 1,
            },
            "style": {
                "type": "number",
                "default": 0.0,
                "minimum": 0,
                "maximum": 1,
            },
            "speed": {
                "type": "number",
                "default": 1.0,
                "minimum": 0.7,
                "maximum": 1.2,
            },
            "use_speaker_boost": {
                "type": "boolean",
                "default": True,
            },
            "output_path": {"type": "string"},
            "output_format": {
                "type": "string",
                "default": "mp3_44100_128",
                "enum": ["mp3_44100_128", "mp3_44100_192", "pcm_16000", "pcm_24000"],
            },
        },
    }
    output_schema = {
        "type": "object",
        "required": [
            "provider",
            "model",
            "voice_id",
            "text_length",
            "format",
            "output",
            "output_path",
        ],
        "properties": {
            "provider": {"type": "string", "const": "elevenlabs"},
            "model": {"type": "string"},
            "voice_id": {"type": "string"},
            "text_length": {"type": "integer", "minimum": 0},
            "format": {
                "type": "string",
                "enum": ["mp3_44100_128", "mp3_44100_192", "pcm_16000", "pcm_24000"],
            },
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
        "output_path",
        "voice_id",
        "model_id",
        "stability",
        "similarity_boost",
        "style",
        "speed",
        "use_speaker_boost",
        "output_format",
    ]
    side_effects = ["writes audio file to output_path", "calls ElevenLabs API"]
    user_visible_verification = ["Inspect transcript alignment, duration, and waveform metrics for natural speech quality"]

    DEFAULT_VOICE_ID = "21m00Tcm4TlvDq8ikWAM"

    # Class-level cache: key prefixes that returned 401 this process lifetime.
    # Prevents repeated "available" status reports after a known-bad key.
    _AUTH_FAILED_KEY_PREFIXES: set[str] = set()

    def get_status(self) -> ToolStatus:
        key = os.environ.get("ELEVENLABS_API_KEY", "")
        if not key:
            return ToolStatus.UNAVAILABLE
        if key[:8] in self.__class__._AUTH_FAILED_KEY_PREFIXES:
            return ToolStatus.UNAVAILABLE
        return ToolStatus.AVAILABLE

    def estimate_cost(self, inputs: dict[str, Any]) -> float:
        return round(len(inputs.get("text", "")) * 0.0003, 4)

    def execute(self, inputs: dict[str, Any]) -> ToolResult:
        output_path, output_error = require_explicit_output_path(
            inputs, self.name, artifact_label="generated speech audio"
        )
        if output_error:
            return output_error
        assert output_path is not None

        api_key = os.environ.get("ELEVENLABS_API_KEY")
        if not api_key:
            return ToolResult(success=False, error="No ElevenLabs API key. " + self.install_instructions)

        start = time.time()
        try:
            result = self._generate(inputs, api_key, output_path)
        except Exception as exc:
            return ToolResult(success=False, error=f"TTS generation failed: {exc}")

        result.duration_seconds = round(time.time() - start, 2)
        result.cost_usd = self.estimate_cost(inputs)
        if result.success:
            result.data.setdefault("output_path", str(output_path))
        return result

    def _generate(
        self,
        inputs: dict[str, Any],
        api_key: str,
        output_path: Path,
    ) -> ToolResult:
        import requests

        text = inputs["text"]
        voice_id = inputs.get("voice_id", self.DEFAULT_VOICE_ID)
        model_id = inputs.get("model_id", "eleven_v3")
        output_format = inputs.get("output_format", "mp3_44100_128")
        voice_settings = {
            "stability": inputs.get("stability", 0.5),
            "similarity_boost": inputs.get("similarity_boost", 0.75),
            "style": inputs.get("style", 0.0),
            "speed": inputs.get("speed", 1.0),
            "use_speaker_boost": inputs.get("use_speaker_boost", True),
        }

        response = requests.post(
            f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
            headers={
                "xi-api-key": api_key,
                "Content-Type": "application/json",
                "Accept": "audio/mpeg",
            },
            json={
                "text": text,
                "model_id": model_id,
                "voice_settings": voice_settings,
            },
            params={"output_format": output_format},
            timeout=120,
        )
        if response.status_code == 401:
            self.__class__._AUTH_FAILED_KEY_PREFIXES.add(api_key[:8])
        response.raise_for_status()

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(response.content)

        return ToolResult(
            success=True,
            data={
                "provider": self.provider,
                "model": model_id,
                "voice_id": voice_id,
                "voice_settings": voice_settings,
                "text_length": len(text),
                "output": str(output_path),
                "format": output_format,
            },
            artifacts=[str(output_path)],
            model=model_id,
        )
