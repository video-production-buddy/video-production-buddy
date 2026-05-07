"""Wan video generation and editing via Alibaba Cloud Bailian / DashScope API.

Supports Wan 2.7 (i2v, r2v, videoedit — Bailian China), Wan 2.6 (t2v, i2v-flash),
and legacy Wan 2.1. All use the async task pattern: submit → poll → download.

Endpoint (all models): /api/v1/services/aigc/video-generation/video-synthesis
Task polling:          /api/v1/tasks/{task_id}
"""

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

_API_BASE = "https://dashscope.aliyuncs.com/api/v1"
_VIDEO_GEN_URL = f"{_API_BASE}/services/aigc/video-generation/video-synthesis"
_TASK_URL = f"{_API_BASE}/tasks/{{task_id}}"

# ── Model registry ─────────────────────────────────────────────────────────────
_MODELS: dict[str, dict[str, Any]] = {
    # ── Wan 2.7 (Bailian China mainland, latest) ──────────────────────────────
    "wan2.7-i2v": {
        "name": "Wan 2.7 Image-to-Video",
        "operation": "image_to_video",
        "quality": "highest",
        "speed": "medium",
        "cost_per_5s": 0.22,
        "max_duration": 10,
    },
    "wan2.7-r2v": {
        "name": "Wan 2.7 Reference-to-Video",
        "operation": "reference_to_video",
        "quality": "highest",
        "speed": "medium",
        "cost_per_5s": 0.24,
        "max_duration": 10,
    },
    "wan2.7-videoedit": {
        "name": "Wan 2.7 Video Edit",
        "operation": "video_editing",
        "quality": "highest",
        "speed": "medium",
        "cost_per_5s": 0.26,
        "max_duration": 10,
    },
    # ── Wan 2.6 (international + China, latest docs) ──────────────────────────
    "wan2.6-t2v": {
        "name": "Wan 2.6 Text-to-Video",
        "operation": "text_to_video",
        "quality": "highest",
        "speed": "medium",
        "cost_per_5s": 0.20,
        "max_duration": 15,
    },
    "wan2.6-i2v-flash": {
        "name": "Wan 2.6 Image-to-Video Flash",
        "operation": "image_to_video",
        "quality": "high",
        "speed": "fast",
        "cost_per_5s": 0.16,
        "max_duration": 15,
    },
    # ── Wan 2.1 (legacy, T2V only) ────────────────────────────────────────────
    "wanx2.1-t2v-turbo": {
        "name": "Wan 2.1 T2V Turbo",
        "operation": "text_to_video",
        "quality": "high",
        "speed": "fast",
        "cost_per_5s": 0.14,
        "max_duration": 5,
    },
    "wanx2.1-t2v-plus": {
        "name": "Wan 2.1 T2V Plus",
        "operation": "text_to_video",
        "quality": "high",
        "speed": "medium",
        "cost_per_5s": 0.20,
        "max_duration": 5,
    },
    "wanx2.1-i2v-turbo": {
        "name": "Wan 2.1 I2V Turbo",
        "operation": "image_to_video",
        "quality": "high",
        "speed": "fast",
        "cost_per_5s": 0.16,
        "max_duration": 5,
    },
    "wanx2.1-i2v-plus": {
        "name": "Wan 2.1 I2V Plus",
        "operation": "image_to_video",
        "quality": "high",
        "speed": "medium",
        "cost_per_5s": 0.22,
        "max_duration": 5,
    },
}

# Best model per operation (prefer Wan 2.7/2.6 where available)
_OP_DEFAULTS: dict[str, str] = {
    "text_to_video": "wan2.6-t2v",
    "image_to_video": "wan2.7-i2v",
    "reference_to_video": "wan2.7-r2v",
    "video_editing": "wan2.7-videoedit",
}

# Resolution presets (480P / 720P / 1080P) — accepted by 2.5/2.6 models.
# Older 2.1 models use the "size" string (e.g. "1280*720").
_RESOLUTION_PRESETS = ["480P", "720P", "1080P"]
_VALID_SIZES = ["1280*720", "960*960", "720*1280", "1920*1080", "1080*1920"]


class WanVideoAPI(BaseTool):
    name = "wan_video_api"
    version = "0.3.0"
    tier = ToolTier.GENERATE
    capability = "video_generation"
    provider = "bailian"
    stability = ToolStability.BETA
    execution_mode = ExecutionMode.SYNC
    determinism = Determinism.STOCHASTIC
    runtime = ToolRuntime.API

    dependencies = ["env:DASHSCOPE_API_KEY"]
    install_instructions = (
        "Set the DASHSCOPE_API_KEY environment variable:\n"
        "  export DASHSCOPE_API_KEY=your_key_here\n"
        "Get a key at https://bailian.console.aliyun.com/\n"
        "Enable Wan video models in the Bailian console model list."
    )
    agent_skills = ["ai-video-gen"]

    capabilities = [
        "text_to_video",
        "image_to_video",
        "reference_to_video",
        "video_editing",
    ]
    supports = {
        "text_to_video": True,
        "image_to_video": True,
        "reference_to_video": True,
        "video_editing": True,
        "native_audio": True,
        "cinematic_quality": True,
        "offline": False,
        "local_gpu": False,
    }
    best_for = [
        "Wan 2.7 i2v/r2v/videoedit on Bailian without a local GPU",
        "video editing via natural-language instruction (wan2.7-videoedit)",
        "reference-guided video generation (wan2.7-r2v)",
        "Wan 2.6 t2v for 1080P long clips (up to 15s)",
        "Chinese-language prompt video generation",
    ]
    not_good_for = [
        "very fast iteration (task polling adds latency)",
        "projects needing guaranteed sub-60s turnaround",
    ]
    fallback_tools = ["wan_video", "kling_video", "minimax_video"]

    input_schema = {
        "type": "object",
        "required": ["prompt"],
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
                        {"required": ["ref_images"]},
                        {"required": ["ref_video_url"]},
                    ]
                },
            },
            {
                "if": {
                    "properties": {"operation": {"const": "video_editing"}},
                    "required": ["operation"],
                },
                "then": {
                    "anyOf": [
                        {"required": ["video_url"]},
                        {"required": ["video_path"]},
                    ]
                },
            },
            *[
                {
                    "if": {
                        "properties": {"model_variant": {"const": variant}},
                        "required": ["model_variant"],
                    },
                    "then": {
                        "properties": {
                            "operation": {"const": model_meta["operation"]},
                        },
                        **(
                            {"required": ["operation"]}
                            if model_meta["operation"] != "text_to_video"
                            else {}
                        ),
                    },
                }
                for variant, model_meta in _MODELS.items()
            ],
        ],
        "properties": {
            "prompt": {
                "type": "string",
                "description": "Generation prompt or edit instruction (max 1500 chars for 2.6)",
            },
            "negative_prompt": {"type": "string", "description": "Elements to avoid"},
            "operation": {
                "type": "string",
                "enum": [
                    "text_to_video",
                    "image_to_video",
                    "reference_to_video",
                    "video_editing",
                ],
                "default": "text_to_video",
                "description": (
                    "text_to_video: prompt → clip. "
                    "image_to_video: still image → clip (wan2.7-i2v/wan2.6-i2v-flash). "
                    "reference_to_video: reference images/video → new clip (wan2.7-r2v). "
                    "video_editing: edit existing video by instruction (wan2.7-videoedit)."
                ),
            },
            "model_variant": {
                "type": "string",
                "enum": list(_MODELS.keys()),
                "description": "Override auto model selection. Default: best model for the operation.",
            },
            "duration": {
                "type": "integer",
                "minimum": 3,
                "maximum": 15,
                "default": 5,
                "description": "Clip duration in seconds. Max depends on model (5s for 2.1, 15s for 2.6).",
            },
            "aspect_ratio": {
                "type": "string",
                "enum": ["16:9", "9:16", "1:1"],
                "description": (
                    "Convenience param. When set, the tool resolves to the matching `size` "
                    "value (16:9->1920*1080, 9:16->1080*1920, 1:1->960*960) and clears any "
                    "`resolution` preset so the API honors the aspect ratio. Use this for "
                    "vertical TikTok / Reels output instead of `resolution: 1080P`, which "
                    "produces landscape on wan2.6-t2v."
                ),
            },
            "resolution": {
                "type": "string",
                "enum": _RESOLUTION_PRESETS,
                "description": (
                    "Resolution preset for wan2.5/2.6 models (480P/720P/1080P). "
                    "NOTE: the API treats this as a *landscape* preset for t2v; pass "
                    "`aspect_ratio` (or `size`) for non-landscape output."
                ),
            },
            "size": {
                "type": "string",
                "enum": _VALID_SIZES,
                "default": "1280*720",
                "description": (
                    "Exact resolution string (e.g. '1080*1920'). Honored by wan2.1 models "
                    "and by wan2.6-t2v when `resolution` is omitted. Prefer `aspect_ratio` "
                    "when you only care about the shape, not the pixel count."
                ),
            },
            # ── image_to_video ───────────────────────────────────────────────
            "image_url": {
                "type": "string",
                "minLength": 1,
                "description": "Source image URL (image_to_video)",
            },
            "image_path": {
                "type": "string",
                "minLength": 1,
                "description": "Local source image path (image_to_video; auto base64-encoded)",
            },
            # ── audio sync (wan2.6/2.5) ──────────────────────────────────────
            "audio_url": {
                "type": "string",
                "minLength": 1,
                "description": "Audio URL for audio-synced generation (wan2.6/2.5 only)",
            },
            # ── reference_to_video ───────────────────────────────────────────
            "ref_images": {
                "type": "array",
                "items": {"type": "string"},
                "minItems": 1,
                "description": "Reference image URLs or local paths (reference_to_video)",
            },
            "ref_video_url": {
                "type": "string",
                "minLength": 1,
                "description": "Reference video URL (reference_to_video)",
            },
            # ── video_editing ────────────────────────────────────────────────
            "video_url": {
                "type": "string",
                "minLength": 1,
                "description": "Source video URL to edit (video_editing)",
            },
            "video_path": {
                "type": "string",
                "minLength": 1,
                "description": "Local source video path to edit (video_editing; auto base64-encoded)",
            },
            # ── common ───────────────────────────────────────────────────────
            "prompt_extend": {
                "type": "boolean",
                "default": True,
                "description": "Let Bailian LLM auto-enhance the prompt (prompt_extend)",
            },
            "seed": {"type": "integer"},
            "output_path": {"type": "string"},
        },
    }

    resource_profile = ResourceProfile(
        cpu_cores=1, ram_mb=512, vram_mb=0, disk_mb=500, network_required=True
    )
    retry_policy = RetryPolicy(max_retries=2, retryable_errors=["rate_limit", "timeout"])
    idempotency_key_fields = [
        "prompt",
        "negative_prompt",
        "model_variant",
        "operation",
        "duration",
        "aspect_ratio",
        "resolution",
        "size",
        "image_url",
        "image_path",
        "audio_url",
        "ref_images",
        "ref_video_url",
        "video_url",
        "video_path",
        "prompt_extend",
        "seed",
        "output_path",
    ]
    side_effects = ["writes video file to output_path", "calls Bailian/DashScope API"]
    user_visible_verification = ["Watch generated clip for motion coherence and visual quality"]

    def _get_api_key(self) -> str | None:
        return os.environ.get("DASHSCOPE_API_KEY")

    def get_status(self) -> ToolStatus:
        if self._get_api_key():
            return ToolStatus.AVAILABLE
        return ToolStatus.UNAVAILABLE

    def estimate_cost(self, inputs: dict[str, Any]) -> float:
        operation = inputs.get("operation", "text_to_video")
        variant = inputs.get("model_variant") or _OP_DEFAULTS.get(operation, "wan2.6-t2v")
        duration = int(inputs.get("duration", 5))
        base = _MODELS.get(variant, _MODELS["wan2.6-t2v"])["cost_per_5s"]
        return round(base * (duration / 5), 4)

    def estimate_runtime(self, inputs: dict[str, Any]) -> float:
        operation = inputs.get("operation", "text_to_video")
        variant = inputs.get("model_variant") or _OP_DEFAULTS.get(operation, "wan2.6-t2v")
        speed = _MODELS.get(variant, {}).get("speed", "medium")
        return {"fast": 60.0, "medium": 120.0, "slow": 240.0}.get(speed, 120.0)

    def execute(self, inputs: dict[str, Any]) -> ToolResult:
        api_key = self._get_api_key()
        if not api_key:
            return ToolResult(
                success=False,
                error="DASHSCOPE_API_KEY not set. " + self.install_instructions,
            )

        import requests

        start = time.time()
        operation = inputs.get("operation", "text_to_video")
        if operation not in _OP_DEFAULTS:
            return ToolResult(
                success=False,
                error=(
                    f"Unknown operation {operation!r}. Valid values: "
                    f"{', '.join(sorted(_OP_DEFAULTS))}."
                ),
            )
        variant = inputs.get("model_variant") or _OP_DEFAULTS[operation]
        if variant not in _MODELS:
            return ToolResult(
                success=False,
                error=(
                    f"Unknown model_variant {variant!r}. Available: "
                    f"{', '.join(sorted(_MODELS))}."
                ),
            )
        model_meta = _MODELS[variant]
        model_operation = model_meta["operation"]
        if model_operation != operation:
            return ToolResult(
                success=False,
                error=(
                    f"model_variant {variant!r} supports {model_operation}, "
                    f"but operation is {operation}. Choose a matching model_variant "
                    "or omit model_variant to use the operation default."
                ),
            )

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "X-DashScope-Async": "enable",
        }

        inp: dict[str, Any] = {"prompt": inputs["prompt"]}
        if inputs.get("negative_prompt"):
            inp["negative_prompt"] = inputs["negative_prompt"]
        if inputs.get("audio_url"):
            inp["audio_url"] = inputs["audio_url"]

        # ── Operation-specific input assembly ──────────────────────────────
        # wan2.7-* uses input.media:[{url, type}]; wan2.6/2.1 use img_url/video/ref_images
        use_media_api = variant.startswith("wan2.7-")

        if operation == "image_to_video":
            err = self._attach_image(inputs, inp, use_media_api)
            if err:
                return ToolResult(success=False, error=err)

        elif operation == "reference_to_video":
            err = self._attach_reference(inputs, inp, use_media_api)
            if err:
                return ToolResult(success=False, error=err)

        elif operation == "video_editing":
            err = self._attach_video(inputs, inp, use_media_api)
            if err:
                return ToolResult(success=False, error=err)

        # ── Resolution / size ───────────────────────────────────────────────
        params: dict[str, Any] = {
            "duration": inputs.get("duration", 5),
            "prompt_extend": inputs.get("prompt_extend", True),
        }
        # aspect_ratio convenience: takes precedence over resolution+size, derives the
        # explicit `size` string, and clears any resolution preset so the API honors
        # the aspect ratio (resolution presets force landscape on wan2.6-t2v).
        aspect_ratio = inputs.get("aspect_ratio")
        if aspect_ratio:
            _AR_TO_SIZE = {
                "16:9": "1920*1080",
                "9:16": "1080*1920",
                "1:1": "960*960",
            }
            params["size"] = _AR_TO_SIZE[aspect_ratio]
        elif inputs.get("resolution"):
            # wan2.5/2.6 accept resolution presets (landscape only)
            params["resolution"] = inputs["resolution"]
        else:
            params["size"] = inputs.get("size", "1280*720")
        if inputs.get("seed") is not None:
            params["seed"] = inputs["seed"]

        payload = {"model": variant, "input": inp, "parameters": params}

        try:
            submit_resp = requests.post(
                _VIDEO_GEN_URL, headers=headers, json=payload, timeout=30
            )
            submit_resp.raise_for_status()
            task_id = submit_resp.json()["output"]["task_id"]

            task_status, video_url = self._poll_task(task_id, api_key)
            if task_status != "SUCCEEDED":
                return ToolResult(
                    success=False, error=f"Wan video task {task_status.lower()}"
                )

            video_resp = requests.get(video_url, timeout=300)
            video_resp.raise_for_status()

            output_path = Path(inputs.get("output_path", "wan_api_output.mp4"))
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(video_resp.content)

        except Exception as exc:
            return ToolResult(success=False, error=f"Wan API video generation failed: {exc}")

        from tools.video._shared import probe_output

        probed = probe_output(output_path)
        return ToolResult(
            success=True,
            data={
                "provider": self.provider,
                "model": variant,
                "model_name": model_meta["name"],
                "prompt": inputs["prompt"],
                "operation": operation,
                "duration": inputs.get("duration", 5),
                "output": str(output_path),
                "output_path": str(output_path),
                "format": "mp4",
                **probed,
            },
            artifacts=[str(output_path)],
            cost_usd=self.estimate_cost(inputs),
            duration_seconds=round(time.time() - start, 2),
            seed=inputs.get("seed"),
            model=variant,
        )

    # ── Input helpers ──────────────────────────────────────────────────────────

    def _attach_image(
        self, inputs: dict[str, Any], inp: dict[str, Any], use_media_api: bool
    ) -> str | None:
        """image_to_video: wan2.7-i2v uses media:[{url, type:"first_frame"}]; others use img_url."""
        b64 = self._file_to_b64(inputs.get("image_path"))
        ref = b64 or inputs.get("image_url") or ""
        if not ref:
            return "image_to_video requires image_url or image_path"
        if use_media_api:
            inp["media"] = [{"url": ref, "type": "first_frame"}]
        else:
            inp["img_url"] = ref
        return None

    def _attach_reference(
        self, inputs: dict[str, Any], inp: dict[str, Any], use_media_api: bool
    ) -> str | None:
        """reference_to_video: wan2.7-r2v uses media:[{url, type:"reference_image"|"reference_video"}]."""
        if use_media_api:
            media: list[dict[str, Any]] = []
            for item in inputs.get("ref_images", []):
                b64 = self._file_to_b64(item)
                media.append({"url": b64 or item, "type": "reference_image"})
            if inputs.get("ref_video_url"):
                media.append({"url": inputs["ref_video_url"], "type": "reference_video"})
            if not media:
                return "reference_to_video requires ref_images or ref_video_url"
            inp["media"] = media
        else:
            resolved = [self._file_to_b64(i) or i for i in inputs.get("ref_images", [])]
            if resolved:
                inp["ref_images"] = resolved
            elif inputs.get("ref_video_url"):
                inp["ref_video_url"] = inputs["ref_video_url"]
            else:
                return "reference_to_video requires ref_images or ref_video_url"
        return None

    def _attach_video(
        self, inputs: dict[str, Any], inp: dict[str, Any], use_media_api: bool
    ) -> str | None:
        """video_editing: wan2.7-videoedit uses media:[{url, type:"video"}]; others use video/video_url."""
        b64 = self._file_to_b64(inputs.get("video_path"), mime_type="video/mp4")
        ref = b64 or inputs.get("video_url") or ""
        if not ref:
            return "video_editing requires video_url or video_path"
        if use_media_api:
            inp["media"] = [{"url": ref, "type": "video"}]
        else:
            if b64:
                inp["video"] = b64
            else:
                inp["video_url"] = ref
        return None

    def _file_to_b64(
        self, path_str: str | None, mime_type: str | None = None
    ) -> str | None:
        if not path_str:
            return None
        path = Path(path_str)
        if not path.exists():
            return None
        if mime_type is None:
            suffix = path.suffix.lower().lstrip(".")
            mime_type = {
                "jpg": "image/jpeg", "jpeg": "image/jpeg",
                "png": "image/png", "mp4": "video/mp4",
            }.get(suffix, "application/octet-stream")
        encoded = base64.b64encode(path.read_bytes()).decode("utf-8")
        return f"data:{mime_type};base64,{encoded}"

    def _poll_task(
        self, task_id: str, api_key: str, max_wait: int = 900
    ) -> tuple[str, str]:
        import requests

        headers = {"Authorization": f"Bearer {api_key}"}
        url = _TASK_URL.format(task_id=task_id)
        deadline = time.time() + max_wait

        while time.time() < deadline:
            time.sleep(10)
            resp = requests.get(url, headers=headers, timeout=15)
            resp.raise_for_status()
            output = resp.json().get("output", {})
            status = output.get("task_status", "UNKNOWN")

            if status == "SUCCEEDED":
                return status, output.get("video_url", "")
            if status in ("FAILED", "CANCELLED"):
                return status, ""

        return "TIMEOUT", ""
