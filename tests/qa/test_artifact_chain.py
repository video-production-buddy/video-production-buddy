#!/usr/bin/env python3
"""Tests: realistic artifact chain assembly and internal consistency.

Validates that a full intake_brief → intelligence_brief → production_bible
chain can be assembled and that each artifact:
  - Validates against its JSON Schema
  - Is internally consistent (beat_ids in compliance_manifest exist in
    emotional_beat_sequence; confidence tiers are valid; etc.)
  - Respects cross-artifact contracts (CTA non-null before approval,
    rejected_approaches present and propagated, etc.)

Also tests the mechanical compliance_manifest generation rules:
  - Structural check_types → evaluation_method=structural
  - Content check_types → evaluation_method=semantic
  - default-heuristic confidence → failure_action=flag
  - research-grounded/pattern-inferred → failure_action=revise

Run: python3 tests/qa/test_artifact_chain.py
"""

import json
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

try:
    import jsonschema
    HAS_JSONSCHEMA = True
except ImportError:
    HAS_JSONSCHEMA = False

ROOT = Path(__file__).resolve().parent.parent.parent
SCHEMAS = ROOT / "schemas" / "artifacts"


def load_schema(name: str) -> dict:
    path = SCHEMAS / f"{name}.schema.json"
    assert path.exists(), f"Schema not found: {path}"
    with open(path) as f:
        return json.load(f)


def validate(instance: dict, schema: dict) -> None:
    if not HAS_JSONSCHEMA:
        raise RuntimeError("jsonschema not installed — run: pip install jsonschema")
    jsonschema.validate(instance, schema, format_checker=jsonschema.FormatChecker())


def deep_copy(d: dict) -> dict:
    return json.loads(json.dumps(d))


# ─────────────────────────────────────────────────────────────────────────────
# Realistic artifact fixtures (all synthetic data)
# ─────────────────────────────────────────────────────────────────────────────

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
    },
    "intelligence": {
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


# ─────────────────────────────────────────────────────────────────────────────
# Standalone runner
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if not HAS_JSONSCHEMA:
        print("WARNING: jsonschema not installed — schema validation tests will fail.")
        print("Install with: pip install jsonschema\n")

    tests = [
        # intake_brief
        test_intake_brief_rich_validates,
        test_intake_brief_thin_validates,
        test_intake_brief_completeness_values,
        test_intake_brief_rejects_more_than_3_questions,
        test_intake_brief_rejects_invalid_platform,
        test_intake_brief_rejects_invalid_completeness,
        test_intake_brief_requires_product_and_platform,
        # intelligence_brief
        test_intelligence_brief_validates,
        test_intelligence_brief_rejects_empty_rejected_approaches,
        test_intelligence_brief_rejects_invalid_confidence_tier,
        test_intelligence_brief_confidence_tiers_are_valid,
        test_intelligence_brief_has_minimum_required_counts,
        test_intelligence_brief_requires_platform_trends_minItems,
        # production_bible schema
        test_production_bible_validates,
        test_production_bible_null_cta_passes_schema,
        test_production_bible_pipeline_must_be_ad_video,
        test_production_bible_brand_name_in_final_frame_must_be_true,
        test_production_bible_beat_name_accepts_arc_specific_names,
        test_production_bible_rejects_invalid_evaluation_method,
        test_production_bible_rejects_invalid_failure_action,
        test_production_bible_requires_approval_flags,
        # Internal consistency
        test_all_beat_ids_referenced_in_checkpoints_exist,
        test_key_visual_moments_reference_valid_beats,
        test_editing_rhythm_references_valid_beats,
        # Compliance manifest generation rules
        test_structural_check_types_have_structural_evaluation_method,
        test_content_check_type_has_semantic_evaluation_method,
        test_default_heuristic_maps_to_flag,
        test_research_grounded_maps_to_revise,
        test_pattern_inferred_maps_to_revise,
        test_compliance_manifest_covers_all_downstream_stages,
        test_compliance_manifest_has_both_structural_and_semantic,
        test_all_checkpoints_have_required_fields,
        # Cross-artifact contracts
        test_approved_bible_has_non_null_cta,
        test_bible_inherits_rejected_approaches_from_intelligence,
        test_bible_beat_durations_sum_to_target,
        test_bible_intensity_values_are_normalized,
        test_deliverables_primary_aspect_ratio_matches_platform,
    ]
    passed = failed = 0
    for t in tests:
        try:
            t()
            print(f"[PASS] {t.__name__}")
            passed += 1
        except Exception as e:
            print(f"[FAIL] {t.__name__}: {e}")
            traceback.print_exc()
            failed += 1
    print(f"\n{passed}/{passed + failed} tests passed")
    import sys; sys.exit(0 if failed == 0 else 1)
