"""OpenAI GPT Image generation (GPT Image 2 / GPT Image 1 / DALL-E 3)."""

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
from tools.output_paths import require_explicit_output_path


class OpenAIImage(BaseTool):
    name = "openai_image"
    version = "0.1.0"
    tier = ToolTier.GENERATE
    capability = "image_generation"
    provider = "openai"
    stability = ToolStability.BETA
    execution_mode = ExecutionMode.SYNC
    determinism = Determinism.STOCHASTIC
    runtime = ToolRuntime.API

    dependencies = ["env:OPENAI_API_KEY"]
    install_instructions = (
        "Set OPENAI_API_KEY to your OpenAI API key.\n"
        "  pip install openai"
    )
    agent_skills = ["flux-best-practices"]  # general image gen knowledge

    capabilities = ["generate_image", "generate_illustration", "text_to_image"]
    supports = {
        "complex_instructions": True,
        "text_in_image": True,
        "multiple_outputs": True,
    }
    best_for = [
        "complex multi-element compositions",
        "images with text/labels",
        "following detailed instructions accurately",
    ]
    not_good_for = ["offline generation", "budget-constrained projects at high quality"]
    model_options = [
        {
            "id": "gpt-image-2",
            "name": "GPT Image 2",
            "field": "model",
            "default": True,
            "quality": "highest",
            "speed": "medium",
            "release_stage": "current_sota",
            "last_verified": "2026-06-28",
            "source_url": "https://developers.openai.com/api/docs/guides/image-generation",
        },
        {
            "id": "gpt-image-1",
            "name": "GPT Image 1",
            "field": "model",
            "default": False,
            "quality": "high",
            "speed": "medium",
            "release_stage": "legacy",
            "last_verified": "2026-06-28",
            "source_url": "https://developers.openai.com/api/docs/guides/image-generation",
        },
        {
            "id": "dall-e-3",
            "name": "DALL-E 3",
            "field": "model",
            "default": False,
            "quality": "legacy_high",
            "speed": "medium",
            "release_stage": "legacy",
            "last_verified": "2026-06-28",
            "source_url": "https://platform.openai.com/docs/models",
        },
    ]

    input_schema = {
        "type": "object",
        "required": ["prompt", "output_path"],
        "properties": {
            "prompt": {"type": "string"},
            "model": {
                "type": "string",
                "enum": ["gpt-image-2", "gpt-image-1", "dall-e-3"],
                "default": "gpt-image-2",
            },
            "size": {
                "type": "string",
                "enum": [
                    "1024x1024", "1536x1024", "1024x1536", "auto",
                    "1024x1792", "1792x1024",  # dall-e-3 only
                ],
                "default": "1024x1024",
            },
            "quality": {
                "type": "string",
                "enum": ["low", "medium", "high", "auto", "standard", "hd"],
                "default": "high",
            },
            "output_format": {
                "type": "string",
                "enum": ["png", "jpeg", "webp"],
                "default": "png",
            },
            "n": {"type": "integer", "default": 1, "minimum": 1, "maximum": 4},
            "output_path": {"type": "string"},
        },
    }
    output_schema = {
        "type": "object",
        "required": ["provider", "model", "prompt", "output", "output_path"],
        "properties": {
            "provider": {"type": "string", "const": "openai"},
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
        "size",
        "quality",
        "model",
        "output_format",
        "n",
    ]
    side_effects = ["writes image file to output_path", "calls OpenAI API"]
    user_visible_verification = ["Inspect generated image for relevance and quality"]

    def get_status(self) -> ToolStatus:
        if os.environ.get("OPENAI_API_KEY"):
            return ToolStatus.AVAILABLE
        return ToolStatus.UNAVAILABLE

    def estimate_cost(self, inputs: dict[str, Any]) -> float:
        model = inputs.get("model", "gpt-image-2")
        quality = inputs.get("quality", "high")
        n = inputs.get("n", 1)
        if model == "gpt-image-2":
            cost_map = {"low": 0.016, "medium": 0.063, "high": 0.25, "auto": 0.063}
            return cost_map.get(quality, 0.063) * n
        if model == "gpt-image-1":
            cost_map = {"low": 0.011, "medium": 0.042, "high": 0.167, "auto": 0.042}
            return cost_map.get(quality, 0.042) * n
        # dall-e-3 fallback pricing
        quality_map = {"standard": 0.04, "hd": 0.08}
        return quality_map.get(quality, 0.04) * n

    def execute(self, inputs: dict[str, Any]) -> ToolResult:
        _, output_error = require_explicit_output_path(
            inputs, self.name, artifact_label="generated image"
        )
        if output_error:
            return output_error

        if not os.environ.get("OPENAI_API_KEY"):
            return ToolResult(
                success=False,
                error="OPENAI_API_KEY not set. " + self.install_instructions,
            )

        from openai import OpenAI

        start = time.time()
        client = OpenAI()
        model = inputs.get("model", "gpt-image-2")
        prompt = inputs["prompt"]
        size = inputs.get("size", "1024x1024")
        n = inputs.get("n", 1)

        try:
            if model in {"gpt-image-2", "gpt-image-1"}:
                quality = inputs.get("quality", "high")
                output_format = inputs.get("output_format", "png")
                response = client.images.generate(
                    model=model,
                    prompt=prompt,
                    size=size,
                    quality=quality,
                    output_format=output_format,
                    n=n,
                )
            else:
                # dall-e-3 path
                quality = inputs.get("quality", "standard")
                if quality in ("low", "medium", "high", "auto"):
                    quality = "standard"  # map to dall-e-3 quality options
                response = client.images.generate(
                    model=model,
                    prompt=prompt,
                    size=size,
                    quality=quality,
                    n=1,  # dall-e-3 only supports n=1
                    response_format="b64_json",
                )

            image_data = base64.b64decode(response.data[0].b64_json)
            output_path = Path(inputs["output_path"])
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(image_data)

        except Exception as e:
            return ToolResult(success=False, error=f"OpenAI image generation failed: {e}")

        return ToolResult(
            success=True,
            data={
                "provider": "openai",
                "model": model,
                "prompt": prompt,
                "output": str(output_path),
                "output_path": str(output_path),
            },
            artifacts=[str(output_path)],
            cost_usd=self.estimate_cost(inputs),
            duration_seconds=round(time.time() - start, 2),
            model=model,
        )
