"""Phase 0 contract tests — infrastructure layer.

Tests config, schemas, checkpoints, pipeline manifests, tools, cost tracker,
and media profiles. The intelligence layer (orchestrator, reviewer, checkpoint
policy, handlers) has been replaced by instruction-driven architecture:
pipeline manifests + stage director skills + meta skills.
"""

import importlib
import json
import re
import sys
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

import pytest

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from lib.config_model import OpenMontageConfig
from lib.checkpoint import (
    CheckpointValidationError,
    STAGES,
    get_next_stage,
    read_checkpoint,
    write_checkpoint,
)
from lib.media_profiles import get_profile, ffmpeg_output_args, ALL_PROFILES
from lib.pipeline_loader import (
    get_required_tools,
    get_stage_order,
    get_stage_skill,
    get_stage_sub_stages,
    get_stage_review_focus,
    list_pipelines,
    load_pipeline,
    pipeline_supports_reference_input,
)
from tools.base_tool import BaseTool, ToolResult, ToolTier, ToolStatus
from tools.tool_registry import ToolRegistry
from tools.cost_tracker import CostTracker, BudgetMode, BudgetExceededError, ApprovalRequiredError
from schemas.artifacts import load_schema, validate_artifact, list_schemas
from tests.contracts.conftest import _minimal_production_proposal


def test_makefile_lint_py_compile_targets_exist():
    """Every Python file referenced by `make lint` must exist in the repo."""
    makefile = PROJECT_ROOT / "Makefile"
    body = makefile.read_text(encoding="utf-8")
    compile_targets = re.findall(r"python -m py_compile ([^\s]+\.py)", body)
    assert compile_targets, "Makefile lint target should py_compile at least one file"

    missing = [path for path in compile_targets if not (PROJECT_ROOT / path).is_file()]
    assert missing == []


def sample_artifact(name: str) -> dict:
    """Return a minimal schema-valid artifact for tests."""
    if name == "research_brief":
        return {
            "version": "1.0",
            "topic": "Test Topic",
            "research_date": "2026-03-27",
            "landscape": {
                "existing_content": [
                    {"title": "Existing Video 1", "source": "youtube", "angle": "tutorial", "what_it_covers": "basics"},
                    {"title": "Existing Video 2", "source": "blog", "angle": "deep dive", "what_it_covers": "advanced"},
                    {"title": "Existing Video 3", "source": "youtube", "angle": "comparison", "what_it_covers": "alternatives"},
                ],
                "saturated_angles": ["basic tutorial"],
                "underserved_gaps": ["misconceptions about topic"],
            },
            "data_points": [
                {"claim": "73% of users prefer X", "source_url": "https://example.com/study", "credibility": "primary_source"},
                {"claim": "Market grew 40% in 2025", "source_url": "https://example.com/report", "credibility": "secondary_source"},
                {"claim": "Most experts agree on Y", "source_url": "https://example.com/survey", "credibility": "primary_source"},
            ],
            "audience_insights": {
                "common_questions": ["What is X?", "How does X work?", "Why is X important?"],
                "misconceptions": [{"myth": "X is slow", "reality": "X is fast"}],
                "knowledge_level": "Beginner to intermediate",
            },
            "angles_discovered": [
                {"name": "The Surprising Truth", "hook": "You think X is slow. It's not.", "type": "contrarian", "why_now": "New benchmark data", "grounded_in": ["data_point_1"]},
                {"name": "X From Scratch", "hook": "Build X in 5 minutes.", "type": "evergreen", "why_now": "Audience demand", "grounded_in": ["audience_q1"]},
                {"name": "Why X Matters Now", "hook": "X just changed everything.", "type": "trending", "why_now": "Recent announcement", "grounded_in": ["trending_1"]},
            ],
            "sources": [
                {"url": "https://example.com/study", "title": "Study on X", "used_for": "data_points"},
                {"url": "https://example.com/report", "title": "Market Report", "used_for": "data_points"},
                {"url": "https://example.com/survey", "title": "Expert Survey", "used_for": "data_points"},
                {"url": "https://example.com/reddit", "title": "Reddit Discussion", "used_for": "audience_insights"},
                {"url": "https://example.com/blog", "title": "Tech Blog", "used_for": "landscape"},
            ],
        }
    if name == "proposal_packet":
        return {
            "version": "1.0",
            "concept_options": [
                {
                    "id": "c1", "title": "The Surprising Truth About X", "hook": "You think X is slow.",
                    "narrative_structure": "myth_busting", "visual_approach": "animated diagrams",
                    "target_duration_seconds": 60, "why_this_works": "Strong misconception found in research",
                },
                {
                    "id": "c2", "title": "X From Scratch", "hook": "Build X in 5 minutes.",
                    "narrative_structure": "tutorial", "visual_approach": "code walkthrough",
                    "target_duration_seconds": 90, "why_this_works": "High demand in audience questions",
                },
                {
                    "id": "c3", "title": "Why X Matters Now", "hook": "X just changed everything.",
                    "narrative_structure": "timeline", "visual_approach": "motion graphics",
                    "target_duration_seconds": 75, "why_this_works": "Recent announcement creates timeliness",
                },
            ],
            "selected_concept": {"concept_id": "c1", "rationale": "Strongest research backing"},
            "production_plan": {
                "pipeline": "animated-explainer",
                "render_runtime": "remotion",
                "stages": [
                    {"stage": "script", "tools": [], "approach": "Write from research"},
                    {"stage": "assets", "tools": [{"tool_name": "tts_selector", "role": "narration", "available": True}], "approach": "Generate assets"},
                ],
            },
            "cost_estimate": {
                "total_estimated_usd": 0.52,
                "line_items": [{"tool": "elevenlabs_tts", "operation": "narration", "estimated_usd": 0.18}],
                "budget_verdict": "within_budget",
            },
            "approval": {"status": "approved"},
        }
    if name == "brief":
        return {
            "version": "1.0",
            "title": "Test Brief",
            "hook": "Did you know?",
            "key_points": ["point 1"],
            "tone": "casual",
            "style": "clean-professional",
            "target_platform": "youtube",
            "target_duration_seconds": 60,
        }
    if name == "script":
        return {
            "version": "1.0",
            "title": "Test Script",
            "total_duration_seconds": 60,
            "sections": [
                {
                    "id": "s1",
                    "text": "Hello world",
                    "start_seconds": 0,
                    "end_seconds": 10,
                }
            ],
        }
    if name == "scene_plan":
        return {
            "version": "1.0",
            "scenes": [
                {
                    "id": "scene-1",
                    "type": "talking_head",
                    "description": "Host on camera",
                    "start_seconds": 0,
                    "end_seconds": 10,
                }
            ],
        }
    if name == "asset_manifest":
        return {
            "version": "1.0",
            "assets": [
                {
                    "id": "asset-1",
                    "type": "video",
                    "path": "assets/clip.mp4",
                    "source_tool": "ffmpeg",
                    "scene_id": "scene-1",
                }
            ],
            "costs": [{"tool": "ffmpeg", "cost_usd": 0.0}],
            "total_cost_usd": 0.0,
        }
    if name == "edit_decisions":
        return {
            "version": "1.0",
            "cuts": [
                {
                    "id": "cut-1",
                    "source": "asset-1",
                    "in_seconds": 0,
                    "out_seconds": 10,
                }
            ],
        }
    if name == "render_report":
        return {
            "version": "1.0",
            "outputs": [
                {
                    "path": "renders/output.mp4",
                    "format": "mp4",
                    "resolution": "1920x1080",
                    "duration_seconds": 60,
                }
            ],
        }
    if name == "publish_log":
        return {
            "version": "1.0",
            "entries": [
                {
                    "platform": "youtube",
                    "status": "draft",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            ],
        }
    if name == "video_analysis_brief":
        return {
            "version": "1.0",
            "source": {
                "type": "youtube",
                "url": "https://example.com/watch?v=abc123def45",
                "title": "Reference Video",
                "duration_seconds": 60,
            },
            "content_analysis": {
                "summary": "A fast explainer reference.",
                "topics": ["quantum computing"],
                "target_audience": "general",
            },
            "structure_analysis": {
                "total_scenes": 3,
                "scenes": [
                    {
                        "scene_index": 0,
                        "start_time": 0,
                        "end_time": 5,
                        "description": "Hook",
                    },
                    {
                        "scene_index": 1,
                        "start_time": 5,
                        "end_time": 20,
                        "description": "Setup",
                    },
                    {
                        "scene_index": 2,
                        "start_time": 20,
                        "end_time": 60,
                        "description": "Payoff",
                    },
                ],
                "pacing_profile": {
                    "avg_scene_duration_seconds": 20,
                    "cuts_per_minute": 3,
                    "pacing_style": "steady_educational",
                },
            },
        }
    raise KeyError(f"Unknown artifact sample: {name}")


def ad_video_asset_manifest_with_narration() -> dict:
    artifact = sample_artifact("asset_manifest")
    artifact["assets"].append(
        {
            "id": "narr-1",
            "type": "narration",
            "path": "assets/audio/narr-1.mp3",
            "source_tool": "tts_selector",
            "scene_id": "scene-1",
        }
    )
    artifact["costs"].append({"tool": "tts_selector", "cost_usd": 0.0})
    return artifact


def ad_video_assets_checkpoint_context() -> dict:
    proposal = deepcopy(_minimal_production_proposal())
    proposal["product_reference_strategy"] = "not_applicable"

    voice_performance = {
        "emotion": "calm confidence",
        "intonation": "natural conversational rises",
        "rhythm": "measured product proof beats",
        "pace": "measured",
        "pause_after_seconds": 0.25,
    }
    script = {
        "version": "1.0",
        "title": "Assets Checkpoint Script",
        "total_duration_seconds": 8,
        "user_approved": True,
        "sections": [
            {
                "id": "hook",
                "text": "Meet the workflow that keeps every launch on track.",
                "start_seconds": 0,
                "end_seconds": 4,
                "speaker_directions": "Open with understated confidence.",
                "voice_performance": voice_performance,
                "tts_directive": {"speed_mult": 1.0},
            },
            {
                "id": "cta",
                "text": "Start your next campaign with fewer handoffs.",
                "start_seconds": 4,
                "end_seconds": 8,
                "speaker_directions": "Close with a precise CTA.",
                "voice_performance": voice_performance,
                "tts_directive": {"speed_mult": 1.0},
            },
        ],
    }
    scene_plan = {
        "version": "1.0",
        "style_mode": "cinematic",
        "total_duration_seconds": 8,
        "scenes": [
            {
                "id": "scene-1",
                "type": "text_card",
                "description": "Brand promise text card over abstract interface motion.",
                "start_seconds": 0,
                "end_seconds": 8,
                "core": True,
                "motion_required": False,
                "product_visibility": "none",
                "product_reference_required": False,
            }
        ],
    }
    decision_log = {
        "version": "1.0",
        "project_id": "assets-checkpoint-context",
        "decisions": [
            {
                "decision_id": "d-runtime",
                "stage": "proposal",
                "category": "render_runtime_selection",
                "subject": "Select render runtime",
                "options_considered": [
                    {
                        "option_id": "ffmpeg",
                        "label": "FFmpeg",
                        "score": 0.8,
                        "reason": "Best fit for this simple cinematic checkpoint fixture.",
                    }
                ],
                "selected": "ffmpeg",
                "reason": "Matches the locked proposal runtime.",
                "user_visible": True,
                "user_approved": True,
            },
            {
                "decision_id": "d-product-reference",
                "stage": "proposal",
                "category": "product_identity_reference_selection",
                "subject": "Select product reference strategy",
                "options_considered": [
                    {
                        "option_id": "not_applicable",
                        "label": "Not applicable",
                        "score": 0.9,
                        "reason": "No product-visible scenes are planned.",
                    }
                ],
                "selected": "not_applicable",
                "reason": "No product-visible scenes are planned.",
                "user_visible": True,
                "user_approved": True,
            },
            {
                "decision_id": "d-music",
                "stage": "proposal",
                "category": "music_strategy_selection",
                "subject": "Select music strategy",
                "options_considered": [
                    {
                        "option_id": "generative_loose",
                        "label": "Generative loose",
                        "score": 0.8,
                        "reason": "Adequate for a non-beat-locked checkpoint fixture.",
                    }
                ],
                "selected": "generative_loose",
                "reason": "Matches the locked proposal music strategy.",
                "user_visible": True,
                "user_approved": True,
            },
        ],
    }
    return {
        "production_proposal": proposal,
        "production_bible": ad_video_production_bible(),
        "script": script,
        "scene_plan": scene_plan,
        "decision_log": decision_log,
    }


def ad_video_assets_manifest_with_narration_inventory(section_ids=("hook", "cta")) -> dict:
    assets = [
        {
            "id": f"narr-{section_id}",
            "type": "narration",
            "path": f"assets/audio/{section_id}.mp3",
            "source_tool": "cosyvoice_tts",
            "scene_id": "global",
            "model": "qwen3-tts-instruct-flash",
        }
        for section_id in section_ids
    ]
    assets.append(
        {
            "id": "music-1",
            "type": "music",
            "path": "assets/music/background.mp3",
            "source_tool": "minimax_music",
            "scene_id": "global",
            "model": "music-2.6",
        }
    )
    return {
        "version": "1.0",
        "assets": assets,
        "narration_files": [
            {
                "section_id": section_id,
                "file": f"assets/audio/{section_id}.mp3",
                "duration_seconds": 4,
            }
            for section_id in section_ids
        ],
        "subtitle_file": "assets/subtitles.ass",
        "music_file": "assets/music/background.mp3",
        "costs": [
            {"tool": "cosyvoice_tts", "cost_usd": 0.0},
            {"tool": "minimax_music", "cost_usd": 0.0},
        ],
        "total_cost_usd": 0.0,
    }


def ad_video_assets_checkpoint_artifacts(product_identity_reference: dict) -> dict:
    return {
        "product_identity_reference": product_identity_reference,
        "asset_manifest": ad_video_assets_manifest_with_narration_inventory(),
        **ad_video_assets_checkpoint_context(),
    }


def ad_video_scene_plan_for_edit() -> dict:
    return {
        "version": "1.0",
        "style_mode": "cinematic",
        "total_duration_seconds": 1.2,
        "scenes": [
            {
                "id": "scene-1",
                "type": "generated",
                "description": "Single edit checkpoint scene.",
                "start_seconds": 0,
                "end_seconds": 1.2,
                "duration_seconds": 1.2,
                "product_visibility": "none",
                "product_reference_required": False,
                "core": True,
                "motion_required": True,
            }
        ],
    }


def ad_video_production_bible() -> dict:
    truth_rule = {
        "rule_id": "TC-1",
        "requirement": "Product remains Acme Widget Pro.",
        "prohibited_failure": "Renaming or visually replacing the product.",
        "evidence_source": "brief",
        "source_confidence": "source-backed",
    }
    return {
        "version": "1.0",
        "pipeline": "ad-video",
        "project_id": "phase0-test",
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
            "key_message": "Widget Pro saves time.",
            "cta": "Buy now at acme.com",
            "tone": "confident",
        },
        "narrative": {
            "arc_type": "problem-solution",
            "pacing_model": "punchy",
            "hook_mechanic": "question",
            "hook_window_seconds": 3,
            "tension_peak_at_seconds": 20,
            "resolution_type": "aspiration",
            "emotional_beat_sequence": [
                {
                    "beat_id": "B1",
                    "name": "HOOK",
                    "duration_seconds": 10,
                    "emotional_target": "confidence",
                    "intensity": 0.7,
                    "script_constraint": "Open with the product promise.",
                    "visual_constraint": "Show the product clearly.",
                },
                {
                    "beat_id": "B2",
                    "name": "CTA",
                    "duration_seconds": 20,
                    "emotional_target": "action",
                    "intensity": 0.8,
                    "script_constraint": "Close on the call to action.",
                    "visual_constraint": "End with brand and product visible.",
                }
            ],
            "intensity_curve": [
                {"t_seconds": 0, "value": 0.7},
                {"t_seconds": 10, "value": 0.8},
                {"t_seconds": 30, "value": 0.8},
            ],
        },
        "intelligence": {
            "trend_alignment": {"selected_trend_ids": [], "alignments": []},
            "knowledge_alignment": {"selected_card_ids": [], "alignments": []},
        },
        "truth_contract": {
            "objective_facts": [truth_rule],
            "physical_constraints": [truth_rule],
            "product_geometry_rules": [truth_rule],
            "motion_coherence_rules": [truth_rule],
            "values_guardrails": [truth_rule],
        },
        "visual": {"style_mode": "cinematic"},
        "audio": {
            "voice_character": {
                "tone": "warm",
                "pacing": "measured",
                "persona": "product narrator",
            },
            "music_direction": {"mood": "aspirational"},
            "av_sync_notes": "",
        },
        "brand_constraints": {"brand_name_in_final_frame": True},
        "deliverables": {
            "primary": {
                "aspect_ratio": "16:9",
                "duration_seconds": 30,
            }
        },
        "compliance_manifest": {"checkpoints": []},
    }


def ad_video_render_report() -> dict:
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


def ad_video_final_review(status: str = "pass") -> dict:
    return {
        "version": "1.0",
        "output_path": "renders/final.mp4",
        "status": status,
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
        "issues_found": [] if status == "pass" else ["Render has visible defects."],
        "recommended_action": "present_to_user" if status == "pass" else "revise_edit",
    }


def ad_video_publish_log() -> dict:
    return {
        "version": "1.0",
        "entries": [
            {
                "platform": "youtube",
                "status": "exported",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "export_path": "renders/final.mp4",
            }
        ],
        "output_file_matrix": [
            {
                "file": "renders/final.mp4",
                "variant": "16:9",
                "duration_seconds": 30,
                "target_platforms": ["youtube"],
                "thumbnail_concept": "Product hero shot",
                "metadata": {
                    "title": "Acme Widget Launch",
                    "description": "A direct response product spot.",
                    "tags": ["acme", "widget", "ad"],
                    "cta_url": "https://example.com",
                },
            }
        ],
    }


# ---- Config ----

class TestConfig:
    def test_load_defaults(self):
        config = OpenMontageConfig()
        assert config.llm.provider == "anthropic"
        assert config.budget.mode.value == "warn"
        assert config.checkpoint.policy.value == "guided"

    def test_load_from_yaml(self):
        config = OpenMontageConfig.load()
        assert config.budget.total_usd == 10.0


# ---- Schemas ----

class TestSchemas:
    def test_all_schemas_loadable(self):
        names = list_schemas()
        assert len(names) >= 7
        for name in names:
            schema = load_schema(name)
            assert "$schema" in schema

    def test_brief_validates(self):
        validate_artifact("brief", sample_artifact("brief"))

    def test_brief_rejects_invalid(self):
        with pytest.raises(Exception):
            validate_artifact("brief", {"version": "1.0"})

    def test_video_analysis_brief_validates(self):
        validate_artifact("video_analysis_brief", sample_artifact("video_analysis_brief"))

    def test_edit_decisions_accepts_volume_schedule(self):
        """audio.music.volume_schedule is the new optional Path B field.
        Edit decisions emitting it must validate against the schema."""
        artifact = {
            "version": "1.0",
            "render_runtime": "remotion",
            "cuts": [
                {"id": "cut-1", "source": "asset-1", "in_seconds": 0, "out_seconds": 10},
            ],
            "audio": {
                "music": {
                    "asset_id": "music-1",
                    "volume_schedule": [
                        {"t_seconds": 0.0,  "gain_db": 0.0},
                        {"t_seconds": 1.7,  "gain_db": 0.0},
                        {"t_seconds": 2.0,  "gain_db": -18.0},
                        {"t_seconds": 8.0,  "gain_db": -18.0},
                        {"t_seconds": 8.3,  "gain_db": 0.0},
                    ],
                }
            },
        }
        validate_artifact("edit_decisions", artifact)

    def test_ad_video_edit_decisions_accept_cut_beat_labels_and_volume_schedule(self):
        artifact = {
            "version": "1.0",
            "render_runtime": "remotion",
            "music_strategy": "generative_loose",
            "cuts": [
                {
                    "id": "cut-1",
                    "source": "asset-1",
                    "in_seconds": 0,
                    "out_seconds": 1.2,
                    "maps_to_beat": "B3",
                    "transition_out": "match_cut",
                },
            ],
            "audio": {
                "music": {
                    "asset_id": "music-1",
                    "volume_schedule": [
                        {"t_seconds": 0.0, "gain_db": 0.0},
                        {"t_seconds": 0.3, "gain_db": -11.2},
                        {"t_seconds": 1.2, "gain_db": -11.2},
                        {"t_seconds": 1.5, "gain_db": 0.0},
                    ],
                }
            },
        }

        validate_artifact("edit_decisions", artifact, pipeline_type="ad-video")

    def test_ad_video_edit_decisions_allow_no_music_without_volume_schedule(self):
        artifact = {
            "version": "1.0",
            "render_runtime": "remotion",
            "music_strategy": "none",
            "cuts": [
                {
                    "id": "cut-1",
                    "source": "asset-1",
                    "in_seconds": 0,
                    "out_seconds": 1.2,
                    "maps_to_beat": "B3",
                },
            ],
            "audio": {
                "narration": {
                    "segments": [
                        {"asset_id": "narr-1", "start_seconds": 0, "end_seconds": 1.1},
                    ],
                },
                "sfx": [
                    {"asset_id": "sfx-1", "start_seconds": 0.8, "volume": 0.5},
                ],
            },
        }

        validate_artifact("edit_decisions", artifact, pipeline_type="ad-video")

    def test_edit_decisions_rejects_volume_schedule_missing_gain_db(self):
        """volume_schedule items must carry gain_db (no default)."""
        artifact = {
            "version": "1.0",
            "render_runtime": "remotion",
            "cuts": [
                {"id": "cut-1", "source": "asset-1", "in_seconds": 0, "out_seconds": 10},
            ],
            "audio": {
                "music": {
                    "volume_schedule": [
                        {"t_seconds": 0.0},
                    ],
                }
            },
        }
        with pytest.raises(Exception):
            validate_artifact("edit_decisions", artifact)

    def test_edit_decisions_rejects_volume_schedule_negative_time(self):
        artifact = {
            "version": "1.0",
            "render_runtime": "remotion",
            "cuts": [
                {"id": "cut-1", "source": "asset-1", "in_seconds": 0, "out_seconds": 10},
            ],
            "audio": {
                "music": {
                    "volume_schedule": [
                        {"t_seconds": -0.5, "gain_db": 0.0},
                    ],
                }
            },
        }
        with pytest.raises(Exception):
            validate_artifact("edit_decisions", artifact)

    def test_script_accepts_tts_directive(self):
        """sections[].tts_directive is the new optional Path A field."""
        artifact = {
            "version": "1.0",
            "title": "Path A test",
            "total_duration_seconds": 30,
            "sections": [
                {
                    "id": "s1",
                    "text": "Hook line.",
                    "start_seconds": 0,
                    "end_seconds": 5,
                    "tts_directive": {"speed_mult": 1.03},
                },
                {
                    "id": "s2",
                    "text": "Reveal line.",
                    "start_seconds": 5,
                    "end_seconds": 12,
                    "tts_directive": {"speed_mult": 0.97},
                },
            ],
        }
        validate_artifact("script", artifact)

    def test_script_rejects_tts_directive_without_speed_mult(self):
        """speed_mult is the only field; without it the directive is meaningless."""
        artifact = {
            "version": "1.0",
            "title": "Bad directive",
            "total_duration_seconds": 10,
            "sections": [
                {
                    "id": "s1",
                    "text": "x",
                    "start_seconds": 0,
                    "end_seconds": 10,
                    "tts_directive": {},
                },
            ],
        }
        with pytest.raises(Exception):
            validate_artifact("script", artifact)

    def test_script_rejects_tts_directive_speed_outside_safe_range(self):
        """speed_mult bounded [0.5, 2.0] to match cosyvoice and keep delivery natural."""
        artifact = {
            "version": "1.0",
            "title": "Out of range",
            "total_duration_seconds": 10,
            "sections": [
                {
                    "id": "s1",
                    "text": "x",
                    "start_seconds": 0,
                    "end_seconds": 10,
                    "tts_directive": {"speed_mult": 3.0},  # > 2.0
                },
            ],
        }
        with pytest.raises(Exception):
            validate_artifact("script", artifact)


# ---- Checkpoint ----

class TestCheckpoint:
    def test_write_read_roundtrip(self, tmp_path):
        write_checkpoint(
            tmp_path, "test_project", "research", "completed",
            {"research_brief": sample_artifact("research_brief")},
        )
        cp = read_checkpoint(tmp_path, "test_project", "research")
        assert cp is not None
        assert cp["stage"] == "research"
        assert cp["status"] == "completed"
        assert cp["artifacts"]["research_brief"]["topic"] == "Test Topic"

    def test_get_next_stage(self, tmp_path):
        assert get_next_stage(tmp_path, "proj") == "research"
        write_checkpoint(
            tmp_path,
            "proj",
            "research",
            "completed",
            {"research_brief": sample_artifact("research_brief")},
        )
        assert get_next_stage(tmp_path, "proj") == "proposal"

    def test_invalid_stage_rejected(self, tmp_path):
        with pytest.raises(ValueError):
            write_checkpoint(tmp_path, "proj", "invalid_stage", "completed", {})

    def test_ad_video_manifest_stage_accepted(self, tmp_path):
        write_checkpoint(
            tmp_path,
            "proj",
            "intake",
            "in_progress",
            {},
            pipeline_type="ad-video",
        )
        cp = read_checkpoint(tmp_path, "proj", "intake")
        assert cp is not None
        assert cp["pipeline_type"] == "ad-video"
        assert cp["stage"] == "intake"

    def test_ad_video_stage_requires_pipeline_specific_artifact(self, tmp_path):
        with pytest.raises(CheckpointValidationError, match="production_bible"):
            write_checkpoint(
                tmp_path,
                "proj",
                "bible",
                "completed",
                {},
                pipeline_type="ad-video",
            )

    def test_ad_video_assets_checkpoint_requires_product_identity_reference(self, tmp_path):
        with pytest.raises(CheckpointValidationError, match="product_identity_reference"):
            write_checkpoint(
                tmp_path,
                "proj",
                "assets",
                "completed",
                {
                    "asset_manifest": ad_video_assets_manifest_with_narration_inventory(),
                    **ad_video_assets_checkpoint_context(),
                },
                pipeline_type="ad-video",
            )

        product_identity_reference = {
            "version": "1.0",
            "reference_id": "pir-none",
            "product_name": "Acme SaaS",
            "source_type": "not_applicable",
            "approval_status": "not_required",
            "required_visual_features": [],
            "prohibited_variations": [],
        }

        path = write_checkpoint(
            tmp_path,
            "proj",
            "assets",
            "completed",
            ad_video_assets_checkpoint_artifacts(product_identity_reference),
            pipeline_type="ad-video",
            metadata={
                "ep_state": {
                    "sample_approved": True,
                    "asset_review_approved": True,
                    "music_review_approved": True,
                }
            },
        )

        assert path.exists()

    def test_ad_video_assets_checkpoint_requires_cross_stage_validation_context(self, tmp_path):
        product_identity_reference = {
            "version": "1.0",
            "reference_id": "pir-none",
            "product_name": "Acme SaaS",
            "source_type": "not_applicable",
            "approval_status": "not_required",
            "required_visual_features": [],
            "prohibited_variations": [],
        }

        with pytest.raises(CheckpointValidationError, match="production_proposal"):
            write_checkpoint(
                tmp_path,
                "proj",
                "assets",
                "completed",
                {
                    "product_identity_reference": product_identity_reference,
                    "asset_manifest": ad_video_assets_manifest_with_narration_inventory(),
                },
                pipeline_type="ad-video",
                metadata={
                    "ep_state": {
                        "sample_approved": True,
                        "asset_review_approved": True,
                        "music_review_approved": True,
                    }
                },
            )

    def test_ad_video_assets_checkpoint_runs_provider_consistency_with_script(self, tmp_path):
        product_identity_reference = {
            "version": "1.0",
            "reference_id": "pir-none",
            "product_name": "Acme SaaS",
            "source_type": "not_applicable",
            "approval_status": "not_required",
            "required_visual_features": [],
            "prohibited_variations": [],
        }
        artifacts = {
            "product_identity_reference": product_identity_reference,
            "asset_manifest": ad_video_assets_manifest_with_narration_inventory(
                section_ids=("hook",)
            ),
            **ad_video_assets_checkpoint_context(),
        }

        with pytest.raises(CheckpointValidationError, match="provider_consistency_check"):
            write_checkpoint(
                tmp_path,
                "proj",
                "assets",
                "completed",
                artifacts,
                pipeline_type="ad-video",
                metadata={
                    "ep_state": {
                        "sample_approved": True,
                        "asset_review_approved": True,
                        "music_review_approved": True,
                    }
                },
            )

    def test_ad_video_assets_checkpoint_requires_approval_gate_state(self, tmp_path):
        product_identity_reference = {
            "version": "1.0",
            "reference_id": "pir-none",
            "product_name": "Acme SaaS",
            "source_type": "not_applicable",
            "approval_status": "not_required",
            "required_visual_features": [],
            "prohibited_variations": [],
        }
        artifacts = ad_video_assets_checkpoint_artifacts(product_identity_reference)

        with pytest.raises(CheckpointValidationError, match="sample_approved"):
            write_checkpoint(
                tmp_path,
                "proj",
                "assets",
                "completed",
                artifacts,
                pipeline_type="ad-video",
            )

        with pytest.raises(CheckpointValidationError, match="asset_review_approved"):
            write_checkpoint(
                tmp_path,
                "proj",
                "assets",
                "completed",
                artifacts,
                pipeline_type="ad-video",
                metadata={
                    "ep_state": {
                        "sample_approved": True,
                        "asset_review_approved": False,
                        "music_review_approved": True,
                    }
                },
            )

        path = write_checkpoint(
            tmp_path,
            "proj",
            "assets",
            "completed",
            artifacts,
            pipeline_type="ad-video",
            metadata={
                "ep_state": {
                    "sample_approved": True,
                    "asset_review_approved": True,
                    "music_review_approved": True,
                }
            },
        )

        assert path.exists()

    def test_ad_video_assets_checkpoint_rejects_pending_product_reference(self, tmp_path):
        product_identity_reference = {
            "version": "1.0",
            "reference_id": "pir-generated",
            "product_name": "Acme Phone",
            "source_type": "generated",
            "approval_status": "pending",
            "selected_reference_image_path": "reference_assets/product.png",
            "required_visual_features": ["round camera island"],
            "prohibited_variations": ["generic rectangle camera bar"],
        }

        with pytest.raises(CheckpointValidationError, match="product_identity_reference"):
            write_checkpoint(
                tmp_path,
                "proj",
                "assets",
                "completed",
                {
                    "product_identity_reference": product_identity_reference,
                    "asset_manifest": ad_video_assets_manifest_with_narration_inventory(),
                    **ad_video_assets_checkpoint_context(),
                },
                pipeline_type="ad-video",
                metadata={
                    "ep_state": {
                        "sample_approved": True,
                        "asset_review_approved": True,
                        "music_review_approved": True,
                    }
                },
            )

    def test_ad_video_script_checkpoint_requires_voice_cues(self, tmp_path):
        with pytest.raises(CheckpointValidationError, match="speaker_directions"):
            write_checkpoint(
                tmp_path,
                "proj",
                "script",
                "completed",
                {
                    "script": {
                        "version": "1.0",
                        "title": "Missing voice cues",
                        "total_duration_seconds": 5,
                        "sections": [
                            {
                                "id": "hook",
                                "text": "A sparse ad-video line.",
                                "start_seconds": 0,
                                "end_seconds": 5,
                            }
                        ],
                    }
                },
                pipeline_type="ad-video",
            )

    def test_ad_video_script_checkpoint_requires_tts_directive(self, tmp_path):
        with pytest.raises(CheckpointValidationError, match="tts_directive"):
            write_checkpoint(
                tmp_path,
                "proj",
                "script",
                "completed",
                {
                    "script": {
                        "version": "1.0",
                        "title": "Missing TTS Directive",
                        "total_duration_seconds": 5,
                        "sections": [
                            {
                                "id": "hook",
                                "text": "A sparse ad-video line.",
                                "start_seconds": 0,
                                "end_seconds": 5,
                                "speaker_directions": "Measured and intimate.",
                                "voice_performance": {
                                    "emotion": "intrigue",
                                    "intonation": "soft rise, clean resolve",
                                    "rhythm": "short phrase with a breath before the claim",
                                    "pace": "measured",
                                    "pause_after_seconds": 0.25,
                                },
                            }
                        ],
                    }
                },
                pipeline_type="ad-video",
            )

    def test_ad_video_edit_checkpoint_requires_volume_schedule(self, tmp_path):
        proposal = _minimal_production_proposal()
        proposal["render_runtime"] = "remotion"

        with pytest.raises(CheckpointValidationError, match="volume_schedule"):
            write_checkpoint(
                tmp_path,
                "proj",
                "edit",
                "completed",
                {
                    "production_proposal": proposal,
                    "scene_plan": ad_video_scene_plan_for_edit(),
                    "asset_manifest": sample_artifact("asset_manifest"),
                    "edit_decisions": {
                        "version": "1.0",
                        "render_runtime": "remotion",
                        "music_strategy": "generative_loose",
                        "cuts": [
                            {
                                "id": "cut-1",
                                "source": "asset-1",
                                "in_seconds": 0,
                                "out_seconds": 1.2,
                                "maps_to_beat": "B3",
                            }
                        ],
                    }
                },
                pipeline_type="ad-video",
            )

    def test_ad_video_edit_checkpoint_requires_cut_beat_labels(self, tmp_path):
        proposal = _minimal_production_proposal()
        proposal["render_runtime"] = "remotion"

        with pytest.raises(CheckpointValidationError, match="beat"):
            write_checkpoint(
                tmp_path,
                "proj",
                "edit",
                "completed",
                {
                    "production_proposal": proposal,
                    "scene_plan": ad_video_scene_plan_for_edit(),
                    "asset_manifest": sample_artifact("asset_manifest"),
                    "edit_decisions": {
                        "version": "1.0",
                        "render_runtime": "remotion",
                        "music_strategy": "generative_loose",
                        "cuts": [
                            {
                                "id": "cut-1",
                                "source": "asset-1",
                                "in_seconds": 0,
                                "out_seconds": 1.2,
                            }
                        ],
                        "audio": {
                            "music": {
                                "volume_schedule": [
                                    {"t_seconds": 0.0, "gain_db": 0.0},
                                    {"t_seconds": 0.3, "gain_db": -11.2},
                                    {"t_seconds": 1.2, "gain_db": -11.2},
                                    {"t_seconds": 1.5, "gain_db": 0.0},
                                ],
                            }
                        },
                    }
                },
                pipeline_type="ad-video",
            )

    def test_ad_video_edit_checkpoint_allows_no_music_strategy_none(self, tmp_path):
        proposal = _minimal_production_proposal()
        proposal["music_strategy"] = "none"
        proposal["render_runtime"] = "remotion"

        path = write_checkpoint(
            tmp_path,
            "proj",
            "edit",
            "completed",
            {
                "production_proposal": proposal,
                "scene_plan": ad_video_scene_plan_for_edit(),
                "asset_manifest": ad_video_asset_manifest_with_narration(),
                "edit_decisions": {
                    "version": "1.0",
                    "render_runtime": "remotion",
                    "music_strategy": "none",
                    "cuts": [
                        {
                            "id": "cut-1",
                            "source": "asset-1",
                            "in_seconds": 0,
                            "out_seconds": 1.2,
                            "maps_to_beat": "B3",
                        }
                    ],
                    "audio": {
                        "narration": {
                            "segments": [
                                {
                                    "asset_id": "narr-1",
                                    "start_seconds": 0,
                                    "end_seconds": 1.1,
                                },
                            ],
                        }
                    },
                }
            },
            pipeline_type="ad-video",
        )

        assert path.exists()

    def test_ad_video_edit_checkpoint_requires_production_proposal(self, tmp_path):
        with pytest.raises(CheckpointValidationError, match="production_proposal"):
            write_checkpoint(
                tmp_path,
                "proj",
                "edit",
                "completed",
                {
                    "scene_plan": ad_video_scene_plan_for_edit(),
                    "asset_manifest": sample_artifact("asset_manifest"),
                    "edit_decisions": {
                        "version": "1.0",
                        "render_runtime": "ffmpeg",
                        "music_strategy": "none",
                        "cuts": [
                            {
                                "id": "cut-1",
                                "source": "asset-1",
                                "in_seconds": 0,
                                "out_seconds": 1.2,
                                "maps_to_beat": "B3",
                            }
                        ],
                    }
                },
                pipeline_type="ad-video",
            )

    def test_ad_video_edit_checkpoint_requires_asset_manifest(self, tmp_path):
        proposal = _minimal_production_proposal()
        proposal["music_strategy"] = "none"

        with pytest.raises(CheckpointValidationError, match="asset_manifest"):
            write_checkpoint(
                tmp_path,
                "proj",
                "edit",
                "completed",
                {
                    "production_proposal": proposal,
                    "scene_plan": ad_video_scene_plan_for_edit(),
                    "edit_decisions": {
                        "version": "1.0",
                        "render_runtime": "ffmpeg",
                        "music_strategy": "none",
                        "cuts": [
                            {
                                "id": "cut-1",
                                "source": "asset-1",
                                "in_seconds": 0,
                                "out_seconds": 1.2,
                                "maps_to_beat": "B3",
                            }
                        ],
                    },
                },
                pipeline_type="ad-video",
            )

    def test_ad_video_edit_checkpoint_requires_scene_plan(self, tmp_path):
        proposal = _minimal_production_proposal()
        proposal["music_strategy"] = "none"

        with pytest.raises(CheckpointValidationError, match="scene_plan"):
            write_checkpoint(
                tmp_path,
                "proj",
                "edit",
                "completed",
                {
                    "production_proposal": proposal,
                    "asset_manifest": sample_artifact("asset_manifest"),
                    "edit_decisions": {
                        "version": "1.0",
                        "render_runtime": "ffmpeg",
                        "music_strategy": "none",
                        "cuts": [
                            {
                                "id": "cut-1",
                                "source": "asset-1",
                                "in_seconds": 0,
                                "out_seconds": 1.2,
                                "maps_to_beat": "B3",
                            }
                        ],
                    },
                },
                pipeline_type="ad-video",
            )

    def test_ad_video_edit_checkpoint_rejects_timeline_gap(self, tmp_path):
        proposal = _minimal_production_proposal()
        proposal["music_strategy"] = "none"
        scene_plan = ad_video_scene_plan_for_edit()
        scene_plan["total_duration_seconds"] = 2.0
        scene_plan["scenes"][0]["end_seconds"] = 2.0
        scene_plan["scenes"][0]["duration_seconds"] = 2.0

        with pytest.raises(CheckpointValidationError, match="timeline gap"):
            write_checkpoint(
                tmp_path,
                "proj",
                "edit",
                "completed",
                {
                    "production_proposal": proposal,
                    "scene_plan": scene_plan,
                    "asset_manifest": sample_artifact("asset_manifest"),
                    "edit_decisions": {
                        "version": "1.0",
                        "render_runtime": "ffmpeg",
                        "music_strategy": "none",
                        "cuts": [
                            {
                                "id": "cut-1",
                                "source": "asset-1",
                                "in_seconds": 0,
                                "out_seconds": 0.8,
                                "maps_to_beat": "B1",
                            },
                            {
                                "id": "cut-2",
                                "source": "remotion:stat_card",
                                "in_seconds": 1.0,
                                "out_seconds": 2.0,
                                "maps_to_beat": "B2",
                            },
                        ],
                    },
                },
                pipeline_type="ad-video",
            )

    def test_ad_video_edit_checkpoint_rejects_unresolved_cut_source(self, tmp_path):
        proposal = _minimal_production_proposal()
        proposal["music_strategy"] = "none"

        with pytest.raises(CheckpointValidationError, match="cut source"):
            write_checkpoint(
                tmp_path,
                "proj",
                "edit",
                "completed",
                {
                    "production_proposal": proposal,
                    "scene_plan": ad_video_scene_plan_for_edit(),
                    "asset_manifest": sample_artifact("asset_manifest"),
                    "edit_decisions": {
                        "version": "1.0",
                        "render_runtime": "ffmpeg",
                        "music_strategy": "none",
                        "cuts": [
                            {
                                "id": "cut-1",
                                "source": "missing-asset",
                                "in_seconds": 0,
                                "out_seconds": 1.2,
                                "maps_to_beat": "B3",
                            }
                        ],
                    },
                },
                pipeline_type="ad-video",
            )

    def test_ad_video_edit_checkpoint_rejects_missing_music_asset_id(self, tmp_path):
        proposal = _minimal_production_proposal()

        with pytest.raises(CheckpointValidationError, match="audio.music.asset_id"):
            write_checkpoint(
                tmp_path,
                "proj",
                "edit",
                "completed",
                {
                    "production_proposal": proposal,
                    "scene_plan": ad_video_scene_plan_for_edit(),
                    "asset_manifest": sample_artifact("asset_manifest"),
                    "edit_decisions": {
                        "version": "1.0",
                        "render_runtime": "ffmpeg",
                        "music_strategy": "generative_loose",
                        "cuts": [
                            {
                                "id": "cut-1",
                                "source": "asset-1",
                                "in_seconds": 0,
                                "out_seconds": 1.2,
                                "maps_to_beat": "B3",
                            }
                        ],
                        "audio": {
                            "music": {
                                "volume_schedule": [
                                    {"t_seconds": 0.0, "gain_db": 0.0},
                                    {"t_seconds": 0.3, "gain_db": -11.2},
                                    {"t_seconds": 1.2, "gain_db": -11.2},
                                    {"t_seconds": 1.5, "gain_db": 0.0},
                                ],
                            }
                        },
                    },
                },
                pipeline_type="ad-video",
            )

    def test_ad_video_edit_checkpoint_rejects_unresolved_subtitle_source(self, tmp_path):
        proposal = _minimal_production_proposal()
        proposal["music_strategy"] = "none"

        with pytest.raises(CheckpointValidationError, match="subtitles.source"):
            write_checkpoint(
                tmp_path,
                "proj",
                "edit",
                "completed",
                {
                    "production_proposal": proposal,
                    "scene_plan": ad_video_scene_plan_for_edit(),
                    "asset_manifest": sample_artifact("asset_manifest"),
                    "edit_decisions": {
                        "version": "1.0",
                        "render_runtime": "ffmpeg",
                        "music_strategy": "none",
                        "cuts": [
                            {
                                "id": "cut-1",
                                "source": "asset-1",
                                "in_seconds": 0,
                                "out_seconds": 1.2,
                                "maps_to_beat": "B3",
                            }
                        ],
                        "subtitles": {
                            "enabled": True,
                            "source": "missing-subtitle",
                        },
                    },
                },
                pipeline_type="ad-video",
            )

    def test_ad_video_edit_checkpoint_rejects_runtime_mismatch_to_proposal(self, tmp_path):
        proposal = _minimal_production_proposal()
        proposal["music_strategy"] = "none"

        with pytest.raises(CheckpointValidationError, match="render_runtime"):
            write_checkpoint(
                tmp_path,
                "proj",
                "edit",
                "completed",
                {
                    "production_proposal": proposal,
                    "scene_plan": ad_video_scene_plan_for_edit(),
                    "asset_manifest": sample_artifact("asset_manifest"),
                    "edit_decisions": {
                        "version": "1.0",
                        "render_runtime": "remotion",
                        "music_strategy": "none",
                        "cuts": [
                            {
                                "id": "cut-1",
                                "source": "asset-1",
                                "in_seconds": 0,
                                "out_seconds": 1.2,
                                "maps_to_beat": "B3",
                            }
                        ],
                    },
                },
                pipeline_type="ad-video",
            )

    def test_ad_video_edit_checkpoint_requires_derivative_specs_for_variants(self, tmp_path):
        proposal = _minimal_production_proposal()
        proposal["music_strategy"] = "none"
        proposal["derivatives_added"] = ["9:16"]

        with pytest.raises(CheckpointValidationError, match="derivative_specs"):
            write_checkpoint(
                tmp_path,
                "proj",
                "edit",
                "completed",
                {
                    "production_proposal": proposal,
                    "scene_plan": ad_video_scene_plan_for_edit(),
                    "asset_manifest": sample_artifact("asset_manifest"),
                    "edit_decisions": {
                        "version": "1.0",
                        "render_runtime": "ffmpeg",
                        "music_strategy": "none",
                        "cuts": [
                            {
                                "id": "cut-1",
                                "source": "asset-1",
                                "in_seconds": 0,
                                "out_seconds": 1.2,
                                "maps_to_beat": "B3",
                            }
                        ],
                    },
                },
                pipeline_type="ad-video",
            )

    def test_ad_video_compose_checkpoint_requires_final_review(self, tmp_path):
        with pytest.raises(CheckpointValidationError, match="final_review"):
            write_checkpoint(
                tmp_path,
                "proj",
                "compose",
                "completed",
                {"render_report": ad_video_render_report()},
                pipeline_type="ad-video",
            )

    def test_ad_video_compose_checkpoint_rejects_non_passing_final_review(self, tmp_path):
        with pytest.raises(CheckpointValidationError, match="final_review.status"):
            write_checkpoint(
                tmp_path,
                "proj",
                "compose",
                "completed",
                {
                    "production_proposal": _minimal_production_proposal(),
                    "production_bible": ad_video_production_bible(),
                    "render_report": ad_video_render_report(),
                    "final_review": ad_video_final_review(status="revise"),
                },
                pipeline_type="ad-video",
            )

    def test_ad_video_compose_checkpoint_accepts_passing_final_review(self, tmp_path):
        path = write_checkpoint(
            tmp_path,
            "proj",
            "compose",
            "completed",
            {
                "production_proposal": _minimal_production_proposal(),
                "production_bible": ad_video_production_bible(),
                "render_report": ad_video_render_report(),
                "final_review": ad_video_final_review(),
            },
            pipeline_type="ad-video",
        )

        assert path.exists()

    def test_ad_video_compose_checkpoint_rejects_final_review_not_matching_render_report(
        self, tmp_path
    ):
        final_review = ad_video_final_review()
        final_review["output_path"] = "renders/not-rendered.mp4"

        with pytest.raises(CheckpointValidationError, match="output_path"):
            write_checkpoint(
                tmp_path,
                "proj",
                "compose",
                "completed",
                {
                    "render_report": ad_video_render_report(),
                    "final_review": final_review,
                    "production_proposal": _minimal_production_proposal(),
                    "production_bible": ad_video_production_bible(),
                },
                pipeline_type="ad-video",
            )

    def test_ad_video_compose_checkpoint_rejects_missing_derivative_render(
        self, tmp_path
    ):
        proposal = _minimal_production_proposal()
        proposal["derivatives_added"] = ["9:16"]

        with pytest.raises(CheckpointValidationError, match="derivatives_added"):
            write_checkpoint(
                tmp_path,
                "proj",
                "compose",
                "completed",
                {
                    "production_proposal": proposal,
                    "production_bible": ad_video_production_bible(),
                    "render_report": ad_video_render_report(),
                    "final_review": ad_video_final_review(),
                },
                pipeline_type="ad-video",
            )

    def test_ad_video_publish_checkpoint_requires_final_review(self, tmp_path):
        with pytest.raises(CheckpointValidationError, match="final_review"):
            write_checkpoint(
                tmp_path,
                "proj",
                "publish",
                "completed",
                {"publish_log": ad_video_publish_log()},
                pipeline_type="ad-video",
            )

    def test_ad_video_publish_checkpoint_rejects_non_passing_final_review(self, tmp_path):
        with pytest.raises(CheckpointValidationError, match="final_review.status"):
            write_checkpoint(
                tmp_path,
                "proj",
                "publish",
                "completed",
                {
                    "production_proposal": _minimal_production_proposal(),
                    "production_bible": ad_video_production_bible(),
                    "publish_log": ad_video_publish_log(),
                    "render_report": ad_video_render_report(),
                    "final_review": ad_video_final_review(status="fail"),
                },
                pipeline_type="ad-video",
            )

    def test_ad_video_publish_checkpoint_requires_render_report(self, tmp_path):
        with pytest.raises(CheckpointValidationError, match="render_report"):
            write_checkpoint(
                tmp_path,
                "proj",
                "publish",
                "completed",
                {
                    "production_proposal": _minimal_production_proposal(),
                    "production_bible": ad_video_production_bible(),
                    "publish_log": ad_video_publish_log(),
                    "final_review": ad_video_final_review(),
                },
                pipeline_type="ad-video",
            )

    def test_ad_video_publish_checkpoint_rejects_publish_log_not_matching_render_report(
        self, tmp_path
    ):
        publish_log = ad_video_publish_log()
        publish_log["entries"][0]["export_path"] = "renders/other.mp4"

        with pytest.raises(CheckpointValidationError, match="export_path"):
            write_checkpoint(
                tmp_path,
                "proj",
                "publish",
                "completed",
                {
                    "publish_log": publish_log,
                    "render_report": ad_video_render_report(),
                    "final_review": ad_video_final_review(),
                    "production_proposal": _minimal_production_proposal(),
                    "production_bible": ad_video_production_bible(),
                },
                pipeline_type="ad-video",
            )

    def test_ad_video_publish_checkpoint_rejects_missing_derivative_render(
        self, tmp_path
    ):
        proposal = _minimal_production_proposal()
        proposal["derivatives_added"] = ["9:16"]

        with pytest.raises(CheckpointValidationError, match="derivatives_added"):
            write_checkpoint(
                tmp_path,
                "proj",
                "publish",
                "completed",
                {
                    "publish_log": ad_video_publish_log(),
                    "render_report": ad_video_render_report(),
                    "final_review": ad_video_final_review(),
                    "production_proposal": proposal,
                    "production_bible": ad_video_production_bible(),
                },
                pipeline_type="ad-video",
            )

    def test_invalid_canonical_artifact_rejected(self, tmp_path):
        with pytest.raises(CheckpointValidationError):
            write_checkpoint(
                tmp_path,
                "proj",
                "research",
                "completed",
                {"research_brief": {"topic": "missing schema fields"}},
            )

    def test_missing_canonical_artifact_rejected(self, tmp_path):
        with pytest.raises(CheckpointValidationError):
            write_checkpoint(tmp_path, "proj", "research", "completed", {})

    def test_invalid_status_rejected(self, tmp_path):
        with pytest.raises(CheckpointValidationError):
            write_checkpoint(
                tmp_path,
                "proj",
                "research",
                "mystery",
                {"research_brief": sample_artifact("research_brief")},
            )

    def test_supplementary_video_analysis_brief_is_validated(self, tmp_path):
        write_checkpoint(
            tmp_path,
            "proj",
            "proposal",
            "completed",
            {
                "proposal_packet": sample_artifact("proposal_packet"),
                "video_analysis_brief": sample_artifact("video_analysis_brief"),
            },
        )
        cp = read_checkpoint(tmp_path, "proj", "proposal")
        assert cp is not None
        assert "video_analysis_brief" in cp["artifacts"]


# ---- Pipeline manifests ----

class TestPipelineManifests:
    def test_all_pipeline_manifests_load_through_loader(self):
        failures = {}
        for name in list_pipelines():
            try:
                load_pipeline(name)
            except Exception as exc:  # pragma: no cover - failure path is the assertion payload
                failures[name] = f"{type(exc).__name__}: {exc}"

        assert not failures, (
            "Every manifest in pipeline_defs/ must validate through "
            f"lib.pipeline_loader.load_pipeline(); failures: {failures}"
        )

    def test_framework_smoke_manifest_loads(self):
        manifest = load_pipeline("framework-smoke")
        assert manifest["name"] == "framework-smoke"
        assert get_stage_order(manifest) == ["research", "script"]
        assert get_required_tools(manifest) == set()

    def test_framework_smoke_manifest_listed(self):
        assert "framework-smoke" in list_pipelines()

    def test_reference_sub_stage_helpers(self):
        manifest = load_pipeline("animated-explainer")
        assert pipeline_supports_reference_input(manifest) is True
        assert "video_analyzer" in get_required_tools(manifest)

        all_units = get_stage_order(manifest, include_sub_stages=True)
        assert "proposal.sample" in all_units

        active_sub_stages = get_stage_sub_stages(
            manifest,
            "proposal",
            context={"video_analysis_brief_exists": True},
            include_inactive=False,
        )
        assert any(s["name"] == "sample" for s in active_sub_stages)


# ---- BaseTool ----

class DummyTool(BaseTool):
    name = "dummy"
    version = "0.1.0"
    tier = ToolTier.CORE
    capabilities = ["test"]
    dependencies = []

    def execute(self, inputs):
        return ToolResult(success=True, data={"echo": inputs})


class TestBaseTool:
    def test_get_info(self):
        tool = DummyTool()
        info = tool.get_info()
        assert info["name"] == "dummy"
        assert info["tier"] == "core"
        assert info["status"] == "available"

    def test_execute(self):
        tool = DummyTool()
        result = tool.execute({"msg": "hello"})
        assert result.success

    def test_unavailable_when_deps_missing(self):
        class MissingDepTool(BaseTool):
            name = "missing"
            dependencies = ["cmd:nonexistent_binary_xyz"]
            def execute(self, inputs):
                return ToolResult(success=True)

        tool = MissingDepTool()
        assert tool.get_status() == ToolStatus.UNAVAILABLE


# ---- ToolRegistry ----

class TestToolRegistry:
    def test_register_and_find(self):
        reg = ToolRegistry()
        reg.register(DummyTool())
        assert reg.get("dummy") is not None
        assert "dummy" in reg.list_all()
        assert len(reg.get_by_tier(ToolTier.CORE)) == 1
        assert len(reg.find_by_capability("test")) == 1

    def test_support_envelope(self):
        reg = ToolRegistry()
        reg.register(DummyTool())
        envelope = reg.support_envelope()
        assert "dummy" in envelope
        assert envelope["dummy"]["status"] == "available"

    def test_discovers_concrete_tools_from_package(self, tmp_path, monkeypatch):
        package_dir = tmp_path / "demo_tools"
        package_dir.mkdir()
        (package_dir / "__init__.py").write_text("", encoding="utf-8")
        (package_dir / "demo_tool.py").write_text(
            "\n".join(
                [
                    "from tools.base_tool import BaseTool, ToolResult, ToolTier",
                    "",
                    "class DiscoveredTool(BaseTool):",
                    "    name = 'discovered'",
                    "    tier = ToolTier.CORE",
                    "    capabilities = ['discover']",
                    "    dependencies = []",
                    "",
                    "    def execute(self, inputs):",
                    "        return ToolResult(success=True, data=inputs)",
                    "",
                ]
            ),
            encoding="utf-8",
        )

        monkeypatch.syspath_prepend(str(tmp_path))
        importlib.invalidate_caches()

        reg = ToolRegistry()
        discovered = reg.discover("demo_tools")

        assert discovered == ["discovered"]
        assert reg.get("discovered") is not None
        assert reg.find_by_capability("discover")[0].name == "discovered"


# ---- CostTracker ----

class TestCostTracker:
    def test_estimate_reserve_reconcile(self):
        tracker = CostTracker(budget_total_usd=10.0, mode=BudgetMode.OBSERVE)
        entry_id = tracker.estimate("image_selector", "generate", 0.05)
        tracker.reserve(entry_id)
        assert tracker.budget_reserved_usd == 0.05
        tracker.reconcile(entry_id, 0.04, success=True)
        assert tracker.budget_spent_usd == 0.04
        assert tracker.budget_reserved_usd == 0.0

    def test_cap_mode_blocks_overspend(self):
        tracker = CostTracker(
            budget_total_usd=1.0,
            mode=BudgetMode.CAP,
            single_action_approval_usd=10.0,  # raise threshold so budget check triggers
        )
        tracker.approve_tool("expensive")
        eid = tracker.estimate("expensive", "op", 5.0)
        with pytest.raises(BudgetExceededError):
            tracker.reserve(eid)

    def test_persistence(self, tmp_path):
        log_path = tmp_path / "cost_log.json"
        t1 = CostTracker(budget_total_usd=10.0, mode=BudgetMode.OBSERVE, cost_log_path=log_path)
        eid = t1.estimate("tool", "op", 0.10)
        t1.reserve(eid)
        t1.reconcile(eid, 0.08)

        t2 = CostTracker(cost_log_path=log_path)
        assert t2.budget_spent_usd == 0.08

    def test_reference_estimate_falls_back_when_scene_types_are_unclassified(self):
        tracker = CostTracker(mode=BudgetMode.OBSERVE)
        brief = {
            "source": {"type": "shorts", "duration_seconds": 60},
            "structure_analysis": {
                "total_scenes": 12,
                "pacing_profile": {"pacing_style": "rapid_fire"},
                "scenes": [{"visual_type": "other"} for _ in range(12)],
            },
            "narration_transcript": {"word_count": 180},
            "replication_guidance": {"motion_required": True, "suggested_pipeline": "animation"},
        }
        plan = {
            "video_generation": {"tool": "kling_fal", "cost_per_unit": 0.3, "clip_duration_seconds": 5},
            "image_generation": {"tool": "flux_fal", "cost_per_unit": 0.05},
            "tts": {"tool": "elevenlabs_tts", "cost_per_word": 0.00003},
            "music": {"tool": "music_gen", "cost_per_track": 0.1},
        }

        estimate = tracker.estimate_from_reference(brief, 60, plan)

        assert estimate["motion_ratio"] >= 0.6
        assert estimate["estimated_clips"] >= 7
        assert any(
            "scene visual types have not been enriched yet" in note
            for note in estimate["assumptions"]
        )


# ---- Pipeline Instruction Architecture ----

class TestPipelineInstructionArchitecture:
    """Verify that the instruction-driven architecture is in place:
    manifests reference skills, not Python handlers."""

    def test_animated_explainer_stages_have_skills(self):
        try:
            manifest = load_pipeline("animated-explainer")
        except FileNotFoundError:
            pytest.skip("animated-explainer manifest not yet created")
        for stage in manifest["stages"]:
            assert "skill" in stage, f"Stage {stage['name']} missing skill field"

    def test_stage_skill_lookup(self):
        manifest = load_pipeline("framework-smoke")
        # framework-smoke may not have skills yet — just verify the function works
        result = get_stage_skill(manifest, "idea")
        assert result is None or isinstance(result, str)

    def test_stage_review_focus_lookup(self):
        manifest = load_pipeline("framework-smoke")
        result = get_stage_review_focus(manifest, "idea")
        assert isinstance(result, list)


# ---- Agent context files ----

class TestAgentContextFiles:
    def test_agent_guide_contains_canonical_sections(self):
        contents = (PROJECT_ROOT / "AGENT_GUIDE.md").read_text(encoding="utf-8")
        for header in (
            "## Orchestrator",
            "## Stage Agents",
            "## Reviewer Protocol",
            "## Communication Protocol",
            "## Human Checkpoint Protocol",
        ):
            assert header in contents

    def test_agent_guide_lists_every_pipeline_manifest(self):
        contents = (PROJECT_ROOT / "AGENT_GUIDE.md").read_text(encoding="utf-8")
        manifest_names = {path.stem for path in (PROJECT_ROOT / "pipeline_defs").glob("*.yaml")}
        listed_names = set()
        in_available_table = False
        for line in contents.splitlines():
            if line.strip() == "## Available Pipelines":
                in_available_table = True
                continue
            if in_available_table and line.startswith("## "):
                break
            if in_available_table and line.startswith("| `"):
                listed_names.add(line.split("`", 2)[1])

        assert listed_names >= manifest_names, (
            "AGENT_GUIDE.md Available Pipelines table is missing pipeline "
            f"manifests: {sorted(manifest_names - listed_names)}"
        )

    def test_agent_guide_documents_ad_video_governance_contract(self):
        contents = (PROJECT_ROOT / "AGENT_GUIDE.md").read_text(encoding="utf-8")
        required_fragments = (
            "`ad-video`",
            "intake -> brief_enrichment -> intelligence -> bible -> idea -> proposal -> script -> scene_plan -> assets -> edit -> compose -> publish",
            "production_bible",
            "style_mode",
            "render_runtime",
            "sample approval",
            "asset_review",
            "music_review",
        )
        missing = [fragment for fragment in required_fragments if fragment not in contents]
        assert not missing, (
            "AGENT_GUIDE.md is missing ad-video governance guidance: "
            f"{missing}"
        )

    def test_agent_guide_resume_call_passes_selected_pipeline(self):
        contents = (PROJECT_ROOT / "AGENT_GUIDE.md").read_text(encoding="utf-8")
        assert "get_next_stage(" in contents
        assert "pipeline_type=<selected pipeline>" in contents, (
            "AGENT_GUIDE.md must tell agents to pass pipeline_type when calling "
            "get_next_stage; otherwise manifest-specific pipelines such as "
            "ad-video resume from the legacy fallback stage order."
        )

    def test_gitignore_blocks_root_wan_provider_outputs(self):
        contents = (PROJECT_ROOT / ".gitignore").read_text(encoding="utf-8")
        assert "wanx_*_output.png" in contents, (
            ".gitignore should ignore root-level Wan provider image outputs; "
            "generated media belongs under projects/ or another ignored output path."
        )

    def test_platform_wrappers_reference_agent_guide(self):
        for path in ("CLAUDE.md", "CODEX.md", "CURSOR.md", "COPILOT.md", "AGENTS.md"):
            contents = (PROJECT_ROOT / path).read_text(encoding="utf-8")
            assert "AGENT_GUIDE.md" in contents


# ---- Media Profiles ----

class TestMediaProfiles:
    def test_all_profiles_exist(self):
        assert len(ALL_PROFILES) >= 9

    def test_get_profile(self):
        p = get_profile("youtube_landscape")
        assert p.width == 1920
        assert p.height == 1080

    def test_ffmpeg_args(self):
        args = ffmpeg_output_args(get_profile("tiktok"))
        assert "-c:v" in args
        assert "1080" in args[-1]

    def test_unknown_profile_raises(self):
        with pytest.raises(ValueError):
            get_profile("nonexistent")
