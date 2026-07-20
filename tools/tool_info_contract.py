"""Shared field names for normalized tool metadata."""

LIST_INFO_FIELDS = (
    "dependencies",
    "capabilities",
    "best_for",
    "not_good_for",
    "model_options",
    "idempotency_key_fields",
    "side_effects",
    "fallback_tools",
    "agent_skills",
    "related_skills",
    "user_visible_verification",
)

DICT_INFO_FIELDS = (
    "input_schema",
    "output_schema",
    "artifact_schema",
    "supports",
    "provider_matrix",
)

MODEL_FIELD_NAMES = ("model_variant", "model_id", "model", "resource_id")
