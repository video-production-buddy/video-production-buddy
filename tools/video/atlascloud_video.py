"""Atlas Cloud video generation via the Media Generation API.

Uses Atlas Cloud's async task flow:
submit video generation -> poll prediction -> download video.
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
from tools.video._shared import probe_output, require_generated_video_output_path

_DEFAULT_MEDIA_BASE_URL = "https://api.atlascloud.ai/api/v1"
_MODEL_SOURCE_URL = "https://api.atlascloud.ai/api/v1/models"
_TEXT_MODEL = "bytedance/seedance-2.0-fast/text-to-video"
_IMAGE_MODEL = "bytedance/seedance-2.0-fast/image-to-video"
_REFERENCE_MODEL = "bytedance/seedance-2.0-fast/reference-to-video"
_OP_DEFAULTS = {
    "text_to_video": _TEXT_MODEL,
    "image_to_video": _IMAGE_MODEL,
    "reference_to_video": _REFERENCE_MODEL,
}
_MODELS: dict[str, dict[str, Any]] = {
    _TEXT_MODEL: {
        "name": "Seedance 2.0 Fast Text-to-Video",
        "operation": "text_to_video",
        "quality": "high",
        "speed": "fast",
        "cost_per_generation": 0.072,
        "last_verified": "2026-07-22",
        "schema_url": (
            "https://static.atlascloud.ai/model/schema/"
            "bytedance-seedance-2.0-fast-text-to-video.json"
        ),
    },
    _IMAGE_MODEL: {
        "name": "Seedance 2.0 Fast Image-to-Video",
        "operation": "image_to_video",
        "quality": "high",
        "speed": "fast",
        "cost_per_generation": 0.072,
        "last_verified": "2026-07-22",
        "schema_url": (
            "https://static.atlascloud.ai/model/schema/"
            "bytedance-seedance-2.0-fast-image-to-video.json"
        ),
    },
    _REFERENCE_MODEL: {
        "name": "Seedance 2.0 Fast Reference-to-Video",
        "operation": "reference_to_video",
        "quality": "high",
        "speed": "fast",
        "cost_per_generation": 0.072,
        "last_verified": "2026-07-22",
        "schema_url": (
            "https://static.atlascloud.ai/model/schema/"
            "bytedance-seedance-2.0-fast-reference-to-video.json"
        ),
    },
}
_DURATIONS = [-1, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15]
_RESOLUTIONS = ["480p", "720p", "720p-SR", "1080p-SR", "1440p-SR"]
_RATIOS = ["16:9", "4:3", "1:1", "3:4", "9:16", "21:9", "adaptive"]


def _api_key() -> str | None:
    return os.environ.get("ATLASCLOUD_API_KEY") or os.environ.get("ATLAS_CLOUD_API_KEY")


def _media_base_url() -> str:
    return os.environ.get("ATLASCLOUD_MEDIA_API_BASE", _DEFAULT_MEDIA_BASE_URL).rstrip("/")


def _prediction_id(payload: dict[str, Any]) -> str | None:
    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    for key in ("id", "prediction_id", "request_id", "task_id"):
        value = data.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def _status_payload(payload: dict[str, Any]) -> dict[str, Any]:
    data = payload.get("data")
    if isinstance(data, dict):
        return data
    return payload


def _collect_urls(value: Any) -> list[str]:
    urls: list[str] = []
    if isinstance(value, str):
        if value.startswith(("http://", "https://")):
            urls.append(value)
        return urls
    if isinstance(value, list):
        for item in value:
            urls.extend(_collect_urls(item))
        return urls
    if isinstance(value, dict):
        for key in ("url", "video", "video_url", "download_url", "output_url"):
            candidate = value.get(key)
            if isinstance(candidate, str) and candidate.startswith(
                ("http://", "https://")
            ):
                urls.append(candidate)
        for key in ("outputs", "output", "result", "results", "videos", "data"):
            if key in value:
                urls.extend(_collect_urls(value[key]))
    return urls


class AtlasCloudVideo(BaseTool):
    name = "atlascloud_video"
    version = "0.1.0"
    tier = ToolTier.GENERATE
    capability = "video_generation"
    provider = "atlascloud"
    stability = ToolStability.BETA
    execution_mode = ExecutionMode.SYNC
    determinism = Determinism.STOCHASTIC
    runtime = ToolRuntime.API

    dependencies = ["env:ATLASCLOUD_API_KEY"]
    install_instructions = (
        "Set ATLASCLOUD_API_KEY to your Atlas Cloud API key.\n"
        "  Get one at https://www.atlascloud.ai/console/api-keys"
    )
    agent_skills = ["atlas-cloud", "ai-video-gen"]

    capabilities = ["text_to_video", "image_to_video", "reference_to_video"]
    supports = {
        "text_to_video": True,
        "image_to_video": True,
        "reference_to_video": True,
        "multiple_reference_images": True,
        "reference_image": True,
        "native_audio": True,
        "aspect_ratio": True,
        "seed": True,
    }
    best_for = [
        "Atlas Cloud Seedance 2.0 Fast video generation with one API key",
        "text-to-video, image-to-video, and reference-conditioned video workflows",
        "short production clips with synchronized audio and live Atlas Cloud model routing",
    ]
    not_good_for = ["offline generation", "long-form video rendering"]
    fallback_tools = ["seedance_video", "wan_video_api", "kling_video"]
    quality_score = 0.9
    model_options = [
        {
            "id": model_id,
            "name": meta["name"],
            "field": "model_variant",
            "default_for_operations": [meta["operation"]],
            "operation": meta["operation"],
            "quality": meta["quality"],
            "speed": meta["speed"],
            "cost_hint": {"usd": meta["cost_per_generation"], "unit": "per_generation"},
            "last_verified": meta["last_verified"],
            "source_url": _MODEL_SOURCE_URL,
            "schema_url": meta["schema_url"],
        }
        for model_id, meta in _MODELS.items()
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
                        {"required": ["image"]},
                        {"required": ["image_url"]},
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
                "enum": list(_MODELS),
                "description": "Atlas Cloud Seedance model id. Omit to use the operation default.",
            },
            "model": {
                "type": "string",
                "enum": list(_MODELS),
                "description": "Alias for model_variant.",
            },
            "duration": {
                "type": "integer",
                "enum": _DURATIONS,
                "default": 5,
                "description": "Duration in seconds, or -1 to let the model decide.",
            },
            "resolution": {
                "type": "string",
                "enum": _RESOLUTIONS,
                "default": "720p",
            },
            "ratio": {
                "type": "string",
                "enum": _RATIOS,
                "default": "adaptive",
            },
            "aspect_ratio": {
                "type": "string",
                "enum": _RATIOS,
                "default": "adaptive",
                "description": "Selector-friendly alias mapped to Atlas Cloud's ratio field.",
            },
            "bitrate_mode": {
                "type": "string",
                "enum": ["standard", "high"],
                "default": "standard",
            },
            "generate_audio": {"type": "boolean", "default": True},
            "seed": {"type": "integer", "minimum": -1, "maximum": 4294967295},
            "watermark": {"type": "boolean", "default": False},
            "image": {
                "type": "string",
                "description": "First-frame image URL, Base64, or asset reference for image_to_video.",
            },
            "image_url": {
                "type": "string",
                "description": "Alias for image. Atlas Cloud accepts image URLs in the image field.",
            },
            "last_image": {
                "type": "string",
                "description": "Optional last-frame image URL, Base64, or asset reference.",
            },
            "last_image_url": {
                "type": "string",
                "description": "Alias for last_image.",
            },
            "reference_image_urls": {
                "type": "array",
                "items": {"type": "string"},
                "minItems": 1,
                "maxItems": 9,
            },
            "reference_video_urls": {
                "type": "array",
                "items": {"type": "string"},
                "minItems": 1,
                "maxItems": 3,
            },
            "reference_audio_urls": {
                "type": "array",
                "items": {"type": "string"},
                "minItems": 1,
                "maxItems": 3,
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
            "duration",
            "resolution",
            "ratio",
            "generate_audio",
            "seed",
            "output",
            "output_path",
            "format",
        ],
        "properties": {
            "provider": {"type": "string", "const": "atlascloud"},
            "model": {"type": "string"},
            "prompt": {"type": "string"},
            "operation": {
                "type": "string",
                "enum": ["text_to_video", "image_to_video", "reference_to_video"],
            },
            "duration": {"type": "integer"},
            "resolution": {"type": "string"},
            "ratio": {"type": "string"},
            "bitrate_mode": {"type": "string"},
            "generate_audio": {"type": "boolean"},
            "seed": {"type": ["integer", "null"]},
            "prediction_id": {"type": "string"},
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
        "model",
        "operation",
        "duration",
        "resolution",
        "ratio",
        "aspect_ratio",
        "bitrate_mode",
        "generate_audio",
        "seed",
        "watermark",
        "image",
        "image_url",
        "last_image",
        "last_image_url",
        "reference_image_urls",
        "reference_video_urls",
        "reference_audio_urls",
    ]
    side_effects = ["writes video file to output_path", "calls Atlas Cloud Media API"]
    user_visible_verification = ["Inspect sampled frames for motion coherence and visual quality"]

    def get_status(self) -> ToolStatus:
        return ToolStatus.AVAILABLE if _api_key() else ToolStatus.UNAVAILABLE

    def estimate_cost(self, inputs: dict[str, Any]) -> float:
        operation = inputs.get("operation", "text_to_video")
        model = (
            inputs.get("model_variant")
            or inputs.get("model")
            or _OP_DEFAULTS.get(operation, _TEXT_MODEL)
        )
        return float(_MODELS.get(str(model), _MODELS[_TEXT_MODEL])["cost_per_generation"])

    def estimate_runtime(self, inputs: dict[str, Any]) -> float:
        return 90.0

    def execute(self, inputs: dict[str, Any]) -> ToolResult:
        operation = inputs.get("operation", "text_to_video")
        if operation not in _OP_DEFAULTS:
            return ToolResult(
                success=False,
                error=(
                    f"Unknown operation {operation!r}. Valid values: "
                    f"{', '.join(sorted(_OP_DEFAULTS))}."
                ),
            )

        model = inputs.get("model_variant") or inputs.get("model") or _OP_DEFAULTS[operation]
        if model not in _MODELS:
            return ToolResult(
                success=False,
                error=(
                    f"Unknown model_variant {model!r}. "
                    f"Available: {', '.join(sorted(_MODELS))}."
                ),
            )
        model_operation = _MODELS[model]["operation"]
        if model_operation != operation:
            return ToolResult(
                success=False,
                error=(
                    f"model_variant {model!r} supports {model_operation}, "
                    f"but operation is {operation}. Choose a matching model_variant "
                    "or omit model_variant to use the operation default."
                ),
            )

        validation_error = self._validate_conditioning_inputs(inputs, operation)
        if validation_error:
            return ToolResult(success=False, error=validation_error)

        output_path, output_error = require_generated_video_output_path(inputs, self.name)
        if output_error:
            return output_error

        api_key = _api_key()
        if not api_key:
            return ToolResult(
                success=False,
                error="ATLASCLOUD_API_KEY not set. " + self.install_instructions,
            )

        import requests

        start = time.time()
        payload = self._build_payload(inputs, str(model), operation)
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        try:
            submit = requests.post(
                f"{_media_base_url()}/model/generateVideo",
                headers=headers,
                json=payload,
                timeout=30,
            )
            submit.raise_for_status()
            task_id = _prediction_id(submit.json())
            if not task_id:
                return ToolResult(
                    success=False,
                    error="Atlas Cloud video generation returned no prediction id",
                )

            result_payload = self._poll_prediction(task_id, headers)
            urls = _collect_urls(result_payload)
            if not urls:
                return ToolResult(
                    success=False,
                    error="Atlas Cloud video generation completed without an output URL",
                )

            video_response = requests.get(urls[0], timeout=300)
            video_response.raise_for_status()
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(video_response.content)

        except Exception as exc:
            return ToolResult(success=False, error=f"Atlas Cloud video generation failed: {exc}")

        probed = probe_output(output_path)
        return ToolResult(
            success=True,
            data={
                "provider": self.provider,
                "model": model,
                "prompt": inputs["prompt"],
                "operation": operation,
                "duration": payload.get("duration", 5),
                "resolution": payload.get("resolution", "720p"),
                "ratio": payload.get("ratio", "adaptive"),
                "bitrate_mode": payload.get("bitrate_mode", "standard"),
                "generate_audio": payload.get("generate_audio", True),
                "seed": payload.get("seed"),
                "prediction_id": task_id,
                "output": str(output_path),
                "output_path": str(output_path),
                "format": "mp4",
                **probed,
            },
            artifacts=[str(output_path)],
            cost_usd=self.estimate_cost(inputs),
            duration_seconds=round(time.time() - start, 2),
            seed=payload.get("seed"),
            model=str(model),
        )

    def _build_payload(
        self,
        inputs: dict[str, Any],
        model: str,
        operation: str,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": model,
            "prompt": inputs["prompt"],
            "duration": inputs.get("duration", 5),
            "resolution": inputs.get("resolution", "720p"),
            "ratio": inputs.get("ratio") or inputs.get("aspect_ratio", "adaptive"),
            "bitrate_mode": inputs.get("bitrate_mode", "standard"),
            "generate_audio": inputs.get("generate_audio", True),
            "watermark": inputs.get("watermark", False),
        }
        if inputs.get("seed") is not None:
            payload["seed"] = inputs["seed"]

        if operation == "image_to_video":
            payload["image"] = inputs.get("image") or inputs.get("image_url")
            if inputs.get("last_image") or inputs.get("last_image_url"):
                payload["last_image"] = inputs.get("last_image") or inputs.get("last_image_url")

        if operation == "reference_to_video":
            if inputs.get("reference_image_urls"):
                payload["reference_images"] = inputs["reference_image_urls"]
            if inputs.get("reference_video_urls"):
                payload["reference_videos"] = inputs["reference_video_urls"]
            if inputs.get("reference_audio_urls"):
                payload["reference_audios"] = inputs["reference_audio_urls"]

        return payload

    @staticmethod
    def _validate_conditioning_inputs(
        inputs: dict[str, Any],
        operation: str,
    ) -> str | None:
        if operation == "image_to_video" and not (inputs.get("image") or inputs.get("image_url")):
            return "image_to_video requires image or image_url"
        if operation == "reference_to_video":
            if not any(
                inputs.get(key)
                for key in (
                    "reference_image_urls",
                    "reference_video_urls",
                    "reference_audio_urls",
                )
            ):
                return (
                    "reference_to_video requires reference_image_urls, "
                    "reference_video_urls, or reference_audio_urls"
                )
        return None

    def _poll_prediction(self, task_id: str, headers: dict[str, str]) -> dict[str, Any]:
        import requests

        deadline = time.time() + 600
        while True:
            response = requests.get(
                f"{_media_base_url()}/model/prediction/{task_id}",
                headers=headers,
                timeout=30,
            )
            response.raise_for_status()
            payload = response.json()
            data = _status_payload(payload)
            status = str(data.get("status", "")).lower()
            if status in {"completed", "succeeded", "success"}:
                return data
            if status in {"failed", "error", "canceled", "cancelled"}:
                message = data.get("error") or data.get("message") or status
                raise RuntimeError(f"Atlas Cloud video generation {message}")
            if time.time() >= deadline:
                raise TimeoutError("Atlas Cloud video generation timed out")
            time.sleep(5)
