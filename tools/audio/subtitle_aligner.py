"""Forced-aligned subtitle generator (faster-whisper).

Takes a list of TTS audio files (each with their reference text and start
offset in the timeline) and emits an ASS subtitle file with word-level
timing aligned to actual phoneme boundaries — not estimated from script word
counts.

Why ASS (not SRT):
  When ffmpeg burns subtitles via the `subtitles=` filter, all sizes/margins
  are interpreted relative to the ASS PlayResX/PlayResY header. SRT lacks
  PlayRes, so libass falls back to a default ~384x288, scaling everything
  wrong. ASS is mandatory for predictable visual layout.

Used by:
  - asset-director-animated.md (Step 3: subtitle generation)

Run from CLI:
  python -m tools.audio.subtitle_aligner \
      --output assets/subtitles.ass \
      --resolution 1080x1920 \
      --segment "assets/audio/n01.mp3:0.0:Hook narration text..." \
      --segment "assets/audio/n02.mp3:6.0:Build narration text..."
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class Word:
    """Single word with timestamps relative to the global timeline."""
    text: str
    start: float
    end: float


@dataclass
class Segment:
    """One TTS audio file + its reference text + where it sits in the timeline."""
    audio_path: str
    text: str
    start_offset_seconds: float


# ────────────────────────────────────────────────────────────────────────────
# Forced alignment via faster-whisper
# ────────────────────────────────────────────────────────────────────────────

# Module-level cache keyed on (model_size, device, compute_type). WhisperModel
# load is the expensive step (multi-second on CPU) — caching lets a multi-
# segment ad reuse one instance instead of paying the load cost N times.
# Pipeline runs are single-threaded so no lock is needed.
_MODEL_CACHE: dict[tuple[str, str, str], Any] = {}


def _clear_model_cache() -> None:
    """Test helper — drop all cached WhisperModel instances.

    Production code never needs this; tests call it to reset between cases.
    """
    _MODEL_CACHE.clear()


def _get_model(model_size: str, device: str, compute_type: str) -> Any:
    """Return a WhisperModel for the given config, instantiating only on cache miss."""
    try:
        from faster_whisper import WhisperModel
    except ImportError as e:
        raise RuntimeError(
            "faster-whisper is not installed. Run: pip install faster-whisper"
        ) from e

    key = (model_size, device, compute_type)
    if key not in _MODEL_CACHE:
        _MODEL_CACHE[key] = WhisperModel(model_size, device=device, compute_type=compute_type)
    return _MODEL_CACHE[key]


def _align_segment(
    segment: Segment,
    model_size: str = "base",
) -> list[Word]:
    """Run Whisper word-level transcription on a TTS file and return words
    offset into the global timeline by `segment.start_offset_seconds`.
    """
    # Default to CPU. CUDA wheels of faster-whisper need libcublas.so.12 +
    # libcudnn — often missing on WSL2 / fresh Linux installs. Set
    # SUBTITLE_ALIGNER_DEVICE=cuda explicitly to override.
    import os
    device = os.environ.get("SUBTITLE_ALIGNER_DEVICE", "cpu")
    compute_type = "float16" if device == "cuda" else "int8"

    model = _get_model(model_size, device, compute_type)

    # initial_prompt biases recognition toward the reference text — cheap
    # forced alignment without WhisperX. For ad-video TTS the audio is
    # clean and the model will almost always produce the same words.
    segments_iter, _info = model.transcribe(
        segment.audio_path,
        word_timestamps=True,
        vad_filter=False,
        initial_prompt=segment.text,
    )

    words: list[Word] = []
    for seg in segments_iter:
        if not seg.words:
            continue
        for w in seg.words:
            if w.start is None or w.end is None:
                continue
            words.append(
                Word(
                    text=w.word.strip(),
                    start=round(w.start + segment.start_offset_seconds, 3),
                    end=round(w.end + segment.start_offset_seconds, 3),
                )
            )
    return words


# ────────────────────────────────────────────────────────────────────────────
# Word grouping → subtitle lines
# ────────────────────────────────────────────────────────────────────────────

_PUNCT_BREAK = {".", "!", "?"}
_PUNCT_SOFT = {",", ";", ":", "—", "–"}


def _group_words(words: list[Word], max_words_per_line: int) -> list[list[Word]]:
    """Group words into subtitle lines.

    Break rules (in priority order):
      1. Hit hard punctuation (. ! ?) at end of word
      2. Hit max_words_per_line
      3. Hit soft punctuation (, ; : — –) AND already at >= max_words_per_line - 1
    """
    lines: list[list[Word]] = []
    current: list[Word] = []
    for w in words:
        current.append(w)
        last_char = w.text.rstrip()[-1:] if w.text.rstrip() else ""
        if last_char in _PUNCT_BREAK:
            lines.append(current)
            current = []
            continue
        if len(current) >= max_words_per_line:
            lines.append(current)
            current = []
            continue
        if last_char in _PUNCT_SOFT and len(current) >= max_words_per_line - 1:
            lines.append(current)
            current = []
    if current:
        lines.append(current)
    return lines


# ────────────────────────────────────────────────────────────────────────────
# ASS file writer
# ────────────────────────────────────────────────────────────────────────────

def _format_ass_time(seconds: float) -> str:
    """Format a float seconds value as ASS time: H:MM:SS.cs"""
    total_cs = max(0, int(seconds * 100 + 0.5))
    hours = total_cs // 360_000
    minutes = (total_cs % 360_000) // 6_000
    secs = (total_cs % 6_000) // 100
    centiseconds = total_cs % 100
    return f"{hours}:{minutes:02d}:{secs:02d}.{centiseconds:02d}"


def _ass_header(width: int, height: int, font_size: int, margin_v: int) -> str:
    return (
        "[Script Info]\n"
        "ScriptType: v4.00+\n"
        f"PlayResX: {width}\n"
        f"PlayResY: {height}\n"
        "ScaledBorderAndShadow: yes\n\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
        "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
        "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding\n"
        f"Style: Default,Inter,{font_size},&H00FFFFFF,&H000000FF,"
        f"&H00000000,&H80000000,1,0,0,0,100,100,0,0,1,2,1,2,40,40,{margin_v},1\n\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )


def _line_to_dialogue(line: list[Word]) -> str:
    start = _format_ass_time(line[0].start)
    end = _format_ass_time(line[-1].end)
    text = " ".join(w.text.strip() for w in line).strip()
    return f"Dialogue: 0,{start},{end},Default,,0,0,0,,{text}\n"


def _validate_no_overlap(lines: list[list[Word]]) -> list[str]:
    """Return any error strings — empty list means clean."""
    errors = []
    last_end = 0.0
    for i, line in enumerate(lines):
        if not line:
            continue
        start = line[0].start
        if start < last_end - 0.001:
            errors.append(
                f"line {i}: start {start:.2f}s overlaps previous line ending at {last_end:.2f}s"
            )
        last_end = max(last_end, line[-1].end)
    return errors


def _clamp_no_overlap(lines: list[list[Word]], gap_seconds: float = 0.05) -> list[list[Word]]:
    """Mutate `lines` so no two consecutive lines overlap visually.

    Strategy:
      1. Drop trailing words from line[i-1] whose `start` >= line[i][0].start - gap.
         (When TTS audio of two adjacent narration files genuinely overlaps,
          the only honest fix is to omit the late words from subtitles —
          truncating the End time alone leaves a too-late display tail.)
      2. After dropping, clamp the remaining last word's `end` to next_start - gap.
    """
    for i in range(1, len(lines)):
        if not lines[i] or not lines[i - 1]:
            continue
        next_start = lines[i][0].start

        while (
            lines[i - 1]
            and lines[i - 1][-1].start >= next_start - gap_seconds
        ):
            lines[i - 1].pop()

        if not lines[i - 1]:
            continue
        prev_last = lines[i - 1][-1]
        if prev_last.end > next_start - gap_seconds:
            prev_last.end = round(max(prev_last.start + 0.05, next_start - gap_seconds), 3)
    return [line for line in lines if line]


# ────────────────────────────────────────────────────────────────────────────
# Public API
# ────────────────────────────────────────────────────────────────────────────

def align(
    segments: list[Segment],
    output_path: Path,
    width: int = 1080,
    height: int = 1920,
    max_words_per_line: int | None = None,
    font_size: int | None = None,
    margin_v: int | None = None,
    model_size: str = "base",
) -> dict[str, Any]:
    """Produce a forced-aligned ASS subtitle file from a list of TTS segments.

    Returns a dict with `output_path`, `lines`, `total_words`, `validation_errors`.
    """
    is_vertical = height > width
    if max_words_per_line is None:
        max_words_per_line = 5 if is_vertical else 9
    if font_size is None:
        font_size = 28 if is_vertical else 24
    if margin_v is None:
        margin_v = 160 if is_vertical else 20

    output_path.parent.mkdir(parents=True, exist_ok=True)

    all_words: list[Word] = []
    for seg in segments:
        all_words.extend(_align_segment(seg, model_size=model_size))

    grouped = _group_words(all_words, max_words_per_line)

    # Auto-clamp so visually overlapping lines don't double up on screen.
    # The underlying TTS audio is not modified — only subtitle End times are
    # pulled back. If clamping was applied, we still surface the original
    # overlaps as warnings so script-director can investigate the timing bug.
    pre_clamp_errors = _validate_no_overlap(grouped)
    grouped = _clamp_no_overlap(grouped)

    body_parts = [_line_to_dialogue(line) for line in grouped if line]
    output_path.write_text(
        _ass_header(width, height, font_size, margin_v) + "".join(body_parts),
        encoding="utf-8",
    )

    errors = _validate_no_overlap(grouped)

    return {
        "output_path": str(output_path),
        "lines": len(grouped),
        "total_words": len(all_words),
        "validation_errors": errors,
        "warnings_pre_clamp": pre_clamp_errors,  # underlying TTS overlap signal
        "ok": len(errors) == 0,
    }


# ────────────────────────────────────────────────────────────────────────────
# CLI
# ────────────────────────────────────────────────────────────────────────────

def _parse_segment_arg(s: str) -> Segment:
    """Parse 'audio_path:start_seconds:text' (text may contain colons; only first 2 are split)."""
    parts = s.split(":", 2)
    if len(parts) != 3:
        raise argparse.ArgumentTypeError(
            f"--segment must be 'audio_path:start_seconds:text', got {s!r}"
        )
    return Segment(
        audio_path=parts[0],
        start_offset_seconds=float(parts[1]),
        text=parts[2],
    )


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="subtitle_aligner")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--resolution", default="1080x1920", help="WIDTHxHEIGHT")
    parser.add_argument(
        "--segment",
        action="append",
        type=_parse_segment_arg,
        default=[],
        help="Segment as 'audio_path:start_seconds:text'. Repeat for each TTS file.",
    )
    parser.add_argument("--segments-json", type=Path, help="Path to JSON file with segments[]")
    parser.add_argument("--max-words-per-line", type=int, default=None)
    parser.add_argument("--font-size", type=int, default=None)
    parser.add_argument("--margin-v", type=int, default=None)
    parser.add_argument("--model-size", default="base", help="faster-whisper model: tiny|base|small|medium|large")
    args = parser.parse_args(argv[1:])

    width, height = (int(p) for p in args.resolution.lower().split("x"))

    segments: list[Segment] = list(args.segment)
    if args.segments_json:
        for s in json.loads(args.segments_json.read_text()):
            segments.append(
                Segment(
                    audio_path=s["audio_path"],
                    start_offset_seconds=float(s["start_offset_seconds"]),
                    text=s["text"],
                )
            )

    if not segments:
        parser.error("Provide at least one --segment or --segments-json")

    report = align(
        segments,
        output_path=args.output,
        width=width,
        height=height,
        max_words_per_line=args.max_words_per_line,
        font_size=args.font_size,
        margin_v=args.margin_v,
        model_size=args.model_size,
    )
    print(json.dumps(report, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
