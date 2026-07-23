"""Atlas Cloud image generation via the Media Generation API.

Uses Atlas Cloud's async task flow:
submit image generation -> poll prediction -> download image.
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
from tools.output_paths import require_explicit_output_path

_DEFAULT_MEDIA_BASE_URL = "https://api.atlascloud.ai/api/v1"
_DEFAULT_MODEL = "bytedance/seedream-v5.0-lite"
_MODEL_SOURCE_URL = "https://api.atlascloud.ai/api/v1/models"
_SCHEMA_SOURCE_URL = (
    "https://static.atlascloud.ai/model/schema/bytedance-seedream-v5.0-lite.json"
)
_SIZES = [
    "2048*2048",
    "2304*1728",
    "1728*2304",
    "2848*1600",
    "1600*2848",
    "2496*1664",
    "1664*2496",
    "3136*1344",
    "3072*3072",
    "3456*2592",
    "2592*3456",
    "4096*2304",
    "2304*4096",
    "2496*3744",
    "3744*2496",
    "4704*2016",
]


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
        for key in ("url", "image", "image_url", "download_url", "output_url"):
            candidate = value.get(key)
            if isinstance(candidate, str) and candidate.startswith(
                ("http://", "https://")
            ):
                urls.append(candidate)
        for key in ("outputs", "output", "result", "results", "images", "data"):
            if key in value:
                urls.extend(_collect_urls(value[key]))
    return urls


class AtlasCloudImage(BaseTool):
    name = "atlascloud_image"
    version = "0.1.0"
    tier = ToolTier.GENERATE
    capability = "image_generation"
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
    agent_skills = ["atlas-cloud"]

    capabilities = ["generate_image", "text_to_image"]
    supports = {
        "text_to_image": True,
        "custom_size": True,
        "seed": False,
    }
    best_for = [
        "2K and 3K production stills through Atlas Cloud's Media Generation API",
        "teams that want one Atlas Cloud key for both image and video generation",
        "Seedream v5.0 Lite image generation with jpeg/png output",
    ]
    not_good_for = ["offline generation", "image editing"]
    fallback_tools = ["wanx_image", "openai_image", "flux_image"]
    model_options = [
        {
            "id": _DEFAULT_MODEL,
            "name": "Seedream v5.0 Lite",
            "field": "model",
            "default": True,
            "quality": "high",
            "speed": "fast",
            "cost_hint": {"usd": 0.032, "unit": "per_image"},
            "last_verified": "2026-07-22",
            "source_url": _MODEL_SOURCE_URL,
            "schema_url": _SCHEMA_SOURCE_URL,
        }
    ]

    input_schema = {
        "type": "object",
        "required": ["prompt", "output_path"],
        "properties": {
            "prompt": {"type": "string"},
            "model": {
                "type": "string",
                "enum": [_DEFAULT_MODEL],
                "default": _DEFAULT_MODEL,
            },
            "size": {
                "type": "string",
                "enum": _SIZES,
                "default": "2048*2048",
            },
            "output_format": {
                "type": "string",
                "enum": ["jpeg", "png"],
                "default": "jpeg",
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
            "size",
            "output_format",
            "output",
            "output_path",
        ],
        "properties": {
            "provider": {"type": "string", "const": "atlascloud"},
            "model": {"type": "string"},
            "prompt": {"type": "string"},
            "size": {"type": "string"},
            "output_format": {"type": "string"},
            "prediction_id": {"type": "string"},
            "output": {"type": "string"},
            "output_path": {"type": "string"},
        },
    }

    resource_profile = ResourceProfile(
        cpu_cores=1, ram_mb=512, vram_mb=0, disk_mb=100, network_required=True
    )
    retry_policy = RetryPolicy(max_retries=2, retryable_errors=["rate_limit", "timeout"])
    idempotency_key_fields = ["prompt", "model", "size", "output_format", "output_path"]
    side_effects = ["writes image file to output_path", "calls Atlas Cloud Media API"]
    user_visible_verification = ["Inspect generated image for relevance and quality"]

    def get_status(self) -> ToolStatus:
        return ToolStatus.AVAILABLE if _api_key() else ToolStatus.UNAVAILABLE

    def estimate_cost(self, inputs: dict[str, Any]) -> float:
        return 0.032

    def execute(self, inputs: dict[str, Any]) -> ToolResult:
        model = inputs.get("model", _DEFAULT_MODEL)
        if model != _DEFAULT_MODEL:
            return ToolResult(success=False, error=f"Unsupported model {model!r}.")

        output_path, output_error = require_explicit_output_path(
            inputs, self.name, artifact_label="generated image"
        )
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
        payload = {
            "model": model,
            "prompt": inputs["prompt"],
            "size": inputs.get("size", "2048*2048"),
            "output_format": inputs.get("output_format", "jpeg"),
        }
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        try:
            submit = requests.post(
                f"{_media_base_url()}/model/generateImage",
                headers=headers,
                json=payload,
                timeout=30,
            )
            submit.raise_for_status()
            task_id = _prediction_id(submit.json())
            if not task_id:
                return ToolResult(
                    success=False,
                    error="Atlas Cloud image generation returned no prediction id",
                )

            result_payload = self._poll_prediction(task_id, headers)
            urls = _collect_urls(result_payload)
            if not urls:
                return ToolResult(
                    success=False,
                    error="Atlas Cloud image generation completed without an output URL",
                )

            image_response = requests.get(urls[0], timeout=120)
            image_response.raise_for_status()
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(image_response.content)

        except Exception as exc:
            return ToolResult(success=False, error=f"Atlas Cloud image generation failed: {exc}")

        return ToolResult(
            success=True,
            data={
                "provider": self.provider,
                "model": model,
                "prompt": inputs["prompt"],
                "size": payload["size"],
                "output_format": payload["output_format"],
                "prediction_id": task_id,
                "output": str(output_path),
                "output_path": str(output_path),
            },
            artifacts=[str(output_path)],
            cost_usd=self.estimate_cost(inputs),
            duration_seconds=round(time.time() - start, 2),
            model=model,
        )

    def _poll_prediction(self, task_id: str, headers: dict[str, str]) -> dict[str, Any]:
        import requests

        deadline = time.time() + 300
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
                raise RuntimeError(f"Atlas Cloud image generation {message}")
            if time.time() >= deadline:
                raise TimeoutError("Atlas Cloud image generation timed out")
            time.sleep(3)
