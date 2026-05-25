"""Fine-grained edge-case tests for ad-video validation tools.

Tests hallucination_contract_check, product_identity_consistency_check,
runtime_consistency_check, sample_product_visibility_check, scene_fidelity_check,
and planning_chain_check at boundary conditions.
"""

from __future__ import annotations

import pytest

from tools.validation.hallucination_contract_check import (
    PRODUCT_VISIBLE_VALUES,
    VISUAL_ASSET_TYPES,
    WAIVER_DECISION_CATEGORY,
    _asset_has_sourced_provenance,
    _asset_has_generated_provenance,
    _asset_is_generated_visual,
    _decision_is_user_approved,
    _find_decision,
    _normalized_token,
    _review_has_waiver,
    _scene_has_generated_visual_scope,
    _scene_is_high_risk,
    _selected_option_is_waiver,
    check_hallucination_contract,
    _truth_contract_issues,
)
from tools.validation.product_identity_consistency_check import (
    check_product_identity_consistency,
    _reference_is_approved,
    _risk_waiver_is_approved,
)
from tools.validation.runtime_consistency_check import (
    check_runtime_consistency,
)
from tools.validation.sample_product_visibility_check import (
    _extract_keywords,
    _NEGATED_VISUAL_CONSTRAINT_RE,
    check_sample_visibility,
)


# ---------------------------------------------------------------------------
# hallucination_contract_check edge cases
# ---------------------------------------------------------------------------


def _minimal_bible(**overrides) -> dict:
    truth = {
        "objective_facts": ["product is aluminum"],
        "physical_constraints": ["no liquid shown"],
        "product_geometry_rules": ["rounded corners"],
        "motion_coherence_rules": ["smooth transitions"],
        "values_guardrails": ["no violence"],
    }
    bible: dict = {"truth_contract": truth, "intelligence": {}}
    bible.update(overrides)
    return bible


def _minimal_scene(scene_id: str = "s1", **overrides) -> dict:
    scene: dict = {
        "id": scene_id,
        "type": "generated",
        "product_visibility": "hero",
        "hallucination_checks": [
            {
                "check_id": "geo",
                "category": "product_geometry",
                "requirement": "correct shape",
                "prohibited_failure": "wrong shape",
                "severity": "critical",
                "evidence_source": "keyframe",
            }
        ],
    }
    scene.update(overrides)
    return scene


def _minimal_asset(asset_id: str = "a1", scene_id: str = "s1", **overrides) -> dict:
    asset: dict = {
        "id": asset_id,
        "scene_id": scene_id,
        "type": "video",
        "subtype": "generated",
        "prompt": "product hero shot",
        "model": "wan2.7",
        "hallucination_review": {
            "status": "PASS",
            "keyframe_paths": ["start.png", "mid.png", "end.png"],
            "check_verdicts": [
                {"check_id": "geo", "status": "PASS", "severity": "critical"}
            ],
        },
    }
    asset.update(overrides)
    return asset


class TestHallucinationContractEdgeCases:
    def test_empty_scene_plan_scenes_list(self) -> None:
        bible = _minimal_bible()
        scene_plan = {"scenes": []}
        asset_manifest = {"assets": []}
        result = check_hallucination_contract(bible, scene_plan, asset_manifest)
        assert result["status"] == "PASS"

    def test_none_scenes_handled(self) -> None:
        bible = _minimal_bible()
        scene_plan = {"scenes": None}
        asset_manifest = {"assets": None}
        result = check_hallucination_contract(bible, scene_plan, asset_manifest)
        assert result["status"] == "PASS"

    def test_non_dict_scene_entries_skipped(self) -> None:
        bible = _minimal_bible()
        scene_plan = {"scenes": ["not_a_dict", 42, None]}
        asset_manifest = {"assets": []}
        result = check_hallucination_contract(bible, scene_plan, asset_manifest)
        assert result["status"] == "PASS"

    def test_missing_truth_contract_section(self) -> None:
        bible = _minimal_bible()
        del bible["truth_contract"]["physical_constraints"]
        scene_plan = {"scenes": []}
        asset_manifest = {"assets": []}
        result = check_hallucination_contract(bible, scene_plan, asset_manifest)
        assert result["status"] == "FAIL"
        assert any("physical_constraints" in i for i in result["issues"])

    def test_empty_truth_contract_section_list(self) -> None:
        bible = _minimal_bible()
        bible["truth_contract"]["objective_facts"] = []
        scene_plan = {"scenes": []}
        asset_manifest = {"assets": []}
        result = check_hallucination_contract(bible, scene_plan, asset_manifest)
        assert result["status"] == "FAIL"

    def test_high_risk_scene_with_source_generate_in_required_assets(self) -> None:
        scene = {
            "id": "s1",
            "type": "broll",
            "product_visibility": "hero",
            "required_assets": [
                {"type": "video", "source": "generate"},
                {"type": "image", "source": "stock"},
            ],
            "hallucination_checks": [
                {"check_id": "c1", "category": "geo", "requirement": "ok",
                 "prohibited_failure": "bad", "severity": "major", "evidence_source": "kf"}
            ],
        }
        assert _scene_is_high_risk(scene)

    def test_non_generated_source_not_high_risk_for_visual_scope(self) -> None:
        scene = {
            "id": "s1",
            "type": "broll",
            "product_visibility": "none",
            "required_assets": [
                {"type": "video", "source": "stock"},
            ],
        }
        assert not _scene_has_generated_visual_scope(scene)

    def test_scene_with_type_generated_is_high_risk(self) -> None:
        assert _scene_is_high_risk({"id": "x", "type": "generated"})

    def test_image_asset_needs_only_one_keyframe(self) -> None:
        bible = _minimal_bible()
        scene = _minimal_scene()
        asset = {
            "id": "img1",
            "scene_id": "s1",
            "type": "image",
            "subtype": "generated",
            "prompt": "product",
            "hallucination_review": {
                "status": "PASS",
                "keyframe_paths": ["kf1.png"],
                "check_verdicts": [
                    {"check_id": "geo", "status": "PASS", "severity": "critical"}
                ],
            },
        }
        result = check_hallucination_contract(
            bible, {"scenes": [scene]}, {"assets": [asset]}
        )
        assert result["status"] == "PASS"

    def test_video_asset_with_two_keyframes_fails(self) -> None:
        bible = _minimal_bible()
        scene = _minimal_scene()
        asset = _minimal_asset().copy()
        asset["hallucination_review"] = {
            "status": "PASS",
            "keyframe_paths": ["start.png", "mid.png"],
            "check_verdicts": [
                {"check_id": "geo", "status": "PASS", "severity": "critical"}
            ],
        }
        result = check_hallucination_contract(
            bible, {"scenes": [scene]}, {"assets": [asset]}
        )
        assert result["status"] == "FAIL"
        assert any("start/mid/end" in i for i in result["issues"])

    def test_flag_verdict_blocks(self) -> None:
        bible = _minimal_bible()
        scene = _minimal_scene()
        asset = _minimal_asset()
        asset["hallucination_review"]["check_verdicts"] = [
            {"check_id": "geo", "status": "FLAG", "severity": "critical"}
        ]
        result = check_hallucination_contract(
            bible, {"scenes": [scene]}, {"assets": [asset]}
        )
        assert result["status"] == "FAIL"

    def test_warn_verdict_passes_with_warnings(self) -> None:
        bible = _minimal_bible()
        scene = _minimal_scene()
        asset = _minimal_asset()
        asset["hallucination_review"]["check_verdicts"] = [
            {"check_id": "geo", "status": "WARN", "severity": "major"}
        ]
        result = check_hallucination_contract(
            bible, {"scenes": [scene]}, {"assets": [asset]}
        )
        assert result["status"] == "WARN"
        assert len(result["warnings"]) > 0

    def test_missing_verdict_for_scene_check(self) -> None:
        bible = _minimal_bible()
        scene = _minimal_scene()
        scene["hallucination_checks"].append({
            "check_id": "extra",
            "category": "test",
            "requirement": "ok",
            "prohibited_failure": "bad",
            "severity": "minor",
            "evidence_source": "kf",
        })
        asset = _minimal_asset()
        result = check_hallucination_contract(
            bible, {"scenes": [scene]}, {"assets": [asset]}
        )
        assert any("extra" in i for i in result["issues"])

    def test_high_risk_scene_with_no_generated_visual_asset(self) -> None:
        bible = _minimal_bible()
        scene = _minimal_scene()
        result = check_hallucination_contract(
            bible, {"scenes": [scene]}, {"assets": []}
        )
        assert result["status"] == "FAIL"
        assert any("no generated visual asset" in i for i in result["issues"])

    def test_sourced_asset_not_treated_as_generated(self) -> None:
        asset = {
            "type": "video",
            "subtype": "stock",
            "license": "CC-BY",
            "original_url": "https://example.com/vid.mp4",
        }
        assert _asset_has_sourced_provenance(asset)

    def test_generated_provenance_from_conditioning(self) -> None:
        asset = {"type": "video", "product_identity_conditioning": {"mode": "reference"}}
        assert _asset_has_generated_provenance(asset)

    def test_generated_provenance_from_seed(self) -> None:
        asset = {"type": "video", "seed": 12345}
        assert _asset_has_generated_provenance(asset)

    def test_review_waiver_via_status(self) -> None:
        assert _review_has_waiver({"status": "WAIVED"})

    def test_review_waiver_via_action(self) -> None:
        assert _review_has_waiver({"regeneration_action": {"action": "human_waiver"}})

    def test_review_waiver_via_verdict(self) -> None:
        assert _review_has_waiver({"check_verdicts": [{"status": "WAIVED"}]})

    def test_no_waiver_when_none_present(self) -> None:
        assert not _review_has_waiver({"status": "PASS"})

    def test_waiver_requires_user_approved_decision(self) -> None:
        bible = _minimal_bible()
        scene = _minimal_scene()
        asset = _minimal_asset()
        asset["hallucination_review"]["status"] = "WAIVED"
        result = check_hallucination_contract(
            bible, {"scenes": [scene]}, {"assets": [asset]}
        )
        assert result["status"] == "FAIL"
        assert any("waiver" in i.lower() for i in result["issues"])


class TestNormalizedToken:
    def test_none_returns_empty(self) -> None:
        assert _normalized_token(None) == ""

    def test_non_string_returns_empty(self) -> None:
        assert _normalized_token(42) == ""

    def test_strips_and_lowercases(self) -> None:
        assert _normalized_token("  WaIvEr  ") == "waiver"

    def test_replaces_hyphens_and_spaces(self) -> None:
        assert _normalized_token("text-only waived") == "text_only_waived"


class TestSelectedOptionIsWaiver:
    def test_waiver_option_id(self) -> None:
        assert _selected_option_is_waiver({"selected": "waiver"})

    def test_waiver_via_option_label(self) -> None:
        decision = {
            "selected": "opt_w",
            "options_considered": [
                {"option_id": "opt_w", "label": "waiver"}
            ],
        }
        assert _selected_option_is_waiver(decision)

    def test_non_waiver_rejected(self) -> None:
        assert not _selected_option_is_waiver({"selected": "regenerate"})

    def test_no_options_considered(self) -> None:
        assert not _selected_option_is_waiver({"selected": "regenerate", "options_considered": []})


class TestFindDecision:
    def test_returns_none_for_empty_log(self) -> None:
        assert _find_decision(None, "d1") is None
        assert _find_decision({}, "d1") is None

    def test_finds_matching_decision(self) -> None:
        log = {"decisions": [{"decision_id": "d1", "category": "test"}]}
        assert _find_decision(log, "d1") is not None

    def test_returns_latest_match(self) -> None:
        log = {
            "decisions": [
                {"decision_id": "d1", "v": 1},
                {"decision_id": "d1", "v": 2},
            ]
        }
        result = _find_decision(log, "d1")
        assert result["v"] == 2


class TestDecisionIsUserApproved:
    def test_valid_waiver_decision(self) -> None:
        decision = {
            "category": WAIVER_DECISION_CATEGORY,
            "user_visible": True,
            "user_approved": True,
            "selected": "waiver",
        }
        assert _decision_is_user_approved(decision)

    def test_rejects_non_waiver_category(self) -> None:
        decision = {
            "category": "other",
            "user_visible": True,
            "user_approved": True,
            "selected": "waiver",
        }
        assert not _decision_is_user_approved(decision)

    def test_rejects_not_user_visible(self) -> None:
        decision = {
            "category": WAIVER_DECISION_CATEGORY,
            "user_visible": False,
            "user_approved": True,
            "selected": "waiver",
        }
        assert not _decision_is_user_approved(decision)


# ---------------------------------------------------------------------------
# product_identity_consistency_check edge cases
# ---------------------------------------------------------------------------


class TestProductIdentityEdgeCases:
    def _approved_reference(self, source_type: str = "user_provided") -> dict:
        return {
            "source_type": source_type,
            "approval_status": "approved",
            "reference_id": "ref-1",
            "selected_reference_image_path": "/path/to/ref.png",
            "user_approval": {
                "approved": True,
                "approved_by": "user",
                "approved_at": "2026-01-01T00:00:00Z",
            },
        }

    def _risk_waiver_reference(self) -> dict:
        return {
            "source_type": "risk_accepted",
            "approval_status": "approved",
            "risk_waiver": {
                "user_approved": True,
                "approved_by": "user",
                "approved_at": "2026-01-01T00:00:00Z",
            },
        }

    def test_not_applicable_with_no_product_visible_scenes(self) -> None:
        reference = {"source_type": "not_applicable", "approval_status": "not_required"}
        scene_plan = {"scenes": [{"id": "s1", "product_visibility": "none"}]}
        asset_manifest = {"assets": []}
        result = check_product_identity_consistency(
            reference, scene_plan, asset_manifest
        )
        assert result["status"] == "PASS"

    def test_reference_without_approval_fails(self) -> None:
        reference = {
            "source_type": "user_provided",
            "approval_status": "pending",
            "selected_reference_image_path": "/path/to/ref.png",
        }
        scene_plan = {"scenes": [
            {"id": "s1", "product_visibility": "hero", "product_reference_required": True}
        ]}
        asset_manifest = {"assets": [
            {"id": "a1", "scene_id": "s1", "type": "video"}
        ]}
        result = check_product_identity_consistency(
            reference, scene_plan, asset_manifest
        )
        assert result["status"] == "FAIL"

    def test_unknown_source_type_fails(self) -> None:
        reference = {"source_type": "magic", "approval_status": "approved"}
        scene_plan = {"scenes": [
            {"id": "s1", "product_visibility": "hero", "product_reference_required": True}
        ]}
        asset_manifest = {"assets": []}
        result = check_product_identity_consistency(
            reference, scene_plan, asset_manifest
        )
        assert result["status"] == "FAIL"
        assert any("Unknown" in i for i in result["issues"])

    def test_risk_waiver_asset_must_be_text_only_waived(self) -> None:
        reference = self._risk_waiver_reference()
        scene_plan = {"scenes": [
            {"id": "s1", "product_visibility": "hero", "product_reference_required": True}
        ]}
        asset_manifest = {"assets": [
            {
                "id": "a1",
                "scene_id": "s1",
                "type": "video",
                "product_identity_conditioning": {
                    "conditioning_mode": "reference",
                    "approved_reference_id": "ref-1",
                },
            }
        ]}
        result = check_product_identity_consistency(
            reference, scene_plan, asset_manifest
        )
        assert result["status"] == "FAIL"
        assert any("text_only_waived" in i for i in result["issues"])

    def test_text_only_waived_without_decision_id_fails(self) -> None:
        reference = self._risk_waiver_reference()
        scene_plan = {"scenes": [
            {"id": "s1", "product_visibility": "hero", "product_reference_required": True}
        ]}
        asset_manifest = {"assets": [
            {
                "id": "a1",
                "scene_id": "s1",
                "type": "video",
                "product_identity_conditioning": {
                    "conditioning_mode": "text_only_waived",
                },
            }
        ]}
        result = check_product_identity_consistency(
            reference, scene_plan, asset_manifest
        )
        assert result["status"] == "FAIL"
        assert any("waiver_decision_id" in i for i in result["issues"])

    def test_approved_reference_with_mismatched_reference_id_fails(self) -> None:
        reference = self._approved_reference()
        scene_plan = {"scenes": [
            {"id": "s1", "product_visibility": "hero", "product_reference_required": True}
        ]}
        asset_manifest = {"assets": [
            {
                "id": "a1",
                "scene_id": "s1",
                "type": "video",
                "product_identity_conditioning": {
                    "conditioning_mode": "reference",
                    "approved_reference_id": "wrong-ref",
                    "approved_reference_path": "/path/to/ref.png",
                },
            }
        ]}
        result = check_product_identity_consistency(
            reference, scene_plan, asset_manifest
        )
        assert result["status"] == "FAIL"
        assert any("wrong-ref" in i for i in result["issues"])

    def test_product_visible_scene_with_no_visual_asset_fails(self) -> None:
        reference = self._approved_reference()
        scene_plan = {"scenes": [
            {"id": "s1", "product_visibility": "hero", "product_reference_required": True}
        ]}
        asset_manifest = {"assets": [
            {"id": "a1", "scene_id": "s1", "type": "audio"}
        ]}
        result = check_product_identity_consistency(
            reference, scene_plan, asset_manifest
        )
        assert result["status"] == "FAIL"

    def test_fidelity_verdict_flag_fails(self) -> None:
        reference = self._approved_reference()
        scene_plan = {"scenes": [
            {"id": "s1", "product_visibility": "hero", "product_reference_required": True}
        ]}
        asset_manifest = {"assets": [
            {
                "id": "a1",
                "scene_id": "s1",
                "type": "video",
                "product_identity_conditioning": {
                    "conditioning_mode": "reference",
                    "approved_reference_id": "ref-1",
                    "approved_reference_path": "/path/to/ref.png",
                    "fidelity_verdict": "FLAG",
                },
            }
        ]}
        result = check_product_identity_consistency(
            reference, scene_plan, asset_manifest
        )
        assert result["status"] == "FAIL"

    def test_generated_scene_ids_scope(self) -> None:
        reference = self._approved_reference()
        scene_plan = {"scenes": [
            {"id": "s1", "product_visibility": "hero", "product_reference_required": True},
            {"id": "s2", "product_visibility": "hero", "product_reference_required": True},
        ]}
        asset_manifest = {"assets": [
            {
                "id": "a1",
                "scene_id": "s1",
                "type": "video",
                "product_identity_conditioning": {
                    "conditioning_mode": "reference",
                    "approved_reference_id": "ref-1",
                    "approved_reference_path": "/path/to/ref.png",
                },
            }
        ]}
        result = check_product_identity_consistency(
            reference, scene_plan, asset_manifest, generated_scene_ids=["s1"]
        )
        assert result["status"] == "PASS"
        assert result["summary"]["asset_scope"] == "generated_scene_ids"

    def test_generated_scene_ids_missing_from_plan_fails(self) -> None:
        reference = self._approved_reference()
        scene_plan = {"scenes": [{"id": "s1", "product_visibility": "none"}]}
        asset_manifest = {"assets": []}
        result = check_product_identity_consistency(
            reference, scene_plan, asset_manifest, generated_scene_ids=["s_missing"]
        )
        assert result["status"] == "FAIL"

    def test_non_applicable_with_product_visible_scenes_fails(self) -> None:
        reference = {"source_type": "not_applicable", "approval_status": "not_required"}
        scene_plan = {"scenes": [
            {"id": "s1", "product_visibility": "hero", "product_reference_required": True}
        ]}
        asset_manifest = {"assets": []}
        result = check_product_identity_consistency(
            reference, scene_plan, asset_manifest
        )
        assert result["status"] == "FAIL"

    def test_reference_is_approved_rejects_missing_path(self) -> None:
        ref = {
            "source_type": "user_provided",
            "approval_status": "approved",
            "user_approval": {"approved": True, "approved_by": "u", "approved_at": "t"},
        }
        assert not _reference_is_approved(ref)

    def test_risk_waiver_not_approved(self) -> None:
        ref = {
            "source_type": "risk_accepted",
            "approval_status": "pending",
            "risk_waiver": {"user_approved": False},
        }
        assert not _risk_waiver_is_approved(ref)


# ---------------------------------------------------------------------------
# runtime_consistency_check edge cases
# ---------------------------------------------------------------------------


class TestRuntimeConsistencyEdgeCases:
    def test_matching_runtimes_pass(self) -> None:
        result = check_runtime_consistency(
            {"render_runtime": "remotion"},
            {"render_runtime": "remotion"},
        )
        assert result["status"] == "PASS"
        assert result["match"] is True

    def test_missing_proposal_runtime_fails(self) -> None:
        result = check_runtime_consistency(
            {},
            {"render_runtime": "remotion"},
        )
        assert result["status"] == "FAIL"
        assert any("proposal" in i.lower() for i in result["issues"])

    def test_missing_edit_decisions_runtime_fails(self) -> None:
        result = check_runtime_consistency(
            {"render_runtime": "remotion"},
            {},
        )
        assert result["status"] == "FAIL"

    def test_swap_without_decision_log_fails(self) -> None:
        result = check_runtime_consistency(
            {"render_runtime": "remotion"},
            {"render_runtime": "hyperframes"},
        )
        assert result["status"] == "FAIL"
        assert any("Silent runtime swap" in i for i in result["issues"])

    def test_swap_with_unapproved_decision_fails(self) -> None:
        decision_log = {
            "decisions": [
                {
                    "category": "render_runtime_selection",
                    "user_approved": False,
                    "selected": "hyperframes",
                }
            ]
        }
        result = check_runtime_consistency(
            {"render_runtime": "remotion"},
            {"render_runtime": "hyperframes"},
            decision_log,
        )
        assert result["status"] == "FAIL"
        assert any("user_approved" in i for i in result["issues"])

    def test_swap_with_approved_decision_selecting_wrong_runtime_fails(self) -> None:
        decision_log = {
            "decisions": [
                {
                    "category": "render_runtime_selection",
                    "user_approved": True,
                    "selected": "ffmpeg",
                }
            ]
        }
        result = check_runtime_consistency(
            {"render_runtime": "remotion"},
            {"render_runtime": "hyperframes"},
            decision_log,
        )
        assert result["status"] == "FAIL"
        assert any("does not select actual" in i for i in result["issues"])

    def test_swap_with_correct_approved_decision_passes(self) -> None:
        decision_log = {
            "decisions": [
                {
                    "category": "render_runtime_selection",
                    "user_approved": True,
                    "selected": "hyperframes",
                }
            ]
        }
        result = check_runtime_consistency(
            {"render_runtime": "remotion"},
            {"render_runtime": "hyperframes"},
            decision_log,
        )
        assert result["status"] == "PASS"

    def test_legacy_embedded_decision_in_edit_decisions(self) -> None:
        edit_decisions = {
            "render_runtime": "hyperframes",
            "metadata": {
                "decision_log": {
                    "render_runtime_selection": {
                        "category": "render_runtime_selection",
                        "user_approved": True,
                        "selected": "hyperframes",
                    }
                }
            },
        }
        result = check_runtime_consistency(
            {"render_runtime": "remotion"}, edit_decisions
        )
        assert result["status"] == "PASS"

    def test_both_runtimes_none_fails(self) -> None:
        result = check_runtime_consistency({}, {})
        assert result["status"] == "FAIL"
        assert len(result["issues"]) >= 2

    def test_none_none_is_not_match(self) -> None:
        result = check_runtime_consistency({}, {})
        assert result["match"] is False


# ---------------------------------------------------------------------------
# sample_product_visibility_check edge cases
# ---------------------------------------------------------------------------


class TestSampleVisibilityEdgeCases:
    def test_empty_mandatory_elements_passes(self) -> None:
        bible = {"brand_constraints": {"mandatory_elements": []}}
        scene_plan = {"scenes": [{"id": "s1"}]}
        result = check_sample_visibility(bible, scene_plan, ["s1"])
        assert result["status"] == "PASS"

    def test_no_mandatory_elements_key_passes(self) -> None:
        bible = {"brand_constraints": {}}
        scene_plan = {"scenes": [{"id": "s1"}]}
        result = check_sample_visibility(bible, scene_plan, ["s1"])
        assert result["status"] == "PASS"

    def test_missing_scene_id_produces_issue(self) -> None:
        bible = {"brand_constraints": {"mandatory_elements": ["product logo"]}}
        scene_plan = {"scenes": []}
        result = check_sample_visibility(bible, scene_plan, ["nonexistent"])
        assert result["status"] == "FAIL"
        assert any("not found" in i for i in result["issues"])

    def test_negated_visual_constraint_excluded(self) -> None:
        assert _NEGATED_VISUAL_CONSTRAINT_RE.search("do not show the product")
        assert _NEGATED_VISUAL_CONSTRAINT_RE.search("product not visible yet")
        assert _NEGATED_VISUAL_CONSTRAINT_RE.search("no product shown")
        assert _NEGATED_VISUAL_CONSTRAINT_RE.search("keep product hidden")
        assert not _NEGATED_VISUAL_CONSTRAINT_RE.search("product appears in frame")

    def test_keyword_extraction(self) -> None:
        keywords = _extract_keywords("OPPO wordmark in final frame")
        assert "OPPO" in keywords
        assert "wordmark" in keywords
        assert "in" not in keywords

    def test_keyword_extraction_drops_quoted_content(self) -> None:
        keywords = _extract_keywords('Tagline "For everyone who sees."')
        assert "For" not in keywords

    def test_single_keyword_overlap_is_partial(self) -> None:
        bible = {"brand_constraints": {"mandatory_elements": ["OPPO Find X9 Pro"]}}
        scene_plan = {"scenes": [
            {"id": "s1", "description": "A beautiful OPPO device on a table"}
        ]}
        result = check_sample_visibility(bible, scene_plan, ["s1"])
        assert result["status"] == "WARN"
        assert result["partial_hits"]

    def test_two_keyword_overlap_is_full_match(self) -> None:
        bible = {"brand_constraints": {"mandatory_elements": ["OPPO Find X9 Pro"]}}
        scene_plan = {"scenes": [
            {"id": "s1", "description": "OPPO Find X9 Pro smartphone reveal"}
        ]}
        result = check_sample_visibility(bible, scene_plan, ["s1"])
        assert result["status"] == "PASS"
        assert result["matches"]

    def test_no_keyword_overlap_fails(self) -> None:
        bible = {"brand_constraints": {"mandatory_elements": ["OPPO Find X9 Pro"]}}
        scene_plan = {"scenes": [
            {"id": "s1", "description": "A sunset over the ocean"}
        ]}
        result = check_sample_visibility(bible, scene_plan, ["s1"])
        assert result["status"] == "FAIL"
