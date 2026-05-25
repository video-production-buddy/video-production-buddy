"""Ad-video artifact schema validation regressions."""

from __future__ import annotations

from copy import deepcopy

import pytest

from schemas.artifacts import validate_artifact
from tools.compliance.compliance_check import ComplianceCheck

from tests.contracts.conftest import (
    _editing_rhythm_checkpoint,
    _minimal_production_proposal,
    _scene_plan_for_hallucination,
    _trend_alignment_block,
    _voice_performance_lock,
)


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
    with pytest.raises(Exception, match="tts_directive"):
        validate_artifact("script", script, pipeline_type="ad-video")

    script["sections"][0]["tts_directive"] = {"speed_mult": 0.94}
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


def test_production_bible_validation_requires_derived_intensity_curve() -> None:
    """Ad-video bibles must carry the exact curve derived from emotional beats."""
    from tests.qa.test_artifact_chain import PRODUCTION_BIBLE_VALID

    bible = deepcopy(PRODUCTION_BIBLE_VALID)
    validate_artifact("production_bible", bible)

    missing = deepcopy(bible)
    del missing["narrative"]["intensity_curve"]
    with pytest.raises(Exception, match="intensity_curve"):
        validate_artifact("production_bible", missing)

    drifted = deepcopy(bible)
    drifted["narrative"]["intensity_curve"][1]["value"] = 0.1
    with pytest.raises(Exception, match="derive_intensity_curve"):
        validate_artifact("production_bible", drifted)


def _trend_alignment_block() -> dict:
    return {
        "selected_trend_ids": ["trend-tiktok-text-hooks"],
        "alignments": [
            {
                "trend_id": "trend-tiktok-text-hooks",
                "signal": "Native text-first hooks are lifting completion rates.",
                "source": "https://example.com/current-hook",
                "sentiment": "positive",
                "brand_safety": "safe",
                "trend_type": "visual_style",
                "application_targets": ["hook", "build", "scene_plan", "visual"],
                "target_beat": "hook",
                "script_usage": {
                    "required_section_ids": ["hook", "build"],
                    "source_ref": "trend_alignment:trend-tiktok-text-hooks",
                    "usage_note": "Let the hook/build borrow the native text-first pacing pattern.",
                },
                "scene_usage": {
                    "required": True,
                    "required_scene_count": 1,
                    "visual_or_pacing_instruction": "Use native overlay text and rapid visual confirmation without copying a viral layout.",
                },
                "do_not_imitate": [
                    "Do not copy creator identity, captions, audio, choreography, or shot sequence from the source.",
                ],
            }
        ],
    }


def test_production_bible_schema_requires_trend_alignment_block() -> None:
    """The bible must make selected trend usage observable to downstream stages."""
    from tests.qa.test_artifact_chain import PRODUCTION_BIBLE_VALID

    bible = deepcopy(PRODUCTION_BIBLE_VALID)
    bible["intelligence"]["trend_alignment"] = _trend_alignment_block()
    validate_artifact("production_bible", bible)

    bad = deepcopy(bible)
    del bad["intelligence"]["trend_alignment"]
    with pytest.raises(Exception):
        validate_artifact("production_bible", bad)

    unsafe = deepcopy(bible)
    unsafe["intelligence"]["trend_alignment"]["alignments"][0]["brand_safety"] = "unsafe"
    with pytest.raises(Exception):
        validate_artifact("production_bible", unsafe)


def test_production_bible_schema_accepts_structured_editing_rhythm_checkpoint() -> None:
    """CP-E checkpoints need a structured form so compliance_check can inspect cuts."""
    from tests.qa.test_artifact_chain import PRODUCTION_BIBLE_VALID

    bible = deepcopy(PRODUCTION_BIBLE_VALID)
    bible["compliance_manifest"]["checkpoints"].append(
        {
            "id": "CP-E-STRUCTURED",
            "applies_to_stage": "edit",
            "description": "B3 edit rhythm",
            "check_type": "timing",
            "evaluation_method": "structural",
            "criterion": "Cuts in beat B3 match rapid/match-cut rhythm",
            "structured": {
                "kind": "editing_rhythm",
                "beat_id": "B3",
                "cuts_density": "rapid",
                "avg_shot_duration_seconds": 1.2,
                "transition_style": "match_cut",
                "tolerance": 0.25,
            },
            "source_confidence": "research-grounded",
            "failure_action": "revise",
        }
    )

    validate_artifact("production_bible", bible)


def _editing_rhythm_checkpoint(**overrides: object) -> dict:
    structured = {
        "kind": "editing_rhythm",
        "beat_id": "B3",
        "cuts_density": "rapid",
        "avg_shot_duration_seconds": 1.2,
        "transition_style": "match_cut",
        "tolerance": 0.25,
    }
    structured.update(overrides)
    return {
        "id": "CP-E3",
        "applies_to_stage": "edit",
        "description": "B3 edit rhythm",
        "check_type": "timing",
        "evaluation_method": "structural",
        "criterion": "Cuts in beat B3 match rapid/match-cut rhythm",
        "structured": structured,
        "source_confidence": "research-grounded",
        "failure_action": "revise",
    }


def test_compliance_beat_mapping_checks_edit_decision_cuts() -> None:
    """Beat mapping is not only a scene-plan check; edit cuts must preserve it."""
    result = ComplianceCheck().execute(
        {
            "stage_output": {
                "cuts": [
                    {
                        "id": "cut-1",
                        "source": "asset-1",
                        "in_seconds": 0,
                        "out_seconds": 1.2,
                        "maps_to_beat": "B3",
                    }
                ]
            },
            "checkpoint": {
                "id": "CP-E-BEAT",
                "evaluation_method": "structural",
                "check_type": "structural",
                "structured": {"kind": "beat_mapping", "beat_id": "B3"},
                "failure_action": "revise",
            },
        }
    )

    assert result.success is True
    assert result.data["pass"] is True


def test_compliance_editing_rhythm_passes_matching_cuts() -> None:
    result = ComplianceCheck().execute(
        {
            "stage_output": {
                "cuts": [
                    {
                        "id": "cut-1",
                        "source": "asset-1",
                        "in_seconds": 0.0,
                        "out_seconds": 1.2,
                        "maps_to_beat": "B3",
                        "transition_out": "match_cut",
                    },
                    {
                        "id": "cut-2",
                        "source": "asset-2",
                        "in_seconds": 1.2,
                        "out_seconds": 2.4,
                        "maps_to_beat": "B3",
                        "transition_in": "match_cut",
                    },
                ]
            },
            "checkpoint": _editing_rhythm_checkpoint(),
        }
    )

    assert result.success is True
    assert result.data["pass"] is True


def test_compliance_editing_rhythm_rejects_flattened_long_cuts() -> None:
    result = ComplianceCheck().execute(
        {
            "stage_output": {
                "cuts": [
                    {
                        "id": "cut-1",
                        "source": "asset-1",
                        "in_seconds": 0.0,
                        "out_seconds": 7.4,
                        "maps_to_beat": "B3",
                        "transition_out": "dissolve",
                    },
                    {
                        "id": "cut-2",
                        "source": "asset-2",
                        "in_seconds": 7.4,
                        "out_seconds": 15.2,
                        "maps_to_beat": "B3",
                        "transition_in": "dissolve",
                    },
                ]
            },
            "checkpoint": _editing_rhythm_checkpoint(),
        }
    )

    assert result.success is True
    assert result.data["pass"] is False
    assert "avg_shot_duration_seconds" in result.data["deviation"]
    assert "transition_style" in result.data["deviation"]


def test_compliance_editing_rhythm_accepts_schema_valid_slow_density() -> None:
    result = ComplianceCheck().execute(
        {
            "stage_output": {
                "cuts": [
                    {
                        "id": "cut-1",
                        "source": "asset-1",
                        "in_seconds": 0.0,
                        "out_seconds": 4.5,
                        "maps_to_beat": "B3",
                        "transition_out": "match_cut",
                    },
                    {
                        "id": "cut-2",
                        "source": "asset-2",
                        "in_seconds": 4.5,
                        "out_seconds": 9.0,
                        "maps_to_beat": "B3",
                        "transition_in": "match_cut",
                    },
                ]
            },
            "checkpoint": _editing_rhythm_checkpoint(
                cuts_density="slow",
                avg_shot_duration_seconds=4.5,
                transition_style="match_cut",
                tolerance=0.10,
            ),
        }
    )

    assert result.success is True
    assert result.data["pass"] is True


def test_scene_plan_schema_accepts_hallucination_checks() -> None:
    """Scene plans must carry explicit checks for generated high-risk visuals."""
    scene_plan = _scene_plan_for_hallucination()
    validate_artifact("scene_plan", scene_plan)

    bad = deepcopy(scene_plan)
    del bad["scenes"][0]["hallucination_checks"][0]["prohibited_failure"]
    with pytest.raises(Exception):
        validate_artifact("scene_plan", bad)


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
