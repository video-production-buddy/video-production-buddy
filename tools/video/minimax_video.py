"""MiniMax (Hailuo AI) video generation via the native MiniMax platform API.

Drives MiniMax-Hailuo-2.3 (current flagship) and siblings through the native
async task flow: create → poll → retrieve file. Uses MINIMAX_API_KEY directly
(no third-party gateway). Rewards prompt craft — camera movements via
`[command]` syntax and high prompt adherence.

Endpoint (create):  POST {base}/video_generation        → task_id
Endpoint (query):   GET  {base}/query/video_generation  → file_id
Endpoint (file):    GET  {base}/files/retrieve          → download_url

Base host defaults to the China-mainland host (matching minimax_music); override
with the MINIMAX_API_BASE env var, e.g. https://api.minimax.io/v1 for overseas.
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
from tools.video._shared import require_generated_video_output_path, validate_video_operation, probe_output

# China mainland host (consistent with minimax_music). Overseas: https://api.minimax.io/v1
_DEFAULT_API_BASE = "https://api.minimaxi.com/v1"

# ── Model registry ─────────────────────────────────────────────────────────────
_MODELS: dict[str, dict[str, Any]] = {
    # MiniMax-Hailuo-2.3 — current flagship (newest)
    "MiniMax-Hailuo-2.3": {
        "name": "MiniMax Hailuo 2.3",
        "quality": "highest",
        "speed": "medium",
        "cost_per_6s": 0.15,
        "supports_t2v": True,
        "supports_i2v": True,
    },
    "MiniMax-Hailuo-2.3-Fast": {
        "name": "MiniMax Hailuo 2.3 Fast",
        "quality": "high",
        "speed": "fast",
        "cost_per_6s": 0.08,
        "supports_t2v": False,
        "supports_i2v": True,
        "note": "Image-to-video value/efficiency model",
    },
    "MiniMax-Hailuo-02": {
        "name": "MiniMax Hailuo 02",
        "quality": "high",
        "speed": "medium",
        "cost_per_6s": 0.10,
        "supports_t2v": True,
        "supports_i2v": True,
        "note": "Supports up to 1080P / 10s and first+last frame",
    },
}


def _api_base() -> str:
    """Resolve the MiniMax API base host, honoring the override env var."""
    return os.environ.get("MINIMAX_API_BASE", _DEFAULT_API_BASE).rstrip("/")


class MiniMaxVideo(BaseTool):
    name = "minimax_video"
    version = "0.2.0"
    tier = ToolTier.GENERATE
    capability = "video_generation"
    provider = "minimax"
    stability = ToolStability.BETA
    execution_mode = ExecutionMode.SYNC
    determinism = Determinism.STOCHASTIC
    runtime = ToolRuntime.API

    dependencies = ["env:MINIMAX_API_KEY"]
    install_instructions = (
        "Set the MINIMAX_API_KEY environment variable:\n"
        "  export MINIMAX_API_KEY=your_key_here\n"
        "Get a key from Account > API Keys in the MiniMax API Platform:\n"
        "  https://platform.minimax.io/docs/guides/quickstart-preparation\n"
        "For the overseas host, also set MINIMAX_API_BASE=https://api.minimax.io/v1\n"
        "(default host is the China-mainland https://api.minimaxi.com/v1)"
    )
    agent_skills = ["ai-video-gen"]

    capabilities = ["text_to_video", "image_to_video"]
    supports = {
        "text_to_video": True,
        "image_to_video": True,
        "camera_direction": True,
        "native_audio": False,
        "offline": False,
        "local_gpu": False,
    }
    best_for = [
        "MiniMax-Hailuo-2.3 flagship — best-in-class body motion, facial expression, physical realism",
        "prompt-following with camera directions via [command] syntax (e.g. [Push in], [Tracking shot])",
        "image-to-video (first frame) with high prompt adherence",
        "cost-effective video generation on MINIMAX_API_KEY without a third-party gateway",
    ]
    not_good_for = ["offline generation", "native audio in the generated clip"]
    fallback_tools = ["kling_video", "veo_video", "wan_video_api"]

    input_schema = {
        "type": "object",
        "required": ["prompt", "output_path"],
        "properties": {
            "prompt": {
                "type": "string",
                "description": (
                    "Video description (max 2000 chars). Control camera motion with [command] "
                    "syntax for Hailuo 2.3/02/Director: e.g. '[Push in]', '[Tracking shot]', "
                    "'[Pan left,Pedestal up]'."
                ),
            },
            "operation": {
                "type": "string",
                "enum": ["text_to_video", "image_to_video"],
                "default": "text_to_video",
            },
            "model_variant": {
                "type": "string",
                "enum": list(_MODELS.keys()),
                "default": "MiniMax-Hailuo-2.3",
                "description": "MiniMax-Hailuo-2.3 (default flagship). -2.3-Fast: fast I2V. -02: 1080P/10s.",
            },
            "image_url": {
                "type": "string",
                "description": "First-frame image URL for image_to_video (public HTTP(S) URL)",
            },
            "image_path": {
                "type": "string",
                "description": "Local first-frame image path for image_to_video (auto base64-encoded as a data URL)",
            },
            "duration": {
                "type": "integer",
                "enum": [6, 10],
                "default": 6,
                "description": "Clip duration in seconds (6 or 10; 10s availability depends on model+resolution)",
            },
            "resolution": {
                "type": "string",
                "enum": ["512P", "720P", "768P", "1080P"],
                "default": "768P",
                "description": "Output resolution tier. 1080P only at 6s; 768P default.",
            },
            "prompt_optimizer": {
                "type": "boolean",
                "default": True,
                "description": "Let MiniMax auto-optimize the prompt (set false for precise control)",
            },
            "output_path": {"type": "string"},
        },
    }
    output_schema = {
        "type": "object",
        "required": [
            "provider",
            "model",
            "model_name",
            "prompt",
            "operation",
            "duration",
            "resolution",
            "output",
            "output_path",
            "format",
            "file_size_bytes",
        ],
        "properties": {
            "provider": {"type": "string", "const": "minimax"},
            "model": {"type": "string"},
            "model_name": {"type": "string"},
            "prompt": {"type": "string"},
            "operation": {"type": "string", "enum": ["text_to_video", "image_to_video"]},
            "duration": {"type": "integer", "minimum": 0},
            "resolution": {"type": "string"},
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
        "image_url",
        "image_path",
        "duration",
        "resolution",
        "prompt_optimizer",
    ]
    side_effects = ["writes video file to output_path", "calls MiniMax platform API"]
    user_visible_verification = ["Inspect sampled frames for motion coherence and prompt adherence"]

    def _get_api_key(self) -> str | None:
        return os.environ.get("MINIMAX_API_KEY")

    def get_status(self) -> ToolStatus:
        if self._get_api_key():
            return ToolStatus.AVAILABLE
        return ToolStatus.UNAVAILABLE

    def estimate_cost(self, inputs: dict[str, Any]) -> float:
        variant = inputs.get("model_variant", "MiniMax-Hailuo-2.3")
        duration = int(inputs.get("duration", 6))
        base = _MODELS.get(variant, _MODELS["MiniMax-Hailuo-2.3"])["cost_per_6s"]
        return round(base * (duration / 6), 4)

    def estimate_runtime(self, inputs: dict[str, Any]) -> float:
        variant = inputs.get("model_variant", "MiniMax-Hailuo-2.3")
        speed = _MODELS.get(variant, {}).get("speed", "medium")
        return {"fast": 45.0, "medium": 90.0, "slow": 180.0}.get(speed, 90.0)

    def execute(self, inputs: dict[str, Any]) -> ToolResult:
        operation = inputs.get("operation", "text_to_video")
        operation_error = validate_video_operation(operation, {"text_to_video", "image_to_video"})
        if operation_error:
            return ToolResult(success=False, error=operation_error)

        variant = inputs.get("model_variant", "MiniMax-Hailuo-2.3")
        if variant not in _MODELS:
            return ToolResult(
                success=False,
                error=f"Unknown model_variant {variant!r}. Available: {', '.join(sorted(_MODELS))}.",
            )

        if operation == "text_to_video" and not _MODELS[variant].get("supports_t2v"):
            return ToolResult(
                success=False,
                error=(
                    f"model_variant {variant!r} does not support text_to_video. "
                    "Use 'MiniMax-Hailuo-2.3' for text_to_video, or switch operation to image_to_video."
                ),
            )

        if operation == "image_to_video":
            if not (inputs.get("image_url") or inputs.get("image_path")):
                return ToolResult(success=False, error="image_to_video requires image_url or image_path")
            if not _MODELS[variant].get("supports_i2v"):
                return ToolResult(
                    success=False,
                    error=f"model_variant {variant!r} does not support image_to_video.",
                )

        output_path, output_error = require_generated_video_output_path(inputs, self.name)
        if output_error:
            return output_error

        api_key = self._get_api_key()
        if not api_key:
            return ToolResult(success=False, error="MINIMAX_API_KEY not set. " + self.install_instructions)

        import requests

        start = time.time()
        base = _api_base()
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        # ── Build create-task payload ───────────────────────────────────────────
        payload: dict[str, Any] = {
            "model": variant,
            "prompt": inputs["prompt"],
            "duration": int(inputs.get("duration", 6)),
            "resolution": inputs.get("resolution", "768P"),
            "prompt_optimizer": inputs.get("prompt_optimizer", True),
        }

        if operation == "image_to_video":
            err = self._attach_first_frame(inputs, payload)
            if err:
                return ToolResult(success=False, error=err)

        try:
            task_id = self._create_task(base, headers, payload)
            file_id = self._poll_task(base, headers, task_id)
            download_url = self._retrieve_file(base, headers, file_id)

            video_response = requests.get(download_url, timeout=300)
            video_response.raise_for_status()
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(video_response.content)
        except Exception as exc:
            return ToolResult(success=False, error=f"MiniMax video generation failed: {exc}")

        probed = probe_output(output_path)
        return ToolResult(
            success=True,
            data={
                "provider": "minimax",
                "model": variant,
                "model_name": _MODELS[variant]["name"],
                "prompt": inputs["prompt"],
                "operation": operation,
                "duration": inputs.get("duration", 6),
                "resolution": inputs.get("resolution", "768P"),
                "output": str(output_path),
                "output_path": str(output_path),
                "format": "mp4",
                **probed,
            },
            artifacts=[str(output_path)],
            cost_usd=self.estimate_cost(inputs),
            duration_seconds=round(time.time() - start, 2),
            model=variant,
        )

    # ── Helpers ──────────────────────────────────────────────────────────────────

    def _attach_first_frame(self, inputs: dict[str, Any], payload: dict[str, Any]) -> str | None:
        """image_to_video: first_frame_image accepts a public URL or a base64 data URL."""
        if inputs.get("image_url"):
            payload["first_frame_image"] = inputs["image_url"]
            return None
        path_str = inputs.get("image_path")
        if not path_str:
            return "image_to_video requires image_url or image_path"
        path = Path(path_str)
        if not path.exists():
            return f"First-frame image not found: {path_str}"
        suffix = path.suffix.lower().lstrip(".")
        mime = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png", "webp": "image/webp"}.get(
            suffix, "image/jpeg"
        )
        b64 = base64.b64encode(path.read_bytes()).decode("utf-8")
        payload["first_frame_image"] = f"data:{mime};base64,{b64}"
        return None

    def _create_task(self, base: str, headers: dict[str, str], payload: dict[str, Any]) -> str:
        import requests

        resp = requests.post(f"{base}/video_generation", headers=headers, json=payload, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        self._check_base_resp(data)
        task_id = data.get("task_id")
        if not task_id:
            raise ValueError(f"No task_id in MiniMax response: {data}")
        return task_id

    def _poll_task(self, base: str, headers: dict[str, str], task_id: str, max_wait: int = 900) -> str:
        import requests

        url = f"{base}/query/video_generation"
        deadline = time.time() + max_wait
        while time.time() < deadline:
            time.sleep(8)
            resp = requests.get(url, headers=headers, params={"task_id": task_id}, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            self._check_base_resp(data)
            status = data.get("status", "")
            if status == "Success" or status == "success":
                file_id = data.get("file_id", "")
                if not file_id:
                    raise ValueError(f"Task succeeded but no file_id: {data}")
                return file_id
            if status in ("Fail", "failed", "Failed"):
                raise ValueError(f"MiniMax video task failed: {data}")
        raise TimeoutError(f"MiniMax video task {task_id} timed out after {max_wait}s")

    def _retrieve_file(self, base: str, headers: dict[str, str], file_id: str) -> str:
        import requests

        resp = requests.get(f"{base}/files/retrieve", headers=headers, params={"file_id": file_id}, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        self._check_base_resp(data)
        download_url = data.get("file", {}).get("download_url", "")
        if not download_url:
            raise ValueError(f"No download_url in MiniMax file response: {data}")
        return download_url

    @staticmethod
    def _check_base_resp(data: dict[str, Any]) -> None:
        base_resp = data.get("base_resp", {})
        code = base_resp.get("status_code", 0)
        if code != 0:
            raise ValueError(f"MiniMax API error [{code}]: {base_resp.get('status_msg', 'unknown')}")
