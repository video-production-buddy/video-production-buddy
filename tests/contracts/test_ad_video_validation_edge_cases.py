"""Fine-grained edge-case tests for ad-video validation tools.

Tests hallucination_contract_check, product_identity_consistency_check,
runtime_consistency_check, sample_product_visibility_check, scene_fidelity_check,
and planning_chain_check at boundary conditions.
"""

from __future__ import annotations

import importlib
import json

import pytest

from tools.validation.hallucination_contract_check import (
    HallucinationContractCheck,
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
    ProductIdentityConsistencyCheck,
    check_product_identity_consistency,
    _reference_is_approved,
    _risk_waiver_is_approved,
)
from tools.validation.runtime_consistency_check import (
    RuntimeConsistencyCheck,
    check_runtime_consistency,
)
from tools.validation.sample_product_visibility_check import (
    SampleProductVisibilityCheck,
    _extract_keywords,
    _NEGATED_VISUAL_CONSTRAINT_RE,
    check_sample_visibility,
)
from tools.validation.scene_fidelity_check import SceneFidelityCheck, check_plan, load_registry


def _provider_consistency_module():
    try:
        return importlib.import_module("tools.validation.provider_consistency_check")
    except ModuleNotFoundError as exc:
        pytest.fail(f"provider_consistency_check tool is missing: {exc}")


def _provider_locked_proposal(**overrides) -> dict:
    proposal = {
        "render_runtime": "ffmpeg",
        "music_strategy": "generative_loose",
        "audio_contract": {
            "voice_provider": "qwen3",
            "voice_model": "qwen3-tts-instruct-flash",
        },
        "visual_contract": {
            "visual_asset_provider_locks": [
                {
                    "asset_type": "image",
                    "source_tool": "wanx_image",
                    "model": "wan2.7-image-pro",
                    "usage": "still product images",
                },
                {
                    "asset_type": "video",
                    "source_tool": "wan_video_api",
                    "model": "wan2.6-t2v",
                    "usage": "generated motion clips",
                },
                {
                    "asset_type": "video",
                    "source_tool": "pexels_video",
                    "usage": "stock establishing clips",
                },
            ]
        },
    }
    proposal.update(overrides)
    return proposal


def _provider_script(*section_ids: str) -> dict:
    ids = section_ids or ("hook", "body")
    sections = []
    cursor = 0.0
    for section_id in ids:
        end = cursor + 4.0
        sections.append(
            {
                "id": section_id,
                "narration": f"Narration for {section_id}.",
                "start_seconds": cursor,
                "end_seconds": end,
            }
        )
        cursor = end
    return {
        "version": "1.0",
        "sections": sections,
        "total_duration_seconds": cursor,
    }


def _provider_asset_manifest(*assets: dict, **overrides) -> dict:
    manifest = {
        "version": "1.0",
        "assets": list(assets)
        or [
            {
                "id": "narr-hook",
                "type": "narration",
                "path": "assets/audio/hook.mp3",
                "source_tool": "cosyvoice_tts",
                "scene_id": "global",
                "model": "qwen3-tts-instruct-flash",
            },
            {
                "id": "music-1",
                "type": "music",
                "path": "assets/music/background.mp3",
                "source_tool": "minimax_music",
                "scene_id": "global",
                "model": "music-2.6",
            },
        ],
    }
    manifest.update(overrides)
    return manifest


def _approved_provider_decision(selected: str) -> dict:
    return {
        "version": "1.0",
        "project_id": "ad-test",
        "decisions": [
            {
                "decision_id": "d-provider-1",
                "stage": "assets",
                "category": "provider_selection",
                "subject": "Narration provider substitution",
                "options_considered": [
                    {
                        "option_id": selected,
                        "label": selected,
                        "score": 0.8,
                        "reason": "Approved fallback.",
                    }
                ],
                "selected": selected,
                "reason": "User approved provider substitution after original path failed.",
                "user_visible": True,
                "user_approved": True,
            }
        ],
    }


def _approved_budget_tradeoff_decision(selected: str = "approve-overage") -> dict:
    return {
        "version": "1.0",
        "project_id": "ad-test",
        "decisions": [
            {
                "decision_id": "d-budget-1",
                "stage": "assets",
                "category": "budget_tradeoff",
                "subject": "Asset generation budget overage",
                "options_considered": [
                    {
                        "option_id": selected,
                        "label": selected,
                        "score": 0.7,
                        "reason": "Budget tradeoff option shown to the user.",
                    }
                ],
                "selected": selected,
                "reason": "User approved the selected budget tradeoff before compose.",
                "user_visible": True,
                "user_approved": True,
            }
        ],
    }


def _approved_music_source_decision(selected: str) -> dict:
    return {
        "version": "1.0",
        "project_id": "ad-test",
        "decisions": [
            {
                "decision_id": "d-music-source-1",
                "stage": "assets",
                "category": "music_source",
                "subject": "Music source substitution",
                "options_considered": [
                    {
                        "option_id": selected,
                        "label": selected,
                        "score": 0.6,
                        "reason": "User approved a music source change.",
                    }
                ],
                "selected": selected,
                "reason": "User approved the music source substitution.",
                "user_visible": True,
                "user_approved": True,
            }
        ],
    }


def _approved_music_strategy_decision(selected: str) -> dict:
    return {
        "version": "1.0",
        "project_id": "ad-test",
        "decisions": [
            {
                "decision_id": "d-music-strategy-1",
                "stage": "assets",
                "category": "music_strategy_selection",
                "subject": "Music strategy substitution",
                "options_considered": [
                    {
                        "option_id": selected,
                        "label": selected,
                        "score": 0.7,
                        "reason": "User approved a music strategy change.",
                    }
                ],
                "selected": selected,
                "reason": "User approved the music strategy substitution.",
                "user_visible": True,
                "user_approved": True,
            }
        ],
    }


def _library_music_asset(*, drift_seconds: float = 0.2, include_alignment: bool = True) -> dict:
    asset = {
        "id": "music-1",
        "type": "music",
        "path": "assets/music/background.mp3",
        "source_tool": "music_library",
        "scene_id": "global",
    }
    if include_alignment:
        asset["music_alignment"] = {
            "strategy": "library_locked",
            "target_peak_seconds": 18.0,
            "selected_peak_seconds": 30.0,
            "aligned_peak_seconds": 18.2,
            "drift_seconds": drift_seconds,
            "timing_sidecar_path": "music_library/background.timing.json",
            "evidence": "Validated music_library timing sidecar and trimmed track.",
        }
    return asset


def _search_aligned_music_asset(*, include_alignment: bool = True) -> dict:
    asset = {
        "id": "music-1",
        "type": "music",
        "path": "assets/music/background.mp3",
        "source_tool": "pixabay_music",
        "scene_id": "global",
        "model": "pixabay-search",
    }
    if include_alignment:
        asset["music_alignment"] = {
            "strategy": "search_align",
            "target_peak_seconds": 18.0,
            "selected_peak_seconds": 26.4,
            "aligned_peak_seconds": 17.9,
            "drift_seconds": -0.1,
            "beat_detection_report": {
                "source": "lib.beat_detector",
                "drop_seconds": [26.4],
            },
            "evidence": "Detected stock track drop and trimmed to target peak.",
        }
    return asset


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

    def test_duplicate_scene_hallucination_check_ids_fail(self) -> None:
        bible = _minimal_bible()
        scene = _minimal_scene()
        scene["hallucination_checks"].append({
            "check_id": "geo",
            "category": "product_geometry",
            "requirement": "second check with same id",
            "prohibited_failure": "ambiguous review mapping",
            "severity": "critical",
            "evidence_source": "keyframe",
        })
        asset = _minimal_asset()

        result = check_hallucination_contract(
            bible, {"scenes": [scene]}, {"assets": [asset]}
        )

        assert result["status"] == "FAIL"
        assert any("duplicate hallucination check id" in i for i in result["issues"])

    def test_duplicate_asset_review_verdict_ids_fail(self) -> None:
        bible = _minimal_bible()
        scene = _minimal_scene()
        asset = _minimal_asset()
        asset["hallucination_review"]["check_verdicts"].append(
            {"check_id": "geo", "status": "PASS", "severity": "critical"}
        )

        result = check_hallucination_contract(
            bible, {"scenes": [scene]}, {"assets": [asset]}
        )

        assert result["status"] == "FAIL"
        assert any("duplicate hallucination_review verdict id" in i for i in result["issues"])

    def test_high_risk_scene_with_no_generated_visual_asset(self) -> None:
        bible = _minimal_bible()
        scene = _minimal_scene()
        result = check_hallucination_contract(
            bible, {"scenes": [scene]}, {"assets": []}
        )
        assert result["status"] == "FAIL"
        assert any("no generated visual asset" in i for i in result["issues"])

    def test_generated_visual_asset_with_unknown_scene_id_fails(self) -> None:
        bible = _minimal_bible()
        asset = _minimal_asset("a-unknown", "missing-scene")
        result = check_hallucination_contract(
            bible, {"scenes": []}, {"assets": [asset]}
        )

        assert result["status"] == "FAIL"
        assert any("missing-scene" in i and "scene_plan" in i for i in result["issues"])

    def test_generated_scene_ids_must_be_list_of_strings(self) -> None:
        result = check_hallucination_contract(
            _minimal_bible(),
            {"scenes": [_minimal_scene("s1")]},
            {"assets": [_minimal_asset("a1", "s1")]},
            generated_scene_ids="s1",  # type: ignore[arg-type]
        )

        assert result["status"] == "FAIL"
        assert any("generated_scene_ids must be a list" in i for i in result["issues"])

    def test_duplicate_generated_scene_ids_fail(self) -> None:
        result = check_hallucination_contract(
            _minimal_bible(),
            {"scenes": [_minimal_scene("s1")]},
            {"assets": [_minimal_asset("a1", "s1")]},
            generated_scene_ids=["s1", "s1"],
        )

        assert result["status"] == "FAIL"
        assert any("duplicate" in i for i in result["issues"])

    def test_sourced_asset_not_treated_as_generated(self) -> None:
        asset = {
            "type": "video",
            "subtype": "stock",
            "license": "CC-BY",
            "original_url": "https://example.com/vid.mp4",
        }
        assert _asset_has_sourced_provenance(asset)

    def test_user_upload_source_tool_is_sourced_provenance(self) -> None:
        asset = {
            "type": "video",
            "source_tool": "user_upload",
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
        assert _selected_option_is_waiver(
            {
                "selected": "waiver",
                "options_considered": [
                    {"option_id": "waiver", "label": "Waiver"}
                ],
            }
        )

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

    def test_selected_waiver_must_be_in_options_considered(self) -> None:
        assert not _selected_option_is_waiver(
            {
                "selected": "waiver",
                "options_considered": [
                    {"option_id": "regenerate", "label": "Regenerate"}
                ],
            }
        )


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
            "options_considered": [
                {"option_id": "waiver", "label": "Waiver"}
            ],
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

    def test_sourced_product_visible_asset_does_not_require_generation_conditioning(self) -> None:
        reference = self._approved_reference()
        scene_plan = {"scenes": [
            {"id": "s1", "product_visibility": "hero", "product_reference_required": True}
        ]}
        asset_manifest = {"assets": [
            {
                "id": "a-user-product-shot",
                "scene_id": "s1",
                "type": "video",
                "subtype": "user_provided",
                "path": "reference_assets/product_demo.mp4",
                "source_tool": "user_upload",
            }
        ]}

        result = check_product_identity_consistency(
            reference, scene_plan, asset_manifest
        )

        assert result["status"] == "PASS"
        assert result["summary"]["conditioned_assets_checked"] == 0

    def test_user_upload_source_tool_does_not_require_generation_conditioning(self) -> None:
        reference = self._approved_reference()
        scene_plan = {"scenes": [
            {"id": "s1", "product_visibility": "hero", "product_reference_required": True}
        ]}
        asset_manifest = {"assets": [
            {
                "id": "a-user-product-shot",
                "scene_id": "s1",
                "type": "video",
                "path": "reference_assets/product_demo.mp4",
                "source_tool": "user_upload",
            }
        ]}

        result = check_product_identity_consistency(
            reference, scene_plan, asset_manifest
        )

        assert result["status"] == "PASS"
        assert result["summary"]["conditioned_assets_checked"] == 0

    def test_visual_asset_with_unknown_scene_id_fails(self) -> None:
        reference = self._approved_reference()
        scene_plan = {"scenes": []}
        asset_manifest = {"assets": [
            {
                "id": "a-unknown",
                "scene_id": "missing-scene",
                "type": "video",
                "product_identity_conditioning": {
                    "conditioning_mode": "reference",
                    "approved_reference_id": "ref-1",
                    "approved_reference_path": "/path/to/ref.png",
                },
            }
        ]}

        result = check_product_identity_consistency(
            reference, scene_plan, asset_manifest
        )

        assert result["status"] == "FAIL"
        assert any("missing-scene" in issue and "scene_plan" in issue for issue in result["issues"])

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

    def test_empty_generated_scene_ids_cannot_bypass_product_visible_scenes(self) -> None:
        reference = self._approved_reference()
        scene_plan = {"scenes": [
            {"id": "s1", "product_visibility": "hero", "product_reference_required": True},
        ]}
        asset_manifest = {"assets": []}

        result = check_product_identity_consistency(
            reference,
            scene_plan,
            asset_manifest,
            generated_scene_ids=[],
        )

        assert result["status"] == "FAIL"
        assert any("generated_scene_ids" in issue for issue in result["issues"])

    def test_generated_scene_ids_missing_from_plan_fails(self) -> None:
        reference = self._approved_reference()
        scene_plan = {"scenes": [{"id": "s1", "product_visibility": "none"}]}
        asset_manifest = {"assets": []}
        result = check_product_identity_consistency(
            reference, scene_plan, asset_manifest, generated_scene_ids=["s_missing"]
        )
        assert result["status"] == "FAIL"

    def test_generated_scene_ids_must_be_list_of_strings(self) -> None:
        reference = self._approved_reference()
        scene_plan = {"scenes": [
            {"id": "s1", "product_visibility": "hero", "product_reference_required": True}
        ]}
        asset_manifest = {"assets": []}
        result = check_product_identity_consistency(
            reference,
            scene_plan,
            asset_manifest,
            generated_scene_ids="s1",  # type: ignore[arg-type]
        )

        assert result["status"] == "FAIL"
        assert any("generated_scene_ids must be a list" in issue for issue in result["issues"])

    def test_duplicate_generated_scene_ids_fail(self) -> None:
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
                },
            }
        ]}
        result = check_product_identity_consistency(
            reference,
            scene_plan,
            asset_manifest,
            generated_scene_ids=["s1", "s1"],
        )

        assert result["status"] == "FAIL"
        assert any("duplicate" in issue for issue in result["issues"])

    def test_generated_scene_ids_are_trimmed_before_scope_matching(self) -> None:
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
                },
            }
        ]}
        result = check_product_identity_consistency(
            reference,
            scene_plan,
            asset_manifest,
            generated_scene_ids=[" s1 "],
        )

        assert result["status"] == "PASS"
        assert result["summary"]["asset_required_product_visible_scenes"] == 1

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

    def test_reference_is_approved_rejects_missing_reference_id(self) -> None:
        ref = {
            "source_type": "user_provided",
            "approval_status": "approved",
            "selected_reference_image_path": "/path/to/ref.png",
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

    def test_project_mode_loads_decision_log_from_artifacts_dir(self, tmp_path) -> None:
        project_dir = tmp_path / "risk-project"
        artifacts_dir = project_dir / "artifacts"
        artifacts_dir.mkdir(parents=True)

        reference = self._risk_waiver_reference()
        reference["risk_waiver"]["decision_id"] = "d-risk-001"
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
                    "waiver_decision_id": "d-risk-001",
                },
            }
        ]}
        decision_log = {
            "decisions": [
                {
                    "decision_id": "d-risk-001",
                    "category": "product_identity_reference_selection",
                    "selected": "risk_accepted",
                    "user_visible": True,
                    "user_approved": True,
                    "options_considered": [
                        {
                            "option_id": "risk_accepted",
                            "label": "Accept fidelity risk",
                            "score": 0.1,
                            "reason": "No usable product reference is available.",
                        }
                    ],
                }
            ]
        }

        for filename, payload in (
            ("product_identity_reference.json", reference),
            ("scene_plan.json", scene_plan),
            ("asset_manifest.json", asset_manifest),
            ("decision_log.json", decision_log),
        ):
            (artifacts_dir / filename).write_text(json.dumps(payload), encoding="utf-8")

        result = ProductIdentityConsistencyCheck().execute({"project_dir": str(project_dir)})

        assert result.success is True
        assert result.data["status"] == "PASS"


# ---------------------------------------------------------------------------
# runtime_consistency_check edge cases
# ---------------------------------------------------------------------------


class TestRuntimeConsistencyEdgeCases:
    @staticmethod
    def _approved_music_strategy_decision(selected: str) -> dict:
        return {
            "decisions": [
                {
                    "category": "music_strategy_selection",
                    "user_visible": True,
                    "user_approved": True,
                    "options_considered": [
                        {"option_id": selected, "label": selected}
                    ],
                    "selected": selected,
                }
            ]
        }

    @staticmethod
    def _approved_music_source_decision(selected: str) -> dict:
        return {
            "decisions": [
                {
                    "category": "music_source",
                    "user_visible": True,
                    "user_approved": True,
                    "options_considered": [
                        {"option_id": selected, "label": selected}
                    ],
                    "selected": selected,
                }
            ]
        }

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
                    "user_visible": True,
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
                    "user_visible": True,
                    "options_considered": [
                        {"option_id": "hyperframes", "label": "HyperFrames"}
                    ],
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

    def test_music_strategy_drift_without_decision_fails(self) -> None:
        result = check_runtime_consistency(
            {"render_runtime": "remotion", "music_strategy": "library_locked"},
            {"render_runtime": "remotion", "music_strategy": "generative_loose"},
        )

        assert result["status"] == "FAIL"
        assert result["music_strategy_match"] is False
        assert any("Silent music_strategy swap" in i for i in result["issues"])

    def test_music_strategy_drift_with_visible_approved_decision_passes(self) -> None:
        result = check_runtime_consistency(
            {"render_runtime": "remotion", "music_strategy": "library_locked"},
            {"render_runtime": "remotion", "music_strategy": "search_align"},
            self._approved_music_strategy_decision("search_align"),
        )

        assert result["status"] == "PASS"
        assert result["music_strategy_match"] is False
        assert result["music_strategy_decision_user_approved"] is True

    def test_music_source_decision_does_not_authorize_strategy_swap(self) -> None:
        result = check_runtime_consistency(
            {"render_runtime": "remotion", "music_strategy": "library_locked"},
            {"render_runtime": "remotion", "music_strategy": "generative_loose"},
            self._approved_music_source_decision("generative_loose"),
        )

        assert result["status"] == "FAIL"
        assert result["music_strategy_decision_present"] is False
        assert any("music_strategy_selection" in i for i in result["issues"])

    def test_missing_edit_music_strategy_fails_when_proposal_locked(self) -> None:
        result = check_runtime_consistency(
            {"render_runtime": "remotion", "music_strategy": "none"},
            {"render_runtime": "remotion"},
        )

        assert result["status"] == "FAIL"
        assert any("edit_decisions.music_strategy" in i for i in result["issues"])

    def test_legacy_embedded_decision_in_edit_decisions(self) -> None:
        edit_decisions = {
            "render_runtime": "hyperframes",
            "metadata": {
                "decision_log": {
                    "render_runtime_selection": {
                        "category": "render_runtime_selection",
                        "user_approved": True,
                        "user_visible": True,
                        "options_considered": [
                            {"option_id": "hyperframes", "label": "HyperFrames"}
                        ],
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

    def test_empty_selected_scene_ids_fails(self) -> None:
        bible = {"brand_constraints": {"mandatory_elements": []}}
        scene_plan = {"scenes": [{"id": "s1"}]}
        result = check_sample_visibility(bible, scene_plan, [])
        assert result["status"] == "FAIL"
        assert any("selected_scene_ids" in issue for issue in result["issues"])

    def test_duplicate_selected_scene_ids_fails(self) -> None:
        bible = {"brand_constraints": {"mandatory_elements": []}}
        scene_plan = {"scenes": [{"id": "s1"}]}
        result = check_sample_visibility(bible, scene_plan, ["s1", "s1"])
        assert result["status"] == "FAIL"
        assert any("duplicate" in issue for issue in result["issues"])

    def test_duplicate_selected_scene_ids_fail_after_trimming(self) -> None:
        bible = {"brand_constraints": {"mandatory_elements": []}}
        scene_plan = {"scenes": [{"id": "s1"}]}
        result = check_sample_visibility(bible, scene_plan, ["s1", " s1 "])
        assert result["status"] == "FAIL"
        assert any("duplicate" in issue for issue in result["issues"])
        assert not any("not found" in issue for issue in result["issues"])

    def test_selected_scene_ids_must_be_list_of_strings(self) -> None:
        bible = {"brand_constraints": {"mandatory_elements": []}}
        scene_plan = {"scenes": [{"id": "s1"}]}
        result = check_sample_visibility(
            bible,
            scene_plan,
            "s1",  # type: ignore[arg-type]
        )

        assert result["status"] == "FAIL"
        assert any("selected_scene_ids must be a list" in issue for issue in result["issues"])

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


class TestValidationToolWrappers:
    @pytest.mark.parametrize(
        "tool",
        [
            lambda: _provider_consistency_module().ProviderConsistencyCheck(),
            HallucinationContractCheck,
            ProductIdentityConsistencyCheck,
            RuntimeConsistencyCheck,
            SampleProductVisibilityCheck,
        ],
    )
    def test_project_scoped_validation_tools_key_by_project_dir(self, tool) -> None:
        validator = tool()
        base = {"project_dir": "projects/ad-a", "selected_scene_ids": ["s1"]}

        assert validator.idempotency_key(base) != validator.idempotency_key(
            {**base, "project_dir": "projects/ad-b"}
        )

    def test_hallucination_tool_maps_fail_verdict_to_failed_result(self) -> None:
        result = HallucinationContractCheck().execute(
            {
                "production_bible": _minimal_bible(),
                "scene_plan": {"scenes": [_minimal_scene()]},
                "asset_manifest": {"assets": []},
            }
        )

        assert result.success is False
        assert result.data["status"] == "FAIL"
        assert result.error

    def test_hallucination_tool_accepts_sample_scope(self) -> None:
        future_scene = _minimal_scene("s2")
        result = HallucinationContractCheck().execute(
            {
                "production_bible": _minimal_bible(),
                "scene_plan": {"scenes": [_minimal_scene("s1"), future_scene]},
                "asset_manifest": {"assets": [_minimal_asset("a1", "s1")]},
                "generated_scene_ids": ["s1"],
            }
        )

        assert result.success is True
        assert result.data["status"] == "PASS"
        assert result.data["summary"]["asset_scope"] == "generated_scene_ids"

    def test_hallucination_tool_rejects_empty_sample_scope(self) -> None:
        result = HallucinationContractCheck().execute(
            {
                "production_bible": _minimal_bible(),
                "scene_plan": {"scenes": [_minimal_scene("s1")]},
                "asset_manifest": {"assets": []},
                "generated_scene_ids": [],
            }
        )

        assert result.success is False
        assert result.data["status"] == "FAIL"
        assert any("generated_scene_ids" in issue for issue in result.data["issues"])

    def test_hallucination_tool_rejects_string_sample_scope(self) -> None:
        result = HallucinationContractCheck().execute(
            {
                "production_bible": _minimal_bible(),
                "scene_plan": {"scenes": [_minimal_scene("s1")]},
                "asset_manifest": {"assets": [_minimal_asset("a1", "s1")]},
                "generated_scene_ids": "s1",
            }
        )

        assert result.success is False
        assert "generated_scene_ids must be a list" in (result.error or "")

    def test_product_identity_tool_maps_warn_verdict_to_successful_result(self) -> None:
        reference = {"source_type": "generated", "approval_status": "approved"}
        scene_plan = {"scenes": []}
        asset_manifest = {"assets": []}

        result = ProductIdentityConsistencyCheck().execute(
            {
                "product_identity_reference": reference,
                "scene_plan": scene_plan,
                "asset_manifest": asset_manifest,
            }
        )

        assert result.success is True
        assert result.data["status"] == "WARN"

    def test_product_identity_tool_rejects_string_sample_scope(self) -> None:
        result = ProductIdentityConsistencyCheck().execute(
            {
                "product_identity_reference": {
                    "source_type": "user_provided",
                    "approval_status": "approved",
                    "approved_reference_path": "/path/to/ref.png",
                },
                "scene_plan": {
                    "scenes": [
                        {
                            "id": "s1",
                            "product_visibility": "hero",
                            "product_reference_required": True,
                        }
                    ]
                },
                "asset_manifest": {"assets": []},
                "generated_scene_ids": "s1",
            }
        )

        assert result.success is False
        assert "generated_scene_ids must be a list" in (result.error or "")

    def test_runtime_consistency_tool_accepts_unchanged_runtime(self) -> None:
        result = RuntimeConsistencyCheck().execute(
            {
                "production_proposal": {"render_runtime": "remotion"},
                "edit_decisions": {"render_runtime": "remotion"},
            }
        )

        assert result.success is True
        assert result.data["status"] == "PASS"

    def test_runtime_consistency_project_mode_rejects_non_strict_json(
        self, tmp_path
    ) -> None:
        project_dir = tmp_path / "runtime-strict"
        artifacts_dir = project_dir / "artifacts"
        artifacts_dir.mkdir(parents=True)
        (artifacts_dir / "production_proposal.json").write_text(
            '{"render_runtime": NaN}\n'
        )
        (artifacts_dir / "edit_decisions.json").write_text(
            '{"render_runtime": "remotion"}\n'
        )

        result = RuntimeConsistencyCheck().execute({"project_dir": str(project_dir)})

        assert result.success is False
        assert "strict JSON" in (result.error or "")

    def test_runtime_consistency_tool_schema_requires_proposal_with_edit_decisions(self) -> None:
        import jsonschema

        schema = RuntimeConsistencyCheck().input_schema

        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(
                {"edit_decisions": {"render_runtime": "remotion"}},
                schema,
            )

        jsonschema.validate(
            {
                "production_proposal": {"render_runtime": "remotion"},
                "edit_decisions": {"render_runtime": "remotion"},
            },
            schema,
        )
        jsonschema.validate(
            {
                "proposal": {"render_runtime": "remotion"},
                "edit_decisions": {"render_runtime": "remotion"},
            },
            schema,
        )

    def test_sample_visibility_tool_maps_fail_verdict_to_failed_result(self) -> None:
        result = SampleProductVisibilityCheck().execute(
            {
                "production_bible": {
                    "brand_constraints": {"mandatory_elements": ["OPPO Find X9 Pro"]}
                },
                "scene_plan": {"scenes": [{"id": "s1", "description": "A sunset"}]},
                "selected_scene_ids": ["s1"],
            }
        )

        assert result.success is False
        assert result.data["status"] == "FAIL"

    def test_sample_visibility_tool_rejects_string_scene_ids(self) -> None:
        result = SampleProductVisibilityCheck().execute(
            {
                "production_bible": {"brand_constraints": {"mandatory_elements": []}},
                "scene_plan": {"scenes": [{"id": "s1"}]},
                "selected_scene_ids": "s1",
            }
        )

        assert result.success is False
        assert "selected_scene_ids must be a list" in (result.error or "")

    def test_sample_visibility_tool_requires_bible_when_not_using_project_dir(self) -> None:
        result = SampleProductVisibilityCheck().execute(
            {
                "scene_plan": {
                    "scenes": [{"id": "s1", "description": "OPPO Find X9 Pro reveal"}]
                },
                "selected_scene_ids": ["s1"],
            }
        )

        assert result.success is False
        assert "production_bible" in (result.error or "")

    def test_scene_fidelity_tool_rejects_unknown_scene_type(self) -> None:
        result = SceneFidelityCheck().execute(
            {"scene_plan": {"scenes": [{"id": "s1", "scene_type": "missing_type"}]}}
        )

        assert result.success is False
        assert result.data["scene_fidelity"]["ok"] is False

    def test_scene_fidelity_requires_scene_type_for_scene_plan_scenes(self) -> None:
        registry = load_registry()
        report = check_plan(
            {
                "scenes": [
                    {
                        "id": "scene-1",
                        "type": "brand_card",
                        "motion_specs": ["letter_spring"],
                    }
                ]
            },
            registry,
        )

        assert report["ok"] is False
        assert any(issue["kind"] == "missing_scene_type" for issue in report["issues"])

    def test_scene_fidelity_rejects_anime_scene_with_empty_images(self) -> None:
        registry = load_registry()
        report = check_plan(
            {
                "version": "1.0",
                "render_runtime": "remotion",
                "cuts": [
                    {
                        "id": "cut-anime",
                        "type": "anime_scene",
                        "source": "remotion:anime_scene",
                        "in_seconds": 0.0,
                        "out_seconds": 3.0,
                        "images": [],
                    }
                ],
            },
            registry,
        )

        assert report["ok"] is False
        assert any(issue["kind"] == "missing_required_props" for issue in report["issues"])

    def test_scene_fidelity_tool_prefers_edit_decisions_when_both_inputs_are_present(self) -> None:
        result = SceneFidelityCheck().execute(
            {
                "scene_plan": {
                    "scenes": [
                        {
                            "id": "scene-1",
                            "type": "broll",
                            "description": "Coarse planning scene without Remotion type.",
                        }
                    ]
                },
                "edit_decisions": {
                    "version": "1.0",
                    "render_runtime": "ffmpeg",
                    "cuts": [
                        {
                            "id": "cut-1",
                            "source": "assets/video/clip.mp4",
                            "in_seconds": 0.0,
                            "out_seconds": 2.0,
                        }
                    ],
                },
            }
        )

        assert result.success is True
        assert result.data["scene_fidelity"]["summary"]["scenes_checked"] == 1

    def test_scene_fidelity_accepts_asset_manifest_id_media_cuts(self) -> None:
        registry = load_registry()
        report = check_plan(
            {
                "version": "1.0",
                "render_runtime": "ffmpeg",
                "cuts": [
                    {
                        "id": "cut-1",
                        "source": "video-1",
                        "in_seconds": 0.0,
                        "out_seconds": 2.0,
                    }
                ],
            },
            registry,
            asset_manifest={
                "assets": [
                    {
                        "id": "video-1",
                        "type": "video",
                        "path": "assets/video/clip.mp4",
                    }
                ]
            },
        )

        assert report["ok"], report["issues"]


# ---------------------------------------------------------------------------
# provider_consistency_check edge cases
# ---------------------------------------------------------------------------


class TestProviderConsistencyEdgeCases:
    def test_narration_model_swap_without_decision_fails(self) -> None:
        mod = _provider_consistency_module()
        manifest = _provider_asset_manifest(
            {
                "id": "narr-hook",
                "type": "narration",
                "path": "assets/audio/hook.mp3",
                "source_tool": "openai_tts",
                "scene_id": "global",
                "model": "gpt-4o-mini-tts",
            },
            {
                "id": "music-1",
                "type": "music",
                "path": "assets/music/background.mp3",
                "source_tool": "minimax_music",
                "scene_id": "global",
                "model": "music-2.6",
            }
        )

        verdict = mod.check_provider_consistency(
            _provider_locked_proposal(),
            manifest,
        )

        assert verdict["status"] == "FAIL"
        assert any("voice_model" in issue for issue in verdict["issues"])
        assert any("provider_selection" in issue for issue in verdict["issues"])

    def test_narration_provider_swap_with_visible_approved_decision_passes(self) -> None:
        mod = _provider_consistency_module()
        manifest = _provider_asset_manifest(
            {
                "id": "narr-hook",
                "type": "narration",
                "path": "assets/audio/hook.mp3",
                "source_tool": "openai_tts",
                "scene_id": "global",
                "model": "gpt-4o-mini-tts",
            },
            {
                "id": "music-1",
                "type": "music",
                "path": "assets/music/background.mp3",
                "source_tool": "minimax_music",
                "scene_id": "global",
                "model": "music-2.6",
            }
        )

        verdict = mod.check_provider_consistency(
            _provider_locked_proposal(),
            manifest,
            _approved_provider_decision("openai_tts:gpt-4o-mini-tts"),
        )

        assert verdict["status"] == "PASS"
        assert verdict["approved_substitutions"]

    def test_narration_model_drift_requires_model_or_pair_approval(self) -> None:
        mod = _provider_consistency_module()
        manifest = _provider_asset_manifest(
            {
                "id": "narr-hook",
                "type": "narration",
                "path": "assets/audio/hook.mp3",
                "source_tool": "cosyvoice_tts",
                "scene_id": "global",
                "model": "qwen3-tts-flash",
            },
            {
                "id": "music-1",
                "type": "music",
                "path": "assets/music/background.mp3",
                "source_tool": "minimax_music",
                "scene_id": "global",
                "model": "music-2.6",
            },
        )

        verdict = mod.check_provider_consistency(
            _provider_locked_proposal(),
            manifest,
            _approved_provider_decision("cosyvoice_tts"),
        )

        assert verdict["status"] == "FAIL"
        assert any("voice_model" in issue for issue in verdict["issues"])

    def test_narration_inventory_without_auditable_assets_fails(self) -> None:
        mod = _provider_consistency_module()
        manifest = _provider_asset_manifest(
            assets=[],
            narration_files=[
                {
                    "section_id": "hook",
                    "file": "assets/audio/hook.mp3",
                    "duration_seconds": 4.2,
                }
            ],
        )

        verdict = mod.check_provider_consistency(_provider_locked_proposal(), manifest)

        assert verdict["status"] == "FAIL"
        assert any("narration_files" in issue for issue in verdict["issues"])

    def test_missing_narration_assets_fail_when_voice_contract_is_locked(self) -> None:
        mod = _provider_consistency_module()
        manifest = _provider_asset_manifest(
            {
                "id": "music-1",
                "type": "music",
                "path": "assets/music/background.mp3",
                "source_tool": "minimax_music",
                "scene_id": "global",
                "model": "music-2.6",
            }
        )

        verdict = mod.check_provider_consistency(_provider_locked_proposal(), manifest)

        assert verdict["status"] == "FAIL"
        assert any("narration asset" in issue for issue in verdict["issues"])

    def test_script_sections_require_matching_narration_files_and_assets(self) -> None:
        mod = _provider_consistency_module()
        manifest = _provider_asset_manifest(
            {
                "id": "narr-hook",
                "type": "narration",
                "path": "assets/audio/hook.mp3",
                "source_tool": "cosyvoice_tts",
                "scene_id": "global",
                "model": "qwen3-tts-instruct-flash",
            },
            {
                "id": "music-1",
                "type": "music",
                "path": "assets/music/background.mp3",
                "source_tool": "minimax_music",
                "scene_id": "global",
                "model": "music-2.6",
            },
            narration_files=[
                {
                    "section_id": "hook",
                    "file": "assets/audio/hook.mp3",
                    "duration_seconds": 4.0,
                }
            ],
        )

        verdict = mod.check_provider_consistency(
            _provider_locked_proposal(),
            manifest,
            script=_provider_script("hook", "body"),
        )

        assert verdict["status"] == "FAIL"
        assert any("body" in issue for issue in verdict["issues"])

    def test_narration_file_requires_matching_auditable_asset_entry(self) -> None:
        mod = _provider_consistency_module()
        manifest = _provider_asset_manifest(
            {
                "id": "narr-hook",
                "type": "narration",
                "path": "assets/audio/hook.mp3",
                "source_tool": "cosyvoice_tts",
                "scene_id": "global",
                "model": "qwen3-tts-instruct-flash",
            },
            {
                "id": "music-1",
                "type": "music",
                "path": "assets/music/background.mp3",
                "source_tool": "minimax_music",
                "scene_id": "global",
                "model": "music-2.6",
            },
            narration_files=[
                {
                    "section_id": "hook",
                    "file": "assets/audio/hook.mp3",
                    "duration_seconds": 4.0,
                },
                {
                    "section_id": "body",
                    "file": "assets/audio/body.mp3",
                    "duration_seconds": 4.0,
                },
            ],
        )

        verdict = mod.check_provider_consistency(
            _provider_locked_proposal(),
            manifest,
            script=_provider_script("hook", "body"),
        )

        assert verdict["status"] == "FAIL"
        assert any("assets/audio/body.mp3" in issue for issue in verdict["issues"])

    def test_script_sections_with_matching_narration_inventory_passes(self) -> None:
        mod = _provider_consistency_module()
        manifest = _provider_asset_manifest(
            {
                "id": "narr-hook",
                "type": "narration",
                "path": "assets/audio/hook.mp3",
                "source_tool": "cosyvoice_tts",
                "scene_id": "global",
                "model": "qwen3-tts-instruct-flash",
            },
            {
                "id": "narr-body",
                "type": "narration",
                "path": "assets/audio/body.mp3",
                "source_tool": "cosyvoice_tts",
                "scene_id": "global",
                "model": "qwen3-tts-instruct-flash",
            },
            {
                "id": "music-1",
                "type": "music",
                "path": "assets/music/background.mp3",
                "source_tool": "minimax_music",
                "scene_id": "global",
                "model": "music-2.6",
            },
            narration_files=[
                {
                    "section_id": "hook",
                    "file": "assets/audio/hook.mp3",
                    "duration_seconds": 4.0,
                },
                {
                    "section_id": "body",
                    "file": "assets/audio/body.mp3",
                    "duration_seconds": 4.0,
                },
            ],
        )

        verdict = mod.check_provider_consistency(
            _provider_locked_proposal(),
            manifest,
            script=_provider_script("hook", "body"),
        )

        assert verdict["status"] == "PASS"
        assert verdict["script_sections_checked"] == 2
        assert verdict["narration_files_checked"] == 2

    def test_no_music_strategy_rejects_music_asset(self) -> None:
        mod = _provider_consistency_module()
        verdict = mod.check_provider_consistency(
            _provider_locked_proposal(music_strategy="none"),
            _provider_asset_manifest(),
        )

        assert verdict["status"] == "FAIL"
        assert any("music_strategy='none'" in issue for issue in verdict["issues"])

    def test_no_music_strategy_allows_approved_generated_music_change(self) -> None:
        mod = _provider_consistency_module()
        verdict = mod.check_provider_consistency(
            _provider_locked_proposal(music_strategy="none"),
            _provider_asset_manifest(),
            _approved_music_strategy_decision("generative_loose"),
        )

        assert verdict["status"] == "PASS"
        assert any(
            substitution["kind"] == "music_strategy"
            for substitution in verdict["approved_substitutions"]
        )

    def test_music_strategy_change_to_none_allows_missing_music_assets(self) -> None:
        mod = _provider_consistency_module()
        manifest = _provider_asset_manifest(
            {
                "id": "narr-hook",
                "type": "narration",
                "path": "assets/audio/hook.mp3",
                "source_tool": "cosyvoice_tts",
                "scene_id": "global",
                "model": "qwen3-tts-instruct-flash",
            },
        )

        verdict = mod.check_provider_consistency(
            _provider_locked_proposal(music_strategy="generative_loose"),
            manifest,
            _approved_music_strategy_decision("none"),
        )

        assert verdict["status"] == "PASS"
        assert any(
            substitution["selected_strategy"] == "none"
            for substitution in verdict["approved_substitutions"]
        )

    def test_music_file_without_auditable_music_asset_fails(self) -> None:
        mod = _provider_consistency_module()
        manifest = _provider_asset_manifest(
            {
                "id": "narr-hook",
                "type": "narration",
                "path": "assets/audio/hook.mp3",
                "source_tool": "cosyvoice_tts",
                "scene_id": "global",
                "model": "qwen3-tts-instruct-flash",
            },
            music_file="assets/music/background.mp3",
        )

        verdict = mod.check_provider_consistency(_provider_locked_proposal(), manifest)

        assert verdict["status"] == "FAIL"
        assert any("music_file" in issue for issue in verdict["issues"])

    def test_library_locked_rejects_generated_music_without_decision(self) -> None:
        mod = _provider_consistency_module()
        verdict = mod.check_provider_consistency(
            _provider_locked_proposal(music_strategy="library_locked"),
            _provider_asset_manifest(),
        )

        assert verdict["status"] == "FAIL"
        assert any("library_locked" in issue for issue in verdict["issues"])
        assert any("minimax_music" in issue for issue in verdict["issues"])

    def test_library_locked_accepts_music_library_asset(self) -> None:
        mod = _provider_consistency_module()
        manifest = _provider_asset_manifest(
            {
                "id": "narr-hook",
                "type": "narration",
                "path": "assets/audio/hook.mp3",
                "source_tool": "cosyvoice_tts",
                "scene_id": "global",
                "model": "qwen3-tts-instruct-flash",
            },
            _library_music_asset(),
        )

        verdict = mod.check_provider_consistency(
            _provider_locked_proposal(music_strategy="library_locked"),
            manifest,
        )

        assert verdict["status"] == "PASS"

    def test_library_locked_music_requires_alignment_evidence(self) -> None:
        mod = _provider_consistency_module()
        manifest = _provider_asset_manifest(
            {
                "id": "narr-hook",
                "type": "narration",
                "path": "assets/audio/hook.mp3",
                "source_tool": "cosyvoice_tts",
                "scene_id": "global",
                "model": "qwen3-tts-instruct-flash",
            },
            _library_music_asset(include_alignment=False),
        )

        verdict = mod.check_provider_consistency(
            _provider_locked_proposal(music_strategy="library_locked"),
            manifest,
        )

        assert verdict["status"] == "FAIL"
        assert any("music_alignment" in issue for issue in verdict["issues"])

    def test_library_locked_music_rejects_drop_alignment_drift(self) -> None:
        mod = _provider_consistency_module()
        manifest = _provider_asset_manifest(
            {
                "id": "narr-hook",
                "type": "narration",
                "path": "assets/audio/hook.mp3",
                "source_tool": "cosyvoice_tts",
                "scene_id": "global",
                "model": "qwen3-tts-instruct-flash",
            },
            _library_music_asset(drift_seconds=1.2),
        )

        verdict = mod.check_provider_consistency(
            _provider_locked_proposal(music_strategy="library_locked"),
            manifest,
        )

        assert verdict["status"] == "FAIL"
        assert any("drift_seconds" in issue for issue in verdict["issues"])

    def test_search_align_rejects_generated_music_without_decision(self) -> None:
        mod = _provider_consistency_module()
        verdict = mod.check_provider_consistency(
            _provider_locked_proposal(music_strategy="search_align"),
            _provider_asset_manifest(),
        )

        assert verdict["status"] == "FAIL"
        assert any("search_align" in issue for issue in verdict["issues"])

    def test_search_align_music_requires_beat_detection_evidence(self) -> None:
        mod = _provider_consistency_module()
        manifest = _provider_asset_manifest(
            {
                "id": "narr-hook",
                "type": "narration",
                "path": "assets/audio/hook.mp3",
                "source_tool": "cosyvoice_tts",
                "scene_id": "global",
                "model": "qwen3-tts-instruct-flash",
            },
            _search_aligned_music_asset(include_alignment=False),
        )

        verdict = mod.check_provider_consistency(
            _provider_locked_proposal(music_strategy="search_align"),
            manifest,
        )

        assert verdict["status"] == "FAIL"
        assert any("beat_detection_report" in issue for issue in verdict["issues"])

    def test_search_align_music_with_beat_detection_evidence_passes(self) -> None:
        mod = _provider_consistency_module()
        manifest = _provider_asset_manifest(
            {
                "id": "narr-hook",
                "type": "narration",
                "path": "assets/audio/hook.mp3",
                "source_tool": "cosyvoice_tts",
                "scene_id": "global",
                "model": "qwen3-tts-instruct-flash",
            },
            _search_aligned_music_asset(),
        )

        verdict = mod.check_provider_consistency(
            _provider_locked_proposal(music_strategy="search_align"),
            manifest,
        )

        assert verdict["status"] == "PASS"

    def test_music_source_swap_cannot_bypass_strict_strategy_lock(self) -> None:
        mod = _provider_consistency_module()
        verdict = mod.check_provider_consistency(
            _provider_locked_proposal(music_strategy="library_locked"),
            _provider_asset_manifest(),
            _approved_music_source_decision("minimax_music:music-2.6"),
        )

        assert verdict["status"] == "FAIL"
        assert any("music_strategy_selection" in issue for issue in verdict["issues"])

    def test_music_strategy_change_with_visible_decision_allows_new_source_path(self) -> None:
        mod = _provider_consistency_module()
        verdict = mod.check_provider_consistency(
            _provider_locked_proposal(music_strategy="library_locked"),
            _provider_asset_manifest(),
            _approved_music_strategy_decision("generative_loose"),
        )

        assert verdict["status"] == "PASS"
        assert any(
            substitution["kind"] == "music_strategy"
            for substitution in verdict["approved_substitutions"]
        )

    def test_budget_overage_without_approved_tradeoff_fails(self) -> None:
        mod = _provider_consistency_module()
        verdict = mod.check_provider_consistency(
            _provider_locked_proposal(approved_budget_usd=0.25),
            _provider_asset_manifest(total_cost_usd=0.31),
        )

        assert verdict["status"] == "FAIL"
        assert any("approved_budget_usd" in issue for issue in verdict["issues"])
        assert any("budget_tradeoff" in issue for issue in verdict["issues"])

    def test_budget_overage_with_visible_approved_tradeoff_passes(self) -> None:
        import jsonschema

        mod = _provider_consistency_module()
        verdict = mod.check_provider_consistency(
            _provider_locked_proposal(approved_budget_usd=0.25),
            _provider_asset_manifest(total_cost_usd=0.31),
            _approved_budget_tradeoff_decision(),
        )

        assert verdict["status"] == "PASS"
        assert verdict["approved_budget_overage_decision"] == "d-budget-1"
        jsonschema.validate(verdict, mod.ProviderConsistencyCheck.output_schema)

    def test_budget_tradeoff_must_select_overage_approval(self) -> None:
        mod = _provider_consistency_module()
        verdict = mod.check_provider_consistency(
            _provider_locked_proposal(approved_budget_usd=0.25),
            _provider_asset_manifest(total_cost_usd=0.31),
            _approved_budget_tradeoff_decision("reduce-scope"),
        )

        assert verdict["status"] == "FAIL"
        assert verdict["approved_budget_overage_decision"] is None
        assert any("approve-overage" in issue for issue in verdict["issues"])

    def test_visual_provider_model_swap_without_decision_fails(self) -> None:
        mod = _provider_consistency_module()
        manifest = _provider_asset_manifest(
            {
                "id": "narr-hook",
                "type": "narration",
                "path": "assets/audio/hook.mp3",
                "source_tool": "cosyvoice_tts",
                "scene_id": "global",
                "model": "qwen3-tts-instruct-flash",
            },
            {
                "id": "music-1",
                "type": "music",
                "path": "assets/music/background.mp3",
                "source_tool": "minimax_music",
                "scene_id": "global",
                "model": "music-2.6",
            },
            {
                "id": "visual-1",
                "type": "video",
                "path": "assets/video/scene-1.mp4",
                "source_tool": "runway_video",
                "scene_id": "scene-1",
                "model": "gen-3-alpha",
            },
        )

        verdict = mod.check_provider_consistency(_provider_locked_proposal(), manifest)

        assert verdict["status"] == "FAIL"
        assert any("Visual provider/model drift" in issue for issue in verdict["issues"])
        assert any("runway_video" in issue for issue in verdict["issues"])

    def test_visual_provider_model_swap_with_visible_approved_decision_passes(self) -> None:
        mod = _provider_consistency_module()
        manifest = _provider_asset_manifest(
            {
                "id": "narr-hook",
                "type": "narration",
                "path": "assets/audio/hook.mp3",
                "source_tool": "cosyvoice_tts",
                "scene_id": "global",
                "model": "qwen3-tts-instruct-flash",
            },
            {
                "id": "music-1",
                "type": "music",
                "path": "assets/music/background.mp3",
                "source_tool": "minimax_music",
                "scene_id": "global",
                "model": "music-2.6",
            },
            {
                "id": "visual-1",
                "type": "video",
                "path": "assets/video/scene-1.mp4",
                "source_tool": "runway_video",
                "scene_id": "scene-1",
                "model": "gen-3-alpha",
            },
        )

        verdict = mod.check_provider_consistency(
            _provider_locked_proposal(),
            manifest,
            _approved_provider_decision("runway_video:gen-3-alpha"),
        )

        assert verdict["status"] == "PASS"
        assert any(
            substitution["kind"] == "visual_provider_model"
            for substitution in verdict["approved_substitutions"]
        )

    def test_visual_model_drift_requires_model_or_pair_approval(self) -> None:
        mod = _provider_consistency_module()
        manifest = _provider_asset_manifest(
            {
                "id": "narr-hook",
                "type": "narration",
                "path": "assets/audio/hook.mp3",
                "source_tool": "cosyvoice_tts",
                "scene_id": "global",
                "model": "qwen3-tts-instruct-flash",
            },
            {
                "id": "music-1",
                "type": "music",
                "path": "assets/music/background.mp3",
                "source_tool": "minimax_music",
                "scene_id": "global",
                "model": "music-2.6",
            },
            {
                "id": "visual-1",
                "type": "video",
                "path": "assets/video/scene-1.mp4",
                "source_tool": "wan_video_api",
                "scene_id": "scene-1",
                "model": "wan2.7-t2v",
            },
        )

        verdict = mod.check_provider_consistency(
            _provider_locked_proposal(),
            manifest,
            _approved_provider_decision("wan_video_api"),
        )

        assert verdict["status"] == "FAIL"
        assert any("Visual provider/model drift" in issue for issue in verdict["issues"])

    def test_tool_execute_maps_fail_verdict_to_failed_result(self) -> None:
        mod = _provider_consistency_module()
        result = mod.ProviderConsistencyCheck().execute(
            {
                "production_proposal": _provider_locked_proposal(),
                "asset_manifest": _provider_asset_manifest(
                    {
                        "id": "narr-hook",
                        "type": "narration",
                        "path": "assets/audio/hook.mp3",
                        "source_tool": "openai_tts",
                        "scene_id": "global",
                        "model": "gpt-4o-mini-tts",
                    }
                ),
            }
        )

        assert result.success is False
        assert result.data["status"] == "FAIL"
