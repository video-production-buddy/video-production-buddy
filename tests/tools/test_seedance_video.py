import jsonschema
import pytest

from tools.video.seedance_video import SeedanceVideo


class _FakeResponse:
    def __init__(self, json_data=None, content: bytes = b"", status_code: int = 200):
        self._json_data = json_data or {}
        self.content = content
        self.status_code = status_code

    def json(self):
        return self._json_data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


@pytest.fixture
def seedance_env(monkeypatch):
    monkeypatch.setenv("FAL_KEY", "test-key")
    monkeypatch.setattr("tools.video.seedance_video.time.sleep", lambda _seconds: None)

    import tools.video._shared as shared

    monkeypatch.setattr(shared, "probe_output", lambda _path: {"duration_seconds": 1.0})


def test_seedance_polls_returned_queue_urls(monkeypatch, tmp_path, seedance_env):
    """Seedance must poll the queue URLs returned by the same submission."""
    import requests

    model_path = "bytedance/seedance-2.0/text-to-video"
    submit_url = f"https://queue.fal.run/{model_path}"
    status_url = f"{submit_url}/requests/req-123/status"
    response_url = f"{submit_url}/requests/req-123"
    video_url = "https://cdn.example.test/seedance.mp4"
    get_urls: list[str] = []

    def fake_post(url, **_kwargs):
        assert url == submit_url
        return _FakeResponse(
            {
                "request_id": "req-123",
                "status_url": status_url,
                "response_url": response_url,
            }
        )

    def fake_get(url, **_kwargs):
        get_urls.append(url)
        if url == status_url:
            return _FakeResponse({"status": "COMPLETED"})
        if url == response_url:
            return _FakeResponse({"video": {"url": video_url}, "seed": 42})
        if url == video_url:
            return _FakeResponse(content=b"fake-video")
        raise AssertionError(f"unexpected GET URL: {url}")

    monkeypatch.setattr(requests, "post", fake_post)
    monkeypatch.setattr(requests, "get", fake_get)

    out = tmp_path / "seedance.mp4"
    result = SeedanceVideo().execute({"prompt": "A calm product reveal", "output_path": str(out)})

    assert result.success, result.error
    assert out.read_bytes() == b"fake-video"
    assert status_url in get_urls
    assert response_url in get_urls
    assert not any("/fal-ai/bytedance/" in url for url in get_urls)


def test_seedance_fallback_queue_urls_match_submission_base(monkeypatch, tmp_path, seedance_env):
    """If fal.ai omits queue URLs, construct them from the POST base path."""
    import requests

    model_path = "bytedance/seedance-2.0/fast/image-to-video"
    submit_url = f"https://queue.fal.run/{model_path}"
    status_url = f"{submit_url}/requests/req-fallback/status"
    response_url = f"{submit_url}/requests/req-fallback"
    video_url = "https://cdn.example.test/seedance-fallback.mp4"
    get_urls: list[str] = []

    def fake_post(url, **_kwargs):
        assert url == submit_url
        return _FakeResponse({"request_id": "req-fallback"})

    def fake_get(url, **_kwargs):
        get_urls.append(url)
        if url == status_url:
            return _FakeResponse({"status": "COMPLETED"})
        if url == response_url:
            return _FakeResponse({"video": {"url": video_url}, "seed": 11})
        if url == video_url:
            return _FakeResponse(content=b"fake-video")
        raise AssertionError(f"unexpected GET URL: {url}")

    monkeypatch.setattr(requests, "post", fake_post)
    monkeypatch.setattr(requests, "get", fake_get)

    out = tmp_path / "seedance-fallback.mp4"
    result = SeedanceVideo().execute(
        {
            "prompt": "A calm product reveal",
            "operation": "image_to_video",
            "model_variant": "fast",
            "image_url": "https://example.test/start.png",
            "output_path": str(out),
        }
    )

    assert result.success, result.error
    assert out.read_bytes() == b"fake-video"
    assert status_url in get_urls
    assert response_url in get_urls
    assert not any("/fal-ai/bytedance/" in url for url in get_urls)


def test_seedance_image_to_video_requires_start_frame(monkeypatch, seedance_env):
    import requests

    def fail_post(*_args, **_kwargs):
        raise AssertionError("network called before local input validation")

    monkeypatch.setattr(requests, "post", fail_post)

    result = SeedanceVideo().execute(
        {
            "prompt": "A product starts moving",
            "operation": "image_to_video",
        }
    )

    assert not result.success
    assert "image_to_video requires image_url or image_path" in result.error


def test_seedance_reference_to_video_requires_reference_inputs(monkeypatch, seedance_env):
    import requests

    def fail_post(*_args, **_kwargs):
        raise AssertionError("network called before local input validation")

    monkeypatch.setattr(requests, "post", fail_post)

    result = SeedanceVideo().execute(
        {
            "prompt": "Keep the same character identity",
            "operation": "reference_to_video",
        }
    )

    assert not result.success
    assert "reference_to_video requires reference_image_urls, reference_image_paths, reference_video_urls, or reference_audio_urls" in result.error


def test_seedance_schema_requires_image_to_video_start_frame():
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(
            instance={
                "prompt": "A product starts moving",
                "operation": "image_to_video",
            },
            schema=SeedanceVideo.input_schema,
        )

    jsonschema.validate(
        instance={
            "prompt": "A product starts moving",
            "operation": "image_to_video",
            "image_url": "https://example.test/start.png",
        },
        schema=SeedanceVideo.input_schema,
    )


def test_seedance_schema_requires_reference_to_video_inputs():
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(
            instance={
                "prompt": "Keep the same character identity",
                "operation": "reference_to_video",
            },
            schema=SeedanceVideo.input_schema,
        )

    jsonschema.validate(
        instance={
            "prompt": "Keep the same character identity",
            "operation": "reference_to_video",
            "reference_image_urls": ["https://example.test/ref.png"],
        },
        schema=SeedanceVideo.input_schema,
    )


def test_seedance_idempotency_includes_conditioning_inputs():
    tool = SeedanceVideo()

    first = tool.idempotency_key(
        {
            "prompt": "A product starts moving",
            "operation": "image_to_video",
            "image_url": "https://example.test/a.png",
            "seed": 7,
        }
    )
    second = tool.idempotency_key(
        {
            "prompt": "A product starts moving",
            "operation": "image_to_video",
            "image_url": "https://example.test/b.png",
            "seed": 7,
        }
    )

    assert first != second
