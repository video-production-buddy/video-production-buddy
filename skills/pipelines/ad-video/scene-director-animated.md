# Scene Director — Animated Mode Supplement

## Scene Type Vocabulary (CLOSED ENUM — MANDATORY)

**You MUST pick `scene_type` for every scene from the registry at `remotion-composer/scene_type_registry.json`.** This file is the single source of truth — if a beat needs a motif not in the registry, request a new component before authoring the plan. The pipeline's fidelity gate (`tools/validation/scene_fidelity_check.py`) will reject any plan that uses a non-registered type.

Common ad-video scene types (see registry for full prop schema and supported `motion_primitives`):

| Scene Type | Component | Best for beats | Key motion primitives |
|---|---|---|---|
| `notification_scene` | NotificationScene | B1 hook | icon_spring_in, badge_counter_roll, banner_cascade |
| `badge_freeze_scene` | BadgeFreezeScene | B1 hook (recognition trigger) | counter_roll, thumb_silhouette_swipe, freeze_pulse |
| `creator_workflow_scene` | CreatorWorkflowScene | B1 hook, B2 build, B4 reveal for premium hardware / creator workflow ads with an approved product reference | product_scale_reveal, timeline_playhead_sweep, workflow_chip_orbit, panel_cascade, progress_bar_race, connection_line_draw |
| `browser_tabs_scene` | BrowserTabsScene | B2 build (multi-tool overload) | tab_overflow, cursor_blink, keyboard_pill |
| `terminal_scene` | TerminalScene | B2 build (developer audience) | cmd_type, output_print |
| `text_card` | TextCard | B2 / B3 flash | text_entrance_fade |
| `dashboard_scene` | DashboardScene | B3 / B4 product reveal | sidebar_spring, card_stagger, toast_slide |
| `checkmark_scene` | CheckmarkScene | B3 / B4 visual resolution moment | checkmark_draw, radial_ripple, spring_pop |
| `line_connection_scene` | LineConnectionScene | B4 sync / data-flow | line_draw_between_anchors, mutual_highlight_pulse |
| `stat_card` / `stat_roll_scene` | StatCard / StatRollScene | B4 reveal stats | digit_roll_up, comma_separators |
| `brand_card` | BrandCardScene | B5 CTA | letter_spring, underline_draw, cta_appear, wordmark_pulse; product_scale_reveal only when `productImage` or `hardwareTreatment` is set |

## Required per-scene fields (fidelity gate enforces)

For every entry in `scene_plan.scenes[]`:

```json
{
  "id": "scene-X",
  "scene_type": "<from registry>",
  "fulfills_kvm": ["KVM-1", ...],         // empty array if scene fulfills no KVM
  "motion_specs": ["counter_roll", ...],  // must be a subset of the chosen component's motion_primitives
  "style_layers": [                        // optional atmosphere/style layers — see scene_type_registry.json#style_layers
    { "type": "grain", "intensity": 0.06 },
    { "type": "ambient_glow", "color": "#FF3B30", "intensity": 0.45, "pulse": true }
  ]
}
```

If a scene declares a motion primitive with registry-specific cut prop
requirements (for example `brand_card` + `product_scale_reveal`), ensure the
downstream `edit_decisions.cuts[]` entry carries the required prop. A text-only
`brand_card` must not claim product-scale motion.

## KVM coverage (MANDATORY)

Every `production_bible.visual.key_visual_moments[]` entry with `mandatory: true` MUST be referenced by at least one scene's `fulfills_kvm` array. Before accepting the plan, run `scene_fidelity_check` (or its `check_kvm_coverage(production_bible, scene_plan)` helper) and include the returned KVM coverage report in the review notes:

```json
{
  "kvm_coverage": [
    {"kvm_id": "KVM-1", "covered_by_scene_id": "scene-2", "component": "BadgeFreezeScene", "missing_primitives": []},
    ...
  ]
}
```

If any mandatory KVM is uncovered, or `missing_primitives` is non-empty, **REJECT** the plan and either re-map a scene or request a new component. Do not proceed to asset generation.

## Keyframe Beats

For each beat of the four-beat structure, recommend scene types:

### Hook (~15% of duration)
- Primary: `text_card` with short hook text (≤8 words)
- Optional follow: `stat_card` or `stat_roll_scene` if hook uses a statistic
- Energy: fast entrance, overshooting spring animation

### Build (~40% of duration)
- Primary: `badge_freeze_scene`, `browser_tabs_scene`, `notification_scene`, `comparison`
- Avoid: consecutive `text_card` scenes (visual monotony)
- Energy: building rhythm, each scene slightly faster than last

### Reveal (~30% of duration)
- Primary: `dashboard_scene`, `checkmark_scene`, or `line_connection_scene`
- Secondary: `stat_roll_scene` if a product stat lands here
- Energy: peak visual complexity, then sudden hold for emphasis

### CTA + Brand Landing (~15% of duration)
- Must use: `brand_card`
- CTA text: center-weighted, within all safe zones
- Brand name: visible in full at end of `brand_card`
- Music: rises to full volume here (ducking lifted)

## Asset Requirements per Scene Type

| Scene Type | Required Assets |
|-----------|----------------|
| `text_card` | None (generated from script text + playbook) |
| `stat_card` / `stat_roll_scene` | None (generated from stat data) |
| `notification_scene` | Optional brand/product icon set |
| `creator_workflow_scene` | Required `productImage` from the approved product identity reference; do not substitute generic hardware |
| `badge_freeze_scene` | None unless the badge must use a real product icon |
| `browser_tabs_scene` | None |
| `comparison` | Optional before/after image or UI references |
| `dashboard_scene` | Product UI screenshot/reference if the product interface must be accurate |
| `line_connection_scene` | Optional UI labels/data-flow labels |
| `brand_card` | Brand logo file when available; otherwise render wordmark text. Keep text-only unless an approved `productImage` is provided or the user explicitly approved `hardwareTreatment: "synthetic_laptop"`. |

## Example Scene Plan (60s animated ad)

> This example assumes `derivative_variants` does not include `"15s"`. If `"15s"` is opted in, mark additional scenes as `core: false` so that `sum(core:true durations) ≤ 15s`.

```json
[
  {
    "id": "scene-1",
    "type": "animation",
    "scene_type": "text_card",
    "beat": "hook",
    "start_seconds": 0,
    "end_seconds": 5,
    "duration_seconds": 5,
    "core": true,
    "description": "Hook text slams in: '45 minutes. Gone.'",
    "motion_required": false,
    "fulfills_kvm": [],
    "motion_specs": ["text_entrance_scale"],
    "style_layers": [{"type": "grain", "intensity": 0.05}]
  },
  {
    "id": "scene-2",
    "type": "animation",
    "scene_type": "badge_freeze_scene",
    "beat": "build",
    "start_seconds": 5,
    "end_seconds": 11,
    "duration_seconds": 6,
    "core": false,
    "description": "Badge counter climbs, then freezes mid-swipe.",
    "motion_required": true,
    "fulfills_kvm": ["KVM-1"],
    "motion_specs": ["counter_roll", "thumb_silhouette_swipe", "freeze_pulse"],
    "style_layers": [{"type": "ambient_glow", "color": "#FF3B30", "intensity": 0.45, "pulse": true}]
  },
  {
    "id": "scene-3",
    "type": "animation",
    "scene_type": "dashboard_scene",
    "beat": "reveal",
    "start_seconds": 11,
    "end_seconds": 21,
    "duration_seconds": 10,
    "core": true,
    "description": "Flowcut dashboard resolves the overload with animated cards and toast.",
    "motion_required": true,
    "fulfills_kvm": ["KVM-2"],
    "motion_specs": ["sidebar_spring", "card_stagger", "toast_slide"],
    "style_layers": []
  },
  {
    "id": "scene-4",
    "type": "animation",
    "scene_type": "brand_card",
    "beat": "cta_brand",
    "start_seconds": 21,
    "end_seconds": 29,
    "duration_seconds": 8,
    "core": true,
    "description": "flowcut.io CTA + Flowcut brand name hold.",
    "motion_required": false,
    "fulfills_kvm": ["KVM-3"],
    "motion_specs": ["letter_spring", "underline_draw", "cta_appear"],
    "style_layers": []
  }
]
```
