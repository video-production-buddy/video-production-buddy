#!/usr/bin/env python3
"""Unit tests for ComplianceCheck — structural checkpoint evaluation. 16 tests total."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from tools.compliance.compliance_check import ComplianceCheck


def make_tool():
    return ComplianceCheck()


# ── Timing ────────────────────────────────────────────────────────────────────

def test_timing_pass_within_tolerance():
    tool = make_tool()
    # 120 words at 150 WPM = 48s. Target 50s ±5s (10%). PASS.
    stage = {"sections": [{"beat_id": "B1", "narration": " ".join(["word"] * 120)}]}
    cp = {"id": "CP-S1", "check_type": "timing", "evaluation_method": "structural",
          "criterion": "Section covering beat B1 (hook) must be within ±10% of 50s",
          "failure_action": "revise"}
    r = tool.execute({"stage_output": stage, "checkpoint": cp})
    assert r.success and r.data["pass"] is True and r.data["deviation"] is None


def test_timing_fail_too_short():
    tool = make_tool()
    # 10 words = 4s. Target 50s ±5s. FAIL.
    stage = {"sections": [{"beat_id": "B1", "narration": " ".join(["word"] * 10)}]}
    cp = {"id": "CP-S1", "check_type": "timing", "evaluation_method": "structural",
          "criterion": "Section covering beat B1 (hook) must be within ±10% of 50s",
          "failure_action": "revise"}
    r = tool.execute({"stage_output": stage, "checkpoint": cp})
    assert r.success and r.data["pass"] is False and r.data["deviation"] is not None


def test_timing_sums_multiple_sections_for_beat():
    tool = make_tool()
    # Two B1 sections: 60+60=120 words → 48s. B2 (200 words) ignored. Target 50s. PASS.
    stage = {"sections": [
        {"beat_id": "B1", "narration": " ".join(["word"] * 60)},
        {"beat_id": "B1", "narration": " ".join(["word"] * 60)},
        {"beat_id": "B2", "narration": " ".join(["word"] * 200)},
    ]}
    cp = {"id": "CP-S1", "check_type": "timing", "evaluation_method": "structural",
          "criterion": "Section covering beat B1 (hook) must be within ±10% of 50s",
          "failure_action": "revise"}
    r = tool.execute({"stage_output": stage, "checkpoint": cp})
    assert r.success and r.data["pass"] is True


def test_timing_unparseable_beat_id_fails_safe():
    """If criterion doesn't contain 'beat <ID>', fail-safe instead of silently summing all sections."""
    tool = make_tool()
    stage = {"sections": [{"beat_id": "B1", "narration": " ".join(["word"] * 120)}]}
    cp = {"id": "CP-S1", "check_type": "timing", "evaluation_method": "structural",
          "criterion": "The hook section should be about 50s",
          "failure_action": "revise"}
    r = tool.execute({"stage_output": stage, "checkpoint": cp})
    assert r.success and r.data["pass"] is False


# ── Presence ─────────────────────────────────────────────────────────────────

def test_presence_brand_name_found():
    tool = make_tool()
    stage = {"scenes": [{"description": "Acme Corp logo fades in", "maps_to_beat": "B6"}]}
    cp = {"id": "CP-B1", "check_type": "presence", "evaluation_method": "structural",
          "criterion": "brand_name 'Acme Corp' must appear in final scene (last 5s)",
          "failure_action": "revise"}
    r = tool.execute({"stage_output": stage, "checkpoint": cp})
    assert r.success and r.data["pass"] is True


def test_presence_brand_name_missing():
    tool = make_tool()
    stage = {"scenes": [{"description": "Generic outro", "maps_to_beat": "B6"}]}
    cp = {"id": "CP-B1", "check_type": "presence", "evaluation_method": "structural",
          "criterion": "brand_name 'Acme Corp' must appear in final scene (last 5s)",
          "failure_action": "revise"}
    r = tool.execute({"stage_output": stage, "checkpoint": cp})
    assert r.success and r.data["pass"] is False


def test_presence_motif_minimum_count_met():
    tool = make_tool()
    stage = {"scenes": [
        {"description": "clock imagery ticking"},
        {"description": "clock imagery on wall"},
        {"description": "product reveal"},
    ]}
    cp = {"id": "CP-V1", "check_type": "presence", "evaluation_method": "structural",
          "criterion": "'clock imagery' must appear in ≥2 scenes",
          "failure_action": "revise"}
    r = tool.execute({"stage_output": stage, "checkpoint": cp})
    assert r.success and r.data["pass"] is True


def test_presence_motif_minimum_count_not_met():
    tool = make_tool()
    stage = {"scenes": [
        {"description": "clock imagery ticking"},
        {"description": "product showcase"},
    ]}
    cp = {"id": "CP-V1", "check_type": "presence", "evaluation_method": "structural",
          "criterion": "'clock imagery' must appear in ≥3 scenes",
          "failure_action": "revise"}
    r = tool.execute({"stage_output": stage, "checkpoint": cp})
    assert r.success and r.data["pass"] is False


# ── Presence: Negated (prohibited elements) ──────────────────────────────────

def test_presence_prohibited_element_found():
    """CP-B3: prohibited terms found → FAIL."""
    tool = make_tool()
    stage = {"sections": [{"narration": "Our competitor Brand X is worse"}]}
    cp = {"id": "CP-B3", "check_type": "presence", "evaluation_method": "structural",
          "criterion": "prohibited_elements ['competitor', 'brand x'] must not appear in any script section",
          "failure_action": "revise"}
    r = tool.execute({"stage_output": stage, "checkpoint": cp})
    assert r.success and r.data["pass"] is False


def test_presence_prohibited_element_clean():
    """CP-B3: no prohibited terms found → PASS."""
    tool = make_tool()
    stage = {"sections": [{"narration": "Our product is amazing"}]}
    cp = {"id": "CP-B3", "check_type": "presence", "evaluation_method": "structural",
          "criterion": "prohibited_elements ['competitor'] must not appear in any script section",
          "failure_action": "revise"}
    r = tool.execute({"stage_output": stage, "checkpoint": cp})
    assert r.success and r.data["pass"] is True


# ── Structural (beat mapping) ────────────────────────────────────────────────

def test_structural_beat_mapping_found():
    tool = make_tool()
    stage = {"scenes": [
        {"maps_to_beat": "B1", "description": "hook scene"},
        {"maps_to_beat": "B3", "description": "product reveal with full-screen close-up"},
    ]}
    cp = {"id": "CP-V2", "check_type": "structural", "evaluation_method": "structural",
          "criterion": "A scene for 'product reveal' must be present, mapped to beat B3",
          "failure_action": "revise"}
    r = tool.execute({"stage_output": stage, "checkpoint": cp})
    assert r.success and r.data["pass"] is True


def test_structural_beat_mapping_not_found():
    tool = make_tool()
    stage = {"scenes": [{"maps_to_beat": "B1", "description": "hook"}]}
    cp = {"id": "CP-V2", "check_type": "structural", "evaluation_method": "structural",
          "criterion": "A scene for 'product reveal' must be present, mapped to beat B3",
          "failure_action": "revise"}
    r = tool.execute({"stage_output": stage, "checkpoint": cp})
    assert r.success and r.data["pass"] is False


# ── Guards ────────────────────────────────────────────────────────────────────

def test_rejects_semantic_checkpoint():
    tool = make_tool()
    cp = {"id": "CP-S1a", "check_type": "content", "evaluation_method": "semantic",
          "criterion": "Section must achieve emotional_target='curiosity'",
          "failure_action": "revise"}
    r = tool.execute({"stage_output": {}, "checkpoint": cp})
    assert r.success is False and "structural" in r.error.lower()


def test_rejects_missing_stage_output():
    tool = make_tool()
    r = tool.execute({"checkpoint": {"id": "CP-S1", "check_type": "timing",
                                      "evaluation_method": "structural",
                                      "criterion": "x", "failure_action": "revise"}})
    assert r.success is False


def test_rejects_missing_checkpoint():
    tool = make_tool()
    r = tool.execute({"stage_output": {"sections": []}})
    assert r.success is False


def test_rejects_unknown_check_type():
    tool = make_tool()
    cp = {"id": "CP-X1", "check_type": "unknown_type",
          "evaluation_method": "structural", "criterion": "x", "failure_action": "flag"}
    r = tool.execute({"stage_output": {}, "checkpoint": cp})
    assert r.success is False


# ── Structured criteria (v2 path — replaces natural-language regex parsing) ──

def test_structured_timing_pass_within_tolerance():
    """A structured timing criterion bypasses the regex parser entirely."""
    tool = make_tool()
    # 120 words at 150 WPM = 48s. Target 50s ±10%. PASS.
    stage = {"sections": [{"beat_id": "B1", "narration": " ".join(["word"] * 120)}]}
    cp = {
        "id": "CP-S1", "check_type": "timing", "evaluation_method": "structural",
        "criterion": "(legacy text — must NOT be parsed because structured is present)",
        "structured": {
            "kind": "timing",
            "beat_id": "B1",
            "target_seconds": 50.0,
            "tolerance": 0.10,
        },
        "failure_action": "revise",
    }
    r = tool.execute({"stage_output": stage, "checkpoint": cp})
    assert r.success and r.data["pass"] is True and r.data["deviation"] is None


def test_structured_timing_fail_outside_tolerance():
    tool = make_tool()
    stage = {"sections": [{"beat_id": "B1", "narration": " ".join(["word"] * 10)}]}
    cp = {
        "id": "CP-S1", "check_type": "timing", "evaluation_method": "structural",
        "criterion": "anything", "failure_action": "revise",
        "structured": {
            "kind": "timing", "beat_id": "B1",
            "target_seconds": 50.0, "tolerance": 0.10,
        },
    }
    r = tool.execute({"stage_output": stage, "checkpoint": cp})
    assert r.success and r.data["pass"] is False and r.data["deviation"]


def test_structured_timing_uses_structured_even_when_legacy_text_is_unparseable():
    """Hard contract: if structured is present, the legacy free-text criterion
    is never parsed — even if it would have failed regex parsing."""
    tool = make_tool()
    stage = {"sections": [{"beat_id": "B1", "narration": " ".join(["word"] * 120)}]}
    cp = {
        "id": "CP-S1", "check_type": "timing", "evaluation_method": "structural",
        "criterion": "this string would crash the legacy regex (no 'beat X' or 'Ns' tokens)",
        "structured": {
            "kind": "timing", "beat_id": "B1",
            "target_seconds": 50.0, "tolerance": 0.10,
        },
        "failure_action": "revise",
    }
    r = tool.execute({"stage_output": stage, "checkpoint": cp})
    assert r.success and r.data["pass"] is True
    assert "Cannot parse" not in (r.data.get("deviation") or "")


def test_structured_presence_brand_name_found():
    tool = make_tool()
    stage = {"sections": [{"narration": "Try Flowcut now."}]}
    cp = {
        "id": "CP-B1", "check_type": "presence", "evaluation_method": "structural",
        "criterion": "anything", "failure_action": "revise",
        "structured": {"kind": "presence", "terms": ["Flowcut"], "min_count": 1},
    }
    r = tool.execute({"stage_output": stage, "checkpoint": cp})
    assert r.success and r.data["pass"] is True


def test_structured_presence_minimum_count_not_met():
    tool = make_tool()
    stage = {"scenes": [{"description": "frost wave on hand"}]}
    cp = {
        "id": "CP-V1", "check_type": "presence", "evaluation_method": "structural",
        "criterion": "anything", "failure_action": "revise",
        "structured": {"kind": "presence", "terms": ["frost wave"], "min_count": 3},
    }
    r = tool.execute({"stage_output": stage, "checkpoint": cp})
    assert r.success and r.data["pass"] is False
    assert "frost wave" in (r.data.get("deviation") or "")


def test_structured_presence_negated_finds_violation():
    """Negated structured presence rejects when prohibited terms appear."""
    tool = make_tool()
    stage = {"sections": [{"narration": "Beat the competition with X."}]}
    cp = {
        "id": "CP-B3", "check_type": "presence", "evaluation_method": "structural",
        "criterion": "anything", "failure_action": "revise",
        "structured": {"kind": "presence", "terms": ["beat the competition"], "negated": True},
    }
    r = tool.execute({"stage_output": stage, "checkpoint": cp})
    assert r.success and r.data["pass"] is False


def test_structured_presence_ignores_hallucination_check_metadata():
    """Presence must prove the term appears in stage content, not review metadata."""
    tool = make_tool()
    stage = {
        "scenes": [
            {
                "id": "scene-1",
                "description": "Clean abstract productivity interface.",
                "hallucination_checks": [
                    {
                        "check_id": "HC-LOGO",
                        "requirement": "Acme logo appears clearly.",
                        "prohibited_failure": "Missing Acme logo.",
                    }
                ],
            }
        ]
    }
    cp = {
        "id": "CP-V1",
        "check_type": "presence",
        "evaluation_method": "structural",
        "criterion": "anything",
        "failure_action": "revise",
        "structured": {"kind": "presence", "terms": ["Acme logo"], "min_count": 1},
    }

    r = tool.execute({"stage_output": stage, "checkpoint": cp})
    assert r.success and r.data["pass"] is False


def test_structured_negated_presence_ignores_prohibited_failure_metadata():
    """A prohibited term in audit instructions is not itself a content violation."""
    tool = make_tool()
    stage = {
        "scenes": [
            {
                "id": "scene-1",
                "description": "Clean product shot with no competing marks.",
                "hallucination_checks": [
                    {
                        "check_id": "HC-COMPETITOR",
                        "requirement": "Avoid competitor logos.",
                        "prohibited_failure": "Competitor logo appears.",
                    }
                ],
            }
        ]
    }
    cp = {
        "id": "CP-B3",
        "check_type": "presence",
        "evaluation_method": "structural",
        "criterion": "anything",
        "failure_action": "revise",
        "structured": {
            "kind": "presence",
            "terms": ["Competitor logo"],
            "negated": True,
        },
    }

    r = tool.execute({"stage_output": stage, "checkpoint": cp})
    assert r.success and r.data["pass"] is True


def test_structured_beat_mapping_passes_when_scene_maps_to_beat():
    tool = make_tool()
    stage = {"scenes": [{"id": "scene-1", "maps_to_beat": "cta_brand"}]}
    cp = {
        "id": "CP-V2", "check_type": "structural", "evaluation_method": "structural",
        "criterion": "anything", "failure_action": "revise",
        "structured": {"kind": "beat_mapping", "beat_id": "cta_brand"},
    }
    r = tool.execute({"stage_output": stage, "checkpoint": cp})
    assert r.success and r.data["pass"] is True


def test_structured_beat_mapping_fails_when_no_scene_maps():
    tool = make_tool()
    stage = {"scenes": [{"id": "scene-1", "maps_to_beat": "hook"}]}
    cp = {
        "id": "CP-V2", "check_type": "structural", "evaluation_method": "structural",
        "criterion": "anything", "failure_action": "revise",
        "structured": {"kind": "beat_mapping", "beat_id": "cta_brand"},
    }
    r = tool.execute({"stage_output": stage, "checkpoint": cp})
    assert r.success and r.data["pass"] is False


def test_structured_rejects_unknown_kind():
    """A typo in 'kind' must surface as an error, not silently fall through to regex."""
    tool = make_tool()
    cp = {
        "id": "CP-X", "check_type": "timing", "evaluation_method": "structural",
        "criterion": "x", "failure_action": "flag",
        "structured": {"kind": "made_up_kind", "beat_id": "B1"},
    }
    r = tool.execute({"stage_output": {"sections": []}, "checkpoint": cp})
    assert r.success is False
    assert "kind" in r.error.lower()


def test_legacy_path_unchanged_when_structured_absent():
    """Sanity: when structured is missing, the legacy regex path runs (existing behavior)."""
    tool = make_tool()
    stage = {"sections": [{"beat_id": "B1", "narration": " ".join(["word"] * 120)}]}
    cp = {
        "id": "CP-S1", "check_type": "timing", "evaluation_method": "structural",
        "criterion": "Section covering beat B1 (hook) must be within ±10% of 50s",
        "failure_action": "revise",
    }
    r = tool.execute({"stage_output": stage, "checkpoint": cp})
    assert r.success and r.data["pass"] is True


if __name__ == "__main__":
    import traceback
    tests = [
        test_timing_pass_within_tolerance, test_timing_fail_too_short,
        test_timing_sums_multiple_sections_for_beat, test_timing_unparseable_beat_id_fails_safe,
        test_presence_brand_name_found, test_presence_brand_name_missing,
        test_presence_motif_minimum_count_met, test_presence_motif_minimum_count_not_met,
        test_presence_prohibited_element_found, test_presence_prohibited_element_clean,
        test_structural_beat_mapping_found, test_structural_beat_mapping_not_found,
        test_rejects_semantic_checkpoint, test_rejects_missing_stage_output,
        test_rejects_missing_checkpoint, test_rejects_unknown_check_type,
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
    print(f"\n{passed}/{passed+failed} tests passed")
    sys.exit(0 if failed == 0 else 1)
