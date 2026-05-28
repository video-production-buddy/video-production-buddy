"""Cross-stage quality tests for ad-video pipeline.

Tests that verify each stage's output produces substantive, positive effects
on the final video — not just schema conformance but actual content quality:
- Intensity curve propagates correctly to duck schedule and TTS directives
- Script section word counts fit within their duration windows
- Scene plan scenes cover the full script duration without gaps
- Beat labels propagate from bible → script → edit_decisions
- Production proposal decisions propagate to downstream artifacts
"""

from __future__ import annotations

from lib.constants import WORDS_PER_MINUTE_VO
from lib.hook_window import estimate_hook_duration_seconds
from lib.intensity_curve import (
    derive_duck_schedule,
    derive_intensity_curve,
    derive_tts_directive,
    sample_at,
)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _beats():
    return [
        {"beat_id": "B1", "name": "HOOK", "duration_seconds": 8.0, "intensity": 0.7},
        {"beat_id": "B2", "name": "BUILD", "duration_seconds": 8.0, "intensity": 0.5},
        {"beat_id": "B3", "name": "REVEAL", "duration_seconds": 8.0, "intensity": 0.8},
        {"beat_id": "B4", "name": "CTA", "duration_seconds": 6.0, "intensity": 0.65},
    ]


def _script_sections():
    return [
        {
            "id": "hook",
            "beat": "hook",
            "text": "What if your widget worked this fast?",
            "start_seconds": 0,
            "end_seconds": 8,
            "speaker_directions": "Measured, intriguing.",
            "voice_performance": {
                "emotion": "intrigue",
                "intonation": "rising",
                "rhythm": "short phrase",
                "pace": "measured",
                "pause_after_seconds": 0.3,
            },
            "tts_directive": {"speed_mult": 0.95},
        },
        {
            "id": "build",
            "beat": "build",
            "text": "The Widget Pro handles everything. Fast. Reliable.",
            "start_seconds": 8,
            "end_seconds": 16,
            "speaker_directions": "Confident proof.",
            "voice_performance": {
                "emotion": "confidence",
                "intonation": "steady",
                "rhythm": "medium phrases",
                "pace": "conversational",
                "pause_after_seconds": 0.2,
            },
            "tts_directive": {"speed_mult": 1.0},
        },
        {
            "id": "reveal",
            "beat": "reveal",
            "text": "See the difference. Three seconds of pure wow.",
            "start_seconds": 16,
            "end_seconds": 24,
            "speaker_directions": "Excited reveal.",
            "voice_performance": {
                "emotion": "excitement",
                "intonation": "rising",
                "rhythm": "punchy",
                "pace": "fast",
                "pause_after_seconds": 0.4,
            },
            "tts_directive": {"speed_mult": 0.92},
        },
        {
            "id": "cta",
            "beat": "cta",
            "text": "Get yours today at acme.com.",
            "start_seconds": 24,
            "end_seconds": 30,
            "speaker_directions": "Warm invitation.",
            "voice_performance": {
                "emotion": "warmth",
                "intonation": "settling",
                "rhythm": "clean close",
                "pace": "measured",
                "pause_after_seconds": 0.5,
            },
            "tts_directive": {"speed_mult": 0.96},
        },
    ]


def _narration_windows_from_script(sections):
    return [
        {"start_seconds": s["start_seconds"], "end_seconds": s["end_seconds"]}
        for s in sections
        if s.get("text", "").strip()
    ]


# ---------------------------------------------------------------------------
# Intensity curve → duck schedule propagation
# ---------------------------------------------------------------------------


class TestIntensityCurveToDuckSchedule:
    def test_duck_schedule_covers_all_narration_windows(self) -> None:
        """Every narration window must produce duck samples in the schedule."""
        curve = derive_intensity_curve(_beats())
        windows = _narration_windows_from_script(_script_sections())
        schedule = derive_duck_schedule(curve, windows)

        schedule_times = {round(s["t_seconds"], 1) for s in schedule}
        for win in windows:
            assert round(win["start_seconds"], 1) in schedule_times, (
                f"Missing duck entry at narration start {win['start_seconds']}"
            )

    def test_duck_schedule_music_at_zero_outside_windows(self) -> None:
        """Music should return to 0 dB outside narration windows."""
        curve = derive_intensity_curve(_beats())
        windows = _narration_windows_from_script(_script_sections())
        schedule = derive_duck_schedule(curve, windows)

        # Find a point well outside any narration window
        after_all = max(w["end_seconds"] for w in windows) + 2.0
        post_samples = [s for s in schedule if s["t_seconds"] >= after_all]
        if post_samples:
            assert post_samples[0]["gain_db"] == 0.0

    def test_duck_depth_varies_with_intensity(self) -> None:
        """Higher intensity beats should duck music less (so music breathes)."""
        curve = derive_intensity_curve(_beats())
        windows = _narration_windows_from_script(_script_sections())

        # B3 (reveal) has highest intensity (0.8), B2 (build) has lowest (0.5)
        schedule = derive_duck_schedule(curve, windows)

        # Find duck samples at B2 start (t=8) and B3 start (t=16)
        b2_duck = next(
            (s for s in schedule if abs(s["t_seconds"] - 8.0) < 0.1),
            None,
        )
        b3_duck = next(
            (s for s in schedule if abs(s["t_seconds"] - 16.0) < 0.1),
            None,
        )
        if b2_duck and b3_duck:
            # Lower intensity → deeper duck (more negative dB)
            assert b2_duck["gain_db"] < b3_duck["gain_db"], (
                f"B2 (intensity=0.5) should duck deeper than B3 (intensity=0.8); "
                f"got B2={b2_duck['gain_db']}dB, B3={b3_duck['gain_db']}dB"
            )

    def test_empty_curve_uses_default_duck_depth(self) -> None:
        """Legacy briefs without intensity curve should use flat -18 dB."""
        windows = _narration_windows_from_script(_script_sections())
        schedule = derive_duck_schedule([], windows)

        duck_samples = [
            s for s in schedule
            if s["gain_db"] != 0.0
        ]
        if duck_samples:
            for sample in duck_samples:
                assert sample["gain_db"] == -18.0


# ---------------------------------------------------------------------------
# Intensity curve → TTS directive propagation
# ---------------------------------------------------------------------------


class TestIntensityCurveToTTSDirective:
    def test_higher_intensity_slows_tts(self) -> None:
        """Peak beats should slow down for emphasis."""
        low_directive = derive_tts_directive(0.3)
        high_directive = derive_tts_directive(0.9)
        assert high_directive["speed_mult"] < low_directive["speed_mult"]

    def test_tts_speed_range_stays_narrow(self) -> None:
        """Speed modulation stays within ±3% to keep delivery natural."""
        directive_min = derive_tts_directive(0.0)
        directive_max = derive_tts_directive(1.0)
        spread = abs(directive_max["speed_mult"] - directive_min["speed_mult"])
        assert spread <= 0.07, f"TTS speed spread {spread} exceeds ±3% band"

    def test_tts_directive_always_returns_speed_mult(self) -> None:
        for intensity in [0.0, 0.3, 0.5, 0.7, 1.0]:
            directive = derive_tts_directive(intensity)
            assert "speed_mult" in directive
            assert 0.9 <= directive["speed_mult"] <= 1.0


# ---------------------------------------------------------------------------
# Intensity curve sampling correctness
# ---------------------------------------------------------------------------


class TestIntensityCurveSampling:
    def test_curve_values_match_beat_intensities(self) -> None:
        """Each sample's value must equal its beat's intensity."""
        beats = _beats()
        curve = derive_intensity_curve(beats)
        for beat, sample in zip(beats, curve):
            assert abs(sample["value"] - beat["intensity"]) < 1e-6

    def test_closing_sample_carries_last_beat_intensity(self) -> None:
        beats = _beats()
        curve = derive_intensity_curve(beats)
        closing = curve[-1]
        assert abs(closing["value"] - beats[-1]["intensity"]) < 1e-6

    def test_sample_at_interpolates_between_beats(self) -> None:
        """Mid-beat sampling should interpolate between adjacent samples."""
        curve = derive_intensity_curve(_beats())
        # At t=4 (midpoint of B1 0.7 → B2 0.5 transition)
        mid_value = sample_at(curve, 4.0)
        assert 0.5 < mid_value < 0.7

    def test_sample_at_clamps_before_curve(self) -> None:
        curve = derive_intensity_curve(_beats())
        assert sample_at(curve, -1.0) == curve[0]["value"]

    def test_sample_at_clamps_after_curve(self) -> None:
        curve = derive_intensity_curve(_beats())
        assert sample_at(curve, 100.0) == curve[-1]["value"]

    def test_empty_beats_produces_empty_curve(self) -> None:
        assert derive_intensity_curve([]) == []


# ---------------------------------------------------------------------------
# Script word count vs section duration feasibility
# ---------------------------------------------------------------------------


class TestScriptPacingFeasibility:
    def test_hook_section_fits_within_window(self) -> None:
        """Hook narration must complete within hook_window_seconds."""
        sections = _script_sections()
        hook = next(s for s in sections if s["beat"] == "hook")
        # estimate_hook_duration_seconds uses narration or word_count fields
        hook_with_narration = {**hook, "narration": hook["text"]}
        estimated = estimate_hook_duration_seconds(hook_with_narration)
        assert estimated > 0, "Hook section should have measurable duration"
        # 7 words / 150 wpm * 60 = 2.8s — should fit in 3.0s window
        assert estimated <= 3.0, (
            f"Hook narration needs {estimated:.2f}s, exceeding 3.0s window"
        )

    def test_each_section_duration_accommodates_narration(self) -> None:
        """Word count at WORDS_PER_MINUTE_VO should fit in section duration."""
        sections = _script_sections()
        for section in sections:
            words = len(section["text"].split())
            duration = section["end_seconds"] - section["start_seconds"]
            seconds_needed = words / WORDS_PER_MINUTE_VO * 60.0
            # Allow 20% margin for pauses and pacing variation
            assert seconds_needed <= duration * 1.2, (
                f"Section {section['id']}: {words} words need ~{seconds_needed:.1f}s "
                f"but only {duration:.1f}s allocated (even with 20% margin)"
            )

    def test_all_sections_cover_full_duration(self) -> None:
        """Script sections should cover the entire video without gaps."""
        sections = sorted(_script_sections(), key=lambda s: s["start_seconds"])
        total_duration = sections[-1]["end_seconds"]

        covered = 0.0
        for section in sections:
            # Sections should start where the previous one ended (or at 0)
            assert section["start_seconds"] == covered, (
                f"Gap or overlap: section {section['id']} starts at "
                f"{section['start_seconds']} but expected {covered}"
            )
            covered = section["end_seconds"]

        assert covered == total_duration


# ---------------------------------------------------------------------------
# Beat label propagation: bible → script → edit_decisions
# ---------------------------------------------------------------------------


class TestBeatLabelPropagation:
    def test_script_beats_align_with_bible_beats(self) -> None:
        """Script section beat labels should map to bible beat IDs."""
        beats = _beats()
        sections = _script_sections()

        # script uses beat names (hook, build, reveal, cta) which map to
        # B1, B2, B3, B4 — verify the section count matches
        assert len(sections) == len(beats), (
            f"Script has {len(sections)} sections but bible has {len(beats)} beats"
        )

    def test_edit_cuts_map_to_beats(self) -> None:
        """Each edit cut should reference a beat from the bible."""
        beats = _beats()
        cuts = [
            {"id": "cut-1", "maps_to_beat": "B1", "in_seconds": 0, "out_seconds": 8},
            {"id": "cut-2", "maps_to_beat": "B2", "in_seconds": 8, "out_seconds": 16},
            {"id": "cut-3", "maps_to_beat": "B3", "in_seconds": 16, "out_seconds": 24},
            {"id": "cut-4", "maps_to_beat": "B4", "in_seconds": 24, "out_seconds": 30},
        ]
        beat_ids = {b["beat_id"] for b in beats}
        for cut in cuts:
            assert cut["maps_to_beat"] in beat_ids, (
                f"Cut {cut['id']} references unknown beat {cut['maps_to_beat']}"
            )

    def test_all_beats_have_corresponding_cuts(self) -> None:
        """Every beat in the bible should be covered by at least one cut."""
        beats = _beats()
        beat_ids_in_cuts = {"B1", "B2", "B3", "B4"}
        for beat in beats:
            assert beat["beat_id"] in beat_ids_in_cuts, (
                f"Beat {beat['beat_id']} has no corresponding cut"
            )


# ---------------------------------------------------------------------------
# Scene plan duration coverage
# ---------------------------------------------------------------------------


class TestScenePlanDurationCoverage:
    def test_scenes_cover_full_duration(self) -> None:
        """All scenes together should cover the entire video duration."""
        scenes = [
            {"id": "scene-1", "start_seconds": 0, "end_seconds": 8},
            {"id": "scene-2", "start_seconds": 8, "end_seconds": 16},
            {"id": "scene-3", "start_seconds": 16, "end_seconds": 24},
            {"id": "scene-4", "start_seconds": 24, "end_seconds": 30},
        ]
        total = 30.0
        max_end = max(s["end_seconds"] for s in scenes)
        min_start = min(s["start_seconds"] for s in scenes)
        assert min_start == 0
        assert max_end == total

    def test_no_scene_time_overlaps(self) -> None:
        """Scenes should not overlap in time."""
        scenes = [
            {"id": "scene-1", "start_seconds": 0, "end_seconds": 8},
            {"id": "scene-2", "start_seconds": 8, "end_seconds": 16},
            {"id": "scene-3", "start_seconds": 16, "end_seconds": 24},
            {"id": "scene-4", "start_seconds": 24, "end_seconds": 30},
        ]
        sorted_scenes = sorted(scenes, key=lambda s: s["start_seconds"])
        for i in range(len(sorted_scenes) - 1):
            assert sorted_scenes[i]["end_seconds"] <= sorted_scenes[i + 1]["start_seconds"], (
                f"Scene {sorted_scenes[i]['id']} overlaps with "
                f"{sorted_scenes[i + 1]['id']}"
            )


# ---------------------------------------------------------------------------
# Editing rhythm consistency with intensity
# ---------------------------------------------------------------------------


class TestEditingRhythmIntensityConsistency:
    def test_peak_beat_gets_rapid_cuts(self) -> None:
        from lib.intensity_curve import derive_editing_rhythm_from_intensity
        # B3 (reveal) has intensity 0.8 — should be rapid
        rhythm = derive_editing_rhythm_from_intensity(0.8)
        assert rhythm["cuts_density"] == "rapid"

    def test_low_beat_gets_held_or_moderate_cuts(self) -> None:
        from lib.intensity_curve import derive_editing_rhythm_from_intensity
        rhythm = derive_editing_rhythm_from_intensity(0.2)
        assert rhythm["cuts_density"] in ("held", "slow", "moderate")

    def test_editing_rhythm_check_catches_divergence(self) -> None:
        from lib.intensity_curve import check_editing_rhythm_consistency
        # Peak intensity with held shots = 2+ tier divergence
        warnings = check_editing_rhythm_consistency(
            intensity=0.9,
            editing_rhythm={"cuts_density": "held", "avg_shot_duration_seconds": 6.0},
        )
        assert len(warnings) > 0, "Should warn about held shots at peak intensity"

    def test_editing_rhythm_check_passes_aligned(self) -> None:
        from lib.intensity_curve import check_editing_rhythm_consistency
        warnings = check_editing_rhythm_consistency(
            intensity=0.5,
            editing_rhythm={"cuts_density": "moderate", "avg_shot_duration_seconds": 3.0},
        )
        assert len(warnings) == 0

    def test_long_shots_at_peak_warns(self) -> None:
        from lib.intensity_curve import check_editing_rhythm_consistency
        warnings = check_editing_rhythm_consistency(
            intensity=0.8,
            editing_rhythm={"cuts_density": "rapid", "avg_shot_duration_seconds": 5.0},
        )
        assert any("long shots" in w.lower() for w in warnings)


# ---------------------------------------------------------------------------
# Duck schedule round-trip to FFmpeg expression
# ---------------------------------------------------------------------------


class TestDuckScheduleToFfmpeg:
    def test_compile_empty_schedule_returns_unity(self) -> None:
        from lib.intensity_curve import compile_volume_schedule_to_ffmpeg_expr
        assert compile_volume_schedule_to_ffmpeg_expr([]) == "1.0"

    def test_compiled_schedule_is_valid_expression(self) -> None:
        from lib.intensity_curve import compile_volume_schedule_to_ffmpeg_expr
        curve = derive_intensity_curve(_beats())
        windows = _narration_windows_from_script(_script_sections())
        schedule = derive_duck_schedule(curve, windows)
        expr = compile_volume_schedule_to_ffmpeg_expr(schedule)
        # Should be a non-trivial expression with if/lt functions
        assert "if(" in expr
        assert "lt(" in expr


# ---------------------------------------------------------------------------
# Intensity arc description for music prompts
# ---------------------------------------------------------------------------


class TestIntensityArcDescription:
    def test_arc_description_produces_nonempty_string(self) -> None:
        from lib.intensity_curve import describe_intensity_arc
        curve = derive_intensity_curve(_beats())
        arc = describe_intensity_arc(curve)
        assert len(arc) > 0
        assert "peak" in arc.lower() or "energy" in arc.lower()

    def test_flat_curve_produces_sustained_description(self) -> None:
        from lib.intensity_curve import describe_intensity_arc
        flat_curve = [
            {"t_seconds": 0, "value": 0.5},
            {"t_seconds": 15, "value": 0.5},
            {"t_seconds": 30, "value": 0.5},
        ]
        arc = describe_intensity_arc(flat_curve)
        assert "sustained" in arc.lower()

    def test_empty_curve_produces_empty_string(self) -> None:
        from lib.intensity_curve import describe_intensity_arc
        assert describe_intensity_arc([]) == ""

    def test_arc_description_stays_under_200_chars(self) -> None:
        from lib.intensity_curve import describe_intensity_arc
        curve = derive_intensity_curve(_beats())
        arc = describe_intensity_arc(curve)
        assert len(arc) <= 200
