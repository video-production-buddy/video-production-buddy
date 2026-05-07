"""Reference-video analyzer regression tests."""

from __future__ import annotations

from pathlib import Path

from tools.base_tool import ToolResult
from tools.analysis.video_analyzer import VideoAnalyzer


def test_local_video_transcript_only_uses_video_path_for_whisper_fallback(
    tmp_path: Path,
    monkeypatch,
) -> None:
    video_path = tmp_path / "reference.mp4"
    video_path.write_bytes(b"fixture")
    output_dir = tmp_path / "analysis"
    transcribed_inputs = []

    class StubTranscriber:
        def execute(self, inputs):
            transcribed_inputs.append(inputs)
            return ToolResult(
                success=True,
                data={
                    "segments": [{"start": 0, "end": 1, "text": "Local speech"}],
                    "language": "en",
                    "duration_seconds": 1,
                },
            )

    monkeypatch.setattr(
        "tools.analysis.transcriber.Transcriber",
        StubTranscriber,
    )

    analyzer = VideoAnalyzer()
    monkeypatch.setattr(analyzer, "_get_duration", lambda _path: 1.0)

    result = analyzer.execute(
        {
            "source": str(video_path),
            "analysis_depth": "transcript_only",
            "output_dir": str(output_dir),
        }
    )

    assert result.success
    assert transcribed_inputs
    assert transcribed_inputs[0]["input_path"] == str(video_path)
    assert result.data["narration_transcript"]["full_text"] == "Local speech"
