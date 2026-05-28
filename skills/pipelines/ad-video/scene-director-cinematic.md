# Scene Director — Cinematic Mode Supplement

## Scene Type Vocabulary

| Scene Type | Description | Typical Duration | motion_required |
|-----------|-------------|-----------------|-----------------|
| `hero_shot` | Product or subject as hero — dramatic lighting, slow reveal | 4–8s | true |
| `lifestyle_moment` | Person using product in aspirational context | 5–10s | true |
| `detail_close` | Extreme close-up on product feature or material quality | 2–5s | true |
| `environment_wide` | Establishing or mood-setting wide shot | 3–6s | true |
| `text_overlay` | Cinematic text over still or motion image | 3–5s | false |
| `stat_lower_third` | Statistic as lower-third text over cinematic image | 4–6s | false |
| `social_proof_quick` | Fast-cut quote or user testimonial text | 3–5s | false |
| `brand_landing` | Final brand frame: logo on dark/brand-color background | 4–6s | false |
| `cta_overlay` | CTA text over closing shot or brand landing | 3–5s | false |

## Shot Type Reference

| Shot | Abbreviation | When to Use |
|------|-------------|-------------|
| Extreme close-up | ECU | Texture, detail, emotion |
| Close-up | CU | Face, product hero |
| Medium close-up | MCU | Person + product interaction |
| Medium shot | MS | Action context |
| Wide shot | WS | Environment, scale |
| Over-the-shoulder | OTS | Demonstration, POV |

## Emotional Arc

Cinematic ads follow an emotional arc, not just a logical one:

| Beat | Emotional Goal | Suggested Shots |
|------|---------------|----------------|
| Hook | Disruption or recognition | ECU or unexpected WS |
| Build | Empathy or aspiration | MCU lifestyle, slow pace |
| Reveal | Resolution or wonder | CU product hero, rising music |
| CTA + Brand | Confidence and trust | brand_landing, WS with text |

Each scene's `description` must embed the emotional goal and visual treatment
from its matched beat in `production_bible.narrative.emotional_beat_sequence`.
Read the beat's `emotional_target` and `visual_constraint` and translate them
into concrete cinematic language in the description — camera behavior, lighting
mood, motion energy — not just subject placement.

For example, if the hook beat says `visual_constraint: "abrupt jarring camera
to disrupt complacency"` and `emotional_target: "Disruption — snap the viewer
out of autopilot"`, the scene description should read something like:
"Sudden handheld close-up of a clock face, sharp rack focus, jarring edit-in
camera — raw urgency" — not just "Clock on a desk."

The `emotional_target` and `visual_constraint` fields must also be carried as
structured data on each scene object so the asset-director can use them
directly when constructing generation prompts.

## Asset Requirements per Scene Type

| Scene Type | Required Assets |
|-----------|----------------|
| `hero_shot` | 1× AI-generated video clip or approved product reference still for packshot-only end frames |
| `lifestyle_moment` | 1× AI-generated video clip (Wan/Kling) OR 1× stock video |
| `detail_close` | 1× AI-generated macro video clip |
| `environment_wide` | 1× AI-generated video clip or wide stock video |
| `text_overlay` | 1× background image + text from script |
| `stat_lower_third` | 1× background image + stat data |
| `social_proof_quick` | Text only (from brand_context reference_files or fabricated from concept) |
| `brand_landing` | Brand logo (from reference_files) or generated brand frame |
| `cta_overlay` | Background image + CTA text from script |

## Image Generation Prompt Structure (Cinematic)

```
{playbook.asset_generation.image_prompt_prefix}
{scene description in detail}
{shot type}: {ECU|CU|MCU|MS|WS}
lighting: {cinematic, motivated, {direction}}
color: {aligned to brand palette from playbook}
{playbook.asset_generation.image_negative_prompt} [negative]
```

## Example Scene Plan (60s cinematic ad)

> This example assumes `derivative_variants` does not include `"15s"`. If `"15s"` is opted in, mark additional scenes as `core: false` so that `sum(core:true durations) ≤ 15s`.

```json
[
  {"id": "scene-1", "scene_type": "environment_wide", "beat": "hook", "duration_seconds": 5, "core": true,
   "description": "Slow-motion city morning rush — people hurrying, clock in frame", "motion_required": true},
  {"id": "scene-2", "scene_type": "text_overlay", "beat": "hook", "duration_seconds": 4, "core": true,
   "description": "'45 minutes. Every morning.' over blurred commute background", "motion_required": false},
  {"id": "scene-3", "scene_type": "lifestyle_moment", "beat": "build", "duration_seconds": 8, "core": false,
   "description": "Person frustrated at desk, switching tabs, sighing", "motion_required": true},
  {"id": "scene-4", "scene_type": "stat_lower_third", "beat": "build", "duration_seconds": 5, "core": false,
   "description": "'4 hours/week wasted' over productivity context", "motion_required": false},
  {"id": "scene-5", "scene_type": "hero_shot", "beat": "reveal", "duration_seconds": 6, "core": true,
   "description": "Product hero reveal clip — clean desk, Flowcut on screen, warm light", "motion_required": true},
  {"id": "scene-6", "scene_type": "lifestyle_moment", "beat": "reveal", "duration_seconds": 10, "core": true,
   "description": "Person calmly finishing work, leaning back satisfied", "motion_required": true},
  {"id": "scene-7", "scene_type": "brand_landing", "beat": "cta_brand", "duration_seconds": 7, "core": true,
   "description": "Flowcut logo on dark background, URL lower-third", "motion_required": false},
  {"id": "scene-8", "scene_type": "cta_overlay", "beat": "cta_brand", "duration_seconds": 5, "core": true,
   "description": "'Start free at flowcut.io' — center frame, fade in", "motion_required": false}
]
```
