# Remotion Composer — Scene & Overlay Cheat Sheet

Authoritative list of `cut.type` and `overlay.type` values the `Explainer` composition accepts. Each row maps to a dispatch case in `src/Explainer.tsx`.

When you add a new component, append it here and in `src/components/index.ts`.

---

## Cut types (`cut.type`)

| `type` | Component | Required fields | Common fields | Purpose |
|---|---|---|---|---|
| *(none — video)* | `OffthreadVideo` | `source` (path to mp4) | `source_in_seconds`, `animation` (zoom-in, ken-burns), `in_seconds`, `out_seconds` | Play an MP4 clip directly |
| *(none — image)* | `Img` | `source` (path to png/jpg) | `animation`, `in_seconds`, `out_seconds` | Play a still with Ken Burns |
| `text_card` | `TextCard` | `text` | `fontSize`, `backgroundVideo`, `backgroundOverlay`, `color` | Large-typography beat |
| `hero_title` | `HeroTitle` | `text` | `heroSubtitle`, `backgroundVideo`, `backgroundOverlay` | Title/end card |
| `stat_card` | `StatCard` | `stat` | `subtitle`, `accentColor`, `backgroundVideo` | A single big number |
| `callout` | `CalloutBox` | `text` | `callout_type` (info/warning/tip/quote), `title`, `backgroundVideo` | Boxed message with bullets |
| `comparison` | `ComparisonCard` | `leftLabel`, `leftValue`, `rightLabel`, `rightValue` | `title`, `backgroundColor` | Side-by-side compare |
| `bar_chart` | `BarChart` | `chartData` | `chartAnimation`, `showValues`, `showGrid`, `backgroundVideo` | Animated bars |
| `line_chart` | `LineChart` | `chartSeries` | `chartAnimation`, `xLabel`, `yLabel`, `showMarkers` | Animated line |
| `pie_chart` | `PieChart` | `chartData` | `donut`, `centerLabel`, `centerValue`, `showLegend` | Pie / donut |
| `kpi_grid` | `KPIGrid` | `chartData` | `title`, `columns`, `chartAnimation` | 2–4 column KPI grid |
| `progress_bar` | `ProgressBar` | `progress` | `progressLabel`, `progressColor`, `progressSegments` | Animated progress |
| `anime_scene` | `AnimeScene` | `images` (list) | `particles`, `lightingFrom`, `lightingTo`, `vignette` | Still-image anime scene with particles + camera motion. **Ad-video restriction: do NOT use for chaos/product/brand beats — use the dynamic types below instead.** |
| `notification_scene` | `NotificationScene` | *(all optional)* | `badgeStart`, `badgeEnd`, `badgeColor`, `banners` (string[]), `backgroundColor`, `sceneDurationSeconds` | Animated app-icon grid with spring-entrance icons, incrementing badge counters, and staggered notification banners. Use for hook/chaos beats. |
| `creator_workflow_scene` | `CreatorWorkflowScene` | `productImage` | `text`, `subtitle`, `banners`, `sidebarItems`, `animation`, `accentColor`, `backgroundColor`, `sceneDurationSeconds` | Product-visible creator workflow scene. Renders the approved `productImage`; it must not substitute generic hardware. |
| `dashboard_scene` | `DashboardScene` | *(all optional)* | `primaryColor`, `accentColor`, `toastText`, `toastDelay`, `sidebarItems` (string[]), `panelTitle`, `sceneDurationSeconds` | Animated product-UI: sidebar items spring in from left, task cards scale up sequentially, toast slides from right. Use for product-reveal beats. |
| `brand_card` | `BrandCardScene` | `productImage` or `hardwareTreatment` when `motion_specs` includes `product_scale_reveal` | `brandName`, `tagline`, `ctaText`, `productImage`, `hardwareTreatment`, `accentColor`, `backgroundColor`, `sceneDurationSeconds` | Animated end card: letters spring up individually, accent underline draws in, tagline fades, CTA appears in accent color, wordmark pulses once at 4 s. Text-only by default; product visuals require an approved `productImage` or explicit synthetic hardware treatment. |
| **`terminal_scene`** | **`TerminalScene`** | **`steps`** (list of cmd/out/pause/pill) | **`terminalTitle`, `prompt`, `accentColor`** | **Synthetic terminal animation — NO real capture needed. See [`.agents/skills/synthetic-screen-recording/SKILL.md`](../.agents/skills/synthetic-screen-recording/SKILL.md)** |
| **`screenshot_scene`** | **`ScreenshotScene`** | **`backgroundImage`** (path in `public/`), **`screenshotSteps`** (list of overlays) | **`screenshotSize` (natural px w/h), `cursorStartAt`, `accentColor`** | **Synthetic UI recording — drop any screenshot, animate scripted overlays on top (`cursor_move`, `click_pulse`, `type_into`, `bubble_append`, `typing_dots`, `highlight_box`, `callout_balloon`). Coordinates are normalized (0–1) against the contain-fit rect.** |
| `checkmark_scene` | `CheckmarkScene` | *(all optional)* | `label`, `accentColor`, `backgroundColor`, `sceneDurationSeconds`, `styleLayers` | Checkmark path draw + radial ripple + label fade. Use for resolution moments or proof that a workflow completed. |
| `browser_tabs_scene` | `BrowserTabsScene` | *(all optional)* | `tabCount`, `showKeyboardPill`, `keyShortcut`, `backgroundColor`, `sceneDurationSeconds`, `styleLayers` | Synthetic crowded browser tab bar with cursor blink, optional keyboard shortcut pill, and tab-close motion. Use for browser/workflow overload beats. |
| `badge_freeze_scene` | `BadgeFreezeScene` | *(all optional)* | `startCount`, `endCount`, `freezeAtSeconds`, `showThumb`, `accentColor`, `backgroundColor`, `sceneDurationSeconds`, `styleLayers` | Extreme close-up counter roll with thumb-swipe freeze. Use for attention/recognition-trigger beats. |
| `line_connection_scene` | `LineConnectionScene` | `leftLabel`, `rightLabel` | `leftSubLabel`, `rightSubLabel`, `drawDelay`, `accentColor`, `backgroundColor`, `sceneDurationSeconds`, `styleLayers` | Two labeled anchors highlight while a connecting line draws between them. Use for sync, handoff, and data-flow reveals. |
| `stat_roll_scene` | `StatRollScene` | `targetValue` | `unitLabel`, `subtitle`, `rollDurationSeconds`, `accentColor`, `backgroundColor`, `sceneDurationSeconds`, `styleLayers` | Rolling-number reveal with comma separators and unit label fade. Use for numeric proof beats where a static stat card is too flat. |

---

## Overlay types (`overlay.type`)

| `type` | Component | Required fields | Common fields | Purpose |
|---|---|---|---|---|
| `section_title` | `SectionTitle` | `text` | `accentColor`, `position` (top-left, etc.) | Tiny section label |
| `stat_reveal` | `StatReveal` | `text` | `subtitle`, `accentColor`, `position` | Corner stat badge |
| `hero_title` | `HeroTitle` (as overlay) | `text` | `subtitle` | Full-frame title overlay |
| **`provider_chip`** | **`ProviderChip`** | **`providers`** (list of strings) | **`cycleSeconds`, `position`, `accentColor`, `label`** | **Rotating badge that cycles through provider names — used in AI-generated-motion scenes to show which model produced the clip** |

---

## Adding a new scene type

1. Create the React component in `src/components/MyScene.tsx`. Use `interpolate(frame, [inFrame, outFrame], [from, to])` and `spring(...)` for motion. Read `useCurrentFrame()` and `useVideoConfig()`.
2. Export it in `src/components/index.ts`.
3. Add the `type` to the `Cut` interface in `src/Explainer.tsx` (and any new prop fields).
4. Add a dispatch case in `SceneRenderer`:
   ```tsx
   if (cut.type === "my_scene" && cut.mySceneData) {
     return maybeWrapWithBg(<MyScene ... />);
   }
   ```
5. Document it in this file. That's what makes it discoverable to the next agent.

## Existing synthetic-UI components

`TerminalScene` covers CLI/install flows. `ScreenshotScene` covers static app screenshots with deterministic cursor, click, typing, bubble, highlight, and callout overlays. The pattern generalizes — likely candidates to add next, if a pipeline needs them:

- `ChatTranscript` — Claude/Cursor/GPT chat-bubble timeline with typing animation
- `EditorScene` — VS Code-style code editor with syntax highlight + cursor motion
- `PrReview` — GitHub PR diff view with inline-comment reveals
- `SlackThread` — Slack thread with avatars + reaction pops
- `TicketBoard` — Jira / Linear card moving across columns

Pattern: follow `TerminalScene.tsx` — a `steps` list of timeline primitives, cursor-advancing durations, spring-based reveals, optional non-blocking pills/badges.
