"""Google image generation via Gemini API and Imagen."""

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
from tools.google_credentials import (
    get_access_token,
    resolve_project_id,
    service_account_configured,
)
from tools.output_paths import require_explicit_output_path

# Aspect ratio to approximate pixel dimensions (for cost/reporting only)
ASPECT_RATIOS = {
    "1:1": (1024, 1024),
    "3:4": (896, 1152),
    "4:3": (1152, 896),
    "9:16": (768, 1344),
    "16:9": (1344, 768),
}

_GEMINI_IMAGE_MODELS = {
    "gemini-3-pro-image",
    "gemini-3.1-flash-image",
    "gemini-2.5-flash-image",
}
_API_KEY_DEFAULT_MODEL = "gemini-3-pro-image"
_VERTEX_DEFAULT_MODEL = "imagen-4.0-generate-001"


def _dims_to_aspect_ratio(width: int, height: int) -> str:
    """Convert width/height to the nearest supported aspect ratio."""
    target = width / height
    best = "1:1"
    best_diff = float("inf")
    for ratio, (w, h) in ASPECT_RATIOS.items():
        diff = abs(target - w / h)
        if diff < best_diff:
            best_diff = diff
            best = ratio
    return best


def _extract_gemini_image_payloads(data: dict[str, Any]) -> list[str]:
    """Return base64 image payloads from Gemini image generation responses."""
    payloads: list[str] = []

    output_image = data.get("output_image")
    if isinstance(output_image, dict) and isinstance(output_image.get("data"), str):
        payloads.append(output_image["data"])

    for step in data.get("steps") or []:
        if not isinstance(step, dict):
            continue
        for content_item in step.get("content") or []:
            if not isinstance(content_item, dict):
                continue
            item_type = content_item.get("type")
            mime_type = content_item.get("mime_type") or content_item.get("mimeType") or ""
            if (
                isinstance(content_item.get("data"), str)
                and (item_type == "image" or str(mime_type).startswith("image/"))
            ):
                payloads.append(content_item["data"])

    for candidate in data.get("candidates") or []:
        if not isinstance(candidate, dict):
            continue
        content = candidate.get("content")
        if not isinstance(content, dict):
            continue
        for part in content.get("parts") or []:
            if not isinstance(part, dict):
                continue
            inline_data = part.get("inlineData") or part.get("inline_data")
            if isinstance(inline_data, dict) and isinstance(inline_data.get("data"), str):
                payloads.append(inline_data["data"])

    return payloads


class GoogleImagen(BaseTool):
    name = "google_imagen"
    version = "0.1.0"
    tier = ToolTier.GENERATE
    capability = "image_generation"
    provider = "google_imagen"
    stability = ToolStability.BETA
    execution_mode = ExecutionMode.SYNC
    determinism = Determinism.STOCHASTIC
    runtime = ToolRuntime.API

    dependencies = ["env_any:GOOGLE_API_KEY,GEMINI_API_KEY,GOOGLE_APPLICATION_CREDENTIALS"]
    install_instructions = (
        "Auth option A — API key (AI Studio): set GOOGLE_API_KEY (or GEMINI_API_KEY).\n"
        "  Get one at https://aistudio.google.com/apikey\n"
        "Auth option B — service account (Vertex AI): set GOOGLE_APPLICATION_CREDENTIALS\n"
        "  to a service-account JSON key (needs the 'google-auth' package), plus\n"
        "  GOOGLE_CLOUD_PROJECT and optionally GOOGLE_CLOUD_LOCATION (default us-central1).\n"
        "  Requires the Vertex AI API enabled and billing on the project."
    )
    agent_skills = ["flux-best-practices"]

    capabilities = ["generate_image", "generate_illustration", "text_to_image"]
    supports = {
        "negative_prompt": False,
        "seed": False,
        "custom_size": False,
        "aspect_ratio": True,
    }
    best_for = [
        "Google SOTA image generation with Gemini 3 Pro Image / Nano Banana Pro",
        "high-quality photorealistic images",
        "Google ecosystem integration",
        "fast generation with multiple aspect ratios",
    ]
    not_good_for = [
        "negative prompt control (not supported)",
        "exact pixel dimensions (uses aspect ratios)",
        "offline generation",
    ]
    model_options = [
        {
            "id": "gemini-3-pro-image",
            "name": "Gemini 3 Pro Image (Nano Banana Pro)",
            "field": "model",
            "default": True,
            "quality": "highest",
            "speed": "medium",
            "release_stage": "current_sota",
            "requires_api_key": True,
            "last_verified": "2026-06-28",
            "source_url": "https://ai.google.dev/gemini-api/docs/image-generation",
            "note": "Gemini image generation requires GOOGLE_API_KEY or GEMINI_API_KEY in this tool.",
        },
        {
            "id": "gemini-3.1-flash-image",
            "name": "Gemini 3.1 Flash Image (Nano Banana 2)",
            "field": "model",
            "default": False,
            "quality": "high",
            "speed": "fast",
            "release_stage": "current",
            "requires_api_key": True,
            "last_verified": "2026-06-28",
            "source_url": "https://ai.google.dev/gemini-api/docs/video",
        },
        {
            "id": "gemini-2.5-flash-image",
            "name": "Gemini 2.5 Flash Image",
            "field": "model",
            "default": False,
            "quality": "high",
            "speed": "fast",
            "release_stage": "legacy_current",
            "requires_api_key": True,
            "last_verified": "2026-06-28",
            "source_url": "https://ai.google.dev/gemini-api/docs/image-generation",
        },
        {
            "id": "imagen-4.0-ultra-generate-001",
            "name": "Imagen 4 Ultra",
            "field": "model",
            "default": False,
            "quality": "highest",
            "speed": "medium",
            "release_stage": "current_imagen",
            "last_verified": "2026-06-28",
            "source_url": "https://ai.google.dev/gemini-api/docs/imagen",
        },
        {
            "id": "imagen-4.0-generate-001",
            "name": "Imagen 4",
            "field": "model",
            "default": False,
            "quality": "high",
            "speed": "medium",
            "release_stage": "current_imagen",
            "last_verified": "2026-06-28",
            "source_url": "https://ai.google.dev/gemini-api/docs/imagen",
        },
        {
            "id": "imagen-4.0-fast-generate-001",
            "name": "Imagen 4 Fast",
            "field": "model",
            "default": False,
            "quality": "high",
            "speed": "fast",
            "release_stage": "current_imagen",
            "last_verified": "2026-06-28",
            "source_url": "https://ai.google.dev/gemini-api/docs/imagen",
        },
    ]

    input_schema = {
        "type": "object",
        "required": ["prompt", "output_path"],
        "properties": {
            "prompt": {"type": "string", "description": "Image description (max 480 tokens)"},
            "aspect_ratio": {
                "type": "string",
                "enum": ["1:1", "3:4", "4:3", "9:16", "16:9"],
                "default": "1:1",
                "description": "Aspect ratio of generated image",
            },
            "width": {
                "type": "integer",
                "description": "Desired width in pixels — mapped to nearest aspect ratio",
            },
            "height": {
                "type": "integer",
                "description": "Desired height in pixels — mapped to nearest aspect ratio",
            },
            "model": {
                "type": "string",
                "enum": [
                    "gemini-3-pro-image",
                    "gemini-3.1-flash-image",
                    "gemini-2.5-flash-image",
                    "imagen-4.0-ultra-generate-001",
                    "imagen-4.0-generate-001",
                    "imagen-4.0-fast-generate-001",
                ],
                "default": "gemini-3-pro-image",
                "description": "Google image model variant",
            },
            "number_of_images": {
                "type": "integer",
                "default": 1,
                "minimum": 1,
                "maximum": 4,
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
            "aspect_ratio",
            "output",
            "output_path",
            "images_generated",
        ],
        "properties": {
            "provider": {"type": "string", "const": "google_imagen"},
            "model": {"type": "string"},
            "prompt": {"type": "string"},
            "aspect_ratio": {"type": "string"},
            "output": {"type": "string"},
            "output_path": {"type": "string"},
            "images_generated": {"type": "integer", "minimum": 1},
        },
    }

    resource_profile = ResourceProfile(
        cpu_cores=1, ram_mb=512, vram_mb=0, disk_mb=100, network_required=True
    )
    retry_policy = RetryPolicy(max_retries=2, retryable_errors=["rate_limit", "timeout"])
    idempotency_key_fields = [
        "prompt",
        "output_path",
        "aspect_ratio",
        "width",
        "height",
        "number_of_images",
        "model",
    ]
    side_effects = ["writes image file to output_path", "calls Google Generative AI API"]
    user_visible_verification = ["Inspect generated image for relevance and quality"]

    def _get_api_key(self) -> str | None:
        return os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")

    def _default_model_for_auth(self, api_key: str | None = None) -> str:
        if api_key is None:
            api_key = self._get_api_key()
        if api_key:
            return _API_KEY_DEFAULT_MODEL
        if service_account_configured():
            return _VERTEX_DEFAULT_MODEL
        return _API_KEY_DEFAULT_MODEL

    def get_info(self) -> dict[str, Any]:
        info = super().get_info()
        api_key = self._get_api_key()
        default_model = self._default_model_for_auth()
        if not api_key and service_account_configured():
            model_options = [
                option
                for option in info.get("model_options", [])
                if not (
                    isinstance(option, dict)
                    and (
                        option.get("requires_api_key")
                        or option.get("id") in _GEMINI_IMAGE_MODELS
                    )
                )
            ]
            info["model_options"] = model_options
            model_schema = (
                info.get("input_schema", {})
                .get("properties", {})
                .get("model", {})
            )
            if isinstance(model_schema, dict):
                model_schema["enum"] = [
                    option["id"]
                    for option in model_options
                    if isinstance(option, dict) and option.get("id")
                ]
        model_schema = (
            info.get("input_schema", {})
            .get("properties", {})
            .get("model", {})
        )
        if isinstance(model_schema, dict):
            model_schema["default"] = default_model
        for option in info.get("model_options", []):
            if isinstance(option, dict):
                option["default"] = option.get("id") == default_model
        return info

    def get_status(self) -> ToolStatus:
        # API key -> AI Studio endpoint; service-account JSON -> Vertex AI.
        if self._get_api_key() or service_account_configured():
            return ToolStatus.AVAILABLE
        return ToolStatus.UNAVAILABLE

    def estimate_cost(self, inputs: dict[str, Any]) -> float:
        model = inputs.get("model", self._default_model_for_auth())
        n = inputs.get("number_of_images", 1)
        if model == "gemini-3-pro-image":
            return 0.134 * n
        if model.startswith("gemini-"):
            return 0.039 * n
        if "ultra" in model:
            return 0.06 * n
        if "fast" in model:
            return 0.02 * n
        return 0.04 * n

    def execute(self, inputs: dict[str, Any]) -> ToolResult:
        output_path, output_error = require_explicit_output_path(
            inputs, self.name, artifact_label="generated image"
        )
        if output_error:
            return output_error
        assert output_path is not None

        # Two auth paths: an AI Studio API key, or a service-account JSON that
        # routes to Vertex AI (the AI Studio endpoint does not accept service
        # accounts). API key wins when both are present.
        api_key = self._get_api_key()
        bearer_token: str | None = None
        project_id: str | None = None
        if not api_key:
            if not service_account_configured():
                return ToolResult(
                    success=False,
                    error="No Google credentials found. " + self.install_instructions,
                )
            try:
                bearer_token, creds_project = get_access_token()
            except RuntimeError as exc:
                return ToolResult(success=False, error=str(exc))
            project_id = resolve_project_id(creds_project)
            if not project_id:
                return ToolResult(
                    success=False,
                    error=(
                        "Vertex AI needs a project id. Set GOOGLE_CLOUD_PROJECT "
                        "(or include project_id in the service-account key)."
                    ),
                )

        import requests

        start = time.time()
        model = inputs.get("model", self._default_model_for_auth(api_key))
        prompt = inputs["prompt"]

        import logging
        logger = logging.getLogger(__name__)

        # Resolve aspect ratio: explicit > derived from width/height > default
        if "aspect_ratio" in inputs:
            aspect_ratio = inputs["aspect_ratio"]
        elif "width" in inputs and "height" in inputs:
            requested_ratio = f"{inputs['width']}x{inputs['height']}"
            aspect_ratio = _dims_to_aspect_ratio(inputs["width"], inputs["height"])
            logger.info(
                "google_imagen: remapped %s to nearest supported aspect ratio %s",
                requested_ratio, aspect_ratio,
            )
        else:
            aspect_ratio = "1:1"

        number_of_images = inputs.get("number_of_images", 1)

        parameters: dict[str, Any] = {
            "sampleCount": number_of_images,
            "aspectRatio": aspect_ratio,
        }

        if model in _GEMINI_IMAGE_MODELS:
            if not api_key:
                return ToolResult(
                    success=False,
                    error=(
                        f"{model} requires GOOGLE_API_KEY or GEMINI_API_KEY in "
                        "google_imagen. Use an imagen-4.0-* model for the "
                        "service-account Vertex AI path."
                    ),
                )
            if number_of_images != 1:
                return ToolResult(
                    success=False,
                    error=(
                        f"{model} supports one image per request in google_imagen. "
                        "Set number_of_images=1 or choose an imagen-4.0-* model "
                        "for multi-image generation."
                    ),
                )
            url = "https://generativelanguage.googleapis.com/v1beta/interactions"
            headers = {
                "Content-Type": "application/json",
                "x-goog-api-key": api_key,
            }
            request_json = {
                "model": model,
                "input": prompt,
                "response_format": {
                    "type": "image",
                    "mime_type": "image/png",
                    "aspect_ratio": aspect_ratio,
                },
            }
        else:
            request_json = {
                "instances": [{"prompt": prompt}],
                "parameters": parameters,
            }

        if bearer_token and model not in _GEMINI_IMAGE_MODELS:
            location = os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1")
            url = (
                f"https://{location}-aiplatform.googleapis.com/v1/projects/"
                f"{project_id}/locations/{location}/publishers/google/models/"
                f"{model}:predict"
            )
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {bearer_token}",
            }
        elif model not in _GEMINI_IMAGE_MODELS:
            url = (
                f"https://generativelanguage.googleapis.com/v1beta/models/"
                f"{model}:predict"
            )
            headers = {
                "Content-Type": "application/json",
                "x-goog-api-key": api_key,
            }

        try:
            if model in _GEMINI_IMAGE_MODELS:
                image_payloads: list[str] = []
                for _ in range(number_of_images):
                    response = requests.post(
                        url,
                        headers=headers,
                        json=request_json,
                        timeout=120,
                    )
                    response.raise_for_status()
                    data = response.json()
                    batch_payloads = _extract_gemini_image_payloads(data)
                    predictions = data.get("predictions", [])
                    if not batch_payloads and predictions:
                        batch_payloads = [
                            item["bytesBase64Encoded"]
                            for item in predictions
                            if isinstance(item, dict) and item.get("bytesBase64Encoded")
                        ]
                    image_payloads.extend(batch_payloads)
                    if len(image_payloads) >= number_of_images:
                        break

                if not image_payloads:
                    return ToolResult(
                        success=False,
                        error="No images returned from Gemini image API",
                    )
                image_bytes = base64.b64decode(image_payloads[0])
                images_generated = len(image_payloads)
            else:
                response = requests.post(
                    url,
                    headers=headers,
                    json=request_json,
                    timeout=120,
                )
                response.raise_for_status()
                data = response.json()
                predictions = data.get("predictions", [])
                if not predictions:
                    return ToolResult(success=False, error="No images returned from Imagen API")
                image_bytes = base64.b64decode(
                    predictions[0]["bytesBase64Encoded"]
                )
                images_generated = len(predictions)

            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(image_bytes)

        except Exception as e:
            return ToolResult(success=False, error=f"Google image generation failed: {e}")

        return ToolResult(
            success=True,
            data={
                "provider": "google_imagen",
                "model": model,
                "prompt": prompt,
                "aspect_ratio": aspect_ratio,
                "output": str(output_path),
                "output_path": str(output_path),
                "images_generated": images_generated,
            },
            artifacts=[str(output_path)],
            cost_usd=self.estimate_cost(inputs),
            duration_seconds=round(time.time() - start, 2),
            model=model,
        )
