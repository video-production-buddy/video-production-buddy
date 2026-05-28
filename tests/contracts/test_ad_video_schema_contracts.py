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


def _valid_ad_video_scene_plan() -> dict:
    return {
        "version": "1.0",
        "style_mode": "cinematic",
        "total_duration_seconds": 10,
        "scenes": [
            {
                "id": "scene-1",
                "type": "generated",
                "description": "First product moment.",
                "start_seconds": 0,
                "end_seconds": 4,
                "duration_seconds": 4,
                "core": True,
                "motion_required": True,
                "product_visibility": "hero",
                "product_reference_required": True,
            },
            {
                "id": "scene-2",
                "type": "generated",
                "description": "Second product moment.",
                "start_seconds": 4,
                "end_seconds": 10,
                "duration_seconds": 6,
                "core": True,
                "motion_required": True,
                "product_visibility": "none",
                "product_reference_required": False,
            },
        ],
    }


def _valid_ad_video_asset_manifest() -> dict:
    return {
        "version": "1.0",
        "assets": [
            {
                "id": "asset-1",
                "type": "video",
                "path": "assets/video/scene-1.mp4",
                "source_tool": "wan_video_api",
                "scene_id": "scene-1",
            },
            {
                "id": "asset-2",
                "type": "audio",
                "path": "assets/audio/narration.mp3",
                "source_tool": "tts_selector",
                "scene_id": "scene-1",
            },
        ],
        "costs": [
            {"tool": "wan_video_api", "cost_usd": 0.18},
            {"tool": "tts_selector", "cost_usd": 0.02},
        ],
        "total_cost_usd": 0.20,
    }


def _library_locked_music_alignment() -> dict:
    return {
        "strategy": "library_locked",
        "target_peak_seconds": 18.0,
        "selected_peak_seconds": 30.0,
        "aligned_peak_seconds": 18.2,
        "drift_seconds": 0.2,
        "timing_sidecar_path": "music_library/background.timing.json",
        "evidence": "Validated timing sidecar and trimmed the track to target.",
    }


def _search_align_music_alignment() -> dict:
    return {
        "strategy": "search_align",
        "target_peak_seconds": 18.0,
        "selected_peak_seconds": 26.4,
        "aligned_peak_seconds": 17.9,
        "drift_seconds": -0.1,
        "beat_detection_report": {
            "source": "lib.beat_detector",
            "drop_seconds": [26.4],
        },
        "evidence": "Detected stock track drop and trimmed it to target.",
    }


def _valid_ad_video_edit_decisions() -> dict:
    return {
        "version": "1.0",
        "render_runtime": "remotion",
        "music_strategy": "none",
        "total_duration_seconds": 10,
        "cuts": [
            {
                "id": "cut-1",
                "source": "asset-1",
                "in_seconds": 0,
                "out_seconds": 4,
                "maps_to_beat": "hook",
            },
            {
                "id": "cut-2",
                "source": "asset-2",
                "in_seconds": 4,
                "out_seconds": 10,
                "maps_to_beat": "cta",
            },
        ],
    }


def _valid_ad_video_script() -> dict:
    voice_performance = {
        "emotion": "calm urgency",
        "intonation": "clear lift then resolve",
        "rhythm": "short phrases with a breath",
        "pace": "measured",
        "pause_after_seconds": 0.2,
    }
    return {
        "version": "1.0",
        "title": "Proof Script",
        "style_mode": "cinematic",
        "total_duration_seconds": 10,
        "user_approved": True,
        "sections": [
            {
                "id": "hook",
                "text": "The first proof lands fast.",
                "start_seconds": 0,
                "end_seconds": 4,
                "duration_estimate_seconds": 4,
                "speaker_directions": "Measured opening with clean emphasis.",
                "voice_performance": dict(voice_performance),
                "tts_directive": {"speed_mult": 0.96},
            },
            {
                "id": "cta_brand",
                "text": "Choose Flowcut today. Flowcut.",
                "start_seconds": 4,
                "end_seconds": 10,
                "duration_estimate_seconds": 6,
                "speaker_directions": "Confident low-pressure close.",
                "voice_performance": dict(voice_performance),
                "tts_directive": {"speed_mult": 0.96},
            },
        ],
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


def test_ad_video_proposal_requires_user_confirmed_budget_and_subtitles() -> None:
    proposal = _minimal_production_proposal()
    validate_artifact("production_proposal", proposal, pipeline_type="ad-video")

    budget_not_confirmed = deepcopy(proposal)
    budget_not_confirmed["budget_confirmed"] = False
    with pytest.raises(Exception, match="budget_confirmed"):
        validate_artifact(
            "production_proposal", budget_not_confirmed, pipeline_type="ad-video"
        )

    subtitles_not_confirmed = deepcopy(proposal)
    subtitles_not_confirmed["subtitles"]["user_confirmed"] = False
    with pytest.raises(Exception, match="subtitles.user_confirmed"):
        validate_artifact(
            "production_proposal", subtitles_not_confirmed, pipeline_type="ad-video"
        )

    missing_subtitle_confirmation = deepcopy(proposal)
    del missing_subtitle_confirmation["subtitles"]["user_confirmed"]
    with pytest.raises(Exception, match="subtitles.user_confirmed"):
        validate_artifact(
            "production_proposal",
            missing_subtitle_confirmation,
            pipeline_type="ad-video",
        )


def test_ad_video_proposal_requires_locked_music_strategy() -> None:
    proposal = _minimal_production_proposal()
    del proposal["music_strategy"]

    with pytest.raises(Exception, match="music_strategy"):
        validate_artifact("production_proposal", proposal, pipeline_type="ad-video")


def test_ad_video_proposal_requires_visual_asset_provider_locks() -> None:
    proposal = _minimal_production_proposal()
    del proposal["visual_contract"]["visual_asset_provider_locks"]

    with pytest.raises(Exception, match="visual_asset_provider_locks"):
        validate_artifact("production_proposal", proposal, pipeline_type="ad-video")


def test_ad_video_asset_manifest_accepts_strict_music_alignment_evidence() -> None:
    manifest = _valid_ad_video_asset_manifest()
    manifest["assets"].append(
        {
            "id": "music-1",
            "type": "music",
            "path": "assets/music/background.mp3",
            "source_tool": "music_library",
            "scene_id": "global",
            "music_alignment": _library_locked_music_alignment(),
        }
    )
    manifest["costs"].append({"tool": "music_library", "cost_usd": 0.0})

    validate_artifact("asset_manifest", manifest, pipeline_type="ad-video")

    search_manifest = deepcopy(manifest)
    search_manifest["assets"][-1]["source_tool"] = "pixabay_music"
    search_manifest["assets"][-1]["music_alignment"] = _search_align_music_alignment()
    search_manifest["costs"][-1]["tool"] = "pixabay_music"
    validate_artifact("asset_manifest", search_manifest, pipeline_type="ad-video")


def test_ad_video_asset_manifest_rejects_malformed_music_alignment() -> None:
    manifest = _valid_ad_video_asset_manifest()
    manifest["assets"].append(
        {
            "id": "music-1",
            "type": "music",
            "path": "assets/music/background.mp3",
            "source_tool": "music_library",
            "scene_id": "global",
            "music_alignment": _library_locked_music_alignment(),
        }
    )
    manifest["costs"].append({"tool": "music_library", "cost_usd": 0.0})

    missing_sidecar = deepcopy(manifest)
    del missing_sidecar["assets"][-1]["music_alignment"]["timing_sidecar_path"]
    with pytest.raises(Exception, match="timing_sidecar_path"):
        validate_artifact("asset_manifest", missing_sidecar, pipeline_type="ad-video")

    missing_report = deepcopy(manifest)
    missing_report["assets"][-1]["source_tool"] = "pixabay_music"
    missing_report["assets"][-1]["music_alignment"] = _search_align_music_alignment()
    missing_report["assets"][-1]["music_alignment"].pop("beat_detection_report")
    missing_report["costs"][-1]["tool"] = "pixabay_music"
    with pytest.raises(Exception):
        validate_artifact("asset_manifest", missing_report, pipeline_type="ad-video")


def test_production_proposal_rejects_duplicate_derivative_variants() -> None:
    proposal = _minimal_production_proposal()
    proposal["derivatives_added"] = ["9:16", "9:16"]

    with pytest.raises(Exception, match="derivatives_added"):
        validate_artifact("production_proposal", proposal, pipeline_type="ad-video")


def test_production_proposal_rejects_unknown_derivative_variants() -> None:
    proposal = _minimal_production_proposal()
    proposal["derivatives_added"] = ["portrait_crop"]

    with pytest.raises(Exception, match="derivatives_added"):
        validate_artifact("production_proposal", proposal, pipeline_type="ad-video")


def test_production_proposal_rejects_duplicate_dubbing_languages() -> None:
    proposal = _minimal_production_proposal()
    proposal["dubbing"] = [
        {"language": "es-ES", "voice_id": "narrator-es-a"},
        {"language": "es-ES", "voice_id": "narrator-es-b"},
    ]

    with pytest.raises(Exception, match="dubbing"):
        validate_artifact("production_proposal", proposal, pipeline_type="ad-video")


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


def test_idea_options_requires_exactly_one_matching_selected_concept() -> None:
    idea_options = {
        "version": "1.0",
        "concepts": [
            {
                "id": "C1",
                "name": "Quiet Proof",
                "scenario": "A compact product proof story.",
                "selected": False,
            },
            {
                "id": "C2",
                "name": "Tactile Reveal",
                "scenario": "A tactile reveal with the product in use.",
                "selected": True,
            },
        ],
        "selected_concept_id": "C2",
    }
    validate_artifact("idea_options", idea_options)

    no_selected = deepcopy(idea_options)
    no_selected["concepts"][1]["selected"] = False
    with pytest.raises(Exception, match="selected"):
        validate_artifact("idea_options", no_selected)

    two_selected = deepcopy(idea_options)
    two_selected["concepts"][0]["selected"] = True
    with pytest.raises(Exception, match="exactly one"):
        validate_artifact("idea_options", two_selected)

    mismatched_id = deepcopy(idea_options)
    mismatched_id["selected_concept_id"] = "C1"
    with pytest.raises(Exception, match="selected_concept_id"):
        validate_artifact("idea_options", mismatched_id)


def test_idea_options_rejects_duplicate_concept_ids() -> None:
    idea_options = {
        "version": "1.0",
        "concepts": [
            {
                "id": "C1",
                "name": "Quiet Proof",
                "scenario": "A compact product proof story.",
                "selected": True,
            },
            {
                "id": "C1",
                "name": "Tactile Reveal",
                "scenario": "A tactile reveal with the product in use.",
                "selected": False,
            },
        ],
        "selected_concept_id": "C1",
    }

    with pytest.raises(Exception, match="duplicate concept id"):
        validate_artifact("idea_options", idea_options)


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
                "end_seconds": 6,
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
    with pytest.raises(Exception, match="user_approved"):
        validate_artifact("script", script, pipeline_type="ad-video")

    script["user_approved"] = True
    validate_artifact("script", script, pipeline_type="ad-video")


def test_ad_video_script_rejects_duplicate_section_ids() -> None:
    """Section IDs must be unique because scene_plan maps back to script sections."""
    script = _valid_ad_video_script()
    script["sections"][1]["id"] = "hook"

    with pytest.raises(Exception, match="duplicate section id"):
        validate_artifact("script", script, pipeline_type="ad-video")


def test_ad_video_script_rejects_non_positive_section_duration() -> None:
    """Script sections must have positive time windows before TTS generation."""
    script = _valid_ad_video_script()
    script["sections"][0]["end_seconds"] = 0

    with pytest.raises(Exception, match="end_seconds.*greater than start_seconds"):
        validate_artifact("script", script, pipeline_type="ad-video")


def test_ad_video_script_rejects_overlapping_sections() -> None:
    """Script timing must be ordered and non-overlapping."""
    script = _valid_ad_video_script()
    script["sections"][1]["start_seconds"] = 3.5

    with pytest.raises(Exception, match="overlaps previous section"):
        validate_artifact("script", script, pipeline_type="ad-video")


def test_ad_video_script_rejects_timeline_gaps() -> None:
    """Script sections should cover the narration timeline without blank gaps."""
    script = _valid_ad_video_script()
    script["sections"][1]["start_seconds"] = 5
    script["sections"][1]["duration_estimate_seconds"] = 5

    with pytest.raises(Exception, match="gap before section"):
        validate_artifact("script", script, pipeline_type="ad-video")


def test_ad_video_script_rejects_duration_estimate_drift() -> None:
    """duration_estimate_seconds must agree with start/end when present."""
    script = _valid_ad_video_script()
    script["sections"][0]["duration_estimate_seconds"] = 9

    with pytest.raises(Exception, match="duration_estimate_seconds"):
        validate_artifact("script", script, pipeline_type="ad-video")


def test_ad_video_script_rejects_total_duration_mismatch() -> None:
    """Script total duration must match the final section end."""
    script = _valid_ad_video_script()
    script["total_duration_seconds"] = 8

    with pytest.raises(Exception, match="total_duration_seconds"):
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


def test_ad_video_animated_scene_plan_requires_scene_type() -> None:
    scene_plan = {
        "version": "1.0",
        "style_mode": "animated",
        "total_duration_seconds": 5,
        "scenes": [
            {
                "id": "scene-1",
                "type": "animation",
                "description": "Animated brand-card CTA.",
                "start_seconds": 0,
                "end_seconds": 5,
                "core": True,
                "motion_required": True,
                "product_visibility": "none",
                "product_reference_required": False,
                "fulfills_kvm": [],
                "motion_specs": ["letter_spring"],
            }
        ],
    }

    with pytest.raises(Exception, match="scene_type"):
        validate_artifact("scene_plan", scene_plan, pipeline_type="ad-video")

    scene_plan["scenes"][0]["scene_type"] = "brand_card"
    validate_artifact("scene_plan", scene_plan, pipeline_type="ad-video")


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
    with pytest.raises(Exception, match="motion_required"):
        validate_artifact("scene_plan", scene_plan, pipeline_type="ad-video")

    scene_plan["scenes"][0]["motion_required"] = True
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


def test_ad_video_asset_manifest_requires_ass_subtitle_paths() -> None:
    manifest = {
        "version": "1.0",
        "subtitle_file": "assets/subtitles.srt",
        "assets": [
            {
                "id": "subtitle-1",
                "type": "subtitle",
                "path": "assets/subtitles.srt",
                "source_tool": "subtitle_gen",
                "scene_id": "global",
            }
        ],
        "costs": [{"tool": "subtitle_gen", "cost_usd": 0.0}],
        "total_cost_usd": 0.0,
    }

    with pytest.raises(Exception, match="ASS"):
        validate_artifact("asset_manifest", manifest, pipeline_type="ad-video")

    manifest["subtitle_file"] = "assets/subtitles.ass"
    manifest["assets"][0]["path"] = "assets/subtitles.ass"
    validate_artifact("asset_manifest", manifest, pipeline_type="ad-video")


def test_ad_video_asset_manifest_rejects_duplicate_asset_ids() -> None:
    """Asset IDs must be unique because edit and review artifacts reference them."""
    manifest = _valid_ad_video_asset_manifest()
    manifest["assets"][1]["id"] = "asset-1"

    with pytest.raises(Exception, match="duplicate asset id"):
        validate_artifact("asset_manifest", manifest, pipeline_type="ad-video")


def test_ad_video_asset_manifest_requires_cost_log_for_assets() -> None:
    """Ad-video assets must carry an auditable per-tool cost log."""
    manifest = _valid_ad_video_asset_manifest()
    del manifest["costs"]

    with pytest.raises(Exception, match="costs"):
        validate_artifact("asset_manifest", manifest, pipeline_type="ad-video")


def test_ad_video_asset_manifest_rejects_total_cost_mismatch() -> None:
    """The manifest total must match the per-tool cost log."""
    manifest = _valid_ad_video_asset_manifest()
    manifest["total_cost_usd"] = 0.01

    with pytest.raises(Exception, match="total_cost_usd"):
        validate_artifact("asset_manifest", manifest, pipeline_type="ad-video")


def test_ad_video_asset_manifest_requires_cost_entry_for_each_source_tool() -> None:
    """Every generated or sourced asset tool must be represented in costs[]."""
    manifest = _valid_ad_video_asset_manifest()
    manifest["costs"] = [{"tool": "tts_selector", "cost_usd": 0.02}]
    manifest["total_cost_usd"] = 0.02

    with pytest.raises(Exception, match="wan_video_api"):
        validate_artifact("asset_manifest", manifest, pipeline_type="ad-video")


def test_ad_video_edit_decisions_reject_duplicate_cut_ids() -> None:
    """Cut IDs must be unique for deterministic review and render diagnostics."""
    edit_decisions = _valid_ad_video_edit_decisions()
    edit_decisions["cuts"][1]["id"] = "cut-1"

    with pytest.raises(Exception, match="duplicate cut id"):
        validate_artifact("edit_decisions", edit_decisions, pipeline_type="ad-video")


def test_ad_video_edit_decisions_require_locked_music_strategy() -> None:
    edit_decisions = _valid_ad_video_edit_decisions()
    del edit_decisions["music_strategy"]

    with pytest.raises(Exception, match="music_strategy"):
        validate_artifact("edit_decisions", edit_decisions, pipeline_type="ad-video")


def test_ad_video_edit_decisions_reject_non_positive_cut_duration() -> None:
    """Cut source ranges must have positive duration before composition."""
    edit_decisions = _valid_ad_video_edit_decisions()
    edit_decisions["cuts"][0]["out_seconds"] = 0

    with pytest.raises(Exception, match="out_seconds.*greater than in_seconds"):
        validate_artifact("edit_decisions", edit_decisions, pipeline_type="ad-video")


def test_ad_video_edit_decisions_reject_total_duration_mismatch() -> None:
    """Edit duration should preserve the approved scene/script runtime."""
    edit_decisions = _valid_ad_video_edit_decisions()
    edit_decisions["total_duration_seconds"] = 7

    with pytest.raises(Exception, match="total_duration_seconds"):
        validate_artifact("edit_decisions", edit_decisions, pipeline_type="ad-video")


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


def test_ad_video_enriched_brief_requires_explicit_user_approval() -> None:
    from tests.qa.test_schemas_preproduction import _minimal_enriched_brief

    brief = _minimal_enriched_brief()
    brief["user_approved"] = True
    validate_artifact("enriched_brief", brief, pipeline_type="ad-video")

    brief["user_approved"] = False
    with pytest.raises(Exception, match="user_approved"):
        validate_artifact("enriched_brief", brief, pipeline_type="ad-video")


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


def test_production_bible_rejects_duplicate_narrative_beat_ids() -> None:
    """Beat ids must be unique because script, scene, edit, and compliance refs key by them."""
    from tests.qa.test_artifact_chain import PRODUCTION_BIBLE_VALID

    bible = deepcopy(PRODUCTION_BIBLE_VALID)
    bible["narrative"]["emotional_beat_sequence"][1]["beat_id"] = "B1"

    with pytest.raises(Exception, match="duplicate beat_id"):
        validate_artifact("production_bible", bible, pipeline_type="ad-video")


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


def test_production_bible_selected_trends_must_resolve_to_alignment_rows() -> None:
    """Selected trend ids are canonical refs, not advisory labels."""
    from tests.qa.test_artifact_chain import PRODUCTION_BIBLE_VALID

    bible = deepcopy(PRODUCTION_BIBLE_VALID)
    bible["intelligence"]["trend_alignment"]["selected_trend_ids"] = ["trend-missing"]

    with pytest.raises(Exception, match="selected_trend_ids"):
        validate_artifact("production_bible", bible, pipeline_type="ad-video")


def test_production_bible_trend_source_refs_must_match_alignment_id() -> None:
    """Script refs must use the canonical trend_alignment:<trend_id> value."""
    from tests.qa.test_artifact_chain import PRODUCTION_BIBLE_VALID

    bible = deepcopy(PRODUCTION_BIBLE_VALID)
    bible["intelligence"]["trend_alignment"]["alignments"][0]["script_usage"][
        "source_ref"
    ] = "trend_alignment:wrong-trend"

    with pytest.raises(Exception, match="source_ref"):
        validate_artifact("production_bible", bible, pipeline_type="ad-video")


def test_production_bible_selected_knowledge_cards_must_resolve_to_alignment_rows() -> None:
    """Selected knowledge card ids must have a matching alignment contract."""
    from tests.qa.test_artifact_chain import PRODUCTION_BIBLE_VALID

    bible = deepcopy(PRODUCTION_BIBLE_VALID)
    bible["intelligence"]["knowledge_alignment"]["selected_card_ids"] = [
        "missing.card",
    ]

    with pytest.raises(Exception, match="selected_card_ids"):
        validate_artifact("production_bible", bible, pipeline_type="ad-video")


def test_production_bible_knowledge_source_refs_must_match_alignment_id() -> None:
    """Professional-knowledge refs must survive as knowledge_alignment:<card_id>."""
    from tests.qa.test_artifact_chain import PRODUCTION_BIBLE_VALID

    bible = deepcopy(PRODUCTION_BIBLE_VALID)
    bible["intelligence"]["knowledge_alignment"]["alignments"][0][
        "source_ref"
    ] = "knowledge_alignment:wrong.card"

    with pytest.raises(Exception, match="source_ref"):
        validate_artifact("production_bible", bible, pipeline_type="ad-video")


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


def test_ad_video_scene_plan_rejects_duplicate_scene_ids() -> None:
    """Scene ids must be unique because asset/review gates key by scene_id."""
    scene_plan = {
        "version": "1.0",
        "style_mode": "cinematic",
        "total_duration_seconds": 10,
        "scenes": [
            {
                "id": "scene-1",
                "type": "generated",
                "description": "First product moment.",
                "start_seconds": 0,
                "end_seconds": 5,
                "core": True,
                "motion_required": True,
                "product_visibility": "hero",
                "product_reference_required": True,
            },
            {
                "id": "scene-1",
                "type": "generated",
                "description": "Second product moment with the same id.",
                "start_seconds": 5,
                "end_seconds": 10,
                "core": True,
                "motion_required": True,
                "product_visibility": "none",
                "product_reference_required": False,
            },
        ],
    }

    with pytest.raises(Exception, match="duplicate scene id"):
        validate_artifact("scene_plan", scene_plan, pipeline_type="ad-video")


def test_ad_video_scene_plan_rejects_bare_trend_alignment_refs() -> None:
    """Trend refs must use the canonical trend_alignment:<id> form."""
    scene_plan = _valid_ad_video_scene_plan()
    scene_plan["scenes"][0]["trend_alignment_refs"] = ["trend-tiktok-lofi-hook"]
    scene_plan["scenes"][0]["trend_alignment_notes"] = (
        "Use warm native pacing without copying source captions or shot order."
    )

    with pytest.raises(Exception, match="trend_alignment"):
        validate_artifact("scene_plan", scene_plan, pipeline_type="ad-video")


def test_ad_video_scene_plan_rejects_non_positive_scene_duration() -> None:
    """Scenes must have positive timeline duration before assets/edit can key timing."""
    scene_plan = _valid_ad_video_scene_plan()
    scene_plan["scenes"][0]["end_seconds"] = 0

    with pytest.raises(Exception, match="end_seconds.*greater than start_seconds"):
        validate_artifact("scene_plan", scene_plan, pipeline_type="ad-video")


def test_ad_video_scene_plan_rejects_overlapping_timeline() -> None:
    """Scene timelines must be ordered and non-overlapping for deterministic edits."""
    scene_plan = _valid_ad_video_scene_plan()
    scene_plan["scenes"][1]["start_seconds"] = 3.5

    with pytest.raises(Exception, match="overlaps previous scene"):
        validate_artifact("scene_plan", scene_plan, pipeline_type="ad-video")


def test_ad_video_scene_plan_rejects_timeline_gaps() -> None:
    """Scene durations must cover the timeline instead of hiding blank gaps."""
    scene_plan = _valid_ad_video_scene_plan()
    scene_plan["scenes"][1]["start_seconds"] = 5
    scene_plan["scenes"][1]["duration_seconds"] = 5

    with pytest.raises(Exception, match="gap before scene"):
        validate_artifact("scene_plan", scene_plan, pipeline_type="ad-video")


def test_ad_video_scene_plan_rejects_duration_seconds_drift() -> None:
    """Optional duration_seconds must agree with start/end when present."""
    scene_plan = _valid_ad_video_scene_plan()
    scene_plan["scenes"][0]["duration_seconds"] = 9

    with pytest.raises(Exception, match="duration_seconds"):
        validate_artifact("scene_plan", scene_plan, pipeline_type="ad-video")


def test_ad_video_scene_plan_rejects_total_duration_mismatch() -> None:
    """Scene-plan total duration must match the final timeline end."""
    scene_plan = _valid_ad_video_scene_plan()
    scene_plan["total_duration_seconds"] = 8

    with pytest.raises(Exception, match="total_duration_seconds"):
        validate_artifact("scene_plan", scene_plan, pipeline_type="ad-video")


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


def test_ad_video_production_bible_requires_approval_flags_and_cta() -> None:
    from tests.qa.test_artifact_chain import PRODUCTION_BIBLE_VALID

    bible = deepcopy(PRODUCTION_BIBLE_VALID)
    validate_artifact("production_bible", bible, pipeline_type="ad-video")

    not_approved = deepcopy(bible)
    not_approved["approval"]["execution_approved"] = False
    with pytest.raises(Exception, match="execution_approved"):
        validate_artifact("production_bible", not_approved, pipeline_type="ad-video")

    missing_cta = deepcopy(bible)
    missing_cta["identity"]["cta"] = None
    with pytest.raises(Exception, match="cta"):
        validate_artifact("production_bible", missing_cta, pipeline_type="ad-video")


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


def test_ad_video_publish_log_requires_complete_output_file_matrix() -> None:
    publish_log = {
        "version": "1.0",
        "pipeline": "ad-video",
        "brand_name": "Acme",
        "entries": [
            {
                "platform": "local-export",
                "status": "exported",
                "timestamp": "2026-05-25T00:00:00Z",
                "export_path": "renders/output_16x9.mp4",
            }
        ],
    }

    with pytest.raises(Exception):
        validate_artifact("publish_log", publish_log, pipeline_type="ad-video")

    publish_log["output_file_matrix"] = []
    with pytest.raises(Exception):
        validate_artifact("publish_log", publish_log, pipeline_type="ad-video")

    publish_log["output_file_matrix"] = [
        {
            "file": "renders/output_16x9.mp4",
            "variant": "16:9",
            "duration_seconds": 30.0,
            "target_platforms": ["youtube"],
            "metadata": {
                "title": "Acme Launch",
                "description": "A direct product story.",
                "tags": ["Acme", "ad"],
                "cta_url": "https://example.com",
            },
            "thumbnail_concept": "Product hero frame with short headline",
        }
    ]
    validate_artifact("publish_log", publish_log, pipeline_type="ad-video")

    missing_metadata = deepcopy(publish_log)
    del missing_metadata["output_file_matrix"][0]["metadata"]["title"]
    with pytest.raises(Exception):
        validate_artifact("publish_log", missing_metadata, pipeline_type="ad-video")


def test_ad_video_render_report_requires_verified_stereo_outputs() -> None:
    render_report = {
        "version": "1.0",
        "renderer": "remotion",
        "outputs": [
            {
                "path": "renders/output_16x9.mp4",
                "format": "mp4",
                "resolution": "1920x1080",
                "duration_seconds": 30.0,
                "variant": "16:9",
                "audio_channels": 2,
            }
        ],
        "probe_results": {
            "16:9": {
                "duration_check": "PASS",
                "resolution_check": "PASS",
                "audio_check": "PASS",
            }
        },
    }

    missing_audio = deepcopy(render_report)
    del missing_audio["outputs"][0]["audio_channels"]
    with pytest.raises(Exception, match="audio_channels"):
        validate_artifact("render_report", missing_audio, pipeline_type="ad-video")

    failed_probe = deepcopy(render_report)
    failed_probe["probe_results"]["16:9"]["audio_check"] = "FAIL"
    with pytest.raises(Exception, match="probe_results"):
        validate_artifact("render_report", failed_probe, pipeline_type="ad-video")

    missing_probe_check = deepcopy(render_report)
    del missing_probe_check["probe_results"]["16:9"]["audio_check"]
    with pytest.raises(Exception, match="audio_check"):
        validate_artifact(
            "render_report", missing_probe_check, pipeline_type="ad-video"
        )

    zero_duration = deepcopy(render_report)
    zero_duration["outputs"][0]["duration_seconds"] = 0
    with pytest.raises(Exception, match="duration_seconds"):
        validate_artifact("render_report", zero_duration, pipeline_type="ad-video")

    validate_artifact("render_report", render_report, pipeline_type="ad-video")
