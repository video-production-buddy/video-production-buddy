"""Shared fixtures for ad-video contract alignment tests."""

from __future__ import annotations

import json
import re
from copy import deepcopy
from pathlib import Path

import yaml


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


def _stage_tool_names(stage: dict) -> set[str]:
    tools: set[str] = set()
    for key in ("required_tools", "optional_tools", "preferred_tools", "fallback_tools", "tools_available"):
        tools.update(stage.get(key, []))
    return tools


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
            "visual_asset_provider_locks": [
                {
                    "asset_type": "image",
                    "source_tool": "wanx_image",
                    "model": "wan2.7-image-pro",
                    "usage": "packshots and still cards",
                },
                {
                    "asset_type": "video",
                    "source_tool": "wan_video_api",
                    "model": "wan2.6-t2v",
                    "usage": "generated product and lifestyle motion scenes",
                },
                {
                    "asset_type": "video",
                    "source_tool": "pexels_video",
                    "usage": "stock establishing shots",
                },
            ],
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

def _trend_threaded_script(source_ref: str = "trend_alignment:trend-tiktok-lofi-hook") -> dict:
    voice_performance = {
        "emotion": "intrigue",
        "intonation": "soft rise, clean resolve",
        "rhythm": "short phrase, breath, proof phrase",
        "pace": "measured",
        "pause_after_seconds": 0.25,
    }
    tts_directive = {"speed_mult": 0.96}
    return {
        "version": "1.0",
        "title": "Trend Threaded Script",
        "total_duration_seconds": 8,
        "user_approved": True,
        "sections": [
            {
                "id": "hook",
                "beat": "hook",
                "text": "Three seconds decide the scroll.",
                "start_seconds": 0,
                "end_seconds": 3,
                "source_ref": source_ref,
                "source_refs": [
                    source_ref,
                    "knowledge_alignment:hook.visual-contrast.001",
                ],
                "speaker_directions": "Measured and immediate.",
                "voice_performance": voice_performance,
                "tts_directive": tts_directive,
            },
            {
                "id": "build",
                "beat": "build",
                "text": "Then prove the change before attention drops.",
                "start_seconds": 3,
                "end_seconds": 8,
                "source_ref": source_ref,
                "speaker_directions": "Confident proof, no hype.",
                "voice_performance": voice_performance,
                "tts_directive": tts_directive,
            },
        ],
    }


def _trend_threaded_scene_plan(source_ref: str = "trend_alignment:trend-tiktok-lofi-hook") -> dict:
    return {
        "version": "1.0",
        "style_mode": "animated",
        "total_duration_seconds": 4,
        "scenes": [
            {
                "id": "scene-hook",
                "type": "generated",
                "scene_type": "text_card",
                "description": "Native overlay text lands on the first visual beat.",
                "start_seconds": 0,
                "end_seconds": 4,
                "beat": "hook",
                "product_visibility": "none",
                "product_reference_required": False,
                "core": True,
                "motion_required": True,
                "trend_alignment_refs": [source_ref],
                "trend_alignment_notes": "Warm native pacing is adapted without copying source captions, audio, or shot order.",
                "knowledge_alignment_refs": ["knowledge_alignment:hook.visual-contrast.001"],
                "knowledge_alignment_notes": "Opening scene uses a visible before/after contrast without turning into clickbait.",
            }
        ],
    }


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
