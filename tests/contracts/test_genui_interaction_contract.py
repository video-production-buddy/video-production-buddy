from pathlib import Path

import pytest
import jsonschema

from schemas.artifacts import ARTIFACT_NAMES, validate_artifact


ROOT = Path(__file__).resolve().parent.parent.parent


def _sample_config() -> dict:
    return {
        "version": "1.0",
        "config_id": "cfg-ad-video-g0",
        "project_id": "demo-ad",
        "pipeline_type": "ad-video",
        "stage": "brief_enrichment",
        "gate": "G-0",
        "title": "Creative Requirements Worksheet",
        "description": "Review the prefilled ad requirements before enrichment.",
        "sections": [
            {
                "id": "product",
                "title": "Product",
                "fields": [
                    {
                        "id": "product_model",
                        "label": "Product/model",
                        "type": "text",
                        "required": True,
                        "default": "OPPO Find X9 Pro",
                        "recommended": "Use the exact public model name.",
                        "help_text": "This binds to creative_requirements.product_model.",
                        "binding": {
                            "artifact": "enriched_brief",
                            "path": "creative_requirements.product_model.value",
                        },
                    }
                ],
            }
        ],
        "submit_actions": [
            {
                "id": "approve",
                "label": "Approve worksheet",
                "kind": "approve",
                "recommended": True,
            },
            {
                "id": "revise",
                "label": "Send revisions",
                "kind": "revise",
            },
        ],
    }


def _sample_response() -> dict:
    return {
        "version": "1.0",
        "response_id": "resp-ad-video-g0",
        "config_id": "cfg-ad-video-g0",
        "project_id": "demo-ad",
        "pipeline_type": "ad-video",
        "stage": "brief_enrichment",
        "gate": "G-0",
        "submitted_at": "2026-05-20T00:00:00+00:00",
        "action": "approve",
        "values": {"product_model": "OPPO Find X9 Pro"},
        "validation": {"status": "pending", "errors": []},
    }


def test_genui_artifact_names_are_registered():
    assert "ui_form_config" in ARTIFACT_NAMES
    assert "ui_response" in ARTIFACT_NAMES


def test_ui_form_config_schema_accepts_form_first_gate_config():
    validate_artifact("ui_form_config", _sample_config())


def test_ui_form_config_rejects_direct_canonical_write_action():
    bad = _sample_config()
    bad["submit_actions"][0]["canonical_artifact"] = "enriched_brief"

    with pytest.raises(jsonschema.ValidationError):
        validate_artifact("ui_form_config", bad)


def test_ui_response_schema_accepts_agent_reviewable_submission():
    validate_artifact("ui_response", _sample_response())


def test_ad_video_skills_document_form_first_and_cli_fallback():
    brief_skill = (ROOT / "skills/pipelines/ad-video/brief-enrichment-director.md").read_text()
    proposal_skill = (ROOT / "skills/pipelines/ad-video/proposal-director.md").read_text()
    combined = f"{brief_skill}\n{proposal_skill}".lower()

    assert "genui" in combined
    assert "ui_response" in combined
    assert "cli fallback" in combined or "cli path" in combined
    assert "must not write canonical" in combined


def test_agent_guide_describes_genui_as_interaction_layer_not_orchestrator():
    guide = (ROOT / "AGENT_GUIDE.md").read_text().lower()

    assert "genui" in guide
    assert "interaction layer" in guide
    assert "not an orchestrator" in guide
    assert "canonical artifacts" in guide


def test_architecture_docs_include_genui_interaction_layer():
    architecture = (ROOT / "docs/ARCHITECTURE.md").read_text().lower()
    context = (ROOT / "PROJECT_CONTEXT.md").read_text().lower()
    combined = f"{architecture}\n{context}"

    assert "genui" in combined
    assert "ui_form_config" in architecture
    assert "ui_response" in architecture
    assert "interaction layer" in combined
    assert "not an orchestrator" in combined
