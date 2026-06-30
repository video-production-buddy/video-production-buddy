"""Beginner-friendly model preference inspection and configuration."""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable, Sequence

from lib.model_preferences import (
    env_keys_for_capability,
    env_model_preferences,
    model_field_for_capability,
)


PRESETS = ("auto", "balanced", "fast", "highest_quality", "lowest_cost")
_QUALITY_SCORE = {
    "legacy_good": 1,
    "legacy_high": 2,
    "lowest": 0,
    "low": 1,
    "standard": 2,
    "medium": 2,
    "balanced": 2,
    "high": 3,
    "higher": 3,
    "hd": 3,
    "highest": 4,
    "current_sota": 4,
    "premium": 4,
    "pro": 4,
}
_SPEED_SCORE = {
    "slow": 0,
    "medium": 1,
    "balanced": 1,
    "standard": 1,
    "fast": 2,
    "faster": 3,
    "realtime": 4,
}
_PRESET_ALIASES = {
    "recommended": "auto",
    "default": "auto",
    "quality": "highest_quality",
    "best": "highest_quality",
    "cheap": "lowest_cost",
    "cost": "lowest_cost",
}


@dataclass(frozen=True)
class ModelPreferenceSelection:
    """A concrete model preference ready to persist as VPB_* env keys."""

    capability: str
    provider: str | None
    tool: str | None
    field: str
    model_id: str
    model_name: str
    preset: str = "auto"


@dataclass(frozen=True)
class ModelPreferenceIssue:
    """A user-fixable problem in .env model preferences."""

    capability: str
    message: str


def load_model_choices() -> list[dict[str, Any]]:
    """Read live model choices from the tool registry preflight summary."""
    from tools.tool_registry import registry

    registry.discover()
    summary = registry.provider_menu_summary()
    return list(summary.get("model_choices") or [])


def format_model_choices_for_user(
    model_choices: Sequence[dict[str, Any]],
    *,
    capability: str | None = None,
) -> str:
    """Render model choices as a short plain-language list instead of JSON."""
    choices = [
        choice for choice in model_choices
        if capability is None or choice.get("capability") == capability
    ]
    if not choices:
        label = _capability_label(capability) if capability else "Any capability"
        return f"No model choices found for {label}."

    lines = ["Available model choices"]
    current_capability: str | None = None
    for choice in sorted(choices, key=_choice_sort_key):
        choice_capability = str(choice.get("capability") or "unknown")
        if choice_capability != current_capability:
            current_capability = choice_capability
            lines.append("")
            lines.append(_capability_label(choice_capability))

        provider = choice.get("provider") or "unknown provider"
        tool = choice.get("tool") or "unknown tool"
        status = choice.get("status") or "unknown"
        field = choice.get("field") or "model"
        lines.append(f"  {provider} ({tool}, {status}) - set {field}")

        for option in choice.get("options") or []:
            option_name = option.get("name") or option.get("id") or "unnamed model"
            option_id = option.get("id") or option_name
            details = _option_details(option)
            default_marker = " [default]" if _is_default_option(choice, option) else ""
            suffix = f"; {details}" if details else ""
            lines.append(f"    - {option_name} ({option_id}){default_marker}{suffix}")

    return "\n".join(lines)


def select_model_preference(
    model_choices: Sequence[dict[str, Any]],
    *,
    capability: str,
    preset: str = "auto",
    provider: str | None = None,
    model_id: str | None = None,
) -> ModelPreferenceSelection:
    """Choose a model preference by explicit model or by a beginner preset."""
    preset = _normalize_preset(preset)
    rows = list(_model_rows(model_choices, capability=capability))
    if not rows:
        raise ValueError(f"No model choices found for {capability}.")

    if provider:
        rows = [
            row for row in rows
            if row["provider"] == provider or row["tool"] == provider
        ]
        if not rows:
            raise ValueError(
                f"No model choices found for provider or tool {provider!r} "
                f"under {capability}."
            )

    if model_id:
        explicit = [row for row in rows if row["model_id"] == model_id]
        if not explicit:
            raise ValueError(
                f"No model option {model_id!r} found for {capability}. "
                "Run `make models-list` to inspect valid model IDs."
            )
        compatible = [row for row in explicit if _row_supports_default_operation(row)]
        if not compatible:
            operation = _default_operation_for_capability(capability)
            operation_suffix = (
                f" for the default {operation} operation"
                if operation
                else ""
            )
            raise ValueError(
                f"Model option {model_id!r} is not supported{operation_suffix}. "
                "Choose a compatible model or run `make models-list` to inspect "
                "valid model IDs."
            )
        return _selection_from_row(
            compatible[0],
            preset=preset,
            requested_provider=provider,
        )

    compatible_rows = [row for row in rows if _row_supports_default_operation(row)]
    if not compatible_rows:
        operation = _default_operation_for_capability(capability)
        operation_suffix = (
            f" for the default {operation} operation"
            if operation
            else ""
        )
        raise ValueError(
            f"No model choices found for {capability}{operation_suffix}."
        )

    available_rows = [row for row in compatible_rows if row["status"] == "available"]
    candidates = available_rows or compatible_rows
    ranked = sorted(candidates, key=lambda row: _preset_sort_key(row, preset))
    return _selection_from_row(
        ranked[0],
        preset=preset,
        requested_provider=provider,
    )


def write_model_preference(
    env_path: Path,
    selection: ModelPreferenceSelection,
) -> dict[str, str]:
    """Persist one selected capability as beginner-facing .env keys."""
    values = {
        env_keys_for_capability(selection.capability)["provider"]: selection.provider or "",
        env_keys_for_capability(selection.capability)["model"]: selection.model_id,
    }
    _write_env_values(env_path, values)
    return _read_env_mapping(env_path)


def validate_model_preferences(
    env_path: Path,
    model_choices: Sequence[dict[str, Any]],
) -> list[ModelPreferenceIssue]:
    """Validate .env model preferences against live registry choices."""
    env = _read_env_mapping(env_path)
    issues: list[ModelPreferenceIssue] = []
    for capability in _capabilities_from_env(env):
        preferences = env_model_preferences(capability, environ=env)
        provider = preferences.get("preferred_provider")
        model_field = model_field_for_capability(capability)
        model_id = preferences.get(model_field)
        if not provider and not model_id and not preferences.get("allowed_providers"):
            continue

        rows = list(_model_rows(model_choices, capability=capability))
        if not rows:
            issues.append(
                ModelPreferenceIssue(
                    capability=capability,
                    message=(
                        f"No model list is available for {capability} in .env. "
                        f"Run `make models-list CAPABILITY={capability}`."
                    ),
                )
            )
            continue

        if provider and not any(
            _provider_matches(row, provider) for row in rows
        ):
            issues.append(
                ModelPreferenceIssue(
                    capability=capability,
                    message=(
                        f"Unknown provider/tool {provider!r} for {capability} in .env. "
                        f"Run `make models-list CAPABILITY={capability}`."
                    ),
                )
            )
            continue

        allowed_providers = preferences.get("allowed_providers") or []
        unknown_allowed = [
            value for value in allowed_providers
            if not any(_provider_matches(row, value) for row in rows)
        ]
        if unknown_allowed:
            issues.append(
                ModelPreferenceIssue(
                    capability=capability,
                    message=(
                        f"Unknown allowed provider/tool {unknown_allowed[0]!r} "
                        f"for {capability} in .env. Run `make models-list "
                        f"CAPABILITY={capability}`."
                    ),
                )
            )
            continue

        if provider and allowed_providers and not any(
            _provider_matches(row, provider) and _row_allowed(row, allowed_providers)
            for row in rows
        ):
            issues.append(
                ModelPreferenceIssue(
                    capability=capability,
                    message=(
                        f"Provider/tool {provider!r} for {capability} is not "
                        "included in the allowed provider shortlist in .env."
                    ),
                )
            )
            continue

        if model_id:
            model_matches = [
                row for row in rows
                if row["model_id"] == model_id
                and (not provider or _provider_matches(row, provider))
            ]
            if not model_matches:
                issues.append(
                    ModelPreferenceIssue(
                        capability=capability,
                        message=(
                            f"Unknown model {model_id!r} for {capability} in .env. "
                            f"Run `make models-list CAPABILITY={capability}`."
                        ),
                    )
                )
                continue
            if not any(_row_allowed(row, allowed_providers) for row in model_matches):
                issues.append(
                    ModelPreferenceIssue(
                        capability=capability,
                        message=(
                            f"Model {model_id!r} for {capability} is not "
                            "included in the allowed provider shortlist in .env."
                        ),
                    ),
                )
                continue
            if not any(_row_supports_default_operation(row) for row in model_matches):
                operation = _default_operation_for_capability(capability)
                operation_suffix = (
                    f" the default {operation} operation"
                    if operation
                    else " the default operation"
                )
                issues.append(
                    ModelPreferenceIssue(
                        capability=capability,
                        message=(
                            f"Model {model_id!r} for {capability} does not "
                            f"support{operation_suffix} in .env. Choose a "
                            "compatible default model or omit the model default."
                        ),
                    ),
                )
                continue

    return issues


def _provider_matches(row: dict[str, Any], value: str) -> bool:
    return row["provider"] == value or row["tool"] == value


def _row_allowed(row: dict[str, Any], allowed_providers: Sequence[str]) -> bool:
    return not allowed_providers or any(
        _provider_matches(row, value) for value in allowed_providers
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    env_path = Path(args.env)
    model_choices = load_model_choices()

    if args.check:
        issues = validate_model_preferences(env_path, model_choices)
        if issues:
            for issue in issues:
                print(f"Error: {issue.message}", file=sys.stderr)
            return 1
        print(f"Model preferences in {env_path} are valid.")
        return 0

    if args.list:
        print(format_model_choices_for_user(model_choices, capability=args.capability))
        return 0

    try:
        capability, preset, provider, model_id = _resolve_cli_selection(args, model_choices)
        selection = select_model_preference(
            model_choices,
            capability=capability,
            preset=preset,
            provider=provider,
            model_id=model_id,
        )
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    print(_format_selection_preview(env_path, selection))
    if args.dry_run:
        return 0

    if not args.yes and not _confirm("Write this model preference?"):
        print("No changes written.")
        return 0

    write_model_preference(env_path, selection)
    print(f"Updated {env_path}.")
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Inspect provider models and validate optional VPB_* model defaults."
        )
    )
    parser.add_argument(
        "--env",
        default=".env.example",
        help="Path to an env-style file. Defaults to ./.env.example.",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List model choices in plain language without writing files.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Validate VPB_* model defaults in the env-style file.",
    )
    parser.add_argument(
        "--capability",
        help="Capability to inspect or configure, for example video_generation.",
    )
    parser.add_argument(
        "--preset",
        default="auto",
        help=(
            "Model preset: auto, balanced, fast, highest_quality, or "
            "lowest_cost. Defaults to auto."
        ),
    )
    parser.add_argument(
        "--provider",
        help="Provider or concrete tool name to prefer, for example seedance.",
    )
    parser.add_argument(
        "--model",
        dest="model_id",
        help="Exact model ID to write, for example wan2.7-image-pro.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview the config change without writing.",
    )
    parser.add_argument(
        "--yes",
        "-y",
        action="store_true",
        help="Write without an interactive confirmation prompt.",
    )
    return parser


def _resolve_cli_selection(
    args: argparse.Namespace,
    model_choices: Sequence[dict[str, Any]],
) -> tuple[str, str, str | None, str | None]:
    if args.capability:
        return args.capability, args.preset, args.provider, args.model_id

    if not sys.stdin.isatty():
        raise ValueError(
            "Pass --capability for non-interactive use, or run this command in "
            "an interactive terminal."
        )

    print(format_model_choices_for_user(model_choices))
    capabilities = sorted(
        {
            str(choice.get("capability"))
            for choice in model_choices
            if choice.get("capability")
        }
    )
    capability = _prompt_choice("Capability", capabilities)
    preset = _prompt_choice("Preset", list(PRESETS), default="auto")
    provider = _prompt_optional("Provider or tool name (blank = auto)")
    model_id = _prompt_optional("Exact model ID (blank = preset pick)")
    return capability, preset, provider, model_id


def _model_rows(
    model_choices: Sequence[dict[str, Any]],
    *,
    capability: str,
) -> Iterable[dict[str, Any]]:
    for choice in model_choices:
        if choice.get("capability") != capability:
            continue
        field = str(choice.get("field") or "model")
        for option in choice.get("options") or []:
            option_id = option.get("id")
            if not option_id:
                continue
            yield {
                "capability": capability,
                "provider": choice.get("provider"),
                "tool": choice.get("tool"),
                "status": choice.get("status"),
                "field": option.get("field") or field,
                "model_id": str(option_id),
                "model_name": str(option.get("name") or option_id),
                "option": option,
                "choice": choice,
            }


def _selection_from_row(
    row: dict[str, Any],
    *,
    preset: str,
    requested_provider: str | None = None,
) -> ModelPreferenceSelection:
    provider_value = row.get("provider")
    if requested_provider and row.get("tool") == requested_provider:
        provider_value = requested_provider
    return ModelPreferenceSelection(
        capability=str(row["capability"]),
        provider=provider_value,
        tool=row.get("tool"),
        field=str(row["field"]),
        model_id=str(row["model_id"]),
        model_name=str(row["model_name"]),
        preset=preset,
    )


def _default_operation_for_capability(capability: str) -> str | None:
    if capability == "video_generation":
        return "text_to_video"
    return None


def _row_supports_default_operation(row: dict[str, Any]) -> bool:
    operation = _default_operation_for_capability(str(row["capability"]))
    if operation is None:
        return True
    return _option_supports_operation(row["option"], operation)


def _option_supports_operation(option: dict[str, Any], operation: str) -> bool:
    option_operation = option.get("operation")
    if option_operation and str(option_operation) != operation:
        return False

    supports = option.get("supports")
    if isinstance(supports, dict):
        if supports.get(operation) is False:
            return False
        if operation == "text_to_video" and supports.get("supports_t2v") is False:
            return False
        if operation == "image_to_video" and supports.get("supports_i2v") is False:
            return False

    return True


def _preset_sort_key(row: dict[str, Any], preset: str) -> tuple[Any, ...]:
    option = row["option"]
    default_rank = 0 if _is_default_option(row["choice"], option) else 1
    deprecated_rank = 1 if option.get("deprecated") else 0
    quality = _score_text(option.get("quality"), _QUALITY_SCORE)
    speed = _score_text(option.get("speed"), _SPEED_SCORE)
    cost = _cost_usd(option)
    has_cost = 0 if cost is not None else 1
    cost_value = cost if cost is not None else float("inf")

    if preset == "fast":
        return (deprecated_rank, -speed, default_rank, -quality, has_cost, cost_value, row["model_id"])
    if preset == "highest_quality":
        return (deprecated_rank, -quality, default_rank, -speed, has_cost, cost_value, row["model_id"])
    if preset == "lowest_cost":
        return (deprecated_rank, has_cost, cost_value, -speed, -quality, default_rank, row["model_id"])
    if preset == "balanced":
        return (deprecated_rank, -(quality + speed), default_rank, has_cost, cost_value, row["model_id"])
    return (deprecated_rank, default_rank, has_cost, cost_value, -quality, -speed, row["model_id"])


def _normalize_preset(preset: str) -> str:
    normalized = _PRESET_ALIASES.get(preset, preset)
    if normalized not in PRESETS:
        raise ValueError(
            f"Unknown preset {preset!r}. Choose one of: {', '.join(PRESETS)}."
        )
    return normalized


def _is_default_option(choice: dict[str, Any], option: dict[str, Any]) -> bool:
    option_id = option.get("id")
    choice_default = choice.get("default")
    return bool(option.get("default")) or (
        option_id is not None
        and (
            option_id == choice_default
            or (isinstance(choice_default, list) and option_id in choice_default)
        )
    )


def _option_details(option: dict[str, Any]) -> str:
    details: list[str] = []
    if option.get("deprecated"):
        details.append("deprecated")
    release_stage = option.get("release_stage")
    if release_stage:
        details.append(f"stage: {str(release_stage).replace('_', ' ')}")
    if option.get("quality"):
        details.append(f"quality: {str(option['quality']).replace('_', ' ')}")
    if option.get("speed"):
        details.append(f"speed: {option['speed']}")
    cost_hint = option.get("cost_hint")
    cost = _cost_usd(option)
    if isinstance(cost_hint, dict) and cost is not None:
        unit = str(cost_hint.get("unit") or "unit").replace("_", " ")
        details.append(f"cost: {_format_usd(cost)} {unit}")
    note = option.get("note")
    if note:
        details.append(str(note))
    last_verified = option.get("last_verified")
    if last_verified:
        details.append(f"verified: {last_verified}")
    return "; ".join(details)


def _format_selection_preview(
    env_path: Path,
    selection: ModelPreferenceSelection,
) -> str:
    keys = env_keys_for_capability(selection.capability)
    return "\n".join(
        [
            f"Env preview for {env_path}:",
            f"  {keys['provider']}={selection.provider or ''}",
            f"  {keys['model']}={selection.model_id}",
            f"  selected model = {selection.model_name}",
            f"  preset = {selection.preset}",
        ]
    )


def _read_env_mapping(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        key = key.strip()
        if key.startswith("export "):
            key = key[len("export "):].strip()
        values[key] = _clean_env_value(value)
    return values


def _write_env_values(path: Path, values: dict[str, str]) -> None:
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    pending = dict(values)
    lines: list[str] = []
    for line in existing.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            lines.append(line)
            continue
        key, _, _value = stripped.partition("=")
        raw_key = key.strip()
        prefix = "export " if raw_key.startswith("export ") else ""
        clean_key = raw_key[len("export "):].strip() if prefix else raw_key
        if clean_key in pending:
            lines.append(f"{prefix}{clean_key}={pending.pop(clean_key)}")
        else:
            lines.append(line)
    if pending and lines and lines[-1].strip():
        lines.append("")
    for key, value in pending.items():
        lines.append(f"{key}={value}")
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def _clean_env_value(value: str) -> str:
    value = value.strip()
    if value.startswith(("'", '"')):
        quote = value[0]
        end = value.find(quote, 1)
        return value[1:end] if end > 0 else value.strip(quote)
    for sep in ("  #", "\t#", " #"):
        idx = value.find(sep)
        if idx != -1:
            value = value[:idx].rstrip()
            break
    if value.startswith("#"):
        return ""
    return value


def _capabilities_from_env(env: dict[str, str]) -> list[str]:
    capabilities: set[str] = set()
    suffixes = (
        "_ALLOWED_PROVIDERS",
        "_MODEL_VARIANT",
        "_MODEL_ID",
        "_PROVIDER",
        "_MODEL",
    )
    for key in env:
        if not key.startswith("VPB_"):
            continue
        for suffix in suffixes:
            if key.endswith(suffix):
                capabilities.add(key[len("VPB_"):-len(suffix)].lower())
                break
    return sorted(capabilities)


def _score_text(value: Any, scores: dict[str, int]) -> int:
    if value is None:
        return -1
    normalized = str(value).strip().lower().replace("-", "_")
    return scores.get(normalized, 0)


def _cost_usd(option: dict[str, Any]) -> float | None:
    cost_hint = option.get("cost_hint")
    if not isinstance(cost_hint, dict):
        return None
    try:
        return float(cost_hint["usd"])
    except (KeyError, TypeError, ValueError):
        return None


def _format_usd(cost: float) -> str:
    if cost == 0 or abs(cost) >= 0.01:
        return f"${cost:.2f}"
    formatted = format(Decimal(str(cost)).normalize(), "f")
    return f"${formatted}"


def _choice_sort_key(choice: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(choice.get("capability") or ""),
        str(choice.get("provider") or ""),
        str(choice.get("tool") or ""),
    )


def _capability_label(capability: str | None) -> str:
    if not capability:
        return "Model choices"
    return capability.replace("_", " ").capitalize()


def _prompt_choice(
    label: str,
    options: Sequence[str],
    *,
    default: str | None = None,
) -> str:
    if not options:
        raise ValueError(f"No {label.lower()} options are available.")
    for index, option in enumerate(options, start=1):
        default_marker = " [default]" if option == default else ""
        print(f"  {index}. {option}{default_marker}")
    while True:
        suffix = f" [{default}]" if default else ""
        answer = input(f"{label}{suffix}: ").strip()
        if not answer and default:
            return default
        if answer.isdigit():
            index = int(answer)
            if 1 <= index <= len(options):
                return options[index - 1]
        if answer in options:
            return answer
        print("Choose a listed number or value.")


def _prompt_optional(label: str) -> str | None:
    answer = input(f"{label}: ").strip()
    return answer or None


def _confirm(label: str) -> bool:
    answer = input(f"{label} [y/N]: ").strip().lower()
    return answer in {"y", "yes"}


if __name__ == "__main__":
    raise SystemExit(main())
