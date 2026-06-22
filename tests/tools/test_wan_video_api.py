import jsonschema
import pytest

from tools.video.wan_video_api import WanVideoAPI


class _FakeResponse:
    def __init__(self, json_data=None, content: bytes = b"") -> None:
        self._json_data = json_data or {}
        self.content = content

    def json(self):
        return self._json_data

    def raise_for_status(self) -> None:
        return None


@pytest.fixture
def wan_env(monkeypatch):
    monkeypatch.setenv("DASHSCOPE_API_KEY", "test-key")


def test_wan_success_payload_matches_output_schema(monkeypatch, tmp_path, wan_env):
    import requests

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("tools.video.wan_video_api.time.sleep", lambda _seconds: None)
    download_url = "https://cdn.example.test/wan.mp4"

    def fake_post(*_args, **_kwargs):
        return _FakeResponse({"output": {"task_id": "task-1"}})

    def fake_get(url, *_args, **_kwargs):
        if url.endswith("/tasks/task-1"):
            return _FakeResponse(
                {"output": {"task_status": "SUCCEEDED", "video_url": download_url}}
            )
        if url == download_url:
            return _FakeResponse(content=b"fake wan mp4")
        raise AssertionError(f"unexpected GET URL: {url}")

    monkeypatch.setattr(requests, "post", fake_post)
    monkeypatch.setattr(requests, "get", fake_get)

    output_path = "projects/demo/assets/video/wan-api.mp4"
    result = WanVideoAPI().execute(
        {"prompt": "A landscape hero shot", "output_path": output_path}
    )

    assert result.success, result.error
    assert result.data["output_path"] == output_path
    assert result.data["format"] == "mp4"
    assert (tmp_path / output_path).read_bytes() == b"fake wan mp4"
    output_properties = WanVideoAPI.output_schema["properties"]
    assert {
        "provider",
        "model",
        "model_name",
        "prompt",
        "operation",
        "duration",
        "output",
        "output_path",
        "format",
        "file_size_bytes",
    } <= set(output_properties)
    jsonschema.validate(instance=result.data, schema=WanVideoAPI.output_schema)


def test_wan_rejects_model_variant_operation_mismatch(monkeypatch, wan_env):
    import requests

    def fail_post(*_args, **_kwargs):
        raise AssertionError("network called before local input validation")

    monkeypatch.setattr(requests, "post", fail_post)

    result = WanVideoAPI().execute(
        {
            "prompt": "A landscape hero shot",
            "operation": "text_to_video",
            "model_variant": "wan2.7-i2v",
        }
    )

    assert not result.success
    assert "model_variant 'wan2.7-i2v' supports image_to_video" in result.error


def test_wan_rejects_unknown_model_variant(monkeypatch, wan_env):
    import requests

    def fail_post(*_args, **_kwargs):
        raise AssertionError("network called before local input validation")

    monkeypatch.setattr(requests, "post", fail_post)

    result = WanVideoAPI().execute(
        {
            "prompt": "A landscape hero shot",
            "operation": "text_to_video",
            "model_variant": "wan2.7-unknown",
        }
    )

    assert not result.success
    assert "Unknown model_variant 'wan2.7-unknown'" in result.error


def test_wan_schema_rejects_operation_specific_missing_inputs():
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(
            instance={
                "prompt": "Move from a product still",
                "operation": "image_to_video",
            },
            schema=WanVideoAPI.input_schema,
        )

    jsonschema.validate(
        instance={
            "prompt": "Move from a product still",
            "operation": "image_to_video",
            "image_url": "https://example.test/product.png",
            "output_path": "projects/demo/assets/video/wan-i2v.mp4",
        },
        schema=WanVideoAPI.input_schema,
    )


def test_wan_schema_rejects_model_variant_operation_mismatch():
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(
            instance={
                "prompt": "A landscape hero shot",
                "operation": "text_to_video",
                "model_variant": "wan2.7-i2v",
            },
            schema=WanVideoAPI.input_schema,
        )

    jsonschema.validate(
        instance={
            "prompt": "Move from a product still",
            "operation": "image_to_video",
            "model_variant": "wan2.7-i2v",
            "image_url": "https://example.test/product.png",
            "output_path": "projects/demo/assets/video/wan-variant-i2v.mp4",
        },
        schema=WanVideoAPI.input_schema,
    )


def test_wan_idempotency_includes_conditioning_inputs():
    tool = WanVideoAPI()

    first = tool.idempotency_key(
        {
            "prompt": "Move from a product still",
            "operation": "image_to_video",
            "model_variant": "wan2.7-i2v",
            "image_url": "https://example.test/a.png",
            "seed": 7,
        }
    )
    second = tool.idempotency_key(
        {
            "prompt": "Move from a product still",
            "operation": "image_to_video",
            "model_variant": "wan2.7-i2v",
            "image_url": "https://example.test/b.png",
            "seed": 7,
        }
    )

    assert first != second

    jsonschema.validate(
        instance={
            "prompt": "A landscape hero shot",
            "model_variant": "wan2.6-t2v",
            "output_path": "projects/demo/assets/video/wan-t2v.mp4",
        },
        schema=WanVideoAPI.input_schema,
    )
