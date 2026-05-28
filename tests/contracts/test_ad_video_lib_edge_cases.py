"""Fine-grained edge-case tests for lib modules used by ad-video pipeline.

Tests trend_alignment, knowledge_alignment, conflict_detection,
trend_recency, provenance_audit, checkpoint, user_request, and
intensity_curve at boundary conditions.
"""

from __future__ import annotations

import pytest
from datetime import date, timedelta
from typing import Any

from lib.trend_alignment import (
    check_ad_video_planning_trend_alignment,
    check_script_trend_alignment,
    check_scene_plan_trend_alignment,
    select_trends_for_alignment,
)
from lib.knowledge_alignment import (
    check_ad_video_planning_knowledge_alignment,
    check_script_knowledge_alignment,
    check_scene_plan_knowledge_alignment,
)
from lib.conflict_detection import (
    check_trend_knowledge_conflicts,
    _text_overlaps,
)
from lib.trend_recency import (
    score_trend_recency,
    filter_stale_trends,
    dedupe_trends,
)
from lib.provenance_audit import (
    audit_intelligence_provenance,
    _has_citable_evidence,
)
from lib.intensity_curve import derive_intensity_curve


# ---------------------------------------------------------------------------
# trend_alignment edge cases
# ---------------------------------------------------------------------------


def _minimal_bible_with_trends(trends: list[dict] | None = None) -> dict:
    alignments = trends or []
    return {
        "intelligence": {
            "trend_alignment": {
                "selected_trend_ids": [t.get("trend_id", "") for t in alignments],
                "alignments": alignments,
            }
        }
    }


def _trend_entry(
    trend_id: str = "t1",
    target_beat: str = "hook",
    source_ref: str = "",
) -> dict:
    entry: dict[str, Any] = {
        "trend_id": trend_id,
        "target_beat": target_beat,
        "script_usage": {"required": True},
        "scene_usage": {},
        "application_targets": [],
    }
    if source_ref:
        entry["script_usage"]["source_ref"] = source_ref
    return entry


def _script_section(section_id: str, beat: str, source_ref: str = "") -> dict:
    section: dict[str, Any] = {"id": section_id, "beat": beat}
    if source_ref:
        section["source_ref"] = source_ref
    return section


def _scene_with_trend(scene_id: str, trend_refs: list[str] | None = None) -> dict:
    scene: dict[str, Any] = {"id": scene_id}
    if trend_refs:
        scene["trend_alignment_refs"] = trend_refs
        scene["trend_alignment_notes"] = "applied trend"
    return scene


class TestTrendAlignmentEdgeCases:
    def test_missing_intelligence_block(self) -> None:
        bible = {}
        result = check_ad_video_planning_trend_alignment(bible, {}, {})
        assert not result["ok"]
        assert any(i["kind"] == "trend_alignment_block_missing" for i in result["issues"])

    def test_empty_selection_is_valid(self) -> None:
        bible = {
            "intelligence": {
                "trend_alignment": {"selected_trend_ids": [], "alignments": []}
            }
        }
        result = check_ad_video_planning_trend_alignment(
            bible, {"sections": []}, {"scenes": []}
        )
        assert result["ok"]

    def test_selected_trend_without_alignment_entry(self) -> None:
        bible = {
            "intelligence": {
                "trend_alignment": {
                    "selected_trend_ids": ["t1"],
                    "alignments": [],
                }
            }
        }
        result = check_ad_video_planning_trend_alignment(bible, {}, {})
        assert not result["ok"]
        assert any(i["kind"] == "missing_selected_trend_alignment" for i in result["issues"])

    def test_trend_alignment_rejects_inconsistent_source_ref(self) -> None:
        bible = _minimal_bible_with_trends([
            _trend_entry("t1", "hook", source_ref="trend_alignment:wrong")
        ])
        script = {"sections": [
            _script_section("hook", "hook", "trend_alignment:wrong")
        ]}

        result = check_ad_video_planning_trend_alignment(bible, script, {"scenes": []})

        assert not result["ok"]
        assert any(i["kind"] == "inconsistent_trend_source_ref" for i in result["issues"])

    def test_trend_with_hook_beat_requires_hook_section(self) -> None:
        bible = _minimal_bible_with_trends([_trend_entry("t1", "hook")])
        script = {"sections": []}
        result = check_script_trend_alignment(bible, script)
        assert not result["ok"]

    def test_trend_with_build_beat_requires_build_section(self) -> None:
        bible = _minimal_bible_with_trends([_trend_entry("t1", "build")])
        script = {"sections": [_script_section("s1", "hook")]}
        result = check_script_trend_alignment(bible, script)
        assert not result["ok"]

    def test_trend_with_reveal_beat_does_not_require_script(self) -> None:
        bible = _minimal_bible_with_trends([_trend_entry("t1", "reveal")])
        script = {"sections": []}
        result = check_script_trend_alignment(bible, script)
        assert result["ok"]

    def test_multi_target_requires_both_hook_and_build(self) -> None:
        bible = _minimal_bible_with_trends([_trend_entry("t1", "multi")])
        script = {"sections": [
            _script_section("s1", "hook"),
        ]}
        result = check_script_trend_alignment(bible, script)
        assert not result["ok"]

    def test_multi_target_passes_with_both(self) -> None:
        bible = _minimal_bible_with_trends([
            _trend_entry("t1", "multi", source_ref="trend_alignment:t1"),
        ])
        script = {"sections": [
            _script_section("s1", "hook", "trend_alignment:t1"),
            _script_section("s2", "build", "trend_alignment:t1"),
        ]}
        result = check_script_trend_alignment(bible, script)
        assert result["ok"]

    def test_visual_trend_requires_scene_alignment(self) -> None:
        bible = _minimal_bible_with_trends([{
            "trend_id": "t1",
            "target_beat": "reveal",
            "script_usage": {},
            "scene_usage": {"required": True},
            "application_targets": ["visual"],
        }])
        result = check_scene_plan_trend_alignment(bible, {"scenes": []})
        assert not result["ok"]

    def test_visual_trend_passes_with_scene(self) -> None:
        bible = _minimal_bible_with_trends([{
            "trend_id": "t1",
            "target_beat": "reveal",
            "script_usage": {},
            "scene_usage": {},
            "application_targets": ["visual"],
        }])
        scene_plan = {"scenes": [_scene_with_trend("s1", ["trend_alignment:t1"])]}
        result = check_scene_plan_trend_alignment(bible, scene_plan)
        assert result["ok"]

    def test_visual_trend_requires_canonical_scene_ref(self) -> None:
        bible = _minimal_bible_with_trends([{
            "trend_id": "t1",
            "target_beat": "reveal",
            "script_usage": {},
            "scene_usage": {"required": True},
            "application_targets": ["visual"],
        }])
        scene_plan = {"scenes": [_scene_with_trend("s1", ["t1"])]}

        result = check_scene_plan_trend_alignment(bible, scene_plan)

        assert not result["ok"]
        assert any(i["kind"] == "missing_scene_trend_alignment" for i in result["issues"])

    def test_select_trends_for_alignment_filters_unsafe(self) -> None:
        trends = [
            {"signal": "safe trend", "sentiment": "positive", "brand_safety": "safe"},
            {"signal": "unsafe trend", "sentiment": "positive", "brand_safety": "unsafe"},
        ]
        result = select_trends_for_alignment(trends, now=date.today())
        assert len(result) == 1
        assert result[0]["signal"] == "safe trend"

    def test_select_trends_for_alignment_filters_negative(self) -> None:
        trends = [
            {"signal": "positive", "sentiment": "positive", "brand_safety": "safe"},
            {"signal": "negative", "sentiment": "negative", "brand_safety": "safe"},
        ]
        result = select_trends_for_alignment(trends, now=date.today())
        assert len(result) == 1

    def test_select_trends_for_alignment_unknown_sentiment_excluded(self) -> None:
        trends = [
            {"signal": "unknown", "sentiment": "unknown", "brand_safety": "safe"},
        ]
        result = select_trends_for_alignment(trends, now=date.today())
        assert len(result) == 0

    def test_select_trends_for_alignment_platform_norm_unknown_allowed(self) -> None:
        trends = [
            {
                "signal": "platform norm",
                "sentiment": "unknown",
                "brand_safety": "safe",
                "trend_type": "platform_format_norm",
            },
        ]
        result = select_trends_for_alignment(trends, now=date.today())
        assert len(result) == 1

    def test_select_trends_respects_max_items(self) -> None:
        trends = [
            {"signal": f"trend-{i}", "sentiment": "positive", "brand_safety": "safe"}
            for i in range(10)
        ]
        result = select_trends_for_alignment(trends, now=date.today(), max_items=3)
        assert len(result) == 3


# ---------------------------------------------------------------------------
# knowledge_alignment edge cases
# ---------------------------------------------------------------------------


def _minimal_bible_with_knowledge(
    cards: list[dict] | None = None,
    alignments: list[dict] | None = None,
) -> dict:
    cards = cards or []
    alignments = alignments or []
    return {
        "intelligence": {
            "knowledge_alignment": {
                "selected_card_ids": [a.get("card_id", "") for a in alignments],
                "alignments": alignments,
            }
        }
    }


class TestKnowledgeAlignmentEdgeCases:
    def test_missing_intelligence_block(self) -> None:
        result = check_ad_video_planning_knowledge_alignment({}, {}, {})
        assert not result["ok"]
        assert any(i["kind"] == "knowledge_alignment_block_missing" for i in result["issues"])

    def test_empty_selection_is_valid(self) -> None:
        bible = {
            "intelligence": {
                "knowledge_alignment": {"selected_card_ids": [], "alignments": []}
            }
        }
        result = check_ad_video_planning_knowledge_alignment(
            bible, {"sections": []}, {"scenes": []}
        )
        assert result["ok"]

    def test_selected_card_without_alignment_entry(self) -> None:
        bible = {
            "intelligence": {
                "knowledge_alignment": {
                    "selected_card_ids": ["c1"],
                    "alignments": [],
                }
            }
        }
        result = check_ad_video_planning_knowledge_alignment(bible, {}, {})
        assert not result["ok"]
        assert any(i["kind"] == "missing_selected_knowledge_alignment" for i in result["issues"])

    def test_inconsistent_source_ref_detected(self) -> None:
        bible = {
            "intelligence": {
                "knowledge_alignment": {
                    "selected_card_ids": ["card-1"],
                    "alignments": [{
                        "card_id": "card-1",
                        "source_ref": "wrong_ref",
                        "script_usage": {"source_ref": "also_wrong"},
                        "application_targets": [],
                    }],
                }
            }
        }
        result = check_ad_video_planning_knowledge_alignment(
            bible, {"sections": []}, {"scenes": []}
        )
        assert not result["ok"]
        consistency = [i for i in result["issues"] if "inconsistent" in i.get("kind", "")]
        assert len(consistency) > 0

    def test_script_alignment_for_hook_beat(self) -> None:
        bible = _minimal_bible_with_knowledge(alignments=[{
            "card_id": "c1",
            "target_beat": "hook",
            "script_usage": {"required": True, "source_ref": "knowledge_alignment:c1"},
            "scene_usage": {},
            "application_targets": [],
        }])
        script = {"sections": [
            {"id": "s1", "beat": "hook", "source_ref": "knowledge_alignment:c1"}
        ]}
        result = check_script_knowledge_alignment(bible, script)
        assert result["ok"]

    def test_scene_alignment_for_visual_targets(self) -> None:
        bible = _minimal_bible_with_knowledge(alignments=[{
            "card_id": "c1",
            "script_usage": {},
            "scene_usage": {},
            "application_targets": ["visual"],
        }])
        scene_plan = {"scenes": [
            {
                "id": "s1",
                "knowledge_alignment_refs": ["knowledge_alignment:c1"],
                "knowledge_alignment_notes": "applied principle",
            }
        ]}
        result = check_scene_plan_knowledge_alignment(bible, scene_plan)
        assert result["ok"]

    def test_scene_alignment_missing_notes_fails(self) -> None:
        bible = _minimal_bible_with_knowledge(alignments=[{
            "card_id": "c1",
            "script_usage": {},
            "scene_usage": {},
            "application_targets": ["visual"],
        }])
        scene_plan = {"scenes": [
            {"id": "s1", "knowledge_alignment_refs": ["knowledge_alignment:c1"]}
        ]}
        result = check_scene_plan_knowledge_alignment(bible, scene_plan)
        assert not result["ok"]


# ---------------------------------------------------------------------------
# conflict_detection edge cases
# ---------------------------------------------------------------------------


class TestConflictDetectionEdgeCases:
    def test_no_conflicts_when_no_overlap(self) -> None:
        result = check_trend_knowledge_conflicts(
            trend_alignments=[{
                "trend_id": "t1",
                "scene_usage": {"visual_or_pacing_instruction": "fast cuts bright colors"},
            }],
            knowledge_cards=[{
                "card_id": "c1",
                "avoid_when": ["slow pacing minimal visuals"],
            }],
            knowledge_alignments=[{"card_id": "c1"}],
        )
        assert result["ok"]

    def test_conflict_when_trend_matches_avoid_condition(self) -> None:
        result = check_trend_knowledge_conflicts(
            trend_alignments=[{
                "trend_id": "t1",
                "scene_usage": {"visual_or_pacing_instruction": "rapid cuts saturated colors everywhere"},
            }],
            knowledge_cards=[{
                "card_id": "c1",
                "avoid_when": ["saturated colors everywhere all the time"],
            }],
            knowledge_alignments=[{"card_id": "c1"}],
        )
        assert not result["ok"]
        assert any(c["kind"] == "trend_knowledge_conflict" for c in result["conflicts"])

    def test_overapply_conflict_detected(self) -> None:
        result = check_trend_knowledge_conflicts(
            trend_alignments=[{
                "trend_id": "t1",
                "scene_usage": {"visual_or_pacing_instruction": "constant emotional storytelling throughout"},
            }],
            knowledge_cards=[{"card_id": "c1", "avoid_when": []}],
            knowledge_alignments=[{
                "card_id": "c1",
                "do_not_overapply": ["emotional storytelling throughout entire video"],
            }],
        )
        assert not result["ok"]

    def test_text_overlaps_boundary(self) -> None:
        assert _text_overlaps("rapid cuts bright colors everywhere", "rapid cuts bright colors everywhere")
        assert not _text_overlaps("short text", "completely different content")

    def test_empty_inputs_produce_no_conflicts(self) -> None:
        result = check_trend_knowledge_conflicts([], [], [])
        assert result["ok"]
        assert result["conflicts"] == []

    def test_non_dict_entries_skipped(self) -> None:
        result = check_trend_knowledge_conflicts(
            trend_alignments=["not_a_dict"],
            knowledge_cards=["not_a_dict"],
            knowledge_alignments=["not_a_dict"],
        )
        assert result["ok"]


# ---------------------------------------------------------------------------
# trend_recency edge cases
# ---------------------------------------------------------------------------


class TestTrendRecencyEdgeCases:
    def test_evergreen_always_fresh(self) -> None:
        trend = {"is_evergreen": True, "observed_at": "2020-01-01"}
        assert score_trend_recency(trend, now=date(2026, 1, 1)) == 1.0

    def test_no_observed_at_is_fresh(self) -> None:
        assert score_trend_recency({}, now=date(2026, 1, 1)) == 1.0

    def test_future_date_is_fresh(self) -> None:
        trend = {"observed_at": "2027-01-01"}
        assert score_trend_recency(trend, now=date(2026, 1, 1)) == 1.0

    def test_same_day_is_fresh(self) -> None:
        trend = {"observed_at": "2026-01-01"}
        assert score_trend_recency(trend, now=date(2026, 1, 1)) == 1.0

    def test_within_window_is_fresh(self) -> None:
        trend = {"observed_at": "2025-07-01", "decay_window_days": 200}
        assert score_trend_recency(trend, now=date(2026, 1, 1)) == 1.0

    def test_at_2x_window_is_stale(self) -> None:
        trend = {"observed_at": "2025-01-01", "decay_window_days": 180}
        assert score_trend_recency(trend, now=date(2026, 1, 1)) == 0.0

    def test_beyond_2x_window_is_stale(self) -> None:
        trend = {"observed_at": "2024-01-01", "decay_window_days": 180}
        score = score_trend_recency(trend, now=date(2026, 1, 1))
        assert score == 0.0

    def test_linear_decay_between_window_and_2x(self) -> None:
        window = 180
        trend = {"observed_at": "2025-01-01", "decay_window_days": window}
        now = date(2025, 7, 1) + timedelta(days=90)
        score = score_trend_recency(trend, now=now)
        assert 0.0 < score < 1.0
        assert abs(score - 0.5) < 0.01

    def test_invalid_date_raises(self) -> None:
        with pytest.raises(ValueError):
            score_trend_recency({"observed_at": "not-a-date"}, now=date.today())

    def test_zero_window_treated_as_one(self) -> None:
        trend = {"observed_at": "2026-01-01", "decay_window_days": 0}
        assert score_trend_recency(trend, now=date(2026, 1, 1)) == 1.0

    def test_filter_stale_removes_stale(self) -> None:
        trends = [
            {"signal": "fresh", "observed_at": "2026-01-01"},
            {"signal": "stale", "observed_at": "2020-01-01"},
        ]
        result = filter_stale_trends(trends, now=date(2026, 6, 1))
        assert len(result) == 1
        assert result[0]["signal"] == "fresh"

    def test_dedupe_preserves_first(self) -> None:
        trends = [
            {"signal": "Same Trend"},
            {"signal": "same trend"},
            {"signal": "  same   trend  "},
        ]
        result = dedupe_trends(trends)
        assert len(result) == 1

    def test_dedupe_preserves_order(self) -> None:
        trends = [
            {"signal": "first"},
            {"signal": "second"},
            {"signal": "first"},
            {"signal": "third"},
        ]
        result = dedupe_trends(trends)
        assert [t["signal"] for t in result] == ["first", "second", "third"]


# ---------------------------------------------------------------------------
# provenance_audit edge cases
# ---------------------------------------------------------------------------


class TestProvenanceAuditEdgeCases:
    def test_has_citable_evidence_url(self) -> None:
        assert _has_citable_evidence("See https://example.com/report for details")

    def test_has_citable_evidence_named_entity(self) -> None:
        assert _has_citable_evidence("According to Nielsen data")

    def test_has_citable_evidence_generic_token(self) -> None:
        assert _has_citable_evidence("The report shows growth")

    def test_no_evidence_generic_noun_embedding(self) -> None:
        assert not _has_citable_evidence("Reportedly the data clearly shows")

    def test_no_evidence_for_empty(self) -> None:
        assert not _has_citable_evidence("")
        assert not _has_citable_evidence("   ")

    def test_no_evidence_for_vague_claim(self) -> None:
        assert not _has_citable_evidence("the data clearly shows that this works")

    def test_audit_flags_research_grounded_without_citation(self) -> None:
        brief = {
            "recommendations": {
                "arc_type": {
                    "value": "problem-solution",
                    "confidence": "research-grounded",
                    "rationale": "our analysis shows this works best",
                }
            },
            "dimension_verdicts": [],
        }
        flags = audit_intelligence_provenance(brief)
        assert len(flags) == 1
        assert flags[0]["suggested_confidence"] == "pattern-inferred"

    def test_audit_passes_with_url(self) -> None:
        brief = {
            "recommendations": {
                "arc_type": {
                    "value": "problem-solution",
                    "confidence": "research-grounded",
                    "rationale": "See https://adweek.com/study",
                }
            },
            "dimension_verdicts": [],
        }
        flags = audit_intelligence_provenance(brief)
        assert len(flags) == 0

    def test_audit_flags_contradicted_verdict_without_evidence(self) -> None:
        brief = {
            "recommendations": {},
            "dimension_verdicts": [
                {
                    "dimension": "tone",
                    "confidence": "research-grounded",
                    "verdict": "CONTRADICTED",
                    "challenge_evidence": "we disagree with the hypothesis",
                }
            ],
        }
        flags = audit_intelligence_provenance(brief)
        assert len(flags) == 1

    def test_audit_skips_supported_verdicts(self) -> None:
        brief = {
            "recommendations": {},
            "dimension_verdicts": [
                {
                    "dimension": "tone",
                    "confidence": "research-grounded",
                    "verdict": "SUPPORTED",
                    "challenge_evidence": "",
                }
            ],
        }
        flags = audit_intelligence_provenance(brief)
        assert len(flags) == 0

    def test_audit_skips_pattern_inferred_confidence(self) -> None:
        brief = {
            "recommendations": {
                "arc_type": {
                    "value": "problem-solution",
                    "confidence": "pattern-inferred",
                    "rationale": "no evidence at all",
                }
            },
            "dimension_verdicts": [],
        }
        flags = audit_intelligence_provenance(brief)
        assert len(flags) == 0


# ---------------------------------------------------------------------------
# intensity_curve edge cases
# ---------------------------------------------------------------------------


class TestIntensityCurveEdgeCases:
    def test_single_beat(self) -> None:
        beats = [{"beat_name": "HOOK", "duration_seconds": 10, "intensity": 0.8}]
        curve = derive_intensity_curve(beats)
        assert len(curve) > 0
        assert curve[0]["value"] == pytest.approx(0.8)

    def test_empty_beats(self) -> None:
        curve = derive_intensity_curve([])
        assert curve == []

    def test_multiple_beats_produce_samples(self) -> None:
        beats = [
            {"beat_name": "HOOK", "duration_seconds": 10, "intensity": 0.9},
            {"beat_name": "BUILD", "duration_seconds": 20, "intensity": 0.5},
            {"beat_name": "REVEAL", "duration_seconds": 15, "intensity": 1.0},
        ]
        curve = derive_intensity_curve(beats)
        assert len(curve) > 0
        values = [s["value"] for s in curve]
        assert max(values) == pytest.approx(1.0)
        assert min(values) == pytest.approx(0.5)
