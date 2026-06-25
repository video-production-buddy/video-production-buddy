import hashlib
import json
import re
import subprocess
import urllib.request
from pathlib import Path

import pytest

from schemas.artifacts import validate_artifact


ROOT = Path(__file__).resolve().parent.parent.parent
LOCAL_SERVER_TIMEOUT_SECONDS = 5.0


def _tracked_genui_public_files() -> list[Path]:
    output = subprocess.check_output(["git", "ls-files"], cwd=ROOT, text=True)
    included: list[Path] = []
    exact = {
        "AGENT_GUIDE.md",
        "PROJECT_CONTEXT.md",
        "docs/ARCHITECTURE.md",
        "skills/meta/genui-interaction.md",
        "Makefile",
    }
    prefixes = (
        "lib/genui/",
        "genui-renderer/src/",
        "tools/interaction/genui",
        "schemas/artifacts/ui_",
        "schemas/genui/",
        "tests/contracts/test_genui_",
        "tests/tools/test_genui_",
    )
    for rel in output.splitlines():
        if rel in exact or rel.startswith(prefixes):
            included.append(ROOT / rel)
    return included


def test_genui_public_surface_hides_release_iteration_labels():
    forbidden = {
        "GenUI release label": re.compile(r"GenUI " + r"v[0-9]"),
        "GenUI snake release flag": re.compile("genui_" + r"v[0-9]"),
        "GenUI slug release label": re.compile("genui-" + r"v[0-9]"),
        "Video Production Buddy GenUI release catalog": re.compile("video-production-buddy-genui-" + r"v[0-9]"),
        "renderer release CSS class": re.compile("om-" + r"v[0-9]"),
        "legacy product version field": re.compile("genui" + "_product" + "_version"),
        "legacy product version constant": re.compile("GENUI" + "_PRODUCT" + "_VERSION"),
        "legacy compatible product field": re.compile("compatible" + "_product" + "_versions"),
        "legacy requested GenUI version field": re.compile("genui" + "_version"),
        "legacy session version field": re.compile("session" + "_version"),
        "legacy surface version field": re.compile("surface" + "_version"),
    }
    violations: list[str] = []
    for path in _tracked_genui_public_files():
        if not path.exists() or path.is_dir():
            continue
        text = path.read_text(encoding="utf-8")
        for label, pattern in forbidden.items():
            for match in pattern.finditer(text):
                line = text.count("\n", 0, match.start()) + 1
                violations.append(f"{path.relative_to(ROOT)}:{line}: {label}: {match.group(0)}")

    assert violations == []


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _proposal_request(**overrides: object) -> dict:
    request = {
        "request_id": "proposal-lock-product",
        "project_id": "demo-ad",
        "pipeline_type": "ad-video",
        "stage": "proposal",
        "gate": "proposal_lock",
        "title": "Lock production proposal",
        "prompt": "Review proposal details and approve before script work.",
        "interaction_kind": "approval",
        "capabilities_needed": ["structured_revision_capture", "approval_gate"],
        "fields": [
            {
                "id": "approval_notes",
                "label": "Approval notes",
                "type": "textarea",
                "binding": {
                    "artifact": "production_proposal",
                    "path": "human_feedback.approval_notes",
                },
            }
        ],
    }
    request.update(overrides)
    return request


def _approval_submission(surface_id: str, *, action: str = "approve", values: dict | None = None) -> dict:
    return {
        "action": action,
        "values": values or {},
        "approval_attestations": [
            {"id": surface_id, "label": "I reviewed and approve this workspace.", "approved": True}
        ],
        "interaction_evidence": {
            "media_opened": [],
            "timeline_inspected": [],
            "seconds_watched": 0,
        },
        "browser_events": [{"type": "submit_attempt", "action": action}],
    }


def test_genui_product_keeps_stable_session_contract_with_product_metadata():
    from lib.genui.session import build_dynamic_session_config, compile_session_view_spec

    config = build_dynamic_session_config(_proposal_request())

    validate_artifact("ui_session_config", config)
    assert config["contract"] == "genui_session"
    assert config["metadata"]["genui_contract"] == "genui"
    assert config["workspace_kind"] == "proposal_lock"
    assert config["event_stream"]["transport"] == "sse"
    assert config["draft_state"]["path"] == "draft.json"
    assert config["conflict_policy"]["source_hash_check"] == "on_submit"
    assert not [key for key in config["metadata"] if key.startswith("genui_v")]
    assert "compatible_contracts" not in config["metadata"]

    proposal_surface = next(surface for surface in config["surfaces"] if surface["type"] == "ProposalLock")
    assert proposal_surface["contract"]["workspace_kind"] == "proposal_lock"
    assert proposal_surface["contract"]["canonical_writes"] is False
    assert proposal_surface["contract"]["response_artifact"] == "ui_session_response"
    assert proposal_surface["contract"]["allowed_actions"] == ["approve", "revise", "abort"]

    spec = compile_session_view_spec(config)
    assert spec["contract"] == "genui_session_view"
    assert spec["metadata"]["genui_contract"] == "genui"
    assert spec["metadata"]["workspace_kind"] == "proposal_lock"
    assert spec["state"]["session"]["genui_contract"] == "genui"


def test_genui_product_runtime_selection_uses_fixed_workspace_contract():
    from lib.genui.session import build_dynamic_session_config

    config = build_dynamic_session_config(
        _proposal_request(
            request_id="runtime-selection-product",
            gate="runtime_selection",
            interaction_kind="option_comparison",
            capabilities_needed=["side_by_side_comparison", "structured_revision_capture"],
            choices=[
                {"value": "remotion", "label": "Remotion", "recommended": True},
                {"value": "hyperframes", "label": "HyperFrames"},
            ],
            selection_field_id="render_runtime",
            selection_binding={
                "artifact": "production_proposal",
                "path": "visual_contract.render_runtime",
            },
        )
    )

    assert config["stage_policy_id"] == "ad-video.runtime_selection"
    assert config["workspace_kind"] == "runtime_selection"
    workspace = next(surface for surface in config["surfaces"] if surface["type"] == "GateWorkspace")
    assert workspace["workspace_kind"] == "runtime_selection"
    assert workspace["contract"]["workspace_kind"] == "runtime_selection"
    assert "approval_attested" in workspace["required_evidence"]


def test_genui_product_product_media_review_requires_approval_evidence():
    from lib.genui.session import build_dynamic_session_config

    config = build_dynamic_session_config(
        _proposal_request(
            request_id="product-reference-product",
            gate="product_reference",
            interaction_kind="media_review",
            capabilities_needed=["media_review"],
            media_items=[
                {"id": "reference_frame", "title": "Reference frame", "kind": "image", "path": "renders/reference.png"}
            ],
        )
    )

    assert config["stage_policy_id"] == "ad-video.product_reference"
    assert config["workspace_kind"] == "product_reference"
    product_surface = next(surface for surface in config["surfaces"] if surface["type"] == "ProductReferenceApproval")
    assert "approval_attested" in product_surface["required_evidence"]
    assert "approval_attested" in product_surface["contract"]["required_evidence"]
    review_room = next(surface for surface in config["surfaces"] if surface["type"] == "MediaReviewRoom")
    assert review_room["contract"]["required_evidence"] == ["media_opened", "timeline_inspected"]


def test_genui_product_product_reference_blocks_when_no_review_media(tmp_path: Path):
    from tools.interaction.genui_session import GenUISession

    project_dir = tmp_path / "projects" / "demo-ad"
    result = GenUISession().execute(
        {
            "project_dir": str(project_dir),
            "interaction_request": _proposal_request(
                request_id="product-reference-missing-media-product",
                stage="assets",
                gate="product_reference",
                interaction_kind="approval",
                capabilities_needed=["approval_gate"],
            ),
            "mode": "prepare",
        }
    )

    assert result.success is False
    assert "requires at least one browser-reviewable media item" in result.error


def test_genui_product_checks_source_artifact_hashes_on_submission(tmp_path: Path):
    from lib.genui.session import build_dynamic_session_config, session_response_payload_from_submission

    project_dir = tmp_path / "projects" / "demo-ad"
    artifact_path = project_dir / "artifacts" / "production_proposal.json"
    artifact_path.parent.mkdir(parents=True)
    artifact_path.write_text('{"render_runtime":"remotion"}\n')
    clean_hash = _sha256(artifact_path)

    config = build_dynamic_session_config(
        _proposal_request(source_artifact_hashes={"artifacts/production_proposal.json": clean_hash})
    )
    proposal_surface = next(surface for surface in config["surfaces"] if surface["type"] == "ProposalLock")

    clean = session_response_payload_from_submission(
        config,
        _approval_submission(proposal_surface["id"]),
        response_id="resp-clean",
        project_dir=project_dir,
    )
    assert clean["conflict_status"]["status"] == "clean"
    assert clean["conflict_status"]["conflicting_artifacts"] == []

    artifact_path.write_text('{"render_runtime":"hyperframes"}\n')
    conflicted = session_response_payload_from_submission(
        config,
        _approval_submission(proposal_surface["id"]),
        response_id="resp-conflict",
        project_dir=project_dir,
    )
    assert conflicted["conflict_status"]["status"] == "conflict"
    assert conflicted["conflict_status"]["conflicting_artifacts"] == ["artifacts/production_proposal.json"]


def test_genui_product_auto_hashes_bound_source_artifacts_for_real_sessions(tmp_path: Path):
    from lib.genui.session import session_response_payload_from_submission
    from tools.interaction.genui_session import GenUISession

    project_dir = tmp_path / "projects" / "demo-ad"
    artifact_path = project_dir / "artifacts" / "production_proposal.json"
    artifact_path.parent.mkdir(parents=True)
    artifact_path.write_text('{"render_runtime":"remotion"}\n')

    result = GenUISession().execute(
        {
            "project_dir": str(project_dir),
            "interaction_request": _proposal_request(request_id="auto-source-hash-product"),
            "mode": "prepare",
        }
    )

    assert result.success, result.error
    config = json.loads(Path(result.data["config_path"]).read_text())
    assert config["source_artifact_hashes"] == {"production_proposal": _sha256(artifact_path)}

    proposal_surface = next(surface for surface in config["surfaces"] if surface["type"] == "ProposalLock")
    clean = session_response_payload_from_submission(
        config,
        _approval_submission(proposal_surface["id"]),
        response_id="resp-auto-hash-clean",
        project_dir=project_dir,
    )
    assert clean["conflict_status"]["status"] == "clean"

    artifact_path.write_text('{"render_runtime":"hyperframes"}\n')
    conflicted = session_response_payload_from_submission(
        config,
        _approval_submission(proposal_surface["id"]),
        response_id="resp-auto-hash-conflict",
        project_dir=project_dir,
    )
    assert conflicted["conflict_status"]["status"] == "conflict"
    assert conflicted["conflict_status"]["conflicting_artifacts"] == ["production_proposal"]


def test_genui_product_enforces_required_and_visible_if_fields():
    from lib.genui.session import build_dynamic_session_config, session_response_payload_from_submission

    config = build_dynamic_session_config(
        _proposal_request(
            request_id="conditional-fields-product",
            fields=[
                {
                    "id": "needs_revision",
                    "label": "Needs revision",
                    "type": "checkbox",
                    "required": False,
                },
                {
                    "id": "revision_notes",
                    "label": "Revision notes",
                    "type": "textarea",
                    "required": True,
                    "visible_if": {
                        "field": "needs_revision",
                        "operator": "equals",
                        "value": True,
                    },
                    "binding": {
                        "artifact": "production_proposal",
                        "path": "human_feedback.revision_notes",
                    },
                },
            ],
        )
    )
    proposal_surface = next(surface for surface in config["surfaces"] if surface["type"] == "ProposalLock")

    with pytest.raises(ValueError, match="required value"):
        session_response_payload_from_submission(
            config,
            _approval_submission(
                proposal_surface["id"],
                values={"needs_revision": True, "revision_notes": ""},
            ),
        )

    with pytest.raises(ValueError, match="hidden value"):
        session_response_payload_from_submission(
            config,
            _approval_submission(
                proposal_surface["id"],
                action="revise",
                values={"needs_revision": False, "revision_notes": "This stale hidden value must not submit."},
            ),
        )


def test_genui_product_materializes_draft_file_and_replay_events(tmp_path: Path):
    from lib.genui.session import build_dynamic_session_config, ensure_session_events, write_session_bundle

    project_dir = tmp_path / "projects" / "demo-ad"
    config = build_dynamic_session_config(_proposal_request())
    bundle = write_session_bundle(project_dir, config)

    assert bundle.draft_path == bundle.response_path.with_name("draft.json")
    assert not bundle.draft_path.exists()
    stored_config = json.loads(bundle.config_path.read_text())
    assert stored_config["draft_state"]["path"] == "draft.json"

    spec = json.loads(bundle.view_spec_path.read_text())
    events = ensure_session_events(bundle.events_path, stored_config, spec["state"])
    event_types = [event["type"] for event in events]
    assert "GENUI_SESSION_READY" in event_types
    assert "STATE_SNAPSHOT" in event_types
    assert all(event["cursor"].startswith("proposal-lock-product:") for event in events)


def test_genui_product_server_draft_endpoint_is_response_only(tmp_path: Path):
    from tools.interaction.genui_session import GenUISession

    project_dir = tmp_path / "projects" / "demo-ad"
    result = GenUISession().execute(
        {
            "project_dir": str(project_dir),
            "interaction_request": _proposal_request(request_id="draft-endpoint-product"),
            "mode": "serve",
        }
    )
    assert result.success, result.error
    url = result.data["url"].rstrip("/")
    response_path = Path(result.data["response_path"])
    draft_path = Path(result.data["draft_path"])

    spec = json.loads(urllib.request.urlopen(f"{url}/spec.json", timeout=LOCAL_SERVER_TIMEOUT_SECONDS).read().decode("utf-8"))
    nonce = spec["metadata"]["submit_nonce"]
    draft_payload = json.dumps(
        {
            "nonce": nonce,
            "saved_at": "2026-06-04T00:00:00+00:00",
            "model": {"values": {"approval_notes": "Keep this draft."}},
            "browser_events": [{"type": "draft_autosave"}],
        }
    ).encode("utf-8")
    draft_request = urllib.request.Request(
        f"{url}/draft",
        data=draft_payload,
        method="POST",
        headers={"Content-Type": "application/json", "Origin": url},
    )
    draft_response = json.loads(urllib.request.urlopen(draft_request, timeout=LOCAL_SERVER_TIMEOUT_SECONDS).read().decode("utf-8"))
    assert draft_response["ok"] is True
    assert draft_path.exists()
    assert not response_path.exists()

    restored = json.loads(urllib.request.urlopen(f"{url}/draft", timeout=LOCAL_SERVER_TIMEOUT_SECONDS).read().decode("utf-8"))
    assert restored["draft"]["model"]["values"]["approval_notes"] == "Keep this draft."
    events_text = urllib.request.urlopen(f"{url}/events", timeout=LOCAL_SERVER_TIMEOUT_SECONDS).read().decode("utf-8")
    assert "GENUI_DRAFT_SAVED" in events_text

    submit_payload = json.dumps(
        {
            "nonce": nonce,
            "action": "abort",
            "values": {},
            "issues": [],
            "interaction_evidence": {"media_opened": [], "timeline_inspected": [], "seconds_watched": 0},
        }
    ).encode("utf-8")
    submit_request = urllib.request.Request(
        f"{url}/submit",
        data=submit_payload,
        method="POST",
        headers={"Content-Type": "application/json", "Origin": url},
    )
    urllib.request.urlopen(submit_request, timeout=LOCAL_SERVER_TIMEOUT_SECONDS).close()


def test_genui_product_verify_target_is_documented():
    makefile = (ROOT / "Makefile").read_text()
    product_contract_lines = [
        line.strip()
        for line in makefile.splitlines()
        if "tests/contracts/test_genui_product_contract.py" in line
    ]

    assert product_contract_lines
    assert all(line.startswith("VPB_ALLOW_BROWSER_OPEN=0 ") for line in product_contract_lines)
    assert all(" -m pytest" in line for line in product_contract_lines)
