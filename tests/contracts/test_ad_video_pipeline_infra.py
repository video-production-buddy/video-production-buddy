"""Tests for pipeline infrastructure: pipeline_loader, tool_registry, checkpoint I/O.

Covers gaps not exercised by existing test suites:
- pipeline_loader: sub-stages, extensions, reference input, stage skill/review_focus
- tool_registry: provider_menu_summary, capability_catalog, fallback, unicode scrub
- checkpoint: write/read roundtrip for ad-video, decision_log merge, get_completed_stages
"""

from __future__ import annotations

import json
import math
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

from lib.checkpoint import (
    CheckpointValidationError,
    get_completed_stages,
    get_latest_checkpoint,
    get_next_stage,
    read_checkpoint,
    validate_checkpoint,
    write_checkpoint,
)
from lib.pipeline_loader import (
    ExtensionNotPermitted,
    check_extension_permitted,
    get_checkpoint_stage_order,
    get_genui_required_gates_for_checkpoint,
    get_permitted_extensions,
    get_reference_input_config,
    get_required_tools,
    get_stage_order,
    get_stage_review_focus,
    get_stage_skill,
    get_stage_sub_stages,
    list_pipelines,
    load_pipeline,
    pipeline_supports_reference_input,
)
from tools.base_tool import BaseTool, ToolResult, ToolRuntime, ToolStatus, ToolTier
from tools.tool_registry import ToolRegistry, _scrub_unicode_dashes


# ---------------------------------------------------------------------------
# pipeline_loader
# ---------------------------------------------------------------------------


class TestPipelineLoaderManifest:
    def test_load_ad_video_manifest(self) -> None:
        manifest = load_pipeline("ad-video")
        assert "stages" in manifest
        assert [stage["name"] for stage in manifest["stages"]] == [
            "research",
            "proposal",
            "script",
            "scene_plan",
            "assets",
            "edit",
            "compose",
            "publish",
        ]

    def test_load_nonexistent_manifest_raises(self) -> None:
        with pytest.raises(FileNotFoundError):
            load_pipeline("does-not-exist")

    def test_list_pipelines_includes_ad_video(self) -> None:
        names = list_pipelines()
        assert "ad-video" in names

    def test_get_stage_order_returns_all_ad_video_stages(self) -> None:
        manifest = load_pipeline("ad-video")
        order = get_stage_order(manifest)
        assert order[0] == "research"
        assert order[-1] == "publish"
        assert len(order) == len(manifest["stages"])

    def test_get_checkpoint_stage_order_returns_ad_video_child_gates(self) -> None:
        manifest = load_pipeline("ad-video")
        assert get_checkpoint_stage_order(manifest) == [
            "research.intake",
            "research.brief_enrichment",
            "research.intelligence",
            "proposal.bible",
            "proposal.idea",
            "proposal.technical_proposal",
            "script",
            "scene_plan",
            "assets",
            "edit",
            "compose",
            "publish",
        ]

    def test_get_stage_order_with_sub_stages(self) -> None:
        manifest = load_pipeline("ad-video")
        order = get_stage_order(manifest, include_sub_stages=True, context=None)
        flat = get_stage_order(manifest)
        assert len(order) >= len(flat)

    def test_get_stage_sub_stages_returns_all_by_default(self) -> None:
        manifest = load_pipeline("ad-video")
        for stage in manifest["stages"]:
            subs = get_stage_sub_stages(manifest, stage["name"])
            declared = stage.get("sub_stages", [])
            assert len(subs) == len(declared)

    def test_get_stage_sub_stages_unknown_stage_returns_empty(self) -> None:
        manifest = load_pipeline("ad-video")
        assert get_stage_sub_stages(manifest, "nonexistent_stage") == []

    def test_get_genui_required_gates_for_assets_checkpoint(self) -> None:
        manifest = load_pipeline("ad-video")

        assert get_genui_required_gates_for_checkpoint(manifest, "assets") == [
            {"stage": "assets", "gate": "product_reference"},
            {"stage": "assets", "gate": "sample_review"},
            {"stage": "assets", "gate": "asset_review"},
            {"stage": "assets", "gate": "music_review"},
        ]

    def test_get_stage_skill_returns_path(self) -> None:
        manifest = load_pipeline("ad-video")
        skill = get_stage_skill(manifest, "research.intake")
        assert skill is not None
        assert "intake" in skill

    def test_get_stage_skill_resolves_collapsed_technical_proposal_gate(self) -> None:
        manifest = load_pipeline("ad-video")
        skill = get_stage_skill(manifest, "proposal.technical_proposal")
        assert skill == "pipelines/ad-video/technical-proposal-director"

    def test_get_stage_skill_unknown_returns_none(self) -> None:
        manifest = load_pipeline("ad-video")
        assert get_stage_skill(manifest, "nonexistent") is None

    def test_get_stage_review_focus_returns_list(self) -> None:
        manifest = load_pipeline("ad-video")
        focus = get_stage_review_focus(manifest, "compose")
        assert isinstance(focus, list)

    def test_get_stage_review_focus_resolves_child_gate(self) -> None:
        manifest = load_pipeline("ad-video")
        focus = get_stage_review_focus(manifest, "research.brief_enrichment")
        assert any("user_approved" in item for item in focus)

    def test_get_stage_review_focus_unknown_returns_empty(self) -> None:
        manifest = load_pipeline("ad-video")
        assert get_stage_review_focus(manifest, "nonexistent") == []


class TestPipelineLoaderReferenceInput:
    def test_reference_input_config_defaults_empty(self) -> None:
        manifest = load_pipeline("ad-video")
        config = get_reference_input_config(manifest)
        assert isinstance(config, dict)

    def test_reference_input_supported_flag(self) -> None:
        manifest = load_pipeline("ad-video")
        supported = pipeline_supports_reference_input(manifest)
        assert isinstance(supported, bool)


class TestPipelineLoaderRequiredTools:
    def test_required_tools_includes_ad_video_tools(self) -> None:
        manifest = load_pipeline("ad-video")
        tools = get_required_tools(manifest)
        assert isinstance(tools, set)
        assert len(tools) > 0


class TestPipelineLoaderExtensions:
    def test_extension_not_permitted_raises(self) -> None:
        manifest = load_pipeline("ad-video")
        with pytest.raises(ExtensionNotPermitted):
            check_extension_permitted(manifest, "custom_tools")

    def test_unknown_extension_type_raises_value_error(self) -> None:
        manifest = load_pipeline("ad-video")
        with pytest.raises(ValueError, match="Unknown extension type"):
            check_extension_permitted(manifest, "custom_rockets")

    def test_get_permitted_extensions_returns_all_flags(self) -> None:
        manifest = load_pipeline("ad-video")
        perms = get_permitted_extensions(manifest)
        assert set(perms.keys()) == {
            "custom_scripts", "custom_playbooks", "custom_skills", "custom_tools"
        }


# ---------------------------------------------------------------------------
# tool_registry
# ---------------------------------------------------------------------------


class _StubTool(BaseTool):
    name = "stub_tool"
    tier = ToolTier.CORE
    capabilities = ["test"]
    dependencies = []

    def execute(self, inputs: dict[str, Any]) -> ToolResult:
        return ToolResult(success=True, data=inputs)


class _UnavailableStubTool(BaseTool):
    name = "unavail_stub"
    tier = ToolTier.ENHANCE
    capabilities = ["test"]
    dependencies = ["nonexistent_dep_xyz"]

    def execute(self, inputs: dict[str, Any]) -> ToolResult:  # noqa: ARG002
        return ToolResult(success=False, data={})

    def get_status(self) -> ToolStatus:
        return ToolStatus.UNAVAILABLE


class _EnvSetupStubTool(BaseTool):
    name = "env_setup_stub"
    tier = ToolTier.GENERATE
    capability = "video_generation"
    provider = "stub_provider"
    runtime = ToolRuntime.API
    dependencies = ["env:STUB_PROVIDER_API_KEY"]
    install_instructions = "Set STUB_PROVIDER_API_KEY in .env to enable this provider."

    def execute(self, inputs: dict[str, Any]) -> ToolResult:  # noqa: ARG002
        return ToolResult(success=False, data={})


class TestToolRegistryEdgeCases:
    def test_register_empty_name_raises(self) -> None:
        reg = ToolRegistry()
        tool = _StubTool()
        tool.name = ""
        with pytest.raises(ValueError, match="non-empty name"):
            reg.register(tool)

    def test_get_nonexistent_returns_none(self) -> None:
        reg = ToolRegistry()
        assert reg.get("nope") is None

    def test_list_all_empty_registry(self) -> None:
        reg = ToolRegistry()
        assert reg.list_all() == []

    def test_get_by_tier_empty(self) -> None:
        reg = ToolRegistry()
        assert reg.get_by_tier(ToolTier.CORE) == []

    def test_get_by_capability_empty(self) -> None:
        reg = ToolRegistry()
        assert reg.get_by_capability("test") == []

    def test_get_by_provider_empty(self) -> None:
        reg = ToolRegistry()
        assert reg.get_by_provider("fake") == []

    def test_find_fallback_none_for_unknown(self) -> None:
        reg = ToolRegistry()
        assert reg.find_fallback("unknown") is None

    def test_find_fallback_returns_none_when_no_available(self) -> None:
        reg = ToolRegistry()
        tool = _StubTool()
        tool.fallback = "unavail_stub"
        reg.register(tool)
        reg.register(_UnavailableStubTool())
        result = reg.find_fallback("stub_tool")
        assert result is None

    def test_get_unavailable_filters_correctly(self) -> None:
        reg = ToolRegistry()
        reg.register(_StubTool())
        reg.register(_UnavailableStubTool())
        unavailable = reg.get_unavailable()
        assert len(unavailable) == 1
        assert unavailable[0].name == "unavail_stub"

    def test_get_available_filters_correctly(self) -> None:
        reg = ToolRegistry()
        reg.register(_StubTool())
        reg.register(_UnavailableStubTool())
        available = reg.get_available()
        assert len(available) == 1
        assert available[0].name == "stub_tool"

    def test_tier_summary_counts(self) -> None:
        reg = ToolRegistry()
        reg.register(_StubTool())
        reg.register(_UnavailableStubTool())
        summary = reg.tier_summary()
        assert "core" in summary
        assert summary["core"]["available"] == 1

    def test_capability_catalog_groups_by_capability(self) -> None:
        reg = ToolRegistry()
        reg.register(_StubTool())
        reg._discovered_packages.add("tools")
        catalog = reg.capability_catalog()
        assert "generic" in catalog

    def test_provider_catalog_groups_by_provider(self) -> None:
        reg = ToolRegistry()
        reg.register(_StubTool())
        reg._discovered_packages.add("tools")
        catalog = reg.provider_catalog()
        assert isinstance(catalog, dict)

    def test_provider_menu_entries_include_dependencies(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("STUB_PROVIDER_API_KEY", raising=False)
        reg = ToolRegistry()
        reg.register(_EnvSetupStubTool())
        reg._discovered_packages.add("tools")

        menu = reg.provider_menu()
        entry = menu["video_generation"]["unavailable"][0]

        assert entry["dependencies"] == ["env:STUB_PROVIDER_API_KEY"]

    def test_provider_menu_summary_setup_offers_include_dependencies(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("STUB_PROVIDER_API_KEY", raising=False)
        reg = ToolRegistry()
        reg.register(_EnvSetupStubTool())
        reg._discovered_packages.add("tools")

        summary = reg.provider_menu_summary()

        assert summary["setup_offers"][0]["dependencies"] == [
            "env:STUB_PROVIDER_API_KEY"
        ]

    def test_gpu_required_tools_empty(self) -> None:
        reg = ToolRegistry()
        reg.register(_StubTool())
        assert reg.gpu_required_tools() == []

    def test_network_required_tools_empty(self) -> None:
        reg = ToolRegistry()
        reg.register(_StubTool())
        assert reg.network_required_tools() == []

    def test_clear_resets_state(self) -> None:
        reg = ToolRegistry()
        reg.register(_StubTool())
        assert len(reg.list_all()) == 1
        reg.clear()
        assert len(reg.list_all()) == 0


class TestScrubUnicodeDashes:
    def test_em_dash_replaced(self) -> None:
        assert _scrub_unicode_dashes("foo—bar") == "foo--bar"

    def test_en_dash_replaced(self) -> None:
        assert _scrub_unicode_dashes("1–2") == "1-2"

    def test_ellipsis_replaced(self) -> None:
        assert _scrub_unicode_dashes("wait…") == "wait..."

    def test_nested_dict_scrubbed(self) -> None:
        data = {"key": "val—ue", "nested": {"inner": "…end"}}
        result = _scrub_unicode_dashes(data)
        assert result["key"] == "val--ue"
        assert result["nested"]["inner"] == "...end"

    def test_list_scrubbed(self) -> None:
        result = _scrub_unicode_dashes(["—", "…"])
        assert result == ["--", "..."]

    def test_non_string_values_unchanged(self) -> None:
        assert _scrub_unicode_dashes(42) == 42
        assert _scrub_unicode_dashes(None) is None

    def test_tuple_scrubbed(self) -> None:
        result = _scrub_unicode_dashes(("—", "ok"))
        assert result == ("--", "ok")
        assert isinstance(result, tuple)


# ---------------------------------------------------------------------------
# checkpoint I/O roundtrip for ad-video pipeline
# ---------------------------------------------------------------------------


def _minimal_ad_video_intake_brief() -> dict[str, Any]:
    return {
        "product": "TestProduct",
        "platform": "youtube",
        "duration_target_seconds": 60,
        "intake_completeness": "adequate",
        "round1_questions_asked": ["What is the target demographic?"],
    }


def _minimal_ad_video_proposal_with_decisions() -> dict[str, Any]:
    proposal = deepcopy({
        "version": "1.0",
        "selected_idea_id": "C2",
        "style_mode": "cinematic",
        "render_runtime": "ffmpeg",
        "product_reference_strategy": "generate_concept_reference",
        "subtitles": {"mode": "burnt-in", "language": "en", "user_confirmed": True},
        "dubbing": [],
        "derivatives_added": [],
        "budget_confirmed": True,
        "approved_budget_usd": 5.0,
        "music_strategy": "generative_loose",
        "audio_contract": {
            "voice_provider": "qwen3",
            "voice_id": "Dylan",
            "voice_model": "qwen3-tts-instruct-flash",
            "voice_gender": "male",
            "voice_persona": "warm narrator",
            "voice_performance": {
                "tone": "warm",
                "baseline_emotion": "calm assurance",
                "emotion_arc": "curiosity -> clarity -> confident CTA",
                "intonation": "natural",
                "rhythm": "varied",
                "pause_policy": "brief pause after claims",
            },
            "voice_sample_approved": True,
            "target_speed_wps": 2.5,
            "target_lufs": -14,
            "max_section_drift_pct": 5,
            "duck_depth_db": -18,
        },
        "visual_contract": {
            "style_direction": "editorial-tech",
            "typography_pairing": {"display": "Inter 800", "body": "Inter 400"},
            "color_rhythm": "held-accent",
            "atmosphere": {"default_layers": [{"type": "grain", "intensity": 0.04}]},
            "anti_template_checklist": ["hero product visible before the CTA"],
            "visual_asset_provider_locks": [
                {
                    "asset_type": "image",
                    "source_tool": "wanx_image",
                    "model": "wan2.7-image-pro",
                },
                {
                    "asset_type": "video",
                    "source_tool": "wan_video_api",
                    "model": "wan2.6-t2v",
                },
                {"asset_type": "video", "source_tool": "pexels_video"},
            ],
        },
    })
    return proposal


def _minimal_ad_video_scene_plan(*, user_approved: bool) -> dict[str, Any]:
    return {
        "version": "1.0",
        "user_approved": user_approved,
        "style_mode": "cinematic",
        "total_duration_seconds": 5,
        "scenes": [
            {
                "id": "scene-1",
                "type": "text_card",
                "description": "Opening product promise.",
                "start_seconds": 0,
                "end_seconds": 5,
                "duration_seconds": 5,
                "core": True,
                "motion_required": False,
                "product_visibility": "none",
                "product_reference_required": False,
            }
        ],
    }


def _decision_log_with_approved_runtime_and_product_ref() -> dict[str, Any]:
    return {
        "version": "1.0",
        "project_id": "test-project",
        "decisions": [
            {
                "decision_id": "d-runtime-001",
                "stage": "proposal",
                "category": "render_runtime_selection",
                "subject": "Select render runtime",
                "options_considered": [
                    {
                        "option_id": "remotion",
                        "label": "Remotion",
                        "score": 0.5,
                        "reason": "Available alternative for motion graphics.",
                    },
                    {
                        "option_id": "hyperframes",
                        "label": "HyperFrames",
                        "score": 0.5,
                        "reason": "Available alternative for HTML/GSAP composition.",
                    },
                    {
                        "option_id": "ffmpeg",
                        "label": "FFmpeg",
                        "score": 0.9,
                        "reason": "Best for cinematic source-footage assembly.",
                    },
                ],
                "selected": "ffmpeg",
                "reason": "Best for cinematic style",
                "user_visible": True,
                "user_approved": True,
            },
            {
                "decision_id": "d-pir-001",
                "stage": "proposal",
                "category": "product_identity_reference_selection",
                "subject": "Select product reference strategy",
                "options_considered": [
                    {"option_id": "generate_concept_reference", "label": "Generate", "score": 0.8, "reason": "Best for this product"},
                ],
                "selected": "generate_concept_reference",
                "reason": "Best for this product",
                "user_visible": True,
                "user_approved": True,
            },
            {
                "decision_id": "d-music-strategy-001",
                "stage": "proposal",
                "category": "music_strategy_selection",
                "subject": "Select music strategy",
                "options_considered": [
                    {
                        "option_id": "generative_loose",
                        "label": "Generative loose",
                        "score": 0.8,
                        "reason": "Best fit when bar-precise sync is not required",
                    },
                ],
                "selected": "generative_loose",
                "reason": "Matches the approved music plan",
                "user_visible": True,
                "user_approved": True,
            },
        ],
    }


class TestCheckpointWriteReadRoundtrip:
    def test_ad_video_intake_roundtrip(self, tmp_path: Path) -> None:
        artifacts = {"intake_brief": _minimal_ad_video_intake_brief()}
        path = write_checkpoint(
            tmp_path, "test-proj", "research.intake", "completed", artifacts,
            pipeline_type="ad-video",
        )
        assert path.exists()

        cp = read_checkpoint(tmp_path, "test-proj", "research.intake")
        assert cp is not None
        assert cp["stage"] == "research.intake"
        assert cp["status"] == "completed"
        assert cp["pipeline_type"] == "ad-video"
        assert "intake_brief" in cp["artifacts"]

    def test_read_nonexistent_returns_none(self, tmp_path: Path) -> None:
        assert read_checkpoint(tmp_path, "test-proj", "research.intake") is None

    def test_write_with_metadata(self, tmp_path: Path) -> None:
        artifacts = {"intake_brief": _minimal_ad_video_intake_brief()}
        write_checkpoint(
            tmp_path, "test-proj", "research.intake", "completed", artifacts,
            pipeline_type="ad-video",
            metadata={"ep_state": {"sample_approved": True}},
        )
        cp = read_checkpoint(tmp_path, "test-proj", "research.intake")
        assert cp is not None
        assert cp["metadata"]["ep_state"]["sample_approved"] is True

    def test_write_with_error(self, tmp_path: Path) -> None:
        artifacts = {"intake_brief": _minimal_ad_video_intake_brief()}
        write_checkpoint(
            tmp_path, "test-proj", "research.intake", "failed", artifacts,
            pipeline_type="ad-video",
            error="Something went wrong",
        )
        cp = read_checkpoint(tmp_path, "test-proj", "research.intake")
        assert cp is not None
        assert cp["error"] == "Something went wrong"
        assert cp["status"] == "failed"

    def test_write_with_review(self, tmp_path: Path) -> None:
        artifacts = {"intake_brief": _minimal_ad_video_intake_brief()}
        review = {"verdict": "pass", "notes": "Looks good"}
        write_checkpoint(
            tmp_path, "test-proj", "research.intake", "completed", artifacts,
            pipeline_type="ad-video",
            review=review,
        )
        cp = read_checkpoint(tmp_path, "test-proj", "research.intake")
        assert cp is not None
        assert cp["review"]["verdict"] == "pass"

    def test_write_with_cost_snapshot(self, tmp_path: Path) -> None:
        artifacts = {"intake_brief": _minimal_ad_video_intake_brief()}
        cost = {"total_usd": 1.23}
        write_checkpoint(
            tmp_path, "test-proj", "research.intake", "completed", artifacts,
            pipeline_type="ad-video",
            cost_snapshot=cost,
        )
        cp = read_checkpoint(tmp_path, "test-proj", "research.intake")
        assert cp is not None
        assert cp["cost_snapshot"]["total_usd"] == 1.23

    def test_scene_plan_awaiting_human_allows_pending_user_approval(
        self, tmp_path: Path
    ) -> None:
        artifacts = {
            "scene_plan": _minimal_ad_video_scene_plan(user_approved=False),
        }

        path = write_checkpoint(
            tmp_path,
            "test-proj",
            "scene_plan",
            "awaiting_human",
            artifacts,
            pipeline_type="ad-video",
            human_approval_required=True,
            human_approved=False,
        )

        assert path.exists()
        cp = read_checkpoint(tmp_path, "test-proj", "scene_plan")
        assert cp is not None
        assert cp["status"] == "awaiting_human"
        assert cp["artifacts"]["scene_plan"]["user_approved"] is False

    def test_scene_plan_completed_checkpoint_requires_user_approval(
        self, tmp_path: Path
    ) -> None:
        artifacts = {
            "scene_plan": _minimal_ad_video_scene_plan(user_approved=False),
        }

        with pytest.raises(CheckpointValidationError, match="user_approved"):
            write_checkpoint(
                tmp_path,
                "test-proj",
                "scene_plan",
                "completed",
                artifacts,
                pipeline_type="ad-video",
            )

    def test_ad_video_proposal_with_decision_log_merge(self, tmp_path: Path) -> None:
        proposal = _minimal_ad_video_proposal_with_decisions()
        decision_log = _decision_log_with_approved_runtime_and_product_ref()
        artifacts = {
            "production_proposal": proposal,
            "decision_log": decision_log,
        }
        write_checkpoint(
            tmp_path, "test-proj", "proposal.technical_proposal", "completed", artifacts,
            pipeline_type="ad-video",
        )

        log_path = tmp_path / "test-proj" / "decision_log.json"
        assert log_path.exists()
        log = json.loads(log_path.read_text())
        assert len(log["decisions"]) == 3

        cp = read_checkpoint(tmp_path, "test-proj", "proposal.technical_proposal")
        assert cp is not None
        assert "decision_log_ref" in cp["artifacts"]["production_proposal"]

    def test_decision_log_idempotent_merge(self, tmp_path: Path) -> None:
        proposal = _minimal_ad_video_proposal_with_decisions()
        decision_log = _decision_log_with_approved_runtime_and_product_ref()
        artifacts = {
            "production_proposal": proposal,
            "decision_log": decision_log,
        }
        write_checkpoint(
            tmp_path, "test-proj", "proposal.technical_proposal", "completed", artifacts,
            pipeline_type="ad-video",
        )
        write_checkpoint(
            tmp_path, "test-proj", "proposal.technical_proposal", "completed", artifacts,
            pipeline_type="ad-video",
        )

        log_path = tmp_path / "test-proj" / "decision_log.json"
        log = json.loads(log_path.read_text())
        assert len(log["decisions"]) == 3

    def test_invalid_decision_log_does_not_write_cumulative_log(self, tmp_path: Path) -> None:
        proposal = _minimal_ad_video_proposal_with_decisions()
        decision_log = _decision_log_with_approved_runtime_and_product_ref()
        decision_log["decisions"].append(dict(decision_log["decisions"][0]))
        artifacts = {
            "production_proposal": proposal,
            "decision_log": decision_log,
        }

        with pytest.raises(CheckpointValidationError, match="decision_log"):
            write_checkpoint(
                tmp_path,
                "test-proj",
                "proposal.technical_proposal",
                "completed",
                artifacts,
                pipeline_type="ad-video",
            )

        assert not (tmp_path / "test-proj" / "decision_log.json").exists()

    def test_non_finite_checkpoint_payload_is_rejected_before_side_effects(
        self, tmp_path: Path
    ) -> None:
        artifacts = {
            "production_proposal": _minimal_ad_video_proposal_with_decisions(),
            "decision_log": _decision_log_with_approved_runtime_and_product_ref(),
        }

        with pytest.raises(CheckpointValidationError, match="strict JSON"):
            write_checkpoint(
                tmp_path,
                "test-proj",
                "proposal.technical_proposal",
                "completed",
                artifacts,
                pipeline_type="ad-video",
                cost_snapshot={"total_usd": math.nan},
            )

        assert not (tmp_path / "test-proj" / "decision_log.json").exists()
        assert not (
            tmp_path / "test-proj" / "checkpoint_proposal.technical_proposal.json"
        ).exists()

    def test_invalid_stage_rejected(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="Invalid stage"):
            write_checkpoint(
                tmp_path, "test-proj", "bogus_stage", "completed",
                {"intake_brief": _minimal_ad_video_intake_brief()},
                pipeline_type="ad-video",
            )

    def test_read_dotted_gate_falls_back_to_legacy_checkpoint_file(
        self, tmp_path: Path
    ) -> None:
        project_dir = tmp_path / "test-proj"
        project_dir.mkdir()
        legacy_checkpoint = {
            "version": "1.0",
            "project_id": "test-proj",
            "pipeline_type": "ad-video",
            "stage": "intake",
            "status": "completed",
            "timestamp": "2026-06-07T00:00:00+00:00",
            "checkpoint_policy": "guided",
            "human_approval_required": False,
            "human_approved": False,
            "artifacts": {"intake_brief": _minimal_ad_video_intake_brief()},
        }
        (project_dir / "checkpoint_intake.json").write_text(
            json.dumps(legacy_checkpoint),
            encoding="utf-8",
        )

        cp = read_checkpoint(tmp_path, "test-proj", "research.intake")

        assert cp is not None
        assert cp["stage"] == "research.intake"


class TestCheckpointGetCompletedStages:
    def test_no_checkpoints_returns_empty(self, tmp_path: Path) -> None:
        stages = get_completed_stages(tmp_path, "test-proj", "ad-video")
        assert stages == []

    def test_completed_stages_returned_in_order(self, tmp_path: Path) -> None:
        artifacts = {"intake_brief": _minimal_ad_video_intake_brief()}
        write_checkpoint(
            tmp_path, "test-proj", "research.intake", "completed", artifacts,
            pipeline_type="ad-video",
        )
        stages = get_completed_stages(tmp_path, "test-proj", "ad-video")
        assert stages == ["research.intake"]

    def test_failed_stage_not_counted_as_completed(self, tmp_path: Path) -> None:
        artifacts = {"intake_brief": _minimal_ad_video_intake_brief()}
        write_checkpoint(
            tmp_path, "test-proj", "research.intake", "failed", artifacts,
            pipeline_type="ad-video",
        )
        stages = get_completed_stages(tmp_path, "test-proj", "ad-video")
        assert stages == []


class TestCheckpointGetNextStage:
    def test_first_stage_when_none_completed(self, tmp_path: Path) -> None:
        next_stage = get_next_stage(tmp_path, "test-proj", "ad-video")
        assert next_stage == "research.intake"

    def test_second_stage_after_first_completed(self, tmp_path: Path) -> None:
        artifacts = {"intake_brief": _minimal_ad_video_intake_brief()}
        write_checkpoint(
            tmp_path, "test-proj", "research.intake", "completed", artifacts,
            pipeline_type="ad-video",
        )
        next_stage = get_next_stage(tmp_path, "test-proj", "ad-video")
        assert next_stage == "research.brief_enrichment"

    def test_get_next_stage_with_no_pipeline_type(self, tmp_path: Path) -> None:
        result = get_next_stage(tmp_path, "test-proj")
        assert result is not None


class TestCheckpointGetLatest:
    def test_no_project_dir_returns_none(self, tmp_path: Path) -> None:
        assert get_latest_checkpoint(tmp_path, "nonexistent") is None

    def test_returns_most_recent_checkpoint(self, tmp_path: Path) -> None:
        artifacts = {"intake_brief": _minimal_ad_video_intake_brief()}
        write_checkpoint(
            tmp_path, "test-proj", "research.intake", "completed", artifacts,
            pipeline_type="ad-video",
        )
        cp = get_latest_checkpoint(tmp_path, "test-proj")
        assert cp is not None
        assert cp["stage"] == "research.intake"


class TestCheckpointValidation:
    def test_validate_valid_checkpoint(self) -> None:
        cp = {
            "version": "1.0",
            "project_id": "test",
            "pipeline_type": "ad-video",
            "stage": "research.intake",
            "status": "completed",
            "timestamp": "2026-05-26T00:00:00Z",
            "checkpoint_policy": "guided",
            "human_approval_required": False,
            "human_approved": False,
            "artifacts": {"intake_brief": _minimal_ad_video_intake_brief()},
        }
        validate_checkpoint(cp)

    def test_validate_checkpoint_enforces_timestamp_format(self) -> None:
        cp = {
            "version": "1.0",
            "project_id": "test",
            "pipeline_type": "ad-video",
            "stage": "research.intake",
            "status": "completed",
            "timestamp": "not-a-date-time",
            "checkpoint_policy": "guided",
            "human_approval_required": False,
            "human_approved": False,
            "artifacts": {"intake_brief": _minimal_ad_video_intake_brief()},
        }

        with pytest.raises(CheckpointValidationError, match="timestamp"):
            validate_checkpoint(cp)

    def test_validate_invalid_status_type(self) -> None:
        cp = {
            "version": "1.0",
            "project_id": "test",
            "pipeline_type": "ad-video",
            "stage": "research.intake",
            "status": 42,
            "timestamp": "2026-05-26T00:00:00Z",
            "artifacts": {},
        }
        with pytest.raises(CheckpointValidationError, match="Invalid status"):
            validate_checkpoint(cp)

    def test_validate_artifacts_not_dict(self) -> None:
        cp = {
            "version": "1.0",
            "project_id": "test",
            "pipeline_type": "ad-video",
            "stage": "research.intake",
            "status": "completed",
            "timestamp": "2026-05-26T00:00:00Z",
            "artifacts": "not a dict",
        }
        with pytest.raises(CheckpointValidationError, match="must be a dictionary"):
            validate_checkpoint(cp)

    def test_validate_ad_video_proposal_missing_decision_log(self) -> None:
        proposal = _minimal_ad_video_proposal_with_decisions()
        cp = {
            "version": "1.0",
            "project_id": "test",
            "pipeline_type": "ad-video",
            "stage": "proposal.technical_proposal",
            "status": "completed",
            "timestamp": "2026-05-26T00:00:00Z",
            "artifacts": {"production_proposal": proposal},
        }
        with pytest.raises(CheckpointValidationError, match="decision_log"):
            validate_checkpoint(cp)
