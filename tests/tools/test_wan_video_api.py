import jsonschema
import pytest

from tools.video.wan_video_api import WanVideoAPI


@pytest.fixture
def wan_env(monkeypatch):
    monkeypatch.setenv("DASHSCOPE_API_KEY", "test-key")


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
        },
        schema=WanVideoAPI.input_schema,
    )
