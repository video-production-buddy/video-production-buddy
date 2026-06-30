"""Helpers for exposing provider model choices in registry metadata."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def build_model_options(
    models: Mapping[str, Mapping[str, Any]],
    *,
    field: str,
    default: str | None = None,
    default_by_operation: Mapping[str, str] | None = None,
    cost_units: Mapping[str, str] | None = None,
    include_keys: tuple[str, ...] = (
        "operation",
        "quality",
        "speed",
        "family",
        "note",
        "max_duration",
        "max_n",
        "native_audio",
        "api_style",
        "release_stage",
        "deprecated",
        "last_verified",
        "source_url",
        "requires_api_key",
        "compatibility",
    ),
    support_keys: tuple[str, ...] = (),
) -> list[dict[str, Any]]:
    """Build JSON-safe model metadata from a provider module's model registry."""
    reverse_defaults: dict[str, list[str]] = {}
    for operation, model_id in (default_by_operation or {}).items():
        reverse_defaults.setdefault(model_id, []).append(operation)

    options: list[dict[str, Any]] = []
    for model_id, meta in models.items():
        option: dict[str, Any] = {
            "id": model_id,
            "name": meta.get("name", model_id),
            "field": field,
        }
        if default is not None:
            option["default"] = model_id == default
        if model_id in reverse_defaults:
            option["default_for_operations"] = sorted(reverse_defaults[model_id])

        for key in include_keys:
            if key in meta:
                option[key] = meta[key]

        for cost_key, unit in (cost_units or {}).items():
            if cost_key in meta:
                option["cost_hint"] = {"usd": meta[cost_key], "unit": unit}
                break

        supports = {key: bool(meta[key]) for key in support_keys if key in meta}
        if supports:
            option["supports"] = supports

        options.append(option)

    return options
