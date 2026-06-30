from __future__ import annotations

import pytest

from lib.model_settings_wizard import (
    ModelPreferenceSelection,
    format_model_choices_for_user,
    select_model_preference,
    validate_model_preferences,
    write_model_preference,
)


MODEL_CHOICES = [
    {
        "capability": "video_generation",
        "tool": "seedance_video",
        "provider": "seedance",
        "status": "available",
        "field": "model_variant",
        "default": "quality-model",
        "options": [
            {
                "id": "quality-model",
                "name": "Quality Model",
                "field": "model_variant",
                "default": True,
                "quality": "highest",
                "speed": "medium",
                "cost_hint": {"usd": 0.25, "unit": "per_5s"},
                "release_stage": "current_sota",
                "last_verified": "2026-06-28",
            },
            {
                "id": "fast-model",
                "name": "Fast Model",
                "field": "model_variant",
                "quality": "high",
                "speed": "fast",
                "cost_hint": {"usd": 0.10, "unit": "per_5s"},
            },
        ],
    },
    {
        "capability": "video_generation",
        "tool": "slow_unavailable_video",
        "provider": "slow",
        "status": "unavailable",
        "field": "model_variant",
        "default": "slow-cheap",
        "options": [
            {
                "id": "slow-cheap",
                "name": "Slow Cheap",
                "field": "model_variant",
                "default": True,
                "quality": "low",
                "speed": "slow",
                "cost_hint": {"usd": 0.01, "unit": "per_5s"},
            }
        ],
    },
    {
        "capability": "tts",
        "tool": "minimax_tts",
        "provider": "minimax",
        "status": "available",
        "field": "model_id",
        "default": "speech-2.8-hd",
        "options": [
            {
                "id": "speech-2.8-hd",
                "name": "Speech 2.8 HD",
                "field": "model_id",
                "default": True,
                "quality": "highest",
                "speed": "medium",
            }
        ],
    },
]


def test_format_model_choices_for_user_is_plain_language() -> None:
    text = format_model_choices_for_user(MODEL_CHOICES, capability="video_generation")

    assert "Video generation" in text
    assert "seedance" in text
    assert "Quality Model" in text
    assert "Fast Model" in text
    assert "stage: current sota" in text
    assert "verified: 2026-06-28" in text
    assert "$0.10 per 5s" in text
    assert "slow_unavailable_video" in text
    assert "unavailable" in text
    assert "minimax_tts" not in text
    assert "model_choices" not in text
    assert "{" not in text


def test_format_model_choices_marks_operation_defaults() -> None:
    choices = [
        {
            "capability": "video_generation",
            "tool": "wan_video_api",
            "provider": "bailian",
            "status": "available",
            "field": "model_variant",
            "default": ["happyhorse-1.1-t2v", "happyhorse-1.1-i2v"],
            "options": [
                {"id": "happyhorse-1.1-t2v", "name": "HappyHorse T2V"},
                {"id": "happyhorse-1.1-i2v", "name": "HappyHorse I2V"},
                {"id": "wan2.7-t2v", "name": "Wan 2.7 T2V"},
            ],
        }
    ]

    text = format_model_choices_for_user(choices, capability="video_generation")

    assert "HappyHorse T2V (happyhorse-1.1-t2v) [default]" in text
    assert "HappyHorse I2V (happyhorse-1.1-i2v) [default]" in text
    assert "Wan 2.7 T2V (wan2.7-t2v) [default]" not in text


def test_format_model_choices_preserves_small_nonzero_unit_costs() -> None:
    choices = [
        {
            "capability": "tts",
            "tool": "cosyvoice_tts",
            "provider": "bailian",
            "status": "available",
            "field": "model_id",
            "default": "qwen3-tts-flash",
            "options": [
                {
                    "id": "qwen3-tts-flash",
                    "name": "Qwen3 TTS Flash",
                    "field": "model_id",
                    "cost_hint": {"usd": 0.000014, "unit": "per_char"},
                }
            ],
        }
    ]

    text = format_model_choices_for_user(choices, capability="tts")

    assert "$0.000014 per char" in text
    assert "$0.00 per char" not in text


def test_select_model_preference_uses_preset_without_picking_unavailable_models() -> None:
    selection = select_model_preference(
        MODEL_CHOICES,
        capability="video_generation",
        preset="lowest_cost",
    )

    assert selection.capability == "video_generation"
    assert selection.provider == "seedance"
    assert selection.tool == "seedance_video"
    assert selection.field == "model_variant"
    assert selection.model_id == "fast-model"


def test_select_model_preference_fast_preset_skips_i2v_only_video_models() -> None:
    model_choices = [
        {
            "capability": "video_generation",
            "tool": "minimax_video",
            "provider": "minimax",
            "status": "available",
            "field": "model_variant",
            "default": "MiniMax-Hailuo-2.3",
            "options": [
                {
                    "id": "MiniMax-Hailuo-2.3",
                    "name": "MiniMax Hailuo 2.3",
                    "field": "model_variant",
                    "quality": "highest",
                    "speed": "medium",
                    "supports": {"supports_t2v": True, "supports_i2v": True},
                },
                {
                    "id": "MiniMax-Hailuo-2.3-Fast",
                    "name": "MiniMax Hailuo 2.3 Fast",
                    "field": "model_variant",
                    "quality": "high",
                    "speed": "fast",
                    "supports": {"supports_t2v": False, "supports_i2v": True},
                },
            ],
        }
    ]

    selection = select_model_preference(
        model_choices,
        capability="video_generation",
        preset="fast",
    )

    assert selection.model_id == "MiniMax-Hailuo-2.3"


def test_select_model_preference_accepts_explicit_provider_and_model() -> None:
    selection = select_model_preference(
        MODEL_CHOICES,
        capability="tts",
        provider="minimax",
        model_id="speech-2.8-hd",
    )

    assert selection.provider == "minimax"
    assert selection.field == "model_id"
    assert selection.model_id == "speech-2.8-hd"


def test_select_model_preference_preserves_explicit_tool_name(tmp_path) -> None:
    model_choices = [
        *MODEL_CHOICES,
        {
            "capability": "video_generation",
            "tool": "seedance_replicate",
            "provider": "seedance",
            "status": "available",
            "field": "model_variant",
            "default": "replicate-fast",
            "options": [
                {
                    "id": "replicate-fast",
                    "name": "Replicate Fast",
                    "field": "model_variant",
                    "quality": "high",
                    "speed": "fast",
                }
            ],
        },
    ]

    selection = select_model_preference(
        model_choices,
        capability="video_generation",
        provider="seedance_replicate",
        model_id="replicate-fast",
    )
    assert selection.provider == "seedance_replicate"
    assert selection.tool == "seedance_replicate"

    env_path = tmp_path / ".env"
    write_model_preference(env_path, selection)

    text = env_path.read_text(encoding="utf-8")
    assert "VPB_VIDEO_GENERATION_PROVIDER=seedance_replicate" in text
    assert "VPB_VIDEO_GENERATION_MODEL=replicate-fast" in text


def test_select_model_preference_rejects_unknown_model_with_clear_message() -> None:
    with pytest.raises(ValueError, match="not-a-model.*video_generation"):
        select_model_preference(
            MODEL_CHOICES,
            capability="video_generation",
            model_id="not-a-model",
        )


def test_write_model_preference_updates_only_selected_capability(tmp_path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text(
        """
MINIMAX_API_KEY=test-key
VPB_IMAGE_GENERATION_PROVIDER=bailian
VPB_IMAGE_GENERATION_MODEL=qwen-image-2.0-pro
""".lstrip(),
        encoding="utf-8",
    )
    selection = ModelPreferenceSelection(
        capability="video_generation",
        provider="seedance",
        tool="seedance_video",
        field="model_variant",
        model_id="fast-model",
        model_name="Fast Model",
        preset="lowest_cost",
    )

    write_model_preference(env_path, selection)

    text = env_path.read_text(encoding="utf-8")
    assert "MINIMAX_API_KEY=test-key" in text
    assert "VPB_IMAGE_GENERATION_PROVIDER=bailian" in text
    assert "VPB_IMAGE_GENERATION_MODEL=qwen-image-2.0-pro" in text
    assert "VPB_VIDEO_GENERATION_PROVIDER=seedance" in text
    assert "VPB_VIDEO_GENERATION_MODEL=fast-model" in text


def test_validate_model_preferences_accepts_env_file_settings(tmp_path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text(
        """
DASHSCOPE_API_KEY=test-key
VPB_VIDEO_GENERATION_PROVIDER=seedance
VPB_VIDEO_GENERATION_MODEL=fast-model
MINIMAX_API_KEY=test-key
VPB_TTS_PROVIDER=minimax
VPB_TTS_MODEL=speech-2.8-hd
""".lstrip(),
        encoding="utf-8",
    )

    issues = validate_model_preferences(env_path, MODEL_CHOICES)

    assert issues == []


def test_validate_model_preferences_accepts_allowed_provider_shortlist(tmp_path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text(
        """
VPB_VIDEO_GENERATION_ALLOWED_PROVIDERS=seedance,seedance_video
""".lstrip(),
        encoding="utf-8",
    )

    issues = validate_model_preferences(env_path, MODEL_CHOICES)

    assert issues == []


def test_validate_model_preferences_reports_unknown_allowed_provider(tmp_path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text(
        """
VPB_VIDEO_GENERATION_ALLOWED_PROVIDERS=seedance,typo-provider
""".lstrip(),
        encoding="utf-8",
    )

    issues = validate_model_preferences(env_path, MODEL_CHOICES)

    assert len(issues) == 1
    assert issues[0].capability == "video_generation"
    assert "typo-provider" in issues[0].message
    assert "make models-list CAPABILITY=video_generation" in issues[0].message


def test_validate_model_preferences_reports_provider_outside_shortlist(tmp_path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text(
        """
VPB_VIDEO_GENERATION_PROVIDER=seedance
VPB_VIDEO_GENERATION_ALLOWED_PROVIDERS=slow
""".lstrip(),
        encoding="utf-8",
    )

    issues = validate_model_preferences(env_path, MODEL_CHOICES)

    assert len(issues) == 1
    assert issues[0].capability == "video_generation"
    assert "not included" in issues[0].message


def test_validate_model_preferences_reports_model_outside_shortlist(tmp_path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text(
        """
VPB_VIDEO_GENERATION_MODEL=fast-model
VPB_VIDEO_GENERATION_ALLOWED_PROVIDERS=slow
""".lstrip(),
        encoding="utf-8",
    )

    issues = validate_model_preferences(env_path, MODEL_CHOICES)

    assert len(issues) == 1
    assert issues[0].capability == "video_generation"
    assert "fast-model" in issues[0].message


def test_validate_model_preferences_reports_unknown_env_model_with_suggested_list_command(
    tmp_path,
) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text(
        """
VPB_VIDEO_GENERATION_PROVIDER=seedance
VPB_VIDEO_GENERATION_MODEL=typo-model
""".lstrip(),
        encoding="utf-8",
    )

    issues = validate_model_preferences(env_path, MODEL_CHOICES)

    assert len(issues) == 1
    assert issues[0].capability == "video_generation"
    assert "typo-model" in issues[0].message
    assert ".env" in issues[0].message
    assert "make models-list CAPABILITY=video_generation" in issues[0].message


def test_validate_model_preferences_rejects_i2v_only_video_default(tmp_path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text(
        """
VPB_VIDEO_GENERATION_PROVIDER=minimax
VPB_VIDEO_GENERATION_MODEL=MiniMax-Hailuo-2.3-Fast
""".lstrip(),
        encoding="utf-8",
    )
    model_choices = [
        {
            "capability": "video_generation",
            "tool": "minimax_video",
            "provider": "minimax",
            "status": "available",
            "field": "model_variant",
            "default": "MiniMax-Hailuo-2.3",
            "options": [
                {
                    "id": "MiniMax-Hailuo-2.3-Fast",
                    "name": "MiniMax Hailuo 2.3 Fast",
                    "field": "model_variant",
                    "quality": "high",
                    "speed": "fast",
                    "supports": {"supports_t2v": False, "supports_i2v": True},
                }
            ],
        }
    ]

    issues = validate_model_preferences(env_path, model_choices)

    assert len(issues) == 1
    assert issues[0].capability == "video_generation"
    assert "MiniMax-Hailuo-2.3-Fast" in issues[0].message
    assert "default text_to_video" in issues[0].message
