import json
import math
from pathlib import Path
import subprocess

import jsonschema
import pytest

from schemas.artifacts import ARTIFACT_NAMES, validate_artifact


ROOT = Path(__file__).resolve().parent.parent.parent


def _write_sample_clip(project_dir: Path, rel: str = "renders/sample_clip.mp4") -> Path:
    path = project_dir / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"sample")
    return path


def _media_review_request() -> dict:
    return {
        "request_id": "asset-sample-review",
        "project_id": "demo-ad",
        "pipeline_type": "ad-video",
        "stage": "assets",
        "gate": "sample_review",
        "title": "Review generated product sample",
        "prompt": "Review the sample clip and capture exact timecoded revisions before approving.",
        "interaction_kind": "media_review",
        "capabilities_needed": [
            "media_review",
            "visual_demonstration",
            "structured_revision_capture",
        ],
        "media_items": [
            {
                "id": "sample_clip",
                "title": "Sample clip",
                "kind": "video",
                "path": "/media/renders/sample_clip.mp4",
                "alt": "Generated sample clip for approval",
            }
        ],
        "review_items": [
            {
                "scene_id": "scene_01",
                "label": "Opening hero product shot",
                "start_seconds": 0,
                "end_seconds": 4.5,
            }
        ],
        "fields": [
            {
                "id": "product_fidelity_notes",
                "label": "Product fidelity notes",
                "type": "textarea",
                "required": False,
                "binding": {
                    "artifact": "asset_manifest",
                    "path": "human_feedback.product_fidelity_notes",
                },
            }
        ],
    }


def _gate_workspace_request() -> dict:
    return {
        "request_id": "proposal-lock",
        "project_id": "demo-ad",
        "pipeline_type": "ad-video",
        "stage": "proposal",
        "gate": "proposal_lock",
        "title": "Lock the production proposal",
        "prompt": "Review the recommended creative plan and approve before script work starts.",
        "interaction_kind": "approval",
        "capabilities_needed": [
            "structured_revision_capture",
            "multi_axis_selection",
        ],
        "fields": [
            {
                "id": "approval_notes",
                "label": "Approval notes",
                "type": "textarea",
                "required": False,
                "binding": {
                    "artifact": "production_proposal",
                    "path": "human_feedback.approval_notes",
                },
            }
        ],
    }


def _option_revision_request() -> dict:
    request = _gate_workspace_request()
    request.update(
        {
            "request_id": "proposal-options",
            "interaction_kind": "option_comparison",
            "capabilities_needed": [
                "side_by_side_comparison",
                "multi_axis_selection",
                "structured_revision_capture",
            ],
            "selection_field_id": "selected_runtime",
            "selection_label": "Render runtime",
            "selection_binding": {
                "artifact": "production_proposal",
                "path": "render_runtime_selection.selected_runtime",
            },
            "choices": [
                {
                    "value": "remotion",
                    "label": "Remotion",
                    "description": "Best for precise browser-rendered motion graphics.",
                    "recommended": True,
                },
                {
                    "value": "hyperframes",
                    "label": "HyperFrames",
                    "description": "Best for timeline-driven composition.",
                },
                {
                    "value": "ffmpeg",
                    "label": "FFmpeg",
                    "description": "Best for simple deterministic assembly.",
                },
            ],
        }
    )
    return request


def _session_config() -> dict:
    return {
        "contract": "genui_session",
        "session_id": "asset-sample-review",
        "project_id": "demo-ad",
        "pipeline_type": "ad-video",
        "stage": "assets",
        "gate": "sample_review",
        "mode": "media_review_room",
        "title": "Review generated product sample",
        "description": "Use timecoded notes and issue IDs for sample approval.",
        "framework": {
            "name": "a2ui",
            "renderer": "@copilotkit/a2ui-renderer",
            "packages": ["@a2ui/react", "@a2ui/web_core", "@copilotkit/a2ui-renderer"],
        },
        "transport": {
            "name": "ag-ui",
            "thread_id": "demo-ad",
            "run_id": "asset-sample-review",
        },
        "visual_need_assessment": {
            "recommended_mode": "media_review_room",
            "recommended_tool": "genui_session",
            "linear_chat_sufficient": False,
            "reasons": ["media_review", "visual_demonstration"],
            "required_ui_primitives": ["media_player", "timecoded_annotation", "issue_tracker"],
            "confidence": 0.95,
            "fallback": "cli_only_when_browser_fails_or_user_declines",
        },
        "media_refs": [
            {
                "id": "sample_clip",
                "kind": "video",
                "title": "Sample clip",
                "path": "/media/renders/sample_clip.mp4",
            }
        ],
        "artifact_refs": [
            {
                "id": "asset-feedback",
                "artifact": "asset_manifest",
                "path": "human_feedback.product_fidelity_notes",
                "label": "Product fidelity notes",
            }
        ],
        "trace_refs": [
            {
                "id": "agent-review-boundary",
                "label": "Agent review boundary",
                "source": "AGENT_GUIDE.md",
                "summary": "The browser writes only ui_session_response; the agent validates before canonical writes.",
            }
        ],
        "surfaces": [
            {
                "id": "review-room",
                "type": "MediaReviewRoom",
                "title": "Sample review room",
                "media_ids": ["sample_clip"],
                "artifact_ref_ids": ["asset-feedback"],
                "required_evidence": ["media_opened", "timeline_inspected"],
            },
            {
                "id": "issues",
                "type": "IssueTracker",
                "title": "Review issues",
                "allowed_targets": ["sample_clip", "scene_01"],
                "allowed_statuses": [
                    "open",
                    "accepted",
                    "rejected",
                    "resolved",
                    "needs_recheck",
                    "waived",
                ],
            },
        ],
        "actions": [
            {"id": "approve", "label": "Approve sample", "kind": "approve", "recommended": True},
            {"id": "revise", "label": "Request revisions", "kind": "revise"},
            {"id": "abort", "label": "Abort", "kind": "abort"},
        ],
    }


def _session_submission() -> dict:
    return {
        "action": "revise",
        "values": {
            "asset_manifest.human_feedback.product_fidelity_notes": "Logo reflection drifts in the first hero shot.",
        },
        "annotations": [
            {
                "surface_id": "review-room",
                "target_ref": "sample_clip",
                "comment": "Logo reflection changes shape after the camera move.",
                "timestamp_seconds": 1.4,
                "time_range": {"start_seconds": 1.1, "end_seconds": 2.0},
                "region": {"x": 0.42, "y": 0.22, "width": 0.2, "height": 0.16},
            }
        ],
        "issues": [
            {
                "id": "issue-logo-reflection",
                "target_ref": "sample_clip",
                "status": "open",
                "severity": "blocking",
                "requested_change": "Regenerate the first shot with stable logo reflection.",
                "artifact": "asset_manifest",
                "path": "human_feedback.product_fidelity_notes",
            }
        ],
        "revision_patches": [
            {
                "artifact": "asset_manifest",
                "path": "human_feedback.product_fidelity_notes",
                "value": "Logo reflection drifts in the first hero shot.",
            }
        ],
        "approval_attestations": [
            {
                "id": "reviewed-media",
                "label": "I reviewed the sample media before submitting.",
                "approved": True,
            }
        ],
        "interaction_evidence": {
            "media_opened": ["sample_clip"],
            "timeline_inspected": ["sample_clip"],
            "seconds_watched": 2.5,
        },
        "browser_events": [
            {"type": "media_opened", "target_ref": "sample_clip"},
            {"type": "timeline_seek", "target_ref": "sample_clip", "timestamp_seconds": 1.4},
        ],
    }


def test_genui_session_public_artifacts_are_registered():
    assert "ui_session_config" in ARTIFACT_NAMES
    assert "ui_session_response" in ARTIFACT_NAMES
    assert "ui_interaction_journal" in ARTIFACT_NAMES
    assert "visual_need_assessment" in ARTIFACT_NAMES
    assert "ui_surface_config" in ARTIFACT_NAMES
    assert "ui_surface_response" in ARTIFACT_NAMES


def test_ui_session_config_schema_accepts_framework_backed_media_review_room():
    validate_artifact("ui_session_config", _session_config())


def test_ui_session_config_rejects_canonical_write_action_and_unsafe_media():
    bad_action = _session_config()
    bad_action["actions"][0]["canonical_artifact"] = "asset_manifest"
    with pytest.raises(jsonschema.ValidationError):
        validate_artifact("ui_session_config", bad_action)

    bad_media = _session_config()
    bad_media["media_refs"][0]["path"] = "https://example.test/sample.mp4"
    with pytest.raises(jsonschema.ValidationError):
        validate_artifact("ui_session_config", bad_media)


def test_visual_need_assessment_schema_captures_dynamic_mode_decision():
    assessment = _session_config()["visual_need_assessment"]
    validate_artifact("visual_need_assessment", assessment)


def test_build_dynamic_session_config_selects_media_review_room_and_a2ui_renderer():
    from lib.genui.session import build_dynamic_session_config, compile_session_view_spec

    config = build_dynamic_session_config(_media_review_request())
    validate_artifact("ui_session_config", config)

    assert config["contract"] == "genui_session"
    assert config["mode"] == "media_review_room"
    assert config["framework"]["name"] == "a2ui"
    assert "@a2ui/react" in config["framework"]["packages"]
    assert config["transport"]["name"] == "ag-ui"
    assert config["visual_need_assessment"]["recommended_mode"] == "media_review_room"

    spec = compile_session_view_spec(config, submit_url="http://127.0.0.1:8123/submit", submit_nonce="nonce")
    assert spec["contract"] == "genui_session_view"
    assert spec["renderer"] == "a2ui"
    assert spec["metadata"]["framework"]["renderer"] == "@copilotkit/a2ui-renderer"
    assert spec["a2ui"]["operations"][0]["type"] == "surfaceUpdate"
    assert spec["a2ui"]["operations"][1]["type"] == "dataModelUpdate"
    assert spec["a2ui"]["operations"][2]["type"] == "beginRendering"


def test_view_spec_schema_accepts_compiled_a2ui_session_spec():
    from lib.genui.session import build_dynamic_session_config, compile_session_view_spec

    schema = jsonschema.Draft202012Validator(
        json.loads((ROOT / "schemas/genui/view_spec.schema.json").read_text())
    )
    config = build_dynamic_session_config(_media_review_request())
    spec = compile_session_view_spec(config, submit_url="http://127.0.0.1:8123/submit", submit_nonce="nonce")

    schema.validate(spec)
    assert spec["contract"] == "genui_session_view"
    assert spec["renderer"] == "a2ui"


def test_session_response_payload_accepts_timecoded_issues_and_builds_patch_plan():
    from lib.genui.session import (
        review_session_response,
        session_response_payload_from_submission,
    )

    response = session_response_payload_from_submission(
        _session_config(),
        _session_submission(),
        response_id="resp-asset-sample-review",
    )
    validate_artifact("ui_session_response", response)

    assert response["contract"] == "genui_session_response"
    assert response["issues"][0]["status"] == "open"
    assert response["annotations"][0]["time_range"]["start_seconds"] == 1.1
    assert response["validation"]["status"] == "pending"

    review = review_session_response(_session_config(), response)
    assert review["canonical_writes"] == []
    assert review["blocking_issue_ids"] == ["issue-logo-reflection"]
    assert review["patch_plan"][0]["artifact"] == "asset_manifest"
    assert review["patch_plan"][0]["path"] == "human_feedback.product_fidelity_notes"


def test_session_response_rejects_unconfigured_issue_patch_target():
    from lib.genui.session import session_response_payload_from_submission

    submission = _session_submission()
    submission["issues"][0]["artifact"] = "production_proposal"
    submission["issues"][0]["path"] = "render_runtime"

    with pytest.raises(ValueError, match="issue patch target"):
        session_response_payload_from_submission(_session_config(), submission)


@pytest.mark.parametrize(
    ("mutation", "expected_error"),
    [
        (
            lambda payload: payload["values"].update({"unexpected_field": "hidden"}),
            "value key",
        ),
        (
            lambda payload: payload.update({"selected_refs": ["not-configured"]}),
            "selected_ref",
        ),
        (
            lambda payload: payload["values"].update({"selected_runtime": "made-up"}),
            "selected_runtime",
        ),
        (
            lambda payload: payload["revision_patches"][0].update({"value": "ffmpeg"}),
            "contradicts submitted value",
        ),
    ],
)
def test_session_response_rejects_unconfigured_values_refs_and_patch_mismatches(mutation, expected_error):
    from lib.genui.session import build_dynamic_session_config, session_response_payload_from_submission

    config = build_dynamic_session_config(_option_revision_request())
    submission = {
        "action": "revise",
        "values": {
            "selected_runtime": "hyperframes",
            "approval_notes": "Use the timeline-driven runtime for this cut.",
        },
        "selected_refs": ["hyperframes"],
        "revision_patches": [
            {
                "artifact": "production_proposal",
                "path": "render_runtime_selection.selected_runtime",
                "value": "hyperframes",
            },
            {
                "artifact": "production_proposal",
                "path": "human_feedback.approval_notes",
                "value": "Use the timeline-driven runtime for this cut.",
            },
        ],
        "interaction_evidence": {"media_opened": [], "timeline_inspected": [], "seconds_watched": 0},
        "browser_events": [{"type": "submit_attempt"}],
    }

    mutation(submission)

    with pytest.raises(ValueError, match=expected_error):
        session_response_payload_from_submission(config, submission)


def test_session_response_requires_media_evidence_before_approval():
    from lib.genui.session import session_response_payload_from_submission

    submission = _session_submission()
    submission["action"] = "approve"
    submission["issues"] = []
    submission["interaction_evidence"] = {"media_opened": [], "timeline_inspected": [], "seconds_watched": 0}

    with pytest.raises(ValueError, match="media_opened"):
        session_response_payload_from_submission(_session_config(), submission)


def test_gate_workspace_approval_requires_human_attestation():
    from lib.genui.session import build_dynamic_session_config, session_response_payload_from_submission

    config = build_dynamic_session_config(_gate_workspace_request())
    assert config["mode"] == "gate_workspace"
    required_gate_ids = [
        surface["id"]
        for surface in config["surfaces"]
        if "approval_attested" in surface.get("required_evidence", [])
    ]
    assert required_gate_ids

    submission = {
        "action": "approve",
        "values": {},
        "approval_attestations": [],
        "interaction_evidence": {"media_opened": [], "timeline_inspected": [], "seconds_watched": 0},
        "browser_events": [{"type": "submit_attempt"}],
    }

    with pytest.raises(ValueError, match="approval_attested"):
        session_response_payload_from_submission(config, submission)

    submission["approval_attestations"] = [
        {"id": required_gate_ids[0], "label": "I reviewed and approve this workspace.", "approved": True}
    ]
    response = session_response_payload_from_submission(config, submission, response_id="resp-proposal-lock")
    assert response["approval_attestations"][0]["approved"] is True


def test_read_only_session_sessions_reject_direct_submissions():
    from lib.genui.session import build_dynamic_session_config, session_response_payload_from_submission

    for interaction_kind in ("project_cockpit", "background_status"):
        request = _gate_workspace_request()
        request.update(
            {
                "request_id": f"readonly-{interaction_kind}",
                "interaction_kind": interaction_kind,
                "capabilities_needed": ["status_timeline", "artifact_trace"],
            }
        )
        config = build_dynamic_session_config(request)
        assert config["actions"] == []

        with pytest.raises(ValueError, match="does not accept browser submissions"):
            session_response_payload_from_submission(
                config,
                {
                    "action": "approve",
                    "values": {},
                    "interaction_evidence": {"media_opened": [], "timeline_inspected": [], "seconds_watched": 0},
                    "browser_events": [{"type": "submit_attempt"}],
                },
            )


def test_dynamic_gate_session_preserves_choices_fields_and_revision_bindings():
    from lib.genui.session import (
        build_dynamic_session_config,
        compile_session_view_spec,
        review_session_response,
        session_response_payload_from_submission,
    )

    config = build_dynamic_session_config(_option_revision_request())
    validate_artifact("ui_session_config", config)

    workspace = next(surface for surface in config["surfaces"] if surface["type"] == "ProposalLock")
    assert [choice["value"] for choice in workspace["choices"]] == ["remotion", "hyperframes", "ffmpeg"]
    assert workspace["fields"][0]["id"] == "approval_notes"
    assert workspace["selection"]["fieldId"] == "selected_runtime"
    assert config["initial_values"]["selected_runtime"] == "remotion"

    spec = compile_session_view_spec(config)
    proposal_component = next(component for component in spec["a2ui"]["components"] if component["type"] == "ProposalLock")
    assert proposal_component["props"]["choices"][0]["value"] == "remotion"
    assert proposal_component["props"]["fields"][0]["binding"]["artifact"] == "production_proposal"
    assert spec["state"]["values"]["selected_runtime"] == "remotion"

    submission = {
        "action": "revise",
        "values": {
            "selected_runtime": "hyperframes",
            "approval_notes": "Use the timeline-driven runtime for this cut.",
        },
        "revision_patches": [
            {
                "artifact": "production_proposal",
                "path": "render_runtime_selection.selected_runtime",
                "value": "hyperframes",
            },
            {
                "artifact": "production_proposal",
                "path": "human_feedback.approval_notes",
                "value": "Use the timeline-driven runtime for this cut.",
            },
        ],
        "interaction_evidence": {"media_opened": [], "timeline_inspected": [], "seconds_watched": 0},
        "browser_events": [{"type": "submit_attempt"}],
    }
    response = session_response_payload_from_submission(config, submission, response_id="resp-proposal-options")
    review = review_session_response(config, response)
    assert response["values"]["selected_runtime"] == "hyperframes"
    assert review["patch_plan"][0]["path"] == "render_runtime_selection.selected_runtime"


def test_dynamic_session_routes_project_cockpit_and_background_status_modes():
    from lib.genui.session import build_dynamic_session_config

    for interaction_kind, expected_mode, expected_surface in [
        ("project_cockpit", "project_cockpit", "ProjectCockpit"),
        ("background_status", "background_status", "BackgroundStatus"),
    ]:
        request = _gate_workspace_request()
        request.update(
            {
                "request_id": f"status-{interaction_kind}",
                "interaction_kind": interaction_kind,
                "capabilities_needed": ["status_timeline", "artifact_trace"],
            }
        )
        config = build_dynamic_session_config(request)
        validate_artifact("ui_session_config", config)
        assert config["mode"] == expected_mode
        assert [surface["type"] for surface in config["surfaces"]] == [expected_surface]
        assert config["actions"] == []


def test_genui_session_tool_materializes_session(tmp_path: Path):
    from tools.interaction.genui_session import GenUISession
    from tools.tool_registry import registry

    project_dir = tmp_path / "projects" / "demo-ad"
    _write_sample_clip(project_dir)
    result = GenUISession().execute(
        {
            "project_dir": str(project_dir),
            "interaction_request": _media_review_request(),
            "mode": "prepare",
        }
    )

    assert result.success, result.error
    assert result.data["session_contract"] == "genui_session"
    assert result.data["renderer"] == "a2ui"
    assert result.data["framework"] == "a2ui"
    assert Path(result.data["config_path"]).exists()
    assert Path(result.data["view_spec_path"]).exists()
    assert json.loads(Path(result.data["view_spec_path"]).read_text())["renderer"] == "a2ui"

    registry.clear()
    registry.discover()
    assert registry.get("genui_session") is not None


def test_genui_session_serve_does_not_open_browser_by_default(tmp_path: Path, monkeypatch):
    from tools.interaction.genui_session import GenUISession

    class FakeProcess:
        pid = 42001

        def poll(self):
            return None

        def terminate(self):
            return None

    project_dir = tmp_path / "projects" / "demo-ad"
    _write_sample_clip(project_dir)
    tool = GenUISession()
    opened_urls: list[str] = []
    monkeypatch.setattr(tool, "_choose_port", lambda host: 8123)
    monkeypatch.setattr(tool, "_start_server", lambda *args, **kwargs: FakeProcess())
    monkeypatch.setattr(tool, "_wait_until_ready", lambda *args, **kwargs: None)
    monkeypatch.setattr(tool, "_try_open_browser", lambda url: opened_urls.append(url) or True)

    result = tool.execute(
        {
            "project_dir": str(project_dir),
            "config": _session_config(),
            "mode": "serve",
            "record_journal": False,
        }
    )

    assert result.success, result.error
    assert result.data["server_state"] == "running"
    assert result.data["browser_url"]
    assert result.data["browser_opened"] is False
    assert opened_urls == []
    assert not result.data["instructions"].startswith("Open ")
    assert result.data["browser_url"] in result.data["instructions"]

    opt_in_result = tool.execute(
        {
            "project_dir": str(project_dir),
            "config": {**_session_config(), "session_id": "asset-sample-review-open"},
            "mode": "serve",
            "record_journal": False,
            "open_browser": True,
        }
    )

    assert opt_in_result.success, opt_in_result.error
    assert opt_in_result.data["browser_opened"] is True
    assert opened_urls == [opt_in_result.data["browser_url"]]


def test_genui_browser_open_is_suppressed_during_pytest(monkeypatch):
    import webbrowser

    from tools.interaction import genui_runtime
    from tools.interaction.genui_runtime import LocalGenUIServerRuntime

    opened_urls: list[str] = []
    monkeypatch.setenv("PYTEST_CURRENT_TEST", "test blocks visible browser open")
    monkeypatch.delenv("VPB_ALLOW_BROWSER_OPEN", raising=False)
    monkeypatch.setattr(genui_runtime, "is_wsl2", lambda: False)
    monkeypatch.setattr(webbrowser, "open", lambda url: opened_urls.append(url) or True)

    opened = LocalGenUIServerRuntime()._try_open_browser("http://127.0.0.1:8123/")

    assert opened is False
    assert opened_urls == []


def test_genui_server_readiness_uses_spec_probe_with_load_tolerant_timeout(monkeypatch):
    from tools.interaction import genui_runtime
    from tools.interaction.genui_runtime import LocalGenUIServerRuntime

    class FakeProcess:
        returncode = None

        def poll(self):
            return None

    class FakeResponse:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    observed: dict[str, object] = {}
    now = {"value": 0.0}

    def fake_monotonic():
        now["value"] += 0.01
        return now["value"]

    def fake_urlopen(url: str, timeout: float):
        observed["url"] = url
        observed["timeout"] = timeout
        if timeout < 1.0:
            raise TimeoutError("readiness probe timed out before server response")
        return FakeResponse()

    monkeypatch.setattr(genui_runtime.time, "monotonic", fake_monotonic)
    monkeypatch.setattr(genui_runtime.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(genui_runtime.urllib.request, "urlopen", fake_urlopen)

    LocalGenUIServerRuntime()._wait_until_ready(
        FakeProcess(),
        "127.0.0.1",
        8123,
        timeout_seconds=0.1,
    )

    assert observed["url"] == "http://127.0.0.1:8123/spec.json"
    assert observed["timeout"] >= 1.0


def test_genui_server_readiness_reports_startup_stderr():
    from tools.interaction.genui_runtime import LocalGenUIServerRuntime

    class FakeStderr:
        def read(self):
            return "Traceback omitted\nRuntimeError: invalid view spec\n"

    class FailedProcess:
        returncode = 2
        stderr = FakeStderr()

        def poll(self):
            return self.returncode

    with pytest.raises(RuntimeError, match="invalid view spec"):
        LocalGenUIServerRuntime()._wait_until_ready(
            FailedProcess(),
            "127.0.0.1",
            8123,
            timeout_seconds=0.1,
        )


def test_genui_server_start_uses_file_backed_stderr_to_avoid_pipe_deadlock(
    tmp_path: Path, monkeypatch
):
    from tools.interaction import genui_runtime
    from tools.interaction.genui_runtime import LocalGenUIServerRuntime

    class FakeBundle:
        config_path = tmp_path / "config.json"
        response_path = tmp_path / "response.json"
        view_spec_path = tmp_path / "view_spec.json"

    class FakeProcess:
        pass

    observed: dict[str, object] = {}

    def fake_popen(cmd, **kwargs):
        observed["cmd"] = cmd
        observed.update(kwargs)
        return FakeProcess()

    monkeypatch.setattr(genui_runtime.subprocess, "Popen", fake_popen)

    process = LocalGenUIServerRuntime()._start_server(
        FakeBundle(),
        "127.0.0.1",
        8123,
        "nonce",
    )

    stderr_log = getattr(process, "_genui_stderr_log")
    try:
        assert observed["stderr"] is stderr_log
        assert observed["stderr"] not in {
            subprocess.PIPE,
            subprocess.DEVNULL,
            None,
        }
        assert stderr_log.seekable()
        assert stderr_log.writable()
        assert observed["stdout"] == subprocess.DEVNULL
    finally:
        stderr_log.close()


def test_genui_server_readiness_reports_file_backed_startup_stderr(
    tmp_path: Path,
):
    from tools.interaction.genui_runtime import LocalGenUIServerRuntime

    stderr_log = (tmp_path / "genui-server.stderr").open("w+", encoding="utf-8")
    stderr_log.write("Traceback omitted\nRuntimeError: invalid view spec\n")
    stderr_log.flush()

    class FailedProcess:
        returncode = 2
        _genui_stderr_log = stderr_log
        stderr = None

        def poll(self):
            return self.returncode

    try:
        with pytest.raises(RuntimeError, match="invalid view spec"):
            LocalGenUIServerRuntime()._wait_until_ready(
                FailedProcess(),
                "127.0.0.1",
                8123,
                timeout_seconds=0.1,
            )
    finally:
        stderr_log.close()


def test_genui_browser_open_is_suppressed_during_pytest_even_when_env_allows(
    monkeypatch,
):
    import webbrowser

    from tools.interaction import genui_runtime
    from tools.interaction.genui_runtime import LocalGenUIServerRuntime

    opened_urls: list[str] = []
    monkeypatch.setenv("PYTEST_CURRENT_TEST", "test blocks explicit browser open")
    monkeypatch.setenv("VPB_ALLOW_BROWSER_OPEN", "1")
    monkeypatch.setattr(genui_runtime, "is_wsl2", lambda: False)
    monkeypatch.setattr(webbrowser, "open", lambda url: opened_urls.append(url) or True)

    opened = LocalGenUIServerRuntime()._try_open_browser("http://127.0.0.1:8123/")

    assert opened is False
    assert opened_urls == []


def test_genui_browser_open_respects_environment_opt_out(monkeypatch):
    import webbrowser

    from tools.interaction import genui_runtime
    from tools.interaction.genui_runtime import LocalGenUIServerRuntime

    opened_urls: list[str] = []
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.setenv("VPB_ALLOW_BROWSER_OPEN", "0")
    monkeypatch.setattr(genui_runtime, "is_wsl2", lambda: False)
    monkeypatch.setattr(webbrowser, "open", lambda url: opened_urls.append(url) or True)

    opened = LocalGenUIServerRuntime()._try_open_browser("http://127.0.0.1:8123/")

    assert opened is False
    assert opened_urls == []


def test_genui_browser_open_strips_environment_opt_out(monkeypatch):
    import webbrowser

    from tools.interaction import genui_runtime
    from tools.interaction.genui_runtime import LocalGenUIServerRuntime

    opened_urls: list[str] = []
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.setenv("VPB_ALLOW_BROWSER_OPEN", " 0 ")
    monkeypatch.setattr(genui_runtime, "is_wsl2", lambda: False)
    monkeypatch.setattr(webbrowser, "open", lambda url: opened_urls.append(url) or True)

    opened = LocalGenUIServerRuntime()._try_open_browser("http://127.0.0.1:8123/")

    assert opened is False
    assert opened_urls == []


def test_genui_browser_open_respects_environment_off_opt_out(monkeypatch):
    import webbrowser

    from tools.interaction import genui_runtime
    from tools.interaction.genui_runtime import LocalGenUIServerRuntime

    opened_urls: list[str] = []
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.setenv("VPB_ALLOW_BROWSER_OPEN", " off ")
    monkeypatch.setattr(genui_runtime, "is_wsl2", lambda: False)
    monkeypatch.setattr(webbrowser, "open", lambda url: opened_urls.append(url) or True)

    opened = LocalGenUIServerRuntime()._try_open_browser("http://127.0.0.1:8123/")

    assert opened is False
    assert opened_urls == []


def test_genui_wsl_browser_start_is_suppressed_during_pytest(monkeypatch):
    from tools.interaction import genui_runtime
    from tools.interaction.genui_runtime import LocalGenUIServerRuntime

    start_calls: list[list[str]] = []
    monkeypatch.setenv("PYTEST_CURRENT_TEST", "test blocks visible wsl browser start")
    monkeypatch.delenv("VPB_ALLOW_BROWSER_OPEN", raising=False)
    monkeypatch.setattr(genui_runtime, "is_wsl2", lambda: True)
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda cmd, **kwargs: start_calls.append(cmd)
        or subprocess.CompletedProcess(cmd, 0),
    )

    opened = LocalGenUIServerRuntime()._try_open_browser("http://127.0.0.1:8123/")

    assert opened is False
    assert start_calls == []


def test_genui_session_rejects_non_finite_server_state_before_writing(
    tmp_path: Path, monkeypatch
):
    from tools.interaction.genui_session import GenUISession

    class FakeProcess:
        pid = math.nan
        terminated = False

        def poll(self):
            return None

        def terminate(self):
            self.terminated = True
            return None

    project_dir = tmp_path / "projects" / "demo-ad"
    _write_sample_clip(project_dir)
    tool = GenUISession()
    fake_process = FakeProcess()
    monkeypatch.setattr(tool, "_choose_port", lambda host: 8123)
    monkeypatch.setattr(tool, "_start_server", lambda *args, **kwargs: fake_process)
    monkeypatch.setattr(tool, "_wait_until_ready", lambda *args, **kwargs: None)
    monkeypatch.setattr(tool, "_try_open_browser", lambda url: True)

    result = tool.execute(
        {
            "project_dir": str(project_dir),
            "config": _session_config(),
            "mode": "serve",
            "record_journal": False,
        }
    )

    assert not result.success
    assert "strict JSON" in result.error
    assert fake_process.terminated is True
    assert not (
        project_dir / "artifacts" / "ui" / "asset-sample-review" / "server.json"
    ).exists()


def test_genui_interaction_defaults_to_session_and_preserves_surface_fallback(tmp_path: Path):
    from tools.interaction.genui_interaction import GenUIInteraction

    session_project_dir = tmp_path / "projects" / "demo-ad-session"
    surface_project_dir = tmp_path / "projects" / "demo-ad-surface"
    _write_sample_clip(session_project_dir)
    _write_sample_clip(surface_project_dir)

    session_result = GenUIInteraction().execute(
        {
            "project_dir": str(session_project_dir),
            "interaction_request": _media_review_request(),
            "mode": "prepare",
        }
    )
    assert session_result.success, session_result.error
    assert session_result.data["delegated_tool"] == "genui_session"
    assert session_result.data["renderer"] == "a2ui"
    assert session_result.data["session_contract"] == "genui_session"

    surface_result = GenUIInteraction().execute(
        {
            "project_dir": str(surface_project_dir),
            "interaction_request": _media_review_request(),
            "mode": "prepare",
            "compatibility_mode": "surface",
        }
    )
    assert surface_result.success, surface_result.error
    assert surface_result.data["delegated_tool"] == "genui_surface"
    assert surface_result.data["renderer"] == "json-render"
    assert surface_result.data["surface_contract"] == "genui_surface"


def test_dynamic_session_uses_pipeline_specific_workspace_types():
    from lib.genui.session import build_dynamic_session_config

    cases = [
        ("proposal", "proposal_lock", "ProposalLock"),
        ("script", "script_review", "ScriptReviewWorkspace"),
        ("scene_plan", "scene_plan_approval", "ScenePlanWorkspace"),
        ("assets", "product_reference", "ProductReferenceApproval"),
        ("assets", "sample_review", "SampleReview"),
        ("assets", "asset_review", "AssetReview"),
        ("assets", "music_review", "MusicReview"),
        ("publish", "publish_review", "PublishReview"),
    ]

    for stage, gate, expected_type in cases:
        request = _media_review_request()
        request.update(
            {
                "request_id": f"{stage}-{gate}",
                "stage": stage,
                "gate": gate,
                "interaction_kind": "media_review" if "review" in gate or gate == "sample_review" else "multi_axis_selection",
                "capabilities_needed": ["media_review", "structured_revision_capture"] if "review" in gate else ["multi_axis_selection"],
            }
        )
        config = build_dynamic_session_config(request)
        surface_types = {surface["type"] for surface in config["surfaces"]}
        assert expected_type in surface_types, (stage, gate, surface_types)
        assert "IssueTracker" in surface_types


def test_project_cockpit_session_is_read_only_and_framework_backed(tmp_path: Path):
    from lib.genui.session import build_project_cockpit_session_config, compile_session_view_spec

    project_dir = tmp_path / "projects" / "demo-ad"
    config = build_project_cockpit_session_config(
        project_dir,
        project_id="demo-ad",
        pipeline_type="ad-video",
        active_stage="assets",
    )

    validate_artifact("ui_session_config", config)
    assert config["mode"] == "project_cockpit"
    assert config["actions"] == []
    assert config["framework"]["name"] == "a2ui"
    assert config["visual_need_assessment"]["recommended_mode"] == "project_cockpit"

    spec = compile_session_view_spec(config)
    assert spec["renderer"] == "a2ui"
    assert {component["type"] for component in spec["a2ui"]["components"]} >= {"SessionShell", "ProjectCockpit"}


def test_project_cockpit_timeline_shows_child_gate_without_lifecycle_fields(tmp_path: Path):
    from lib.genui.project_snapshot import build_project_cockpit_snapshot

    snapshot = build_project_cockpit_snapshot(
        tmp_path / "projects" / "demo-ad",
        pipeline_type="ad-video",
        active_stage="research.brief_enrichment",
    )

    timeline = {item["id"]: item for item in snapshot["timeline_items"]}

    assert "brief_enrichment" not in timeline
    assert timeline["research"]["id"] == "research"
    assert timeline["research"]["status"] == "active"
    assert timeline["research"]["active_stage"] == "research.brief_enrichment"
    assert timeline["research"]["active_sub_stage"] == "brief_enrichment"
    assert "phase" not in timeline["research"]
    assert "parent_stage" not in timeline["research"]
    assert "bible" not in timeline
    assert "proposal" in timeline


def test_project_cockpit_marks_parent_stage_active_for_active_sub_stage(tmp_path: Path):
    from lib.genui.project_snapshot import build_project_cockpit_snapshot

    snapshot = build_project_cockpit_snapshot(
        tmp_path / "projects" / "demo-ad",
        pipeline_type="ad-video",
        active_stage="assets.sample",
    )

    timeline = {item["id"]: item for item in snapshot["timeline_items"]}

    assert "assets.sample" not in timeline
    assert timeline["assets"]["status"] == "active"
    assert timeline["assets"]["active_stage"] == "assets.sample"
    assert timeline["assets"]["active_sub_stage"] == "sample"
    assert timeline["assets"]["active_sub_stage_label"] == "Sample"


def test_project_cockpit_keeps_parent_checkpoint_active_for_active_sub_stage(
    tmp_path: Path,
):
    from lib.genui.project_snapshot import build_project_cockpit_snapshot

    project_dir = tmp_path / "projects" / "demo-ad"
    project_dir.mkdir(parents=True)
    (project_dir / "checkpoint_assets.json").write_text(
        json.dumps(
            {
                "stage": "assets",
                "approved": False,
                "artifacts": {},
            }
        ),
        encoding="utf-8",
    )

    snapshot = build_project_cockpit_snapshot(
        project_dir,
        pipeline_type="ad-video",
        active_stage="assets.sample",
    )

    timeline = {item["id"]: item for item in snapshot["timeline_items"]}

    assert timeline["assets"]["status"] == "awaiting_human"
    assert timeline["assets"]["approved"] is False
    assert timeline["assets"]["active_stage"] == "assets.sample"
    assert timeline["assets"]["active_sub_stage"] == "sample"


def test_project_cockpit_marks_dotted_active_stage_active_when_manifest_is_missing(
    tmp_path: Path,
):
    from lib.genui.project_snapshot import build_project_cockpit_snapshot

    snapshot = build_project_cockpit_snapshot(
        tmp_path / "projects" / "demo-ad",
        pipeline_type="missing-pipeline",
        active_stage="assets.sample",
    )

    assert snapshot["timeline_items"] == [
        {
            "id": "assets.sample",
            "label": "Assets.Sample",
            "status": "active",
            "active_stage": "assets.sample",
            "active_sub_stage": "sample",
            "active_sub_stage_label": "Sample",
        }
    ]


def test_project_cockpit_child_gate_fields_survive_compilation(
    tmp_path: Path,
):
    from lib.genui.session import build_project_cockpit_session_config, compile_session_view_spec

    config = build_project_cockpit_session_config(
        tmp_path / "projects" / "demo-ad",
        project_id="demo-ad",
        pipeline_type="ad-video",
        active_stage="assets.sample",
    )
    spec = compile_session_view_spec(config)
    cockpit = next(
        component
        for component in spec["a2ui"]["components"]
        if component["type"] == "ProjectCockpit"
    )
    timeline = {item["id"]: item for item in cockpit["props"]["timelineItems"]}

    assert timeline["assets"]["active_stage"] == "assets.sample"
    assert timeline["assets"]["active_sub_stage"] == "sample"
    assert "phase" not in timeline["assets"]
    assert "parent_stage" not in timeline["assets"]


def test_genui_product_session_config_declares_product_contract_and_component_pack():
    from lib.genui.session import build_dynamic_session_config, compile_session_view_spec

    config = build_dynamic_session_config(_media_review_request())
    validate_artifact("ui_session_config", config)

    assert config["metadata"]["genui_contract"] == "genui"
    assert not [key for key in config["metadata"] if key.startswith("genui_v")]
    assert config["metadata"]["interaction_journal"] is True
    assert config["metadata"]["framework_renderer"] == "@copilotkit/a2ui-renderer"
    assert config["metadata"]["protocol"] == "ag-ui"

    spec = compile_session_view_spec(config)
    component_types = {component["type"] for component in spec["a2ui"]["components"]}
    assert {
        "SessionShell",
        "MediaReviewRoom",
        "MediaTimeline",
        "MediaComparison",
        "RegionAnnotation",
        "IssueBoard",
        "ArtifactTrace",
        "RevisionPatchPreview",
        "LiveStatusPanel",
        "InteractionJournalPanel",
    }.issubset(component_types)
    assert spec["metadata"]["genui_contract"] == "genui"
    assert spec["state"]["session"]["genui_contract"] == "genui"


def test_ui_interaction_journal_schema_tracks_cli_and_genui_decisions():
    from lib.genui.journal import build_interaction_journal

    journal = build_interaction_journal(
        project_id="demo-ad",
        pipeline_type="ad-video",
        entries=[
            {
                "interaction_id": "quick-confirm",
                "routing_decision_id": "route-quick-confirm",
                "request_id": "quick-confirm",
                "project_id": "demo-ad",
                "pipeline_type": "ad-video",
                "stage": "intake",
                "gate": "clarification",
                "interaction_kind": "clarification",
                "mode": "cli",
                "recommended_tool": None,
                "linear_chat_sufficient": True,
                "reasons": [],
                "required_ui_primitives": [],
                "status": "cli_recommended",
                "fallback_reason": "linear_chat_sufficient",
                "validation": {"status": "not_required", "errors": []},
            },
            {
                "interaction_id": "asset-sample-review",
                "routing_decision_id": "route-asset-sample-review",
                "request_id": "asset-sample-review",
                "project_id": "demo-ad",
                "pipeline_type": "ad-video",
                "stage": "assets",
                "gate": "sample_review",
                "interaction_kind": "media_review",
                "mode": "media_review_room",
                "recommended_tool": "genui_session",
                "linear_chat_sufficient": False,
                "reasons": ["media_review"],
                "required_ui_primitives": ["media_player", "timecoded_annotation"],
                "status": "prepared",
                "session_id": "asset-sample-review",
                "session_contract": "genui_session",
                "config_path": "projects/demo-ad/artifacts/ui/asset-sample-review/config.json",
                "view_spec_path": "projects/demo-ad/artifacts/ui/asset-sample-review/view_spec.json",
                "response_path": "projects/demo-ad/artifacts/ui/asset-sample-review/response.json",
                "validation": {"status": "pending", "errors": []},
            },
        ],
    )

    validate_artifact("ui_interaction_journal", journal)
    assert journal["contract"] == "genui_interaction_journal"
    assert [entry["status"] for entry in journal["interactions"]] == ["cli_recommended", "prepared"]


def test_ui_interaction_journal_reader_rejects_non_strict_json(tmp_path: Path):
    from lib.genui.journal import interaction_journal_path, read_interaction_journal

    project_dir = tmp_path / "projects" / "demo-ad"
    path = interaction_journal_path(project_dir)
    path.parent.mkdir(parents=True)
    path.write_text(
        """
{
  "contract": "genui_interaction_journal",
  "project_id": "demo-ad",
  "pipeline_type": "ad-video",
  "created_at": "2026-06-14T00:00:00+00:00",
  "updated_at": "2026-06-14T00:00:00+00:00",
  "interactions": [],
  "metadata": {
    "genui_contract": "genui",
    "canonical_writes": false,
    "browser_writes": ["ui_session_response"],
    "x_non_finite_sentinel": NaN
  }
}
""".lstrip(),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="strict JSON"):
        read_interaction_journal(
            project_dir,
            project_id="demo-ad",
            pipeline_type="ad-video",
        )


def test_genui_session_modes_status_validate_summarize_and_replay(tmp_path: Path):
    from tools.interaction.genui_session import GenUISession
    from lib.genui.session import session_response_payload_from_submission, write_session_response

    project_dir = tmp_path / "projects" / "demo-ad"
    _write_sample_clip(project_dir)
    tool = GenUISession()
    prepared = tool.execute(
        {
            "project_dir": str(project_dir),
            "interaction_request": _media_review_request(),
            "mode": "prepare",
        }
    )
    assert prepared.success, prepared.error
    assert prepared.data["genui_contract"] == "genui"
    assert Path(prepared.data["journal_path"]).exists()

    config = json.loads(Path(prepared.data["config_path"]).read_text())
    response = session_response_payload_from_submission(
        config,
        _session_submission(),
        response_id="resp-asset-sample-review",
    )
    write_session_response(prepared.data["response_path"], response)

    status = tool.execute(
        {
            "project_dir": str(project_dir),
            "session_id": "asset-sample-review",
            "mode": "status",
        }
    )
    assert status.success, status.error
    assert status.data["server_state"] == "submitted"
    assert status.data["response_exists"] is True
    assert status.data["journal_path"] == prepared.data["journal_path"]

    validated = tool.execute(
        {
            "project_dir": str(project_dir),
            "session_id": "asset-sample-review",
            "mode": "validate_response",
        }
    )
    assert validated.success, validated.error
    assert validated.data["server_state"] == "blocked"
    assert validated.data["review"]["canonical_writes"] == []
    assert validated.data["validation"]["status"] == "blocked"

    summarized = tool.execute(
        {
            "project_dir": str(project_dir),
            "session_id": "asset-sample-review",
            "mode": "summarize",
        }
    )
    assert summarized.success, summarized.error
    assert summarized.data["server_state"] == "blocked"
    assert summarized.data["validation"]["status"] == "blocked"
    assert "blocked" in summarized.data["instructions"]
    assert "Logo reflection" in summarized.data["summary"]
    assert summarized.data["patch_plan"][0]["artifact"] == "asset_manifest"

    replay = tool.execute(
        {
            "project_dir": str(project_dir),
            "session_id": "asset-sample-review",
            "mode": "replay",
        }
    )
    assert replay.success, replay.error
    assert replay.data["server_state"] == "replay_prepared"
    assert replay.data["replay_path"] == prepared.data["html_path"]


def test_genui_session_status_rejects_non_strict_config_json(tmp_path: Path):
    from tools.interaction.genui_session import GenUISession

    project_dir = tmp_path / "projects" / "demo-ad"
    session_dir = project_dir / "artifacts" / "ui" / "asset-sample-review"
    session_dir.mkdir(parents=True)
    (session_dir / "config.json").write_text(
        """
{
  "session_id": "asset-sample-review",
  "project_id": "demo-ad",
  "pipeline_type": "ad-video",
  "x-non-finite-sentinel": NaN
}
""".lstrip(),
        encoding="utf-8",
    )

    result = GenUISession().execute(
        {
            "project_dir": str(project_dir),
            "session_id": "asset-sample-review",
            "mode": "status",
            "record_journal": False,
        }
    )

    assert result.success is False
    assert "strict JSON" in (result.error or "")


def test_genui_session_status_rejects_non_strict_server_state_json(tmp_path: Path):
    from tools.interaction.genui_session import GenUISession

    project_dir = tmp_path / "projects" / "demo-ad"
    session_dir = project_dir / "artifacts" / "ui" / "asset-sample-review"
    session_dir.mkdir(parents=True)
    (session_dir / "config.json").write_text(
        """
{
  "session_id": "asset-sample-review",
  "project_id": "demo-ad",
  "pipeline_type": "ad-video"
}
""".lstrip(),
        encoding="utf-8",
    )
    (session_dir / "server.json").write_text(
        """
{
  "server_state": "running",
  "url": "http://127.0.0.1:8123/",
  "pid": NaN
}
""".lstrip(),
        encoding="utf-8",
    )

    result = GenUISession().execute(
        {
            "project_dir": str(project_dir),
            "session_id": "asset-sample-review",
            "mode": "status",
            "record_journal": False,
        }
    )

    assert result.success is False
    assert "strict JSON" in (result.error or "")


def test_genui_session_validate_response_rejects_non_strict_response_json(tmp_path: Path):
    from tools.interaction.genui_session import GenUISession
    from lib.genui.session import session_response_payload_from_submission

    project_dir = tmp_path / "projects" / "demo-ad"
    _write_sample_clip(project_dir)
    tool = GenUISession()
    prepared = tool.execute(
        {
            "project_dir": str(project_dir),
            "interaction_request": _media_review_request(),
            "mode": "prepare",
        }
    )
    assert prepared.success, prepared.error

    config = json.loads(Path(prepared.data["config_path"]).read_text())
    response = session_response_payload_from_submission(
        config,
        _session_submission(),
        response_id="resp-asset-sample-review",
    )
    response["metadata"]["x_non_finite_sentinel"] = float("nan")
    Path(prepared.data["response_path"]).write_text(
        json.dumps(response),
        encoding="utf-8",
    )

    result = tool.execute(
        {
            "project_dir": str(project_dir),
            "session_id": "asset-sample-review",
            "mode": "validate_response",
            "record_journal": False,
        }
    )

    assert result.success is False
    assert "strict JSON" in (result.error or "")


def test_genui_session_normalizes_project_relative_review_media_paths(tmp_path: Path):
    from tools.interaction.genui_session import GenUISession

    project_dir = tmp_path / "projects" / "demo-ad"
    sample_path = project_dir / "renders" / "sample_preview.mp4"
    sample_path.parent.mkdir(parents=True)
    sample_path.write_bytes(b"sample")

    request = _media_review_request()
    request["media_items"] = [
        {
            "id": "sample_preview",
            "title": "Sample preview",
            "kind": "video",
            "path": "renders/sample_preview.mp4",
        }
    ]

    result = GenUISession().execute(
        {
            "project_dir": str(project_dir),
            "interaction_request": request,
            "mode": "prepare",
        }
    )

    assert result.success, result.error
    config = json.loads(Path(result.data["config_path"]).read_text())
    assert config["mode"] == "media_review_room"
    assert config["media_refs"] == [
        {
            "id": "sample_preview",
            "kind": "video",
            "title": "Sample preview",
            "path": "/media/renders/sample_preview.mp4",
            "alt": "Sample preview",
        }
    ]


def test_genui_session_schema_and_builder_accept_project_relative_review_media_paths():
    from lib.genui.dynamic import validate_interaction_request
    from lib.genui.session import build_dynamic_session_config

    request = _media_review_request()
    request["media_items"][0]["path"] = "renders/sample_preview.mp4"

    validate_interaction_request(request)
    config = build_dynamic_session_config(request)

    assert config["media_refs"][0]["path"] == "/media/renders/sample_preview.mp4"


def test_genui_session_rejects_missing_explicit_browser_media_paths(tmp_path: Path):
    from tools.interaction.genui_session import GenUISession

    project_dir = tmp_path / "projects" / "demo-ad"

    result = GenUISession().execute(
        {
            "project_dir": str(project_dir),
            "interaction_request": _media_review_request(),
            "mode": "prepare",
        }
    )

    assert not result.success
    assert "review media does not exist" in result.error


def test_genui_session_auto_populates_media_review_assets_from_project_artifacts(tmp_path: Path):
    from tools.interaction.genui_session import GenUISession

    project_dir = tmp_path / "projects" / "demo-ad"
    for rel in [
        "renders/sample_preview.mp4",
        "assets/video/s01.mp4",
        "assets/images/s02.png",
        "assets/keyframes/s01/start.png",
        "assets/keyframes/s01/mid.png",
        "assets/music/background_music.mp3",
        "outputs/final.mp4",
    ]:
        path = project_dir / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"sample")
    artifacts_dir = project_dir / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    (artifacts_dir / "asset_manifest.json").write_text(
        json.dumps(
            {
                "version": "1.0",
                "assets": [
                    {
                        "id": "scene-video",
                        "type": "video",
                        "path": "assets/video/s01.mp4",
                        "source_tool": "wan_video_api",
                        "scene_id": "s01",
                        "hallucination_review": {
                            "status": "WARN",
                            "keyframe_paths": [
                                "assets/keyframes/s01/start.png",
                                "assets/keyframes/s01/mid.png",
                            ],
                            "check_verdicts": [
                                {
                                    "check_id": "shape",
                                    "category": "product_geometry",
                                    "status": "WARN",
                                    "notes": "Inspect during human review.",
                                }
                            ],
                            "reviewer": {
                                "type": "agent",
                                "reviewed_at": "2026-06-04T00:00:00Z",
                                "method": "start_mid_end_keyframe_review",
                            },
                        },
                    },
                    {
                        "id": "scene-still",
                        "type": "image",
                        "path": "assets/images/s02.png",
                        "source_tool": "wanx_image",
                        "scene_id": "s02",
                    },
                ],
                "sample_clip": "renders/sample_preview.mp4",
                "music_file": "assets/music/background_music.mp3",
            }
        )
        + "\n"
    )
    (artifacts_dir / "render_report.json").write_text(
        json.dumps(
            {
                "version": "1.0",
                "outputs": [
                    {
                        "path": "outputs/final.mp4",
                        "format": "mp4",
                        "resolution": "1920x1080",
                        "duration_seconds": 15,
                    }
                ],
            }
        )
        + "\n"
    )

    request = _media_review_request()
    request["request_id"] = "full-asset-review"
    request["gate"] = "asset_review"
    request["title"] = "Review generated assets"
    request["media_items"] = []

    result = GenUISession().execute(
        {
            "project_dir": str(project_dir),
            "interaction_request": request,
            "mode": "prepare",
        }
    )

    assert result.success, result.error
    config = json.loads(Path(result.data["config_path"]).read_text())
    media_paths = {item["path"] for item in config["media_refs"]}
    assert {
        "/media/renders/sample_preview.mp4",
        "/media/assets/video/s01.mp4",
        "/media/assets/images/s02.png",
        "/media/assets/keyframes/s01/start.png",
        "/media/assets/keyframes/s01/mid.png",
        "/media/assets/music/background_music.mp3",
        "/media/outputs/final.mp4",
    }.issubset(media_paths)
    assert config["metadata"]["review_assets_auto_populated"] is True


def test_genui_session_auto_population_rejects_non_strict_asset_manifest_json(
    tmp_path: Path,
) -> None:
    from tools.interaction.genui_session import GenUISession

    project_dir = tmp_path / "projects" / "demo-ad"
    sample_path = project_dir / "renders" / "sample_preview.mp4"
    sample_path.parent.mkdir(parents=True)
    sample_path.write_bytes(b"sample")
    artifacts_dir = project_dir / "artifacts"
    artifacts_dir.mkdir(parents=True)
    (artifacts_dir / "asset_manifest.json").write_text(
        """
{
  "version": "1.0",
  "assets": [],
  "sample_clip": "renders/sample_preview.mp4",
  "metadata": {
    "x_non_finite_sentinel": NaN
  }
}
""".lstrip(),
        encoding="utf-8",
    )

    request = _media_review_request()
    request["media_items"] = []

    result = GenUISession().execute(
        {
            "project_dir": str(project_dir),
            "interaction_request": request,
            "mode": "prepare",
        }
    )

    assert result.success is False
    assert "strict JSON" in (result.error or "")


def test_genui_session_auto_populates_product_reference_candidates(tmp_path: Path):
    from tools.interaction.genui_session import GenUISession

    project_dir = tmp_path / "projects" / "demo-ad"
    for rel in [
        "reference_assets/product_candidate_01.png",
        "reference_assets/product_candidate_02.png",
    ]:
        path = project_dir / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"sample")
    artifacts_dir = project_dir / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    (artifacts_dir / "product_identity_reference.json").write_text(
        json.dumps(
            {
                "version": "1.0",
                "reference_id": "product-ref",
                "product_name": "Demo Product",
                "source_type": "generated",
                "approval_status": "pending",
                "selected_reference_image_path": "reference_assets/product_candidate_01.png",
                "candidate_reference_paths": [
                    "reference_assets/product_candidate_01.png",
                    "reference_assets/product_candidate_02.png",
                ],
                "required_visual_features": ["silver body"],
                "prohibited_variations": ["warped logo"],
            }
        )
        + "\n"
    )

    request = _gate_workspace_request()
    request.update(
        {
            "request_id": "product-reference",
            "stage": "assets",
            "gate": "product_reference",
            "title": "Approve product reference",
            "prompt": "Select the product reference image to lock identity.",
            "interaction_kind": "multi_axis_selection",
            "capabilities_needed": ["visual_demonstration", "multi_axis_selection"],
        }
    )

    result = GenUISession().execute(
        {
            "project_dir": str(project_dir),
            "interaction_request": request,
            "mode": "prepare",
        }
    )

    assert result.success, result.error
    config = json.loads(Path(result.data["config_path"]).read_text())
    media_paths = {item["path"] for item in config["media_refs"]}
    assert {
        "/media/reference_assets/product_candidate_01.png",
        "/media/reference_assets/product_candidate_02.png",
    }.issubset(media_paths)
    assert config["metadata"]["review_assets_auto_populated"] is True


def test_genui_session_auto_populates_source_media_review_assets(tmp_path: Path):
    from tools.interaction.genui_session import GenUISession

    project_dir = tmp_path / "projects" / "demo-ad"
    for rel in ["media/source/interview.mp4", "media/source/interview-frame.png"]:
        path = project_dir / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"sample")
    artifacts_dir = project_dir / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    (artifacts_dir / "source_media_review.json").write_text(
        json.dumps(
            {
                "version": "1.0",
                "files": [
                    {
                        "path": "media/source/interview.mp4",
                        "media_type": "video",
                        "reviewed": True,
                        "representative_frames": ["media/source/interview-frame.png"],
                        "content_summary": "Interview footage",
                    }
                ],
                "summary": "Reviewed source media.",
                "planning_implications": ["Use the interview as source footage."],
            }
        )
        + "\n"
    )

    request = _media_review_request()
    request.update(
        {
            "request_id": "source-media-review",
            "stage": "intake",
            "gate": "source_media_review",
            "title": "Review source media",
            "prompt": "Review the supplied source files before planning.",
            "media_items": [],
        }
    )

    result = GenUISession().execute(
        {
            "project_dir": str(project_dir),
            "interaction_request": request,
            "mode": "prepare",
        }
    )

    assert result.success, result.error
    config = json.loads(Path(result.data["config_path"]).read_text())
    media_paths = {item["path"] for item in config["media_refs"]}
    assert {
        "/media/media/source/interview.mp4",
        "/media/media/source/interview-frame.png",
    }.issubset(media_paths)
    assert config["metadata"]["review_assets_auto_populated"] is True


def test_genui_interaction_auto_populates_review_assets_before_session_delegation(tmp_path: Path):
    from tools.interaction.genui_interaction import GenUIInteraction

    project_dir = tmp_path / "projects" / "demo-ad"
    sample_path = project_dir / "renders" / "sample_preview.mp4"
    sample_path.parent.mkdir(parents=True, exist_ok=True)
    sample_path.write_bytes(b"sample")
    artifacts_dir = project_dir / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    (artifacts_dir / "asset_manifest.json").write_text(
        json.dumps({"version": "1.0", "assets": [], "sample_clip": "renders/sample_preview.mp4"}) + "\n"
    )

    request = _media_review_request()
    request["media_items"] = []

    result = GenUIInteraction().execute(
        {
            "project_dir": str(project_dir),
            "interaction_request": request,
            "mode": "prepare",
            "force_genui": True,
        }
    )

    assert result.success, result.error
    config = json.loads(Path(result.data["config_path"]).read_text())
    assert config["media_refs"][0]["path"] == "/media/renders/sample_preview.mp4"
    assert config["metadata"]["review_assets_auto_populated"] is True
    assert config["metadata"]["review_asset_issues"] == []
    assert result.data["delegated_tool"] == "genui_session"


def test_genui_interaction_structured_text_review_does_not_require_media_assets(tmp_path: Path):
    from tools.interaction.genui_interaction import GenUIInteraction

    project_dir = tmp_path / "projects" / "demo-ad"
    request = _gate_workspace_request()
    request.update(
        {
            "request_id": "script-review",
            "stage": "script",
            "gate": "script_review",
            "title": "Review script draft",
            "prompt": "Review the script and capture structured revisions.",
            "interaction_kind": "structured_revision",
            "capabilities_needed": ["structured_revision_capture", "artifact_trace"],
        }
    )

    result = GenUIInteraction().execute(
        {
            "project_dir": str(project_dir),
            "interaction_request": request,
            "mode": "prepare",
        }
    )

    assert result.success, result.error
    config = json.loads(Path(result.data["config_path"]).read_text())
    assert config["mode"] == "gate_workspace"
    assert config["media_refs"] == []
    assert config["metadata"]["review_assets_auto_populated"] is False
    assert any(surface["type"] == "ScriptReviewWorkspace" for surface in config["surfaces"])


def test_genui_interaction_records_cli_and_browser_routing_in_journal(tmp_path: Path):
    from tools.interaction.genui_interaction import GenUIInteraction

    project_dir = tmp_path / "projects" / "demo-ad"
    _write_sample_clip(project_dir)
    tool = GenUIInteraction()

    cli = tool.execute(
        {
            "project_dir": str(project_dir),
            "interaction_request": {
                "request_id": "quick-confirm",
                "project_id": "demo-ad",
                "pipeline_type": "ad-video",
                "stage": "intake",
                "gate": "clarification",
                "title": "Confirm duration",
                "prompt": "Should the video be 15 seconds?",
                "interaction_kind": "clarification",
            },
            "mode": "prepare",
        }
    )
    assert cli.success, cli.error
    assert cli.data["recommended_mode"] == "cli"
    assert cli.data["journal_path"]

    browser = tool.execute(
        {
            "project_dir": str(project_dir),
            "interaction_request": _media_review_request(),
            "mode": "prepare",
        }
    )
    assert browser.success, browser.error
    assert browser.data["genui_contract"] == "genui"
    assert browser.data["session_contract"] == "genui_session"
    assert browser.data["delegated_tool"] == "genui_session"

    journal = json.loads(Path(browser.data["journal_path"]).read_text())
    validate_artifact("ui_interaction_journal", journal)
    assert [entry["interaction_id"] for entry in journal["interactions"]] == [
        "quick-confirm",
        "asset-sample-review",
    ]
    assert journal["interactions"][0]["status"] == "cli_recommended"
    assert journal["interactions"][1]["status"] == "prepared"
    assert journal["interactions"][1]["config_path"] == browser.data["config_path"]
