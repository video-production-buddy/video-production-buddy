"""Sample product-visibility validator regressions."""

from __future__ import annotations

from tools.validation.sample_product_visibility_check import check_sample_visibility


def test_sample_visibility_matches_mandatory_element_in_visual_constraint() -> None:
    bible = {
        "brand_constraints": {
            "mandatory_elements": ["OPPO Find X9 Pro camera island"],
        }
    }
    scene_plan = {
        "scenes": [
            {
                "id": "hook",
                "description": "Abstract light sweeps across the launch frame.",
                "visual_constraint": (
                    "OPPO Find X9 Pro camera island visible in a macro hero shot."
                ),
                "scene_type": "creator_workflow_scene",
            }
        ]
    }

    verdict = check_sample_visibility(bible, scene_plan, ["hook"])

    assert verdict["status"] == "PASS"
    assert verdict["matches"][0]["scene_id"] == "hook"


def test_sample_visibility_does_not_match_negated_visual_constraint() -> None:
    bible = {
        "brand_constraints": {
            "mandatory_elements": ["OPPO Find X9 Pro camera island"],
        }
    }
    scene_plan = {
        "scenes": [
            {
                "id": "hook",
                "description": "Abstract light sweep with no product in frame.",
                "visual_constraint": (
                    "Do not reveal the OPPO Find X9 Pro camera island yet; "
                    "keep it hidden until the final scene."
                ),
                "scene_type": "creator_workflow_scene",
            }
        ]
    }

    verdict = check_sample_visibility(bible, scene_plan, ["hook"])

    assert verdict["status"] == "FAIL"
    assert verdict["matches"] == []
    assert "product-visible scene" in verdict["issues"][0]


def test_sample_visibility_does_not_match_negated_description() -> None:
    bible = {
        "brand_constraints": {
            "mandatory_elements": ["OPPO Find X9 Pro camera island"],
        }
    }
    scene_plan = {
        "scenes": [
            {
                "id": "hook",
                "description": (
                    "Do not reveal the OPPO Find X9 Pro camera island yet; "
                    "keep the phone hidden behind abstract reflections."
                ),
                "scene_type": "creator_workflow_scene",
            }
        ]
    }

    verdict = check_sample_visibility(bible, scene_plan, ["hook"])

    assert verdict["status"] == "FAIL"
    assert verdict["matches"] == []
    assert any("product-visible scene" in issue for issue in verdict["issues"])


def test_sample_visibility_requires_selected_product_visible_scene_when_plan_has_one() -> None:
    bible = {"brand_constraints": {"mandatory_elements": []}}
    scene_plan = {
        "scenes": [
            {
                "id": "hook",
                "description": "Creator struggles with a cluttered workflow.",
                "product_visibility": "none",
                "product_reference_required": False,
            },
            {
                "id": "hero",
                "description": "OPPO Find X9 Pro camera island fills the frame.",
                "product_visibility": "hero",
                "product_reference_required": True,
            },
        ]
    }

    verdict = check_sample_visibility(bible, scene_plan, ["hook"])

    assert verdict["status"] == "FAIL"
    assert "product-visible scene" in verdict["issues"][0]


def test_sample_visibility_product_visible_requirement_overrides_partial_keyword_hit() -> None:
    bible = {
        "brand_constraints": {
            "mandatory_elements": ["OPPO Find X9 Pro camera island"],
        }
    }
    scene_plan = {
        "scenes": [
            {
                "id": "hook",
                "description": "Creator mentions OPPO in a caption over a desk montage.",
                "product_visibility": "none",
                "product_reference_required": False,
            },
            {
                "id": "hero",
                "description": "OPPO Find X9 Pro camera island fills the frame.",
                "product_visibility": "hero",
                "product_reference_required": True,
            },
        ]
    }

    verdict = check_sample_visibility(bible, scene_plan, ["hook"])

    assert verdict["status"] == "FAIL"
    assert verdict["partial_hits"]
    assert any("product-visible scene" in issue for issue in verdict["issues"])
