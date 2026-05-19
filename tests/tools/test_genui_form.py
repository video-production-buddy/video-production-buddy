from pathlib import Path
import socket
import time
import urllib.error
import urllib.request

import pytest

from schemas.artifacts import validate_artifact
from tools.tool_registry import registry


def _sample_config(project_id: str = "demo-ad") -> dict:
    return {
        "version": "1.0",
        "config_id": "cfg-demo",
        "project_id": project_id,
        "pipeline_type": "ad-video",
        "stage": "brief_enrichment",
        "gate": "G-0",
        "title": "Creative Requirements Worksheet",
        "sections": [
            {
                "id": "identity",
                "title": "Identity",
                "description": "Confirm the product identity.",
                "fields": [
                    {
                        "id": "product_model",
                        "label": "Product/model",
                        "type": "text",
                        "required": True,
                        "default": "OPPO Find X9 Pro",
                        "help_text": "<script>alert('unsafe')</script>",
                        "binding": {
                            "artifact": "enriched_brief",
                            "path": "creative_requirements.product_model.value",
                        },
                    },
                    {
                        "id": "visual_approach",
                        "label": "Visual approach",
                        "type": "radio",
                        "required": True,
                        "choices": [
                            {"value": "cinematic", "label": "Cinematic", "recommended": True},
                            {"value": "animated", "label": "Animated"},
                        ],
                    },
                    {
                        "id": "derivatives",
                        "label": "Derivative variants",
                        "type": "multiselect",
                        "choices": [
                            {"value": "9:16", "label": "9:16 vertical"},
                            {"value": "1:1", "label": "1:1 square"},
                        ],
                    },
                ],
            }
        ],
        "submit_actions": [
            {"id": "approve", "label": "Approve", "kind": "approve", "recommended": True}
        ],
    }


def test_write_form_bundle_materializes_config_html_and_response_path(tmp_path: Path):
    from lib.genui import write_form_bundle

    project_dir = tmp_path / "projects" / "demo-ad"
    bundle = write_form_bundle(project_dir, _sample_config())

    assert bundle.config_path.exists()
    assert bundle.html_path.exists()
    assert bundle.response_path.parent.exists()
    assert not bundle.response_path.exists()

    validate_artifact("ui_form_config", bundle.config)
    html = bundle.html_path.read_text()
    assert "Creative Requirements Worksheet" in html
    assert "<script>alert('unsafe')</script>" not in html
    assert "&lt;script&gt;alert(&#x27;unsafe&#x27;)&lt;/script&gt;" in html


def test_project_path_containment_rejects_parent_escape(tmp_path: Path):
    from lib.genui import resolve_project_path

    project_dir = tmp_path / "project"
    project_dir.mkdir()

    with pytest.raises(ValueError, match="outside project directory"):
        resolve_project_path(project_dir, "../escape.json")


def test_response_payload_rejects_unconfigured_submit_action():
    from lib.genui import response_payload_from_submission

    with pytest.raises(ValueError, match="not configured"):
        response_payload_from_submission(
            _sample_config(),
            {"action": "abort", "values": {"product_model": "OPPO Find X9 Pro"}},
        )


def test_response_payload_rejects_missing_required_value():
    from lib.genui import response_payload_from_submission

    with pytest.raises(ValueError, match="product_model"):
        response_payload_from_submission(
            _sample_config(),
            {"action": "approve", "values": {"product_model": ""}},
        )


def test_response_payload_rejects_unconfigured_values():
    from lib.genui import response_payload_from_submission

    with pytest.raises(ValueError, match="not configured"):
        response_payload_from_submission(
            _sample_config(),
            {
                "action": "approve",
                "values": {
                    "product_model": "OPPO Find X9 Pro",
                    "visual_approach": "cinematic",
                    "internal_override": "write enriched_brief directly",
                },
            },
        )


def test_genui_form_tool_prepare_mode_returns_reviewable_paths(tmp_path: Path):
    from tools.interaction.genui_form import GenUIForm

    project_dir = tmp_path / "projects" / "demo-ad"
    result = GenUIForm().execute(
        {
            "project_dir": str(project_dir),
            "config": _sample_config(project_id="demo-ad"),
            "mode": "prepare",
        }
    )

    assert result.success, result.error
    assert result.data["server_state"] == "prepared"
    assert result.data["url"] is None
    assert Path(result.data["config_path"]).exists()
    assert Path(result.data["html_path"]).exists()
    assert result.data["response_path"].endswith("response.json")
    assert "enriched_brief" not in [Path(p).name for p in result.artifacts]


def test_genui_form_tool_serve_mode_reports_port_conflict(tmp_path: Path):
    from tools.interaction.genui_form import GenUIForm

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        sock.listen()
        port = int(sock.getsockname()[1])
        result = GenUIForm().execute(
            {
                "project_dir": str(tmp_path / "projects" / "demo-ad"),
                "config": _sample_config(project_id="demo-ad"),
                "mode": "serve",
                "port": port,
            }
        )

    assert not result.success
    assert "ready" in (result.error or "")


def test_genui_form_server_stops_after_successful_submission(tmp_path: Path):
    from tools.interaction.genui_form import GenUIForm

    result = GenUIForm().execute(
        {
            "project_dir": str(tmp_path / "projects" / "demo-ad"),
            "config": _sample_config(project_id="demo-ad"),
            "mode": "serve",
        }
    )

    assert result.success, result.error
    url = result.data["url"]
    submit_url = f"{url.rstrip('/')}/submit"
    payload = (
        b'{"action":"approve","values":{'
        b'"product_model":"OPPO Find X9 Pro",'
        b'"visual_approach":"cinematic",'
        b'"derivatives":["9:16"]'
        b"}}"
    )
    request = urllib.request.Request(
        submit_url,
        data=payload,
        method="POST",
        headers={"Content-Type": "application/json"},
    )

    with urllib.request.urlopen(request, timeout=2.0) as response:
        assert response.status == 200

    deadline = time.monotonic() + 3.0
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            urllib.request.urlopen(url, timeout=0.2).close()
        except (OSError, urllib.error.URLError) as exc:
            last_error = exc
            break
        time.sleep(0.05)

    assert last_error is not None, "GenUI server still accepted requests after submission"


def test_tool_registry_discovers_genui_form():
    registry.clear()
    registry.discover()

    tool = registry.get("genui_form")
    assert tool is not None
    info = tool.get_info()
    assert info["capability"] == "interaction"
    assert info["provider"] == "openmontage"
    assert info["runtime"] == "local"
