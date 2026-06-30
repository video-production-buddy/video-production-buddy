"""Face restoration tool wrapping CodeFormer / GFPGAN.

Restores degraded or low-quality faces in images and video frames.
Fixes blur, compression artifacts, and low resolution specifically on
face regions while preserving the rest of the image.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from tools.base_tool import (
    BaseTool,
    Determinism,
    ExecutionMode,
    ResourceProfile,
    ToolResult,
    ToolRuntime,
    ToolStability,
    ToolTier,
)
from tools.output_paths import require_explicit_output_path


MODELS = ["CodeFormer", "GFPGAN"]


class FaceRestore(BaseTool):
    name = "face_restore"
    version = "0.1.0"
    tier = ToolTier.ENHANCE
    capability = "enhancement"
    provider = "codeformer"
    stability = ToolStability.EXPERIMENTAL
    execution_mode = ExecutionMode.SYNC
    determinism = Determinism.DETERMINISTIC
    runtime = ToolRuntime.LOCAL_GPU

    dependencies = ["python:gfpgan", "python:torch", "python:cv2"]
    install_instructions = (
        "uv pip install gfpgan torch\n"
        "Works on: CUDA (NVIDIA), MPS (Apple Silicon M-series, macOS >= 12.3), CPU fallback.\n"
        "No CUDA build needed on macOS — uv pip install torch includes MPS support."
    )
    agent_skills = ["ffmpeg"]
    fallback = None

    capabilities = [
        "face_restoration",
        "face_detection",
        "quality_enhancement",
    ]
    best_for = [
        "Restoring low-quality face images when local GPU models are installed",
        "Improving source portrait quality before avatar or talking-head generation",
    ]

    input_schema = {
        "type": "object",
        "required": ["input_path", "output_path"],
        "properties": {
            "input_path": {
                "type": "string",
                "description": "Path to image or video frame",
            },
            "output_path": {
                "type": "string",
                "description": "Project-scoped output path under projects/<project-name>/assets/... or projects/<project-name>/renders/...",
            },
            "model": {
                "type": "string",
                "enum": MODELS,
                "default": "CodeFormer",
                "description": "Restoration model to use",
            },
            "fidelity": {
                "type": "number",
                "default": 0.5,
                "description": (
                    "0 = max quality, 1 = max fidelity to input (CodeFormer only)"
                ),
            },
            "upscale": {
                "type": "integer",
                "default": 2,
                "description": "Face upscale factor",
            },
            "bg_upsampler": {
                "type": "boolean",
                "default": False,
                "description": "Also upscale background with Real-ESRGAN",
            },
        },
    }
    output_schema = {
        "type": "object",
        "required": [
            "input",
            "output",
            "output_path",
            "model",
            "faces_detected",
            "upscale",
            "fidelity",
            "bg_upsampler",
        ],
        "properties": {
            "input": {"type": "string"},
            "output": {"type": "string"},
            "output_path": {"type": "string"},
            "model": {"type": "string", "enum": MODELS},
            "faces_detected": {"type": "integer"},
            "upscale": {"type": "integer"},
            "fidelity": {"type": ["number", "null"]},
            "bg_upsampler": {"type": "boolean"},
        },
    }

    resource_profile = ResourceProfile(
        cpu_cores=2, ram_mb=2048, vram_mb=2048, disk_mb=1000
    )
    idempotency_key_fields = [
        "input_path",
        "output_path",
        "model",
        "fidelity",
        "upscale",
        "bg_upsampler",
    ]
    side_effects = ["writes restored image to output_path"]
    user_visible_verification = [
        "Compare restored face with original for natural appearance",
        "Verify face identity is preserved after restoration",
    ]

    def execute(self, inputs: dict[str, Any]) -> ToolResult:
        input_path = Path(inputs["input_path"])
        if not input_path.exists():
            return ToolResult(success=False, error=f"Input not found: {input_path}")

        output_path, output_error = require_explicit_output_path(
            inputs,
            self.name,
            artifact_label="restored face image",
        )
        if output_error:
            return output_error
        assert output_path is not None
        model_name = inputs.get("model", "CodeFormer")
        fidelity = inputs.get("fidelity", 0.5)
        upscale = inputs.get("upscale", 2)
        bg_upsampler_flag = inputs.get("bg_upsampler", False)
        if model_name not in MODELS:
            return ToolResult(success=False, error=f"Unknown model: {model_name}")

        try:
            import cv2
            import inspect
            from gfpgan import GFPGANer
            import torch
            from tools.video._shared import get_torch_device as _get_device
        except ImportError as e:
            return ToolResult(
                success=False,
                error=f"Missing dependency: {e}. Run: uv pip install gfpgan",
            )

        _device = _get_device()

        start = time.time()

        # Optional background upsampler
        bg_upsampler = None
        if bg_upsampler_flag:
            try:
                from basicsr.archs.rrdbnet_arch import RRDBNet
                from realesrgan import RealESRGANer

                realesrgan_model = RRDBNet(
                    num_in_ch=3, num_out_ch=3, num_feat=64,
                    num_block=23, num_grow_ch=32, scale=2,
                )
                bg_kwargs: dict = {
                    "scale": 2,
                    "model_path": (
                        "https://github.com/xinntao/Real-ESRGAN/releases/download/"
                        "v0.2.1/RealESRGAN_x2plus.pth"
                    ),
                    "model": realesrgan_model,
                    "tile": 400,
                    "tile_pad": 10,
                    "pre_pad": 0,
                    "half": (_device == "cuda"),
                }
                # Guard: only pass device= if the installed version accepts it
                if "device" in inspect.signature(RealESRGANer.__init__).parameters:
                    bg_kwargs["device"] = torch.device(_device)
                bg_upsampler = RealESRGANer(**bg_kwargs)
            except ImportError:
                bg_upsampler = None

        # Select model path based on model choice
        if model_name == "CodeFormer":
            model_path = (
                "https://github.com/sczhou/CodeFormer/releases/download/"
                "v0.1.0/codeformer.pth"
            )
            arch = "CodeFormer"
        else:
            model_path = (
                "https://github.com/TencentARC/GFPGAN/releases/download/"
                "v1.3.0/GFPGANv1.3.pth"
            )
            arch = "clean"

        # Instantiate restorer
        try:
            restorer_kwargs: dict = {
                "model_path": model_path,
                "upscale": upscale,
                "arch": arch,
                "bg_upsampler": bg_upsampler,
            }
            # Guard: only pass device= if the installed version accepts it
            if "device" in inspect.signature(GFPGANer.__init__).parameters:
                restorer_kwargs["device"] = torch.device(_device)
            restorer = GFPGANer(**restorer_kwargs)
        except Exception as e:
            return ToolResult(
                success=False, error=f"Failed to load {model_name} model: {e}"
            )

        # Read input image
        input_img = cv2.imread(str(input_path), cv2.IMREAD_COLOR)
        if input_img is None:
            return ToolResult(
                success=False, error=f"Failed to read image: {input_path}"
            )

        # Run restoration
        try:
            _, restored_faces, restored_img = restorer.enhance(
                input_img,
                has_aligned=False,
                only_center_face=False,
                paste_back=True,
                weight=fidelity if model_name == "CodeFormer" else None,
            )
        except Exception as e:
            return ToolResult(success=False, error=f"Restoration failed: {e}")

        if restored_img is None:
            return ToolResult(
                success=False, error="Restoration produced no output"
            )

        # Save restored output
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if not cv2.imwrite(str(output_path), restored_img) or not output_path.exists():
            return ToolResult(
                success=False,
                error=f"Expected output was not created: {output_path}",
            )

        elapsed = time.time() - start
        faces_detected = len(restored_faces) if restored_faces else 0

        return ToolResult(
            success=True,
            data={
                "input": str(input_path),
                "output": str(output_path),
                "output_path": str(output_path),
                "model": model_name,
                "faces_detected": faces_detected,
                "upscale": upscale,
                "fidelity": fidelity if model_name == "CodeFormer" else None,
                "bg_upsampler": bg_upsampler_flag,
            },
            artifacts=[str(output_path)],
            duration_seconds=round(elapsed, 2),
        )
