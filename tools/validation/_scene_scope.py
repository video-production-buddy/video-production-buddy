"""Shared scene-id scope validation for ad-video gates."""

from __future__ import annotations

from collections import Counter
from typing import Any


def validate_scene_id_list(value: Any, field_name: str) -> tuple[list[str], list[str], bool]:
    """Return normalized scene ids, issues, and whether callers may iterate them."""
    if not isinstance(value, list):
        return (
            [],
            [f"{field_name} must be a list of non-empty scene id strings."],
            False,
        )

    invalid_indexes = [
        idx
        for idx, scene_id in enumerate(value)
        if not isinstance(scene_id, str) or not scene_id.strip()
    ]
    if invalid_indexes:
        return (
            [],
            [
                f"{field_name} must contain only non-empty scene id strings; "
                f"invalid entries at indexes {invalid_indexes}."
            ],
            False,
        )

    duplicate_ids = sorted(
        scene_id for scene_id, count in Counter(value).items() if count > 1
    )
    issues = [
        f"{field_name} contains duplicate scene ids: {duplicate_ids}."
    ] if duplicate_ids else []
    return value, issues, True
