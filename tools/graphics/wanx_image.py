"""Wanxiang image generation and editing via Alibaba Cloud Bailian / DashScope API.

Supports Wanxiang 2.1 (default) and legacy Wanx 2.0 / v1 models.
Uses the DashScope async task pattern: submit → poll → download.

Endpoint: /api/v1/services/aigc/text2image/image-synthesis (all operations)
  Image editing is via the same endpoint with base_image_url in input.
  Size separator is '*' (e.g. "1024*1024"), not 'x'.
"""

from __future__ import annotations

import base64
import os
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

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

_API_BASE = "https://dashscope.aliyuncs.com/api/v1"
# wanx2.x models: text2image/image-synthesis
_WANX_URL = f"{_API_BASE}/services/aigc/text2image/image-synthesis"
# wan2.7-image-pro: image-generation/generation (messages format, different result path)
_WAN27_URL = f"{_API_BASE}/services/aigc/image-generation/generation"
_TASK_URL = f"{_API_BASE}/tasks/{{task_id}}"

# ── Model registry ─────────────────────────────────────────────────────────────
_MODELS: dict[str, dict[str, Any]] = {
    # ── Wan 2.7 image-pro (latest, messages API, /image-generation/generation) ─
    "wan2.7-image-pro": {
        "name": "Wan 2.7 Image Pro",
        "quality": "highest",
        "speed": "medium",
        "cost_per_image": 0.020,
        "max_n": 4,
        "supports_editing": True,
        "supports_ref": True,
        "api_style": "wan27",  # messages format, different endpoint + result path
    },
    # ── Wan 2.7 image (general/accelerated variant, same messages API) ─────────
    "wan2.7-image": {
        "name": "Wan 2.7 Image",
        "quality": "high",
        "speed": "fast",
        "cost_per_image": 0.010,
        "max_n": 4,
        "supports_editing": True,
        "supports_ref": True,
        "api_style": "wan27",
    },
    # ── Wanxiang 2.1 (confirmed available, /text2image/image-synthesis) ───────
    "wanx2.1-t2i-turbo": {
        "name": "Wanxiang 2.1 Turbo",
        "quality": "high",
        "speed": "fast",
        "cost_per_image": 0.006,
        "max_n": 4,
        "supports_editing": True,
        "supports_ref": False,
    },
    "wanx2.1-t2i-plus": {
        "name": "Wanxiang 2.1 Plus",
        "quality": "highest",
        "speed": "medium",
        "cost_per_image": 0.017,
        "max_n": 4,
        "supports_editing": True,
        "supports_ref": False,
    },
    # ── Wanxiang 2.0 (legacy) ─────────────────────────────────────────────────
    "wanx2.0-t2i-turbo": {
        "name": "Wanxiang 2.0 Turbo",
        "quality": "good",
        "speed": "fast",
        "cost_per_image": 0.006,
        "max_n": 4,
        "supports_editing": False,
        "supports_ref": False,
    },
    "wanx-v1": {
        "name": "Wanx v1",
        "quality": "medium",
        "speed": "medium",
        "cost_per_image": 0.015,
        "max_n": 4,
        "supports_editing": False,
        "supports_ref": False,
    },
}

# Image size strings use '*' separator (e.g. "1024*1024") — video uses the same convention.
_VALID_SIZES = [
    "1024*1024",
    "720*1280",
    "1280*720",
    "512*1024",
    "1024*512",
    "768*1024",
    "1024*768",
]

_WANX_STYLES = [
    "<auto>",
    "<photography>",
    "<portrait>",
    "<flat illustration>",
    "<3d cartoon>",
    "<anime>",
    "<oil painting>",
    "<watercolor>",
    "<sketch>",
    "<chinese painting>",
    "<film>",
]

_VALID_OPERATIONS = {
    "text_to_image",
    "text_to_image_set",
    "image_editing",
    "image_to_image_set",
    "multi_image_reference",
}


def _is_windows_drive_path(value: str) -> bool:
    return (
        len(value) >= 3
        and value[0].isalpha()
        and value[1] == ":"
        and value[2] in {"/", "\\"}
    )


class WanxImage(BaseTool):
    name = "wanx_image"
    version = "0.3.0"
    tier = ToolTier.GENERATE
    capability = "image_generation"
    provider = "bailian"
    stability = ToolStability.BETA
    execution_mode = ExecutionMode.SYNC
    determinism = Determinism.SEEDED
    runtime = ToolRuntime.API

    dependencies = ["env:DASHSCOPE_API_KEY"]
    install_instructions = (
        "Set the DASHSCOPE_API_KEY environment variable:\n"
        "  export DASHSCOPE_API_KEY=your_key_here\n"
        "Get a key at https://bailian.console.aliyun.com/\n"
        "Enable Wanxiang in the Bailian console model list."
    )
    agent_skills = ["wanx-best-practices"]

    capabilities = [
        "generate_image",
        "text_to_image",
        "image_editing",
        "image_to_image",
        "multi_image_reference",
        "style_control",
    ]
    supports = {
        "negative_prompt": True,
        "seed": True,
        "custom_size": True,
        "style_presets": True,
        "batch_generation": True,
        "image_edit": True,
        "image_editing": True,
        "multiple_reference_images": True,
        "multi_image_reference": True,
    }
    best_for = [
        "Chinese aesthetic style presets (ink, watercolor, flat illustration)",
        "image editing via natural-language instruction (Wanxiang 2.7)",
        "multi-image reference generation for consistent characters/styles",
        "low-cost generation at scale (~$0.006/image for turbo)",
        "text-to-image sets for cohesive production series",
    ]
    not_good_for = [
        "fully offline production",
        "complex text rendering in images",
        "photorealistic Western faces (FLUX or Recraft preferred)",
    ]
    fallback_tools = ["flux_image", "openai_image", "recraft_image"]

    input_schema = {
        "type": "object",
        "required": ["prompt", "output_path"],
        "allOf": [
            {
                "if": {
                    "properties": {"operation": {"const": "multi_image_reference"}},
                    "required": ["operation"],
                },
                "then": {"required": ["ref_images"]},
            },
            {
                "if": {
                    "properties": {
                        "operation": {
                            "enum": ["image_editing", "image_to_image_set"]
                        }
                    },
                    "required": ["operation"],
                },
                "then": {
                    "anyOf": [
                        {"required": ["base_image_url"]},
                        {"required": ["base_image_path"]},
                    ]
                },
            },
        ],
        "properties": {
            "prompt": {
                "type": "string",
                "description": "Generation prompt or editing instruction",
            },
            "negative_prompt": {"type": "string", "description": "Elements to avoid"},
            "operation": {
                "type": "string",
                "enum": [
                    "text_to_image",
                    "text_to_image_set",
                    "image_editing",
                    "image_to_image_set",
                    "multi_image_reference",
                ],
                "default": "text_to_image",
                "description": (
                    "text_to_image: standard generation. "
                    "text_to_image_set: generate a cohesive set (n > 1). "
                    "image_editing: edit base_image by prompt (Wanxiang 2.7 or Wan 2.6). "
                    "image_to_image_set: transform base_image into n variants (Wanxiang 2.7). "
                    "multi_image_reference: generate guided by multiple reference images (Wanxiang 2.7)."
                ),
            },
            "model": {
                "type": "string",
                "enum": list(_MODELS.keys()),
                "default": "wan2.7-image-pro",
                "description": "wan2.7-image-pro: highest quality (default). wan2.7-image: faster general variant. wanx2.1-t2i-turbo: fastest/cheapest.",
            },
            "size": {
                "type": "string",
                "enum": _VALID_SIZES,
                "default": "1024*1024",
                "description": "Output resolution using '*' separator (e.g. '1024*1024')",
            },
            "n": {
                "type": "integer",
                "minimum": 1,
                "maximum": 4,
                "default": 1,
            },
            "seed": {"type": "integer"},
            "style": {
                "type": "string",
                "enum": _WANX_STYLES,
                "default": "<auto>",
                "description": "Style preset (Wanx models; ignored for flux-merged and wan2.6-image)",
            },
            # ── Source image for editing / i2i ─────────────────────────────
            "base_image_url": {
                "type": "string",
                "description": "Source image URL for image_editing or image_to_image_set",
            },
            "base_image_path": {
                "type": "string",
                "description": "Local source image path (auto base64-encoded)",
            },
            "mask_image_url": {
                "type": "string",
                "description": "Optional inpainting mask URL (white = edit area)",
            },
            # ── Multi-image reference ──────────────────────────────────────
            "ref_images": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Reference image URLs or local paths for multi_image_reference",
            },
            "ref_strength": {
                "type": "number",
                "minimum": 0.0,
                "maximum": 1.0,
                "default": 0.8,
                "description": "How strongly reference images influence output",
            },
            "output_path": {
                "type": "string",
                "description": "Output file path; index appended when n > 1",
            },
        },
    }
    output_schema = {
        "type": "object",
        "required": [
            "provider",
            "model",
            "model_name",
            "operation",
            "prompt",
            "size",
            "n",
            "output",
            "output_path",
            "outputs",
            "seed",
        ],
        "properties": {
            "provider": {"type": "string", "const": "bailian"},
            "model": {"type": "string"},
            "model_name": {"type": "string"},
            "operation": {
                "type": "string",
                "enum": [
                    "text_to_image",
                    "text_to_image_set",
                    "image_editing",
                    "image_to_image_set",
                    "multi_image_reference",
                ],
            },
            "prompt": {"type": "string"},
            "size": {"type": "string"},
            "n": {"type": "integer", "minimum": 1},
            "output": {"type": "string"},
            "output_path": {"type": "string"},
            "outputs": {"type": "array", "items": {"type": "string"}},
            "seed": {"type": ["integer", "string", "null"]},
        },
    }

    resource_profile = ResourceProfile(
        cpu_cores=1, ram_mb=256, vram_mb=0, disk_mb=100, network_required=True
    )
    retry_policy = RetryPolicy(max_retries=2, retryable_errors=["rate_limit", "timeout"])
    idempotency_key_fields = [
        "prompt",
        "negative_prompt",
        "model",
        "operation",
        "size",
        "seed",
        "n",
        "style",
        "base_image_url",
        "base_image_path",
        "mask_image_url",
        "ref_images",
        "ref_strength",
        "output_path",
    ]
    side_effects = ["writes image file(s) to output_path", "calls Bailian/DashScope API"]
    user_visible_verification = ["Inspect generated image for relevance and quality"]

    def _get_api_key(self) -> str | None:
        return os.environ.get("DASHSCOPE_API_KEY")

    def get_status(self) -> ToolStatus:
        if self._get_api_key():
            return ToolStatus.AVAILABLE
        return ToolStatus.UNAVAILABLE

    def estimate_cost(self, inputs: dict[str, Any]) -> float:
        model = inputs.get("model", "wan2.7-image-pro")
        n = int(inputs.get("n", 1))
        cost_per = _MODELS.get(model, _MODELS["wan2.7-image-pro"])["cost_per_image"]
        return round(cost_per * n, 4)

    def execute(self, inputs: dict[str, Any]) -> ToolResult:
        model = inputs.get("model", "wan2.7-image-pro")
        operation = inputs.get("operation", "text_to_image")
        if operation not in _VALID_OPERATIONS:
            return ToolResult(success=False, error=f"Unsupported operation '{operation}'.")
        if model not in _MODELS:
            return ToolResult(success=False, error=f"Unsupported model '{model}'.")

        validated_output_path, output_error = require_explicit_output_path(
            inputs,
            self.name,
            artifact_label="generated image",
        )
        if output_error:
            return output_error

        api_key = self._get_api_key()
        if not api_key:
            return ToolResult(
                success=False,
                error="DASHSCOPE_API_KEY not set. " + self.install_instructions,
            )

        import requests

        start = time.time()
        model_meta = _MODELS.get(model, _MODELS["wan2.7-image-pro"])
        n = min(int(inputs.get("n", 1)), model_meta["max_n"])

        # Guard: editing/reference ops require a capable model
        if operation in ("image_editing", "image_to_image_set"):
            if not model_meta.get("supports_editing"):
                return ToolResult(
                    success=False,
                    error=(
                        f"Operation '{operation}' requires an edit-capable Wanx "
                        f"image model. Current model: '{model}'."
                    ),
                )
        if operation == "multi_image_reference":
            if not model_meta.get("supports_ref"):
                return ToolResult(
                    success=False,
                    error=(
                        f"Operation 'multi_image_reference' is not supported by '{model}'."
                    ),
                )

        api_style = model_meta.get("api_style", "standard")

        if api_style == "wan27":
            payload, err = self._build_wan27_payload(inputs, model, operation, n)
        else:
            payload, err = self._build_standard_payload(inputs, model, operation, n)

        if err:
            return ToolResult(success=False, error=err)

        endpoint = _WAN27_URL if api_style == "wan27" else _WANX_URL
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "X-DashScope-Async": "enable",
        }

        try:
            submit_resp = requests.post(
                endpoint, headers=headers, json=payload, timeout=30
            )
            submit_resp.raise_for_status()
            task_id = submit_resp.json()["output"]["task_id"]

            task_status, results = self._poll_task(task_id, api_key, api_style=api_style)
            if task_status != "SUCCEEDED" or not results:
                return ToolResult(
                    success=False,
                    error=f"Wanxiang image task {task_status.lower()}",
                )

            output_paths = self._download_images(
                results,
                str(validated_output_path),
                model,
            )

        except Exception as exc:
            return ToolResult(success=False, error=f"Wanxiang image generation failed: {exc}")

        seed_out = results[0].get("seed") if results else inputs.get("seed")
        primary = output_paths[0] if output_paths else ""

        return ToolResult(
            success=True,
            data={
                "provider": self.provider,
                "model": model,
                "model_name": model_meta["name"],
                "operation": operation,
                "prompt": inputs["prompt"],
                "size": inputs.get("size", "1024*1024"),
                "n": n,
                "output": primary,
                "output_path": primary,
                "outputs": output_paths,
                "seed": seed_out,
            },
            artifacts=output_paths,
            cost_usd=self.estimate_cost(inputs),
            duration_seconds=round(time.time() - start, 2),
            seed=seed_out,
            model=model,
        )

    # ── Payload builders ───────────────────────────────────────────────────────

    def _build_wan27_payload(
        self,
        inputs: dict[str, Any],
        model: str,
        operation: str,
        n: int,
    ) -> tuple[dict[str, Any], str | None]:
        """wan2.7-image-pro: messages format, /image-generation/generation endpoint.

        T2I: messages=[{role:user, content:[{type:text, text:prompt}]}]
        I2I: messages=[{role:user, content:[{type:image, image:url}, {type:text, text:prompt}]}]
        Result: output.choices[0].message.content[0].image
        """
        content: list[dict[str, Any]] = []

        if operation in ("image_editing", "image_to_image_set"):
            base_url = inputs.get("base_image_url")
            base_b64 = self._file_to_b64(inputs.get("base_image_path"))
            img_ref = base_b64 or base_url
            if not img_ref:
                return {}, f"'{operation}' requires base_image_url or base_image_path"
            content.append({"image": img_ref})
        elif operation == "multi_image_reference":
            ref_images = inputs.get("ref_images") or []
            if not ref_images:
                return {}, "multi_image_reference requires ref_images"
            for ref in ref_images:
                resolved, err = self._resolve_image_reference(ref)
                if err:
                    return {}, err
                content.append({"image": resolved})

        content.append({"text": inputs["prompt"]})

        params: dict[str, Any] = {
            "size": inputs.get("size", "1024*1024"),
            "n": n,
        }
        if inputs.get("seed") is not None:
            params["seed"] = inputs["seed"]

        payload = {
            "model": model,
            "input": {"messages": [{"role": "user", "content": content}]},
            "parameters": params,
        }
        return payload, None

    def _build_standard_payload(
        self,
        inputs: dict[str, Any],
        model: str,
        operation: str,
        n: int,
    ) -> tuple[dict[str, Any], str | None]:
        """Wanxiang 2.1/2.0/v1: classic DashScope image API format."""
        inp: dict[str, Any] = {"prompt": inputs["prompt"]}
        if inputs.get("negative_prompt"):
            inp["negative_prompt"] = inputs["negative_prompt"]

        if operation in ("image_editing", "image_to_image_set"):
            err = self._attach_base_image(inputs, inp)
            if err:
                return {}, err
            if inputs.get("mask_image_url"):
                inp["mask_image_url"] = inputs["mask_image_url"]

        elif operation == "multi_image_reference":
            err = self._attach_ref_images(inputs, inp)
            if err:
                return {}, err
            if inputs.get("ref_strength") is not None:
                inp["ref_strength"] = inputs["ref_strength"]

        params: dict[str, Any] = {
            "size": inputs.get("size", "1024*1024"),
            "n": n,
        }
        if inputs.get("seed") is not None:
            params["seed"] = inputs["seed"]
        if inputs.get("style"):
            params["style"] = inputs["style"]

        return {"model": model, "input": inp, "parameters": params}, None


    # ── Image input helpers ────────────────────────────────────────────────────

    def _attach_base_image(
        self, inputs: dict[str, Any], inp: dict[str, Any]
    ) -> str | None:
        b64 = self._file_to_b64(inputs.get("base_image_path"))
        if b64:
            inp["base_image_url"] = b64
        elif inputs.get("base_image_url"):
            inp["base_image_url"] = inputs["base_image_url"]
        else:
            return "image_editing/image_to_image_set requires base_image_url or base_image_path"
        return None

    def _attach_ref_images(
        self, inputs: dict[str, Any], inp: dict[str, Any]
    ) -> str | None:
        ref_images = inputs.get("ref_images", [])
        if not ref_images:
            return "multi_image_reference requires ref_images (list of URLs or local paths)"
        resolved: list[str] = []
        for item in ref_images:
            ref, err = self._resolve_image_reference(item)
            if err:
                return err
            resolved.append(ref)
        inp["ref_images"] = resolved
        return None

    def _resolve_image_reference(self, value: str) -> tuple[str | None, str | None]:
        if not _is_windows_drive_path(value):
            parsed = urlparse(value)
            if parsed.scheme:
                return value, None
        path = Path(value)
        if not path.exists():
            return None, f"Reference image path not found: {value}"
        return self._file_to_b64(value), None

    def _file_to_b64(self, path_str: str | None) -> str | None:
        if not path_str:
            return None
        path = Path(path_str)
        if not path.exists():
            return None
        suffix = path.suffix.lower().lstrip(".")
        mime = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png"}.get(
            suffix, "image/jpeg"
        )
        return f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode()}"

    def _poll_task(
        self, task_id: str, api_key: str, max_wait: int = 300, api_style: str = "standard"
    ) -> tuple[str, list[dict[str, Any]]]:
        import requests

        headers = {"Authorization": f"Bearer {api_key}"}
        url = _TASK_URL.format(task_id=task_id)
        deadline = time.time() + max_wait

        while time.time() < deadline:
            time.sleep(5)
            resp = requests.get(url, headers=headers, timeout=15)
            resp.raise_for_status()
            output = resp.json().get("output", {})
            status = output.get("task_status", "UNKNOWN")

            if status == "SUCCEEDED":
                if api_style == "wan27":
                    # wan2.7-image-pro: output.choices[N].message.content[M].image
                    results = [
                        {"url": item["image"]}
                        for choice in output.get("choices", [])
                        for item in choice.get("message", {}).get("content", [])
                        if item.get("type") == "image" or "image" in item
                    ]
                else:
                    results = output.get("results", [])
                return status, results
            if status in ("FAILED", "CANCELLED"):
                return status, []

        return "TIMEOUT", []

    def _download_images(
        self,
        results: list[dict[str, Any]],
        output_path_hint: str,
        model: str,
    ) -> list[str]:
        import requests

        paths: list[str] = []
        base = Path(output_path_hint)
        stem = base.stem
        suffix = base.suffix or ".png"
        parent = base.parent

        for i, result in enumerate(results):
            url = result.get("url")
            if not url:
                continue
            img_resp = requests.get(url, timeout=60)
            img_resp.raise_for_status()
            out = (
                parent / f"{stem}{suffix}"
                if len(results) == 1
                else parent / f"{stem}_{i}{suffix}"
            )
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(img_resp.content)
            paths.append(str(out))

        return paths
