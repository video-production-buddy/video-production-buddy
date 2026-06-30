from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import jsonschema

from tools.audio.openai_tts import OpenAITTS
from tools.graphics.wanx_image import WanxImage


class _FakeResponse:
    def __init__(self, payload: dict | None = None, content: bytes = b"payload") -> None:
        self._payload = payload or {}
        self.content = content

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


def test_openai_tts_requires_output_path_before_client_creation(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    calls: list[str] = []

    class FakeOpenAI:
        def __init__(self) -> None:
            calls.append("client")
            raise AssertionError("OpenAI client should not be created")

    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=FakeOpenAI))

    result = OpenAITTS().execute({"text": "hello"})

    assert result.success is False
    assert "output_path is required" in (result.error or "")
    assert calls == []


def test_openai_tts_success_payload_matches_output_schema(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    captured_kwargs: dict[str, object] = {}

    class FakeStreamingResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_exc_info):
            return None

        def stream_to_file(self, output_path: Path) -> None:
            output_path.write_bytes(b"mp3")

    class FakeSpeech:
        class with_streaming_response:
            @staticmethod
            def create(**kwargs):
                captured_kwargs.update(kwargs)
                return FakeStreamingResponse()

    class FakeOpenAI:
        audio = SimpleNamespace(speech=FakeSpeech())

    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=FakeOpenAI))
    monkeypatch.setattr("tools.analysis.audio_probe.probe_duration", lambda _path: 1.25)

    output_path = "projects/demo/assets/audio/openai.mp3"
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
    assert captured_kwargs["input"] == "hello"
    assert result.data["output"] == output_path
    assert result.data["output_path"] == output_path
    assert result.artifacts == [output_path]
    assert (tmp_path / output_path).read_bytes() == b"mp3"
    jsonschema.validate(instance=result.data, schema=OpenAITTS.output_schema)


def test_wanx_image_requires_project_output_path_before_network(monkeypatch) -> None:
    monkeypatch.setenv("DASHSCOPE_API_KEY", "test-key")
    calls: list[object] = []

    def fake_post(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("Wanx should not call network for invalid output_path")

    monkeypatch.setattr("requests.post", fake_post)

    result = WanxImage().execute({"prompt": "product hero", "output_path": "wanx.png"})

    assert result.success is False
    assert "output_path" in (result.error or "")
    assert "projects/<project-name>/" in (result.error or "")
    assert calls == []


def test_wanx_image_success_payload_matches_output_schema(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DASHSCOPE_API_KEY", "test-key")
    monkeypatch.setenv("DASHSCOPE_WORKSPACE_ID", "ws-test")
    monkeypatch.setenv("DASHSCOPE_REGION", "ap-southeast-1")
    monkeypatch.setattr("time.sleep", lambda _seconds: None)
    post_calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    def fake_post(*args, **kwargs):
        post_calls.append((args, kwargs))
        return _FakeResponse(
            {
                "output": {
                    "choices": [
                        {
                            "message": {
                                "content": [
                                    {"image": "https://cdn.example.test/wanx.png"}
                                ]
                            }
                        }
                    ],
                    "seed": 123,
                }
            }
        )

    def fake_get(url, *_args, **_kwargs):
        if url == "https://cdn.example.test/wanx.png":
            return _FakeResponse(content=b"png")
        raise AssertionError(f"unexpected GET {url}")

    monkeypatch.setattr("requests.post", fake_post)
    monkeypatch.setattr("requests.get", fake_get)

    output_path = "projects/demo/assets/images/wanx.png"
    result = WanxImage().execute({"prompt": "product hero", "output_path": output_path})

    assert result.success is True
    assert post_calls[0][0][0] == (
        "https://ws-test.ap-southeast-1.maas.aliyuncs.com"
        "/api/v1/services/aigc/multimodal-generation/generation"
    )
    assert result.data["output"] == output_path
    assert result.data["output_path"] == output_path
    assert result.artifacts == [output_path]
    assert (tmp_path / output_path).read_bytes() == b"png"
    jsonschema.validate(instance=result.data, schema=WanxImage.output_schema)
