from __future__ import annotations

import base64
import builtins
import math
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import jsonschema
import pytest

from lib.scoring import ProviderScore
from tools.audio.audio_enhance import AudioEnhance
from tools.audio.audio_mixer import AudioMixer
from tools.audio.cosyvoice_tts import CosyVoiceTTS
from tools.audio.doubao_tts import DoubaoTTS
from tools.audio.elevenlabs_tts import ElevenLabsTTS
from tools.audio.freesound_music import FreesoundMusic
from tools.audio.google_tts import GoogleTTS
from tools.audio.minimax_music import MinimaxMusic
from tools.audio.minimax_tts import VOICES as MINIMAX_TTS_VOICES
from tools.audio.minimax_tts import MinimaxTTS
from tools.audio.music_gen import MusicGen
from tools.audio.openai_tts import OpenAITTS
from tools.audio.pixabay_music import PixabayMusic
from tools.audio.piper_tts import PiperTTS
from tools.audio.qwen_asr import QwenASR
from tools.audio.suno_music import SunoMusic
from tools.audio.tts_selector import TTSSelector
from tools.base_tool import ToolResult, ToolStatus
from tools.output_paths import require_explicit_output_path


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
            "output_path": "projects/demo/assets/audio/hook.wav",
        }
    )

    assert result.success
    assert openai_like.calls[0] == {
        "text": "A precise narration line.",
        "voice": "alloy",
        "model": "gpt-4o-mini-tts",
        "format": "wav",
        "speed": 0.95,
        "output_path": "projects/demo/assets/audio/hook.wav",
    }


def test_openai_tts_schema_declares_speed_used_by_asset_director():
    assert "speed" in OpenAITTS.input_schema["properties"]
    assert "speed" in OpenAITTS.idempotency_key_fields


def test_tts_selector_schema_declares_delivery_shaping_inputs():
    properties = TTSSelector.input_schema["properties"]

    assert "instructions" in properties
    assert "speed" in properties
    assert "instructions" in TTSSelector.idempotency_key_fields
    assert "speed" in TTSSelector.idempotency_key_fields


def test_tts_selector_generation_success_payload_matches_output_schema(monkeypatch):
    selector = TTSSelector()
    output_path = "projects/demo/assets/audio/selector-voice.wav"
    openai_like = _FakeTTSProvider(
        "openai_tts",
        "openai",
        {
            "text": {"type": "string"},
            "voice": {"type": "string"},
            "model": {"type": "string"},
            "format": {"type": "string"},
            "output_path": {"type": "string"},
        },
    )
    openai_like.agent_skills = ["text-to-speech"]
    openai_like.best_for = ["instruction-rich narration"]

    def fake_execute(inputs: dict[str, object]) -> ToolResult:
        openai_like.calls.append(dict(inputs))
        return ToolResult(
            success=True,
            data={
                "provider": "openai",
                "model": "gpt-4o-mini-tts",
                "voice": "alloy",
                "format": "wav",
                "text_length": 21,
                "audio_duration_seconds": None,
                "output": output_path,
                "output_path": output_path,
            },
            artifacts=[output_path],
        )

    monkeypatch.setattr(selector, "_providers", lambda: [openai_like])
    monkeypatch.setattr(openai_like, "execute", fake_execute)
    monkeypatch.setattr("lib.scoring.rank_providers", lambda candidates, _ctx: _rank_as(*candidates))

    output_properties = TTSSelector.output_schema["properties"]
    assert {
        "output",
        "output_path",
        "selected_tool",
        "selected_provider",
        "selection_reason",
        "provider_score",
        "selected_tool_agent_skills",
        "required_agent_skills",
        "selected_tool_usage_location",
        "selected_tool_best_for",
        "alternatives_considered",
    } <= set(output_properties)

    result = selector.execute(
        {
            "text": "A concise narration.",
            "voice_id": "alloy",
            "model_id": "gpt-4o-mini-tts",
            "output_format": "wav",
            "preferred_provider": "openai",
            "allowed_providers": ["openai_tts"],
            "output_path": output_path,
        }
    )

    assert result.success is True
    assert result.data["selected_tool"] == "openai_tts"
    assert result.data["selected_provider"] == "openai"
    assert result.data["required_agent_skills"] == ["text-to-speech"]
    assert result.data["selected_tool_best_for"] == ["instruction-rich narration"]
    assert result.data["output_path"] == output_path
    assert result.artifacts == [output_path]
    jsonschema.validate(instance=result.data, schema=TTSSelector.output_schema)


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


@pytest.mark.parametrize(
    ("tool", "env_var", "inputs"),
    [
        (
            ElevenLabsTTS(),
            "ELEVENLABS_API_KEY",
            {"text": "hello", "voice_id": "voice", "model_id": "eleven_multilingual_v2"},
        ),
        (
            GoogleTTS(),
            "GOOGLE_API_KEY",
            {"text": "hello", "voice": "en-US-Chirp3-HD-Orus", "language_code": "en-US"},
        ),
        (
            CosyVoiceTTS(),
            "DASHSCOPE_API_KEY",
            {"text": "hello", "voice": "Dylan", "model": "qwen3-tts-instruct-flash"},
        ),
        (
            MinimaxTTS(),
            "MINIMAX_API_KEY",
            {"text": "hello", "voice": "Calm_Woman"},
        ),
        (
            MinimaxMusic(),
            "MINIMAX_API_KEY",
            {"prompt": "cinematic bed", "model": "music-2.6", "is_instrumental": True},
        ),
        (
            MusicGen(),
            "ELEVENLABS_API_KEY",
            {"prompt": "cinematic ambient bed", "duration_seconds": 12},
        ),
    ],
)
def test_api_audio_generators_require_output_path_before_requests(
    monkeypatch: pytest.MonkeyPatch,
    tool: Any,
    env_var: str,
    inputs: dict[str, object],
):
    monkeypatch.setenv(env_var, "test-key")
    calls: list[object] = []

    def fake_post(*args: object, **kwargs: object) -> object:
        calls.append((args, kwargs))
        raise AssertionError("network should not be called without output_path")

    monkeypatch.setattr("requests.post", fake_post)

    result = tool.execute(inputs)

    assert result.success is False
    assert "output_path is required" in (result.error or "")
    assert calls == []


def test_openai_tts_requires_output_path_before_client_creation(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    calls: list[str] = []

    class FakeOpenAI:
        def __init__(self) -> None:
            calls.append("client")
            raise AssertionError("OpenAI client should not be created without output_path")

    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=FakeOpenAI))

    result = OpenAITTS().execute({"text": "hello"})

    assert result.success is False
    assert "output_path is required" in (result.error or "")
    assert calls == []


def test_suno_music_requires_output_path_before_submission(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("SUNO_API_KEY", "test-key")
    calls: list[object] = []

    def fake_submit(self: SunoMusic, inputs: dict[str, Any], api_key: str) -> str:
        calls.append((self, inputs, api_key))
        raise AssertionError("Suno should not submit without output_path")

    monkeypatch.setattr(SunoMusic, "_submit", fake_submit)

    result = SunoMusic().execute(
        {"prompt": "cinematic bed", "style": "ambient", "instrumental": True}
    )

    assert result.success is False
    assert "output_path is required" in (result.error or "")
    assert calls == []


def test_doubao_tts_requires_output_path_before_generation(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("DOUBAO_SPEECH_API_KEY", "test-key")
    calls: list[object] = []

    def fake_generate(
        self: DoubaoTTS,
        inputs: dict[str, Any],
        *,
        api_key: str,
        voice_id: str,
    ) -> ToolResult:
        calls.append((self, inputs, api_key, voice_id))
        raise AssertionError("Doubao should not generate without output_path")

    monkeypatch.setattr(DoubaoTTS, "_generate", fake_generate)

    result = DoubaoTTS().execute({"text": "hello", "voice_id": "voice"})

    assert result.success is False
    assert "output_path is required" in (result.error or "")
    assert calls == []


def test_piper_tts_requires_output_path_before_local_process(
    monkeypatch: pytest.MonkeyPatch,
):
    calls: list[object] = []

    def fake_run(*args: object, **kwargs: object) -> object:
        calls.append((args, kwargs))
        raise AssertionError("piper should not run without output_path")

    monkeypatch.setattr(PiperTTS, "get_status", lambda self: ToolStatus.AVAILABLE)
    monkeypatch.setattr("subprocess.run", fake_run)

    result = PiperTTS().execute({"text": "hello"})

    assert result.success is False
    assert "output_path is required" in (result.error or "")
    assert calls == []


def test_piper_tts_writes_to_validated_output_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    raw_output_path = "projects/demo/assets/audio/raw-piper.wav"
    validated_output_path = Path("projects/demo/assets/audio/validated-piper.wav")

    def fake_require_explicit_output_path(
        inputs: dict[str, Any],
        tool_name: str,
        *,
        artifact_label: str = "generated media",
    ) -> tuple[Path | None, ToolResult | None]:
        return validated_output_path, None

    monkeypatch.setattr(
        "tools.audio.piper_tts.require_explicit_output_path",
        fake_require_explicit_output_path,
    )
    monkeypatch.setattr(PiperTTS, "get_status", lambda self: ToolStatus.AVAILABLE)
    monkeypatch.setattr(PiperTTS, "_resolve_model_path", lambda self, model: model)

    def fake_run(args: list[str], **kwargs: object) -> object:
        output_arg = Path(args[args.index("--output_file") + 1])
        output_arg.parent.mkdir(parents=True, exist_ok=True)
        output_arg.write_bytes(b"wav")
        return SimpleNamespace(returncode=0, stderr="")

    monkeypatch.setattr("subprocess.run", fake_run)

    result = PiperTTS().execute({"text": "hello", "output_path": raw_output_path})

    assert result.success is True
    assert (tmp_path / validated_output_path).read_bytes() == b"wav"
    assert not (tmp_path / raw_output_path).exists()
    assert result.data["output"] == str(validated_output_path)
    assert result.data["output_path"] == str(validated_output_path)
    assert result.artifacts == [str(validated_output_path)]


def test_google_tts_writes_to_validated_output_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    raw_output_path = "projects/demo/assets/audio/raw-google.mp3"
    validated_output_path = Path("projects/demo/assets/audio/validated-google.mp3")

    def fake_require_explicit_output_path(
        inputs: dict[str, Any],
        tool_name: str,
        *,
        artifact_label: str = "generated media",
    ) -> tuple[Path | None, ToolResult | None]:
        return validated_output_path, None

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, str]:
            return {"audioContent": base64.b64encode(b"mp3").decode("ascii")}

    monkeypatch.setattr(
        "tools.audio.google_tts.require_explicit_output_path",
        fake_require_explicit_output_path,
    )
    monkeypatch.setenv("GOOGLE_API_KEY", "test-key")
    monkeypatch.setattr("requests.post", lambda *args, **kwargs: FakeResponse())

    result = GoogleTTS().execute(
        {
            "text": "hello",
            "voice": "en-US-Chirp3-HD-Orus",
            "language_code": "en-US",
            "output_path": raw_output_path,
        }
    )

    assert result.success is True
    assert (tmp_path / validated_output_path).read_bytes() == b"mp3"
    assert not (tmp_path / raw_output_path).exists()
    assert result.data["output"] == str(validated_output_path)
    assert result.data["output_path"] == str(validated_output_path)
    assert result.artifacts == [str(validated_output_path)]


def test_music_gen_writes_to_validated_output_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    raw_output_path = "projects/demo/assets/audio/raw-music-gen.mp3"
    validated_output_path = Path("projects/demo/assets/audio/validated-music-gen.mp3")

    def fake_require_explicit_output_path(
        inputs: dict[str, Any],
        tool_name: str,
        *,
        artifact_label: str = "generated media",
    ) -> tuple[Path | None, ToolResult | None]:
        return validated_output_path, None

    monkeypatch.setattr(
        "tools.audio.music_gen.require_explicit_output_path",
        fake_require_explicit_output_path,
    )
    monkeypatch.setenv("ELEVENLABS_API_KEY", "test-key")
    monkeypatch.setattr(
        "requests.post",
        lambda *args, **kwargs: SimpleNamespace(
            status_code=200,
            content=b"mp3",
            raise_for_status=lambda: None,
        ),
    )

    result = MusicGen().execute(
        {
            "prompt": "cinematic bed",
            "duration_seconds": 12,
            "output_path": raw_output_path,
        }
    )

    assert result.success is True
    assert (tmp_path / validated_output_path).read_bytes() == b"mp3"
    assert not (tmp_path / raw_output_path).exists()
    assert result.data["output"] == str(validated_output_path)
    assert result.data["output_path"] == str(validated_output_path)
    assert result.artifacts == [str(validated_output_path)]


def test_minimax_music_writes_to_validated_output_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    raw_output_path = "projects/demo/assets/audio/raw-minimax-music.mp3"
    validated_output_path = Path("projects/demo/assets/audio/validated-minimax-music.mp3")

    def fake_require_explicit_output_path(
        inputs: dict[str, Any],
        tool_name: str,
        *,
        artifact_label: str = "generated media",
    ) -> tuple[Path | None, ToolResult | None]:
        return validated_output_path, None

    monkeypatch.setattr(
        "tools.audio.minimax_music.require_explicit_output_path",
        fake_require_explicit_output_path,
    )
    monkeypatch.setenv("MINIMAX_API_KEY", "test-key")
    monkeypatch.setattr(
        "requests.post",
        lambda *args, **kwargs: SimpleNamespace(
            status_code=200,
            json=lambda: {
                "base_resp": {"status_code": 0},
                "data": {"status": 2, "audio": b"mp3".hex()},
                "extra_info": {"music_duration": 12000},
            },
            raise_for_status=lambda: None,
        ),
    )

    result = MinimaxMusic().execute(
        {
            "prompt": "cinematic bed",
            "model": "music-2.6",
            "is_instrumental": True,
            "output_path": raw_output_path,
        }
    )

    assert result.success is True
    assert (tmp_path / validated_output_path).read_bytes() == b"mp3"
    assert not (tmp_path / raw_output_path).exists()
    assert result.data["output"] == str(validated_output_path)
    assert result.data["output_path"] == str(validated_output_path)
    assert result.artifacts == [str(validated_output_path)]


def test_suno_music_writes_to_validated_output_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    raw_output_path = "projects/demo/assets/audio/raw-suno.mp3"
    validated_output_path = Path("projects/demo/assets/audio/validated-suno.mp3")

    def fake_require_explicit_output_path(
        inputs: dict[str, Any],
        tool_name: str,
        *,
        artifact_label: str = "generated media",
    ) -> tuple[Path | None, ToolResult | None]:
        return validated_output_path, None

    class FakeResponse:
        content = b"mp3"

        def raise_for_status(self) -> None:
            return None

    monkeypatch.setattr(
        "tools.audio.suno_music.require_explicit_output_path",
        fake_require_explicit_output_path,
    )
    monkeypatch.setenv("SUNO_API_KEY", "test-key")
    monkeypatch.setattr(SunoMusic, "_submit", lambda self, inputs, api_key: "task-1")
    monkeypatch.setattr(
        SunoMusic,
        "_poll",
        lambda self, task_id, api_key: {
            "data": [
                {
                    "audio_url": "https://example.test/suno.mp3",
                    "duration": 12,
                    "id": "track-1",
                    "title": "Hook",
                }
            ]
        },
    )
    monkeypatch.setattr("requests.get", lambda *args, **kwargs: FakeResponse())

    result = SunoMusic().execute(
        {
            "prompt": "cinematic bed",
            "style": "ambient",
            "instrumental": True,
            "output_path": raw_output_path,
        }
    )

    assert result.success is True
    assert (tmp_path / validated_output_path).read_bytes() == b"mp3"
    assert not (tmp_path / raw_output_path).exists()
    assert result.data["output"] == str(validated_output_path)
    assert result.data["output_path"] == str(validated_output_path)
    assert result.artifacts == [str(validated_output_path)]


@pytest.mark.parametrize(
    ("model", "voice"),
    [
        ("qwen3-tts-flash", "Cherry"),
        ("cosyvoice-v2", "longanyang"),
    ],
)
def test_cosyvoice_tts_writes_to_validated_output_path(
    model: str,
    voice: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    raw_output_path = f"projects/demo/assets/audio/raw-{model}.mp3"
    validated_output_path = Path(f"projects/demo/assets/audio/validated-{model}.mp3")

    def fake_require_explicit_output_path(
        inputs: dict[str, Any],
        tool_name: str,
        *,
        artifact_label: str = "generated media",
    ) -> tuple[Path | None, ToolResult | None]:
        return validated_output_path, None

    class FakeResponse:
        content = b"mp3"
        headers = {"content-type": "audio/mpeg"}

        def json(self) -> dict[str, object]:
            return {
                "output": {
                    "audio": {
                        "data": base64.b64encode(b"mp3").decode("ascii"),
                    }
                }
            }

        def raise_for_status(self) -> None:
            return None

    def fake_format(content: bytes, fmt: str, output: Path) -> str:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(content)
        return fmt

    monkeypatch.setattr(
        "tools.audio.cosyvoice_tts.require_explicit_output_path",
        fake_require_explicit_output_path,
    )
    monkeypatch.setenv("DASHSCOPE_API_KEY", "test-key")
    monkeypatch.setattr("requests.post", lambda *args, **kwargs: FakeResponse())
    monkeypatch.setattr(CosyVoiceTTS, "_ensure_audio_format", staticmethod(fake_format))

    result = CosyVoiceTTS().execute(
        {
            "text": "hello",
            "voice": voice,
            "model": model,
            "output_path": raw_output_path,
        }
    )

    assert result.success is True
    assert (tmp_path / validated_output_path).read_bytes() == b"mp3"
    assert not (tmp_path / raw_output_path).exists()
    assert result.data["output"] == str(validated_output_path)
    assert result.data["output_path"] == str(validated_output_path)
    assert result.artifacts == [str(validated_output_path)]


def test_doubao_tts_writes_to_validated_output_and_metadata_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    raw_output_path = "projects/demo/assets/audio/raw-doubao.mp3"
    raw_metadata_path = "projects/demo/artifacts/raw-doubao.json"
    validated_output_path = Path("projects/demo/assets/audio/validated-doubao.mp3")
    validated_metadata_path = Path("projects/demo/artifacts/validated-doubao.json")

    def fake_require_explicit_output_path(
        inputs: dict[str, Any],
        tool_name: str,
        *,
        artifact_label: str = "generated media",
    ) -> tuple[Path | None, ToolResult | None]:
        return validated_output_path, None

    def fake_require_optional_project_sidecar_path(
        inputs: dict[str, Any],
        field_name: str,
        tool_name: str,
        *,
        artifact_label: str = "sidecar artifact",
    ) -> tuple[Path | None, ToolResult | None]:
        return validated_metadata_path, None

    class FakeResponse:
        status_code = 200
        content = b"mp3"

        def json(self) -> dict[str, object]:
            return {"code": 20000000, "data": {"task_id": "task-1"}}

        def raise_for_status(self) -> None:
            return None

    monkeypatch.setattr(
        "tools.audio.doubao_tts.require_explicit_output_path",
        fake_require_explicit_output_path,
    )
    monkeypatch.setattr(
        "tools.audio.doubao_tts.require_optional_project_sidecar_path",
        fake_require_optional_project_sidecar_path,
    )
    monkeypatch.setenv("DOUBAO_SPEECH_API_KEY", "test-key")
    monkeypatch.setattr("requests.post", lambda *args, **kwargs: FakeResponse())
    monkeypatch.setattr("requests.get", lambda *args, **kwargs: FakeResponse())
    monkeypatch.setattr(
        DoubaoTTS,
        "_poll_query",
        lambda self, **kwargs: {
            "code": 20000000,
            "data": {
                "task_status": 2,
                "audio_url": "https://example.test/doubao.mp3",
                "sentences": [],
            },
        },
    )
    monkeypatch.setattr(DoubaoTTS, "_audio_duration", staticmethod(lambda path: 1.25))

    result = DoubaoTTS().execute(
        {
            "text": "hello",
            "voice_id": "voice",
            "output_path": raw_output_path,
            "metadata_path": raw_metadata_path,
        }
    )

    assert result.success is True
    assert (tmp_path / validated_output_path).read_bytes() == b"mp3"
    assert (tmp_path / validated_metadata_path).read_text(encoding="utf-8")
    assert not (tmp_path / raw_output_path).exists()
    assert not (tmp_path / raw_metadata_path).exists()
    assert result.data["output"] == str(validated_output_path)
    assert result.data["output_path"] == str(validated_output_path)
    assert result.data["metadata_path"] == str(validated_metadata_path)
    assert result.artifacts == [str(validated_output_path), str(validated_metadata_path)]


@pytest.mark.parametrize(
    ("tool", "inputs", "env_vars"),
    [
        (
            CosyVoiceTTS(),
            {"text": "hello", "voice": "Dylan", "model": "qwen3-tts-instruct-flash", "output_path": "voice.mp3"},
            ("DASHSCOPE_API_KEY",),
        ),
        (
            DoubaoTTS(),
            {"text": "hello", "voice_id": "voice", "output_path": "voice.mp3"},
            ("DOUBAO_SPEECH_API_KEY",),
        ),
        (
            ElevenLabsTTS(),
            {"text": "hello", "voice_id": "voice", "model_id": "eleven_multilingual_v2", "output_path": "voice.mp3"},
            ("ELEVENLABS_API_KEY",),
        ),
        (
            GoogleTTS(),
            {"text": "hello", "voice": "en-US-Chirp3-HD-Orus", "language_code": "en-US", "output_path": "voice.mp3"},
            ("GOOGLE_API_KEY", "GEMINI_API_KEY"),
        ),
        (
            MinimaxMusic(),
            {"prompt": "cinematic bed", "model": "music-2.6", "is_instrumental": True, "output_path": "music.mp3"},
            ("MINIMAX_API_KEY",),
        ),
        (
            MusicGen(),
            {"prompt": "cinematic ambient bed", "duration_seconds": 12, "output_path": "music.mp3"},
            ("ELEVENLABS_API_KEY",),
        ),
        (
            OpenAITTS(),
            {"text": "hello", "output_path": "voice.mp3"},
            ("OPENAI_API_KEY",),
        ),
        (
            MinimaxTTS(),
            {"text": "hello", "voice": "Calm_Woman", "output_path": "voice.mp3"},
            ("MINIMAX_API_KEY",),
        ),
        (
            SunoMusic(),
            {"prompt": "cinematic bed", "style": "ambient", "instrumental": True, "output_path": "music.mp3"},
            ("SUNO_API_KEY",),
        ),
    ],
)
def test_api_audio_generators_reject_non_project_output_path_before_credentials(
    monkeypatch: pytest.MonkeyPatch,
    tool: Any,
    inputs: dict[str, object],
    env_vars: tuple[str, ...],
) -> None:
    for env_var in env_vars:
        monkeypatch.delenv(env_var, raising=False)

    result = tool.execute(inputs)

    assert result.success is False
    assert "output_path" in (result.error or "")
    assert "projects/<project-name>/" in (result.error or "")


def test_piper_tts_rejects_non_project_output_path_before_status_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[object] = []

    def fail_status(self: PiperTTS) -> ToolStatus:
        calls.append(self)
        raise AssertionError("Piper status should not be checked for invalid output_path")

    monkeypatch.setattr(PiperTTS, "get_status", fail_status)

    result = PiperTTS().execute({"text": "hello", "output_path": "voice.wav"})

    assert result.success is False
    assert "output_path" in (result.error or "")
    assert "projects/<project-name>/" in (result.error or "")
    assert calls == []


@pytest.mark.parametrize(
    ("tool_cls", "minimal_inputs"),
    [
        (CosyVoiceTTS, {"text": "hello"}),
        (DoubaoTTS, {"text": "hello"}),
        (ElevenLabsTTS, {"text": "hello"}),
        (GoogleTTS, {"text": "hello"}),
        (MinimaxMusic, {"prompt": "cinematic bed"}),
        (MusicGen, {"prompt": "cinematic ambient bed"}),
        (OpenAITTS, {"text": "hello"}),
        (PiperTTS, {"text": "hello"}),
        (SunoMusic, {"prompt": "cinematic bed"}),
    ],
)
def test_generated_audio_schemas_require_output_path(
    tool_cls: type[Any],
    minimal_inputs: dict[str, object],
) -> None:
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance=minimal_inputs, schema=tool_cls.input_schema)


@pytest.mark.parametrize(
    ("tool", "env_var"),
    [
        (FreesoundMusic(), "FREESOUND_API_KEY"),
        (PixabayMusic(), None),
    ],
)
@pytest.mark.parametrize(
    "output_path",
    [
        None,
        "background.mp3",
        "/tmp/background.mp3",
    ],
)
def test_stock_music_requires_project_output_path_before_search(
    tool: FreesoundMusic | PixabayMusic,
    env_var: str | None,
    output_path: str | None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if env_var:
        monkeypatch.setenv(env_var, "test-key")
    calls: list[object] = []

    def fake_search(*args: object, **kwargs: object) -> list[dict[str, object]]:
        calls.append((args, kwargs))
        raise AssertionError("music search should not run before output_path validation")

    monkeypatch.setattr(tool, "_search", fake_search)
    inputs: dict[str, object] = {"query": "cinematic ambient bed"}
    if output_path is not None:
        inputs["output_path"] = output_path

    result = tool.execute(inputs)

    assert result.success is False
    assert "output_path" in (result.error or "")
    assert "projects/<project-name>/" in (result.error or "")
    assert calls == []


@pytest.mark.parametrize(
    "tool_cls",
    [FreesoundMusic, PixabayMusic],
)
def test_stock_music_schemas_require_output_path(
    tool_cls: type[FreesoundMusic] | type[PixabayMusic],
) -> None:
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(
            instance={"query": "cinematic ambient bed"},
            schema=tool_cls.input_schema,
        )


@pytest.mark.parametrize(
    "output_path",
    [
        "voice.mp3",
        "assets/audio/voice.mp3",
        "/tmp/voice.mp3",
        "projects/demo/../evil/assets/audio/voice.mp3",
        "projects/demo/assets/../renders/voice.mp3",
        "projects/demo/assets",
        "projects/demo/renders",
        "projects/demo/assets/audio/voice",
    ],
)
def test_generated_media_output_path_must_stay_inside_project_workspace(
    output_path: str,
):
    returned_path, error = require_explicit_output_path(
        {"output_path": output_path},
        "audio_tool",
        artifact_label="generated speech audio",
    )

    assert returned_path is None
    assert error is not None
    assert "projects/<project-name>/" in (error.error or "")


@pytest.mark.parametrize("output_path", [[], {}, 123])
def test_generated_media_output_path_rejects_non_string_values(output_path: object):
    returned_path, error = require_explicit_output_path(
        {"output_path": output_path},
        "audio_tool",
        artifact_label="generated speech audio",
    )

    assert returned_path is None
    assert error is not None
    assert "output_path for generated speech audio must be a string path" in (
        error.error or ""
    )


def test_generated_media_output_path_accepts_project_assets_path():
    returned_path, error = require_explicit_output_path(
        {"output_path": "projects/demo/assets/audio/voice.mp3"},
        "audio_tool",
        artifact_label="generated speech audio",
    )

    assert error is None
    assert str(returned_path) == "projects/demo/assets/audio/voice.mp3"


def test_audio_mixer_mix_success_payload_matches_output_schema(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    speech = tmp_path / "speech.wav"
    music = tmp_path / "music.wav"
    speech.write_bytes(b"speech")
    music.write_bytes(b"music")
    output_path = "projects/demo/assets/audio/mixed.wav"

    def fake_run_command(self: AudioMixer, cmd: list[str], **kwargs: object) -> object:
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(AudioMixer, "run_command", fake_run_command)

    output_properties = AudioMixer.output_schema["properties"]
    assert {
        "operation",
        "track_count",
        "output",
        "output_path",
        "normalized",
    } <= set(output_properties)

    result = AudioMixer().execute(
        {
            "operation": "mix",
            "tracks": [
                {"path": str(speech), "role": "speech"},
                {"path": str(music), "role": "music", "volume": 0.25},
            ],
            "output_path": output_path,
        }
    )

    assert result.success is True
    assert result.data == {
        "operation": "mix",
        "track_count": 2,
        "output": output_path,
        "normalized": True,
        "output_path": output_path,
    }
    assert result.artifacts == [output_path]
    jsonschema.validate(instance=result.data, schema=AudioMixer.output_schema)


def test_audio_enhance_success_payload_matches_output_schema(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    input_path = tmp_path / "voice.wav"
    input_path.write_bytes(b"voice")
    output_path = "projects/demo/assets/audio/enhanced.wav"

    def fake_run_command(
        self: AudioEnhance,
        cmd: list[str],
        **kwargs: object,
    ) -> object:
        Path(cmd[-1]).write_bytes(b"enhanced")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(AudioEnhance, "run_command", fake_run_command)

    output_properties = AudioEnhance.output_schema["properties"]
    assert {
        "input",
        "output",
        "output_path",
        "preset",
        "filter",
    } <= set(output_properties)

    result = AudioEnhance().execute(
        {
            "input_path": str(input_path),
            "output_path": output_path,
            "preset": "normalize_only",
        }
    )

    assert result.success is True
    assert result.data["input"] == str(input_path)
    assert result.data["output"] == output_path
    assert result.data["output_path"] == output_path
    assert result.data["preset"] == "normalize_only"
    assert result.data["filter"]
    assert (tmp_path / output_path).read_bytes() == b"enhanced"
    assert result.artifacts == [output_path]
    jsonschema.validate(instance=result.data, schema=AudioEnhance.output_schema)


def test_piper_tts_success_payload_includes_output_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    output_path = "projects/demo/assets/audio/piper.wav"

    def fake_run(cmd: list[str], **kwargs: object) -> SimpleNamespace:
        Path(cmd[cmd.index("--output_file") + 1]).write_bytes(b"wav")
        return SimpleNamespace(returncode=0, stderr="")

    monkeypatch.setattr(PiperTTS, "get_status", lambda self: ToolStatus.AVAILABLE)
    monkeypatch.setattr(PiperTTS, "_resolve_model_path", lambda self, model: model)
    monkeypatch.setattr("subprocess.run", fake_run)

    result = PiperTTS().execute({"text": "hello", "output_path": output_path})

    assert result.success
    assert result.data["output_path"] == output_path
    assert result.artifacts == [output_path]


def test_piper_tts_success_payload_matches_output_schema(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    output_path = "projects/demo/assets/audio/piper-schema.wav"

    def fake_run(cmd: list[str], **kwargs: object) -> SimpleNamespace:
        Path(cmd[cmd.index("--output_file") + 1]).write_bytes(b"wav")
        return SimpleNamespace(returncode=0, stderr="")

    monkeypatch.setattr(PiperTTS, "get_status", lambda self: ToolStatus.AVAILABLE)
    monkeypatch.setattr(PiperTTS, "_resolve_model_path", lambda self, model: model)
    monkeypatch.setattr("subprocess.run", fake_run)

    output_properties = PiperTTS.output_schema["properties"]
    assert {
        "provider",
        "model",
        "speaker_id",
        "text_length",
        "format",
        "output",
        "output_path",
    } <= set(output_properties)

    result = PiperTTS().execute(
        {
            "text": "hello",
            "model": "en_US-lessac-medium",
            "speaker_id": 0,
            "output_path": output_path,
        }
    )

    assert result.success is True
    assert result.data == {
        "provider": "piper",
        "model": "en_US-lessac-medium",
        "speaker_id": 0,
        "text_length": 5,
        "output": output_path,
        "format": "wav",
        "output_path": output_path,
    }
    assert (tmp_path / output_path).read_bytes() == b"wav"
    assert result.artifacts == [output_path]
    jsonschema.validate(instance=result.data, schema=PiperTTS.output_schema)


def test_openai_tts_success_payload_includes_output_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    output_path = "projects/demo/assets/audio/openai.mp3"

    class FakeStreamingResponse:
        def __enter__(self) -> "FakeStreamingResponse":
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def stream_to_file(self, path: Path) -> None:
            Path(path).write_bytes(b"mp3")

    class FakeOpenAI:
        def __init__(self) -> None:
            self.audio = SimpleNamespace(
                speech=SimpleNamespace(
                    with_streaming_response=SimpleNamespace(
                        create=lambda **kwargs: FakeStreamingResponse()
                    )
                )
            )

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=FakeOpenAI))
    monkeypatch.setattr("tools.analysis.audio_probe.probe_duration", lambda path: 1.25)

    result = OpenAITTS().execute({"text": "hello", "output_path": output_path})

    assert result.success
    assert result.data["output_path"] == output_path
    assert result.artifacts == [output_path]


def test_openai_tts_success_payload_matches_output_schema(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    output_path = "projects/demo/assets/audio/openai-schema.mp3"

    class FakeStreamingResponse:
        def __enter__(self) -> "FakeStreamingResponse":
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def stream_to_file(self, path: Path) -> None:
            Path(path).write_bytes(b"mp3")

    class FakeOpenAI:
        def __init__(self) -> None:
            self.audio = SimpleNamespace(
                speech=SimpleNamespace(
                    with_streaming_response=SimpleNamespace(
                        create=lambda **kwargs: FakeStreamingResponse()
                    )
                )
            )

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=FakeOpenAI))
    monkeypatch.setattr("tools.analysis.audio_probe.probe_duration", lambda path: 1.25)

    output_properties = OpenAITTS.output_schema["properties"]
    assert {
        "provider",
        "model",
        "voice",
        "format",
        "response_format",
        "instructions",
        "speed",
        "text_length",
        "audio_duration_seconds",
        "output",
        "output_path",
    } <= set(output_properties)

    result = OpenAITTS().execute(
        {
            "text": "hello",
            "voice": "alloy",
            "model": "gpt-4o-mini-tts",
            "format": "mp3",
            "output_path": output_path,
        }
    )

    assert result.success is True
    assert result.data == {
        "provider": "openai",
        "model": "gpt-4o-mini-tts",
        "voice": "alloy",
        "format": "mp3",
        "response_format": "mp3",
        "instructions": None,
        "speed": 1.0,
        "text_length": 5,
        "audio_duration_seconds": 1.25,
        "output": output_path,
        "output_path": output_path,
    }
    assert (tmp_path / output_path).read_bytes() == b"mp3"
    assert result.artifacts == [output_path]
    jsonschema.validate(instance=result.data, schema=OpenAITTS.output_schema)


def test_elevenlabs_tts_success_payload_matches_output_schema(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    output_path = "projects/demo/assets/audio/elevenlabs-schema.mp3"

    class FakeResponse:
        status_code = 200
        content = b"mp3"

        def raise_for_status(self) -> None:
            return None

    monkeypatch.setenv("ELEVENLABS_API_KEY", "test-key")
    monkeypatch.setattr("requests.post", lambda *args, **kwargs: FakeResponse())

    output_properties = ElevenLabsTTS.output_schema["properties"]
    assert {
        "provider",
        "model",
        "voice_id",
        "voice_settings",
        "text_length",
        "format",
        "output",
        "output_path",
    } <= set(output_properties)

    result = ElevenLabsTTS().execute(
        {
            "text": "hello",
            "voice_id": "voice",
            "model_id": "eleven_multilingual_v2",
            "output_format": "mp3_44100_128",
            "output_path": output_path,
        }
    )

    assert result.success is True
    assert result.data == {
        "provider": "elevenlabs",
        "model": "eleven_multilingual_v2",
        "voice_id": "voice",
        "voice_settings": {
            "stability": 0.5,
            "similarity_boost": 0.75,
            "style": 0.0,
            "speed": 1.0,
            "use_speaker_boost": True,
        },
        "text_length": 5,
        "output": output_path,
        "format": "mp3_44100_128",
        "output_path": output_path,
    }
    assert (tmp_path / output_path).read_bytes() == b"mp3"
    assert result.artifacts == [output_path]
    jsonschema.validate(instance=result.data, schema=ElevenLabsTTS.output_schema)


def test_google_tts_success_payload_matches_output_schema(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    output_path = "projects/demo/assets/audio/google-schema.mp3"

    class FakeResponse:
        def json(self) -> dict[str, object]:
            return {"audioContent": base64.b64encode(b"mp3").decode("ascii")}

        def raise_for_status(self) -> None:
            return None

    monkeypatch.setenv("GOOGLE_API_KEY", "test-key")
    monkeypatch.setattr("requests.post", lambda *args, **kwargs: FakeResponse())

    output_properties = GoogleTTS.output_schema["properties"]
    assert {
        "provider",
        "voice",
        "language_code",
        "input_type",
        "text_length",
        "format",
        "speaking_rate",
        "pitch",
        "output",
        "output_path",
    } <= set(output_properties)

    result = GoogleTTS().execute(
        {
            "text": "hello",
            "voice": "en-US-Chirp3-HD-Orus",
            "language_code": "en-US",
            "speaking_rate": 1.0,
            "pitch": 0.0,
            "audio_encoding": "MP3",
            "output_path": output_path,
        }
    )

    assert result.success is True
    assert result.data == {
        "provider": "google_tts",
        "voice": "en-US-Chirp3-HD-Orus",
        "language_code": "en-US",
        "input_type": "text",
        "text_length": 5,
        "output": output_path,
        "format": "MP3",
        "speaking_rate": 1.0,
        "pitch": 0.0,
        "output_path": output_path,
    }
    assert (tmp_path / output_path).read_bytes() == b"mp3"
    assert result.artifacts == [output_path]
    jsonschema.validate(instance=result.data, schema=GoogleTTS.output_schema)


@pytest.mark.parametrize(
    ("tool", "env_var", "inputs", "fake_response"),
    [
        (
            ElevenLabsTTS(),
            "ELEVENLABS_API_KEY",
            {"text": "hello", "voice_id": "voice", "model_id": "eleven_multilingual_v2"},
            lambda: SimpleNamespace(
                status_code=200,
                content=b"mp3",
                raise_for_status=lambda: None,
            ),
        ),
        (
            GoogleTTS(),
            "GOOGLE_API_KEY",
            {"text": "hello", "voice": "en-US-Chirp3-HD-Orus", "language_code": "en-US"},
            lambda: SimpleNamespace(
                status_code=200,
                json=lambda: {"audioContent": base64.b64encode(b"mp3").decode("ascii")},
                raise_for_status=lambda: None,
            ),
        ),
        (
            MusicGen(),
            "ELEVENLABS_API_KEY",
            {"prompt": "cinematic bed", "duration_seconds": 12},
            lambda: SimpleNamespace(
                status_code=200,
                content=b"mp3",
                raise_for_status=lambda: None,
            ),
        ),
        (
            MinimaxMusic(),
            "MINIMAX_API_KEY",
            {"prompt": "cinematic bed", "model": "music-2.6", "is_instrumental": True},
            lambda: SimpleNamespace(
                status_code=200,
                json=lambda: {
                    "base_resp": {"status_code": 0},
                    "data": {"status": 2, "audio": b"mp3".hex()},
                    "extra_info": {"music_duration": 12000},
                },
                raise_for_status=lambda: None,
            ),
        ),
    ],
)
def test_http_audio_success_payload_includes_output_path(
    tool: Any,
    env_var: str,
    inputs: dict[str, object],
    fake_response: Any,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    output_path = f"projects/demo/assets/audio/{tool.name}.mp3"
    monkeypatch.setenv(env_var, "test-key")
    monkeypatch.setattr("requests.post", lambda *args, **kwargs: fake_response())

    result = tool.execute({**inputs, "output_path": output_path})

    assert result.success
    assert result.data["output_path"] == output_path
    assert result.artifacts == [output_path]


def test_music_gen_success_payload_matches_output_schema(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    output_path = "projects/demo/assets/audio/music-gen-schema.mp3"

    monkeypatch.setenv("ELEVENLABS_API_KEY", "test-key")
    monkeypatch.setattr(
        "requests.post",
        lambda *args, **kwargs: SimpleNamespace(
            status_code=200,
            content=b"mp3",
            raise_for_status=lambda: None,
        ),
    )

    output_properties = MusicGen.output_schema["properties"]
    assert {
        "provider",
        "prompt",
        "duration_seconds",
        "format",
        "output",
        "output_path",
    } <= set(output_properties)

    result = MusicGen().execute(
        {
            "prompt": "cinematic bed",
            "duration_seconds": 12,
            "output_path": output_path,
        }
    )

    assert result.success is True
    assert result.data == {
        "provider": "elevenlabs",
        "prompt": "cinematic bed",
        "duration_seconds": 12,
        "output": output_path,
        "format": "mp3",
        "output_path": output_path,
    }
    assert (tmp_path / output_path).read_bytes() == b"mp3"
    assert result.artifacts == [output_path]
    jsonschema.validate(instance=result.data, schema=MusicGen.output_schema)


def test_minimax_music_success_payload_matches_output_schema(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    output_path = "projects/demo/assets/audio/minimax-music.mp3"

    class FakeResponse:
        def json(self) -> dict[str, object]:
            return {
                "base_resp": {"status_code": 0, "status_msg": "success"},
                "data": {"status": 2, "audio": b"mp3".hex()},
                "extra_info": {"music_duration": 12000},
            }

        def raise_for_status(self) -> None:
            return None

    monkeypatch.setenv("MINIMAX_API_KEY", "test-key")
    monkeypatch.setattr("requests.post", lambda *args, **kwargs: FakeResponse())

    output_properties = MinimaxMusic.output_schema["properties"]
    assert {
        "provider",
        "model",
        "model_name",
        "prompt",
        "is_instrumental",
        "music_duration_ms",
        "music_duration_s",
        "format",
        "output",
        "output_path",
    } <= set(output_properties)

    result = MinimaxMusic().execute(
        {
            "prompt": "cinematic bed",
            "model": "music-2.6",
            "is_instrumental": True,
            "output_path": output_path,
        }
    )

    assert result.success is True
    assert result.data == {
        "provider": "minimax",
        "model": "music-2.6",
        "model_name": "MiniMax Music 2.6",
        "prompt": "cinematic bed",
        "is_instrumental": True,
        "music_duration_ms": 12000,
        "music_duration_s": 12.0,
        "format": "mp3",
        "output": output_path,
        "output_path": output_path,
    }
    assert (tmp_path / output_path).read_bytes() == b"mp3"
    assert result.artifacts == [output_path]
    jsonschema.validate(instance=result.data, schema=MinimaxMusic.output_schema)


def test_cosyvoice_tts_success_payload_includes_output_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    output_path = "projects/demo/assets/audio/cosyvoice.mp3"

    class FakeResponse:
        def json(self) -> dict[str, object]:
            return {
                "output": {
                    "audio": {
                        "data": base64.b64encode(b"mp3").decode("ascii"),
                    }
                }
            }

        def raise_for_status(self) -> None:
            return None

    def fake_format(content: bytes, fmt: str, output: Path) -> str:
        output.write_bytes(content)
        return fmt

    monkeypatch.setenv("DASHSCOPE_API_KEY", "test-key")
    monkeypatch.setattr("requests.post", lambda *args, **kwargs: FakeResponse())
    monkeypatch.setattr(CosyVoiceTTS, "_ensure_audio_format", staticmethod(fake_format))

    result = CosyVoiceTTS().execute({"text": "hello", "output_path": output_path})

    assert result.success
    assert result.data["output_path"] == output_path
    assert result.artifacts == [output_path]


def test_cosyvoice_tts_success_payload_matches_output_schema(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    output_path = "projects/demo/assets/audio/cosyvoice-schema.mp3"

    class FakeResponse:
        def json(self) -> dict[str, object]:
            return {
                "output": {
                    "audio": {
                        "data": base64.b64encode(b"mp3").decode("ascii"),
                    }
                }
            }

        def raise_for_status(self) -> None:
            return None

    def fake_format(content: bytes, fmt: str, output: Path) -> str:
        output.write_bytes(content)
        return fmt

    monkeypatch.setenv("DASHSCOPE_API_KEY", "test-key")
    monkeypatch.setattr("requests.post", lambda *args, **kwargs: FakeResponse())
    monkeypatch.setattr(CosyVoiceTTS, "_ensure_audio_format", staticmethod(fake_format))

    output_properties = CosyVoiceTTS.output_schema["properties"]
    assert {
        "provider",
        "model",
        "model_name",
        "voice",
        "voice_description",
        "text_length",
        "format",
        "actual_api_format",
        "output",
        "output_path",
    } <= set(output_properties)

    result = CosyVoiceTTS().execute(
        {
            "text": "hello",
            "voice": "Cherry",
            "model": "qwen3-tts-flash",
            "format": "mp3",
            "output_path": output_path,
        }
    )

    assert result.success is True
    assert result.data == {
        "provider": "bailian",
        "model": "qwen3-tts-flash",
        "model_name": "Qwen3 TTS Flash",
        "voice": "Cherry",
        "voice_description": "female, warm",
        "text_length": 5,
        "output": output_path,
        "format": "mp3",
        "actual_api_format": "mp3",
        "output_path": output_path,
    }
    assert (tmp_path / output_path).read_bytes() == b"mp3"
    assert result.artifacts == [output_path]
    jsonschema.validate(instance=result.data, schema=CosyVoiceTTS.output_schema)


def test_doubao_tts_success_payload_includes_output_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    output_path = "projects/demo/assets/audio/doubao.mp3"

    class FakeResponse:
        status_code = 200
        content = b"mp3"

        def json(self) -> dict[str, object]:
            return {"code": 20000000, "data": {"task_id": "task-1"}}

        def raise_for_status(self) -> None:
            return None

    monkeypatch.setenv("DOUBAO_SPEECH_API_KEY", "test-key")
    monkeypatch.setattr("requests.post", lambda *args, **kwargs: FakeResponse())
    monkeypatch.setattr("requests.get", lambda *args, **kwargs: FakeResponse())
    monkeypatch.setattr(
        DoubaoTTS,
        "_poll_query",
        lambda self, **kwargs: {
            "code": 20000000,
            "data": {
                "task_status": 2,
                "audio_url": "https://example.test/audio.mp3",
                "sentences": [],
            },
        },
    )
    monkeypatch.setattr(DoubaoTTS, "_audio_duration", staticmethod(lambda path: 1.25))

    result = DoubaoTTS().execute(
        {"text": "hello", "voice_id": "voice", "output_path": output_path}
    )

    assert result.success
    assert result.data["output_path"] == output_path
    assert result.artifacts[0] == output_path


def test_minimax_tts_success_payload_matches_output_schema(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    output_path = "projects/demo/assets/audio/minimax-voice.mp3"

    class FakeResponse:
        def json(self) -> dict[str, object]:
            return {
                "base_resp": {"status_code": 0, "status_msg": "success"},
                "data": {"audio": b"mp3".hex()},
                "extra_info": {"audio_length": 1250},
            }

        def raise_for_status(self) -> None:
            return None

    monkeypatch.setenv("MINIMAX_API_KEY", "test-key")
    monkeypatch.setattr("requests.post", lambda *args, **kwargs: FakeResponse())

    output_properties = MinimaxTTS.output_schema["properties"]
    assert {
        "provider",
        "model",
        "model_name",
        "voice",
        "voice_description",
        "text_length",
        "audio_length_s",
        "format",
        "output",
        "output_path",
    } <= set(output_properties)

    result = MinimaxTTS().execute(
        {"text": "hello", "voice": "Calm_Woman", "output_path": output_path}
    )

    assert result.success is True
    assert result.data == {
        "provider": "minimax",
        "model": "speech-2.8-hd",
        "model_name": "MiniMax Speech 2.8 HD",
        "voice": "Calm_Woman",
        "voice_description": MINIMAX_TTS_VOICES["Calm_Woman"],
        "text_length": 5,
        "audio_length_s": 1.25,
        "format": "mp3",
        "output": output_path,
        "output_path": output_path,
    }
    assert (tmp_path / output_path).read_bytes() == b"mp3"
    assert result.artifacts == [output_path]
    jsonschema.validate(instance=result.data, schema=MinimaxTTS.output_schema)


def test_suno_music_success_payload_includes_output_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    output_path = "projects/demo/assets/audio/suno.mp3"

    def fake_download(self: SunoMusic, audio_url: str, inputs: dict[str, Any], api_key: str) -> Path:
        path = Path(inputs["output_path"])
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"mp3")
        return path

    monkeypatch.setenv("SUNO_API_KEY", "test-key")
    monkeypatch.setattr(SunoMusic, "_submit", lambda self, inputs, api_key: "task-1")
    monkeypatch.setattr(
        SunoMusic,
        "_poll",
        lambda self, task_id, api_key: {
            "data": [
                {
                    "audio_url": "https://example.test/suno.mp3",
                    "duration": 12,
                    "id": "track-1",
                    "title": "Hook",
                }
            ]
        },
    )
    monkeypatch.setattr(SunoMusic, "_download", fake_download)

    result = SunoMusic().execute(
        {
            "prompt": "cinematic bed",
            "style": "ambient",
            "instrumental": True,
            "output_path": output_path,
        }
    )

    assert result.success
    assert result.data["output_path"] == output_path
    assert result.artifacts == [output_path]


def test_suno_music_success_payload_matches_output_schema(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    output_path = "projects/demo/assets/audio/suno-schema.mp3"

    def fake_download(
        self: SunoMusic,
        audio_url: str,
        inputs: dict[str, Any],
        api_key: str,
    ) -> Path:
        path = Path(inputs["output_path"])
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"mp3")
        return path

    monkeypatch.setenv("SUNO_API_KEY", "test-key")
    monkeypatch.setattr(SunoMusic, "_submit", lambda self, inputs, api_key: "task-1")
    monkeypatch.setattr(
        SunoMusic,
        "_poll",
        lambda self, task_id, api_key: {
            "data": [
                {
                    "audio_url": "https://example.test/suno.mp3",
                    "duration": 12,
                    "id": "track-1",
                    "title": "Hook",
                }
            ]
        },
    )
    monkeypatch.setattr(SunoMusic, "_download", fake_download)

    output_properties = SunoMusic.output_schema["properties"]
    assert {
        "provider",
        "model",
        "prompt",
        "style",
        "title",
        "instrumental",
        "duration_seconds",
        "format",
        "output",
        "output_path",
        "track_id",
        "tracks_generated",
    } <= set(output_properties)

    result = SunoMusic().execute(
        {
            "prompt": "cinematic bed",
            "style": "ambient",
            "instrumental": True,
            "model": "V4",
            "output_path": output_path,
        }
    )

    assert result.success is True
    assert result.data == {
        "provider": "suno",
        "model": "V4",
        "prompt": "cinematic bed",
        "style": "ambient",
        "title": "Hook",
        "instrumental": True,
        "duration_seconds": 12,
        "output": output_path,
        "output_path": output_path,
        "format": "mp3",
        "track_id": "track-1",
        "tracks_generated": 1,
    }
    assert (tmp_path / output_path).read_bytes() == b"mp3"
    assert result.artifacts == [output_path]
    jsonschema.validate(instance=result.data, schema=SunoMusic.output_schema)


@pytest.mark.parametrize(
    "tool",
    [
        FreesoundMusic(),
        PixabayMusic(),
    ],
)
def test_stock_music_success_payload_includes_output_path(
    tool: FreesoundMusic | PixabayMusic,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    output_path = f"projects/demo/assets/audio/{tool.name}.mp3"

    def fake_download(track: dict[str, object], inputs: dict[str, Any], *args: object) -> Path:
        path = Path(inputs["output_path"])
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"mp3")
        return path

    monkeypatch.setenv("FREESOUND_API_KEY", "test-key")
    monkeypatch.setattr(
        tool,
        "_search",
        lambda *args, **kwargs: [
            {
                "id": 123,
                "name": "Track",
                "title": "Track",
                "artist": "Artist",
                "duration": 60,
                "avg_rating": 4.5,
                "tags": ["ambient"],
                "username": "artist",
            }
        ],
    )
    monkeypatch.setattr(tool, "_download", fake_download)

    result = tool.execute({"query": "ambient score", "output_path": output_path})

    assert result.success
    assert result.data["output_path"] == output_path
    assert result.artifacts == [output_path]


@pytest.mark.parametrize(
    "tool",
    [
        FreesoundMusic(),
        PixabayMusic(),
    ],
)
def test_stock_music_success_payload_matches_output_schema(
    tool: FreesoundMusic | PixabayMusic,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    output_path = f"projects/demo/assets/audio/{tool.name}-schema.mp3"

    def fake_download(
        track: dict[str, object],
        inputs: dict[str, Any],
        *args: object,
    ) -> Path:
        path = Path(inputs["output_path"])
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"mp3")
        return path

    monkeypatch.setenv("FREESOUND_API_KEY", "test-key")
    monkeypatch.setattr(
        tool,
        "_search",
        lambda *args, **kwargs: [
            {
                "id": 123,
                "name": "Track",
                "title": "Track",
                "artist": "Artist",
                "duration": 60,
                "avg_rating": 4.5,
                "tags": ["ambient"],
                "username": "artist",
            }
        ],
    )
    monkeypatch.setattr(tool, "_download", fake_download)

    output_properties = tool.output_schema["properties"]
    common_fields = {
        "provider",
        "duration_seconds",
        "query",
        "format",
        "output",
        "output_path",
        "license",
        "results_found",
    }
    assert common_fields <= set(output_properties)

    result = tool.execute({"query": "ambient score", "output_path": output_path})

    assert result.success is True
    assert (tmp_path / output_path).read_bytes() == b"mp3"
    assert result.artifacts == [output_path]
    jsonschema.validate(instance=result.data, schema=tool.output_schema)

    if isinstance(tool, FreesoundMusic):
        assert result.data == {
            "provider": "freesound",
            "sound_id": 123,
            "name": "Track",
            "duration_seconds": 60,
            "avg_rating": 4.5,
            "tags": ["ambient"],
            "query": "ambient score",
            "output": output_path,
            "output_path": output_path,
            "format": "mp3",
            "license": "Creative Commons (check individual sound license)",
            "freesound_url": "https://freesound.org/people/artist/sounds/123/",
            "results_found": 1,
        }
    else:
        assert result.data == {
            "provider": "pixabay_music",
            "track_title": "Track",
            "artist": "Artist",
            "duration_seconds": 60,
            "query": "ambient score",
            "output": output_path,
            "output_path": output_path,
            "format": "mp3",
            "license": "Pixabay Content License (free, no attribution required)",
            "results_found": 1,
            "results_after_filter": 1,
        }


def test_qwen_asr_success_payload_includes_output_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    output_path = "projects/demo/artifacts/transcript.txt"

    class FakeResponse:
        def json(self) -> dict[str, object]:
            return {
                "output": {
                    "choices": [
                        {
                            "message": {
                                "content": [{"text": "Hello from the clip."}],
                                "annotations": [
                                    {"type": "audio_info", "language": "English"}
                                ],
                            }
                        }
                    ]
                }
            }

        def raise_for_status(self) -> None:
            return None

    monkeypatch.setenv("DASHSCOPE_API_KEY", "test-key")
    monkeypatch.setattr("requests.post", lambda *args, **kwargs: FakeResponse())

    result = QwenASR().execute(
        {
            "audio_url": "https://example.test/voice.mp3",
            "output_path": output_path,
        }
    )

    assert result.success
    assert result.data["output_path"] == output_path
    assert result.artifacts == [output_path]


def test_api_audio_generators_reject_non_project_output_path_before_requests(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("ELEVENLABS_API_KEY", "test-key")
    calls: list[object] = []

    def fake_post(*args: object, **kwargs: object) -> object:
        calls.append((args, kwargs))
        raise AssertionError("network should not be called for non-project output_path")

    monkeypatch.setattr("requests.post", fake_post)

    result = MusicGen().execute(
        {
            "prompt": "cinematic ambient bed",
            "duration_seconds": 12,
            "output_path": "music_output.mp3",
        }
    )

    assert result.success is False
    assert "projects/<project-name>/" in (result.error or "")
    assert calls == []


def test_doubao_tts_rejects_non_project_metadata_path_before_submit(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("DOUBAO_SPEECH_API_KEY", "test-key")
    calls: list[object] = []

    def fake_post(*args: object, **kwargs: object) -> object:
        calls.append((args, kwargs))
        raise AssertionError("Doubao should not submit with non-project metadata_path")

    monkeypatch.setattr("requests.post", fake_post)

    result = DoubaoTTS().execute(
        {
            "text": "hello",
            "voice_id": "voice",
            "output_path": "projects/test-audio/assets/audio/doubao.mp3",
            "metadata_path": "/tmp/doubao.mp3.json",
        }
    )

    assert result.success is False
    assert "metadata_path" in (result.error or "")
    assert "projects/<project-name>/" in (result.error or "")
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


def test_google_tts_service_account_file_is_advertised_available(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    key_file = tmp_path / "service-account.json"
    key_file.write_text("{}", encoding="utf-8")
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", str(key_file))

    assert GoogleTTS().get_status() == ToolStatus.AVAILABLE


def test_piper_tts_status_requires_piper_binary_even_if_python_module_exists(monkeypatch):
    monkeypatch.setattr("tools.base_tool.shutil.which", lambda _cmd: None)
    real_import = builtins.__import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "piper":
            return object()
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    assert PiperTTS().get_status() == ToolStatus.UNAVAILABLE


def test_doubao_tts_rejects_non_finite_metadata_before_writing_artifacts(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
):
    output_path = Path("projects/test-audio/assets/audio/doubao.mp3")
    metadata_path = Path("projects/test-audio/artifacts/doubao.mp3.json")
    get_calls: list[str] = []

    class FakeResponse:
        status_code = 200
        content = b"audio"

        def json(self) -> dict[str, Any]:
            return {"code": 20000000, "data": {"task_id": "task-1"}}

        def raise_for_status(self) -> None:
            return None

    def fake_get(url: str, *args: Any, **kwargs: Any) -> FakeResponse:
        get_calls.append(url)
        return FakeResponse()

    monkeypatch.setenv("DOUBAO_SPEECH_API_KEY", "test-key")
    monkeypatch.setitem(
        sys.modules,
        "requests",
        SimpleNamespace(post=lambda *args, **kwargs: FakeResponse(), get=fake_get),
    )
    monkeypatch.setattr(
        DoubaoTTS,
        "_poll_query",
        lambda self, **kwargs: {
            "code": 20000000,
            "data": {
                "task_status": 2,
                "audio_url": "https://example.test/audio.mp3",
                "sentences": [{"start_time": math.nan, "end_time": 1.0}],
            },
        },
    )
    monkeypatch.setattr(DoubaoTTS, "_audio_duration", staticmethod(lambda path: None))

    result = DoubaoTTS().execute(
        {
            "text": "hello",
            "voice_id": "voice",
            "output_path": str(output_path),
            "metadata_path": str(metadata_path),
        }
    )

    assert result.success is False
    assert "strict JSON" in (result.error or "")
    assert get_calls == []
    assert not output_path.exists()
    assert not metadata_path.exists()


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
            {"output_path": "doubao-a.mp3", "metadata_path": "doubao-a.mp3.json"},
        ),
        (
            DoubaoTTS(),
            {
                "text": "hello",
                "voice_id": "voice",
                "resource_id": "seed-tts-2.0",
                "speech_rate": 0,
                "sample_rate": 24000,
                "output_path": "doubao-a.mp3",
            },
            {"metadata_path": "doubao-b.mp3.json"},
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
