"""Audio mixer tool wrapping FFmpeg and pydub.

Mixes speech, music, and SFX tracks with support for ducking, fades,
and volume normalization. Falls back to FFmpeg-only mode if pydub is
not installed.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from tools.base_tool import (
    BaseTool,
    Determinism,
    ExecutionMode,
    ResourceProfile,
    ToolResult,
    ToolStability,
    ToolStatus,
    ToolTier,
)


class AudioMixer(BaseTool):
    name = "audio_mixer"
    version = "0.1.0"
    tier = ToolTier.CORE
    capability = "audio_processing"
    provider = "ffmpeg"
    stability = ToolStability.EXPERIMENTAL
    execution_mode = ExecutionMode.SYNC
    determinism = Determinism.DETERMINISTIC

    dependencies = ["cmd:ffmpeg"]
    install_instructions = (
        "FFmpeg is required. pydub is optional for advanced mixing:\n"
        "pip install pydub"
    )
    agent_skills = ["ffmpeg", "video_toolkit"]

    capabilities = ["mix", "duck", "fade", "normalize", "extract_audio", "segmented_music"]
    best_for = [
        "Combining narration, music, and effects into a final mix",
        "Applying speech ducking and segment-specific music beds",
    ]

    input_schema = {
        "type": "object",
        "required": ["operation"],
        "properties": {
            "operation": {
                "type": "string",
                "enum": ["mix", "duck", "extract", "full_mix", "segmented_music"],
                "description": (
                    "mix: layer multiple tracks with volume/delay/fades. "
                    "duck: lower music volume when speech is present. "
                    "extract: extract audio from video file. "
                    "full_mix: combine narration tracks + music with ducking + normalize "
                    "in a single call (preferred for compose-director). "
                    "segmented_music: mix music into a video only during specified "
                    "time segments (e.g. music during talking head, silence during "
                    "showcase clips)."
                ),
            },
            "tracks": {
                "type": "array",
                "description": (
                    "Audio tracks for mix/duck operations (advanced format). "
                    "For duck, each track needs a 'role' of 'speech' or 'music'. "
                    "For the simple duck API, use primary_audio/secondary_audio instead."
                ),
                "items": {
                    "type": "object",
                    "required": ["path", "role"],
                    "properties": {
                        "path": {"type": "string"},
                        "role": {
                            "type": "string",
                            "enum": ["speech", "music", "sfx", "primary", "secondary"],
                        },
                        "volume": {
                            "type": "number",
                            "minimum": 0,
                            "maximum": 1.0,
                            "default": 1.0,
                        },
                        "start_seconds": {"type": "number", "minimum": 0},
                        "fade_in_seconds": {"type": "number", "minimum": 0},
                        "fade_out_seconds": {"type": "number", "minimum": 0},
                    },
                },
            },
            "primary_audio": {
                "type": "string",
                "description": (
                    "Path to primary/speech audio track (duck operation, simple format). "
                    "This is the track that stays at full volume (e.g. narration/dialogue). "
                    "Use with secondary_audio as an alternative to the tracks array."
                ),
            },
            "secondary_audio": {
                "type": "string",
                "description": (
                    "Path to secondary/music audio track (duck operation, simple format). "
                    "This track gets ducked (volume lowered) when primary audio is present. "
                    "Use with primary_audio as an alternative to the tracks array."
                ),
            },
            "duck_level": {
                "type": "number",
                "description": (
                    "Ducking attenuation in dB for the secondary track (duck operation, "
                    "simple format). Negative values reduce volume, e.g. -12 means duck "
                    "by 12dB. Converted to a linear ratio internally. Default: -12."
                ),
                "default": -12,
            },
            "input_path": {"type": "string", "description": "Input for extract operation"},
            "output_path": {"type": "string"},
            "ducking": {
                "type": "object",
                "description": (
                    "Advanced ducking parameters. Works with both the simple "
                    "(primary_audio/secondary_audio) and advanced (tracks) formats."
                ),
                "properties": {
                    "enabled": {"type": "boolean", "default": True},
                    "music_volume_during_speech": {
                        "type": "number", "minimum": 0, "maximum": 1.0, "default": 0.15,
                    },
                    "attack_ms": {"type": "number", "default": 200},
                    "release_ms": {"type": "number", "default": 500},
                },
            },
            "normalize": {"type": "boolean", "default": True},
            "target_lufs": {
                "type": "number",
                "default": -16,
                "description": (
                    "Target integrated loudness for loudnorm when normalize is true. "
                    "Common platform defaults: TikTok/Reels/Shorts -14, YouTube -13, "
                    "broadcast -23. Omitted values preserve the legacy -16 default."
                ),
            },
            "target_total_duration_seconds": {
                "type": "number",
                "minimum": 0,
                "description": (
                    "Optional hard output duration. When set for mix/full_mix, the "
                    "tool pads or trims the audio so it matches the final video runtime."
                ),
            },
            "video_path": {
                "type": "string",
                "description": (
                    "Path to the assembled video (segmented_music operation). "
                    "Music is mixed into this video's audio at specified segments."
                ),
            },
            "music_path": {
                "type": "string",
                "description": "Path to background music file (segmented_music operation).",
            },
            "music_volume": {
                "type": "number",
                "minimum": 0,
                "maximum": 1.0,
                "default": 0.20,
                "description": "Volume level for music during active segments.",
            },
            "segments": {
                "type": "array",
                "description": (
                    "Time segments where music should play (segmented_music operation). "
                    "Each segment: {start: seconds, end: seconds}. Music fades in/out "
                    "at segment boundaries. Outside these segments, music is silent."
                ),
                "items": {
                    "type": "object",
                    "required": ["start", "end"],
                    "properties": {
                        "start": {"type": "number", "minimum": 0},
                        "end": {"type": "number", "minimum": 0},
                    },
                },
            },
            "fade_duration": {
                "type": "number",
                "default": 0.5,
                "description": "Duration of fade in/out at segment boundaries (seconds).",
            },
            "music_volume_schedule": {
                "type": "array",
                "description": (
                    "Path B: per-timestamp music gain envelope produced by "
                    "lib.intensity_curve.derive_duck_schedule. When provided "
                    "(and non-empty) on a 'duck' or 'full_mix' operation, the "
                    "music track is attenuated by a deterministic time-varying "
                    "FFmpeg volume filter instead of the speech-amplitude-driven "
                    "sidechaincompress path. Empty list / absent = legacy path."
                ),
                "items": {
                    "type": "object",
                    "required": ["t_seconds", "gain_db"],
                    "properties": {
                        "t_seconds": {"type": "number", "minimum": 0},
                        "gain_db": {"type": "number"},
                    },
                },
            },
        },
    }

    resource_profile = ResourceProfile(cpu_cores=2, ram_mb=1024, vram_mb=0, disk_mb=500)
    idempotency_key_fields = [
        "operation",
        "output_path",
        "tracks",
        "primary_audio",
        "secondary_audio",
        "duck_level",
        "ducking",
        "input_path",
        "normalize",
        "target_lufs",
        "target_total_duration_seconds",
        "music_volume_schedule",
        "video_path",
        "music_path",
        "music_volume",
        "segments",
        "fade_duration",
    ]
    side_effects = ["writes mixed audio file to output_path"]
    user_visible_verification = [
        "Listen to mixed output and verify speech clarity and music ducking",
    ]

    def execute(self, inputs: dict[str, Any]) -> ToolResult:
        operation = inputs["operation"]
        start = time.time()

        try:
            if operation == "mix":
                result = self._mix(inputs)
            elif operation == "duck":
                result = self._duck(inputs)
            elif operation == "extract":
                result = self._extract(inputs)
            elif operation == "full_mix":
                result = self._full_mix(inputs)
            elif operation == "segmented_music":
                result = self._segmented_music(inputs)
            else:
                return ToolResult(success=False, error=f"Unknown operation: {operation}")
        except Exception as e:
            return ToolResult(success=False, error=str(e))

        result.duration_seconds = round(time.time() - start, 2)
        return result

    def _mix(self, inputs: dict[str, Any]) -> ToolResult:
        """Mix multiple audio tracks into one output."""
        tracks = inputs.get("tracks", [])
        if not tracks:
            return ToolResult(success=False, error="No tracks provided")

        output_path = Path(inputs.get("output_path", "mixed_audio.wav"))
        normalize = inputs.get("normalize", True)
        # Configurable LUFS target. Per-platform defaults:
        #   TikTok / Reels / Shorts → -14, YouTube → -13, broadcast → -23.
        # Falls back to -16 (legacy) when omitted to preserve back-compat.
        target_lufs = float(inputs.get("target_lufs", -16))
        # Hard duration target — pad with silence (or truncate) so the output
        # matches the video runtime. Prevents the "mix ends at 26s for a 30s
        # video, final frames silent" failure mode. None = skip.
        target_total_duration_seconds = inputs.get("target_total_duration_seconds")

        # Validate all inputs exist
        for t in tracks:
            if not Path(t["path"]).exists():
                return ToolResult(success=False, error=f"Track not found: {t['path']}")

        # Build FFmpeg complex filter for mixing
        filter_parts = []
        input_args = []

        for i, track in enumerate(tracks):
            input_args.extend(["-i", track["path"]])
            volume = track.get("volume", 1.0)
            delay_ms = int(track.get("start_seconds", 0) * 1000)
            fade_in = track.get("fade_in_seconds", 0)
            fade_out = track.get("fade_out_seconds", 0)

            filters = []
            if volume != 1.0:
                filters.append(f"volume={volume}")
            if delay_ms > 0:
                filters.append(f"adelay={delay_ms}|{delay_ms}")
            if fade_in > 0:
                filters.append(f"afade=t=in:d={fade_in}")
            if fade_out > 0:
                filters.append(f"afade=t=out:d={fade_out}")

            if filters:
                filter_chain = ",".join(filters)
                filter_parts.append(f"[{i}:a]{filter_chain}[a{i}]")
            else:
                filter_parts.append(f"[{i}:a]acopy[a{i}]")

        # Amix all processed streams
        mix_inputs = "".join(f"[a{i}]" for i in range(len(tracks)))
        filter_parts.append(
            f"{mix_inputs}amix=inputs={len(tracks)}:duration=longest:dropout_transition=2[mixed]"
        )

        # Optional duration contract: pad with silence (or truncate) so the
        # output is exactly target_total_duration_seconds long.
        if target_total_duration_seconds:
            d = float(target_total_duration_seconds)
            filter_parts.append(
                f"[mixed]apad=whole_dur={d},atrim=0:{d},asetpts=N/SR/TB[mixed_padded]"
            )
            mixed_label = "[mixed_padded]"
        else:
            mixed_label = "[mixed]"

        if normalize:
            filter_parts.append(
                f"{mixed_label}loudnorm=I={target_lufs}:LRA=11:TP=-1.5[out]"
            )
            out_label = "[out]"
        else:
            out_label = mixed_label

        filter_complex = ";".join(filter_parts)

        cmd = ["ffmpeg", "-y"]
        cmd.extend(input_args)
        cmd.extend(["-filter_complex", filter_complex])
        cmd.extend(["-map", out_label, str(output_path)])

        self.run_command(cmd)

        return ToolResult(
            success=True,
            data={
                "operation": "mix",
                "track_count": len(tracks),
                "output": str(output_path),
                "normalized": normalize,
            },
            artifacts=[str(output_path)],
        )

    def _duck(self, inputs: dict[str, Any]) -> ToolResult:
        """Apply ducking: lower music volume when speech is present.

        Path B: if ``music_volume_schedule`` is provided and non-empty, the
        music track is attenuated by a time-varying FFmpeg ``volume`` filter
        whose envelope is dictated by the schedule (deterministic, derived from
        the bible's emotional intensity curve). Otherwise the legacy
        speech-amplitude-driven sidechaincompress path runs unchanged.

        Accepts two input formats:

        Simple format (preferred for agents):
            {
                "operation": "duck",
                "primary_audio": "speech.mp3",
                "secondary_audio": "music.mp3",
                "duck_level": -12,
                "output_path": "out.wav"
            }

        Advanced format (tracks array):
            {
                "operation": "duck",
                "tracks": [
                    {"path": "speech.mp3", "role": "primary"},  # or "speech"
                    {"path": "music.mp3", "role": "secondary"}  # or "music"
                ],
                "output_path": "out.wav"
            }
        """
        ducking = inputs.get("ducking", {})
        output_path = Path(inputs.get("output_path", "ducked_audio.wav"))
        schedule = inputs.get("music_volume_schedule") or []

        # --- Resolve speech/music paths from either input format ---
        speech_path = None
        music_path = None

        # Simple format: primary_audio / secondary_audio
        if "primary_audio" in inputs or "secondary_audio" in inputs:
            speech_path = inputs.get("primary_audio")
            music_path = inputs.get("secondary_audio")
            # If duck_level (dB) is provided, convert to linear ratio for
            # music_volume_during_speech.  e.g. -12 dB -> 10^(-12/20) ~ 0.25
            if "duck_level" in inputs and "ducking" not in inputs:
                import math
                db = inputs["duck_level"]
                ducking = dict(ducking)  # copy so we don't mutate caller
                ducking.setdefault(
                    "music_volume_during_speech",
                    round(math.pow(10, db / 20), 4),
                )

        # Advanced format: tracks array with role field
        tracks = inputs.get("tracks", [])
        if tracks and speech_path is None and music_path is None:
            # Support both naming conventions: speech/music and primary/secondary
            speech_tracks = [
                t for t in tracks if t.get("role") in ("speech", "primary")
            ]
            music_tracks = [
                t for t in tracks if t.get("role") in ("music", "secondary")
            ]
            if speech_tracks:
                speech_path = speech_tracks[0]["path"]
            if music_tracks:
                music_path = music_tracks[0]["path"]

        if not speech_path or not music_path:
            return ToolResult(
                success=False,
                error=(
                    "Ducking requires a primary (speech) and secondary (music) track. "
                    "Provide either primary_audio/secondary_audio params, or a tracks "
                    "array with role='speech'/'primary' and role='music'/'secondary'."
                ),
            )

        # Path B: schedule-driven duck envelope replaces sidechaincompress.
        if schedule:
            return self._duck_with_schedule(
                speech_path=speech_path,
                music_path=music_path,
                schedule=schedule,
                output_path=output_path,
            )

        # Use FFmpeg sidechaincompress for ducking.
        # Speech (input 0) is split into two copies: one feeds the sidechain
        # key signal, the other goes to the final mix output. This avoids the
        # "filter graph label consumed twice" error that breaks the naive pattern
        # of using [0:a] both as sidechain key and in the amix output.
        music_vol = ducking.get("music_volume_during_speech", 0.15)
        attack = ducking.get("attack_ms", 200) / 1000
        release = ducking.get("release_ms", 500) / 1000

        filter_complex = (
            f"[0:a]asplit=2[speech_key][speech_out];"
            f"[1:a][speech_key]sidechaincompress="
            f"threshold=0.02:ratio=9:attack={attack}:release={release}:"
            f"level_sc=1:mix=0.9[music_ducked];"
            f"[music_ducked]volume={music_vol * 3}[music_out];"
            f"[speech_out][music_out]amix=inputs=2:duration=longest[out]"
        )

        cmd = [
            "ffmpeg", "-y",
            "-i", speech_path,
            "-i", music_path,
            "-filter_complex", filter_complex,
            "-map", "[out]",
            str(output_path),
        ]

        self.run_command(cmd)

        return ToolResult(
            success=True,
            data={
                "operation": "duck",
                "speech_track": speech_path,
                "music_track": music_path,
                "output": str(output_path),
            },
            artifacts=[str(output_path)],
        )

    def _duck_with_schedule(
        self,
        *,
        speech_path: str,
        music_path: str,
        schedule: list[dict[str, float]],
        output_path: Path,
    ) -> ToolResult:
        """Path B: attenuate music with a deterministic time-varying volume envelope.

        Compiles ``schedule`` into an FFmpeg ``volume`` expression and applies it
        to the music track with ``eval=frame`` so the gain is recomputed every
        frame. Speech passes through unchanged and is mixed with the
        envelope-shaped music via ``amix``.
        """
        # Validate inputs explicitly so a missing fixture surfaces as a clean
        # ToolResult error instead of an opaque subprocess.CalledProcessError dump.
        if not Path(speech_path).exists():
            return ToolResult(
                success=False,
                error=f"Speech audio not found: {speech_path}",
            )
        if not Path(music_path).exists():
            return ToolResult(
                success=False,
                error=f"Music audio not found: {music_path}",
            )

        # Local import keeps audio_mixer's module-load surface unchanged for
        # registry discovery — only paid on the schedule code path.
        from lib.intensity_curve import compile_volume_schedule_to_ffmpeg_expr

        volume_expr = compile_volume_schedule_to_ffmpeg_expr(schedule)

        filter_complex = (
            f"[1:a]volume='{volume_expr}':eval=frame[music_env];"
            f"[0:a][music_env]amix=inputs=2:duration=longest:dropout_transition=0[out]"
        )

        cmd = [
            "ffmpeg", "-y",
            "-i", speech_path,
            "-i", music_path,
            "-filter_complex", filter_complex,
            "-map", "[out]",
            str(output_path),
        ]

        self.run_command(cmd)

        return ToolResult(
            success=True,
            data={
                "operation": "duck",
                "mode": "schedule",
                "speech_track": speech_path,
                "music_track": music_path,
                "schedule_samples": len(schedule),
                "output": str(output_path),
            },
            artifacts=[str(output_path)],
        )

    def _extract(self, inputs: dict[str, Any]) -> ToolResult:
        """Extract audio from a video file."""
        input_path = Path(inputs["input_path"])
        if not input_path.exists():
            return ToolResult(success=False, error=f"Input not found: {input_path}")

        output_path = Path(
            inputs.get("output_path", str(input_path.with_suffix(".wav")))
        )

        cmd = [
            "ffmpeg", "-y",
            "-i", str(input_path),
            "-vn",
            "-acodec", "pcm_s16le",
            "-ar", "16000",
            "-ac", "1",
            str(output_path),
        ]

        self.run_command(cmd)

        return ToolResult(
            success=True,
            data={
                "operation": "extract",
                "input": str(input_path),
                "output": str(output_path),
            },
            artifacts=[str(output_path)],
        )

    def _probe_audio_duration(self, path: Path) -> float | None:
        """Return audio duration in seconds via ffprobe, or None on error."""
        try:
            result = self.run_command([
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "csv=p=0",
                str(path),
            ])
            return round(float(result.stdout.strip().split("\n")[0]), 2)
        except Exception:
            return None

    def _full_mix(self, inputs: dict[str, Any]) -> ToolResult:
        """One-call mix: layer narration tracks, add music with ducking, normalize.

        This is the preferred operation for the compose-director skill.
        It combines mix + duck + normalize in a single FFmpeg filter graph.

        Input format:
            {
                "operation": "full_mix",
                "tracks": [
                    {"path": "narration_s1.mp3", "role": "speech", "start_seconds": 0},
                    {"path": "narration_s2.mp3", "role": "speech", "start_seconds": 10.5},
                    {"path": "music.mp3", "role": "music", "volume": 0.3}
                ],
                "ducking": {
                    "enabled": true,
                    "music_volume_during_speech": 0.15,
                    "attack_ms": 200,
                    "release_ms": 500
                },
                "normalize": true,
                "output_path": "mixed_audio.wav"
            }
        """
        tracks = inputs.get("tracks", [])
        if not tracks:
            return ToolResult(success=False, error="No tracks provided for full_mix")

        output_path = Path(inputs.get("output_path", "full_mix_output.wav"))
        output_path.parent.mkdir(parents=True, exist_ok=True)
        normalize = inputs.get("normalize", True)
        ducking = inputs.get("ducking", {"enabled": True})
        # Configurable LUFS target. Per-platform defaults:
        #   TikTok / Reels / Shorts → -14, YouTube → -13, broadcast → -23.
        # Falls back to -16 (legacy) when omitted.
        target_lufs = float(inputs.get("target_lufs", -16))
        # Hard duration target — pad with silence (or truncate) so the output
        # matches the video runtime. None = skip.
        target_total_duration_seconds = inputs.get("target_total_duration_seconds")

        speech_tracks = [t for t in tracks if t.get("role") in ("speech", "primary")]
        music_tracks = [t for t in tracks if t.get("role") in ("music", "secondary")]
        sfx_tracks = [t for t in tracks if t.get("role") == "sfx"]
        all_tracks = speech_tracks + music_tracks + sfx_tracks

        if not all_tracks:
            return ToolResult(success=False, error="No valid tracks (need speech/music/sfx roles)")

        # Validate all files exist
        for t in all_tracks:
            if not Path(t["path"]).exists():
                return ToolResult(success=False, error=f"Track not found: {t['path']}")

        # Build FFmpeg inputs and filter graph
        input_args = []
        filter_parts = []

        for i, track in enumerate(all_tracks):
            input_args.extend(["-i", track["path"]])
            volume = track.get("volume", 1.0)
            delay_ms = int(track.get("start_seconds", 0) * 1000)
            fade_in = track.get("fade_in_seconds", 0)
            fade_out = track.get("fade_out_seconds", 0)

            filters = []
            if volume != 1.0:
                filters.append(f"volume={volume}")
            if delay_ms > 0:
                filters.append(f"adelay={delay_ms}|{delay_ms}")
            if fade_in > 0:
                filters.append(f"afade=t=in:d={fade_in}")
            if fade_out > 0:
                filters.append(f"afade=t=out:d={fade_out}")

            if filters:
                filter_chain = ",".join(filters)
                filter_parts.append(f"[{i}:a]{filter_chain}[a{i}]")
            else:
                filter_parts.append(f"[{i}:a]acopy[a{i}]")

        duck_enabled = ducking.get("enabled", True) if isinstance(ducking, dict) else bool(ducking)
        duck_params = ducking if isinstance(ducking, dict) else {}
        music_vol = duck_params.get("music_volume_during_speech", 0.15)
        schedule = inputs.get("music_volume_schedule") or []

        if schedule and music_tracks:
            from lib.intensity_curve import compile_volume_schedule_to_ffmpeg_expr

            volume_expr = compile_volume_schedule_to_ffmpeg_expr(schedule)
            schedule_parts = list(filter_parts)
            mix_labels: list[str] = []

            speech_indices = list(range(len(speech_tracks)))
            music_start = len(speech_tracks)
            music_indices = list(range(music_start, music_start + len(music_tracks)))
            sfx_start = len(speech_tracks) + len(music_tracks)

            if speech_indices:
                speech_labels = "".join(f"[a{i}]" for i in speech_indices)
                if len(speech_indices) > 1:
                    schedule_parts.append(
                        f"{speech_labels}amix=inputs={len(speech_indices)}:"
                        f"duration=longest[speech_out]"
                    )
                else:
                    schedule_parts.append(f"[a{speech_indices[0]}]acopy[speech_out]")
                mix_labels.append("[speech_out]")

            music_labels = "".join(f"[a{i}]" for i in music_indices)
            if len(music_indices) > 1:
                schedule_parts.append(
                    f"{music_labels}amix=inputs={len(music_indices)}:"
                    f"duration=longest[music_pre]"
                )
                music_input = "[music_pre]"
            else:
                music_input = f"[a{music_indices[0]}]"

            schedule_parts.append(
                f"{music_input}volume='{volume_expr}':eval=frame[music_env]"
            )
            mix_labels.append("[music_env]")

            if sfx_tracks:
                mix_labels.extend(
                    f"[a{i}]" for i in range(sfx_start, sfx_start + len(sfx_tracks))
                )

            if len(mix_labels) > 1:
                all_labels = "".join(mix_labels)
                schedule_parts.append(
                    f"{all_labels}amix=inputs={len(mix_labels)}:"
                    f"duration=longest:dropout_transition=2[premix]"
                )
                premix_label = "[premix]"
            else:
                schedule_parts.append(f"{mix_labels[0]}acopy[premix]")
                premix_label = "[premix]"

            if target_total_duration_seconds:
                d = float(target_total_duration_seconds)
                schedule_parts.append(
                    f"{premix_label}apad=whole_dur={d},atrim=0:{d},"
                    f"asetpts=N/SR/TB[premix_padded]"
                )
                premix_label = "[premix_padded]"

            if normalize:
                schedule_parts.append(
                    f"{premix_label}loudnorm=I={target_lufs}:LRA=11:TP=-1.5[out]"
                )
                out_label = "[out]"
            else:
                out_label = premix_label

            schedule_filter = ";".join(p for p in schedule_parts if p)
            schedule_cmd = ["ffmpeg", "-y"] + input_args + [
                "-filter_complex", schedule_filter,
                "-map", out_label,
                str(output_path),
            ]
            self.run_command(schedule_cmd)
            return ToolResult(
                success=True,
                data={
                    "operation": "full_mix",
                    "speech_tracks": len(speech_tracks),
                    "music_tracks": len(music_tracks),
                    "sfx_tracks": len(sfx_tracks),
                    "ducking_enabled": True,
                    "ducking_mode": "schedule",
                    "schedule_samples": len(schedule),
                    "normalized": normalize,
                    "output": str(output_path),
                    "duration_seconds": self._probe_audio_duration(output_path),
                },
                artifacts=[str(output_path)],
            )

        if duck_enabled and speech_tracks and music_tracks:
            attack = duck_params.get("attack_ms", 200) / 1000
            release = duck_params.get("release_ms", 500) / 1000
            speech_indices = list(range(len(speech_tracks)))
            music_start = len(speech_tracks)
            music_indices = list(range(music_start, music_start + len(music_tracks)))
            sfx_start = len(speech_tracks) + len(music_tracks)

            # Build sidechain filter graph.
            # Each speech track is split: one copy feeds the sidechain key signal,
            # the other feeds the final output mix. This avoids the "filter graph
            # label consumed twice" error that caused the original implementation to fail.
            sc_parts = list(filter_parts)
            for i in speech_indices:
                sc_parts.append(f"[a{i}]asplit=2[asp{i}a][asp{i}b]")

            speech_key_labels = "".join(f"[asp{i}a]" for i in speech_indices)
            speech_out_labels = "".join(f"[asp{i}b]" for i in speech_indices)

            if len(speech_tracks) > 1:
                sc_parts.append(
                    f"{speech_key_labels}amix=inputs={len(speech_tracks)}:duration=longest[speech_key]"
                )
                sc_parts.append(
                    f"{speech_out_labels}amix=inputs={len(speech_tracks)}:duration=longest[speech_out]"
                )
            else:
                sc_parts.append(f"[asp{speech_indices[0]}a]acopy[speech_key]")
                sc_parts.append(f"[asp{speech_indices[0]}b]acopy[speech_out]")

            music_labels = "".join(f"[a{i}]" for i in music_indices)
            if len(music_tracks) > 1:
                sc_parts.append(
                    f"{music_labels}amix=inputs={len(music_tracks)}:duration=longest[music_pre]"
                )
                music_in = "[music_pre]"
            else:
                music_in = f"[a{music_indices[0]}]"

            sc_parts.append(
                f"{music_in}[speech_key]sidechaincompress="
                f"threshold=0.02:ratio=9:attack={attack}:release={release}:"
                f"level_sc=1:mix=0.9[music_ducked]"
            )
            sc_parts.append(f"[music_ducked]volume={music_vol * 3}[music_out]")

            if sfx_tracks:
                sfx_labels = "".join(f"[a{i}]" for i in range(sfx_start, sfx_start + len(sfx_tracks)))
                sc_parts.append(
                    f"[speech_out][music_out]{sfx_labels}"
                    f"amix=inputs={2 + len(sfx_tracks)}:duration=longest[premix]"
                )
            else:
                sc_parts.append("[speech_out][music_out]amix=inputs=2:duration=longest[premix]")

            if target_total_duration_seconds:
                d = float(target_total_duration_seconds)
                sc_parts.append(
                    f"[premix]apad=whole_dur={d},atrim=0:{d},asetpts=N/SR/TB[premix_padded]"
                )
                premix_label = "[premix_padded]"
            else:
                premix_label = "[premix]"

            if normalize:
                sc_parts.append(
                    f"{premix_label}loudnorm=I={target_lufs}:LRA=11:TP=-1.5[out]"
                )
                sc_out_label = "[out]"
            else:
                sc_out_label = premix_label

            sc_filter = ";".join(p for p in sc_parts if p)
            sc_cmd = ["ffmpeg", "-y"] + input_args + [
                "-filter_complex", sc_filter,
                "-map", sc_out_label,
                str(output_path),
            ]
            try:
                self.run_command(sc_cmd)
                return ToolResult(
                    success=True,
                    data={
                        "operation": "full_mix",
                        "speech_tracks": len(speech_tracks),
                        "music_tracks": len(music_tracks),
                        "sfx_tracks": len(sfx_tracks),
                        "ducking_enabled": True,
                        "ducking_mode": "sidechaincompress",
                        "normalized": normalize,
                        "output": str(output_path),
                        "duration_seconds": self._probe_audio_duration(output_path),
                    },
                    artifacts=[str(output_path)],
                )
            except Exception:
                pass  # sidechaincompress unavailable — fall through to fixed-volume mix

            # Fallback: fixed-volume music mix (reliable on all FFmpeg builds).
            # Reset filter_parts and rebuild without sidechaincompress.
            filter_parts = []
            for i, track in enumerate(all_tracks):
                vol = track.get("volume", 1.0)
                # Apply ducking volume reduction to music tracks
                if track.get("role") in ("music", "secondary"):
                    vol = vol * music_vol
                delay_ms = int(track.get("start_seconds", 0) * 1000)
                fade_in = track.get("fade_in_seconds", 0)
                fade_out = track.get("fade_out_seconds", 0)
                filters = []
                if vol != 1.0:
                    filters.append(f"volume={vol}")
                if delay_ms > 0:
                    filters.append(f"adelay={delay_ms}|{delay_ms}")
                if fade_in > 0:
                    filters.append(f"afade=t=in:d={fade_in}")
                if fade_out > 0:
                    filters.append(f"afade=t=out:d={fade_out}")
                if filters:
                    filter_parts.append(f"[{i}:a]{','.join(filters)}[a{i}]")
                else:
                    filter_parts.append(f"[{i}:a]acopy[a{i}]")

        # Simple amix of all (possibly pre-volume-adjusted) tracks
        all_labels = "".join(f"[a{i}]" for i in range(len(all_tracks)))
        filter_parts.append(
            f"{all_labels}amix=inputs={len(all_tracks)}:duration=longest:dropout_transition=2[premix]"
        )

        if target_total_duration_seconds:
            d = float(target_total_duration_seconds)
            filter_parts.append(
                f"[premix]apad=whole_dur={d},atrim=0:{d},asetpts=N/SR/TB[premix_padded]"
            )
            premix_label = "[premix_padded]"
        else:
            premix_label = "[premix]"

        # Normalize
        if normalize:
            filter_parts.append(
                f"{premix_label}loudnorm=I={target_lufs}:LRA=11:TP=-1.5[out]"
            )
            out_label = "[out]"
        else:
            out_label = premix_label

        filter_complex = ";".join(p for p in filter_parts if p)

        cmd = ["ffmpeg", "-y"]
        cmd.extend(input_args)
        cmd.extend(["-filter_complex", filter_complex])
        cmd.extend(["-map", out_label, str(output_path)])

        self.run_command(cmd)

        return ToolResult(
            success=True,
            data={
                "operation": "full_mix",
                "speech_tracks": len(speech_tracks),
                "music_tracks": len(music_tracks),
                "sfx_tracks": len(sfx_tracks),
                "ducking_enabled": duck_enabled,
                "normalized": normalize,
                "output": str(output_path),
                "duration_seconds": self._probe_audio_duration(output_path),
            },
            artifacts=[str(output_path)],
        )

    def _segmented_music(self, inputs: dict[str, Any]) -> ToolResult:
        """Mix background music into a video only during specified time segments.

        Uses FFmpeg volume expressions with smooth fades at segment boundaries.
        Music is silent outside the specified segments.

        Input format:
            {
                "operation": "segmented_music",
                "video_path": "assembled.mp4",
                "music_path": "bg_music.mp3",
                "music_volume": 0.20,
                "segments": [
                    {"start": 0, "end": 17.0},
                    {"start": 167.0, "end": 175.0}
                ],
                "fade_duration": 0.5,
                "output_path": "final_with_music.mp4"
            }
        """
        video_path = inputs.get("video_path")
        music_path = inputs.get("music_path")
        output_path = Path(inputs.get("output_path", "segmented_music_output.mp4"))
        segments = inputs.get("segments", [])
        music_volume = inputs.get("music_volume", 0.20)
        fade_dur = inputs.get("fade_duration", 0.5)

        if not video_path or not Path(video_path).exists():
            return ToolResult(success=False, error=f"Video not found: {video_path}")
        if not music_path or not Path(music_path).exists():
            return ToolResult(success=False, error=f"Music not found: {music_path}")
        if not segments:
            return ToolResult(success=False, error="No segments specified")

        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Get video duration
        dur_cmd = [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "csv=p=0",
            video_path,
        ]
        total_dur = float(self.run_command(dur_cmd).stdout.strip().split("\n")[0])

        # Build volume expression for each segment with smooth fades
        parts = []
        for seg in sorted(segments, key=lambda s: s["start"]):
            s = seg["start"]
            e = seg["end"]
            fade_in_end = s + fade_dur
            fade_out_start = e - fade_dur
            parts.append(
                f"if(lt(t,{s}),0,"
                f"if(lt(t,{fade_in_end}),{music_volume}*(t-{s})/{fade_dur},"
                f"if(lt(t,{fade_out_start}),{music_volume},"
                f"if(lt(t,{e}),{music_volume}*({e}-t)/{fade_dur},"
                f"0))))"
            )

        vol_expr = "+".join(f"({p})" for p in parts) if len(parts) > 1 else parts[0]

        filter_complex = (
            f"[1:a]atrim=0:{total_dur},asetpts=PTS-STARTPTS,"
            f"volume='{vol_expr}':eval=frame[music_shaped];"
            f"[0:a]aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo[speech];"
            f"[music_shaped]aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo[music_fmt];"
            f"[speech][music_fmt]amix=inputs=2:duration=first:dropout_transition=2[aout]"
        )

        cmd = [
            "ffmpeg", "-y",
            "-i", video_path,
            "-stream_loop", "-1",
            "-i", music_path,
            "-filter_complex", filter_complex,
            "-map", "0:v",
            "-map", "[aout]",
            "-c:v", "copy",
            "-c:a", "aac", "-b:a", "192k",
            str(output_path),
        ]

        self.run_command(cmd)

        if not output_path.exists():
            return ToolResult(success=False, error="No output produced")

        return ToolResult(
            success=True,
            data={
                "operation": "segmented_music",
                "video": video_path,
                "music": music_path,
                "segments": segments,
                "music_volume": music_volume,
                "fade_duration": fade_dur,
                "output": str(output_path),
            },
            artifacts=[str(output_path)],
        )
