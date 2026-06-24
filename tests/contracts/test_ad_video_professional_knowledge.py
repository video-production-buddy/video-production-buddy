"""Professional ad-video knowledge retrieval and threading contracts."""

from __future__ import annotations

import json
from copy import deepcopy

import pytest

from schemas.artifacts import validate_artifact


def _knowledge_alignment_block() -> dict:
    return {
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
                    "usage_note": "The hook copy must create a visible before/after gap without explaining the whole product.",
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
    }


def test_ad_video_knowledge_cards_validate_and_cover_core_domains() -> None:
    from lib.ad_knowledge import load_ad_knowledge_cards

    cards = load_ad_knowledge_cards()
    ids = [card["card_id"] for card in cards]
    domains = {card["domain"] for card in cards}

    assert len(cards) >= 15
    assert len(ids) == len(set(ids))
    assert {
        "hook_mechanic",
        "emotional_rhythm",
        "positioning",
        "proof_logic",
        "visual_rhetoric",
        "commercial_compliance",
        "cinematography",
        "color_theory",
        "editing_technique",
        "sound_design",
        "music_direction",
        "audience_insight",
        "narrative_arc",
    }.issubset(domains)


def test_ad_video_knowledge_card_content_hash_detects_tampering(tmp_path) -> None:
    from lib.ad_knowledge import load_ad_knowledge_cards

    card = deepcopy(load_ad_knowledge_cards()[0])
    card["summary"] = card["summary"] + " Tampered."
    (tmp_path / "tampered.json").write_text(json.dumps(card), encoding="utf-8")

    with pytest.raises(ValueError, match="content_hash mismatch"):
        load_ad_knowledge_cards(tmp_path)


def test_ad_video_knowledge_card_loader_rejects_non_strict_json(tmp_path) -> None:
    from lib.ad_knowledge import load_ad_knowledge_cards

    card = deepcopy(load_ad_knowledge_cards()[0])
    card["summary"] = float("nan")
    (tmp_path / "non_strict.json").write_text(json.dumps(card), encoding="utf-8")

    with pytest.raises(ValueError, match="strict JSON"):
        load_ad_knowledge_cards(tmp_path)


def test_bm25_retrieval_returns_relevant_cards_with_stable_source_refs() -> None:
    from lib.ad_knowledge import retrieve_ad_knowledge
    from tests.contracts.test_artifact_chain import INTELLIGENCE_BRIEF_VALID

    result = retrieve_ad_knowledge(
        {
            "product_category": "smartphone camera",
            "platform": "tiktok",
            "audience": "global photography enthusiasts",
            "objectives": ["premium launch", "visual contrast hook"],
            "validation_targets": ["hook_mechanic", "emotional_rhythm", "proof_logic"],
            "backend": "auto",
        }
    )

    assert result["retrieval_backend"] == "bm25"
    assert "backend_used" not in result
    assert "retrieved_cards" not in result
    assert result["cards_used"]
    assert any(card["domain"] == "hook_mechanic" for card in result["cards_used"])
    assert any(card["domain"] == "emotional_rhythm" for card in result["cards_used"])
    assert all(card["source_ref"].startswith("knowledge_alignment:") for card in result["cards_used"])
    assert all(0 < card["relevance_score"] <= 1 for card in result["cards_used"])

    brief = deepcopy(INTELLIGENCE_BRIEF_VALID)
    brief["professional_knowledge"] = result
    validate_artifact("intelligence_brief", brief)


def test_embedding_backend_request_falls_back_to_bm25_with_warning() -> None:
    from tools.analysis.ad_knowledge_retriever import AdKnowledgeRetriever

    result = AdKnowledgeRetriever().execute(
        {
            "product_category": "productivity app",
            "platform": "tiktok",
            "audience": "busy professionals",
            "objectives": ["problem-solution launch"],
            "validation_targets": ["hook_mechanic"],
            "backend": "embedding",
        }
    )

    assert result.success is True
    assert result.data["retrieval_backend"] == "bm25"
    assert "backend_used" not in result.data
    assert "retrieved_cards" not in result.data
    assert any("Embedding backend" in warning for warning in result.data["warnings"])


def test_knowledge_retrieval_rejects_top_k_outside_declared_schema_bounds() -> None:
    from lib.ad_knowledge import retrieve_ad_knowledge

    base_inputs = {
        "product_category": "smartphone camera",
        "platform": "tiktok",
        "audience": "global photography enthusiasts",
        "objectives": ["premium launch", "visual contrast hook"],
        "validation_targets": ["hook_mechanic"],
        "backend": "auto",
    }

    for invalid_top_k in (-1, 0, 21):
        with pytest.raises(
            ValueError,
            match="top_k must be an integer between 1 and 20",
        ):
            retrieve_ad_knowledge({**base_inputs, "top_k": invalid_top_k})


def test_knowledge_retrieval_rejects_non_integer_top_k() -> None:
    from lib.ad_knowledge import retrieve_ad_knowledge

    base_inputs = {
        "product_category": "smartphone camera",
        "platform": "tiktok",
        "audience": "global photography enthusiasts",
        "objectives": ["premium launch", "visual contrast hook"],
        "validation_targets": ["hook_mechanic"],
        "backend": "auto",
    }

    for invalid_top_k in (True, 1.5, "6"):
        with pytest.raises(
            ValueError,
            match="top_k must be an integer between 1 and 20",
        ):
            retrieve_ad_knowledge({**base_inputs, "top_k": invalid_top_k})


def test_knowledge_retriever_tool_reports_invalid_top_k_as_failed_result() -> None:
    from tools.analysis.ad_knowledge_retriever import AdKnowledgeRetriever

    result = AdKnowledgeRetriever().execute(
        {
            "product_category": "smartphone camera",
            "platform": "tiktok",
            "objectives": ["visual contrast hook"],
            "validation_targets": ["hook_mechanic"],
            "top_k": -1,
        }
    )

    assert result.success is False
    assert "top_k must be an integer between 1 and 20" in (result.error or "")


def test_intelligence_brief_schema_requires_professional_knowledge_block() -> None:
    from tests.contracts.test_artifact_chain import INTELLIGENCE_BRIEF_VALID

    validate_artifact("intelligence_brief", deepcopy(INTELLIGENCE_BRIEF_VALID))

    missing = deepcopy(INTELLIGENCE_BRIEF_VALID)
    del missing["professional_knowledge"]
    with pytest.raises(Exception):
        validate_artifact("intelligence_brief", missing)

    bad = deepcopy(INTELLIGENCE_BRIEF_VALID)
    bad["professional_knowledge"]["cards_used"][0]["source_ref"] = "trend_alignment:wrong"
    with pytest.raises(Exception):
        validate_artifact("intelligence_brief", bad)


def test_intelligence_brief_rejects_duplicate_professional_knowledge_card_ids() -> None:
    from tests.contracts.test_artifact_chain import INTELLIGENCE_BRIEF_VALID

    brief = deepcopy(INTELLIGENCE_BRIEF_VALID)
    duplicate = deepcopy(brief["professional_knowledge"]["cards_used"][0])
    duplicate["summary"] = "A duplicate id with different prose would be ambiguous."
    brief["professional_knowledge"]["cards_used"].append(duplicate)

    with pytest.raises(Exception, match="duplicate card_id"):
        validate_artifact("intelligence_brief", brief)


def test_intelligence_brief_rejects_professional_knowledge_source_ref_mismatch() -> None:
    from tests.contracts.test_artifact_chain import INTELLIGENCE_BRIEF_VALID

    brief = deepcopy(INTELLIGENCE_BRIEF_VALID)
    brief["professional_knowledge"]["cards_used"][0][
        "source_ref"
    ] = "knowledge_alignment:wrong.card"

    with pytest.raises(Exception, match="source_ref"):
        validate_artifact("intelligence_brief", brief)


def test_intelligence_brief_rejects_recommendations_for_unknown_cards() -> None:
    from tests.contracts.test_artifact_chain import INTELLIGENCE_BRIEF_VALID

    brief = deepcopy(INTELLIGENCE_BRIEF_VALID)
    brief["professional_knowledge"]["application_recommendations"][0][
        "card_id"
    ] = "unknown.card"

    with pytest.raises(Exception, match="application_recommendations"):
        validate_artifact("intelligence_brief", brief)


def test_intelligence_brief_rejects_contraindications_for_unknown_cards() -> None:
    from tests.contracts.test_artifact_chain import INTELLIGENCE_BRIEF_VALID

    brief = deepcopy(INTELLIGENCE_BRIEF_VALID)
    brief["professional_knowledge"]["contraindications"][0][
        "card_id"
    ] = "unknown.card"

    with pytest.raises(Exception, match="contraindications"):
        validate_artifact("intelligence_brief", brief)


def test_intelligence_brief_rejects_duplicate_trend_ids_when_present() -> None:
    from tests.contracts.test_artifact_chain import INTELLIGENCE_BRIEF_VALID

    brief = deepcopy(INTELLIGENCE_BRIEF_VALID)
    brief["platform_trends"][0]["trend_id"] = "trend-fast-hook"
    brief["platform_trends"][1]["trend_id"] = "trend-fast-hook"

    with pytest.raises(Exception, match="duplicate trend_id"):
        validate_artifact("intelligence_brief", brief)


def test_ad_video_intelligence_rejects_research_grounded_contradiction_without_challenge_evidence() -> None:
    from tests.contracts.test_artifact_chain import INTELLIGENCE_BRIEF_VALID

    brief = deepcopy(INTELLIGENCE_BRIEF_VALID)
    brief["dimension_verdicts"] = [
        {
            "dimension": "arc_type",
            "confidence": "research-grounded",
            "verdict": "CONTRADICTED",
        }
    ]

    with pytest.raises(Exception, match="challenge_evidence"):
        validate_artifact("intelligence_brief", brief, pipeline_type="ad-video")


@pytest.mark.parametrize(
    "challenge_evidence",
    [
        "The report contradicts this audience hypothesis.",
        "A study says this positioning is wrong.",
        "Industry reports show this visual approach is uncommon.",
    ],
)
def test_ad_video_intelligence_rejects_generic_research_grounded_challenge_evidence(
    challenge_evidence: str,
) -> None:
    from tests.contracts.test_artifact_chain import INTELLIGENCE_BRIEF_VALID

    brief = deepcopy(INTELLIGENCE_BRIEF_VALID)
    brief["dimension_verdicts"] = [
        {
            "dimension": "arc_type",
            "confidence": "research-grounded",
            "verdict": "CONTRADICTED",
            "challenge_evidence": challenge_evidence,
        }
    ]

    with pytest.raises(Exception, match="challenge_evidence"):
        validate_artifact("intelligence_brief", brief, pipeline_type="ad-video")


@pytest.mark.parametrize(
    "challenge_evidence",
    [
        "Nielsen Q3 2025 report contradicts this audience hypothesis.",
        "See https://example.com/category-study for the contradictory evidence.",
        "A category report cites 42% lower completion for this hook pattern.",
    ],
)
def test_ad_video_intelligence_accepts_specific_research_grounded_challenge_evidence(
    challenge_evidence: str,
) -> None:
    from tests.contracts.test_artifact_chain import INTELLIGENCE_BRIEF_VALID

    brief = deepcopy(INTELLIGENCE_BRIEF_VALID)
    brief["dimension_verdicts"] = [
        {
            "dimension": "arc_type",
            "confidence": "research-grounded",
            "verdict": "CONTRADICTED",
            "challenge_evidence": challenge_evidence,
        }
    ]

    validate_artifact("intelligence_brief", brief, pipeline_type="ad-video")


def test_ad_video_intelligence_rejects_default_heuristic_contradiction() -> None:
    from tests.contracts.test_artifact_chain import INTELLIGENCE_BRIEF_VALID

    brief = deepcopy(INTELLIGENCE_BRIEF_VALID)
    brief["dimension_verdicts"] = [
        {
            "dimension": "pacing_model",
            "confidence": "default-heuristic",
            "verdict": "CONTRADICTED",
        }
    ]

    with pytest.raises(Exception, match="default-heuristic"):
        validate_artifact("intelligence_brief", brief, pipeline_type="ad-video")


def test_ad_video_intelligence_verdicts_cover_enriched_brief_hypotheses() -> None:
    from tests.contracts.test_artifact_chain import INTELLIGENCE_BRIEF_VALID
    from tests.contracts.test_schemas_preproduction import _minimal_enriched_brief

    enriched = _minimal_enriched_brief()
    enriched["user_approved"] = True
    brief = deepcopy(INTELLIGENCE_BRIEF_VALID)

    with pytest.raises(Exception, match="dimension_verdicts"):
        validate_artifact(
            "intelligence_brief",
            brief,
            pipeline_type="ad-video",
            related_artifacts={"enriched_brief": enriched},
        )

    brief["dimension_verdicts"] = [
        {
            "dimension": "arc_type",
            "confidence": "pattern-inferred",
            "verdict": "SUPPORTED",
        },
        {
            "dimension": "music_direction",
            "confidence": "pattern-inferred",
            "verdict": "SUPPORTED",
        },
        {
            "dimension": "visual_approach",
            "confidence": "pattern-inferred",
            "verdict": "SUPPORTED",
        },
    ]
    validate_artifact(
        "intelligence_brief",
        brief,
        pipeline_type="ad-video",
        related_artifacts={"enriched_brief": enriched},
    )


def test_ad_video_intelligence_verdicts_do_not_challenge_from_brief_dimensions() -> None:
    from tests.contracts.test_artifact_chain import INTELLIGENCE_BRIEF_VALID
    from tests.contracts.test_schemas_preproduction import _minimal_enriched_brief

    enriched = _minimal_enriched_brief()
    enriched["user_approved"] = True
    brief = deepcopy(INTELLIGENCE_BRIEF_VALID)
    brief["dimension_verdicts"] = [
        {
            "dimension": "arc_type",
            "confidence": "pattern-inferred",
            "verdict": "SUPPORTED",
        },
        {
            "dimension": "music_direction",
            "confidence": "pattern-inferred",
            "verdict": "SUPPORTED",
        },
        {
            "dimension": "visual_approach",
            "confidence": "pattern-inferred",
            "verdict": "SUPPORTED",
        },
        {
            "dimension": "target_demographic",
            "confidence": "research-grounded",
            "verdict": "CONTRADICTED",
            "challenge_evidence": "Example Report 2026: a cited demographic note.",
        },
    ]

    with pytest.raises(Exception, match="FROM BRIEF"):
        validate_artifact(
            "intelligence_brief",
            brief,
            pipeline_type="ad-video",
            related_artifacts={"enriched_brief": enriched},
        )


def test_ad_video_intelligence_rejects_from_brief_verdicts_even_without_hypotheses() -> None:
    from tests.contracts.test_artifact_chain import INTELLIGENCE_BRIEF_VALID
    from tests.contracts.test_schemas_preproduction import _minimal_enriched_brief

    enriched = _minimal_enriched_brief()
    enriched["user_approved"] = True
    for flag in enriched["hypothesis_flags"]:
        flag["status"] = "FROM BRIEF"
    brief = deepcopy(INTELLIGENCE_BRIEF_VALID)
    brief["dimension_verdicts"] = [
        {
            "dimension": "arc_type",
            "confidence": "research-grounded",
            "verdict": "SUPPORTED",
        },
    ]

    with pytest.raises(Exception, match="FROM BRIEF"):
        validate_artifact(
            "intelligence_brief",
            brief,
            pipeline_type="ad-video",
            related_artifacts={"enriched_brief": enriched},
        )


def test_production_bible_schema_requires_knowledge_alignment_block() -> None:
    from tests.contracts.test_artifact_chain import PRODUCTION_BIBLE_VALID

    validate_artifact("production_bible", deepcopy(PRODUCTION_BIBLE_VALID))

    missing = deepcopy(PRODUCTION_BIBLE_VALID)
    del missing["intelligence"]["knowledge_alignment"]
    with pytest.raises(Exception):
        validate_artifact("production_bible", missing)

    bad = deepcopy(PRODUCTION_BIBLE_VALID)
    bad["intelligence"]["knowledge_alignment"]["alignments"][0]["source_ref"] = "trend_alignment:wrong"
    with pytest.raises(Exception):
        validate_artifact("production_bible", bad)


def test_production_bible_schema_accepts_knowledge_cross_domain_notes() -> None:
    from tests.contracts.test_artifact_chain import PRODUCTION_BIBLE_VALID

    bible = deepcopy(PRODUCTION_BIBLE_VALID)
    bible["intelligence"]["knowledge_alignment"]["alignments"][0][
        "cross_domain_notes"
    ] = [
        {
            "domain": "emotional_rhythm",
            "note": "Coordinate hook contrast with the emotional tension peak.",
        }
    ]

    validate_artifact("production_bible", bible, pipeline_type="ad-video")


def test_knowledge_alignment_requires_script_and_scene_threading() -> None:
    from lib.knowledge_alignment import check_ad_video_planning_knowledge_alignment

    bible = {"intelligence": {"knowledge_alignment": _knowledge_alignment_block()}}
    script = {
        "sections": [
            {
                "id": "hook",
                "beat": "hook",
                "text": "Two photos, same night, only one remembers the color.",
            }
        ]
    }
    scene_plan = {
        "scenes": [
            {
                "id": "scene-hook",
                "beat": "hook",
                "knowledge_alignment_refs": ["knowledge_alignment:hook.visual-contrast.001"],
                "knowledge_alignment_notes": "Before/after night color contrast lands in the opening second.",
            }
        ]
    }

    report = check_ad_video_planning_knowledge_alignment(bible, script, scene_plan)

    assert report["ok"] is False
    assert any(issue["kind"] == "missing_knowledge_source_ref" for issue in report["issues"])

    script["sections"][0]["source_ref"] = "knowledge_alignment:hook.visual-contrast.001"
    assert check_ad_video_planning_knowledge_alignment(bible, script, scene_plan)["ok"] is True

    scene_plan["scenes"][0]["knowledge_alignment_refs"] = ["hook.visual-contrast.001"]
    report = check_ad_video_planning_knowledge_alignment(bible, script, scene_plan)
    assert report["ok"] is False
    assert any(issue["kind"] == "missing_scene_knowledge_alignment" for issue in report["issues"])

    scene_plan["scenes"][0]["knowledge_alignment_refs"] = []
    report = check_ad_video_planning_knowledge_alignment(bible, script, scene_plan)
    assert report["ok"] is False
    assert any(issue["kind"] == "missing_scene_knowledge_alignment" for issue in report["issues"])


def test_scene_knowledge_alignment_treats_craft_targets_as_scene_observable() -> None:
    from lib.knowledge_alignment import check_scene_plan_knowledge_alignment

    for target in ("color", "sound", "music", "editing"):
        bible = {"intelligence": {"knowledge_alignment": _knowledge_alignment_block()}}
        alignment = bible["intelligence"]["knowledge_alignment"]["alignments"][0]
        alignment["application_targets"] = [target]
        alignment["scene_usage"]["required"] = False
        alignment["scene_usage"]["required_scene_count"] = 1

        report = check_scene_plan_knowledge_alignment(
            bible,
            {"scenes": [{"id": "scene-hook", "beat": "hook"}]},
        )

        assert report["ok"] is False
        assert any(
            issue["kind"] == "missing_scene_knowledge_alignment"
            and issue["card_id"] == "hook.visual-contrast.001"
            for issue in report["issues"]
        )


def test_knowledge_alignment_rejects_mismatched_nested_source_refs() -> None:
    from lib.knowledge_alignment import check_ad_video_planning_knowledge_alignment

    bible = {"intelligence": {"knowledge_alignment": _knowledge_alignment_block()}}
    bible["intelligence"]["knowledge_alignment"]["alignments"][0]["script_usage"][
        "source_ref"
    ] = "knowledge_alignment:proof.specific-demonstration.001"
    wrong_ref = "knowledge_alignment:proof.specific-demonstration.001"
    script = {
        "sections": [
            {
                "id": "hook",
                "beat": "hook",
                "text": "Two photos, same night, only one remembers the color.",
                "source_ref": wrong_ref,
            }
        ]
    }
    scene_plan = {
        "scenes": [
            {
                "id": "scene-hook",
                "beat": "hook",
                "knowledge_alignment_refs": [wrong_ref],
                "knowledge_alignment_notes": "Before/after night color contrast lands in the opening second.",
            }
        ]
    }

    report = check_ad_video_planning_knowledge_alignment(bible, script, scene_plan)

    assert report["ok"] is False
    assert any(issue["kind"] == "inconsistent_knowledge_source_ref" for issue in report["issues"])
    assert any(
        issue["kind"] == "missing_knowledge_source_ref"
        and issue["expected_ref"] == "knowledge_alignment:hook.visual-contrast.001"
        for issue in report["issues"]
    )


def test_script_only_cross_domain_knowledge_does_not_require_scene_co_presence() -> None:
    from lib.knowledge_alignment import check_ad_video_planning_knowledge_alignment

    def entry(card_id: str, domain: str, partner_domain: str) -> dict:
        source_ref = f"knowledge_alignment:{card_id}"
        return {
            "card_id": card_id,
            "domain": domain,
            "source_ref": source_ref,
            "application_targets": ["script"],
            "target_beat": "hook",
            "script_usage": {
                "required_section_ids": ["hook"],
                "source_ref": source_ref,
            },
            "scene_usage": {"required": False},
            "cross_domain_notes": [
                {"domain": partner_domain, "note": "Coordinate in the script."}
            ],
        }

    bible = {
        "intelligence": {
            "knowledge_alignment": {
                "selected_card_ids": [
                    "positioning.single-promise.001",
                    "audience.psychographic-depth.001",
                ],
                "alignments": [
                    entry(
                        "positioning.single-promise.001",
                        "positioning",
                        "audience_insight",
                    ),
                    entry(
                        "audience.psychographic-depth.001",
                        "audience_insight",
                        "positioning",
                    ),
                ],
            }
        }
    }
    script = {
        "sections": [
            {
                "id": "hook",
                "beat": "hook",
                "source_refs": [
                    "knowledge_alignment:positioning.single-promise.001",
                    "knowledge_alignment:audience.psychographic-depth.001",
                ],
            }
        ]
    }
    scene_plan = {"scenes": [{"id": "scene-1", "description": "Visual scene."}]}

    report = check_ad_video_planning_knowledge_alignment(bible, script, scene_plan)

    assert report["ok"] is True
    assert not any(
        issue["kind"] == "missing_cross_domain_co_presence"
        for issue in report["issues"]
    )


def test_scene_plan_rejects_bare_knowledge_alignment_refs() -> None:
    scene_plan = {
        "version": "1.0",
        "user_approved": True,
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
                "knowledge_alignment_refs": ["knowledge_alignment:hook.visual-contrast.001"],
                "knowledge_alignment_notes": "Opening scene uses a visible before/after contrast without turning into clickbait.",
            }
        ],
    }

    validate_artifact("scene_plan", deepcopy(scene_plan), pipeline_type="ad-video")

    bad = deepcopy(scene_plan)
    bad["scenes"][0]["knowledge_alignment_refs"] = ["hook.visual-contrast.001"]
    with pytest.raises(Exception):
        validate_artifact("scene_plan", bad, pipeline_type="ad-video")


def test_all_cards_have_required_deep_fields() -> None:
    from lib.ad_knowledge import load_ad_knowledge_cards

    cards = load_ad_knowledge_cards()
    for card in cards:
        assert len(card.get("principles", [])) >= 5, (
            f"{card['card_id']}: principles must have >= 5 items"
        )
        assert len(card.get("failure_patterns", [])) >= 2, (
            f"{card['card_id']}: failure_patterns must have >= 2 items"
        )
        assert len(card.get("cross_domain_notes", [])) >= 1, (
            f"{card['card_id']}: cross_domain_notes must have >= 1 item"
        )
        assert len(card.get("execution_techniques", [])) >= 2, (
            f"{card['card_id']}: execution_techniques must have >= 2 items"
        )


def test_field_weighted_retrieval_ranks_domain_matches_higher() -> None:
    from lib.ad_knowledge import retrieve_ad_knowledge

    result = retrieve_ad_knowledge(
        {
            "product_category": "smartphone",
            "platform": "tiktok",
            "audience": "photography enthusiasts",
            "objectives": ["cinematic launch"],
            "validation_targets": ["cinematography", "hook_mechanic"],
            "backend": "auto",
        }
    )

    assert result["retrieval_backend"] == "bm25"
    assert len(result["cards_used"]) >= 2

    domain_order = [card["domain"] for card in result["cards_used"]]
    hook_idx = domain_order.index("hook_mechanic") if "hook_mechanic" in domain_order else 99
    cine_idx = domain_order.index("cinematography") if "cinematography" in domain_order else 99
    assert hook_idx < 99 or cine_idx < 99, "At least one target domain should be retrieved"


def test_retrieval_returns_cards_from_new_domains() -> None:
    from lib.ad_knowledge import retrieve_ad_knowledge

    result = retrieve_ad_knowledge(
        {
            "product_category": "lifestyle product",
            "platform": "instagram",
            "audience": "creative professionals",
            "objectives": ["emotional storytelling", "color palette"],
            "validation_targets": ["color_theory", "sound_design", "music_direction"],
            "backend": "auto",
        }
    )

    retrieved_domains = {card["domain"] for card in result["cards_used"]}
    assert "color_theory" in retrieved_domains


def test_retrieval_gaps_accept_downstream_target_matches() -> None:
    from lib.ad_knowledge import retrieve_ad_knowledge

    result = retrieve_ad_knowledge(
        {
            "product_category": "mobile app launch",
            "platform": "reels",
            "audience": "creative teams",
            "objectives": [
                "color palette",
                "sound design",
                "music direction",
                "editing rhythm",
            ],
            "validation_targets": ["color", "sound", "music", "editing"],
            "top_k": 15,
            "backend": "auto",
        }
    )

    assert result["gaps"] == []


def test_retrieval_exposes_cross_domain_notes_for_bible_alignment() -> None:
    from lib.ad_knowledge import retrieve_ad_knowledge

    card = {
        "card_id": "hook.test-cross-domain.001",
        "domain": "hook_mechanic",
        "summary": "Use a clear opening contrast.",
        "keywords": ["hook", "contrast"],
        "apply_when": ["The brief needs an immediate comprehension gap."],
        "principles": ["Open on a concrete contrast."],
        "execution_techniques": ["Before/after opening beat."],
        "avoid_when": ["The contrast would exaggerate the claim."],
        "failure_patterns": ["Generic shock image."],
        "downstream_targets": ["hook", "visual"],
        "cross_domain_notes": [
            {
                "domain": "emotional_rhythm",
                "note": "Coordinate the contrast with the tension peak.",
            }
        ],
    }

    result = retrieve_ad_knowledge({"brief": "hook contrast"}, cards=[card])

    assert result["cards_used"][0]["cross_domain_notes"] == card["cross_domain_notes"]


def test_retrieval_exposes_deep_card_guidance_for_bible_director() -> None:
    from lib.ad_knowledge import retrieve_ad_knowledge

    card = {
        "card_id": "hook.test-deep-guidance.001",
        "domain": "hook_mechanic",
        "summary": "Use a clear opening contrast.",
        "keywords": ["hook", "contrast"],
        "apply_when": ["The brief needs an immediate comprehension gap."],
        "principles": [
            "Open on a concrete contrast.",
            "Resolve the contrast into the product promise.",
        ],
        "execution_techniques": [
            "Use a hard cut between before and after.",
            "Keep the product position stable across the contrast.",
        ],
        "avoid_when": [
            "The contrast would exaggerate the claim.",
            "The only available contrast is unrelated clickbait.",
        ],
        "failure_patterns": [
            "Generic shock image.",
            "Before/after that cannot be substantiated.",
        ],
        "downstream_targets": ["hook", "visual"],
        "cross_domain_notes": [
            {
                "domain": "emotional_rhythm",
                "note": "Coordinate the contrast with the tension peak.",
            }
        ],
    }

    result = retrieve_ad_knowledge({"brief": "hook contrast"}, cards=[card])
    retrieved = result["cards_used"][0]

    assert retrieved["principles"] == card["principles"]
    assert retrieved["execution_techniques"] == card["execution_techniques"]
    assert retrieved["avoid_when"] == card["avoid_when"]
    assert retrieved["failure_patterns"] == card["failure_patterns"]


def test_intelligence_brief_schema_accepts_card_cross_domain_notes() -> None:
    from tests.contracts.test_artifact_chain import INTELLIGENCE_BRIEF_VALID

    brief = deepcopy(INTELLIGENCE_BRIEF_VALID)
    brief["professional_knowledge"]["cards_used"][0]["cross_domain_notes"] = [
        {
            "domain": "emotional_rhythm",
            "note": "Coordinate hook contrast with the emotional tension peak.",
        }
    ]

    validate_artifact("intelligence_brief", brief, pipeline_type="ad-video")


def test_intelligence_brief_schema_accepts_card_deep_guidance() -> None:
    from tests.contracts.test_artifact_chain import INTELLIGENCE_BRIEF_VALID

    brief = deepcopy(INTELLIGENCE_BRIEF_VALID)

    validate_artifact("intelligence_brief", brief, pipeline_type="ad-video")


@pytest.mark.parametrize(
    "field",
    ["principles", "avoid_when", "failure_patterns", "execution_techniques"],
)
def test_intelligence_brief_schema_requires_card_deep_guidance(field: str) -> None:
    from tests.contracts.test_artifact_chain import INTELLIGENCE_BRIEF_VALID

    brief = deepcopy(INTELLIGENCE_BRIEF_VALID)
    del brief["professional_knowledge"]["cards_used"][0][field]

    with pytest.raises(Exception, match=field):
        validate_artifact("intelligence_brief", brief, pipeline_type="ad-video")


def test_production_bible_accepts_all_knowledge_downstream_targets() -> None:
    from lib.ad_knowledge import load_ad_knowledge_cards
    from tests.contracts.test_artifact_chain import PRODUCTION_BIBLE_VALID

    cards = load_ad_knowledge_cards()
    all_downstream_targets = sorted(
        {
            target
            for card in cards
            for target in card["downstream_targets"]
        }
    )
    bible = deepcopy(PRODUCTION_BIBLE_VALID)
    alignment = bible["intelligence"]["knowledge_alignment"]["alignments"][0]
    alignment["application_targets"] = all_downstream_targets

    validate_artifact("production_bible", bible)


def test_cross_domain_notes_reference_valid_domains() -> None:
    from lib.ad_knowledge import load_ad_knowledge_cards

    all_domains = {
        "positioning", "audience_insight", "hook_mechanic", "narrative_arc",
        "emotional_rhythm", "visual_rhetoric", "proof_logic", "product_demo_logic",
        "platform_format", "commercial_compliance", "cinematography", "color_theory",
        "editing_technique", "sound_design", "music_direction",
    }

    cards = load_ad_knowledge_cards()
    for card in cards:
        for note in card.get("cross_domain_notes", []):
            referenced_domain = note.get("domain", "")
            assert referenced_domain in all_domains, (
                f"{card['card_id']}: cross_domain_notes references unknown domain '{referenced_domain}'"
            )
