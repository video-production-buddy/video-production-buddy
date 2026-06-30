"""Recraft V4.1 image generation via fal.ai API.

Best for logos, brand assets, SVG vectors, and images with accurate text rendering.
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
from tools.output_paths import require_explicit_output_path

_MODEL_PATHS = {
    "v4.1": "recraft/v4.1/text-to-image",
    "v4.1-pro": "recraft/v4.1/pro/text-to-image",
    "v4.1-utility": "recraft/v4.1/utility/text-to-image",
    "v4.1-utility-pro": "recraft/v4.1/utility/pro/text-to-image",
    "v4": "recraft/v4/text-to-image",
    "v4-pro": "recraft/v4/pro/text-to-image",
}


class RecraftImage(BaseTool):
    name = "recraft_image"
    version = "0.1.0"
    tier = ToolTier.GENERATE
    capability = "image_generation"
    provider = "recraft"
    stability = ToolStability.EXPERIMENTAL
    execution_mode = ExecutionMode.SYNC
    determinism = Determinism.STOCHASTIC
    runtime = ToolRuntime.API

    dependencies = ["env_any:FAL_KEY,FAL_AI_API_KEY"]
    install_instructions = (
        "Set FAL_KEY to your fal.ai API key.\n"
        "  Get one at https://fal.ai/dashboard/keys"
    )
    agent_skills = ["flux-best-practices"]

    capabilities = [
        "generate_image",
        "generate_logo",
        "generate_vector",
        "text_to_image",
    ]
    supports = {
        "svg_output": True,
        "text_rendering": True,
        "color_palette": True,
        "custom_size": True,
    }
    best_for = [
        "logos and brand assets",
        "SVG vector output",
        "images with accurate text rendering",
        "clean professional graphics",
    ]
    not_good_for = ["photorealistic images", "offline generation"]
    model_options = [
        {
            "id": "v4.1",
            "name": "Recraft V4.1",
            "field": "model",
            "default": True,
            "quality": "highest",
            "speed": "medium",
            "release_stage": "current_sota",
            "last_verified": "2026-06-28",
            "source_url": "https://www.recraft.ai/blog/recraft-v4-1-more-beautiful-by-nature",
        },
        {
            "id": "v4.1-pro",
            "name": "Recraft V4.1 Pro",
            "field": "model",
            "default": False,
            "quality": "highest",
            "speed": "medium",
            "release_stage": "current",
            "last_verified": "2026-06-28",
            "source_url": "https://www.recraft.ai/blog/recraft-v4-1-more-beautiful-by-nature",
        },
        {
            "id": "v4.1-utility",
            "name": "Recraft V4.1 Utility",
            "field": "model",
            "default": False,
            "quality": "high",
            "speed": "fast",
            "release_stage": "current",
            "last_verified": "2026-06-28",
            "source_url": "https://www.recraft.ai/blog/recraft-v4-1-more-beautiful-by-nature",
        },
        {
            "id": "v4.1-utility-pro",
            "name": "Recraft V4.1 Utility Pro",
            "field": "model",
            "default": False,
            "quality": "high",
            "speed": "fast",
            "release_stage": "current",
            "last_verified": "2026-06-28",
            "source_url": "https://www.recraft.ai/blog/recraft-v4-1-more-beautiful-by-nature",
        },
        {
            "id": "v4",
            "name": "Recraft V4",
            "field": "model",
            "default": False,
            "quality": "legacy_high",
            "speed": "medium",
            "release_stage": "legacy",
            "last_verified": "2026-06-28",
            "source_url": "https://www.recraft.ai/docs/api-reference",
        },
        {
            "id": "v4-pro",
            "name": "Recraft V4 Pro",
            "field": "model",
            "default": False,
            "quality": "legacy_high",
            "speed": "medium",
            "release_stage": "legacy",
            "last_verified": "2026-06-28",
            "source_url": "https://www.recraft.ai/docs/api-reference",
        },
    ]

    input_schema = {
        "type": "object",
        "required": ["prompt", "output_path"],
        "properties": {
            "prompt": {"type": "string"},
            "model": {
                "type": "string",
                "enum": [
                    "v4.1",
                    "v4.1-pro",
                    "v4.1-utility",
                    "v4.1-utility-pro",
                    "v4",
                    "v4-pro",
                ],
                "default": "v4.1",
            },
            "image_size": {
                "type": "string",
                "enum": [
                    "square", "square_hd",
                    "landscape_4_3", "landscape_16_9",
                    "portrait_4_3", "portrait_16_9",
                ],
                "default": "square_hd",
            },
            "style": {
                "type": "string",
                "enum": [
                    "any", "realistic_image", "digital_illustration",
                    "vector_illustration", "icon",
                ],
                "default": "any",
            },
            "colors": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Color palette as hex strings, e.g. ['#FF5733', '#2E86C1']",
            },
            "output_path": {"type": "string"},
        },
    }
    output_schema = {
        "type": "object",
        "required": ["provider", "model", "prompt", "output", "output_path"],
        "properties": {
            "provider": {"type": "string", "const": "recraft"},
            "model": {"type": "string"},
            "prompt": {"type": "string"},
            "output": {"type": "string"},
            "output_path": {"type": "string"},
        },
    }

    resource_profile = ResourceProfile(
        cpu_cores=1, ram_mb=512, vram_mb=0, disk_mb=100, network_required=True
    )
    retry_policy = RetryPolicy(max_retries=2, retryable_errors=["rate_limit", "timeout"])
    idempotency_key_fields = [
        "prompt",
        "output_path",
        "model",
        "style",
        "image_size",
        "colors",
    ]
    side_effects = ["writes image file to output_path", "calls fal.ai API"]
    user_visible_verification = ["Inspect generated image for brand accuracy and text readability"]

    def _get_api_key(self) -> str | None:
        return os.environ.get("FAL_KEY") or os.environ.get("FAL_AI_API_KEY")

    def get_status(self) -> ToolStatus:
        if self._get_api_key():
            return ToolStatus.AVAILABLE
        return ToolStatus.UNAVAILABLE

    def estimate_cost(self, inputs: dict[str, Any]) -> float:
        model = inputs.get("model", "v4.1")
        if model in {"v4.1-pro", "v4.1-utility-pro", "v4-pro"}:
            return 0.25
        if model == "v4.1-utility":
            return 0.02
        return 0.04

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
                error="FAL_KEY not set. " + self.install_instructions,
            )

        import requests

        start = time.time()
        model = inputs.get("model", "v4.1")
        prompt = inputs["prompt"]

        model_path = _MODEL_PATHS.get(model, _MODEL_PATHS["v4.1"])

        payload: dict[str, Any] = {"prompt": prompt}
        if inputs.get("image_size"):
            payload["image_size"] = inputs["image_size"]
        if inputs.get("style"):
            # NOTE: As of 2026-04, fal.ai's Recraft V4 endpoint rejects the
            # `style` parameter with a 422 Unprocessable Entity error. The
            # style enum values (digital_illustration, realistic_image, etc.)
            # are NOT accepted by the /fal-ai/recraft/v4/text-to-image route.
            # Workaround: encode the style direction in the prompt text instead
            # (e.g. "digital illustration of..." rather than style="digital_illustration").
            # We still pass the parameter through in case fal.ai re-enables it,
            # but callers should be aware this may fail.
            payload["style"] = inputs["style"]
        if inputs.get("colors"):
            payload["colors"] = inputs["colors"]

        try:
            response = requests.post(
                f"https://fal.run/fal-ai/{model_path}",
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
            return ToolResult(success=False, error=f"Recraft generation failed: {e}")

        return ToolResult(
            success=True,
            data={
                "provider": "recraft",
                "model": model,
                "prompt": prompt,
                "output": str(output_path),
                "output_path": str(output_path),
            },
            artifacts=[str(output_path)],
            cost_usd=self.estimate_cost(inputs),
            duration_seconds=round(time.time() - start, 2),
            model=f"fal-ai/{model_path}",
        )
