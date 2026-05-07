from __future__ import annotations

import builtins
from typing import Any

import pytest

from lib.scoring import ProviderScore
from tools.audio.audio_enhance import AudioEnhance
from tools.audio.cosyvoice_tts import CosyVoiceTTS
from tools.audio.doubao_tts import DoubaoTTS
from tools.audio.elevenlabs_tts import ElevenLabsTTS
from tools.audio.google_tts import GoogleTTS
from tools.audio.minimax_music import MinimaxMusic
from tools.audio.music_gen import MusicGen
from tools.audio.openai_tts import OpenAITTS
from tools.audio.piper_tts import PiperTTS
from tools.audio.qwen_asr import QwenASR
from tools.audio.suno_music import SunoMusic
from tools.audio.tts_selector import TTSSelector
from tools.base_tool import ToolResult, ToolStatus


class _FakeTTSProvider:
    def __init__(self, name: str, provider: str, props: dict[str, object]) -> None:
        self.name = name
        self.provider = provider
        self.best_for: list[str] = []
        self.agent_skills: list[str] = []
        self.input_schema = {"properties": props}
        self.supports: dict[str, object] = {}
        self.calls: list[dict[str, object]] = []

    def get_status(self) -> ToolStatus:
        return ToolStatus.AVAILABLE

    def get_info(self) -> dict[str, object]:
        return {
            "name": self.name,
            "provider": self.provider,
            "agent_skills": self.agent_skills,
            "usage_location": __file__,
            "best_for": self.best_for,
            "supports": self.supports,
        }

    def estimate_cost(self, _inputs: dict[str, object]) -> float:
        return 0.0

    def execute(self, inputs: dict[str, object]) -> ToolResult:
        self.calls.append(dict(inputs))
        return ToolResult(success=True, data={"output": "voice.mp3"})


def _rank_as(*providers: _FakeTTSProvider) -> list[ProviderScore]:
    return [
        ProviderScore(tool_name=tool.name, provider=tool.provider, task_fit=1.0 - idx / 10)
        for idx, tool in enumerate(providers)
    ]


def test_tts_selector_allows_concrete_tool_names_in_normal_selection(monkeypatch):
    selector = TTSSelector()
    allowed = _FakeTTSProvider("openai_tts", "openai", {"text": {"type": "string"}})
    blocked = _FakeTTSProvider("google_tts", "google_tts", {"text": {"type": "string"}})
    monkeypatch.setattr("lib.scoring.rank_providers", lambda _candidates, _ctx: _rank_as(allowed))

    selected, score = selector._select_best_tool(
        {"text": "Narration", "allowed_providers": ["openai_tts"]},
        [allowed, blocked],
        selector._prepare_task_context({"text": "Narration"}),
    )

    assert selected is allowed
    assert score.tool_name == "openai_tts"


def test_tts_selector_maps_locked_voice_model_and_format_to_provider_contract(monkeypatch):
    selector = TTSSelector()
    openai_like = _FakeTTSProvider(
        "openai_tts",
        "openai",
        {
            "text": {"type": "string"},
            "voice": {"type": "string"},
            "model": {"type": "string"},
            "format": {"type": "string"},
            "speed": {"type": "number"},
            "output_path": {"type": "string"},
        },
    )
    monkeypatch.setattr(selector, "_providers", lambda: [openai_like])
    monkeypatch.setattr("lib.scoring.rank_providers", lambda candidates, _ctx: _rank_as(*candidates))

    result = selector.execute(
        {
            "text": "A precise narration line.",
            "voice_id": "alloy",
            "model_id": "gpt-4o-mini-tts",
            "output_format": "wav",
            "speed": 0.95,
            "preferred_provider": "openai",
            "allowed_providers": ["openai_tts"],
            "operation": "generate",
            "output_path": "assets/audio/hook.wav",
        }
    )

    assert result.success
    assert openai_like.calls[0] == {
        "text": "A precise narration line.",
        "voice": "alloy",
        "model": "gpt-4o-mini-tts",
        "format": "wav",
        "speed": 0.95,
        "output_path": "assets/audio/hook.wav",
    }


def test_openai_tts_schema_declares_speed_used_by_asset_director():
    assert "speed" in OpenAITTS.input_schema["properties"]
    assert "speed" in OpenAITTS.idempotency_key_fields


def test_cosyvoice_rejects_unknown_model_before_network(monkeypatch):
    monkeypatch.setenv("DASHSCOPE_API_KEY", "test-key")
    calls: list[object] = []

    def fake_post(*args: object, **kwargs: object) -> object:
        calls.append((args, kwargs))
        raise AssertionError("network should not be called for unsupported models")

    monkeypatch.setattr("requests.post", fake_post)

    result = CosyVoiceTTS().execute({"text": "hello", "model": "not-a-real-model"})

    assert not result.success
    assert "Unsupported model" in (result.error or "")
    assert calls == []


def test_minimax_music_rejects_unknown_model_before_network(monkeypatch):
    monkeypatch.setenv("MINIMAX_API_KEY", "test-key")
    calls: list[object] = []

    def fake_post(*args: object, **kwargs: object) -> object:
        calls.append((args, kwargs))
        raise AssertionError("network should not be called for unsupported models")

    monkeypatch.setattr("requests.post", fake_post)

    result = MinimaxMusic().execute({"prompt": "tense cinematic bed", "model": "not-real"})

    assert not result.success
    assert "Unsupported model" in (result.error or "")
    assert calls == []


def test_music_gen_missing_duration_returns_tool_error_before_network(monkeypatch):
    monkeypatch.setenv("ELEVENLABS_API_KEY", "test-key")
    calls: list[object] = []

    def fake_post(*args: object, **kwargs: object) -> object:
        calls.append((args, kwargs))
        raise AssertionError("network should not be called without duration_seconds")

    monkeypatch.setattr("requests.post", fake_post)

    result = MusicGen().execute({"prompt": "cinematic ambient bed"})

    assert not result.success
    assert "duration_seconds is required" in (result.error or "")
    assert calls == []


def test_suno_custom_mode_requires_style_and_title_before_network(monkeypatch):
    monkeypatch.setenv("SUNO_API_KEY", "test-key")
    calls: list[object] = []

    def fake_post(*args: object, **kwargs: object) -> object:
        calls.append((args, kwargs))
        raise AssertionError("network should not be called for invalid custom mode")

    monkeypatch.setattr("requests.post", fake_post)

    result = SunoMusic().execute(
        {"prompt": "[Verse]\nLaunch day lights up.", "custom_mode": True}
    )

    assert not result.success
    assert "custom_mode" in (result.error or "")
    assert "style" in (result.error or "")
    assert "title" in (result.error or "")
    assert calls == []


def test_google_tts_service_account_only_is_not_advertised_available(monkeypatch):
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setenv(
        "GOOGLE_APPLICATION_CREDENTIALS",
        "/tmp/video-production-buddy-service-account.json",
    )

    assert GoogleTTS().get_status() == ToolStatus.UNAVAILABLE


def test_piper_tts_status_requires_piper_binary_even_if_python_module_exists(monkeypatch):
    monkeypatch.setattr("tools.base_tool.shutil.which", lambda _cmd: None)
    real_import = builtins.__import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "piper":
            return object()
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    assert PiperTTS().get_status() == ToolStatus.UNAVAILABLE


@pytest.mark.parametrize(
    ("tool", "base", "variant"),
    [
        (
            ElevenLabsTTS(),
            {"text": "hello", "voice_id": "voice", "model_id": "eleven_multilingual_v2"},
            {"output_path": "elevenlabs-a.mp3"},
        ),
        (
            ElevenLabsTTS(),
            {"text": "hello", "voice_id": "voice", "model_id": "eleven_multilingual_v2"},
            {"stability": 0.2},
        ),
        (
            OpenAITTS(),
            {"text": "hello", "voice": "alloy", "model": "gpt-4o-mini-tts", "format": "mp3"},
            {"output_path": "openai-a.mp3"},
        ),
        (
            OpenAITTS(),
            {"text": "hello", "voice": "alloy", "model": "gpt-4o-mini-tts", "format": "mp3"},
            {"instructions": "warm documentary restraint"},
        ),
        (
            GoogleTTS(),
            {
                "text": "hello",
                "voice": "en-US-Chirp3-HD-Orus",
                "language_code": "en-US",
                "speaking_rate": 1.0,
                "pitch": 0.0,
            },
            {"output_path": "google-a.mp3"},
        ),
        (
            GoogleTTS(),
            {
                "text": "hello",
                "voice": "en-US-Chirp3-HD-Orus",
                "language_code": "en-US",
                "speaking_rate": 1.0,
                "pitch": 0.0,
            },
            {"audio_encoding": "LINEAR16"},
        ),
        (
            CosyVoiceTTS(),
            {"text": "hello", "voice": "Dylan", "model": "qwen3-tts-instruct-flash", "speed": 1.0},
            {"language_type": "English"},
        ),
        (
            CosyVoiceTTS(),
            {"text": "hello", "voice": "Dylan", "model": "qwen3-tts-instruct-flash", "speed": 1.0},
            {"output_path": "cosyvoice-a.mp3"},
        ),
        (
            DoubaoTTS(),
            {
                "text": "hello",
                "voice_id": "voice",
                "resource_id": "seed-tts-2.0",
                "speech_rate": 0,
                "sample_rate": 24000,
            },
            {"output_path": "doubao-a.mp3"},
        ),
        (
            DoubaoTTS(),
            {
                "text": "hello",
                "voice_id": "voice",
                "resource_id": "seed-tts-2.0",
                "speech_rate": 0,
                "sample_rate": 24000,
            },
            {"format": "ogg_opus"},
        ),
        (
            PiperTTS(),
            {"text": "hello", "model": "en_US-lessac-medium", "speaker_id": 0, "length_scale": 1.0},
            {"output_path": "piper-a.wav"},
        ),
        (
            PiperTTS(),
            {"text": "hello", "model": "en_US-lessac-medium", "speaker_id": 0, "length_scale": 1.0},
            {"sentence_silence": 0.8},
        ),
        (
            MinimaxMusic(),
            {"prompt": "cinematic bed", "lyrics": "", "model": "music-2.6", "is_instrumental": True},
            {"sample_rate": 16000},
        ),
        (
            MinimaxMusic(),
            {"prompt": "cinematic bed", "lyrics": "", "model": "music-2.6", "is_instrumental": True},
            {"output_path": "minimax-a.mp3"},
        ),
        (
            SunoMusic(),
            {"prompt": "cinematic bed", "style": "ambient", "instrumental": True, "model": "V4"},
            {"output_path": "suno-a.mp3"},
        ),
        (
            SunoMusic(),
            {"prompt": "cinematic bed", "style": "ambient", "instrumental": True, "model": "V4"},
            {"track_index": 1},
        ),
        (
            MusicGen(),
            {"prompt": "ambient launch bed", "duration_seconds": 12},
            {"output_path": "musicgen-a.mp3"},
        ),
        (
            AudioEnhance(),
            {
                "input_path": "speech.wav",
                "preset": "clean_speech",
                "audio_codec": "aac",
                "audio_bitrate": "192k",
            },
            {"output_path": "speech-enhanced-a.wav"},
        ),
        (
            QwenASR(),
            {"audio_url": "https://example.test/speech.mp3", "model": "qwen3-asr-flash"},
            {"output_path": "speech-transcript-a.txt"},
        ),
    ],
)
def test_audio_provider_idempotency_keys_include_delivery_shaping_inputs(
    tool: Any,
    base: dict[str, object],
    variant: dict[str, object],
):
    assert tool.idempotency_key(base) != tool.idempotency_key({**base, **variant})
