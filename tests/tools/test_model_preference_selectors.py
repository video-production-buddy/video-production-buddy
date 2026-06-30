from __future__ import annotations

import jsonschema

from lib.model_preferences import apply_model_preferences
from lib.scoring import ProviderScore
from tools.audio.music_selector import MusicSelector
from tools.audio.transcription_selector import TranscriptionSelector
from tools.audio.tts_selector import TTSSelector
from tools.base_tool import ToolResult, ToolStatus
from tools.text.text_selector import TextSelector


class _FakeProvider:
    def __init__(
        self,
        name: str,
        provider: str,
        *,
        capability: str,
        model_id: str | None = None,
        props: dict[str, object] | None = None,
    ) -> None:
        self.name = name
        self.provider = provider
        self.capability = capability
        self.best_for = []
        self.agent_skills = []
        self.supports = {}
        self.calls: list[dict[str, object]] = []
        self.cost_calls: list[dict[str, object]] = []
        self.model_options = (
            [{"id": model_id, "field": "model", "default": True}]
            if model_id
            else []
        )
        self.input_schema = {
            "properties": props or {
                "prompt": {"type": "string"},
                "messages": {"type": "array"},
                "audio_url": {"type": "string"},
                "audio_path": {"type": "string"},
                "model": {"type": "string"},
                "output_path": {"type": "string"},
            }
        }

    def get_status(self) -> ToolStatus:
        return ToolStatus.AVAILABLE

    def get_info(self) -> dict[str, object]:
        return {
            "name": self.name,
            "provider": self.provider,
            "capability": self.capability,
            "agent_skills": self.agent_skills,
            "usage_location": __file__,
            "best_for": self.best_for,
            "supports": self.supports,
            "model_options": self.model_options,
            "input_schema": self.input_schema,
        }

    def estimate_cost(self, inputs: dict[str, object]) -> float:
        self.cost_calls.append(dict(inputs))
        return 0.02 if inputs.get("model") == "speech-2.8-turbo" else 0.01

    def execute(self, inputs: dict[str, object]) -> ToolResult:
        self.calls.append(dict(inputs))
        return ToolResult(
            success=True,
            data={
                "inputs": dict(inputs),
                "output": inputs.get("output_path"),
                "output_path": inputs.get("output_path"),
            },
        )


def _rank_as(*providers: _FakeProvider) -> list[ProviderScore]:
    return [
        ProviderScore(
            tool_name=tool.name,
            provider=tool.provider,
            task_fit=1.0 - idx / 10,
        )
        for idx, tool in enumerate(providers)
    ]


def test_new_selector_output_schemas_declare_generation_and_rank_shapes() -> None:
    cases = [
        (MusicSelector(), "projects/demo/assets/audio/music.mp3"),
        (TextSelector(), None),
        (TranscriptionSelector(), None),
    ]

    for selector, output_path in cases:
        assert "output_path" in selector.output_schema["properties"]
        assert "anyOf" in selector.output_schema

        generation_payload = {
            "selected_tool": "provider_tool",
            "selected_provider": "provider",
            "selection_reason": "Selected provider",
            "output": output_path,
            "output_path": output_path,
            "alternatives_considered": [],
        }
        jsonschema.validate(instance=generation_payload, schema=selector.output_schema)

        rank_payload = {
            "rankings": [],
            "explanation": "",
            "normalized_task_context": {},
        }
        jsonschema.validate(instance=rank_payload, schema=selector.output_schema)


def test_music_selector_idempotency_includes_local_reference_audio_path() -> None:
    selector = MusicSelector()
    base = {
        "prompt": "cover this reference",
        "audio_path": "projects/demo/assets/audio/reference-a.wav",
        "output_path": "projects/demo/assets/audio/cover.mp3",
    }

    assert "audio_path" in selector.idempotency_key_fields
    assert selector.idempotency_key(base) != selector.idempotency_key(
        {**base, "audio_path": "projects/demo/assets/audio/reference-b.wav"}
    )


def test_music_selector_idempotency_includes_remote_reference_audio_url() -> None:
    selector = MusicSelector()
    base = {
        "prompt": "cover this reference",
        "audio_url": "https://example.test/reference-a.wav",
        "output_path": "projects/demo/assets/audio/cover.mp3",
    }

    assert "audio_url" in selector.idempotency_key_fields
    assert selector.idempotency_key(base) != selector.idempotency_key(
        {**base, "audio_url": "https://example.test/reference-b.wav"}
    )


def test_music_selector_env_provider_and_model_route_to_matching_tool(
    monkeypatch,
) -> None:
    selector = MusicSelector()
    selected = _FakeProvider(
        "minimax_music",
        "minimax",
        capability="music_generation",
        model_id="music-2.6-free",
    )
    fallback = _FakeProvider(
        "suno_music",
        "suno",
        capability="music_generation",
        model_id="V4",
    )

    monkeypatch.setenv("VPB_MUSIC_GENERATION_PROVIDER", "minimax")
    monkeypatch.setenv("VPB_MUSIC_GENERATION_MODEL", "music-2.6-free")
    monkeypatch.setattr(selector, "_providers", lambda: [selected, fallback])
    monkeypatch.setattr(
        "lib.scoring.rank_providers",
        lambda _candidates, _ctx: _rank_as(fallback, selected),
    )

    result = selector.execute(
        {
            "prompt": "quiet cinematic bed",
            "preferred_provider": "auto",
            "output_path": "projects/demo/assets/audio/music.mp3",
        }
    )

    assert result.success
    assert selected.calls[0]["model"] == "music-2.6-free"
    assert "preferred_provider" not in selected.calls[0]
    assert not fallback.calls
    assert result.data["selected_tool"] == "minimax_music"
    jsonschema.validate(instance=result.data, schema=selector.output_schema)


def test_text_selector_model_only_env_preference_filters_matching_provider(
    monkeypatch,
) -> None:
    selector = TextSelector()
    selected = _FakeProvider(
        "minimax_chat",
        "minimax",
        capability="text_generation",
        model_id="MiniMax-M3",
    )
    fallback = _FakeProvider(
        "qwen_chat",
        "bailian",
        capability="text_generation",
        model_id="qwen3.7-plus",
    )

    monkeypatch.setenv("VPB_TEXT_GENERATION_MODEL", "MiniMax-M3")
    monkeypatch.setattr(selector, "_providers", lambda: [selected, fallback])
    monkeypatch.setattr(
        "lib.scoring.rank_providers",
        lambda _candidates, _ctx: _rank_as(fallback, selected),
    )

    result = selector.execute({"prompt": "Polish this line."})

    assert result.success
    assert selected.calls[0]["model"] == "MiniMax-M3"
    assert not fallback.calls
    assert result.data["selected_provider"] == "minimax"
    jsonschema.validate(instance=result.data, schema=selector.output_schema)


def test_text_selector_does_not_fall_through_when_env_provider_model_conflict(
    monkeypatch,
) -> None:
    selector = TextSelector()
    minimax = _FakeProvider(
        "minimax_chat",
        "minimax",
        capability="text_generation",
        model_id="MiniMax-M3",
    )
    qwen = _FakeProvider(
        "qwen_chat",
        "bailian",
        capability="text_generation",
        model_id="qwen3.7-plus",
    )

    monkeypatch.setenv("VPB_TEXT_GENERATION_PROVIDER", "bailian")
    monkeypatch.setenv("VPB_TEXT_GENERATION_MODEL", "MiniMax-M3")
    monkeypatch.setattr(selector, "_providers", lambda: [minimax, qwen])
    monkeypatch.setattr(
        "lib.scoring.rank_providers",
        lambda _candidates, _ctx: _rank_as(minimax, qwen),
    )

    result = selector.execute({"prompt": "Polish this line."})

    assert not result.success
    assert "No text generation provider available" in (result.error or "")
    assert minimax.calls == []
    assert qwen.calls == []


def test_text_selector_explicit_provider_and_model_win_over_env(
    monkeypatch,
) -> None:
    selector = TextSelector()
    selected = _FakeProvider(
        "qwen_chat",
        "bailian",
        capability="text_generation",
        model_id="qwen3.7-plus",
    )
    fallback = _FakeProvider(
        "minimax_chat",
        "minimax",
        capability="text_generation",
        model_id="MiniMax-M3",
    )

    monkeypatch.setenv("VPB_TEXT_GENERATION_PROVIDER", "minimax")
    monkeypatch.setenv("VPB_TEXT_GENERATION_MODEL", "MiniMax-M3")
    monkeypatch.setattr(selector, "_providers", lambda: [selected, fallback])
    monkeypatch.setattr(
        "lib.scoring.rank_providers",
        lambda _candidates, _ctx: _rank_as(fallback, selected),
    )

    result = selector.execute(
        {
            "prompt": "Polish this line.",
            "preferred_provider": "bailian",
            "model": "qwen3.7-plus",
        }
    )

    assert result.success
    assert selected.calls[0]["model"] == "qwen3.7-plus"
    assert not fallback.calls
    assert result.data["selected_tool"] == "qwen_chat"


def test_model_preferences_do_not_apply_env_model_to_explicit_provider(
    monkeypatch,
) -> None:
    monkeypatch.setenv("VPB_VIDEO_GENERATION_PROVIDER", "kling")
    monkeypatch.setenv("VPB_VIDEO_GENERATION_ALLOWED_PROVIDERS", "kling")
    monkeypatch.setenv("VPB_VIDEO_GENERATION_MODEL", "gen4.5")

    merged = apply_model_preferences(
        {"preferred_provider": "runway", "prompt": "cinematic product reveal"},
        "video_generation",
    )

    assert merged["preferred_provider"] == "runway"
    assert "allowed_providers" not in merged
    assert "model_variant" not in merged


def test_model_preferences_do_not_import_env_provider_to_explicit_allowed_list(
    monkeypatch,
) -> None:
    monkeypatch.setenv("VPB_VIDEO_GENERATION_PROVIDER", "minimax")
    monkeypatch.setenv("VPB_VIDEO_GENERATION_ALLOWED_PROVIDERS", "minimax")
    monkeypatch.setenv("VPB_VIDEO_GENERATION_MODEL", "MiniMax-Hailuo-2.3")

    merged = apply_model_preferences(
        {
            "prompt": "cinematic product reveal",
            "preferred_provider": "auto",
            "allowed_providers": ["runway"],
        },
        "video_generation",
    )

    assert merged["preferred_provider"] == "auto"
    assert merged["allowed_providers"] == ["runway"]
    assert "model_variant" not in merged


def test_model_filter_reads_explicit_video_model_alias() -> None:
    from lib.model_preferences import filter_model_candidates

    runway = _FakeProvider(
        "runway_video",
        "runway",
        capability="video_generation",
        model_id="gen4.5",
    )
    seedance = _FakeProvider(
        "seedance_video",
        "seedance",
        capability="video_generation",
        model_id="seedance2",
    )

    assert filter_model_candidates(
        {"model": "gen4.5"},
        "video_generation",
        [seedance, runway],
    ) == [runway]


def test_music_selector_maps_instrumental_aliases_to_selected_provider(
    monkeypatch,
) -> None:
    selector = MusicSelector()
    suno = _FakeProvider(
        "suno_music",
        "suno",
        capability="music_generation",
        props={
            "prompt": {"type": "string"},
            "instrumental": {"type": "boolean"},
            "output_path": {"type": "string"},
        },
    )
    minimax = _FakeProvider(
        "minimax_music",
        "minimax",
        capability="music_generation",
        props={
            "prompt": {"type": "string"},
            "is_instrumental": {"type": "boolean"},
            "output_path": {"type": "string"},
        },
    )

    monkeypatch.setattr(selector, "_providers", lambda: [suno, minimax])
    monkeypatch.setattr(
        "lib.scoring.rank_providers",
        lambda _candidates, _ctx: _rank_as(suno, minimax),
    )

    result = selector.execute(
        {
            "prompt": "cinematic song with vocals",
            "is_instrumental": False,
            "output_path": "projects/demo/assets/audio/song.mp3",
        }
    )

    assert result.success
    assert suno.calls[0]["instrumental"] is False
    assert "is_instrumental" not in suno.calls[0]

    monkeypatch.setattr(
        "lib.scoring.rank_providers",
        lambda _candidates, _ctx: _rank_as(minimax, suno),
    )

    result = selector.execute(
        {
            "prompt": "cinematic song with vocals",
            "instrumental": False,
            "output_path": "projects/demo/assets/audio/song-2.mp3",
        }
    )

    assert result.success
    assert minimax.calls[0]["is_instrumental"] is False
    assert "instrumental" not in minimax.calls[0]


def test_tts_selector_rejects_env_model_when_schema_default_mismatches(
    monkeypatch,
) -> None:
    selector = TTSSelector()
    openai = _FakeProvider(
        "openai_tts",
        "openai",
        capability="tts",
    )
    openai.input_schema["properties"]["model"] = {
        "type": "string",
        "default": "gpt-4o-mini-tts",
    }

    monkeypatch.setenv("VPB_TTS_MODEL", "speech-2.8-hd")
    monkeypatch.setattr(selector, "_providers", lambda: [openai])

    result = selector.execute(
        {
            "text": "Narration line.",
            "output_path": "projects/demo/assets/audio/narration.mp3",
        }
    )

    assert not result.success
    assert "No TTS provider available" in (result.error or "")
    assert openai.calls == []


def test_tts_selector_estimates_with_provider_adapted_model_field(
    monkeypatch,
) -> None:
    selector = TTSSelector()
    minimax = _FakeProvider(
        "minimax_tts",
        "minimax",
        capability="tts",
        model_id="speech-2.8-turbo",
    )

    monkeypatch.setenv("VPB_TTS_PROVIDER", "minimax")
    monkeypatch.setenv("VPB_TTS_MODEL", "speech-2.8-turbo")
    monkeypatch.setattr(selector, "_providers", lambda: [minimax])
    monkeypatch.setattr(
        "lib.scoring.rank_providers",
        lambda candidates, _ctx: _rank_as(*candidates),
    )

    cost = selector.estimate_cost({"text": "Narration line."})

    assert cost == 0.02
    assert minimax.cost_calls[0]["model"] == "speech-2.8-turbo"
    assert "model_id" not in minimax.cost_calls[0]


def test_transcription_selector_env_preferences_pass_model(monkeypatch) -> None:
    selector = TranscriptionSelector()
    selected = _FakeProvider(
        "qwen_asr",
        "bailian",
        capability="transcription",
        model_id="qwen3-asr-flash",
    )

    monkeypatch.setenv("VPB_TRANSCRIPTION_PROVIDER", "bailian")
    monkeypatch.setenv("VPB_TRANSCRIPTION_MODEL", "qwen3-asr-flash")
    monkeypatch.setattr(selector, "_providers", lambda: [selected])
    monkeypatch.setattr(
        "lib.scoring.rank_providers",
        lambda candidates, _ctx: _rank_as(*candidates),
    )

    result = selector.execute(
        {"audio_url": "https://example.test/speech.wav"}
    )

    assert result.success
    assert selected.calls[0]["model"] == "qwen3-asr-flash"
    assert result.data["selected_tool"] == "qwen_asr"
    jsonschema.validate(instance=result.data, schema=selector.output_schema)
