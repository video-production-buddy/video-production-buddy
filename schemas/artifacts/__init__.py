"""Artifact schema loading and validation utilities."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import jsonschema

SCHEMA_DIR = Path(__file__).parent

ARTIFACT_NAMES = [
    "user_request",
    "research_brief",
    "proposal_packet",
    "brief",
    "intake_brief",
    "enriched_brief",
    "intelligence_brief",
    "production_bible",
    "idea_options",
    "production_proposal",
    "product_identity_reference",
    "script",
    "character_design",
    "rig_plan",
    "pose_library",
    "scene_plan",
    "action_timeline",
    "asset_manifest",
    "edit_decisions",
    "render_report",
    "publish_log",
    "review",
    "cost_log",
    "decision_log",
    "ui_form_config",
    "ui_response",
    "source_media_review",
    "final_review",
    "character_qa_report",
    "video_analysis_brief",
]


def load_schema(name: str) -> dict:
    """Load a JSON schema by artifact name."""
    path = SCHEMA_DIR / f"{name}.schema.json"
    if not path.exists():
        raise FileNotFoundError(f"Schema not found: {path}")
    with open(path) as f:
        return json.load(f)


def _validate_ad_video_script(data: dict[str, Any]) -> None:
    """Enforce ad-video script requirements that need pipeline context."""
    required_voice_performance = [
        "emotion",
        "intonation",
        "rhythm",
        "pace",
        "pause_after_seconds",
    ]
    seen_section_ids: set[str] = set()
    previous_end: float | None = None
    timeline_end = 0.0
    for idx, section in enumerate(data.get("sections", []) or []):
        section_id = section.get("id", f"section-{idx}")
        if section_id in seen_section_ids:
            raise jsonschema.ValidationError(
                "ad-video script contains duplicate section id "
                f"{section_id!r}; section ids must be unique because "
                "scene_plan.scenes[].script_section_id maps to them"
            )
        seen_section_ids.add(section_id)

        start_seconds = float(section.get("start_seconds"))
        end_seconds = float(section.get("end_seconds"))
        if end_seconds <= start_seconds:
            raise jsonschema.ValidationError(
                "ad-video script section "
                f"{section_id!r} end_seconds must be greater than start_seconds"
            )

        if previous_end is not None:
            if start_seconds < previous_end - 1e-6:
                raise jsonschema.ValidationError(
                    "ad-video script section "
                    f"{section_id!r} overlaps previous section; start_seconds "
                    "must equal the previous section end_seconds"
                )
            if start_seconds > previous_end + 1e-6:
                raise jsonschema.ValidationError(
                    "ad-video script has a timeline gap before section "
                    f"{section_id!r}; add an explicit section or align "
                    "start_seconds to the previous section end_seconds"
                )

        duration_estimate = section.get("duration_estimate_seconds")
        expected_duration = end_seconds - start_seconds
        if (
            duration_estimate is not None
            and abs(float(duration_estimate) - expected_duration) > 0.05
        ):
            raise jsonschema.ValidationError(
                "ad-video script section "
                f"{section_id!r} duration_estimate_seconds must equal "
                "end_seconds - start_seconds"
            )

        previous_end = end_seconds
        timeline_end = end_seconds

        speaker_directions = section.get("speaker_directions")
        if not isinstance(speaker_directions, str) or not speaker_directions.strip():
            raise jsonschema.ValidationError(
                "ad-video script section "
                f"{section_id!r} must include non-empty speaker_directions"
            )

        voice_performance = section.get("voice_performance")
        if not isinstance(voice_performance, dict):
            raise jsonschema.ValidationError(
                "ad-video script section "
                f"{section_id!r} must include voice_performance"
            )

        missing = [
            field
            for field in required_voice_performance
            if field not in voice_performance
        ]
        if missing:
            raise jsonschema.ValidationError(
                "ad-video script section "
                f"{section_id!r} voice_performance missing fields: {missing}"
            )

        if not isinstance(section.get("tts_directive"), dict):
            raise jsonschema.ValidationError(
                "ad-video script section "
                f"{section_id!r} must include tts_directive"
            )

    total_duration = data.get("total_duration_seconds")
    if total_duration is not None and abs(float(total_duration) - timeline_end) > 0.5:
        raise jsonschema.ValidationError(
            "ad-video script total_duration_seconds must match the final "
            "section end_seconds within +/-0.5s"
        )

    if data.get("user_approved") is not True:
        raise jsonschema.ValidationError(
            "ad-video script.user_approved must be true"
        )


def _validate_ad_video_enriched_brief(data: dict[str, Any]) -> None:
    """Enforce the ad-video G-0 human approval gate."""
    if data.get("user_approved") is not True:
        raise jsonschema.ValidationError(
            "ad-video enriched_brief.user_approved must be true"
        )


def _validate_intelligence_brief(data: dict[str, Any]) -> None:
    """Enforce semantic references inside intelligence research output."""
    professional_knowledge = data.get("professional_knowledge") or {}
    card_ids: set[str] = set()
    for idx, card in enumerate(professional_knowledge.get("cards_used") or []):
        card_id = str(card.get("card_id") or "").strip()
        if card_id in card_ids:
            raise jsonschema.ValidationError(
                "intelligence_brief.professional_knowledge.cards_used "
                f"contains duplicate card_id {card_id!r}"
            )
        card_ids.add(card_id)

        expected_ref = f"knowledge_alignment:{card_id}"
        if str(card.get("source_ref") or "").strip() != expected_ref:
            raise jsonschema.ValidationError(
                "intelligence_brief.professional_knowledge.cards_used"
                f"[{idx}].source_ref must equal {expected_ref!r}"
            )

    for collection_name in ("application_recommendations", "contraindications"):
        for idx, entry in enumerate(professional_knowledge.get(collection_name) or []):
            card_id = str(entry.get("card_id") or "").strip()
            if card_id not in card_ids:
                raise jsonschema.ValidationError(
                    "intelligence_brief.professional_knowledge."
                    f"{collection_name}[{idx}].card_id {card_id!r} must "
                    "match professional_knowledge.cards_used[].card_id"
                )

    seen_trend_ids: set[str] = set()
    for idx, trend in enumerate(data.get("platform_trends") or []):
        trend_id = str(trend.get("trend_id") or "").strip()
        if not trend_id:
            continue
        if trend_id in seen_trend_ids:
            raise jsonschema.ValidationError(
                "intelligence_brief.platform_trends contains duplicate "
                f"trend_id {trend_id!r} at index {idx}"
            )
        seen_trend_ids.add(trend_id)


def _validate_ad_video_production_proposal(data: dict[str, Any]) -> None:
    """Enforce proposal-stage user confirmations before production spend."""
    if data.get("budget_confirmed") is not True:
        raise jsonschema.ValidationError(
            "ad-video production_proposal.budget_confirmed must be true"
        )

    subtitles = data.get("subtitles")
    if not isinstance(subtitles, dict) or subtitles.get("user_confirmed") is not True:
        raise jsonschema.ValidationError(
            "ad-video production_proposal.subtitles.user_confirmed must be true"
        )

    seen_derivatives: set[str] = set()
    allowed_derivatives = {"9:16", "1:1", "15s", "15s_short"}
    for derivative in data.get("derivatives_added") or []:
        if not isinstance(derivative, str) or derivative not in allowed_derivatives:
            raise jsonschema.ValidationError(
                "ad-video production_proposal.derivatives_added contains "
                f"unsupported variant {derivative!r}; expected one of "
                + ", ".join(sorted(repr(variant) for variant in allowed_derivatives))
            )
        if derivative in seen_derivatives:
            raise jsonschema.ValidationError(
                "ad-video production_proposal.derivatives_added contains "
                f"duplicate variant {derivative!r}"
            )
        seen_derivatives.add(derivative)

    seen_dub_languages: set[str] = set()
    for dub in data.get("dubbing") or []:
        language = str(dub.get("language") or "").strip().casefold()
        if language in seen_dub_languages:
            raise jsonschema.ValidationError(
                "ad-video production_proposal.dubbing contains duplicate "
                f"language {dub.get('language')!r}"
            )
        seen_dub_languages.add(language)


def _validate_idea_options(data: dict[str, Any]) -> None:
    """Enforce concept-selection invariants described by the schema."""
    concepts = data.get("concepts") or []
    seen_concept_ids: set[str] = set()
    for concept in concepts:
        if not isinstance(concept, dict):
            continue
        concept_id = concept.get("id")
        if concept_id in seen_concept_ids:
            raise jsonschema.ValidationError(
                f"idea_options.concepts contains duplicate concept id {concept_id!r}"
            )
        seen_concept_ids.add(concept_id)

    selected_concepts = [
        concept
        for concept in concepts
        if isinstance(concept, dict) and concept.get("selected") is True
    ]
    if len(selected_concepts) != 1:
        raise jsonschema.ValidationError(
            "idea_options.concepts must contain exactly one selected=true concept"
        )

    selected_id = data.get("selected_concept_id")
    selected_concept_id = selected_concepts[0].get("id")
    if selected_id != selected_concept_id:
        raise jsonschema.ValidationError(
            "idea_options.selected_concept_id must match the selected concept id"
        )


def _validate_ad_video_production_bible(data: dict[str, Any]) -> None:
    """Enforce derived emotional rhythm data for ad-video bibles."""
    from lib.intensity_curve import derive_intensity_curve

    approval = data.get("approval") or {}
    for field in ("strategic_approved", "execution_approved"):
        if approval.get(field) is not True:
            raise jsonschema.ValidationError(
                f"ad-video production_bible.approval.{field} must be true"
            )

    identity = data.get("identity") or {}
    cta = identity.get("cta")
    if cta is None or (isinstance(cta, str) and not cta.strip()):
        raise jsonschema.ValidationError(
            "ad-video production_bible.identity.cta must be non-null"
        )

    truth_contract = data.get("truth_contract")
    if not isinstance(truth_contract, dict):
        raise jsonschema.ValidationError(
            "ad-video production_bible.truth_contract is required"
        )
    for section in ("objective_facts", "physical_constraints",
                     "product_geometry_rules", "motion_coherence_rules",
                     "values_guardrails"):
        rules = truth_contract.get(section)
        if not isinstance(rules, list) or not rules:
            raise jsonschema.ValidationError(
                f"ad-video production_bible.truth_contract.{section} "
                "must contain at least one rule"
            )

    narrative = data.get("narrative") or {}
    beats = narrative.get("emotional_beat_sequence") or []
    seen_beat_ids: set[str] = set()
    for beat in beats:
        beat_id = beat.get("beat_id")
        if beat_id in seen_beat_ids:
            raise jsonschema.ValidationError(
                "ad-video production_bible.narrative.emotional_beat_sequence "
                f"contains duplicate beat_id {beat_id!r}"
            )
        seen_beat_ids.add(beat_id)

    curve = narrative.get("intensity_curve")
    if not isinstance(curve, list) or not curve:
        raise jsonschema.ValidationError(
            "ad-video production_bible.narrative.intensity_curve is required"
        )

    expected = derive_intensity_curve(beats)
    if len(curve) != len(expected):
        raise jsonschema.ValidationError(
            "ad-video production_bible.narrative.intensity_curve must match "
            "lib.intensity_curve.derive_intensity_curve(emotional_beat_sequence); "
            f"expected {len(expected)} samples, got {len(curve)}"
        )

    for idx, (actual, wanted) in enumerate(zip(curve, expected)):
        actual_t = float(actual.get("t_seconds"))
        actual_value = float(actual.get("value"))
        wanted_t = float(wanted["t_seconds"])
        wanted_value = float(wanted["value"])
        if abs(actual_t - wanted_t) > 1e-6 or abs(actual_value - wanted_value) > 1e-6:
            raise jsonschema.ValidationError(
                "ad-video production_bible.narrative.intensity_curve must match "
                "lib.intensity_curve.derive_intensity_curve(emotional_beat_sequence); "
                f"sample {idx} expected {wanted!r}, got {actual!r}"
            )

    intelligence = data.get("intelligence")
    if isinstance(intelligence, dict):
        for block in ("trend_alignment", "knowledge_alignment"):
            if block not in intelligence:
                raise jsonschema.ValidationError(
                    f"ad-video production_bible.intelligence.{block} is required"
                )
        _validate_alignment_block(
            intelligence.get("trend_alignment") or {},
            block_name="trend_alignment",
            selected_key="selected_trend_ids",
            alignment_id_key="trend_id",
            ref_prefix="trend_alignment",
        )
        _validate_alignment_block(
            intelligence.get("knowledge_alignment") or {},
            block_name="knowledge_alignment",
            selected_key="selected_card_ids",
            alignment_id_key="card_id",
            ref_prefix="knowledge_alignment",
        )


def _validate_alignment_block(
    block: dict[str, Any],
    *,
    block_name: str,
    selected_key: str,
    alignment_id_key: str,
    ref_prefix: str,
) -> None:
    selected_ids = {
        str(item).strip()
        for item in block.get(selected_key) or []
    }

    aligned_ids: set[str] = set()
    for idx, alignment in enumerate(block.get("alignments") or []):
        alignment_id = str(alignment.get(alignment_id_key) or "").strip()
        if alignment_id in aligned_ids:
            raise jsonschema.ValidationError(
                "ad-video production_bible.intelligence."
                f"{block_name}.alignments contains duplicate {alignment_id_key} "
                f"{alignment_id!r}"
            )
        aligned_ids.add(alignment_id)

        expected_ref = f"{ref_prefix}:{alignment_id}"
        ref_checks = [
            (
                "script_usage.source_ref",
                (alignment.get("script_usage") or {}).get("source_ref"),
            ),
        ]
        if "source_ref" in alignment:
            ref_checks.append(("source_ref", alignment.get("source_ref")))

        for path, actual_ref in ref_checks:
            if str(actual_ref or "").strip() != expected_ref:
                raise jsonschema.ValidationError(
                    "ad-video production_bible.intelligence."
                    f"{block_name}.alignments[{idx}].{path} must equal "
                    f"{expected_ref!r}"
                )

    missing_alignments = selected_ids - aligned_ids
    extra_alignments = aligned_ids - selected_ids
    if missing_alignments or extra_alignments:
        missing_kind = (
            "missing_selected_trend_alignment"
            if block_name == "trend_alignment"
            else "missing_selected_knowledge_alignment"
        )
        raise jsonschema.ValidationError(
            "ad-video production_bible.intelligence."
            f"{block_name}.{selected_key} must match alignments[]."
            f"{alignment_id_key}; missing={sorted(missing_alignments)!r}, "
            f"extra={sorted(extra_alignments)!r}; {missing_kind}"
        )


def _validate_ad_video_scene_plan(data: dict[str, Any]) -> None:
    """Enforce ad-video scene metadata that needs pipeline context."""
    animated = data.get("style_mode") == "animated"
    seen_scene_ids: set[str] = set()
    previous_end: float | None = None
    timeline_end = 0.0
    for idx, scene in enumerate(data.get("scenes", []) or []):
        scene_id = scene.get("id", f"scene-{idx}")
        if scene_id in seen_scene_ids:
            raise jsonschema.ValidationError(
                "ad-video scene_plan contains duplicate scene id "
                f"{scene_id!r}; scene ids must be unique because asset, "
                "edit, and review gates key by scene_id"
            )
        seen_scene_ids.add(scene_id)

        if "product_visibility" not in scene:
            raise jsonschema.ValidationError(
                "ad-video scene_plan scene "
                f"{scene_id!r} must include product_visibility"
            )
        if "product_reference_required" not in scene:
            raise jsonschema.ValidationError(
                "ad-video scene_plan scene "
                f"{scene_id!r} must include product_reference_required"
            )
        scene_kind = str(scene.get("type") or "").strip()
        scene_type = str(scene.get("scene_type") or "").strip()
        still_allowed = (
            scene_kind == "text_card"
            or scene.get("product_visibility") == "packshot"
            or scene_type == "brand_landing"
        )
        if (
            scene_kind in {"broll", "generated"}
            and not still_allowed
            and scene.get("motion_required") is not True
        ):
            raise jsonschema.ValidationError(
                "ad-video scene_plan scene "
                f"{scene_id!r} has type {scene_kind!r}; broll and generated "
                "scenes must set motion_required=true unless they are text "
                "cards, packshots, or brand landing frames"
            )
        if animated and "scene_type" not in scene:
            raise jsonschema.ValidationError(
                "ad-video animated scene_plan scene "
                f"{scene_id!r} must include scene_type from "
                "remotion-composer/scene_type_registry.json"
            )

        start_seconds = float(scene.get("start_seconds"))
        end_seconds = float(scene.get("end_seconds"))
        if end_seconds <= start_seconds:
            raise jsonschema.ValidationError(
                "ad-video scene_plan scene "
                f"{scene_id!r} end_seconds must be greater than start_seconds"
            )

        if previous_end is not None:
            if start_seconds < previous_end - 1e-6:
                raise jsonschema.ValidationError(
                    "ad-video scene_plan scene "
                    f"{scene_id!r} overlaps previous scene; start_seconds must "
                    "equal the previous scene end_seconds"
                )
            if start_seconds > previous_end + 1e-6:
                raise jsonschema.ValidationError(
                    "ad-video scene_plan has a timeline gap before scene "
                    f"{scene_id!r}; add an explicit scene or align start_seconds "
                    "to the previous scene end_seconds"
                )

        duration_seconds = scene.get("duration_seconds")
        expected_duration = end_seconds - start_seconds
        if duration_seconds is not None and abs(float(duration_seconds) - expected_duration) > 0.05:
            raise jsonschema.ValidationError(
                "ad-video scene_plan scene "
                f"{scene_id!r} duration_seconds must equal "
                "end_seconds - start_seconds"
            )

        previous_end = end_seconds
        timeline_end = end_seconds

    total_duration = data.get("total_duration_seconds")
    if total_duration is not None and abs(float(total_duration) - timeline_end) > 0.5:
        raise jsonschema.ValidationError(
            "ad-video scene_plan total_duration_seconds must match the final "
            "scene end_seconds within +/-0.5s"
        )


def _ad_video_derivative_needs_aspect_crop(variant: str) -> bool:
    normalized = variant.strip().lower()
    return "9:16" in normalized or "1:1" in normalized


def _ad_video_derivative_needs_short_scene_selection(variant: str) -> bool:
    normalized = variant.strip().lower()
    return normalized in {"15s", "15s_short"} or "15s" in normalized


def _ad_video_scene_durations_by_id(scene_plan: dict[str, Any]) -> dict[str, float]:
    durations: dict[str, float] = {}
    scenes = scene_plan.get("scenes")
    if not isinstance(scenes, list):
        return durations

    for idx, scene in enumerate(scenes):
        if not isinstance(scene, dict):
            continue
        scene_id = scene.get("id")
        if not isinstance(scene_id, str) or not scene_id.strip():
            scene_id = f"scene-{idx}"
        duration = scene.get("duration_seconds")
        if duration is None:
            try:
                duration = float(scene.get("end_seconds")) - float(
                    scene.get("start_seconds")
                )
            except (TypeError, ValueError):
                continue
        try:
            duration_seconds = float(duration)
        except (TypeError, ValueError):
            continue
        if duration_seconds >= 0:
            durations[scene_id] = duration_seconds

    return durations


def _validate_ad_video_derivative_spec_content(
    variant: str,
    spec: Any,
    scene_plan: dict[str, Any] | None = None,
) -> None:
    if not isinstance(spec, dict):
        raise jsonschema.ValidationError(
            "ad-video edit_decisions.derivative_specs"
            f"[{variant!r}] must be an object"
        )

    if _ad_video_derivative_needs_aspect_crop(variant):
        crop_regions = spec.get("crop_regions")
        if not isinstance(crop_regions, (str, dict)):
            raise jsonschema.ValidationError(
                "ad-video edit_decisions.derivative_specs"
                f"[{variant!r}].crop_regions is required for aspect-ratio "
                "derivatives"
            )
        if isinstance(crop_regions, str):
            if crop_regions.strip() != "from_scene_plan":
                raise jsonschema.ValidationError(
                    "ad-video edit_decisions.derivative_specs"
                    f"[{variant!r}].crop_regions must be the literal "
                    "'from_scene_plan' or a non-empty crop-region map"
                )
        elif not crop_regions:
            raise jsonschema.ValidationError(
                "ad-video edit_decisions.derivative_specs"
                f"[{variant!r}].crop_regions must be a non-empty crop-region map"
            )

    if _ad_video_derivative_needs_short_scene_selection(variant):
        include_scenes = spec.get("include_scenes")
        if not isinstance(include_scenes, list) or not include_scenes:
            raise jsonschema.ValidationError(
                "ad-video edit_decisions.derivative_specs"
                f"[{variant!r}].include_scenes must list the scene ids kept "
                "in the <=15s derivative"
            )
        selected_scene_ids = [
            scene_id.strip()
            for scene_id in include_scenes
            if isinstance(scene_id, str) and scene_id.strip()
        ]
        if len(selected_scene_ids) != len(include_scenes):
            raise jsonschema.ValidationError(
                "ad-video edit_decisions.derivative_specs"
                f"[{variant!r}].include_scenes must contain only non-empty "
                "scene id strings"
            )

        if scene_plan is None:
            return

        scene_durations = _ad_video_scene_durations_by_id(scene_plan)
        if not scene_durations:
            return
        missing_scene_ids = [
            scene_id
            for scene_id in selected_scene_ids
            if scene_id not in scene_durations
        ]
        if missing_scene_ids:
            raise jsonschema.ValidationError(
                "ad-video edit_decisions.derivative_specs"
                f"[{variant!r}].include_scenes references unknown "
                "scene_plan scene ids: "
                + ", ".join(repr(scene_id) for scene_id in missing_scene_ids)
            )

        total_duration = sum(
            scene_durations[scene_id] for scene_id in selected_scene_ids
        )
        if total_duration > 15.05:
            raise jsonschema.ValidationError(
                "ad-video edit_decisions.derivative_specs"
                f"[{variant!r}].include_scenes totals "
                f"{total_duration:.2f}s, which exceeds the 15s short "
                "derivative limit"
            )


def _ad_video_decision_option_ids(decision: dict[str, Any]) -> set[str]:
    options = decision.get("options_considered")
    if not isinstance(options, list):
        return set()
    return {
        option.get("option_id")
        for option in options
        if isinstance(option, dict) and isinstance(option.get("option_id"), str)
    }


def _find_ad_video_approved_decision_selection(
    decision_log: dict[str, Any] | None,
    *,
    category: str,
    selected: Any,
) -> dict[str, Any] | None:
    if not isinstance(decision_log, dict) or not isinstance(selected, str):
        return None

    decisions = decision_log.get("decisions")
    if not isinstance(decisions, list):
        return None

    for decision in reversed(decisions):
        if not isinstance(decision, dict):
            continue
        decision_selected = decision.get("selected")
        if (
            decision.get("category") == category
            and decision.get("user_visible") is True
            and decision.get("user_approved") is True
            and decision_selected == selected
            and decision_selected in _ad_video_decision_option_ids(decision)
        ):
            return decision
    return None


def _ad_video_effective_edit_value(
    *,
    production_proposal: dict[str, Any],
    edit_decisions: dict[str, Any] | None,
    decision_log: dict[str, Any] | None,
    proposal_field: str,
    decision_category: str,
) -> Any:
    """Return the approved edit-stage value, or the proposal lock."""
    proposal_value = production_proposal.get(proposal_field)
    if not isinstance(edit_decisions, dict):
        return proposal_value

    edit_value = edit_decisions.get(proposal_field)
    if edit_value == proposal_value:
        return edit_value

    if (
        isinstance(edit_value, str)
        and _find_ad_video_approved_decision_selection(
            decision_log,
            category=decision_category,
            selected=edit_value,
        )
        is not None
    ):
        return edit_value

    return proposal_value


def _validate_ad_video_edit_matches_production_proposal(
    edit_decisions: dict[str, Any],
    production_proposal: dict[str, Any],
    decision_log: dict[str, Any] | None = None,
    scene_plan: dict[str, Any] | None = None,
) -> None:
    """Ensure edit-stage locks preserve the approved production proposal."""
    expected_runtime = production_proposal.get("render_runtime")
    actual_runtime = edit_decisions.get("render_runtime")
    if (
        isinstance(expected_runtime, str)
        and expected_runtime.strip()
        and actual_runtime != expected_runtime
        and _find_ad_video_approved_decision_selection(
            decision_log,
            category="render_runtime_selection",
            selected=actual_runtime,
        )
        is None
    ):
        raise jsonschema.ValidationError(
            "ad-video edit_decisions.render_runtime must match "
            "production_proposal.render_runtime unless an approved "
            "render_runtime_selection decision selects the edit runtime"
        )

    actual_music_strategy = edit_decisions.get("music_strategy")
    expected_music_strategy = production_proposal.get("music_strategy")
    if (
        isinstance(expected_music_strategy, str)
        and expected_music_strategy.strip()
        and actual_music_strategy != expected_music_strategy
        and _find_ad_video_approved_decision_selection(
            decision_log,
            category="music_strategy_selection",
            selected=actual_music_strategy,
        )
        is None
    ):
        raise jsonschema.ValidationError(
            "ad-video edit_decisions.music_strategy must match "
            "production_proposal.music_strategy unless an approved "
            "music_strategy_selection decision selects the edit strategy"
        )

    derivative_variants = [
        variant
        for variant in production_proposal.get("derivatives_added") or []
        if isinstance(variant, str) and variant.strip()
    ]
    if not derivative_variants:
        return

    derivative_specs = edit_decisions.get("derivative_specs")
    if not isinstance(derivative_specs, dict):
        raise jsonschema.ValidationError(
            "ad-video edit_decisions.derivative_specs is required when "
            "production_proposal.derivatives_added is non-empty"
        )

    missing_specs = sorted(set(derivative_variants) - set(derivative_specs))
    if missing_specs:
        raise jsonschema.ValidationError(
            "ad-video edit_decisions.derivative_specs must include every "
            "production_proposal.derivatives_added variant; missing "
            + ", ".join(repr(variant) for variant in missing_specs)
        )

    for variant in derivative_variants:
        _validate_ad_video_derivative_spec_content(
            variant,
            derivative_specs.get(variant),
            scene_plan,
        )


def _ad_video_asset_refs(
    asset_manifest: dict[str, Any],
) -> tuple[dict[str, dict[str, Any]], set[str]]:
    assets = asset_manifest.get("assets")
    if not isinstance(assets, list):
        return {}, set()

    assets_by_id: dict[str, dict[str, Any]] = {}
    paths: set[str] = set()
    for asset in assets:
        if not isinstance(asset, dict):
            continue
        asset_id = asset.get("id")
        if isinstance(asset_id, str) and asset_id.strip():
            assets_by_id[asset_id] = asset
        path = asset.get("path")
        if isinstance(path, str) and path.strip():
            paths.add(path)

    for path_key in ("sample_clip", "subtitle_file", "music_file"):
        path = asset_manifest.get(path_key)
        if isinstance(path, str) and path.strip():
            paths.add(path)

    narration_files = asset_manifest.get("narration_files")
    if isinstance(narration_files, list):
        for entry in narration_files:
            if not isinstance(entry, dict):
                continue
            path = entry.get("file")
            if isinstance(path, str) and path.strip():
                paths.add(path)

    return assets_by_id, paths


def _validate_ad_video_edit_matches_asset_manifest(
    edit_decisions: dict[str, Any],
    asset_manifest: dict[str, Any],
) -> None:
    assets_by_id, asset_paths = _ad_video_asset_refs(asset_manifest)
    known_asset_ids = set(assets_by_id)

    for idx, cut in enumerate(edit_decisions.get("cuts", []) or []):
        cut_id = cut.get("id", f"cut-{idx}")
        source = cut.get("source")
        if not isinstance(source, str) or not source.strip():
            continue
        if source.startswith("remotion:"):
            continue
        if source in known_asset_ids or source in asset_paths:
            continue
        raise jsonschema.ValidationError(
            "ad-video edit_decisions cut source "
            f"{source!r} for cut {cut_id!r} must resolve to "
            "asset_manifest.assets[].id, asset_manifest.assets[].path, or "
            "use the remotion:<component> source convention"
        )

    audio = edit_decisions.get("audio")
    narration = audio.get("narration") if isinstance(audio, dict) else None
    segments = narration.get("segments") if isinstance(narration, dict) else None
    if isinstance(segments, list):
        for idx, segment in enumerate(segments):
            if not isinstance(segment, dict):
                continue
            asset_id = segment.get("asset_id")
            if not isinstance(asset_id, str) or not asset_id.strip():
                continue
            asset = assets_by_id.get(asset_id)
            asset_type = asset.get("type") if isinstance(asset, dict) else None
            if asset_type in {"audio", "narration"}:
                continue
            raise jsonschema.ValidationError(
                "ad-video edit_decisions narration segment "
                f"{idx} asset_id {asset_id!r} must resolve to an audio or "
                "narration asset in asset_manifest.assets[]"
            )

    music = audio.get("music") if isinstance(audio, dict) else None
    music_asset_id = music.get("asset_id") if isinstance(music, dict) else None
    if isinstance(music_asset_id, str) and music_asset_id.strip():
        asset = assets_by_id.get(music_asset_id)
        asset_type = asset.get("type") if isinstance(asset, dict) else None
        if asset_type not in {"music", "audio"}:
            raise jsonschema.ValidationError(
                "ad-video edit_decisions.audio.music.asset_id "
                f"{music_asset_id!r} must resolve to a music or audio asset "
                "in asset_manifest.assets[]"
            )

    sfx_items = audio.get("sfx") if isinstance(audio, dict) else None
    if isinstance(sfx_items, list):
        for idx, item in enumerate(sfx_items):
            if not isinstance(item, dict):
                continue
            asset_id = item.get("asset_id")
            if not isinstance(asset_id, str) or not asset_id.strip():
                continue
            asset = assets_by_id.get(asset_id)
            asset_type = asset.get("type") if isinstance(asset, dict) else None
            if asset_type in {"sfx", "audio"}:
                continue
            raise jsonschema.ValidationError(
                "ad-video edit_decisions audio.sfx "
                f"{idx} asset_id {asset_id!r} must resolve to an sfx or "
                "audio asset in asset_manifest.assets[]"
            )

    for idx, overlay in enumerate(edit_decisions.get("overlays") or []):
        if not isinstance(overlay, dict):
            continue
        asset_id = overlay.get("asset_id")
        if not isinstance(asset_id, str) or not asset_id.strip():
            continue
        if asset_id in known_asset_ids:
            continue
        raise jsonschema.ValidationError(
            "ad-video edit_decisions overlay "
            f"{idx} asset_id {asset_id!r} must resolve to "
            "asset_manifest.assets[].id"
        )

    subtitles = edit_decisions.get("subtitles")
    if isinstance(subtitles, dict) and subtitles.get("enabled") is True:
        source = subtitles.get("source")
        if not isinstance(source, str) or not source.strip():
            return
        source = source.strip()
        subtitle_asset = assets_by_id.get(source)
        if isinstance(subtitle_asset, dict):
            subtitle_path = subtitle_asset.get("path")
            if (
                subtitle_asset.get("type") == "subtitle"
                and isinstance(subtitle_path, str)
                and subtitle_path.lower().endswith(".ass")
            ):
                return
        if source in asset_paths and source.lower().endswith(".ass"):
            return
        raise jsonschema.ValidationError(
            "ad-video edit_decisions.subtitles.source "
            f"{source!r} must resolve to an ASS subtitle asset or path in "
            "asset_manifest"
        )


def _scene_plan_windows(
    scene_plan: dict[str, Any],
) -> tuple[list[tuple[float, float, str]], float | None]:
    scenes = scene_plan.get("scenes")
    if not isinstance(scenes, list):
        return [], None

    windows: list[tuple[float, float, str]] = []
    for idx, scene in enumerate(scenes):
        if not isinstance(scene, dict):
            continue
        try:
            start_seconds = float(scene.get("start_seconds"))
            end_seconds = float(scene.get("end_seconds"))
        except (TypeError, ValueError):
            continue
        windows.append((start_seconds, end_seconds, str(scene.get("id", f"scene-{idx}"))))

    total_duration = scene_plan.get("total_duration_seconds")
    if total_duration is not None:
        try:
            return windows, float(total_duration)
        except (TypeError, ValueError):
            return windows, None

    if windows:
        return windows, windows[-1][1]
    return windows, None


def _validate_ad_video_narration_segments_fit_scene_plan(
    edit_decisions: dict[str, Any],
    scene_plan: dict[str, Any],
) -> None:
    scene_windows, _ = _scene_plan_windows(scene_plan)
    if not scene_windows:
        return

    audio = edit_decisions.get("audio")
    narration = audio.get("narration") if isinstance(audio, dict) else None
    segments = narration.get("segments") if isinstance(narration, dict) else None
    if not isinstance(segments, list):
        return

    tolerance = 0.05
    for idx, segment in enumerate(segments):
        if not isinstance(segment, dict) or "end_seconds" not in segment:
            continue
        try:
            start_seconds = float(segment.get("start_seconds"))
            end_seconds = float(segment.get("end_seconds"))
        except (TypeError, ValueError):
            continue

        matching_scene = next(
            (
                (scene_start, scene_end, scene_id)
                for scene_start, scene_end, scene_id in scene_windows
                if scene_start - tolerance <= start_seconds < scene_end
            ),
            None,
        )
        if matching_scene is None:
            raise jsonschema.ValidationError(
                "ad-video edit_decisions narration segment "
                f"{idx} must start within a scene_plan scene window"
            )

        _, scene_end, scene_id = matching_scene
        if end_seconds > scene_end + tolerance:
            raise jsonschema.ValidationError(
                "ad-video edit_decisions narration segment "
                f"{idx} must fit within matching scene_plan scene {scene_id!r}"
            )


def _validate_ad_video_edit_timeline(
    edit_decisions: dict[str, Any],
    scene_plan: dict[str, Any] | None = None,
) -> None:
    previous_end: float | None = None
    timeline_end = 0.0
    tolerance = 0.05

    for idx, cut in enumerate(edit_decisions.get("cuts", []) or []):
        cut_id = cut.get("id", f"cut-{idx}")
        try:
            in_seconds = float(cut.get("in_seconds"))
            out_seconds = float(cut.get("out_seconds"))
        except (TypeError, ValueError):
            continue

        if idx == 0 and abs(in_seconds) > tolerance:
            raise jsonschema.ValidationError(
                "ad-video edit_decisions timeline must start at 0.0; "
                f"cut {cut_id!r} starts at {in_seconds:.3f}"
            )

        if previous_end is not None:
            if in_seconds < previous_end - tolerance:
                raise jsonschema.ValidationError(
                    "ad-video edit_decisions cut "
                    f"{cut_id!r} overlaps previous cut; in_seconds must equal "
                    "the previous cut out_seconds"
                )
            if in_seconds > previous_end + tolerance:
                raise jsonschema.ValidationError(
                    "ad-video edit_decisions has a timeline gap before cut "
                    f"{cut_id!r}; align in_seconds to the previous cut "
                    "out_seconds"
                )

        previous_end = out_seconds
        timeline_end = out_seconds

    if previous_end is None:
        return

    total_duration = edit_decisions.get("total_duration_seconds")
    if total_duration is not None and abs(float(total_duration) - timeline_end) > 0.5:
        raise jsonschema.ValidationError(
            "ad-video edit_decisions total_duration_seconds must match the "
            "final cut out_seconds within +/-0.5s"
        )

    if scene_plan is not None:
        _, scene_total = _scene_plan_windows(scene_plan)
        if scene_total is not None and abs(scene_total - timeline_end) > 0.5:
            raise jsonschema.ValidationError(
                "ad-video edit_decisions final cut out_seconds must match "
                "scene_plan total_duration_seconds within +/-0.5s"
            )
        _validate_ad_video_narration_segments_fit_scene_plan(
            edit_decisions,
            scene_plan,
        )


def _validate_ad_video_edit_decisions(
    data: dict[str, Any],
    related_artifacts: dict[str, Any] | None = None,
) -> None:
    """Enforce ad-video edit decisions that carry emotional rhythm to render."""
    audio = data.get("audio")
    music = audio.get("music") if isinstance(audio, dict) else None
    schedule = music.get("volume_schedule") if isinstance(music, dict) else None
    music_strategy = data.get("music_strategy")
    if not isinstance(music_strategy, str) or not music_strategy.strip():
        raise jsonschema.ValidationError(
            "ad-video edit_decisions.music_strategy is required"
        )
    if music_strategy != "none" and (not isinstance(schedule, list) or not schedule):
        raise jsonschema.ValidationError(
            "ad-video edit_decisions.audio.music.volume_schedule is required"
        )

    seen_cut_ids: set[str] = set()
    total_cut_duration = 0.0
    for idx, cut in enumerate(data.get("cuts", []) or []):
        cut_id = cut.get("id", f"cut-{idx}")
        if cut_id in seen_cut_ids:
            raise jsonschema.ValidationError(
                "ad-video edit_decisions contains duplicate cut id "
                f"{cut_id!r}; cut ids must be unique for render diagnostics"
            )
        seen_cut_ids.add(cut_id)

        in_seconds = float(cut.get("in_seconds"))
        out_seconds = float(cut.get("out_seconds"))
        if out_seconds <= in_seconds:
            raise jsonschema.ValidationError(
                "ad-video edit_decisions cut "
                f"{cut_id!r} out_seconds must be greater than in_seconds"
            )
        total_cut_duration += out_seconds - in_seconds

        if not any(
            isinstance(cut.get(field), str) and cut[field].strip()
            for field in ("maps_to_beat", "beat_id", "beat")
        ):
            raise jsonschema.ValidationError(
                "ad-video edit_decisions cut "
                f"{cut_id!r} must include a beat label "
                "(maps_to_beat, beat_id, or beat)"
            )

    if music_strategy != "none":
        music_asset_id = music.get("asset_id") if isinstance(music, dict) else None
        if not isinstance(music_asset_id, str) or not music_asset_id.strip():
            raise jsonschema.ValidationError(
                "ad-video edit_decisions.audio.music.asset_id is required "
                "when music_strategy is not 'none'"
            )

    subtitles = data.get("subtitles")
    if isinstance(subtitles, dict) and subtitles.get("enabled") is True:
        subtitle_source = subtitles.get("source")
        if not isinstance(subtitle_source, str) or not subtitle_source.strip():
            raise jsonschema.ValidationError(
                "ad-video edit_decisions.subtitles.source is required when "
                "subtitles.enabled is true"
            )
        suffix = Path(subtitle_source).suffix.lower()
        if suffix and suffix != ".ass":
            raise jsonschema.ValidationError(
                "ad-video edit_decisions.subtitles.source must be an ASS "
                "subtitle path or an asset_manifest subtitle asset id"
            )

    scene_plan = (
        related_artifacts.get("scene_plan")
        if isinstance(related_artifacts, dict)
        else None
    )
    _validate_ad_video_edit_timeline(
        data,
        scene_plan if isinstance(scene_plan, dict) else None,
    )

    total_duration = data.get("total_duration_seconds")
    if total_duration is not None and abs(float(total_duration) - total_cut_duration) > 0.5:
        raise jsonschema.ValidationError(
            "ad-video edit_decisions total_duration_seconds must match summed "
            "cut duration within +/-0.5s"
        )

    if isinstance(related_artifacts, dict):
        production_proposal = related_artifacts.get("production_proposal")
        if isinstance(production_proposal, dict):
            decision_log = related_artifacts.get("decision_log")
            _validate_ad_video_edit_matches_production_proposal(
                data,
                production_proposal,
                decision_log if isinstance(decision_log, dict) else None,
                scene_plan if isinstance(scene_plan, dict) else None,
            )
        asset_manifest = related_artifacts.get("asset_manifest")
        if isinstance(asset_manifest, dict):
            _validate_ad_video_edit_matches_asset_manifest(data, asset_manifest)


def _validate_ad_video_asset_manifest(data: dict[str, Any]) -> None:
    """Enforce ad-video asset manifest conventions."""
    subtitle_file = data.get("subtitle_file")
    if isinstance(subtitle_file, str) and subtitle_file.strip():
        if not subtitle_file.lower().endswith(".ass"):
            raise jsonschema.ValidationError(
                "ad-video asset_manifest.subtitle_file must be an ASS subtitle path"
            )

    assets = data.get("assets", []) or []
    seen_asset_ids: set[str] = set()
    source_tools: set[str] = set()
    for idx, asset in enumerate(assets):
        asset_id = asset.get("id", f"asset-{idx}")
        if asset_id in seen_asset_ids:
            raise jsonschema.ValidationError(
                "ad-video asset_manifest contains duplicate asset id "
                f"{asset_id!r}; asset ids must be unique because edit and "
                "review artifacts reference them"
            )
        seen_asset_ids.add(asset_id)

        source_tool = asset.get("source_tool")
        if isinstance(source_tool, str) and source_tool.strip():
            source_tools.add(source_tool.strip())

        if asset.get("type") != "subtitle":
            continue
        path = asset.get("path")
        if not isinstance(path, str) or not path.lower().endswith(".ass"):
            raise jsonschema.ValidationError(
                "ad-video subtitle assets must use ASS paths; "
                f"assets[{idx}].path={path!r}"
            )

    if not assets:
        return

    costs = data.get("costs")
    if not isinstance(costs, list) or not costs:
        raise jsonschema.ValidationError(
            "ad-video asset_manifest.costs must be a non-empty per-tool cost log"
        )

    total_cost = data.get("total_cost_usd")
    if not isinstance(total_cost, (int, float)):
        raise jsonschema.ValidationError(
            "ad-video asset_manifest.total_cost_usd must be present when costs are logged"
        )

    cost_tools: set[str] = set()
    summed_cost = 0.0
    for idx, entry in enumerate(costs):
        tool = entry.get("tool")
        if isinstance(tool, str) and tool.strip():
            cost_tools.add(tool.strip())
        try:
            summed_cost += float(entry.get("cost_usd", 0.0))
        except (TypeError, ValueError) as exc:
            raise jsonschema.ValidationError(
                "ad-video asset_manifest.costs"
                f"[{idx}].cost_usd must be numeric"
            ) from exc

    if abs(float(total_cost) - summed_cost) > 0.005:
        raise jsonschema.ValidationError(
            "ad-video asset_manifest.total_cost_usd must equal the sum of "
            f"costs[].cost_usd ({summed_cost:.4f})"
        )

    missing_cost_tools = sorted(source_tools - cost_tools)
    if missing_cost_tools:
        raise jsonschema.ValidationError(
            "ad-video asset_manifest.costs must include an entry for each "
            "asset source_tool; missing "
            + ", ".join(repr(tool) for tool in missing_cost_tools)
        )


def _validate_ad_video_publish_matches_render_report(
    publish_log: dict[str, Any],
    render_report: dict[str, Any],
) -> None:
    """Enforce publish inventory consistency against rendered outputs."""
    outputs = render_report.get("outputs")
    if not isinstance(outputs, list) or not outputs:
        return

    output_by_path: dict[str, dict[str, Any]] = {}
    output_by_variant: dict[str, dict[str, Any]] = {}
    for output in outputs:
        if not isinstance(output, dict):
            continue
        path = output.get("path")
        variant = output.get("variant")
        if isinstance(path, str) and path.strip():
            output_by_path[path.strip()] = output
        if isinstance(variant, str) and variant.strip():
            output_by_variant[variant.strip()] = output

    matrix = publish_log.get("output_file_matrix")
    if not isinstance(matrix, list):
        return

    matrix_files = {
        entry.get("file").strip()
        for entry in matrix
        if isinstance(entry, dict)
        and isinstance(entry.get("file"), str)
        and entry.get("file").strip()
    }
    matrix_variants = {
        entry.get("variant").strip()
        for entry in matrix
        if isinstance(entry, dict)
        and isinstance(entry.get("variant"), str)
        and entry.get("variant").strip()
    }

    output_files = set(output_by_path)
    missing_files = sorted(output_files - matrix_files)
    if missing_files:
        raise jsonschema.ValidationError(
            "ad-video publish_log.output_file_matrix missing rendered output "
            "file(s) from render_report.outputs: "
            + ", ".join(repr(path) for path in missing_files)
        )

    extra_files = sorted(matrix_files - output_files)
    if extra_files:
        raise jsonschema.ValidationError(
            "ad-video publish_log.output_file_matrix contains file(s) not "
            "present in render_report.outputs: "
            + ", ".join(repr(path) for path in extra_files)
        )

    output_variants = set(output_by_variant)
    missing_variants = sorted(output_variants - matrix_variants)
    if missing_variants:
        raise jsonschema.ValidationError(
            "ad-video publish_log.output_file_matrix missing rendered output "
            "variant(s) from render_report.outputs: "
            + ", ".join(repr(variant) for variant in missing_variants)
        )

    extra_variants = sorted(matrix_variants - output_variants)
    if extra_variants:
        raise jsonschema.ValidationError(
            "ad-video publish_log.output_file_matrix contains variant(s) not "
            "present in render_report.outputs: "
            + ", ".join(repr(variant) for variant in extra_variants)
        )

    for idx, entry in enumerate(matrix):
        if not isinstance(entry, dict):
            continue
        file_path = entry.get("file")
        if not isinstance(file_path, str):
            continue
        output = output_by_path.get(file_path.strip())
        if not isinstance(output, dict):
            continue

        matrix_variant = entry.get("variant")
        output_variant = output.get("variant")
        if (
            isinstance(matrix_variant, str)
            and isinstance(output_variant, str)
            and matrix_variant.strip() != output_variant.strip()
        ):
            raise jsonschema.ValidationError(
                "ad-video publish_log.output_file_matrix"
                f"[{idx}].variant must match render_report.outputs for "
                f"{file_path!r}"
            )

        matrix_duration = entry.get("duration_seconds")
        output_duration = output.get("duration_seconds")
        if isinstance(matrix_duration, (int, float)) and isinstance(
            output_duration, (int, float)
        ):
            if abs(float(matrix_duration) - float(output_duration)) > 0.05:
                raise jsonschema.ValidationError(
                    "ad-video publish_log.output_file_matrix"
                    f"[{idx}].duration_seconds must match render_report.outputs "
                    f"for {file_path!r}"
                )

    entries = publish_log.get("entries")
    if isinstance(entries, list):
        for idx, entry in enumerate(entries):
            if not isinstance(entry, dict):
                continue
            export_path = entry.get("export_path")
            if (
                isinstance(export_path, str)
                and export_path.strip()
                and export_path.strip() not in output_files
            ):
                raise jsonschema.ValidationError(
                    "ad-video publish_log.entries"
                    f"[{idx}].export_path must be present in render_report.outputs"
                )

    total_files = publish_log.get("total_files_rendered")
    if total_files is not None and total_files != len(output_files):
        raise jsonschema.ValidationError(
            "ad-video publish_log.total_files_rendered must equal the number "
            "of render_report.outputs"
        )


def _validate_ad_video_publish_log(
    data: dict[str, Any],
    related_artifacts: dict[str, Any] | None = None,
) -> None:
    """Enforce ad-video publish inventory completeness."""
    matrix = data.get("output_file_matrix")
    if not isinstance(matrix, list) or not matrix:
        raise jsonschema.ValidationError(
            "ad-video publish_log.output_file_matrix must be non-empty"
        )

    required_metadata = ["title", "description", "tags", "cta_url"]
    seen_variants: set[str] = set()
    seen_files: set[str] = set()
    for idx, entry in enumerate(matrix):
        if not isinstance(entry, dict):
            raise jsonschema.ValidationError(
                f"ad-video publish_log.output_file_matrix[{idx}] must be an object"
            )

        for field in ("file", "variant", "thumbnail_concept"):
            value = entry.get(field)
            if not isinstance(value, str) or not value.strip():
                raise jsonschema.ValidationError(
                    "ad-video publish_log.output_file_matrix"
                    f"[{idx}].{field} must be non-empty"
                )

        variant = entry.get("variant")
        if variant in seen_variants:
            raise jsonschema.ValidationError(
                "ad-video publish_log.output_file_matrix contains duplicate "
                f"output variant {variant!r}"
            )
        seen_variants.add(variant)

        file_path = entry.get("file")
        if file_path in seen_files:
            raise jsonschema.ValidationError(
                "ad-video publish_log.output_file_matrix contains duplicate "
                f"output file {file_path!r}"
            )
        seen_files.add(file_path)

        duration = entry.get("duration_seconds")
        if not isinstance(duration, (int, float)) or duration <= 0:
            raise jsonschema.ValidationError(
                "ad-video publish_log.output_file_matrix"
                f"[{idx}].duration_seconds must be > 0"
            )

        platforms = entry.get("target_platforms")
        if not isinstance(platforms, list) or not platforms or not all(
            isinstance(platform, str) and platform.strip() for platform in platforms
        ):
            raise jsonschema.ValidationError(
                "ad-video publish_log.output_file_matrix"
                f"[{idx}].target_platforms must contain at least one platform"
            )

        metadata = entry.get("metadata")
        if not isinstance(metadata, dict):
            raise jsonschema.ValidationError(
                "ad-video publish_log.output_file_matrix"
                f"[{idx}].metadata is required"
            )
        missing = [
            field
            for field in required_metadata
            if field not in metadata
        ]
        if missing:
            raise jsonschema.ValidationError(
                "ad-video publish_log.output_file_matrix"
                f"[{idx}].metadata missing fields: {missing}"
            )
        for field in ("title", "description", "cta_url"):
            value = metadata.get(field)
            if not isinstance(value, str) or not value.strip():
                raise jsonschema.ValidationError(
                    "ad-video publish_log.output_file_matrix"
                    f"[{idx}].metadata.{field} must be non-empty"
                )
        tags = metadata.get("tags")
        if not isinstance(tags, list) or not tags or not all(
            isinstance(tag, str) and tag.strip() for tag in tags
        ):
            raise jsonschema.ValidationError(
                "ad-video publish_log.output_file_matrix"
                f"[{idx}].metadata.tags must contain at least one tag"
            )

    if isinstance(related_artifacts, dict):
        render_report = related_artifacts.get("render_report")
        if isinstance(render_report, dict):
            _validate_ad_video_publish_matches_render_report(data, render_report)


def _ad_video_parse_resolution(resolution: Any) -> tuple[int, int] | None:
    if not isinstance(resolution, str) or not resolution.strip():
        return None
    normalized = resolution.strip().lower().replace("\u00d7", "x")
    parts = normalized.split("x", maxsplit=1)
    if len(parts) != 2:
        return None
    try:
        width = int(parts[0])
        height = int(parts[1])
    except ValueError:
        return None
    if width <= 0 or height <= 0:
        return None
    return width, height


def _validate_ad_video_render_output_variant_semantics(
    output: dict[str, Any],
    idx: int,
) -> None:
    variant = output.get("variant")
    if not isinstance(variant, str) or not variant.strip():
        return
    variant = variant.strip()

    expected_ratios = {
        "16:9": 16 / 9,
        "9:16": 9 / 16,
        "1:1": 1.0,
    }
    for token, expected_ratio in expected_ratios.items():
        if token not in variant:
            continue
        resolution = _ad_video_parse_resolution(output.get("resolution"))
        if resolution is None:
            raise jsonschema.ValidationError(
                "ad-video render_report.outputs"
                f"[{idx}].resolution must be parseable as WIDTHxHEIGHT for "
                f"variant {variant!r}"
            )
        width, height = resolution
        actual_ratio = width / height
        if abs(actual_ratio - expected_ratio) > 0.03:
            raise jsonschema.ValidationError(
                "ad-video render_report.outputs"
                f"[{idx}].resolution {width}x{height} does not match "
                f"variant {variant!r}"
            )
        break

    if _ad_video_derivative_needs_short_scene_selection(variant):
        duration = output.get("duration_seconds")
        if isinstance(duration, (int, float)) and float(duration) > 15.05:
            raise jsonschema.ValidationError(
                "ad-video render_report.outputs"
                f"[{idx}].duration_seconds must be <=15s for "
                f"variant {variant!r}"
            )


def _validate_ad_video_render_report(
    data: dict[str, Any],
    related_artifacts: dict[str, Any] | None = None,
) -> None:
    """Enforce ad-video render verification fields before publish."""
    renderer = data.get("renderer")
    if not isinstance(renderer, str) or not renderer.strip():
        raise jsonschema.ValidationError("ad-video render_report.renderer is required")

    outputs = data.get("outputs") or []
    probe_results = data.get("probe_results")
    if not isinstance(probe_results, dict) or not probe_results:
        raise jsonschema.ValidationError(
            "ad-video render_report.probe_results is required"
        )

    seen_variants: set[str] = set()
    seen_paths: set[str] = set()
    for idx, output in enumerate(outputs):
        path = output.get("path")
        if not isinstance(path, str) or not path.strip():
            raise jsonschema.ValidationError(
                f"ad-video render_report.outputs[{idx}].path must be non-empty"
            )
        if path in seen_paths:
            raise jsonschema.ValidationError(
                "ad-video render_report.outputs contains duplicate output "
                f"path {path!r}"
            )
        seen_paths.add(path)

        duration = output.get("duration_seconds")
        if not isinstance(duration, (int, float)) or duration <= 0:
            raise jsonschema.ValidationError(
                "ad-video render_report.outputs"
                f"[{idx}].duration_seconds must be > 0"
            )

        variant = output.get("variant")
        if not isinstance(variant, str) or not variant.strip():
            raise jsonschema.ValidationError(
                f"ad-video render_report.outputs[{idx}].variant is required"
            )
        if variant in seen_variants:
            raise jsonschema.ValidationError(
                "ad-video render_report.outputs contains duplicate output "
                f"variant {variant!r}"
            )
        seen_variants.add(variant)

        if output.get("audio_channels") != 2:
            raise jsonschema.ValidationError(
                "ad-video render_report.outputs"
                f"[{idx}].audio_channels must be 2 for stereo output"
            )
        _validate_ad_video_render_output_variant_semantics(output, idx)

        variant_probe = probe_results.get(variant)
        if not isinstance(variant_probe, dict):
            raise jsonschema.ValidationError(
                f"ad-video render_report.probe_results missing variant {variant!r}"
            )
        required_checks = ("duration_check", "resolution_check", "audio_check")
        missing_checks = [
            check_name
            for check_name in required_checks
            if variant_probe.get(check_name) != "PASS"
        ]
        if missing_checks:
            raise jsonschema.ValidationError(
                "ad-video render_report.probe_results"
                f"[{variant!r}] missing PASS checks: {missing_checks}"
            )
        failed_checks = {
            name: value
            for name, value in variant_probe.items()
            if value != "PASS"
        }
        if failed_checks:
            raise jsonschema.ValidationError(
                "ad-video render_report.probe_results must be PASS for "
                f"variant {variant!r}; got {failed_checks}"
            )

    if not isinstance(related_artifacts, dict):
        return

    output_variants = {
        output.get("variant").strip()
        for output in outputs
        if isinstance(output, dict)
        and isinstance(output.get("variant"), str)
        and output.get("variant").strip()
    }

    production_proposal = related_artifacts.get("production_proposal")
    if isinstance(production_proposal, dict):
        edit_decisions = related_artifacts.get("edit_decisions")
        decision_log = related_artifacts.get("decision_log")
        expected_runtime = _ad_video_effective_edit_value(
            production_proposal=production_proposal,
            edit_decisions=edit_decisions if isinstance(edit_decisions, dict) else None,
            decision_log=decision_log if isinstance(decision_log, dict) else None,
            proposal_field="render_runtime",
            decision_category="render_runtime_selection",
        )
        if (
            isinstance(expected_runtime, str)
            and expected_runtime.strip()
            and renderer.strip().lower() != expected_runtime.strip().lower()
        ):
            raise jsonschema.ValidationError(
                "ad-video render_report.renderer must match "
                "the approved render_runtime"
            )

        expected_derivatives = {
            variant.strip()
            for variant in production_proposal.get("derivatives_added") or []
            if isinstance(variant, str) and variant.strip()
        }
        missing_derivatives = sorted(expected_derivatives - output_variants)
        if missing_derivatives:
            raise jsonschema.ValidationError(
                "ad-video render_report.outputs must include every "
                "production_proposal.derivatives_added variant; missing "
                + ", ".join(repr(variant) for variant in missing_derivatives)
            )

    production_bible = related_artifacts.get("production_bible")
    primary = (
        ((production_bible.get("deliverables") or {}).get("primary") or {})
        if isinstance(production_bible, dict)
        else {}
    )
    primary_aspect_ratio = primary.get("aspect_ratio") if isinstance(primary, dict) else None
    if (
        isinstance(primary_aspect_ratio, str)
        and primary_aspect_ratio.strip()
        and primary_aspect_ratio.strip() not in output_variants
    ):
        raise jsonschema.ValidationError(
            "ad-video render_report.outputs must include the primary "
            "production_bible.deliverables.primary.aspect_ratio "
            f"{primary_aspect_ratio!r}"
        )


def _validate_ad_video_final_review_matches_render_report(
    final_review: dict[str, Any],
    render_report: dict[str, Any],
) -> None:
    """Ensure a passing final review inspects the rendered output it claims."""
    output_path = final_review.get("output_path")
    if not isinstance(output_path, str) or not output_path.strip():
        raise jsonschema.ValidationError(
            "ad-video final_review.output_path must be non-empty when status is pass"
        )
    output_path = output_path.strip()

    outputs = render_report.get("outputs")
    if not isinstance(outputs, list) or not outputs:
        return

    output_by_path = {
        output.get("path").strip(): output
        for output in outputs
        if isinstance(output, dict)
        and isinstance(output.get("path"), str)
        and output.get("path").strip()
    }
    rendered_output = output_by_path.get(output_path)
    if not isinstance(rendered_output, dict):
        raise jsonschema.ValidationError(
            "ad-video final_review.output_path must be present in "
            "render_report.outputs"
        )

    reviewed_outputs = final_review.get("reviewed_outputs")
    if len(output_by_path) > 1 and not isinstance(reviewed_outputs, list):
        raise jsonschema.ValidationError(
            "ad-video final_review.reviewed_outputs is required when "
            "render_report.outputs contains derivative outputs"
        )

    if isinstance(reviewed_outputs, list):
        reviewed_paths: set[str] = set()
        reviewed_variants: set[str] = set()
        for idx, reviewed in enumerate(reviewed_outputs):
            if not isinstance(reviewed, dict):
                raise jsonschema.ValidationError(
                    f"ad-video final_review.reviewed_outputs[{idx}] "
                    "must be an object"
                )

            reviewed_path = reviewed.get("path")
            if not isinstance(reviewed_path, str) or not reviewed_path.strip():
                raise jsonschema.ValidationError(
                    f"ad-video final_review.reviewed_outputs[{idx}].path "
                    "must be non-empty"
                )
            reviewed_path = reviewed_path.strip()
            if reviewed_path in reviewed_paths:
                raise jsonschema.ValidationError(
                    "ad-video final_review.reviewed_outputs contains duplicate "
                    f"path {reviewed_path!r}"
                )
            reviewed_paths.add(reviewed_path)

            rendered = output_by_path.get(reviewed_path)
            if not isinstance(rendered, dict):
                raise jsonschema.ValidationError(
                    "ad-video final_review.reviewed_outputs contains path not "
                    f"present in render_report.outputs: {reviewed_path!r}"
                )

            reviewed_variant = reviewed.get("variant")
            rendered_variant = rendered.get("variant")
            if not isinstance(reviewed_variant, str) or not reviewed_variant.strip():
                raise jsonschema.ValidationError(
                    f"ad-video final_review.reviewed_outputs[{idx}].variant "
                    "must be non-empty"
                )
            reviewed_variants.add(reviewed_variant.strip())
            if (
                isinstance(rendered_variant, str)
                and rendered_variant.strip()
                and reviewed_variant.strip() != rendered_variant.strip()
            ):
                raise jsonschema.ValidationError(
                    "ad-video final_review.reviewed_outputs"
                    f"[{idx}].variant must match render_report.outputs for "
                    f"{reviewed_path!r}"
                )

            review_duration = reviewed.get("duration_seconds")
            output_duration = rendered.get("duration_seconds")
            if isinstance(review_duration, (int, float)) and isinstance(
                output_duration, (int, float)
            ):
                if abs(float(review_duration) - float(output_duration)) > 0.1:
                    raise jsonschema.ValidationError(
                        "ad-video final_review.reviewed_outputs"
                        f"[{idx}].duration_seconds must match "
                        f"render_report.outputs for {reviewed_path!r}"
                    )

            review_resolution = reviewed.get("resolution")
            output_resolution = rendered.get("resolution")
            if (
                isinstance(review_resolution, str)
                and isinstance(output_resolution, str)
                and review_resolution.strip() != output_resolution.strip()
            ):
                raise jsonschema.ValidationError(
                    "ad-video final_review.reviewed_outputs"
                    f"[{idx}].resolution must match render_report.outputs for "
                    f"{reviewed_path!r}"
                )

            issues = reviewed.get("issues")
            if isinstance(issues, list) and issues:
                raise jsonschema.ValidationError(
                    "ad-video final_review.reviewed_outputs"
                    f"[{idx}].issues must be empty when status is pass"
                )

        missing_paths = sorted(set(output_by_path) - reviewed_paths)
        if missing_paths:
            raise jsonschema.ValidationError(
                "ad-video final_review.reviewed_outputs missing rendered "
                "output file(s): "
                + ", ".join(repr(path) for path in missing_paths)
            )

        output_variants = {
            output.get("variant").strip()
            for output in output_by_path.values()
            if isinstance(output.get("variant"), str)
            and output.get("variant").strip()
        }
        missing_variants = sorted(output_variants - reviewed_variants)
        if missing_variants:
            raise jsonschema.ValidationError(
                "ad-video final_review.reviewed_outputs missing rendered "
                "variant(s): "
                + ", ".join(repr(variant) for variant in missing_variants)
            )

    technical_probe = (final_review.get("checks") or {}).get("technical_probe")
    if isinstance(technical_probe, dict):
        review_duration = technical_probe.get("duration_seconds")
        output_duration = rendered_output.get("duration_seconds")
        if isinstance(review_duration, (int, float)) and isinstance(
            output_duration, (int, float)
        ):
            if abs(float(review_duration) - float(output_duration)) > 0.1:
                raise jsonschema.ValidationError(
                    "ad-video final_review.checks.technical_probe."
                    "duration_seconds must match render_report.outputs for "
                    f"{output_path!r}"
                )

        review_resolution = technical_probe.get("resolution")
        output_resolution = rendered_output.get("resolution")
        if (
            isinstance(review_resolution, str)
            and isinstance(output_resolution, str)
            and review_resolution.strip() != output_resolution.strip()
        ):
            raise jsonschema.ValidationError(
                "ad-video final_review.checks.technical_probe.resolution "
                f"must match render_report.outputs for {output_path!r}"
            )

    promise = (final_review.get("checks") or {}).get("promise_preservation")
    renderer = render_report.get("renderer")
    runtime_used = promise.get("render_runtime_used") if isinstance(promise, dict) else None
    if (
        isinstance(renderer, str)
        and renderer.strip()
        and isinstance(runtime_used, str)
        and runtime_used.strip()
        and runtime_used.strip().lower() != renderer.strip().lower()
    ):
        raise jsonschema.ValidationError(
            "ad-video final_review.checks.promise_preservation."
            "render_runtime_used must match render_report.renderer"
        )


def _validate_ad_video_final_review_matches_production_proposal(
    final_review: dict[str, Any],
    production_proposal: dict[str, Any],
    edit_decisions: dict[str, Any] | None = None,
    decision_log: dict[str, Any] | None = None,
) -> None:
    checks = (
        final_review.get("checks")
        if isinstance(final_review.get("checks"), dict)
        else {}
    )

    music_strategy = _ad_video_effective_edit_value(
        production_proposal=production_proposal,
        edit_decisions=edit_decisions,
        decision_log=decision_log,
        proposal_field="music_strategy",
        decision_category="music_strategy_selection",
    )
    audio_spotcheck = (
        checks.get("audio_spotcheck") if isinstance(checks, dict) else None
    )
    if isinstance(music_strategy, str) and isinstance(audio_spotcheck, dict):
        music_present = audio_spotcheck.get("music_present")
        if isinstance(music_present, bool):
            normalized_music_strategy = music_strategy.strip().lower()
            if normalized_music_strategy == "none" and music_present:
                raise jsonschema.ValidationError(
                    "ad-video final_review.checks.audio_spotcheck.music_present "
                    "must be false when approved music_strategy is 'none'"
                )
            if normalized_music_strategy != "none" and not music_present:
                raise jsonschema.ValidationError(
                    "ad-video final_review.checks.audio_spotcheck.music_present "
                    "must be true when approved music_strategy "
                    "is not 'none'"
                )

    subtitles = production_proposal.get("subtitles")
    if not isinstance(subtitles, dict):
        return

    mode = subtitles.get("mode")
    if mode not in {"off", "burnt-in", "sidecar"}:
        return

    subtitle_check = (
        checks.get("subtitle_check") if isinstance(checks, dict) else None
    )
    if not isinstance(subtitle_check, dict):
        return

    actual_expected = subtitle_check.get("subtitles_expected")
    if not isinstance(actual_expected, bool):
        return

    expected = mode != "off"
    if actual_expected is not expected:
        raise jsonschema.ValidationError(
            "ad-video final_review.checks.subtitle_check.subtitles_expected "
            "must match production_proposal.subtitles.mode"
        )

    subtitles_present = subtitle_check.get("subtitles_present")
    if not isinstance(subtitles_present, bool):
        return

    coverage_ratio = subtitle_check.get("coverage_ratio")
    if expected:
        return

    if subtitles_present:
        raise jsonschema.ValidationError(
            "ad-video final_review.checks.subtitle_check.subtitles_present "
            "must be false when production_proposal.subtitles.mode is 'off'"
        )
    if isinstance(coverage_ratio, (int, float)) and float(coverage_ratio) != 0:
        raise jsonschema.ValidationError(
            "ad-video final_review.checks.subtitle_check.coverage_ratio "
            "must be 0 when production_proposal.subtitles.mode is 'off'"
        )


def _validate_ad_video_final_review(
    data: dict[str, Any],
    related_artifacts: dict[str, Any] | None = None,
) -> None:
    """Enforce completeness for a passing ad-video post-render self-review."""
    if data.get("status") != "pass":
        return

    if data.get("recommended_action") != "present_to_user":
        raise jsonschema.ValidationError(
            "ad-video final_review.status='pass' requires "
            "recommended_action='present_to_user'"
        )

    checks = data.get("checks") or {}
    issues_found = data.get("issues_found")
    if isinstance(issues_found, list) and issues_found:
        raise jsonschema.ValidationError(
            "ad-video final_review.status='pass' requires issues_found to be empty"
        )

    def require_mapping(name: str) -> dict[str, Any]:
        value = checks.get(name)
        if not isinstance(value, dict):
            raise jsonschema.ValidationError(
                f"ad-video final_review.checks.{name} must be an object"
            )
        return value

    def require_no_check_issues(block: dict[str, Any], block_name: str) -> None:
        issues = block.get("issues")
        if isinstance(issues, list) and issues:
            raise jsonschema.ValidationError(
                f"ad-video final_review.checks.{block_name}.issues must be empty "
                "when status is pass"
            )

    def require_bool(block: dict[str, Any], block_name: str, field: str) -> bool:
        value = block.get(field)
        if not isinstance(value, bool):
            raise jsonschema.ValidationError(
                f"ad-video final_review.checks.{block_name}.{field} must be boolean"
            )
        return value

    def require_positive_number(
        block: dict[str, Any], block_name: str, field: str
    ) -> float:
        value = block.get(field)
        if not isinstance(value, (int, float)) or value <= 0:
            raise jsonschema.ValidationError(
                f"ad-video final_review.checks.{block_name}.{field} must be > 0"
            )
        return float(value)

    def require_non_empty_string(block: dict[str, Any], block_name: str, field: str) -> str:
        value = block.get(field)
        if not isinstance(value, str) or not value.strip():
            raise jsonschema.ValidationError(
                f"ad-video final_review.checks.{block_name}.{field} must be non-empty"
            )
        return value

    technical_probe = require_mapping("technical_probe")
    require_no_check_issues(technical_probe, "technical_probe")
    if require_bool(technical_probe, "technical_probe", "valid_container") is not True:
        raise jsonschema.ValidationError(
            "ad-video final_review.checks.technical_probe.valid_container "
            "must be true when status is pass"
        )
    require_positive_number(technical_probe, "technical_probe", "duration_seconds")
    require_non_empty_string(technical_probe, "technical_probe", "resolution")
    require_positive_number(technical_probe, "technical_probe", "fps")
    require_bool(technical_probe, "technical_probe", "has_audio")
    require_non_empty_string(technical_probe, "technical_probe", "codec")
    require_positive_number(technical_probe, "technical_probe", "file_size_bytes")

    visual_spotcheck = require_mapping("visual_spotcheck")
    require_no_check_issues(visual_spotcheck, "visual_spotcheck")
    frames_sampled = visual_spotcheck.get("frames_sampled")
    if not isinstance(frames_sampled, int) or frames_sampled < 4:
        raise jsonschema.ValidationError(
            "ad-video final_review.checks.visual_spotcheck.frames_sampled "
            "must be at least 4"
        )
    frame_paths = visual_spotcheck.get("frame_paths")
    if (
        not isinstance(frame_paths, list)
        or len(frame_paths) < 4
        or not all(isinstance(path, str) and path.strip() for path in frame_paths)
    ):
        raise jsonschema.ValidationError(
            "ad-video final_review.checks.visual_spotcheck.frame_paths "
            "must include at least four non-empty paths"
        )
    for field in (
        "black_frames_detected",
        "broken_overlays",
        "missing_assets",
        "unreadable_text",
    ):
        if require_bool(visual_spotcheck, "visual_spotcheck", field):
            raise jsonschema.ValidationError(
                f"ad-video final_review.checks.visual_spotcheck.{field} "
                "must be false when status is pass"
            )

    audio_spotcheck = require_mapping("audio_spotcheck")
    require_no_check_issues(audio_spotcheck, "audio_spotcheck")
    if require_bool(audio_spotcheck, "audio_spotcheck", "narration_present") is not True:
        raise jsonschema.ValidationError(
            "ad-video final_review.checks.audio_spotcheck.narration_present "
            "must be true when status is pass"
        )
    require_bool(audio_spotcheck, "audio_spotcheck", "music_present")
    if require_bool(audio_spotcheck, "audio_spotcheck", "unexpected_silence"):
        raise jsonschema.ValidationError(
            "ad-video final_review.checks.audio_spotcheck.unexpected_silence "
            "must be false when status is pass"
        )
    if require_bool(audio_spotcheck, "audio_spotcheck", "clipping_detected"):
        raise jsonschema.ValidationError(
            "ad-video final_review.checks.audio_spotcheck.clipping_detected "
            "must be false when status is pass"
        )
    if require_bool(audio_spotcheck, "audio_spotcheck", "mix_intelligible") is not True:
        raise jsonschema.ValidationError(
            "ad-video final_review.checks.audio_spotcheck.mix_intelligible "
            "must be true when status is pass"
        )

    promise = require_mapping("promise_preservation")
    require_no_check_issues(promise, "promise_preservation")
    if require_bool(promise, "promise_preservation", "delivery_promise_honored") is not True:
        raise jsonschema.ValidationError(
            "ad-video final_review.checks.promise_preservation."
            "delivery_promise_honored must be true when status is pass"
        )
    require_non_empty_string(promise, "promise_preservation", "renderer_family_used")
    require_non_empty_string(promise, "promise_preservation", "render_runtime_used")
    require_non_empty_string(promise, "promise_preservation", "runtime_swap_check")
    if "motion_ratio_actual" in promise:
        motion_ratio_actual = promise.get("motion_ratio_actual")
        if (
            not isinstance(motion_ratio_actual, (int, float))
            or not 0 <= float(motion_ratio_actual) <= 1
        ):
            raise jsonschema.ValidationError(
                "ad-video final_review.checks.promise_preservation."
                "motion_ratio_actual must be between 0 and 1"
            )
    if require_bool(promise, "promise_preservation", "runtime_swap_detected"):
        raise jsonschema.ValidationError(
            "ad-video final_review.checks.promise_preservation."
            "runtime_swap_detected must be false when status is pass"
        )
    if require_bool(promise, "promise_preservation", "silent_downgrade_detected"):
        raise jsonschema.ValidationError(
            "ad-video final_review.checks.promise_preservation."
            "silent_downgrade_detected must be false when status is pass"
        )

    subtitle_check = require_mapping("subtitle_check")
    require_no_check_issues(subtitle_check, "subtitle_check")
    subtitles_expected = require_bool(
        subtitle_check, "subtitle_check", "subtitles_expected"
    )
    subtitles_present = require_bool(subtitle_check, "subtitle_check", "subtitles_present")
    coverage_ratio = subtitle_check.get("coverage_ratio")
    if not isinstance(coverage_ratio, (int, float)):
        raise jsonschema.ValidationError(
            "ad-video final_review.checks.subtitle_check.coverage_ratio "
            "must be numeric"
        )
    if subtitles_expected and (not subtitles_present or float(coverage_ratio) < 0.95):
        raise jsonschema.ValidationError(
            "ad-video final_review.checks.subtitle_check coverage must be "
            "present and >= 0.95 when subtitles are expected"
        )
    if require_bool(subtitle_check, "subtitle_check", "timing_drift_detected"):
        raise jsonschema.ValidationError(
            "ad-video final_review.checks.subtitle_check.timing_drift_detected "
            "must be false when status is pass"
        )

    if isinstance(related_artifacts, dict):
        render_report = related_artifacts.get("render_report")
        if isinstance(render_report, dict):
            _validate_ad_video_final_review_matches_render_report(data, render_report)
        production_proposal = related_artifacts.get("production_proposal")
        if isinstance(production_proposal, dict):
            edit_decisions = related_artifacts.get("edit_decisions")
            decision_log = related_artifacts.get("decision_log")
            _validate_ad_video_final_review_matches_production_proposal(
                data,
                production_proposal,
                edit_decisions if isinstance(edit_decisions, dict) else None,
                decision_log if isinstance(decision_log, dict) else None,
            )


def _validate_decision_log(data: dict[str, Any]) -> None:
    """Enforce semantic decision-log invariants not expressible in JSON Schema."""
    seen_decision_ids: set[str] = set()
    for idx, decision in enumerate(data.get("decisions", []) or []):
        decision_id = decision.get("decision_id")
        if decision_id in seen_decision_ids:
            raise jsonschema.ValidationError(
                f"decision_log.decisions[{idx}] has duplicate decision_id "
                f"{decision_id!r}"
            )
        seen_decision_ids.add(decision_id)

        options = decision.get("options_considered") or []
        seen_option_ids: set[str] = set()
        for option_idx, option in enumerate(options):
            option_id = option.get("option_id") if isinstance(option, dict) else None
            if option_id in seen_option_ids:
                raise jsonschema.ValidationError(
                    "decision_log.decisions"
                    f"[{idx}].options_considered[{option_idx}] has duplicate "
                    f"option_id {option_id!r}"
                )
            seen_option_ids.add(option_id)

        option_ids = {
            option.get("option_id")
            for option in options
            if isinstance(option, dict)
        }
        selected = decision.get("selected")
        if selected not in option_ids:
            raise jsonschema.ValidationError(
                "decision_log.decisions"
                f"[{idx}].selected must match an options_considered option_id"
            )

        if decision.get("user_approved") is True and decision.get("user_visible") is not True:
            raise jsonschema.ValidationError(
                "decision_log.decisions"
                f"[{idx}] user_approved=true requires user_visible=true"
            )


def _is_ad_video_script(data: dict[str, Any], pipeline_type: str | None) -> bool:
    if pipeline_type == "ad-video":
        return True
    if pipeline_type is not None:
        return False
    if data.get("pipeline") == "ad-video":
        return True
    metadata = data.get("metadata") or {}
    if isinstance(metadata, dict) and metadata.get("pipeline") == "ad-video":
        return True
    return data.get("style_mode") in {"animated", "cinematic"}


def _is_ad_video_scene_plan(pipeline_type: str | None) -> bool:
    return pipeline_type == "ad-video"


def _is_ad_video_enriched_brief(pipeline_type: str | None) -> bool:
    return pipeline_type == "ad-video"


def _is_ad_video_production_proposal(pipeline_type: str | None) -> bool:
    return pipeline_type == "ad-video"


def _is_ad_video_production_bible(data: dict[str, Any], pipeline_type: str | None) -> bool:
    return pipeline_type == "ad-video" or data.get("pipeline") == "ad-video"


def _is_ad_video_edit_decisions(pipeline_type: str | None) -> bool:
    return pipeline_type == "ad-video"


def _is_ad_video_asset_manifest(pipeline_type: str | None) -> bool:
    return pipeline_type == "ad-video"


def _is_ad_video_publish_log(data: dict[str, Any], pipeline_type: str | None) -> bool:
    return pipeline_type == "ad-video" or data.get("pipeline") == "ad-video"


def _is_ad_video_render_report(pipeline_type: str | None) -> bool:
    return pipeline_type == "ad-video"


def _is_ad_video_final_review(pipeline_type: str | None) -> bool:
    return pipeline_type == "ad-video"


def validate_artifact(
    name: str,
    data: dict[str, Any],
    *,
    pipeline_type: str | None = None,
    related_artifacts: dict[str, Any] | None = None,
) -> None:
    """Validate artifact data against its schema. Raises on failure."""
    schema = load_schema(name)
    jsonschema.validate(instance=data, schema=schema)
    if name == "enriched_brief" and _is_ad_video_enriched_brief(pipeline_type):
        _validate_ad_video_enriched_brief(data)
    if name == "intelligence_brief":
        _validate_intelligence_brief(data)
    if name == "production_proposal" and _is_ad_video_production_proposal(pipeline_type):
        _validate_ad_video_production_proposal(data)
    if name == "idea_options":
        _validate_idea_options(data)
    if name == "production_bible" and _is_ad_video_production_bible(data, pipeline_type):
        _validate_ad_video_production_bible(data)
    if name == "script" and _is_ad_video_script(data, pipeline_type):
        _validate_ad_video_script(data)
    if name == "scene_plan" and _is_ad_video_scene_plan(pipeline_type):
        _validate_ad_video_scene_plan(data)
    if name == "edit_decisions" and _is_ad_video_edit_decisions(pipeline_type):
        _validate_ad_video_edit_decisions(data, related_artifacts=related_artifacts)
    if name == "asset_manifest" and _is_ad_video_asset_manifest(pipeline_type):
        _validate_ad_video_asset_manifest(data)
    if name == "publish_log" and _is_ad_video_publish_log(data, pipeline_type):
        _validate_ad_video_publish_log(data, related_artifacts=related_artifacts)
    if name == "render_report" and _is_ad_video_render_report(pipeline_type):
        _validate_ad_video_render_report(data, related_artifacts=related_artifacts)
    if name == "final_review" and _is_ad_video_final_review(pipeline_type):
        _validate_ad_video_final_review(data, related_artifacts=related_artifacts)
    if name == "decision_log":
        _validate_decision_log(data)


def list_schemas() -> list[str]:
    """List all available artifact schema names."""
    return [p.stem.replace(".schema", "") for p in SCHEMA_DIR.glob("*.schema.json")]
