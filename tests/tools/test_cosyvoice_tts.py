from __future__ import annotations

import pytest

from tools.audio.cosyvoice_tts import CosyVoiceTTS


def test_qwen_tts_rejects_instructions_on_non_instruct_model(monkeypatch: pytest.MonkeyPatch) -> None:
    """Delivery instructions must never be silently dropped by qwen3-tts-flash."""

    def fail_if_called(*args, **kwargs):
        raise AssertionError("network call should not happen for an invalid instruction/model pair")

    monkeypatch.setattr("requests.post", fail_if_called)

    with pytest.raises(ValueError, match="instructions require qwen3-tts-instruct-flash"):
        CosyVoiceTTS()._generate_qwen(
            {
                "text": "A quiet reveal.",
                "voice": "Serena",
                "instructions": "Hushed, intimate, and slower on the product reveal.",
            },
            api_key="fake-key",
            model="qwen3-tts-flash",
        )
