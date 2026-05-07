import hashlib
import re
from pathlib import Path

from tools.video.stock_sources import (
    SearchFilters,
    absolute_url,
    all_sources,
    safe_clip_file_name,
)
from tools.video.stock_sources.coverr import CoverrSource
from tools.video.stock_sources.loc import LibraryOfCongressSource
from tools.video.stock_sources.nara import NARASource
from tools.video.stock_sources.nasa import _sanitize_source_id
from tools.video.stock_sources.unsplash import _build_download_url, _orientation_for_unsplash
from tools.video.stock_sources.videvo import VidevoSource
from tools.video.stock_sources.wikimedia import (
    _build_search_queries,
    _kind_from_mime,
    _meta_value,
)


def test_stock_source_autodiscovery_includes_new_sources():
    names = {source.name for source in all_sources()}
    assert "wikimedia" in names
    assert "unsplash" in names


def test_stock_source_ids_do_not_use_process_salted_hash():
    source_dir = Path(__file__).resolve().parents[2] / "tools" / "video" / "stock_sources"
    offenders = []
    for path in source_dir.glob("*.py"):
        if path.name == "__init__.py":
            continue
        if re.search(r"\bhash\s*\(", path.read_text(encoding="utf-8")):
            offenders.append(path.name)

    assert offenders == []


def test_stock_source_adapters_do_not_stringify_missing_provider_ids():
    source_dir = Path(__file__).resolve().parents[2] / "tools" / "video" / "stock_sources"
    pattern = re.compile(r"source_id=str\([^)]*\.get\([\"']id[\"']")
    offenders = []
    for path in source_dir.glob("*.py"):
        if path.name == "__init__.py":
            continue
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if pattern.search(line):
                offenders.append(f"{path.name}:{line_number}:{line.strip()}")

    assert offenders == []


def test_stock_source_adapters_do_not_concatenate_relative_urls():
    source_dir = Path(__file__).resolve().parents[2] / "tools" / "video" / "stock_sources"
    pattern = re.compile(
        r'f"[^"]*\{(?:href|download_url|thumb|url|image_url)\}[^"]*"'
    )
    offenders = []
    for path in source_dir.glob("*.py"):
        if path.name == "__init__.py":
            continue
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if pattern.search(line):
                offenders.append(f"{path.name}:{line_number}:{line.strip()}")

    assert offenders == []


def test_absolute_url_resolves_relative_paths_without_leading_slash():
    assert absolute_url("https://example.test", "media/clip.mp4") == (
        "https://example.test/media/clip.mp4"
    )
    assert absolute_url("https://example.test", "/media/clip.mp4") == (
        "https://example.test/media/clip.mp4"
    )
    assert absolute_url("https://example.test/root", "media/clip.mp4") == (
        "https://example.test/root/media/clip.mp4"
    )


def test_safe_clip_file_name_caps_safe_but_overlong_ids():
    clip_id = "pexels_" + ("a" * 300)
    file_name = safe_clip_file_name(clip_id, ".mp4")

    assert len(file_name) <= 120
    assert file_name.endswith(".mp4")
    assert f"-{hashlib.sha256(clip_id.encode('utf-8')).hexdigest()[:12]}" in file_name


def test_safe_clip_file_name_caps_overlong_directory_names_without_extension():
    clip_id = "archive_org_" + ("b" * 300)
    directory_name = safe_clip_file_name(clip_id, "")

    assert len(directory_name) <= 120
    assert directory_name.endswith(hashlib.sha256(clip_id.encode("utf-8")).hexdigest()[:12])


def test_nasa_sanitized_source_ids_keep_long_ids_unique():
    shared_prefix = "Mission " + ("A" * 140)

    first = _sanitize_source_id(f"{shared_prefix} alpha")
    second = _sanitize_source_id(f"{shared_prefix} beta")

    assert first != second
    assert len(first) <= 120
    assert len(second) <= 120


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


def test_coverr_search_falls_back_to_stable_ids_when_api_ids_are_missing(monkeypatch):
    import requests

    monkeypatch.setattr(
        requests,
        "get",
        lambda *args, **kwargs: _FakeResponse(
            {
                "hits": [
                    {"urls": {"mp4_720": "https://cdn.test/a.mp4"}},
                    {"urls": {"mp4_720": "https://cdn.test/b.mp4"}},
                ]
            }
        ),
    )

    candidates = CoverrSource().search("city", SearchFilters(kind="video"))

    source_ids = [candidate.source_id for candidate in candidates]
    assert len(source_ids) == 2
    assert len(set(source_ids)) == 2
    assert all(source_id for source_id in source_ids)


def test_videvo_search_falls_back_to_stable_ids_when_api_ids_are_missing(monkeypatch):
    import requests

    monkeypatch.setenv("VIDEVO_API_KEY", "test-key")
    monkeypatch.setattr(
        requests,
        "get",
        lambda *args, **kwargs: _FakeResponse(
            {
                "data": [
                    {"download_url": "https://cdn.test/a.mp4"},
                    {"download_url": "https://cdn.test/b.mp4"},
                ]
            }
        ),
    )

    candidates = VidevoSource().search("city", SearchFilters(kind="video"))

    source_ids = [candidate.source_id for candidate in candidates]
    assert len(source_ids) == 2
    assert len(set(source_ids)) == 2
    assert all(source_id for source_id in source_ids)


def test_nara_extract_candidates_handles_null_object_ids_without_collisions():
    item = {
        "naId": "123",
        "objects": [
            {"objectId": None, "url": "https://catalog.test/a.mp4", "mimeType": "video/mp4"},
            {"objectId": None, "url": "https://catalog.test/b.mp4", "mimeType": "video/mp4"},
        ],
    }

    candidates = NARASource()._extract_candidates(
        item, kind="video", filters=SearchFilters(kind="video")
    )

    source_ids = [candidate.source_id for candidate in candidates]
    assert source_ids == ["123_0", "123_1"]


def test_nara_extract_candidates_detects_media_urls_with_query_strings():
    item = {
        "naId": "123",
        "objects": [
            {"url": "https://catalog.test/a.mp4?download=1", "mimeType": ""},
        ],
    }

    candidates = NARASource()._extract_candidates(
        item, kind="video", filters=SearchFilters(kind="video")
    )

    assert [candidate.download_url for candidate in candidates] == [
        "https://catalog.test/a.mp4?download=1"
    ]


def test_loc_extract_candidates_detects_media_urls_with_query_strings():
    item = {
        "id": "/item/test/",
        "resources": [
            {
                "files": [
                    [
                        {
                            "url": "/media/test.mp4?download=1",
                            "mimetype": "",
                        }
                    ]
                ]
            }
        ],
    }

    candidates = LibraryOfCongressSource()._extract_candidates(
        item, kind="video", filters=SearchFilters(kind="video")
    )

    assert [candidate.download_url for candidate in candidates] == [
        "https://www.loc.gov/media/test.mp4?download=1"
    ]


def test_wikimedia_search_query_respects_kind():
    # The cascade's first ("full") query should always carry the
    # filetype filter for video/image kinds. "any" drops the prefix.
    video_cascade = _build_search_queries("rain city", "video")
    assert video_cascade[0][0] == "full"
    assert video_cascade[0][1].startswith("filetype:video")

    image_cascade = _build_search_queries("rain city", "image")
    assert image_cascade[0][0] == "full"
    assert image_cascade[0][1].startswith("filetype:image")

    any_cascade = _build_search_queries("rain city", "any")
    assert any_cascade[0][0] == "full"
    assert any_cascade[0][1] == "rain city"


def test_wikimedia_cascade_falls_back_on_multi_word():
    # Multi-word query should produce a 3-stage cascade: full, top2_or,
    # single_best. Tokens are picked by length, so "television" beats
    # "family" and "watching".
    cascade = _build_search_queries(
        "1950s family watching television", "video"
    )
    labels = [label for label, _ in cascade]
    assert labels == ["full", "top2_or", "single_best"]
    assert cascade[1][1] == "filetype:video television watching"
    assert cascade[2][1] == "filetype:video television"


def test_wikimedia_cascade_strips_source_hints_and_years():
    # "prelinger" is a source hint (redundant on Commons) and "1955" is
    # a year — both are excluded from distinctive-token picks.
    cascade = _build_search_queries(
        "Prelinger 1955 housewife kitchen", "video"
    )
    # Full query keeps the source hint + year (first attempt is strict).
    assert cascade[0][1] == "filetype:video Prelinger 1955 housewife kitchen"
    # Distinctive picks do NOT include prelinger or 1955.
    joined = " ".join(sq for _, sq in cascade[1:])
    assert "housewife" in joined
    assert "kitchen" in joined
    assert "prelinger" not in joined.lower()
    assert "1955" not in joined


def test_wikimedia_kind_and_metadata_helpers():
    assert _kind_from_mime("video/webm", "File:foo.webm") == "video"
    assert _kind_from_mime("image/jpeg", "File:foo.jpg") == "image"
    assert _meta_value({"Artist": {"value": "<a href='/wiki/User:Test'>Test User</a>"}}, "Artist") == "Test User"


def test_unsplash_helpers_preserve_query_params():
    assert _orientation_for_unsplash("square") == "squarish"
    url = _build_download_url("https://images.unsplash.com/photo-123?ixid=abc", 1920)
    assert "ixid=abc" in url
    assert "w=1920" in url
    assert "fm=jpg" in url
