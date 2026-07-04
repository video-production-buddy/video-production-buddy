"""Piper local text-to-speech provider tool."""

from __future__ import annotations

import subprocess
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


class PiperTTS(BaseTool):
    name = "piper_tts"
    version = "0.1.0"
    tier = ToolTier.VOICE
    capability = "tts"
    provider = "piper"
    stability = ToolStability.EXPERIMENTAL
    execution_mode = ExecutionMode.SYNC
    determinism = Determinism.DETERMINISTIC
    runtime = ToolRuntime.LOCAL

    dependencies = ["cmd:piper"]
    install_instructions = (
        "Install Piper TTS:\n"
        "  pip install piper-tts\n"
        "Or download from https://github.com/rhasspy/piper/releases\n"
        "Then download a voice model:\n"
        "  piper --download-dir ~/.piper/models --model en_US-lessac-medium"
    )
    agent_skills = ["text-to-speech"]

    capabilities = [
        "text_to_speech",
        "offline_generation",
    ]
    supports = {
        "voice_cloning": False,
        "multilingual": False,
        "offline": True,
        "native_audio": True,
    }
    best_for = [
        "offline narration fallback",
        "privacy-sensitive local-only workflows",
    ]
    not_good_for = [
        "best-in-class expressive voice quality",
        "voice clone matching",
    ]

    input_schema = {
        "type": "object",
        "required": ["text", "output_path"],
        "properties": {
            "text": {"type": "string"},
            "model": {
                "type": "string",
                "default": "en_US-lessac-medium",
            },
            "speaker_id": {
                "type": "integer",
                "default": 0,
            },
            "length_scale": {
                "type": "number",
                "default": 1.0,
            },
            "sentence_silence": {
                "type": "number",
                "default": 0.3,
            },
            "output_path": {"type": "string"},
        },
    }
    output_schema = {
        "type": "object",
        "required": [
            "provider",
            "model",
            "speaker_id",
            "text_length",
            "format",
            "output",
            "output_path",
        ],
        "properties": {
            "provider": {"type": "string", "const": "piper"},
            "model": {"type": "string"},
            "speaker_id": {"type": "integer"},
            "text_length": {"type": "integer", "minimum": 0},
            "format": {"type": "string", "const": "wav"},
            "output": {"type": "string"},
            "output_path": {"type": "string"},
        },
    }

    resource_profile = ResourceProfile(
        cpu_cores=2, ram_mb=512, vram_mb=0, disk_mb=200, network_required=False
    )
    retry_policy = RetryPolicy(max_retries=1, retryable_errors=[])
    idempotency_key_fields = [
        "text",
        "output_path",
        "model",
        "speaker_id",
        "length_scale",
        "sentence_silence",
    ]
    side_effects = ["writes audio file to output_path"]
    user_visible_verification = ["Inspect transcript alignment, duration, and waveform metrics for intelligibility"]

    def get_status(self) -> ToolStatus:
        if shutil.which("piper"):
            return ToolStatus.AVAILABLE
        return ToolStatus.UNAVAILABLE

    def estimate_cost(self, inputs: dict[str, Any]) -> float:
        return 0.0

    def execute(self, inputs: dict[str, Any]) -> ToolResult:
        output_path, output_error = require_explicit_output_path(
            inputs, self.name, artifact_label="generated speech audio"
        )
        if output_error:
            return output_error
        assert output_path is not None

        if self.get_status() != ToolStatus.AVAILABLE:
            return ToolResult(success=False, error="Piper TTS not available. " + self.install_instructions)

        start = time.time()
        try:
            result = self._generate(inputs, output_path)
        except Exception as exc:
            return ToolResult(success=False, error=f"Local TTS generation failed: {exc}")

        result.duration_seconds = round(time.time() - start, 2)
        if result.success:
            result.data.setdefault("output_path", str(output_path))
        return result

    def _resolve_model_path(self, model: str) -> str:
        """Resolve a model shortname to its full .onnx path if available locally."""
        if model.endswith(".onnx") or Path(model).exists():
            return model
        candidates = [
            Path.home() / ".piper" / "models" / f"{model}.onnx",
            Path.home() / ".local" / "share" / "piper" / f"{model}.onnx",
        ]
        for candidate in candidates:
            if candidate.exists():
                return str(candidate)
        return model  # fall back and let piper error naturally

    def _generate(self, inputs: dict[str, Any], output_path: Path) -> ToolResult:
        output_path.parent.mkdir(parents=True, exist_ok=True)

        model = self._resolve_model_path(inputs.get("model", "en_US-lessac-medium"))

        proc = subprocess.run(
            [
                "piper",
                "--model", model,
                "--speaker", str(inputs.get("speaker_id", 0)),
                "--length-scale", str(inputs.get("length_scale", 1.0)),
                "--sentence-silence", str(inputs.get("sentence_silence", 0.3)),
                "--output_file", str(output_path),
            ],
            input=inputs["text"],
            capture_output=True,
            text=True,
            timeout=300,
        )

        if proc.returncode != 0:
            return ToolResult(success=False, error=f"Piper failed (exit {proc.returncode}): {proc.stderr}")
        if not output_path.exists():
            return ToolResult(success=False, error=f"Piper output file missing: {output_path}")

        return ToolResult(
            success=True,
            data={
                "provider": self.provider,
                "model": inputs.get("model", "en_US-lessac-medium"),
                "speaker_id": inputs.get("speaker_id", 0),
                "text_length": len(inputs["text"]),
                "output": str(output_path),
                "format": "wav",
            },
            artifacts=[str(output_path)],
            model=inputs.get("model", "en_US-lessac-medium"),
        )
