"""Ad-video schema/director/tool contract alignment regressions."""

from __future__ import annotations

import json
import re
from copy import deepcopy
from pathlib import Path

import pytest
import yaml

from lib.pipeline_loader import get_required_tools
from schemas.artifacts import validate_artifact
from tools.validation.hallucination_contract_check import check_hallucination_contract
from tools.validation.product_identity_consistency_check import (
    check_product_identity_consistency,
)
from tools.validation.runtime_consistency_check import check_runtime_consistency
from tools.validation.scene_fidelity_check import check_kvm_coverage, check_plan
from tools.video.video_compose import VideoCompose


ROOT = Path(__file__).resolve().parent.parent.parent
AD_VIDEO_SKILLS = ROOT / "skills" / "pipelines" / "ad-video"
AD_VIDEO_MANIFEST = ROOT / "pipeline_defs" / "ad-video.yaml"


def _read_skill(name: str) -> str:
    return (AD_VIDEO_SKILLS / name).read_text(encoding="utf-8")


def _load_ad_video_manifest() -> dict:
    return yaml.safe_load(AD_VIDEO_MANIFEST.read_text(encoding="utf-8"))


def _load_scene_type_registry() -> dict:
    return json.loads(
        (ROOT / "remotion-composer" / "scene_type_registry.json").read_text(encoding="utf-8")
    )


def _json_fences(markdown: str) -> list[str]:
    return re.findall(r"```json\s*\n(.*?)\n```", markdown, flags=re.DOTALL)


def _minimal_production_proposal() -> dict:
    return {
        "version": "1.0",
        "selected_idea_id": "C2",
        "style_mode": "cinematic",
        "render_runtime": "ffmpeg",
        "product_reference_strategy": "generate_concept_reference",
        "subtitles": {"mode": "burnt-in", "language": "en", "user_confirmed": True},
        "dubbing": [],
        "derivatives_added": [],
        "budget_confirmed": True,
        "approved_budget_usd": 5.0,
        "music_strategy": "generative_loose",
        "audio_contract": {
            "voice_provider": "qwen3",
            "voice_id": "Dylan",
            "voice_model": "qwen3-tts-instruct-flash",
            "voice_gender": "male",
            "voice_persona": "warm product narrator with documentary restraint",
            "voice_performance": {
                "tone": "warm, confident, and precise",
                "baseline_emotion": "calm assurance",
                "emotion_arc": "curiosity -> clarity -> confident CTA",
                "intonation": "natural conversational rises; no hard-sell announcer cadence",
                "rhythm": "varied sentence lengths with clean pauses around claims",
                "pause_policy": "brief pause after each product proof point",
            },
            "voice_sample_approved": True,
            "target_speed_wps": 2.5,
            "target_lufs": -14,
            "max_section_drift_pct": 5,
            "duck_depth_db": -18,
        },
        "visual_contract": {
            "style_direction": "editorial-tech",
            "typography_pairing": {
                "display": "Inter 800",
                "body": "Inter 400",
            },
            "color_rhythm": "held-accent",
            "atmosphere": {"default_layers": [{"type": "grain", "intensity": 0.04}]},
            "anti_template_checklist": ["hero product visible before the CTA"],
        },
    }


def _voice_performance_lock() -> dict:
    return {
        "voice_model": "qwen3-tts-instruct-flash",
        "voice_gender": "male",
        "voice_persona": "late-20s product filmmaker, intimate but confident",
        "voice_performance": {
            "tone": "hushed confidence with slight breathiness",
            "baseline_emotion": "observant wonder",
            "emotion_arc": "quiet intrigue -> tactile reveal -> assured CTA",
            "intonation": "low-rise starts, gentle downward resolves, no announcer cadence",
            "rhythm": "measured phrases with varied clause length; never metronomic",
            "pause_policy": "short breath before each reveal; 0.3-0.5s after product claims",
        },
        "voice_sample_approved": True,
    }


def test_production_proposal_audio_contract_locks_voice_performance_controls() -> None:
    """Proposal must lock the expressive voice controls before TTS generation."""
    proposal = _minimal_production_proposal()
    proposal["audio_contract"].update(_voice_performance_lock())

    validate_artifact("production_proposal", proposal)

    for required_field in [
        "voice_model",
        "voice_gender",
        "voice_persona",
        "voice_performance",
        "voice_sample_approved",
    ]:
        bad = deepcopy(proposal)
        del bad["audio_contract"][required_field]
        with pytest.raises(Exception):
            validate_artifact("production_proposal", bad)

    bad = deepcopy(proposal)
    del bad["audio_contract"]["voice_performance"]["rhythm"]
    with pytest.raises(Exception):
        validate_artifact("production_proposal", bad)


def test_production_proposal_rejects_non_instruct_qwen_voice_model() -> None:
    """Qwen narration with delivery controls must lock an instruct-capable model."""
    proposal = _minimal_production_proposal()

    bad = deepcopy(proposal)
    bad["audio_contract"]["voice_model"] = "qwen3-tts-flash"
    with pytest.raises(Exception):
        validate_artifact("production_proposal", bad)


def test_production_proposal_rejects_qwen_flash_even_when_provider_is_cosyvoice() -> None:
    """Qwen model rules must follow the model family, not only voice_provider."""
    proposal = _minimal_production_proposal()
    proposal["audio_contract"]["voice_provider"] = "cosyvoice"
    proposal["audio_contract"]["voice_id"] = "Dylan"

    bad = deepcopy(proposal)
    bad["audio_contract"]["voice_model"] = "qwen3-tts-flash"
    with pytest.raises(Exception):
        validate_artifact("production_proposal", bad)


def test_production_proposal_rejects_known_qwen_voice_gender_mismatch() -> None:
    """Known gendered Qwen voices must match the approved voice_gender lock."""
    proposal = _minimal_production_proposal()

    bad = deepcopy(proposal)
    bad["audio_contract"]["voice_id"] = "Dylan"
    bad["audio_contract"]["voice_gender"] = "female"
    with pytest.raises(Exception):
        validate_artifact("production_proposal", bad)

    female_voice = deepcopy(proposal)
    female_voice["audio_contract"]["voice_id"] = "Cherry"
    female_voice["audio_contract"]["voice_gender"] = "female"
    validate_artifact("production_proposal", female_voice)


def test_script_schema_accepts_structured_voice_performance_per_section() -> None:
    """Ad-video scripts need structured delivery cues, not just raw narration text."""
    script = {
        "version": "1.0",
        "title": "Voice Performance Script",
        "total_duration_seconds": 6,
        "sections": [
            {
                "id": "hook",
                "text": "Night changes when the lens starts listening.",
                "start_seconds": 0,
                "end_seconds": 3,
                "speaker_directions": "Hushed, intimate, slightly breathy; do not sell.",
                "voice_performance": {
                    "emotion": "intrigue",
                    "intonation": "soft rise on 'Night', downward resolve on 'listening'",
                    "rhythm": "slow first phrase, tiny breath before the final clause",
                    "pace": "measured",
                    "pause_after_seconds": 0.35,
                },
            }
        ],
    }

    validate_artifact("script", script)

    bad = deepcopy(script)
    del bad["sections"][0]["voice_performance"]["intonation"]
    with pytest.raises(Exception):
        validate_artifact("script", bad)


def test_ad_video_script_validation_requires_section_voice_cues() -> None:
    """Ad-video checkpoint validation must reject scripts that would drop TTS delivery controls."""
    script = {
        "version": "1.0",
        "title": "Missing Voice Cues",
        "style_mode": "cinematic",
        "total_duration_seconds": 6,
        "sections": [
            {
                "id": "hook",
                "text": "Night changes when the lens starts listening.",
                "start_seconds": 0,
                "end_seconds": 3,
            }
        ],
    }

    with pytest.raises(Exception, match="speaker_directions"):
        validate_artifact("script", script)

    contextual_script = deepcopy(script)
    contextual_script.pop("style_mode")
    with pytest.raises(Exception, match="speaker_directions"):
        validate_artifact("script", contextual_script, pipeline_type="ad-video")

    generic_script = deepcopy(contextual_script)
    validate_artifact("script", generic_script)

    script["sections"][0]["speaker_directions"] = "Hushed, intimate, slightly breathy."
    with pytest.raises(Exception, match="voice_performance"):
        validate_artifact("script", script, pipeline_type="ad-video")

    script["sections"][0]["voice_performance"] = {
        "emotion": "intrigue",
        "intonation": "soft rise on 'Night', downward resolve on 'listening'",
        "rhythm": "slow first phrase, tiny breath before the final clause",
        "pace": "measured",
        "pause_after_seconds": 0.35,
    }
    validate_artifact("script", script, pipeline_type="ad-video")


def test_explicit_non_ad_pipeline_context_does_not_apply_ad_video_script_heuristics() -> None:
    """An explicit non-ad pipeline must not be overridden by shared style_mode."""
    script = {
        "version": "1.0",
        "title": "Explainer Script",
        "style_mode": "animated",
        "total_duration_seconds": 6,
        "sections": [
            {
                "id": "intro",
                "text": "A neural network learns by adjusting tiny weights.",
                "start_seconds": 0,
                "end_seconds": 6,
            }
        ],
    }

    validate_artifact("script", script, pipeline_type="animated-explainer")


def test_scene_plan_schema_accepts_animated_scene_contract_fields() -> None:
    """Animated scene-director fields must validate under scene_plan.schema.json."""
    scene_plan = {
        "version": "1.0",
        "style_mode": "animated",
        "total_duration_seconds": 5,
        "scenes": [
            {
                "id": "scene-1",
                "type": "animation",
                "scene_type": "text_card",
                "description": "Hook text slams into frame.",
                "start_seconds": 0,
                "end_seconds": 5,
                "core": True,
                "motion_required": False,
                "product_visibility": "none",
                "product_reference_required": False,
                "fulfills_kvm": ["KVM-1"],
                "motion_specs": ["text_entrance_fade"],
                "style_layers": [
                    {"type": "grain", "intensity": 0.06},
                    {"type": "ambient_glow", "color": "#FF3B30", "pulse": True},
                ],
            }
        ],
    }

    validate_artifact("scene_plan", scene_plan)


def test_production_proposal_schema_requires_product_reference_strategy() -> None:
    """Proposal must lock the product-reference strategy before assets can run."""
    proposal = _minimal_production_proposal()
    validate_artifact("production_proposal", proposal)

    for strategy in [
        "not_applicable",
        "use_provided_reference",
        "generate_concept_reference",
        "risk_accepted",
    ]:
        proposal["product_reference_strategy"] = strategy
        validate_artifact("production_proposal", proposal)

    bad = _minimal_production_proposal()
    del bad["product_reference_strategy"]
    with pytest.raises(Exception):
        validate_artifact("production_proposal", bad)

    bad = _minimal_production_proposal()
    bad["product_reference_strategy"] = "text_prompt_only"
    with pytest.raises(Exception):
        validate_artifact("production_proposal", bad)


def test_scene_plan_schema_requires_product_visibility_metadata_for_ad_video() -> None:
    """Ad-video scenes must declare whether product identity conditioning is needed."""
    scene_plan = {
        "version": "1.0",
        "style_mode": "cinematic",
        "total_duration_seconds": 5,
        "scenes": [
            {
                "id": "scene-1",
                "type": "generated",
                "description": "Macro hero shot of the product camera module.",
                "start_seconds": 0,
                "end_seconds": 5,
                "core": True,
                "motion_required": True,
            }
        ],
    }

    with pytest.raises(Exception):
        validate_artifact("scene_plan", scene_plan)

    scene_plan["scenes"][0]["product_visibility"] = "hero"
    scene_plan["scenes"][0]["product_reference_required"] = True
    validate_artifact("scene_plan", scene_plan)

    scene_plan["scenes"][0]["product_reference_required"] = False
    with pytest.raises(Exception):
        validate_artifact("scene_plan", scene_plan)


def test_ad_video_scene_plan_requires_product_metadata_without_style_mode() -> None:
    """Pipeline context, not optional style_mode, must trigger ad-video product metadata."""
    scene_plan = {
        "version": "1.0",
        "total_duration_seconds": 5,
        "scenes": [
            {
                "id": "scene-1",
                "type": "generated",
                "description": "Macro hero shot of the product camera module.",
                "start_seconds": 0,
                "end_seconds": 5,
            }
        ],
    }

    validate_artifact("scene_plan", scene_plan)

    with pytest.raises(Exception, match="product_visibility"):
        validate_artifact("scene_plan", scene_plan, pipeline_type="ad-video")

    scene_plan["scenes"][0]["product_visibility"] = "none"
    with pytest.raises(Exception, match="product_reference_required"):
        validate_artifact("scene_plan", scene_plan, pipeline_type="ad-video")

    scene_plan["scenes"][0]["product_reference_required"] = False
    validate_artifact("scene_plan", scene_plan, pipeline_type="ad-video")


def test_asset_manifest_schema_accepts_product_identity_conditioning_metadata() -> None:
    """Product-visible generated assets must be able to record conditioning metadata."""
    manifest = {
        "version": "1.0",
        "assets": [
            {
                "id": "scene-1-video",
                "type": "video",
                "path": "assets/video/scene-1.mp4",
                "source_tool": "wan_video_api",
                "scene_id": "scene-1",
                "model": "wan2.7-i2v",
                "product_identity_conditioning": {
                    "approved_reference_id": "pir-001",
                    "approved_reference_path": "reference_assets/product_phone.png",
                    "conditioning_mode": "reference_to_video",
                    "generation_tool": "wan_video_api",
                    "generation_model": "wan2.7-i2v",
                    "fidelity_verdict": "PASS",
                },
            }
        ],
    }
    validate_artifact("asset_manifest", manifest)

    bad = deepcopy(manifest)
    del bad["assets"][0]["product_identity_conditioning"]["conditioning_mode"]
    with pytest.raises(Exception):
        validate_artifact("asset_manifest", bad)

    bad = deepcopy(manifest)
    del bad["assets"][0]["product_identity_conditioning"]["approved_reference_path"]
    with pytest.raises(Exception):
        validate_artifact("asset_manifest", bad)

    waived = deepcopy(manifest)
    conditioning = waived["assets"][0]["product_identity_conditioning"]
    conditioning["conditioning_mode"] = "text_only_waived"
    conditioning["waiver_decision_id"] = "d-002"
    del conditioning["approved_reference_id"]
    del conditioning["approved_reference_path"]
    validate_artifact("asset_manifest", waived)

    bad = deepcopy(waived)
    del bad["assets"][0]["product_identity_conditioning"]["waiver_decision_id"]
    with pytest.raises(Exception):
        validate_artifact("asset_manifest", bad)


def test_enriched_brief_schema_requires_truth_and_safety_constraints_dimension() -> None:
    """G-0 must capture explicit truth/safety constraints before enrichment."""
    from tests.qa.test_schemas_preproduction import _minimal_enriched_brief

    brief = _minimal_enriched_brief()
    validate_artifact("enriched_brief", brief)

    bad = deepcopy(brief)
    del bad["creative_requirements"]["truth_and_safety_constraints"]
    with pytest.raises(Exception):
        validate_artifact("enriched_brief", bad)

    bad = deepcopy(brief)
    bad["creative_requirements"]["truth_and_safety_constraints"]["source"] = "INFERRED"
    with pytest.raises(Exception):
        validate_artifact("enriched_brief", bad)


def test_production_bible_schema_requires_truth_contract() -> None:
    """The bible must carry the broader truth contract used by scene/assets gates."""
    from tests.qa.test_artifact_chain import PRODUCTION_BIBLE_VALID

    bible = deepcopy(PRODUCTION_BIBLE_VALID)
    validate_artifact("production_bible", bible)

    bad = deepcopy(bible)
    del bad["truth_contract"]
    with pytest.raises(Exception):
        validate_artifact("production_bible", bad)

    bad = deepcopy(bible)
    bad["truth_contract"]["product_geometry_rules"] = []
    with pytest.raises(Exception):
        validate_artifact("production_bible", bad)


def _hallucination_check(check_id: str = "HC-PRODUCT-GEOMETRY") -> dict:
    return {
        "check_id": check_id,
        "category": "product_geometry",
        "requirement": "Phone camera island remains circular with three visible lenses and OPPO wordmark.",
        "prohibited_failure": "Generic rectangular camera bar, wrong lens count, or missing OPPO mark.",
        "severity": "blocker",
        "evidence_source": "truth_contract.product_geometry_rules[0]",
    }


def _truth_contract() -> dict:
    return {
        "objective_facts": [
            {
                "rule_id": "TC-FACT-1",
                "requirement": "Advertised product name is OPPO Find X9 Pro.",
                "prohibited_failure": "Renaming or implying a different model.",
                "evidence_source": "enriched_brief.product_brief.product_name",
                "source_confidence": "source-backed",
            }
        ],
        "physical_constraints": [
            {
                "rule_id": "TC-PHYS-1",
                "requirement": "The phone remains rigid; it does not bend, melt, split, or float without support.",
                "prohibited_failure": "Impossible deformation or unsupported levitation.",
                "evidence_source": "physical-product plausibility",
                "source_confidence": "director-verified",
            }
        ],
        "product_geometry_rules": [
            {
                "rule_id": "TC-GEO-1",
                "requirement": "Preserve circular rear camera island, visible lens layout, and brand mark placement.",
                "prohibited_failure": "Generic phone silhouette, changed camera layout, or invented markings.",
                "evidence_source": "product_identity_reference.required_visual_features",
                "source_confidence": "source-backed",
            }
        ],
        "motion_coherence_rules": [
            {
                "rule_id": "TC-MOTION-1",
                "requirement": "Camera motion and object motion remain continuous across start/mid/end keyframes.",
                "prohibited_failure": "Teleporting product, discontinuous hand pose, or impossible perspective jump.",
                "evidence_source": "scene_plan.motion_specs",
                "source_confidence": "director-verified",
            }
        ],
        "values_guardrails": [
            {
                "rule_id": "TC-VALUES-1",
                "requirement": "Do not imply medical, safety, or competitor claims absent from the approved brief.",
                "prohibited_failure": "Unapproved superiority claim or unsafe product-use depiction.",
                "evidence_source": "enriched_brief.brand_guideline.prohibited_elements",
                "source_confidence": "source-backed",
            }
        ],
    }


def _bible_with_truth_contract() -> dict:
    return {"truth_contract": _truth_contract()}


def _scene_plan_for_hallucination(
    *,
    include_checks: bool = True,
    text_card: bool = False,
) -> dict:
    scene = {
        "id": "scene-1",
        "type": "text_card" if text_card else "generated",
        "description": "Hero shot of OPPO Find X9 Pro camera island.",
        "start_seconds": 0,
        "end_seconds": 5,
        "core": True,
        "motion_required": not text_card,
        "product_visibility": "none" if text_card else "hero",
        "product_reference_required": not text_card,
    }
    if include_checks:
        scene["hallucination_checks"] = [_hallucination_check()]
    return {"version": "1.0", "style_mode": "cinematic", "scenes": [scene]}


def _asset_manifest_for_hallucination(
    *,
    include_review: bool = True,
    review_status: str = "PASS",
    check_status: str = "PASS",
    waiver_decision_id: str | None = None,
) -> dict:
    asset = {
        "id": "scene-1-video",
        "type": "video",
        "path": "assets/video/scene-1.mp4",
        "source_tool": "wan_video_api",
        "scene_id": "scene-1",
        "model": "wan2.7-i2v",
    }
    if include_review:
        review = {
            "status": review_status,
            "keyframe_paths": [
                "assets/keyframes/scene-1/start.png",
                "assets/keyframes/scene-1/mid.png",
                "assets/keyframes/scene-1/end.png",
            ],
            "check_verdicts": [
                {
                    "check_id": "HC-PRODUCT-GEOMETRY",
                    "category": "product_geometry",
                    "status": check_status,
                    "severity": "blocker",
                    "notes": "Reviewed start/mid/end keyframes against the approved product reference.",
                }
            ],
            "reviewer": {
                "type": "agent",
                "reviewed_at": "2026-05-19T09:00:00Z",
                "method": "start_mid_end_keyframe_review",
            },
        }
        if waiver_decision_id:
            review["waiver_decision_id"] = waiver_decision_id
        asset["hallucination_review"] = review
    return {"version": "1.0", "assets": [asset]}


def _approved_hallucination_waiver_log() -> dict:
    return {
        "version": "1.0",
        "project_id": "hallucination-waiver-regression",
        "decisions": [
            {
                "decision_id": "d-waive-001",
                "stage": "assets",
                "category": "hallucination_review_waiver",
                "subject": "Waive warned product-geometry review for scene-1",
                "options_considered": [
                    {
                        "option_id": "regenerate",
                        "label": "Regenerate",
                        "score": 0.7,
                        "reason": "Would reduce geometry ambiguity at extra cost.",
                    },
                    {
                        "option_id": "waive",
                        "label": "Waive",
                        "score": 0.6,
                        "reason": "User accepted the visible keyframe risk for this sample.",
                    },
                ],
                "selected": "waive",
                "reason": "User explicitly approved the waiver after seeing keyframes.",
                "user_visible": True,
                "user_approved": True,
            }
        ],
    }


def test_scene_plan_schema_accepts_hallucination_checks() -> None:
    """Scene plans must carry explicit checks for generated high-risk visuals."""
    scene_plan = _scene_plan_for_hallucination()
    validate_artifact("scene_plan", scene_plan)

    bad = deepcopy(scene_plan)
    del bad["scenes"][0]["hallucination_checks"][0]["prohibited_failure"]
    with pytest.raises(Exception):
        validate_artifact("scene_plan", bad)


def test_asset_manifest_schema_accepts_hallucination_review() -> None:
    """Asset manifests must record keyframe review verdicts for generated clips."""
    manifest = _asset_manifest_for_hallucination()
    validate_artifact("asset_manifest", manifest)

    bad = deepcopy(manifest)
    del bad["assets"][0]["hallucination_review"]["reviewer"]
    with pytest.raises(Exception):
        validate_artifact("asset_manifest", bad)

    bad = deepcopy(manifest)
    bad["assets"][0]["hallucination_review"]["status"] = "WAIVED"
    with pytest.raises(Exception):
        validate_artifact("asset_manifest", bad)

    waived = deepcopy(manifest)
    waived["assets"][0]["hallucination_review"]["status"] = "WAIVED"
    waived["assets"][0]["hallucination_review"]["waiver_decision_id"] = "d-waive-001"
    validate_artifact("asset_manifest", waived)


def test_hallucination_contract_rejects_missing_scene_checks_for_high_risk_scene() -> None:
    verdict = check_hallucination_contract(
        _bible_with_truth_contract(),
        _scene_plan_for_hallucination(include_checks=False),
        {"version": "1.0", "assets": []},
    )

    assert verdict["status"] == "FAIL"
    assert any("hallucination_checks" in issue for issue in verdict["issues"])


def test_hallucination_contract_rejects_missing_asset_review() -> None:
    verdict = check_hallucination_contract(
        _bible_with_truth_contract(),
        _scene_plan_for_hallucination(),
        _asset_manifest_for_hallucination(include_review=False),
    )

    assert verdict["status"] == "FAIL"
    assert any("hallucination_review" in issue for issue in verdict["issues"])


def test_hallucination_contract_rejects_blocker_flag() -> None:
    verdict = check_hallucination_contract(
        _bible_with_truth_contract(),
        _scene_plan_for_hallucination(),
        _asset_manifest_for_hallucination(review_status="FLAG", check_status="FLAG"),
    )

    assert verdict["status"] == "FAIL"
    assert any("FLAG" in issue for issue in verdict["issues"])


def test_hallucination_contract_accepts_product_visible_scene_with_review() -> None:
    verdict = check_hallucination_contract(
        _bible_with_truth_contract(),
        _scene_plan_for_hallucination(),
        _asset_manifest_for_hallucination(),
    )

    assert verdict["status"] == "PASS"
    assert verdict["summary"]["high_risk_scenes"] == 1
    assert verdict["summary"]["reviewed_assets"] == 1


def test_hallucination_contract_accepts_approved_waiver() -> None:
    verdict = check_hallucination_contract(
        _bible_with_truth_contract(),
        _scene_plan_for_hallucination(),
        _asset_manifest_for_hallucination(
            review_status="WAIVED",
            check_status="WAIVED",
            waiver_decision_id="d-waive-001",
        ),
        _approved_hallucination_waiver_log(),
    )

    assert verdict["status"] == "WARN"
    assert verdict["summary"]["waivers"] == 1


def test_hallucination_contract_rejects_visual_accuracy_decision_for_waiver() -> None:
    decision_log = _approved_hallucination_waiver_log()
    decision_log["decisions"][0]["category"] = "visual_accuracy_check"

    verdict = check_hallucination_contract(
        _bible_with_truth_contract(),
        _scene_plan_for_hallucination(),
        _asset_manifest_for_hallucination(
            review_status="WAIVED",
            check_status="WAIVED",
            waiver_decision_id="d-waive-001",
        ),
        decision_log,
    )

    assert verdict["status"] == "FAIL"
    assert any("hallucination_review_waiver" in issue for issue in verdict["issues"])


def test_hallucination_contract_rejects_non_waiver_selection_for_waiver() -> None:
    decision_log = _approved_hallucination_waiver_log()
    decision_log["decisions"][0]["selected"] = "regenerate"

    verdict = check_hallucination_contract(
        _bible_with_truth_contract(),
        _scene_plan_for_hallucination(),
        _asset_manifest_for_hallucination(
            review_status="WAIVED",
            check_status="WAIVED",
            waiver_decision_id="d-waive-001",
        ),
        decision_log,
    )

    assert verdict["status"] == "FAIL"
    assert any("selected" in issue and "waiver" in issue.lower() for issue in verdict["issues"])


def test_hallucination_contract_rejects_waiver_without_user_approval() -> None:
    verdict = check_hallucination_contract(
        _bible_with_truth_contract(),
        _scene_plan_for_hallucination(),
        _asset_manifest_for_hallucination(
            review_status="WAIVED",
            check_status="WAIVED",
            waiver_decision_id="d-waive-001",
        ),
        {"version": "1.0", "project_id": "missing-waiver", "decisions": []},
    )

    assert verdict["status"] == "FAIL"
    assert any("waiver" in issue.lower() for issue in verdict["issues"])


def test_hallucination_contract_accepts_non_product_text_card_without_checks() -> None:
    verdict = check_hallucination_contract(
        _bible_with_truth_contract(),
        _scene_plan_for_hallucination(include_checks=False, text_card=True),
        {"version": "1.0", "assets": []},
    )

    assert verdict["status"] == "PASS"
    assert verdict["summary"]["high_risk_scenes"] == 0


def test_hallucination_contract_skips_sourced_visual_assets() -> None:
    scene_plan = {
        "version": "1.0",
        "style_mode": "cinematic",
        "scenes": [
            {
                "id": "scene-1",
                "type": "broll",
                "description": "User-provided product footage.",
                "start_seconds": 0,
                "end_seconds": 5,
                "core": True,
                "motion_required": True,
                "product_visibility": "hero",
                "product_reference_required": True,
                "required_assets": [
                    {
                        "type": "video",
                        "description": "Provided footage from the user.",
                        "source": "provided",
                    }
                ],
            }
        ],
    }
    asset_manifest = {
        "version": "1.0",
        "assets": [
            {
                "id": "scene-1-source-video",
                "type": "video",
                "path": "assets/video/scene-1-source.mp4",
                "source_tool": "user_upload",
                "scene_id": "scene-1",
                "subtype": "provided",
            }
        ],
    }

    verdict = check_hallucination_contract(
        _bible_with_truth_contract(),
        scene_plan,
        asset_manifest,
    )

    assert verdict["status"] == "PASS"
    assert verdict["summary"]["high_risk_scenes"] == 0
    assert verdict["summary"]["reviewed_assets"] == 0


def test_hallucination_contract_uses_asset_generation_metadata_for_scope() -> None:
    scene_plan = _scene_plan_for_hallucination()
    scene_plan["scenes"][0]["type"] = "broll"
    scene_plan["scenes"][0]["required_assets"] = [
        {
            "type": "video",
            "description": "A visual asset whose actual manifest provenance decides scope.",
            "source": "provided",
        }
    ]

    verdict = check_hallucination_contract(
        _bible_with_truth_contract(),
        scene_plan,
        _asset_manifest_for_hallucination(),
    )

    assert verdict["status"] == "PASS"
    assert verdict["summary"]["high_risk_scenes"] == 1
    assert verdict["summary"]["reviewed_assets"] == 1


def test_ad_video_scene_plan_schema_requires_scene_governance_fields() -> None:
    """Ad-video scene plans must carry fields used by derivative and motion gates."""
    scene_plan = {
        "version": "1.0",
        "style_mode": "cinematic",
        "total_duration_seconds": 5,
        "scenes": [
            {
                "id": "scene-1",
                "type": "generated",
                "description": "A moving lifestyle scene.",
                "start_seconds": 0,
                "end_seconds": 5,
            }
        ],
    }

    with pytest.raises(Exception):
        validate_artifact("scene_plan", scene_plan)


def test_ad_video_scene_plan_schema_requires_crop_regions_for_aspect_ratio_derivatives() -> None:
    """Aspect-ratio derivatives are not renderable unless every scene has crop regions."""
    scene_plan = {
        "version": "1.0",
        "style_mode": "cinematic",
        "total_duration_seconds": 5,
        "derivative_variants": ["9:16"],
        "scenes": [
            {
                "id": "scene-1",
                "type": "generated",
                "description": "A moving lifestyle scene.",
                "start_seconds": 0,
                "end_seconds": 5,
                "core": True,
                "motion_required": True,
            }
        ],
    }

    with pytest.raises(Exception):
        validate_artifact("scene_plan", scene_plan)

    scene_plan["scenes"][0]["crop_regions"] = {}
    with pytest.raises(Exception):
        validate_artifact("scene_plan", scene_plan)

    scene_plan["scenes"][0]["crop_regions"] = {
        "1:1": {"x": 0, "y": 0, "w": 1080, "h": 1080}
    }
    with pytest.raises(Exception):
        validate_artifact("scene_plan", scene_plan)

    scene_plan["scenes"][0]["crop_regions"] = {
        "9:16": {"x": 656, "y": 0, "w": 608, "h": 1080}
    }
    scene_plan["scenes"][0]["product_visibility"] = "none"
    scene_plan["scenes"][0]["product_reference_required"] = False
    validate_artifact("scene_plan", scene_plan)


def test_ad_video_scene_plan_schema_does_not_require_crop_regions_for_duration_only_derivatives() -> None:
    """Duration cuts are handled by core-scene filtering, not crop rectangles."""
    scene_plan = {
        "version": "1.0",
        "style_mode": "cinematic",
        "total_duration_seconds": 15,
        "derivative_variants": ["15s_short"],
        "scenes": [
            {
                "id": "scene-1",
                "type": "generated",
                "description": "A moving lifestyle scene kept in the short cut.",
                "start_seconds": 0,
                "end_seconds": 5,
                "core": True,
                "motion_required": True,
                "product_visibility": "none",
                "product_reference_required": False,
            }
        ],
    }

    validate_artifact("scene_plan", scene_plan)

    with_aspect_ratio = deepcopy(scene_plan)
    with_aspect_ratio["derivative_variants"] = ["15s_short", "9:16"]
    with pytest.raises(Exception):
        validate_artifact("scene_plan", with_aspect_ratio)

    with_aspect_ratio["scenes"][0]["crop_regions"] = {
        "9:16": {"x": 656, "y": 0, "w": 608, "h": 1080}
    }
    validate_artifact("scene_plan", with_aspect_ratio)

    duration_key_as_crop = deepcopy(scene_plan)
    duration_key_as_crop["scenes"][0]["crop_regions"] = {
        "15s_short": {"x": 0, "y": 0, "w": 1920, "h": 1080}
    }
    with pytest.raises(Exception):
        validate_artifact("scene_plan", duration_key_as_crop)


def test_production_bible_schema_allows_runtime_deferral_until_proposal() -> None:
    """Bible runs before proposal, so render_runtime must be optional there."""
    from tests.qa.test_artifact_chain import PRODUCTION_BIBLE_VALID

    bible = deepcopy(PRODUCTION_BIBLE_VALID)
    bible["visual"].pop("render_runtime")

    validate_artifact("production_bible", bible)


def test_production_bible_schema_requires_kvm_motion_primitives() -> None:
    """Bible KVMs must name the scene motion primitives needed to fulfill them."""
    from tests.qa.test_artifact_chain import PRODUCTION_BIBLE_VALID

    bible = deepcopy(PRODUCTION_BIBLE_VALID)
    for kvm in bible["visual"]["key_visual_moments"]:
        kvm["required_motion_primitives"] = ["text_entrance_fade"]
    validate_artifact("production_bible", bible)

    bad = deepcopy(bible)
    del bad["visual"]["key_visual_moments"][0]["required_motion_primitives"]
    with pytest.raises(Exception):
        validate_artifact("production_bible", bad)

    bad = deepcopy(bible)
    bad["visual"]["key_visual_moments"][0]["required_motion_primitives"] = []
    with pytest.raises(Exception):
        validate_artifact("production_bible", bad)


def test_ad_video_ep_reads_proposal_locks_after_proposal_approval() -> None:
    """EP_STATE must use proposal-stage locks, not optional bible audit copies."""
    ep = _read_skill("executive-producer.md")

    assert "`style_mode` from `production_proposal.style_mode`" in ep
    assert "`render_runtime` from `production_proposal.render_runtime`" in ep
    assert "`derivative_variants` from `production_proposal.derivatives_added`" in ep
    assert "`render_runtime` from `production_bible.visual.render_runtime`" not in ep
    assert "`derivative_variants` from `production_bible.deliverables.derivatives`" not in ep
    assert "render_runtime locked in production_bible.visual.render_runtime" not in ep


def test_brief_enrichment_director_references_artifact_schema_path() -> None:
    """Skill prerequisites should point to the real schema location."""
    brief_enrichment = _read_skill("brief-enrichment-director.md")

    assert "schemas/artifacts/enriched_brief.schema.json" in brief_enrichment
    assert "schemas/enriched_brief.schema.json" not in brief_enrichment


def test_brief_enrichment_director_requires_creative_requirements_worksheet_before_g0() -> None:
    """Every ad-video brief must pass a structured creative-director worksheet before G-0."""
    brief_enrichment = _read_skill("brief-enrichment-director.md")

    assert "Creative Requirements Worksheet" in brief_enrichment
    assert "`creative_requirements`" in brief_enrichment
    assert "`product_model`" in brief_enrichment
    assert "`core_selling_points`" in brief_enrichment
    assert "`platform_duration`" in brief_enrichment
    assert "`target_audience`" in brief_enrichment
    assert "`tone_style`" in brief_enrichment
    assert "`visual_approach`" in brief_enrichment
    assert "`language_voiceover`" in brief_enrichment
    assert "`mandatory_marketing`" in brief_enrichment
    assert "`cta`" in brief_enrichment
    assert "`product_fidelity_references`" in brief_enrichment
    assert "`truth_and_safety_constraints`" in brief_enrichment
    assert "RECOMMEND FOR ME" in brief_enrichment
    assert "FROM BRIEF or DELEGATED" in brief_enrichment


def test_intelligence_director_validates_delegated_dimensions() -> None:
    """Delegated dimensions are recommendations, so intelligence must validate them."""
    intelligence = _read_skill("intelligence-director.md")

    assert "status == \"INFERRED\" or status == \"DELEGATED\"" in intelligence
    assert "DELEGATED" in intelligence
    assert "FROM BRIEF" in intelligence


def test_executive_producer_gate_g0_checks_creative_requirements() -> None:
    """EP Gate G-0 must block if the worksheet is missing or silently inferred."""
    ep = _read_skill("executive-producer.md")

    assert "creative_requirements" in ep
    assert "product_model" in ep
    assert "product_fidelity_references" in ep
    assert "truth_and_safety_constraints" in ep
    assert "FROM BRIEF or DELEGATED" in ep


def test_ad_video_manifest_brief_enrichment_review_focus_checks_creative_requirements() -> None:
    """Manifest review focus should make worksheet completeness a stage contract."""
    manifest = _load_ad_video_manifest()
    brief_enrichment_stage = next(stage for stage in manifest["stages"] if stage["name"] == "brief_enrichment")
    focus_text = "\n".join(brief_enrichment_stage.get("review_focus", []))

    assert "creative_requirements" in focus_text
    assert "FROM BRIEF or DELEGATED" in focus_text
    assert "No required worksheet dimension is INFERRED" in focus_text


def test_ad_video_manifest_proposal_success_criteria_use_proposal_locks() -> None:
    """The manifest should not require back-writing proposal locks into bible."""
    manifest = _load_ad_video_manifest()
    proposal_stage = next(stage for stage in manifest["stages"] if stage["name"] == "proposal")
    success_text = "\n".join(proposal_stage.get("success_criteria", []))

    assert "production_proposal.render_runtime" in success_text
    assert "production_proposal.derivatives_added" in success_text
    assert "production_bible.visual.render_runtime" not in success_text
    assert "deliverables.derivatives populated in production_bible" not in success_text


def test_executive_producer_script_gate_uses_locked_audio_contract_rate() -> None:
    """EP script review must mirror script-director's target_speed_wps contract."""
    ep = _read_skill("executive-producer.md")

    assert "production_proposal.audio_contract.target_speed_wps" in ep
    assert "target_words = target_duration_seconds × 2.5" not in ep


def test_ad_video_manifest_script_gate_uses_locked_audio_contract_rate() -> None:
    """The manifest script-stage review contract must match the EP/script-director gate."""
    manifest = _load_ad_video_manifest()
    script_stage = next(stage for stage in manifest["stages"] if stage["name"] == "script")
    gate_text = "\n".join(
        script_stage.get("review_focus", []) + script_stage.get("success_criteria", [])
    )

    assert "production_proposal.audio_contract.target_speed_wps" in gate_text
    assert "target_duration_seconds × 2.5" not in gate_text


def test_proposal_director_does_not_teach_backwriting_locks_to_bible() -> None:
    """Proposal should produce production_proposal locks instead of mutating bible locks."""
    proposal = _read_skill("proposal-director.md")

    assert "Populate `deliverables.derivatives` in production_bible" not in proposal
    assert "Lock `visual.style_mode` in production_bible" not in proposal
    assert "Lock `visual.render_runtime` in production_bible" not in proposal
    assert "`production_proposal.derivatives_added[]`" in proposal
    assert "`production_proposal.render_runtime`" in proposal


def test_kvm_coverage_reads_visual_key_visual_moments() -> None:
    bible = {
        "visual": {
            "key_visual_moments": [
                {
                    "moment_id": "KVM-1",
                    "description": "Product reveal lands at the emotional peak.",
                    "maps_to_beat": "B3",
                    "mandatory": True,
                }
            ]
        }
    }
    scene_plan = {"scenes": [{"id": "scene-1", "fulfills_kvm": []}]}

    report = check_kvm_coverage(bible, scene_plan)

    assert report["summary"]["kvms_checked"] == 1
    assert report["ok"] is False
    assert report["issues"][0]["kvm_id"] == "KVM-1"


def test_kvm_coverage_requires_fulfilling_scenes_to_carry_required_motion_primitives() -> None:
    bible = {
        "visual": {
            "key_visual_moments": [
                {
                    "moment_id": "KVM-1",
                    "description": "Product reveal lands at the emotional peak.",
                    "maps_to_beat": "B3",
                    "mandatory": True,
                    "required_motion_primitives": [
                        "camera_push",
                        "product_reveal",
                    ],
                }
            ]
        }
    }
    scene_plan = {
        "scenes": [
            {
                "id": "scene-1",
                "fulfills_kvm": ["KVM-1"],
                "motion_specs": ["camera_push"],
            }
        ]
    }

    report = check_kvm_coverage(bible, scene_plan)

    assert report["ok"] is False
    assert report["issues"][0]["kind"] == "missing_required_motion_primitives"
    assert report["issues"][0]["scene_id"] == "scene-1"
    assert report["issues"][0]["kvm_id"] == "KVM-1"
    assert report["issues"][0]["missing_motion_primitives"] == ["product_reveal"]

    scene_plan["scenes"][0]["motion_specs"].append("product_reveal")
    report = check_kvm_coverage(bible, scene_plan)

    assert report["ok"] is True
    assert report["issues"] == []


def test_runtime_consistency_accepts_user_approved_decision_log_swap() -> None:
    proposal = {"render_runtime": "remotion"}
    edit_decisions = {"render_runtime": "hyperframes"}
    decision_log = {
        "version": "1.0",
        "project_id": "runtime-swap-regression",
        "decisions": [
            {
                "decision_id": "d-001",
                "stage": "proposal",
                "category": "render_runtime_selection",
                "subject": "Composition runtime",
                "options_considered": [
                    {
                        "option_id": "remotion",
                        "label": "Remotion",
                        "score": 0.8,
                        "reason": "Available baseline",
                    },
                    {
                        "option_id": "hyperframes",
                        "label": "HyperFrames",
                        "score": 0.9,
                        "reason": "Better for the approved kinetic typography route",
                    },
                ],
                "selected": "hyperframes",
                "reason": "User approved HyperFrames after seeing the tradeoff.",
                "user_visible": True,
                "user_approved": True,
            }
        ],
    }

    verdict = check_runtime_consistency(proposal, edit_decisions, decision_log)

    assert verdict["status"] == "PASS"
    assert verdict["decision_present"] is True
    assert verdict["decision_user_approved"] is True
    assert verdict["decision_selected_runtime"] == "hyperframes"
    assert verdict["decision_matches_actual"] is True


def test_runtime_consistency_rejects_approved_old_selection_for_new_actual() -> None:
    proposal = {"render_runtime": "remotion"}
    edit_decisions = {"render_runtime": "hyperframes"}
    decision_log = {
        "version": "1.0",
        "project_id": "runtime-swap-regression",
        "decisions": [
            {
                "decision_id": "d-001",
                "stage": "proposal",
                "category": "render_runtime_selection",
                "subject": "Composition runtime",
                "options_considered": [
                    {
                        "option_id": "remotion",
                        "label": "Remotion",
                        "score": 0.9,
                        "reason": "User originally approved Remotion",
                    },
                    {
                        "option_id": "hyperframes",
                        "label": "HyperFrames",
                        "score": 0.7,
                        "reason": "Considered but rejected",
                    },
                ],
                "selected": "remotion",
                "reason": "Initial proposal approval selected Remotion.",
                "user_visible": True,
                "user_approved": True,
            }
        ],
    }

    verdict = check_runtime_consistency(proposal, edit_decisions, decision_log)

    assert verdict["status"] == "FAIL"
    assert verdict["decision_present"] is True
    assert verdict["decision_user_approved"] is True
    assert verdict["decision_selected_runtime"] == "remotion"
    assert verdict["decision_matches_actual"] is False
    assert any("selected 'remotion'" in issue for issue in verdict["issues"])


def test_runtime_consistency_rejects_approved_swap_without_selected_runtime() -> None:
    proposal = {"render_runtime": "remotion"}
    edit_decisions = {"render_runtime": "hyperframes"}
    decision_log = {
        "version": "1.0",
        "project_id": "runtime-swap-regression",
        "decisions": [
            {
                "decision_id": "d-001",
                "stage": "edit",
                "category": "render_runtime_selection",
                "subject": "Composition runtime",
                "options_considered": [],
                "reason": "User approved a runtime swap, but the selected runtime was not recorded.",
                "user_visible": True,
                "user_approved": True,
            }
        ],
    }

    verdict = check_runtime_consistency(proposal, edit_decisions, decision_log)

    assert verdict["status"] == "FAIL"
    assert verdict["decision_selected_runtime"] is None
    assert verdict["decision_matches_actual"] is False
    assert any("does not select actual runtime 'hyperframes'" in issue for issue in verdict["issues"])


def test_decision_log_accepts_product_identity_reference_selection_category() -> None:
    decision_log = {
        "version": "1.0",
        "project_id": "product-reference-regression",
        "decisions": [
            {
                "decision_id": "d-001",
                "stage": "proposal",
                "category": "product_identity_reference_selection",
                "subject": "Product identity reference strategy",
                "options_considered": [
                    {
                        "option_id": "generate_concept_reference",
                        "label": "Generate concept reference",
                        "score": 0.8,
                        "reason": "No user product photo was available.",
                    }
                ],
                "selected": "generate_concept_reference",
                "reason": "User approved generated reference candidates before video generation.",
                "user_visible": True,
                "user_approved": True,
            }
        ],
    }

    validate_artifact("decision_log", decision_log)


def _approved_product_identity_reference(source_type: str = "generated") -> dict:
    return {
        "version": "1.0",
        "reference_id": "pir-001",
        "product_name": "OPPO Find X9 Pro",
        "source_type": source_type,
        "approval_status": "approved",
        "selected_reference_image_path": "reference_assets/product_oppo.png",
        "required_visual_features": [
            "large circular camera island",
            "OPPO wordmark placement",
        ],
        "prohibited_variations": [
            "different lens count",
            "generic phone silhouette",
        ],
        "user_approval": {
            "approved": True,
            "approved_by": "user",
            "approved_at": "2026-05-19T09:00:00Z",
            "decision_id": "d-001",
        },
    }


def _product_visible_scene_plan() -> dict:
    return {
        "version": "1.0",
        "style_mode": "cinematic",
        "scenes": [
            {
                "id": "scene-1",
                "type": "generated",
                "description": "Hero push-in on OPPO Find X9 Pro camera island.",
                "start_seconds": 0,
                "end_seconds": 5,
                "core": True,
                "motion_required": True,
                "product_visibility": "hero",
                "product_reference_required": True,
            }
        ],
    }


def _two_product_visible_scene_plan() -> dict:
    scene_plan = _product_visible_scene_plan()
    later_scene = deepcopy(scene_plan["scenes"][0])
    later_scene["id"] = "scene-2"
    later_scene["description"] = "Later packshot of OPPO Find X9 Pro in hand."
    later_scene["start_seconds"] = 5
    later_scene["end_seconds"] = 10
    scene_plan["scenes"].append(later_scene)
    return scene_plan


def _conditioned_asset_manifest(conditioning_mode: str = "reference_to_video") -> dict:
    return {
        "version": "1.0",
        "assets": [
            {
                "id": "scene-1-video",
                "type": "video",
                "path": "assets/video/scene-1.mp4",
                "source_tool": "wan_video_api",
                "scene_id": "scene-1",
                "model": "wan2.7-i2v",
                "product_identity_conditioning": {
                    "approved_reference_id": "pir-001",
                    "approved_reference_path": "reference_assets/product_oppo.png",
                    "conditioning_mode": conditioning_mode,
                    "generation_tool": "wan_video_api",
                    "generation_model": "wan2.7-i2v",
                    "fidelity_verdict": "PASS",
                },
            }
        ],
    }


def test_product_identity_consistency_rejects_visible_scene_without_reference_or_waiver() -> None:
    reference = {
        "version": "1.0",
        "reference_id": "pir-none",
        "product_name": "OPPO Find X9 Pro",
        "source_type": "not_applicable",
        "approval_status": "not_required",
        "required_visual_features": [],
        "prohibited_variations": [],
    }

    verdict = check_product_identity_consistency(
        reference,
        _product_visible_scene_plan(),
        {"version": "1.0", "assets": []},
    )

    assert verdict["status"] == "FAIL"
    assert any("approved product identity reference" in issue for issue in verdict["issues"])


def test_product_identity_consistency_accepts_approved_generated_reference_and_conditioned_assets() -> None:
    verdict = check_product_identity_consistency(
        _approved_product_identity_reference(),
        _product_visible_scene_plan(),
        _conditioned_asset_manifest(),
    )

    assert verdict["status"] == "PASS"
    assert verdict["summary"]["product_visible_scenes"] == 1
    assert verdict["summary"]["conditioned_assets_checked"] == 1


def test_product_identity_consistency_sample_scope_ignores_unselected_future_scenes() -> None:
    """Sample approval must not require visual assets for product scenes outside the sample."""
    verdict = check_product_identity_consistency(
        _approved_product_identity_reference(),
        _two_product_visible_scene_plan(),
        _conditioned_asset_manifest(),
        generated_scene_ids=["scene-1"],
    )

    assert verdict["status"] == "PASS"
    assert verdict["summary"]["product_visible_scenes"] == 2
    assert verdict["summary"]["asset_required_product_visible_scenes"] == 1
    assert verdict["summary"]["conditioned_assets_checked"] == 1


def test_product_identity_consistency_full_scope_rejects_missing_future_scene_asset() -> None:
    """Full asset review still requires assets for every product-visible scene."""
    verdict = check_product_identity_consistency(
        _approved_product_identity_reference(),
        _two_product_visible_scene_plan(),
        _conditioned_asset_manifest(),
    )

    assert verdict["status"] == "FAIL"
    assert any("scene-2" in issue for issue in verdict["issues"])


def test_product_identity_consistency_rejects_risk_waiver_without_user_approval() -> None:
    reference = {
        "version": "1.0",
        "reference_id": "pir-risk",
        "product_name": "OPPO Find X9 Pro",
        "source_type": "risk_accepted",
        "approval_status": "pending",
        "required_visual_features": [],
        "prohibited_variations": ["generic phone silhouette"],
        "risk_waiver": {
            "reason": "User has no product photos.",
            "user_approved": False,
            "decision_id": "d-001",
        },
    }
    manifest = _conditioned_asset_manifest(conditioning_mode="text_only_waived")
    manifest["assets"][0]["product_identity_conditioning"].pop("approved_reference_path")

    verdict = check_product_identity_consistency(
        reference,
        _product_visible_scene_plan(),
        manifest,
    )

    assert verdict["status"] == "FAIL"
    assert any("risk waiver" in issue for issue in verdict["issues"])


def test_product_identity_consistency_accepts_non_product_visible_not_applicable() -> None:
    reference = {
        "version": "1.0",
        "reference_id": "pir-none",
        "product_name": "Acme SaaS",
        "source_type": "not_applicable",
        "approval_status": "not_required",
        "required_visual_features": [],
        "prohibited_variations": [],
    }
    scene_plan = {
        "version": "1.0",
        "style_mode": "animated",
        "scenes": [
            {
                "id": "scene-1",
                "type": "text_card",
                "description": "Animated headline card.",
                "start_seconds": 0,
                "end_seconds": 5,
                "core": True,
                "motion_required": False,
                "product_visibility": "none",
                "product_reference_required": False,
            }
        ],
    }

    verdict = check_product_identity_consistency(
        reference,
        scene_plan,
        {"version": "1.0", "assets": []},
    )

    assert verdict["status"] == "PASS"
    assert verdict["summary"]["product_visible_scenes"] == 0


def test_video_compose_render_accepts_artifact_paths(tmp_path: Path) -> None:
    """The tool may receive path strings from older directors; it must coerce them."""
    edit_path = tmp_path / "edit_decisions.json"
    asset_path = tmp_path / "asset_manifest.json"
    edit_path.write_text(
        json.dumps({"version": "1.0", "render_runtime": "ffmpeg", "cuts": []}),
        encoding="utf-8",
    )
    asset_path.write_text(json.dumps({"assets": []}), encoding="utf-8")

    result = VideoCompose().execute(
        {
            "operation": "render",
            "edit_decisions": str(edit_path),
            "asset_manifest": str(asset_path),
        }
    )

    assert result.success is False
    assert result.error == "No cuts in edit_decisions"


def test_edit_director_json_examples_do_not_teach_legacy_shape() -> None:
    text = _read_skill("edit-director.md")

    for block in _json_fences(text):
        assert '"timeline"' not in block
        assert '"source_file"' not in block
        assert '"burn_in"' not in block


def test_ad_video_directors_reference_current_contract_names() -> None:
    asset = _read_skill("asset-director.md")
    proposal = _read_skill("proposal-director.md")
    compose = _read_skill("compose-director.md")
    publish = _read_skill("publish-director.md")
    animated_scene = _read_skill("scene-director-animated.md")

    assert 'production_plan["voice_selection"]["voice_id"]' not in asset
    assert 'audio_contract = production_proposal["audio_contract"]' in asset
    assert 'audio_contract["voice_id"]' in asset
    assert 'model = audio_contract["voice_model"]' in asset
    assert "voice_performance" in asset
    assert "speaker_directions" in asset

    assert 'either `"remotion"` or `"hyperframes"`' not in proposal
    assert '"ffmpeg"' in proposal
    assert '"voice_model": "qwen3-tts-instruct-flash"' in proposal
    assert "voice_performance" in proposal
    assert "voice_sample_approved" in proposal
    assert "Populate `deliverables.derivatives` in production_bible" not in proposal
    assert "Lock `visual.render_runtime` in production_bible" not in proposal

    assert '"edit_decisions": "projects/<name>/artifacts/edit_decisions.json"' not in compose
    assert '"asset_manifest": "projects/<name>/artifacts/asset_manifest.json"' not in compose
    assert "render_report.output_files" not in publish
    assert "render_report.outputs" in publish

    assert "production_bible.kvms" not in animated_scene
    assert "production_bible.visual.key_visual_moments" in animated_scene


def test_ad_video_contract_mentions_product_identity_reference_flow() -> None:
    manifest = _load_ad_video_manifest()
    guide = (ROOT / "AGENT_GUIDE.md").read_text(encoding="utf-8")
    brief_enrichment = _read_skill("brief-enrichment-director.md")
    proposal = _read_skill("proposal-director.md")
    scene = _read_skill("scene-director.md")
    asset = _read_skill("asset-director.md")
    ep = _read_skill("executive-producer.md")

    proposal_stage = next(stage for stage in manifest["stages"] if stage["name"] == "proposal")
    scene_stage = next(stage for stage in manifest["stages"] if stage["name"] == "scene_plan")
    asset_stage = next(stage for stage in manifest["stages"] if stage["name"] == "assets")
    asset_substage_names = [substage["name"] for substage in asset_stage.get("sub_stages", [])]
    contract_text = "\n".join(
        proposal_stage.get("review_focus", [])
        + proposal_stage.get("success_criteria", [])
        + scene_stage.get("review_focus", [])
        + scene_stage.get("success_criteria", [])
        + asset_stage.get("review_focus", [])
        + asset_stage.get("success_criteria", [])
    )

    assert "product_reference_strategy" in contract_text
    assert "product_identity_reference" in asset_stage.get("produces", [])
    assert "product_reference" in asset_substage_names
    assert "no text-only" in contract_text.lower()
    assert "Product Identity Reference" in brief_enrichment
    assert "`product_reference_strategy`" in proposal
    assert "`product_visibility`" in scene
    assert "`product_reference_required`" in scene
    assert "product_identity_consistency_check" in asset
    assert "generated_scene_ids" in asset
    assert asset.index("## Product Reference Sub-Stage") < asset.index("## Sample Sub-Stage")
    assert "sample sub-stage first" not in asset
    assert "product_identity_reference_selection" in proposal
    assert "product_identity_reference_selection" in ep
    assert "`product_identity_reference` + `asset_manifest`" in guide


def test_product_visible_remotion_scene_registry_requires_approved_product_image() -> None:
    registry = _load_scene_type_registry()
    scene_types = registry["scene_types"]

    creator = scene_types["creator_workflow_scene"]
    assert "productImage" in creator["required_cut_props"]
    assert "generic hardware" in creator["description"]

    brand = scene_types["brand_card"]
    assert "productImage" in brand["optional_props"]
    assert "hardwareTreatment" in brand["optional_props"]
    assert "Text-only by default" in brand["description"]
    assert "creator_workflow_scene" in VideoCompose._REMOTION_COMPONENTS
    assert "brand_card" in VideoCompose._REMOTION_COMPONENTS


def test_scene_fidelity_rejects_creator_workflow_without_product_image() -> None:
    registry = _load_scene_type_registry()
    missing_product = {
        "cuts": [
            {
                "id": "scene-1",
                "type": "creator_workflow_scene",
                "source": "remotion:creator_workflow_scene",
                "in_seconds": 0,
                "out_seconds": 4,
                "motion_specs": ["product_scale_reveal"],
            }
        ]
    }

    report = check_plan(missing_product, registry)

    assert report["ok"] is False
    assert any(issue["kind"] == "missing_required_props" for issue in report["issues"])

    with_product = deepcopy(missing_product)
    with_product["cuts"][0]["productImage"] = "reference_assets/product.png"

    assert check_plan(with_product, registry)["ok"] is True


def test_remotion_product_components_do_not_render_synthetic_hardware_by_default() -> None:
    brand_source = (
        ROOT / "remotion-composer" / "src" / "components" / "BrandCardScene.tsx"
    ).read_text(encoding="utf-8")
    workflow_source = (
        ROOT / "remotion-composer" / "src" / "components" / "CreatorWorkflowScene.tsx"
    ).read_text(encoding="utf-8")

    for source in (brand_source, workflow_source):
        assert "<ProductImageMotion" in source
        assert 'hardwareTreatment === "synthetic_laptop"' in source
        assert "void productImage" not in source

    assert "hasProductImage || showSyntheticHardware" in brand_source
    assert "hasProductImage && productImage" in workflow_source


def test_ad_video_contract_mentions_hallucination_flow() -> None:
    """Manifest and director skills must expose the truth-contract review flow."""
    manifest = _load_ad_video_manifest()
    guide = (ROOT / "AGENT_GUIDE.md").read_text(encoding="utf-8")
    reviewer = (ROOT / "skills" / "meta" / "reviewer.md").read_text(encoding="utf-8")
    bible = _read_skill("bible-director.md")
    scene = _read_skill("scene-director.md")
    asset = _read_skill("asset-director.md")
    cinematic_asset = _read_skill("asset-director-cinematic.md")
    animated_asset = _read_skill("asset-director-animated.md")
    ep = _read_skill("executive-producer.md")

    brief_enrichment_stage = next(stage for stage in manifest["stages"] if stage["name"] == "brief_enrichment")
    bible_stage = next(stage for stage in manifest["stages"] if stage["name"] == "bible")
    scene_stage = next(stage for stage in manifest["stages"] if stage["name"] == "scene_plan")
    asset_stage = next(stage for stage in manifest["stages"] if stage["name"] == "assets")
    compose_stage = next(stage for stage in manifest["stages"] if stage["name"] == "compose")
    publish_stage = next(stage for stage in manifest["stages"] if stage["name"] == "publish")
    contract_text = "\n".join(
        brief_enrichment_stage.get("review_focus", [])
        + bible_stage.get("review_focus", [])
        + bible_stage.get("success_criteria", [])
        + scene_stage.get("review_focus", [])
        + scene_stage.get("success_criteria", [])
        + asset_stage.get("review_focus", [])
        + asset_stage.get("success_criteria", [])
        + compose_stage.get("review_focus", [])
        + publish_stage.get("review_focus", [])
    )

    assert "truth_and_safety_constraints" in contract_text
    assert "truth_contract" in contract_text
    assert "hallucination_checks" in contract_text
    assert "hallucination_review" in contract_text
    assert "hallucination_contract_check" in contract_text
    assert "FLAG" in contract_text
    assert "hallucination_review_waiver" in contract_text

    assert "`production_bible.truth_contract`" in guide
    assert "`hallucination_checks[]`" in guide
    assert "`asset_manifest.assets[].hallucination_review`" in guide
    assert "`hallucination_review_waiver`" in guide
    assert "production_bible.truth_contract" in bible
    assert "`scene_plan.scenes[].hallucination_checks[]`" in bible
    assert "`hallucination_checks[]`" in scene
    assert "hallucination_contract_check" in asset
    assert "hallucination_review" in cinematic_asset
    assert "hallucination_review" in animated_asset
    assert "hallucination_contract_check" in ep
    assert "Ad-Video Hallucination Review" in reviewer


def test_ad_video_asset_stage_exposes_frame_sampler_for_hallucination_keyframes() -> None:
    manifest = _load_ad_video_manifest()
    asset_stage = next(stage for stage in manifest["stages"] if stage["name"] == "assets")

    asset_stage_tools = set(asset_stage.get("required_tools", []))
    asset_stage_tools.update(asset_stage.get("optional_tools", []))
    asset_stage_tools.update(asset_stage.get("tools_available", []))

    assert "frame_sampler" in asset_stage_tools
    assert "frame_sampler" in get_required_tools(manifest)
