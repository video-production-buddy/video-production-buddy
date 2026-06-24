"""Source media review helper.

Standardizes inspection of user-supplied media files so pipelines stop
reinventing partial checks. Uses existing analysis tools (audio_probe,
frame_sampler, scene_detect, transcriber) to produce a normalized
source_media_review artifact.

The contract: if user-supplied media exists, source_media_review is
REQUIRED before the first planning stage that depends on creative
assumptions. Never claim a file was reviewed unless a real probe ran.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Optional

from schemas.artifacts import validate_artifact

logger = logging.getLogger(__name__)


# Media type detection by extension
_VIDEO_EXTENSIONS = frozenset({".mp4", ".mov", ".webm", ".avi", ".mkv", ".m4v"})
_AUDIO_EXTENSIONS = frozenset({".mp3", ".wav", ".aac", ".flac", ".ogg", ".m4a", ".opus"})
_IMAGE_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff", ".svg"})
_VECTOR_IMAGE_EXTENSIONS = frozenset({".svg"})


def detect_media_type(path: Path) -> Optional[str]:
    """Classify a file as video, audio, or image by extension."""
    ext = path.suffix.lower()
    if ext in _VIDEO_EXTENSIONS:
        return "video"
    if ext in _AUDIO_EXTENSIONS:
        return "audio"
    if ext in _IMAGE_EXTENSIONS:
        return "image"
    return None


def _has_video_stream_metadata(probe: dict[str, Any]) -> bool:
    """Return True when probe data contains real video dimensions."""
    resolution = probe.get("resolution")
    if not isinstance(resolution, str) or "x" not in resolution:
        return False
    width, height = resolution.split("x", maxsplit=1)
    return width.isdigit() and height.isdigit()


def _safe_int(value: Any) -> int:
    if value in (None, ""):
        return 0
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _safe_float(value: Any) -> float:
    if value in (None, ""):
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _canonical_video_probe(
    fmt: dict[str, Any],
    video_stream: dict[str, Any],
    audio_stream: dict[str, Any] | None,
) -> dict[str, Any]:
    return {
        "duration_seconds": _safe_float(fmt.get("duration")),
        "resolution": (
            f"{video_stream.get('width', '?')}x{video_stream.get('height', '?')}"
        ),
        "fps": _parse_fps(str(video_stream.get("r_frame_rate", "0/1"))),
        "codec": video_stream.get("codec_name", "unknown"),
        "audio_codec": audio_stream.get("codec_name", "") if audio_stream else "",
        "sample_rate": _safe_int(audio_stream.get("sample_rate")) if audio_stream else 0,
        "channels": _safe_int(audio_stream.get("channels")) if audio_stream else 0,
        "file_size_bytes": _safe_int(fmt.get("size")),
        "bitrate_kbps": round(_safe_int(fmt.get("bit_rate")) / 1000, 1),
    }


def _canonical_audio_probe(
    fmt: dict[str, Any],
    audio_stream: dict[str, Any],
) -> dict[str, Any]:
    return {
        "duration_seconds": _safe_float(fmt.get("duration")),
        "audio_codec": audio_stream.get("codec_name", "unknown"),
        "sample_rate": _safe_int(audio_stream.get("sample_rate")),
        "channels": _safe_int(audio_stream.get("channels")),
        "file_size_bytes": _safe_int(fmt.get("size")),
        "bitrate_kbps": round(_safe_int(fmt.get("bit_rate")) / 1000, 1),
    }


def _probe_video(path: Path, tool_registry: Any) -> dict[str, Any]:
    """Probe a video file using audio_probe (ffprobe wrapper) and frame_sampler."""
    result: dict[str, Any] = {"technical_probe": {}, "representative_frames": [], "quality_risks": []}

    # Technical probe via audio_probe or ffprobe
    try:
        audio_probe = tool_registry.get("audio_probe")
        if audio_probe:
            probe_result = audio_probe.execute({"input_path": str(path)})
            if probe_result.success:
                result["technical_probe"] = probe_result.data
    except Exception as e:
        logger.warning("audio_probe failed for %s: %s", path, e)

    # audio_probe reports generic duration/audio fields. A video source still
    # needs stream-level video metadata for truthful planning summaries.
    needs_video_stream_probe = not _has_video_stream_metadata(result["technical_probe"])
    if needs_video_stream_probe:
        try:
            import subprocess
            cmd = [
                "ffprobe", "-v", "quiet", "-print_format", "json",
                "-show_format", "-show_streams", str(path),
            ]
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if proc.returncode == 0:
                probe_data = json.loads(proc.stdout)
                fmt = probe_data.get("format", {})
                streams = probe_data.get("streams", [])
                video_stream = next((s for s in streams if s.get("codec_type") == "video"), None)
                audio_stream = next((s for s in streams if s.get("codec_type") == "audio"), None)
                if video_stream:
                    result["technical_probe"] = _canonical_video_probe(
                        fmt,
                        video_stream,
                        audio_stream,
                    )
                elif audio_stream:
                    result["detected_media_type"] = "audio"
                    result["technical_probe"] = _canonical_audio_probe(fmt, audio_stream)
                    result["quality_risks"].append(
                        "File has a video extension but no video stream; treat it as audio-only source media"
                    )
                else:
                    result["quality_risks"].append(
                        "Container has no detectable video or audio streams"
                    )
        except Exception as e:
            logger.warning("ffprobe failed for %s: %s", path, e)
            result["quality_risks"].append(f"Could not probe file: {e}")

    # Sample frames
    try:
        frame_sampler = tool_registry.get("frame_sampler")
        if frame_sampler:
            duration = result["technical_probe"].get("duration_seconds", 0)
            timestamps = _sample_timestamps(duration, count=4)
            sample_result = frame_sampler.execute({
                "input_path": str(path),
                "timestamps": timestamps,
                "output_dir": str(path.parent / ".source_review_frames"),
            })
            if sample_result.success:
                result["representative_frames"] = sample_result.data.get("frame_paths", [])
    except Exception as e:
        logger.warning("frame_sampler failed for %s: %s", path, e)

    # Quality risk assessment
    probe = result["technical_probe"]
    if probe:
        res = probe.get("resolution", "")
        if res and "x" in res:
            try:
                w, h = res.split("x")
                if int(w) < 720 or int(h) < 480:
                    result["quality_risks"].append(f"Low resolution ({res}) — may appear pixelated in final output")
            except ValueError:
                pass
        if probe.get("channels", 0) == 1:
            result["quality_risks"].append("Mono audio — consider if stereo output is expected")
        if probe.get("duration_seconds", 0) < 3:
            result["quality_risks"].append("Very short clip (<3s) — limited usability")

    return result


def _probe_audio(path: Path, tool_registry: Any) -> dict[str, Any]:
    """Probe an audio file using audio_probe."""
    result: dict[str, Any] = {"technical_probe": {}, "quality_risks": []}

    try:
        audio_probe = tool_registry.get("audio_probe")
        if audio_probe:
            probe_result = audio_probe.execute({"input_path": str(path)})
            if probe_result.success:
                result["technical_probe"] = probe_result.data
    except Exception as e:
        logger.warning("audio_probe failed for %s: %s", path, e)

    # Fallback ffprobe
    if not result["technical_probe"]:
        try:
            import subprocess
            cmd = [
                "ffprobe", "-v", "quiet", "-print_format", "json",
                "-show_format", "-show_streams", str(path),
            ]
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if proc.returncode == 0:
                probe_data = json.loads(proc.stdout)
                fmt = probe_data.get("format", {})
                stream = next(
                    (s for s in probe_data.get("streams", []) if s.get("codec_type") == "audio"),
                    {},
                )
                result["technical_probe"] = {
                    "duration_seconds": float(fmt.get("duration", 0)),
                    "audio_codec": stream.get("codec_name", "unknown"),
                    "sample_rate": int(stream.get("sample_rate", 0)),
                    "channels": int(stream.get("channels", 0)),
                    "file_size_bytes": int(fmt.get("size", 0)),
                    "bitrate_kbps": round(int(fmt.get("bit_rate", 0)) / 1000, 1),
                }
        except Exception as e:
            logger.warning("ffprobe failed for audio %s: %s", path, e)
            result["quality_risks"].append(f"Could not probe audio: {e}")

    return result


def _probe_image(path: Path) -> dict[str, Any]:
    """Probe an image file for basic metadata."""
    result: dict[str, Any] = {"technical_probe": {}, "quality_risks": []}

    if path.suffix.lower() in _VECTOR_IMAGE_EXTENSIONS:
        result["technical_probe"] = {
            "file_size_bytes": path.stat().st_size,
            "codec": path.suffix.lower().lstrip(".") or "unknown",
        }
        return result

    try:
        from PIL import Image
        with Image.open(path) as img:
            w, h = img.size
            image_format = img.format or "unknown"
            img.verify()
        result["technical_probe"] = {
            "resolution": f"{w}x{h}",
            "file_size_bytes": path.stat().st_size,
            "codec": image_format,
        }
        if w < 640 or h < 480:
            result["quality_risks"].append(f"Low resolution ({w}x{h}) — may need upscaling")
    except ImportError:
        result["quality_risks"].append(
            "Could not probe raster image: Pillow is not installed"
        )
    except Exception as e:
        result["quality_risks"].append(f"Could not probe image: {e}")

    return result


def _has_review_evidence(entry: dict[str, Any]) -> bool:
    """Return True when an entry has real inspection evidence."""
    return bool(
        entry.get("technical_probe")
        or entry.get("representative_frames")
        or entry.get("transcript_summary")
    )


def _transcribe_if_available(
    path: Path, media_type: str, tool_registry: Any
) -> Optional[str]:
    """Attempt transcription for video/audio files."""
    if media_type not in ("video", "audio"):
        return None

    try:
        transcriber = tool_registry.get("transcriber")
        if transcriber and transcriber.get_status().value == "available":
            result = transcriber.execute({"input_path": str(path)})
            if result.success:
                text = result.data.get("text", "")
                if text:
                    # Return summary, not full transcript
                    words = text.split()
                    if len(words) > 100:
                        return f"{' '.join(words[:100])}... ({len(words)} words total)"
                    return text
    except Exception as e:
        logger.warning("Transcription failed for %s: %s", path, e)

    return None


def review_source_media(
    files: list[Path],
    context: dict[str, Any],
    tool_registry: Any = None,
) -> dict[str, Any]:
    """Review user-supplied media files and produce a source_media_review artifact.

    Args:
        files: Paths to user-supplied media files.
        context: Dict with optional keys like 'pipeline_type', 'project_dir'.
        tool_registry: The tool registry instance (for accessing analysis tools).

    Returns:
        Schema-valid source_media_review artifact dict.

    Must never claim a file was reviewed unless a real probe/sampling/transcription ran.
    """
    if tool_registry is None:
        try:
            from tools.tool_registry import registry
            registry.ensure_discovered()
            tool_registry = registry
        except Exception:
            pass

    reviewed_files: list[dict[str, Any]] = []
    all_implications: list[str] = []
    summaries: list[str] = []
    unreviewed_files: list[str] = []

    for file_path in files:
        media_type = detect_media_type(file_path)
        if media_type is None:
            logger.warning("Skipping unrecognized file type: %s", file_path)
            unreviewed_files.append(file_path.name)
            all_implications.append(
                f"{file_path.name} is not a supported media type; "
                "do not plan around it as reviewed source media."
            )
            continue

        if not file_path.exists():
            logger.warning("File does not exist: %s", file_path)
            unreviewed_files.append(file_path.name)
            all_implications.append(
                f"{file_path.name} was provided but does not exist; "
                "do not plan around its contents."
            )
            continue

        entry: dict[str, Any] = {
            "path": str(file_path),
            "media_type": media_type,
            "reviewed": True,
        }

        # Probe based on media type
        if media_type == "video":
            probe_data = _probe_video(file_path, tool_registry)
        elif media_type == "audio":
            probe_data = _probe_audio(file_path, tool_registry)
        else:
            probe_data = _probe_image(file_path)

        detected_media_type = probe_data.get("detected_media_type")
        if media_type == "video" and detected_media_type == "audio":
            media_type = "audio"
            entry["media_type"] = media_type

        entry["technical_probe"] = probe_data.get("technical_probe", {})
        entry["quality_risks"] = probe_data.get("quality_risks", [])
        entry["representative_frames"] = probe_data.get("representative_frames", [])

        # Attempt transcription for audio/video
        transcript = _transcribe_if_available(file_path, media_type, tool_registry)
        if transcript:
            entry["transcript_summary"] = transcript

        if not _has_review_evidence(entry):
            unreviewed_files.append(file_path.name)
            all_implications.append(
                f"{file_path.name} could not be reviewed with available probes; "
                "do not plan around its contents until a real probe succeeds."
            )
            continue

        # Build content summary
        probe = entry["technical_probe"]
        if media_type == "video":
            dur = probe.get("duration_seconds", 0)
            res = probe.get("resolution", "unknown")
            has_audio = bool(probe.get("audio_codec"))
            entry["content_summary"] = (
                f"Video file: {dur:.1f}s at {res}, "
                f"{'with' if has_audio else 'without'} audio"
            )
            entry["usable_for"] = _infer_video_usability(probe, transcript)
        elif media_type == "audio":
            dur = probe.get("duration_seconds", 0)
            entry["content_summary"] = f"Audio file: {dur:.1f}s, {probe.get('audio_codec', 'unknown')}"
            entry["usable_for"] = _infer_audio_usability(probe, transcript)
        else:
            res = probe.get("resolution", "unknown")
            entry["content_summary"] = f"Image file: {res}"
            entry["usable_for"] = ["visual asset", "reference image"]

        summaries.append(f"{file_path.name}: {entry['content_summary']}")
        reviewed_files.append(entry)

        # Derive planning implications from quality risks
        for risk in entry.get("quality_risks", []):
            all_implications.append(f"Quality risk in {file_path.name}: {risk}")

    if unreviewed_files:
        detail = ", ".join(dict.fromkeys(unreviewed_files))
        raise RuntimeError(f"Source media could not be reviewed completely: {detail}")

    # Build overall summary
    if not reviewed_files:
        raise RuntimeError("Source media could not be reviewed: no supported files")
    else:
        summary = "; ".join(summaries)

    # Add media-type implications
    has_video = any(f["media_type"] == "video" for f in reviewed_files)
    has_audio = any(f["media_type"] == "audio" for f in reviewed_files)
    has_images = any(f["media_type"] == "image" for f in reviewed_files)

    if has_video:
        all_implications.append("Source video available — consider source-led or hybrid production approach")
    if has_audio and not has_video:
        all_implications.append("Audio-only source — production needs visual assets to accompany audio")
    if has_images and not has_video:
        all_implications.append("Image-only source — motion must come from animation or video generation")

    if not all_implications:
        all_implications.append("No specific constraints identified from source media.")

    review = {
        "version": "1.0",
        "files": reviewed_files,
        "summary": summary,
        "planning_implications": all_implications,
    }
    validate_artifact("source_media_review", review)
    return review


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_fps(fps_str: str) -> float:
    """Parse ffprobe fps string like '30/1' or '24000/1001'."""
    try:
        if "/" in fps_str:
            num, den = fps_str.split("/")
            return round(int(num) / max(int(den), 1), 2)
        return float(fps_str)
    except (ValueError, ZeroDivisionError):
        return 0.0


def _sample_timestamps(duration: float, count: int = 4) -> list[float]:
    """Generate evenly-spaced sample timestamps for a given duration."""
    if duration <= 0:
        return [0.0]
    if count <= 1:
        return [duration / 2]
    step = duration / (count + 1)
    return [round(step * (i + 1), 2) for i in range(count)]


def _infer_video_usability(probe: dict, transcript: Optional[str]) -> list[str]:
    """Infer what a video file can be used for."""
    uses = []
    dur = probe.get("duration_seconds", 0)
    if dur > 10:
        uses.append("hero footage")
    if dur > 3:
        uses.append("b-roll")
    if transcript:
        uses.append("source dialogue")
    if probe.get("audio_codec"):
        uses.append("source audio")
    return uses or ["short clip"]


def _infer_audio_usability(probe: dict, transcript: Optional[str]) -> list[str]:
    """Infer what an audio file can be used for."""
    uses = []
    dur = probe.get("duration_seconds", 0)
    if transcript:
        uses.append("narration source")
    if dur > 30:
        uses.append("background music candidate")
    if dur > 5:
        uses.append("sound effect or ambient")
    return uses or ["audio clip"]


def has_user_media(project_dir: Path) -> bool:
    """Check if a project directory contains user-supplied media files."""
    if not project_dir.exists():
        return False
    search_roots = [project_dir, project_dir / "reference_assets"]
    media_exts = set().union(_VIDEO_EXTENSIONS, _AUDIO_EXTENSIONS, _IMAGE_EXTENSIONS)
    for root in search_roots:
        if not root.exists():
            continue
        for path in root.iterdir():
            if path.is_file() and path.suffix.lower() in media_exts:
                return True
            if root.name == "reference_assets" and path.is_dir():
                if any(
                    child.is_file() and child.suffix.lower() in media_exts
                    for child in path.rglob("*")
                ):
                    return True
    return False
