"""Deep edge-case tests for ad-video pipeline components.

Covers gaps not exercised by existing test suites:
- user_request: idempotency, append_turn, add_reference
- hallucination contract: image assets, multiple scenes, review status edge cases
- scene fidelity: overlapping source reuse, missing IDs
- product identity: external_url source, fidelity verdict edge cases
- runtime consistency: legacy embedded decisions
- checkpoint: assets EP_STATE, invalid artifacts
- sample_product_visibility: empty mandatory elements with product_visible scenes
- planning chain: conflict detection with overlapping conditions
"""

from __future__ import annotations

import json
import math
from copy import deepcopy
from pathlib import Path

import pytest

from lib.checkpoint import (
    CheckpointValidationError,
    write_checkpoint,
)
from lib.user_request import (
    Reference,
    record_user_request,
    append_turn,
    add_reference,
    read_user_request,
)
from tools.validation.hallucination_contract_check import (
    check_hallucination_contract,
)
from tools.validation.product_identity_consistency_check import (
    check_product_identity_consistency,
)
from tools.validation.runtime_consistency_check import check_runtime_consistency
from tools.validation.scene_fidelity_check import (
    check_kvm_coverage,
    check_plan,
    _check_overlapping_source_reuse,
)
from tools.validation.sample_product_visibility_check import (
    check_sample_visibility,
)

from tests.contracts.conftest import (
    _approved_product_identity_reference,
    _asset_manifest_for_hallucination,
    _bible_with_truth_contract,
    _conditioned_asset_manifest,
    _hallucination_check,
    _load_scene_type_registry,
    _product_visible_scene_plan,
    write_genui_required_gate_evidence,
)
from tests.contracts.test_phase0_contracts import (
    ad_video_assets_checkpoint_context,
    ad_video_assets_manifest_with_narration_inventory,
)


# ---------------------------------------------------------------------------
# user_request
# ---------------------------------------------------------------------------


class TestUserRequestEdgeCases:
    def _project_dir(self, tmp_path: Path, project_id: str) -> Path:
        return tmp_path / "projects" / project_id

    def test_record_rejects_project_dir_outside_projects_before_side_effects(
        self, tmp_path: Path
    ) -> None:
        project_dir = tmp_path / "rogue-project"

        with pytest.raises(ValueError, match="projects/<project-name>"):
            record_user_request(
                project_dir,
                "Make a 60-second launch ad.",
                project_id="rogue-project",
            )

        assert not (project_dir / "artifacts" / "user_request.json").exists()
        assert not (project_dir / "USER_PROMPT.md").exists()

    def test_record_creates_artifact_and_mirror(self, tmp_path: Path) -> None:
        project_dir = self._project_dir(tmp_path, "my-project")
        record_user_request(
            project_dir,
            "Make a 60-second MacBook Pro ad for YouTube.",
            project_id="my-project",
        )

        artifact = project_dir / "artifacts" / "user_request.json"
        mirror = project_dir / "USER_PROMPT.md"
        assert artifact.exists()
        assert mirror.exists()

        data = json.loads(artifact.read_text())
        assert data["prompt"] == "Make a 60-second MacBook Pro ad for YouTube."
        assert data["project_id"] == "my-project"
        assert "MacBook Pro ad" in mirror.read_text()

    def test_record_is_idempotent(self, tmp_path: Path) -> None:
        project_dir = self._project_dir(tmp_path, "idem")
        path1 = record_user_request(project_dir, "First prompt", project_id="idem")
        path2 = record_user_request(project_dir, "Second prompt", project_id="idem")

        assert path1 == path2
        data = json.loads(path1.read_text())
        assert data["prompt"] == "First prompt"

    def test_record_idempotent_call_restores_missing_mirror(
        self, tmp_path: Path
    ) -> None:
        project_dir = self._project_dir(tmp_path, "idem-mirror")
        path = record_user_request(
            project_dir, "Original prompt", project_id="idem-mirror"
        )
        mirror = project_dir / "USER_PROMPT.md"
        mirror.unlink()

        path2 = record_user_request(
            project_dir, "Changed prompt", project_id="idem-mirror"
        )

        assert path2 == path
        assert mirror.exists()
        assert "Original prompt" in mirror.read_text()
        assert "Changed prompt" not in mirror.read_text()

    def test_record_overwrite(self, tmp_path: Path) -> None:
        project_dir = self._project_dir(tmp_path, "overwrite")
        record_user_request(project_dir, "Original", project_id="overwrite")
        path = record_user_request(
            project_dir, "Replaced", project_id="overwrite", overwrite=True
        )

        data = json.loads(path.read_text())
        assert data["prompt"] == "Replaced"

    def test_record_rejects_empty_prompt(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="non-empty"):
            record_user_request(tmp_path / "bad", "", project_id="bad")

        with pytest.raises(ValueError, match="non-empty"):
            record_user_request(tmp_path / "bad2", "   ", project_id="bad2")

    def test_record_rejects_non_kebab_project_id(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="kebab-case"):
            record_user_request(
                tmp_path / "Bad_Project",
                "Prompt",
                project_id="Bad_Project",
            )

    def test_record_rejects_project_id_that_does_not_match_directory(
        self, tmp_path: Path
    ) -> None:
        with pytest.raises(ValueError, match="match project directory"):
            record_user_request(
                tmp_path / "actual-project",
                "Prompt",
                project_id="different-project",
            )

    def test_record_rejects_non_finite_metadata_before_side_effects(
        self, tmp_path: Path
    ) -> None:
        project_dir = self._project_dir(tmp_path, "strict-json")

        with pytest.raises(ValueError, match="strict JSON"):
            record_user_request(
                project_dir,
                "Prompt",
                project_id="strict-json",
                metadata={"routing_confidence": math.nan},
            )

        assert not (project_dir / "artifacts" / "user_request.json").exists()
        assert not (project_dir / "USER_PROMPT.md").exists()

    def test_read_rejects_non_strict_json_payload(self, tmp_path: Path) -> None:
        project_dir = self._project_dir(tmp_path, "strict-read")
        artifact = project_dir / "artifacts" / "user_request.json"
        artifact.parent.mkdir(parents=True)
        artifact.write_text(
            """
{
  "version": "1.0",
  "project_id": "strict-read",
  "created_at": "2026-06-14T00:00:00+00:00",
  "prompt": "Prompt",
  "prompt_turns": [],
  "references": [],
  "pipeline_hint": null,
  "session_id": null,
  "language": null,
  "metadata": {
    "routing_confidence": NaN
  }
}
""".lstrip()
        )

        with pytest.raises(ValueError, match="strict JSON"):
            read_user_request(project_dir)

    def test_append_turn(self, tmp_path: Path) -> None:
        project_dir = self._project_dir(tmp_path, "turns")
        record_user_request(
            project_dir, "Initial prompt", project_id="turns"
        )
        append_turn(project_dir, "Actually, make it 30 seconds instead.")
        append_turn(project_dir, "And add Chinese subtitles.", note="Language change")

        data = read_user_request(project_dir)
        assert len(data["prompt_turns"]) == 2
        assert data["prompt_turns"][0]["text"] == "Actually, make it 30 seconds instead."
        assert data["prompt_turns"][1]["note"] == "Language change"

    def test_append_turn_rejects_empty(self, tmp_path: Path) -> None:
        project_dir = self._project_dir(tmp_path, "turns-bad")
        record_user_request(project_dir, "Prompt", project_id="turns-bad")
        with pytest.raises(ValueError, match="non-empty"):
            append_turn(project_dir, "")

    def test_add_reference(self, tmp_path: Path) -> None:
        project_dir = self._project_dir(tmp_path, "refs")
        record_user_request(
            project_dir,
            "Make a video",
            project_id="refs",
            references=[Reference(kind="url", value="https://example.com/ref", role="reference_video")],
        )
        add_reference(
            project_dir,
            Reference(kind="file", value="product.png", role="product_photo"),
        )

        data = read_user_request(project_dir)
        assert len(data["references"]) == 2
        assert data["references"][1]["kind"] == "file"

    def test_reference_to_dict(self) -> None:
        ref = Reference(kind="url", value="https://example.com")
        d = ref.to_dict()
        assert d == {"kind": "url", "value": "https://example.com"}

        ref_with_extras = Reference(
            kind="music_library", value="ambient.mp3", role="bgm", note="royalty-free"
        )
        d2 = ref_with_extras.to_dict()
        assert d2["role"] == "bgm"
        assert d2["note"] == "royalty-free"

    def test_read_raises_when_missing(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            read_user_request(tmp_path / "nonexistent")

    def test_mirror_includes_pipeline_hint(self, tmp_path: Path) -> None:
        project_dir = self._project_dir(tmp_path, "hinted")
        record_user_request(
            project_dir,
            "Make an ad",
            project_id="hinted",
            pipeline_hint="ad-video",
            language="en",
        )

        mirror = (project_dir / "USER_PROMPT.md").read_text()
        assert "`ad-video`" in mirror
        assert "`en`" in mirror


# ---------------------------------------------------------------------------
# hallucination_contract edge cases
# ---------------------------------------------------------------------------


class TestHallucinationContractDeepEdgeCases:
    def test_image_asset_with_zero_keyframes_fails(self) -> None:
        bible = _bible_with_truth_contract()
        scene_plan = {
            "version": "1.0",
            "style_mode": "cinematic",
            "scenes": [
                {
                    "id": "scene-1",
                    "type": "generated",
                    "description": "Product hero shot.",
                    "start_seconds": 0,
                    "end_seconds": 5,
                    "core": True,
                    "motion_required": True,
                    "product_visibility": "hero",
                    "product_reference_required": True,
                    "hallucination_checks": [_hallucination_check()],
                }
            ],
        }
        asset_manifest = {
            "version": "1.0",
            "assets": [
                {
                    "id": "scene-1-img",
                    "type": "image",
                    "path": "assets/images/scene-1.png",
                    "source_tool": "wanx_image",
                    "scene_id": "scene-1",
                    "model": "wanx2.1",
                    "hallucination_review": {
                        "status": "PASS",
                        "keyframe_paths": [],
                        "check_verdicts": [
                            {
                                "check_id": "HC-PRODUCT-GEOMETRY",
                                "status": "PASS",
                                "severity": "blocker",
                            }
                        ],
                        "reviewer": {
                            "type": "agent",
                            "reviewed_at": "2026-05-19T09:00:00Z",
                            "method": "keyframe_review",
                        },
                    },
                }
            ],
        }

        verdict = check_hallucination_contract(bible, scene_plan, asset_manifest)
        assert verdict["status"] == "FAIL"
        assert any("keyframe" in issue for issue in verdict["issues"])

    def test_image_asset_with_one_keyframe_passes(self) -> None:
        bible = _bible_with_truth_contract()
        scene_plan = {
            "version": "1.0",
            "style_mode": "cinematic",
            "scenes": [
                {
                    "id": "scene-1",
                    "type": "generated",
                    "description": "Product hero shot.",
                    "start_seconds": 0,
                    "end_seconds": 5,
                    "core": True,
                    "motion_required": True,
                    "product_visibility": "hero",
                    "product_reference_required": True,
                    "hallucination_checks": [_hallucination_check()],
                }
            ],
        }
        asset_manifest = {
            "version": "1.0",
            "assets": [
                {
                    "id": "scene-1-img",
                    "type": "image",
                    "path": "assets/images/scene-1.png",
                    "source_tool": "wanx_image",
                    "scene_id": "scene-1",
                    "model": "wanx2.1",
                    "hallucination_review": {
                        "status": "PASS",
                        "keyframe_paths": ["assets/keyframes/scene-1/mid.png"],
                        "check_verdicts": [
                            {
                                "check_id": "HC-PRODUCT-GEOMETRY",
                                "status": "PASS",
                                "severity": "blocker",
                            }
                        ],
                        "reviewer": {
                            "type": "agent",
                            "reviewed_at": "2026-05-19T09:00:00Z",
                            "method": "keyframe_review",
                        },
                    },
                }
            ],
        }

        verdict = check_hallucination_contract(bible, scene_plan, asset_manifest)
        assert verdict["status"] == "PASS"

    def test_video_with_two_keyframes_fails(self) -> None:
        bible = _bible_with_truth_contract()
        scene_plan = {
            "version": "1.0",
            "style_mode": "cinematic",
            "scenes": [
                {
                    "id": "scene-1",
                    "type": "generated",
                    "description": "Product video shot.",
                    "start_seconds": 0,
                    "end_seconds": 5,
                    "core": True,
                    "motion_required": True,
                    "product_visibility": "hero",
                    "product_reference_required": True,
                    "hallucination_checks": [_hallucination_check()],
                }
            ],
        }
        manifest = _asset_manifest_for_hallucination()
        manifest["assets"][0]["hallucination_review"]["keyframe_paths"] = [
            "assets/keyframes/scene-1/start.png",
            "assets/keyframes/scene-1/end.png",
        ]

        verdict = check_hallucination_contract(bible, scene_plan, manifest)
        assert verdict["status"] == "FAIL"
        assert any("start/mid/end keyframes" in issue for issue in verdict["issues"])

    def test_multiple_high_risk_scenes_missing_assets(self) -> None:
        bible = _bible_with_truth_contract()
        scene_plan = {
            "version": "1.0",
            "style_mode": "cinematic",
            "scenes": [
                {
                    "id": "scene-1",
                    "type": "generated",
                    "description": "Product hero.",
                    "start_seconds": 0,
                    "end_seconds": 5,
                    "core": True,
                    "motion_required": True,
                    "product_visibility": "hero",
                    "product_reference_required": True,
                    "hallucination_checks": [_hallucination_check()],
                },
                {
                    "id": "scene-2",
                    "type": "generated",
                    "description": "Product detail.",
                    "start_seconds": 5,
                    "end_seconds": 10,
                    "core": True,
                    "motion_required": True,
                    "product_visibility": "detail",
                    "product_reference_required": True,
                    "hallucination_checks": [_hallucination_check("HC-DETAIL")],
                },
            ],
        }

        verdict = check_hallucination_contract(
            bible, scene_plan, {"version": "1.0", "assets": []}
        )
        assert verdict["status"] == "FAIL"
        assert verdict["summary"]["high_risk_scenes"] == 2
        scene_ids_in_issues = [i for i in verdict["issues"] if "no generated visual asset" in i]
        assert len(scene_ids_in_issues) == 2

    def test_not_reviewed_status_fails(self) -> None:
        manifest = _asset_manifest_for_hallucination(review_status="NOT_REVIEWED")
        verdict = check_hallucination_contract(
            _bible_with_truth_contract(),
            {
                "version": "1.0",
                "style_mode": "cinematic",
                "scenes": [
                    {
                        "id": "scene-1",
                        "type": "generated",
                        "description": "Hero.",
                        "start_seconds": 0,
                        "end_seconds": 5,
                        "core": True,
                        "motion_required": True,
                        "product_visibility": "hero",
                        "product_reference_required": True,
                        "hallucination_checks": [_hallucination_check()],
                    }
                ],
            },
            manifest,
        )
        assert verdict["status"] == "FAIL"
        assert any("NOT_REVIEWED" in issue for issue in verdict["issues"])

    def test_null_review_status_fails(self) -> None:
        manifest = _asset_manifest_for_hallucination()
        manifest["assets"][0]["hallucination_review"]["status"] = None
        verdict = check_hallucination_contract(
            _bible_with_truth_contract(),
            {
                "version": "1.0",
                "style_mode": "cinematic",
                "scenes": [
                    {
                        "id": "scene-1",
                        "type": "generated",
                        "description": "Hero.",
                        "start_seconds": 0,
                        "end_seconds": 5,
                        "core": True,
                        "motion_required": True,
                        "product_visibility": "hero",
                        "product_reference_required": True,
                        "hallucination_checks": [_hallucination_check()],
                    }
                ],
            },
            manifest,
        )
        assert verdict["status"] == "FAIL"

    def test_missing_verdict_for_required_check(self) -> None:
        manifest = _asset_manifest_for_hallucination()
        manifest["assets"][0]["hallucination_review"]["check_verdicts"] = []
        verdict = check_hallucination_contract(
            _bible_with_truth_contract(),
            {
                "version": "1.0",
                "style_mode": "cinematic",
                "scenes": [
                    {
                        "id": "scene-1",
                        "type": "generated",
                        "description": "Hero.",
                        "start_seconds": 0,
                        "end_seconds": 5,
                        "core": True,
                        "motion_required": True,
                        "product_visibility": "hero",
                        "product_reference_required": True,
                        "hallucination_checks": [_hallucination_check()],
                    }
                ],
            },
            manifest,
        )
        assert verdict["status"] == "FAIL"
        assert any("missing" in issue.lower() and "verdict" in issue.lower() for issue in verdict["issues"])


# ---------------------------------------------------------------------------
# scene_fidelity overlapping source reuse
# ---------------------------------------------------------------------------


class TestSceneFidelityOverlappingSourceReuse:
    def test_overlapping_ranges_detected(self) -> None:
        plan = {
            "render_runtime": "ffmpeg",
            "cuts": [
                {
                    "id": "cut-1",
                    "source": "assets/video/hero.mp4",
                    "in_seconds": 0,
                    "out_seconds": 5,
                    "source_in_seconds": 2,
                },
                {
                    "id": "cut-2",
                    "source": "assets/video/hero.mp4",
                    "in_seconds": 5,
                    "out_seconds": 10,
                    "source_in_seconds": 4,
                },
            ],
        }
        issues = _check_overlapping_source_reuse(plan)
        assert len(issues) == 1
        assert issues[0]["kind"] == "overlapping_source_reuse"
        assert issues[0]["severity"] == "critical"

    def test_non_overlapping_ranges_pass(self) -> None:
        plan = {
            "render_runtime": "ffmpeg",
            "cuts": [
                {
                    "id": "cut-1",
                    "source": "assets/video/hero.mp4",
                    "in_seconds": 0,
                    "out_seconds": 5,
                    "source_in_seconds": 0,
                },
                {
                    "id": "cut-2",
                    "source": "assets/video/hero.mp4",
                    "in_seconds": 5,
                    "out_seconds": 10,
                    "source_in_seconds": 5,
                },
            ],
        }
        issues = _check_overlapping_source_reuse(plan)
        assert len(issues) == 0

    def test_remotion_default_source_start_zero(self) -> None:
        """Remotion cuts without source_in_seconds default to source_start=0."""
        plan = {
            "render_runtime": "remotion",
            "cuts": [
                {
                    "id": "cut-1",
                    "source": "assets/video/hero.mp4",
                    "in_seconds": 0,
                    "out_seconds": 3,
                },
                {
                    "id": "cut-2",
                    "source": "assets/video/hero.mp4",
                    "in_seconds": 3,
                    "out_seconds": 6,
                },
            ],
        }
        issues = _check_overlapping_source_reuse(plan)
        assert len(issues) == 1

    def test_different_sources_no_overlap(self) -> None:
        plan = {
            "render_runtime": "ffmpeg",
            "cuts": [
                {
                    "id": "cut-1",
                    "source": "assets/video/hero.mp4",
                    "in_seconds": 0,
                    "out_seconds": 5,
                    "source_in_seconds": 0,
                },
                {
                    "id": "cut-2",
                    "source": "assets/video/broll.mp4",
                    "in_seconds": 5,
                    "out_seconds": 10,
                    "source_in_seconds": 0,
                },
            ],
        }
        issues = _check_overlapping_source_reuse(plan)
        assert len(issues) == 0

    def test_remotion_source_prefix_skipped(self) -> None:
        plan = {
            "render_runtime": "remotion",
            "cuts": [
                {
                    "id": "cut-1",
                    "source": "remotion:text_card",
                    "in_seconds": 0,
                    "out_seconds": 3,
                },
                {
                    "id": "cut-2",
                    "source": "remotion:text_card",
                    "in_seconds": 3,
                    "out_seconds": 6,
                },
            ],
        }
        issues = _check_overlapping_source_reuse(plan)
        assert len(issues) == 0

    def test_still_image_sources_skipped(self) -> None:
        plan = {
            "render_runtime": "ffmpeg",
            "cuts": [
                {
                    "id": "cut-1",
                    "source": "assets/images/frame1.png",
                    "in_seconds": 0,
                    "out_seconds": 3,
                },
                {
                    "id": "cut-2",
                    "source": "assets/images/frame1.png",
                    "in_seconds": 3,
                    "out_seconds": 6,
                },
            ],
        }
        issues = _check_overlapping_source_reuse(plan)
        assert len(issues) == 0

    def test_asset_manifest_video_id_sources_detect_overlap(self) -> None:
        plan = {
            "render_runtime": "remotion",
            "cuts": [
                {
                    "id": "cut-1",
                    "source": "hero-video",
                    "in_seconds": 0,
                    "out_seconds": 3,
                },
                {
                    "id": "cut-2",
                    "source": "hero-video",
                    "in_seconds": 3,
                    "out_seconds": 6,
                },
            ],
        }
        asset_manifest = {
            "assets": [
                {
                    "id": "hero-video",
                    "type": "video",
                    "path": "assets/video/hero.mp4",
                }
            ]
        }

        issues = _check_overlapping_source_reuse(plan, asset_manifest)

        assert len(issues) == 1
        assert issues[0]["kind"] == "overlapping_source_reuse"

    def test_cut_without_id_gets_generated_id(self) -> None:
        plan = {
            "render_runtime": "ffmpeg",
            "cuts": [
                {
                    "source": "assets/video/hero.mp4",
                    "in_seconds": 0,
                    "out_seconds": 5,
                    "source_in_seconds": 0,
                },
                {
                    "source": "assets/video/hero.mp4",
                    "in_seconds": 5,
                    "out_seconds": 10,
                    "source_in_seconds": 2,
                },
            ],
        }
        issues = _check_overlapping_source_reuse(plan)
        assert len(issues) == 1
        assert "cut-1" in issues[0]["scene_id"]


# ---------------------------------------------------------------------------
# product_identity_consistency edge cases
# ---------------------------------------------------------------------------


class TestProductIdentityDeepEdgeCases:
    def test_external_url_source_type_with_approved_reference(self) -> None:
        reference = {
            "version": "1.0",
            "reference_id": "pir-url",
            "product_name": "Acme Widget",
            "source_type": "external_url",
            "approval_status": "approved",
            "selected_reference_url": "https://brand.acme.com/product.png",
            "required_visual_features": ["distinctive notch"],
            "prohibited_variations": [],
            "user_approval": {
                "approved": True,
                "approved_by": "user",
                "approved_at": "2026-05-20T10:00:00Z",
                "decision_id": "d-url",
            },
        }
        scene_plan = _product_visible_scene_plan()
        manifest = {
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
                        "approved_reference_id": "pir-url",
                        "approved_reference_path": "https://brand.acme.com/product.png",
                        "conditioning_mode": "reference_to_video",
                        "generation_tool": "wan_video_api",
                        "generation_model": "wan2.7-i2v",
                        "fidelity_verdict": "PASS",
                    },
                }
            ],
        }

        verdict = check_product_identity_consistency(reference, scene_plan, manifest)
        assert verdict["status"] == "PASS"

    def test_fidelity_verdict_warn_not_flag(self) -> None:
        reference = _approved_product_identity_reference()
        scene_plan = _product_visible_scene_plan()
        manifest = _conditioned_asset_manifest()
        manifest["assets"][0]["product_identity_conditioning"]["fidelity_verdict"] = "WARN"

        verdict = check_product_identity_consistency(reference, scene_plan, manifest)
        assert verdict["status"] == "WARN"
        assert any("WARN" in w for w in verdict["warnings"])

    def test_fidelity_verdict_not_checked_warns(self) -> None:
        reference = _approved_product_identity_reference()
        scene_plan = _product_visible_scene_plan()
        manifest = _conditioned_asset_manifest()
        manifest["assets"][0]["product_identity_conditioning"]["fidelity_verdict"] = "NOT_CHECKED"

        verdict = check_product_identity_consistency(reference, scene_plan, manifest)
        assert verdict["status"] == "WARN"

    def test_mismatched_reference_id_fails(self) -> None:
        reference = _approved_product_identity_reference()
        scene_plan = _product_visible_scene_plan()
        manifest = _conditioned_asset_manifest()
        manifest["assets"][0]["product_identity_conditioning"]["approved_reference_id"] = "pir-wrong"

        verdict = check_product_identity_consistency(reference, scene_plan, manifest)
        assert verdict["status"] == "FAIL"
        assert any("approved_reference_id" in issue for issue in verdict["issues"])

    def test_conditioning_missing_for_product_visible_scene(self) -> None:
        reference = _approved_product_identity_reference()
        scene_plan = _product_visible_scene_plan()
        manifest = {
            "version": "1.0",
            "assets": [
                {
                    "id": "scene-1-video",
                    "type": "video",
                    "path": "assets/video/scene-1.mp4",
                    "source_tool": "wan_video_api",
                    "scene_id": "scene-1",
                    "model": "wan2.7-i2v",
                }
            ],
        }

        verdict = check_product_identity_consistency(reference, scene_plan, manifest)
        assert verdict["status"] == "FAIL"
        assert any("product_identity_conditioning" in issue for issue in verdict["issues"])


# ---------------------------------------------------------------------------
# runtime_consistency edge cases
# ---------------------------------------------------------------------------


class TestRuntimeConsistencyDeepEdgeCases:
    def test_legacy_embedded_decision_in_edit_decisions(self) -> None:
        proposal = {"render_runtime": "remotion"}
        edit_decisions = {
            "render_runtime": "hyperframes",
            "metadata": {
                "decision_log": {
                    "decisions": [
                        {
                            "category": "render_runtime_selection",
                            "selected": "hyperframes",
                            "user_visible": True,
                            "user_approved": True,
                            "options_considered": [
                                {"option_id": "remotion"},
                                {"option_id": "hyperframes"},
                            ],
                        }
                    ],
                }
            },
        }

        verdict = check_runtime_consistency(proposal, edit_decisions)
        assert verdict["status"] == "PASS"
        assert verdict["decision_present"] is True
        assert verdict["decision_matches_actual"] is True

    def test_legacy_one_off_embedded_decision(self) -> None:
        proposal = {"render_runtime": "remotion"}
        edit_decisions = {
            "render_runtime": "hyperframes",
            "metadata": {
                "decision_log": {
                    "render_runtime_selection": {
                        "category": "render_runtime_selection",
                        "actual_at_compose": "hyperframes",
                        "user_visible": True,
                        "user_approved": True,
                        "options_considered": [
                            {"option_id": "hyperframes"},
                        ],
                    }
                }
            },
        }

        verdict = check_runtime_consistency(proposal, edit_decisions)
        assert verdict["status"] == "PASS"

    def test_matching_runtimes_pass_without_decision_log(self) -> None:
        proposal = {"render_runtime": "remotion"}
        edit_decisions = {"render_runtime": "remotion"}

        verdict = check_runtime_consistency(proposal, edit_decisions)
        assert verdict["status"] == "PASS"
        assert verdict["match"] is True

    def test_both_none_fails(self) -> None:
        verdict = check_runtime_consistency({}, {})
        assert verdict["status"] == "FAIL"
        assert len(verdict["issues"]) == 2


# ---------------------------------------------------------------------------
# checkpoint assets EP_STATE
# ---------------------------------------------------------------------------


class TestCheckpointAssetsEPState:
    def _valid_assets_artifacts(self) -> dict:
        return {
            "asset_manifest": ad_video_assets_manifest_with_narration_inventory(),
            "product_identity_reference": {
                "version": "1.0",
                "reference_id": "pir-none",
                "product_name": "Acme SaaS",
                "source_type": "not_applicable",
                "approval_status": "not_required",
                "required_visual_features": [],
                "prohibited_variations": [],
            },
            **ad_video_assets_checkpoint_context(),
        }

    def test_assets_checkpoint_requires_ep_state_flags(self, tmp_path: Path) -> None:
        artifacts = self._valid_assets_artifacts()
        with pytest.raises(CheckpointValidationError, match="sample_approved"):
            write_checkpoint(
                tmp_path,
                "ep-test",
                "assets",
                "completed",
                artifacts,
                pipeline_type="ad-video",
                metadata={"ep_state": {}},
            )

    def test_assets_completed_checkpoint_requires_genui_gate_evidence(
        self, tmp_path: Path
    ) -> None:
        artifacts = self._valid_assets_artifacts()

        with pytest.raises(CheckpointValidationError, match="GenUI evidence") as exc_info:
            write_checkpoint(
                tmp_path,
                "ep-test-no-genui",
                "assets",
                "completed",
                artifacts,
                pipeline_type="ad-video",
                metadata={
                    "ep_state": {
                        "sample_approved": True,
                        "asset_review_approved": True,
                        "music_review_approved": True,
                    }
                },
            )
        message = str(exc_info.value)
        assert "genui_evidence_check" in message
        assert "python -m tools.validation.genui_evidence_check" in message
        assert "ad-video assets" in message

    def test_assets_checkpoint_passes_with_all_flags(self, tmp_path: Path) -> None:
        artifacts = self._valid_assets_artifacts()
        write_genui_required_gate_evidence(
            tmp_path / "ep-test-ok",
            project_id="ep-test-ok",
        )
        write_checkpoint(
            tmp_path,
            "ep-test-ok",
            "assets",
            "completed",
            artifacts,
            pipeline_type="ad-video",
            metadata={
                "ep_state": {
                    "sample_approved": True,
                    "asset_review_approved": True,
                    "music_review_approved": True,
                }
            },
        )

    def test_assets_checkpoint_partial_flags_fails(self, tmp_path: Path) -> None:
        artifacts = self._valid_assets_artifacts()
        with pytest.raises(CheckpointValidationError, match="music_review_approved"):
            write_checkpoint(
                tmp_path,
                "ep-test-partial",
                "assets",
                "completed",
                artifacts,
                pipeline_type="ad-video",
                metadata={
                    "ep_state": {
                        "sample_approved": True,
                        "asset_review_approved": True,
                    }
                },
            )

    def test_assets_checkpoint_risk_accepted_rejects_unapproved_waiver(self, tmp_path: Path) -> None:
        artifacts = self._valid_assets_artifacts()
        artifacts["product_identity_reference"] = {
            "version": "1.0",
            "reference_id": "pir-risk",
            "product_name": "Acme Widget",
            "source_type": "risk_accepted",
            "approval_status": "approved",
            "required_visual_features": [],
            "prohibited_variations": [],
            "risk_waiver": {
                "reason": "No product photos available",
                "user_approved": True,
                "approved_by": "user",
                "approved_at": "2026-05-20T10:00:00Z",
                "decision_id": "d-001",
            },
        }
        write_genui_required_gate_evidence(
            tmp_path / "ep-risk-ok",
            project_id="ep-risk-ok",
        )
        write_checkpoint(
            tmp_path,
            "ep-risk-ok",
            "assets",
            "completed",
            artifacts,
            pipeline_type="ad-video",
            metadata={
                "ep_state": {
                    "sample_approved": True,
                    "asset_review_approved": True,
                    "music_review_approved": True,
                }
            },
        )

        unapproved = deepcopy(artifacts)
        unapproved["product_identity_reference"]["risk_waiver"]["user_approved"] = False
        with pytest.raises(CheckpointValidationError):
            write_checkpoint(
                tmp_path,
                "ep-risk-fail",
                "assets",
                "completed",
                unapproved,
                pipeline_type="ad-video",
                metadata={
                    "ep_state": {
                        "sample_approved": True,
                        "asset_review_approved": True,
                        "music_review_approved": True,
                    }
                },
            )


# ---------------------------------------------------------------------------
# sample_product_visibility deep edge cases
# ---------------------------------------------------------------------------


class TestSampleVisibilityDeepEdgeCases:
    def test_product_visible_scene_passes_without_mandatory_elements(self) -> None:
        bible = {
            "brand_constraints": {
                "mandatory_elements": [],
            }
        }
        scene_plan = {
            "scenes": [
                {
                    "id": "scene-1",
                    "description": "Product hero shot",
                    "product_visibility": "hero",
                    "product_reference_required": True,
                }
            ],
        }

        verdict = check_sample_visibility(bible, scene_plan, ["scene-1"])
        assert verdict["status"] == "PASS"

    def test_negated_visual_constraint_excluded_from_match(self) -> None:
        bible = {
            "brand_constraints": {
                "mandatory_elements": ["OPPO wordmark"],
            }
        }
        scene_plan = {
            "scenes": [
                {
                    "id": "scene-1",
                    "description": "Elegant setup",
                    "visual_constraint": "Do not show the OPPO wordmark until the reveal",
                    "product_visibility": "none",
                    "product_reference_required": False,
                }
            ],
        }

        verdict = check_sample_visibility(bible, scene_plan, ["scene-1"])
        assert verdict["status"] == "FAIL"

    def test_keyword_extraction_handles_hyphens(self) -> None:
        bible = {
            "brand_constraints": {
                "mandatory_elements": ["OPPO Find-X9 Pro"],
            }
        }
        scene_plan = {
            "scenes": [
                {
                    "id": "scene-1",
                    "description": "Find-X9 Pro hero shot with OPPO branding",
                    "product_visibility": "hero",
                    "product_reference_required": True,
                }
            ],
        }

        verdict = check_sample_visibility(bible, scene_plan, ["scene-1"])
        assert verdict["status"] == "PASS"

    def test_multiple_mandatory_elements_need_separate_matches(self) -> None:
        bible = {
            "brand_constraints": {
                "mandatory_elements": [
                    "OPPO wordmark",
                    "Hasselblad camera branding",
                ],
            }
        }
        scene_plan = {
            "scenes": [
                {
                    "id": "scene-1",
                    "description": "OPPO wordmark appears in final frame",
                    "product_visibility": "partial",
                    "product_reference_required": True,
                },
                {
                    "id": "scene-2",
                    "description": "Hasselblad camera branding on the device",
                    "product_visibility": "detail",
                    "product_reference_required": True,
                },
            ],
        }

        verdict = check_sample_visibility(bible, scene_plan, ["scene-1", "scene-2"])
        assert verdict["status"] == "PASS"
        assert len(verdict["matches"]) == 2


# ---------------------------------------------------------------------------
# scene_fidelity with registry
# ---------------------------------------------------------------------------


class TestSceneFidelityDeepEdgeCases:
    def test_scene_without_scene_type_in_scene_plan_fails(self) -> None:
        registry = _load_scene_type_registry()
        plan = {
            "scenes": [
                {
                    "id": "scene-1",
                    "type": "animation",
                    "description": "Animated scene without scene_type.",
                }
            ]
        }
        report = check_plan(plan, registry)
        assert report["ok"] is False
        assert any(i["kind"] == "missing_scene_type" for i in report["issues"])

    def test_unknown_scene_type_fails(self) -> None:
        registry = _load_scene_type_registry()
        plan = {
            "scenes": [
                {
                    "id": "scene-1",
                    "scene_type": "nonexistent_scene_type",
                    "description": "Unknown type",
                }
            ]
        }
        report = check_plan(plan, registry)
        assert report["ok"] is False
        assert any(i["kind"] == "unknown_scene_type" for i in report["issues"])

    def test_plain_media_cut_passes(self) -> None:
        registry = _load_scene_type_registry()
        plan = {
            "cuts": [
                {
                    "id": "cut-1",
                    "source": "assets/video/clip.mp4",
                    "in_seconds": 0,
                    "out_seconds": 5,
                }
            ]
        }
        report = check_plan(plan, registry)
        assert report["ok"] is True

    def test_cut_with_missing_required_props_fails(self) -> None:
        registry = _load_scene_type_registry()
        plan = {
            "cuts": [
                {
                    "id": "cut-1",
                    "type": "creator_workflow_scene",
                    "source": "remotion:creator_workflow_scene",
                    "in_seconds": 0,
                    "out_seconds": 4,
                }
            ]
        }
        report = check_plan(plan, registry)
        assert report["ok"] is False
        assert any(i["kind"] == "missing_required_props" for i in report["issues"])

    def test_scene_fulfilling_unknown_kvm_fails(self) -> None:
        bible = {
            "visual": {
                "key_visual_moments": [
                    {
                        "moment_id": "kvm-1",
                        "mandatory": False,
                        "description": "Known product reveal.",
                    }
                ]
            }
        }
        scene_plan = {
            "scenes": [
                {
                    "id": "scene-1",
                    "fulfills_kvm": ["missing-kvm"],
                }
            ]
        }

        report = check_kvm_coverage(bible, scene_plan)

        assert report["ok"] is False
        assert any(i["kind"] == "unknown_kvm_reference" for i in report["issues"])


# ---------------------------------------------------------------------------
# conflict detection deep edge cases
# ---------------------------------------------------------------------------


class TestConflictDetectionDeepEdgeCases:
    def test_trend_with_empty_instruction_skipped(self) -> None:
        from lib.conflict_detection import check_trend_knowledge_conflicts

        result = check_trend_knowledge_conflicts(
            trend_alignments=[{
                "trend_id": "t1",
                "scene_usage": {"visual_or_pacing_instruction": ""},
            }],
            knowledge_cards=[{
                "card_id": "c1",
                "avoid_when": ["rapid cuts bright colors everywhere"],
            }],
            knowledge_alignments=[{"card_id": "c1"}],
        )
        assert result["ok"]

    def test_card_with_missing_avoid_when_handled(self) -> None:
        from lib.conflict_detection import check_trend_knowledge_conflicts

        result = check_trend_knowledge_conflicts(
            trend_alignments=[{
                "trend_id": "t1",
                "scene_usage": {"visual_or_pacing_instruction": "fast cuts"},
            }],
            knowledge_cards=[{"card_id": "c1"}],
            knowledge_alignments=[{"card_id": "c1"}],
        )
        assert result["ok"]

    def test_knowledge_card_without_card_id_skipped(self) -> None:
        from lib.conflict_detection import check_trend_knowledge_conflicts

        result = check_trend_knowledge_conflicts(
            trend_alignments=[{
                "trend_id": "t1",
                "scene_usage": {"visual_or_pacing_instruction": "fast cuts"},
            }],
            knowledge_cards=[{"not_card_id": "c1"}],
            knowledge_alignments=[{"card_id": "c1"}],
        )
        assert result["ok"]

    def test_scene_usage_as_string_handled(self) -> None:
        from lib.conflict_detection import check_trend_knowledge_conflicts

        result = check_trend_knowledge_conflicts(
            trend_alignments=[{
                "trend_id": "t1",
                "scene_usage": "not a dict",
            }],
            knowledge_cards=[{
                "card_id": "c1",
                "avoid_when": ["something"],
            }],
            knowledge_alignments=[{"card_id": "c1"}],
        )
        assert result["ok"]
