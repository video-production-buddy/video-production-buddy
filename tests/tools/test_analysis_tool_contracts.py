"""Analysis tool contract regressions."""

from __future__ import annotations

import sys
from types import SimpleNamespace
from typing import Any

import pytest

from tools.analysis.audio_energy import AudioEnergy
from tools.analysis.face_tracker import FaceTracker
from tools.analysis.frame_sampler import FrameSampler
from tools.analysis.scene_detect import SceneDetect
from tools.analysis.transcriber import Transcriber
from tools.analysis.transcript_fetcher import TranscriptFetcher
from tools.analysis.video_analyzer import VideoAnalyzer
from tools.analysis.video_downloader import VideoDownloader
from tools.analysis.video_understand import VideoUnderstand
from tools.analysis.visual_qa import VisualQA
from tools.base_tool import ToolStatus


@pytest.mark.parametrize(
    ("tool", "base", "variant"),
    [
        (AudioEnergy(), {"input_path": "music.wav"}, {"energy_threshold_lufs": -30}),
        (AudioEnergy(), {"input_path": "music.wav"}, {"video_duration_seconds": 30}),
        (
            FrameSampler(),
            {"input_path": "clip.mp4", "strategy": "timestamps"},
            {"timestamps": [1.0, 2.0]},
        ),
        (
            FrameSampler(),
            {"input_path": "clip.mp4", "strategy": "scene_guided"},
            {"scene_boundaries": [{"start_seconds": 0, "end_seconds": 4}]},
        ),
        (
            FrameSampler(),
            {"input_path": "clip.mp4", "strategy": "scene_guided"},
            {"max_frames": 3},
        ),
        (
            FrameSampler(),
            {"input_path": "clip.mp4", "strategy": "count", "count": 5},
            {"format": "png"},
        ),
        (
            FrameSampler(),
            {"input_path": "clip.mp4", "strategy": "count", "count": 5},
            {"quality": 10},
        ),
        (
            FrameSampler(),
            {"input_path": "clip.mp4", "strategy": "count", "count": 5},
            {"output_dir": "frames-a"},
        ),
        (
            FaceTracker(),
            {"input_path": "clip.mp4", "sample_fps": 5},
            {"output_path": "faces-a.json"},
        ),
        (
            SceneDetect(),
            {"input_path": "clip.mp4", "method": "content", "threshold": 0.3},
            {"min_scene_length_seconds": 3},
        ),
        (
            SceneDetect(),
            {"input_path": "clip.mp4", "method": "content", "threshold": 0.3},
            {"output_path": "scenes-a.json"},
        ),
        (
            Transcriber(),
            {"input_path": "voice.wav", "model_size": "base"},
            {"diarize": True},
        ),
        (
            Transcriber(),
            {"input_path": "voice.wav", "model_size": "base"},
            {"output_dir": "transcripts-a"},
        ),
        (
            TranscriptFetcher(),
            {"url_or_video_id": "abcdefghijk", "languages": ["en"]},
            {"include_auto_generated": False},
        ),
        (
            VideoAnalyzer(),
            {"source": "clip.mp4", "analysis_depth": "standard"},
            {"max_keyframes": 5},
        ),
        (
            VideoAnalyzer(),
            {"source": "clip.mp4", "analysis_depth": "standard"},
            {"output_dir": "analysis-a"},
        ),
        (
            VideoDownloader(),
            {
                "url": "https://example.com/video",
                "format": "video",
                "max_resolution": "720p",
            },
            {"max_duration_seconds": 10},
        ),
        (
            VideoDownloader(),
            {
                "url": "https://example.com/video",
                "format": "video",
                "max_resolution": "720p",
            },
            {"output_dir": "downloads-a"},
        ),
        (
            VideoUnderstand(),
            {"input_path": "clip.mp4", "mode": "quality", "model": "clip"},
            {"frame_indices": [1, 5]},
        ),
        (
            VideoUnderstand(),
            {"input_path": "clip.mp4", "mode": "quality", "model": "clip"},
            {"max_frames": 1},
        ),
        (
            VisualQA(),
            {"operation": "probe", "input_path": "render.mp4"},
            {"expected": {"width": 1920}},
        ),
        (
            VisualQA(),
            {"operation": "review", "input_path": "render.mp4", "timestamps": [1.0]},
            {"output_dir": "qa-a"},
        ),
    ],
)
def test_analysis_idempotency_keys_include_output_shaping_inputs(
    tool: Any,
    base: dict[str, object],
    variant: dict[str, object],
) -> None:
    assert tool.idempotency_key(base) != tool.idempotency_key({**base, **variant})


@pytest.mark.parametrize(
    "tool",
    [AudioEnergy(), FrameSampler(), SceneDetect(), VideoAnalyzer()],
)
def test_ffprobe_callers_declare_ffprobe_dependency(tool: Any) -> None:
    assert any(str(dep).endswith(":ffprobe") for dep in tool.dependencies)


def test_frame_sampler_rejects_unknown_format_before_extraction(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    input_path = tmp_path / "clip.mp4"
    input_path.write_bytes(b"video")

    monkeypatch.setattr(
        FrameSampler,
        "_extract_count",
        lambda self, *args, **kwargs: [{"path": "frame.gif", "timestamp_seconds": 0}],
    )

    result = FrameSampler().execute(
        {
            "input_path": str(input_path),
            "strategy": "count",
            "count": 1,
            "format": "gif",
        }
    )

    assert result.success is False
    assert "Unknown format" in (result.error or "")


def test_scene_detect_rejects_unknown_method_before_detector(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    input_path = tmp_path / "clip.mp4"
    input_path.write_bytes(b"video")
    monkeypatch.setattr(SceneDetect, "_has_pyscenedetect", lambda self: False)
    monkeypatch.setattr(SceneDetect, "_detect_ffmpeg", lambda self, inputs: [])

    result = SceneDetect().execute(
        {
            "input_path": str(input_path),
            "method": "not-a-real-method",
        }
    )

    assert result.success is False
    assert "Unknown method" in (result.error or "")


def test_transcriber_rejects_unknown_model_size_before_loading_model(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    input_path = tmp_path / "voice.wav"
    input_path.write_bytes(b"audio")

    class FakeWhisperModel:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        def transcribe(self, *args: Any, **kwargs: Any):
            return [], SimpleNamespace(language="en", duration=0.0)

    monkeypatch.setitem(
        sys.modules,
        "faster_whisper",
        SimpleNamespace(WhisperModel=FakeWhisperModel),
    )
    monkeypatch.setitem(
        sys.modules,
        "torch",
        SimpleNamespace(cuda=SimpleNamespace(is_available=lambda: False)),
    )

    result = Transcriber().execute(
        {
            "input_path": str(input_path),
            "model_size": "not-a-real-model",
            "output_dir": str(tmp_path),
        }
    )

    assert result.success is False
    assert "Unknown model_size" in (result.error or "")


def test_video_analyzer_rejects_unknown_analysis_depth_before_subtools(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(VideoAnalyzer, "_save_brief", lambda self, brief, output_dir: None)

    result = VideoAnalyzer().execute(
        {
            "source": "https://example.com/video",
            "analysis_depth": "not-a-real-depth",
            "output_dir": str(tmp_path / "analysis"),
        }
    )

    assert result.success is False
    assert "Unknown analysis_depth" in (result.error or "")


def test_video_downloader_rejects_unknown_format_before_download(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(VideoDownloader, "_extract_metadata", lambda self, url: {"duration": 0})

    result = VideoDownloader().execute(
        {
            "url": "https://example.com/video",
            "output_dir": str(tmp_path),
            "format": "not-a-real-format",
        }
    )

    assert result.success is False
    assert "Unknown format" in (result.error or "")


def test_video_downloader_rejects_unknown_max_resolution_before_download(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(VideoDownloader, "_extract_metadata", lambda self, url: {"duration": 0})
    monkeypatch.setattr(
        VideoDownloader,
        "_download_video",
        lambda self, url, output_dir, max_res: (str(output_dir / "reference_video.mp4"), None),
    )

    result = VideoDownloader().execute(
        {
            "url": "https://example.com/video",
            "output_dir": str(tmp_path),
            "format": "video",
            "max_resolution": "1440p",
        }
    )

    assert result.success is False
    assert "Unknown max_resolution" in (result.error or "")


def test_audio_energy_status_requires_ffprobe(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_which(command: str) -> str | None:
        if command == "ffmpeg":
            return f"/usr/bin/{command}"
        return None

    monkeypatch.setattr("tools.analysis.audio_energy.shutil.which", fake_which)

    assert AudioEnergy().get_status() == ToolStatus.UNAVAILABLE


def test_transcript_fetcher_can_exclude_auto_generated_captions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeSnippet:
        text = "manual caption"
        start = 1.2
        duration = 3.4

    class FakeManualTranscript:
        is_generated = False
        language_code = "en"

        def fetch(self):
            return SimpleNamespace(
                snippets=[FakeSnippet()],
                is_generated=False,
                language="en",
            )

    class FakeTranscriptList:
        def find_manually_created_transcript(self, languages):
            assert languages == ["en"]
            return FakeManualTranscript()

    class FakeYouTubeTranscriptApi:
        def list(self, video_id):
            assert video_id == "abcdefghijk"
            return FakeTranscriptList()

        def fetch(self, video_id, languages):
            return SimpleNamespace(
                snippets=[
                    SimpleNamespace(
                        text="auto caption",
                        start=0.0,
                        duration=1.0,
                    )
                ],
                is_generated=True,
                language="en",
            )

    monkeypatch.setitem(
        sys.modules,
        "youtube_transcript_api",
        SimpleNamespace(YouTubeTranscriptApi=FakeYouTubeTranscriptApi),
    )

    result = TranscriptFetcher().execute(
        {
            "url_or_video_id": "abcdefghijk",
            "languages": ["en"],
            "include_auto_generated": False,
        }
    )

    assert result.success, result.error
    assert result.data["full_text"] == "manual caption"
    assert result.data["is_auto_generated"] is False
