"""Seedance 2.0 (ByteDance) video generation via fal.ai API.

Best for cinematic clips with native audio, director-level camera control,
and lip-sync from quoted dialogue in prompts.
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
from tools.video._shared import require_generated_video_output_path


class SeedanceVideo(BaseTool):
    name = "seedance_video"
    version = "0.2.0"
    tier = ToolTier.GENERATE
    capability = "video_generation"
    provider = "seedance"
    stability = ToolStability.BETA
    execution_mode = ExecutionMode.SYNC
    determinism = Determinism.STOCHASTIC
    runtime = ToolRuntime.API

    dependencies = ["env_any:FAL_KEY,FAL_AI_API_KEY"]
    install_instructions = (
        "Set FAL_KEY to your fal.ai API key.\n"
        "  Get one at https://fal.ai/dashboard/keys"
    )
    agent_skills = ["seedance-2-0", "ai-video-gen"]

    capabilities = ["text_to_video", "image_to_video", "reference_to_video"]
    supports = {
        "text_to_video": True,
        "image_to_video": True,
        "reference_to_video": True,
        "multiple_reference_images": True,
        "reference_image": True,
        "native_audio": True,
        "cinematic_quality": True,
        "camera_direction": True,
        "lip_sync": True,
        "multi_shot": True,
        "aspect_ratio": True,
        "seed": True,
    }
    best_for = [
        "preferred premium video gen when FAL_KEY is available",
        "cinematic trailers, teasers, and high-fidelity clips with native synchronized audio",
        "director-level camera control and multi-shot editing in a single generation",
        "lip-sync from quoted dialogue in prompts",
        "reference-conditioned generation (up to 9 images + 3 video clips + 3 audio clips)",
        "consistent character identity across shots",
    ]
    not_good_for = ["offline generation", "budget-constrained projects"]
    fallback_tools = ["veo_video", "kling_video", "minimax_video"]
    # Premium model — beat out "experimental stability" baseline. The scoring
    # engine reads quality_score directly when present (see lib/scoring.py).
    quality_score = 0.95
    model_options = [
        {
            "id": "standard",
            "name": "Seedance 2.0 Standard",
            "field": "model_variant",
            "default": True,
            "quality": "highest",
            "speed": "medium",
            "cost_hint": {"usd": 0.3034, "unit": "per_second"},
            "note": "Highest quality Seedance route with native audio support.",
        },
        {
            "id": "fast",
            "name": "Seedance 2.0 Fast",
            "field": "model_variant",
            "default": False,
            "quality": "high",
            "speed": "fast",
            "cost_hint": {"usd": 0.2419, "unit": "per_second"},
            "note": "Lower-latency and lower-cost variant.",
        },
    ]

    input_schema = {
        "type": "object",
        "required": ["prompt", "output_path"],
        "allOf": [
            {
                "if": {
                    "properties": {"operation": {"const": "image_to_video"}},
                    "required": ["operation"],
                },
                "then": {
                    "anyOf": [
                        {"required": ["image_url"]},
                        {"required": ["image_path"]},
                    ]
                },
            },
            {
                "if": {
                    "properties": {"operation": {"const": "reference_to_video"}},
                    "required": ["operation"],
                },
                "then": {
                    "anyOf": [
                        {"required": ["reference_image_urls"]},
                        {"required": ["reference_image_paths"]},
                        {"required": ["reference_video_urls"]},
                        {"required": ["reference_audio_urls"]},
                    ]
                },
            },
        ],
        "properties": {
            "prompt": {"type": "string"},
            "operation": {
                "type": "string",
                "enum": ["text_to_video", "image_to_video", "reference_to_video"],
                "default": "text_to_video",
            },
            "model_variant": {
                "type": "string",
                "enum": ["standard", "fast"],
                "default": "standard",
                "description": "standard = highest quality, fast = lower latency and cost",
            },
            "duration": {
                "type": "string",
                "enum": ["auto", "4", "5", "6", "7", "8", "9", "10", "11", "12", "13", "14", "15"],
                "default": "5",
                "description": "Duration in seconds. 'auto' lets the model decide.",
            },
            "aspect_ratio": {
                "type": "string",
                "enum": ["auto", "21:9", "16:9", "4:3", "1:1", "3:4", "9:16"],
                "default": "16:9",
            },
            "resolution": {
                "type": "string",
                "enum": ["480p", "720p"],
                "default": "720p",
            },
            "generate_audio": {
                "type": "boolean",
                "default": True,
                "description": "Generate synchronized audio (speech, SFX, ambient)",
            },
            "image_url": {
                "type": "string",
                "minLength": 1,
                "description": "Start frame image URL for image_to_video (jpg, png, webp)",
            },
            "image_path": {
                "type": "string",
                "minLength": 1,
                "description": "Local start-frame path for image_to_video. Auto-uploaded to fal.ai storage.",
            },
            "end_image_url": {
                "type": "string",
                "minLength": 1,
                "description": "Optional end frame URL for image_to_video",
            },
            "reference_image_urls": {
                "type": "array",
                "items": {"type": "string"},
                "minItems": 1,
                "description": "Up to 9 reference image URLs for reference_to_video (identity / wardrobe / setting / style anchors).",
            },
            "reference_image_paths": {
                "type": "array",
                "items": {"type": "string"},
                "minItems": 1,
                "description": "Local reference image paths for reference_to_video. Auto-uploaded to fal.ai storage.",
            },
            "reference_video_urls": {
                "type": "array",
                "items": {"type": "string"},
                "minItems": 1,
                "description": "Up to 3 reference video clip URLs for reference_to_video (motion / camera / pacing anchors).",
            },
            "reference_audio_urls": {
                "type": "array",
                "items": {"type": "string"},
                "minItems": 1,
                "description": "Up to 3 reference audio clip URLs for reference_to_video (voice / music / ambience anchors).",
            },
            "seed": {
                "type": "integer",
                "description": "Optional seed for reproducibility",
            },
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
            "variant",
            "aspect_ratio",
            "resolution",
            "generate_audio",
            "seed",
            "output",
            "output_path",
            "format",
        ],
        "properties": {
            "provider": {"type": "string", "const": "seedance"},
            "model": {"type": "string"},
            "prompt": {"type": "string"},
            "operation": {
                "type": "string",
                "enum": ["text_to_video", "image_to_video", "reference_to_video"],
            },
            "variant": {"type": "string", "enum": ["standard", "fast"]},
            "aspect_ratio": {"type": "string"},
            "resolution": {"type": "string"},
            "generate_audio": {"type": "boolean"},
            "seed": {"type": ["integer", "null"]},
            "output": {"type": "string"},
            "output_path": {"type": "string"},
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
    retry_policy = RetryPolicy(max_retries=2, retryable_errors=["rate_limit", "timeout"])
    idempotency_key_fields = [
        "prompt",
        "output_path",
        "model_variant",
        "operation",
        "duration",
        "aspect_ratio",
        "resolution",
        "generate_audio",
        "image_url",
        "image_path",
        "end_image_url",
        "reference_image_urls",
        "reference_image_paths",
        "reference_video_urls",
        "reference_audio_urls",
        "seed",
    ]
    side_effects = ["writes video file to output_path", "calls fal.ai API"]
    user_visible_verification = [
        "Inspect sampled frames and timing metadata for motion coherence, audio sync, and visual quality"
    ]

    def _get_api_key(self) -> str | None:
        return os.environ.get("FAL_KEY") or os.environ.get("FAL_AI_API_KEY")

    def get_status(self) -> ToolStatus:
        if self._get_api_key():
            return ToolStatus.AVAILABLE
        return ToolStatus.UNAVAILABLE

    def estimate_cost(self, inputs: dict[str, Any]) -> float:
        variant = inputs.get("model_variant", "standard")
        duration = inputs.get("duration", "5")
        secs = 5 if duration == "auto" else int(duration)
        rate = 0.2419 if variant == "fast" else 0.3034
        return round(rate * secs, 2)

    def estimate_runtime(self, inputs: dict[str, Any]) -> float:
        variant = inputs.get("model_variant", "standard")
        return 60.0 if variant == "fast" else 120.0

    def execute(self, inputs: dict[str, Any]) -> ToolResult:
        operation = inputs.get("operation", "text_to_video")
        variant = inputs.get("model_variant", "standard")
        if operation not in {"text_to_video", "image_to_video", "reference_to_video"}:
            return ToolResult(
                success=False,
                error=(
                    f"Unknown operation {operation!r}. "
                    "Valid values: text_to_video, image_to_video, reference_to_video."
                ),
            )
        if variant not in {"standard", "fast"}:
            return ToolResult(
                success=False,
                error="Unknown model_variant {!r}. Valid values: standard, fast.".format(variant),
            )
        if operation == "image_to_video" and not (
            inputs.get("image_url") or inputs.get("image_path")
        ):
            return ToolResult(
                success=False,
                error="image_to_video requires image_url or image_path",
            )
        if operation == "reference_to_video" and not any(
            inputs.get(key)
            for key in (
                "reference_image_urls",
                "reference_image_paths",
                "reference_video_urls",
                "reference_audio_urls",
            )
        ):
            return ToolResult(
                success=False,
                error=(
                    "reference_to_video requires reference_image_urls, "
                    "reference_image_paths, reference_video_urls, or reference_audio_urls"
                ),
            )
        output_path, output_error = require_generated_video_output_path(inputs, self.name)
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
        operation_path = operation.replace("_", "-")

        if variant == "fast":
            model_path = f"bytedance/seedance-2.0/fast/{operation_path}"
        else:
            model_path = f"bytedance/seedance-2.0/{operation_path}"

        payload: dict[str, Any] = {"prompt": inputs["prompt"]}

        if inputs.get("duration"):
            payload["duration"] = inputs["duration"]
        if inputs.get("aspect_ratio"):
            payload["aspect_ratio"] = inputs["aspect_ratio"]
        if inputs.get("resolution"):
            payload["resolution"] = inputs["resolution"]
        if "generate_audio" in inputs:
            payload["generate_audio"] = inputs["generate_audio"]
        if inputs.get("seed") is not None:
            payload["seed"] = inputs["seed"]

        if operation == "image_to_video":
            if inputs.get("image_url"):
                payload["image_url"] = inputs["image_url"]
            elif inputs.get("image_path"):
                from tools.video._shared import upload_image_fal
                payload["image_url"] = upload_image_fal(inputs["image_path"])
            if inputs.get("end_image_url"):
                payload["end_image_url"] = inputs["end_image_url"]

        if operation == "reference_to_video":
            ref_image_urls = list(inputs.get("reference_image_urls") or [])
            for local_path in inputs.get("reference_image_paths") or []:
                from tools.video._shared import upload_image_fal
                ref_image_urls.append(upload_image_fal(local_path))
            # Seedance 2.0 reference-to-video ceilings: 9 images + 3 video + 3 audio.
            if len(ref_image_urls) > 9:
                return ToolResult(
                    success=False,
                    error=f"Seedance 2.0 reference_to_video accepts at most 9 reference images; got {len(ref_image_urls)}",
                )
            ref_video_urls = list(inputs.get("reference_video_urls") or [])
            if len(ref_video_urls) > 3:
                return ToolResult(
                    success=False,
                    error=f"Seedance 2.0 reference_to_video accepts at most 3 reference videos; got {len(ref_video_urls)}",
                )
            ref_audio_urls = list(inputs.get("reference_audio_urls") or [])
            if len(ref_audio_urls) > 3:
                return ToolResult(
                    success=False,
                    error=f"Seedance 2.0 reference_to_video accepts at most 3 reference audio clips; got {len(ref_audio_urls)}",
                )
            if ref_image_urls:
                payload["reference_image_urls"] = ref_image_urls
            if ref_video_urls:
                payload["reference_video_urls"] = ref_video_urls
            if ref_audio_urls:
                payload["reference_audio_urls"] = ref_audio_urls

        headers = {
            "Authorization": f"Key {api_key}",
            "Content-Type": "application/json",
        }

        try:
            submit_url = f"https://queue.fal.run/{model_path}"
            submit_resp = requests.post(
                submit_url,
                headers=headers,
                json=payload,
                timeout=30,
            )
            submit_resp.raise_for_status()
            queue_data = submit_resp.json()
            request_id = queue_data["request_id"]
            fallback_base = f"{submit_url}/requests/{request_id}"

            # Prefer fal.ai's returned queue URLs. If they are absent or missing
            # this model path, fall back to the same queue path used for POST.
            returned_status_url = queue_data.get("status_url")
            returned_response_url = queue_data.get("response_url")
            model_request_path = f"/{model_path}/requests/"
            status_url = (
                returned_status_url
                if returned_status_url and model_request_path in returned_status_url
                else f"{fallback_base}/status"
            )
            response_url = (
                returned_response_url
                if returned_response_url and model_request_path in returned_response_url
                else fallback_base
            )

            while True:
                time.sleep(5)
                status_resp = requests.get(status_url, headers=headers, timeout=15)
                status_resp.raise_for_status()
                status = status_resp.json().get("status", "UNKNOWN")
                if status == "COMPLETED":
                    break
                if status in ("FAILED", "CANCELLED"):
                    return ToolResult(
                        success=False,
                        error=f"Seedance 2.0 video generation {status.lower()}",
                    )

            result_resp = requests.get(response_url, headers=headers, timeout=30)
            result_resp.raise_for_status()
            data = result_resp.json()

            video_url = data["video"]["url"]
            video_response = requests.get(video_url, timeout=120)
            video_response.raise_for_status()

            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(video_response.content)

        except Exception as e:
            return ToolResult(
                success=False,
                error=f"Seedance 2.0 video generation failed: {e}",
            )

        from tools.video._shared import probe_output

        probed = probe_output(output_path)
        return ToolResult(
            success=True,
            data={
                "provider": "seedance",
                "model": model_path,
                "prompt": inputs["prompt"],
                "operation": operation,
                "variant": variant,
                "aspect_ratio": inputs.get("aspect_ratio", "16:9"),
                "resolution": inputs.get("resolution", "720p"),
                "generate_audio": inputs.get("generate_audio", True),
                "seed": data.get("seed"),
                "output": str(output_path),
                "output_path": str(output_path),
                "format": "mp4",
                **probed,
            },
            artifacts=[str(output_path)],
            cost_usd=self.estimate_cost(inputs),
            duration_seconds=round(time.time() - start, 2),
            model=model_path,
        )
