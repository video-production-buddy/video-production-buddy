from __future__ import annotations

from pathlib import Path

from tools.video.direct_clip_search import DirectClipSearch
from tools.video.stock_sources.base import Candidate


class _UnsafeIdSource:
    name = "unsafe"

    def is_available(self) -> bool:
        return True

    def search(self, query: str, filters) -> list[Candidate]:
        return [
            Candidate(
                source=self.name,
                source_id="../../../escape",
                source_url="https://example.test/landing",
                download_url="https://example.test/clip.mp4",
                kind="video",
            )
        ]

    def download(self, candidate: Candidate, out_path: Path) -> Path:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(b"x" * 2048)
        return out_path


class _PartialFailureSource:
    name = "partial"

    def is_available(self) -> bool:
        return True

    def search(self, query: str, filters) -> list[Candidate]:
        return [
            Candidate(
                source=self.name,
                source_id="clip_1",
                source_url="https://example.test/landing",
                download_url="https://example.test/clip.mp4",
                kind="video",
            )
        ]

    def download(self, candidate: Candidate, out_path: Path) -> Path:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(b"x" * 2048)
        raise OSError("interrupted download")


class _ImageSource:
    name = "image"

    def is_available(self) -> bool:
        return True

    def search(self, query: str, filters) -> list[Candidate]:
        return [
            Candidate(
                source=self.name,
                source_id="still_1",
                source_url="https://example.test/still",
                download_url="https://example.test/still.jpg",
                kind="image",
            )
        ]

    def download(self, candidate: Candidate, out_path: Path) -> Path:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(b"image-bytes" * 256)
        return out_path


class _ExistingVideoSource:
    name = "existing"

    def is_available(self) -> bool:
        return True

    def search(self, query: str, filters) -> list[Candidate]:
        return [
            Candidate(
                source=self.name,
                source_id="clip_1",
                source_url="https://example.test/existing",
                download_url="https://example.test/existing.mp4",
                kind="video",
            )
        ]

    def download(self, candidate: Candidate, out_path: Path) -> Path:
        raise AssertionError("existing clip should not be downloaded again")


def _install_source(monkeypatch, source) -> None:
    import tools.video.stock_sources as stock_sources

    monkeypatch.setattr(stock_sources, "all_sources", lambda: [source])
    monkeypatch.setattr(stock_sources, "available_sources", lambda: [source])
    monkeypatch.setattr(stock_sources, "get_source", lambda name: source)
    monkeypatch.setattr(
        stock_sources,
        "source_summary",
        lambda: {
            "configured": 1,
            "total": 1,
            "available_source_names": [source.name],
            "unavailable_source_names": [],
        },
    )


def test_direct_clip_search_keeps_download_paths_inside_clips_dir(monkeypatch, tmp_path):
    source = _UnsafeIdSource()
    _install_source(monkeypatch, source)

    output_dir = tmp_path / "raw"
    result = DirectClipSearch().execute(
        {
            "output_dir": str(output_dir),
            "queries": [{"query": "test"}],
            "sources": [source.name],
            "extract_thumbnails": False,
            "clips_per_query": 1,
        }
    )

    assert result.success
    clip_path = Path(result.data["clips"][0]["path"]).resolve()
    clip_path.relative_to((output_dir / "clips").resolve())
    assert clip_path.exists()
    assert not (tmp_path / "escape.mp4").exists()


def test_direct_clip_search_removes_partial_file_when_download_fails(
    monkeypatch, tmp_path
):
    source = _PartialFailureSource()
    _install_source(monkeypatch, source)

    output_dir = tmp_path / "raw"
    result = DirectClipSearch().execute(
        {
            "output_dir": str(output_dir),
            "queries": [{"query": "test"}],
            "sources": [source.name],
            "extract_thumbnails": False,
            "clips_per_query": 1,
        }
    )

    assert result.success
    assert result.data["clips_downloaded"] == 0
    assert result.data["errors"][0]["phase"] == "download"
    assert not (output_dir / "clips" / "partial_clip_1.mp4").exists()


def test_direct_clip_search_extracts_missing_thumbnail_for_reused_video(
    monkeypatch, tmp_path
):
    source = _ExistingVideoSource()
    _install_source(monkeypatch, source)

    output_dir = tmp_path / "raw"
    clip_path = output_dir / "clips" / "existing_clip_1.mp4"
    clip_path.parent.mkdir(parents=True)
    clip_path.write_bytes(b"x" * 2048)

    def fake_extract(video_path: Path, thumb_path: Path) -> None:
        assert video_path == clip_path
        thumb_path.parent.mkdir(parents=True, exist_ok=True)
        thumb_path.write_bytes(b"thumbnail")

    monkeypatch.setattr(
        "tools.video.direct_clip_search._extract_mid_thumbnail",
        fake_extract,
    )

    result = DirectClipSearch().execute(
        {
            "output_dir": str(output_dir),
            "queries": [{"query": "test"}],
            "sources": [source.name],
            "extract_thumbnails": True,
            "clips_per_query": 1,
            "skip_existing": True,
        }
    )

    assert result.success
    clip = result.data["clips"][0]
    assert clip["skipped_existing"] is True
    assert clip["thumbnail"]
    thumbnail_path = Path(clip["thumbnail"])
    assert thumbnail_path.exists()
    assert thumbnail_path.read_bytes() == b"thumbnail"


def test_direct_clip_search_materializes_image_thumbnails(monkeypatch, tmp_path):
    source = _ImageSource()
    _install_source(monkeypatch, source)

    output_dir = tmp_path / "raw"
    result = DirectClipSearch().execute(
        {
            "output_dir": str(output_dir),
            "queries": [{"query": "test", "kind": "image"}],
            "sources": [source.name],
            "extract_thumbnails": True,
            "clips_per_query": 1,
        }
    )

    assert result.success
    clip = result.data["clips"][0]
    thumbnail_path = Path(clip["thumbnail"]).resolve()
    thumbnail_path.relative_to((output_dir / "thumbnails").resolve())
    assert thumbnail_path.exists()


def test_direct_clip_search_idempotency_key_includes_acquisition_inputs():
    tool = DirectClipSearch()
    base = {
        "output_dir": "projects/demo/assets/video/raw",
        "queries": [{"query": "city skyline", "kind": "video"}],
        "sources": ["pexels"],
        "clips_per_query": 2,
        "filters": {"orientation": "landscape"},
        "extract_thumbnails": True,
        "skip_existing": True,
    }
    variants = [
        {"queries": [{"query": "forest trail", "kind": "video"}]},
        {"sources": ["archive_org"]},
        {"clips_per_query": 4},
        {"filters": {"orientation": "portrait"}},
        {"extract_thumbnails": False},
        {"skip_existing": False},
    ]

    base_key = tool.idempotency_key(base)
    for variant in variants:
        assert tool.idempotency_key({**base, **variant}) != base_key
