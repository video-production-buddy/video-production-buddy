"""Shared local runtime helpers for GenUI browser serving."""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path
from typing import Any

from lib.genui import is_wsl2


class LocalGenUIServerRuntime:
    """Browser/server helpers shared by localhost GenUI interaction tools."""

    def _write_strict_json_file(self, path: Path, payload: dict[str, Any]) -> None:
        try:
            serialized = json.dumps(payload, indent=2, allow_nan=False)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"GenUI state must be strict JSON serializable: {exc}") from exc
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            f.write(serialized)
            f.write("\n")

    def _try_open_browser(self, url: str) -> bool:
        import webbrowser

        allow_browser_open = os.environ.get("VPB_ALLOW_BROWSER_OPEN")
        if os.environ.get("PYTEST_CURRENT_TEST"):
            return False
        if str(allow_browser_open).strip().lower() in {"0", "false", "no", "off"}:
            return False

        if is_wsl2():
            try:
                windows_url = url.replace("127.0.0.1", "localhost", 1)
                completed = subprocess.run(
                    ["cmd.exe", "/c", "start", windows_url],
                    check=False,
                    capture_output=True,
                    timeout=5,
                )
                return completed.returncode == 0
            except (FileNotFoundError, subprocess.TimeoutExpired):
                return False
        return webbrowser.open(url)

    def _choose_port(self, host: str) -> int:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind((host, 0))
            return int(sock.getsockname()[1])

    def _start_server(self, bundle: Any, host: str, port: int, submit_nonce: str) -> subprocess.Popen:
        cmd = [
            sys.executable,
            "-m",
            "lib.genui.server",
            "--config-path",
            str(bundle.config_path),
            "--response-path",
            str(bundle.response_path),
            "--view-spec-path",
            str(bundle.view_spec_path),
            f"--submit-nonce={submit_nonce}",
            "--host",
            host,
            "--port",
            str(port),
        ]
        stderr_log = tempfile.TemporaryFile(
            mode="w+",
            encoding="utf-8",
            errors="replace",
        )
        try:
            process = subprocess.Popen(
                cmd,
                cwd=Path(__file__).resolve().parent.parent.parent,
                stdout=subprocess.DEVNULL,
                stderr=stderr_log,
                start_new_session=True,
            )
        except Exception:
            stderr_log.close()
            raise
        setattr(process, "_genui_stderr_log", stderr_log)
        return process

    def _read_startup_stderr(self, process: subprocess.Popen, *, limit: int = 4000) -> str:
        stderr = getattr(process, "_genui_stderr_log", None)
        if stderr is None:
            stderr = getattr(process, "stderr", None)
        if stderr is None:
            return ""
        try:
            flush = getattr(stderr, "flush", None)
            if callable(flush):
                flush()
            seekable = getattr(stderr, "seekable", None)
            if callable(seekable) and seekable():
                stderr.seek(0)
            raw = stderr.read()
        except Exception:
            return ""
        if isinstance(raw, bytes):
            text = raw.decode("utf-8", errors="replace")
        else:
            text = str(raw or "")
        return text.strip()[-limit:]

    def _server_exit_detail(self, process: subprocess.Popen) -> str:
        detail = f"process exited with code {process.returncode}"
        stderr = self._read_startup_stderr(process)
        if stderr:
            detail = f"{detail}; stderr: {stderr}"
        return detail

    def _wait_until_ready(
        self,
        process: subprocess.Popen,
        host: str,
        port: int,
        *,
        timeout_seconds: float = 10.0,
        probe_timeout_seconds: float = 1.0,
    ) -> None:
        deadline = time.monotonic() + timeout_seconds
        last_error: Exception | None = None
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError(
                    "GenUI browser server did not become ready "
                    f"({self._server_exit_detail(process)})"
                )
            try:
                with urllib.request.urlopen(
                    f"http://{host}:{port}/spec.json",
                    timeout=probe_timeout_seconds,
                ) as response:
                    if response.status == 200:
                        return
                    last_error = RuntimeError(f"unexpected HTTP status {response.status}")
            except Exception as exc:
                if process.poll() is not None:
                    raise RuntimeError(
                        "GenUI browser server did not become ready "
                        f"({self._server_exit_detail(process)})"
                    ) from exc
                last_error = exc
                time.sleep(0.1)
            else:
                if process.poll() is None:
                    return
        raise RuntimeError(
            "GenUI browser server did not become ready "
            f"on {host}:{port}: {last_error}"
        )
