from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest

from lib.corpus import Corpus
from tools.video.corpus_builder import CorpusBuilder, _save_as_jpeg
from tools.video.stock_sources import safe_clip_file_name
from tools.video.stock_sources.base import Candidate


class _NoCache:
    def try_link(self, clip_id: str, out_path: Path) -> bool:
        return False

    def ingest(self, *args, **kwargs) -> bool:
        return True


class _PartialFailureSource:
    name = "partial"

    def download(self, candidate: Candidate, out_path: Path) -> Path:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(b"x" * 2048)
        raise OSError("interrupted download")


def test_corpus_builder_removes_partial_file_when_download_fails(monkeypatch, tmp_path):
    monkeypatch.setitem(sys.modules, "cv2", types.SimpleNamespace())
    corpus = Corpus(tmp_path / "corpus")
    candidate = Candidate(
        source="partial",
        source_id="clip_1",
        source_url="https://example.test/landing",
        download_url="https://example.test/clip.mp4",
        kind="video",
    )

    with pytest.raises(OSError, match="interrupted download"):
        CorpusBuilder()._process_candidate(
            cand=candidate,
            src=_PartialFailureSource(),
            corp=corpus,
            query="test",
            thumbs_per_video=1,
            cache=_NoCache(),
            run_cache_stats={"hits": 0, "misses": 0, "bytes_saved": 0},
        )

    final_path = corpus.clips_dir / safe_clip_file_name(candidate.clip_id, ".mp4")
    assert not final_path.exists()


def test_save_as_jpeg_reports_failed_cv2_write(monkeypatch, tmp_path):
    fake_cv2 = types.SimpleNamespace(
        IMWRITE_JPEG_QUALITY=1,
        imread=lambda path: object(),
        imwrite=lambda path, image, params: False,
    )
    monkeypatch.setitem(sys.modules, "cv2", fake_cv2)

    assert not _save_as_jpeg(tmp_path / "input.png", tmp_path / "thumb.jpg")


def test_corpus_builder_idempotency_key_includes_population_inputs():
    tool = CorpusBuilder()
    base = {
        "corpus_dir": "projects/demo/corpus",
        "queries": [{"query": "city skyline", "kind": "video", "per_source": 5}],
        "sources": ["pexels"],
        "filters": {"orientation": "landscape"},
        "max_new_clips": 10,
        "skip_existing": True,
        "thumbs_per_video": 5,
    }
    variants = [
        {"queries": [{"query": "forest trail", "kind": "video", "per_source": 5}]},
        {"sources": ["archive_org"]},
        {"filters": {"orientation": "portrait"}},
        {"max_new_clips": 20},
        {"skip_existing": False},
        {"thumbs_per_video": 8},
    ]

    base_key = tool.idempotency_key(base)
    for variant in variants:
        assert tool.idempotency_key({**base, **variant}) != base_key
