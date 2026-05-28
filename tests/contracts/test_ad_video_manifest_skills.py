"""Ad-video manifest/skills/directors/alignment contract regressions."""

from __future__ import annotations

import json
import re
from copy import deepcopy
from pathlib import Path

import pytest

from lib.pipeline_loader import get_required_tools, load_pipeline
from schemas.artifacts import validate_artifact
from tools.analysis.video_analyzer import VideoAnalyzer
from tools.analysis.video_downloader import VideoDownloader
from tools.validation.scene_fidelity_check import check_plan
from tools.video.video_compose import VideoCompose

from tests.contracts.conftest import (
    _approved_hallucination_waiver_log,
    _asset_manifest_for_hallucination,
    _bible_with_truth_contract,
    _hallucination_check,
    _json_fences,
    _load_ad_video_manifest,
    _load_scene_type_registry,
    _minimal_production_proposal,
    _read_skill,
    _scene_plan_for_hallucination,
    _stage_tool_names,
    _trend_alignment_block,
    _trend_threaded_scene_plan,
    _trend_threaded_script,
    _truth_contract,
    ROOT,
)


def test_script_trend_alignment_requires_hook_build_source_refs() -> None:
    """Selected bible trend_alignment refs must reach hook/build script sections."""
    from lib.trend_alignment import check_script_trend_alignment

    bible = {"intelligence": {"trend_alignment": _trend_alignment_block()}}
    script = {
        "sections": [
            {"id": "hook", "beat": "hook", "text": "Three seconds decide the scroll."},
            {
                "id": "build",
                "beat": "build",
                "text": "Then prove it before the viewer asks why.",
                "source_ref": "trend_alignment:trend-tiktok-text-hooks",
            },
        ]
    }

    report = check_script_trend_alignment(bible, script)

    assert report["ok"] is False
    assert any(issue["beat"] == "hook" for issue in report["issues"])

    script["sections"][0]["source_ref"] = "trend_alignment:trend-tiktok-text-hooks"
    assert check_script_trend_alignment(bible, script)["ok"] is True


def test_script_schema_accepts_multiple_source_refs_per_section() -> None:
    """A shared hook/build section may carry multiple trend-alignment refs."""
    voice_performance = {
        "emotion": "intrigue",
        "intonation": "soft rise, clean resolve",
        "rhythm": "short phrase, breath, proof phrase",
        "pace": "measured",
        "pause_after_seconds": 0.25,
    }
    script = {
        "version": "1.0",
        "title": "Multi Trend Script",
        "total_duration_seconds": 3,
        "user_approved": True,
        "sections": [
            {
                "id": "hook",
                "beat": "hook",
                "text": "Three seconds decide the scroll.",
                "start_seconds": 0,
                "end_seconds": 3,
                "source_refs": [
                    "trend_alignment:trend-tiktok-text-hooks",
                    "trend_alignment:trend-mute-friendly-format",
                ],
                "speaker_directions": "Measured and immediate.",
                "voice_performance": voice_performance,
                "tts_directive": {"speed_mult": 0.96},
            }
        ],
    }

    validate_artifact("script", script, pipeline_type="ad-video")


def test_script_trend_alignment_allows_multiple_refs_on_shared_sections() -> None:
    """Multiple selected hook/build trends should not require duplicate sections."""
    from lib.trend_alignment import check_script_trend_alignment

    trend_alignment = _trend_alignment_block()
    second = deepcopy(trend_alignment["alignments"][0])
    second["trend_id"] = "trend-mute-friendly-format"
    second["signal"] = "Mute-friendly captions are a platform baseline."
    second["trend_type"] = "platform_format_norm"
    second["script_usage"]["source_ref"] = "trend_alignment:trend-mute-friendly-format"
    second["script_usage"]["usage_note"] = "Keep the hook understandable without audio."
    trend_alignment["selected_trend_ids"].append("trend-mute-friendly-format")
    trend_alignment["alignments"].append(second)
    bible = {"intelligence": {"trend_alignment": trend_alignment}}
    script = {
        "sections": [
            {
                "id": "hook",
                "beat": "hook",
                "text": "Three seconds decide the scroll.",
                "source_refs": [
                    "trend_alignment:trend-tiktok-text-hooks",
                    "trend_alignment:trend-mute-friendly-format",
                ],
            },
            {
                "id": "build",
                "beat": "build",
                "text": "Then prove it before the viewer asks why.",
                "source_refs": [
                    "trend_alignment:trend-tiktok-text-hooks",
                    "trend_alignment:trend-mute-friendly-format",
                ],
            },
        ]
    }

    report = check_script_trend_alignment(bible, script)

    assert report["ok"] is True
    assert report["issues"] == []


def test_scene_plan_trend_alignment_requires_scene_for_visual_trend() -> None:
    """Each selected visual trend must have at least one scene carrying its ref."""
    from lib.trend_alignment import check_scene_plan_trend_alignment

    bible = {"intelligence": {"trend_alignment": _trend_alignment_block()}}
    scene_plan = {
        "scenes": [
            {
                "id": "scene-1",
                "beat": "hook",
                "description": "Product UI reveal without trend-specific pacing.",
            }
        ]
    }

    report = check_scene_plan_trend_alignment(bible, scene_plan)

    assert report["ok"] is False
    assert any(issue["trend_id"] == "trend-tiktok-text-hooks" for issue in report["issues"])

    scene_plan["scenes"][0]["trend_alignment_refs"] = ["trend_alignment:trend-tiktok-text-hooks"]
    scene_plan["scenes"][0]["trend_alignment_notes"] = (
        "Native overlay text lands on the first visual beat; no viral layout copied."
    )
    assert check_scene_plan_trend_alignment(bible, scene_plan)["ok"] is True


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
                "type": "animation",
                "scene_type": "text_card",
                "description": "Native overlay text lands on the first visual beat.",
                "start_seconds": 0,
                "end_seconds": 4,
                "beat": "hook",
                "product_visibility": "none",
                "product_reference_required": False,
                "core": True,
                "motion_required": True,
                "fulfills_kvm": [],
                "motion_specs": ["text_entrance_fade"],
                "trend_alignment_refs": [source_ref],
                "trend_alignment_notes": "Warm native pacing is adapted without copying source captions, audio, or shot order.",
                "knowledge_alignment_refs": ["knowledge_alignment:hook.visual-contrast.001"],
                "knowledge_alignment_notes": "Opening scene uses a visible before/after contrast without turning into clickbait.",
            }
        ],
    }


def test_ad_video_planning_chain_check_rejects_unthreaded_selected_trends() -> None:
    """The pre-asset gate must fail when selected trends stop at the bible."""
    from tests.qa.test_artifact_chain import PRODUCTION_BIBLE_VALID
    from tools.validation.ad_video_planning_chain_check import AdVideoPlanningChainCheck

    bible = deepcopy(PRODUCTION_BIBLE_VALID)
    script = _trend_threaded_script()
    scene_plan = _trend_threaded_scene_plan()
    del script["sections"][0]["source_ref"]
    script["sections"][0].pop("source_refs", None)

    result = AdVideoPlanningChainCheck().execute({
        "production_bible": bible,
        "script": script,
        "scene_plan": scene_plan,
    })

    assert result.success is False
    assert "missing_trend_source_ref" in (result.error or "")

    script = _trend_threaded_script()
    scene_plan["scenes"][0].pop("trend_alignment_refs")
    result = AdVideoPlanningChainCheck().execute({
        "production_bible": bible,
        "script": script,
        "scene_plan": scene_plan,
    })

    assert result.success is False
    assert "missing_scene_trend_alignment" in (result.error or "")

    bible_without_alignments = deepcopy(PRODUCTION_BIBLE_VALID)
    bible_without_alignments["intelligence"]["trend_alignment"]["selected_trend_ids"] = [
        "trend-tiktok-lofi-hook"
    ]
    bible_without_alignments["intelligence"]["trend_alignment"]["alignments"] = []
    result = AdVideoPlanningChainCheck().execute({
        "production_bible": bible_without_alignments,
        "script": _trend_threaded_script(),
        "scene_plan": _trend_threaded_scene_plan(),
    })

    assert result.success is False
    assert "missing_selected_trend_alignment" in (result.error or "")


def test_ad_video_planning_chain_check_rejects_unthreaded_selected_knowledge() -> None:
    """The pre-asset gate must fail when selected producer knowledge stops at the bible."""
    from tests.qa.test_artifact_chain import PRODUCTION_BIBLE_VALID
    from tools.validation.ad_video_planning_chain_check import AdVideoPlanningChainCheck

    bible = deepcopy(PRODUCTION_BIBLE_VALID)
    script = _trend_threaded_script()
    scene_plan = _trend_threaded_scene_plan()
    script["sections"][0]["source_ref"] = "trend_alignment:trend-tiktok-lofi-hook"
    script["sections"][0].pop("source_refs", None)

    result = AdVideoPlanningChainCheck().execute({
        "production_bible": bible,
        "script": script,
        "scene_plan": scene_plan,
    })

    assert result.success is False
    assert "missing_knowledge_source_ref" in (result.error or "")

    knowledge_ref = "knowledge_alignment:hook.visual-contrast.001"
    script["sections"][0]["source_refs"] = [
        "trend_alignment:trend-tiktok-lofi-hook",
        knowledge_ref,
    ]
    scene_plan["scenes"][0]["knowledge_alignment_refs"] = [knowledge_ref]
    scene_plan["scenes"][0]["knowledge_alignment_notes"] = (
        "Opening scene uses a visible before/after contrast without turning into clickbait."
    )

    result = AdVideoPlanningChainCheck().execute({
        "production_bible": bible,
        "script": script,
        "scene_plan": scene_plan,
    })

    assert result.success is True
    assert result.data["knowledge_alignment"]["ok"] is True


def test_ad_video_planning_chain_check_rejects_missing_selected_knowledge_card() -> None:
    """Conflict detection must not pass when selected card ids cannot be resolved."""
    from tools.validation.ad_video_planning_chain_check import AdVideoPlanningChainCheck

    bible = {
        "intelligence": {
            "trend_alignment": {
                "alignments": [
                    {
                        "trend_id": "trend-overload",
                        "scene_usage": {
                            "visual_or_pacing_instruction": (
                                "Overload the frame with rapid product claim text"
                            )
                        },
                    }
                ]
            },
            "knowledge_alignment": {
                "selected_card_ids": ["knowledge.missing.001"],
                "alignments": [
                    {
                        "card_id": "knowledge.missing.001",
                        "do_not_overapply": [
                            "Overload the frame with rapid product claim text"
                        ],
                    }
                ],
            },
        }
    }

    report = AdVideoPlanningChainCheck()._check_conflicts(bible)

    assert report["ok"] is False
    assert report["conflicts"][0]["kind"] == "missing_selected_knowledge_card"
    assert report["conflicts"][0]["card_id"] == "knowledge.missing.001"


def test_ad_video_planning_chain_check_rejects_knowledge_card_load_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """Knowledge-card integrity failures must fail the pre-asset conflict gate."""
    import lib.ad_knowledge
    from tools.validation.ad_video_planning_chain_check import AdVideoPlanningChainCheck

    def broken_loader() -> list[dict]:
        raise ValueError("content_hash mismatch")

    monkeypatch.setattr(lib.ad_knowledge, "load_ad_knowledge_cards", broken_loader)

    bible = {
        "intelligence": {
            "trend_alignment": {"alignments": []},
            "knowledge_alignment": {
                "selected_card_ids": ["hook.visual-contrast.001"],
                "alignments": [{"card_id": "hook.visual-contrast.001"}],
            },
        }
    }

    report = AdVideoPlanningChainCheck()._check_conflicts(bible)

    assert report["ok"] is False
    assert report["conflicts"][0]["kind"] == "knowledge_card_load_failed"
    assert "content_hash mismatch" in report["conflicts"][0]["detail"]


def test_ad_video_planning_chain_check_accepts_fresh_threaded_chain() -> None:
    """A fresh planning chain with selected trends in bible, script, and scene plan passes."""
    from tests.qa.test_artifact_chain import PRODUCTION_BIBLE_VALID
    from tools.validation.ad_video_planning_chain_check import AdVideoPlanningChainCheck

    result = AdVideoPlanningChainCheck().execute({
        "production_bible": deepcopy(PRODUCTION_BIBLE_VALID),
        "script": _trend_threaded_script(),
        "scene_plan": _trend_threaded_scene_plan(),
    })

    assert result.success is True
    assert result.data["trend_alignment"]["ok"] is True


def test_ad_video_manifest_exposes_planning_chain_gate_before_assets() -> None:
    """The pipeline must surface the planning-chain gate before asset generation."""
    manifest = _load_ad_video_manifest()
    asset_stage = next(stage for stage in manifest["stages"] if stage["name"] == "assets")
    compose_stage = next(stage for stage in manifest["stages"] if stage["name"] == "compose")
    asset_director = _read_skill("asset-director.md")
    compose_director = _read_skill("compose-director.md")

    asset_tools = set(asset_stage.get("required_tools", []))
    asset_tools.update(asset_stage.get("optional_tools", []))
    asset_tools.update(asset_stage.get("tools_available", []))
    compose_tools = set(compose_stage.get("required_tools", []))
    compose_tools.update(compose_stage.get("optional_tools", []))
    compose_tools.update(compose_stage.get("tools_available", []))

    assert "ad_video_planning_chain_check" in asset_tools
    assert "ad_video_planning_chain_check" in compose_tools
    assert "ad_video_planning_chain_check" in get_required_tools(manifest)
    assert {"production_bible", "script", "scene_plan"}.issubset(
        set(compose_stage["required_artifacts_in"])
    )
    assert "ad_video_planning_chain_check" in asset_director
    assert "ad_video_planning_chain_check" in compose_director
    assert "Do not treat missing planning artifacts as permission to skip" in compose_director


def test_ad_video_manifest_and_skills_require_professional_knowledge_retrieval() -> None:
    """Professional producer knowledge must be a real intelligence-stage contract."""
    manifest = _load_ad_video_manifest()
    stages = {stage["name"]: stage for stage in manifest["stages"]}

    intelligence_stage = stages["intelligence"]
    assert "ad_knowledge_retriever" in _stage_tool_names(intelligence_stage)
    assert any("professional_knowledge" in item for item in intelligence_stage["review_focus"])
    assert any("professional_knowledge" in item for item in intelligence_stage["success_criteria"])

    intelligence_director = _read_skill("intelligence-director.md")
    bible_director = _read_skill("bible-director.md")
    script_director = _read_skill("script-director.md")
    scene_director = _read_skill("scene-director.md")

    assert "ad_knowledge_retriever" in intelligence_director
    assert "professional_knowledge" in intelligence_director
    assert "knowledge_alignment" in bible_director
    assert "knowledge_alignment" in script_director
    assert "check_script_knowledge_alignment" in script_director
    assert "knowledge_alignment_refs" in scene_director
    assert "check_scene_plan_knowledge_alignment" in scene_director


def test_ad_video_manifest_declares_genui_form_for_form_first_gates() -> None:
    """Form-first human gates must make genui_form visible to preflight audits."""
    manifest = load_pipeline("ad-video")
    stages = {stage["name"]: stage for stage in manifest["stages"]}

    for stage_name in ["brief_enrichment", "bible", "proposal", "script"]:
        assert "genui_form" in _stage_tool_names(stages[stage_name]), stage_name

    asset_substages = {
        substage["name"]: substage for substage in stages["assets"].get("sub_stages", [])
    }
    for substage_name in ["product_reference", "asset_review"]:
        assert "genui_form" in asset_substages[substage_name].get("tools_available", []), substage_name

    assert "genui_form" in get_required_tools(manifest)


def test_ad_video_director_intros_name_manifest_required_inputs() -> None:
    """A fresh agent should see every required stage input in the director intro."""
    manifest = load_pipeline("ad-video")

    for stage in manifest["stages"]:
        required_inputs = set(stage.get("required_artifacts_in", []))
        if not required_inputs:
            continue

        skill_ref = stage["skill"].removeprefix("pipelines/ad-video/")
        skill_text = _read_skill(f"{skill_ref}.md")
        intro = skill_text.split("## When to Use", 1)[1].split("\n## ", 1)[0]
        missing = sorted(name for name in required_inputs if name not in intro)

        assert missing == [], (
            f"{skill_ref}.md intro omits manifest-required input(s): {missing}"
        )


def test_video_analysis_detects_chinese_short_video_platforms() -> None:
    """Bilibili, Douyin, and Kuaishou must not collapse into generic other_url."""
    analyzer = VideoAnalyzer()
    downloader = VideoDownloader()

    cases = [
        ("https://www.bilibili.com/video/BV1xx411c7mD", "bilibili"),
        ("https://b23.tv/abc123", "bilibili"),
        ("https://www.douyin.com/video/7333333333333333333", "douyin"),
        ("https://v.douyin.com/iabc123/", "douyin"),
        ("https://www.kuaishou.com/short-video/3xabc123", "kuaishou"),
        ("https://v.kuaishou.com/abc123", "kuaishou"),
        ("https://www.kwai.com/@creator/video/123", "kuaishou"),
    ]

    for url, expected in cases:
        assert analyzer._detect_platform(url) == expected
        assert downloader._detect_platform(url) == expected

        validate_artifact(
            "video_analysis_brief",
            {
                "version": "1.0",
                "source": {"type": expected, "duration_seconds": 10},
                "content_analysis": {
                    "summary": "Reference ad summary.",
                    "topics": ["ad"],
                    "target_audience": "general",
                },
                "structure_analysis": {
                    "total_scenes": 0,
                    "scenes": [],
                    "pacing_profile": {},
                },
            },
        )


def test_ad_video_contract_mentions_trend_alignment_flow() -> None:
    """Manifest and director skills must expose selected-trend propagation."""
    manifest = _load_ad_video_manifest()
    intelligence = _read_skill("intelligence-director.md")
    bible = _read_skill("bible-director.md")
    script = _read_skill("script-director.md")
    scene = _read_skill("scene-director.md")

    intelligence_stage = next(stage for stage in manifest["stages"] if stage["name"] == "intelligence")
    bible_stage = next(stage for stage in manifest["stages"] if stage["name"] == "bible")
    script_stage = next(stage for stage in manifest["stages"] if stage["name"] == "script")
    scene_stage = next(stage for stage in manifest["stages"] if stage["name"] == "scene_plan")
    contract_text = "\n".join(
        intelligence_stage.get("review_focus", [])
        + bible_stage.get("review_focus", [])
        + bible_stage.get("success_criteria", [])
        + script_stage.get("review_focus", [])
        + script_stage.get("success_criteria", [])
        + scene_stage.get("review_focus", [])
        + scene_stage.get("success_criteria", [])
    )

    assert "sentiment" in contract_text
    assert "brand_safety" in contract_text
    assert "trend_alignment" in contract_text
    assert "source_ref" in contract_text
    assert "trend_alignment_refs" in contract_text

    assert "`sentiment`" in intelligence
    assert "`brand_safety`" in intelligence
    assert "select_trends_for_alignment" in bible
    assert "`production_bible.intelligence.trend_alignment`" in bible
    assert "`source_ref`" in script
    assert "check_script_trend_alignment" in script
    assert "`trend_alignment_refs`" in scene
    assert "check_scene_plan_trend_alignment" in scene


def test_trend_alignment_guard_rejects_missing_block() -> None:
    """A production_bible with no trend_alignment key fails the planning check."""
    from lib.trend_alignment import check_ad_video_planning_trend_alignment

    bible_no_block = {"intelligence": {}}
    report = check_ad_video_planning_trend_alignment(
        bible_no_block, {"sections": []}, {"scenes": []}
    )
    assert report["ok"] is False
    assert any(i["kind"] == "trend_alignment_block_missing" for i in report["issues"])


def test_trend_alignment_guard_rejects_block_without_selected_ids() -> None:
    """A trend_alignment block missing selected_trend_ids also fails."""
    from lib.trend_alignment import check_ad_video_planning_trend_alignment

    bible = {"intelligence": {"trend_alignment": {"alignments": []}}}
    report = check_ad_video_planning_trend_alignment(
        bible, {"sections": []}, {"scenes": []}
    )
    assert report["ok"] is False
    assert any(i["kind"] == "trend_alignment_selection_skipped" for i in report["issues"])


def test_trend_alignment_guard_passes_explicit_empty_selection() -> None:
    """An explicit selected_trend_ids: [] with empty alignments is valid."""
    from lib.trend_alignment import check_ad_video_planning_trend_alignment

    bible = {"intelligence": {"trend_alignment": {"selected_trend_ids": [], "alignments": []}}}
    report = check_ad_video_planning_trend_alignment(
        bible, {"sections": []}, {"scenes": []}
    )
    assert report["ok"] is True


def test_knowledge_alignment_guard_rejects_missing_block() -> None:
    """A production_bible with no knowledge_alignment key fails the planning check."""
    from lib.knowledge_alignment import check_ad_video_planning_knowledge_alignment

    bible_no_block = {"intelligence": {}}
    report = check_ad_video_planning_knowledge_alignment(
        bible_no_block, {"sections": []}, {"scenes": []}
    )
    assert report["ok"] is False
    assert any(i["kind"] == "knowledge_alignment_block_missing" for i in report["issues"])


def test_knowledge_alignment_guard_rejects_block_without_selected_ids() -> None:
    """A knowledge_alignment block missing selected_card_ids also fails."""
    from lib.knowledge_alignment import check_ad_video_planning_knowledge_alignment

    bible = {"intelligence": {"knowledge_alignment": {"alignments": []}}}
    report = check_ad_video_planning_knowledge_alignment(
        bible, {"sections": []}, {"scenes": []}
    )
    assert report["ok"] is False
    assert any(i["kind"] == "knowledge_alignment_selection_skipped" for i in report["issues"])


def test_knowledge_alignment_guard_passes_explicit_empty_selection() -> None:
    """An explicit selected_card_ids: [] with empty alignments is valid."""
    from lib.knowledge_alignment import check_ad_video_planning_knowledge_alignment

    bible = {"intelligence": {"knowledge_alignment": {"selected_card_ids": [], "alignments": []}}}
    report = check_ad_video_planning_knowledge_alignment(
        bible, {"sections": []}, {"scenes": []}
    )
    assert report["ok"] is True


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


def test_ad_video_ep_reads_proposal_locks_after_proposal_approval() -> None:
    """EP_STATE must use proposal-stage locks, not optional bible audit copies."""
    ep = _read_skill("executive-producer.md")

    assert "`style_mode` from `production_proposal.style_mode`" in ep
    assert "`render_runtime` from `production_proposal.render_runtime`" in ep
    assert "`derivative_variants` from `production_proposal.derivatives_added`" in ep
    assert "`render_runtime` from `production_bible.visual.render_runtime`" not in ep
    assert "`derivative_variants` from `production_bible.deliverables.derivatives`" not in ep
    assert "render_runtime locked in production_bible.visual.render_runtime" not in ep


def test_brief_enrichment_director_references_artifact_schema_path() -> None:
    """Skill prerequisites should point to the real schema location."""
    brief_enrichment = _read_skill("brief-enrichment-director.md")

    assert "schemas/artifacts/enriched_brief.schema.json" in brief_enrichment
    assert "schemas/enriched_brief.schema.json" not in brief_enrichment


def test_brief_enrichment_director_requires_creative_requirements_worksheet_before_g0() -> None:
    """Every ad-video brief must pass a structured creative-director worksheet before G-0."""
    brief_enrichment = _read_skill("brief-enrichment-director.md")

    assert "Creative Requirements Worksheet" in brief_enrichment
    assert "`creative_requirements`" in brief_enrichment
    assert "`product_model`" in brief_enrichment
    assert "`core_selling_points`" in brief_enrichment
    assert "`platform_duration`" in brief_enrichment
    assert "`target_audience`" in brief_enrichment
    assert "`tone_style`" in brief_enrichment
    assert "`visual_approach`" in brief_enrichment
    assert "`language_voiceover`" in brief_enrichment
    assert "`mandatory_marketing`" in brief_enrichment
    assert "`cta`" in brief_enrichment
    assert "`product_fidelity_references`" in brief_enrichment
    assert "`truth_and_safety_constraints`" in brief_enrichment
    assert "RECOMMEND FOR ME" in brief_enrichment
    assert "FROM BRIEF or DELEGATED" in brief_enrichment


def test_intelligence_director_validates_delegated_dimensions() -> None:
    """Delegated dimensions are recommendations, so intelligence must validate them."""
    intelligence = _read_skill("intelligence-director.md")

    assert "status == \"INFERRED\" or status == \"DELEGATED\"" in intelligence
    assert "DELEGATED" in intelligence
    assert "FROM BRIEF" in intelligence


def test_executive_producer_gate_g0_checks_creative_requirements() -> None:
    """EP Gate G-0 must block if the worksheet is missing or silently inferred."""
    ep = _read_skill("executive-producer.md")

    assert "creative_requirements" in ep
    assert "product_model" in ep
    assert "product_fidelity_references" in ep
    assert "truth_and_safety_constraints" in ep
    assert "FROM BRIEF or DELEGATED" in ep


def test_ad_video_manifest_brief_enrichment_review_focus_checks_creative_requirements() -> None:
    """Manifest review focus should make worksheet completeness a stage contract."""
    manifest = _load_ad_video_manifest()
    brief_enrichment_stage = next(stage for stage in manifest["stages"] if stage["name"] == "brief_enrichment")
    focus_text = "\n".join(brief_enrichment_stage.get("review_focus", []))

    assert "creative_requirements" in focus_text
    assert "FROM BRIEF or DELEGATED" in focus_text
    assert "No required worksheet dimension is INFERRED" in focus_text


def test_ad_video_manifest_proposal_success_criteria_use_proposal_locks() -> None:
    """The manifest should not require back-writing proposal locks into bible."""
    manifest = _load_ad_video_manifest()
    proposal_stage = next(stage for stage in manifest["stages"] if stage["name"] == "proposal")
    success_text = "\n".join(proposal_stage.get("success_criteria", []))

    assert "production_proposal.render_runtime" in success_text
    assert "production_proposal.derivatives_added" in success_text
    assert "production_bible.visual.render_runtime" not in success_text
    assert "deliverables.derivatives populated in production_bible" not in success_text


def test_executive_producer_script_gate_uses_locked_audio_contract_rate() -> None:
    """EP script review must mirror script-director's target_speed_wps contract."""
    ep = _read_skill("executive-producer.md")

    assert "production_proposal.audio_contract.target_speed_wps" in ep
    assert "target_words = target_duration_seconds × 2.5" not in ep


def test_ad_video_manifest_script_gate_uses_locked_audio_contract_rate() -> None:
    """The manifest script-stage review contract must match the EP/script-director gate."""
    manifest = _load_ad_video_manifest()
    script_stage = next(stage for stage in manifest["stages"] if stage["name"] == "script")
    gate_text = "\n".join(
        script_stage.get("review_focus", []) + script_stage.get("success_criteria", [])
    )

    assert "production_proposal.audio_contract.target_speed_wps" in gate_text
    assert "target_duration_seconds × 2.5" not in gate_text


def test_proposal_director_does_not_teach_backwriting_locks_to_bible() -> None:
    """Proposal should produce production_proposal locks instead of mutating bible locks."""
    proposal = _read_skill("proposal-director.md")

    assert "Populate `deliverables.derivatives` in production_bible" not in proposal
    assert "Lock `visual.style_mode` in production_bible" not in proposal
    assert "Lock `visual.render_runtime` in production_bible" not in proposal
    assert "`production_proposal.derivatives_added[]`" in proposal
    assert "`production_proposal.render_runtime`" in proposal


def test_video_compose_render_accepts_artifact_paths(tmp_path: Path) -> None:
    """The tool may receive path strings from older directors; it must coerce them."""
    edit_path = tmp_path / "edit_decisions.json"
    asset_path = tmp_path / "asset_manifest.json"
    edit_path.write_text(
        json.dumps({"version": "1.0", "render_runtime": "ffmpeg", "cuts": []}),
        encoding="utf-8",
    )
    asset_path.write_text(json.dumps({"assets": []}), encoding="utf-8")

    result = VideoCompose().execute(
        {
            "operation": "render",
            "edit_decisions": str(edit_path),
            "asset_manifest": str(asset_path),
        }
    )

    assert result.success is False
    assert result.error == "No cuts in edit_decisions"


def test_edit_director_json_examples_do_not_teach_legacy_shape() -> None:
    text = _read_skill("edit-director.md")

    for block in _json_fences(text):
        assert '"timeline"' not in block
        assert '"source_file"' not in block
        assert '"burn_in"' not in block


def test_ad_video_directors_reference_current_contract_names() -> None:
    asset = _read_skill("asset-director.md")
    proposal = _read_skill("proposal-director.md")
    compose = _read_skill("compose-director.md")
    publish = _read_skill("publish-director.md")
    animated_scene = _read_skill("scene-director-animated.md")

    assert 'production_plan["voice_selection"]["voice_id"]' not in asset
    assert 'audio_contract = production_proposal["audio_contract"]' in asset
    assert 'audio_contract["voice_id"]' in asset
    assert 'model = audio_contract["voice_model"]' in asset
    assert "voice_performance" in asset
    assert "speaker_directions" in asset

    assert 'either `"remotion"` or `"hyperframes"`' not in proposal
    assert '"ffmpeg"' in proposal
    assert '"voice_model": "qwen3-tts-instruct-flash"' in proposal
    assert "voice_performance" in proposal
    assert "voice_sample_approved" in proposal
    assert "Populate `deliverables.derivatives` in production_bible" not in proposal
    assert "Lock `visual.render_runtime` in production_bible" not in proposal

    assert '"edit_decisions": "projects/<name>/artifacts/edit_decisions.json"' not in compose
    assert '"asset_manifest": "projects/<name>/artifacts/asset_manifest.json"' not in compose
    assert "render_report.output_files" not in publish
    assert "render_report.outputs" in publish

    assert "production_bible.kvms" not in animated_scene
    assert "production_bible.visual.key_visual_moments" in animated_scene


def test_ad_video_scene_and_edit_directors_enforce_editing_rhythm_contract() -> None:
    scene = _read_skill("scene-director.md")
    edit = _read_skill("edit-director.md")

    assert "production_bible.visual.editing_rhythm" in scene
    assert "scene count" in scene
    assert "scene duration" in scene
    assert "transition_style" in scene

    assert "production_bible.visual.editing_rhythm" in edit
    assert "maps_to_beat" in edit
    assert "scene.get(\"beat\")" in edit or "scene.beat" in edit
    assert "audio.music.volume_schedule" in edit


def test_ad_video_contract_mentions_product_identity_reference_flow() -> None:
    manifest = _load_ad_video_manifest()
    guide = (ROOT / "AGENT_GUIDE.md").read_text(encoding="utf-8")
    brief_enrichment = _read_skill("brief-enrichment-director.md")
    proposal = _read_skill("proposal-director.md")
    scene = _read_skill("scene-director.md")
    asset = _read_skill("asset-director.md")
    ep = _read_skill("executive-producer.md")

    proposal_stage = next(stage for stage in manifest["stages"] if stage["name"] == "proposal")
    scene_stage = next(stage for stage in manifest["stages"] if stage["name"] == "scene_plan")
    asset_stage = next(stage for stage in manifest["stages"] if stage["name"] == "assets")
    asset_substage_names = [substage["name"] for substage in asset_stage.get("sub_stages", [])]
    contract_text = "\n".join(
        proposal_stage.get("review_focus", [])
        + proposal_stage.get("success_criteria", [])
        + scene_stage.get("review_focus", [])
        + scene_stage.get("success_criteria", [])
        + asset_stage.get("review_focus", [])
        + asset_stage.get("success_criteria", [])
    )

    assert "product_reference_strategy" in contract_text
    assert "product_identity_reference" in asset_stage.get("produces", [])
    assert "product_reference" in asset_substage_names
    assert "no text-only" in contract_text.lower()
    assert "Product Identity Reference" in brief_enrichment
    assert "`product_reference_strategy`" in proposal
    assert "`product_visibility`" in scene
    assert "`product_reference_required`" in scene
    assert "product_identity_consistency_check" in asset
    assert "generated_scene_ids" in asset
    assert asset.index("## Product Reference Sub-Stage") < asset.index("## Sample Sub-Stage")
    assert "sample sub-stage first" not in asset
    assert "product_identity_reference_selection" in proposal
    assert "product_identity_reference_selection" in ep
    assert "`product_identity_reference` + `asset_manifest`" in guide


def test_product_visible_remotion_scene_registry_requires_approved_product_image() -> None:
    registry = _load_scene_type_registry()
    scene_types = registry["scene_types"]

    creator = scene_types["creator_workflow_scene"]
    assert "productImage" in creator["required_cut_props"]
    assert "generic hardware" in creator["description"]

    brand = scene_types["brand_card"]
    assert "productImage" in brand["optional_props"]
    assert "hardwareTreatment" in brand["optional_props"]
    assert brand["motion_required_cut_props"]["product_scale_reveal"]["any_of"] == [
        "productImage",
        "hardwareTreatment",
    ]
    assert "Text-only by default" in brand["description"]
    assert "creator_workflow_scene" in VideoCompose._REMOTION_COMPONENTS
    assert "brand_card" in VideoCompose._REMOTION_COMPONENTS


def test_scene_fidelity_rejects_creator_workflow_without_product_image() -> None:
    registry = _load_scene_type_registry()
    missing_product = {
        "cuts": [
            {
                "id": "scene-1",
                "type": "creator_workflow_scene",
                "source": "remotion:creator_workflow_scene",
                "in_seconds": 0,
                "out_seconds": 4,
                "motion_specs": ["product_scale_reveal"],
            }
        ]
    }

    report = check_plan(missing_product, registry)

    assert report["ok"] is False
    assert any(issue["kind"] == "missing_required_props" for issue in report["issues"])

    with_product = deepcopy(missing_product)
    with_product["cuts"][0]["productImage"] = "reference_assets/product.png"

    assert check_plan(with_product, registry)["ok"] is True


def test_scene_fidelity_rejects_brand_card_product_reveal_without_product_visual() -> None:
    registry = _load_scene_type_registry()
    missing_product_visual = {
        "cuts": [
            {
                "id": "scene-cta",
                "type": "brand_card",
                "source": "remotion:brand_card",
                "in_seconds": 0,
                "out_seconds": 4,
                "motion_specs": ["product_scale_reveal"],
            }
        ]
    }

    report = check_plan(missing_product_visual, registry)

    assert report["ok"] is False
    assert any(
        issue["kind"] == "missing_motion_required_props" for issue in report["issues"]
    )

    with_product_image = deepcopy(missing_product_visual)
    with_product_image["cuts"][0]["productImage"] = "reference_assets/product.png"

    assert check_plan(with_product_image, registry)["ok"] is True

    with_hardware_treatment = deepcopy(missing_product_visual)
    with_hardware_treatment["cuts"][0]["hardwareTreatment"] = "synthetic_laptop"

    assert check_plan(with_hardware_treatment, registry)["ok"] is True


def test_remotion_product_components_do_not_render_synthetic_hardware_by_default() -> None:
    brand_source = (
        ROOT / "remotion-composer" / "src" / "components" / "BrandCardScene.tsx"
    ).read_text(encoding="utf-8")
    workflow_source = (
        ROOT / "remotion-composer" / "src" / "components" / "CreatorWorkflowScene.tsx"
    ).read_text(encoding="utf-8")

    for source in (brand_source, workflow_source):
        assert "<ProductImageMotion" in source
        assert 'hardwareTreatment === "synthetic_laptop"' in source
        assert "void productImage" not in source

    assert "hasProductImage || showSyntheticHardware" in brand_source
    assert "hasProductImage && productImage" in workflow_source


def test_ad_video_contract_mentions_hallucination_flow() -> None:
    """Manifest and director skills must expose the truth-contract review flow."""
    manifest = _load_ad_video_manifest()
    guide = (ROOT / "AGENT_GUIDE.md").read_text(encoding="utf-8")
    reviewer = (ROOT / "skills" / "meta" / "reviewer.md").read_text(encoding="utf-8")
    bible = _read_skill("bible-director.md")
    scene = _read_skill("scene-director.md")
    asset = _read_skill("asset-director.md")
    cinematic_asset = _read_skill("asset-director-cinematic.md")
    animated_asset = _read_skill("asset-director-animated.md")
    ep = _read_skill("executive-producer.md")

    brief_enrichment_stage = next(stage for stage in manifest["stages"] if stage["name"] == "brief_enrichment")
    bible_stage = next(stage for stage in manifest["stages"] if stage["name"] == "bible")
    scene_stage = next(stage for stage in manifest["stages"] if stage["name"] == "scene_plan")
    asset_stage = next(stage for stage in manifest["stages"] if stage["name"] == "assets")
    compose_stage = next(stage for stage in manifest["stages"] if stage["name"] == "compose")
    publish_stage = next(stage for stage in manifest["stages"] if stage["name"] == "publish")
    contract_text = "\n".join(
        brief_enrichment_stage.get("review_focus", [])
        + bible_stage.get("review_focus", [])
        + bible_stage.get("success_criteria", [])
        + scene_stage.get("review_focus", [])
        + scene_stage.get("success_criteria", [])
        + asset_stage.get("review_focus", [])
        + asset_stage.get("success_criteria", [])
        + compose_stage.get("review_focus", [])
        + publish_stage.get("review_focus", [])
    )

    assert "truth_and_safety_constraints" in contract_text
    assert "truth_contract" in contract_text
    assert "hallucination_checks" in contract_text
    assert "hallucination_review" in contract_text
    assert "hallucination_contract_check" in contract_text
    assert "generated_scene_ids" in contract_text
    assert "FLAG" in contract_text
    assert "hallucination_review_waiver" in contract_text

    assert "`production_bible.truth_contract`" in guide
    assert "`hallucination_checks[]`" in guide
    assert "`asset_manifest.assets[].hallucination_review`" in guide
    assert "`hallucination_review_waiver`" in guide
    assert "production_bible.truth_contract" in bible
    assert "`scene_plan.scenes[].hallucination_checks[]`" in bible
    assert "`hallucination_checks[]`" in scene
    assert "hallucination_contract_check" in asset
    assert (
        "generated_scene_ids` to both `product_identity_consistency_check` "
        "and `hallucination_contract_check`"
    ) in asset
    assert "hallucination_review" in cinematic_asset
    assert "hallucination_review" in animated_asset
    assert "hallucination_contract_check" in ep
    assert "Ad-Video Hallucination Review" in reviewer


def test_ad_video_asset_stage_exposes_frame_sampler_for_hallucination_keyframes() -> None:
    manifest = _load_ad_video_manifest()
    asset_stage = next(stage for stage in manifest["stages"] if stage["name"] == "assets")

    asset_stage_tools = set(asset_stage.get("required_tools", []))
    asset_stage_tools.update(asset_stage.get("optional_tools", []))
    asset_stage_tools.update(asset_stage.get("tools_available", []))

    assert "frame_sampler" in asset_stage_tools
    assert "frame_sampler" in get_required_tools(manifest)


def test_ad_video_validation_gates_are_registry_tools_and_manifest_visible() -> None:
    """Hard ad-video gates must be discoverable through the registry and manifest."""
    from tools.tool_registry import registry

    expected_tools = {
        "hallucination_contract_check",
        "product_identity_consistency_check",
        "runtime_consistency_check",
        "sample_product_visibility_check",
        "scene_fidelity_check",
    }
    manifest = load_pipeline("ad-video")
    registry.clear()
    registry.discover()

    missing_registry_tools = expected_tools - set(registry.list_all())
    assert missing_registry_tools == set()
    assert expected_tools <= get_required_tools(manifest)

    asset_stage = next(stage for stage in manifest["stages"] if stage["name"] == "assets")
    asset_tools = _stage_tool_names(asset_stage)
    for sub_stage in asset_stage.get("sub_stages", []):
        asset_tools.update(sub_stage.get("tools_available", []))
    assert {
        "hallucination_contract_check",
        "product_identity_consistency_check",
        "sample_product_visibility_check",
    } <= asset_tools

    compose_stage = next(stage for stage in manifest["stages"] if stage["name"] == "compose")
    assert {
        "hallucination_contract_check",
        "runtime_consistency_check",
        "scene_fidelity_check",
    } <= _stage_tool_names(compose_stage)


def test_ad_video_proposal_produces_decision_log_for_locked_choices() -> None:
    manifest = load_pipeline("ad-video")
    proposal_stage = next(stage for stage in manifest["stages"] if stage["name"] == "proposal")
    proposal = _read_skill("proposal-director.md")

    assert "decision_log" in proposal_stage.get("produces", [])
    assert "render_runtime_selection" in proposal
    assert "product_identity_reference_selection" in proposal
    assert "music_strategy_selection" in proposal


def test_ad_video_edit_stage_declares_proposal_input_for_locked_choices() -> None:
    manifest = load_pipeline("ad-video")
    edit_stage = next(stage for stage in manifest["stages"] if stage["name"] == "edit")
    edit = _read_skill("edit-director.md")

    required = set(edit_stage.get("required_artifacts_in", []))
    assert "production_proposal" in required
    assert "production_proposal.render_runtime" in edit
    assert "production_proposal.music_strategy" in edit
    assert "production_proposal.derivatives_added" in edit


def _music_strategy_decision(selected: str = "generative_loose") -> dict:
    return {
        "decision_id": "d-music-strategy",
        "stage": "proposal",
        "category": "music_strategy_selection",
        "subject": "Music strategy",
        "options_considered": [
            {
                "option_id": selected,
                "label": selected,
                "score": 0.8,
                "reason": "Matches the approved music plan.",
            }
        ],
        "selected": selected,
        "reason": "Approved music strategy for this ad.",
        "user_visible": True,
        "user_approved": True,
    }


def test_ad_video_proposal_checkpoint_requires_decision_log_lock_entries(tmp_path: Path) -> None:
    from lib.checkpoint import CheckpointValidationError, write_checkpoint

    proposal = _minimal_production_proposal()
    with pytest.raises(CheckpointValidationError, match="decision_log"):
        write_checkpoint(
            tmp_path,
            "ad-proposal-audit",
            "proposal",
            "completed",
            {"production_proposal": proposal},
            pipeline_type="ad-video",
        )

    empty_log = {"version": "1.0", "project_id": "ad-proposal-audit", "decisions": []}
    with pytest.raises(CheckpointValidationError, match="render_runtime_selection"):
        write_checkpoint(
            tmp_path,
            "ad-proposal-audit",
            "proposal",
            "completed",
            {"production_proposal": proposal, "decision_log": empty_log},
            pipeline_type="ad-video",
        )

    decision_log = {
        "version": "1.0",
        "project_id": "ad-proposal-audit",
        "decisions": [
            {
                "decision_id": "d-runtime",
                "stage": "proposal",
                "category": "render_runtime_selection",
                "subject": "Composition runtime",
                "options_considered": [
                    {
                        "option_id": "ffmpeg",
                        "label": "FFmpeg",
                        "score": 0.9,
                        "reason": "Best fit for cinematic clip assembly.",
                    }
                ],
                "selected": "ffmpeg",
                "reason": "Approved runtime for this ad.",
                "user_visible": True,
                "user_approved": True,
            },
            {
                "decision_id": "d-product-reference",
                "stage": "proposal",
                "category": "product_identity_reference_selection",
                "subject": "Product reference strategy",
                "options_considered": [
                    {
                        "option_id": "generate_concept_reference",
                        "label": "Generate concept reference",
                        "score": 0.8,
                        "reason": "No user product image was provided.",
                    }
                ],
                "selected": "generate_concept_reference",
                "reason": "Matches the approved product reference strategy.",
                "user_visible": True,
                "user_approved": True,
            },
            _music_strategy_decision(),
        ],
    }
    write_checkpoint(
        tmp_path,
        "ad-proposal-audit",
        "proposal",
        "completed",
        {"production_proposal": proposal, "decision_log": decision_log},
        pipeline_type="ad-video",
    )


def test_ad_video_proposal_checkpoint_requires_music_strategy_decision(tmp_path: Path) -> None:
    from lib.checkpoint import CheckpointValidationError, write_checkpoint

    proposal = _minimal_production_proposal()
    decision_log = {
        "version": "1.0",
        "project_id": "ad-proposal-music-missing",
        "decisions": [
            {
                "decision_id": "d-runtime",
                "stage": "proposal",
                "category": "render_runtime_selection",
                "subject": "Composition runtime",
                "options_considered": [
                    {
                        "option_id": "ffmpeg",
                        "label": "FFmpeg",
                        "score": 0.9,
                        "reason": "Best fit for cinematic clip assembly.",
                    }
                ],
                "selected": "ffmpeg",
                "reason": "Approved runtime for this ad.",
                "user_visible": True,
                "user_approved": True,
            },
            {
                "decision_id": "d-product-reference",
                "stage": "proposal",
                "category": "product_identity_reference_selection",
                "subject": "Product reference strategy",
                "options_considered": [
                    {
                        "option_id": "generate_concept_reference",
                        "label": "Generate concept reference",
                        "score": 0.8,
                        "reason": "No user product image was provided.",
                    }
                ],
                "selected": "generate_concept_reference",
                "reason": "Matches the approved product reference strategy.",
                "user_visible": True,
                "user_approved": True,
            },
        ],
    }

    with pytest.raises(CheckpointValidationError, match="music_strategy_selection"):
        write_checkpoint(
            tmp_path,
            "ad-proposal-music-missing",
            "proposal",
            "completed",
            {"production_proposal": proposal, "decision_log": decision_log},
            pipeline_type="ad-video",
        )


def test_ad_video_proposal_checkpoint_decisions_must_match_locked_proposal(tmp_path: Path) -> None:
    from lib.checkpoint import CheckpointValidationError, write_checkpoint

    proposal = _minimal_production_proposal()
    proposal["render_runtime"] = "hyperframes"
    decision_log = {
        "version": "1.0",
        "project_id": "ad-proposal-mismatch",
        "decisions": [
            {
                "decision_id": "d-runtime",
                "stage": "proposal",
                "category": "render_runtime_selection",
                "subject": "Composition runtime",
                "options_considered": [
                    {
                        "option_id": "remotion",
                        "label": "Remotion",
                        "score": 0.9,
                        "reason": "Best fit for React scene stack.",
                    },
                    {
                        "option_id": "hyperframes",
                        "label": "HyperFrames",
                        "score": 0.8,
                        "reason": "Good fit for GSAP typography.",
                    },
                ],
                "selected": "remotion",
                "reason": "Approved runtime for this ad.",
                "user_visible": True,
                "user_approved": True,
            },
            {
                "decision_id": "d-product-reference",
                "stage": "proposal",
                "category": "product_identity_reference_selection",
                "subject": "Product reference strategy",
                "options_considered": [
                    {
                        "option_id": "not_applicable",
                        "label": "Not applicable",
                        "score": 1.0,
                        "reason": "No product-visible scenes.",
                    }
                ],
                "selected": "not_applicable",
                "reason": "No product identity reference is required.",
                "user_visible": True,
                "user_approved": True,
            },
            _music_strategy_decision(),
        ],
    }

    with pytest.raises(CheckpointValidationError, match="render_runtime_selection"):
        write_checkpoint(
            tmp_path,
            "ad-proposal-mismatch",
            "proposal",
            "completed",
            {"production_proposal": proposal, "decision_log": decision_log},
            pipeline_type="ad-video",
        )


def test_ad_video_proposal_checkpoint_music_decision_must_match_locked_strategy(tmp_path: Path) -> None:
    from lib.checkpoint import CheckpointValidationError, write_checkpoint

    proposal = _minimal_production_proposal()
    proposal["music_strategy"] = "search_align"
    decision_log = {
        "version": "1.0",
        "project_id": "ad-proposal-music-mismatch",
        "decisions": [
            {
                "decision_id": "d-runtime",
                "stage": "proposal",
                "category": "render_runtime_selection",
                "subject": "Composition runtime",
                "options_considered": [
                    {
                        "option_id": "ffmpeg",
                        "label": "FFmpeg",
                        "score": 0.9,
                        "reason": "Best fit for cinematic clip assembly.",
                    }
                ],
                "selected": "ffmpeg",
                "reason": "Approved runtime for this ad.",
                "user_visible": True,
                "user_approved": True,
            },
            {
                "decision_id": "d-product-reference",
                "stage": "proposal",
                "category": "product_identity_reference_selection",
                "subject": "Product reference strategy",
                "options_considered": [
                    {
                        "option_id": "generate_concept_reference",
                        "label": "Generate concept reference",
                        "score": 0.8,
                        "reason": "No user product image was provided.",
                    }
                ],
                "selected": "generate_concept_reference",
                "reason": "Matches the approved product reference strategy.",
                "user_visible": True,
                "user_approved": True,
            },
            _music_strategy_decision("generative_loose"),
        ],
    }

    with pytest.raises(CheckpointValidationError, match="music_strategy_selection"):
        write_checkpoint(
            tmp_path,
            "ad-proposal-music-mismatch",
            "proposal",
            "completed",
            {"production_proposal": proposal, "decision_log": decision_log},
            pipeline_type="ad-video",
        )


def test_ad_video_production_proposal_checkpoint_records_decision_log_ref(tmp_path: Path) -> None:
    from lib.checkpoint import write_checkpoint

    decision_log = {
        "version": "1.0",
        "project_id": "ad-proposal-ref",
        "decisions": [
            {
                "decision_id": "d-runtime",
                "stage": "proposal",
                "category": "render_runtime_selection",
                "subject": "Composition runtime",
                "options_considered": [
                    {
                        "option_id": "ffmpeg",
                        "label": "FFmpeg",
                        "score": 0.9,
                        "reason": "Best fit for cinematic clip assembly.",
                    }
                ],
                "selected": "ffmpeg",
                "reason": "Approved runtime for this ad.",
                "user_visible": True,
                "user_approved": True,
            },
            {
                "decision_id": "d-product-reference",
                "stage": "proposal",
                "category": "product_identity_reference_selection",
                "subject": "Product reference strategy",
                "options_considered": [
                    {
                        "option_id": "generate_concept_reference",
                        "label": "Generate concept reference",
                        "score": 0.8,
                        "reason": "No user product image was provided.",
                    }
                ],
                "selected": "generate_concept_reference",
                "reason": "Matches the approved product reference strategy.",
                "user_visible": True,
                "user_approved": True,
            },
            _music_strategy_decision(),
        ],
    }

    checkpoint_path = write_checkpoint(
        tmp_path,
        "ad-proposal-ref",
        "proposal",
        "completed",
        {
            "production_proposal": _minimal_production_proposal(),
            "decision_log": decision_log,
        },
        pipeline_type="ad-video",
    )
    checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))

    proposal = checkpoint["artifacts"]["production_proposal"]
    assert proposal["decision_log_ref"].endswith("ad-proposal-ref/decision_log.json")


def test_ad_video_publish_declares_artifacts_needed_for_final_safety_review() -> None:
    manifest = load_pipeline("ad-video")
    publish_stage = next(stage for stage in manifest["stages"] if stage["name"] == "publish")
    publish = _read_skill("publish-director.md")

    required = set(publish_stage.get("required_artifacts_in", []))
    assert {
        "render_report",
        "production_proposal",
        "script",
        "production_bible",
        "scene_plan",
        "asset_manifest",
        "decision_log",
    } <= required
    assert "hallucination_contract_check" in _stage_tool_names(publish_stage)
    assert "hallucination_contract_check" in publish
    assert "asset_manifest" in publish
    assert "decision_log" in publish


def test_ad_video_subtitle_contract_uses_ass_not_srt_examples() -> None:
    """Ad-video subtitles must use ASS because FFmpeg SRT styling is unsafe here."""
    manifest = _load_ad_video_manifest()
    asset_stage = next(stage for stage in manifest["stages"] if stage["name"] == "assets")
    asset_contract_lines = asset_stage.get("review_focus", []) + asset_stage.get("success_criteria", [])
    for sub_stage in asset_stage.get("sub_stages", []):
        asset_contract_lines.extend(sub_stage.get("review_focus", []))
        asset_contract_lines.extend(sub_stage.get("success_criteria", []))
    asset_contract = "\n".join(
        asset_contract_lines
    )
    asset = _read_skill("asset-director.md")
    compose = _read_skill("compose-director.md")
    proposal = _read_skill("proposal-director.md")
    production_proposal_schema = (
        ROOT / "schemas" / "artifacts" / "production_proposal.schema.json"
    ).read_text(encoding="utf-8")

    assert "ASS subtitle file" in asset_contract
    assert "SRT/VTT" not in asset_contract
    assert "ASS" in proposal
    assert "SRT" not in proposal
    assert ".srt" not in production_proposal_schema.lower()
    assert ".vtt" not in production_proposal_schema.lower()
    assert "Format: ASS" in asset
    assert "SRT (preferred)" not in asset
    assert '"subtitle_path": "assets/subtitles.ass"' in compose
    assert '"subtitle_path": "assets/subtitles.srt"' not in compose


def test_ad_video_manifest_uses_render_report_outputs_contract_name() -> None:
    manifest = _load_ad_video_manifest()
    compose_stage = next(stage for stage in manifest["stages"] if stage["name"] == "compose")
    publish_stage = next(stage for stage in manifest["stages"] if stage["name"] == "publish")
    contract_text = "\n".join(
        compose_stage.get("success_criteria", [])
        + publish_stage.get("review_focus", [])
        + publish_stage.get("success_criteria", [])
    )

    assert "render_report.outputs" in contract_text
    assert "output_files" not in contract_text


def test_ad_video_manifest_threads_final_review_from_compose_to_publish() -> None:
    manifest = _load_ad_video_manifest()
    compose_stage = next(stage for stage in manifest["stages"] if stage["name"] == "compose")
    publish_stage = next(stage for stage in manifest["stages"] if stage["name"] == "publish")
    compose_director = _read_skill("compose-director.md")
    publish_director = _read_skill("publish-director.md")

    assert "final_review" in compose_stage.get("produces", [])
    assert "final_review" in publish_stage.get("required_artifacts_in", [])
    assert any("final_review" in item for item in compose_stage.get("success_criteria", []))
    assert any("final_review" in item for item in publish_stage.get("review_focus", []))
    assert "final_review" in compose_director
    assert "final_review" in publish_director


def test_ad_video_manifest_exposes_provider_consistency_gate_before_compose() -> None:
    manifest = _load_ad_video_manifest()
    asset_stage = next(stage for stage in manifest["stages"] if stage["name"] == "assets")
    compose_stage = next(stage for stage in manifest["stages"] if stage["name"] == "compose")
    asset_director = _read_skill("asset-director.md")
    compose_director = _read_skill("compose-director.md")
    executive_producer = _read_skill("executive-producer.md")

    asset_tools = _stage_tool_names(asset_stage)
    compose_tools = _stage_tool_names(compose_stage)

    assert "provider_consistency_check" in asset_tools
    assert "provider_consistency_check" in compose_tools
    assert "provider_consistency_check" in get_required_tools(manifest)
    assert "provider_consistency_check" in asset_director
    assert "visual_asset_provider_locks" in asset_director
    assert "music_source" in asset_director
    assert "music_alignment" in asset_director
    assert "visual_asset_provider_locks" in compose_director
    assert "approved_budget_usd" in compose_director
    assert "music_source" in compose_director
    assert "music_alignment" in compose_director
    assert any("visual provider" in item for item in compose_stage.get("success_criteria", []))
    assert any("music_alignment" in item for item in compose_stage.get("success_criteria", []))
    assert any("approved budget" in item for item in compose_stage.get("success_criteria", []))
    assert "provider_consistency_check" in executive_producer


def test_asset_director_manifest_example_satisfies_provider_gates() -> None:
    from tools.validation.provider_consistency_check import check_provider_consistency

    asset_director = _read_skill("asset-director.md")
    manifest_section = asset_director.split("## Asset Manifest Format", maxsplit=1)[1]
    manifest_match = re.search(
        r"```json\s*\n(.*?)\n```",
        manifest_section,
        flags=re.DOTALL,
    )
    assert manifest_match is not None
    manifest = json.loads(manifest_match.group(1))
    script = {
        "version": "1.0",
        "sections": [
            {"id": entry["section_id"], "narration": f"Line for {entry['section_id']}."}
            for entry in manifest["narration_files"]
        ],
    }

    validate_artifact("asset_manifest", manifest, pipeline_type="ad-video")
    verdict = check_provider_consistency(
        _minimal_production_proposal(),
        manifest,
        script=script,
    )

    assert verdict["status"] == "PASS", verdict["issues"]


def test_ad_video_runtime_docs_use_production_proposal_not_legacy_proposal_packet() -> None:
    guide = (ROOT / "AGENT_GUIDE.md").read_text(encoding="utf-8")
    reviewer = (ROOT / "skills" / "meta" / "reviewer.md").read_text(encoding="utf-8")
    animation_runtime_selector = (
        ROOT / "skills" / "meta" / "animation-runtime-selector.md"
    ).read_text(encoding="utf-8")
    edit_schema = (ROOT / "schemas" / "artifacts" / "edit_decisions.schema.json").read_text(
        encoding="utf-8"
    )
    final_review_schema = (
        ROOT / "schemas" / "artifacts" / "final_review.schema.json"
    ).read_text(encoding="utf-8")

    for source_name, text in {
        "AGENT_GUIDE.md": guide,
        "skills/meta/reviewer.md": reviewer,
        "skills/meta/animation-runtime-selector.md": animation_runtime_selector,
        "edit_decisions.schema.json": edit_schema,
        "final_review.schema.json": final_review_schema,
    }.items():
        assert "production_proposal.render_runtime" in text, source_name
        assert "proposal_packet.production_plan.render_runtime" not in text, source_name
        assert "runtime locked in proposal_packet" not in text, source_name


def test_animated_scene_director_uses_kvm_gate_not_unregistered_artifact() -> None:
    animated_scene = _read_skill("scene-director-animated.md")

    assert "check_kvm_coverage" in animated_scene or "scene_fidelity_check" in animated_scene
    assert "kvm_coverage.json" not in animated_scene


def test_edit_director_enforces_duck_schedule_when_intensity_curve_present() -> None:
    edit = _read_skill("edit-director.md")

    # The edit-director must make volume_schedule MANDATORY when intensity_curve
    # exists — not just mention it as a "prefer" option.
    assert "HARD RULE" in edit
    assert "derive_duck_schedule" in edit
    assert "volume_schedule" in edit
    assert "intensity_curve" in edit


def test_asset_director_threads_emotional_mood_into_prompts() -> None:
    asset = _read_skill("asset-director.md")

    # The asset-director must apply emotional mood from the beat sequence
    # to every visual prompt, not just color_direction and resolution_treatment.
    assert "apply_emotional_mood" in asset
    assert "find_beat_for_scene" in asset
    assert "emotional_prompt" in asset
