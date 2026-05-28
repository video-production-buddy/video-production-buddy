"""Structural compliance checker for production_bible checkpoints.

Evaluates check_type IN ['timing', 'presence', 'structural'] deterministically.
Rejects semantic checkpoints — those require LLM judgment.
"""
from __future__ import annotations

import re
from typing import Any

from tools.base_tool import (
    BaseTool, Determinism, ExecutionMode,
    ToolResult, ToolRuntime, ToolStability, ToolTier,
)

from lib.constants import WORDS_PER_MINUTE_VO
from lib.hit_ad_pacing import cuts_density_from_shot_duration

# VO pacing assumption per spec §9 — sourced from lib.constants so
# lib/hook_window.py and this module can never silently diverge. Tests pin
# both to the same source.
_WORDS_PER_MINUTE = WORDS_PER_MINUTE_VO
_TIMING_TOLERANCE = 0.10  # ±10%
_PRESENCE_METADATA_SUBTREE_KEYS = {
    "hallucination_checks",
    "compliance_failures",
    "review",
    "metadata",
}
_PRESENCE_METADATA_TEXT_KEYS = {
    "id",
    "asset_id",
    "beat_id",
    "category",
    "check_id",
    "check_type",
    "criterion",
    "decision_id",
    "evaluation_method",
    "evidence_source",
    "failure_action",
    "prohibited_failure",
    "reason",
    "requirement",
    "rule_id",
    "severity",
    "source_confidence",
    "source_ref",
    "stage",
    "status",
    "type",
}


class _StructuredCriterionError(Exception):
    """Raised by structured-criterion handlers on malformed input.

    Caught by ``ComplianceCheck.execute`` and surfaced as a tool error so a
    typo in the bible's compliance_manifest fails loudly instead of silently
    falling through to the regex parser.
    """


class ComplianceCheck(BaseTool):
    """Evaluate a structural compliance checkpoint against stage output.

    Accepts: { stage_output: dict, checkpoint: dict }
    Returns ToolResult.data: { checkpoint_id, pass, actual_value, deviation, failure_action }
    """

    name = "compliance_check"
    version = "1.0.0"
    tier = ToolTier.CORE
    stability = ToolStability.BETA
    execution_mode = ExecutionMode.SYNC
    determinism = Determinism.DETERMINISTIC
    runtime = ToolRuntime.LOCAL
    capability = "compliance"
    provider = "openmontage"
    best_for = ["structural compliance checking", "bible checkpoint evaluation"]
    not_good_for = ["semantic compliance — use LLM judgment instead"]

    def execute(self, inputs: dict[str, Any]) -> ToolResult:
        stage_output = inputs.get("stage_output")
        checkpoint = inputs.get("checkpoint")

        if stage_output is None:
            return ToolResult(success=False, error="stage_output is required")
        if not checkpoint:
            return ToolResult(success=False, error="checkpoint is required")

        eval_method = checkpoint.get("evaluation_method", "")
        if eval_method != "structural":
            return ToolResult(
                success=False,
                error=(
                    f"compliance_check only handles structural checkpoints; "
                    f"got evaluation_method='{eval_method}'. "
                    f"Semantic checkpoints require LLM judgment."
                ),
            )

        # v2 structured criteria short-circuit the regex parser. When `structured`
        # is present the legacy `criterion` text is informational only; we never
        # parse it. This eliminates the silent-failure class where slightly
        # off-template English broke the regex and reported "content failure".
        structured = checkpoint.get("structured")
        if structured is not None:
            try:
                result = self._check_structured(stage_output, structured)
            except _StructuredCriterionError as exc:
                return ToolResult(success=False, error=str(exc))
            return ToolResult(
                success=True,
                data={
                    "checkpoint_id": checkpoint.get("id"),
                    "pass": result["pass"],
                    "actual_value": result.get("actual_value"),
                    "deviation": result.get("deviation"),
                    "failure_action": checkpoint.get("failure_action", "flag"),
                },
            )

        check_type = checkpoint.get("check_type", "")
        dispatch = {
            "timing": self._check_timing,
            "presence": self._check_presence,
            "structural": self._check_structural,
        }
        handler = dispatch.get(check_type)
        if not handler:
            return ToolResult(
                success=False,
                error=f"Unknown check_type: '{check_type}'. Valid: {list(dispatch)}"
            )

        result = handler(stage_output, checkpoint)
        # success=True means the tool ran; check data["pass"] for the compliance result
        return ToolResult(
            success=True,
            data={
                "checkpoint_id": checkpoint.get("id"),
                "pass": result["pass"],
                "actual_value": result.get("actual_value"),
                "deviation": result.get("deviation"),
                "failure_action": checkpoint.get("failure_action", "flag"),
            },
        )

    # ── v2 structured-criterion handlers ──────────────────────────────────

    def _check_structured(self, stage_output: dict, structured: dict) -> dict:
        kind = structured.get("kind")
        dispatch = {
            "timing": self._check_structured_timing,
            "presence": self._check_structured_presence,
            "beat_mapping": self._check_structured_beat_mapping,
            "editing_rhythm": self._check_structured_editing_rhythm,
        }
        handler = dispatch.get(kind)
        if handler is None:
            raise _StructuredCriterionError(
                f"Unknown structured criterion kind: {kind!r}. "
                f"Valid: {sorted(dispatch)}."
            )
        return handler(stage_output, structured)

    def _check_structured_timing(self, stage_output: dict, structured: dict) -> dict:
        """Sum words for the named beat; compare to target_seconds at WPM ±tolerance."""
        try:
            beat_id = structured["beat_id"]
            target_seconds = float(structured["target_seconds"])
            tolerance = float(structured.get("tolerance", _TIMING_TOLERANCE))
        except (KeyError, TypeError, ValueError) as exc:
            raise _StructuredCriterionError(
                f"timing structured criterion is missing or has invalid fields "
                f"(beat_id, target_seconds, optional tolerance): {exc}"
            ) from exc

        total_words = 0
        for section in stage_output.get("sections", []):
            if (
                section.get("beat_id") != beat_id
                and section.get("maps_to_beat") != beat_id
                and section.get("beat") != beat_id
            ):
                continue
            text = section.get("narration", section.get("text", ""))
            total_words += len(text.split())

        estimated = (total_words / _WORDS_PER_MINUTE) * 60
        tol_seconds = target_seconds * tolerance
        passed = abs(estimated - target_seconds) <= tol_seconds
        return {
            "pass": passed,
            "actual_value": f"{estimated:.1f}s",
            "deviation": (None if passed else
                          f"estimated {estimated:.1f}s vs target {target_seconds}s "
                          f"(tolerance ±{tol_seconds:.1f}s)"),
        }

    def _check_structured_presence(self, stage_output: dict, structured: dict) -> dict:
        """Substring search across the stage_output JSON. Negated form rejects on hit."""
        terms = structured.get("terms")
        if not terms or not isinstance(terms, list):
            raise _StructuredCriterionError(
                "presence structured criterion requires 'terms' (non-empty list of strings)"
            )
        min_count = int(structured.get("min_count", 1))
        negated = bool(structured.get("negated", False))

        haystack = _presence_haystack(stage_output)
        found = {t: haystack.count(str(t).lower()) for t in terms}

        if negated:
            violations = {t: c for t, c in found.items() if c > 0}
            return {
                "pass": len(violations) == 0,
                "actual_value": found,
                "deviation": (None if not violations else
                              "; ".join(f"prohibited '{t}' found {c} time(s)"
                                        for t, c in violations.items())),
            }

        failing = [(t, c) for t, c in found.items() if c < min_count]
        return {
            "pass": len(failing) == 0,
            "actual_value": found,
            "deviation": (None if not failing else
                          "; ".join(f"'{t}' found {c}, required ≥{min_count}"
                                    for t, c in failing)),
        }

    def _check_structured_beat_mapping(self, stage_output: dict, structured: dict) -> dict:
        """At least one scene/section must declare the named beat as its target."""
        beat_id = structured.get("beat_id")
        if not beat_id:
            raise _StructuredCriterionError(
                "beat_mapping structured criterion requires 'beat_id'"
            )
        scenes = _stage_entries(stage_output)
        matched = [
            s for s in scenes
            if _entry_maps_to_beat(s, beat_id)
        ]
        passed = len(matched) > 0
        return {
            "pass": passed,
            "actual_value": f"{len(matched)} entry(ies) mapped to beat {beat_id}",
            "deviation": (None if passed else f"No scene/section/cut mapped to beat {beat_id}"),
        }

    def _check_structured_editing_rhythm(self, stage_output: dict, structured: dict) -> dict:
        """Verify edit_decisions.cuts[] match the bible's editing_rhythm entry."""
        try:
            beat_id = structured["beat_id"]
            target_avg = float(structured["avg_shot_duration_seconds"])
            expected_density = str(structured["cuts_density"])
            expected_transition = _normalize_transition_style(
                str(structured["transition_style"])
            )
            tolerance = float(structured.get("tolerance", 0.25))
        except (KeyError, TypeError, ValueError) as exc:
            raise _StructuredCriterionError(
                "editing_rhythm structured criterion is missing or has invalid fields "
                "(beat_id, cuts_density, avg_shot_duration_seconds, transition_style, "
                f"optional tolerance): {exc}"
            ) from exc

        if target_avg <= 0:
            raise _StructuredCriterionError(
                "editing_rhythm avg_shot_duration_seconds must be > 0"
            )
        if not 0 <= tolerance <= 1:
            raise _StructuredCriterionError(
                "editing_rhythm tolerance must be between 0 and 1"
            )

        cuts = _stage_cuts(stage_output)
        matched = [cut for cut in cuts if _entry_maps_to_beat(cut, beat_id)]
        if not matched:
            return {
                "pass": False,
                "actual_value": "0 cut(s)",
                "deviation": f"No edit_decisions.cuts[] mapped to beat {beat_id}",
            }

        durations: list[float] = []
        invalid_duration_ids: list[str] = []
        for cut in matched:
            start = cut.get("in_seconds")
            end = cut.get("out_seconds")
            if (
                not isinstance(start, (int, float))
                or not isinstance(end, (int, float))
                or end <= start
            ):
                invalid_duration_ids.append(str(cut.get("id", "<unknown>")))
                continue
            durations.append(float(end) - float(start))

        if not durations:
            return {
                "pass": False,
                "actual_value": f"{len(matched)} cut(s)",
                "deviation": (
                    "No valid cut durations for beat "
                    f"{beat_id}; invalid cut ids: {invalid_duration_ids}"
                ),
            }

        actual_avg = sum(durations) / len(durations)
        actual_density = cuts_density_from_shot_duration(actual_avg)
        observed_transitions = sorted(
            {
                _normalize_transition_style(style)
                for cut in matched
                for style in (cut.get("transition_in"), cut.get("transition_out"))
                if isinstance(style, str) and style.strip()
            }
        )

        tolerance_seconds = target_avg * tolerance
        deviations: list[str] = []
        if abs(actual_avg - target_avg) > tolerance_seconds:
            deviations.append(
                "avg_shot_duration_seconds "
                f"{actual_avg:.2f}s vs target {target_avg:.2f}s "
                f"(tolerance ±{tolerance_seconds:.2f}s)"
            )
        if actual_density != expected_density:
            deviations.append(
                f"cuts_density {actual_density!r} vs expected {expected_density!r}"
            )
        if not observed_transitions:
            deviations.append(
                f"transition_style missing; expected {expected_transition!r}"
            )
        elif any(style != expected_transition for style in observed_transitions):
            deviations.append(
                "transition_style "
                f"{observed_transitions!r} vs expected {expected_transition!r}"
            )

        return {
            "pass": not deviations,
            "actual_value": {
                "cut_count": len(matched),
                "avg_shot_duration_seconds": round(actual_avg, 3),
                "cuts_density": actual_density,
                "transition_styles": observed_transitions,
            },
            "deviation": None if not deviations else "; ".join(deviations),
        }

    def _check_timing(self, stage_output: dict, checkpoint: dict) -> dict:
        """Word count → WPM estimate → compare to target_seconds ±10%."""
        criterion = checkpoint.get("criterion", "")
        # Prefer anchored match ("of Xs") for precision; fall back to any "Ns" pattern.
        # NOTE: v1 uses natural-language criteria. This parser will be replaced in v2
        # when criteria migrate to structured {field, operator, value, tolerance} format.
        duration_match = re.search(r"\bof\s+(\d+(?:\.\d+)?)s\b", criterion)
        if not duration_match:
            duration_match = re.search(r"(?<!\w)(\d+(?:\.\d+)?)s\b", criterion)
        if not duration_match:
            return {"pass": False, "actual_value": None,
                    "deviation": f"Cannot parse target duration from: {criterion!r}"}
        target_seconds = float(duration_match.group(1))

        beat_match = re.search(r"\bbeat (\w+)", criterion)
        if not beat_match:
            return {"pass": False, "actual_value": None,
                    "deviation": (
                        f"Cannot parse beat_id from criterion: {criterion!r}. "
                        f"Expected 'beat <ID>' pattern. "
                        f"NOTE: v1 uses natural-language criteria; this parser will be replaced in v2."
                    )}
        beat_id = beat_match.group(1)

        total_words = 0
        for section in stage_output.get("sections", []):
            if section.get("beat_id") != beat_id and section.get("maps_to_beat") != beat_id:
                continue
            text = section.get("narration", section.get("text", ""))
            total_words += len(text.split())

        estimated = (total_words / _WORDS_PER_MINUTE) * 60
        tolerance = target_seconds * _TIMING_TOLERANCE
        passed = abs(estimated - target_seconds) <= tolerance
        return {
            "pass": passed,
            "actual_value": f"{estimated:.1f}s",
            "deviation": (None if passed else
                          f"estimated {estimated:.1f}s vs target {target_seconds}s "
                          f"(tolerance ±{tolerance:.1f}s)"),
        }

    def _check_presence(self, stage_output: dict, checkpoint: dict) -> dict:
        """String/keyword search. Supports positive and negated ('must not appear') checks."""
        criterion = checkpoint.get("criterion", "")
        output_str = _presence_haystack(stage_output)
        quoted_terms = re.findall(r"'([^']+)'", criterion)
        if not quoted_terms:
            return {"pass": False, "actual_value": None,
                    "deviation": f"Cannot parse presence target from: {criterion!r}"}

        # Detect negation — prohibited / must-not checks
        is_negated = bool(re.search(
            r"\bmust not\b|\bprohibited\b|\bmust never\b|\bnot appear\b",
            criterion.lower(),
        ))

        found_map = {t: output_str.count(t.lower()) for t in quoted_terms}

        if is_negated:
            violations = {t: c for t, c in found_map.items() if c > 0}
            return {
                "pass": len(violations) == 0,
                "actual_value": found_map,
                "deviation": (None if not violations else
                              "; ".join(f"prohibited '{t}' found {c} time(s)"
                                        for t, c in violations.items())),
            }

        count_match = re.search(r"[≥>=]\s*(\d+)", criterion)
        min_count = int(count_match.group(1)) if count_match else 1

        results = [{"term": t, "found": found_map[t], "required": min_count}
                   for t in quoted_terms]
        all_passed = all(r["found"] >= r["required"] for r in results)
        failing = [r for r in results if r["found"] < r["required"]]
        return {
            "pass": all_passed,
            "actual_value": found_map,
            "deviation": (None if all_passed else
                          "; ".join(f"'{r['term']}' found {r['found']}, required ≥{r['required']}"
                                    for r in failing)),
        }

    def _check_structural(self, stage_output: dict, checkpoint: dict) -> dict:
        """Beat ID mapping: verify ≥1 scene maps to the target beat."""
        criterion = checkpoint.get("criterion", "")
        beat_match = re.search(r"\bbeat (\w+)", criterion)
        if not beat_match:
            return self._check_presence(stage_output, checkpoint)
        target_beat = beat_match.group(1)
        scenes = _stage_entries(stage_output)
        matched = [s for s in scenes
                   if _entry_maps_to_beat(s, target_beat)]
        passed = len(matched) > 0
        return {
            "pass": passed,
            "actual_value": f"{len(matched)} entry(ies) mapped to beat {target_beat}",
            "deviation": (None if passed else f"No scene/section/cut found mapped to beat {target_beat}"),
        }


def _entry_maps_to_beat(entry: dict[str, Any], beat_id: str) -> bool:
    return (
        entry.get("maps_to_beat") == beat_id
        or entry.get("beat_id") == beat_id
        or entry.get("beat") == beat_id
    )


def _stage_cuts(stage_output: dict[str, Any]) -> list[dict[str, Any]]:
    cuts = stage_output.get("cuts")
    if isinstance(cuts, list):
        return [cut for cut in cuts if isinstance(cut, dict)]

    edit_decisions = stage_output.get("edit_decisions")
    if isinstance(edit_decisions, dict) and isinstance(edit_decisions.get("cuts"), list):
        return [cut for cut in edit_decisions["cuts"] if isinstance(cut, dict)]

    return []


def _presence_haystack(stage_output: Any) -> str:
    values: list[str] = []
    _collect_presence_text(stage_output, values)
    return "\n".join(values).lower()


def _collect_presence_text(value: Any, values: list[str], key: str | None = None) -> None:
    if key in _PRESENCE_METADATA_SUBTREE_KEYS:
        return

    if isinstance(value, dict):
        for child_key, child_value in value.items():
            normalized_key = str(child_key)
            if normalized_key in _PRESENCE_METADATA_SUBTREE_KEYS:
                continue
            _collect_presence_text(child_value, values, normalized_key)
        return

    if isinstance(value, list):
        for item in value:
            _collect_presence_text(item, values, key)
        return

    if isinstance(value, str) and key not in _PRESENCE_METADATA_TEXT_KEYS:
        stripped = value.strip()
        if stripped:
            values.append(stripped)


def _stage_entries(stage_output: dict[str, Any]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for key in ("scenes", "sections", "cuts"):
        value = stage_output.get(key)
        if isinstance(value, list):
            entries.extend(item for item in value if isinstance(item, dict))

    edit_decisions = stage_output.get("edit_decisions")
    if isinstance(edit_decisions, dict) and isinstance(edit_decisions.get("cuts"), list):
        entries.extend(item for item in edit_decisions["cuts"] if isinstance(item, dict))

    return entries


def _normalize_transition_style(style: str) -> str:
    normalized = style.strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "cut": "hard_cut",
        "hardcut": "hard_cut",
        "hard_cut": "hard_cut",
        "match": "match_cut",
        "matchcut": "match_cut",
        "match_cut": "match_cut",
    }
    return aliases.get(normalized, normalized)
