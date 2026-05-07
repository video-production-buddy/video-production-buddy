"""TDD regression test for CosyVoiceTTS.retry_policy actually being honored.

Until this fix, `retry_policy = RetryPolicy(max_retries=2, retryable_errors=...)`
was declared on the tool but never consumed — execute() caught any exception
once and returned failure. This test pins the wiring so it can't silently
revert.

Pattern: every tool that declares a non-zero retry_policy should pass these
checks once the BaseTool template-method retry helper is generalized. For now
it's a CosyVoiceTTS-specific fixture.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from tools.audio.cosyvoice_tts import CosyVoiceTTS
from tools.base_tool import ToolResult


@pytest.fixture(autouse=True)
def _stub_api_key(monkeypatch):
    """Make _get_api_key() pass so we exercise the retry path, not the auth gate."""
    monkeypatch.setenv("DASHSCOPE_API_KEY", "test_key_synthetic_value")


def _ok_result() -> ToolResult:
    return ToolResult(success=True, data={"path": "/tmp/synthetic.mp3"})


class TestCosyVoiceTTSRetryWiring:
    """RetryPolicy is data; these tests pin that it actually drives behavior."""

    def test_transient_then_success_retries_once(self):
        # Arrange — fail once with a retryable error, then succeed.
        tool = CosyVoiceTTS()
        gen = MagicMock(side_effect=[RuntimeError("rate_limit exceeded"), _ok_result()])
        # Act
        with patch.object(tool, "_generate_qwen", gen), \
             patch("tools.audio.cosyvoice_tts.time.sleep"):
            result = tool.execute({"text": "hi"})
        # Assert — the retry policy declares max_retries=2, so one transient
        # failure followed by success must produce a successful ToolResult and
        # exactly two calls to the underlying generator.
        assert result.success is True, f"expected success after retry, got error={result.error!r}"
        assert gen.call_count == 2, (
            f"expected 2 calls (1 initial + 1 retry), got {gen.call_count}"
        )

    def test_exhausted_retries_returns_failure(self):
        # Arrange — three retryable failures in a row.
        tool = CosyVoiceTTS()
        gen = MagicMock(side_effect=[
            RuntimeError("rate_limit"),
            RuntimeError("rate_limit"),
            RuntimeError("rate_limit"),
        ])
        # Act
        with patch.object(tool, "_generate_qwen", gen), \
             patch("tools.audio.cosyvoice_tts.time.sleep"):
            result = tool.execute({"text": "hi"})
        # Assert — max_retries=2 means 1 initial + 2 retries = 3 total attempts.
        # After the third failure the tool surfaces a failed ToolResult.
        assert result.success is False
        assert gen.call_count == 3, (
            f"expected 3 calls (1 initial + 2 retries), got {gen.call_count}"
        )
        assert "rate_limit" in (result.error or "")

    def test_non_retryable_error_fails_fast(self):
        # Arrange — an exception whose message matches none of the
        # retryable_errors patterns ("rate_limit", "timeout").
        tool = CosyVoiceTTS()
        gen = MagicMock(side_effect=RuntimeError("malformed_input: bad voice id"))
        # Act
        with patch.object(tool, "_generate_qwen", gen), \
             patch("tools.audio.cosyvoice_tts.time.sleep"):
            result = tool.execute({"text": "hi"})
        # Assert — non-retryable errors must fail immediately. No retries.
        assert result.success is False
        assert gen.call_count == 1, (
            f"non-retryable error must not retry; got {gen.call_count} calls"
        )
