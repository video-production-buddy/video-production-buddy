# Asset Director — Ad Video Pipeline (Base)

## When to Use

You are the Asset Director (base). You receive `scene_plan`, `script`, `production_bible`, and `production_proposal` and generate all assets. You resolve the **Product Reference sub-stage first** when product-visible scenes exist, then run the sample sub-stage, await human approval, and proceed to full generation.

**Always read the mode supplement before generating visual assets:**
- `EP_STATE.style_mode == "animated"` → read `asset-director-animated.md`
- `EP_STATE.style_mode == "cinematic"` → read `asset-director-cinematic.md`

## Tool Call Pattern

All asset generation uses the tool registry — never construct raw shell commands or API calls manually. Import the tool class, call `.execute(inputs_dict)`, check `result.error` before proceeding. Never assume success.

## Pre-Asset Planning Chain Gate

Before generating narration, images, video, music, subtitles, or sample assets, run
`ad_video_planning_chain_check` with `production_bible`, `script`, and
`scene_plan`. If it fails, abort asset generation and send the exact issues back
to the responsible planning stage. This gate catches stale ad-video artifacts
where `truth_contract`, `trend_alignment`, or `knowledge_alignment` is missing,
or where selected trend / producer-knowledge guidance did not reach script
`source_ref/source_refs` and scene `trend_alignment_refs` /
`knowledge_alignment_refs`.

```python
from tools.validation.ad_video_planning_chain_check import AdVideoPlanningChainCheck

gate = AdVideoPlanningChainCheck().execute({
    "production_bible": production_bible,
    "script": script,
    "scene_plan": scene_plan,
})
if not gate.success:
    raise RuntimeError(f"Planning chain gate failed: {gate.error}")
```

Before handing assets to edit/compose, also run
`provider_consistency_check` with `production_proposal`, `asset_manifest`,
`script`, and `decision_log`. This blocks missing or unauditable narration
coverage, silent narration provider/model swaps, silent
image/video provider or model swaps against
`production_proposal.visual_contract.visual_asset_provider_locks`, no-music
proposal drift, music source drift for `library_locked` / `search_align` /
`generative_loose`, missing `music_alignment` evidence for strict
library/search music paths, and asset spend above
`production_proposal.approved_budget_usd` without an approved
`budget_tradeoff` whose selected option explicitly approves the overage, such
as `approve-overage`. If it fails, either regenerate with the locked
provider/model or surface the substitution/overage to the user and log a
visible approved `provider_selection`, `voice_selection`,
`music_strategy_selection`, or overage-approving `budget_tradeoff` decision
before continuing. If both provider and model change, the provider decision's
selected option must name the exact `source_tool:model` pair; a provider-only
selection does not authorize a model downgrade. A `music_source` decision alone
does not authorize switching from `library_locked` / `search_align` to a
different strategy family.

**Cost capture (use `result.cost_usd`, NOT hand-authored estimates):**

Every paid tool's `execute()` returns a `ToolResult` with a top-level `cost_usd: float` field (see `tools/base_tool.py` line 135 — this is part of the BaseTool contract, not inside `result.data`). Most paid tools populate it from `self.estimate_cost(inputs)` automatically; some can use real billing info from the API response when available.

Read `result.cost_usd` after every call and accumulate into `asset_manifest.costs[]`:

```python
# After every paid tool call, BEFORE moving to the next tool:
asset_manifest["costs"].append({
    "tool": tool.name,
    "cost_usd": result.cost_usd,  # Read from the ToolResult, NOT from a manual estimate
})
asset_manifest["total_cost_usd"] = sum(c["cost_usd"] for c in asset_manifest["costs"])
```

Anti-pattern: writing the cost dict with a hand-authored number ("`0.30` because that's roughly what a 3s clip costs"). The agent's intuition about API pricing is a poor substitute for the tool's own estimate. Free tools (Pexels, Pixabay, FFmpeg) report `cost_usd=0.0` which is also the correct manifest entry.

When `result.cost_usd == 0.0` on a tool you expected to be paid: log a `cost_capture_warning` in `asset_manifest.metadata` rather than guessing — that signals the tool's `estimate_cost` may be incomplete and prompts a follow-up audit.

```python
from tools.audio.cosyvoice_tts import CosyVoiceTTS
from tools.audio.openai_tts import OpenAITTS
from tools.audio.minimax_tts import MinimaxTTS
from tools.graphics.wanx_image import WanxImage
from tools.video.wan_video_api import WanVideoAPI
from tools.audio.minimax_music import MinimaxMusic
from tools.video.pexels_video import PexelsVideo

# TTS narration — one call per script section.
# Path A: when script-director sets section["tts_directive"], the speed
# multiplier per section is derived from the bible's beat intensity. Quieter
# build sections pace slightly faster; peak sections slow down for emphasis.
# Legacy briefs without tts_directive use the historical 0.95 baseline.
speed = section.get("tts_directive", {}).get("speed_mult", 0.95)
audio_contract = production_proposal["audio_contract"]
voice_provider = audio_contract["voice_provider"]
model = audio_contract["voice_model"]
section_performance = section.get("voice_performance", {})
performance_parts = [
    f"Overall tone: {audio_contract['voice_performance']['tone']}",
    f"Baseline emotion: {audio_contract['voice_performance']['baseline_emotion']}",
    f"Section emotion: {section_performance.get('emotion', audio_contract['voice_performance']['baseline_emotion'])}",
    f"Intonation: {section_performance.get('intonation', audio_contract['voice_performance']['intonation'])}",
    f"Rhythm: {section_performance.get('rhythm', audio_contract['voice_performance']['rhythm'])}",
    f"Pause policy: {section_performance.get('pause_after_seconds', 0)}s after this section; {audio_contract['voice_performance']['pause_policy']}",
    section.get("speaker_directions", ""),
]
instructions = " ".join(part for part in performance_parts if part)

if voice_provider == "qwen3":
    tts = CosyVoiceTTS()
    result = tts.execute({
        "text": section["text"],
        "voice": audio_contract["voice_id"],  # e.g. "Ethan"
        "model": model,
        "language_type": "English",
        "speed": speed,
        "instructions": instructions,
        "format": "mp3",
        "output_path": f"projects/<project-name>/assets/audio/{section['id']}_narration.mp3",
    })
elif voice_provider == "openai":
    tts = OpenAITTS()
    result = tts.execute({
        "text": section["text"],
        "voice": audio_contract["voice_id"],  # e.g. "alloy"
        "model": model,
        "speed": speed,
        "instructions": instructions,
        "format": "mp3",
        "output_path": f"projects/<project-name>/assets/audio/{section['id']}_narration.mp3",
    })
elif voice_provider == "minimax":
    # MiniMax speech-2.8-hd is NOT free-form-instruction-capable; delivery is
    # controlled via voice_id choice + pitch + speed. Use this branch when
    # qwen3 male voices render feminine in Mandarin and OpenAI is unavailable
    # (user-approved provider substitution — see decision_log voice_selection).
    # Records source_tool="minimax_tts" in the narration asset entry.
    tts = MinimaxTTS()
    pitch = section.get("tts_directive", {}).get("pitch", -2)
    result = tts.execute({
        "text": section["text"],
        "voice": audio_contract["voice_id"],  # e.g. "male-qn-badao"
        "model": model,  # speech-2.8-hd
        "speed": speed,
        "pitch": pitch,
        "format": "mp3",
        "output_path": f"projects/<project-name>/assets/audio/{section['id']}_narration.mp3",
    })
else:
    raise RuntimeError(f"Unsupported instruction-capable TTS provider: {voice_provider}")
if result.error:
    # STOP — do not silently fall back to another provider.
    # Surface to user per the Provider Swap Emergency Rule in proposal-director.md.
    raise RuntimeError(f"TTS failed for {section['id']}: {result.error}")

# Bible-derived prompt suffixes — applied to every visual prompt (image and
# video) so the generation lands on-brief instead of using model defaults.
# All helpers return the prompt unchanged when the bible field is unset
# (legacy briefs).
from lib.color_direction import apply_color_direction
from lib.resolution_treatment import apply_resolution_treatment
from lib.emotional_prompt import apply_emotional_mood, apply_alignment_notes, find_beat_for_scene

color_direction = production_bible["visual"].get("color_direction")
resolution_type = production_bible["narrative"].get("resolution_type")
beat_sequence = production_bible["narrative"].get("emotional_beat_sequence", [])

# Identify whether this scene maps to the resolution beat. The resolution
# beat is the highest-intensity beat before cta_brand — its beat_id varies
# by arc_type ("resolution"|"fulfillment"|"after"|"triumph"|"product_reveal"|
# "payoff"). Look up the bible's emotional_beat_sequence: the beat whose
# intensity is the maximum among non-cta beats is the resolution.
# Filter ONLY by beat_id (the authoritative identifier). Substring matching
# on the free-form `name` field would falsely exclude beats whose name
# happens to contain "cta" as a substring.
non_cta = [b for b in beat_sequence if b.get("beat_id") != "cta_brand"]
resolution_beat_id = max(non_cta, key=lambda b: b["intensity"])["beat_id"] if non_cta else None
is_resolution_scene = (scene.get("beat_id") == resolution_beat_id) or (scene.get("beat") == resolution_beat_id)

# Look up the emotional beat for this scene so the mood suffix is scene-specific.
scene_beat = find_beat_for_scene(beat_sequence, scene)


# Use default-arg capture so this helper carries the per-iteration value of
# `is_resolution_scene` and `scene_beat` even if the snippet is later
# refactored to define `_wrap` outside the per-scene loop. Without the
# default-arg trick a closure would capture the loop variable's *final*
# value for every scene.
def _wrap(prompt: str, *, _is_resolution=is_resolution_scene, _beat=scene_beat, _scene=scene) -> str:
    """Apply color_direction, emotional mood, visual constraint, and alignment
    notes to every scene; apply resolution_treatment only on the resolution-beat
    scene so the emotional register doesn't leak into other beats' generation."""
    out = apply_color_direction(prompt, color_direction)
    out = apply_emotional_mood(out, _beat)
    out = apply_alignment_notes(out, _scene)
    if _is_resolution:
        out = apply_resolution_treatment(out, resolution_type)
    return out


# Still image — one call per non-motion scene
img = WanxImage()
img_prompt = f"{playbook['asset_generation']['image_prompt_prefix']} {scene_description}"
result = img.execute({
    "prompt": _wrap(img_prompt),
    "negative_prompt": playbook["asset_generation"]["image_negative_prompt"],
    "size": "1920*1080",
    "model": "wan2.7-image-pro",
    "output_path": f"projects/<project-name>/assets/images/{scene_id}_img.png",
})
if result.error:
    raise RuntimeError(f"Image gen failed for {scene_id}: {result.error}")

# Video clip — one call per motion_required scene
vid = WanVideoAPI()
result = vid.execute({
    "prompt": _wrap(scene_prompt),
    "negative_prompt": playbook["asset_generation"]["image_negative_prompt"],
    "operation": "text_to_video",
    "model_variant": "wan2.6-t2v",
    "duration": str(int(scene["duration_seconds"])),
    "resolution": "1080P",
    "output_path": f"projects/<project-name>/assets/video/{scene_id}_video.mp4",
})
if result.error:
    raise RuntimeError(f"Video gen failed for {scene_id}: {result.error}")

# Stock video — free, for generic establishing shots where AI gen is unnecessary
stock = PexelsVideo()
result = stock.execute({
    "query": "city summer heat haze skyline",
    "orientation": "landscape",
    "size": "large",
    "preferred_quality": "hd",
    "output_path": f"projects/<project-name>/assets/video/{scene_id}_stock.mp4",
})

# Music — one call for the full track
music = MinimaxMusic()
result = music.execute({
    "prompt": playbook["audio"]["music_mood"],
    "is_instrumental": True,
    "model": "music-2.6",
    "format": "mp3",
    "sample_rate": 44100,
    "output_path": "projects/<project-name>/assets/music/background_music.mp3",
})
if result.error:
    raise RuntimeError(f"Music gen failed: {result.error}")
```

**Stills fallback rule:** If WanVideoAPI fails for a lifestyle/product/environmental scene, retry once with a simplified prompt, then fall back to PexelsVideo stock — **never** substitute a WanxImage still for a scene that should be moving. A still image lasting more than ~1 second in a commercial is always wrong. If stock has no suitable clip, log it and skip the scene rather than insert a still.

**Provider failure rule:** If any tool returns an error (401 Unauthorized, 429 Too Many Requests, quota exceeded): STOP. Do NOT fall back to a different provider silently. Surface to user with the exact error and the proposed alternative. Wait for explicit approval before retrying with a different provider. Log the swap as a `provider_selection` decision in `decision_log` with `user_approved: true`.

## Required Assets (Non-Negotiable)

These are REQUIRED for ALL style modes and ALL ads:

1. **TTS narration audio** — one audio file per `script.sections[]` item
   - Provider/model: follow `production_proposal.audio_contract` exactly. Do not default to ElevenLabs; current governed ad narration commonly uses `cosyvoice_tts` with `qwen3-tts-instruct-flash` when section-level delivery instructions must be honored.
   - Format: MP3 or WAV, 44.1 kHz
   - Voice style: `EP_STATE.playbook.audio.voice_style`
   - Hero moment variation: apply `playbook.audio.hero_moment_voice_shift` on `cta_brand` section

Subtitles are conditional on `production_proposal.subtitles.mode`; see Step 3.
Missing required narration is a CRITICAL failure. Abort and alert the EP.

## Product Reference Sub-Stage (Before Sample)

Run this before any product-visible visual generation, including sample clips.

Use `genui_interaction` by default for this G5 sub-gate when the local browser
path is available. It should decide that linear chat is not sufficient when the
round includes media review, visual demonstration, reference comparison, or a
risk waiver, then delegate to `genui_session`. Generate a project-specific
`ui_session_config` that displays product-reference strategy, provided reference
paths or generated candidate paths, risk waiver text when applicable, and
approve/revise/abort actions. After submission, read and validate
`ui_session_response`, summarize the selected reference or waiver, and only then write
`product_identity_reference` and any `decision_log` entry. The GenUI path must
not write canonical artifacts directly: it must not write
`product_identity_reference`, `asset_manifest`, `decision_log`, or checkpoints.
Use media items for provided or generated reference images. Safe project-relative
paths under `reference_assets/` or `assets/` are acceptable in the
`interaction_request`; `genui_interaction`/`genui_session` materialize them to
`/media/...` so the user reviews the references inline in the browser.

CLI fallback: use it only when `genui_session` execution fails or the user
explicitly declines the browser path. A returned localhost URL counts as
browser path available; paste the URL and wait for `response_path` validation
instead of switching to CLI.

1. Read `production_proposal.product_reference_strategy`.
2. Read `scene_plan.scenes[].product_visibility` and `product_reference_required`.
3. If no scene is product-visible, write `product_identity_reference` with
   `source_type: "not_applicable"` and `approval_status: "not_required"`.
4. If `use_provided_reference`, validate the selected
   `projects/<project>/reference_assets/product_*.png|jpg` path and write it to
   `product_identity_reference.selected_reference_image_path`.
5. If `generate_concept_reference`, generate 2-4 concept reference candidates,
   include each candidate as a GenUI `media_items[]` entry, serve the browser
   session, and wait for explicit approval of one candidate in
   `ui_session_response`. Do not generate product-visible video until
   `product_identity_reference.approval_status == "approved"`.
6. If `risk_accepted`, stop until the user explicitly approves the fidelity-risk waiver.
   Record `risk_waiver.user_approved: true`.

Log the strategy as a `product_identity_reference_selection` decision. For product-visible
generated assets:

- Prefer `reference_to_video` when the provider supports identity references.
- Otherwise create a scene keyframe constrained by the approved Product Identity Reference,
  then animate it with image-to-video and record `scene_keyframe_to_video`.
- Use `text_only_waived` only when the approved strategy is `risk_accepted`.
- Treat the approved reference as identity/geometry guidance, not production
  footage. Do not paste the reference bitmap directly into the sample or final
  video as the visible product unless the user explicitly approved a static
  packshot treatment for that exact shot.
- Deterministic Remotion product scenes are the exception only when the scene
  contract explicitly carries `productImage` (for example
  `creator_workflow_scene` or a product-visible `brand_card`). In that case,
  pass the approved reference path through; do not substitute synthetic generic
  hardware.

Before sample approval and again before asset review, run:
- `product_identity_consistency_check` against `product_identity_reference`, `scene_plan`,
  and `asset_manifest`
- `hallucination_contract_check` against `production_bible`, `scene_plan`,
  `asset_manifest`, and `decision_log`

For the sample approval gate, pass the selected sample scene ids as
`generated_scene_ids` to both `product_identity_consistency_check` and `hallucination_contract_check`.
The sample `asset_manifest` intentionally contains only selected/generated
scene assets, so missing visual assets for later product-visible or high-risk
generated scenes are deferred to the full asset review. For full asset review,
omit `generated_scene_ids` so every product-visible and high-risk generated
scene must have its visual asset and review metadata.

A FAIL blocks progress. A WARN must be shown during asset review.

## Sample Sub-Stage (Always Runs)

The sample sub-stage generates a preview clip from the **first 2–3 scenes** before full asset generation proceeds. If any selected sample scene is product-visible, the Product Reference sub-stage must already be approved or waived.

### Sample Generation Protocol

1. Generate assets for scenes 1–3 only (or first 2 if scenes are long)
2. Generate TTS for the hook section only
3. Assemble the sample clip using compose tools (10–15 second target)
**Sample scene selection rule:** The sample MUST include at least one scene where the advertised product is visible — even if the creative concept hides the product until a late-stage reveal. If the first 2 chronological scenes contain no product, build the sample as a teaser cut instead: pick one early life-moment scene + one product-visible scene + the tagline/end card. This gives the user enough context to evaluate the concept and the product fit.
Before assembling the sample, run `sample_product_visibility_check` with the selected sample scene ids. A FAIL blocks assembly; a WARN must be shown with the sample review context. Product keywords inside negated wording such as "do not reveal the product yet" or "keep the phone hidden" are not visibility evidence; select a scene that visibly shows the product or a brand-mandatory element.

4. **GenUI v7 sample review workspace (default path):**

Sample approval is a visual media gate. Use `genui_interaction` by default and
serve a GenUI v7 session before any full-generation run.

Build an `interaction_request` that produces a `ui_session_config` with:

- `MediaCompare` showing `renders/sample_preview.mp4` and any product-visible
  stills used to judge the sample.
- `RevisionPatch` fields bound to `asset_manifest.human_feedback.sample.*` for
  visual, product-fit, pacing, narration, and scene-selection feedback.
- `ApprovalChecklist` requiring the user to confirm they watched the actual
  video, the sample includes a product-visible moment, and the direction is
  acceptable for full generation.
- `ArtifactTracePanel` linking back to `scene_plan`, `script`,
  `sample_product_visibility_check`, and the sample render artifact.

Use media item paths such as `renders/sample_preview.mp4`,
`assets/video/<scene>.mp4`, `assets/images/<scene>.png`, and approved product
reference images. The GenUI tools materialize those project-relative paths to
`/media/...` and render the sample video/keyframes inline. If the sample clip is
missing or no reviewable media remains after materialization, stop and surface
the missing output instead of asking the user to inspect folders manually.

Wait for `ui_session_response`. Validate and summarize it before setting
`EP_STATE.sample_approved = true` or returning revision feedback to the EP.

CLI fallback is allowed only when `genui_session execution fails` or the user
explicitly declines the browser path. A returned localhost URL counts as browser
path available. In fallback, mirror the same MediaCompare, RevisionPatch,
ApprovalChecklist, and trace fields in compact CLI form.

Fallback CLI path:

**Message 1 — announce the file path without launching anything:**

> "Sample preview is available at: `renders/sample_preview.mp4`
> I will not open or play it automatically. Review it in your preferred method when convenient; then reply **Approve** to proceed to full generation, or **Reject: [feedback]** to adjust the approach before I generate any more assets."

   Do NOT describe what is in the clip. Do NOT ask the user to open folders or launch a player. The user controls whether and when to review the actual video.

If **approved**: set `EP_STATE.sample_approved = true`. Proceed to full generation.
If **rejected**: set `EP_STATE.sample_approved = false`. Return the user's feedback to the EP.
   - EP will determine whether to send back to `scene_plan` (visual issue) or `script` (content issue).

**The EP gates all further work on `sample_approved == true`.**

## Full Generation Protocol

After sample approval, generate all remaining assets:

### Step 1: TTS Narration (Complete)
For each `script.sections[]` item not yet generated, call `CosyVoiceTTS().execute(…)` (see Tool Call Pattern above):
- Use voice from `production_proposal.audio_contract.voice_id`
- Use model from `production_proposal.audio_contract.voice_model`
- Pass the combined `speaker_directions` + `voice_performance` instructions to the TTS tool
- For Qwen/DashScope, use `qwen3-tts-instruct-flash` whenever instructions are non-empty; never accept a run where instructions were ignored by `qwen3-tts-flash`
- Apply `playbook.audio.hero_moment_voice_shift` instruction on `cta_brand` section
- Store output at `assets/audio/{section_id}_narration.mp3`
- After each call: record actual duration. Prefer `result.duration_seconds` if present; if absent, probe via `ffprobe -show_entries format=duration` on the output file. Record in `asset_manifest.narration_durations`.

### Step 2: Visual Assets
Delegate to mode supplement for all visual asset generation (images, video clips). The supplement specifies per-scene-type which tool class to use (`WanxImage` for stills, `WanVideoAPI` for motion clips, `PexelsVideo` for free stock). All calls follow the Tool Call Pattern above.

### Step 3: Subtitle File
Read `production_proposal.subtitles.mode` before generating anything.

- If `production_proposal.subtitles.mode == "off"`, do not generate a subtitle
  file, do not add subtitle assets to `asset_manifest`, and carry the no-subtitle
  choice forward so edit/compose keep subtitles disabled.
- If `production_proposal.subtitles.mode != "off"`, generate an ASS subtitle file
  from actual TTS durations.
  - Format: ASS with explicit PlayResX/PlayResY matching the output resolution
  - Timecodes must align to TTS audio files (use actual TTS durations)
  - Must be legible at 720p on mobile (minimum 24px equivalent)

**CRITICAL: Generate ASS format, NOT SRT.** When ffmpeg's `subtitles=` filter renders an SRT file, it uses libass's internal default resolution (~384×288) to interpret font sizes and margins, making them scale up massively and appear at wrong positions. An ASS file with explicit `PlayResX`/`PlayResY` headers forces exact pixel-level sizing.

Generate a `.ass` file with headers matching the video resolution:

```python
def build_ass(cues, video_w, video_h, font_size, margin_v):
    """cues: list of (start_secs, end_secs, text_with_\N_for_linebreaks)"""
    def ts(s):
        h, r = divmod(s, 3600); m, r = divmod(r, 60)
        return f"{int(h)}:{int(m):02d}:{r:05.2f}"
    lines = [
        "[Script Info]",
        "ScriptType: v4.00+",
        f"PlayResX: {video_w}",
        f"PlayResY: {video_h}",
        "WrapStyle: 0",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        f"Style: Default,DejaVu Sans,{font_size},&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,1,1,2,10,10,{margin_v},1",
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    for start, end, text in cues:
        lines.append(f"Dialogue: 0,{ts(start)},{ts(end)},Default,,0,0,0,,{text}")
    return "\n".join(lines)

# 16:9 (1920x1080): Fontsize=20, MarginV=20
# 9:16 (1080x1920): Fontsize=24, MarginV=160
video_w = 1080 if primary_is_9x16 else 1920
video_h = 1920 if primary_is_9x16 else 1080
font_size = 28 if primary_is_9x16 else 24
margin_v = 160 if primary_is_9x16 else 20

ass_content = build_ass(narration_cues, video_w, video_h, font_size, margin_v)
Path("assets/subtitles.ass").write_text(ass_content, encoding="utf-8")
```

When subtitles are enabled, store: `subtitles.ass` (not `subtitles.srt`). Pass
this path to `video_compose` as `subtitle_path`.

### Step 4: Music

**Music Strategy Branch (read FIRST):**

Read `production_proposal.music_strategy` (default `generative_loose` if unset for legacy briefs):

| Strategy | Path | Use when |
|---|---|---|
| `generative_loose` | MiniMax / Suno text-to-music with arc-shaped prompt (current default behavior — see snippet below) | Atmospheric ads where ±2-5s drift on bass-drop timing is acceptable |
| `library_locked` | Pick a track from `music_library/` whose `<track>.timing.json` sidecar declares `drop_seconds` close to `production_bible.narrative.tension_peak_at_seconds`. Validate the sidecar against `schemas/music_library/track_timing.schema.json`. Trim/pad the track so the chosen drop lands at the target time. | Bar-precise sync required (cinematic trailers, hero product reveals where the bass drop must hit a visual peak within ±0.5s) |
| `search_align` | Search `pixabay_music` for a track matching `bible.audio.music_direction`, run beat detection with `lib.beat_detector`, align the detected drop to `tension_peak_at_seconds`. | Bar-precise sync needed but no curated library track fits |
| `none` | Skip music entirely. Final mix = narration + ambient SFX only. | Brief explicitly calls for silent or SFX-only audio bed |

**library_locked workflow:**

```python
import json
from pathlib import Path
import jsonschema

ml = Path("music_library")
target_drop = production_bible["narrative"]["tension_peak_at_seconds"]

candidates = []
for sidecar in ml.glob("*.timing.json"):
    sidecar_schema = json.load(open("schemas/music_library/track_timing.schema.json"))
    timing = json.load(open(sidecar))
    jsonschema.validate(timing, sidecar_schema)  # refuse malformed sidecars
    track_path = ml / timing["track_file"]
    if not track_path.exists():
        continue  # sidecar references a missing file
    if timing["duration_seconds"] < scene_plan["total_duration_seconds"]:
        continue  # too short, can't cover the ad
    if timing.get("license") == "personal-only":
        continue  # license forbids ad use
    drops = timing.get("drop_seconds", [])
    if not drops:
        continue  # no declared drop — useless for library_locked
    nearest_drop = min(drops, key=lambda d: abs(d - target_drop))
    distance = abs(nearest_drop - target_drop)
    candidates.append({
        "track": track_path,
        "timing": timing,
        "nearest_drop": nearest_drop,
        "distance": distance,
    })

if not candidates:
    raise RuntimeError(
        f"music_strategy=library_locked requires at least one music_library/ track "
        f"with a valid <track>.timing.json declaring drop_seconds. None found. "
        f"Options: (a) drop a track + sidecar into music_library/, "
        f"(b) switch music_strategy to generative_loose with documented drift risk, "
        f"(c) switch to search_align."
    )

# Pick the best candidate (closest drop, then preferring matching arc_shape).
chosen = min(candidates, key=lambda c: c["distance"])
# Trim/pad so chosen.nearest_drop lands at target_drop in the final mix.
# (See compose-director for the audio-mixer call that does the alignment.)
```

After trimming/padding a `library_locked` track, the `music` asset in
`asset_manifest.assets[]` MUST include `music_alignment`:

```json
{
  "strategy": "library_locked",
  "target_peak_seconds": 18.0,
  "selected_peak_seconds": 30.0,
  "aligned_peak_seconds": 18.2,
  "drift_seconds": 0.2,
  "timing_sidecar_path": "music_library/background.timing.json",
  "evidence": "Validated timing sidecar and trimmed track to target."
}
```

For `search_align`, call `lib.beat_detector.analyze(track_path)`, choose the
detected `drop_seconds[]` entry nearest `target_drop`, trim/pad the track, and
record the same timing fields plus either `beat_detection_report` (inline) or
`beat_detection_report_path`. `provider_consistency_check` blocks compose when
`library_locked` / `search_align` music lacks this evidence or has
`abs(drift_seconds) > 0.5`.

**generative_loose workflow** (default — the existing MiniMax path):

Generate or select background music:
- Duration: match total video duration
- Mood: `EP_STATE.playbook.audio.music_mood`
- At CTA beat: music rises to full volume (ducking lifted)
- Store: `background_music.mp3`

**Path B — emotion-aware arc prompting.** When
`production_bible.narrative.intensity_curve` is present, prepend an arc summary
to the MiniMax prompt so the generated track climbs and resolves with the
emotional contour. The duck schedule (set by edit-director) carries the
rhythm even when MiniMax misses timestamps, so this is reinforcement, not
the sole signal.

```python
from lib.intensity_curve import describe_intensity_arc
from lib.av_sync import apply_av_sync_notes

curve = production_bible["narrative"].get("intensity_curve", [])
arc = describe_intensity_arc(curve)  # "" when absent

base_mood = playbook["audio"]["music_mood"]
prompt = f"{base_mood}. Arc: {arc}." if arc else base_mood

# Bible's audio.av_sync_notes (free-form prose like "Music swell on B3
# solution reveal") is appended last so prompt-conditioned music models
# can attempt the sync at generation time. Pass-through when notes unset.
av_sync_notes = production_bible.get("audio", {}).get("av_sync_notes")
prompt = apply_av_sync_notes(prompt, av_sync_notes)

music = MinimaxMusic()
result = music.execute({
    "prompt": prompt,
    "is_instrumental": True,
    "model": "music-2.6",
    "format": "mp3",
    "sample_rate": 44100,
    "output_path": "projects/<project-name>/assets/music/background_music.mp3",
})
```

The helpers are deterministic; do not hand-author the arc or sync strings.
Empty intensity_curve → empty arc → falls back to the legacy mood-only
prompt. Empty av_sync_notes → no suffix appended. No behavior change for
legacy briefs without these fields.

### Step 4.5: Agent Hallucination Review (REQUIRED before sample approval and asset review)

**Purpose:** catch objective-fact, physical-plausibility, product-geometry, motion-coherence,
and values/safety failures BEFORE they reach sample approval, asset_review, compose, or
publish. The user's review should be about creative judgment ("does the Hasselblad color
sing?"), not about catching known blocker hallucinations the agent should have flagged.

**Workflow:**

1. For each generated video clip in `asset_manifest.assets[]` linked to a scene with
   `hallucination_checks[]`, extract 3 keyframes (start / middle / end) using the
   existing `frame_sampler` tool before sample approval and again before full asset review:

   ```python
   from tools.analysis.frame_sampler import FrameSampler
   from pathlib import Path

   sampler = FrameSampler()
   high_risk_scene_ids = {
       s["id"]
       for s in scene_plan["scenes"]
       if s.get("hallucination_checks")
   }
   for asset in [
       a for a in asset_manifest["assets"]
       if a["type"] == "video" and a.get("scene_id") in high_risk_scene_ids
   ]:
       scene_id = asset["scene_id"]
       duration = asset.get("duration_seconds", 5)
       output_dir = Path("projects") / project_id / "assets" / "keyframes" / scene_id
       output_dir.mkdir(parents=True, exist_ok=True)

       result = sampler.execute({
           "input_path": asset["path"],
           "strategy": "timestamps",
           "timestamps": [0.5, duration / 2, max(0.5, duration - 0.5)],
           "output_dir": str(output_dir),
       })
       if not result.success:
           # Frame extraction failures are non-blocking — flag and continue
           continue
   ```

2. Read each keyframe PNG and evaluate every
   `scene_plan.scenes[].hallucination_checks[]` entry for that scene:

   | Check | What it catches |
   |---|---|
   | Objective facts | Wrong product/model, invented claim, wrong CTA, wrong app/service name |
   | Physical plausibility | Six-finger hands, impossible bend/deformation, unsupported floating objects |
   | Product geometry | Wan generated a generic phone instead of the OPPO/Hasselblad reference; the orange dot is missing; the device isn't in frame at all |
   | Motion coherence | Product teleports between start/mid/end keyframes; hand pose or UI state jumps impossibly |
   | Values/safety | Unsafe use depiction, unapproved competitor/medical/superiority claim |
   | Aspect ratio correct? | Tool defaulted to landscape when 9:16 was required (the wan2.6-t2v + resolution-preset trap) |
   | Real-light continuity intact? | Greenscreen seam visible; floating-product compositing fingerprint |
   | Color science on-brief? | Hasselblad-Natural-Color was specified but the output is over-saturated or blown out |

3. For each generated visual asset, record `asset_manifest.assets[].hallucination_review`:

   ```json
   {
     "status": "PASS",
     "keyframe_paths": [
       "projects/<project-id>/assets/keyframes/scene-1/start.png",
       "projects/<project-id>/assets/keyframes/scene-1/mid.png",
       "projects/<project-id>/assets/keyframes/scene-1/end.png"
     ],
     "check_verdicts": [
       {
         "check_id": "HC-GEO-1",
         "category": "product_geometry",
         "status": "PASS",
         "severity": "blocker",
         "notes": "Camera island and brand mark match the approved reference in all three frames."
       }
     ],
     "reviewer": {
       "type": "agent",
       "reviewed_at": "2026-05-19T09:00:00Z",
       "method": "start_mid_end_keyframe_review"
     }
   }
   ```

4. Run `hallucination_contract_check`:

   ```python
   from tools.validation.hallucination_contract_check import check_hallucination_contract

   verdict = check_hallucination_contract(
       production_bible,
       scene_plan,
       asset_manifest,
       decision_log,
       generated_scene_ids=selected_sample_scene_ids,  # sample gate only; omit for full asset review
   )
   ```

   - `FAIL` blocks sample approval, asset_review, compose, and publish.
   - `FLAG` on any blocker check requires regeneration or rerouting, not silent acceptance.
   - `WARN` can pass through to human asset review with the keyframe paths and notes.
   - `WAIVED` requires an explicit user-approved `decision_log` entry with category
     `hallucination_review_waiver` whose selected waiver option was present in
     `options_considered`; otherwise it fails validation.

5. **Skip rule:** if frame_sampler is unavailable (ffmpeg missing) OR the agent's runtime
   cannot read PNGs (no multimodal capability), stop and surface the limitation. Do not
   mark generated high-risk assets as PASS. Either reroute to stock/programmatic assets,
   ask the user for a waiver, or record `hallucination_review.status="WAIVED"` with a
   user-approved `hallucination_review_waiver` decision that includes the selected
   waiver option in `options_considered`.

**Why this matters:** Wan 2.6 t2v has no reliable mechanism to render specific brand
product geometry from prose alone — it generates plausible-looking generic objects.
Prompt improvements help, but they are not sufficient mitigation. The pipeline must
prevent bad prompts through `truth_contract`, route high-risk visuals away from raw
text-to-video when possible, and block compose/publish until keyframe review is recorded.

### Step 5: Asset Review Gate (REQUIRED before compose)

After all visual assets are generated, present them to the user for review in a
GenUI media review room.

Use `genui_interaction` by default for asset review when the local browser path
is available. It should decide that linear chat is not sufficient because the
round requires media review, visual demonstration, and structured flag capture,
then delegate to `genui_session`. Generate a project-specific `ui_session_config`
that includes every reviewable image/video path, generated concept image,
sample clip, product reference candidate, keyframe review image, hallucination
WARN/FLAG note, and approve/flag action per scene. Include media items from
`asset_manifest.assets[].path`, `asset_manifest.sample_clip`,
`asset_manifest.assets[].hallucination_review.keyframe_paths[]`, and any
approved product reference. The GenUI tools materialize those project-relative
paths to `/media/...`, and the browser must show the assets inline instead of
requiring the user to open folders.

If the request omits `media_items`, `genui_session` auto-populates review media
from `asset_manifest`, `product_identity_reference`, `render_report`, and
`final_review`. If no reviewable media is found, treat that as a blocking asset
stage defect and repair the manifest or generation outputs before requesting
approval.

After submission, read and validate `ui_session_response`, summarize flagged
assets or approval, and only then update `asset_manifest` review state. The
GenUI path must not write canonical artifacts directly.

Manual folder opening is fallback only: use it only when `genui_session
execution fails` or the user explicitly declines the browser path. A returned
localhost URL counts as browser path available. In fallback, mirror the same
MediaReviewRoom, per-scene media list, keyframe evidence, RevisionPatch,
ApprovalChecklist, and trace fields in compact CLI form. If any asset is
flagged, regenerate the specified asset, re-present that updated asset in GenUI,
and wait for approval before proceeding.

### Step 6: Music Review Gate (required when music is approved)

If the effective `production_proposal.music_strategy` is `"none"` and no visible
approved `music_strategy_selection` decision opts into another strategy, do not
generate music, do not create `asset_manifest.music_file` or a music asset, and
do not set `music_review_approved`. In that no-music case, the completed assets
checkpoint and `genui_evidence_check` skip `music_review`.

When music is generated, present it for approval. This is an audio review gate,
so use `genui_interaction` by default and serve a GenUI v7 session. If the user
later approves a `music_strategy_selection` change away from `"none"`, run this
gate before compose.

Build an `interaction_request` that produces a `ui_session_config` with:

- `MusicReview` for `assets/music/background_music.mp3`, duration, provider,
  prompt summary, mood target, and intensity alignment.
- `RevisionPatch` fields bound to `asset_manifest.human_feedback.music.*` for
  mood, instrumentation, pacing, loop, or replacement feedback.
- `ApprovalChecklist` requiring explicit confirmation that the user listened to
  the track and approves its use in compose.
- `ArtifactTracePanel` linking back to `production_proposal`, `script`,
  `scene_plan`, and the generated music artifact.

Wait for `ui_session_response`. Validate and summarize it before setting
`music_review_approved`. CLI fallback is allowed only when `genui_session
execution fails` or the user explicitly declines the browser path. A returned
localhost URL counts as browser path available. In fallback, mirror the same
MusicReview, RevisionPatch, ApprovalChecklist, and trace fields in compact CLI
form.

The music media item should use `assets/music/background_music.mp3`; the GenUI
tools materialize it to `/media/assets/music/background_music.mp3` and render an
inline audio control. Do not ask the user to manually open the music folder
unless the browser path fails or the user declines it.

Fallback CLI path: two messages.

**Message 1 — announce music path ONLY:**
> "Music track ready at: `assets/music/background_music.mp3`
> Please listen to the full track. I'll wait."

**Message 2 — request decision:**
> "Does the music match the brief direction ([e.g., cicada intro → guzheng+electronic → calm outro])? Reply **Approve** or **Reject: [feedback]**."

If rejected: regenerate with adjusted prompt or try a different music provider.
Do NOT mix any music into the render without explicit `music_review_approved`.

## Asset Manifest Format

```json
{
  "version": "1.0",
  "assets": [
    {
      "id": "narr-hook",
      "type": "narration",
      "path": "assets/audio/hook_narration.mp3",
      "source_tool": "cosyvoice_tts",
      "scene_id": "global",
      "model": "qwen3-tts-instruct-flash"
    },
    {
      "id": "narr-build-1",
      "type": "narration",
      "path": "assets/audio/build_1_narration.mp3",
      "source_tool": "cosyvoice_tts",
      "scene_id": "global",
      "model": "qwen3-tts-instruct-flash"
    },
    {
      "id": "music-track-1",
      "type": "music",
      "path": "assets/music/background_music.mp3",
      "source_tool": "minimax_music",
      "scene_id": "global",
      "model": "music-2.6"
    }
  ],
  "style_mode": "animated",
  "narration_files": [
    {"section_id": "hook", "file": "assets/audio/hook_narration.mp3", "duration_seconds": 5.2},
    {"section_id": "build_1", "file": "assets/audio/build_1_narration.mp3", "duration_seconds": 6.1}
  ],
  "subtitle_file": "assets/subtitles.ass",
  "music_file": "assets/music/background_music.mp3",
  "narration_durations": {
    "hook": 5.2,
    "build_1": 6.1
  },
  "visual_assets": [],
  "sample_clip": "assets/sample_preview.mp4",
  "total_narration_seconds": 11.3,
  "costs": [
    {"tool": "cosyvoice_tts", "cost_usd": 0.30},
    {"tool": "minimax_music", "cost_usd": 0.12}
  ],
  "total_cost_usd": 0.42
}
```

## Budget Tracking

After each tool call, record the cost in the asset_manifest:
- Add to `asset_manifest.costs[]`: `{"tool": "{tool_name}", "cost_usd": {amount}}`
- Accumulate `asset_manifest.total_cost_usd`
- If `total_cost_usd > EP_STATE.budget_total * 0.9` and asset generation is not complete: include a budget warning in the artifact.
- If `total_cost_usd > EP_STATE.budget_total`: STOP. Return partial artifact to EP. Do not continue without new budget approval.

The EP will read `asset_manifest.total_cost_usd` and update `EP_STATE.budget_spent_usd` after reviewing the artifact. Directors never write to EP_STATE directly.

## Validation Before Submitting

- [ ] `sample_approved == true` in EP_STATE
- [ ] `genui_evidence_check` passes before completing the assets checkpoint:
      `make genui-evidence-check PROJECT=projects/<project-id> PIPELINE=ad-video STAGE=assets`
      or `python -m tools.validation.genui_evidence_check
      projects/<project-id> ad-video assets`. This verifies
      `ui_interaction_journal` evidence for `product_reference`,
      `sample_review`, `asset_review`, and `music_review` when the effective
      music strategy is not `none`.
- [ ] TTS file present for every `script.sections[]` item
- [ ] Every narration file also has an `assets[]` entry with `type="narration"`,
      `source_tool`, and `model` so `provider_consistency_check` can verify the
      proposal lock
- [ ] `provider_consistency_check` passes, or any substitution has a visible
      user-approved decision; missing narration coverage blocks compose,
      image/video substitutions must match
      `visual_asset_provider_locks` or a visible approved `provider_selection`
      decision selecting the changed model or exact `source_tool:model` pair,
      music strategy substitutions must have a visible approved
      `music_strategy_selection` decision, `library_locked` / `search_align`
      music must include `asset_manifest.assets[].music_alignment`, and budget
      overages must have a visible approved `budget_tradeoff` selecting an
      overage approval such as `approve-overage`
- [ ] The completed assets checkpoint carries `production_proposal`,
      `production_bible`, `script`, `scene_plan`, and `decision_log` alongside
      `asset_manifest` and `product_identity_reference`; checkpoint validation
      re-runs provider, product-identity, and hallucination gates before compose
- [ ] ASS `subtitle_file` present in asset_manifest when `production_proposal.subtitles.mode != "off"`; omitted when `production_proposal.subtitles.mode == "off"`
- [ ] All visual assets listed in asset_manifest exist on disk
- [ ] `narration_durations` populated for all sections
- [ ] Budget not exceeded
