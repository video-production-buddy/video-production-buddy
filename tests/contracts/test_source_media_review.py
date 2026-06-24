"""Source-media review contract regressions."""

from __future__ import annotations

import subprocess
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

import pytest

from lib.source_media_review import has_user_media, review_source_media


class _EmptyRegistry:
    def get(self, name: str):  # noqa: ANN001, ARG002
        return None


class _AudioProbeOnlyRegistry:
    def get(self, name: str):  # noqa: ANN001
        if name == "audio_probe":
            return self
        return None

    def execute(self, inputs: dict):  # noqa: ANN001, ARG002
        return SimpleNamespace(
            success=True,
            data={
                "duration_seconds": 12.0,
                "audio": {
                    "codec": "aac",
                    "sample_rate": 48000,
                    "channels": 2,
                },
            },
        )


def test_review_source_media_refuses_unprobed_video(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A video file must not be marked reviewed when no probe evidence exists."""
    video_path = tmp_path / "broken.mp4"
    video_path.write_bytes(b"not a valid mp4")

    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 1, "", "bad input"),
    )

    with pytest.raises(RuntimeError, match="could not be reviewed"):
        review_source_media([video_path], {}, tool_registry=_EmptyRegistry())


def test_review_source_media_enriches_audio_probe_video_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AudioProbe output alone is not enough to summarize a video source."""
    video_path = tmp_path / "source.mp4"
    video_path.write_bytes(b"placeholder")

    def fake_run(*args, **kwargs):  # noqa: ANN001, ARG001
        return subprocess.CompletedProcess(
            args[0],
            0,
            (
                '{"format":{"duration":"12.0","size":"240000","bit_rate":"1600000"},'
                '"streams":['
                '{"codec_type":"video","width":1920,"height":1080,'
                '"r_frame_rate":"30000/1001","codec_name":"h264"},'
                '{"codec_type":"audio","codec_name":"aac","sample_rate":"48000","channels":2}'
                "]}"
            ),
            "",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)

    review = review_source_media(
        [video_path],
        {},
        tool_registry=_AudioProbeOnlyRegistry(),
    )

    file_review = review["files"][0]
    assert file_review["media_type"] == "video"
    assert file_review["technical_probe"]["resolution"] == "1920x1080"
    assert file_review["technical_probe"]["audio_codec"] == "aac"
    assert file_review["content_summary"] == "Video file: 12.0s at 1920x1080, with audio"


def test_review_source_media_treats_audio_only_mp4_as_audio(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An audio-only container must not unlock source-video planning."""
    media_path = tmp_path / "audio_only.mp4"
    media_path.write_bytes(b"placeholder")

    def fake_run(*args, **kwargs):  # noqa: ANN001, ARG001
        return subprocess.CompletedProcess(
            args[0],
            0,
            (
                '{"format":{"duration":"9.0","size":"90000","bit_rate":"128000"},'
                '"streams":['
                '{"codec_type":"audio","codec_name":"aac","sample_rate":"48000","channels":2}'
                "]}"
            ),
            "",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)

    review = review_source_media(
        [media_path],
        {},
        tool_registry=_EmptyRegistry(),
    )

    file_review = review["files"][0]
    assert file_review["media_type"] == "audio"
    assert file_review["technical_probe"]["audio_codec"] == "aac"
    assert file_review["content_summary"] == "Audio file: 9.0s, aac"
    assert "Source video available" not in " ".join(review["planning_implications"])


def test_review_source_media_records_svg_file_metadata(tmp_path: Path) -> None:
    """SVGs are valid reference images even when Pillow cannot raster-probe them."""
    svg_path = tmp_path / "brand_logo.svg"
    svg_path.write_text("<svg xmlns='http://www.w3.org/2000/svg'></svg>", encoding="utf-8")

    review = review_source_media([svg_path], {}, tool_registry=_EmptyRegistry())

    file_review = review["files"][0]
    assert file_review["reviewed"] is True
    assert file_review["technical_probe"]["file_size_bytes"] == svg_path.stat().st_size
    assert file_review["content_summary"].startswith("Image file:")
    assert file_review["quality_risks"] == []
    assert not any("Could not probe image" in item for item in review["planning_implications"])


def test_review_source_media_refuses_corrupt_raster_image(tmp_path: Path) -> None:
    """Raster product/reference images need a real image probe, not file-size fallback."""
    image_path = tmp_path / "product_hero.png"
    image_path.write_bytes(b"not a valid png")

    with pytest.raises(RuntimeError, match="product_hero.png"):
        review_source_media([image_path], {}, tool_registry=_EmptyRegistry())


def test_review_source_media_refuses_truncated_raster_image(tmp_path: Path) -> None:
    """Header-readable but truncated rasters must not count as reviewed media."""
    image_module = pytest.importorskip("PIL.Image")
    image_path = tmp_path / "product_hero.png"
    image = image_module.new("RGB", (16, 16), "red")
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    image_path.write_bytes(buffer.getvalue()[:50])

    with pytest.raises(RuntimeError, match="product_hero.png"):
        review_source_media([image_path], {}, tool_registry=_EmptyRegistry())


def test_review_source_media_refuses_partial_review_when_one_file_fails(
    tmp_path: Path,
) -> None:
    """A valid source file must not hide an unreviewed companion file."""
    svg_path = tmp_path / "brand_logo.svg"
    svg_path.write_text("<svg xmlns='http://www.w3.org/2000/svg'></svg>", encoding="utf-8")
    image_path = tmp_path / "product_hero.png"
    image_path.write_bytes(b"not a valid png")

    with pytest.raises(RuntimeError, match="product_hero.png"):
        review_source_media([svg_path, image_path], {}, tool_registry=_EmptyRegistry())


def test_review_source_media_refuses_partial_review_when_file_is_missing(
    tmp_path: Path,
) -> None:
    """A missing user-supplied media path must not disappear from the review."""
    svg_path = tmp_path / "brand_logo.svg"
    svg_path.write_text("<svg xmlns='http://www.w3.org/2000/svg'></svg>", encoding="utf-8")
    missing_path = tmp_path / "missing_clip.mp4"

    with pytest.raises(RuntimeError, match="missing_clip.mp4"):
        review_source_media([svg_path, missing_path], {}, tool_registry=_EmptyRegistry())


def test_has_user_media_detects_reference_assets(tmp_path: Path) -> None:
    """Project reference_assets are user-supplied media under the project contract."""
    reference_dir = tmp_path / "reference_assets"
    reference_dir.mkdir()
    (reference_dir / "product_hero.png").write_bytes(b"placeholder")

    assert has_user_media(tmp_path) is True
