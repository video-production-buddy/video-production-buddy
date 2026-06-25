<p align="center">
  <img src="assets/logo.png" alt="织影" width="180">
</p>

<h1 align="center">织影</h1>

<p align="center"><strong>开放、可治理的 AI 视频制作系统：先规划、先确认，再生成、合成和验证。</strong></p>

<p align="center">
  <a href="README.md">English</a> | <strong>简体中文</strong>
</p>

<p align="center">
  <a href="#演示">🎬 演示</a> &nbsp;·&nbsp;
  <a href="#差异点">✨ 差异点</a> &nbsp;·&nbsp;
  <a href="#工作方式">🧭 工作方式</a> &nbsp;·&nbsp;
  <a href="#快速开始">⚡ 快速开始</a> &nbsp;·&nbsp;
  <a href="#能力">🧩 能力</a> &nbsp;·&nbsp;
  <a href="#社区与讨论">💬 讨论</a> &nbsp;·&nbsp;
  <a href="#参与贡献">🤝 贡献</a> &nbsp;·&nbsp;
  <a href="#引用">📚 引用</a> &nbsp;·&nbsp;
  <a href="#致谢">🙏 致谢</a>
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
  <img src="assets/hero-production-assistant.png" alt="织影工作流概览" width="100%">
</p>

---

> **织影 / Video Production Buddy** 可以把通用 AI 助手变成一个有治理流程的视频制作工作室。它不会把视频生成当成黑盒提示词，而是通过需求细化、背景研究、方案确认、素材生成、合成和渲染后检查来分阶段推进。
>
> **核心设计是 agent-first：** AI 助手承担制片人与流程编排角色，skills 和 Python 工具负责具体执行，例如 provider 路由、媒体分析、素材生成、合成、校验、checkpoint 和成本记录。
>
> <p align="center"><strong>⭐ 如果你希望看到一个开放、可检查的黑盒 AI 视频生成替代方案，欢迎 Star 这个项目，谢谢！</strong></p>

## 演示

[![MacBook Air 广告](assets/readme/macbook_air.jpg)](assets/readme/macbook_air.mp4)

> **MacBook Air 广告** - “Please help me design an ad video for MacBook Air.”

[![织影产品广告](assets/readme/zhiying.jpg)](assets/readme/zhiying.mp4)

> **织影产品广告** - 展示从需求输入、方案确认、素材生成、合成到最终交付复核的引导式助手流程。

## 差异点

- 🎬 **不是 prompt-to-video，而是 pipeline-to-video。** YAML manifests 和 director skills 会引导从需求到发布的每个阶段。
- 💬 **不是让用户一次说清，而是一起澄清。** 通过 chat 和 GenUI 交互，逐步明确受众、审美、情绪、约束，以及用户心中的理想视频画像。
- 🧠 **先设计，再生成素材。** 热点搜索、Bilibili/抖音等爆款视频分析、专业视频制作知识检索和情绪曲线检查，会在仍然易修改的文本阶段打磨方案。
- 🧷 **生成前先锁定一致性。** Concept maps 和已确认约束会限制产品、角色、场景和视觉逻辑在不同片段间漂移。
- 🛡️ **引入幻觉复核。** Review agents 会结合 policies 和 few-shot cases，提前发现不安全、不符合物理常识、价值冲突或破坏故事的样片。
- ✅ **昂贵生成前先人工确认。** 需求、方案、脚本、分镜、样片和最终渲染都可以先复核，再进入下一步。
- 🔀 **感知 provider 的执行系统。** 图像、视频、配音、音乐、素材、字幕、分析和合成工具都来自实时工具注册表，并按任务匹配路由。
- 🧾 **可 checkpoint、可复盘、可恢复。** JSON artifacts、decision logs 和 checkpoints 会保留制作轨迹。
- 🧪 **输出经过验证。** 场景保真、产品一致性、provider 一致性、渲染校验和 post-render review 会对照已确认的 brief 检查结果。

| 常见 AI 视频工具 | 织影 / Video Production Buddy |
|------------------|-------------------------------|
| 一句话提示词直接生成 | 从 brief 到 verified render 的分阶段 pipeline |
| 需要用户一开始就说清所有需求 | 通过 chat 和 GenUI 在制作前澄清需求 |
| 趋势和参考分析常常是可选项 | 热点与爆款视频会在设计阶段建立与受众相关的时空感 |
| 故事是否打动人通常渲染后才知道 | 在轻量文本阶段复核情绪节奏 |
| provider 和成本选择不透明 | 可见的 provider routing、budget checks 和 approval gates |
| 片段之间容易漂移 | 用 concept maps 约束跨片段一致性 |
| 很难恢复或审计 | checkpointed artifacts 和 decision logs |
| 先生成，后修补 | 先确认方案，再进行昂贵生成 |
| 主要凭感觉判断输出 | 合成后进行结构化质量检查 |

## 工作方式

```text
用户需求
  -> Chat 和 GenUI 澄清受众、审美、情绪与约束
  -> AI 助手选择 pipeline manifest
  -> AI 助手读取 stage director skill
  -> Design intelligence 检索趋势、参考和专业制作知识
  -> Python 工具执行具体媒体任务
  -> JSON artifacts 和 checkpoints 保存状态
  -> review gates 校验创意与技术决策
  -> composition runtime 渲染最终视频
  -> post-render checks 验证输出结果
```

织影没有 Python orchestrator。助手会读取 YAML manifest 和 Markdown skills 中的可读契约；代码库提供工具、schema、持久化、校验和渲染 runtime。

对于广告和商业类项目，pipeline 会加入更强的前期制作：产品定位、专业视频制作知识检索、热点搜索、Bilibili/抖音等爆款视频分析、情绪节奏约束、concept-map 一致性检查、样片确认、场景保真检查、产品身份验证、幻觉复核和最终一致性复核。

## 快速开始

### 快速路径

```bash
git clone https://github.com/video-production-buddy/video-production-buddy.git
cd video-production-buddy
make setup
python -m lib.agent_components install --profile default --frozen
make preflight
```

然后在 AI 助手中打开仓库并提出视频需求。如果 preflight 显示 FFmpeg、Remotion 和你需要的 provider 可用，就可以开始制作。

### 前置依赖

- **Python 3.10+** - [python.org](https://www.python.org/downloads/)
- **FFmpeg** - `brew install ffmpeg` / `sudo apt install ffmpeg` / `winget install FFmpeg` / [ffmpeg.org](https://ffmpeg.org/download.html)
- **Node.js 22+** - Remotion、HyperFrames 和 character-animation 渲染需要
- **AI 编程助手** - Codex、Claude Code、Cursor、GitHub Copilot、Windsurf，或其他能读文件和运行 shell 命令的助手

建议使用虚拟环境：

```bash
python -m venv .venv
source .venv/bin/activate
```

Windows PowerShell：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### 安装并运行

```bash
git clone https://github.com/video-production-buddy/video-production-buddy.git
cd video-production-buddy
make setup
python -m lib.agent_components install --profile default --frozen
```

`make setup` 会安装 Python 依赖、安装 Remotion composer、尽量安装 Piper TTS、尽量预热 HyperFrames 的 `npx` 缓存，并在 `.env` 不存在时从 `.env.example` 创建一份。`lib.agent_components` 命令会安装 provider 工具和 runtime 指南所需的 agent skill packs。

如果本机没有 `make`：

```bash
pip install -r requirements.txt
python -m lib.agent_components install --profile default --frozen
cd remotion-composer
npx --yes pnpm install --frozen-lockfile
cd ..
pip install piper-tts || echo "Piper TTS install skipped; offline narration may be unavailable"
npx --yes hyperframes --version || echo "HyperFrames cache warm skipped; run make hyperframes-doctor later"
test -f .env || cp .env.example .env
```

> **Windows 提示：** 如果 Node 包安装时出现 `ERR_INVALID_ARG_TYPE`，请进入 `remotion-composer/` 后使用 `npx --yes pnpm install --frozen-lockfile` 安装 Remotion 依赖。

### 验证安装

先运行 preflight 摘要：

```bash
make preflight
```

你应该看到包含 `composition_runtimes` 和 provider 可用性的 JSON。健康的本地环境在 FFmpeg、Node.js 和 Remotion 依赖安装完成后，应显示 FFmpeg 和 Remotion 可用。HyperFrames 需要 Node.js 22+、FFmpeg 和 `npx`，可以单独验证：

```bash
make hyperframes-doctor
```

HyperFrames doctor 打印 Docker 警告不一定影响本地渲染；关键是命令成功退出，并报告 runtime available。如果它打印 `FAIL` 或以非零状态退出，就先把 HyperFrames 视为当前机器不可用，改用 Remotion 或 FFmpeg 路径，直到修好 Node/FFmpeg/npx 环境。

然后渲染仓库内置的零 API key 演示套件：

```bash
make demo
```

这条 demo 路径使用本地 Remotion 组件，不需要云端 API key。第一次 Remotion 渲染可能会下载 Chrome Headless Shell，普通笔记本上需要几分钟。生成的视频位于 `projects/demos/renders/`；如果 Remotion 结束后没有生成预期 MP4，命令会以非零状态退出。

### 添加 API Key

所有 key 都是可选的。只需要在 `.env` 中添加你计划使用的 provider：

```bash
# 免费素材
PEXELS_API_KEY=your-key
PIXABAY_API_KEY=your-key
UNSPLASH_ACCESS_KEY=your-key

# 图像、视频、配音和音乐 provider
FAL_KEY=your-key              # FLUX, Recraft, Seedance, Kling, Veo, MiniMax video
DASHSCOPE_API_KEY=your-key    # Qwen TTS/ASR, Wan video, Wanxiang image
GOOGLE_API_KEY=your-key       # Google Imagen + Google TTS
ELEVENLABS_API_KEY=your-key   # TTS, music, sound effects
OPENAI_API_KEY=your-key       # OpenAI TTS + image generation
XAI_API_KEY=your-key          # Grok image/video
HEYGEN_API_KEY=your-key       # Avatar and video gateway
RUNWAY_API_KEY=your-key       # Runway video
SUNO_API_KEY=your-key         # Music generation
MINIMAX_API_KEY=your-key      # Music generation
```

完整 provider 列表、价格说明和免费额度建议见 [`docs/PROVIDERS.md`](docs/PROVIDERS.md)。

如果你有 NVIDIA GPU，并希望使用本地生成：

```bash
make install-gpu
```

然后设置：

```bash
VIDEO_GEN_LOCAL_ENABLED=true
VIDEO_GEN_LOCAL_MODEL=wan2.1-1.3b
```

其他本地模型选项包括 `wan2.1-14b`、`hunyuan-1.5`、`ltx2-local` 和 `cogvideo-5b`。

### 没有 API Key 也能做什么

开箱后，本地路径仍然可以完成一些有用工作：

| 能力 | 免费/本地工具 | 作用 |
|------|---------------|------|
| 旁白 | Piper TTS | 安装成功后可离线 text-to-speech。 |
| 合成 | Remotion | 基于 React 的动画场景、标题卡、图表、字幕和图片运动。 |
| 动效 | HyperFrames | 在 Node.js 22+ 且 runtime check 通过时，生成 HTML/CSS/GSAP 视频。 |
| 后期 | FFmpeg | 编码、拼接、裁剪、混音、字幕烧录和验证。 |
| 演示 | `make demo` | 渲染仓库内置零 API key 演示套件，输出到 `projects/demos/renders/`。 |

对于真实制作需求，助手会先展示 preflight menu，告诉你哪些 provider 可用、缺失或可选，再进行会产生费用的生成。

### 从一个需求开始

在 AI 助手中打开仓库，然后提出视频需求：

```text
Make a 30-second video ad for a new coffee brand.
Target audience: office workers who need a calm afternoon reset.
Platform: TikTok or Instagram Reels.
Style: warm, modern, cinematic, not loud.
```

助手应读取 `AGENT_GUIDE.md`，选择合适 pipeline，检查可用工具，提出制作方案，并在主要生成工作前等待确认。

更多起步示例：

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

## 能力

| 方向 | 支持内容 |
|------|----------|
| 🎞️ 生成视频 | 主题到视频、解释型视频、动画、电影感预告、产品广告和短视频。 |
| 💬 交互式需求澄清 | 通过 chat 和 GenUI 在生成前明确目标受众、情绪、约束和理想视频画像。 |
| 📣 广告制作 | 策略、热点搜索、Bilibili/抖音等爆款视频分析、专业制作知识检索、产品约束、样片确认和发布检查。 |
| 🎥 源素材处理 | 口播剪辑、屏幕演示、播客再创作、片段抽取、本地化和混合视频。 |
| 🧭 参考视频规划 | 先分析参考视频或用户提供的源素材，再设计新输出。 |
| 🎭 故事控制 | 情绪节奏约束会检查悬念、反转、情绪锚点和故事吸引力，再进入素材生成。 |
| 🧩 一致性控制 | Concept maps 和已确认设计约束会保持产品身份、角色、场景与视觉逻辑的跨片段一致性。 |
| 🔀 Provider 路由 | 在已配置的图像、视频、配音、音乐、素材、字幕、分析和合成工具之间选择。 |
| 🧱 合成 | FFmpeg 后期、Remotion React 视频场景、HyperFrames HTML/CSS/GSAP 动效。 |
| ✅ 质量门禁 | Schema 校验、checkpoint、decision log、provider 一致性、幻觉复核、场景保真、渲染验证和 post-render review。 |

## 社区与讨论

请根据你的需求选择讨论路径：

| 需求 | 推荐位置 |
|------|----------|
| 问题、想法、路线图、作品展示 | [GitHub Issues](https://github.com/video-production-buddy/video-production-buddy/issues) |
| Bug、安装失败、provider 文档缺失 | [GitHub Issues](https://github.com/video-production-buddy/video-production-buddy/issues) |
| 代码、文档、示例、provider/runtime 修复 | [Pull requests](https://github.com/video-production-buddy/video-production-buddy/pulls) |

反馈安装问题时，请附上操作系统、Python 版本、Node.js 版本、FFmpeg 是否可用、运行的命令，以及相关的 `make preflight` 输出。

## 参与贡献

欢迎贡献，但请优先保持项目可检查、可复现，并服务于真实视频制作。

适合开始的贡献：

- 改进阻塞过你的安装文档、provider 说明或错误提示。
- 添加 demo prompts、style playbooks、sample props 或小型零 API key 示例。
- 改进 schemas、pipeline manifests、provider routing 或 render validation 相关测试。
- 翻译或精简公开文档，并保持 `README.md` 和 `README.zh-CN.md` 同步。

常见开发路径：

- **添加 provider 或 tool：** 在对应的 `tools/` capability package 中实现，继承 `BaseTool`，声明 dependencies 和 `agent_skills`，让 `tools/tool_registry.py` 自动发现，并添加聚焦测试。
- **添加 pipeline：** 在 `pipeline_defs/` 中创建 manifest，在 `skills/pipelines/<pipeline-id>/` 下添加 stage director skills，优先复用已有工具，并添加 contract tests。
- **添加 demo 或 example：** 尽量优先使用零 API key 的 Remotion/FFmpeg 路径，将生成输出放在 `projects/` 下，并记录复现命令。

Pull request checklist：

1. 从聚焦的 issue、discussion 或清晰的小范围改动开始。
2. 如果改动影响安装、runtime、provider 或 demos，请运行本 README 中的 setup path。
3. 对代码、schema、manifest 或 tool-contract 改动添加或更新聚焦测试。
4. 仅修改 README 时运行 `git diff --check -- README.md README.zh-CN.md`。
5. 修改 manifest、schema、tool registry、pipeline 或 agent instructions 时运行 `make test-contracts`。
6. 在 PR 中说明用户可见影响、列出验证命令；视觉类 README 改动请附截图或 demo 链接。

## 架构

| 路径 | 作用 |
|------|------|
| `AGENT_GUIDE.md` | 生产 agent 的操作契约。 |
| `PROJECT_CONTEXT.md` | 共享架构和开发概览。 |
| `pipeline_defs/` | 声明式视频制作 pipelines。 |
| `skills/` | 阶段导演、创意指导、复核协议和 workflow 规则。 |
| `tools/` | Provider 工具、分析工具、媒体处理、合成、校验和成本记录。 |
| `schemas/` | Artifact、checkpoint、pipeline、style 和 tool 契约。 |
| `project_profile/` | 项目本地生产约定和当前 provider/runtime findings。 |
| `projects/` | 生成的项目工作区；被 git 忽略。 |
| `remotion-composer/` | React/Remotion 合成 runtime。 |

常用本地命令：

```bash
make preflight          # 检查已配置 provider/runtime 可用性
make demo               # 渲染仓库内置零 API key 演示套件
make demo-list          # 列出可用演示
make hyperframes-doctor # 验证 HyperFrames runtime
make test-contracts     # 运行 contract tests
```

## 给 AI 助手的说明

本仓库设计为由 AI 编程助手操作。如果你是 agent：

1. 生产视频时读取 [`AGENT_GUIDE.md`](AGENT_GUIDE.md)。
2. 开发任务时读取 [`PROJECT_CONTEXT.md`](PROJECT_CONTEXT.md) 和 [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)。
3. 在承诺生产路径前，先发现实时 capability envelope：

   ```bash
   python -c "from tools.tool_registry import registry; import json; registry.discover(); print(json.dumps(registry.provider_menu_summary(), indent=2))"
   ```

4. 真正制作视频时，遵循 `pipeline_defs/` 中选定的 pipeline manifest 和 `skills/pipelines/` 中的 stage director skills。
5. 在 proposal 和必要审批节点明确前，不要花费生成工具额度。

## 测试

`make setup` 安装的是运行时依赖。跑测试前先安装开发依赖：

```bash
# Test dependencies
make install-dev

# Contract tests
make test-contracts

# Full test suite
make test
```

## 许可证

[GNU AGPLv3](LICENSE)

## 引用

如果你觉得织影有帮助，欢迎 star 并引用我们的项目，谢谢！

```bibtex
@software{shen2026videoproductionbuddy,
  title = {Video Production Buddy: An Interactive AI Video Production Assistant},
  author = {Shen, Zhouzhou and Chen, Yurun and Hu, Xueyu and Zhang, Shengyu},
  year = {2026},
  url = {https://github.com/video-production-buddy/video-production-buddy}
}
```

## 致谢

织影由浙江大学 [AI4GC Lab](https://ai4gc.org/) 开发。

我们的代码基于优秀的 [OpenMontage codebase](https://github.com/calesthio/OpenMontage)。
