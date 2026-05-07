import jsonschema
import pytest

from tools.audio.qwen_asr import QwenASR


def test_qwen_asr_schema_accepts_local_audio_path_without_url():
    jsonschema.validate(
        instance={"audio_path": "/tmp/local.wav"},
        schema=QwenASR.input_schema,
    )


def test_qwen_asr_schema_requires_some_audio_source():
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(
            instance={"model": "qwen3-asr-flash"},
            schema=QwenASR.input_schema,
        )


def test_qwen_asr_idempotency_includes_local_audio_path():
    assert "audio_path" in QwenASR.idempotency_key_fields
