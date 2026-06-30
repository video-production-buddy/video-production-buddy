"""Apply optional user model preferences from .env to selector inputs."""

from __future__ import annotations

import os
from typing import Any, Mapping

from lib.dotenv_loader import load_dotenv


_CAPABILITY_MODEL_FIELDS = {
    "tts": "model_id",
    "video_generation": "model_variant",
}
_PREFERENCE_FIELDS = (
    "preferred_provider",
    "allowed_providers",
    "model_variant",
    "model_id",
    "model",
)


def apply_model_preferences(
    inputs: dict[str, Any],
    capability: str,
) -> dict[str, Any]:
    """Merge .env provider/model defaults without overriding explicit inputs."""
    preferences = env_model_preferences(capability)
    if not preferences:
        return dict(inputs)

    merged = dict(inputs)
    explicit_provider = _has_explicit_concrete_provider(inputs)
    explicit_provider_scope = explicit_provider or _has_explicit_allowed_providers(inputs)
    explicit_model = _has_explicit_model(inputs, capability)
    for field in _PREFERENCE_FIELDS:
        if explicit_provider_scope and field in {"preferred_provider", "allowed_providers"}:
            continue
        if field in _MODEL_PREFERENCE_FIELDS and (
            explicit_model or explicit_provider_scope
        ):
            continue
        if field in merged and not _is_auto_provider(field, merged[field]):
            continue
        value = preferences.get(field)
        if value is None:
            continue
        if field == "allowed_providers" and not value:
            continue
        merged[field] = list(value) if field == "allowed_providers" else value

    return merged


def filter_model_candidates(
    inputs: Mapping[str, Any],
    capability: str,
    candidates: list[Any],
) -> list[Any]:
    """Restrict provider candidates to those that advertise the requested model."""
    model_field = model_field_for_capability(capability)
    model = _input_model_value(inputs, model_field)
    if model is None:
        return list(candidates)

    operation = _input_operation_value(inputs, capability)
    return [
        tool for tool in candidates
        if _tool_supports_model(tool, model_field, model, operation=operation)
    ]


def env_model_preferences(
    capability: str,
    *,
    environ: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Return selector preference fields from VPB_* environment variables."""
    if environ is None:
        load_dotenv()
        environ = os.environ

    prefix = _env_prefix(capability)
    model_field = model_field_for_capability(capability)
    preferences: dict[str, Any] = {}

    provider = _env_value(environ, f"{prefix}_PROVIDER")
    if provider:
        preferences["preferred_provider"] = provider

    allowed = _split_csv(_env_value(environ, f"{prefix}_ALLOWED_PROVIDERS"))
    if allowed:
        preferences["allowed_providers"] = allowed

    model = _env_value(environ, f"{prefix}_{model_field.upper()}")
    if not model:
        model = _env_value(environ, f"{prefix}_MODEL")
    if model:
        preferences[model_field] = model

    return preferences


def model_field_for_capability(capability: str) -> str:
    """Return the selector input field that should receive VPB_*_MODEL."""
    return _CAPABILITY_MODEL_FIELDS.get(capability, "model")


def env_keys_for_capability(capability: str) -> dict[str, str]:
    """Expose the beginner-facing .env keys for a model-capable selector."""
    prefix = _env_prefix(capability)
    return {
        "provider": f"{prefix}_PROVIDER",
        "model": f"{prefix}_MODEL",
        "allowed_providers": f"{prefix}_ALLOWED_PROVIDERS",
    }


def _env_prefix(capability: str) -> str:
    return f"VPB_{capability.upper()}"


def _is_auto_provider(field: str, value: Any) -> bool:
    return field == "preferred_provider" and str(value).strip().lower() == "auto"


def _has_explicit_concrete_provider(inputs: Mapping[str, Any]) -> bool:
    provider = inputs.get("preferred_provider")
    if provider is None:
        return False
    provider = str(provider).strip()
    return bool(provider) and provider.lower() != "auto"


_MODEL_PREFERENCE_FIELDS = {"model_variant", "model_id", "model", "resource_id"}


def _has_explicit_allowed_providers(inputs: Mapping[str, Any]) -> bool:
    allowed = inputs.get("allowed_providers")
    if not allowed:
        return False
    if isinstance(allowed, str):
        return bool(allowed.strip())
    try:
        return any(str(item).strip() for item in allowed)
    except TypeError:
        return False


def _has_explicit_model(inputs: Mapping[str, Any], capability: str) -> bool:
    return _input_model_value(inputs, model_field_for_capability(capability)) is not None


def _input_model_value(inputs: Mapping[str, Any], model_field: str) -> str | None:
    for field in _compatible_model_fields(model_field):
        value = inputs.get(field)
        if value is None:
            continue
        value = str(value).strip()
        if value:
            return value
    return None


def _input_operation_value(
    inputs: Mapping[str, Any],
    capability: str,
) -> str | None:
    operation = inputs.get("operation")
    if operation == "rank":
        operation = inputs.get("target_operation")
    if operation is None and capability == "video_generation":
        operation = "text_to_video"
    if operation is None:
        return None
    operation = str(operation).strip()
    return operation or None


def _tool_supports_model(
    tool: Any,
    model_field: str,
    model: str,
    *,
    operation: str | None = None,
) -> bool:
    model_fields = _compatible_model_fields(model_field)
    model_options = getattr(tool, "model_options", None) or []
    if model_options:
        return any(
            isinstance(option, Mapping)
            and str(option.get("field") or model_field) in model_fields
            and str(option.get("id")) == model
            and _model_option_supports_operation(option, operation)
            for option in model_options
        )

    input_schema = getattr(tool, "input_schema", {}) or {}
    properties = input_schema.get("properties", {})
    if not isinstance(properties, Mapping):
        return False

    model_property = None
    for candidate_field in model_fields:
        candidate_property = properties.get(candidate_field)
        if isinstance(candidate_property, Mapping):
            model_property = candidate_property
            break
    if model_property is None:
        return False

    enum_values = model_property.get("enum")
    if isinstance(enum_values, list):
        return any(str(value) == model for value in enum_values)

    default = model_property.get("default")
    if default is not None and str(default) == model:
        return True
    if default is not None:
        return False

    return True


def _model_option_supports_operation(
    option: Mapping[str, Any],
    operation: str | None,
) -> bool:
    if not operation:
        return True

    option_operation = option.get("operation")
    if option_operation and str(option_operation) != operation:
        return False

    supports = option.get("supports")
    if isinstance(supports, Mapping):
        if supports.get(operation) is False:
            return False
        if operation == "text_to_video" and supports.get("supports_t2v") is False:
            return False
        if operation == "image_to_video" and supports.get("supports_i2v") is False:
            return False

    return True


def _compatible_model_fields(model_field: str) -> tuple[str, ...]:
    if model_field == "model_id":
        return ("model_id", "model", "resource_id")
    if model_field == "model_variant":
        return ("model_variant", "model")
    return (model_field,)


def _env_value(environ: Mapping[str, str], key: str) -> str | None:
    value = environ.get(key)
    if value is None:
        return None
    value = value.strip()
    return value or None


def _split_csv(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]
