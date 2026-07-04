# Video Production Buddy Architecture

> Last updated: 2026-06-16 | Derived from code exploration, not prior documentation.

Video Production Buddy is an **agent-orchestrated video production platform**. An LLM coding assistant (Claude Code, Cursor, Copilot, etc.) acts as the orchestrator — reading pipeline manifests, following skill instructions, calling Python tools, and checkpointing state. There is no runtime Python orchestrator; the agent _is_ the control plane.

---

## High-Level Flow

```
User gives topic/idea
        |
        v
Agent reads pipeline manifest (YAML)
        |
        v
For each stage:
   1. Agent reads stage-director skill (Markdown)
   2. Agent calls Python tools via tool registry
   3. Agent writes checkpoint (JSON) with artifacts
   4. Agent self-reviews using meta/reviewer skill
   5. Human approval gate (if configured, optionally through GenUI)
        |
        v
Final video output
```

---

## Repository Layout

```
Video Production Buddy/
├── lib/                    # Core runtime infrastructure (Python)
│   ├── config_model.py     # Pydantic config: LLM, budget, checkpoint, output, paths
│   ├── checkpoint.py       # Pipeline state persistence & stage transitions
│   ├── pipeline_loader.py  # YAML manifest loading & validation
│   ├── media_profiles.py   # Platform-specific render profiles (YouTube, TikTok, etc.)
│   ├── genui/              # Visual configs, A2UI/json-render specs, response helpers
│   ├── env_loader.py       # .env variable management
│   └── providers/          # (Reserved for future provider abstractions)
│
├── tools/                  # Registry-discovered Python tool implementations
│   ├── base_tool.py        # Abstract base class — the tool contract
│   ├── tool_registry.py    # Auto-discovery singleton registry
│   ├── cost_tracker.py     # Budget governance (estimate → reserve → reconcile)
│   ├── analysis/           # Transcription, scene detection, frame sampling, video understanding
│   ├── audio/              # TTS (ElevenLabs, OpenAI, Piper), music gen, mixing, enhancement
│   ├── avatar/             # Talking head animation, lip sync
│   ├── capture/            # Screen capture selectors and recorder adapters
│   ├── character/          # Local character specs, rigs, poses, timelines, QA
│   ├── compliance/         # Deterministic structural compliance checks
│   ├── enhancement/        # Upscale, bg removal, face enhance/restore, color grading
│   ├── graphics/           # Image gen (FLUX, GPT Image, Recraft, local diffusion), stock, diagrams, code snippets, math animation
│   ├── publishers/         # (Reserved)
│   ├── subtitle/           # SRT/VTT generation from timestamps
│   ├── text/               # Optional billed LLM chat providers for ad-hoc text sub-tasks
│   ├── validation/         # Cross-artifact governance validators
│   └── video/              # Video generation providers, composition runtimes, stitching, trimming
│
├── pipeline_defs/          # YAML pipeline manifests
├── knowledge/              # Curated ad-video professional knowledge cards
├── schemas/                # JSON Schema definitions for validation
│   ├── artifacts/          # 34 artifact schemas (brief -> publish_log plus governance artifacts)
│   ├── checkpoints/        # Checkpoint state schema
│   ├── pipelines/          # Pipeline manifest schema
│   ├── styles/             # Style playbook schema
│   └── tools/              # Tool-specific schemas
│
├── skills/                 # Layer 2: Video Production Buddy-specific agent instructions
│   ├── core/               # FFmpeg, Remotion, WhisperX, color grading skills
│   ├── creative/           # Video editing, enhancement, data viz, prompt engineering
│   ├── meta/               # reviewer, checkpoint-protocol, skill-creator
│   └── pipelines/          # Per-pipeline stage-director skills
│
├── .agents/components.yaml # Layer 3 dependency manifest
├── .agents/local/skills/   # Tracked first-party / locally edited Layer 3 sources
├── .agents/skills/         # Generated Layer 3 compatibility target
├── styles/                 # Visual style playbooks (YAML) + loader
├── music_library/          # Optional user-provided royalty-free tracks (gitignored)
├── remotion-composer/      # Node.js/React — Remotion video composition renderer
├── tests/                  # Contract tests, QA integration tests, eval harness
├── docs/                   # Best-practices guides, session handoffs, audits
└── config.yaml             # Global runtime configuration
```

---

## Core Architectural Principles

### 1. Agent-First Orchestration

There is **no Python orchestrator**. The LLM agent:
- Reads the pipeline manifest to know the stage order
- Reads each stage-director skill for detailed instructions
- Calls tools, evaluates results, makes creative decisions
- Writes checkpoints to persist state between stages

Python provides **tools and persistence only**. All intelligence lives in skill instructions (Markdown) and pipeline manifests (YAML).

### 2. No Runtime LLM Orchestrator

The coding assistant running in the user's IDE _is_ the LLM control plane.
Video Production Buddy does not autonomously route stages through a Python LLM
orchestrator, and pipeline manifests must not auto-wire general chat models into
stage tool lists. Most generation tools call domain-specific APIs directly
(ElevenLabs, fal.ai, HeyGen, etc.).

`tools/text/` is the explicit exception: it contains optional billed chat
provider tools (`qwen_chat`, `minimax_chat`) for standalone ad-hoc text
sub-tasks such as script polishing, translation, and summarization. Before using
those tools, the agent must announce the provider/model, surface cost or billing
implications, get user approval, and log any resulting governance decision when
the output changes canonical artifacts.

### 3. Dual-Provider Support

Every capability must support both **API providers** (cloud, paid) and **local/open-source alternatives** (free, GPU-dependent). The selector pattern enforces this by routing to whatever is available.

### 4. GenUI Is an Interaction Layer, Not an Orchestrator

Video Production Buddy can present any substantive human interaction round as a local
browser GenUI surface when linear chat is insufficient. The standard browser
path is **GenUI**: an A2UI/CopilotKit React renderer catalog plus AG-UI
event/session transport, backed by an agent-owned `ui_interaction_journal`,
stage-aware routing policies, fixed workspace contracts, durable
decision/resume metadata, operation events, cursor-addressable `events.jsonl`
replay, `/events` streaming, a `/session.json` status document,
response-only `/draft` autosave, conflict-safe source artifact hash checks, and
a project cockpit snapshot.
Before each substantive human interaction, the agent decides whether linear
chat is sufficient. When a round needs visual
demonstration, media review, side-by-side comparison, multi-axis selection,
many options, or structured revision capture, the agent uses
`genui_interaction` to route and synthesize a dynamic `ui_session_config`.
`genui_session` compiles the config into renderer-only `view_spec.json`; the
A2UI/CopilotKit catalog renders gate workspaces, media review rooms, cockpit,
status sessions, and product interaction panels; the server validates the submitted
`ui_session_response`; `genui_session` can report status, prepare replay,
validate responses, and summarize submissions; then the agent writes canonical
artifacts itself. Predecessor session wire artifacts remain compatible, and
GenUI `genui_surface` + `json-render` remains an explicit compatibility
fallback.

Media review rooms materialize safe project-relative review assets from
`asset_manifest`, `product_identity_reference`, `render_report`, and
`final_review` into `/media/...` refs before rendering. The same materialization
normalizes explicit paths under `renders/`, `assets/`, `reference_assets/`,
`media/`, or `outputs/`. This keeps sample clips, generated video clips,
audio/music, product references, concept images, keyframes, and final renders
inside the GenUI review surface; manual folder opening is fallback only when the
local browser path fails or the user declines it.

GenUI does not change stage order, provider/runtime governance, review policy,
checkpoint policy, or canonical artifact ownership. The local surface server must
not write `enriched_brief`, `production_proposal`, `decision_log`, or
checkpoints directly. `view_spec.json` is not a pipeline artifact and does not
make artifact bindings executable. `ui_interaction_journal` is agent-owned
routing/session lifecycle state and is never written by the browser.

---

## The Tool System

Canonical capability packages are `tools/analysis/`, `tools/audio/`,
`tools/avatar/`, `tools/capture/`, `tools/character/`, `tools/compliance/`,
`tools/enhancement/`, `tools/graphics/`, `tools/interaction/`,
`tools/publishers/`, `tools/subtitle/`, `tools/text/`, `tools/validation/`,
and `tools/video/`.

### BaseTool Contract

All tools inherit from `BaseTool` (ABC) and declare:

| Field | Purpose |
|-------|---------|
| `name`, `version` | Identity |
| `tier` | CORE, VOICE, ENHANCE, GENERATE, SOURCE, ANALYZE, PUBLISH |
| `capability` | What it does (e.g., `tts`, `image_generation`, `video_post`) |
| `provider` | Which service (e.g., `elevenlabs`, `ffmpeg`, `selector`) |
| `runtime` | LOCAL, LOCAL_GPU, API, HYBRID |
| `stability` | EXPERIMENTAL, BETA, PRODUCTION |
| `dependencies` | Required binaries (`cmd:ffmpeg`), env vars (`env:ELEVENLABS_API_KEY`), Python packages (`python:torch`) |
| `input_schema`, `output_schema` | JSON Schema for inputs/outputs |
| `fallback_tools` | Ordered fallback chain |
| `agent_skills` | Links to Layer 3 knowledge skills |
| `resource_profile` | CPU, RAM, VRAM, disk, network requirements |
| `retry_policy` | Max retries, backoff strategy |

**Required method:** `execute(inputs) -> ToolResult`

`ToolResult` carries: `success`, `data`, `artifacts` (file paths), `error`, `cost_usd`, `duration_seconds`, `seed`, `model`.

### Tool Registry

`ToolRegistry` is a singleton that auto-discovers all `BaseTool` subclasses via `pkgutil.walk_packages()`. No manual registration.

Key queries:
- `get_by_capability("tts")` — all TTS tools
- `get_by_provider("elevenlabs")` — all ElevenLabs tools
- `get_available()` — tools whose dependencies are satisfied
- `find_fallback("elevenlabs_tts")` — resolve fallback chain
- `support_envelope()` — full capability report for agent consumption
- `provider_menu_summary()` — compact user-facing preflight menu with provider counts, selectable model choices, and composition runtime availability
- `gpu_required_tools()`, `network_required_tools()`

### Selector Pattern

Selector tools abstract multi-provider capabilities:

| Selector | Capability | How selection works |
|----------|-----------|---------------------|
| `tts_selector` | Text-to-speech | Ranks discovered providers by task fit, quality, control, reliability, cost, latency, and continuity |
| `image_selector` | Image generation | Ranks discovered providers from the live registry; no hardcoded provider order |
| `video_selector` | Video generation | Ranks discovered providers from the live registry; user preference is respected when explicitly provided |
| `music_selector` | Music generation | Ranks discovered music providers and honors `.env` provider/model preferences |
| `text_selector` | Optional text generation | Routes approved billed text helper calls to configured text providers |
| `transcription_selector` | Speech-to-text | Ranks discovered transcription providers and honors `.env` provider/model preferences |

Selectors route based on: user preference when explicitly set, then scored ranking across available providers. They adapt input schemas between providers transparently.

### Tool Inventory by Category

The live inventory is intentionally registry-driven. Use:

```bash
python -c "from tools.tool_registry import registry; import json; registry.discover(); print(json.dumps(registry.provider_menu_summary(), indent=2))"
```

For user-facing model setup, use `make models-list` for a readable view, then
copy `.env.example` to `.env` and set optional `VPB_*` model defaults beside
the matching API keys. Validate local settings with
`make models-check ENV_FILE=.env`.

Representative capability families:

| Capability | Examples |
|------------|----------|
| Analysis and transcription | `transcription_selector`, `transcriber`, `qwen_asr`, `scene_detect`, `frame_sampler`, `video_analyzer`, `video_understand`, `visual_qa`, `audio_probe` |
| TTS and audio | `tts_selector`, `cosyvoice_tts`, `doubao_tts`, `elevenlabs_tts`, `google_tts`, `minimax_tts`, `openai_tts`, `piper_tts`, `audio_mixer`, `audio_enhance` |
| Music | `music_selector`, `music_gen`, `minimax_music`, `suno_music`, plus search helpers such as `pixabay_music` |
| Image generation and graphics | `image_selector`, `flux_image`, `grok_image`, `google_imagen`, `openai_image`, `recraft_image`, `wanx_image`, `local_diffusion`, stock image tools, `code_snippet`, `diagram_gen`, `math_animate` |
| Video generation | `video_selector`, `wan_video_api`, `seedance_video`, `grok_video`, `heygen_video`, `higgsfield_video`, `veo_video`, `kling_video`, `runway_video`, `minimax_video`, local GPU tools, and stock video tools |
| Video post-production | `video_compose`, `hyperframes_compose`, `video_stitch`, `video_trimmer`, `auto_reframe`, green-screen tools, silence cutting, showcase cards |
| Text generation | `text_selector`, `qwen_chat`, `minimax_chat` for optional ad-hoc script polishing, translation, summarization, and other explicitly routed billed text sub-tasks |
| Subtitles and captions | `subtitle_gen`, `remotion_caption_burn`, and the `tools.audio.subtitle_aligner` forced-alignment utility |
| Validation and compliance | `provider_consistency_check`, `scene_fidelity_check`, `runtime_consistency_check`, `hallucination_contract_check`, `product_identity_consistency_check`, `sample_product_visibility_check`, `compliance_check` |
| Interaction and planning support | `genui_interaction`, `genui_session`, `genui_surface`, `ad_knowledge_retriever`, source/clip acquisition tools, screen capture selectors, character-animation tools |

---

## Pipeline System

### Pipeline Manifests

Each pipeline is a YAML file in `pipeline_defs/` defining:

```yaml
name: animated-explainer
version: "2.0"
category: generated          # talking_head | generated | hybrid | screen_recording | animation | cinematic | custom
default_checkpoint_policy: guided

orchestration:
  mode: executive-producer
  skill: pipelines/explainer/executive-producer
  budget_default_usd: 2.00
  max_revisions_per_stage: 3

compatible_playbooks:
  - clean-professional
  - flat-motion-graphics

stages:
  - name: research
    skill: pipelines/explainer/research-director
    produces: [research_brief]
    tools_available: []
    checkpoint_required: false
    human_approval_default: false
    review_focus: [...]
    success_criteria: [...]
  # ... through publish
```

### Available Pipelines

| Pipeline | Category | Description |
|----------|----------|-------------|
| `ad-video` | custom | Ad/commercial pipeline with intake, strategic brief enrichment, product identity governance, sample approval, hallucination checks, and publish packaging |
| `animated-explainer` | generated | AI-produced explainer with research, narration, visuals, music |
| `animation` | animation | Motion graphics, kinetic typography |
| `avatar-spokesperson` | custom | Avatar-driven presenter videos |
| `character-animation` | animation | Local rigged cartoon characters with SVG rigs, pose libraries, GSAP timelines, and HyperFrames rendering |
| `cinematic` | cinematic | Trailer, teaser, mood-driven edits |
| `clip-factory` | custom | Batch short-form clips from long source |
| `documentary-montage` | documentary | Documentary-style montage from source media and supporting assets |
| `framework-smoke` | custom | Minimal smoke test for framework validation |
| `hybrid` | hybrid | Source footage + AI-generated support visuals |
| `localization-dub` | custom | Subtitle, dub, and translate existing video |
| `podcast-repurpose` | custom | Podcast highlights to video |
| `screen-demo` | screen_recording | Software screen recordings and walkthroughs |
| `talking-head` | talking_head | Footage-led speaker videos |

### Standard Stage Progression

The canonical top-level stage progression is:

```
research → proposal → script → scene_plan → assets → edit → compose → publish
```

Pipelines should use those names for top-level stages when the work fits the
common model. Specialized governance should be expressed as `sub_stages` under
the nearest standard parent stage, not as a new top-level taxonomy. Stage and
sub-stage ids must be lowercase snake_case without dots. Dotted ids are
reserved for derived `<stage>.<sub_stage>` units emitted by manifest helpers and
used for checkpoint/resume behavior.

Each concrete stage:
1. Has a **stage-director skill** (Markdown instructions for the agent)
2. Declares **tools_available** (what the agent can call), when applicable
3. **Produces** one or more canonical artifacts, when applicable
4. Has **review_focus** criteria and **success_criteria**
5. Can require **human approval** before proceeding
6. Can own `sub_stages` whose child gates carry their own skills, artifacts,
   tools, review criteria, approvals, and checkpoint policy

For example, `ad-video` uses the common top-level flow and places its extra
governance under `research` and `proposal`:

```
research.intake -> research.brief_enrichment -> research.intelligence
-> proposal.bible -> proposal.idea -> proposal.technical_proposal
-> script -> scene_plan -> assets -> edit -> compose -> publish
```

The parent stages keep common orchestration comparable; the child gates preserve
the specialized business approvals and artifacts.

The manifest in `pipeline_defs/<pipeline>.yaml` is the source of truth for
stage order and canonical stage artifacts. Do not assume every pipeline ends in
`publish`; `documentary-montage`, for example, currently ends at `compose`.

### Project Workspaces and User Request Provenance

Production runs write canonical state under `projects/<project-id>/`. Before
research, planning, or paid generation, the agent records the user's original
instruction as `USER_PROMPT.md` and `artifacts/user_request.json` through
`lib.user_request.record_user_request(...)`. Later brief artifacts interpret
that source request; they do not replace it.

Generated media stays inside the project workspace:

```
projects/<project-id>/
├── USER_PROMPT.md
├── artifacts/      # Canonical JSON artifacts
├── reference_assets/
├── assets/
└── renders/
```

### Governed Ad-Video Architecture

The `ad-video` pipeline is a governed commercial-production flow, not a shorter
topic-to-video pipeline. Its manifest-owned stage order is:

```
research -> proposal -> script -> scene_plan -> assets -> edit -> compose -> publish
```

Its checkpointable execution gates are:

```
research.intake -> research.brief_enrichment -> research.intelligence
-> proposal.bible -> proposal.idea -> proposal.technical_proposal
-> script -> scene_plan -> assets -> edit -> compose -> publish
```

Key contract surfaces:

- `research.brief_enrichment`, `research.intelligence`, and `proposal.bible`
  establish the approved strategy before execution. `research.intelligence`
  retrieves curated producer doctrine through `ad_knowledge_retriever`;
  `production_bible` carries the truth
  contract, trend alignment, and professional-knowledge alignment that script
  and scene_plan must reference.
- `proposal.idea` selects the execution concept inside the approved bible.
- `proposal.technical_proposal` locks technical choices: `style_mode`,
  `render_runtime`, `product_reference_strategy`, audio/voice contract,
  subtitles, derivatives, budget, and `decision_log`. Runtime selection must
  consider both Remotion and HyperFrames when both are available.
- Product-visible ads require an approved `product_identity_reference` before
  product-visible generation, or an explicit user-approved `risk_accepted`
  waiver. Text-only product-visible generation is not a silent fallback.
- `assets` always has a sample approval sub-stage before full generation, then
  explicit asset and music review gates before compose.
- High-risk generated visuals carry scene-derived `hallucination_checks`; asset
  review records start/mid/end keyframes and per-check verdicts. Blocker `FLAG`
  verdicts cannot reach compose without regeneration, rerouting, or an approved
  waiver in `decision_log`.
- Compose and publish rerun cross-artifact checks such as
  `ad_video_planning_chain_check`, `provider_consistency_check`,
  `runtime_consistency_check`, `scene_fidelity_check`,
  `product_identity_consistency_check`, `sample_product_visibility_check`, and
  `hallucination_contract_check` where the manifest requires them.

The professional-knowledge layer lives in `knowledge/ad-video/`. Knowledge
cards cover 15 producer domains, including positioning, audience insight, hook
mechanics, narrative arc, emotional rhythm, visual rhetoric, proof logic,
product demo logic, platform format, commercial compliance, cinematography,
color theory, editing technique, sound design, and music direction.
`lib/ad_knowledge.py` retrieves these cards with field-weighted scoring, and
planning checks enforce trend/knowledge conflict detection plus cross-domain
co-presence where selected cards depend on each other.

---

## Checkpoint System

Checkpoints persist pipeline state as JSON in the project's `projects/` directory.

```json
{
  "version": "1.0",
  "project_id": "my-video",
  "stage": "script",
  "status": "completed",
  "timestamp": "2026-03-28T10:00:00Z",
  "checkpoint_policy": "guided",
  "human_approval_required": false,
  "human_approved": true,
  "artifacts": { "script": { ... } },
  "review": { ... },
  "cost_snapshot": { ... }
}
```

**Status values:** `in_progress` | `awaiting_human` | `completed` | `failed`

**Checkpoint policies:**
- `guided` — checkpoint at key creative stages, auto-proceed on mechanical ones
- `manual_all` — human approval at every stage
- `auto_noncreative` — auto-proceed unless stage is creative (assets, edit)

**Functions:** `write_checkpoint()`, `read_checkpoint()`, `get_latest_checkpoint()`, `get_completed_stages()`, `get_next_stage()`

### Artifact Schemas (34 types, all JSON-schema validated)

| Artifact | Stage | Contains |
|----------|-------|----------|
| `research_brief` | research | Landscape analysis, data points, audience insights, angles |
| `proposal_packet` | proposal | Concept options, production plan, cost estimates, approval gate |
| `brief` | idea | Title, hook, key points, tone, style, platform, duration |
| `script` | script | Timestamped sections with enhancement cues, pronunciation guides |
| `scene_plan` | scene_plan | Scene definitions with type, description, timing |
| `asset_manifest` | assets | Generated assets with path, source tool, scene association |
| `edit_decisions` | edit | Editorial cuts with in/out timings |
| `render_report` | compose | Output metadata (format, resolution, duration) |
| `publish_log` | publish | Platform publication entries with status |
| `review` | (any) | Reviewer feedback and approval records |
| `cost_log` | (any) | Budget tracking entries |
| `decision_log` | (any) | Governance decisions such as approved runtime/provider substitutions |
| `visual_need_assessment` | human gate | GenUI dynamic routing decision with stage policy, schema strategy, mode, reasons, UI primitives, confidence, and fallback |
| `ui_interaction_journal` | human gate | GenUI agent-owned journal of CLI-vs-browser routing, session lifecycle, response validation, replay/status state, event/session URLs, pending responses, stale sessions, and fallback reasons |
| `ui_session_config` | human gate | GenUI/session-contract A2UI session surfaces, fixed workspace contracts, durable decision/resume metadata, operation events, media refs, issue lifecycle, trace refs, revision capture, approval contract, source hashes, draft policy, and framework metadata |
| `ui_session_response` | human gate | Submitted GenUI/session-contract values, resume decisions, review completion status, conflict status, timecoded annotations, issue IDs, revision patches, approval attestations, interaction evidence, routing id, evidence status, and bounded event summary pending agent validation |
| `ui_surface_config` | human gate | GenUI compatibility workspace/cockpit blocks, media refs, artifact refs, trace refs, revision capture, approval contract, and renderer-only visual hints |
| `ui_surface_response` | human gate | Submitted GenUI compatibility values, annotations, selected refs, revision patches, approval attestations, and bounded event summary pending agent validation |
| `user_request` | research.intake | Original user request captured for project provenance |
| `intake_brief` | research.intake | Research-direction fields for ad/commercial workflows |
| `enriched_brief` | research.brief_enrichment | Structured worksheet expanding sparse ad briefs before strategy |
| `intelligence_brief` | research.intelligence | Category, audience, and competitive insight for ad strategy |
| `production_bible` | proposal.bible | Approved ad strategy, truth contract, motif, audio, and compliance contract |
| `idea_options` | proposal.idea | Execution concepts constrained by an approved production bible |
| `production_proposal` | proposal.technical_proposal | Ad technical plan, runtime, audio, visual, budget, and variants |
| `product_identity_reference` | assets | Approved visual reference strategy for product-visible ads |
| `character_design` | character_design | Character specifications for local rigged animation |
| `rig_plan` | rig_plan | SVG rig structure, parts, pivots, and animation constraints |
| `pose_library` | rig_plan | Reusable poses/action cycles for character animation |
| `action_timeline` | scene_plan/assets | Timed character actions compiled from scene intent |
| `source_media_review` | preplanning | Source-media suitability and constraints before planning |
| `final_review` | compose | Final self-review before presenting a render |
| `character_qa_report` | compose | Character-animation schema, rig, pose, and timeline QA |
| `video_analysis_brief` | reference input | External/reference video analysis carried into planning |

---

## Budget Governance

The `CostTracker` enforces spending controls across the pipeline.

### Lifecycle

```
estimate(tool, operation, $) → entry_id
        |
reserve(entry_id)          # locks budget
        |
reconcile(entry_id, $)     # records actual spend
```

### Budget Modes

| Mode | Behavior |
|------|----------|
| `observe` | Track costs, no enforcement |
| `warn` | Log warnings on overruns, allow execution |
| `cap` | Reject operations that exceed remaining budget |

### Controls
- **Total budget** (default: $10.00)
- **Reserve holdback** (default: 10%) — kept as safety margin
- **Single-action approval threshold** (default: $0.50) — pause for approval above this
- **New paid tool approval** — first-time use of any paid tool requires confirmation
- Persists to `cost_log.json` per project

---

## 3-Layer Knowledge Architecture

```
Layer 3: .agents/skills/          Generated external technology knowledge skills
         "How the technology works"    FFmpeg, ElevenLabs API, FLUX, Remotion, Three.js, etc.
              ^
              | agent_skills[] references
              |
Layer 2: skills/                  Video Production Buddy conventions
         "How this project uses the tech"  Pipeline integration, quality checklists, artifact mappings
              ^
              | stage skill references
              |
Layer 1: tools/ + pipeline_defs/  Executable capabilities + orchestration definitions
         "What exists and when to use it"  BaseTool contracts, pipeline manifests
```

Each tool's `agent_skills[]` field links Layer 1 to Layers 2 and 3. For example:
- `video_compose.agent_skills = ["remotion-best-practices", "remotion", "ffmpeg"]`
- `tts_selector.agent_skills = ["text-to-speech", "elevenlabs", "doubao-tts"]`

Layer 3 component dependencies are declared in `.agents/components.yaml`, pinned
in `.agents/components.lock.json`, and materialized with
`python -m lib.agent_components install --profile default --frozen`.

---

## Configuration

### config.yaml

```yaml
llm:
  provider: anthropic
  model: null
  temperature: 0.7
  max_tokens: 4096

budget:
  mode: warn
  total_usd: 10.00
  reserve_pct: 0.10
  single_action_approval_usd: 0.50
  require_approval_for_new_paid_tool: true

checkpoint:
  policy: guided
  storage_dir: projects

output:
  default_format: mp4
  default_codec: libx264
  default_audio_codec: aac
  default_resolution: 1920x1080
  default_fps: 30
  default_crf: 23

paths:
  pipeline_dir: pipeline_defs
  library_dir: lib
  styles_dir: styles
  skills_dir: skills
  output_dir: projects
```

All config is validated via Pydantic models in `lib/config_model.py`.

### Environment Variables (.env)

| Variable | Used By | Purpose |
|----------|---------|---------|
| `ELEVENLABS_API_KEY` | elevenlabs_tts, music_gen | TTS, music, sound effects |
| `OPENAI_API_KEY` | openai_tts, openai_image | TTS fallback, GPT Image 2 |
| `XAI_API_KEY` | grok_image, grok_video | Grok image editing/generation, Grok video generation |
| `FAL_KEY` / `FAL_AI_API_KEY` | flux_image, recraft_image, seedance_video, kling_video, veo_video | fal.ai hosted image/video models |
| `DASHSCOPE_API_KEY` | cosyvoice_tts, qwen_asr, wan_video_api, wanx_image, qwen_chat, qwen_vl | Alibaba Cloud Bailian / DashScope — Qwen3.7/CosyVoice TTS, Qwen ASR, HappyHorse/Wan video, Wanxiang image, Qwen LLM chat, Qwen-VL vision |
| `DOUBAO_SPEECH_API_KEY` + `DOUBAO_SPEECH_VOICE_TYPE` | doubao_tts | Volcengine Doubao Speech TTS and default voice |
| `HEYGEN_API_KEY` | heygen_video | Multi-provider video generation |
| `PEXELS_API_KEY` | pexels_image, pexels_video | Stock media |
| `PIXABAY_API_KEY` | pixabay_image, pixabay_video | Stock media |
| `UNSPLASH_ACCESS_KEY`, `COVERR_API_KEY`, `VIDEVO_API_KEY`, `NASA_API_KEY`, `NARA_API_KEY`, `POND5_API_KEY` | source/clip acquisition | Optional stock-source search keys and higher-rate public-media access |
| `FREESOUND_API_KEY` | freesound_music | Freesound music and sound search |
| `GOOGLE_API_KEY` / `GEMINI_API_KEY` | google_imagen, google_tts | Google Gemini/Imagen images, Google Cloud TTS |
| `RUNWAY_API_KEY` / `RUNWAYML_API_SECRET` | runway_video | Runway direct video generation |
| `REPLICATE_API_TOKEN` | seedance_replicate | Replicate-hosted Seedance video |
| `HIGGSFIELD_API_KEY` + `HIGGSFIELD_API_SECRET` / `HIGGSFIELD_KEY` | higgsfield_video | Higgsfield multi-model video |
| `MINIMAX_API_KEY` | minimax_music, minimax_video, minimax_tts, minimax_chat | MiniMax native platform — Music 2.6, Hailuo 2.3 video, Speech 2.8 TTS, MiniMax-M3 chat. Set `MINIMAX_API_BASE=https://api.minimax.io/v1` for the overseas host (default is the China-mainland `api.minimaxi.com`). |
| `SUNO_API_KEY` | suno_music | Suno music generation |
| `VPB_*_PROVIDER`, `VPB_*_MODEL`, `VPB_*_ALLOWED_PROVIDERS` | selector tools | Optional local provider/model defaults and provider shortlists in `.env`, copied from `.env.example`; examples include `VPB_VIDEO_GENERATION_MODEL`, `VPB_TTS_MODEL`, and `VPB_VIDEO_GENERATION_ALLOWED_PROVIDERS` |
| `MODAL_LTX2_ENDPOINT_URL` | ltx_video_modal | Self-hosted LTX-2 |
| `VIDEO_GEN_LOCAL_ENABLED` | local video tools | Enable local GPU generation |
| `VIDEO_GEN_LOCAL_MODEL` | wan, hunyuan, ltx, cogvideo | Select local model |
| `HF_TOKEN` | transcriber | Optional HuggingFace token for speaker diarization |
| `SADTALKER_PATH`, `WAV2LIP_PATH` | talking_head, lip_sync | Local avatar/lip-sync repository locations |
| `VIDEO_PRODUCTION_BUDDY_CACHE_DIR`, `VIDEO_PRODUCTION_BUDDY_CACHE_MAX_GB`, `SUBTITLE_ALIGNER_DEVICE`, `VPB_ALLOW_BROWSER_OPEN` | cache, subtitle alignment, and GenUI browser utilities | Optional local runtime tuning |

---

## Visual Style System

Style playbooks in `styles/` define visual language for pipelines:

- `ad-brand.yaml` — Commercial/product-campaign look with CTA emphasis
- `anime-ghibli.yaml` — Warm anime illustration for narrative animation
- `clean-professional.yaml` — Corporate, polished look
- `flat-motion-graphics.yaml` — Modern flat design
- `minimalist-diagram.yaml` — Technical, minimal diagrams

Loaded by `styles/playbook_loader.py`. Each pipeline declares `compatible_playbooks` in its manifest. Validated against `schemas/styles/playbook.schema.json`.

---

## Media Profiles

Platform-specific render configurations in `lib/media_profiles.py`:

| Profile | Resolution | Aspect | Notes |
|---------|-----------|--------|-------|
| `youtube_landscape` | 1920x1080 | 16:9 | Standard YouTube |
| `youtube_4k` | 3840x2160 | 16:9 | 4K YouTube |
| `youtube_shorts` | 1080x1920 | 9:16 | Max 60s |
| `instagram_reels` | 1080x1920 | 9:16 | Max 90s |
| `instagram_feed` | 1080x1080 | 1:1 | Square |
| `tiktok` | 1080x1920 | 9:16 | Vertical |
| `linkedin` | 1920x1080 | 16:9 | Landscape |
| `cinematic` | 2560x1080 | 21:9 | Ultrawide |

Each profile specifies codec, audio codec, CRF, pixel format, max file size, max duration, and caption format. `ffmpeg_output_args(profile)` generates the corresponding FFmpeg flags.

---

## Composition Runtimes

Video Production Buddy has a multi-runtime composition layer. Three engines live behind `video_compose`, chosen at proposal and locked in `edit_decisions.render_runtime`:

### Remotion (React-based)

A standalone Node.js/React subproject in `remotion-composer/` using [Remotion](https://www.remotion.dev/).

- **React 18** + **Remotion 4.0** + **TypeScript 5.3**
- Handles the existing scene-component stack (`text_card`, `stat_card`, charts, captions, `TalkingHead`, `CinematicRenderer`)
- Dependencies are locked with `pnpm-lock.yaml`; use `make install-remotion` or `cd remotion-composer && npx --yes pnpm install --frozen-lockfile`
- Scripts: `start` (studio), `build` (render), `upgrade`

### HyperFrames (HTML/CSS/GSAP)

Consumed via `npx hyperframes` (no monorepo checkout needed). Runtime floor: Node.js ≥ 22, FFmpeg, `npx`.

- Handles kinetic typography, product promos, launch reels, website-to-video, registry blocks, and SVG/GSAP character rigs
- Driver: `tools/video/hyperframes_compose.py` materializes a workspace under `projects/<name>/hyperframes/`, then runs `lint → validate → render`
- Layer 3 skills materialize at `.agents/skills/hyperframes*/` from the locked component manifest; Layer 2 guide at `skills/core/hyperframes.md`
- The `character-animation` pipeline uses HyperFrames as the production render package. Browser previews are QA/debug artifacts only, not the render path.

### FFmpeg (fallback / simple cuts)

- Handles pure concat/trim when no composition is needed
- Also handles subtitle burn-in as a post-hoc operation

`video_compose` reads `edit_decisions.render_runtime` and dispatches via `_render_via_hyperframes`, `_remotion_render`, or `_render_via_ffmpeg`. Silent runtime swaps are forbidden — the tool returns a structured blocker when the chosen runtime is unavailable. See `AGENT_GUIDE.md` → "Composition Runtimes (Inside video_compose)" and `skills/core/hyperframes.md` for the full decision matrix.

---

## Test Architecture

```
tests/
├── contracts/              # Phase 0-3: tool contract validation, schema checks, registry tests
├── qa/                     # Integration tests: TTS, image gen, music, audio mix, video compose/stitch, E2E
├── eval/                   # Golden scenario replay harness for regression testing
├── pipelines/              # Pipeline-level tests
├── tools/                  # Individual tool tests
└── styles/                 # Style playbook tests
```

**Contract tests** verify every tool satisfies the `BaseTool` contract: identity fields, schemas, dependency declarations, inheritance.

**QA tests** call real tools (with real APIs/binaries) and inspect output quality.

**Eval harness** (`tests/eval/replay_harness/`) replays golden scenarios with tolerance-based comparison for stochastic outputs.

---

## System Dependencies

**Required:**
- Python >= 3.10
- FFmpeg (used by ~15 tools)

**Optional (extend capabilities):**
- Node.js (for Remotion composer)
- GPU + CUDA (for local video/image generation)
- Piper (offline TTS)
- ManimCE (math animations)
- Mermaid CLI (diagram generation)

**Python packages:** pyyaml, pydantic, jsonschema, Pillow, requests, ag-ui-protocol (core); pytest, pytest-asyncio (dev); torch, torchvision, torchaudio (GPU)

---

## Key Design Decisions

1. **No runtime orchestrator** — The LLM agent reads YAML + Markdown and drives everything. This makes the system debuggable (just read the skill) and model-agnostic.

2. **Checkpoint-based resumption** — Any stage can fail and the pipeline resumes from the last checkpoint. No re-running completed stages.

3. **Schema-validated artifacts** — Every stage output is validated against a JSON Schema before the checkpoint is written. Prevents garbage propagation.

4. **Budget as a first-class concept** — Cost estimation before execution, budget reservation, and reconciliation. The agent cannot silently overspend.

5. **Selector pattern over hard-coded providers** — Capabilities degrade gracefully. Missing an API key? The selector falls through to the next provider or a local alternative.

6. **Skills over code for intelligence** — Creative decisions, quality checklists, review criteria, and prompt templates live in Markdown skills, not Python. This means the agent's behavior can be tuned by editing text files, not code.
