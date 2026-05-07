from __future__ import annotations

import jsonschema
import pytest

from tools.graphics.wanx_image import WanxImage


def test_wanx_schema_requires_ref_images_for_multi_image_reference():
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(
            instance={
                "prompt": "Create a product image using the supplied references",
                "operation": "multi_image_reference",
                "model": "wan2.7-image-pro",
            },
            schema=WanxImage.input_schema,
        )

    jsonschema.validate(
        instance={
            "prompt": "Create a product image using the supplied references",
            "operation": "multi_image_reference",
            "model": "wan2.7-image-pro",
            "ref_images": ["https://example.test/product.png"],
        },
        schema=WanxImage.input_schema,
    )


def test_wanx_multi_image_reference_uses_wan27_message_images(monkeypatch, tmp_path):
    monkeypatch.setenv("DASHSCOPE_API_KEY", "test-key")
    captured: dict[str, object] = {}

    class FakeResponse:
        def __init__(self, payload: dict[str, object]):
            self._payload = payload

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return self._payload

    def fake_post(url: str, **kwargs: object) -> FakeResponse:
        captured["url"] = url
        captured["payload"] = kwargs["json"]
        return FakeResponse({"output": {"task_id": "task-123"}})

    monkeypatch.setattr("requests.post", fake_post)
    monkeypatch.setattr(
        WanxImage,
        "_poll_task",
        lambda self, task_id, api_key, api_style="standard": (
            "SUCCEEDED",
            [{"url": "https://example.test/out.png", "seed": 123}],
        ),
    )
    monkeypatch.setattr(
        WanxImage,
        "_download_images",
        lambda self, results, output_path_hint, model: [str(tmp_path / "out.png")],
    )

    result = WanxImage().execute(
        {
            "prompt": "Create a consistent product hero image",
            "operation": "multi_image_reference",
            "model": "wan2.7-image-pro",
            "ref_images": [
                "https://example.test/product.png",
                "https://example.test/style.png",
            ],
            "output_path": str(tmp_path / "out.png"),
        }
    )

    assert result.success
    payload = captured["payload"]
    content = payload["input"]["messages"][0]["content"]
    assert content[:2] == [
        {"image": "https://example.test/product.png"},
        {"image": "https://example.test/style.png"},
    ]
    assert content[-1] == {"text": "Create a consistent product hero image"}


@pytest.mark.parametrize("ref_path", ["C:/assets/ref.png", r"C:\assets\ref.png"])
def test_wanx_windows_drive_ref_images_are_encoded_as_local_files(
    monkeypatch, ref_path
):
    class ExistingPath:
        def __init__(self, value: str):
            self.value = value

        def exists(self) -> bool:
            return True

    monkeypatch.setattr("tools.graphics.wanx_image.Path", ExistingPath)
    monkeypatch.setattr(
        WanxImage,
        "_file_to_b64",
        lambda self, value: f"data:image/png;base64,encoded-{value}",
    )

    resolved, err = WanxImage()._resolve_image_reference(ref_path)

    assert err is None
    assert resolved == f"data:image/png;base64,encoded-{ref_path}"
