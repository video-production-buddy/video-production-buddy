import json
import math
import os
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from schemas.artifacts import validate_artifact


ROOT = Path(__file__).resolve().parent.parent.parent
LOCAL_SERVER_TIMEOUT_SECONDS = 5.0


def _media_review_request() -> dict:
    return {
        "request_id": "sample-review-session",
        "project_id": "demo-ad",
        "pipeline_type": "ad-video",
        "stage": "assets",
        "gate": "sample_review",
        "title": "Review generated sample",
        "prompt": "Review the sample clip and capture exact revisions.",
        "interaction_kind": "media_review",
        "capabilities_needed": ["media_review", "structured_revision_capture"],
        "media_items": [
            {
                "id": "sample_clip",
                "title": "Sample clip",
                "kind": "video",
                "path": "/media/renders/sample_clip.mp4",
            }
        ],
    }


def _approval_request() -> dict:
    return {
        "request_id": "proposal-lock-session",
        "project_id": "demo-ad",
        "pipeline_type": "ad-video",
        "stage": "proposal",
        "gate": "proposal_lock",
        "title": "Lock proposal",
        "prompt": "Approve the proposal before script work starts.",
        "interaction_kind": "approval",
        "capabilities_needed": ["approval_gate"],
    }


def _write_project_state(project_dir: Path) -> None:
    artifact_dir = project_dir / "artifacts"
    renders_dir = project_dir / "renders"
    artifact_dir.mkdir(parents=True)
    renders_dir.mkdir(parents=True)
    (project_dir / "checkpoint_proposal.json").write_text(
        '{"stage":"proposal","status":"approved","approved":true}\n'
    )
    (project_dir / "checkpoint_script.json").write_text(
        '{"stage":"script","status":"awaiting_human","approved":false}\n'
    )
    (artifact_dir / "decision_log.json").write_text(
        '{"decisions":[{"id":"runtime","category":"render_runtime_selection","selected":"remotion","stage":"proposal"}]}\n'
    )
    (artifact_dir / "production_proposal.json").write_text(
        '{"render_runtime":"remotion","budget":{"approved_budget_usd":150},"cost_estimate":{"total_usd":82.5}}\n'
    )
    (renders_dir / "sample_clip.mp4").write_bytes(b"sample")
    ui_dir = artifact_dir / "ui" / "stale-session"
    ui_dir.mkdir(parents=True)
    (ui_dir / "server.json").write_text(
        json.dumps(
            {
                "session_id": "stale-session",
                "server_state": "running",
                "url": "http://127.0.0.1:65534/",
                "response_path": str(ui_dir / "response.json"),
            }
        )
        + "\n"
    )
    (artifact_dir / "ui" / "pending-session").mkdir(parents=True)
    (artifact_dir / "ui" / "pending-session" / "config.json").write_text(
        '{"session_id":"pending-session","project_id":"demo-ad","pipeline_type":"ad-video"}\n'
    )


def _write_valid_session_response(response_path: Path) -> None:
    response_path.parent.mkdir(parents=True, exist_ok=True)
    response_path.write_text(
        json.dumps(
            {
                "contract": "genui_session_response",
                "response_id": "resp-asset-sample-review",
                "session_id": "asset-sample-review",
                "project_id": "demo-ad",
                "pipeline_type": "ad-video",
                "stage": "assets",
                "gate": "sample_review",
                "submitted_at": "2026-06-18T00:00:00+00:00",
                "action": "approve",
                "values": {"approved": True},
                "issues": [],
                "interaction_evidence": {
                    "media_opened": ["sample_clip"],
                    "timeline_inspected": ["sample_clip"],
                    "seconds_watched": 3.5,
                },
                "validation": {"status": "valid", "errors": []},
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def test_genui_session_config_declares_stable_product_contract():
    from lib.genui.session import build_dynamic_session_config, compile_session_view_spec

    config = build_dynamic_session_config(_media_review_request())

    validate_artifact("ui_session_config", config)
    assert config["contract"] == "genui_session"
    assert config["metadata"]["genui_contract"] == "genui"
    assert config["decision_id"] == "decision-sample-review-session"
    assert config["stage_policy_id"] == "ad-video.sample_review"
    assert config["schema_strategy"] == "fixed"
    assert config["resume_token"].startswith("resume-sample-review-session-")
    assert config["expires_at"].endswith("+00:00")
    assert config["source_artifact_hashes"] == {}
    assert not [key for key in config["metadata"] if key.startswith("genui_v")]

    spec = compile_session_view_spec(config)
    assert spec["contract"] == "genui_session_view"
    assert spec["metadata"]["genui_contract"] == "genui"
    assert spec["metadata"]["decision_id"] == config["decision_id"]
    assert spec["state"]["session"]["genui_contract"] == "genui"


def test_stage_policy_promotes_known_approval_gates_to_fixed_schema_genui():
    from lib.genui.interaction_policy import assess_interaction_need

    decision = assess_interaction_need(_approval_request())

    assert decision["recommended_mode"] == "gate_workspace"
    assert decision["stage_policy_id"] == "ad-video.proposal_lock"
    assert decision["schema_strategy"] == "fixed"
    assert decision["linear_chat_sufficient"] is False
    assert "stage_policy_required" in decision["reasons"]
    assert "approval_attestation" in decision["required_ui_primitives"]


def test_generic_visual_round_remains_dynamic_schema_without_stage_policy():
    from lib.genui.session import build_dynamic_session_config, compile_session_view_spec

    request = {
        "request_id": "generic-visual-selection-session",
        "project_id": "demo-ad",
        "pipeline_type": "ad-video",
        "stage": "ideas",
        "gate": "visual_choice",
        "title": "Choose a visual direction",
        "prompt": "Compare three visual directions and capture rationale.",
        "interaction_kind": "option_comparison",
        "capabilities_needed": ["side_by_side_comparison", "multi_axis_selection"],
        "choices": [
            {"value": "a", "label": "Direction A"},
            {"value": "b", "label": "Direction B"},
            {"value": "c", "label": "Direction C"},
        ],
    }

    config = build_dynamic_session_config(request)

    validate_artifact("ui_session_config", config)
    assert config["schema_strategy"] == "dynamic"
    assert "stage_policy_id" not in config
    assert config["visual_need_assessment"]["recommended_mode"] == "gate_workspace"
    assert config["visual_need_assessment"]["linear_chat_sufficient"] is False
    spec = compile_session_view_spec(config)
    assert "stage_policy_id" not in spec["state"]["session"]
    assert "stage_policy_id" not in spec["metadata"]


def test_session_project_cockpit_uses_rich_project_snapshot(tmp_path: Path):
    from lib.genui.session import build_project_cockpit_session_config, compile_session_view_spec

    project_dir = tmp_path / "projects" / "demo-ad"
    _write_project_state(project_dir)

    config = build_project_cockpit_session_config(
        project_dir,
        project_id="demo-ad",
        pipeline_type="ad-video",
        active_stage="proposal",
    )
    validate_artifact("ui_session_config", config)
    assert config["mode"] == "project_cockpit"
    assert len(config["artifact_refs"]) >= 2
    assert any(ref["path"] == "/media/renders/sample_clip.mp4" for ref in config["media_refs"])
    assert config["metadata"]["project_snapshot"]["pending_response_count"] == 1
    assert config["metadata"]["project_snapshot"]["stale_session_count"] == 1

    spec = compile_session_view_spec(config)
    cockpit = next(component for component in spec["a2ui"]["components"] if component["type"] == "ProjectCockpit")
    props = cockpit["props"]
    assert props["timelineItems"][0]["id"] == "research"
    assert any(
        item["id"] == "proposal"
        and item["status"] == "approved"
        and item["checkpoint"] == "checkpoint_proposal.json"
        for item in props["timelineItems"]
    )
    assert any(item["artifact"] == "production_proposal" for item in props["artifactItems"])
    assert props["decisionItems"][0]["category"] == "render_runtime_selection"
    assert props["budgetCostItems"][0]["approved_budget_usd"] == 150
    assert props["pendingResponses"][0]["session_id"] == "pending-session"
    assert props["staleSessions"][0]["session_id"] == "stale-session"


def test_project_cockpit_snapshot_marks_non_strict_artifacts_unreadable(tmp_path: Path):
    from lib.genui.project_snapshot import build_project_cockpit_snapshot

    project_dir = tmp_path / "projects" / "demo-ad"
    artifact_dir = project_dir / "artifacts"
    artifact_dir.mkdir(parents=True)
    (artifact_dir / "production_proposal.json").write_text(
        '{"render_runtime":"remotion","budget":{"approved_budget_usd":NaN}}\n'
    )

    snapshot = build_project_cockpit_snapshot(
        project_dir,
        pipeline_type="ad-video",
        active_stage="proposal",
    )

    proposal_item = next(
        item for item in snapshot["artifact_items"] if item["artifact"] == "production_proposal"
    )
    assert proposal_item["status"] == "unreadable"
    assert snapshot["budget_cost_items"] == []


def test_session_ag_ui_events_include_operation_lifecycle_cards():
    from lib.genui.session import (
        build_dynamic_session_config,
        build_ag_ui_session_events,
        compile_session_view_spec,
    )

    config = build_dynamic_session_config(_media_review_request())
    spec = compile_session_view_spec(config)
    events = build_ag_ui_session_events(config, spec["state"])
    event_types = [event["type"] for event in events]

    assert "RUN_STARTED" in event_types
    assert "STEP_STARTED" in event_types
    assert "TOOL_CALL_START" in event_types
    assert "TOOL_CALL_END" in event_types
    assert "STATE_DELTA" in event_types
    assert "STEP_FINISHED" in event_types
    tool_events = [event for event in events if event["type"].startswith("TOOL_CALL")]
    assert tool_events[0]["toolCallName"] == "genui_session.prepare"
    assert tool_events[-1]["toolCallName"] == "genui_session.await_response"


def test_session_session_response_records_resume_decision_completion_and_conflict_status():
    from lib.genui.session import build_dynamic_session_config, session_response_payload_from_submission

    config = build_dynamic_session_config(_approval_request())
    gate_id = next(
        surface["id"]
        for surface in config["surfaces"]
        if "approval_attested" in surface.get("required_evidence", [])
    )
    response = session_response_payload_from_submission(
        config,
        {
            "action": "approve",
            "values": {},
            "approval_attestations": [
                {"id": gate_id, "label": "I reviewed and approve this workspace.", "approved": True}
            ],
            "interaction_evidence": {"media_opened": [], "timeline_inspected": [], "seconds_watched": 0},
            "browser_events": [{"type": "submit_attempt"}],
        },
        response_id="resp-proposal-lock-session",
    )

    validate_artifact("ui_session_response", response)
    assert response["resume_decision"] == {
        "decision_id": "decision-proposal-lock-session",
        "resume_token": config["resume_token"],
        "action": "approve",
    }
    assert response["review_completion"]["status"] == "complete"
    assert response["review_completion"]["missing_required_evidence"] == []
    assert response["conflict_status"]["status"] == "not_checked"


def test_genui_verify_target_documents_product_workflow():
    makefile = (ROOT / "Makefile").read_text()

    assert "genui-verify:" in makefile
    assert "tests/contracts/test_genui_session_contract.py" in makefile
    assert "tests/contracts/test_genui_session_hardening.py" in makefile
    assert "tests/tools/test_genui_surface_browser.py" in makefile
    assert "pnpm --dir genui-renderer test" in makefile
    assert "pnpm --dir genui-renderer typecheck" in makefile
    assert "pnpm --dir genui-renderer build" in makefile
    assert "git diff --exit-code -- lib/genui/static/renderer" in makefile


def test_genui_evidence_check_target_documents_agent_command():
    makefile = (ROOT / "Makefile").read_text()

    assert "genui-evidence-check:" in makefile
    assert "PROJECT=projects/<project-id>" in makefile
    assert "PIPELINE=ad-video" in makefile
    assert "STAGE=assets" in makefile
    assert " -m tools.validation.genui_evidence_check" in makefile
    assert "PYTHONDONTWRITEBYTECODE=1" in makefile


def test_makefile_pytest_targets_disable_browser_opening():
    makefile = (ROOT / "Makefile").read_text()
    pytest_lines = [
        line.strip()
        for line in makefile.splitlines()
        if " -m pytest" in line
    ]

    assert pytest_lines
    assert all(line.startswith("VPB_ALLOW_BROWSER_OPEN=0 ") for line in pytest_lines)


def test_makefile_genui_renderer_tests_disable_browser_opening():
    makefile = (ROOT / "Makefile").read_text()
    renderer_test_lines = [
        line.strip()
        for line in makefile.splitlines()
        if "pnpm --dir genui-renderer test" in line
    ]

    assert renderer_test_lines
    assert all(line.startswith("VPB_ALLOW_BROWSER_OPEN=0 ") for line in renderer_test_lines)


def test_makefile_pytest_targets_keep_test_artifacts_out_of_checkout():
    makefile = (ROOT / "Makefile").read_text()
    pytest_lines = [
        line.strip()
        for line in makefile.splitlines()
        if " -m pytest" in line
    ]

    assert pytest_lines
    assert all("PYTHONDONTWRITEBYTECODE=1 " in line for line in pytest_lines)
    assert all(" -p no:cacheprovider " in f" {line} " for line in pytest_lines)


def test_direct_pytest_runs_default_to_browser_open_disabled():
    assert os.environ.get("VPB_ALLOW_BROWSER_OPEN") == "0"


def _sse_events(text: str) -> list[dict]:
    events: list[dict] = []
    for chunk in text.split("\n\n"):
        data_line = next((line for line in chunk.splitlines() if line.startswith("data: ")), None)
        if data_line:
            events.append(json.loads(data_line.removeprefix("data: ")))
    return events


def test_session_session_events_are_persisted_cursorable_and_status_addressable(tmp_path: Path):
    from lib.genui import cleanup_server
    from tools.interaction.genui_session import GenUISession

    project_dir = tmp_path / "projects" / "demo-ad"
    (project_dir / "renders").mkdir(parents=True)
    (project_dir / "renders" / "sample_clip.mp4").write_bytes(b"sample")

    result = GenUISession().execute(
        {
            "project_dir": str(project_dir),
            "interaction_request": _media_review_request(),
            "mode": "serve",
        }
    )
    assert result.success, result.error
    response_path = Path(result.data["response_path"])
    state_path = Path(result.data["state_path"])
    events_path = Path(result.data["events_path"])
    base_url = result.data["url"].rstrip("/")

    try:
        events_response = urllib.request.urlopen(f"{base_url}/events", timeout=LOCAL_SERVER_TIMEOUT_SECONDS)
        events_text = events_response.read().decode("utf-8")
        events = _sse_events(events_text)
        assert events_path.exists()
        assert events_response.headers["X-GenUI-Event-Cursor"] == events[-1]["cursor"]
        assert [event["sequence"] for event in events] == list(range(1, len(events) + 1))
        assert all(event["cursor"].startswith("sample-review-session:") for event in events)
        assert all("emitted_at" in event for event in events)

        replay_text = urllib.request.urlopen(
            f"{base_url}/events?after={events[-1]['cursor']}",
            timeout=LOCAL_SERVER_TIMEOUT_SECONDS,
        ).read().decode("utf-8")
        assert _sse_events(replay_text) == []

        session_status = json.loads(
            urllib.request.urlopen(f"{base_url}/session.json", timeout=LOCAL_SERVER_TIMEOUT_SECONDS).read().decode("utf-8")
        )
        assert session_status["session_id"] == "sample-review-session"
        assert session_status["genui_contract"] == "genui"
        assert session_status["event_count"] == len(events)
        assert session_status["event_cursor"] == events[-1]["cursor"]
        assert session_status["events_path"] == str(events_path)
        assert session_status["response_exists"] is False
        assert result.data["session_url"] == f"{base_url}/session.json"
        assert result.data["status_url"] == f"{base_url}/events"
    finally:
        cleanup_server(state_path)
        assert not response_path.exists()


def test_session_event_append_rejects_non_finite_event_before_mutating_log(tmp_path: Path):
    from lib.genui.session import (
        append_session_event,
        build_dynamic_session_config,
        write_session_events,
    )

    config = build_dynamic_session_config(_approval_request())
    events_path = tmp_path / "events.jsonl"
    write_session_events(
        events_path,
        [{"type": "RUN_STARTED", "sequence": 1, "cursor": "proposal-lock-session:000001"}],
    )
    before = events_path.read_text(encoding="utf-8")

    with pytest.raises(ValueError, match="non-finite JSON number"):
        append_session_event(
            events_path,
            config,
            {"type": "STATE_DELTA", "delta": {"non_finite": math.nan}},
        )

    assert events_path.read_text(encoding="utf-8") == before


def test_session_event_batch_write_rejects_non_finite_event_before_creating_log(tmp_path: Path):
    from lib.genui.session import write_session_events

    events_path = tmp_path / "events.jsonl"

    with pytest.raises(ValueError, match="non-finite JSON number"):
        write_session_events(
            events_path,
            [
                {"type": "RUN_STARTED", "sequence": 1, "cursor": "review:000001"},
                {"type": "STATE_DELTA", "delta": {"non_finite": math.nan}},
            ],
        )

    assert not events_path.exists()


def test_interaction_journal_write_rejects_unserializable_metadata_before_mutating_file(tmp_path: Path):
    from lib.genui.journal import build_interaction_journal, write_interaction_journal

    project_dir = tmp_path / "projects" / "demo-ad"
    journal = build_interaction_journal(project_id="demo-ad", pipeline_type="ad-video")
    journal_path = write_interaction_journal(project_dir, journal)
    before = journal_path.read_text(encoding="utf-8")

    journal["metadata"]["not_json"] = tmp_path / "unserializable-path"
    with pytest.raises(ValueError, match="strict JSON serializable"):
        write_interaction_journal(project_dir, journal)

    assert journal_path.read_text(encoding="utf-8") == before


def test_required_gate_evidence_report_accepts_schema_valid_session_response(tmp_path: Path):
    from lib.genui.journal import (
        build_interaction_journal,
        entry_from_request_decision,
        genui_required_gate_evidence_report,
        write_interaction_journal,
    )

    project_dir = tmp_path / "projects" / "demo-ad"
    response_path = (
        project_dir / "artifacts" / "ui" / "asset-sample-review" / "response.json"
    )
    _write_valid_session_response(response_path)
    request = _media_review_request()
    decision = {
        "recommended_mode": "media_review_room",
        "recommended_tool": "genui_session",
        "linear_chat_sufficient": False,
        "interaction_kind": "media_review",
        "reasons": ["media_review"],
    }
    entry = entry_from_request_decision(
        request,
        decision,
        status="submitted",
        session_data={
            "session_id": "asset-sample-review",
            "session_contract": "genui_session",
            "response_path": str(response_path),
        },
    )
    journal = build_interaction_journal(
        project_id="demo-ad",
        pipeline_type="ad-video",
        entries=[entry],
    )
    write_interaction_journal(project_dir, journal)

    report = genui_required_gate_evidence_report(
        project_dir,
        project_id="demo-ad",
        pipeline_type="ad-video",
        required_gates=[{"stage": "assets", "gate": "sample_review"}],
    )

    assert report["ok"] is True
    assert report["issues"] == []
    assert report["evidence"][0]["evidence_type"] == "genui_response"
    assert report["evidence"][0]["response_contract"] == "genui_session_response"


def test_required_gate_evidence_report_accepts_explicit_genui_fallback(tmp_path: Path):
    from lib.genui.journal import (
        build_interaction_journal,
        entry_from_request_decision,
        genui_required_gate_evidence_report,
        write_interaction_journal,
    )

    project_dir = tmp_path / "projects" / "demo-ad"
    request = _media_review_request()
    decision = {
        "recommended_mode": "media_review_room",
        "recommended_tool": "genui_session",
        "linear_chat_sufficient": False,
        "interaction_kind": "media_review",
        "reasons": ["media_review"],
    }
    entry = entry_from_request_decision(
        request,
        decision,
        status="fallback",
        fallback_reason="genui_session serve failed; user_declined_browser_path",
    )
    journal = build_interaction_journal(
        project_id="demo-ad",
        pipeline_type="ad-video",
        entries=[entry],
    )
    write_interaction_journal(project_dir, journal)

    report = genui_required_gate_evidence_report(
        project_dir,
        project_id="demo-ad",
        pipeline_type="ad-video",
        required_gates=["assets:sample_review"],
    )

    assert report["ok"] is True
    assert report["evidence"][0]["evidence_type"] == "genui_fallback"
    assert "genui_session" in report["evidence"][0]["fallback_reason"]


def test_required_gate_evidence_report_rejects_agent_native_ui_bypass(tmp_path: Path):
    from lib.genui.journal import (
        build_interaction_journal,
        entry_from_request_decision,
        genui_required_gate_evidence_report,
        write_interaction_journal,
    )

    project_dir = tmp_path / "projects" / "demo-ad"
    request = _media_review_request()
    decision = {
        "recommended_mode": "media_review_room",
        "recommended_tool": "genui_session",
        "linear_chat_sufficient": False,
        "interaction_kind": "media_review",
        "reasons": ["media_review"],
    }
    entry = entry_from_request_decision(
        request,
        decision,
        status="fallback",
        fallback_reason="AskUserQuestion captured media review",
    )
    journal = build_interaction_journal(
        project_id="demo-ad",
        pipeline_type="ad-video",
        entries=[entry],
    )
    write_interaction_journal(project_dir, journal)

    report = genui_required_gate_evidence_report(
        project_dir,
        project_id="demo-ad",
        pipeline_type="ad-video",
        required_gates=[{"stage": "assets", "gate": "sample_review"}],
    )

    assert report["ok"] is False
    issue = report["issues"][0]
    assert issue["code"] == "missing_genui_gate_evidence"
    assert issue["entry_evaluations"][0]["ok"] is False
    assert any(
        "fallback_reason does not document" in error
        for error in issue["entry_evaluations"][0]["errors"]
    )


def test_session_bundle_write_rejects_unserializable_metadata_before_mutating_config(tmp_path: Path):
    from lib.genui.session import build_dynamic_session_config, write_session_bundle

    project_dir = tmp_path / "projects" / "demo-ad"
    config = build_dynamic_session_config(_approval_request())
    bundle = write_session_bundle(project_dir, config)
    before = bundle.config_path.read_text(encoding="utf-8")

    config["metadata"]["not_json"] = tmp_path / "unserializable-path"
    with pytest.raises(ValueError, match="strict JSON serializable"):
        write_session_bundle(project_dir, config)

    assert bundle.config_path.read_text(encoding="utf-8") == before


def test_surface_bundle_write_rejects_unserializable_metadata_before_mutating_config(tmp_path: Path):
    from lib.genui.surface import build_dynamic_surface_config, write_surface_bundle

    project_dir = tmp_path / "projects" / "demo-ad"
    config = build_dynamic_surface_config(_approval_request())
    bundle = write_surface_bundle(project_dir, config)
    before = bundle.config_path.read_text(encoding="utf-8")

    config["metadata"]["not_json"] = tmp_path / "unserializable-path"
    with pytest.raises(ValueError, match="strict JSON serializable"):
        write_surface_bundle(project_dir, config)

    assert bundle.config_path.read_text(encoding="utf-8") == before


def test_surface_event_snapshot_rejects_non_finite_event_before_creating_log(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    from lib.genui import surface as surface_module
    from lib.genui.server import GenUIRequestHandler

    events_path = tmp_path / "events.jsonl"

    class SurfaceOnlyHandler:
        config = {"surface_id": "surface-review", "version": "2.0"}
        response_path = tmp_path / "response.json"
        draft_path = tmp_path / "draft.json"
        view_spec_path = tmp_path / "view_spec.json"
        submit_nonce = "nonce"

        def _load_spec_state(self):
            return {"values": {}}

        def _is_session_config(self):
            return False

    handler = SurfaceOnlyHandler()
    handler.events_path = events_path
    monkeypatch.setattr(
        surface_module,
        "build_ag_ui_events",
        lambda config, state: [{"type": "STATE_SNAPSHOT", "value": math.nan}],
    )

    with pytest.raises(ValueError, match="strict JSON"):
        GenUIRequestHandler._session_events(handler)

    assert not events_path.exists()


def test_genui_server_view_spec_state_loader_rejects_non_strict_json(tmp_path: Path):
    from lib.genui.server import GenUIRequestHandler
    from lib.genui.session import build_dynamic_session_config, compile_session_view_spec

    spec = compile_session_view_spec(build_dynamic_session_config(_approval_request()))
    spec["metadata"]["non_strict_probe"] = "replace-with-nan"
    spec_text = json.dumps(spec, allow_nan=False).replace('"replace-with-nan"', "NaN")
    view_spec_path = tmp_path / "view_spec.json"
    view_spec_path.write_text(spec_text + "\n")

    handler = type("ViewSpecOnlyHandler", (), {"view_spec_path": view_spec_path})()
    with pytest.raises(ValueError, match="Invalid non-standard JSON constant 'NaN'"):
        GenUIRequestHandler._load_spec_state(handler)


def test_session_session_rejects_foreign_submit_origin(tmp_path: Path):
    from lib.genui import cleanup_server
    from tools.interaction.genui_session import GenUISession

    project_dir = tmp_path / "projects" / "demo-ad"
    (project_dir / "renders").mkdir(parents=True)
    (project_dir / "renders" / "sample_clip.mp4").write_bytes(b"sample")

    result = GenUISession().execute(
        {
            "project_dir": str(project_dir),
            "interaction_request": _media_review_request(),
            "mode": "serve",
        }
    )
    assert result.success, result.error
    response_path = Path(result.data["response_path"])
    state_path = Path(result.data["state_path"])
    base_url = result.data["url"].rstrip("/")
    spec = json.loads(urllib.request.urlopen(f"{base_url}/spec.json", timeout=LOCAL_SERVER_TIMEOUT_SECONDS).read().decode("utf-8"))
    payload = json.dumps(
        {
            "action": "abort",
            "nonce": spec["metadata"]["submit_nonce"],
            "values": {},
            "interaction_evidence": {"media_opened": [], "timeline_inspected": [], "seconds_watched": 0},
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        f"{base_url}/submit",
        data=payload,
        method="POST",
        headers={"Content-Type": "application/json", "Origin": "http://evil.example"},
    )
    try:
        with pytest.raises(urllib.error.HTTPError) as caught:
            urllib.request.urlopen(request, timeout=LOCAL_SERVER_TIMEOUT_SECONDS)
        assert caught.value.code == 403
        assert not response_path.exists()
    finally:
        cleanup_server(state_path)
