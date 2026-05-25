"""Ad-video governance contract regressions: hallucination, product identity, runtime consistency, KVM coverage."""

from __future__ import annotations

from copy import deepcopy

import pytest

from schemas.artifacts import validate_artifact
from tools.validation.hallucination_contract_check import check_hallucination_contract
from tools.validation.product_identity_consistency_check import (
    check_product_identity_consistency,
)
from tools.validation.runtime_consistency_check import check_runtime_consistency
from tools.validation.scene_fidelity_check import check_kvm_coverage

from tests.contracts.conftest import (
    _approved_hallucination_waiver_log,
    _approved_product_identity_reference,
    _asset_manifest_for_hallucination,
    _bible_with_truth_contract,
    _conditioned_asset_manifest,
    _minimal_production_proposal,
    _product_visible_scene_plan,
    _scene_plan_for_hallucination,
    _two_product_visible_scene_plan,
)


def test_asset_manifest_schema_accepts_hallucination_review() -> None:
    """Asset manifests must record keyframe review verdicts for generated clips."""
    manifest = _asset_manifest_for_hallucination()
    validate_artifact("asset_manifest", manifest)

    bad = deepcopy(manifest)
    del bad["assets"][0]["hallucination_review"]["reviewer"]
    with pytest.raises(Exception):
        validate_artifact("asset_manifest", bad)

    bad = deepcopy(manifest)
    bad["assets"][0]["hallucination_review"]["status"] = "WAIVED"
    with pytest.raises(Exception):
        validate_artifact("asset_manifest", bad)

    waived = deepcopy(manifest)
    waived["assets"][0]["hallucination_review"]["status"] = "WAIVED"
    waived["assets"][0]["hallucination_review"]["waiver_decision_id"] = "d-waive-001"
    validate_artifact("asset_manifest", waived)


def test_hallucination_contract_rejects_missing_scene_checks_for_high_risk_scene() -> None:
    verdict = check_hallucination_contract(
        _bible_with_truth_contract(),
        _scene_plan_for_hallucination(include_checks=False),
        {"version": "1.0", "assets": []},
    )

    assert verdict["status"] == "FAIL"
    assert any("hallucination_checks" in issue for issue in verdict["issues"])


def test_hallucination_contract_rejects_missing_asset_review() -> None:
    verdict = check_hallucination_contract(
        _bible_with_truth_contract(),
        _scene_plan_for_hallucination(),
        _asset_manifest_for_hallucination(include_review=False),
    )

    assert verdict["status"] == "FAIL"
    assert any("hallucination_review" in issue for issue in verdict["issues"])


def test_hallucination_contract_rejects_missing_generated_visual_asset() -> None:
    verdict = check_hallucination_contract(
        _bible_with_truth_contract(),
        _scene_plan_for_hallucination(),
        {"version": "1.0", "assets": []},
    )

    assert verdict["status"] == "FAIL"
    assert any("no generated visual asset" in issue for issue in verdict["issues"])


def test_hallucination_contract_rejects_blocker_flag() -> None:
    verdict = check_hallucination_contract(
        _bible_with_truth_contract(),
        _scene_plan_for_hallucination(),
        _asset_manifest_for_hallucination(review_status="FLAG", check_status="FLAG"),
    )

    assert verdict["status"] == "FAIL"
    assert any("FLAG" in issue for issue in verdict["issues"])


def test_hallucination_contract_accepts_product_visible_scene_with_review() -> None:
    verdict = check_hallucination_contract(
        _bible_with_truth_contract(),
        _scene_plan_for_hallucination(),
        _asset_manifest_for_hallucination(),
    )

    assert verdict["status"] == "PASS"
    assert verdict["summary"]["high_risk_scenes"] == 1
    assert verdict["summary"]["reviewed_assets"] == 1


def test_hallucination_contract_accepts_approved_waiver() -> None:
    verdict = check_hallucination_contract(
        _bible_with_truth_contract(),
        _scene_plan_for_hallucination(),
        _asset_manifest_for_hallucination(
            review_status="WAIVED",
            check_status="WAIVED",
            waiver_decision_id="d-waive-001",
        ),
        _approved_hallucination_waiver_log(),
    )

    assert verdict["status"] == "WARN"
    assert verdict["summary"]["waivers"] == 1


def test_hallucination_contract_rejects_visual_accuracy_decision_for_waiver() -> None:
    decision_log = _approved_hallucination_waiver_log()
    decision_log["decisions"][0]["category"] = "visual_accuracy_check"

    verdict = check_hallucination_contract(
        _bible_with_truth_contract(),
        _scene_plan_for_hallucination(),
        _asset_manifest_for_hallucination(
            review_status="WAIVED",
            check_status="WAIVED",
            waiver_decision_id="d-waive-001",
        ),
        decision_log,
    )

    assert verdict["status"] == "FAIL"
    assert any("hallucination_review_waiver" in issue for issue in verdict["issues"])


def test_hallucination_contract_rejects_non_waiver_selection_for_waiver() -> None:
    decision_log = _approved_hallucination_waiver_log()
    decision_log["decisions"][0]["selected"] = "regenerate"

    verdict = check_hallucination_contract(
        _bible_with_truth_contract(),
        _scene_plan_for_hallucination(),
        _asset_manifest_for_hallucination(
            review_status="WAIVED",
            check_status="WAIVED",
            waiver_decision_id="d-waive-001",
        ),
        decision_log,
    )

    assert verdict["status"] == "FAIL"
    assert any("selected" in issue and "waiver" in issue.lower() for issue in verdict["issues"])


def test_hallucination_contract_rejects_waiver_without_user_approval() -> None:
    verdict = check_hallucination_contract(
        _bible_with_truth_contract(),
        _scene_plan_for_hallucination(),
        _asset_manifest_for_hallucination(
            review_status="WAIVED",
            check_status="WAIVED",
            waiver_decision_id="d-waive-001",
        ),
        {"version": "1.0", "project_id": "missing-waiver", "decisions": []},
    )

    assert verdict["status"] == "FAIL"
    assert any("waiver" in issue.lower() for issue in verdict["issues"])


def test_hallucination_contract_accepts_non_product_text_card_without_checks() -> None:
    verdict = check_hallucination_contract(
        _bible_with_truth_contract(),
        _scene_plan_for_hallucination(include_checks=False, text_card=True),
        {"version": "1.0", "assets": []},
    )

    assert verdict["status"] == "PASS"
    assert verdict["summary"]["high_risk_scenes"] == 0


def test_hallucination_contract_skips_sourced_visual_assets() -> None:
    scene_plan = {
        "version": "1.0",
        "style_mode": "cinematic",
        "scenes": [
            {
                "id": "scene-1",
                "type": "broll",
                "description": "User-provided product footage.",
                "start_seconds": 0,
                "end_seconds": 5,
                "core": True,
                "motion_required": True,
                "product_visibility": "hero",
                "product_reference_required": True,
                "required_assets": [
                    {
                        "type": "video",
                        "description": "Provided footage from the user.",
                        "source": "provided",
                    }
                ],
            }
        ],
    }
    asset_manifest = {
        "version": "1.0",
        "assets": [
            {
                "id": "scene-1-source-video",
                "type": "video",
                "path": "assets/video/scene-1-source.mp4",
                "source_tool": "user_upload",
                "scene_id": "scene-1",
                "subtype": "provided",
            }
        ],
    }

    verdict = check_hallucination_contract(
        _bible_with_truth_contract(),
        scene_plan,
        asset_manifest,
    )

    assert verdict["status"] == "PASS"
    assert verdict["summary"]["high_risk_scenes"] == 0
    assert verdict["summary"]["reviewed_assets"] == 0


def test_hallucination_contract_uses_asset_generation_metadata_for_scope() -> None:
    scene_plan = _scene_plan_for_hallucination()
    scene_plan["scenes"][0]["type"] = "broll"
    scene_plan["scenes"][0]["required_assets"] = [
        {
            "type": "video",
            "description": "A visual asset whose actual manifest provenance decides scope.",
            "source": "provided",
        }
    ]

    verdict = check_hallucination_contract(
        _bible_with_truth_contract(),
        scene_plan,
        _asset_manifest_for_hallucination(),
    )

    assert verdict["status"] == "PASS"
    assert verdict["summary"]["high_risk_scenes"] == 1
    assert verdict["summary"]["reviewed_assets"] == 1


def test_kvm_coverage_reads_visual_key_visual_moments() -> None:
    bible = {
        "visual": {
            "key_visual_moments": [
                {
                    "moment_id": "KVM-1",
                    "description": "Product reveal lands at the emotional peak.",
                    "maps_to_beat": "B3",
                    "mandatory": True,
                }
            ]
        }
    }
    scene_plan = {"scenes": [{"id": "scene-1", "fulfills_kvm": []}]}

    report = check_kvm_coverage(bible, scene_plan)

    assert report["summary"]["kvms_checked"] == 1
    assert report["ok"] is False
    assert report["issues"][0]["kvm_id"] == "KVM-1"


def test_kvm_coverage_requires_fulfilling_scenes_to_carry_required_motion_primitives() -> None:
    bible = {
        "visual": {
            "key_visual_moments": [
                {
                    "moment_id": "KVM-1",
                    "description": "Product reveal lands at the emotional peak.",
                    "maps_to_beat": "B3",
                    "mandatory": True,
                    "required_motion_primitives": [
                        "camera_push",
                        "product_reveal",
                    ],
                }
            ]
        }
    }
    scene_plan = {
        "scenes": [
            {
                "id": "scene-1",
                "fulfills_kvm": ["KVM-1"],
                "motion_specs": ["camera_push"],
            }
        ]
    }

    report = check_kvm_coverage(bible, scene_plan)

    assert report["ok"] is False
    assert report["issues"][0]["kind"] == "missing_required_motion_primitives"
    assert report["issues"][0]["scene_id"] == "scene-1"
    assert report["issues"][0]["kvm_id"] == "KVM-1"
    assert report["issues"][0]["missing_motion_primitives"] == ["product_reveal"]

    scene_plan["scenes"][0]["motion_specs"].append("product_reveal")
    report = check_kvm_coverage(bible, scene_plan)

    assert report["ok"] is True
    assert report["issues"] == []


def test_runtime_consistency_accepts_user_approved_decision_log_swap() -> None:
    proposal = {"render_runtime": "remotion"}
    edit_decisions = {"render_runtime": "hyperframes"}
    decision_log = {
        "version": "1.0",
        "project_id": "runtime-swap-regression",
        "decisions": [
            {
                "decision_id": "d-001",
                "stage": "proposal",
                "category": "render_runtime_selection",
                "subject": "Composition runtime",
                "options_considered": [
                    {
                        "option_id": "remotion",
                        "label": "Remotion",
                        "score": 0.8,
                        "reason": "Available baseline",
                    },
                    {
                        "option_id": "hyperframes",
                        "label": "HyperFrames",
                        "score": 0.9,
                        "reason": "Better for the approved kinetic typography route",
                    },
                ],
                "selected": "hyperframes",
                "reason": "User approved HyperFrames after seeing the tradeoff.",
                "user_visible": True,
                "user_approved": True,
            }
        ],
    }

    verdict = check_runtime_consistency(proposal, edit_decisions, decision_log)

    assert verdict["status"] == "PASS"
    assert verdict["decision_present"] is True
    assert verdict["decision_user_approved"] is True
    assert verdict["decision_selected_runtime"] == "hyperframes"
    assert verdict["decision_matches_actual"] is True


def test_runtime_consistency_rejects_approved_old_selection_for_new_actual() -> None:
    proposal = {"render_runtime": "remotion"}
    edit_decisions = {"render_runtime": "hyperframes"}
    decision_log = {
        "version": "1.0",
        "project_id": "runtime-swap-regression",
        "decisions": [
            {
                "decision_id": "d-001",
                "stage": "proposal",
                "category": "render_runtime_selection",
                "subject": "Composition runtime",
                "options_considered": [
                    {
                        "option_id": "remotion",
                        "label": "Remotion",
                        "score": 0.9,
                        "reason": "User originally approved Remotion",
                    },
                    {
                        "option_id": "hyperframes",
                        "label": "HyperFrames",
                        "score": 0.7,
                        "reason": "Considered but rejected",
                    },
                ],
                "selected": "remotion",
                "reason": "Initial proposal approval selected Remotion.",
                "user_visible": True,
                "user_approved": True,
            }
        ],
    }

    verdict = check_runtime_consistency(proposal, edit_decisions, decision_log)

    assert verdict["status"] == "FAIL"
    assert verdict["decision_present"] is True
    assert verdict["decision_user_approved"] is True
    assert verdict["decision_selected_runtime"] == "remotion"
    assert verdict["decision_matches_actual"] is False
    assert any("selected 'remotion'" in issue for issue in verdict["issues"])


def test_runtime_consistency_rejects_approved_swap_without_selected_runtime() -> None:
    proposal = {"render_runtime": "remotion"}
    edit_decisions = {"render_runtime": "hyperframes"}
    decision_log = {
        "version": "1.0",
        "project_id": "runtime-swap-regression",
        "decisions": [
            {
                "decision_id": "d-001",
                "stage": "edit",
                "category": "render_runtime_selection",
                "subject": "Composition runtime",
                "options_considered": [],
                "reason": "User approved a runtime swap, but the selected runtime was not recorded.",
                "user_visible": True,
                "user_approved": True,
            }
        ],
    }

    verdict = check_runtime_consistency(proposal, edit_decisions, decision_log)

    assert verdict["status"] == "FAIL"
    assert verdict["decision_selected_runtime"] is None
    assert verdict["decision_matches_actual"] is False
    assert any("does not select actual runtime 'hyperframes'" in issue for issue in verdict["issues"])


def test_decision_log_accepts_product_identity_reference_selection_category() -> None:
    decision_log = {
        "version": "1.0",
        "project_id": "product-reference-regression",
        "decisions": [
            {
                "decision_id": "d-001",
                "stage": "proposal",
                "category": "product_identity_reference_selection",
                "subject": "Product identity reference strategy",
                "options_considered": [
                    {
                        "option_id": "generate_concept_reference",
                        "label": "Generate concept reference",
                        "score": 0.8,
                        "reason": "No user product photo was available.",
                    }
                ],
                "selected": "generate_concept_reference",
                "reason": "User approved generated reference candidates before video generation.",
                "user_visible": True,
                "user_approved": True,
            }
        ],
    }

    validate_artifact("decision_log", decision_log)


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


def test_product_identity_consistency_rejects_visible_scene_without_reference_or_waiver() -> None:
    reference = {
        "version": "1.0",
        "reference_id": "pir-none",
        "product_name": "OPPO Find X9 Pro",
        "source_type": "not_applicable",
        "approval_status": "not_required",
        "required_visual_features": [],
        "prohibited_variations": [],
    }

    verdict = check_product_identity_consistency(
        reference,
        _product_visible_scene_plan(),
        {"version": "1.0", "assets": []},
    )

    assert verdict["status"] == "FAIL"
    assert any("approved product identity reference" in issue for issue in verdict["issues"])


def test_product_identity_consistency_accepts_approved_generated_reference_and_conditioned_assets() -> None:
    verdict = check_product_identity_consistency(
        _approved_product_identity_reference(),
        _product_visible_scene_plan(),
        _conditioned_asset_manifest(),
    )

    assert verdict["status"] == "PASS"
    assert verdict["summary"]["product_visible_scenes"] == 1
    assert verdict["summary"]["conditioned_assets_checked"] == 1


def test_product_identity_consistency_sample_scope_ignores_unselected_future_scenes() -> None:
    """Sample approval must not require visual assets for product scenes outside the sample."""
    verdict = check_product_identity_consistency(
        _approved_product_identity_reference(),
        _two_product_visible_scene_plan(),
        _conditioned_asset_manifest(),
        generated_scene_ids=["scene-1"],
    )

    assert verdict["status"] == "PASS"
    assert verdict["summary"]["product_visible_scenes"] == 2
    assert verdict["summary"]["asset_required_product_visible_scenes"] == 1
    assert verdict["summary"]["conditioned_assets_checked"] == 1


def test_product_identity_consistency_full_scope_rejects_missing_future_scene_asset() -> None:
    """Full asset review still requires assets for every product-visible scene."""
    verdict = check_product_identity_consistency(
        _approved_product_identity_reference(),
        _two_product_visible_scene_plan(),
        _conditioned_asset_manifest(),
    )

    assert verdict["status"] == "FAIL"
    assert any("scene-2" in issue for issue in verdict["issues"])


def test_product_identity_consistency_rejects_risk_waiver_without_user_approval() -> None:
    reference = {
        "version": "1.0",
        "reference_id": "pir-risk",
        "product_name": "OPPO Find X9 Pro",
        "source_type": "risk_accepted",
        "approval_status": "pending",
        "required_visual_features": [],
        "prohibited_variations": ["generic phone silhouette"],
        "risk_waiver": {
            "reason": "User has no product photos.",
            "user_approved": False,
            "decision_id": "d-001",
        },
    }
    manifest = _conditioned_asset_manifest(conditioning_mode="text_only_waived")
    manifest["assets"][0]["product_identity_conditioning"].pop("approved_reference_path")

    verdict = check_product_identity_consistency(
        reference,
        _product_visible_scene_plan(),
        manifest,
    )

    assert verdict["status"] == "FAIL"
    assert any("risk waiver" in issue for issue in verdict["issues"])


def test_product_identity_consistency_accepts_non_product_visible_not_applicable() -> None:
    reference = {
        "version": "1.0",
        "reference_id": "pir-none",
        "product_name": "Acme SaaS",
        "source_type": "not_applicable",
        "approval_status": "not_required",
        "required_visual_features": [],
        "prohibited_variations": [],
    }
    scene_plan = {
        "version": "1.0",
        "style_mode": "animated",
        "scenes": [
            {
                "id": "scene-1",
                "type": "text_card",
                "description": "Animated headline card.",
                "start_seconds": 0,
                "end_seconds": 5,
                "core": True,
                "motion_required": False,
                "product_visibility": "none",
                "product_reference_required": False,
            }
        ],
    }

    verdict = check_product_identity_consistency(
        reference,
        scene_plan,
        {"version": "1.0", "assets": []},
    )

    assert verdict["status"] == "PASS"
    assert verdict["summary"]["product_visible_scenes"] == 0
