<p align="center">
  <img src="assets/logo.png" alt="Video Production Buddy" width="180">
</p>

<h1 align="center">Video Production Buddy</h1>

<p align="center"><strong>An interactive AI video production assistant that plans before it generates.</strong></p>

<p align="center">
  <a href="#why-video-production-buddy">Why</a> &nbsp;·&nbsp;
  <a href="#workflow">Workflow</a> &nbsp;·&nbsp;
  <a href="#quick-start">Quick Start</a> &nbsp;·&nbsp;
  <a href="#capabilities">Capabilities</a> &nbsp;·&nbsp;
  <a href="#architecture">Architecture</a> &nbsp;·&nbsp;
  <a href="#testing">Testing</a>
</p>

<p align="center">
  <a href="https://video-production-buddy.github.io"><img src="https://img.shields.io/badge/Project%20Page%20%26%20Gallery-video--production--buddy.github.io-18a058" alt="Project Page & Gallery"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-AGPLv3-blue.svg" alt="License: AGPLv3"></a>
</p>

<p align="center">
  <img src="assets/hero-production-assistant.png" alt="Video Production Buddy workflow overview" width="100%">
</p>

---

Video Production Buddy turns an AI coding assistant into a guided video production partner. Instead of asking for one perfect prompt and immediately spending on AIGC calls, it walks through the production process: clarify the brief, research the context, propose options, confirm details, design the script and scenes, generate assets, edit, compose, and verify the final video.

The project is built from the OpenMontage agent-first video production architecture, then specialized around a more interactive assistant experience: form-based requirement collection, explicit confirmation points, ad-video governance, trend and hit-ad analysis, emotional rhythm control, and cross-clip consistency checks.

## Why Video Production Buddy?

Most AI video workflows jump too quickly from idea to generation. That is expensive, brittle, and hard to correct after the model has already produced assets.

Video Production Buddy is designed around a different rule:

> Think through the production before the expensive AIGC step.

That means the assistant should:

- ask for the details that actually affect production quality;
- show a concrete proposal before generating assets;
- make provider, budget, runtime, music, subtitle, and style choices visible;
- preserve a decision trail so work can be reviewed and resumed;
- test whether the generated plan and final render satisfy the approved brief.

## Workflow

The normal production flow is staged and reviewable:

1. **Idea intake** - the user describes the goal, such as "make a video ad for a coffee brand."
2. **Research, proposal, and confirmation** - the assistant clarifies style, audience, length, budget, core message, platform, and tool path.
3. **Script and scene design** - the assistant writes the script, plans scenes, and asks for feedback at meaningful checkpoints.
4. **Asset generation and editing** - AI video, image, voice, music, stock footage, and local editing tools create production assets.
5. **Composition and verification** - the system composes the final video and runs quality checks before presenting the result.

For ads and commercial-style projects, the workflow adds stronger pre-production governance: audience and product positioning, professional advertising knowledge retrieval, trend research, hit-ad pattern analysis, emotional pacing, product-fidelity checks, sample approval, and final consistency validation.

## Key Advantages

| Area | What Video Production Buddy Adds |
|------|----------------------------------|
| Guided interaction | Form-first intake and feedback checkpoints for dense user decisions. |
| Requirement clarity | Active follow-up on audience, platform, message, style, constraints, budget, and references. |
| Ad-video workflow | A dedicated advertising pipeline with pre-production strategy before script or assets. |
| Trend awareness | Trend retrieval and hit-ad analysis to ground ideas in current audience signals. |
| Emotional rhythm | Explicit control of pacing, intensity, music, voice, and scene energy across the edit. |
| Consistency checks | Structured constraints for product identity, character continuity, object behavior, and visual style. |
| Cost discipline | Proposal and sample gates before expensive generation runs. |

## Quick Start

### Prerequisites

- Python 3.10+
- FFmpeg
- Node.js 18+ for Remotion; Node.js 22+ recommended for HyperFrames
- An AI coding assistant that can read files and run shell commands, such as Codex, Claude Code, Cursor, GitHub Copilot, or Windsurf

### Install

```bash
git clone https://github.com/zhouzhoushen/video-production-buddy.git
cd video-production-buddy
make setup
```

If `make` is not available:

```bash
pip install -r requirements.txt
cd remotion-composer
npm install
cd ..
pip install piper-tts
cp .env.example .env
```

Optional cloud and local provider configuration lives in `.env.example`. Add only the keys you want to use; local/offline paths remain available where supported.

### Start With A Prompt

Open the repository in your AI coding assistant and ask for a video:

```text
Make a 30-second video ad for a new coffee brand.
Target audience: office workers who need a calm afternoon reset.
Platform: TikTok or Instagram Reels.
Style: warm, modern, cinematic, not loud.
```

The assistant should read `AGENT_GUIDE.md`, pick the right pipeline, inspect the available tools, propose a plan, and wait for confirmation before major generation work.

## Capabilities

Video Production Buddy keeps the broad production surface inherited from OpenMontage while emphasizing guided use:

- **Generated videos** - topic-to-video, explainers, animations, cinematic teasers, product ads, and short-form social videos.
- **Ad and commercial production** - strategy, trend analysis, hit-ad patterns, product constraints, sample approval, and publish checks.
- **Source-footage workflows** - talking-head edits, screen demos, podcast repurposing, clip extraction, localization, and hybrid videos.
- **Reference-aware planning** - analyze a reference video or user-provided source media before designing the new output.
- **Provider routing** - select among configured image, video, voice, music, stock, subtitle, analysis, and composition tools.
- **Composition runtimes** - FFmpeg for post-production, Remotion for React-based video scenes, and HyperFrames for HTML/CSS/GSAP motion graphics.
- **Quality gates** - schema validation, checkpointing, decision logs, provider consistency checks, scene fidelity checks, render validation, and post-render review.

## Agent Instructions

This repository is meant to be operated by an AI coding assistant. If you are an agent, start here:

1. Read [`AGENT_GUIDE.md`](AGENT_GUIDE.md).
2. Read [`PROJECT_CONTEXT.md`](PROJECT_CONTEXT.md) when you need architecture context.
3. Discover real tool availability through the registry before promising a production path:

   ```bash
   python -c "from tools.tool_registry import registry; import json; registry.discover(); print(json.dumps(registry.provider_menu_summary(), indent=2))"
   ```

4. For any actual video production request, follow the selected pipeline manifest in `pipeline_defs/` and the stage director skills in `skills/pipelines/`.
5. Do not spend on generation tools until the proposal and any required user approval gates are clear.

## Architecture

Video Production Buddy uses an agent-first architecture:

```text
User request
  -> AI assistant reads the pipeline manifest
  -> AI assistant reads the stage director skill
  -> Python tools execute concrete work
  -> JSON artifacts and checkpoints preserve state
  -> Review gates validate the next step
  -> Composition runtime renders the final video
```

Python provides tools and persistence. The assistant provides orchestration by following readable contracts:

| Path | Purpose |
|------|---------|
| `AGENT_GUIDE.md` | Operating contract for agents. |
| `PROJECT_CONTEXT.md` | Shared architecture overview. |
| `pipeline_defs/` | Declarative video production pipelines. |
| `skills/` | Stage directors, creative guidance, review protocols, and workflow rules. |
| `tools/` | Provider tools, analysis tools, media processing, composition, and validation. |
| `schemas/` | Canonical artifact and checkpoint contracts. |
| `projects/` | Generated project workspaces; ignored by git. |
| `remotion-composer/` | React/Remotion composition runtime. |

## Setup Notes

The repository supports both free/local and cloud-backed workflows. Run:

```bash
make preflight
```

to inspect which providers are configured on your machine.

Useful local commands:

```bash
make demo               # render checked-in zero-key demo compositions
make demo-list          # list available demos
make hyperframes-doctor # validate the HyperFrames runtime
make test-contracts     # run contract tests
```

## Project Status

This project is an active fork and productization layer built from OpenMontage. Some internal module names, package metadata, comments, tests, and documentation still use the OpenMontage name because they refer to the upstream architecture or have not yet been renamed. The public README leads with Video Production Buddy while keeping upstream attribution explicit.

## Upstream Attribution

Video Production Buddy is built from and adapted from [OpenMontage](https://github.com/calesthio/OpenMontage), an open-source, agentic video production system. The project keeps the AGPLv3 license and extends the base system with a more guided assistant experience and ad-video production workflow.

## Testing

```bash
# Contract tests
make test-contracts

# Full test suite
make test
```

For README-only edits, use:

```bash
git diff --check -- README.md
```

Also grep for stale upstream launch links and old hero branding before publishing.

## License

[GNU AGPLv3](LICENSE)

---

**Video Production Buddy** - Guided AI video production from idea to finished render.
