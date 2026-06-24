"""Validate ad-video planning artifacts before asset generation or render."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from lib.conflict_detection import check_trend_knowledge_conflicts
from lib.knowledge_alignment import check_ad_video_planning_knowledge_alignment
from lib.trend_alignment import check_ad_video_planning_trend_alignment
from schemas.artifacts import load_strict_json_object, validate_artifact
from tools.base_tool import (
    BaseTool,
    Determinism,
    ExecutionMode,
    ResourceProfile,
    ToolResult,
    ToolRuntime,
    ToolStability,
    ToolTier,
)


class AdVideoPlanningChainCheck(BaseTool):
    name = "ad_video_planning_chain_check"
    version = "0.2.0"
    tier = ToolTier.CORE
    capability = "validation"
    provider = "video_production_buddy"
    stability = ToolStability.PRODUCTION
    execution_mode = ExecutionMode.SYNC
    determinism = Determinism.DETERMINISTIC
    runtime = ToolRuntime.LOCAL
    resource_profile = ResourceProfile(cpu_cores=1, ram_mb=128, disk_mb=1, network_required=False)
    idempotency_key_fields = [
        "production_bible",
        "script",
        "scene_plan",
        "production_bible_path",
        "script_path",
        "scene_plan_path",
    ]

    capabilities = [
        "validate_ad_video_planning_chain",
        "validate_trend_alignment_threading",
        "validate_knowledge_alignment_threading",
        "validate_trend_knowledge_conflicts",
        "validate_cross_domain_co_presence",
        "validate_pre_asset_gate",
    ]
    best_for = [
        "blocking ad-video asset generation when selected trend guidance is not threaded",
        "detecting stale planning artifacts before render",
        "catching trend-knowledge conflicts before asset generation",
    ]
    not_good_for = [
        "evaluating visual quality of rendered clips",
        "discovering live social trends",
    ]

    input_schema = {
        "type": "object",
        "properties": {
            "production_bible": {"type": "object"},
            "script": {"type": "object"},
            "scene_plan": {"type": "object"},
            "production_bible_path": {"type": "string"},
            "script_path": {"type": "string"},
            "scene_plan_path": {"type": "string"},
        },
        "anyOf": [
            {"required": ["production_bible", "script", "scene_plan"]},
            {"required": ["production_bible_path", "script_path", "scene_plan_path"]},
        ],
    }
    output_schema = {
        "type": "object",
        "required": ["trend_alignment", "knowledge_alignment"],
        "properties": {
            "trend_alignment": {"type": "object"},
            "knowledge_alignment": {"type": "object"},
            "conflict_detection": {"type": "object"},
        },
    }
    user_visible_verification = [
        "Confirm selected trend refs appear in required script sections",
        "Confirm visual/pacing trends appear in scene_plan trend refs and notes",
        "Confirm no trend-knowledge conflicts detected",
    ]

    def _load_artifact(self, inputs: dict[str, Any], key: str) -> dict[str, Any]:
        value = inputs.get(key)
        if isinstance(value, dict):
            return value

        path_value = inputs.get(f"{key}_path")
        if not isinstance(path_value, str) or not path_value.strip():
            raise ValueError(f"Missing {key} or {key}_path")
        loaded = load_strict_json_object(Path(path_value), context=f"{key}_path")
        if not isinstance(loaded, dict):
            raise ValueError(f"{key}_path must contain a JSON object")
        return loaded

    def execute(self, inputs: dict[str, Any]) -> ToolResult:
        started = time.time()
        try:
            production_bible = self._load_artifact(inputs, "production_bible")
            script = self._load_artifact(inputs, "script")
            scene_plan = self._load_artifact(inputs, "scene_plan")

            validate_artifact("production_bible", production_bible, pipeline_type="ad-video")
            validate_artifact("script", script, pipeline_type="ad-video")
            validate_artifact("scene_plan", scene_plan, pipeline_type="ad-video")

            report = check_ad_video_planning_trend_alignment(
                production_bible,
                script,
                scene_plan,
            )
            knowledge_report = check_ad_video_planning_knowledge_alignment(
                production_bible,
                script,
                scene_plan,
            )

            # Conflict detection: cross-check trends against knowledge cards.
            conflict_report = self._check_conflicts(production_bible)

            issues: list[dict[str, Any]] = []
            issues.extend(report.get("issues", []))
            issues.extend(knowledge_report.get("issues", []))
            issues.extend(conflict_report.get("conflicts", []))

            data = {
                "trend_alignment": report,
                "knowledge_alignment": knowledge_report,
                "conflict_detection": conflict_report,
            }

            if not report["ok"] or not knowledge_report["ok"] or not conflict_report["ok"]:
                return ToolResult(
                    success=False,
                    data=data,
                    error=json.dumps(issues, sort_keys=True, allow_nan=False),
                    duration_seconds=time.time() - started,
                )
            return ToolResult(
                success=True,
                data=data,
                duration_seconds=time.time() - started,
            )
        except Exception as exc:
            return ToolResult(
                success=False,
                error=str(exc),
                duration_seconds=time.time() - started,
            )

    def _check_conflicts(self, production_bible: dict[str, Any]) -> dict[str, Any]:
        """Run trend-knowledge conflict detection if both alignment blocks exist."""
        intelligence = production_bible.get("intelligence") if isinstance(production_bible, dict) else None
        if not isinstance(intelligence, dict):
            return {"ok": True, "conflicts": [], "summary": {"skipped": True, "reason": "no intelligence block"}}

        trend_block = intelligence.get("trend_alignment")
        knowledge_block = intelligence.get("knowledge_alignment")
        if not isinstance(trend_block, dict) or not isinstance(knowledge_block, dict):
            return {"ok": True, "conflicts": [], "summary": {"skipped": True, "reason": "missing alignment blocks"}}

        trend_alignments = trend_block.get("alignments", [])
        knowledge_alignments = knowledge_block.get("alignments", [])

        # Load actual card data for the selected cards.
        selected_ids = [
            str(cid).strip()
            for cid in knowledge_block.get("selected_card_ids", [])
            if str(cid).strip()
        ]

        if not selected_ids:
            return {"ok": True, "conflicts": [], "summary": {"skipped": True, "reason": "no cards selected"}}

        try:
            from lib.ad_knowledge import load_ad_knowledge_cards
            all_cards = load_ad_knowledge_cards()
            selected_cards = [c for c in all_cards if c["card_id"] in selected_ids]
        except Exception as exc:
            return {
                "ok": False,
                "conflicts": [
                    {
                        "kind": "knowledge_card_load_failed",
                        "conflict_type": "knowledge_card_load_failed",
                        "selected_card_ids": selected_ids,
                        "detail": str(exc),
                        "recommendation": (
                            "Repair the curated knowledge card deck before locking "
                            "the production bible or generating assets."
                        ),
                    }
                ],
                "summary": {
                    "trends_checked": len(trend_alignments) if isinstance(trend_alignments, list) else 0,
                    "knowledge_cards_checked": len(knowledge_alignments) if isinstance(knowledge_alignments, list) else 0,
                    "selected_cards_checked": len(selected_ids),
                    "conflicts_found": 1,
                },
            }

        resolved_ids = {str(card.get("card_id") or "").strip() for card in selected_cards}
        missing_ids = sorted(set(selected_ids) - resolved_ids)
        missing_conflicts = [
            {
                "kind": "missing_selected_knowledge_card",
                "conflict_type": "missing_selected_knowledge_card",
                "card_id": card_id,
                "detail": (
                    f"production_bible.intelligence.knowledge_alignment.selected_card_ids "
                    f"references {card_id!r}, but no loaded knowledge card has that id."
                ),
                "recommendation": (
                    "Select an existing curated knowledge card or repair the card deck "
                    "before proceeding to asset generation."
                ),
            }
            for card_id in missing_ids
        ]

        conflict_report = check_trend_knowledge_conflicts(
            trend_alignments=trend_alignments if isinstance(trend_alignments, list) else [],
            knowledge_cards=selected_cards,
            knowledge_alignments=knowledge_alignments if isinstance(knowledge_alignments, list) else [],
        )
        if missing_conflicts:
            conflicts = missing_conflicts + list(conflict_report.get("conflicts", []))
            summary = dict(conflict_report.get("summary", {}))
            summary["missing_selected_cards"] = len(missing_conflicts)
            summary["selected_cards_checked"] = len(selected_ids)
            summary["conflicts_found"] = len(conflicts)
            return {
                "ok": False,
                "conflicts": conflicts,
                "summary": summary,
            }

        return conflict_report
