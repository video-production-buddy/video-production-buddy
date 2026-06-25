"""HyperFrames composition tool — HTML/CSS/GSAP render path.

Sibling to `video_compose` (FFmpeg + Remotion). This tool owns the HyperFrames
runtime end-to-end: workspace materialization, `hyperframes lint`,
`hyperframes validate`, and `hyperframes render`. It is invoked by
`video_compose` when `edit_decisions.render_runtime == "hyperframes"`, and
can also be called directly by pipelines that want HyperFrames-specific
operations (lint-only, validate-only, scaffold-only).

This tool deliberately does NOT attempt parity with every Remotion scene
component. See `skills/core/hyperframes.md` for what is in scope in Phase 1
and what remains Remotion-only.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, Optional

from lib.hyperframes_gsap_shim import gsap_shim_script
from tools.base_tool import (
    BaseTool,
    Determinism,
    ExecutionMode,
    ResourceProfile,
    ResumeSupport,
    RetryPolicy,
    ToolResult,
    ToolRuntime,
    ToolStability,
    ToolStatus,
    ToolTier,
)
from tools.output_paths import require_explicit_output_path


log = logging.getLogger("hyperframes_compose")


_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".tif", ".webp", ".gif"}
_VIDEO_EXTENSIONS = {".mp4", ".mov", ".webm", ".mkv", ".m4v"}
_AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac"}
_CJK_CHAR_RE = re.compile(
    r"[\u3000-\u303f\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\uff00-\uffef]"
)
_CJK_FONT_FAMILY = "Noto Sans SC"
_CJK_FONT_FILENAME = "NotoSansSC.ttf"
_DENSE_KEYFRAME_THRESHOLD_SECONDS = 5.0
_HYPERFRAMES_AUTO_RESOLVED_FONTS = {
    "outfit": "Outfit",
    "montserrat": "Montserrat",
    "inter": "Inter",
    "jetbrains mono": "JetBrains Mono",
    "poppins": "Poppins",
    "playfair display": "Playfair Display",
}


class HyperFramesCompose(BaseTool):
    name = "hyperframes_compose"
    version = "0.1.0"
    tier = ToolTier.CORE
    capability = "video_post"
    provider = "hyperframes"
    stability = ToolStability.BETA
    execution_mode = ExecutionMode.SYNC
    determinism = Determinism.DETERMINISTIC
    runtime = ToolRuntime.LOCAL

    dependencies = ["cmd:npx", "cmd:ffmpeg"]
    install_instructions = (
        "Requires Node.js >= 22 (https://nodejs.org/) and FFmpeg "
        "(https://ffmpeg.org/download.html). The HyperFrames CLI is fetched "
        "on first use via `npx hyperframes` (npm package: `hyperframes`). "
        "Note: the upstream monorepo develops the package as `@hyperframes/cli`, "
        "but it publishes to npm as `hyperframes`. `npx @hyperframes/cli` "
        "returns 404 -- do NOT use that form. Verify setup with "
        "`npx hyperframes doctor` or run the `doctor` operation on this tool."
    )
    agent_skills = [
        "hyperframes",
        "hyperframes-cli",
        "hyperframes-registry",
        "website-to-hyperframes",
        "gsap-core",
        "gsap-timeline",
    ]

    capabilities = [
        "hyperframes_render",
        "hyperframes_lint",
        "hyperframes_validate",
        "hyperframes_doctor",
        "scaffold_workspace",
        "add_block",
    ]

    best_for = [
        "HTML/CSS/GSAP composition: kinetic typography, product promos, launch reels",
        "Motion-graphics-heavy briefs where the scene library in remotion-composer/ doesn't fit",
        "Website-to-video / UI-driven compositions",
        "Registry-block-driven scenes (hyperframes add data-chart, grain-overlay, etc.)",
    ]
    not_good_for = [
        "Word-level caption burn (stays on Remotion in Phase 1)",
        "Avatar / lip-sync presenter (stays on Remotion in Phase 1)",
        "Existing React scene stack (text_card, stat_card, chart, comparison): reuse Remotion",
    ]
    fallback_tools = ["video_compose"]

    input_schema = {
        "type": "object",
        "required": ["operation"],
        "properties": {
            "operation": {
                "type": "string",
                "enum": [
                    "render",
                    "lint",
                    "validate",
                    "doctor",
                    "scaffold_workspace",
                    "add_block",
                ],
                "description": (
                    "render: materialize workspace + lint + validate + render to MP4. "
                    "lint: run `hyperframes lint` on an existing workspace. "
                    "validate: run `hyperframes validate` (browser-based). "
                    "doctor: run `hyperframes doctor` to check environment. "
                    "scaffold_workspace: materialize HTML/CSS/assets but do not render. "
                    "add_block: run `hyperframes add <name>` to install a registry "
                    "block or component into an existing workspace."
                ),
            },
            "block_name": {
                "type": "string",
                "description": (
                    "Registry block or component name for operation='add_block' "
                    "(e.g. 'data-chart', 'grain-overlay', 'shimmer-sweep'). "
                    "See https://hyperframes.heygen.com/catalog for the list."
                ),
            },
            "workspace_path": {
                "type": "string",
                "description": (
                    "Target HyperFrames workspace directory. Typically "
                    "`projects/<name>/hyperframes/`. Required for every op "
                    "except doctor."
                ),
            },
            "output_path": {
                "type": "string",
                "description": (
                    "Project-scoped output MP4 path. Used by operation='render', "
                    "e.g. projects/<project-name>/renders/final.mp4."
                ),
            },
            "edit_decisions": {
                "type": "object",
                "description": (
                    "Full edit_decisions artifact — required for render and "
                    "scaffold_workspace. Used to generate index.html + CSS."
                ),
            },
            "asset_manifest": {
                "type": "object",
                "description": (
                    "Full asset_manifest artifact — required for render and "
                    "scaffold_workspace. Used to resolve asset IDs to file paths."
                ),
            },
            "playbook": {
                "type": "object",
                "description": (
                    "Loaded playbook dict. Used to drive the style bridge "
                    "(CSS custom properties, typography, motion defaults)."
                ),
            },
            "profile": {
                "type": "string",
                "description": "Media profile name (youtube_landscape, tiktok_vertical, etc.).",
            },
            "quality": {
                "type": "string",
                "enum": ["draft", "standard", "high"],
                "default": "standard",
                "description": "Render quality. `draft` for iterating, `high` for delivery.",
            },
            "fps": {
                "type": "integer",
                "enum": [24, 30, 60],
                "default": 30,
            },
            "strict": {
                "type": "boolean",
                "default": False,
                "description": (
                    "If true, fail the render on any lint error. Matches "
                    "`hyperframes render --strict`."
                ),
            },
            "skip_contrast": {
                "type": "boolean",
                "default": False,
                "description": (
                    "Skip the WCAG contrast audit during validate. Acceptable "
                    "while iterating; forbidden for final delivery."
                ),
            },
            "workers": {
                "type": "integer",
                "minimum": 1,
                "description": (
                    "Number of parallel Chrome workers for `hyperframes render`. "
                    "Defaults to the CLI default unless the composition is "
                    "video-heavy; with >5 video cuts the tool automatically "
                    "uses 1 worker to avoid headless Chrome timeouts."
                ),
            },
        },
        "allOf": [
            {
                "if": {"properties": {"operation": {"const": "render"}}},
                "then": {"required": ["output_path"]},
            },
        ],
    }
    output_schema = {
        "type": "object",
        "properties": {
            "operation": {
                "type": "string",
                "enum": [
                    "render",
                    "scaffold_workspace",
                    "add_block",
                ],
            },
            "output": {"type": "string"},
            "output_path": {"type": "string"},
            "workspace": {"type": "string"},
            "workspace_path": {"type": "string"},
            "width": {"type": "integer", "minimum": 0},
            "height": {"type": "integer", "minimum": 0},
            "fps": {"type": "integer", "minimum": 1},
            "quality": {"type": "string"},
            "workers": {"type": ["integer", "null"], "minimum": 1},
            "steps": {"type": "object"},
            "total_duration_seconds": {"type": "number", "minimum": 0},
            "cut_count": {"type": "integer", "minimum": 0},
            "asset_copies": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "from": {"type": "string", "minLength": 1},
                        "to": {"type": "string", "minLength": 1},
                        "transform": {"type": "string", "minLength": 1},
                        "keyframe_interval_threshold_seconds": {
                            "type": "number",
                            "minimum": 0,
                        },
                    },
                    "required": ["from", "to"],
                },
            },
            "audio_assets": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "track": {
                            "type": "string",
                            "enum": ["narration", "music"],
                        },
                        "asset_id": {"type": ["string", "null"]},
                        "from": {"type": "string", "minLength": 1},
                        "to": {"type": "string", "minLength": 1},
                        "src": {"type": "string", "minLength": 1},
                    },
                    "required": ["track", "asset_id", "from", "to", "src"],
                },
            },
            "font_assets": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "family": {"type": "string", "minLength": 1},
                        "from": {"type": "string", "minLength": 1},
                        "to": {"type": "string", "minLength": 1},
                        "src": {"type": "string", "minLength": 1},
                        "format": {"type": "string", "minLength": 1},
                    },
                    "required": ["family", "from", "to", "src", "format"],
                },
            },
            "block_name": {"type": "string"},
            "runtime_check": {
                "type": "object",
                "properties": {
                    "runtime_available": {"type": "boolean"},
                    "node_major": {"type": ["integer", "null"], "minimum": 0},
                    "ffmpeg_available": {"type": "boolean"},
                    "npx_available": {"type": "boolean"},
                    "npm_package": {"type": "string", "minLength": 1},
                    "npm_package_version": {"type": ["string", "null"]},
                    "npm_resolve_error": {"type": ["string", "null"]},
                    "cli_available": {"type": "boolean"},
                    "cli_smoke_error": {"type": ["string", "null"]},
                    "reasons": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                },
                "required": [
                    "runtime_available",
                    "node_major",
                    "ffmpeg_available",
                    "npx_available",
                    "npm_package",
                    "npm_package_version",
                    "npm_resolve_error",
                    "cli_available",
                    "cli_smoke_error",
                    "reasons",
                ],
            },
            "cli_doctor": {
                "type": "object",
                "properties": {
                    "exit_code": {"type": "integer"},
                    "stdout_tail": {"type": "string"},
                    "stderr_tail": {"type": "string"},
                },
                "required": ["exit_code", "stdout_tail", "stderr_tail"],
            },
            "cli_doctor_error": {"type": "string"},
            "exit_code": {"type": "integer"},
            "report": {"type": "object"},
            "stdout_tail": {"type": "string"},
            "stderr_tail": {"type": "string"},
        },
        "anyOf": [
            {
                "properties": {
                    "operation": {"const": "render"},
                    "steps": {
                        "type": "object",
                        "properties": {
                            "scaffold": {"type": "object"},
                            "lint": {"type": "object"},
                            "validate": {"type": "object"},
                            "render": {
                                "type": "object",
                                "properties": {
                                    "exit_code": {"type": "integer", "const": 0},
                                    "cli_output_path": {
                                        "type": "string",
                                        "minLength": 1,
                                    },
                                    "stdout_tail": {"type": "string"},
                                    "stderr_tail": {"type": "string"},
                                    "workers": {"type": ["integer", "null"]},
                                },
                                "required": ["exit_code", "cli_output_path"],
                            },
                        },
                        "required": ["scaffold", "lint", "validate", "render"],
                    }
                },
                "required": [
                    "operation",
                    "output",
                    "output_path",
                    "workspace",
                    "workspace_path",
                    "width",
                    "height",
                    "fps",
                    "quality",
                    "steps",
                ],
            },
            {
                "properties": {"operation": {"const": "scaffold_workspace"}},
                "required": [
                    "operation",
                    "workspace",
                    "workspace_path",
                    "width",
                    "height",
                    "fps",
                    "total_duration_seconds",
                    "cut_count",
                    "asset_copies",
                    "audio_assets",
                    "font_assets",
                ],
            },
            {
                "properties": {"operation": {"const": "add_block"}},
                "required": [
                    "operation",
                    "block_name",
                    "workspace",
                    "workspace_path",
                    "exit_code",
                ],
            },
            {"required": ["runtime_check"]},
            {
                "not": {"required": ["operation"]},
                "required": ["exit_code", "stderr_tail"],
                "anyOf": [
                    {"required": ["report"]},
                    {"required": ["stdout_tail"]},
                ],
            },
        ],
    }

    resource_profile = ResourceProfile(
        cpu_cores=4, ram_mb=3072, vram_mb=0, disk_mb=2000, network_required=False
    )
    retry_policy = RetryPolicy(max_retries=0)
    resume_support = ResumeSupport.FROM_START
    idempotency_key_fields = [
        "operation",
        "block_name",
        "workspace_path",
        "output_path",
        "edit_decisions",
        "asset_manifest",
        "playbook",
        "profile",
        "quality",
        "fps",
        "strict",
        "skip_contrast",
        "workers",
    ]
    side_effects = [
        "writes HTML/CSS/JS files into workspace_path",
        "copies asset files into workspace_path/assets/",
        "writes MP4 to output_path",
    ]
    user_visible_verification = [
        "Inspect rendered MP4 metadata, audio streams, and sampled frames for scene pacing, typography, and audio",
        "Inspect workspace_path/index.html or sampled frames; run interactive HyperFrames preview only if the user explicitly requests it",
    ]

    # ------------------------------------------------------------------
    # Status / availability
    # ------------------------------------------------------------------

    _NODE_FLOOR_MAJOR = 22
    _NPM_PACKAGE = "hyperframes"  # published npm name (NOT @hyperframes/cli — that's 404)
    # Process-level cache for the npm resolve check. Shape:
    #   {"version": "0.4.5"}   → package resolves
    #   {"error": "<short>"}   → resolution failed (offline, unpublished, etc.)
    # We cache per-process so the first call pays ~2-5s and subsequent calls
    # (get_info spam from the registry) are free.
    _npm_resolve_cache: Optional[dict[str, str]] = None
    _cli_smoke_cache: Optional[dict[str, str]] = None

    @classmethod
    def _node_major_version(cls) -> Optional[int]:
        """Return Node.js major version, or None if node isn't installed."""
        node = shutil.which("node")
        if not node:
            return None
        try:
            out = subprocess.run(
                [node, "--version"], capture_output=True, text=True, timeout=5
            )
            if out.returncode != 0:
                return None
            match = re.match(r"v?(\d+)\.", out.stdout.strip())
            if not match:
                return None
            return int(match.group(1))
        except (OSError, subprocess.SubprocessError):
            return None

    @classmethod
    def _resolve_npm_package(cls) -> dict[str, str]:
        """Verify the `hyperframes` npm package actually resolves.

        `_runtime_check` previously only verified that node/ffmpeg/npx existed
        on PATH, which meant `runtime_available: True` on any machine with
        Node + FFmpeg — even offline, even if npm was down, even if the
        package was unpublished. This method performs a cheap
        `npm view hyperframes version` (5s timeout) and caches the answer
        for the rest of the process.

        Returns {"version": "X.Y.Z"} on success, {"error": "<short>"} on any
        failure (404, timeout, network error, npm missing). Never raises.
        """
        if cls._npm_resolve_cache is not None:
            return cls._npm_resolve_cache

        npm = shutil.which("npm")
        if not npm:
            cls._npm_resolve_cache = {"error": "npm not on PATH"}
            return cls._npm_resolve_cache

        try:
            proc = subprocess.run(
                [npm, "view", cls._NPM_PACKAGE, "version"],
                capture_output=True,
                text=True,
                timeout=5,
            )
        except subprocess.TimeoutExpired:
            cls._npm_resolve_cache = {"error": "timeout (5s) — offline or slow registry"}
            return cls._npm_resolve_cache
        except (OSError, subprocess.SubprocessError) as e:
            cls._npm_resolve_cache = {"error": f"npm view failed: {type(e).__name__}"}
            return cls._npm_resolve_cache

        if proc.returncode != 0:
            stderr = (proc.stderr or "").strip()
            # Most common failure is 404 (package unpublished or name wrong).
            if "404" in stderr or "E404" in stderr:
                cls._npm_resolve_cache = {
                    "error": f"npm package `{cls._NPM_PACKAGE}` not found (404)"
                }
            else:
                tail = stderr.splitlines()[-1][:200] if stderr else f"exit {proc.returncode}"
                cls._npm_resolve_cache = {"error": f"npm view failed: {tail}"}
            return cls._npm_resolve_cache

        version = (proc.stdout or "").strip()
        if not version:
            cls._npm_resolve_cache = {"error": "npm view returned empty version"}
        else:
            cls._npm_resolve_cache = {"version": version}
        return cls._npm_resolve_cache

    @classmethod
    def _probe_cli(cls) -> dict[str, str]:
        """Verify the published CLI can actually start through npx."""
        if cls._cli_smoke_cache is not None:
            return cls._cli_smoke_cache

        npx = shutil.which("npx")
        if not npx:
            cls._cli_smoke_cache = {"error": "npx not on PATH"}
            return cls._cli_smoke_cache

        try:
            proc = subprocess.run(
                [npx, "--yes", cls._NPM_PACKAGE, "--version"],
                capture_output=True,
                text=True,
                timeout=30,
            )
        except subprocess.TimeoutExpired:
            cls._cli_smoke_cache = {
                "error": "timeout (30s) running npx hyperframes --version"
            }
            return cls._cli_smoke_cache
        except (OSError, subprocess.SubprocessError) as e:
            cls._cli_smoke_cache = {
                "error": f"npx hyperframes --version failed: {type(e).__name__}"
            }
            return cls._cli_smoke_cache

        if proc.returncode != 0:
            output = "\n".join(
                part.strip() for part in (proc.stderr, proc.stdout) if part and part.strip()
            )
            tail = output.splitlines()[-1][:200] if output else f"exit {proc.returncode}"
            cls._cli_smoke_cache = {
                "error": f"npx hyperframes --version exit {proc.returncode}: {tail}"
            }
            return cls._cli_smoke_cache

        version = (proc.stdout or "").strip().splitlines()
        if not version:
            cls._cli_smoke_cache = {
                "error": "npx hyperframes --version returned empty output"
            }
        else:
            cls._cli_smoke_cache = {"version": version[-1]}
        return cls._cli_smoke_cache

    def _runtime_check(self) -> dict[str, Any]:
        """Return availability state for the HyperFrames runtime.

        Checks BOTH local binaries (node >= 22, ffmpeg, npx) AND that the
        `hyperframes` npm package actually resolves. A missing/404 package
        counts as unavailable — `runtime_available: True` means the runtime
        can genuinely run end-to-end, not just that the local tooling exists.
        """
        node_major = self._node_major_version()
        ffmpeg_ok = shutil.which("ffmpeg") is not None
        npx_ok = shutil.which("npx") is not None

        reasons: list[str] = []
        if node_major is None:
            reasons.append("node not found on PATH")
        elif node_major < self._NODE_FLOOR_MAJOR:
            reasons.append(
                f"node major version {node_major} < required {self._NODE_FLOOR_MAJOR}"
            )
        if not npx_ok:
            reasons.append("npx not found on PATH")
        if not ffmpeg_ok:
            reasons.append("ffmpeg not found on PATH")

        # Only probe npm if the local tooling is actually usable — otherwise
        # a missing-node run would also show a confusing npm error.
        npm_resolve: dict[str, str] = {}
        cli_smoke: dict[str, str] = {}
        if not reasons:
            npm_resolve = self._resolve_npm_package()
            if "error" in npm_resolve:
                reasons.append(
                    f"npm package `{self._NPM_PACKAGE}` not resolvable: "
                    f"{npm_resolve['error']}"
                )
        if not reasons:
            cli_smoke = self._probe_cli()
            if "error" in cli_smoke:
                reasons.append(
                    f"HyperFrames CLI smoke check failed: {cli_smoke['error']}"
                )

        return {
            "runtime_available": not reasons,
            "node_major": node_major,
            "ffmpeg_available": ffmpeg_ok,
            "npx_available": npx_ok,
            "npm_package": self._NPM_PACKAGE,
            "npm_package_version": npm_resolve.get("version"),
            "npm_resolve_error": npm_resolve.get("error"),
            "cli_available": "version" in cli_smoke,
            "cli_smoke_error": cli_smoke.get("error"),
            "reasons": reasons,
        }

    def get_status(self) -> ToolStatus:
        check = self._runtime_check()
        return ToolStatus.AVAILABLE if check["runtime_available"] else ToolStatus.UNAVAILABLE

    def get_info(self) -> dict[str, Any]:
        info = super().get_info()
        check = self._runtime_check()
        info["hyperframes_runtime"] = check
        if not check["runtime_available"]:
            info["setup_offer"] = {
                "effort": (
                    "1-minute fix"
                    if check["npx_available"] and check["ffmpeg_available"]
                    else "5-minute fix (install Node 22+ and/or FFmpeg)"
                ),
                "install_instructions": self.install_instructions,
                "unlocks": (
                    "HTML/CSS/GSAP composition runtime — kinetic typography, "
                    "product promos, registry blocks, website-to-video."
                ),
            }
        return info

    def estimate_cost(self, inputs: dict[str, Any]) -> float:
        return 0.0

    def estimate_runtime(self, inputs: dict[str, Any]) -> float:
        if not isinstance(inputs, dict):
            return 30.0
        ed = inputs.get("edit_decisions") or {}
        if not isinstance(ed, dict):
            return 30.0
        cuts = ed.get("cuts", [])
        if not isinstance(cuts, list):
            return 30.0
        total = 0.0
        for c in cuts:
            if not isinstance(c, dict):
                continue
            try:
                out_s = float(c.get("out_seconds", 0) or 0)
                in_s = float(c.get("in_seconds", 0) or 0)
            except (TypeError, ValueError):
                continue
            total += max(0.0, out_s - in_s)
        return 30.0 + total * 0.5

    # ------------------------------------------------------------------
    # Execute
    # ------------------------------------------------------------------

    def execute(self, inputs: dict[str, Any]) -> ToolResult:
        operation = inputs.get("operation")
        if not operation:
            return ToolResult(success=False, error="operation is required")
        start = time.time()
        try:
            if operation == "doctor":
                result = self._doctor(inputs)
            elif operation == "scaffold_workspace":
                result = self._scaffold(inputs)
            elif operation == "lint":
                result = self._lint(inputs)
            elif operation == "validate":
                result = self._validate(inputs)
            elif operation == "render":
                result = self._render(inputs)
            elif operation == "add_block":
                result = self._add_block(inputs)
            else:
                return ToolResult(success=False, error=f"Unknown operation: {operation}")
        except Exception as e:
            log.exception("hyperframes_compose failed")
            return ToolResult(success=False, error=f"{type(e).__name__}: {e}")

        result.duration_seconds = round(time.time() - start, 2)
        return result

    # ------------------------------------------------------------------
    # Operations
    # ------------------------------------------------------------------

    def _doctor(self, inputs: dict[str, Any]) -> ToolResult:
        """Probe the environment. Reports node/ffmpeg/npx plus CLI doctor output."""
        check = self._runtime_check()
        out: dict[str, Any] = {"runtime_check": check}

        if not check["runtime_available"]:
            return ToolResult(
                success=False,
                error=(
                    "HyperFrames runtime floor not met: "
                    + "; ".join(check["reasons"])
                ),
                data=out,
            )

        # Ask the CLI itself for a deeper check. This also warms the npm
        # cache so the first real render doesn't pay the download cost.
        try:
            proc = self._run_hf(["doctor"], cwd=None, timeout=180, check=False)
            out["cli_doctor"] = {
                "exit_code": proc.returncode,
                "stdout_tail": (proc.stdout or "")[-4000:],
                "stderr_tail": (proc.stderr or "")[-4000:],
            }
            ok = proc.returncode == 0
            return ToolResult(
                success=ok,
                data=out,
                error=None if ok else f"hyperframes doctor exit {proc.returncode}",
            )
        except Exception as e:
            out["cli_doctor_error"] = str(e)
            return ToolResult(
                success=False,
                error=f"hyperframes doctor failed: {e}",
                data=out,
            )

    def _scaffold(self, inputs: dict[str, Any]) -> ToolResult:
        """Materialize the HyperFrames workspace from Video Production Buddy artifacts.

        This does NOT call `hyperframes init` — we want full control over the
        generated files so they map cleanly to edit_decisions. `init` is
        meant for humans bootstrapping a project by hand.
        """
        workspace = self._require_workspace(inputs)
        edit_decisions = inputs.get("edit_decisions") or {}
        if not isinstance(edit_decisions, dict):
            return ToolResult(
                success=False,
                error="edit_decisions must be an object for scaffold_workspace",
            )
        asset_manifest = inputs.get("asset_manifest") or {}
        if not isinstance(asset_manifest, dict):
            return ToolResult(
                success=False,
                error="asset_manifest must be an object for scaffold_workspace",
            )
        assets = asset_manifest.get("assets", [])
        if not isinstance(assets, list):
            return ToolResult(
                success=False,
                error="asset_manifest.assets must be an array for scaffold_workspace",
            )
        for index, asset in enumerate(assets):
            if not isinstance(asset, dict):
                return ToolResult(
                    success=False,
                    error=(
                        f"asset_manifest.assets[{index}] must be an object "
                        "for scaffold_workspace"
                    ),
                )
            asset_id = asset.get("id")
            if asset_id is not None and not isinstance(asset_id, str):
                return ToolResult(
                    success=False,
                    error=(
                        f"asset_manifest.assets[{index}].id must be a string "
                        "for scaffold_workspace"
                    ),
                )
            asset_path = asset.get("path")
            if asset_path is not None and not isinstance(asset_path, str):
                return ToolResult(
                    success=False,
                    error=(
                        f"asset_manifest.assets[{index}].path must be a string "
                        "for scaffold_workspace"
                    ),
                )
            if asset_path is not None:
                local_asset_path = Path(asset_path)
                if local_asset_path.exists() and not local_asset_path.is_file():
                    return ToolResult(
                        success=False,
                        error=(
                            f"asset_manifest.assets[{index}].path must reference "
                            "a file when the local path exists for scaffold_workspace"
                        ),
                    )
        playbook = inputs.get("playbook") or {}
        if not isinstance(playbook, dict):
            return ToolResult(
                success=False,
                error="playbook must be an object for scaffold_workspace",
            )
        profile_name = inputs.get("profile")

        cuts = edit_decisions.get("cuts")
        if not isinstance(cuts, list):
            return ToolResult(
                success=False,
                error="edit_decisions.cuts must be a non-empty array for scaffold_workspace",
            )
        if not cuts:
            return ToolResult(
                success=False,
                error="edit_decisions with non-empty cuts[] is required for scaffold_workspace",
            )
        for index, cut in enumerate(cuts):
            if not isinstance(cut, dict):
                return ToolResult(
                    success=False,
                    error=(
                        f"edit_decisions.cuts[{index}] must be an object "
                        "for scaffold_workspace"
                    ),
                )
            source = cut.get("source")
            if source is not None and not isinstance(source, str):
                return ToolResult(
                    success=False,
                    error=(
                        f"edit_decisions.cuts[{index}].source must be a string "
                        "for scaffold_workspace"
                    ),
                )
            cut_type = cut.get("type")
            if cut_type is not None and not isinstance(cut_type, str):
                return ToolResult(
                    success=False,
                    error=(
                        f"edit_decisions.cuts[{index}].type must be a string "
                        "for scaffold_workspace"
                    ),
                )
            for seconds_field in ("in_seconds", "out_seconds"):
                seconds_value = cut.get(seconds_field)
                if seconds_value is None:
                    continue
                if isinstance(seconds_value, bool):
                    return ToolResult(
                        success=False,
                        error=(
                            f"edit_decisions.cuts[{index}].{seconds_field} "
                            "must be a number for scaffold_workspace"
                        ),
                    )
                try:
                    float(seconds_value)
                except (TypeError, ValueError):
                    return ToolResult(
                        success=False,
                        error=(
                            f"edit_decisions.cuts[{index}].{seconds_field} "
                            "must be a number for scaffold_workspace"
                        ),
                    )
            for text_field in ("text", "title", "subtitle", "caption", "reason"):
                text_value = cut.get(text_field)
                if text_value is not None and not isinstance(text_value, str):
                    return ToolResult(
                        success=False,
                        error=(
                            f"edit_decisions.cuts[{index}].{text_field} "
                            "must be a string for scaffold_workspace"
                        ),
                    )
        audio = edit_decisions.get("audio", {})
        if not isinstance(audio, dict):
            return ToolResult(
                success=False,
                error="edit_decisions.audio must be an object for scaffold_workspace",
            )
        narration = audio.get("narration", {})
        if not isinstance(narration, dict):
            return ToolResult(
                success=False,
                error=(
                    "edit_decisions.audio.narration must be an object "
                    "for scaffold_workspace"
                ),
            )
        narration_segments = narration.get("segments", [])
        if not isinstance(narration_segments, list):
            return ToolResult(
                success=False,
                error=(
                    "edit_decisions.audio.narration.segments must be an array "
                    "for scaffold_workspace"
                ),
            )
        for index, segment in enumerate(narration_segments):
            if not isinstance(segment, dict):
                return ToolResult(
                    success=False,
                    error=(
                        "edit_decisions.audio.narration.segments"
                        f"[{index}] must be an object for scaffold_workspace"
                    ),
                )
            segment_asset_id = segment.get("asset_id")
            if segment_asset_id is not None and not isinstance(segment_asset_id, str):
                return ToolResult(
                    success=False,
                    error=(
                        "edit_decisions.audio.narration.segments"
                        f"[{index}].asset_id must be a string for scaffold_workspace"
                    ),
                )
            for seconds_field in ("start_seconds", "end_seconds"):
                seconds_value = segment.get(seconds_field)
                if seconds_value is None:
                    continue
                if isinstance(seconds_value, bool):
                    return ToolResult(
                        success=False,
                        error=(
                            "edit_decisions.audio.narration.segments"
                            f"[{index}].{seconds_field} must be a number "
                            "for scaffold_workspace"
                        ),
                    )
                try:
                    float(seconds_value)
                except (TypeError, ValueError):
                    return ToolResult(
                        success=False,
                        error=(
                            "edit_decisions.audio.narration.segments"
                            f"[{index}].{seconds_field} must be a number "
                            "for scaffold_workspace"
                        ),
                    )
        music = audio.get("music", {})
        if not isinstance(music, dict):
            return ToolResult(
                success=False,
                error="edit_decisions.audio.music must be an object for scaffold_workspace",
            )
        music_asset_id = music.get("asset_id")
        if music_asset_id is not None and not isinstance(music_asset_id, str):
            return ToolResult(
                success=False,
                error=(
                    "edit_decisions.audio.music.asset_id must be a string "
                    "for scaffold_workspace"
                ),
            )
        music_src = music.get("src")
        if music_src is not None and not isinstance(music_src, str):
            return ToolResult(
                success=False,
                error=(
                    "edit_decisions.audio.music.src must be a string "
                    "for scaffold_workspace"
                ),
            )
        for music_number_field in (
            "fade_in_seconds",
            "fadeInSeconds",
            "fade_out_seconds",
            "fadeOutSeconds",
            "volume",
        ):
            music_number_value = music.get(music_number_field)
            if music_number_value is None:
                continue
            if isinstance(music_number_value, bool):
                return ToolResult(
                    success=False,
                    error=(
                        f"edit_decisions.audio.music.{music_number_field} "
                        "must be a number for scaffold_workspace"
                    ),
                )
            try:
                float(music_number_value)
            except (TypeError, ValueError):
                return ToolResult(
                    success=False,
                    error=(
                        f"edit_decisions.audio.music.{music_number_field} "
                        "must be a number for scaffold_workspace"
                    ),
                )
        metadata = edit_decisions.get("metadata", {})
        if not isinstance(metadata, dict):
            return ToolResult(
                success=False,
                error="edit_decisions.metadata must be an object for scaffold_workspace",
            )
        metadata_title = metadata.get("title")
        if metadata_title is not None and not isinstance(metadata_title, str):
            return ToolResult(
                success=False,
                error=(
                    "edit_decisions.metadata.title must be a string "
                    "for scaffold_workspace"
                ),
            )

        fps_input = inputs.get("fps", 30)
        allowed_fps = self.input_schema["properties"]["fps"]["enum"]
        if fps_input not in allowed_fps:
            return ToolResult(
                success=False,
                error=(
                    f"Invalid fps {fps_input!r}; expected one of "
                    f"{', '.join(str(fps) for fps in allowed_fps)}."
                ),
            )

        if (
            self._contains_cjk(edit_decisions)
            and self._find_cjk_font_source(workspace) is None
        ):
            return ToolResult(
                success=False,
                error=(
                    "CJK text detected in HyperFrames edit_decisions, but "
                    f"{_CJK_FONT_FILENAME} was not found under the project, "
                    f"workspace, or ~/.fonts. Add projects/<project-id>/fonts/"
                    f"{_CJK_FONT_FILENAME} before scaffolding to avoid missing "
                    "Chinese glyphs."
                ),
            )

        try:
            width, height, fps = self._resolve_dimensions(profile_name, fps_input)
        except ValueError as exc:
            return ToolResult(success=False, error=str(exc))

        workspace.mkdir(parents=True, exist_ok=True)
        (workspace / "compositions").mkdir(exist_ok=True)
        assets_dir = workspace / "assets"
        assets_dir.mkdir(exist_ok=True)

        # Resolve asset IDs → file paths + copy into workspace.
        resolved_cuts, asset_copies = self._resolve_and_stage_assets(
            cuts,
            assets,
            workspace,
        )

        font_assets = self._stage_cjk_fonts_if_needed(edit_decisions, workspace)

        audio_refs, audio_assets = self._resolve_audio_refs(
            audio,
            assets,
            workspace,
        )

        # Style bridge: playbook → CSS custom properties + DESIGN.md.
        css_vars, design_md = self._style_bridge(playbook, edit_decisions)

        # Write hyperframes.json (registry config).
        (workspace / "hyperframes.json").write_text(
            json.dumps(
                {
                    "registry": "https://raw.githubusercontent.com/heygen-com/hyperframes/main/registry",
                    "paths": {
                        "blocks": "compositions",
                        "components": "compositions/components",
                        "assets": "assets",
                    },
                },
                indent=2,
                allow_nan=False,
            ),
            encoding="utf-8",
        )

        # Write DESIGN.md (convenience file for human review + workspace context).
        if design_md:
            (workspace / "DESIGN.md").write_text(design_md, encoding="utf-8")

        # Write index.html — the main composition.
        total_duration = self._compute_total_duration(resolved_cuts)
        html = self._generate_index_html(
            cuts=resolved_cuts,
            audio_refs=audio_refs,
            width=width,
            height=height,
            total_duration=total_duration,
            css_vars=css_vars,
            font_assets=font_assets,
            font_face_css=self._font_face_css(font_assets),
            title=metadata.get("title")
            or f"Video Production Buddy {edit_decisions.get('renderer_family', 'composition')}",
        )
        (workspace / "index.html").write_text(html, encoding="utf-8")

        return ToolResult(
            success=True,
            data={
                "operation": "scaffold_workspace",
                "workspace": str(workspace),
                "workspace_path": str(workspace),
                "width": width,
                "height": height,
                "fps": fps,
                "total_duration_seconds": total_duration,
                "cut_count": len(resolved_cuts),
                "asset_copies": asset_copies,
                "audio_assets": audio_assets,
                "font_assets": font_assets,
            },
            artifacts=[str(workspace / "index.html")],
        )

    def _lint(self, inputs: dict[str, Any]) -> ToolResult:
        workspace = self._require_workspace(inputs)
        if not (workspace / "index.html").exists():
            return ToolResult(
                success=False,
                error=f"No index.html in {workspace}. Run scaffold_workspace first.",
            )
        proc = self._run_hf(["lint", "--json"], cwd=workspace, timeout=120, check=False)
        data: dict[str, Any] = {
            "workspace_path": str(workspace),
            "exit_code": proc.returncode,
        }
        payload = self._parse_json_output(proc.stdout)
        if payload is not None:
            data["report"] = payload
        else:
            data["stdout_tail"] = (proc.stdout or "")[-4000:]
        data["stderr_tail"] = (proc.stderr or "")[-2000:]
        ok = proc.returncode == 0
        return ToolResult(
            success=ok,
            data=data,
            error=None if ok else f"hyperframes lint exit {proc.returncode}",
        )

    def _validate(self, inputs: dict[str, Any]) -> ToolResult:
        if "skip_contrast" in inputs and not isinstance(inputs["skip_contrast"], bool):
            return ToolResult(
                success=False,
                error=(
                    f"Invalid skip_contrast {inputs['skip_contrast']!r}; "
                    "expected a boolean."
                ),
            )

        workspace = self._require_workspace(inputs)
        if not (workspace / "index.html").exists():
            return ToolResult(
                success=False,
                error=f"No index.html in {workspace}. Run scaffold_workspace first.",
            )
        args = ["validate", "--json"]
        if inputs.get("skip_contrast"):
            args.append("--no-contrast")
        proc = self._run_hf(args, cwd=workspace, timeout=300, check=False)
        data: dict[str, Any] = {
            "workspace_path": str(workspace),
            "exit_code": proc.returncode,
        }
        payload = self._parse_json_output(proc.stdout)
        if payload is not None:
            data["report"] = payload
        else:
            data["stdout_tail"] = (proc.stdout or "")[-4000:]
        data["stderr_tail"] = (proc.stderr or "")[-2000:]
        ok = proc.returncode == 0
        return ToolResult(
            success=ok,
            data=data,
            error=None if ok else f"hyperframes validate exit {proc.returncode}",
        )

    def _add_block(self, inputs: dict[str, Any]) -> ToolResult:
        """Install a registry block or component via `hyperframes add`.

        Blocks are standalone sub-compositions (own dimensions, duration, timeline)
        that land at `compositions/<name>.html`. Components are effect snippets
        that land at `compositions/components/<name>.html`. After install, the
        caller is responsible for wiring the block into `index.html` via
        `data-composition-src` or pasting the component's snippet — see
        `.agents/skills/hyperframes-registry/SKILL.md`.
        """
        workspace = self._require_workspace(inputs)
        raw_block = inputs.get("block_name")
        if raw_block is not None and not isinstance(raw_block, str):
            return ToolResult(
                success=False,
                error="block_name must be a string for operation='add_block'",
            )
        block = (raw_block or "").strip()
        if not block:
            return ToolResult(
                success=False,
                error="block_name is required for operation='add_block'",
            )
        if not workspace.exists():
            return ToolResult(
                success=False,
                error=(
                    f"Workspace {workspace} does not exist. Run "
                    "operation='scaffold_workspace' first."
                ),
            )
        args = ["add", block, "--json", "--no-clipboard"]
        proc = self._run_hf(args, cwd=workspace, timeout=300, check=False)
        data: dict[str, Any] = {
            "operation": "add_block",
            "block_name": block,
            "workspace": str(workspace),
            "workspace_path": str(workspace),
            "exit_code": proc.returncode,
        }
        payload = self._parse_json_output(proc.stdout)
        if payload is not None:
            data["report"] = payload
        else:
            data["stdout_tail"] = (proc.stdout or "")[-4000:]
        data["stderr_tail"] = (proc.stderr or "")[-2000:]
        ok = proc.returncode == 0
        return ToolResult(
            success=ok,
            data=data,
            error=None if ok else f"hyperframes add {block} exit {proc.returncode}",
        )

    def _render(self, inputs: dict[str, Any]) -> ToolResult:
        """Full pipeline: scaffold → lint → validate → render."""
        output_path, output_error = require_explicit_output_path(
            inputs,
            self.name,
            artifact_label="HyperFrames render",
        )
        if output_error:
            return output_error

        quality = inputs.get("quality", "standard")
        allowed_qualities = self.input_schema["properties"]["quality"]["enum"]
        if quality not in allowed_qualities:
            return ToolResult(
                success=False,
                error=(
                    f"Invalid quality {quality!r}; expected one of "
                    f"{', '.join(allowed_qualities)}."
                ),
            )

        fps_input = inputs.get("fps", 30)
        allowed_fps = self.input_schema["properties"]["fps"]["enum"]
        if fps_input not in allowed_fps:
            return ToolResult(
                success=False,
                error=(
                    f"Invalid fps {fps_input!r}; expected one of "
                    f"{', '.join(str(fps) for fps in allowed_fps)}."
                ),
            )

        if "workers" in inputs:
            workers_input = inputs["workers"]
            if isinstance(workers_input, bool) or not isinstance(workers_input, int):
                return ToolResult(
                    success=False,
                    error=f"Invalid workers {workers_input!r}; expected an integer >= 1.",
                )
            workers_value = workers_input
            workers_minimum = self.input_schema["properties"]["workers"]["minimum"]
            if workers_value < workers_minimum:
                return ToolResult(
                    success=False,
                    error=(
                        f"Invalid workers {workers_input!r}; expected an integer "
                        f">= {workers_minimum}."
                    ),
                )

        if "strict" in inputs and not isinstance(inputs["strict"], bool):
            return ToolResult(
                success=False,
                error=f"Invalid strict {inputs['strict']!r}; expected a boolean.",
            )
        if "skip_contrast" in inputs and not isinstance(inputs["skip_contrast"], bool):
            return ToolResult(
                success=False,
                error=(
                    f"Invalid skip_contrast {inputs['skip_contrast']!r}; "
                    "expected a boolean."
                ),
            )

        try:
            width, height, fps = self._resolve_dimensions(
                inputs.get("profile"), fps_input
            )
        except ValueError as exc:
            return ToolResult(success=False, error=str(exc))

        runtime_ok = self._runtime_check()
        if not runtime_ok["runtime_available"]:
            return ToolResult(
                success=False,
                error=(
                    "HyperFrames runtime not available: "
                    + "; ".join(runtime_ok["reasons"])
                    + ". Per governance, this is a blocker — do NOT silently "
                    "fall back to another runtime without user approval."
                ),
                data={"runtime_check": runtime_ok},
            )

        workspace = self._require_workspace(inputs)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        steps: dict[str, Any] = {}

        # 1. Scaffold — generate HTML/CSS/assets.
        scaffold = self._scaffold(inputs)
        steps["scaffold"] = scaffold.data
        if not scaffold.success:
            return ToolResult(
                success=False,
                error=f"Scaffold failed: {scaffold.error}",
                data={"steps": steps},
            )

        # 2. Lint — static contract checks.
        lint = self._lint({"workspace_path": str(workspace)})
        steps["lint"] = lint.data
        if not lint.success:
            if inputs.get("strict", False):
                return ToolResult(
                    success=False,
                    error=f"Lint failed (strict mode): {lint.error}",
                    data={"steps": steps},
                )
            log.warning("hyperframes lint reported issues (non-strict mode, continuing)")

        # 3. Validate — browser-based contract + contrast.
        validate = self._validate(
            {
                "workspace_path": str(workspace),
                "skip_contrast": inputs.get("skip_contrast", False),
            }
        )
        steps["validate"] = validate.data
        if not validate.success:
            return ToolResult(
                success=False,
                error=(
                    f"Validate failed: {validate.error}. HyperFrames render "
                    f"is blocked — fix the composition and re-run."
                ),
                data={"steps": steps},
            )

        # 4. Render.
        effective_workers = self._effective_workers(inputs)
        cli_output_path = (
            output_path if output_path.is_absolute() else output_path.resolve(strict=False)
        )
        args = [
            "render",
            "--output", str(cli_output_path),
            "--fps", str(fps),
            "--quality", quality,
        ]
        if inputs.get("strict", False):
            args.append("--strict")
        if effective_workers is not None:
            args += ["--workers", str(effective_workers)]
        proc = self._run_hf(args, cwd=workspace, timeout=1800, check=False)
        steps["render"] = {
            "exit_code": proc.returncode,
            "cli_output_path": str(cli_output_path),
            "stdout_tail": (proc.stdout or "")[-4000:],
            "stderr_tail": (proc.stderr or "")[-4000:],
            "workers": effective_workers,
        }
        if proc.returncode != 0:
            return ToolResult(
                success=False,
                error=f"hyperframes render exit {proc.returncode}",
                data={"steps": steps},
            )

        if not output_path.exists():
            return ToolResult(
                success=False,
                error=(
                    f"hyperframes render exited 0 but output file missing: "
                    f"{output_path}. CLI output path was {cli_output_path}."
                ),
                data={"steps": steps},
            )

        return ToolResult(
            success=True,
            data={
                "operation": "render",
                "output": str(output_path),
                "output_path": str(output_path),
                "workspace": str(workspace),
                "workspace_path": str(workspace),
                "width": width,
                "height": height,
                "fps": fps,
                "quality": quality,
                "workers": effective_workers,
                "steps": steps,
            },
            artifacts=[str(output_path)],
        )

    # ------------------------------------------------------------------
    # Workspace generation helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _require_workspace(inputs: dict[str, Any]) -> Path:
        raw = inputs.get("workspace_path")
        if not raw:
            raise ValueError("workspace_path is required for this operation")
        return Path(raw).resolve()

    @staticmethod
    def _resolve_dimensions(
        profile_name: Optional[str], fps_in: int
    ) -> tuple[int, int, int]:
        """Resolve output dimensions from the media profile, with a safe default."""
        if profile_name:
            try:
                from lib.media_profiles import get_profile  # type: ignore
            except ImportError:
                return 1920, 1080, int(fps_in)
            p = get_profile(profile_name)
            return int(p.width), int(p.height), int(p.fps)
        return 1920, 1080, int(fps_in)

    @staticmethod
    def _compute_total_duration(cuts: list[dict]) -> float:
        if not cuts:
            return 0.0
        return max(float(c.get("out_seconds", 0) or 0) for c in cuts)

    def _resolve_and_stage_assets(
        self,
        cuts: list[dict],
        assets: list[dict],
        workspace: Path,
    ) -> tuple[list[dict], list[dict[str, Any]]]:
        """Resolve asset IDs in cuts[].source, copy files into workspace/assets/.

        HyperFrames resolves `src=` relative to the composition HTML file, so
        every asset must live inside the workspace tree. Copying is simpler
        (and portable) than symlinking, at the cost of disk space — these
        are regenerable under `projects/`.
        """
        asset_lookup = {a["id"]: a for a in assets if "id" in a}
        assets_dir = workspace / "assets"
        copies: list[dict[str, Any]] = []
        resolved: list[dict] = []
        staged_by_source: dict[Path, tuple[Path, dict[str, Any]]] = {}
        used_destinations: set[Path] = set()
        for cut in cuts:
            source = cut.get("source", "")
            resolved_cut = dict(cut)
            if source in asset_lookup:
                resolved_cut["source"] = asset_lookup[source].get("path", source)
            src_path = Path(resolved_cut["source"]) if resolved_cut.get("source") else None
            if src_path and src_path.exists() and not self._is_inside(src_path, workspace):
                source_key = src_path.resolve(strict=False)
                if source_key in staged_by_source:
                    dest, report = staged_by_source[source_key]
                else:
                    dest, report = self._stage_external_asset(
                        src_path,
                        assets_dir,
                        used_destinations=used_destinations,
                    )
                    staged_by_source[source_key] = (dest, report)
                    copies.append(report)
                resolved_cut["source"] = str(dest)
            resolved.append(resolved_cut)
        return resolved, copies

    def _stage_external_asset(
        self,
        src_path: Path,
        assets_dir: Path,
        *,
        used_destinations: Optional[set[Path]] = None,
    ) -> tuple[Path, dict[str, Any]]:
        """Copy or prepare an external asset for HyperFrames workspace use."""
        assets_dir.mkdir(parents=True, exist_ok=True)

        if src_path.suffix.lower() in _VIDEO_EXTENSIONS and self._needs_dense_keyframes(
            src_path
        ):
            dest = self._asset_destination(
                src_path,
                assets_dir,
                used_destinations=used_destinations,
                staged_name=f"{src_path.stem}.dense.mp4",
            )
            if not dest.exists() or dest.stat().st_mtime < src_path.stat().st_mtime:
                self._reencode_video_dense_keyframes(src_path, dest)
            return dest, {
                "from": str(src_path),
                "to": str(dest),
                "transform": "dense_keyframes",
                "keyframe_interval_threshold_seconds": _DENSE_KEYFRAME_THRESHOLD_SECONDS,
            }

        dest = self._asset_destination(
            src_path,
            assets_dir,
            used_destinations=used_destinations,
        )
        if not dest.exists() or dest.stat().st_size != src_path.stat().st_size:
            shutil.copy2(src_path, dest)
        return dest, {"from": str(src_path), "to": str(dest)}

    @staticmethod
    def _asset_destination(
        src_path: Path,
        assets_dir: Path,
        *,
        used_destinations: Optional[set[Path]] = None,
        staged_name: Optional[str] = None,
    ) -> Path:
        candidate = assets_dir / (staged_name or src_path.name)
        if used_destinations is None:
            return candidate
        if candidate not in used_destinations:
            used_destinations.add(candidate)
            return candidate

        stem = re.sub(r"[^A-Za-z0-9_.-]+", "-", candidate.stem).strip("-") or "asset"
        suffix = candidate.suffix
        digest = hashlib.sha1(
            str(src_path.resolve(strict=False)).encode("utf-8")
        ).hexdigest()[:8]
        unique = assets_dir / f"{stem}-{digest}{suffix}"
        counter = 2
        while unique in used_destinations:
            unique = assets_dir / f"{stem}-{digest}-{counter}{suffix}"
            counter += 1
        used_destinations.add(unique)
        return unique

    def _needs_dense_keyframes(self, src_path: Path) -> bool:
        max_interval = self._max_keyframe_interval_seconds(src_path)
        return (
            max_interval is not None
            and max_interval > _DENSE_KEYFRAME_THRESHOLD_SECONDS
        )

    @staticmethod
    def _max_keyframe_interval_seconds(src_path: Path) -> Optional[float]:
        ffprobe = shutil.which("ffprobe")
        if not ffprobe:
            log.warning(
                "ffprobe not found; skipping HyperFrames dense-keyframe check for %s",
                src_path,
            )
            return None

        try:
            proc = subprocess.run(
                [
                    ffprobe,
                    "-v",
                    "error",
                    "-select_streams",
                    "v:0",
                    "-skip_frame",
                    "nokey",
                    "-show_entries",
                    "frame=best_effort_timestamp_time,pkt_pts_time",
                    "-of",
                    "csv=p=0",
                    str(src_path),
                ],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            return None

        if proc.returncode != 0:
            return None

        timestamps: list[float] = []
        for line in (proc.stdout or "").splitlines():
            for raw in line.replace(",", " ").split():
                try:
                    timestamps.append(float(raw))
                    break
                except ValueError:
                    continue

        timestamps = sorted(set(timestamps))
        duration = HyperFramesCompose._video_duration_seconds(src_path)

        intervals: list[float] = []
        if len(timestamps) >= 2:
            intervals.extend(b - a for a, b in zip(timestamps, timestamps[1:]))

        if duration is not None:
            if timestamps:
                intervals.append(max(0.0, timestamps[0]))
                intervals.append(max(0.0, duration - timestamps[-1]))
            else:
                intervals.append(duration)

        if intervals:
            return max(intervals)
        return None

    @staticmethod
    def _video_duration_seconds(src_path: Path) -> Optional[float]:
        ffprobe = shutil.which("ffprobe")
        if not ffprobe:
            return None

        try:
            proc = subprocess.run(
                [
                    ffprobe,
                    "-v",
                    "error",
                    "-show_entries",
                    "format=duration",
                    "-of",
                    "default=noprint_wrappers=1:nokey=1",
                    str(src_path),
                ],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            return None

        if proc.returncode != 0:
            return None

        try:
            duration = float((proc.stdout or "").strip().splitlines()[0])
        except (IndexError, ValueError):
            return None
        return duration if duration >= 0 else None

    @staticmethod
    def _reencode_video_dense_keyframes(src_path: Path, dest: Path) -> None:
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            raise RuntimeError("ffmpeg not found; cannot prepare dense-keyframe video")

        tmp = dest.with_name(f"{dest.stem}.tmp{dest.suffix}")
        tmp.unlink(missing_ok=True)
        cmd = [
            ffmpeg,
            "-y",
            "-i",
            str(src_path),
            "-map",
            "0:v:0",
            "-map",
            "0:a?",
            "-c:v",
            "libx264",
            "-r",
            "30",
            "-g",
            "30",
            "-keyint_min",
            "30",
            "-sc_threshold",
            "0",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            "-c:a",
            "copy",
            str(tmp),
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
        if proc.returncode != 0:
            tmp.unlink(missing_ok=True)
            tail = ((proc.stderr or proc.stdout) or "")[-1200:]
            raise RuntimeError(
                f"ffmpeg dense-keyframe preparation failed for {src_path}: {tail}"
            )
        tmp.replace(dest)

    def _stage_cjk_fonts_if_needed(
        self,
        edit_decisions: dict[str, Any],
        workspace: Path,
    ) -> list[dict[str, str]]:
        """Package a local CJK font when generated HTML contains CJK text."""
        if not self._contains_cjk(edit_decisions):
            return []

        source = self._find_cjk_font_source(workspace)
        if source is None:
            raise FileNotFoundError(
                "CJK text detected in HyperFrames edit_decisions, but "
                f"{_CJK_FONT_FILENAME} was not found under the project, "
                f"workspace, or ~/.fonts. Add projects/<project-id>/fonts/"
                f"{_CJK_FONT_FILENAME} before scaffolding to avoid missing "
                "Chinese glyphs."
            )

        assets_dir = workspace / "assets"
        assets_dir.mkdir(parents=True, exist_ok=True)
        dest = assets_dir / _CJK_FONT_FILENAME
        if not dest.exists() or dest.stat().st_size != source.stat().st_size:
            shutil.copy2(source, dest)

        return [
            {
                "family": _CJK_FONT_FAMILY,
                "from": str(source),
                "to": str(dest),
                "src": self._rel_from_workspace(str(dest)),
                "format": "truetype",
            }
        ]

    @classmethod
    def _contains_cjk(cls, value: Any) -> bool:
        if isinstance(value, str):
            return bool(_CJK_CHAR_RE.search(value))
        if isinstance(value, dict):
            return any(cls._contains_cjk(v) for v in value.values())
        if isinstance(value, list):
            return any(cls._contains_cjk(v) for v in value)
        return False

    @staticmethod
    def _find_cjk_font_source(workspace: Path) -> Optional[Path]:
        search_roots = [workspace, *workspace.parents]
        for root in search_roots:
            for candidate in (
                root / "fonts" / _CJK_FONT_FILENAME,
                root / "assets" / _CJK_FONT_FILENAME,
            ):
                if candidate.exists():
                    return candidate

        home_font = Path.home() / ".fonts" / _CJK_FONT_FILENAME
        if home_font.exists():
            return home_font
        return None

    @staticmethod
    def _font_face_css(font_assets: list[dict[str, str]]) -> str:
        blocks: list[str] = []
        for asset in font_assets:
            family = HyperFramesCompose._escape_text(asset["family"])
            src = HyperFramesCompose._escape_attr(asset["src"])
            fmt = HyperFramesCompose._escape_attr(asset.get("format", "truetype"))
            blocks.append(
                "@font-face {\n"
                f"      font-family: \"{family}\";\n"
                f"      src: url(\"{src}\") format(\"{fmt}\");\n"
                "      font-weight: 100 900;\n"
                "      font-style: normal;\n"
                "      font-display: swap;\n"
                "    }"
            )
        return "\n    ".join(blocks)

    @classmethod
    def _font_family_css(
        cls,
        requested: Any,
        font_assets: list[dict[str, str]],
    ) -> str:
        requested_family = cls._primary_font_family(requested)
        declared_fonts = {
            str(asset.get("family") or "").strip().casefold(): str(asset.get("family"))
            for asset in font_assets
            if str(asset.get("family") or "").strip()
        }
        requested_key = requested_family.casefold()

        if requested_key in declared_fonts:
            families = [declared_fonts[requested_key]]
        else:
            families = [
                _HYPERFRAMES_AUTO_RESOLVED_FONTS.get(requested_key, "Inter")
            ]

        seen = {family.casefold() for family in families}
        for family in declared_fonts.values():
            family_key = family.casefold()
            if family_key not in seen:
                families.append(family)
                seen.add(family_key)

        family_css = ", ".join(cls._quote_font_family(family) for family in families)
        return f"{family_css}, sans-serif"

    @staticmethod
    def _primary_font_family(value: Any) -> str:
        raw = str(value or "").split(",", 1)[0].strip()
        return raw.strip("\"'") or "Inter"

    @staticmethod
    def _quote_font_family(family: str) -> str:
        if re.search(r"[^a-zA-Z0-9_-]", family):
            escaped = family.replace("\\", "\\\\").replace('"', '\\"')
            return f'"{escaped}"'
        return family

    def _effective_workers(self, inputs: dict[str, Any]) -> Optional[int]:
        if "workers" in inputs:
            return int(inputs["workers"])

        edit_decisions = inputs.get("edit_decisions") or {}
        asset_manifest = inputs.get("asset_manifest") or {}
        video_count = self._count_video_cuts(
            edit_decisions.get("cuts", []),
            asset_manifest.get("assets", []),
        )
        if video_count > 5:
            return 1
        return None

    @staticmethod
    def _count_video_cuts(cuts: list[dict], assets: list[dict]) -> int:
        asset_lookup = {a["id"]: a for a in assets if "id" in a}
        count = 0
        for cut in cuts or []:
            source = cut.get("source", "")
            if source in asset_lookup:
                source = asset_lookup[source].get("path", source)
            cut_type = (cut.get("type") or "").lower()
            ext = Path(str(source)).suffix.lower() if source else ""
            if ext in _VIDEO_EXTENSIONS or cut_type in {
                "video",
                "video_clip",
                "background_video",
                "b_roll",
                "broll",
            }:
                count += 1
        return count

    def _resolve_audio_refs(
        self,
        audio: dict[str, Any],
        assets: list[dict],
        workspace: Path,
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        """Resolve narration / music asset IDs and stage them."""
        asset_lookup = {a["id"]: a for a in assets if "id" in a}
        assets_dir = workspace / "assets"
        out: dict[str, Any] = {"narration": [], "music": None}
        audio_assets: list[dict[str, Any]] = []
        staged_by_source: dict[Path, Path] = {}
        used_destinations = (
            {path for path in assets_dir.iterdir() if path.is_file()}
            if assets_dir.exists()
            else set()
        )

        def stage_audio_source(
            src_path: Path,
            *,
            track: str,
            asset_id: Optional[str],
        ) -> Path:
            if self._is_inside(src_path, workspace):
                return src_path

            source_key = src_path.resolve(strict=False)
            if source_key in staged_by_source:
                return staged_by_source[source_key]

            assets_dir.mkdir(parents=True, exist_ok=True)
            dest = self._asset_destination(
                src_path,
                assets_dir,
                used_destinations=used_destinations,
            )
            if not dest.exists() or dest.stat().st_size != src_path.stat().st_size:
                shutil.copy2(src_path, dest)
            staged_by_source[source_key] = dest
            audio_assets.append(
                {
                    "track": track,
                    "asset_id": asset_id,
                    "from": str(src_path),
                    "to": str(dest),
                    "src": self._rel_from_workspace(str(dest)),
                }
            )
            return dest

        for seg in audio.get("narration", {}).get("segments", []) or []:
            aid = seg.get("asset_id")
            if not aid or aid not in asset_lookup:
                continue
            src = Path(asset_lookup[aid].get("path", ""))
            if not src.exists():
                continue
            dest = stage_audio_source(src, track="narration", asset_id=aid)
            out["narration"].append(
                {
                    "src": str(dest),
                    "start_seconds": float(seg.get("start_seconds", 0) or 0),
                    "end_seconds": float(seg.get("end_seconds", 0) or 0) or None,
                }
            )

        music = audio.get("music", {})
        m_id = music.get("asset_id")
        # Resolve music source: prefer asset_id lookup, fall back to direct src path.
        music_src_path: Optional[Path] = None
        if m_id and m_id in asset_lookup:
            music_src_path = Path(asset_lookup[m_id].get("path", ""))
        elif music.get("src"):
            music_src_path = Path(music["src"])
        if music_src_path and music_src_path.exists():
            dest = stage_audio_source(music_src_path, track="music", asset_id=m_id)
            fade_in = float(
                music.get("fade_in_seconds") or music.get("fadeInSeconds") or 0
            )
            fade_out = float(
                music.get("fade_out_seconds") or music.get("fadeOutSeconds") or 0
            )
            out["music"] = {
                "src": str(dest),
                "volume": float(music.get("volume", 0.15) or 0.15),
                "fade_in_seconds": fade_in,
                "fade_out_seconds": fade_out,
            }
        elif music or m_id:
            log.warning(
                "HyperFrames compose: music asset not found at %s — "
                "proceeding without music track.",
                music_src_path,
            )

        return out, audio_assets

    @staticmethod
    def _is_inside(path: Path, root: Path) -> bool:
        try:
            path.resolve().relative_to(root.resolve())
            return True
        except ValueError:
            return False

    def _style_bridge(
        self,
        playbook: dict[str, Any],
        edit_decisions: dict[str, Any],
    ) -> tuple[dict[str, str], str]:
        """Bridge Video Production Buddy playbook → HyperFrames CSS vars + DESIGN.md.

        Delegates to `lib/hyperframes_style_bridge.py` so the logic is
        shareable and testable. Falls back to a safe built-in default when
        the bridge module isn't available.
        """
        try:
            from lib.hyperframes_style_bridge import style_bridge  # type: ignore
            return style_bridge(playbook, edit_decisions)
        except Exception as e:
            log.debug("style_bridge fallback: %s", e)

        vl = (playbook or {}).get("visual_language", {})
        palette = vl.get("color_palette", {})
        typo = (playbook or {}).get("typography", {})

        def _first(raw: Any, default: str) -> str:
            if isinstance(raw, list) and raw:
                return str(raw[0])
            if isinstance(raw, str) and raw:
                return raw
            return default

        bg = _first(palette.get("background"), "#0B0F1A")
        fg = _first(palette.get("text"), "#F5F5F5")
        accent = _first(palette.get("accent"), "#F59E0B")
        primary = _first(palette.get("primary"), "#2563EB")
        heading_spec = typo.get("headings") or typo.get("heading") or {}
        body_spec = typo.get("body") or {}
        heading = heading_spec.get("font") or heading_spec.get("family") or "Inter"
        body = body_spec.get("font") or body_spec.get("family") or "Inter"

        css_vars = {
            "--color-bg": bg,
            "--color-fg": fg,
            "--color-accent": accent,
            "--color-primary": primary,
            "--font-heading": heading,
            "--font-body": body,
            "--ease-primary": "cubic-bezier(0.65, 0, 0.35, 1)",
            "--duration-entrance": "0.6s",
        }
        design_md = (
            "# DESIGN\n\n"
            "Generated by Video Production Buddy HyperFrames style bridge (fallback).\n\n"
            f"- Background: `{bg}`\n"
            f"- Foreground: `{fg}`\n"
            f"- Accent: `{accent}`\n"
            f"- Primary: `{primary}`\n"
            f"- Heading font: `{heading}`\n"
            f"- Body font: `{body}`\n"
        )
        return css_vars, design_md

    # ------------------------------------------------------------------
    # HTML generation (minimal, Phase 1)
    # ------------------------------------------------------------------

    def _generate_index_html(
        self,
        cuts: list[dict],
        audio_refs: dict[str, Any],
        width: int,
        height: int,
        total_duration: float,
        css_vars: dict[str, str],
        font_assets: list[dict[str, str]],
        font_face_css: str,
        title: str,
    ) -> str:
        """Emit a HyperFrames-contract-compliant index.html.

        Phase 1 covers the minimum required for smoke-testing the runtime:
        - still images (img.clip)
        - video clips (video.clip, muted playsinline + separate audio if needed)
        - text cards (div.clip with styled <h1>)
        - narration segments (audio)
        - music bed (audio, lower volume)

        Richer scene types (registry blocks, kinetic typography) are authored
        by the agent directly into compositions/ — this generator just
        provides a functional starting skeleton.
        """
        vars_css = "\n      ".join(f"{k}: {v};" for k, v in css_vars.items())
        body_font_family = self._font_family_css(
            css_vars.get("--font-body"), font_assets
        )
        heading_font_family = self._font_family_css(
            css_vars.get("--font-heading"), font_assets
        )

        clip_html: list[str] = []
        entrance_tweens: list[str] = []
        for i, cut in enumerate(cuts):
            html, tween = self._cut_to_html(i, cut, width, height)
            clip_html.append(html)
            if tween:
                entrance_tweens.append(tween)

        audio_html: list[str] = []
        for j, nar in enumerate(audio_refs.get("narration") or []):
            src = self._rel_from_workspace(nar["src"])
            start = nar.get("start_seconds", 0)
            end = nar.get("end_seconds")
            duration = (end - start) if end and end > start else (total_duration - start)
            audio_html.append(
                f'<audio id="nar-{j}" '
                f'data-start="{self._f(start)}" data-duration="{self._f(duration)}" '
                f'data-track-index="2" src="{self._escape_attr(src)}" '
                f'data-volume="1"></audio>'
            )

        music = audio_refs.get("music")
        if music:
            src = self._rel_from_workspace(music["src"])
            audio_html.append(
                f'<audio id="music" '
                f'data-start="0" data-duration="{self._f(total_duration)}" '
                f'data-track-index="3" src="{self._escape_attr(src)}" '
                f'data-volume="{self._f(music["volume"])}"></audio>'
            )

        tween_block = "\n        ".join(entrance_tweens) if entrance_tweens else "// no tweens"

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>{self._escape_text(title)}</title>
  <style>
    {font_face_css}
    :root {{
      {vars_css}
    }}
    body {{ margin: 0; background: var(--color-bg); color: var(--color-fg); font-family: {body_font_family}; }}
    #root {{
      position: relative;
      width: {width}px;
      height: {height}px;
      overflow: hidden;
    }}
    .clip {{ position: absolute; inset: 0; }}
    .clip.video-clip, .clip.image-clip {{ object-fit: cover; width: 100%; height: 100%; }}
    .clip.text-card {{ display: flex; align-items: center; justify-content: center; padding: 120px 160px; box-sizing: border-box; text-align: center; }}
    .clip.text-card h1 {{ font-family: {heading_font_family}; font-weight: 700; font-size: 96px; line-height: 1.1; margin: 0; color: var(--color-fg); }}
    .clip.text-card .subtitle {{ font-size: 36px; margin-top: 24px; color: var(--color-accent); }}
  </style>
  {gsap_shim_script()}
</head>
<body>
  <div id="root" data-composition-id="root" data-start="0" data-duration="{self._f(total_duration)}" data-width="{width}" data-height="{height}">
    {"".join(clip_html)}
    {"".join(audio_html)}
    <script>
      window.__timelines = window.__timelines || {{}};
      const tl = gsap.timeline({{ paused: true }});
      {tween_block}
      window.__timelines["root"] = tl;
    </script>
  </div>
</body>
</html>
"""

    def _cut_to_html(
        self, index: int, cut: dict, width: int, height: int
    ) -> tuple[str, Optional[str]]:
        """Render one cut + its entrance tween. Returns (html, tween or None)."""
        cut_id = f"cut-{index}"
        in_s = float(cut.get("in_seconds", 0) or 0)
        out_s = float(cut.get("out_seconds", 0) or 0)
        duration = max(0.1, out_s - in_s)

        source = cut.get("source") or ""
        cut_type = (cut.get("type") or "").lower()
        text = cut.get("text") or cut.get("title") or ""

        src_path = Path(source) if source else None
        ext = src_path.suffix.lower() if src_path else ""

        # Decide scene shape
        if cut_type in {"text_card", "hero_title", "callout"} or (not source and text):
            inner = f'<h1>{self._escape_text(text or f"Scene {index + 1}")}</h1>'
            subtitle = cut.get("subtitle") or cut.get("caption")
            if subtitle:
                inner += f'<div class="subtitle">{self._escape_text(subtitle)}</div>'
            html = (
                f'<div id="{cut_id}" class="clip text-card" '
                f'data-start="{self._f(in_s)}" data-duration="{self._f(duration)}" '
                f'data-track-index="1">{inner}</div>'
            )
            return html, None

        if ext in _IMAGE_EXTENSIONS and src_path:
            rel = self._rel_from_workspace(str(src_path))
            html = (
                f'<img id="{cut_id}" class="clip image-clip" '
                f'src="{self._escape_attr(rel)}" '
                f'data-start="{self._f(in_s)}" data-duration="{self._f(duration)}" '
                f'data-track-index="1" alt="">'
            )
            return html, None

        if ext in _VIDEO_EXTENSIONS and src_path:
            rel = self._rel_from_workspace(str(src_path))
            html = (
                f'<video id="{cut_id}" class="clip video-clip" '
                f'src="{self._escape_attr(rel)}" '
                f'data-start="{self._f(in_s)}" data-duration="{self._f(duration)}" '
                f'data-track-index="1" muted playsinline></video>'
            )
            return html, None

        # Unknown cut shape — render a placeholder text card so the render
        # still succeeds; lint/validate will surface the issue.
        if ext in {".html", ".htm"} and src_path:
            rel = self._rel_from_workspace(str(src_path))
            composition_id = Path(rel).stem
            html = (
                f'<div id="{cut_id}" class="clip composition-clip" '
                f'data-composition-id="{self._escape_attr(composition_id)}" '
                f'data-composition-src="{self._escape_attr(rel)}" '
                f'data-start="{self._f(in_s)}" data-duration="{self._f(duration)}" '
                f'data-width="{width}" data-height="{height}" '
                f'data-track-index="1"></div>'
            )
            return html, None

        placeholder = self._escape_text(text or cut.get("reason") or f"Scene {index + 1}")
        html = (
            f'<div id="{cut_id}" class="clip text-card" '
            f'data-start="{self._f(in_s)}" data-duration="{self._f(duration)}" '
            f'data-track-index="1"><h1>{placeholder}</h1></div>'
        )
        return html, None

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    def _run_hf(
        self,
        args: list[str],
        *,
        cwd: Optional[Path],
        timeout: int,
        check: bool,
    ) -> subprocess.CompletedProcess:
        """Invoke `npx hyperframes <args>` with the right Windows quirks.

        We intentionally bypass `self.run_command` here because we do NOT
        want to raise CalledProcessError on non-zero exits — the caller
        parses lint/validate/render exit codes itself.
        """
        cmd = ["npx", "--yes", "hyperframes", *args]
        # On Windows, resolve the .cmd wrapper so subprocess can find it
        # without shell=True.
        if os.name == "nt":
            resolved = shutil.which(cmd[0])
            if resolved:
                cmd[0] = resolved
        try:
            return subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=str(cwd) if cwd else None,
                check=False,
            )
        except subprocess.TimeoutExpired as e:
            # Surface timeouts as a failed CompletedProcess so callers get a
            # uniform shape. The stderr tail will say timeout.
            return subprocess.CompletedProcess(
                args=cmd,
                returncode=124,
                stdout=e.stdout or "",
                stderr=(e.stderr or "") + f"\n[timeout after {timeout}s]",
            )

    @staticmethod
    def _parse_json_output(stdout: str) -> Optional[Any]:
        """Parse a `--json` report, tolerating surrounding banner lines."""
        if not stdout:
            return None
        start = stdout.find("{")
        end = stdout.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return None
        try:
            return json.loads(stdout[start : end + 1])
        except json.JSONDecodeError:
            return None

    @staticmethod
    def _f(v: float) -> str:
        return f"{float(v):.3f}".rstrip("0").rstrip(".")

    @staticmethod
    def _escape_text(s: str) -> str:
        return (
            s.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )

    @staticmethod
    def _escape_attr(s: str) -> str:
        return HyperFramesCompose._escape_text(s).replace('"', "&quot;")

    @staticmethod
    def _rel_from_workspace(path: str) -> str:
        """HyperFrames resolves src= relative to index.html. Our asset files
        live under workspace/assets/, so when we stage a copy we know the
        relative path is `assets/<name>`. For files already in the workspace
        tree, fall back to the file name.
        """
        p = Path(path)
        # If it's already a relative path starting with assets/, keep as-is.
        if not p.is_absolute():
            return str(p).replace("\\", "/")
        parts = p.parts
        for anchor in ("assets", "compositions"):
            if anchor in parts:
                index = len(parts) - 1 - list(reversed(parts)).index(anchor)
                return "/".join(parts[index:])
        # Otherwise emit just the basename under assets/.
        return f"assets/{p.name}"
