"""Local GenUI form materialization and serving tool."""

from __future__ import annotations

import json
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any

from lib.genui import write_form_bundle
from tools.base_tool import BaseTool, ToolResult, ToolRuntime, ToolStability, ToolTier


class GenUIForm(BaseTool):
    """Materialize a project-scoped visual form and optionally serve it locally."""

    name = "genui_form"
    version = "0.1.0"
    tier = ToolTier.CORE
    stability = ToolStability.BETA
    runtime = ToolRuntime.LOCAL
    capability = "interaction"
    provider = "openmontage"
    capabilities = ["visual_form", "questionnaire", "approval_gate"]
    supports = {
        "modes": ["prepare", "serve"],
        "localhost_only": True,
        "canonical_writes": False,
        "components": [
            "text",
            "textarea",
            "select",
            "radio",
            "multiselect",
            "checkbox",
            "number",
            "file_path",
            "url",
            "approval",
            "info_card",
        ],
    }
    best_for = [
        "collecting dense requirements visually",
        "approval gates with many options",
        "reducing long CLI questionnaire fatigue",
    ]
    not_good_for = [
        "canonical artifact mutation without agent review",
        "public web hosting",
    ]
    side_effects = [
        "writes projects/<project>/artifacts/ui/<config_id>/config.json",
        "writes projects/<project>/artifacts/ui/<config_id>/form.html",
        "may start a localhost-only Python HTTP server in serve mode",
    ]
    input_schema = {
        "type": "object",
        "required": ["project_dir", "config"],
        "properties": {
            "project_dir": {"type": "string"},
            "config": {"type": "object"},
            "mode": {"type": "string", "enum": ["prepare", "serve"], "default": "serve"},
            "host": {"type": "string", "default": "127.0.0.1"},
            "port": {"type": "integer", "minimum": 0, "maximum": 65535, "default": 0},
        },
    }
    output_schema = {
        "type": "object",
        "required": ["config_id", "config_path", "html_path", "response_path", "server_state"],
        "properties": {
            "config_id": {"type": "string"},
            "config_path": {"type": "string"},
            "html_path": {"type": "string"},
            "response_path": {"type": "string"},
            "server_state": {"type": "string"},
            "url": {"type": ["string", "null"]},
            "pid": {"type": ["integer", "null"]},
        },
    }
    artifact_schema = {
        "produces": ["ui_form_config"],
        "expects_response": "ui_response",
    }
    user_visible_verification = [
        "Open the returned localhost URL and submit the form.",
        "Confirm projects/<project>/artifacts/ui/<config_id>/response.json exists before mapping to canonical artifacts.",
    ]

    def _choose_port(self, host: str) -> int:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind((host, 0))
            return int(sock.getsockname()[1])

    def _start_server(self, bundle: Any, host: str, port: int) -> subprocess.Popen:
        cmd = [
            sys.executable,
            "-m",
            "lib.genui.server",
            "--config-path",
            str(bundle.config_path),
            "--response-path",
            str(bundle.response_path),
            "--host",
            host,
            "--port",
            str(port),
        ]
        return subprocess.Popen(
            cmd,
            cwd=Path(__file__).resolve().parent.parent.parent,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )

    def _wait_until_ready(
        self,
        process: subprocess.Popen,
        host: str,
        port: int,
        *,
        timeout_seconds: float = 3.0,
    ) -> None:
        deadline = time.monotonic() + timeout_seconds
        last_error: Exception | None = None
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError(
                    "genui_form server did not become ready "
                    f"(process exited with code {process.returncode})"
                )
            try:
                with urllib.request.urlopen(f"http://{host}:{port}/", timeout=0.25) as response:
                    if response.status == 200:
                        return
            except Exception as exc:
                if process.poll() is not None:
                    raise RuntimeError(
                        "genui_form server did not become ready "
                        f"(process exited with code {process.returncode})"
                    ) from exc
                last_error = exc
                try:
                    with socket.create_connection((host, port), timeout=0.25):
                        pass
                except OSError:
                    pass
                time.sleep(0.05)
            else:
                if process.poll() is None:
                    return
        raise RuntimeError(
            "genui_form server did not become ready "
            f"on {host}:{port}: {last_error}"
        )

    def execute(self, inputs: dict[str, Any]) -> ToolResult:
        try:
            project_dir = Path(inputs["project_dir"])
            config = inputs["config"]
            mode = inputs.get("mode", "serve")
            host = inputs.get("host", "127.0.0.1")
            if host not in {"127.0.0.1", "localhost"}:
                raise ValueError("genui_form only serves localhost-bound forms")
            if mode not in {"prepare", "serve"}:
                raise ValueError("mode must be 'prepare' or 'serve'")

            bundle = write_form_bundle(project_dir, config)
            data: dict[str, Any] = {
                "config_id": config["config_id"],
                "config_path": str(bundle.config_path),
                "html_path": str(bundle.html_path),
                "response_path": str(bundle.response_path),
                "server_state": "prepared",
                "url": None,
                "pid": None,
            }

            artifacts = [str(bundle.config_path), str(bundle.html_path)]
            if mode == "serve":
                port = int(inputs.get("port") or 0)
                if port == 0:
                    port = self._choose_port(host)
                process = self._start_server(bundle, host, port)
                try:
                    self._wait_until_ready(process, host, port)
                except Exception:
                    if process.poll() is None:
                        process.terminate()
                    raise
                data.update(
                    {
                        "server_state": "running",
                        "url": f"http://{host}:{port}/",
                        "pid": process.pid,
                    }
                )
                bundle.state_path.parent.mkdir(parents=True, exist_ok=True)
                with open(bundle.state_path, "w") as f:
                    json.dump(data, f, indent=2)
                    f.write("\n")
                artifacts.append(str(bundle.state_path))

            return ToolResult(success=True, data=data, artifacts=artifacts)
        except Exception as exc:
            return ToolResult(success=False, error=str(exc))
