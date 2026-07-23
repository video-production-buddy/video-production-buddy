from __future__ import annotations

import jsonschema
import pytest

from tools.base_tool import ToolResult
from tools.graphics.atlascloud_image import AtlasCloudImage
from tools.video.atlascloud_video import AtlasCloudVideo


class _FakeResponse:
    def __init__(
        self,
        payload: dict | None = None,
        content: bytes = b"fake media",
    ) -> None:
        self._payload = payload or {}
        self.content = content

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


def _fail_network(*_args, **_kwargs):
    raise AssertionError("network called before local input validation")


def test_atlascloud_providers_declare_matching_agent_skills() -> None:
    assert AtlasCloudImage.agent_skills == ["atlas-cloud"]
    assert AtlasCloudVideo.agent_skills == [
        "atlas-cloud",
        "ai-video-gen",
    ]


def test_atlascloud_image_requires_project_output_path_before_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("ATLASCLOUD_API_KEY", raising=False)
    monkeypatch.setattr("requests.post", _fail_network)

    result = AtlasCloudImage().execute(
        {"prompt": "Product hero image", "output_path": "atlascloud.png"}
    )

    assert isinstance(result, ToolResult)
    assert not result.success
    assert "output_path" in (result.error or "")
    assert "projects/<project-name>/" in (result.error or "")


def test_atlascloud_image_success_payload_matches_live_schema(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ATLASCLOUD_API_KEY", "test-key")
    monkeypatch.setattr("time.sleep", lambda _seconds: None)
    captured: dict[str, object] = {}

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured["headers"] = kwargs["headers"]
        captured["json"] = kwargs["json"]
        return _FakeResponse({"data": {"id": "prediction-1", "status": "starting"}})

    def fake_get(url, **_kwargs):
        if url.endswith("/model/prediction/prediction-1"):
            return _FakeResponse(
                {
                    "data": {
                        "status": "completed",
                        "outputs": ["https://cdn.example.test/atlascloud.png"],
                    }
                }
            )
        if url == "https://cdn.example.test/atlascloud.png":
            return _FakeResponse(content=b"fake png")
        raise AssertionError(f"unexpected GET {url}")

    monkeypatch.setattr("requests.post", fake_post)
    monkeypatch.setattr("requests.get", fake_get)

    output_path = "projects/demo/assets/images/atlascloud.png"
    result = AtlasCloudImage().execute(
        {
            "prompt": "Product hero image",
            "size": "2048*2048",
            "output_format": "png",
            "output_path": output_path,
        }
    )

    assert result.success, result.error
    assert captured["url"] == "https://api.atlascloud.ai/api/v1/model/generateImage"
    assert captured["headers"]["Authorization"] == "Bearer test-key"
    assert captured["json"] == {
        "model": "bytedance/seedream-v5.0-lite",
        "prompt": "Product hero image",
        "size": "2048*2048",
        "output_format": "png",
    }
    assert (tmp_path / output_path).read_bytes() == b"fake png"
    assert result.data["output_path"] == output_path
    jsonschema.validate(instance=result.data, schema=AtlasCloudImage().output_schema)


def test_atlascloud_video_image_to_video_requires_image_before_network(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ATLASCLOUD_API_KEY", "test-key")
    monkeypatch.setattr("requests.post", _fail_network)

    result = AtlasCloudVideo().execute(
        {"prompt": "Animate the product frame", "operation": "image_to_video"}
    )

    assert isinstance(result, ToolResult)
    assert not result.success
    assert "image_to_video requires" in (result.error or "")


def test_atlascloud_video_requires_project_output_path_before_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("ATLASCLOUD_API_KEY", raising=False)
    monkeypatch.setattr("requests.post", _fail_network)

    result = AtlasCloudVideo().execute(
        {"prompt": "A product hero shot", "output_path": "atlascloud.mp4"}
    )

    assert isinstance(result, ToolResult)
    assert not result.success
    assert "output_path" in (result.error or "")
    assert "projects/<project-name>/" in (result.error or "")


def test_atlascloud_video_success_payload_matches_live_schema(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ATLASCLOUD_API_KEY", "test-key")
    monkeypatch.setattr("time.sleep", lambda _seconds: None)
    monkeypatch.setattr(
        "tools.video.atlascloud_video.probe_output",
        lambda _path: {"file_size_bytes": 8},
    )
    captured: dict[str, object] = {}

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured["headers"] = kwargs["headers"]
        captured["json"] = kwargs["json"]
        return _FakeResponse({"data": {"id": "prediction-2", "status": "starting"}})

    def fake_get(url, **_kwargs):
        if url.endswith("/model/prediction/prediction-2"):
            return _FakeResponse(
                {
                    "data": {
                        "status": "completed",
                        "outputs": [{"url": "https://cdn.example.test/atlascloud.mp4"}],
                    }
                }
            )
        if url == "https://cdn.example.test/atlascloud.mp4":
            return _FakeResponse(content=b"fake mp4")
        raise AssertionError(f"unexpected GET {url}")

    monkeypatch.setattr("requests.post", fake_post)
    monkeypatch.setattr("requests.get", fake_get)

    output_path = "projects/demo/assets/video/atlascloud.mp4"
    result = AtlasCloudVideo().execute(
        {
            "prompt": "A product hero shot",
            "duration": 5,
            "resolution": "720p",
            "aspect_ratio": "16:9",
            "generate_audio": True,
            "seed": 123,
            "output_path": output_path,
        }
    )

    assert result.success, result.error
    assert captured["url"] == "https://api.atlascloud.ai/api/v1/model/generateVideo"
    assert captured["headers"]["Authorization"] == "Bearer test-key"
    assert captured["json"] == {
        "model": "bytedance/seedance-2.0-fast/text-to-video",
        "prompt": "A product hero shot",
        "duration": 5,
        "resolution": "720p",
        "ratio": "16:9",
        "bitrate_mode": "standard",
        "generate_audio": True,
        "watermark": False,
        "seed": 123,
    }
    assert (tmp_path / output_path).read_bytes() == b"fake mp4"
    assert result.data["output_path"] == output_path
    assert result.data["format"] == "mp4"
    jsonschema.validate(instance=result.data, schema=AtlasCloudVideo().output_schema)


def test_atlascloud_video_image_to_video_uses_atlas_image_field(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ATLASCLOUD_API_KEY", "test-key")
    monkeypatch.setattr("time.sleep", lambda _seconds: None)
    monkeypatch.setattr(
        "tools.video.atlascloud_video.probe_output",
        lambda _path: {"file_size_bytes": 8},
    )
    captured: dict[str, object] = {}

    def fake_post(_url, **kwargs):
        captured["json"] = kwargs["json"]
        return _FakeResponse({"data": {"id": "prediction-3", "status": "starting"}})

    def fake_get(url, **_kwargs):
        if url.endswith("/model/prediction/prediction-3"):
            return _FakeResponse(
                {
                    "data": {
                        "status": "completed",
                        "output": "https://cdn.example.test/atlascloud-i2v.mp4",
                    }
                }
            )
        if url == "https://cdn.example.test/atlascloud-i2v.mp4":
            return _FakeResponse(content=b"fake mp4")
        raise AssertionError(f"unexpected GET {url}")

    monkeypatch.setattr("requests.post", fake_post)
    monkeypatch.setattr("requests.get", fake_get)

    result = AtlasCloudVideo().execute(
        {
            "prompt": "Animate the product frame",
            "operation": "image_to_video",
            "image_url": "https://example.test/frame.png",
            "output_path": "projects/demo/assets/video/atlascloud-i2v.mp4",
        }
    )

    assert result.success, result.error
    assert captured["json"]["model"] == "bytedance/seedance-2.0-fast/image-to-video"
    assert captured["json"]["image"] == "https://example.test/frame.png"
    assert "image_url" not in captured["json"]


def test_atlascloud_providers_are_discovered_by_registry(monkeypatch):
    monkeypatch.setenv("ATLASCLOUD_API_KEY", "test-key")
    from tools.tool_registry import registry

    registry.clear()
    registry.discover()

    assert registry.get("atlascloud_image").get_status().value == "available"
    assert registry.get("atlascloud_video").get_status().value == "available"
