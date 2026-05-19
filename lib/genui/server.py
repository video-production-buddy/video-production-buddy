"""Local GenUI form server.

This module intentionally uses only the Python standard library. The server is
project-scoped and writes ui_response only; canonical artifact writes remain an
agent responsibility.
"""

from __future__ import annotations

import argparse
import json
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from lib.genui import render_form_html, response_payload_from_submission, write_response


class GenUIRequestHandler(BaseHTTPRequestHandler):
    config: dict[str, Any]
    response_path: Path

    def _send(self, status: HTTPStatus, body: str, content_type: str) -> None:
        encoded = body.encode("utf-8")
        self.send_response(status.value)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def do_GET(self) -> None:
        if self.path not in {"/", "/form"}:
            self._send(HTTPStatus.NOT_FOUND, "Not found", "text/plain; charset=utf-8")
            return
        self._send(
            HTTPStatus.OK,
            render_form_html(self.config, submit_url="/submit"),
            "text/html; charset=utf-8",
        )

    def do_POST(self) -> None:
        if self.path != "/submit":
            self._send(HTTPStatus.NOT_FOUND, "Not found", "text/plain; charset=utf-8")
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length)
            submission = json.loads(raw.decode("utf-8"))
            response = response_payload_from_submission(self.config, submission)
            write_response(self.response_path, response)
        except Exception as exc:
            self._send(
                HTTPStatus.BAD_REQUEST,
                json.dumps({"ok": False, "error": str(exc)}),
                "application/json; charset=utf-8",
            )
            return
        self._send(
            HTTPStatus.OK,
            json.dumps({"ok": True, "response_path": str(self.response_path)}),
            "application/json; charset=utf-8",
        )
        threading.Thread(target=self.server.shutdown, daemon=True).start()

    def log_message(self, format: str, *args: Any) -> None:
        return


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config-path", required=True)
    parser.add_argument("--response-path", required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, required=True)
    args = parser.parse_args()

    with open(args.config_path) as f:
        config = json.load(f)

    handler = type(
        "BoundGenUIRequestHandler",
        (GenUIRequestHandler,),
        {
            "config": config,
            "response_path": Path(args.response_path),
        },
    )
    server = ThreadingHTTPServer((args.host, args.port), handler)
    try:
        server.serve_forever()
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
