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
                "end_seconds": 8,
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
                "start_seconds": 8,
                "end_seconds": 16,
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
        "subtitles": {"enabled": False},
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

    def test_user_approved_without_user_visible_rejected(self) -> None:
        log = _valid_decision_log()
        log["decisions"][0]["user_visible"] = False
        log["decisions"][0]["user_approved"] = True
        with pytest.raises(ValidationError, match="user_visible"):
            validate_artifact("decision_log", log)

    def test_valid_decision_log_passes(self) -> None:
        validate_artifact("decision_log", _valid_decision_log())


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
