<p align="center">
  <img src="assets/logo.png" alt="Video Production Buddy" width="180">
</p>

<h1 align="center">Video Production Buddy / 织影</h1>

<p align="center"><strong>Open, governed AI video production: plan, approve, generate, compose, and verify before you spend.</strong></p>

<p align="center">
  <strong>English</strong> | <a href="README.zh-CN.md">简体中文</a>
</p>

<p align="center">
  <a href="#demos">🎬 Demos</a> &nbsp;·&nbsp;
  <a href="#why-it-is-different">✨ Why Different</a> &nbsp;·&nbsp;
  <a href="#how-it-works">🧭 How It Works</a> &nbsp;·&nbsp;
  <a href="#quick-start">⚡ Quick Start</a> &nbsp;·&nbsp;
  <a href="#capabilities">🧩 Capabilities</a> &nbsp;·&nbsp;
  <a href="#community-and-discussion">💬 Community</a> &nbsp;·&nbsp;
  <a href="#contributing">🤝 Contribute</a> &nbsp;·&nbsp;
  <a href="docs/PR_REVIEW_GUIDE.md">🔎 Review Guide</a> &nbsp;·&nbsp;
  <a href="#citation">📚 Citation</a> &nbsp;·&nbsp;
  <a href="#acknowledgements">🙏 Acknowledgements</a>
</p>

<p align="center">
  <a href="https://video-production-buddy.github.io"><img src="https://img.shields.io/badge/Project%20Page%20&%20Gallery-video--production--buddy.github.io-18a058" alt="Project Page"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-AGPLv3-blue.svg" alt="License: AGPLv3"></a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Agent--First-Video%20Production-5CC8FF" alt="Agent-first video production">
  <img src="https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white" alt="Python 3.10+">
  <img src="https://img.shields.io/badge/FFmpeg-Post--Production-007808?logo=ffmpeg&logoColor=white" alt="FFmpeg">
  <img src="https://img.shields.io/badge/Remotion-React%20Video-61DAFB?logo=react&logoColor=111111" alt="Remotion">
  <img src="https://img.shields.io/badge/HyperFrames-HTML%2FCSS%2FGSAP-F7DF1E?logo=javascript&logoColor=111111" alt="HyperFrames">
</p>

<p align="center">
  <img src="assets/hero-production-assistant.png" alt="Video Production Buddy workflow overview" width="100%">
</p>

---

> **Video Production Buddy / 织影** turns a general-purpose AI assistant into a visible video production workflow. Instead of typing one prompt and hoping, you can review the brief, plan, script, assets, render, and final checks before major generation work.
>
> **Agent-first by design:** the AI assistant is the producer and orchestrator, while skills and Python tools handle concrete work such as provider routing, media analysis, generation, composition, validation, checkpointing, and cost tracking.
>
> **Best first try:** run the zero-key demo, confirm your machine can render locally, then open this folder in your AI assistant and paste a starter prompt. Cloud API keys are optional until you want provider-generated images, video, voice, or music.
>
> <p align="center"><strong>⭐ Star this project if you want an open, inspectable alternative to black-box AI video generation, thank you!</strong></p>

## Demos

<div align="center">
  <video src="https://github.com/user-attachments/assets/df481a12-a150-41c6-97fe-24afcbeb85db" width="100%" controls></video>
</div>

> **织影 product ad** - a guided assistant flow for intake, proposal gates, asset generation, composition, and final review before delivery.

<div align="center">
  <video src="https://github.com/user-attachments/assets/c240b2d1-5c65-41f1-8d71-454ae1f43f51" width="100%" controls></video>
</div>

> **MacBook Air ad** - "Please help me design an ad video for MacBook Air."

## Why It Is Different

- 🎬 **Not prompt-to-video. Pipeline-to-video.** YAML manifests and director skills guide each stage from intake to publish.
- 💬 **Needs are discovered, not guessed.** Chat and GenUI gates help uncover the audience, taste, emotion, constraints, and ideal video profile in the user's mind.
- 🧠 **Design before asset generation.** Hot-topic search, Bilibili/Douyin-style viral analysis, professional video knowledge retrieval, and emotion-curve checks shape the plan while it is still cheap to revise.
- 🧷 **Consistency before generation.** Concept maps and approved constraints keep products, characters, scenes, and visual logic aligned across segments.
- 🛡️ **Hallucination review.** Review agents use policies and few-shot cases to catch unsafe, physically implausible, value-conflicting, or story-breaking samples before approval.
- ✅ **Human approval before expensive generation.** Briefs, proposals, scripts, scene plans, samples, and final renders can be reviewed before the next spend.
- 🔀 **Provider-aware execution.** Image, video, voice, music, stock, subtitle, analysis, and composition tools are discovered from the live registry and routed by task fit.
- 🧾 **Checkpointed and reproducible.** JSON artifacts, decision logs, and checkpoints preserve the production trail so work can be reviewed or resumed.
- 🧪 **Verified output.** Scene fidelity, product consistency, provider consistency, render validation, and post-render review keep the final video accountable to the approved brief.

| Typical AI video tools | Video Production Buddy / 织影 |
|------------------------|--------------------------------|
| One-shot prompt to generation | Staged pipeline from brief to verified render |
| The user must know exactly what to ask for | Chat and GenUI clarify needs before production decisions |
| Trend and reference work is optional | Hot topics and viral videos add timely audience context during design |
| Story quality is judged after rendering | Emotion pacing is reviewed in the lightweight text phase |
| Hidden provider, model, and cost choices | Visible provider/model routing, budget checks, and approval gates |
| Segments can drift from each other | Concept maps constrain cross-segment consistency |
| Hard to resume or audit | Checkpointed artifacts and decision logs |
| Generate first, fix later | Approve the plan before expensive generation |
| Output judged by vibe only | Structured quality checks after composition |

## How It Works

```text
User request
  -> Chat and GenUI clarify needs, audience, taste, and constraints
  -> AI assistant selects a pipeline manifest
  -> AI assistant reads the stage director skill
  -> Design intelligence gathers trends, references, and production knowledge
  -> Python tools execute concrete media work
  -> JSON artifacts and checkpoints preserve state
  -> Review gates validate creative and technical decisions
  -> Composition runtime renders the final video
  -> Post-render checks verify the output
```

Video Production Buddy has no Python orchestrator. The assistant follows readable contracts in YAML manifests and Markdown skills. The codebase provides tools, schemas, persistence, validation, and render runtimes.

For ads and commercial-style projects, the pipeline adds stronger pre-production: product positioning, professional video production knowledge retrieval, hot-topic search, Bilibili/Douyin-style viral analysis, emotion pacing constraints, concept-map consistency checks, sample approval, scene fidelity checks, product identity validation, hallucination review, and final consistency review.

## Quick Start

### Before You Start

For a first try, you **do not** need cloud API keys. Render the checked-in zero-key demo first, confirm local rendering works, then add cloud providers only when you need them.

You need:

- **Git** - [git-scm.com](https://git-scm.com/downloads). If you do not want Git yet, download the repository ZIP from GitHub and unzip it.
- **Python 3.10+** - [python.org](https://www.python.org/downloads/); on Ubuntu/Debian, run `sudo apt install python3-venv` if virtualenv creation fails
- **FFmpeg** - `brew install ffmpeg` / `sudo apt install ffmpeg` / `winget install --id Gyan.FFmpeg` / `choco install ffmpeg -y` / [ffmpeg.org](https://ffmpeg.org/download.html)
- **Node.js 22+** - required for Remotion, HyperFrames, and character-animation renders
- **Make** - on macOS run `xcode-select --install`; on Ubuntu/Debian run `sudo apt update && sudo apt install make`; on Windows install [Chocolatey](https://chocolatey.org/install), then run `choco install make -y` in Administrator PowerShell
- **An AI coding assistant** - Codex, Claude Code, Cursor, GitHub Copilot, Windsurf, or another assistant that can read files and run shell commands

On Windows, reopen PowerShell after installing Python, Node.js, FFmpeg, or Make so new `PATH` entries are visible.
If you downloaded the ZIP instead of using Git, skip the `git clone` line and `cd` into the unzipped folder.

### Check Prerequisites

First confirm these commands print version or help output.

macOS/Linux:

```bash
git --version
python3 --version
python3 -m venv --help >/dev/null
ffmpeg -version
node --version
npm --version
npx --version
make --version
```

Windows PowerShell:

```powershell
git --version
python --version
python -m venv --help > $null
ffmpeg -version
node --version
npm --version
npx --version
make --version
```

If a command is not found, install that tool, reopen your terminal, and check again.

### First Local Smoke Test

Run this once to prove your machine can install dependencies, inspect available runtimes, and render a local demo video without API keys.

macOS/Linux:

```bash
git clone https://github.com/video-production-buddy/video-production-buddy.git
cd video-production-buddy
python3 -m venv .venv
source .venv/bin/activate
make setup
python -m lib.agent_components install --profile default --frozen
make preflight
make demo
```

Windows PowerShell:

```powershell
git clone https://github.com/video-production-buddy/video-production-buddy.git
cd video-production-buddy
python -m venv .venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force
.\.venv\Scripts\Activate.ps1
$env:PYTHON = "python"
make setup
python -m lib.agent_components install --profile default --frozen
make preflight
make demo
```

`Set-ExecutionPolicy` only changes the current PowerShell process so the virtualenv activation script can run. `$env:PYTHON = "python"` makes the Makefile use Python from the active virtualenv. Later, when you want API keys, copy `.env.example` to `.env` if `make setup` did not already create it.

Success looks like this:

- `make preflight` prints JSON with `composition_runtimes`, provider availability, and selectable model choices.
- `make models-list` prints model choices in a readable list.
- `make demo` renders local demo MP4 files under `projects/demos/renders/`.
- No cloud API key is required for that demo path.

After the demo works, open this repository folder in your AI assistant and see [Start With A Prompt](#start-with-a-prompt).

### Useful Check Commands

Re-run the local capability/provider summary anytime:

```bash
make preflight
```

List model choices without reading raw JSON:

```bash
make models-list
make models-list CAPABILITY=video_generation
```

If HyperFrames is unavailable, you can ignore it at first; the zero-key demo mainly relies on Remotion and FFmpeg.

Re-render the checked-in demo suite anytime:

```bash
make demo
```

The demo path uses local Remotion components and should not require cloud API keys. The first Remotion render may download Chrome Headless Shell, so allow several minutes on a normal laptop. Generated demo renders are written under `projects/demos/renders/`; the command exits nonzero if Remotion finishes without creating the expected MP4.

If something fails, stay in the same AI assistant session and ask it to inspect the command output, preflight result, OS, Python, Node.js, and FFmpeg versions. If it looks like a project bug or missing documentation, please open a [GitHub Issue](https://github.com/video-production-buddy/video-production-buddy/issues) with those details.

### Add API Keys

All keys are optional. Skip this for the first try; when you need cloud generation, add only the provider keys you plan to use in `.env`. `make setup` usually creates `.env`; if not, copy `.env.example` to `.env`.

```bash
FAL_KEY=your-key              # Image/video generation: FLUX, Recraft, Seedance, Kling, Veo, MiniMax video
DASHSCOPE_API_KEY=your-key    # Qwen speech, Wan video, Wanxiang image
ELEVENLABS_API_KEY=your-key   # TTS, music, sound effects
OPENAI_API_KEY=your-key       # OpenAI TTS and image generation
MINIMAX_API_KEY=your-key      # MiniMax music generation
PEXELS_API_KEY=your-key       # Optional: stock media
```

New to API keys? Follow [`docs/PROVIDERS.md#where-to-get-api-keys`](docs/PROVIDERS.md#where-to-get-api-keys) for official signup/key links and key-safety rules. Keep keys in `.env`; do not paste them into chat prompts, screenshots, issues, or committed files.

For the full provider list, pricing notes, model-choice guidance, and free-tier
guidance, see [`docs/PROVIDERS.md`](docs/PROVIDERS.md). `.env.example` now
groups API keys and optional model defaults together. Copy it to `.env`, add
the keys you use, then set optional `VPB_*` model defaults next to those keys.

After editing local `.env`, validate it:

```bash
make models-check ENV_FILE=.env
```

To see valid provider/model values for the keys you configured:

```bash
make models-list
make models-list CAPABILITY=video_generation
```

If you prefer a command-generated preview instead of editing `.env` manually:

```bash
make models-configure ENV_FILE=.env CAPABILITY=video_generation PRESET=fast DRY_RUN=1
make models-configure ENV_FILE=.env CAPABILITY=video_generation PRESET=fast YES=1
```

Explicit request/tool inputs still win over `.env` defaults.

Have an NVIDIA GPU and want local generation?

```bash
make install-gpu
```

Then set:

```bash
VIDEO_GEN_LOCAL_ENABLED=true
VIDEO_GEN_LOCAL_MODEL=wan2.1-1.3b
```

Other local model options include `wan2.1-14b`, `hunyuan-1.5`, `ltx2-local`, and `cogvideo-5b`.

### What Works With Zero API Keys?

Out of the box, the local path can still do useful work:

| Capability | Free/local tool | What it does |
|------------|-----------------|--------------|
| Narration | Piper TTS | Offline text-to-speech when installation succeeds. |
| Composition | Remotion | React-based animated scenes, title cards, charts, captions, and image motion. |
| Motion graphics | HyperFrames | HTML/CSS/GSAP video when Node.js 22+ and the runtime check pass. |
| Post-production | FFmpeg | Encoding, stitching, trimming, audio mixing, subtitle burn-in, and validation. |
| Demos | `make demo` | Renders the checked-in zero-key demo suite under `projects/demos/renders/`. |

For real production briefs, the assistant will present the preflight menu and tell you which providers and model options are available, missing, or optional before spending on generation.

### Start With A Prompt

Open the repository folder in your AI assistant and describe the video you want, for example:

```text
Make a 30-second video ad for a new coffee brand.
Target audience: office workers who need a calm afternoon reset.
Platform: TikTok or Instagram Reels.
Style: warm, modern, cinematic, not loud.
```

OpenClaw, Claude Code, Codex, and similar assistants generally use the repository's agent instructions to pick the right pipeline, inspect available tools, propose a plan, and wait for confirmation before major generation work. If your assistant does not automatically read the repo instructions, ask it to read `AGENT_GUIDE.md` first. If a provider is missing, it should offer a local fallback or explain which API key unlocks that path.

Useful starter prompts:

```text
Make a 45-second animated explainer about why the sky is blue.
```

```text
Make a 75-second documentary montage about city life in the rain.
Use real footage only, no narration, elegiac tone, with music.
```

```text
Here is a reference video I like. Keep the pacing and hook style,
but turn it into a 30-second product ad for my own app.
```

## Capabilities

| Area | What It Supports |
|------|------------------|
| 🎞️ Generated video | Topic-to-video, explainers, animations, cinematic teasers, product ads, and short-form social videos. |
| 💬 Interactive discovery | Chat and GenUI interfaces clarify the target audience, emotion, constraints, and ideal video profile before generation. |
| 📣 Ad production | Strategy, hot-topic search, Bilibili/Douyin-style viral analysis, professional production knowledge retrieval, product constraints, sample approval, and publish checks. |
| 🎥 Source footage | Talking-head edits, screen demos, podcast repurposing, clip extraction, localization, and hybrid videos. |
| 🧭 Reference-aware planning | Analyze a reference video or user-provided source media before designing the new output. |
| 🎭 Story control | Emotion pacing constraints check suspense, twists, emotional anchors, and story appeal before assets are generated. |
| 🧩 Consistency control | Concept maps and approved design constraints keep product identity, characters, scenes, and visual logic consistent across segments. |
| 🔀 Provider routing | Select among configured image, video, voice, music, stock, subtitle, analysis, and composition tools. |
| 🧱 Composition | FFmpeg post-production, Remotion React video scenes, and HyperFrames HTML/CSS/GSAP motion graphics. |
| ✅ Quality gates | Schema validation, checkpointing, decision logs, provider consistency checks, hallucination review, scene fidelity checks, render validation, and post-render review. |

## Community and Discussion

Use the discussion path that matches what you need:

| Need | Best place |
|------|------------|
| Questions, ideas, roadmap topics, showcases | [GitHub Issues](https://github.com/video-production-buddy/video-production-buddy/issues) |
| Bugs, setup failures, missing provider docs | [GitHub Issues](https://github.com/video-production-buddy/video-production-buddy/issues) |
| Code, docs, examples, and provider/runtime fixes | [Pull requests](https://github.com/video-production-buddy/video-production-buddy/pulls) |

When reporting setup problems, include your OS, Python version, Node.js version, FFmpeg availability, the command you ran, and the relevant `make preflight` output.

## Contributing

Contributions are welcome when they keep the project inspectable, reproducible, and useful for real video production.

Good first contributions:

- Improve setup docs, provider notes, or error messages that blocked you.
- Add demo prompts, style playbooks, sample props, or small zero-key examples.
- Improve tests around schemas, pipeline manifests, provider routing, or render validation.
- Translate or tighten public-facing docs while keeping `README.md` and `README.zh-CN.md` synchronized.

Common developer paths:

- **Add a provider or tool:** put the implementation in the matching `tools/` capability package, inherit `BaseTool`, declare dependencies and `agent_skills`, let `tools/tool_registry.py` discover it, and add focused tests.
- **Add a pipeline:** create a manifest in `pipeline_defs/`, add stage director skills under `skills/pipelines/<pipeline-id>/`, reuse existing tools where possible, and add contract tests.
- **Add a demo or example:** prefer zero-key Remotion/FFmpeg paths when practical, keep generated outputs under `projects/`, and document the command needed to reproduce it.

Pull request checklist:

1. Start from a focused issue, discussion, or clearly scoped change.
2. Run the setup path in this README if your change affects install, runtime, providers, or demos.
3. Add or update focused tests for code, schema, manifest, or tool-contract changes.
4. Run `git diff --check -- README.md README.zh-CN.md` for README-only changes.
5. Run `make test-contracts` for manifest, schema, tool registry, pipeline, or agent-instruction changes. Use `make test-integration` when a change touches FFmpeg, browser, Node, or HyperFrames runtime behavior.
6. Use [`docs/PR_REVIEW_GUIDE.md`](docs/PR_REVIEW_GUIDE.md) to check architecture, provider, security, dependency, and docs risks before requesting review.
7. In the PR, summarize the user-facing impact, list verification commands, and include screenshots or demo links for visual README changes.

## Architecture

| Path | Purpose |
|------|---------|
| `AGENT_GUIDE.md` | Operating contract for production agents. |
| `PROJECT_CONTEXT.md` | Shared architecture and development overview. |
| `docs/PR_REVIEW_GUIDE.md` | Review framework for pull requests, provider changes, runtime changes, and documentation claims. |
| `pipeline_defs/` | Declarative video production pipelines. |
| `skills/` | Stage directors, creative guidance, review protocols, and workflow rules. |
| `tools/` | Provider tools, analysis tools, media processing, composition, validation, and cost tracking. |
| `schemas/` | Canonical artifact, checkpoint, pipeline, style, and tool contracts. |
| `project_profile/` | Project-local production conventions and current provider/runtime findings. |
| `projects/` | Generated project workspaces; ignored by git. |
| `remotion-composer/` | React/Remotion composition runtime. |

Useful local commands:

```bash
make preflight          # inspect configured provider/runtime availability
make models-list        # readable model/provider list
make models-check       # validate .env.example, or ENV_FILE=.env for local settings
make models-configure   # optional command-generated .env model preference update
make demo               # render the checked-in zero-key demo suite
make demo-list          # list available demos
make hyperframes-doctor # validate the HyperFrames runtime
make test-contracts     # run contract tests
make test-integration   # run opt-in local runtime smoke tests
```

## Agent Instructions

This repository is meant to be operated by an AI coding assistant. If you are an agent:

1. Read [`AGENT_GUIDE.md`](AGENT_GUIDE.md) for production work.
2. Read [`PROJECT_CONTEXT.md`](PROJECT_CONTEXT.md) and [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for development work.
3. Discover the live capability envelope before promising a production path:

   ```bash
   python -c "from tools.tool_registry import registry; import json; registry.discover(); print(json.dumps(registry.provider_menu_summary(), indent=2))"
   ```

4. For actual video production, follow the selected pipeline manifest in `pipeline_defs/` and the stage director skills in `skills/pipelines/`.
5. Do not spend on generation tools until the proposal and required approval gates are clear.

## Testing

`make setup` installs runtime dependencies. Install development dependencies before running tests:

```bash
# Test dependencies
make install-dev

# Fast default suite
make test

# Contract tests only
make test-contracts

# Opt-in local runtime checks (FFmpeg/browser/Node/HyperFrames)
make test-integration

# Manual/media QA alias
make test-qa
```

The default suite excludes `integration`, `qa`, `browser`, `ffmpeg`, `node`,
`hyperframes`, `slow`, and `live_provider` markers. Mocked provider tests stay
in the default suite so path validation and payload contracts are checked before
credentials or network calls are possible.

## License

[GNU AGPLv3](LICENSE)

## Citation

If you find Video Production Buddy useful, please star and cite our project, thank you!

```bibtex
@software{shen2026videoproductionbuddy,
  title = {Video Production Buddy: An Interactive AI Video Production Assistant},
  author = {Shen, Zhouzhou and Chen, Yurun and Hu, Xueyu and Zhang, Shengyu},
  year = {2026},
  url = {https://github.com/video-production-buddy/video-production-buddy}
}
```

Video Production Buddy is built on the open-source [OpenMontage](https://github.com/calesthio/OpenMontage) project. When citing or building on this repository, please also acknowledge OpenMontage:

```bibtex
@software{calesthio2026openmontage,
  title = {OpenMontage},
  author = {{Calesthio}},
  year = {2026},
  url = {https://github.com/calesthio/OpenMontage}
}
```

## Acknowledgements

Video Production Buddy is developed by the [AI4GC Lab](https://ai4gc.org/) at Zhejiang University.

The codebase builds on the excellent [OpenMontage](https://github.com/calesthio/OpenMontage) project; we are grateful for its open-source architecture and implementation foundation.
