"""FLUX image generation via fal.ai API."""

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


class FluxImage(BaseTool):
    name = "flux_image"
    version = "0.1.0"
    tier = ToolTier.GENERATE
    capability = "image_generation"
    provider = "flux"
    stability = ToolStability.BETA
    execution_mode = ExecutionMode.SYNC
    determinism = Determinism.SEEDED
    runtime = ToolRuntime.API

    dependencies = ["env_any:FAL_KEY,FAL_AI_API_KEY"]
    install_instructions = (
        "Set FAL_KEY to your fal.ai API key.\n"
        "  Get one at https://fal.ai/dashboard/keys"
    )
    agent_skills = ["flux-best-practices", "bfl-api"]

    capabilities = ["generate_image", "generate_illustration", "text_to_image"]
    supports = {
        "negative_prompt": True,
        "seed": True,
        "custom_size": True,
    }
    best_for = [
        "photorealistic images",
        "general-purpose image generation",
        "high quality at low cost (~$0.03/image)",
    ]
    not_good_for = ["text rendering in images", "offline generation"]
    model_options = [
        {
            "id": "flux-2-pro",
            "name": "FLUX.2 Pro",
            "field": "model",
            "default": True,
            "quality": "highest",
            "speed": "medium",
            "release_stage": "current_sota",
            "last_verified": "2026-06-28",
            "source_url": "https://fal.ai/flux-2",
        },
        {
            "id": "flux-2",
            "name": "FLUX.2",
            "field": "model",
            "default": False,
            "quality": "high",
            "speed": "medium",
            "release_stage": "current",
            "last_verified": "2026-06-28",
            "source_url": "https://fal.ai/flux-2",
        },
        {
            "id": "flux-2/turbo",
            "name": "FLUX.2 Turbo",
            "field": "model",
            "default": False,
            "quality": "high",
            "speed": "fast",
            "release_stage": "current",
            "last_verified": "2026-06-28",
            "source_url": "https://fal.ai/flux-2",
        },
        {
            "id": "flux-pro/v1.1",
            "name": "FLUX.1.1 Pro",
            "field": "model",
            "default": False,
            "quality": "legacy_high",
            "speed": "medium",
            "release_stage": "legacy",
            "last_verified": "2026-06-28",
            "source_url": "https://fal.ai/models/fal-ai/flux-pro/v1.1",
        },
        {
            "id": "flux/dev",
            "name": "FLUX.1 Dev",
            "field": "model",
            "default": False,
            "quality": "legacy_good",
            "speed": "medium",
            "release_stage": "legacy",
            "last_verified": "2026-06-28",
            "source_url": "https://fal.ai/models/fal-ai/flux/dev",
        },
        {
            "id": "flux-pro",
            "name": "FLUX.1 Pro",
            "field": "model",
            "default": False,
            "quality": "legacy_high",
            "speed": "medium",
            "release_stage": "legacy",
            "last_verified": "2026-06-28",
            "source_url": "https://fal.ai/models/fal-ai/flux-pro",
        },
    ]

    input_schema = {
        "type": "object",
        "required": ["prompt", "output_path"],
        "properties": {
            "prompt": {"type": "string"},
            "negative_prompt": {"type": "string", "default": ""},
            "width": {"type": "integer", "default": 1024},
            "height": {"type": "integer", "default": 1024},
            "model": {
                "type": "string",
                "enum": [
                    "flux-2-pro",
                    "flux-2",
                    "flux-2/turbo",
                    "flux-pro/v1.1",
                    "flux/dev",
                    "flux-pro",
                ],
                "default": "flux-2-pro",
            },
            "seed": {"type": "integer"},
            "num_inference_steps": {"type": "integer"},
            "guidance_scale": {"type": "number"},
            "output_path": {"type": "string"},
        },
    }
    output_schema = {
        "type": "object",
        "required": ["provider", "model", "prompt", "output", "output_path", "seed"],
        "properties": {
            "provider": {"type": "string", "const": "flux"},
            "model": {"type": "string"},
            "prompt": {"type": "string"},
            "output": {"type": "string"},
            "output_path": {"type": "string"},
            "seed": {"type": ["integer", "string", "null"]},
        },
    }

    resource_profile = ResourceProfile(
        cpu_cores=1, ram_mb=512, vram_mb=0, disk_mb=100, network_required=True
    )
    retry_policy = RetryPolicy(max_retries=2, retryable_errors=["rate_limit", "timeout"])
    idempotency_key_fields = [
        "prompt",
        "output_path",
        "negative_prompt",
        "width",
        "height",
        "seed",
        "model",
        "num_inference_steps",
        "guidance_scale",
    ]
    side_effects = ["writes image file to output_path", "calls fal.ai API"]
    user_visible_verification = ["Inspect generated image for relevance and quality"]

    def _get_api_key(self) -> str | None:
        return os.environ.get("FAL_KEY") or os.environ.get("FAL_AI_API_KEY")

    def get_status(self) -> ToolStatus:
        if self._get_api_key():
            return ToolStatus.AVAILABLE
        return ToolStatus.UNAVAILABLE

    def estimate_cost(self, inputs: dict[str, Any]) -> float:
        model = inputs.get("model", "flux-2-pro")
        if model == "flux-2/turbo":
            return 0.025
        if "pro" in model:
            return 0.05
        return 0.03  # dev tier

    def execute(self, inputs: dict[str, Any]) -> ToolResult:
        _, output_error = require_explicit_output_path(
            inputs, self.name, artifact_label="generated image"
        )
        if output_error:
            return output_error

        api_key = self._get_api_key()
        if not api_key:
            return ToolResult(
                success=False,
                error="No fal.ai API key found. " + self.install_instructions,
            )

        import requests

        start = time.time()
        model = inputs.get("model", "flux-2-pro")
        prompt = inputs["prompt"]
        width = inputs.get("width", 1024)
        height = inputs.get("height", 1024)

        payload: dict[str, Any] = {
            "prompt": prompt,
            "image_size": {"width": width, "height": height},
        }
        if inputs.get("seed") is not None:
            payload["seed"] = inputs["seed"]
        if inputs.get("num_inference_steps"):
            payload["num_inference_steps"] = inputs["num_inference_steps"]
        if inputs.get("guidance_scale"):
            payload["guidance_scale"] = inputs["guidance_scale"]
        if inputs.get("negative_prompt"):
            payload["negative_prompt"] = inputs["negative_prompt"]

        try:
            response = requests.post(
                f"https://fal.run/fal-ai/{model}",
                headers={
                    "Authorization": f"Key {api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=120,
            )
            response.raise_for_status()
            data = response.json()

            image_url = data["images"][0]["url"]
            image_response = requests.get(image_url, timeout=60)
            image_response.raise_for_status()

            output_path = Path(inputs["output_path"])
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(image_response.content)

        except Exception as e:
            return ToolResult(success=False, error=f"FLUX generation failed: {e}")

        return ToolResult(
            success=True,
            data={
                "provider": "flux",
                "model": model,
                "prompt": prompt,
                "output": str(output_path),
                "output_path": str(output_path),
                "seed": data.get("seed"),
            },
            artifacts=[str(output_path)],
            cost_usd=self.estimate_cost(inputs),
            duration_seconds=round(time.time() - start, 2),
            seed=data.get("seed"),
            model=f"fal-ai/{model}",
        )
