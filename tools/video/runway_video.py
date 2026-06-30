"""Runway video generation via Runway API.

Supports current Runway-hosted generation models such as Seedance 2, Gen-4.5,
Veo 3.1, HappyHorse 1.0, plus legacy Gen-4 options where still accepted.
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
from tools.video._shared import require_generated_video_output_path, validate_video_operation

_RATIO_MAP = {
    "16:9": "1280:720",
    "9:16": "720:1280",
    "1:1": "720:720",
}

_MODEL_OPTIONS = [
    {
        "id": "seedance2",
        "name": "Seedance 2",
        "field": "model",
        "default": True,
        "quality": "highest",
        "speed": "medium",
        "release_stage": "current",
        "last_verified": "2026-06-28",
        "source_url": "https://docs.dev.runwayml.com/guides/models/",
        "note": "Runway-hosted Seedance 2 route with broad text/image/video generation coverage.",
    },
    {
        "id": "seedance2_fast",
        "name": "Seedance 2 Fast",
        "field": "model",
        "default": False,
        "quality": "high",
        "speed": "fast",
        "release_stage": "current",
        "last_verified": "2026-06-28",
        "source_url": "https://docs.dev.runwayml.com/guides/models/",
    },
    {
        "id": "seedance2_mini",
        "name": "Seedance 2 Mini",
        "field": "model",
        "default": False,
        "quality": "good",
        "speed": "fast",
        "release_stage": "current",
        "last_verified": "2026-06-28",
        "source_url": "https://docs.dev.runwayml.com/guides/models/",
    },
    {
        "id": "gen4.5",
        "name": "Runway Gen-4.5",
        "field": "model",
        "default": False,
        "quality": "highest",
        "speed": "medium",
        "release_stage": "current_sota",
        "last_verified": "2026-06-28",
        "source_url": "https://docs.dev.runwayml.com/guides/models/",
    },
    {
        "id": "veo3.1",
        "name": "Veo 3.1 via Runway",
        "field": "model",
        "default": False,
        "quality": "highest",
        "speed": "medium",
        "release_stage": "current",
        "last_verified": "2026-06-28",
        "source_url": "https://docs.dev.runwayml.com/guides/models/",
    },
    {
        "id": "veo3.1_fast",
        "name": "Veo 3.1 Fast via Runway",
        "field": "model",
        "default": False,
        "quality": "high",
        "speed": "fast",
        "release_stage": "current",
        "last_verified": "2026-06-28",
        "source_url": "https://docs.dev.runwayml.com/guides/models/",
    },
    {
        "id": "happyhorse_1_0",
        "name": "HappyHorse 1.0 via Runway",
        "field": "model",
        "default": False,
        "quality": "highest",
        "speed": "medium",
        "release_stage": "current",
        "last_verified": "2026-06-28",
        "source_url": "https://docs.dev.runwayml.com/guides/models/",
    },
    {
        "id": "gen4_turbo",
        "name": "Runway Gen-4 Turbo",
        "field": "model",
        "default": False,
        "quality": "high",
        "speed": "fast",
        "release_stage": "legacy_current",
        "last_verified": "2026-06-28",
        "source_url": "https://docs.dev.runwayml.com/guides/models/",
    },
    {
        "id": "gen4_aleph",
        "name": "Runway Gen-4 Aleph",
        "field": "model",
        "default": False,
        "quality": "legacy_high",
        "speed": "medium",
        "release_stage": "deprecated",
        "deprecated": True,
        "last_verified": "2026-06-28",
        "source_url": "https://docs.dev.runwayml.com/guides/models/",
    },
    {
        "id": "gen3a_turbo",
        "name": "Runway Gen-3 Alpha Turbo",
        "field": "model",
        "default": False,
        "quality": "legacy_good",
        "speed": "fast",
        "release_stage": "legacy",
        "last_verified": "2026-06-28",
        "source_url": "https://docs.dev.runwayml.com/guides/models/",
    },
]

_MODEL_IDS = [str(option["id"]) for option in _MODEL_OPTIONS]

_MODELS_WITHOUT_WATERMARK = {"seedance2", "seedance2_fast", "happyhorse_1_0"}

_COST_PER_SECOND = {
    "seedance2": 0.30,
    "seedance2_fast": 0.24,
    "seedance2_mini": 0.12,
    "gen4.5": 0.15,
    "veo3.1": 0.20,
    "veo3.1_fast": 0.10,
    "happyhorse_1_0": 0.30,
    "gen4_turbo": 0.05,
    "gen4_aleph": 0.15,
    "gen3a_turbo": 0.05,
}

_RUNTIME_SECONDS = {
    "seedance2": 120.0,
    "seedance2_fast": 60.0,
    "seedance2_mini": 45.0,
    "gen4.5": 90.0,
    "veo3.1": 120.0,
    "veo3.1_fast": 60.0,
    "happyhorse_1_0": 120.0,
    "gen4_turbo": 30.0,
    "gen4_aleph": 60.0,
    "gen3a_turbo": 25.0,
}

# Single source of truth for the default model. Referenced by both the input
# schema and every code path that reads `model`, so estimate_cost / estimate_runtime
# / execute can never silently diverge from the advertised default again.
_DEFAULT_MODEL = "seedance2"


class RunwayVideo(BaseTool):
    name = "runway_video"
    version = "0.2.0"
    tier = ToolTier.GENERATE
    capability = "video_generation"
    provider = "runway"
    stability = ToolStability.BETA
    execution_mode = ExecutionMode.SYNC
    determinism = Determinism.STOCHASTIC
    runtime = ToolRuntime.API

    dependencies = ["env_any:RUNWAY_API_KEY,RUNWAYML_API_SECRET"]
    install_instructions = (
        "Set RUNWAY_API_KEY to your Runway API secret.\n"
        "  Get one at https://dev.runwayml.com/"
    )
    agent_skills = ["seedance-2-0", "ai-video-gen"]
    model_options = _MODEL_OPTIONS

    capabilities = ["text_to_video", "image_to_video"]
    supports = {
        "text_to_video": True,
        "image_to_video": True,
        "professional_control": True,
        "native_audio": True,
        "cinematic_quality": True,
        "camera_direction": True,
        "lip_sync": True,
        "multi_shot": True,
    }
    best_for = [
        "preferred premium video gen on Runway when Seedance 2 or Gen-4.5 model is selected",
        "cinematic trailers, teasers, and high-fidelity clips",
        "director-level camera control and professional Runway-hosted generation",
        "professional video production",
    ]
    not_good_for = ["budget projects", "offline generation", "very long clips"]
    fallback_tools = ["seedance_video", "seedance_replicate", "kling_video", "veo_video", "minimax_video", "wan_video"]
    quality_score = 0.9

    input_schema = {
        "type": "object",
        "required": ["prompt", "output_path"],
        "properties": {
            "prompt": {"type": "string"},
            "operation": {
                "type": "string",
                "enum": ["text_to_video", "image_to_video"],
                "default": "text_to_video",
            },
            "model": {
                "type": "string",
                "enum": _MODEL_IDS,
                "default": _DEFAULT_MODEL,
                "description": (
                    "seedance2 = preferred premium default. "
                    "gen4.5 = current Runway-native SOTA option. "
                    "veo3.1 / veo3.1_fast and happyhorse_1_0 are Runway-hosted routes. "
                    "gen4_aleph is deprecated."
                ),
            },
            "duration": {
                "type": "integer",
                "enum": [5, 10],
                "default": 5,
                "description": "Duration in seconds",
            },
            "ratio": {
                "type": "string",
                "enum": ["16:9", "9:16", "1:1"],
                "default": "16:9",
            },
            "watermark": {
                "type": "boolean",
                "default": False,
                "description": "Include Runway watermark on output",
            },
            "image_url": {"type": "string", "description": "Reference image URL for image_to_video"},
            "output_path": {"type": "string"},
        },
    }
    output_schema = {
        "type": "object",
        "required": [
            "provider",
            "model",
            "prompt",
            "operation",
            "ratio",
            "output",
            "output_path",
            "task_id",
            "format",
            "file_size_bytes",
        ],
        "properties": {
            "provider": {"type": "string", "const": "runway"},
            "model": {"type": "string"},
            "prompt": {"type": "string"},
            "operation": {"type": "string", "enum": ["text_to_video", "image_to_video"]},
            "ratio": {"type": "string"},
            "output": {"type": "string"},
            "output_path": {"type": "string"},
            "task_id": {"type": "string"},
            "format": {"type": "string", "const": "mp4"},
            "file_size_bytes": {"type": "integer", "minimum": 0},
            "duration_seconds": {"type": "number", "minimum": 0},
            "file_size_mb": {"type": "number", "minimum": 0},
            "video_width": {"type": "integer", "minimum": 0},
            "video_height": {"type": "integer", "minimum": 0},
            "video_codec": {"type": "string"},
        },
    }

    resource_profile = ResourceProfile(
        cpu_cores=1, ram_mb=512, vram_mb=0, disk_mb=500, network_required=True
    )
    retry_policy = RetryPolicy(max_retries=2, retryable_errors=["rate_limit", "timeout", "THROTTLED"])
    idempotency_key_fields = [
        "prompt",
        "output_path",
        "model",
        "operation",
        "duration",
        "ratio",
        "watermark",
        "image_url",
    ]
    side_effects = ["writes video file to output_path", "calls Runway API"]
    user_visible_verification = ["Inspect sampled frames for visual quality and motion coherence"]

    def get_status(self) -> ToolStatus:
        if os.environ.get("RUNWAY_API_KEY") or os.environ.get("RUNWAYML_API_SECRET"):
            return ToolStatus.AVAILABLE
        return ToolStatus.UNAVAILABLE

    def _get_api_key(self) -> str | None:
        return os.environ.get("RUNWAY_API_KEY") or os.environ.get("RUNWAYML_API_SECRET")

    def estimate_cost(self, inputs: dict[str, Any]) -> float:
        model = inputs.get("model", _DEFAULT_MODEL)
        duration = inputs.get("duration", 5)
        return _COST_PER_SECOND.get(model, 0.05) * duration

    def estimate_runtime(self, inputs: dict[str, Any]) -> float:
        model = inputs.get("model", _DEFAULT_MODEL)
        return _RUNTIME_SECONDS.get(model, 30.0)

    def execute(self, inputs: dict[str, Any]) -> ToolResult:
        model = inputs.get("model", _DEFAULT_MODEL)
        operation = inputs.get("operation", "text_to_video")
        operation_error = validate_video_operation(operation, {"text_to_video", "image_to_video"})
        if operation_error:
            return ToolResult(success=False, error=operation_error)
        if operation == "image_to_video" and not inputs.get("image_url"):
            return ToolResult(success=False, error="image_to_video requires image_url")
        output_path, output_error = require_generated_video_output_path(inputs, self.name)
        if output_error:
            return output_error

        api_key = self._get_api_key()
        if not api_key:
            return ToolResult(
                success=False,
                error="RUNWAY_API_KEY not set. " + self.install_instructions,
            )

        import requests

        start = time.time()
        ratio_friendly = inputs.get("ratio", "16:9")
        ratio_pixels = _RATIO_MAP.get(ratio_friendly, "1280:720")

        task_payload: dict[str, Any] = {
            "model": model,
            "promptText": inputs["prompt"],
            "duration": inputs.get("duration", 5),
            "ratio": ratio_pixels,
        }
        if model not in _MODELS_WITHOUT_WATERMARK and "watermark" in inputs:
            task_payload["watermark"] = bool(inputs["watermark"])
        if operation == "image_to_video":
            task_payload["promptImage"] = inputs["image_url"]

        # Choose endpoint based on operation
        endpoint = (
            "https://api.dev.runwayml.com/v1/image_to_video"
            if operation == "image_to_video"
            else "https://api.dev.runwayml.com/v1/text_to_video"
        )

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "X-Runway-Version": "2024-11-06",
        }

        try:
            # Submit generation task
            submit_response = requests.post(
                endpoint,
                headers=headers,
                json=task_payload,
                timeout=30,
            )
            submit_response.raise_for_status()
            task_id = submit_response.json()["id"]

            # Poll for completion (max ~5 minutes)
            video_url = None
            for _ in range(60):
                time.sleep(5)
                poll_response = requests.get(
                    f"https://api.dev.runwayml.com/v1/tasks/{task_id}",
                    headers=headers,
                    timeout=15,
                )
                poll_response.raise_for_status()
                task_data = poll_response.json()
                status = task_data["status"]

                if status == "SUCCEEDED":
                    video_url = task_data["output"][0]
                    break
                if status == "FAILED":
                    failure_code = task_data.get("failureCode", "unknown")
                    return ToolResult(
                        success=False,
                        error=f"Runway generation failed ({failure_code}): {task_data.get('failure', 'unknown error')}",
                    )
                # PENDING, THROTTLED, RUNNING — keep polling

            if not video_url:
                return ToolResult(success=False, error="Runway generation timed out after 5 minutes.")

            # Download video — URLs are ephemeral (expire in 24-48h)
            video_response = requests.get(video_url, timeout=120)
            video_response.raise_for_status()

            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(video_response.content)

        except Exception as e:
            return ToolResult(success=False, error=f"Runway video generation failed: {e}")

        from tools.video._shared import probe_output

        probed = probe_output(output_path)
        return ToolResult(
            success=True,
            data={
                "provider": "runway",
                "model": model,
                "prompt": inputs["prompt"],
                "operation": operation,
                "ratio": ratio_friendly,
                "output": str(output_path),
                "output_path": str(output_path),
                "task_id": task_id,
                "format": "mp4",
                **probed,
            },
            artifacts=[str(output_path)],
            cost_usd=self.estimate_cost(inputs),
            duration_seconds=round(time.time() - start, 2),
            model=model,
        )
