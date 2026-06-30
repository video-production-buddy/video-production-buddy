# Video Production Buddy - Skill Index

> For the full agent onboarding guide, see [`AGENT_GUIDE.md`](../AGENT_GUIDE.md) in the project root.

This file lists all available Layer 2 skills and documents the 3-layer knowledge architecture.

## Knowledge Architecture

```
Layer 1: tools/tool_registry.py          "What tools exist and what they can do"
         tools/base_tool.py               Each tool declares: capabilities, tier, status,
                                          dependencies, cost, and agent_skills[]

         -> agent_skills[] points to ->

Layer 2: skills/                          "How Video Production Buddy uses these tools"
         Project-specific conventions:     Pipeline integration, artifact mappings,
         {core,creative,meta,pipelines}/   enhancement chain order, quality checklists

         -> references underlying tech in ->

Layer 3: .agents/skills/                  "How the technology itself works"
         Generic API knowledge from        Correct import paths, code patterns,
         locked agent components           constraints, parameters - tech-agnostic
```

**How the agent uses this:**
1. The orchestrator queries Layer 1 (`tool_registry.provider_menu_summary()`) to see what's available
2. Each tool's `agent_skills[]` field names the Layer 3 skills it relies on
3. Layer 2 skills (this directory) teach the agent Video Production Buddy-specific conventions
4. Layer 3 skills (`.agents/skills/`) provide generic API knowledge, generated on-demand from `.agents/components.yaml`

## Capability Families & Tool Discovery

Every tool declares a `capability` (what it does) and a `provider` (who/what powers it). The registry groups tools by capability so agents can discover all options for a given task.

### Selector / Provider Pattern

For capability families with multiple providers (TTS, video generation), the architecture uses:
- **Selector tool** (`tts_selector`, `video_selector`, `image_selector`, `music_selector`, `text_selector`, `transcription_selector`) — routes to the best available provider based on requirements, API key availability, and cost. Selectors auto-discover providers from the registry. Agents should default to selectors when the user hasn't specified a provider.
- **Provider tools** — call a specific provider directly. Agents use these when the user explicitly requests a provider or when the selector's routing isn't appropriate.
- **Dynamic interaction router** (`genui_interaction`) — before each substantive human interaction, decide whether linear chat is sufficient; when visual demonstration, multi-axis selection, media review, or structured revision capture is needed, route to the GenUI A2UI/CopilotKit browser path.

### Capability Family Reference

**Do not maintain a hardcoded tool list.** The registry is the single source of truth. Query it at runtime:

```bash
python -c "from tools.tool_registry import registry; import json; registry.discover(); print(json.dumps(registry.provider_menu_summary(), indent=2))"
```

Use `provider_menu_summary()` for user-facing preflight. Use
`provider_menu()` for per-tool install details and `support_envelope()` only for
deep debugging when the compact summary is not enough.

Key capability families to look for in the output:

| Capability | Selector | Discovery |
|---|---|---|
| `tts` | `tts_selector` | Auto-discovers all `capability="tts"` tools |
| `video_generation` | `video_selector` | Auto-discovers all `capability="video_generation"` tools |
| `image_generation` | `image_selector` | Auto-discovers all `capability="image_generation"` tools |
| `music_generation` | `music_selector` | Auto-discovers all `capability="music_generation"` tools |
| `text_generation` | `text_selector` | Auto-discovers optional billed `capability="text_generation"` tools |
| `transcription` | `transcription_selector` | Auto-discovers all `capability="transcription"` tools |
| `audio_processing` | — | FFmpeg-based local tools |
| `enhancement` | — | Mixed providers |
| `analysis` | — | Mixed providers |
| `character_animation` | — | Local character specs, SVG rigs, pose libraries, action timelines, previews, and QA |
| `clip_acquisition` | — | Fast stock clip/image download through shared source adapters (`direct_clip_search`) |
| `clip_retrieval` | — | Local corpus retrieval and ranking (`clip_search`) |
| `compliance` | — | Deterministic compliance checks for checkpoint/governance artifacts |
| `corpus_population` | — | Stock-source fanout, download, thumbnailing, embedding, and corpus indexing |
| `graphics` | — | Local rendering tools |
| `interaction` | — | GenUI routing/session/surface tools; local UI is opt-in and response-only |
| `knowledge_retrieval` | — | Local curated knowledge retrieval for planning and review |
| `music_generation` | `music_selector` | Registry-discovered providers (`minimax_music`, `music_gen`, `suno_music`, etc.) |
| `music_search` | — | Royalty-free/background music search providers (`pixabay_music`, `freesound_music`) |
| `screen_capture` | `screen_capture_selector` | FFmpeg/Cap screen recording providers for screen-demo pipelines |
| `source_ingest` | — | Source URL download/metadata ingestion (`video_downloader`) |
| `transcription` | `transcription_selector` | Speech-to-text providers such as `qwen_asr`; check supports before using for subtitles |
| `text_generation` | `text_selector` | LLM chat providers (`qwen_chat`, `minimax_chat`); standalone ad-hoc text tools, not auto-wired into pipeline stages |
| `validation` | — | Cross-artifact planning, runtime, provider, identity, fidelity, and GenUI evidence validators |
| `vision_understanding` | — | Image/video understanding (`qwen_vl`); for reference analysis, frame QA, hallucination review |
| `subtitle` | — | Pure Python |
| `avatar` | — | Local GPU models |
| `video_post` | — | FFmpeg-based local tools |

### Adding New Tools

1. Place the tool in the correct capability folder (or create a new one under `tools/`)
2. Set `capability` and `provider` in the class definition
3. If joining a multi-provider family, the existing selector discovers it automatically
4. Attach relevant Layer 2 and Layer 3 skills via `agent_skills[]`
5. The registry discovers tools automatically — no manual registration needed
6. **No selector or manifest files need updating** — selectors derive from the registry; update Layer 2 skills only when agents need new provider-specific cautions or prompt routing rules

### Media Runtime Additions

Recent media-runtime work added registry provider tools that selectors discover
automatically, plus one local CLI utility for generated-TTS subtitle alignment.
Layer 2 skills still need to know their user-facing strengths and constraints:

| Tool | Capability | Provider | Layer 2 Notes |
|------|------------|----------|---------------|
| `cosyvoice_tts` | `tts` | Bailian / DashScope | Qwen3 + CosyVoice narration (latest `cosyvoice-v3.5-plus/flash`); use `qwen3-tts-instruct-flash` when script delivery instructions must be honored |
| `minimax_tts` | `tts` | MiniMax | Studio-grade narration via `speech-2.8-hd`/`turbo`; second TTS provider on `MINIMAX_API_KEY`, no per-section delivery-instruction contract |
| `qwen_asr` | `transcription` | Bailian / DashScope | Fast Chinese/multilingual transcript text; not a subtitle source when word timestamps are required |
| `wanx_image` | `image_generation` | Bailian / DashScope | Wanxiang image generation and editing (latest `wan2.7-image-pro`/`wan2.7-image`); read `.agents/skills/wanx-best-practices/` before prompting |
| `wan_video_api` | `video_generation` | Bailian / DashScope | HappyHorse 1.0 flagship (native audio+video) + Wan 2.7 t2v/i2v/r2v/edit; pass `aspect_ratio` (mapped to `ratio` on 2.7/HappyHorse) for non-landscape output |
| `minimax_video` | `video_generation` | MiniMax | Native MiniMax Hailuo 2.3 / 2.3-Fast / 02 via `MINIMAX_API_KEY`; camera control via `[command]` prompt syntax |
| `minimax_music` | `music_generation` | MiniMax | Instrumental background tracks, structured songs, and cover generation (`music-2.6`) |
| `qwen_chat` | `text_generation` | Bailian / DashScope | Qwen3.7-max/plus/flash chat — standalone ad-hoc text tool; read `.agents/skills/text-generation/` before billed LLM calls |
| `minimax_chat` | `text_generation` | MiniMax | MiniMax-M3/M2.7 chat — standalone ad-hoc text tool; read `.agents/skills/text-generation/` before billed LLM calls |
| `qwen_vl` | `vision_understanding` | Bailian / DashScope | Image/video understanding via qwen3-vl-plus / qwen3.7-plus; reference analysis, frame QA, hallucination review |
| `subtitle_aligner` | local CLI subtitle utility | local faster-whisper | Not registry-discovered; run with `python -m tools.audio.subtitle_aligner` to forced-align generated TTS segments into ASS subtitles with real word timing and PlayRes-safe layout |

## Core Skills

| Skill | File | Trigger | Agent Skills (Layer 3) |
|-------|------|---------|----------------------|
| FFmpeg | `core/ffmpeg.md` | Video encoding, filtering, composition | `ffmpeg`, `video-toolkit` |
| Remotion | `core/remotion.md` | React-based composition, Phase 3+ | `remotion-best-practices`, `remotion` |
| HyperFrames | `core/hyperframes.md` | HTML/CSS/GSAP composition runtime — kinetic typography, music-to-video, product promos, website capture. Vendored at v0.7.17 (2026-06-27). | `hyperframes` (router) → `hyperframes-core` (contract), `hyperframes-creative` (palette/type/narration), `hyperframes-media` (TTS/BGM/SFX/captions), `hyperframes-animation` (all motion), `hyperframes-cli`, `hyperframes-registry`, `media-use`, `motion-graphics`, `music-to-video` (beats-driven), `website-to-video`, `remotion-to-hyperframes` (migration), `gsap-core`, `gsap-timeline` |
| WhisperX | `core/whisperx.md` | Transcription with word-level timestamps | `speech-to-text` |
| Subtitle Sync | `core/subtitle-sync.md` | Subtitle timing and alignment | `remotion-best-practices` |
| Color Grading | `core/color-grading.md` | FFmpeg color profiles, LUT workflow, accessibility | `ffmpeg` |

## Creative Skills

| Skill | File | Trigger | Agent Skills (Layer 3) |
|-------|------|---------|----------------------|
| Video Editing | `creative/video-editing.md` | Cut decisions, pacing, rhythm | `ffmpeg`, `video-toolkit` |
| Enhancement Strategy | `creative/enhancement-strategy.md` | Overlay placement and density | `ffmpeg` |
| Data Visualization | `creative/data-visualization.md` | Chart type selection, animation, label placement | `d3-viz`, `remotion-best-practices` |
| Video Stitching | `creative/video-stitching.md` | Multi-clip assembly, AI clip chaining, spatial composition | `ffmpeg`, `video-toolkit` |
| Video Gen Prompting | `creative/video-gen-prompting.md` | Universal video generation prompt vocabulary; **canonical 5-aspect spec** (Subject / Motion / Scene / Spatial / Camera); ~200 cinematography primitives | `ai-video-gen`, `ltx2`, `create-video` |
| Seedance Prompting | `creative/prompting/seedance-prompting.md` | **Preferred premium default.** Seedance 2.0 8-component structure, multi-shot, lip-sync, reference-to-video | `seedance-2-0`, `ai-video-gen` |
| Grok Prompting | `creative/prompting/grok-prompting.md` | Grok image/video prompting, edit flows, reference-image video | `grok-media` |
| Sora Prompting | `creative/prompting/sora-prompting.md` | Sora 2 structured template, advanced fields | `ai-video-gen` |
| VEO Prompting | `creative/prompting/veo-prompting.md` | VEO 3.1 14-component structure, art movements | `ai-video-gen` |
| LTX Prompting | `creative/prompting/ltx-prompting.md` | LTX-2 6-element structure, audio prompting | `ltx2` |
| HunyuanVideo Prompting | `creative/prompting/hunyuan-prompting.md` | HunyuanVideo formula, I2V best practices | - |
| Storytelling | `creative/storytelling.md` | Narrative structure, hooks, pacing, Mayer's principles | - |
| Sound Design | `creative/sound-design.md` | Audio ducking, LUFS targets, SFX timing, AI TTS mixing | `elevenlabs` |
| Typography | `creative/typography.md` | Font selection, text sizing, safe zones, caption styling | - |
| ManimCE Usage | `creative/manim-usage.md` | Scene composition, animation timing, color usage | `manimce-best-practices` |
| Image Gen Usage | `creative/image-gen-usage.md` | Prompt consistency, hero reference, batch strategy | `flux-best-practices`, `bfl-api` |
| Image Provider Usage | `creative/image-provider-usage.md` | Provider selection (FLUX/Grok/OpenAI/Recraft/Wanx/stock), cost-quality tradeoffs | `flux-best-practices`, `bfl-api`, `grok-media`, `wanx-best-practices` |
| B-Roll Planning | `creative/broll-planning.md` | Stock vs. generated decision, query construction, footage evaluation | — |
| Stock Sourcing Usage | `creative/stock-sourcing-usage.md` | Pexels/Pixabay usage, parameters, licensing, integration | `stock-sourcing` |
| Scene Detect Usage | `creative/scene-detect-usage.md` | Threshold tuning, algorithm selection, content presets | - |
| Diagram Gen Usage | `creative/diagram-gen-usage.md` | Complexity limits, progressive building, themes | `beautiful-mermaid` |
| Music Gen Usage | `creative/music-gen-usage.md` | BPM selection, prompt engineering, provider-specific duration/lyrics controls | `music`, `elevenlabs` |
| Background Removal | `creative/bg-remove-usage.md` | Model selection, alpha matting, compositing workflows | - |
| Upscaling | `creative/upscale-usage.md` | Scale factor, model selection, face-aware upscaling | - |
| Face Restoration | `creative/face-restore-usage.md` | CodeFormer/GFPGAN selection, fidelity tuning, vs face_enhance | - |
| Lip Sync | `creative/lip-sync-usage.md` | Wav2Lip model selection, dubbing workflows, input requirements | `faceswap` |
| Talking Head Gen | `creative/talking-head-gen-usage.md` | SadTalker/MuseTalk, photo-to-video, expression tuning | `avatar-video` |
| Video Understanding | `creative/video-understand-usage.md` | Visual QA, quality gating, scene classification | `video-understand` |

## Pipeline Type Skills

Pipeline type skills provide production guidance for specific video formats, independent of the animated-explainer or talking-head pipeline.

| Skill | File | When to Use |
|-------|------|-------------|
| Short-Form | `creative/short-form.md` | TikTok, Reels, Shorts - vertical 9:16, under 60s |
| Long-Form | `creative/long-form.md` | YouTube 10+ min - chapters, retention, end screens |
| Screen Recording | `creative/screen-recording.md` | Code walkthroughs, tutorials, software demos |
| Animation Pipeline | `creative/animation-pipeline.md` | Motion graphics, easing, transitions, composition |
| Character Animation Pipeline | `pipelines/character-animation/` | Rigged local cartoon characters, pose libraries, action timelines, SVG/Canvas/Remotion/HyperFrames rendering |
| Cinematic | `creative/cinematic.md` | Letterbox, film pacing, layered audio, color grading |

## Pipeline Stage Director Skills

Stage director skills teach the agent HOW to execute each pipeline stage. Each skill is a detailed markdown file with process steps, quality rubrics, and self-evaluation criteria.

### Animated Explainer Pipeline (`pipelines/explainer/`) — v2.0

| Skill | File | Stage | Key Capabilities |
|-------|------|-------|-----------------|
| **Executive Producer** | `pipelines/explainer/executive-producer.md` | `all` | **8-stage serial orchestration, quality gates, cross-stage checks, send-back** |
| **Research Director** | `pipelines/explainer/research-director.md` | `research` | **Web research methodology, 5 search batches, landscape/trending/data/audience/expert analysis** |
| **Proposal Director** | `pipelines/explainer/proposal-director.md` | `proposal` | **Concept options from research, production plan, cost estimate, approval gate** |
| Script Director | `pipelines/explainer/script-director.md` | `script` | Narrative architecture, timing, enhancement cues, research integration |
| Scene Director | `pipelines/explainer/scene-director.md` | `scene_plan` | Visual planning, technique library, feasibility |
| Asset Director | `pipelines/explainer/asset-director.md` | `assets` | TTS, image gen, diagram gen, music, budget |
| Edit Director | `pipelines/explainer/edit-director.md` | `edit` | Timeline assembly, subtitles, audio ducking |
| Compose Director | `pipelines/explainer/compose-director.md` | `compose` | FFmpeg/Remotion render, audio mixing |
| Publish Director | `pipelines/explainer/publish-director.md` | `publish` | SEO metadata, chapters, export packaging |

> **Note:** The old `pipelines/explainer/idea-director.md` still exists for reference but is superseded by the research + proposal two-stage flow in v2.0. The talking-head pipeline continues to use its own `idea-director`.

### Talking Head Pipeline (`pipelines/talking-head/`)

| Skill | File | Stage | Key Capabilities |
|-------|------|-------|-----------------|
| **Executive Producer** | `pipelines/talking-head/executive-producer.md` | `all` | **Footage-first orchestration, transcript truth, A/V sync gates, send-back control** |
| Idea Director | `pipelines/talking-head/idea-director.md` | `idea` | Footage inspection, content assessment |
| Script Director | `pipelines/talking-head/script-director.md` | `script` | Transcription, section segmentation |
| Scene Director | `pipelines/talking-head/scene-director.md` | `scene_plan` | Enhancement planning, overlay placement |
| Asset Director | `pipelines/talking-head/asset-director.md` | `assets` | Subtitle gen, audio extraction |
| Edit Director | `pipelines/talking-head/edit-director.md` | `edit` | Cut assembly, subtitle config |
| Compose Director | `pipelines/talking-head/compose-director.md` | `compose` | Enhancement chain, render |
| Publish Director | `pipelines/talking-head/publish-director.md` | `publish` | Metadata, export packaging |

### Screen Demo Pipeline (`pipelines/screen-demo/`) — v2.0

| Skill | File | Stage | Key Capabilities |
|-------|------|-------|-----------------|
| **Executive Producer** | `pipelines/screen-demo/executive-producer.md` | `all` | **7-stage serial orchestration, legibility gates, audio clarity, pacing checks** |
| Idea Director | `pipelines/screen-demo/idea-director.md` | `idea` | Workflow scoping, UI density assessment, output-shape choice |
| Script Director | `pipelines/screen-demo/script-director.md` | `script` | Action mapping, procedural narration, speed planning |
| Scene Director | `pipelines/screen-demo/scene-director.md` | `scene_plan` | Crop planning, callout restraint, aspect-ratio viability |
| Asset Director | `pipelines/screen-demo/asset-director.md` | `assets` | Subtitle-first asset kit, audio cleanup, reusable overlays |
| Edit Director | `pipelines/screen-demo/edit-director.md` | `edit` | Tight timeline planning, speed notes, subtitle zone control |
| Compose Director | `pipelines/screen-demo/compose-director.md` | `compose` | Legibility-first render, crisp screen output, verification |
| Publish Director | `pipelines/screen-demo/publish-director.md` | `publish` | Searchable metadata, chapter packaging, thumbnail concepts |

### Clip Factory Pipeline (`pipelines/clip-factory/`) — v2.0

| Skill | File | Stage | Key Capabilities |
|-------|------|-------|-----------------|
| **Executive Producer** | `pipelines/clip-factory/executive-producer.md` | `all` | **7-stage serial orchestration, clip selection gates, batch consistency, hook placement** |
| Idea Director | `pipelines/clip-factory/idea-director.md` | `idea` | Batch strategy, clip families, yield planning |
| Script Director | `pipelines/clip-factory/script-director.md` | `script` | Transcript mining, ranking, standalone validation |
| Scene Director | `pipelines/clip-factory/scene-director.md` | `scene_plan` | Platform framing, safe zones, crop-viability planning |
| Asset Director | `pipelines/clip-factory/asset-director.md` | `assets` | Shared brand kit, rebased subtitles, batch audio consistency |
| Edit Director | `pipelines/clip-factory/edit-director.md` | `edit` | Hook-first mini-edits, series consistency |
| Compose Director | `pipelines/clip-factory/compose-director.md` | `compose` | Multi-job rendering, batch resilience, per-output verification |
| Publish Director | `pipelines/clip-factory/publish-director.md` | `publish` | Posting order, platform copy, batch cataloging |

### Podcast Repurpose Pipeline (`pipelines/podcast-repurpose/`) — v2.0

| Skill | File | Stage | Key Capabilities |
|-------|------|-------|-----------------|
| **Executive Producer** | `pipelines/podcast-repurpose/executive-producer.md` | `all` | **7-stage serial orchestration, audio preservation gates, clip quality, multi-deliverable** |
| Idea Director | `pipelines/podcast-repurpose/idea-director.md` | `idea` | Deliverable mix by source mode, realistic long-form planning |
| Script Director | `pipelines/podcast-repurpose/script-director.md` | `script` | Diarized transcript truth, highlight ranking, chapter mapping |
| Scene Director | `pipelines/podcast-repurpose/scene-director.md` | `scene_plan` | Source-faithful treatments, audiogram vs quote vs companion planning |
| Asset Director | `pipelines/podcast-repurpose/asset-director.md` | `assets` | Subtitle-first packaging, speaker assets, optional topic art |
| Edit Director | `pipelines/podcast-repurpose/edit-director.md` | `edit` | Hook-led podcast clips, quote hold time, companion simplicity |
| Compose Director | `pipelines/podcast-repurpose/compose-director.md` | `compose` | Audio-first rendering, deliverable prioritization |
| Publish Director | `pipelines/podcast-repurpose/publish-director.md` | `publish` | Episode cross-linking, guest attribution, staggered release logic |

### Cinematic Pipeline (`pipelines/cinematic/`) — v2.0

| Skill | File | Stage | Key Capabilities |
|-------|------|-------|-----------------|
| **Executive Producer** | `pipelines/cinematic/executive-producer.md` | `all` | **7-stage serial orchestration, emotional pacing gates, color consistency, audio dynamics** |
| **Research Director** | `pipelines/cinematic/research-director.md` | `research` | **Visual references, emotional language, motion precedents, audience context** |
| **Proposal Director** | `pipelines/cinematic/proposal-director.md` | `proposal` | **Concept directions, runtime selection, production plan, approval gate** |
| Idea Director | `pipelines/cinematic/idea-director.md` | `idea` | Emotional arc selection, source truth, delivery-shape planning |
| Script Director | `pipelines/cinematic/script-director.md` | `script` | Beat mapping, dialogue selects, title-card restraint |
| Scene Director | `pipelines/cinematic/scene-director.md` | `scene_plan` | Hero-frame planning, reveal structure, transition limits |
| Asset Director | `pipelines/cinematic/asset-director.md` | `assets` | Source selects, support-insert discipline, music/ambience planning |
| Edit Director | `pipelines/cinematic/edit-director.md` | `edit` | Emotion-first pacing, reveal timing, audio-driven rhythm |
| Compose Director | `pipelines/cinematic/compose-director.md` | `compose` | Grade and mix finishing, frame-treatment judgment |
| Publish Director | `pipelines/cinematic/publish-director.md` | `publish` | Hero vs teaser packaging, poster-frame concepts |

### Animation Pipeline (`pipelines/animation/`) — v2.0

| Skill | File | Stage | Key Capabilities |
|-------|------|-------|-----------------|
| **Executive Producer** | `pipelines/animation/executive-producer.md` | `all` | **8-stage serial orchestration, quality gates, motion consistency, math accuracy checks** |
| **Research Director** | `pipelines/animation/research-director.md` | `research` | **Topic + animation technique research, visual reference scan, mode-informed angles** |
| **Proposal Director** | `pipelines/animation/proposal-director.md` | `proposal` | **Animation mode selection (Manim/Remotion/AI/diagram), reuse strategy, cost estimate, approval gate** |
| Script Director | `pipelines/animation/script-director.md` | `script` | Animation-ready beats, text restraint, research integration, mode-aware writing |
| Scene Director | `pipelines/animation/scene-director.md` | `scene_plan` | Animatic planning, transition systems, tool-path mapping |
| Asset Director | `pipelines/animation/asset-director.md` | `assets` | Deterministic asset choice, reusable motifs, feasibility truth |
| Edit Director | `pipelines/animation/edit-director.md` | `edit` | Hold timing, stagger rules, readable motion planning |
| Compose Director | `pipelines/animation/compose-director.md` | `compose` | Sharp render output, timing integrity, safe-zone checks |
| Publish Director | `pipelines/animation/publish-director.md` | `publish` | Animation-mode packaging, thumbnail-system alignment |

> **Note:** The old `pipelines/animation/idea-director.md` still exists for reference but is superseded by the research + proposal two-stage flow in v2.0.

### Ad Video Pipeline (`pipelines/ad-video/`) — v1.0 beta

Use for ads and commercial-style productions that need pre-production
governance, product-fidelity checks, approved sample generation, and
cross-stage validation before publish.

| Skill | File | Stage | Key Capabilities |
|-------|------|-------|-----------------|
| **Executive Producer** | `pipelines/ad-video/executive-producer.md` | `all` | **Generic top-level orchestration with governed child gates, approval gates, budget and artifact state** |
| Research Director | `pipelines/ad-video/research-director.md` | `research` | Parent gate for intake, brief enrichment, and intelligence |
| Intake Director | `pipelines/ad-video/intake-director.md` | `research.intake` | Research-direction parsing, sparse-brief questions |
| Brief Enrichment Director | `pipelines/ad-video/brief-enrichment-director.md` | `research.brief_enrichment` | Creative-director worksheet, G-0 approval, enriched brief |
| Intelligence Director | `pipelines/ad-video/intelligence-director.md` | `research.intelligence` | Professional knowledge retrieval, trend analysis, hit-ad synthesis |
| Proposal Director | `pipelines/ad-video/proposal-director.md` | `proposal` | Parent gate for bible, idea, and technical proposal |
| Bible Director | `pipelines/ad-video/bible-director.md` | `proposal.bible` | Strategic contract, truth contract, beat and compliance governance |
| Idea Director | `pipelines/ad-video/idea-director.md` | `proposal.idea` | Execution concepts inside the approved bible |
| Technical Proposal Director | `pipelines/ad-video/technical-proposal-director.md` | `proposal.technical_proposal` | Runtime, product-reference, audio, subtitles, derivatives, budget lock |
| Script Director | `pipelines/ad-video/script-director.md` | `script` | Approved narration, beat timing, trend and knowledge source refs |
| Scene Director | `pipelines/ad-video/scene-director.md` | `scene_plan` | Product visibility, hallucination checks, motion-first scene planning |
| Scene Director - Animated Supplement | `pipelines/ad-video/scene-director-animated.md` | `scene_plan` | Remotion scene-type vocabulary and animated-mode fidelity rules |
| Scene Director - Cinematic Supplement | `pipelines/ad-video/scene-director-cinematic.md` | `scene_plan` | Cinematic shot vocabulary and motion-required rules |
| Asset Director | `pipelines/ad-video/asset-director.md` | `assets` | Product identity reference, sample approval, provider and hallucination gates |
| Asset Director - Animated Supplement | `pipelines/ad-video/asset-director-animated.md` | `assets` | Dynamic Remotion scenes and animated asset routing |
| Asset Director - Cinematic Supplement | `pipelines/ad-video/asset-director-cinematic.md` | `assets` | Reference-aware cinematic visual generation and truth-contract branching |
| Edit Director | `pipelines/ad-video/edit-director.md` | `edit` | Timeline, subtitle burn config, music ducking, runtime carry-forward |
| Compose Director | `pipelines/ad-video/compose-director.md` | `compose` | Pre-render gates, derivative renders, final_review with actual-output evidence |
| Publish Director | `pipelines/ad-video/publish-director.md` | `publish` | Output matrix, metadata, thumbnail concept, hallucination publish gate |

### Hybrid Pipeline (`pipelines/hybrid/`) — v2.0

| Skill | File | Stage | Key Capabilities |
|-------|------|-------|-----------------|
| **Executive Producer** | `pipelines/hybrid/executive-producer.md` | `all` | **7-stage serial orchestration, source/support balance gates, overlay density, coherence** |
| Idea Director | `pipelines/hybrid/idea-director.md` | `idea` | Anchor-medium selection, support-layer planning, fallback visibility |
| Script Director | `pipelines/hybrid/script-director.md` | `script` | Source-vs-support beat mapping, dialogue retention, support justification |
| Scene Director | `pipelines/hybrid/scene-director.md` | `scene_plan` | Source-primary layout rules, overlay density control, variant-safe planning |
| Asset Director | `pipelines/hybrid/asset-director.md` | `assets` | Shared support kits, source-vs-generated asset tracking |
| Edit Director | `pipelines/hybrid/edit-director.md` | `edit` | Anchor-cut-first workflow, layered support timing, readable variants |
| Compose Director | `pipelines/hybrid/compose-director.md` | `compose` | Source/support balance checks, variant verification, coherent mix |
| Publish Director | `pipelines/hybrid/publish-director.md` | `publish` | Master-vs-derivative packaging, source-mix metadata |

### Avatar Spokesperson Pipeline (`pipelines/avatar-spokesperson/`) — v2.0

| Skill | File | Stage | Key Capabilities |
|-------|------|-------|-----------------|
| **Executive Producer** | `pipelines/avatar-spokesperson/executive-producer.md` | `all` | **7-stage serial orchestration, lip-sync quality gates, presenter framing, CTA landing** |
| Idea Director | `pipelines/avatar-spokesperson/idea-director.md` | `idea` | Avatar-path classification, CTA scoping, capability truth |
| Script Director | `pipelines/avatar-spokesperson/script-director.md` | `script` | Spoken-copy shaping, scene-safe pacing, text restraint |
| Scene Director | `pipelines/avatar-spokesperson/scene-director.md` | `scene_plan` | Presenter layout, background discipline, variant realism |
| Asset Director | `pipelines/avatar-spokesperson/asset-director.md` | `assets` | Avatar-path locking, narration resolution, minimal support kits |
| Edit Director | `pipelines/avatar-spokesperson/edit-director.md` | `edit` | Presenter-first cut planning, overlay timing, CTA landing |
| Compose Director | `pipelines/avatar-spokesperson/compose-director.md` | `compose` | Lip-sync verification, subtitle-safe framing, clean render checks |
| Publish Director | `pipelines/avatar-spokesperson/publish-director.md` | `publish` | Audience-led packaging, presenter-first thumbnail concepts |

### Localization Dub Pipeline (`pipelines/localization-dub/`) — v2.0

| Skill | File | Stage | Key Capabilities |
|-------|------|-------|-----------------|
| **Executive Producer** | `pipelines/localization-dub/executive-producer.md` | `all` | **7-stage serial orchestration, translation accuracy gates, timing preservation, per-locale QA** |
| Idea Director | `pipelines/localization-dub/idea-director.md` | `idea` | Scope definition, locale planning, glossary and review capture |
| Script Director | `pipelines/localization-dub/script-director.md` | `script` | Transcript truth, translated script packaging, term preservation |
| Scene Director | `pipelines/localization-dub/scene-director.md` | `scene_plan` | Dub-mode selection, timing-risk mapping, on-screen text planning |
| Asset Director | `pipelines/localization-dub/asset-director.md` | `assets` | Subtitle-first localization kit, dubbed audio generation, optional lip sync |
| Edit Director | `pipelines/localization-dub/edit-director.md` | `edit` | Locale-specific timelines, coverage planning, timing adjustments |
| Compose Director | `pipelines/localization-dub/compose-director.md` | `compose` | Per-locale rendering, subtitle-fit checks, output labeling |
| Publish Director | `pipelines/localization-dub/publish-director.md` | `publish` | Locale packaging, metadata precision, QA-note retention |

### Character Animation Pipeline (`pipelines/character-animation/`) — v1.0 beta

| Skill | File | Stage | Key Capabilities |
|-------|------|-------|-----------------|
| **Executive Producer** | `pipelines/character-animation/executive-producer.md` | `all` | **Local rigged-character orchestration, feasibility gates, acting quality** |
| Research Director | `pipelines/character-animation/research-director.md` | `research` | Reference technique analysis, reusable primitives, feasibility truth |
| Proposal Director | `pipelines/character-animation/proposal-director.md` | `proposal` | Character concepts, runtime options, rig reuse, sample plan |
| Script Director | `pipelines/character-animation/script-director.md` | `script` | Performable beats, dialogue and action-friendly writing |
| Character Design Director | `pipelines/character-animation/character-design-director.md` | `character_design` | Cast, silhouettes, emotion/action range, style anchors |
| Rig Plan Director | `pipelines/character-animation/rig-plan-director.md` | `rig_plan` | Parts, pivots, layer order, constraints, pose library |
| Scene Director | `pipelines/character-animation/scene-director.md` | `scene_plan` | Character actions, scene feasibility, complexity budget |
| Asset Director | `pipelines/character-animation/asset-director.md` | `assets` | Character parts, backgrounds, props, audio, previews |
| Edit Director | `pipelines/character-animation/edit-director.md` | `edit` | Timed action timeline, holds, anticipation, gesture/audio sync |
| Compose Director | `pipelines/character-animation/compose-director.md` | `compose` | Remotion/HyperFrames render routing and character QA evidence |
| Publish Director | `pipelines/character-animation/publish-director.md` | `publish` | Character-forward packaging, poster frame, limitation notes |

### Documentary Montage Pipeline (`pipelines/documentary-montage/`) — v1.0 beta

| Skill | File | Stage | Key Capabilities |
|-------|------|-------|-----------------|
| **Executive Producer** | `pipelines/documentary-montage/executive-producer.md` | `all` | **Retrieval-first montage orchestration and Remotion runtime constraint** |
| Idea Director | `pipelines/documentary-montage/idea-director.md` | `idea` | Thematic question, mood, runtime lock, brief artifact |
| Scene Director | `pipelines/documentary-montage/scene-director.md` | `scene_plan` | Slot descriptions and provider queries for retrieval |
| Asset Director | `pipelines/documentary-montage/asset-director.md` | `assets` | Corpus/CLIP or direct-search clip sourcing and assignment |
| Edit Director | `pipelines/documentary-montage/edit-director.md` | `edit` | Juxtaposition, rhythm, transitions, music sync |
| Compose Director | `pipelines/documentary-montage/compose-director.md` | `compose` | Remotion-only render, grade smoothing, output proof |

## Meta Skills

Cross-cutting skills that apply to all pipelines:

| Skill | File | Purpose |
|-------|------|---------|
| Animation Runtime Selector | `meta/animation-runtime-selector.md` | Render-runtime and Layer 3 animation-routing decisions |
| Capability Extension | `meta/capability-extension.md` | Guardrails for project scripts, custom playbooks, new skills, and tool wrappers |
| Onboarding | `meta/onboarding.md` | First-interaction greeting, capability discovery, starter prompts |
| Creative Intake | `meta/creative-intake.md` | Targeted pre-research questions and verbatim user-request capture |
| Video Reference Analyst | `meta/video-reference-analyst.md` | Reference-video analysis and reference-vs-source-footage routing |
| GenUI Interaction | `meta/genui-interaction.md` | A2UI/CopilotKit GenUI sessions, ui_session_response review, compatibility surface fallback, and CLI fallback |
| Reviewer | `meta/reviewer.md` | Self-review protocol after every stage |
| Checkpoint Protocol | `meta/checkpoint-protocol.md` | When/how to checkpoint and request human approval |
| Skill Creator | `meta/skill-creator.md` | Dynamically create new skills during pipeline runs |
| Animation Runtime Selector | `meta/animation-runtime-selector.md` | Choose render runtime + animation library per scene |
| Bespoke Composition (Atelier) | `meta/bespoke-composition.md` | Hand-author a composition from scratch (hero work) — no stock scene-types; routes art-direction → motion principles → engine mechanics → atelier render |

## Style Playbooks

Style playbooks (`styles/*.yaml`) define visual language, typography, motion, audio, and asset generation constraints. They are validated against `schemas/styles/playbook.schema.json`.

| Playbook | Category | Mood | Best For |
|----------|----------|------|----------|
| `ad-brand` | custom | bold, narrative-driven | Ads, commercials, product campaigns |
| `anime-ghibli` | anime-illustration | warm, whimsical | Narrative animation, nature-led storytelling |
| `clean-professional` | motion-graphics | polished, trustworthy | Corporate, educational, SaaS |
| `flat-motion-graphics` | motion-graphics | energetic, bold | Social media, TikTok, startups |
| `minimalist-diagram` | whiteboard | focused, technical | Technical deep-dives, architecture |

Load via `styles/playbook_loader.py`: `load_playbook("clean-professional")`.
List all shipped and custom playbooks via `list_playbooks()`.

## Installed Agent Skills (Layer 3)

Agent skills are declared in `.agents/components.yaml`, pinned in
`.agents/components.lock.json`, and materialized into `.agents/skills/` with:

```bash
python -m lib.agent_components install --profile default --frozen
```

Use `python -m lib.agent_components outdated` to check Git-backed third-party
skills against their upstream refs, and `python -m lib.agent_components update
<component>` to refresh a selected component lock. Skills under
`.agents/local/skills/` are first-party, locally edited, or pending upstream
path verification.

Claude Code compatibility paths are generated in `.claude/skills/`.

| Category | Installed Skills | Source |
|----------|-----------------|--------|
| **Video Composition** | `remotion-best-practices`, `remotion`, `hyperframes` (router), `hyperframes-core`, `hyperframes-creative`, `hyperframes-media`, `hyperframes-animation`, `hyperframes-cli`, `hyperframes-registry`, `media-use`, `motion-graphics`, `music-to-video`, `remotion-to-hyperframes`, `website-to-video` | `remotion-dev/skills`, `digitalsamba/claude-code-video-toolkit`, `heygen-com/hyperframes` (vendored v0.7.17, see `.agents/skills/hyperframes/PROVENANCE.md`) |
| **Video Processing** | `ffmpeg`, `video-toolkit` | `digitalsamba/claude-code-video-toolkit` |
| **TTS & Audio** | `text-to-speech`, `speech-to-text`, `music`, `sound-effects`, `elevenlabs`, `agents`, `setup-api-key` | `elevenlabs/skills`, `digitalsamba/claude-code-video-toolkit` |
| **Image Generation** | `flux-best-practices`, `bfl-api`, `grok-media` | `black-forest-labs/skills`, local Video Production Buddy skill |
| **Stock Media** | `stock-sourcing` | Local Video Production Buddy skill |
| **Text Generation** | `text-generation` | Local Video Production Buddy skill |
| **Math Animation** | `manimce-best-practices`, `manimgl-best-practices`, `manim-composer` | `adithya-s-k/manim_skill` |
| **3D Graphics** | `threejs-animation`, `threejs-fundamentals`, `threejs-geometry`, `threejs-interaction`, `threejs-lighting`, `threejs-loaders`, `threejs-materials`, `threejs-postprocessing`, `threejs-shaders`, `threejs-textures` | `cloudai-x/threejs-skills` |
| **Diagrams** | `beautiful-mermaid`, `d3-viz` | `intellectronica/agent-skills`, `davila7/claude-code-templates` |
| **Animation** | `framer-motion`, `lottie-bodymovin` | `pproenca/dot-skills`, `dylantarre/animation-principles` |
| **Design** | `tailwind-design-system`, `web-design-guidelines`, `vercel-react-best-practices`, `vercel-composition-patterns` | `wshobson/agents`, `vercel-labs/agent-skills` |
| **AI Video (HeyGen)** | `heygen`, `avatar-video`, `create-video`, `faceswap`, `ai-video-gen`, `video-download`, `video-edit`, `video-translate`, `video-understand`, `visual-style` | `heygen-com/skills` |
| **AI Video (Premium)** | `seedance-2-0` — preferred premium default (cinematic, trailer, multi-shot, lip-sync, synced audio); accessed via `seedance_video` (fal.ai) or `heygen_video` Avatar Shots | Local Video Production Buddy skill |
| **Infrastructure** | `acestep`, `ltx2`, `playwright-recording` | `digitalsamba/claude-code-video-toolkit` |
