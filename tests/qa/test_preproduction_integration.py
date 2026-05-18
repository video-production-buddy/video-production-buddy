#!/usr/bin/env python3
"""Integration tests: ComplianceCheck against realistic production_bible + stage outputs.

Tests the full compliance workflow for all checkpoint families:
  CP-S*  — script timing and content checks
  CP-V*  — scene_plan motif presence and beat mapping
  CP-E*  — edit editing-rhythm (confidence tier → failure_action propagation)
  CP-B*  — brand constraints (presence positive and negated)

Tests both passing and failing scenarios using realistic artifact shapes
that mirror actual pipeline data.

Run: python3 tests/qa/test_preproduction_integration.py
"""

import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from tools.compliance.compliance_check import ComplianceCheck

tool = ComplianceCheck()

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def words(n: int) -> str:
    """Return a string of n space-separated 'word' tokens."""
    return " ".join(["word"] * n)


# Word-count calibration at 150 WPM:
#   duration_seconds = word_count / 150 * 60
#   word_count = duration_seconds * 150 / 60 = duration_seconds * 2.5
#   ±10% tolerance means actual must be within 90–110% of target
#
# Beat targets for the 30s problem-solution arc:
#   B1 hook       4s  → 10 words  → 4.0s
#   B2 problem    7s  → 17 words  → 6.8s  (within [6.3, 7.7])
#   B3 solution   8s  → 20 words  → 8.0s
#   B4 resolution 6s  → 15 words  → 6.0s
#   B5 cta        5s  → 12 words  → 4.8s  (within [4.5, 5.5])


# ─────────────────────────────────────────────────────────────────────────────
# Realistic production_bible fixture (30s TikTok, problem-solution arc)
# ─────────────────────────────────────────────────────────────────────────────

REALISTIC_BIBLE = {
    "version": "1.0",
    "pipeline": "ad-video",
    "project_id": "acme-productivity-tiktok-30s",
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
            "core_pain_point": "feel productive but aren't",
            "aspiration": "reclaim control of the day",
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
            {
                "beat_id": "B1", "name": "hook",
                "duration_seconds": 4, "emotional_target": "curiosity", "intensity": 0.8,
                "script_constraint": "Open with the core pain — no brand intro",
                "visual_constraint": "Clock imagery conveying time pressure",
            },
            {
                "beat_id": "B2", "name": "problem",
                "duration_seconds": 7, "emotional_target": "recognition", "intensity": 0.6,
                "script_constraint": "Name the problem: tasks pile up, hours vanish",
                "visual_constraint": "Overwhelmed desk scene or notification avalanche",
            },
            {
                "beat_id": "B3", "name": "solution_intro",
                "duration_seconds": 8, "emotional_target": "hope", "intensity": 0.9,
                "script_constraint": "Introduce Acme — confident, specific",
                "visual_constraint": "Clean Acme app interface reveal",
            },
            {
                "beat_id": "B4", "name": "resolution",
                "duration_seconds": 6, "emotional_target": "aspiration", "intensity": 0.7,
                "script_constraint": "Paint the after: calm, two hours reclaimed",
                "visual_constraint": "Person in control, peaceful workspace",
            },
            {
                "beat_id": "B5", "name": "cta",
                "duration_seconds": 5, "emotional_target": "action", "intensity": 0.5,
                "script_constraint": "Deliver 'Try free at acme.com' with confidence",
                "visual_constraint": "Acme logo + CTA text on screen",
            },
        ],
    },
    "intelligence": {
        "trending_signals": [
            {"signal": "lo-fi aesthetic +34% on TikTok", "source": "Sprout Social 2026", "applied_to": "visual.color_direction"},
        ],
        "reference_ads_analyzed": [
            {"title": "Monday.com Pain-First", "platform": "youtube", "what_works": "Pain-first hook, product at 60%", "adopted": True, "adaptation": "Compress to 30s"},
        ],
        "rejected_approaches": [
            {"approach": "celebrity endorsement", "reason": "oversaturated in productivity category"},
            {"approach": "generic work-smarter tagline", "reason": "used by 7/10 competitors"},
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
            {"maps_to_beat": "B1", "cuts_density": "rapid", "avg_shot_duration_seconds": 1.5, "transition_style": "hard_cut", "confidence": "pattern-inferred"},
            {"maps_to_beat": "B2", "cuts_density": "moderate", "avg_shot_duration_seconds": 3.0, "transition_style": "hard_cut", "confidence": "default-heuristic"},
            {"maps_to_beat": "B3", "cuts_density": "slow", "avg_shot_duration_seconds": 4.5, "transition_style": "match_cut", "confidence": "pattern-inferred"},
            {"maps_to_beat": "B4", "cuts_density": "held", "avg_shot_duration_seconds": 6.0, "transition_style": "dissolve", "confidence": "default-heuristic"},
            {"maps_to_beat": "B5", "cuts_density": "held", "avg_shot_duration_seconds": 5.0, "transition_style": "hard_cut", "confidence": "research-grounded"},
        ],
    },
    "audio": {
        "voice_character": {"tone": "warm and direct", "pacing": "energetic", "persona": "trusted peer"},
        "music_direction": {"mood": "focused optimism", "tempo": "medium", "genre_direction": "lo-fi indie", "arc": "sparse at hook, full at solution_intro"},
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
            # ── Script timing (structural) ─────────────────────────────────
            {
                "id": "CP-S1", "applies_to_stage": "script", "description": "B1 hook timing",
                "check_type": "timing", "evaluation_method": "structural",
                "criterion": "Section covering beat B1 (hook) must be within ±10% of 4s",
                "source_confidence": "research-grounded", "failure_action": "revise",
            },
            {
                "id": "CP-S2", "applies_to_stage": "script", "description": "B2 problem timing",
                "check_type": "timing", "evaluation_method": "structural",
                "criterion": "Section covering beat B2 (problem) must be within ±10% of 7s",
                "source_confidence": "research-grounded", "failure_action": "revise",
            },
            {
                "id": "CP-S3", "applies_to_stage": "script", "description": "B5 CTA timing",
                "check_type": "timing", "evaluation_method": "structural",
                "criterion": "Section covering beat B5 (cta) must be within ±10% of 5s",
                "source_confidence": "research-grounded", "failure_action": "revise",
            },
            # ── Script content (semantic — tool must reject) ───────────────
            {
                "id": "CP-S1a", "applies_to_stage": "script", "description": "B1 achieves curiosity",
                "check_type": "content", "evaluation_method": "semantic",
                "criterion": "Section must achieve emotional_target='curiosity'. Open with pain, no brand intro.",
                "source_confidence": "research-grounded", "failure_action": "revise",
            },
            # ── Script prohibited elements (structural, negated) ───────────
            {
                "id": "CP-B3", "applies_to_stage": "script", "description": "Prohibited terms absent",
                "check_type": "presence", "evaluation_method": "structural",
                "criterion": "prohibited_elements ['competitor', 'monday.com', 'notion'] must not appear in any script section",
                "source_confidence": "research-grounded", "failure_action": "revise",
            },
            # ── Scene plan motif presence (structural) ────────────────────
            {
                "id": "CP-V1", "applies_to_stage": "scene_plan", "description": "Clock imagery ≥2 scenes",
                "check_type": "presence", "evaluation_method": "structural",
                "criterion": "'clock imagery' must appear in ≥2 scenes",
                "source_confidence": "research-grounded", "failure_action": "revise",
            },
            {
                "id": "CP-V2", "applies_to_stage": "scene_plan", "description": "Notification avalanche ≥1 scene",
                "check_type": "presence", "evaluation_method": "structural",
                "criterion": "'notification avalanche' must appear in ≥1 scenes",
                "source_confidence": "research-grounded", "failure_action": "revise",
            },
            # ── Scene plan beat mapping (structural) ──────────────────────
            {
                "id": "CP-V3", "applies_to_stage": "scene_plan", "description": "App reveal mapped to B3",
                "check_type": "structural", "evaluation_method": "structural",
                "criterion": "A scene for 'Acme app interface reveal' must be present, mapped to beat B3",
                "source_confidence": "research-grounded", "failure_action": "revise",
            },
            {
                "id": "CP-V4", "applies_to_stage": "scene_plan", "description": "Logo+CTA mapped to B5",
                "check_type": "structural", "evaluation_method": "structural",
                "criterion": "A scene for 'Acme logo + CTA text' must be present, mapped to beat B5",
                "source_confidence": "research-grounded", "failure_action": "revise",
            },
            # ── Scene plan brand (structural, positive) ───────────────────
            {
                "id": "CP-B1", "applies_to_stage": "scene_plan", "description": "Brand in final scene",
                "check_type": "presence", "evaluation_method": "structural",
                "criterion": "brand_name 'Acme' must appear in final scene (last 5s)",
                "source_confidence": "research-grounded", "failure_action": "revise",
            },
            # ── Asset manifest mandatory elements (flag-level) ────────────
            {
                "id": "CP-B2", "applies_to_stage": "assets", "description": "Mandatory elements in manifest",
                "check_type": "presence", "evaluation_method": "structural",
                "criterion": "mandatory_elements ['Acme logo', 'acme.com'] must each appear in asset_manifest",
                "source_confidence": "research-grounded", "failure_action": "flag",
            },
            # ── Edit rhythm: pattern-inferred → revise ────────────────────
            {
                "id": "CP-E1", "applies_to_stage": "edit", "description": "B1 hook pacing",
                "check_type": "timing", "evaluation_method": "structural",
                "criterion": "Scenes in beat B1: cuts_density=rapid, avg_shot≈1.5s, transition=hard_cut",
                "source_confidence": "pattern-inferred", "failure_action": "revise",
            },
            # ── Edit rhythm: default-heuristic → flag ─────────────────────
            {
                "id": "CP-E2", "applies_to_stage": "edit", "description": "B4 resolution pacing (heuristic)",
                "check_type": "timing", "evaluation_method": "structural",
                "criterion": "Scenes in beat B4: cuts_density=held, avg_shot≈6.0s, transition=dissolve",
                "source_confidence": "default-heuristic", "failure_action": "flag",
            },
        ],
    },
}


def get_cp(cp_id: str) -> dict:
    for cp in REALISTIC_BIBLE["compliance_manifest"]["checkpoints"]:
        if cp["id"] == cp_id:
            return cp
    raise KeyError(f"Checkpoint {cp_id} not found in fixture")


# ─────────────────────────────────────────────────────────────────────────────
# Realistic stage output fixtures
# ─────────────────────────────────────────────────────────────────────────────

SCRIPT_PASSING = {
    "sections": [
        {"beat_id": "B1", "narration": words(10)},   # 4.0s — within ±10% of 4s
        {"beat_id": "B2", "narration": words(17)},   # 6.8s — within [6.3, 7.7]
        {"beat_id": "B3", "narration": words(20)},   # 8.0s — exact
        {"beat_id": "B4", "narration": words(15)},   # 6.0s — exact
        {"beat_id": "B5", "narration": words(12)},   # 4.8s — within [4.5, 5.5]
    ]
}

SCRIPT_FAILING_TIMING = {
    "sections": [
        {"beat_id": "B1", "narration": words(40)},   # 16s — far over 4s target → FAIL CP-S1
        {"beat_id": "B2", "narration": words(17)},
        {"beat_id": "B3", "narration": words(20)},
        {"beat_id": "B4", "narration": words(15)},
        {"beat_id": "B5", "narration": words(12)},
    ]
}

SCRIPT_WITH_PROHIBITED = {
    "sections": [
        {"beat_id": "B1", "narration": "You lose two hours every day."},
        {"beat_id": "B2", "narration": "Unlike competitor apps, we actually work."},  # 'competitor' ← prohibited
        {"beat_id": "B3", "narration": words(20)},
        {"beat_id": "B4", "narration": words(15)},
        {"beat_id": "B5", "narration": "Try free at acme.com"},
    ]
}

SCENE_PLAN_PASSING = {
    "scenes": [
        {"id": "SC1", "maps_to_beat": "B1", "description": "clock imagery ticking down, close-up"},
        {"id": "SC2", "maps_to_beat": "B1", "description": "clock imagery on wall above overwhelmed desk"},
        {"id": "SC3", "maps_to_beat": "B2", "description": "notification avalanche flooding the screen"},
        {"id": "SC4", "maps_to_beat": "B3", "description": "Acme app interface reveal — full-screen clean UI"},
        {"id": "SC5", "maps_to_beat": "B4", "description": "person in calm productive workspace"},
        {"id": "SC6", "maps_to_beat": "B5", "description": "Acme logo + CTA text: Try free at acme.com"},
    ]
}

SCENE_PLAN_MISSING_CLOCK = {
    "scenes": [
        {"id": "SC1", "maps_to_beat": "B1", "description": "clock imagery ticking down"},
        # Only 1 clock imagery scene — need ≥2 → CP-V1 FAIL
        {"id": "SC2", "maps_to_beat": "B2", "description": "notification avalanche screen"},
        {"id": "SC3", "maps_to_beat": "B3", "description": "Acme app interface reveal — full-screen clean UI"},
        {"id": "SC4", "maps_to_beat": "B4", "description": "peaceful workspace"},
        {"id": "SC5", "maps_to_beat": "B5", "description": "Acme logo + CTA text"},
    ]
}

SCENE_PLAN_NO_NOTIFICATION = {
    "scenes": [
        {"id": "SC1", "maps_to_beat": "B1", "description": "clock imagery ticking"},
        {"id": "SC2", "maps_to_beat": "B1", "description": "clock imagery alarm"},
        # Description deliberately avoids 'notification avalanche' — generic scene instead
        {"id": "SC3", "maps_to_beat": "B2", "description": "generic overwhelmed office desk"},
        {"id": "SC4", "maps_to_beat": "B3", "description": "Acme app interface reveal — full-screen clean UI"},
        {"id": "SC5", "maps_to_beat": "B4", "description": "peaceful workspace"},
        {"id": "SC6", "maps_to_beat": "B5", "description": "Acme logo + CTA text"},
    ]
}

SCENE_PLAN_NO_BRAND_IN_FINAL = {
    # v1 known limitation: CP-B1 searches full serialized output, not just the final scene.
    # To test that the check FAILS, the brand name must be absent from ALL scene descriptions.
    # Real enforcement of "final scene only" requires a v2 structured criterion format.
    "scenes": [
        {"id": "SC1", "maps_to_beat": "B1", "description": "clock imagery ticking"},
        {"id": "SC2", "maps_to_beat": "B1", "description": "clock imagery alarm"},
        {"id": "SC3", "maps_to_beat": "B2", "description": "notification avalanche"},
        # SC4 uses 'App' not 'Acme' — brand name deliberately absent from all descriptions
        {"id": "SC4", "maps_to_beat": "B3", "description": "app interface reveal — full-screen clean UI"},
        {"id": "SC5", "maps_to_beat": "B4", "description": "peaceful workspace"},
        {"id": "SC6", "maps_to_beat": "B5", "description": "white screen with CTA text"},
    ]
}

SCENE_PLAN_NO_B3_SCENE = {
    "scenes": [
        {"id": "SC1", "maps_to_beat": "B1", "description": "clock imagery ticking"},
        {"id": "SC2", "maps_to_beat": "B1", "description": "clock imagery alarm"},
        {"id": "SC3", "maps_to_beat": "B2", "description": "notification avalanche"},
        # No scene mapped to B3 → CP-V3 FAIL
        {"id": "SC4", "maps_to_beat": "B4", "description": "peaceful workspace"},
        {"id": "SC5", "maps_to_beat": "B5", "description": "Acme logo + CTA text"},
    ]
}

ASSET_MANIFEST_PASSING = {
    "assets": [
        {"type": "tts", "path": "audio/narration.mp3"},
        {"type": "image", "path": "images/acme_logo.png", "description": "Acme logo brand asset"},
        {"type": "image", "path": "images/cta_card.png", "description": "acme.com CTA card"},
        {"type": "music", "path": "music/lofi_track.mp3"},
    ]
}

ASSET_MANIFEST_MISSING_ELEMENTS = {
    "assets": [
        {"type": "tts", "path": "audio/narration.mp3"},
        {"type": "music", "path": "music/track.mp3"},
        # No 'Acme logo' or 'acme.com' → CP-B2 should flag (not revise)
    ]
}

# ─────────────────────────────────────────────────────────────────────────────
# CP-S* Script timing tests
# ─────────────────────────────────────────────────────────────────────────────

def test_script_B1_timing_passes():
    """CP-S1: 10 words = 4.0s, target 4s ±10% [3.6, 4.4] → PASS."""
    r = tool.execute({"stage_output": SCRIPT_PASSING, "checkpoint": get_cp("CP-S1")})
    assert r.success and r.data["pass"] is True, f"{r.data}"


def test_script_B2_timing_passes():
    """CP-S2: 17 words = 6.8s, target 7s ±10% [6.3, 7.7] → PASS."""
    r = tool.execute({"stage_output": SCRIPT_PASSING, "checkpoint": get_cp("CP-S2")})
    assert r.success and r.data["pass"] is True, f"{r.data}"


def test_script_B5_timing_passes():
    """CP-S3: 12 words = 4.8s, target 5s ±10% [4.5, 5.5] → PASS."""
    r = tool.execute({"stage_output": SCRIPT_PASSING, "checkpoint": get_cp("CP-S3")})
    assert r.success and r.data["pass"] is True, f"{r.data}"


def test_script_B1_timing_fails_too_long():
    """CP-S1: 40 words = 16s vs target 4s → FAIL, failure_action=revise."""
    r = tool.execute({"stage_output": SCRIPT_FAILING_TIMING, "checkpoint": get_cp("CP-S1")})
    assert r.success and r.data["pass"] is False
    assert r.data["failure_action"] == "revise"
    assert r.data["deviation"] is not None


def test_script_timing_ignores_other_beats():
    """CP-S1 only counts sections with beat_id==B1, ignoring B2-B5."""
    # B2 has 100 words (40s) but CP-S1 only measures B1 (10 words = 4.0s)
    mixed = {
        "sections": [
            {"beat_id": "B1", "narration": words(10)},
            {"beat_id": "B2", "narration": words(100)},
        ]
    }
    r = tool.execute({"stage_output": mixed, "checkpoint": get_cp("CP-S1")})
    assert r.success and r.data["pass"] is True, "B2 should be ignored for CP-S1"


def test_script_timing_sums_split_sections():
    """Word counts are summed when a beat spans multiple sections."""
    split = {
        "sections": [
            {"beat_id": "B1", "narration": words(5)},   # 2.0s
            {"beat_id": "B1", "narration": words(5)},   # 2.0s  → total 4.0s ✓
        ]
    }
    r = tool.execute({"stage_output": split, "checkpoint": get_cp("CP-S1")})
    assert r.success and r.data["pass"] is True


def test_script_timing_works_with_maps_to_beat():
    """Timing check works when section uses maps_to_beat instead of beat_id."""
    alt = {"sections": [{"maps_to_beat": "B1", "narration": words(10)}]}
    r = tool.execute({"stage_output": alt, "checkpoint": get_cp("CP-S1")})
    assert r.success and r.data["pass"] is True


def test_structured_timing_works_with_beat_alias():
    """Structured timing accepts the ad-video script schema's beat field."""
    checkpoint = {
        "id": "CP-STRUCT-TIME",
        "evaluation_method": "structural",
        "structured": {"kind": "timing", "beat_id": "hook", "target_seconds": 4},
    }
    stage_output = {"sections": [{"beat": "hook", "narration": words(10)}]}
    r = tool.execute({"stage_output": stage_output, "checkpoint": checkpoint})
    assert r.success and r.data["pass"] is True


def test_script_timing_empty_sections_fails():
    """No sections for a beat → 0 words → 0s → FAIL."""
    r = tool.execute({"stage_output": {"sections": []}, "checkpoint": get_cp("CP-S1")})
    assert r.success and r.data["pass"] is False


def test_script_semantic_cp_rejected():
    """CP-S1a has evaluation_method=semantic → tool returns success=False."""
    cp = get_cp("CP-S1a")
    assert cp["evaluation_method"] == "semantic"
    r = tool.execute({"stage_output": SCRIPT_PASSING, "checkpoint": cp})
    assert r.success is False and "structural" in r.error.lower()


# ─────────────────────────────────────────────────────────────────────────────
# CP-B3 Script prohibited elements (negated presence, structural)
# ─────────────────────────────────────────────────────────────────────────────

def test_script_prohibited_elements_clean():
    """CP-B3: no prohibited terms in script → PASS."""
    r = tool.execute({"stage_output": SCRIPT_PASSING, "checkpoint": get_cp("CP-B3")})
    assert r.success and r.data["pass"] is True


def test_script_prohibited_element_found():
    """CP-B3: 'competitor' in script narration → FAIL, failure_action=revise."""
    r = tool.execute({"stage_output": SCRIPT_WITH_PROHIBITED, "checkpoint": get_cp("CP-B3")})
    assert r.success and r.data["pass"] is False
    assert r.data["failure_action"] == "revise"
    assert r.data["deviation"] is not None


def test_script_prohibited_case_insensitive():
    """Prohibited check is case-insensitive: 'COMPETITOR' is still caught."""
    script_caps = {"sections": [{"beat_id": "B1", "narration": "COMPETITOR apps are worse."}]}
    r = tool.execute({"stage_output": script_caps, "checkpoint": get_cp("CP-B3")})
    assert r.success and r.data["pass"] is False


def test_script_prohibited_partial_match():
    """'competitor' in a longer phrase is still detected."""
    script_partial = {"sections": [{"beat_id": "B1", "narration": "All competitor solutions failed."}]}
    r = tool.execute({"stage_output": script_partial, "checkpoint": get_cp("CP-B3")})
    assert r.success and r.data["pass"] is False


# ─────────────────────────────────────────────────────────────────────────────
# CP-V* Scene plan motif presence
# ─────────────────────────────────────────────────────────────────────────────

def test_scene_clock_imagery_passes_count():
    """CP-V1: 'clock imagery' in 2 scenes, needs ≥2 → PASS."""
    r = tool.execute({"stage_output": SCENE_PLAN_PASSING, "checkpoint": get_cp("CP-V1")})
    assert r.success and r.data["pass"] is True


def test_scene_clock_imagery_fails_count():
    """CP-V1: only 1 'clock imagery' scene instead of ≥2 → FAIL."""
    r = tool.execute({"stage_output": SCENE_PLAN_MISSING_CLOCK, "checkpoint": get_cp("CP-V1")})
    assert r.success and r.data["pass"] is False
    assert r.data["failure_action"] == "revise"


def test_scene_notification_avalanche_passes():
    """CP-V2: 'notification avalanche' in 1 scene, needs ≥1 → PASS."""
    r = tool.execute({"stage_output": SCENE_PLAN_PASSING, "checkpoint": get_cp("CP-V2")})
    assert r.success and r.data["pass"] is True


def test_scene_notification_avalanche_absent():
    """CP-V2: no 'notification avalanche' scene → FAIL."""
    r = tool.execute({"stage_output": SCENE_PLAN_NO_NOTIFICATION, "checkpoint": get_cp("CP-V2")})
    assert r.success and r.data["pass"] is False


# ─────────────────────────────────────────────────────────────────────────────
# CP-V* Scene plan beat mapping (structural)
# ─────────────────────────────────────────────────────────────────────────────

def test_scene_app_reveal_mapped_to_B3_passes():
    """CP-V3: scene mapped to B3 present → PASS."""
    r = tool.execute({"stage_output": SCENE_PLAN_PASSING, "checkpoint": get_cp("CP-V3")})
    assert r.success and r.data["pass"] is True


def test_scene_logo_cta_mapped_to_B5_passes():
    """CP-V4: scene mapped to B5 present → PASS."""
    r = tool.execute({"stage_output": SCENE_PLAN_PASSING, "checkpoint": get_cp("CP-V4")})
    assert r.success and r.data["pass"] is True


def test_structured_beat_mapping_works_with_beat_alias():
    """Structured beat mapping accepts the ad-video scene schema's beat field."""
    checkpoint = {
        "id": "CP-STRUCT-BEAT",
        "evaluation_method": "structural",
        "structured": {"kind": "beat_mapping", "beat_id": "reveal"},
    }
    stage_output = {"scenes": [{"id": "scene-1", "beat": "reveal"}]}
    r = tool.execute({"stage_output": stage_output, "checkpoint": checkpoint})
    assert r.success and r.data["pass"] is True


def test_scene_app_reveal_missing_from_B3():
    """CP-V3: no scene mapped to beat B3 → FAIL."""
    r = tool.execute({"stage_output": SCENE_PLAN_NO_B3_SCENE, "checkpoint": get_cp("CP-V3")})
    assert r.success and r.data["pass"] is False


def test_scene_beat_mapping_wrong_beat():
    """CP-V3: app reveal exists but mapped to wrong beat → FAIL."""
    wrong_beat = {
        "scenes": [
            {"id": "SC1", "maps_to_beat": "B1", "description": "clock imagery"},
            {"id": "SC2", "maps_to_beat": "B1", "description": "clock imagery"},
            {"id": "SC3", "maps_to_beat": "B2", "description": "notification avalanche"},
            {"id": "SC4", "maps_to_beat": "B4", "description": "Acme app interface reveal — mapped to B4 not B3"},
            {"id": "SC5", "maps_to_beat": "B5", "description": "Acme logo + CTA text"},
        ]
    }
    r = tool.execute({"stage_output": wrong_beat, "checkpoint": get_cp("CP-V3")})
    assert r.success and r.data["pass"] is False, "Beat B3 has no scene; wrong beat should fail"


# ─────────────────────────────────────────────────────────────────────────────
# CP-B1 Brand name in final scene (structural, positive presence)
# ─────────────────────────────────────────────────────────────────────────────

def test_scene_brand_in_final_scene_passes():
    """CP-B1: 'Acme' present in scene plan → PASS."""
    r = tool.execute({"stage_output": SCENE_PLAN_PASSING, "checkpoint": get_cp("CP-B1")})
    assert r.success and r.data["pass"] is True


def test_scene_brand_missing_from_all_scenes():
    """CP-B1: no 'Acme' in any scene description → FAIL, failure_action=revise."""
    r = tool.execute({"stage_output": SCENE_PLAN_NO_BRAND_IN_FINAL, "checkpoint": get_cp("CP-B1")})
    assert r.success and r.data["pass"] is False
    assert r.data["failure_action"] == "revise"


# ─────────────────────────────────────────────────────────────────────────────
# CP-B2 Asset manifest mandatory elements (flag-level)
# ─────────────────────────────────────────────────────────────────────────────

def test_asset_manifest_mandatory_elements_pass():
    """CP-B2: 'Acme logo' and 'acme.com' in manifest → PASS."""
    r = tool.execute({"stage_output": ASSET_MANIFEST_PASSING, "checkpoint": get_cp("CP-B2")})
    assert r.success and r.data["pass"] is True


def test_asset_manifest_missing_mandatory_elements():
    """CP-B2: mandatory elements absent → FAIL, but failure_action=flag (not revise)."""
    r = tool.execute({"stage_output": ASSET_MANIFEST_MISSING_ELEMENTS, "checkpoint": get_cp("CP-B2")})
    assert r.success and r.data["pass"] is False
    assert r.data["failure_action"] == "flag", "CP-B2 is flag-level, not revise"


# ─────────────────────────────────────────────────────────────────────────────
# CP-E* Edit rhythm — confidence tier → failure_action propagation
# ─────────────────────────────────────────────────────────────────────────────

def test_edit_pattern_inferred_is_revise_level():
    """CP-E1 source_confidence=pattern-inferred → failure_action=revise."""
    cp = get_cp("CP-E1")
    assert cp["source_confidence"] == "pattern-inferred"
    assert cp["failure_action"] == "revise"
    r = tool.execute({"stage_output": {"cuts": []}, "checkpoint": cp})
    assert r.success and r.data["failure_action"] == "revise"


def test_edit_default_heuristic_is_flag_level():
    """CP-E2 source_confidence=default-heuristic → failure_action=flag."""
    cp = get_cp("CP-E2")
    assert cp["source_confidence"] == "default-heuristic"
    assert cp["failure_action"] == "flag"
    r = tool.execute({"stage_output": {"cuts": []}, "checkpoint": cp})
    assert r.success and r.data["failure_action"] == "flag"


# ─────────────────────────────────────────────────────────────────────────────
# Cross-cutting: result structure and metadata
# ─────────────────────────────────────────────────────────────────────────────

def test_result_always_includes_checkpoint_id():
    """checkpoint_id is always returned for tracing."""
    r = tool.execute({"stage_output": SCRIPT_PASSING, "checkpoint": get_cp("CP-S1")})
    assert r.success and r.data["checkpoint_id"] == "CP-S1"


def test_pass_result_has_null_deviation():
    """When check passes, deviation is None."""
    r = tool.execute({"stage_output": SCRIPT_PASSING, "checkpoint": get_cp("CP-S1")})
    assert r.success and r.data["pass"] is True and r.data["deviation"] is None


def test_fail_result_has_non_null_deviation():
    """When check fails, deviation describes the gap."""
    r = tool.execute({"stage_output": SCRIPT_FAILING_TIMING, "checkpoint": get_cp("CP-S1")})
    assert r.success and r.data["pass"] is False and r.data["deviation"] is not None


def test_result_includes_actual_value():
    """actual_value is always populated for debugging."""
    r = tool.execute({"stage_output": SCRIPT_PASSING, "checkpoint": get_cp("CP-S1")})
    assert r.success and r.data["actual_value"] is not None


def test_research_grounded_maps_to_revise():
    """research-grounded confidence → failure_action=revise."""
    cp = get_cp("CP-V1")
    assert cp["source_confidence"] == "research-grounded"
    assert cp["failure_action"] == "revise"


def test_all_checkpoint_types_covered():
    """Verify fixture has checkpoints for all expected types."""
    checkpoint_types = {cp["check_type"] for cp in REALISTIC_BIBLE["compliance_manifest"]["checkpoints"]}
    assert "timing" in checkpoint_types
    assert "presence" in checkpoint_types
    assert "structural" in checkpoint_types
    assert "content" in checkpoint_types


def test_all_stages_covered():
    """Verify fixture has checkpoints for all four downstream stages."""
    stages = {cp["applies_to_stage"] for cp in REALISTIC_BIBLE["compliance_manifest"]["checkpoints"]}
    assert stages == {"script", "scene_plan", "assets", "edit"}


# ─────────────────────────────────────────────────────────────────────────────
# Audio/video duration alignment check (Pattern D regression guard)
# ─────────────────────────────────────────────────────────────────────────────

def test_audio_video_duration_alignment():
    """render_report.json must not flag audio truncation in any variant.

    Guards against the class of bug where the audio stream is silently shorter
    than the video (e.g. 28.58s audio in a 31s video). Reads the most recent
    render_report.json and checks that:
      - duration_check is PASS for every variant
      - audio_truncation_check (if present) does not start with WARN
    """
    import json
    import pytest as _pytest
    from pathlib import Path

    report_path = (
        Path(__file__).resolve().parent.parent.parent
        / "projects" / "flowly-tiktok-30s" / "artifacts" / "render_report.json"
    )
    if not report_path.exists():
        _pytest.skip(
            f"render_report.json not found at {report_path} — run a production render first"
        )

    report = json.loads(report_path.read_text())
    probe = report.get("probe_results", {})

    assert probe, "render_report.probe_results is empty — no variants were probed"

    for variant, checks in probe.items():
        dur_check = checks.get("duration_check", "MISSING")
        assert dur_check == "PASS", (
            f"Variant '{variant}': duration_check={dur_check!r} — "
            f"expected PASS. Note: {checks.get('duration_note', '')}"
        )

        # audio_truncation_check is written by _run_final_review when total_duration_seconds
        # is set. If absent, the render predates Pattern D — treat as an inconclusive skip
        # rather than a false PASS, so the test is not silently vacuous.
        audio_trunc = checks.get("audio_truncation_check")
        if audio_trunc is None:
            import pytest as _pytest
            _pytest.skip(
                f"Variant '{variant}': audio_truncation_check absent from render_report — "
                "re-render with total_duration_seconds set to enable this check"
            )
        assert not audio_trunc.startswith("WARN"), (
            f"Variant '{variant}': audio_truncation_check={audio_trunc!r} — "
            "audio stream is more than 1s shorter than the target duration. "
            "Check for corrupt TTS files or broken sidechaincompress filter graph."
        )


# ─────────────────────────────────────────────────────────────────────────────
# Standalone runner
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    tests = [
        # Script timing
        test_script_B1_timing_passes,
        test_script_B2_timing_passes,
        test_script_B5_timing_passes,
        test_script_B1_timing_fails_too_long,
        test_script_timing_ignores_other_beats,
        test_script_timing_sums_split_sections,
        test_script_timing_works_with_maps_to_beat,
        test_script_timing_empty_sections_fails,
        test_script_semantic_cp_rejected,
        # Prohibited elements
        test_script_prohibited_elements_clean,
        test_script_prohibited_element_found,
        test_script_prohibited_case_insensitive,
        test_script_prohibited_partial_match,
        # Scene motif presence
        test_scene_clock_imagery_passes_count,
        test_scene_clock_imagery_fails_count,
        test_scene_notification_avalanche_passes,
        test_scene_notification_avalanche_absent,
        # Scene beat mapping
        test_scene_app_reveal_mapped_to_B3_passes,
        test_scene_logo_cta_mapped_to_B5_passes,
        test_scene_app_reveal_missing_from_B3,
        test_scene_beat_mapping_wrong_beat,
        # Brand constraints
        test_scene_brand_in_final_scene_passes,
        test_scene_brand_missing_from_all_scenes,
        # Asset manifest
        test_asset_manifest_mandatory_elements_pass,
        test_asset_manifest_missing_mandatory_elements,
        # Edit rhythm confidence
        test_edit_pattern_inferred_is_revise_level,
        test_edit_default_heuristic_is_flag_level,
        # Result structure
        test_result_always_includes_checkpoint_id,
        test_pass_result_has_null_deviation,
        test_fail_result_has_non_null_deviation,
        test_result_includes_actual_value,
        test_research_grounded_maps_to_revise,
        test_all_checkpoint_types_covered,
        test_all_stages_covered,
        test_audio_video_duration_alignment,
    ]
    passed = failed = 0
    for t in tests:
        try:
            t()
            print(f"[PASS] {t.__name__}")
            passed += 1
        except Exception as e:
            print(f"[FAIL] {t.__name__}: {e}")
            import traceback; traceback.print_exc()
            failed += 1
    print(f"\n{passed}/{passed + failed} tests passed")
    import sys; sys.exit(0 if failed == 0 else 1)
