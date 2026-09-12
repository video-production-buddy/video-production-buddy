"""Cross-stage chain integrity tests for ad-video pipeline.

Validates that each stage's output properly feeds the next stage and that
cross-artifact consistency checks catch violations:
- script.user_approved gate
- production_bible truth_contract structural validation
- production_bible intelligence block presence
- scene_plan animated scene_type requirement
- edit_decisions volume_schedule requirement
- render_report probe_results completeness
- publish_log output_file_matrix completeness
- decision_log semantic invariants
"""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest
import jsonschema
from jsonschema import ValidationError

from schemas.artifacts import validate_artifact
from tests.contracts.conftest import _minimal_production_proposal


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _valid_beat(beat_id: str = "B1", name: str = "HOOK", duration: float = 8.0, intensity: float = 0.7) -> dict:
    return {
        "beat_id": beat_id,
        "name": name,
        "duration_seconds": duration,
        "emotional_target": "intrigue",
        "intensity": intensity,
        "script_constraint": "Open with a question",
        "visual_constraint": "High-contrast product reveal",
    }


def _valid_truth_contract() -> dict:
    return {
        "objective_facts": [
            {
                "rule_id": "TC-FACT-1",
                "requirement": "Product is Acme Widget Pro.",
                "prohibited_failure": "Naming a different product.",
                "evidence_source": "brief",
                "source_confidence": "source-backed",
            }
        ],
        "physical_constraints": [
            {
                "rule_id": "TC-PHYS-1",
                "requirement": "Product is rigid.",
                "prohibited_failure": "Deformation.",
                "evidence_source": "brief",
                "source_confidence": "director-verified",
            }
        ],
        "product_geometry_rules": [
            {
                "rule_id": "TC-GEO-1",
                "requirement": "Widget has three buttons.",
                "prohibited_failure": "Wrong button count.",
                "evidence_source": "brief",
                "source_confidence": "source-backed",
            }
        ],
        "motion_coherence_rules": [
            {
                "rule_id": "TC-MOTION-1",
                "requirement": "Motion is continuous.",
                "prohibited_failure": "Teleportation.",
                "evidence_source": "director",
                "source_confidence": "director-verified",
            }
        ],
        "values_guardrails": [
            {
                "rule_id": "TC-VAL-1",
                "requirement": "No medical claims.",
                "prohibited_failure": "Unapproved claims.",
                "evidence_source": "brief",
                "source_confidence": "source-backed",
            }
        ],
    }


def _valid_production_bible() -> dict:
    return {
        "version": "1.0",
        "pipeline": "ad-video",
        "project_id": "chain-test",
        "approval": {
            "strategic_approved": True,
            "execution_approved": True,
            "modifications_log": [],
        },
        "identity": {
            "product": "Acme Widget Pro",
            "brand_name": "Acme",
            "platform": "youtube",
            "duration_target_seconds": 30,
            "key_message": "Widget Pro saves time",
            "cta": "Buy now at acme.com",
            "tone": "confident, warm",
        },
        "narrative": {
            "arc_type": "problem-solution",
            "pacing_model": "punchy",
            "hook_mechanic": "question",
            "hook_window_seconds": 3.0,
            "tension_peak_at_seconds": 20.0,
            "resolution_type": "aspiration",
            "emotional_beat_sequence": [
                _valid_beat("B1", "HOOK", 8.0, 0.7),
                _valid_beat("B2", "BUILD", 8.0, 0.5),
                _valid_beat("B3", "REVEAL", 8.0, 0.8),
                _valid_beat("B4", "CTA", 6.0, 0.65),
            ],
            "intensity_curve": [
                {"t_seconds": 0, "value": 0.7},
                {"t_seconds": 8, "value": 0.5},
                {"t_seconds": 16, "value": 0.8},
                {"t_seconds": 24, "value": 0.65},
                {"t_seconds": 30, "value": 0.65},
            ],
        },
        "intelligence": {
            "trend_alignment": {
                "selected_trend_ids": [],
                "alignments": [],
            },
            "knowledge_alignment": {
                "selected_card_ids": [],
                "alignments": [],
            },
        },
        "truth_contract": _valid_truth_contract(),
        "visual": {
            "style_mode": "cinematic",
        },
        "audio": {
            "voice_character": {
                "tone": "warm baritone",
                "pacing": "measured",
                "persona": "product narrator",
            },
            "music_direction": {
                "mood": "aspirational",
            },
            "av_sync_notes": "",
        },
        "brand_constraints": {
            "brand_name_in_final_frame": True,
        },
        "deliverables": {
            "primary": {
                "aspect_ratio": "16:9",
                "duration_seconds": 30,
            }
        },
        "compliance_manifest": {
            "checkpoints": [],
        },
    }


def _valid_script() -> dict:
    return {
        "version": "1.0",
        "title": "Chain Test Script",
        "total_duration_seconds": 16,
        "style_mode": "cinematic",
        "user_approved": True,
        "sections": [
            {
                "id": "hook",
                "beat": "hook",
                "text": "What if your widget worked this fast?",
                "start_seconds": 0,
                "end_seconds": 4,
                "speaker_directions": "Measured, intriguing.",
                "voice_performance": {
                    "emotion": "intrigue",
                    "intonation": "rising on question",
                    "rhythm": "short phrase, breath",
                    "pace": "measured",
                    "pause_after_seconds": 0.3,
                },
                "tts_directive": {"speed_mult": 0.95},
            },
            {
                "id": "build",
                "beat": "build",
                "text": "The Widget Pro handles everything.",
                "start_seconds": 4,
                "end_seconds": 8,
                "speaker_directions": "Confident proof.",
                "voice_performance": {
                    "emotion": "confidence",
                    "intonation": "steady resolve",
                    "rhythm": "medium phrases",
                    "pace": "conversational",
                    "pause_after_seconds": 0.2,
                },
                "tts_directive": {"speed_mult": 1.0},
            },
            {
                "id": "reveal",
                "beat": "reveal",
                "text": "Then the product reveal makes the speed obvious.",
                "start_seconds": 8,
                "end_seconds": 12,
                "speaker_directions": "Lift into the reveal without shouting.",
                "voice_performance": {
                    "emotion": "relief",
                    "intonation": "gentle lift then resolve",
                    "rhythm": "open phrase with a clear landing",
                    "pace": "conversational",
                    "pause_after_seconds": 0.25,
                },
                "tts_directive": {"speed_mult": 0.96},
            },
            {
                "id": "cta_brand",
                "beat": "cta_brand",
                "text": "Try Widget Pro today. Widget Pro.",
                "start_seconds": 12,
                "end_seconds": 16,
                "speaker_directions": "Clean brand landing.",
                "voice_performance": {
                    "emotion": "confidence",
                    "intonation": "settled final resolve",
                    "rhythm": "short CTA, breath, brand signature",
                    "pace": "measured",
                    "pause_after_seconds": 0.35,
                },
                "tts_directive": {"speed_mult": 0.96},
            },
        ],
    }


def _valid_edit_decisions() -> dict:
    return {
        "version": "1.0",
        "render_runtime": "ffmpeg",
        "music_strategy": "generative_loose",
        "cuts": [
            {
                "id": "cut-1",
                "source": "assets/video/scene-1.mp4",
                "in_seconds": 0,
                "out_seconds": 8,
                "maps_to_beat": "B1",
            },
        ],
        "audio": {
            "music": {
                "asset_id": "music-1",
                "volume_schedule": [
                    {"t_seconds": 0, "gain_db": -18},
                    {"t_seconds": 8, "gain_db": -18},
                ],
            },
        },
        "subtitles": {"enabled": True, "source": "sub-1"},
    }


def _valid_asset_manifest_for_edit() -> dict:
    return {
        "version": "1.0",
        "assets": [
            {
                "id": "video-1",
                "type": "video",
                "path": "assets/video/scene-1.mp4",
                "source_tool": "wan_video_api",
                "scene_id": "scene-1",
            },
            {
                "id": "narr-1",
                "type": "narration",
                "path": "assets/audio/narr-1.mp3",
                "source_tool": "tts_selector",
                "scene_id": "scene-1",
            },
            {
                "id": "music-1",
                "type": "music",
                "path": "assets/music/bed.mp3",
                "source_tool": "minimax_music",
                "scene_id": "global",
            },
            {
                "id": "sfx-1",
                "type": "sfx",
                "path": "assets/audio/whoosh.wav",
                "source_tool": "audio_mixer",
                "scene_id": "scene-1",
            },
            {
                "id": "overlay-1",
                "type": "image",
                "path": "assets/images/logo.png",
                "source_tool": "wanx_image",
                "scene_id": "scene-1",
            },
            {
                "id": "sub-1",
                "type": "subtitle",
                "path": "assets/subtitles.ass",
                "source_tool": "subtitle_gen",
                "scene_id": "global",
            },
        ],
        "costs": [
            {"tool": "wan_video_api", "cost_usd": 0.18},
            {"tool": "tts_selector", "cost_usd": 0.02},
            {"tool": "minimax_music", "cost_usd": 0.10},
            {"tool": "audio_mixer", "cost_usd": 0.0},
            {"tool": "wanx_image", "cost_usd": 0.05},
            {"tool": "subtitle_gen", "cost_usd": 0.0},
        ],
        "subtitle_file": "assets/subtitles.ass",
        "total_cost_usd": 0.35,
    }


def _valid_scene_plan_for_edit() -> dict:
    return {
        "version": "1.0",
        "style_mode": "cinematic",
        "total_duration_seconds": 8,
        "scenes": [
            {
                "id": "scene-1",
                "type": "generated",
                "description": "A single proof beat.",
                "start_seconds": 0,
                "end_seconds": 8,
                "duration_seconds": 8,
                "product_visibility": "none",
                "product_reference_required": False,
                "core": True,
                "motion_required": True,
            }
        ],
    }


def _valid_render_report() -> dict:
    return {
        "version": "1.0",
        "renderer": "ffmpeg",
        "outputs": [
            {
                "path": "renders/final.mp4",
                "format": "mp4",
                "resolution": "1920x1080",
                "duration_seconds": 30,
                "variant": "16:9",
                "audio_channels": 2,
            },
        ],
        "probe_results": {
            "16:9": {
                "duration_check": "PASS",
                "resolution_check": "PASS",
                "audio_check": "PASS",
            },
        },
    }


def _render_report_with_vertical_derivative() -> dict:
    report = _valid_render_report()
    report["outputs"].append(
        {
            "path": "renders/final-vertical.mp4",
            "format": "mp4",
            "resolution": "1080x1920",
            "duration_seconds": 30,
            "variant": "9:16",
            "audio_channels": 2,
        }
    )
    report["probe_results"]["9:16"] = {
        "duration_check": "PASS",
        "resolution_check": "PASS",
        "audio_check": "PASS",
    }
    return report


def _approved_decision_log(category: str, selected: str) -> dict:
    return {
        "version": "1.0",
        "project_id": "ad-test",
        "decisions": [
            {
                "decision_id": f"d-{category}",
                "stage": "edit",
                "category": category,
                "subject": f"Approved {category}",
                "options_considered": [
                    {
                        "option_id": selected,
                        "label": selected,
                        "score": 0.8,
                        "reason": "User-approved downstream selection.",
                    }
                ],
                "selected": selected,
                "reason": "User approved the downstream selection before compose.",
                "user_visible": True,
                "user_approved": True,
            }
        ],
    }


def _valid_final_review() -> dict:
    return {
        "version": "1.0",
        "output_path": "renders/final.mp4",
        "status": "pass",
        "checks": {
            "technical_probe": {
                "valid_container": True,
                "duration_seconds": 30,
                "resolution": "1920x1080",
                "fps": 30,
                "has_audio": True,
                "codec": "h264",
                "file_size_bytes": 1200000,
                "issues": [],
            },
            "technical_qc_review": {
                "outputs": [
                    {
                        "output_path": "renders/final.mp4",
                        "variant": "16:9",
                        "report_path": "artifacts/technical_qc_primary.json",
                        "scan_status": "pass",
                        "warning_count": 0,
                        "findings": [],
                        "supplemental_checks": [],
                        "unresolved_count": 0,
                    }
                ],
                "unresolved_count": 0,
            },
            "visual_spotcheck": {
                "frames_sampled": 4,
                "frame_paths": [
                    "assets/keyframes/final/open.png",
                    "assets/keyframes/final/mid.png",
                    "assets/keyframes/final/climax.png",
                    "assets/keyframes/final/end.png",
                ],
                "black_frames_detected": False,
                "broken_overlays": False,
                "missing_assets": False,
                "unreadable_text": False,
                "issues": [],
            },
            "audio_spotcheck": {
                "narration_present": True,
                "music_present": True,
                "unexpected_silence": False,
                "clipping_detected": False,
                "mix_intelligible": True,
                "issues": [],
            },
            "promise_preservation": {
                "delivery_promise_honored": True,
                "renderer_family_used": "product-reveal",
                "render_runtime_used": "ffmpeg",
                "runtime_swap_detected": False,
                "runtime_swap_check": "ok - runtime matched approved proposal",
                "motion_ratio_actual": 0.85,
                "silent_downgrade_detected": False,
                "issues": [],
            },
            "subtitle_check": {
                "subtitles_expected": True,
                "subtitles_present": True,
                "coverage_ratio": 1.0,
                "timing_drift_detected": False,
                "issues": [],
            },
        },
        "issues_found": [],
        "recommended_action": "present_to_user",
    }


def _valid_publish_log() -> dict:
    return {
        "version": "1.0",
        "entries": [
            {
                "platform": "youtube",
                "status": "exported",
                "timestamp": "2026-05-26T12:00:00Z",
                "export_path": "renders/final.mp4",
            },
        ],
        "output_file_matrix": [
            {
                "file": "renders/final.mp4",
                "variant": "16:9",
                "duration_seconds": 30,
                "target_platforms": ["youtube"],
                "thumbnail_concept": "Product hero shot",
                "metadata": {
                    "title": "Acme Widget Pro",
                    "description": "See the Widget Pro in action",
                    "tags": ["widget", "product"],
                    "cta_url": "https://acme.com",
                },
            },
        ],
    }


def _valid_decision_log() -> dict:
    return {
        "version": "1.0",
        "project_id": "chain-test",
        "decisions": [
            {
                "decision_id": "d-001",
                "stage": "proposal",
                "category": "render_runtime_selection",
                "subject": "Select runtime",
                "options_considered": [
                    {"option_id": "ffmpeg", "label": "FFmpeg", "score": 0.9, "reason": "Best fit"},
                    {
                        "option_id": "remotion",
                        "label": "Remotion",
                        "score": 0.6,
                        "reason": "Available but unnecessary for this fixture.",
                        "rejected_because": "No motion-graphics scene stack required.",
                    },
                    {
                        "option_id": "hyperframes",
                        "label": "HyperFrames",
                        "score": 0.4,
                        "reason": "Considered for HTML/GSAP motion.",
                        "rejected_because": "Not needed for this fixture runtime.",
                    },
                ],
                "selected": "ffmpeg",
                "reason": "Best fit for cinematic",
                "user_visible": True,
                "user_approved": True,
            },
        ],
    }


# ---------------------------------------------------------------------------
# Script user_approved gate
# ---------------------------------------------------------------------------


class TestScriptUserApprovedGate:
    def test_script_without_user_approved_rejected(self) -> None:
        script = _valid_script()
        del script["user_approved"]
        with pytest.raises(ValidationError, match="user_approved"):
            validate_artifact("script", script, pipeline_type="ad-video")

    def test_script_user_approved_false_rejected(self) -> None:
        script = _valid_script()
        script["user_approved"] = False
        with pytest.raises(ValidationError, match="user_approved"):
            validate_artifact("script", script, pipeline_type="ad-video")

    def test_script_user_approved_true_passes(self) -> None:
        script = _valid_script()
        validate_artifact("script", script, pipeline_type="ad-video")

    def test_non_ad_video_script_does_not_require_user_approved(self) -> None:
        script = _valid_script()
        del script["user_approved"]
        del script["style_mode"]
        validate_artifact("script", script, pipeline_type="cinematic")


# ---------------------------------------------------------------------------
# Production bible truth_contract validation
# ---------------------------------------------------------------------------


class TestProductionBibleTruthContract:
    def test_missing_truth_contract_rejected(self) -> None:
        bible = _valid_production_bible()
        del bible["truth_contract"]
        with pytest.raises(ValidationError, match="truth_contract"):
            validate_artifact("production_bible", bible, pipeline_type="ad-video")

    def test_empty_truth_section_rejected(self) -> None:
        bible = _valid_production_bible()
        bible["truth_contract"]["objective_facts"] = []
        with pytest.raises(ValidationError, match="objective_facts"):
            validate_artifact("production_bible", bible, pipeline_type="ad-video")

    def test_missing_physical_constraints_rejected(self) -> None:
        bible = _valid_production_bible()
        del bible["truth_contract"]["physical_constraints"]
        with pytest.raises(ValidationError, match="physical_constraints"):
            validate_artifact("production_bible", bible, pipeline_type="ad-video")

    def test_complete_truth_contract_passes(self) -> None:
        bible = _valid_production_bible()
        validate_artifact("production_bible", bible, pipeline_type="ad-video")


# ---------------------------------------------------------------------------
# Production bible intelligence block validation
# ---------------------------------------------------------------------------


class TestProductionBibleIntelligence:
    def test_missing_trend_alignment_rejected(self) -> None:
        bible = _valid_production_bible()
        del bible["intelligence"]["trend_alignment"]
        with pytest.raises(ValidationError, match="trend_alignment"):
            validate_artifact("production_bible", bible, pipeline_type="ad-video")

    def test_missing_knowledge_alignment_rejected(self) -> None:
        bible = _valid_production_bible()
        del bible["intelligence"]["knowledge_alignment"]
        with pytest.raises(ValidationError, match="knowledge_alignment"):
            validate_artifact("production_bible", bible, pipeline_type="ad-video")

    def test_empty_alignments_pass(self) -> None:
        bible = _valid_production_bible()
        validate_artifact("production_bible", bible, pipeline_type="ad-video")

    def test_no_intelligence_block_rejected_by_schema(self) -> None:
        bible = _valid_production_bible()
        del bible["intelligence"]
        with pytest.raises(ValidationError, match="intelligence"):
            validate_artifact("production_bible", bible, pipeline_type="ad-video")


# ---------------------------------------------------------------------------
# Scene plan animated scene_type requirement
# ---------------------------------------------------------------------------


class TestScenePlanAnimatedSceneType:
    def test_animated_scene_without_scene_type_rejected(self) -> None:
        plan = {
            "version": "1.0",
            "user_approved": True,
            "style_mode": "animated",
            "scenes": [
                {
                    "id": "scene-1",
                    "type": "animation",
                    "description": "Animated scene",
                    "start_seconds": 0,
                    "end_seconds": 5,
                    "product_visibility": "none",
                    "product_reference_required": False,
                    "core": True,
                    "motion_required": True,
                },
            ],
        }
        with pytest.raises(ValidationError, match="scene_type"):
            validate_artifact("scene_plan", plan, pipeline_type="ad-video")

    def test_cinematic_scene_without_scene_type_passes(self) -> None:
        plan = {
            "version": "1.0",
            "user_approved": True,
            "style_mode": "cinematic",
            "scenes": [
                {
                    "id": "scene-1",
                    "type": "broll",
                    "description": "Cinematic broll",
                    "start_seconds": 0,
                    "end_seconds": 5,
                    "product_visibility": "none",
                    "product_reference_required": False,
                    "core": True,
                    "motion_required": True,
                },
            ],
        }
        validate_artifact("scene_plan", plan, pipeline_type="ad-video")


# ---------------------------------------------------------------------------
# Edit decisions volume_schedule requirement
# ---------------------------------------------------------------------------


class TestEditDecisionsVolumeSchedule:
    def test_missing_volume_schedule_rejected(self) -> None:
        ed = _valid_edit_decisions()
        del ed["audio"]["music"]["volume_schedule"]
        with pytest.raises(ValidationError, match="volume_schedule"):
            validate_artifact("edit_decisions", ed, pipeline_type="ad-video")

    def test_none_music_strategy_skips_volume_schedule(self) -> None:
        ed = _valid_edit_decisions()
        ed["music_strategy"] = "none"
        del ed["audio"]["music"]["volume_schedule"]
        validate_artifact("edit_decisions", ed, pipeline_type="ad-video")

    def test_music_strategy_must_be_top_level_not_metadata_only(self) -> None:
        ed = _valid_edit_decisions()
        ed["metadata"] = {"music_strategy": ed.pop("music_strategy")}

        with pytest.raises(ValidationError, match="music_strategy"):
            validate_artifact("edit_decisions", ed, pipeline_type="ad-video")

    def test_speed_adjusted_cuts_preserve_timeline_total_duration(self) -> None:
        ed = _valid_edit_decisions()
        ed["total_duration_seconds"] = 10
        ed["cuts"] = [
            {
                "id": "fast-forward",
                "source": "assets/video/scene-1.mp4",
                "in_seconds": 0,
                "out_seconds": 10,
                "speed": 2.0,
                "maps_to_beat": "B1",
            }
        ]
        ed["audio"]["music"]["volume_schedule"][-1]["t_seconds"] = 10

        validate_artifact("edit_decisions", ed, pipeline_type="ad-video")

    def test_cut_without_beat_label_rejected(self) -> None:
        ed = _valid_edit_decisions()
        del ed["cuts"][0]["maps_to_beat"]
        with pytest.raises(ValidationError, match="beat"):
            validate_artifact("edit_decisions", ed, pipeline_type="ad-video")


# ---------------------------------------------------------------------------
# Render report probe_results validation
# ---------------------------------------------------------------------------


class TestRenderReportProbeResults:
    def test_duplicate_output_variant_rejected(self) -> None:
        report = _valid_render_report()
        duplicate = deepcopy(report["outputs"][0])
        duplicate["path"] = "renders/final-copy.mp4"
        report["outputs"].append(duplicate)

        with pytest.raises(ValidationError, match="duplicate output variant"):
            validate_artifact("render_report", report, pipeline_type="ad-video")

    def test_duplicate_output_path_rejected(self) -> None:
        report = _valid_render_report()
        duplicate = deepcopy(report["outputs"][0])
        duplicate["variant"] = "9:16"
        report["outputs"].append(duplicate)
        report["probe_results"]["9:16"] = deepcopy(report["probe_results"]["16:9"])

        with pytest.raises(ValidationError, match="duplicate output path"):
            validate_artifact("render_report", report, pipeline_type="ad-video")

    def test_missing_renderer_rejected(self) -> None:
        report = _valid_render_report()
        del report["renderer"]
        with pytest.raises(ValidationError, match="renderer"):
            validate_artifact("render_report", report, pipeline_type="ad-video")

    def test_missing_probe_results_rejected(self) -> None:
        report = _valid_render_report()
        del report["probe_results"]
        with pytest.raises(ValidationError, match="probe_results"):
            validate_artifact("render_report", report, pipeline_type="ad-video")

    def test_non_stereo_audio_rejected(self) -> None:
        report = _valid_render_report()
        report["outputs"][0]["audio_channels"] = 1
        with pytest.raises(ValidationError, match="audio_channels"):
            validate_artifact("render_report", report, pipeline_type="ad-video")

    def test_failed_probe_check_rejected(self) -> None:
        report = _valid_render_report()
        report["probe_results"]["16:9"]["duration_check"] = "FAIL"
        with pytest.raises(ValidationError, match="duration_check"):
            validate_artifact("render_report", report, pipeline_type="ad-video")

    def test_probe_result_for_unrendered_variant_rejected(self) -> None:
        report = _valid_render_report()
        report["probe_results"]["9:16"] = {
            "duration_check": "PASS",
            "resolution_check": "PASS",
            "audio_check": "PASS",
        }

        with pytest.raises(ValidationError, match="unrendered variant"):
            validate_artifact("render_report", report, pipeline_type="ad-video")

    def test_valid_render_report_passes(self) -> None:
        validate_artifact("render_report", _valid_render_report(), pipeline_type="ad-video")


# ---------------------------------------------------------------------------
# Render report variant semantics
# ---------------------------------------------------------------------------


class TestRenderReportVariantSemantics:
    def test_aspect_ratio_variant_resolution_must_match_label(self) -> None:
        report = _valid_render_report()
        report["outputs"][0]["variant"] = "9:16"
        report["probe_results"] = {
            "9:16": {
                "duration_check": "PASS",
                "resolution_check": "PASS",
                "audio_check": "PASS",
            }
        }

        with pytest.raises(ValidationError, match="resolution"):
            validate_artifact("render_report", report, pipeline_type="ad-video")

        report["outputs"][0]["resolution"] = "1080x1920"
        validate_artifact("render_report", report, pipeline_type="ad-video")

    def test_short_variant_duration_must_be_at_most_15_seconds(self) -> None:
        report = _valid_render_report()
        report["outputs"][0]["variant"] = "15s_short"
        report["probe_results"] = {
            "15s_short": {
                "duration_check": "PASS",
                "resolution_check": "PASS",
                "audio_check": "PASS",
            }
        }

        with pytest.raises(ValidationError, match="15s_short"):
            validate_artifact("render_report", report, pipeline_type="ad-video")

        report["outputs"][0]["duration_seconds"] = 15
        validate_artifact("render_report", report, pipeline_type="ad-video")


# ---------------------------------------------------------------------------
# Cross-stage proposal/bible -> render_report coverage
# ---------------------------------------------------------------------------


class TestRenderReportOutputCoverage:
    def test_render_report_must_cover_proposal_derivative_variants(self) -> None:
        proposal = _minimal_production_proposal()
        proposal["derivatives_added"] = ["9:16"]

        with pytest.raises(ValidationError, match="derivatives_added"):
            validate_artifact(
                "render_report",
                _valid_render_report(),
                pipeline_type="ad-video",
                related_artifacts={"production_proposal": proposal},
            )

        validate_artifact(
            "render_report",
            _render_report_with_vertical_derivative(),
            pipeline_type="ad-video",
            related_artifacts={"production_proposal": proposal},
        )

    def test_render_report_renderer_must_match_proposal_runtime(self) -> None:
        proposal = _minimal_production_proposal()
        proposal["render_runtime"] = "remotion"

        with pytest.raises(ValidationError, match="renderer"):
            validate_artifact(
                "render_report",
                _valid_render_report(),
                pipeline_type="ad-video",
                related_artifacts={"production_proposal": proposal},
            )

    def test_render_report_honors_approved_runtime_selection_change(self) -> None:
        proposal = _minimal_production_proposal()
        proposal["render_runtime"] = "remotion"
        edit_decisions = _valid_edit_decisions()
        edit_decisions["render_runtime"] = "ffmpeg"

        validate_artifact(
            "render_report",
            _valid_render_report(),
            pipeline_type="ad-video",
            related_artifacts={
                "production_proposal": proposal,
                "edit_decisions": edit_decisions,
                "decision_log": _approved_decision_log(
                    "render_runtime_selection",
                    "ffmpeg",
                ),
            },
        )

    def test_render_report_rejects_unapproved_runtime_selection_change(self) -> None:
        proposal = _minimal_production_proposal()
        proposal["render_runtime"] = "remotion"
        edit_decisions = _valid_edit_decisions()
        edit_decisions["render_runtime"] = "ffmpeg"

        with pytest.raises(ValidationError, match="renderer"):
            validate_artifact(
                "render_report",
                _valid_render_report(),
                pipeline_type="ad-video",
                related_artifacts={
                    "production_proposal": proposal,
                    "edit_decisions": edit_decisions,
                },
            )

    def test_render_report_must_cover_bible_primary_aspect_ratio(self) -> None:
        bible = _valid_production_bible()
        bible["deliverables"]["primary"]["aspect_ratio"] = "9:16"

        with pytest.raises(ValidationError, match="primary"):
            validate_artifact(
                "render_report",
                _valid_render_report(),
                pipeline_type="ad-video",
                related_artifacts={"production_bible": bible},
            )

        report = _valid_render_report()
        report["outputs"][0]["path"] = "renders/final-vertical.mp4"
        report["outputs"][0]["resolution"] = "1080x1920"
        report["outputs"][0]["variant"] = "9:16"
        report["probe_results"] = {
            "9:16": {
                "duration_check": "PASS",
                "resolution_check": "PASS",
                "audio_check": "PASS",
            }
        }
        validate_artifact(
            "render_report",
            report,
            pipeline_type="ad-video",
            related_artifacts={"production_bible": bible},
        )


# ---------------------------------------------------------------------------
# Final review completeness validation
# ---------------------------------------------------------------------------


class TestFinalReviewCompleteness:
    def test_passing_final_review_requires_contextual_technical_qc(self) -> None:
        review = _valid_final_review()
        del review["checks"]["technical_qc_review"]

        with pytest.raises(ValidationError, match="technical_qc_review"):
            validate_artifact("final_review", review, pipeline_type="ad-video")

    def test_passing_final_review_requires_technical_probe_data(self) -> None:
        review = _valid_final_review()
        del review["checks"]["technical_probe"]["valid_container"]

        with pytest.raises(ValidationError, match="valid_container"):
            validate_artifact("final_review", review, pipeline_type="ad-video")

    def test_passing_final_review_rejects_runtime_swap(self) -> None:
        review = _valid_final_review()
        review["checks"]["promise_preservation"]["runtime_swap_detected"] = True

        with pytest.raises(ValidationError, match="runtime_swap_detected"):
            validate_artifact("final_review", review, pipeline_type="ad-video")

    def test_passing_final_review_rejects_silent_downgrade(self) -> None:
        review = _valid_final_review()
        review["checks"]["promise_preservation"]["silent_downgrade_detected"] = True

        with pytest.raises(ValidationError, match="silent_downgrade_detected"):
            validate_artifact("final_review", review, pipeline_type="ad-video")

    def test_passing_final_review_rejects_top_level_issues_found(self) -> None:
        review = _valid_final_review()
        review["issues_found"] = ["Visual spotcheck found unreadable CTA text."]

        with pytest.raises(ValidationError, match="issues_found"):
            validate_artifact("final_review", review, pipeline_type="ad-video")

    def test_passing_final_review_rejects_check_level_issues(self) -> None:
        review = _valid_final_review()
        review["checks"]["technical_probe"]["issues"] = ["ffprobe failed once"]

        with pytest.raises(ValidationError, match="technical_probe.issues"):
            validate_artifact("final_review", review, pipeline_type="ad-video")

    def test_valid_final_review_passes(self) -> None:
        validate_artifact("final_review", _valid_final_review(), pipeline_type="ad-video")


# ---------------------------------------------------------------------------
# Cross-stage render_report -> final_review consistency
# ---------------------------------------------------------------------------


class TestRenderToFinalReviewConsistency:
    def test_final_review_output_path_must_match_render_output(self) -> None:
        report = _valid_render_report()
        review = _valid_final_review()
        review["output_path"] = "renders/not-rendered.mp4"

        with pytest.raises(ValidationError, match="output_path"):
            validate_artifact(
                "final_review",
                review,
                pipeline_type="ad-video",
                related_artifacts={"render_report": report},
            )

    def test_final_review_technical_probe_must_match_render_output(self) -> None:
        report = _valid_render_report()
        review = _valid_final_review()
        review["checks"]["technical_probe"]["duration_seconds"] = 28.0

        with pytest.raises(ValidationError, match="duration_seconds"):
            validate_artifact(
                "final_review",
                review,
                pipeline_type="ad-video",
                related_artifacts={"render_report": report},
            )

    def test_final_review_runtime_must_match_render_report_renderer(self) -> None:
        report = _valid_render_report()
        review = _valid_final_review()
        review["checks"]["promise_preservation"]["render_runtime_used"] = "remotion"

        with pytest.raises(ValidationError, match="render_runtime_used"):
            validate_artifact(
                "final_review",
                review,
                pipeline_type="ad-video",
                related_artifacts={"render_report": report},
            )

    def test_final_review_must_cover_every_rendered_output(self) -> None:
        report = _render_report_with_vertical_derivative()
        review = _valid_final_review()

        with pytest.raises(ValidationError, match="reviewed_outputs"):
            validate_artifact(
                "final_review",
                review,
                pipeline_type="ad-video",
                related_artifacts={"render_report": report},
            )

        review["reviewed_outputs"] = [
            {
                "path": "renders/final.mp4",
                "variant": "16:9",
                "duration_seconds": 30,
                "resolution": "1920x1080",
            },
            {
                "path": "renders/final-vertical.mp4",
                "variant": "9:16",
                "duration_seconds": 30,
                "resolution": "1080x1920",
            },
        ]
        review["checks"]["technical_qc_review"]["outputs"].append(
            {
                "output_path": "renders/final-vertical.mp4",
                "variant": "9:16",
                "report_path": "artifacts/technical_qc_9x16.json",
                "scan_status": "pass",
                "warning_count": 0,
                "findings": [],
                "supplemental_checks": [],
                "unresolved_count": 0,
            }
        )
        validate_artifact(
            "final_review",
            review,
            pipeline_type="ad-video",
            related_artifacts={"render_report": report},
        )

    def test_technical_qc_review_must_cover_every_rendered_output(self) -> None:
        report = _render_report_with_vertical_derivative()
        review = _valid_final_review()
        review["reviewed_outputs"] = [
            {
                "path": output["path"],
                "variant": output["variant"],
                "duration_seconds": output["duration_seconds"],
                "resolution": output["resolution"],
            }
            for output in report["outputs"]
        ]

        with pytest.raises(ValidationError, match="technical_qc_review.outputs"):
            validate_artifact(
                "final_review",
                review,
                pipeline_type="ad-video",
                related_artifacts={"render_report": report},
            )

    def test_final_review_subtitle_expectation_must_match_proposal(self) -> None:
        proposal = _minimal_production_proposal()
        proposal["subtitles"]["mode"] = "off"
        review = _valid_final_review()

        with pytest.raises(ValidationError, match="subtitles_expected"):
            validate_artifact(
                "final_review",
                review,
                pipeline_type="ad-video",
                related_artifacts={
                    "render_report": _valid_render_report(),
                    "production_proposal": proposal,
                },
            )

    def test_final_review_rejects_unexpected_subtitles_when_proposal_opted_out(self) -> None:
        proposal = _minimal_production_proposal()
        proposal["subtitles"]["mode"] = "off"
        review = _valid_final_review()
        review["checks"]["subtitle_check"]["subtitles_expected"] = False
        review["checks"]["subtitle_check"]["subtitles_present"] = True

        with pytest.raises(ValidationError, match="subtitles_present"):
            validate_artifact(
                "final_review",
                review,
                pipeline_type="ad-video",
                related_artifacts={
                    "render_report": _valid_render_report(),
                    "production_proposal": proposal,
                },
            )

        review["checks"]["subtitle_check"]["subtitles_present"] = False
        with pytest.raises(ValidationError, match="coverage_ratio"):
            validate_artifact(
                "final_review",
                review,
                pipeline_type="ad-video",
                related_artifacts={
                    "render_report": _valid_render_report(),
                    "production_proposal": proposal,
                },
            )

        review["checks"]["subtitle_check"]["coverage_ratio"] = 0
        validate_artifact(
            "final_review",
            review,
            pipeline_type="ad-video",
            related_artifacts={
                "render_report": _valid_render_report(),
                "production_proposal": proposal,
            },
        )

    def test_final_review_music_presence_must_match_proposal_strategy(self) -> None:
        proposal = _minimal_production_proposal()
        proposal["music_strategy"] = "none"
        review = _valid_final_review()

        with pytest.raises(ValidationError, match="music_present"):
            validate_artifact(
                "final_review",
                review,
                pipeline_type="ad-video",
                related_artifacts={
                    "render_report": _valid_render_report(),
                    "production_proposal": proposal,
                },
            )

        review["checks"]["audio_spotcheck"]["music_present"] = False
        validate_artifact(
            "final_review",
            review,
            pipeline_type="ad-video",
            related_artifacts={
                "render_report": _valid_render_report(),
                "production_proposal": proposal,
            },
        )

        proposal["music_strategy"] = "generative_loose"
        with pytest.raises(ValidationError, match="music_present"):
            validate_artifact(
                "final_review",
                review,
                pipeline_type="ad-video",
                related_artifacts={
                    "render_report": _valid_render_report(),
                    "production_proposal": proposal,
                },
            )

    def test_final_review_honors_approved_music_strategy_change_to_none(self) -> None:
        proposal = _minimal_production_proposal()
        proposal["music_strategy"] = "generative_loose"
        edit_decisions = _valid_edit_decisions()
        edit_decisions["music_strategy"] = "none"
        edit_decisions["audio"]["music"].pop("volume_schedule", None)
        review = _valid_final_review()
        review["checks"]["audio_spotcheck"]["music_present"] = False

        validate_artifact(
            "final_review",
            review,
            pipeline_type="ad-video",
            related_artifacts={
                "render_report": _valid_render_report(),
                "production_proposal": proposal,
                "edit_decisions": edit_decisions,
                "decision_log": _approved_decision_log(
                    "music_strategy_selection",
                    "none",
                ),
            },
        )

    def test_final_review_honors_approved_music_strategy_change_to_music(self) -> None:
        proposal = _minimal_production_proposal()
        proposal["music_strategy"] = "none"
        edit_decisions = _valid_edit_decisions()
        review = _valid_final_review()
        review["checks"]["audio_spotcheck"]["music_present"] = False

        with pytest.raises(ValidationError, match="music_present"):
            validate_artifact(
                "final_review",
                review,
                pipeline_type="ad-video",
                related_artifacts={
                    "render_report": _valid_render_report(),
                    "production_proposal": proposal,
                    "edit_decisions": edit_decisions,
                    "decision_log": _approved_decision_log(
                        "music_strategy_selection",
                        "generative_loose",
                    ),
                },
            )


# ---------------------------------------------------------------------------
# Publish log output_file_matrix validation
# ---------------------------------------------------------------------------


class TestPublishLogOutputFileMatrix:
    def test_duplicate_output_matrix_variant_rejected(self) -> None:
        log = _valid_publish_log()
        duplicate = deepcopy(log["output_file_matrix"][0])
        duplicate["file"] = "renders/final-copy.mp4"
        log["output_file_matrix"].append(duplicate)

        with pytest.raises(ValidationError, match="duplicate output variant"):
            validate_artifact("publish_log", log, pipeline_type="ad-video")

    def test_duplicate_output_matrix_file_rejected(self) -> None:
        log = _valid_publish_log()
        duplicate = deepcopy(log["output_file_matrix"][0])
        duplicate["variant"] = "9:16"
        log["output_file_matrix"].append(duplicate)

        with pytest.raises(ValidationError, match="duplicate output file"):
            validate_artifact("publish_log", log, pipeline_type="ad-video")

    def test_empty_matrix_rejected(self) -> None:
        log = _valid_publish_log()
        log["output_file_matrix"] = []
        with pytest.raises(ValidationError, match="output_file_matrix"):
            validate_artifact("publish_log", log, pipeline_type="ad-video")

    def test_missing_thumbnail_concept_rejected(self) -> None:
        log = _valid_publish_log()
        del log["output_file_matrix"][0]["thumbnail_concept"]
        with pytest.raises(ValidationError, match="thumbnail_concept"):
            validate_artifact("publish_log", log, pipeline_type="ad-video")

    def test_missing_metadata_tags_rejected(self) -> None:
        log = _valid_publish_log()
        log["output_file_matrix"][0]["metadata"]["tags"] = []
        with pytest.raises(ValidationError, match="tags"):
            validate_artifact("publish_log", log, pipeline_type="ad-video")

    def test_valid_publish_log_passes(self) -> None:
        validate_artifact("publish_log", _valid_publish_log(), pipeline_type="ad-video")


# ---------------------------------------------------------------------------
# Decision log semantic invariants
# ---------------------------------------------------------------------------


class TestDecisionLogSemantics:
    def test_duplicate_decision_ids_rejected(self) -> None:
        log = _valid_decision_log()
        duplicate = deepcopy(log["decisions"][0])
        log["decisions"].append(duplicate)

        with pytest.raises(ValidationError, match="duplicate decision_id"):
            validate_artifact("decision_log", log)

    def test_duplicate_option_ids_rejected(self) -> None:
        log = _valid_decision_log()
        duplicate = deepcopy(log["decisions"][0]["options_considered"][0])
        log["decisions"][0]["options_considered"].append(duplicate)

        with pytest.raises(ValidationError, match="duplicate option_id"):
            validate_artifact("decision_log", log)

    def test_selected_not_in_options_rejected(self) -> None:
        log = _valid_decision_log()
        log["decisions"][0]["selected"] = "nonexistent"
        with pytest.raises(ValidationError, match="selected"):
            validate_artifact("decision_log", log)

    def test_render_runtime_selection_requires_remotion_and_hyperframes(self) -> None:
        log = _valid_decision_log()
        log["decisions"][0]["options_considered"] = [
            {"option_id": "ffmpeg", "label": "FFmpeg", "score": 0.9, "reason": "Best fit"},
        ]
        with pytest.raises(ValidationError, match="remotion and hyperframes"):
            validate_artifact("decision_log", log)

    def test_user_approved_without_user_visible_rejected(self) -> None:
        log = _valid_decision_log()
        log["decisions"][0]["user_visible"] = False
        log["decisions"][0]["user_approved"] = True
        with pytest.raises(ValidationError, match="user_visible"):
            validate_artifact("decision_log", log)

    def test_valid_decision_log_passes(self) -> None:
        validate_artifact("decision_log", _valid_decision_log())

    def test_trend_knowledge_conflict_resolution_category_passes(self) -> None:
        log = _valid_decision_log()
        log["decisions"][0].update(
            {
                "stage": "bible",
                "category": "trend_knowledge_conflict_resolution",
                "subject": "Resolve trend and producer-knowledge conflict",
                "options_considered": [
                    {
                        "option_id": "follow-producer-principle",
                        "label": "Follow producer principle",
                        "score": 1.0,
                        "reason": "The selected trend contradicts a selected professional knowledge card.",
                    },
                    {
                        "option_id": "keep-trend",
                        "label": "Keep trend unchanged",
                        "score": 0.2,
                        "reason": "Would preserve the trend but violates the producer guardrail.",
                    },
                ],
                "selected": "follow-producer-principle",
                "reason": "User approved reframing the trend to follow the producer guardrail.",
                "user_visible": True,
                "user_approved": True,
            }
        )

        validate_artifact("decision_log", log)


# ---------------------------------------------------------------------------
# Cross-stage production_bible -> script consistency
# ---------------------------------------------------------------------------


class TestBibleToScriptConsistency:
    def test_bible_cta_null_rejected_even_with_valid_script(self) -> None:
        bible = _valid_production_bible()
        bible["identity"]["cta"] = None
        with pytest.raises(ValidationError, match="cta"):
            validate_artifact("production_bible", bible, pipeline_type="ad-video")

    def test_bible_approval_flags_false_rejected(self) -> None:
        bible = _valid_production_bible()
        bible["approval"]["strategic_approved"] = False
        with pytest.raises(ValidationError, match="strategic_approved"):
            validate_artifact("production_bible", bible, pipeline_type="ad-video")


# ---------------------------------------------------------------------------
# Artifact roundtrip file write/read
# ---------------------------------------------------------------------------


class TestArtifactRoundtrip:
    def test_script_roundtrip(self, tmp_path: Path) -> None:
        script = _valid_script()
        path = tmp_path / "script.json"
        path.write_text(json.dumps(script))
        loaded = json.loads(path.read_text())
        validate_artifact("script", loaded, pipeline_type="ad-video")

    def test_production_bible_roundtrip(self, tmp_path: Path) -> None:
        bible = _valid_production_bible()
        path = tmp_path / "production_bible.json"
        path.write_text(json.dumps(bible))
        loaded = json.loads(path.read_text())
        validate_artifact("production_bible", loaded, pipeline_type="ad-video")

    def test_decision_log_roundtrip(self, tmp_path: Path) -> None:
        log = _valid_decision_log()
        path = tmp_path / "decision_log.json"
        path.write_text(json.dumps(log))
        loaded = json.loads(path.read_text())
        validate_artifact("decision_log", loaded)

    def test_edit_decisions_roundtrip(self, tmp_path: Path) -> None:
        ed = _valid_edit_decisions()
        path = tmp_path / "edit_decisions.json"
        path.write_text(json.dumps(ed))
        loaded = json.loads(path.read_text())
        validate_artifact("edit_decisions", loaded, pipeline_type="ad-video")

    def test_render_report_roundtrip(self, tmp_path: Path) -> None:
        report = _valid_render_report()
        path = tmp_path / "render_report.json"
        path.write_text(json.dumps(report))
        loaded = json.loads(path.read_text())
        validate_artifact("render_report", loaded, pipeline_type="ad-video")

    def test_publish_log_roundtrip(self, tmp_path: Path) -> None:
        log = _valid_publish_log()
        path = tmp_path / "publish_log.json"
        path.write_text(json.dumps(log))
        loaded = json.loads(path.read_text())
        validate_artifact("publish_log", loaded, pipeline_type="ad-video")


# ---------------------------------------------------------------------------
# Cross-stage runtime propagation: proposal -> edit_decisions -> render_report
# ---------------------------------------------------------------------------


class TestRuntimePropagation:
    def test_edit_decisions_rejects_empty_render_runtime(self) -> None:
        ed = _valid_edit_decisions()
        ed["render_runtime"] = ""
        with pytest.raises(ValidationError, match="render_runtime"):
            validate_artifact("edit_decisions", ed, pipeline_type="ad-video")

    def test_render_report_rejects_empty_renderer(self) -> None:
        report = _valid_render_report()
        report["renderer"] = ""
        with pytest.raises(ValidationError, match="renderer"):
            validate_artifact("render_report", report, pipeline_type="ad-video")

    def test_edit_decisions_render_runtime_must_match_proposal(self) -> None:
        proposal = _minimal_production_proposal()
        ed = _valid_edit_decisions()
        ed["render_runtime"] = "remotion"

        with pytest.raises(ValidationError, match="render_runtime"):
            validate_artifact(
                "edit_decisions",
                ed,
                pipeline_type="ad-video",
                related_artifacts={"production_proposal": proposal},
            )

    def test_edit_decisions_accepts_user_approved_runtime_change(self) -> None:
        proposal = _minimal_production_proposal()
        ed = _valid_edit_decisions()
        ed["render_runtime"] = "remotion"
        decision_log = {
            "version": "1.0",
            "project_id": "ad-test",
            "decisions": [
                {
                    "decision_id": "d-runtime-1",
                    "stage": "edit",
                    "category": "render_runtime_selection",
                    "subject": "Runtime fallback after proposal",
                    "options_considered": [
                        {
                            "option_id": "remotion",
                            "label": "Remotion",
                            "score": 0.8,
                            "reason": "Approved runtime fallback.",
                        }
                    ],
                    "selected": "remotion",
                    "reason": "User approved the fallback runtime before compose.",
                    "user_visible": True,
                    "user_approved": True,
                }
            ],
        }

        validate_artifact(
            "edit_decisions",
            ed,
            pipeline_type="ad-video",
            related_artifacts={
                "production_proposal": proposal,
                "decision_log": decision_log,
            },
        )

    def test_edit_decisions_music_strategy_must_match_proposal(self) -> None:
        proposal = _minimal_production_proposal()
        proposal["music_strategy"] = "none"
        ed = _valid_edit_decisions()

        with pytest.raises(ValidationError, match="music_strategy"):
            validate_artifact(
                "edit_decisions",
                ed,
                pipeline_type="ad-video",
                related_artifacts={"production_proposal": proposal},
            )

    def test_edit_decisions_cannot_reenable_subtitles_after_proposal_opt_out(self) -> None:
        proposal = _minimal_production_proposal()
        proposal["subtitles"] = {
            "mode": "off",
            "language": "en",
            "user_confirmed": True,
        }
        ed = _valid_edit_decisions()
        ed["subtitles"] = {"enabled": True, "source": "sub-1"}

        with pytest.raises(ValidationError, match="subtitles.enabled"):
            validate_artifact(
                "edit_decisions",
                ed,
                pipeline_type="ad-video",
                related_artifacts={
                    "production_proposal": proposal,
                    "asset_manifest": _valid_asset_manifest_for_edit(),
                },
            )

    def test_edit_decisions_must_enable_subtitles_for_burnt_in_proposal(self) -> None:
        proposal = _minimal_production_proposal()
        proposal["subtitles"] = {
            "mode": "burnt-in",
            "language": "en",
            "user_confirmed": True,
        }
        ed = _valid_edit_decisions()
        ed["subtitles"] = {"enabled": False}

        with pytest.raises(ValidationError, match="subtitles.enabled"):
            validate_artifact(
                "edit_decisions",
                ed,
                pipeline_type="ad-video",
                related_artifacts={"production_proposal": proposal},
            )

    def test_edit_decisions_accepts_user_approved_music_strategy_change(self) -> None:
        proposal = _minimal_production_proposal()
        proposal["music_strategy"] = "none"
        ed = _valid_edit_decisions()
        decision_log = {
            "version": "1.0",
            "project_id": "ad-test",
            "decisions": [
                {
                    "decision_id": "d-music-1",
                    "stage": "edit",
                    "category": "music_strategy_selection",
                    "subject": "Music strategy fallback after proposal",
                    "options_considered": [
                        {
                            "option_id": "generative_loose",
                            "label": "Generative music",
                            "score": 0.7,
                            "reason": "User approved adding generated music.",
                        }
                    ],
                    "selected": "generative_loose",
                    "reason": "User approved the music strategy change before compose.",
                    "user_visible": True,
                    "user_approved": True,
                }
            ],
        }

        validate_artifact(
            "edit_decisions",
            ed,
            pipeline_type="ad-video",
            related_artifacts={
                "production_proposal": proposal,
                "decision_log": decision_log,
            },
        )

    def test_edit_decisions_derivative_specs_must_cover_proposal_variants(self) -> None:
        proposal = _minimal_production_proposal()
        proposal["derivatives_added"] = ["9:16"]
        ed = _valid_edit_decisions()

        with pytest.raises(ValidationError, match="derivative_specs"):
            validate_artifact(
                "edit_decisions",
                ed,
                pipeline_type="ad-video",
                related_artifacts={"production_proposal": proposal},
            )

        ed["derivative_specs"] = {"9:16": {"crop_regions": "from_scene_plan"}}
        validate_artifact(
            "edit_decisions",
            ed,
            pipeline_type="ad-video",
            related_artifacts={"production_proposal": proposal},
        )

    def test_edit_decisions_aspect_ratio_derivative_requires_crop_regions(self) -> None:
        proposal = _minimal_production_proposal()
        proposal["derivatives_added"] = ["9:16"]
        ed = _valid_edit_decisions()
        ed["derivative_specs"] = {"9:16": {}}

        with pytest.raises(ValidationError, match="crop_regions"):
            validate_artifact(
                "edit_decisions",
                ed,
                pipeline_type="ad-video",
                related_artifacts={"production_proposal": proposal},
            )

        ed["derivative_specs"] = {"9:16": {"crop_regions": "center_crop"}}
        with pytest.raises(ValidationError, match="from_scene_plan"):
            validate_artifact(
                "edit_decisions",
                ed,
                pipeline_type="ad-video",
                related_artifacts={"production_proposal": proposal},
            )

    def test_edit_decisions_duration_derivative_requires_valid_short_scene_selection(self) -> None:
        proposal = _minimal_production_proposal()
        proposal["derivatives_added"] = ["15s_short"]
        scene_plan = _valid_scene_plan_for_edit()
        scene_plan["scenes"].append(
            {
                "id": "scene-2",
                "type": "generated",
                "description": "A second proof beat.",
                "start_seconds": 8,
                "end_seconds": 17,
                "duration_seconds": 9,
                "product_visibility": "none",
                "product_reference_required": False,
                "core": True,
                "motion_required": True,
            }
        )
        ed = _valid_edit_decisions()
        ed["derivative_specs"] = {
            "15s_short": {
                "include_scenes": ["scene-1", "scene-2"],
                "total_duration_check": "<=15s",
            }
        }

        with pytest.raises(ValidationError, match="15s_short"):
            validate_artifact(
                "edit_decisions",
                ed,
                pipeline_type="ad-video",
                related_artifacts={
                    "production_proposal": proposal,
                    "scene_plan": scene_plan,
                },
            )

        ed["derivative_specs"]["15s_short"]["include_scenes"] = ["scene-1"]
        validate_artifact(
            "edit_decisions",
            ed,
            pipeline_type="ad-video",
            related_artifacts={
                "production_proposal": proposal,
                "scene_plan": scene_plan,
            },
        )


class TestEditAssetResolution:
    def test_cut_source_must_resolve_to_asset_manifest(self) -> None:
        ed = _valid_edit_decisions()
        asset_manifest = _valid_asset_manifest_for_edit()
        ed["cuts"][0]["source"] = "assets/video/missing.mp4"

        with pytest.raises(ValidationError, match="cut source"):
            validate_artifact(
                "edit_decisions",
                ed,
                pipeline_type="ad-video",
                related_artifacts={"asset_manifest": asset_manifest},
            )

    def test_cut_source_may_use_asset_id_or_manifest_path(self) -> None:
        ed = _valid_edit_decisions()
        asset_manifest = _valid_asset_manifest_for_edit()

        validate_artifact(
            "edit_decisions",
            ed,
            pipeline_type="ad-video",
            related_artifacts={"asset_manifest": asset_manifest},
        )

        ed["cuts"][0]["source"] = "video-1"
        validate_artifact(
            "edit_decisions",
            ed,
            pipeline_type="ad-video",
            related_artifacts={"asset_manifest": asset_manifest},
        )

    def test_remotion_sources_do_not_require_manifest_assets(self) -> None:
        ed = _valid_edit_decisions()
        ed["cuts"][0]["source"] = "remotion:stat_card"

        validate_artifact(
            "edit_decisions",
            ed,
            pipeline_type="ad-video",
            related_artifacts={"asset_manifest": _valid_asset_manifest_for_edit()},
        )

    def test_narration_segment_asset_id_must_resolve_to_asset_manifest(self) -> None:
        ed = _valid_edit_decisions()
        ed["audio"]["narration"] = {
            "segments": [
                {
                    "asset_id": "missing-narration",
                    "start_seconds": 0.0,
                    "end_seconds": 7.8,
                }
            ]
        }

        with pytest.raises(ValidationError, match="narration segment"):
            validate_artifact(
                "edit_decisions",
                ed,
                pipeline_type="ad-video",
                related_artifacts={"asset_manifest": _valid_asset_manifest_for_edit()},
            )

    def test_music_asset_id_required_for_music_backed_strategy(self) -> None:
        ed = _valid_edit_decisions()
        del ed["audio"]["music"]["asset_id"]

        with pytest.raises(ValidationError, match="audio.music.asset_id"):
            validate_artifact(
                "edit_decisions",
                ed,
                pipeline_type="ad-video",
                related_artifacts={"asset_manifest": _valid_asset_manifest_for_edit()},
            )

    def test_music_asset_id_must_resolve_to_music_asset(self) -> None:
        ed = _valid_edit_decisions()
        ed["audio"]["music"]["asset_id"] = "missing-music"

        with pytest.raises(ValidationError, match="audio.music.asset_id"):
            validate_artifact(
                "edit_decisions",
                ed,
                pipeline_type="ad-video",
                related_artifacts={"asset_manifest": _valid_asset_manifest_for_edit()},
            )

    def test_sfx_asset_id_must_resolve_to_asset_manifest(self) -> None:
        ed = _valid_edit_decisions()
        ed["audio"]["sfx"] = [
            {"asset_id": "missing-sfx", "start_seconds": 0.5, "volume": 0.6}
        ]

        with pytest.raises(ValidationError, match="sfx"):
            validate_artifact(
                "edit_decisions",
                ed,
                pipeline_type="ad-video",
                related_artifacts={"asset_manifest": _valid_asset_manifest_for_edit()},
            )

    def test_overlay_asset_id_must_resolve_to_asset_manifest(self) -> None:
        ed = _valid_edit_decisions()
        ed["overlays"] = [
            {
                "asset_id": "missing-overlay",
                "start_seconds": 0.5,
                "end_seconds": 2.0,
                "position": {"x": 0.1, "y": 0.1},
            }
        ]

        with pytest.raises(ValidationError, match="overlay"):
            validate_artifact(
                "edit_decisions",
                ed,
                pipeline_type="ad-video",
                related_artifacts={"asset_manifest": _valid_asset_manifest_for_edit()},
            )

    def test_enabled_subtitle_source_must_resolve_to_ass_asset(self) -> None:
        ed = _valid_edit_decisions()
        ed["subtitles"] = {"enabled": True, "source": "missing-subtitle"}

        with pytest.raises(ValidationError, match="subtitles.source"):
            validate_artifact(
                "edit_decisions",
                ed,
                pipeline_type="ad-video",
                related_artifacts={"asset_manifest": _valid_asset_manifest_for_edit()},
            )

        ed["subtitles"] = {"enabled": True, "source": "sub-1"}
        validate_artifact(
            "edit_decisions",
            ed,
            pipeline_type="ad-video",
            related_artifacts={"asset_manifest": _valid_asset_manifest_for_edit()},
        )


class TestEditTimelineContinuity:
    def test_edit_timeline_must_start_at_zero(self) -> None:
        ed = _valid_edit_decisions()
        ed["total_duration_seconds"] = 8
        ed["cuts"][0]["in_seconds"] = 1
        ed["cuts"][0]["out_seconds"] = 9

        with pytest.raises(ValidationError, match="start at 0.0"):
            validate_artifact(
                "edit_decisions",
                ed,
                pipeline_type="ad-video",
                related_artifacts={"scene_plan": _valid_scene_plan_for_edit()},
            )

    def test_edit_timeline_rejects_gaps_between_cuts(self) -> None:
        ed = _valid_edit_decisions()
        ed["total_duration_seconds"] = 8
        ed["cuts"] = [
            {
                "id": "cut-1",
                "source": "assets/video/scene-1.mp4",
                "in_seconds": 0,
                "out_seconds": 3,
                "maps_to_beat": "B1",
            },
            {
                "id": "cut-2",
                "source": "remotion:stat_card",
                "in_seconds": 4,
                "out_seconds": 9,
                "maps_to_beat": "B2",
            },
        ]

        with pytest.raises(ValidationError, match="timeline gap"):
            validate_artifact(
                "edit_decisions",
                ed,
                pipeline_type="ad-video",
                related_artifacts={"scene_plan": _valid_scene_plan_for_edit()},
            )

    def test_edit_timeline_must_match_scene_plan_duration(self) -> None:
        ed = _valid_edit_decisions()
        ed["total_duration_seconds"] = 9
        ed["cuts"][0]["out_seconds"] = 9

        with pytest.raises(ValidationError, match="scene_plan total_duration_seconds"):
            validate_artifact(
                "edit_decisions",
                ed,
                pipeline_type="ad-video",
                related_artifacts={"scene_plan": _valid_scene_plan_for_edit()},
            )

    def test_narration_segments_must_fit_within_scene_windows(self) -> None:
        ed = _valid_edit_decisions()
        ed["audio"]["narration"] = {
            "segments": [
                {
                    "asset_id": "narr-1",
                    "start_seconds": 0,
                    "end_seconds": 8.5,
                }
            ]
        }

        with pytest.raises(ValidationError, match="narration segment"):
            validate_artifact(
                "edit_decisions",
                ed,
                pipeline_type="ad-video",
                related_artifacts={
                    "asset_manifest": _valid_asset_manifest_for_edit(),
                    "scene_plan": _valid_scene_plan_for_edit(),
                },
            )

    def test_narration_segment_starting_on_scene_boundary_matches_next_scene(self) -> None:
        ed = _valid_edit_decisions()
        ed["total_duration_seconds"] = 16
        ed["cuts"] = [
            {
                "id": "cut-1",
                "source": "assets/video/scene-1.mp4",
                "in_seconds": 0,
                "out_seconds": 8,
                "maps_to_beat": "B1",
            },
            {
                "id": "cut-2",
                "source": "assets/video/scene-2.mp4",
                "in_seconds": 8,
                "out_seconds": 16,
                "maps_to_beat": "B2",
            },
        ]
        ed["audio"]["narration"] = {
            "segments": [
                {
                    "asset_id": "narr-2",
                    "start_seconds": 8,
                    "end_seconds": 15.5,
                }
            ]
        }
        scene_plan = _valid_scene_plan_for_edit()
        scene_plan["total_duration_seconds"] = 16
        scene_plan["scenes"] = [
            {
                "id": "scene-1",
                "type": "generated",
                "description": "Opening proof beat.",
                "start_seconds": 0,
                "end_seconds": 8,
                "duration_seconds": 8,
                "product_visibility": "none",
                "product_reference_required": False,
                "core": True,
                "motion_required": True,
            },
            {
                "id": "scene-2",
                "type": "generated",
                "description": "Second proof beat.",
                "start_seconds": 8,
                "end_seconds": 16,
                "duration_seconds": 8,
                "product_visibility": "none",
                "product_reference_required": False,
                "core": True,
                "motion_required": True,
            },
        ]

        validate_artifact(
            "edit_decisions",
            ed,
            pipeline_type="ad-video",
            related_artifacts={"scene_plan": scene_plan},
        )


# ---------------------------------------------------------------------------
# Cross-stage render_report -> publish_log consistency
# ---------------------------------------------------------------------------


class TestRenderToPublishConsistency:
    def test_publish_export_path_must_match_render_output(self) -> None:
        render_report = _valid_render_report()
        log = _valid_publish_log()
        log["entries"][0]["export_path"] = "renders/nonexistent.mp4"
        with pytest.raises(ValidationError, match="export_path"):
            validate_artifact(
                "publish_log",
                log,
                pipeline_type="ad-video",
                related_artifacts={"render_report": render_report},
            )

    def test_publish_matrix_must_cover_every_render_output(self) -> None:
        render_report = _valid_render_report()
        render_report["outputs"].append(
            {
                "path": "renders/final-vertical.mp4",
                "format": "mp4",
                "resolution": "1080x1920",
                "duration_seconds": 30,
                "variant": "9:16",
                "audio_channels": 2,
            }
        )
        render_report["probe_results"]["9:16"] = {
            "duration_check": "PASS",
            "resolution_check": "PASS",
            "audio_check": "PASS",
        }
        log = _valid_publish_log()

        with pytest.raises(ValidationError, match="missing rendered output"):
            validate_artifact(
                "publish_log",
                log,
                pipeline_type="ad-video",
                related_artifacts={"render_report": render_report},
            )

    def test_publish_matrix_duration_matches_render_output(self) -> None:
        render_report = _valid_render_report()
        log = _valid_publish_log()
        log["output_file_matrix"][0]["duration_seconds"] = 28.5
        with pytest.raises(ValidationError, match="duration_seconds"):
            validate_artifact(
                "publish_log",
                log,
                pipeline_type="ad-video",
                related_artifacts={"render_report": render_report},
            )

    def test_publish_matrix_empty_target_platforms_rejected(self) -> None:
        log = _valid_publish_log()
        log["output_file_matrix"][0]["target_platforms"] = []
        with pytest.raises(ValidationError, match="target_platforms"):
            validate_artifact("publish_log", log, pipeline_type="ad-video")


# ---------------------------------------------------------------------------
# Edit decisions music_strategy -> volume_schedule consistency
# ---------------------------------------------------------------------------


class TestMusicStrategyVolumeConsistency:
    def test_generative_tight_requires_volume_schedule(self) -> None:
        ed = _valid_edit_decisions()
        ed["music_strategy"] = "generative_tight"
        del ed["audio"]["music"]["volume_schedule"]
        with pytest.raises(ValidationError, match="volume_schedule"):
            validate_artifact("edit_decisions", ed, pipeline_type="ad-video")

    def test_stock_licensed_requires_volume_schedule(self) -> None:
        ed = _valid_edit_decisions()
        ed["music_strategy"] = "stock_licensed"
        del ed["audio"]["music"]["volume_schedule"]
        with pytest.raises(ValidationError, match="volume_schedule"):
            validate_artifact("edit_decisions", ed, pipeline_type="ad-video")


# ---------------------------------------------------------------------------
# Production proposal validation gates
# ---------------------------------------------------------------------------


class TestProductionProposalGates:
    def test_budget_not_confirmed_rejected(self) -> None:
        proposal = {
            "version": "1.0",
            "selected_idea_id": "C2",
            "style_mode": "cinematic",
            "render_runtime": "ffmpeg",
            "product_reference_strategy": "generate_concept_reference",
            "subtitles": {"mode": "burnt-in", "language": "en", "user_confirmed": True},
            "dubbing": [],
            "derivatives_added": [],
            "budget_confirmed": False,
            "approved_budget_usd": 5.0,
            "music_strategy": "generative_loose",
            "audio_contract": {
                "voice_provider": "qwen3",
                "voice_id": "Dylan",
                "voice_model": "qwen3-tts-instruct-flash",
                "voice_gender": "male",
                "voice_persona": "warm narrator",
                "voice_performance": {
                    "tone": "warm",
                    "baseline_emotion": "calm",
                    "emotion_arc": "curiosity -> clarity",
                    "intonation": "natural",
                    "rhythm": "varied",
                    "pause_policy": "brief pauses",
                },
                "voice_sample_approved": True,
                "target_speed_wps": 2.5,
                "target_lufs": -14,
                "max_section_drift_pct": 5,
                "duck_depth_db": -18,
            },
            "visual_contract": {
                "style_direction": "editorial-tech",
                "typography_pairing": {"display": "Inter 800", "body": "Inter 400"},
                "color_rhythm": "held-accent",
                "atmosphere": {"default_layers": [{"type": "grain", "intensity": 0.04}]},
                "anti_template_checklist": ["hero product visible before CTA"],
                "visual_asset_provider_locks": [
                    {
                        "asset_type": "image",
                        "source_tool": "wanx_image",
                        "model": "wan2.7-image-pro",
                    },
                    {
                        "asset_type": "video",
                        "source_tool": "wan_video_api",
                        "model": "wan2.6-t2v",
                    },
                    {"asset_type": "video", "source_tool": "pexels_video"},
                ],
            },
        }
        with pytest.raises(ValidationError, match="budget_confirmed"):
            validate_artifact("production_proposal", proposal, pipeline_type="ad-video")

    def test_subtitles_not_user_confirmed_rejected(self) -> None:
        proposal = {
            "version": "1.0",
            "selected_idea_id": "C2",
            "style_mode": "cinematic",
            "render_runtime": "ffmpeg",
            "product_reference_strategy": "generate_concept_reference",
            "subtitles": {"mode": "burnt-in", "language": "en", "user_confirmed": False},
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
                "voice_persona": "warm narrator",
                "voice_performance": {
                    "tone": "warm",
                    "baseline_emotion": "calm",
                    "emotion_arc": "curiosity -> clarity",
                    "intonation": "natural",
                    "rhythm": "varied",
                    "pause_policy": "brief pauses",
                },
                "voice_sample_approved": True,
                "target_speed_wps": 2.5,
                "target_lufs": -14,
                "max_section_drift_pct": 5,
                "duck_depth_db": -18,
            },
            "visual_contract": {
                "style_direction": "editorial-tech",
                "typography_pairing": {"display": "Inter 800", "body": "Inter 400"},
                "color_rhythm": "held-accent",
                "atmosphere": {"default_layers": [{"type": "grain", "intensity": 0.04}]},
                "anti_template_checklist": ["hero product visible before CTA"],
                "visual_asset_provider_locks": [
                    {
                        "asset_type": "image",
                        "source_tool": "wanx_image",
                        "model": "wan2.7-image-pro",
                    },
                    {
                        "asset_type": "video",
                        "source_tool": "wan_video_api",
                        "model": "wan2.6-t2v",
                    },
                    {"asset_type": "video", "source_tool": "pexels_video"},
                ],
            },
        }
        with pytest.raises(ValidationError, match="user_confirmed"):
            validate_artifact("production_proposal", proposal, pipeline_type="ad-video")


# ---------------------------------------------------------------------------
# Enriched brief user_approved gate
# ---------------------------------------------------------------------------


class TestEnrichedBriefUserApprovedGate:
    def test_contextual_validator_rejects_false_user_approved(self) -> None:
        from schemas.artifacts import _validate_ad_video_enriched_brief
        brief = {"user_approved": False}
        with pytest.raises(ValidationError, match="user_approved"):
            _validate_ad_video_enriched_brief(brief)

    def test_contextual_validator_rejects_missing_user_approved(self) -> None:
        from schemas.artifacts import _validate_ad_video_enriched_brief
        brief = {}
        with pytest.raises(ValidationError, match="user_approved"):
            _validate_ad_video_enriched_brief(brief)

    def test_contextual_validator_accepts_true_user_approved(self) -> None:
        from schemas.artifacts import _validate_ad_video_enriched_brief
        _validate_ad_video_enriched_brief({"user_approved": True})


# ---------------------------------------------------------------------------
# Idea options selection invariants
# ---------------------------------------------------------------------------


class TestIdeaOptionsSelection:
    def _valid_concept(self, cid: str, selected: bool = False) -> dict:
        return {
            "id": cid,
            "name": f"Concept {cid}",
            "scenario": f"A compelling scenario for {cid}.",
            "selected": selected,
            "hook_execution": "Open on a concrete before/after gap in the first three seconds.",
            "visual_metaphor": "A messy launch board resolving into a clean route.",
            "beat_mapping": {
                "hook": "Show the before/after contrast immediately.",
                "build": "Demonstrate a concrete use moment.",
                "reveal": "Reveal the product benefit in a single readable action.",
                "cta_brand": "Land the CTA and brand without adding a new claim.",
            },
            "why_this_works": "It converts the approved strategy into visible proof.",
            "knowledge_alignment_refs": ["knowledge_alignment:hook.visual-contrast.001"],
        }

    def test_no_selected_concept_rejected(self) -> None:
        ideas = {
            "version": "1.0",
            "concepts": [
                self._valid_concept("C1", False),
                self._valid_concept("C2", False),
            ],
            "selected_concept_id": "C1",
        }
        with pytest.raises(ValidationError, match="selected"):
            validate_artifact("idea_options", ideas)

    def test_two_selected_concepts_rejected(self) -> None:
        ideas = {
            "version": "1.0",
            "concepts": [
                self._valid_concept("C1", True),
                self._valid_concept("C2", True),
            ],
            "selected_concept_id": "C1",
        }
        with pytest.raises(ValidationError, match="selected"):
            validate_artifact("idea_options", ideas)

    def test_selected_id_mismatch_rejected(self) -> None:
        ideas = {
            "version": "1.0",
            "concepts": [
                self._valid_concept("C1", True),
                self._valid_concept("C2", False),
            ],
            "selected_concept_id": "C2",
        }
        with pytest.raises(ValidationError, match="selected_concept_id"):
            validate_artifact("idea_options", ideas)

    def test_valid_single_selection_passes(self) -> None:
        ideas = {
            "version": "1.0",
            "concepts": [
                self._valid_concept("C1", True),
                self._valid_concept("C2", False),
            ],
            "selected_concept_id": "C1",
        }
        validate_artifact("idea_options", ideas)


# ---------------------------------------------------------------------------
# Scene plan product visibility metadata
# ---------------------------------------------------------------------------


class TestScenePlanProductVisibility:
    def test_scene_without_product_visibility_rejected(self) -> None:
        plan = {
            "version": "1.0",
            "user_approved": True,
            "style_mode": "cinematic",
            "scenes": [
                {
                    "id": "scene-1",
                    "type": "broll",
                    "description": "A scene",
                    "start_seconds": 0,
                    "end_seconds": 5,
                    "core": True,
                    "motion_required": True,
                },
            ],
        }
        with pytest.raises(ValidationError, match="product_visibility"):
            validate_artifact("scene_plan", plan, pipeline_type="ad-video")

    def test_scene_without_product_reference_required_rejected(self) -> None:
        plan = {
            "version": "1.0",
            "user_approved": True,
            "style_mode": "cinematic",
            "scenes": [
                {
                    "id": "scene-1",
                    "type": "broll",
                    "description": "A scene",
                    "start_seconds": 0,
                    "end_seconds": 5,
                    "product_visibility": "none",
                    "core": True,
                    "motion_required": True,
                },
            ],
        }
        with pytest.raises(ValidationError, match="product_reference_required"):
            validate_artifact("scene_plan", plan, pipeline_type="ad-video")

    def test_generated_non_packshot_scene_requires_motion(self) -> None:
        plan = {
            "version": "1.0",
            "user_approved": True,
            "style_mode": "cinematic",
            "scenes": [
                {
                    "id": "scene-1",
                    "type": "generated",
                    "description": "A product interaction scene",
                    "start_seconds": 0,
                    "end_seconds": 5,
                    "product_visibility": "hero",
                    "product_reference_required": True,
                    "core": True,
                    "motion_required": False,
                },
            ],
        }

        with pytest.raises(ValidationError, match="motion_required"):
            validate_artifact("scene_plan", plan, pipeline_type="ad-video")

    def test_packshot_scene_may_be_still(self) -> None:
        plan = {
            "version": "1.0",
            "user_approved": True,
            "style_mode": "cinematic",
            "scenes": [
                {
                    "id": "scene-1",
                    "type": "generated",
                    "scene_type": "brand_landing",
                    "description": "Approved product packshot end card",
                    "start_seconds": 0,
                    "end_seconds": 5,
                    "product_visibility": "packshot",
                    "product_reference_required": True,
                    "core": True,
                    "motion_required": False,
                },
            ],
        }

        validate_artifact("scene_plan", plan, pipeline_type="ad-video")


# ---------------------------------------------------------------------------
# Render report variant probe coverage
# ---------------------------------------------------------------------------


class TestRenderReportVariantProbe:
    def test_missing_variant_in_probe_rejected(self) -> None:
        report = _valid_render_report()
        report["outputs"][0]["variant"] = "9:16"
        with pytest.raises(ValidationError, match="9:16"):
            validate_artifact("render_report", report, pipeline_type="ad-video")

    def test_extra_check_in_probe_not_all_pass_rejected(self) -> None:
        report = _valid_render_report()
        report["probe_results"]["16:9"]["noise_check"] = "FAIL"
        with pytest.raises(ValidationError, match="noise_check"):
            validate_artifact("render_report", report, pipeline_type="ad-video")

# ---------------------------------------------------------------------------
# Realistic artifact chain schema fixtures and invariants
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parent.parent.parent
SCHEMAS = ROOT / "schemas" / "artifacts"


def load_schema(name: str) -> dict:
    path = SCHEMAS / f"{name}.schema.json"
    assert path.exists(), f"Schema not found: {path}"
    with open(path) as f:
        return json.load(f)


def validate(instance: dict, schema: dict) -> None:
    jsonschema.validate(instance, schema, format_checker=jsonschema.FormatChecker())


def deep_copy(d: dict) -> dict:
    return json.loads(json.dumps(d))


# ---------------------------------------------------------------------------
# Realistic artifact fixtures (all synthetic data)
# ---------------------------------------------------------------------------

INTAKE_BRIEF_RICH = {
    "product": "Acme Productivity App",
    "brand_name": "Acme",
    "platform": "tiktok",
    "duration_target_seconds": 30,
    "demographic": "urban professionals 25-35",
    "emotional_intent": "confidence and relief",
    "key_message": "Reclaim two hours every day",
    "cta": "Try free at acme.com",
    "tone": "warm and direct",
    "reference_files": [
        {"filename": "brand_guide_2024.pdf", "inferred_role": "brand_guideline",
         "reason": "Contains color palette and typography specs"}
    ],
    "style_mode_candidate": "animated",
    "round1_questions_asked": [],
    "intake_completeness": "rich",
}

INTAKE_BRIEF_THIN = {
    "product": "Acme Productivity App",
    "platform": "tiktok",
    "duration_target_seconds": 60,
    "round1_questions_asked": [
        "Who should feel something when they watch this?",
        "What should viewers feel at the end?",
    ],
    "intake_completeness": "thin",
}

INTELLIGENCE_BRIEF_VALID = {
    "professional_knowledge": {
        "retrieval_backend": "bm25",
        "cards_used": [
            {
                "card_id": "hook.visual-contrast.001",
                "domain": "hook_mechanic",
                "source_ref": "knowledge_alignment:hook.visual-contrast.001",
                "summary": "A short-form ad hook should land as a visible contrast before the viewer has time to scroll.",
                "principles": ["Create a concrete contrast before explaining the product."],
                "relevance_score": 0.92,
                "why_relevant": "The platform is TikTok, Reels, Shorts, or another fast-scroll placement.",
                "avoid_when": ["The contrast would exaggerate the product claim beyond approved evidence."],
                "downstream_targets": ["hook", "script", "scene_plan", "visual"],
                "failure_patterns": ["Generic shock image unrelated to the offer."],
                "execution_techniques": ["Open with a before/after visual gap, then resolve into the product promise."],
            },
            {
                "card_id": "rhythm.emotional-wave.001",
                "domain": "emotional_rhythm",
                "source_ref": "knowledge_alignment:rhythm.emotional-wave.001",
                "summary": "Professional commercial rhythm alternates pressure and release so the viewer feels progression.",
                "principles": ["Alternate pressure and release across the ad arc."],
                "relevance_score": 0.86,
                "why_relevant": "The brief asks for emotion, aspiration, premium energy, or a cinematic feeling.",
                "avoid_when": ["The format is a purely factual compliance notice."],
                "downstream_targets": ["script", "scene_plan", "pacing", "audio"],
                "failure_patterns": ["Flat pacing that never gives the viewer release."],
                "execution_techniques": ["Map tension to the hook/build and release to the reveal/CTA."],
            },
        ],
        "application_recommendations": [
            {
                "card_id": "hook.visual-contrast.001",
                "target": "hook",
                "recommendation": "Make the first second show a before/after gap, contradiction, or sensory mismatch.",
                "confidence": "producer-doctrine",
            }
        ],
        "contraindications": [
            {
                "card_id": "hook.visual-contrast.001",
                "avoid_when": "The contrast would exaggerate the product claim beyond approved evidence.",
                "reason": "Apply only when the brief and truth contract allow it.",
            }
        ],
        "gaps": [],
        "warnings": [],
    },
    "audience_psychographics": {
        "emotional_profile": "time-starved, achievement-oriented, frustrated by inefficiency",
        "core_pain_point": "feel busy but not productive; hours vanish without progress",
        "aspiration": "reclaim control and end each day with a clear conscience",
    },
    "platform_trends": [
        {"signal": "lo-fi aesthetic +34% on TikTok ads", "source": "Sprout Social 2026", "relevance": "Matches calm-confident tone"},
        {"signal": "pain-first hooks outperform benefit-first 2.3x", "source": "TikTok Creative Centre 2026", "relevance": "Validates problem-first hook"},
        {"signal": "15-30s dominates productivity app category", "source": "Meta benchmark 2025", "relevance": "Confirms 30s target"},
    ],
    "hit_ads_analyzed": [
        {"title": "Monday.com Work OS", "platform": "youtube", "arc_type": "problem-solution",
         "hook_mechanic": "statement", "what_works": "Pain-first hook, product reveal at 60%",
         "adopted": True, "adaptation": "Compress problem beat from 12s to 7s"},
        {"title": "Notion Feel the Flow", "platform": "tiktok", "arc_type": "desire-fulfillment",
         "hook_mechanic": "visual-contrast", "what_works": "Before/after desk comparison",
         "adopted": False, "adaptation": ""},
        {"title": "Asana Clarity Campaign", "platform": "linkedin", "arc_type": "problem-solution",
         "hook_mechanic": "stat", "what_works": "Surprising stat opens: 60% of workday is wasted",
         "adopted": False, "adaptation": ""},
    ],
    "rejected_approaches": [
        {"approach": "celebrity endorsement",
         "reason": "Oversaturated in productivity SaaS 2025-2026; peer signals outperform"},
        {"approach": "generic work-smarter tagline",
         "reason": "Used by 7/10 competitors with no differentiation"},
    ],
    "recommendations": {
        "arc_type": {"value": "problem-solution", "confidence": "research-grounded",
                     "rationale": "Dominant in 2/3 analyzed hit ads; highest completion rate"},
        "pacing_model": {"value": "escalating", "confidence": "pattern-inferred",
                         "rationale": "Fast-cut hooks in analyzed ads suggest escalation"},
        "hook_mechanic": {"value": "statement", "confidence": "research-grounded",
                          "rationale": "Monday.com pain-first statement — directly validated"},
        "hook_window_seconds": {"value": 3, "confidence": "research-grounded",
                                "rationale": "TikTok 3s scroll threshold per platform docs"},
        "editing_rhythm_by_beat": {
            "hook": {
                "value": {"cuts_density": "rapid", "avg_shot_duration_seconds": 1.5, "transition_style": "hard_cut"},
                "confidence": "pattern-inferred",
            },
            "problem": {
                "value": {"cuts_density": "moderate", "avg_shot_duration_seconds": 3.0, "transition_style": "hard_cut"},
                "confidence": "default-heuristic",
            },
        },
        "overall_rationale": (
            "Problem-solution with escalating pacing dominates high-performing productivity ads. "
            "Pain-first hook with product reveal at 60% mark, validated by Monday.com benchmark."
        ),
    },
}

PRODUCTION_BIBLE_VALID = {
    "version": "1.0",
    "pipeline": "ad-video",
    "project_id": "acme-tiktok-30s-v1",
    "approval": {"strategic_approved": True, "execution_approved": True, "modifications_log": []},
    "identity": {
        "product": "Acme Productivity App",
        "brand_name": "Acme",
        "platform": "tiktok",
        "duration_target_seconds": 30,
        "key_message": "Reclaim two hours every day",
        "cta": "Try free at acme.com",
        "tone": "warm and direct",
        "target_audience": {
            "demographic": "urban professionals 25-35",
            "emotional_profile": "time-starved, achievement-oriented",
            "core_pain_point": "feel busy but not productive",
            "aspiration": "reclaim control and end each day with clarity",
        },
    },
    "narrative": {
        "arc_type": "problem-solution",
        "pacing_model": "escalating",
        "hook_mechanic": "statement",
        "hook_window_seconds": 3,
        "tension_peak_at_seconds": 18,
        "resolution_type": "aspiration",
        "emotional_beat_sequence": [
            {"beat_id": "B1", "name": "hook", "duration_seconds": 4, "emotional_target": "curiosity",
             "intensity": 0.8, "script_constraint": "Open with core pain — no brand intro",
             "visual_constraint": "Clock imagery conveying time pressure"},
            {"beat_id": "B2", "name": "problem", "duration_seconds": 7, "emotional_target": "recognition",
             "intensity": 0.6, "script_constraint": "Name the problem specifically",
             "visual_constraint": "Overwhelmed workspace or notification avalanche"},
            {"beat_id": "B3", "name": "solution_intro", "duration_seconds": 8, "emotional_target": "hope",
             "intensity": 0.9, "script_constraint": "Introduce Acme — confident, specific",
             "visual_constraint": "Clean Acme app UI reveal"},
            {"beat_id": "B4", "name": "resolution", "duration_seconds": 6, "emotional_target": "aspiration",
             "intensity": 0.7, "script_constraint": "Paint the after state calmly",
             "visual_constraint": "Peaceful productive workspace"},
            {"beat_id": "B5", "name": "cta", "duration_seconds": 5, "emotional_target": "action",
             "intensity": 0.5, "script_constraint": "Deliver 'Try free at acme.com' verbatim",
             "visual_constraint": "Acme logo + CTA text on screen"},
        ],
        "intensity_curve": [
            {"t_seconds": 0.0, "value": 0.8},
            {"t_seconds": 4.0, "value": 0.6},
            {"t_seconds": 11.0, "value": 0.9},
            {"t_seconds": 19.0, "value": 0.7},
            {"t_seconds": 25.0, "value": 0.5},
            {"t_seconds": 30.0, "value": 0.5},
        ],
    },
    "intelligence": {
        "trend_alignment": {
            "selected_trend_ids": ["trend-tiktok-lofi-hook"],
            "alignments": [
                {
                    "trend_id": "trend-tiktok-lofi-hook",
                    "signal": "lo-fi aesthetic +34% on TikTok",
                    "source": "Sprout Social 2026",
                    "sentiment": "positive",
                    "brand_safety": "safe",
                    "trend_type": "visual_style",
                    "application_targets": ["hook", "build", "scene_plan", "visual"],
                    "target_beat": "hook",
                    "script_usage": {
                        "required_section_ids": ["hook", "build"],
                        "source_ref": "trend_alignment:trend-tiktok-lofi-hook",
                        "usage_note": "Thread the calm native hook pattern through the hook and build without making a topical reference.",
                    },
                    "scene_usage": {
                        "required": True,
                        "required_scene_count": 1,
                        "visual_or_pacing_instruction": "Use warm lo-fi visual pacing and native overlay text while avoiding source imitation.",
                    },
                    "do_not_imitate": [
                        "Do not copy source captions, audio, creator identity, choreography, or exact shot sequence.",
                    ],
                }
            ],
        },
        "knowledge_alignment": {
            "selected_card_ids": ["hook.visual-contrast.001"],
            "alignments": [
                {
                    "card_id": "hook.visual-contrast.001",
                    "domain": "hook_mechanic",
                    "summary": "Use visible contrast in the opening second to create a fast comprehension gap.",
                    "source_ref": "knowledge_alignment:hook.visual-contrast.001",
                    "application_targets": ["hook", "script", "scene_plan", "visual"],
                    "target_beat": "hook",
                    "script_usage": {
                        "required_section_ids": ["hook"],
                        "source_ref": "knowledge_alignment:hook.visual-contrast.001",
                        "usage_note": "Hook copy must create a visible before/after gap without explaining the whole product.",
                    },
                    "scene_usage": {
                        "required": True,
                        "required_scene_count": 1,
                        "visual_or_pacing_instruction": "Open on a visual contradiction or before/after contrast that resolves into the product promise.",
                    },
                    "do_not_overapply": [
                        "Do not turn the hook into clickbait unrelated to the product promise.",
                    ],
                }
            ],
        },
        "trending_signals": [
            {"signal": "lo-fi aesthetic +34% on TikTok", "source": "Sprout Social 2026", "applied_to": "visual.color_direction"},
        ],
        "reference_ads_analyzed": [
            {"title": "Monday.com Work OS", "platform": "youtube", "what_works": "Pain-first hook", "adopted": True, "adaptation": "Compress to 30s"},
        ],
        "rejected_approaches": [
            {"approach": "celebrity endorsement", "reason": "Oversaturated"},
            {"approach": "generic tagline", "reason": "No differentiation"},
        ],
    },
    "truth_contract": {
        "objective_facts": [
            {
                "rule_id": "TC-FACT-1",
                "requirement": "Advertised product is Acme Productivity App.",
                "prohibited_failure": "Rename the product or imply a different app.",
                "evidence_source": "enriched_brief.product_brief.product_name",
                "source_confidence": "source-backed",
            }
        ],
        "physical_constraints": [
            {
                "rule_id": "TC-PHYS-1",
                "requirement": "People, phones, laptops, and desks remain physically plausible.",
                "prohibited_failure": "Warped hands, impossible device geometry, or floating props without context.",
                "evidence_source": "director physical plausibility review",
                "source_confidence": "director-verified",
            }
        ],
        "product_geometry_rules": [
            {
                "rule_id": "TC-GEO-1",
                "requirement": "Preserve Acme app UI identity, Acme logo, and CTA domain.",
                "prohibited_failure": "Invented app name, unrelated UI, missing Acme logo, or wrong domain.",
                "evidence_source": "brand_constraints.mandatory_elements",
                "source_confidence": "source-backed",
            }
        ],
        "motion_coherence_rules": [
            {
                "rule_id": "TC-MOTION-1",
                "requirement": "Notification, UI, and workspace motion remains continuous across keyframes.",
                "prohibited_failure": "Teleporting UI panels, discontinuous hand pose, or impossible perspective jump.",
                "evidence_source": "production_bible.visual.key_visual_moments",
                "source_confidence": "director-verified",
            }
        ],
        "values_guardrails": [
            {
                "rule_id": "TC-VALUES-1",
                "requirement": "No unsupported productivity, medical, safety, or competitor claims.",
                "prohibited_failure": "Unapproved quantified claim or competitor disparagement.",
                "evidence_source": "brand_constraints.prohibited_elements",
                "source_confidence": "source-backed",
            }
        ],
    },
    "visual": {
        "style_mode": "animated",
        "render_runtime": "remotion",
        "color_direction": "muted warm lo-fi palette",
        "visual_motifs": [
            {"motif": "clock imagery", "mandatory": True, "minimum_scene_count": 2},
            {"motif": "notification avalanche", "mandatory": True, "minimum_scene_count": 1},
        ],
        "key_visual_moments": [
            {
                "moment_id": "KV1",
                "description": "Acme app interface reveal",
                "maps_to_beat": "B3",
                "mandatory": True,
                "required_motion_primitives": ["text_entrance_fade"],
            },
            {
                "moment_id": "KV2",
                "description": "Acme logo + CTA text",
                "maps_to_beat": "B5",
                "mandatory": True,
                "required_motion_primitives": ["text_entrance_fade"],
            },
        ],
        "editing_rhythm": [
            {"maps_to_beat": "B1", "cuts_density": "rapid", "avg_shot_duration_seconds": 1.5,
             "transition_style": "hard_cut", "confidence": "pattern-inferred"},
            {"maps_to_beat": "B2", "cuts_density": "moderate", "avg_shot_duration_seconds": 3.0,
             "transition_style": "hard_cut", "confidence": "default-heuristic"},
            {"maps_to_beat": "B3", "cuts_density": "slow", "avg_shot_duration_seconds": 4.5,
             "transition_style": "match_cut", "confidence": "pattern-inferred"},
            {"maps_to_beat": "B5", "cuts_density": "held", "avg_shot_duration_seconds": 5.0,
             "transition_style": "hard_cut", "confidence": "research-grounded"},
        ],
    },
    "audio": {
        "voice_character": {"tone": "warm and direct", "pacing": "energetic", "persona": "trusted peer"},
        "music_direction": {"mood": "focused optimism", "tempo": "medium",
                            "genre_direction": "lo-fi indie", "arc": "sparse at hook, full at B3"},
        "av_sync_notes": "Music swell on B3 solution reveal",
    },
    "brand_constraints": {
        "brand_name_in_final_frame": True,
        "mandatory_elements": ["Acme logo", "acme.com"],
        "prohibited_elements": ["competitor", "monday.com", "notion"],
        "tone_guardrails": ["never condescending", "no corporate jargon"],
    },
    "deliverables": {
        "primary": {"aspect_ratio": "9:16", "duration_seconds": 30},
        "derivatives": [],
    },
    "compliance_manifest": {
        "checkpoints": [
            {"id": "CP-S1", "applies_to_stage": "script", "description": "B1 hook timing",
             "check_type": "timing", "evaluation_method": "structural",
             "criterion": "Section covering beat B1 (hook) must be within ±10% of 4s",
             "source_confidence": "research-grounded", "failure_action": "revise"},
            {"id": "CP-S1a", "applies_to_stage": "script", "description": "B1 achieves curiosity",
             "check_type": "content", "evaluation_method": "semantic",
             "criterion": "Section must achieve emotional_target='curiosity'",
             "source_confidence": "research-grounded", "failure_action": "revise"},
            {"id": "CP-V1", "applies_to_stage": "scene_plan", "description": "Clock imagery ≥2 scenes",
             "check_type": "presence", "evaluation_method": "structural",
             "criterion": "'clock imagery' must appear in ≥2 scenes",
             "source_confidence": "research-grounded", "failure_action": "revise"},
            {"id": "CP-V3", "applies_to_stage": "scene_plan", "description": "App reveal mapped to B3",
             "check_type": "structural", "evaluation_method": "structural",
             "criterion": "A scene for 'Acme app interface reveal' must be present, mapped to beat B3",
             "source_confidence": "research-grounded", "failure_action": "revise"},
            {"id": "CP-E1", "applies_to_stage": "edit", "description": "B1 pacing",
             "check_type": "timing", "evaluation_method": "structural",
             "criterion": "Scenes in beat B1: cuts_density=rapid, avg_shot≈1.5s",
             "source_confidence": "pattern-inferred", "failure_action": "revise"},
            {"id": "CP-E2", "applies_to_stage": "edit", "description": "B2 pacing (heuristic)",
             "check_type": "timing", "evaluation_method": "structural",
             "criterion": "Scenes in beat B2: cuts_density=moderate, avg_shot≈3.0s",
             "source_confidence": "default-heuristic", "failure_action": "flag"},
            {"id": "CP-B1", "applies_to_stage": "scene_plan", "description": "Brand in final scene",
             "check_type": "presence", "evaluation_method": "structural",
             "criterion": "brand_name 'Acme' must appear in final scene",
             "source_confidence": "research-grounded", "failure_action": "revise"},
            {"id": "CP-B3", "applies_to_stage": "script", "description": "Prohibited terms absent",
             "check_type": "presence", "evaluation_method": "structural",
             "criterion": "prohibited_elements ['competitor', 'monday.com'] must not appear in any script section",
             "source_confidence": "research-grounded", "failure_action": "revise"},
        ],
    },
}


# ─────────────────────────────────────────────────────────────────────────────
# intake_brief schema tests
# ─────────────────────────────────────────────────────────────────────────────

def test_intake_brief_rich_validates():
    validate(INTAKE_BRIEF_RICH, load_schema("intake_brief"))


def test_intake_brief_thin_validates():
    validate(INTAKE_BRIEF_THIN, load_schema("intake_brief"))


def test_intake_brief_completeness_values():
    assert INTAKE_BRIEF_RICH["intake_completeness"] == "rich"
    assert INTAKE_BRIEF_THIN["intake_completeness"] == "thin"
    assert len(INTAKE_BRIEF_RICH["round1_questions_asked"]) == 0
    assert len(INTAKE_BRIEF_THIN["round1_questions_asked"]) == 2


def test_intake_brief_rejects_more_than_3_questions():
    bad = deep_copy(INTAKE_BRIEF_RICH)
    bad["round1_questions_asked"] = ["Q1", "Q2", "Q3", "Q4"]
    try:
        validate(bad, load_schema("intake_brief"))
        assert False, "Should raise ValidationError for 4 questions (maxItems: 3)"
    except Exception as e:
        assert "maxItems" in str(e) or "4" in str(e), f"Unexpected error: {e}"


def test_intake_brief_rejects_invalid_platform():
    bad = deep_copy(INTAKE_BRIEF_RICH)
    bad["platform"] = "snapchat"
    try:
        validate(bad, load_schema("intake_brief"))
        assert False, "Invalid platform should fail"
    except Exception:
        pass


def test_intake_brief_rejects_invalid_completeness():
    bad = deep_copy(INTAKE_BRIEF_RICH)
    bad["intake_completeness"] = "complete"  # not in enum
    try:
        validate(bad, load_schema("intake_brief"))
        assert False, "Invalid completeness value should fail"
    except Exception:
        pass


def test_intake_brief_requires_product_and_platform():
    bad = {"intake_completeness": "thin", "round1_questions_asked": [], "duration_target_seconds": 30}
    try:
        validate(bad, load_schema("intake_brief"))
        assert False, "Missing product and platform should fail"
    except Exception:
        pass


# ─────────────────────────────────────────────────────────────────────────────
# intelligence_brief schema tests
# ─────────────────────────────────────────────────────────────────────────────

def test_intelligence_brief_validates():
    validate(INTELLIGENCE_BRIEF_VALID, load_schema("intelligence_brief"))


def test_intelligence_brief_rejects_empty_rejected_approaches():
    bad = deep_copy(INTELLIGENCE_BRIEF_VALID)
    bad["rejected_approaches"] = []
    try:
        validate(bad, load_schema("intelligence_brief"))
        assert False, "Empty rejected_approaches should fail (minItems: 1)"
    except Exception:
        pass


def test_intelligence_brief_rejects_invalid_confidence_tier():
    bad = deep_copy(INTELLIGENCE_BRIEF_VALID)
    bad["recommendations"]["arc_type"]["confidence"] = "guessed"
    try:
        validate(bad, load_schema("intelligence_brief"))
        assert False, "Invalid confidence tier should fail"
    except Exception:
        pass


def test_intelligence_brief_accepts_typed_trend_record_fields():
    """observed_at / decay_window_days / is_evergreen / engagement_proxy are
    additive fields consumed by lib.trend_recency. Briefs that include them
    must validate; briefs without them (legacy) must also still validate."""
    brief = deep_copy(INTELLIGENCE_BRIEF_VALID)
    brief["platform_trends"][0].update({
        "observed_at": "2026-04-15",
        "retrieved_at": "2026-04-26",
        "decay_window_days": 90,
        "is_evergreen": False,
        "engagement_proxy": {"views": 1_200_000, "likes": 45_000, "shares": 3_200},
    })
    validate(brief, load_schema("intelligence_brief"))


def test_intelligence_brief_accepts_trend_alignment_metadata_fields():
    """Trend records can carry typed sentiment, safety, and usage targets.

    The fields are optional for legacy briefs, but new ad-video intelligence
    runs use them so bible-director can select only brand-safe positive/neutral
    trend signals for production_bible.intelligence.trend_alignment.
    """
    brief = deep_copy(INTELLIGENCE_BRIEF_VALID)
    brief["platform_trends"][0].update({
        "trend_id": "trend-tiktok-text-hooks",
        "sentiment": "positive",
        "trend_type": "visual_style",
        "brand_safety": "safe",
        "application_targets": ["hook", "scene_plan", "visual"],
    })
    validate(brief, load_schema("intelligence_brief"))


def test_intelligence_brief_rejects_invalid_trend_sentiment():
    bad = deep_copy(INTELLIGENCE_BRIEF_VALID)
    bad["platform_trends"][0]["sentiment"] = "controversial"
    with pytest.raises(Exception):
        validate(bad, load_schema("intelligence_brief"))


def test_intelligence_brief_rejects_bad_observed_at_type():
    """observed_at must be a string (ISO 8601 date), not a number."""
    bad = deep_copy(INTELLIGENCE_BRIEF_VALID)
    bad["platform_trends"][0]["observed_at"] = 20260415
    try:
        validate(bad, load_schema("intelligence_brief"))
        assert False, "non-string observed_at should fail (type: string)"
    except Exception:
        pass


def test_intelligence_brief_rejects_negative_decay_window():
    bad = deep_copy(INTELLIGENCE_BRIEF_VALID)
    bad["platform_trends"][0]["decay_window_days"] = 0
    try:
        validate(bad, load_schema("intelligence_brief"))
        assert False, "decay_window_days=0 should fail (minimum: 1)"
    except Exception:
        pass


def test_intelligence_brief_accepts_hit_ad_with_pacing_measured():
    """Hit ads with public URLs can carry video_analyzer measured pacing —
    additive fields consumed by lib.hit_ad_pacing.aggregate_pacing_from_hit_ads."""
    brief = deep_copy(INTELLIGENCE_BRIEF_VALID)
    brief["hit_ads_analyzed"][0].update({
        "url": "https://youtube.com/shorts/abc123",
        "analyzed_at": "2026-04-26",
        "pacing_measured": {
            "cuts_per_minute": 32.5,
            "avg_scene_duration_seconds": 1.85,
            "total_scenes": 16,
            "source": "video_analyzer",
        },
    })
    validate(brief, load_schema("intelligence_brief"))


def test_intelligence_brief_rejects_pacing_measured_with_unknown_source():
    """source field is a const enum locked to 'video_analyzer'."""
    bad = deep_copy(INTELLIGENCE_BRIEF_VALID)
    bad["hit_ads_analyzed"][0]["pacing_measured"] = {
        "cuts_per_minute": 30.0,
        "avg_scene_duration_seconds": 2.0,
        "total_scenes": 12,
        "source": "made_up_analyzer",
    }
    try:
        validate(bad, load_schema("intelligence_brief"))
        assert False, "unknown pacing_measured.source should fail (const violation)"
    except Exception:
        pass


def test_intelligence_brief_rejects_pacing_measured_missing_required_field():
    bad = deep_copy(INTELLIGENCE_BRIEF_VALID)
    bad["hit_ads_analyzed"][0]["pacing_measured"] = {
        "cuts_per_minute": 30.0,
        "source": "video_analyzer",
    }
    try:
        validate(bad, load_schema("intelligence_brief"))
        assert False, "pacing_measured missing required fields should fail"
    except Exception:
        pass


def test_intelligence_brief_accepts_hit_ad_with_classification():
    """Project B Commit 2: hit ads can carry a narrative-pattern classification
    block produced by lib.hit_ad_classification.classify_hit_ad_from_video_brief."""
    brief = deep_copy(INTELLIGENCE_BRIEF_VALID)
    brief["hit_ads_analyzed"][0]["classification"] = {
        "arc_type": "problem-solution",
        "hook_mechanic": "stat",
        "what_works": "Opens with stat hook (problem-solution arc). Pacing: ~32 cuts/min.",
        "source": "video_analyzer_classification",
        "signals": {
            "energy_profile": [0, 0, 1, 2, 2],
            "visual_type_distribution": {"text_card": 1, "screen_recording": 3, "product_shot": 1},
            "scene_count": 5,
        },
    }
    validate(brief, load_schema("intelligence_brief"))


def test_intelligence_brief_rejects_classification_with_unknown_arc_type():
    """The classification's arc_type must match production_bible.narrative.arc_type
    enum exactly so the rule classifier can't drift outside the schema."""
    bad = deep_copy(INTELLIGENCE_BRIEF_VALID)
    bad["hit_ads_analyzed"][0]["classification"] = {
        "arc_type": "made_up_arc",
        "hook_mechanic": "stat",
        "source": "video_analyzer_classification",
    }
    try:
        validate(bad, load_schema("intelligence_brief"))
        assert False, "unknown classification.arc_type should fail (enum violation)"
    except Exception:
        pass


def test_intelligence_brief_rejects_classification_with_wrong_source():
    """source is const-locked to 'video_analyzer_classification'."""
    bad = deep_copy(INTELLIGENCE_BRIEF_VALID)
    bad["hit_ads_analyzed"][0]["classification"] = {
        "arc_type": "problem-solution",
        "hook_mechanic": "stat",
        "source": "made_up_source",
    }
    try:
        validate(bad, load_schema("intelligence_brief"))
        assert False, "wrong classification.source should fail (const violation)"
    except Exception:
        pass


def test_intelligence_brief_confidence_tiers_are_valid():
    valid_tiers = {"research-grounded", "pattern-inferred", "default-heuristic"}
    recs = INTELLIGENCE_BRIEF_VALID["recommendations"]
    for key in ("arc_type", "pacing_model", "hook_mechanic", "hook_window_seconds"):
        tier = recs[key]["confidence"]
        assert tier in valid_tiers, f"{key} has invalid confidence tier: {tier!r}"
    for beat_name, beat_val in recs.get("editing_rhythm_by_beat", {}).items():
        tier = beat_val["confidence"]
        assert tier in valid_tiers, f"editing_rhythm.{beat_name} invalid tier: {tier!r}"


def test_intelligence_brief_has_minimum_required_counts():
    assert len(INTELLIGENCE_BRIEF_VALID["platform_trends"]) >= 3, "Need ≥3 trends"
    assert len(INTELLIGENCE_BRIEF_VALID["hit_ads_analyzed"]) >= 3, "Need ≥3 hit ads"
    assert len(INTELLIGENCE_BRIEF_VALID["rejected_approaches"]) >= 1, "Need ≥1 rejected"


def test_intelligence_brief_requires_platform_trends_minItems():
    bad = deep_copy(INTELLIGENCE_BRIEF_VALID)
    bad["platform_trends"] = []
    try:
        validate(bad, load_schema("intelligence_brief"))
        assert False, "Empty platform_trends should fail (minItems: 1)"
    except Exception:
        pass


# ─────────────────────────────────────────────────────────────────────────────
# production_bible schema tests
# ─────────────────────────────────────────────────────────────────────────────

def test_production_bible_validates():
    validate(PRODUCTION_BIBLE_VALID, load_schema("production_bible"))


def test_production_bible_null_cta_passes_schema():
    """Schema allows null CTA — EP gate G-I enforces non-null at runtime (not schema)."""
    bible = deep_copy(PRODUCTION_BIBLE_VALID)
    bible["identity"]["cta"] = None
    validate(bible, load_schema("production_bible"))  # must pass


def test_production_bible_pipeline_must_be_ad_video():
    bad = deep_copy(PRODUCTION_BIBLE_VALID)
    bad["pipeline"] = "animated-explainer"
    try:
        validate(bad, load_schema("production_bible"))
        assert False, "Wrong pipeline should fail (const: 'ad-video')"
    except Exception:
        pass


def test_production_bible_brand_name_in_final_frame_must_be_true():
    bad = deep_copy(PRODUCTION_BIBLE_VALID)
    bad["brand_constraints"]["brand_name_in_final_frame"] = False
    try:
        validate(bad, load_schema("production_bible"))
        assert False, "brand_name_in_final_frame=False should fail (const: true)"
    except Exception:
        pass


def test_production_bible_beat_name_accepts_arc_specific_names():
    """Beat names use minLength:1, not an enum — arc-specific names like 'problem', 'proof' are valid."""
    bible = deep_copy(PRODUCTION_BIBLE_VALID)
    bible["narrative"]["emotional_beat_sequence"] = [
        {"beat_id": "B1", "name": "hook", "duration_seconds": 4, "emotional_target": "curiosity",
         "intensity": 0.8, "script_constraint": "x", "visual_constraint": "x"},
        {"beat_id": "B2", "name": "problem", "duration_seconds": 8, "emotional_target": "recognition",
         "intensity": 0.6, "script_constraint": "x", "visual_constraint": "x"},
        {"beat_id": "B3", "name": "solution_intro", "duration_seconds": 10, "emotional_target": "hope",
         "intensity": 0.9, "script_constraint": "x", "visual_constraint": "x"},
        {"beat_id": "B4", "name": "proof", "duration_seconds": 8, "emotional_target": "trust",
         "intensity": 0.9, "script_constraint": "x", "visual_constraint": "x"},
    ]
    validate(bible, load_schema("production_bible"))


def test_production_bible_rejects_invalid_evaluation_method():
    bad = deep_copy(PRODUCTION_BIBLE_VALID)
    bad["compliance_manifest"]["checkpoints"][0]["evaluation_method"] = "heuristic"
    try:
        validate(bad, load_schema("production_bible"))
        assert False, "Invalid evaluation_method should fail"
    except Exception:
        pass


def test_production_bible_rejects_invalid_failure_action():
    bad = deep_copy(PRODUCTION_BIBLE_VALID)
    bad["compliance_manifest"]["checkpoints"][0]["failure_action"] = "block"
    try:
        validate(bad, load_schema("production_bible"))
        assert False, "Invalid failure_action should fail (enum: revise|flag)"
    except Exception:
        pass


def test_production_bible_requires_approval_flags():
    bad = deep_copy(PRODUCTION_BIBLE_VALID)
    del bad["approval"]["strategic_approved"]
    try:
        validate(bad, load_schema("production_bible"))
        assert False, "Missing strategic_approved should fail"
    except Exception:
        pass


def test_production_bible_accepts_intensity_curve():
    """narrative.intensity_curve is the new optional field consumed by Path B Step 2+.
    Bibles that include it must validate; absent field still validates (legacy path)."""
    bible = deep_copy(PRODUCTION_BIBLE_VALID)
    bible["narrative"]["intensity_curve"] = [
        {"t_seconds": 0.0, "value": 0.3},
        {"t_seconds": 5.0, "value": 0.8},
        {"t_seconds": 15.0, "value": 0.5},
        {"t_seconds": 20.0, "value": 0.5},
    ]
    validate(bible, load_schema("production_bible"))


def test_production_bible_rejects_intensity_curve_value_above_one():
    bad = deep_copy(PRODUCTION_BIBLE_VALID)
    bad["narrative"]["intensity_curve"] = [{"t_seconds": 0.0, "value": 1.5}]
    try:
        validate(bad, load_schema("production_bible"))
        assert False, "value > 1.0 should fail (intensity is bounded 0..1)"
    except Exception:
        pass


def test_production_bible_rejects_intensity_curve_negative_time():
    bad = deep_copy(PRODUCTION_BIBLE_VALID)
    bad["narrative"]["intensity_curve"] = [{"t_seconds": -0.5, "value": 0.5}]
    try:
        validate(bad, load_schema("production_bible"))
        assert False, "negative t_seconds should fail (minimum: 0)"
    except Exception:
        pass


def test_production_bible_accepts_structured_timing_criterion():
    """v2 structured criteria are an additive optional field on checkpoints."""
    bible = deep_copy(PRODUCTION_BIBLE_VALID)
    bible["compliance_manifest"]["checkpoints"][0]["structured"] = {
        "kind": "timing",
        "beat_id": "B1",
        "target_seconds": 5.0,
        "tolerance": 0.10,
    }
    validate(bible, load_schema("production_bible"))


def test_production_bible_accepts_structured_presence_and_beat_mapping():
    bible = deep_copy(PRODUCTION_BIBLE_VALID)
    cps = bible["compliance_manifest"]["checkpoints"]
    cps[0]["structured"] = {"kind": "presence", "terms": ["Flowcut"], "min_count": 1}
    if len(cps) > 1:
        cps[1]["structured"] = {"kind": "beat_mapping", "beat_id": "cta_brand"}
    validate(bible, load_schema("production_bible"))


def test_production_bible_rejects_structured_unknown_kind():
    bad = deep_copy(PRODUCTION_BIBLE_VALID)
    bad["compliance_manifest"]["checkpoints"][0]["structured"] = {
        "kind": "made_up_kind", "beat_id": "B1",
    }
    try:
        validate(bad, load_schema("production_bible"))
        assert False, "unknown structured.kind should fail (oneOf rejection)"
    except Exception:
        pass


def test_production_bible_accepts_provenance_demotions():
    """intelligence.provenance_demotions is an additive audit-trail field
    populated by bible-director Step 0 (provenance audit)."""
    bible = deep_copy(PRODUCTION_BIBLE_VALID)
    bible["intelligence"]["provenance_demotions"] = [
        {
            "path": "recommendations.arc_type",
            "path_type": "recommendation",
            "key": "arc_type",
            "current_confidence": "research-grounded",
            "suggested_confidence": "pattern-inferred",
            "reason": "rationale lacks citable evidence",
        },
        {
            "path": "dimension_verdicts[1]",
            "path_type": "dimension_verdict",
            "index": 1,
            "current_confidence": "research-grounded",
            "suggested_confidence": "pattern-inferred",
            "reason": "CONTRADICTED verdict lacks citable challenge_evidence",
        },
    ]
    validate(bible, load_schema("production_bible"))


def test_production_bible_rejects_provenance_demotion_with_unknown_path_type():
    bad = deep_copy(PRODUCTION_BIBLE_VALID)
    bad["intelligence"]["provenance_demotions"] = [
        {
            "path": "x", "path_type": "made_up_type",
            "current_confidence": "x", "suggested_confidence": "y",
            "reason": "z",
        },
    ]
    try:
        validate(bad, load_schema("production_bible"))
        assert False, "unknown path_type should fail (enum rejection)"
    except Exception:
        pass


def test_production_bible_accepts_rhythm_warnings():
    """intelligence.rhythm_warnings is the audit trail from bible-director Step 3
    consistency check. Both axes (cuts_density and avg_shot_duration) can fire
    on the same beat, so multiple entries per beat_id are valid."""
    bible = deep_copy(PRODUCTION_BIBLE_VALID)
    bible["intelligence"]["rhythm_warnings"] = [
        {
            "beat_id": "B1",
            "warning": "intensity 0.90 suggests rank 3 cuts but cuts_density='held' (rank 0); 2+ tiers apart",
            "rhythm": {
                "cuts_density": "held",
                "avg_shot_duration_seconds": 6.0,
                "transition_style": "dissolve",
                "confidence": "pattern-inferred",
            },
        },
        {
            "beat_id": "B1",
            "warning": "intensity 0.90 (peak) but avg_shot_duration_seconds=6.0 (long shots disagree)",
            "rhythm": {
                "cuts_density": "held",
                "avg_shot_duration_seconds": 6.0,
                "transition_style": "dissolve",
                "confidence": "pattern-inferred",
            },
        },
    ]
    validate(bible, load_schema("production_bible"))


def test_production_bible_rejects_rhythm_warning_missing_beat_id():
    bad = deep_copy(PRODUCTION_BIBLE_VALID)
    bad["intelligence"]["rhythm_warnings"] = [
        {"warning": "x", "rhythm": {}},  # missing beat_id
    ]
    try:
        validate(bad, load_schema("production_bible"))
        assert False, "rhythm_warnings entry missing beat_id should fail"
    except Exception:
        pass


def test_production_bible_rejects_rhythm_warning_with_extra_property():
    """additionalProperties: false on each rhythm_warnings item catches typos
    like 'rhytm' or 'severity' from drifting in silently."""
    bad = deep_copy(PRODUCTION_BIBLE_VALID)
    bad["intelligence"]["rhythm_warnings"] = [
        {"beat_id": "B1", "warning": "x", "rhythm": {}, "severity": "high"},
    ]
    try:
        validate(bad, load_schema("production_bible"))
        assert False, "extra property on rhythm_warnings entry should fail"
    except Exception:
        pass


def test_production_bible_rejects_unknown_key_under_intelligence():
    """The intelligence block is now locked with additionalProperties:false.
    A typo'd key (e.g., 'rhythm_warning' singular instead of 'rhythm_warnings')
    must fail validation rather than silently being accepted as a no-op.

    This regression closes the fragility class flagged by the editing-rhythm
    review: previously `provenance_demotions` and `rhythm_warnings` were
    'permitted only because the intelligence block doesn't have
    additionalProperties: false' — a future schema-tightening pass would
    have broken them silently. Lock it now and surface drift loudly."""
    bad = deep_copy(PRODUCTION_BIBLE_VALID)
    bad["intelligence"]["rhythm_warning"] = []   # singular typo
    try:
        validate(bad, load_schema("production_bible"))
        assert False, "typo'd 'rhythm_warning' (singular) should fail under the lock"
    except Exception:
        pass

    bad2 = deep_copy(PRODUCTION_BIBLE_VALID)
    bad2["intelligence"]["misc_notes"] = "anything"  # made-up field
    try:
        validate(bad2, load_schema("production_bible"))
        assert False, "unknown intelligence key 'misc_notes' should fail under the lock"
    except Exception:
        pass


def test_production_bible_accepts_intelligence_with_only_declared_keys():
    """Sanity: every declared intelligence key continues to validate after
    the lock — trending_signals, reference_ads_analyzed, rejected_approaches,
    provenance_demotions, rhythm_warnings, classification_aggregate."""
    bible = deep_copy(PRODUCTION_BIBLE_VALID)
    bible["intelligence"] = {
        "trend_alignment": {"selected_trend_ids": [], "alignments": []},
        "knowledge_alignment": {"selected_card_ids": [], "alignments": []},
        "trending_signals": [],
        "reference_ads_analyzed": [],
        "rejected_approaches": [{"approach": "x", "reason": "y"}],
        "provenance_demotions": [],
        "rhythm_warnings": [],
        "classification_aggregate": {
            "arc_type": "problem-solution",
            "arc_type_agreement": 1.0,
            "hook_mechanic": "stat",
            "hook_mechanic_agreement": 1.0,
            "sample_size": 2,
            "confidence": "research-grounded",
            "dissent": [],
        },
    }
    validate(bible, load_schema("production_bible"))


def test_production_bible_accepts_classification_aggregate_with_dissent():
    """Project B Commit 2: aggregate carries a dissent list of full
    classifications when ads disagreed on arc_type or hook_mechanic."""
    bible = deep_copy(PRODUCTION_BIBLE_VALID)
    bible["intelligence"]["classification_aggregate"] = {
        "arc_type": "problem-solution",
        "arc_type_agreement": 0.75,
        "hook_mechanic": "stat",
        "hook_mechanic_agreement": 0.75,
        "sample_size": 4,
        "confidence": "research-grounded",
        "dissent": [
            {"arc_type": "demo-reveal", "hook_mechanic": "question"},
        ],
    }
    validate(bible, load_schema("production_bible"))


def test_production_bible_rejects_classification_aggregate_with_unknown_confidence():
    bad = deep_copy(PRODUCTION_BIBLE_VALID)
    bad["intelligence"]["classification_aggregate"] = {
        "arc_type": "problem-solution",
        "hook_mechanic": "stat",
        "sample_size": 2,
        "confidence": "guessed",
    }
    try:
        validate(bad, load_schema("production_bible"))
        assert False, "unknown classification_aggregate.confidence should fail"
    except Exception:
        pass


# ─────────────────────────────────────────────────────────────────────────────
# Internal consistency: compliance_manifest ↔ beat_sequence
# ─────────────────────────────────────────────────────────────────────────────

def test_all_beat_ids_referenced_in_checkpoints_exist():
    """Every beat_id in compliance_manifest criteria must exist in emotional_beat_sequence."""
    import re
    beat_ids = {b["beat_id"] for b in PRODUCTION_BIBLE_VALID["narrative"]["emotional_beat_sequence"]}
    errors = []
    for cp in PRODUCTION_BIBLE_VALID["compliance_manifest"]["checkpoints"]:
        for beat_id in re.findall(r"\bbeat (\w+)", cp["criterion"]):
            if beat_id not in beat_ids:
                errors.append(f"CP {cp['id']} references unknown beat_id '{beat_id}' (valid: {beat_ids})")
    assert not errors, "\n".join(errors)


def test_key_visual_moments_reference_valid_beats():
    """maps_to_beat in key_visual_moments must reference existing beat_ids."""
    beat_ids = {b["beat_id"] for b in PRODUCTION_BIBLE_VALID["narrative"]["emotional_beat_sequence"]}
    for kvm in PRODUCTION_BIBLE_VALID["visual"]["key_visual_moments"]:
        assert kvm["maps_to_beat"] in beat_ids, (
            f"Key visual moment '{kvm['moment_id']}' references unknown beat '{kvm['maps_to_beat']}'"
        )


def test_editing_rhythm_references_valid_beats():
    """maps_to_beat in editing_rhythm must reference existing beat_ids."""
    beat_ids = {b["beat_id"] for b in PRODUCTION_BIBLE_VALID["narrative"]["emotional_beat_sequence"]}
    for rhythm in PRODUCTION_BIBLE_VALID["visual"]["editing_rhythm"]:
        assert rhythm["maps_to_beat"] in beat_ids, (
            f"Editing rhythm references unknown beat '{rhythm['maps_to_beat']}'"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Compliance manifest generation rules
# ─────────────────────────────────────────────────────────────────────────────

def test_structural_check_types_have_structural_evaluation_method():
    """timing, presence, structural check_types → evaluation_method=structural."""
    structural_check_types = {"timing", "presence", "structural"}
    for cp in PRODUCTION_BIBLE_VALID["compliance_manifest"]["checkpoints"]:
        if cp["check_type"] in structural_check_types:
            assert cp["evaluation_method"] == "structural", (
                f"CP {cp['id']}: check_type={cp['check_type']!r} must have "
                f"evaluation_method='structural', got {cp['evaluation_method']!r}"
            )


def test_content_check_type_has_semantic_evaluation_method():
    """content check_type → evaluation_method=semantic."""
    for cp in PRODUCTION_BIBLE_VALID["compliance_manifest"]["checkpoints"]:
        if cp["check_type"] == "content":
            assert cp["evaluation_method"] == "semantic", (
                f"CP {cp['id']}: check_type='content' must have evaluation_method='semantic'"
            )


def test_default_heuristic_maps_to_flag():
    """default-heuristic source_confidence → failure_action=flag."""
    for cp in PRODUCTION_BIBLE_VALID["compliance_manifest"]["checkpoints"]:
        if cp["source_confidence"] == "default-heuristic":
            assert cp["failure_action"] == "flag", (
                f"CP {cp['id']}: default-heuristic must map to failure_action='flag', "
                f"got {cp['failure_action']!r}"
            )


def test_research_grounded_maps_to_revise():
    """research-grounded source_confidence → failure_action=revise."""
    for cp in PRODUCTION_BIBLE_VALID["compliance_manifest"]["checkpoints"]:
        if cp["source_confidence"] == "research-grounded":
            assert cp["failure_action"] == "revise", (
                f"CP {cp['id']}: research-grounded must map to failure_action='revise'"
            )


def test_pattern_inferred_maps_to_revise():
    """pattern-inferred source_confidence → failure_action=revise."""
    for cp in PRODUCTION_BIBLE_VALID["compliance_manifest"]["checkpoints"]:
        if cp["source_confidence"] == "pattern-inferred":
            assert cp["failure_action"] == "revise", (
                f"CP {cp['id']}: pattern-inferred must map to failure_action='revise'"
            )


def test_compliance_manifest_covers_all_downstream_stages():
    """Must have at least one checkpoint for script, scene_plan, and edit."""
    stages_covered = {cp["applies_to_stage"] for cp in PRODUCTION_BIBLE_VALID["compliance_manifest"]["checkpoints"]}
    for required_stage in ("script", "scene_plan", "edit"):
        assert required_stage in stages_covered, f"No checkpoint for stage '{required_stage}'"


def test_compliance_manifest_has_both_structural_and_semantic():
    eval_methods = {cp["evaluation_method"] for cp in PRODUCTION_BIBLE_VALID["compliance_manifest"]["checkpoints"]}
    assert "structural" in eval_methods, "Must have at least one structural checkpoint"
    assert "semantic" in eval_methods, "Must have at least one semantic checkpoint"


def test_all_checkpoints_have_required_fields():
    """Every checkpoint must have all 8 required fields."""
    required = {"id", "applies_to_stage", "description", "check_type",
                "evaluation_method", "criterion", "source_confidence", "failure_action"}
    for cp in PRODUCTION_BIBLE_VALID["compliance_manifest"]["checkpoints"]:
        missing = required - set(cp.keys())
        assert not missing, f"CP {cp.get('id', '?')} missing fields: {missing}"


# ─────────────────────────────────────────────────────────────────────────────
# Cross-artifact contract validation
# ─────────────────────────────────────────────────────────────────────────────

def test_approved_bible_has_non_null_cta():
    """EP gate G-I enforces this at runtime; test documents the invariant."""
    assert PRODUCTION_BIBLE_VALID["approval"]["execution_approved"] is True
    assert PRODUCTION_BIBLE_VALID["identity"]["cta"] is not None, (
        "An execution_approved=True bible must not have null CTA — "
        "bible-director must collect CTA at Round 2b before finalizing"
    )


def test_bible_inherits_rejected_approaches_from_intelligence():
    """production_bible.intelligence.rejected_approaches must not be empty."""
    rejected = PRODUCTION_BIBLE_VALID["intelligence"].get("rejected_approaches", [])
    assert len(rejected) >= 1, (
        "Bible must carry rejected_approaches — prevents downstream stages from "
        "rediscovering the same bad paths in revision loops"
    )


def test_bible_beat_durations_sum_to_target():
    """Sum of beat durations must equal duration_target_seconds."""
    beats = PRODUCTION_BIBLE_VALID["narrative"]["emotional_beat_sequence"]
    total = sum(b["duration_seconds"] for b in beats)
    target = PRODUCTION_BIBLE_VALID["identity"]["duration_target_seconds"]
    assert abs(total - target) <= 0.5, (
        f"Beat durations sum to {total}s but target is {target}s "
        f"(difference: {abs(total - target)}s, tolerance: 0.5s)"
    )


def test_bible_intensity_values_are_normalized():
    """All intensity values must be in [0.0, 1.0]."""
    for beat in PRODUCTION_BIBLE_VALID["narrative"]["emotional_beat_sequence"]:
        intensity = beat["intensity"]
        assert 0.0 <= intensity <= 1.0, (
            f"Beat {beat['beat_id']} intensity {intensity} out of [0.0, 1.0]"
        )


def test_deliverables_primary_aspect_ratio_matches_platform():
    """TikTok platform → primary aspect ratio should be 9:16."""
    platform = PRODUCTION_BIBLE_VALID["identity"]["platform"]
    aspect = PRODUCTION_BIBLE_VALID["deliverables"]["primary"]["aspect_ratio"]
    if platform in ("tiktok", "instagram"):
        assert aspect == "9:16", (
            f"Platform '{platform}' should default to 9:16 primary, got {aspect!r}"
        )
    elif platform in ("youtube", "linkedin", "tv", "generic"):
        assert aspect == "16:9", (
            f"Platform '{platform}' should default to 16:9 primary, got {aspect!r}"
        )
