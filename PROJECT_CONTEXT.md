# Video Production Buddy - Shared Project Context

This is the single source of truth for project architecture and development
conventions. Durable cross-agent production conventions and current
project-local findings live in `project_profile/`. Platform-specific agent files
(AGENTS.md, CLAUDE.md, CURSOR.md, COPILOT.md) should point here and to
`AGENT_GUIDE.md` instead of duplicating this content.

## Identity

Video Production Buddy is an open-source, AI-orchestrated video production platform.

## Architecture: Instruction-Driven (Agent-First)

The AI agent IS the intelligence. Python exists only for tools and persistence. Everything else — orchestration, creative decisions, review, stage transitions — lives in instructions (YAML manifests + markdown skills) the agent follows.

```
Agent reads pipeline manifest (YAML) → reads stage director skill (MD)
→ uses tools (Python BaseTool) → self-reviews (meta skill)
→ checkpoints (Python utility) → presents to human for approval
```

**No Python orchestrator, no Python reviewer, no Python handlers.** The agent drives the pipeline.

## Source of Truth

- **Agent guide & contract:** `AGENT_GUIDE.md` (tool inventory, pipeline selection, stage agents, protocols)
- **Project profile:** `project_profile/` (repo-side cross-agent conventions, brand facts, provider/account findings, voice/subtitle findings; wins over agent-side private memory)
- **Skill index:** `skills/INDEX.md`
- **Tool registry:** `tools/tool_registry.py`
- **Pipeline manifests:** `pipeline_defs/`
- **Artifact schemas:** `schemas/artifacts/`
- **Curated knowledge:** `knowledge/ad-video/` for ad-video professional producer doctrine
- **Style playbooks:** `styles/*.yaml` (schema: `schemas/styles/playbook.schema.json`)
- **Stage director skills:** `skills/pipelines/<pipeline>/<stage>-director.md`
- **Meta skills:** `skills/meta/*.md` (reviewer, checkpoint-protocol, skill-creator)
- **Architecture deep-dive:** `docs/ARCHITECTURE.md`

## Knowledge Architecture (3 Layers)

```
Layer 1: tools/tool_registry.py     → "What tools exist" (runtime capabilities, status, cost)
Layer 2: skills/                    → "How Video Production Buddy uses them" (project conventions)
Layer 3: .agents/skills/            → "How the technology works" (generated from locked component deps)
```

Each tool's `agent_skills[]` field bridges Layer 1 → Layer 3. See `skills/INDEX.md` for the full mapping.
Layer 3 dependencies are declared in `.agents/components.yaml`, pinned in
`.agents/components.lock.json`, and materialized with
`python -m lib.agent_components install --profile default --frozen`.
Verified third-party components are Git-backed in the manifest, so
`python -m lib.agent_components outdated` reports upstream ref movement and
`python -m lib.agent_components update <component>` refreshes the lock. Keep
`.agents/local/skills/` for first-party skills, locally edited third-party
snapshots, or components whose upstream path has not been verified yet.

## Key Patterns

- **Pipeline state machine:** stage order is manifest-owned; top-level stages drive shared pipeline shape, and dotted child gates drive checkpointable specialized execution when a parent stage needs more governance
- **Canonical top-level stages:** `research -> proposal -> script -> scene_plan -> assets -> edit -> compose -> publish`; new pipelines should use these names where applicable and put domain-specific governance in `sub_stages`
- **Instruction-driven stages:** Each stage has a director skill (MD) that teaches the agent HOW
- **Pipeline manifests:** Declarative YAML defining stages, skills, tools, review focus, approval gates
- **Capability-first tool design:** Each major family should expose a selector tool plus explicit provider tools
  - Example: `tts_selector` + `cosyvoice_tts` / `doubao_tts` / `elevenlabs_tts` / `google_tts` / `minimax_tts` / `openai_tts` / `piper_tts`
  - Example: `video_selector` + `heygen_video` / `wan_video` / `hunyuan_video` / `ltx_video_local` / `ltx_video_modal` / `cogvideo_video`
  - Example: `music_selector` + `music_gen` / `minimax_music` / `suno_music`
  - Example: `text_selector` + `qwen_chat` / `minimax_chat` for approved billed helper calls
- **Style playbooks:** YAML defining visual language, typography, motion, audio, asset generation constraints
- **Artifacts are canonical:** `user_request`, `intake_brief`, `enriched_brief`, `intelligence_brief`, `production_bible`, `idea_options`, `production_proposal`, `script`, `scene_plan`, `asset_manifest`, `edit_decisions`, `render_report`, `publish_log`
- **Every tool inherits from `tools/base_tool.py`** (ToolContract)
- **Checkpoint policy** lives in pipeline manifest (`human_approval_default` per stage) + `skills/meta/checkpoint-protocol.md`
- **Reviewer** is a meta skill (`skills/meta/reviewer.md`), advisory, max 2 rounds
- **Cost tracker** (`tools/cost_tracker.py`) manages budget: estimate -> reserve -> reconcile
- **Canonical artifacts** validated against JSON schemas in `schemas/artifacts/`
- **GenUI interaction system:** dynamic local browser sessions for rounds where linear chat is insufficient; `genui_interaction` records every CLI-vs-browser decision in `ui_interaction_journal`, applies stage-aware policies and fixed workspace contracts for known gates, `genui_session` materializes A2UI/CopilotKit + AG-UI sessions, persists cursor-addressable `events.jsonl`, exposes `/events`, `/session.json`, and response-only `/draft`, checks source artifact hashes before resume, and supports status/replay/validate/summarize lifecycle modes. Sessions write `ui_session_response`, predecessor session artifacts remain compatible, `genui_surface`/`ui_surface_response` remains an explicit compatibility fallback, and the agent still writes canonical artifacts.

## Key Files

| File | Purpose |
|------|---------|
| `project_profile/README.md` | Authority and update rules for repo-side cross-agent production profile |
| `project_profile/conventions.md` | Profile index, memory mechanism, and profile changelog |
| `project_profile/agent_behavior.md` | Cross-agent explanation, verification, local UI, and closeout preferences |
| `project_profile/developer_workflow.md` | Repo-side audit, fix, git, generated-artifact, and identity-cleanup workflow rules |
| `project_profile/brand.md` | Active product identity, visual identity, and forbidden brand/IP usage |
| `project_profile/provider_findings.md` | Dated provider/account availability findings and verification commands |
| `project_profile/voice_and_subtitles.md` | Mandarin male voice routing and CJK subtitle rendering requirements |
| `project_profile/model_defaults.md` | Dated model/default observations and re-check commands |
| `project_profile/hyperframes.md` | HyperFrames CJK font packaging and video-heavy render findings |
| `project_profile/update_checklist.md` | Checklist for safe project-profile updates |
| `project_profile/migration_audit.md` | Record of migrated agent-side guidance and intentionally non-migrated local history |
| `docs/PR_REVIEW_GUIDE.md` | Review framework for PR architecture, provider, runtime, dependency, security, and docs risks |
| `config.yaml` | Global configuration |
| `.env.example` | User-facing template for API keys and optional `VPB_*` model defaults |
| `lib/config_model.py` | Runtime config loader (Pydantic) |
| `lib/model_settings_wizard.py` | User-facing model choice listing and `.env` model preference validation |
| `lib/checkpoint.py` | Checkpoint writer/reader |
| `lib/pipeline_loader.py` | Pipeline manifest loader + helpers |
| `lib/media_profiles.py` | Platform-specific render profiles |
| `styles/playbook_loader.py` | Style playbook loader + validator + design intelligence (color/type/a11y) |
| `tools/base_tool.py` | ToolContract base class |
| `tools/tool_registry.py` | Tool discovery and reporting, including provider/model preflight summaries |
| `tools/cost_tracker.py` | Budget governance |
| `lib/ad_knowledge.py` | Curated ad-video knowledge-card loading, validation, and deterministic retrieval |
| `lib/knowledge_alignment.py` | Checks that selected producer-knowledge refs reach script and scene_plan artifacts |
| `lib/genui/` | GenUI journal/lifecycle support plus session and compatibility-surface config validation, A2UI/json-render view-spec compilation, durable event logs, response-only draft state, local serving, and browser response helpers |
| `lib/genui/static/renderer/` | Built React A2UI/json-render browser bundle served by `genui_session` and `genui_surface` |
| `genui-renderer/` | Source package for the Video Production Buddy A2UI/CopilotKit product catalog plus json-render compatibility component catalog |
| `tools/interaction/genui_interaction.py` | Dynamic GenUI router for deciding whether linear chat is sufficient and synthesizing per-round visual interactions |
| `tools/interaction/genui_session.py` | GenUI A2UI session materializer/lifecycle tool; serves AG-UI + framework-backed UI and writes ui_session_response/draft state only |
| `tools/interaction/genui_surface.py` | GenUI compatibility gate workspace/project cockpit materializer; serves AG-UI + json-render UI and writes ui_surface_response only |
| `tools/analysis/ad_knowledge_retriever.py` | Local professional advertising knowledge retrieval for ad-video pre-production |
| `tools/compliance/compliance_check.py` | Deterministic structural compliance checks for `compliance_manifest` checkpoints (timing/presence/beat-mapping) |
| `tools/video/video_stitch.py` | Multi-clip assembly (stitch, spatial, validate, preview) |
| `tools/video/video_compose.py` | Runtime-aware composition orchestrator — routes to Remotion / HyperFrames / FFmpeg based on `edit_decisions.render_runtime` |
| `tools/video/hyperframes_compose.py` | HyperFrames runtime — workspace materialization, `hyperframes lint`/`validate`/`render`, FFmpeg floor check |
| `tools/character/character_animation.py` | Local character-animation tools — character specs, SVG rig plans, pose libraries, action timelines, HyperFrames packages, and QA reports |
| `lib/hyperframes_style_bridge.py` | Playbook → CSS custom properties + `DESIGN.md` bridge for HyperFrames workspaces |
| `remotion-composer/src/components/` | Remotion scene components and registry-backed scene types for deterministic zero-key demos |
| `.agents/components.yaml` + `.agents/components.lock.json` | Version-controlled Layer 3 component manifest and lockfile |
| `.agents/local/skills/` | Tracked first-party, locally edited, or not-yet-verified Layer 3 component sources |
| `.agents/skills/hyperframes*/` | Generated HyperFrames Layer 3 compatibility paths (authoring contract, CLI, registry, website-to-video) |
| `skills/core/hyperframes.md` | Layer 2 — when Video Production Buddy should pick HyperFrames vs Remotion, artifact → workspace mapping |
| `schemas/styles/playbook.schema.json` | Playbook schema v2 with design tokens (chart_palette, scale_system, weight_matrix, color_rules) |
| `tests/integration/` | Opt-in local runtime smoke tests for FFmpeg/browser/Node/HyperFrames behavior |

## Available Pipelines

| Pipeline | Manifest | Type |
|----------|----------|------|
| `talking-head` | `pipeline_defs/talking-head.yaml` | Footage-based |
| `animated-explainer` | `pipeline_defs/animated-explainer.yaml` | AI-generated |
| `screen-demo` | `pipeline_defs/screen-demo.yaml` | Screen-recording |
| `clip-factory` | `pipeline_defs/clip-factory.yaml` | Short-form batch extraction |
| `podcast-repurpose` | `pipeline_defs/podcast-repurpose.yaml` | Podcast repurposing |
| `cinematic` | `pipeline_defs/cinematic.yaml` | Cinematic edit |
| `animation` | `pipeline_defs/animation.yaml` | Animation-first |
| `ad-video` | `pipeline_defs/ad-video.yaml` | Ad/commercial orchestration with pre-production governance and approval gates |
| `character-animation` | `pipeline_defs/character-animation.yaml` | Local rigged character animation |
| `hybrid` | `pipeline_defs/hybrid.yaml` | Source-plus-support hybrid |
| `documentary-montage` | `pipeline_defs/documentary-montage.yaml` | Documentary montage assembly |
| `avatar-spokesperson` | `pipeline_defs/avatar-spokesperson.yaml` | Avatar presenter |
| `localization-dub` | `pipeline_defs/localization-dub.yaml` | Localization and dubbing |
| `framework-smoke` | `pipeline_defs/framework-smoke.yaml` | Test harness |

## When Building New Pipelines

1. Create a YAML manifest in `pipeline_defs/` (validated by `pipeline_manifest.schema.json`)
2. Use lowercase snake_case stage/sub-stage ids without dots; dotted ids are reserved for derived `<stage>.<sub_stage>` checkpoint units
3. Prefer the canonical top-level stages and express specialized governance as `sub_stages` instead of inventing unrelated top-level concepts
4. Create stage director skills in `skills/pipelines/<pipeline-name>/` for every manifest stage
5. Reference meta skills (reviewer, checkpoint-protocol) in the manifest
6. Add compatible playbooks to the manifest
7. Add contract tests in `tests/contracts/`

## When Building New Tools

1. Inherit from `tools/base_tool.py` `BaseTool`
2. Put the tool in the correct capability package (`tools/analysis/`,
   `tools/audio/`, `tools/avatar/`, `tools/capture/`, `tools/character/`,
   `tools/compliance/`, `tools/enhancement/`, `tools/graphics/`,
   `tools/interaction/`, `tools/publishers/`, `tools/subtitle/`,
   `tools/text/`, `tools/validation/`, `tools/video/`)
3. Prefer the selector-plus-provider pattern:
   - one capability router tool for agent convenience
   - one concrete tool per real provider/runtime path
4. Set all contract fields (name, version, tier, capability, provider, supports, fallback_tools, agent_skills, etc.)
5. Implement `execute()` returning a `ToolResult`
6. Let discovery happen through `tools/tool_registry.py`; do not depend on ad hoc imports
7. Add a JSON schema in `schemas/tools/` if the tool has complex I/O
8. Add tests only after the runtime path is correct
