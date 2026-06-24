"""Render-runtime and music-strategy consistency validator.

Enforces the AGENT_GUIDE.md HARD RULE that production_proposal.render_runtime
(locked at proposal stage) must equal edit_decisions.render_runtime (used at
compose stage). Silent runtime swaps are forbidden — any difference must be
backed by an explicit decision_log entry tagged `render_runtime_selection`
with `user_approved == true` whose selected runtime equals the actual compose
runtime.

Also enforces the ad-video proposal lock for `music_strategy`; edit_decisions
must carry it forward unless a visible approved music_strategy_selection
decision selects the actual edit strategy.

Used by:
  - executive-producer.md G6 (after edit stage, before compose)
  - executive-producer.md G7 (after compose, as part of render verification)
  - CLI ad-hoc:
        python -m tools.validation.runtime_consistency_check \
            projects/<project-name>

The validator does NOT read AGENT_GUIDE.md or apply heuristics — it strictly
checks the proposal-vs-edit contract and the decision_log audit trail.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any

from schemas.artifacts import load_strict_json_object
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

MUSIC_STRATEGY_DECISION_CATEGORIES = {"music_strategy_selection"}


def _load_artifact(project_dir: Path, name: str) -> dict[str, Any]:
    path = project_dir / "artifacts" / name
    if not path.exists():
        raise FileNotFoundError(f"missing artifact: {path}")
    return load_strict_json_object(path, context=f"artifact {path}")


def _find_runtime_decision(
    edit_decisions: dict[str, Any],
    decision_log: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Locate a `render_runtime_selection` decision.

    Returns the entry dict, or None when no such entry exists.
    """
    if decision_log:
        decisions = decision_log.get("decisions")
        if isinstance(decisions, list):
            for decision in reversed(decisions):
                if (
                    isinstance(decision, dict)
                    and decision.get("category") == "render_runtime_selection"
                ):
                    return decision

    # Backwards compatibility for older edit_decisions artifacts that embedded
    # a one-off decision stub under metadata. New ad-video projects use the
    # cumulative decision_log.json schema with decisions[].
    metadata = edit_decisions.get("metadata") or {}
    embedded_log = metadata.get("decision_log") or {}
    if isinstance(embedded_log, dict):
        embedded_decisions = embedded_log.get("decisions")
        if isinstance(embedded_decisions, list):
            for decision in reversed(embedded_decisions):
                if (
                    isinstance(decision, dict)
                    and decision.get("category") == "render_runtime_selection"
                ):
                    return decision
        embedded_decision = embedded_log.get("render_runtime_selection")
        if isinstance(embedded_decision, dict):
            return embedded_decision

    return None


def _find_music_strategy_decision(
    edit_decisions: dict[str, Any],
    decision_log: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Locate a user-visible music strategy change decision."""
    if decision_log:
        decisions = decision_log.get("decisions")
        if isinstance(decisions, list):
            for decision in reversed(decisions):
                if (
                    isinstance(decision, dict)
                    and decision.get("category") in MUSIC_STRATEGY_DECISION_CATEGORIES
                ):
                    return decision

    metadata = edit_decisions.get("metadata") or {}
    embedded_log = metadata.get("decision_log") or {}
    if isinstance(embedded_log, dict):
        embedded_decisions = embedded_log.get("decisions")
        if isinstance(embedded_decisions, list):
            for decision in reversed(embedded_decisions):
                if (
                    isinstance(decision, dict)
                    and decision.get("category") in MUSIC_STRATEGY_DECISION_CATEGORIES
                ):
                    return decision
        for category in MUSIC_STRATEGY_DECISION_CATEGORIES:
            embedded_decision = embedded_log.get(category)
            if isinstance(embedded_decision, dict):
                return embedded_decision

    return None


def _selected_runtime(decision: dict[str, Any] | None) -> str | None:
    """Return the runtime explicitly selected by a runtime decision."""
    if not isinstance(decision, dict):
        return None

    selected = decision.get("selected")
    if isinstance(selected, str) and selected:
        return selected

    # Legacy embedded one-off decisions sometimes recorded the compose runtime
    # directly instead of using the decision_log.schema.json `selected` field.
    actual_at_compose = decision.get("actual_at_compose")
    if isinstance(actual_at_compose, str) and actual_at_compose:
        return actual_at_compose

    return None


def _decision_options_include_selected(decision: dict[str, Any] | None) -> bool:
    """Return whether a runtime decision's selected runtime was offered."""
    if not isinstance(decision, dict):
        return False

    selected = _selected_runtime(decision)
    if not selected:
        return False

    options = decision.get("options_considered")
    if not isinstance(options, list):
        return False

    return selected in {
        option.get("option_id")
        for option in options
        if isinstance(option, dict)
    }


def check_runtime_consistency(
    proposal: dict[str, Any],
    edit_decisions: dict[str, Any],
    decision_log: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Compare the locked runtime to the compose-time runtime.

    Returns a verdict dict:
        {
          "status": "PASS" | "FAIL",
          "locked_at_proposal": <runtime or None>,
          "actual_at_compose": <runtime or None>,
          "match": <bool>,
          "decision_present": <bool>,
          "decision_user_visible": <bool>,
          "decision_user_approved": <bool>,
          "decision_selected_runtime": <runtime or None>,
          "decision_matches_actual": <bool>,
          "decision_selected_option_considered": <bool>,
          "locked_music_strategy": <strategy or None>,
          "actual_music_strategy": <strategy or None>,
          "music_strategy_match": <bool>,
          "music_strategy_decision_present": <bool>,
          "issues": [<str>, ...],
        }
    """
    locked = proposal.get("render_runtime")
    actual = edit_decisions.get("render_runtime")
    locked_music_strategy = proposal.get("music_strategy")
    actual_music_strategy = edit_decisions.get("music_strategy")
    issues: list[str] = []

    if locked is None:
        issues.append(
            "production_proposal.render_runtime is unset; "
            "proposal-director must lock the runtime at proposal stage."
        )
    if actual is None:
        issues.append(
            "edit_decisions.render_runtime is unset; "
            "edit-director must carry the locked runtime forward."
        )

    match = locked == actual and locked is not None
    decision = _find_runtime_decision(edit_decisions, decision_log)
    decision_present = decision is not None
    decision_user_visible = bool(
        decision and decision.get("user_visible") is True
    )
    decision_user_approved = bool(
        decision and decision.get("user_approved") is True
    )
    decision_selected_runtime = _selected_runtime(decision)
    decision_matches_actual = (
        actual is not None and decision_selected_runtime == actual
    )
    decision_selected_option_considered = _decision_options_include_selected(decision)

    if not match and (locked is not None and actual is not None):
        # Swap occurred. Require a logged decision with user approval that
        # selects the actual runtime. An old approved proposal decision for the
        # locked runtime does not authorize a later swap.
        if not decision_present:
            issues.append(
                f"Silent runtime swap forbidden: proposal locked '{locked}' but "
                f"edit_decisions uses '{actual}'. No render_runtime_selection entry "
                f"in decision_log.decisions. AGENT_GUIDE HARD RULE "
                f"violation."
            )
        elif not decision_user_approved:
            issues.append(
                f"Runtime swap from '{locked}' to '{actual}' has a decision_log "
                f"entry but user_approved is not true. The HARD RULE requires "
                f"explicit user approval before changing the locked runtime."
            )
        elif not decision_user_visible:
            issues.append(
                f"Runtime swap from '{locked}' to '{actual}' has a decision_log "
                f"entry with user_approved=true but user_visible is not true. "
                "The HARD RULE requires surfacing runtime changes to the user "
                "before changing the locked runtime."
            )
        elif not decision_matches_actual:
            if decision_selected_runtime is None:
                issues.append(
                    f"Runtime swap from '{locked}' to '{actual}' has an approved "
                    f"render_runtime_selection entry, but it does not record a "
                    f"selected runtime and does not select actual runtime "
                    f"'{actual}'."
                )
            else:
                issues.append(
                    f"Runtime swap from '{locked}' to '{actual}' has an approved "
                    f"render_runtime_selection entry, but that decision selected "
                    f"'{decision_selected_runtime}' and does not select actual "
                    f"runtime '{actual}'."
                )
        elif not decision_selected_option_considered:
            issues.append(
                f"Runtime swap from '{locked}' to '{actual}' has an approved "
                f"render_runtime_selection entry selecting '{decision_selected_runtime}', "
                "but decision_log.options_considered does not include that "
                "selected option_id. Runtime swaps must be auditable against "
                "the options shown to the user."
            )

    music_strategy_known = (
        locked_music_strategy is not None or actual_music_strategy is not None
    )
    music_strategy_match = (
        not music_strategy_known
        or (
            locked_music_strategy == actual_music_strategy
            and locked_music_strategy is not None
        )
    )
    music_decision = _find_music_strategy_decision(edit_decisions, decision_log)
    music_decision_present = music_decision is not None
    music_decision_user_visible = bool(
        music_decision and music_decision.get("user_visible") is True
    )
    music_decision_user_approved = bool(
        music_decision and music_decision.get("user_approved") is True
    )
    music_decision_selected_strategy = _selected_runtime(music_decision)
    music_decision_matches_actual = (
        actual_music_strategy is not None
        and music_decision_selected_strategy == actual_music_strategy
    )
    music_decision_selected_option_considered = _decision_options_include_selected(
        music_decision
    )

    if locked_music_strategy is None and actual_music_strategy is not None:
        issues.append(
            "production_proposal.music_strategy is unset; proposal-director "
            "must lock the music strategy at proposal stage."
        )
    if locked_music_strategy is not None and actual_music_strategy is None:
        issues.append(
            "edit_decisions.music_strategy is unset; edit-director must carry "
            "the locked music strategy forward."
        )

    if (
        music_strategy_known
        and locked_music_strategy is not None
        and actual_music_strategy is not None
        and not music_strategy_match
    ):
        if not music_decision_present:
            issues.append(
                "Silent music_strategy swap forbidden: proposal locked "
                f"{locked_music_strategy!r} but edit_decisions uses "
                f"{actual_music_strategy!r}. No music_strategy_selection entry "
                "in decision_log.decisions."
            )
        elif not music_decision_user_approved:
            issues.append(
                "Music strategy swap from "
                f"{locked_music_strategy!r} to {actual_music_strategy!r} has "
                "a decision_log entry but user_approved is not true."
            )
        elif not music_decision_user_visible:
            issues.append(
                "Music strategy swap from "
                f"{locked_music_strategy!r} to {actual_music_strategy!r} has "
                "a decision_log entry with user_approved=true but "
                "user_visible is not true."
            )
        elif not music_decision_matches_actual:
            if music_decision_selected_strategy is None:
                issues.append(
                    "Music strategy swap from "
                    f"{locked_music_strategy!r} to {actual_music_strategy!r} "
                    "has an approved decision, but it does not record a "
                    "selected strategy and does not select the actual edit "
                    "strategy."
                )
            else:
                issues.append(
                    "Music strategy swap from "
                    f"{locked_music_strategy!r} to {actual_music_strategy!r} "
                    "has an approved decision, but that decision selected "
                    f"{music_decision_selected_strategy!r}."
                )
        elif not music_decision_selected_option_considered:
            issues.append(
                "Music strategy swap from "
                f"{locked_music_strategy!r} to {actual_music_strategy!r} has "
                "an approved decision, but decision_log.options_considered "
                "does not include the selected option_id."
            )

    status = "PASS" if not issues else "FAIL"
    return {
        "status": status,
        "locked_at_proposal": locked,
        "actual_at_compose": actual,
        "match": match,
        "decision_present": decision_present,
        "decision_user_visible": decision_user_visible,
        "decision_user_approved": decision_user_approved,
        "decision_selected_runtime": decision_selected_runtime,
        "decision_matches_actual": decision_matches_actual,
        "decision_selected_option_considered": decision_selected_option_considered,
        "locked_music_strategy": locked_music_strategy,
        "actual_music_strategy": actual_music_strategy,
        "music_strategy_match": music_strategy_match,
        "music_strategy_decision_present": music_decision_present,
        "music_strategy_decision_user_visible": music_decision_user_visible,
        "music_strategy_decision_user_approved": music_decision_user_approved,
        "music_strategy_decision_selected": music_decision_selected_strategy,
        "music_strategy_decision_matches_actual": music_decision_matches_actual,
        "music_strategy_decision_selected_option_considered": (
            music_decision_selected_option_considered
        ),
        "issues": issues,
    }


def check_project(project_dir: Path) -> dict[str, Any]:
    """Convenience entry point for ad-hoc CLI use."""
    proposal = _load_artifact(project_dir, "production_proposal.json")
    edit_decisions = _load_artifact(project_dir, "edit_decisions.json")
    decision_log = _load_decision_log(project_dir)
    return check_runtime_consistency(proposal, edit_decisions, decision_log)


class RuntimeConsistencyCheck(BaseTool):
    name = "runtime_consistency_check"
    version = "0.1.0"
    tier = ToolTier.CORE
    capability = "validation"
    provider = "video_production_buddy"
    stability = ToolStability.PRODUCTION
    execution_mode = ExecutionMode.SYNC
    determinism = Determinism.DETERMINISTIC
    runtime = ToolRuntime.LOCAL
    resource_profile = ResourceProfile(cpu_cores=1, ram_mb=64, disk_mb=1, network_required=False)
    idempotency_key_fields = [
        "project_dir",
        "production_proposal",
        "proposal",
        "edit_decisions",
        "decision_log",
    ]
    capabilities = [
        "validate_render_runtime_lock",
        "detect_silent_render_runtime_swap",
        "validate_render_runtime_selection_decision",
        "validate_music_strategy_lock",
        "detect_silent_music_strategy_swap",
    ]
    best_for = [
        "enforcing that edit_decisions.render_runtime carries the proposal runtime lock",
        "blocking silent runtime swaps before compose",
        "enforcing that edit_decisions.music_strategy carries the proposal music strategy lock",
    ]
    input_schema = {
        "type": "object",
        "properties": {
            "project_dir": {"type": "string"},
            "production_proposal": {"type": "object"},
            "proposal": {"type": "object"},
            "edit_decisions": {"type": "object"},
            "decision_log": {"type": "object"},
        },
        "anyOf": [
            {"required": ["project_dir"]},
            {"required": ["production_proposal", "edit_decisions"]},
            {"required": ["proposal", "edit_decisions"]},
        ],
    }
    output_schema = {
        "type": "object",
        "required": [
            "status",
            "locked_at_proposal",
            "actual_at_compose",
            "match",
            "locked_music_strategy",
            "actual_music_strategy",
            "music_strategy_match",
            "decision_selected_option_considered",
            "issues",
        ],
        "properties": {
            "status": {"type": "string", "enum": ["PASS", "FAIL"]},
            "locked_at_proposal": {"type": ["string", "null"]},
            "actual_at_compose": {"type": ["string", "null"]},
            "match": {"type": "boolean"},
            "decision_present": {"type": "boolean"},
            "decision_user_visible": {"type": "boolean"},
            "decision_user_approved": {"type": "boolean"},
            "decision_selected_runtime": {"type": ["string", "null"]},
            "decision_matches_actual": {"type": "boolean"},
            "decision_selected_option_considered": {"type": "boolean"},
            "locked_music_strategy": {"type": ["string", "null"]},
            "actual_music_strategy": {"type": ["string", "null"]},
            "music_strategy_match": {"type": "boolean"},
            "music_strategy_decision_present": {"type": "boolean"},
            "music_strategy_decision_user_visible": {"type": "boolean"},
            "music_strategy_decision_user_approved": {"type": "boolean"},
            "music_strategy_decision_selected": {"type": ["string", "null"]},
            "music_strategy_decision_matches_actual": {"type": "boolean"},
            "music_strategy_decision_selected_option_considered": {"type": "boolean"},
            "issues": {"type": "array", "items": {"type": "string"}},
        },
    }
    user_visible_verification = [
        "Confirm render_runtime selected at proposal is unchanged at compose unless user-approved",
        "Confirm music_strategy selected at proposal is unchanged at edit unless user-approved",
    ]

    def execute(self, inputs: dict[str, Any]) -> ToolResult:
        started = time.time()
        try:
            project_dir = inputs.get("project_dir")
            if isinstance(project_dir, str) and project_dir.strip():
                verdict = check_project(Path(project_dir))
            else:
                proposal = inputs.get("production_proposal") or inputs.get("proposal") or {}
                verdict = check_runtime_consistency(
                    proposal,
                    inputs["edit_decisions"],
                    inputs.get("decision_log"),
                )
        except Exception as exc:
            return ToolResult(success=False, error=str(exc), duration_seconds=round(time.time() - started, 2))

        success = verdict.get("status") == "PASS"
        return ToolResult(
            success=success,
            data=verdict,
            error=json.dumps(verdict.get("issues", []), sort_keys=True, allow_nan=False) if not success else None,
            duration_seconds=round(time.time() - started, 2),
        )


def _load_decision_log(project_dir: Path) -> dict[str, Any] | None:
    for path in (
        project_dir / "decision_log.json",
        project_dir / "artifacts" / "decision_log.json",
    ):
        if path.exists():
            return load_strict_json_object(path, context=f"decision log {path}")
    return None


def _cli(argv: list[str]) -> int:
    if len(argv) != 2:
        print(
            "usage: python -m tools.validation.runtime_consistency_check "
            "<project-dir>",
            file=sys.stderr,
        )
        return 2
    project_dir = Path(argv[1]).resolve()
    if not project_dir.exists():
        print(f"error: project dir not found: {project_dir}", file=sys.stderr)
        return 2
    verdict = check_project(project_dir)
    print(json.dumps(verdict, indent=2, allow_nan=False))
    return 0 if verdict["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(_cli(sys.argv))
