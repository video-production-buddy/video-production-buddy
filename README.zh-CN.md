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
  <a href="#片场看板">🎞️ Backlot</a> &nbsp;·&nbsp;
  <a href="#从参考视频开始">🎯 参考</a> &nbsp;·&nbsp;
  <a href="#差异点">✨ 差异点</a> &nbsp;·&nbsp;
  <a href="#工作方式">🧭 工作方式</a> &nbsp;·&nbsp;
  <a href="#快速开始">⚡ 快速开始</a> &nbsp;·&nbsp;
  <a href="#能力">🧩 能力</a> &nbsp;·&nbsp;
  <a href="#社区与讨论">💬 讨论</a> &nbsp;·&nbsp;
  <a href="#参与贡献">🤝 贡献</a> &nbsp;·&nbsp;
  <a href="docs/PR_REVIEW_GUIDE.md">🔎 Review 指南</a> &nbsp;·&nbsp;
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
  <img src="assets/readme/hero-banner-loop-zh-v1-hd-preview.gif" alt="织影" width="100%">
</p>

---

> **织影 / Video Production Buddy** 可以把通用 AI 助手变成一个可见的视频制作流程。它不是让你输入一句提示词然后碰运气，而是通过需求细化、背景研究、方案确认、素材生成、合成和渲染后检查来分阶段推进。
>
> **核心设计是 agent-first：** AI 助手承担制片人与流程编排角色，skills 和 Python 工具负责具体执行，例如 provider 路由、媒体分析、素材生成、合成、校验、checkpoint 和成本记录。
>
> **第一次试用建议：** 先运行零 API key 演示，确认本机可以完成本地渲染；然后在 AI 助手中打开这个文件夹，并输入视频制作 prompt。当需要云端生成图像、视频、配音或音乐时，需要添加 API key。
>
> **不只是图片动起来：** 根据你机器上可用的工具和 provider，系统可以制作图片动画、AI 生成视频、源素材剪辑，也可以从开放素材或 stock motion footage 里组织真实动态镜头做 documentary montage。
>
> <p align="center"><strong>⭐ 如果你希望看到一个开放、可检查的黑盒 AI 视频生成替代方案，欢迎 Star 这个项目，谢谢！</strong></p>

## 演示

<div align="center">
  <video src="https://github.com/user-attachments/assets/df481a12-a150-41c6-97fe-24afcbeb85db" width="100%" controls></video>
</div>

> **织影产品广告** - 展示从需求输入、方案确认、素材生成、合成到最终交付复核的引导式助手流程。

<div align="center">
  <video src="https://github.com/user-attachments/assets/c240b2d1-5c65-41f1-8d71-454ae1f43f51" width="100%" controls></video>
</div>

> **MacBook Air 广告** - “Please help me design an ad video for MacBook Air.”

## 片场看板

Backlot 是本地生产看板，用来显示一个视频项目实际正在发生什么。Chat 会告诉你助手说了什么；Backlot 会从项目文件里展示阶段、脚本、分镜卡、生成素材、provider 决策、花费和活动记录。

<p align="center"><img src="docs/images/backlot/board-live.png" alt="Backlot live board - assets generating" width="920"></p>

这个看板也可以作为审批界面。素材生成可以在逐场景 contact sheet 上暂停，让你在最终渲染前先复核视觉、prompt、成本和质量信号。

<p align="center"><img src="docs/images/backlot/storyboard.png" alt="Backlot storyboard - filmstrip with takes and renders" width="920"></p>

创意门禁会显示当前等待什么、为什么等待：

<p align="center"><img src="docs/images/backlot/script-gate.png" alt="Backlot script gate - awaiting approval" width="920"></p>

本机磁盘上的每个项目都可以从本地 library 看到：

<p align="center"><img src="docs/images/backlot/library.png" alt="Backlot library" width="920"></p>

```bash
python -m backlot open                  # library view - 本机磁盘上的所有项目
python -m backlot open <project-id>     # 打开某一个项目的 live board
python scripts/backlot_simulate_run.py  # 暂时没有项目时，观看一次模拟运行
```

项目完成后，Backlot 可以根据 checkpoint history 和 event timestamps 回放整次生产过程。更多细节见 [`backlot/README.md`](backlot/README.md)。

## 从参考视频开始

从一个参考视频开始，通常比从空白 prompt 开始更快。

Video Production Buddy 可以分析 YouTube 视频、Short、Reel、TikTok 或本地 clip，并把它转成 grounded production plan：

1. 粘贴或指向一个参考视频。
2. 助手分析 transcript、节奏、场景、关键帧和风格。
3. 在完整生产前，你会得到差异化概念、工具路径、成本预期和 sample plan。

```text
我喜欢这个 YouTube Short 的节奏和开头吸引力。
请用类似方式做一个面向高中生的量子计算科普视频。
```

这个 plan 应该明确说明：会保留参考视频的哪些部分，会改变哪些部分，需要哪些 provider 或本地工具，可能花费多少，以及在你当前环境下能真实产出什么。

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
| provider、模型和成本选择不透明 | 可见的 provider/model routing、budget checks 和 approval gates |
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

### 开始前

第一次试用时，你**不需要**云端 API key。建议先跑仓库内置的零 API key 演示，确认本机渲染链路正常，再按需要接入云端 provider。

你需要：

- **Git** - [git-scm.com](https://git-scm.com/downloads)。如果暂时不想安装 Git，也可以从 GitHub 下载 ZIP 并解压。
- **Python 3.10+** - [python.org](https://www.python.org/downloads/)；Ubuntu/Debian 如果无法创建虚拟环境，请先运行 `sudo apt install python3-venv`
- **FFmpeg** - `brew install ffmpeg` / `sudo apt install ffmpeg` / `winget install --id Gyan.FFmpeg` / `choco install ffmpeg -y` / [ffmpeg.org](https://ffmpeg.org/download.html)
- **Node.js 22+** - Remotion、HyperFrames 和 character-animation 渲染需要；安装后应自带 `npm` 和 `npx`
- **Make** - macOS 可运行 `xcode-select --install`，Ubuntu/Debian 可运行 `sudo apt update && sudo apt install make`，Windows 可先安装 [Chocolatey](https://chocolatey.org/install)，再用管理员 PowerShell 运行 `choco install make -y`
- **AI 编程助手** - Codex、Claude Code、Cursor、GitHub Copilot、Windsurf，或其他能读文件和运行 shell 命令的 AI 助手

在 Windows 上，安装 Python、Node.js、FFmpeg 或 Make 后请重新打开 PowerShell，让新的 `PATH` 生效。如果你下载的是 ZIP，请跳过 `git clone`，直接进入解压后的文件夹。

### 检查前置依赖

先确认这些命令都能正常输出版本信息或帮助信息。

macOS/Linux：

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

Windows PowerShell：

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

如果某一行提示找不到命令，请先安装对应工具，并重新打开终端后再检查。

### 第一次本地自检

macOS/Linux：

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

Windows PowerShell：

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

`Set-ExecutionPolicy` 只影响当前 PowerShell 进程，用来允许虚拟环境 activation 脚本运行。`$env:PYTHON = "python"` 会让 Makefile 使用当前虚拟环境里的 Python。后续要添加 API key 时，再把 `.env.example` 复制为 `.env`。

成功时应该看到：

- `make preflight` 输出包含 `composition_runtimes`、provider 可用性和可选择模型的 JSON。
- `make models-list` 以更易读的列表展示可选择模型。
- `make demo` 在 `projects/demos/renders/` 下生成本地 demo MP4。
- 这条 demo 路径不需要任何云端 API key。

demo 成功后，在 AI 助手中打开这个仓库文件夹，并参考下面的[从一个需求开始](#从一个需求开始)。

### 常用检查命令

需要时可以重新查看本机 capability/provider 摘要：

```bash
make preflight
```

不想直接阅读 JSON 时，可以用列表方式查看模型：

```bash
make models-list
make models-list CAPABILITY=video_generation
```

如果 HyperFrames 显示不可用，可以先忽略；零 API key 演示主要依赖 Remotion 和 FFmpeg。

需要时可以重新渲染仓库内置的零 API key 演示：

```bash
make demo
```

这条 demo 路径使用本地 Remotion 组件，不需要云端 API key。第一次 Remotion 渲染可能会下载 Chrome Headless Shell，普通笔记本上需要几分钟。生成的视频位于 `projects/demos/renders/`；如果 Remotion 结束后没有生成预期 MP4，命令会以非零状态退出。

如果遇到问题，请优先留在同一个 AI 助手会话里继续排查。让它检查命令输出、preflight 结果、操作系统/Python/Node/FFmpeg 版本，并帮助你修复本机设置。如果问题像是项目 bug 或文档缺失，请创建 [GitHub Issue](https://github.com/video-production-buddy/video-production-buddy/issues)，并附上这些信息，非常感谢！

### 添加 API Key

所有 key 都是可选的。第一次试用可以先跳过；需要云端生成时，再在 `.env` 中只添加你计划使用的 provider。`make setup` 通常已经创建 `.env`，如果没有，就把 `.env.example` 复制为 `.env`。

```bash
FAL_KEY=your-key              # 图像/视频生成：FLUX、Recraft、Seedance、Kling、Veo、MiniMax video
DASHSCOPE_API_KEY=your-key    # 通义千问语音、Wan 视频、万相图像
ELEVENLABS_API_KEY=your-key   # 配音、音乐、音效
OPENAI_API_KEY=your-key       # OpenAI TTS 和图像生成
MINIMAX_API_KEY=your-key      # MiniMax 音乐生成
PEXELS_API_KEY=your-key       # 可选：免费素材
```

如果你还不熟悉 API key，请先看 [`docs/PROVIDERS.md#where-to-get-api-keys`](docs/PROVIDERS.md#where-to-get-api-keys)，里面有官方注册/取 key 链接、入门推荐顺序和 key 安全规则。请把 key 放在 `.env`，不要粘贴到聊天、截图、issue 或提交到仓库的文件里。

完整 provider 列表、价格说明、模型选择说明和免费额度建议见 [`docs/PROVIDERS.md`](docs/PROVIDERS.md)。`.env.example` 是仓库里的模板；复制成 `.env` 后，把 API key 和可选的 `VPB_*` 默认模型写在同一个本地文件里。

```bash
MINIMAX_API_KEY=your-key
VPB_VIDEO_GENERATION_PROVIDER=minimax
VPB_VIDEO_GENERATION_MODEL=MiniMax-Hailuo-2.3

DASHSCOPE_API_KEY=your-key
VPB_IMAGE_GENERATION_PROVIDER=bailian
VPB_IMAGE_GENERATION_MODEL=qwen-image-2.0-pro
VPB_TTS_PROVIDER=bailian
VPB_TTS_MODEL=qwen3-tts-flash
```

编辑本地 `.env` 后运行：

```bash
make models-check ENV_FILE=.env
```

查看当前 key 对应的 provider/model 值：

```bash
make models-list
make models-list CAPABILITY=video_generation
```

如果你不想手动编辑 `.env`，也可以用命令先预览再写入：

```bash
make models-configure ENV_FILE=.env CAPABILITY=video_generation PRESET=fast DRY_RUN=1
make models-configure ENV_FILE=.env CAPABILITY=video_generation PRESET=fast YES=1
```

用户在具体请求或工具输入中显式指定的 provider/model 仍然优先于文件默认值。

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

对于真实制作需求，助手会先展示 preflight menu，告诉你哪些 provider 和模型选项可用、缺失或可选，再进行会产生费用的生成。

### 从一个需求开始

在 AI 助手中打开仓库文件夹，直接描述你想制作的视频，例如：

```text
请帮我做一个 30 秒新咖啡品牌短视频广告。
受众：下午需要放松的办公室人群。
平台：TikTok 或 Instagram Reels。
风格：温暖、现代、有电影感，不吵。
```

OpenClaw、Claude Code、Codex等助手一般会自动根据仓库内的 agent instructions 选择合适 pipeline，检查可用工具，提出制作方案，并在主要生成工作前等待确认。如果你的助手没有自动读取仓库说明，请让它先读取 `AGENT_GUIDE.md`。如果缺少某个 provider，它应该给出本地 fallback，或者说明需要哪个 API key 才能解锁对应路径。

更多起步示例：

```text
请做一个 45 秒动画解释视频，主题是“为什么天空是蓝色的”。
```

```text
请做一个 75 秒雨中城市生活纪录片混剪，只用真实素材，不要旁白，情绪安静，有音乐。
```

```text
我有一个喜欢的参考视频。请保留它的节奏和开头吸引力，但改成我的 app 的 30 秒产品广告。
```

## 能力

| 方向 | 支持内容 |
|------|----------|
| 🎞️ 生成视频 | 主题到视频、解释型视频、动画、电影感预告、产品广告和短视频。 |
| 💬 交互式需求澄清 | 通过 chat 和 GenUI 在生成前明确目标受众、情绪、约束和理想视频画像。 |
| 📣 广告制作 | 策略、热点搜索、Bilibili/抖音等爆款视频分析、专业制作知识检索、产品约束、样片确认和发布检查。 |
| 🎥 源素材处理 | 口播剪辑、屏幕演示、播客再创作、片段抽取、本地化和混合视频。 |
| 🎞️ 真实素材 montage | 从开放 archives、公有领域素材或可选 stock providers 中检索真实动态镜头，再组织成剪辑。 |
| 🧭 参考视频规划 | 先分析参考视频或用户提供的源素材，再设计新输出。 |
| 🧱 Live production board | Backlot 从 checkpoint/event 文件显示项目状态、门禁、生成素材、花费和回放。 |
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
5. 修改 manifest、schema、tool registry、pipeline 或 agent instructions 时运行 `make test-contracts`。改动涉及 FFmpeg、browser、Node 或 HyperFrames runtime 时，再运行 `make test-integration`。
6. 请求 review 前，用 [`docs/PR_REVIEW_GUIDE.md`](docs/PR_REVIEW_GUIDE.md) 检查架构、provider、安全、依赖和文档声明风险。
7. 在 PR 中说明用户可见影响、列出验证命令；视觉类 README 改动请附截图或 demo 链接。

## 架构

| 路径 | 作用 |
|------|------|
| `AGENT_GUIDE.md` | 生产 agent 的操作契约。 |
| `PROJECT_CONTEXT.md` | 共享架构和开发概览。 |
| `docs/PR_REVIEW_GUIDE.md` | PR、provider 变更、runtime 变更和文档声明的 review 框架。 |
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
make models-list        # 以易读列表查看 provider/model
make models-check       # 校验 .env.example，或用 ENV_FILE=.env 校验本地设置
make models-configure   # 可选：用命令生成 .env 模型偏好更新
make demo               # 渲染仓库内置零 API key 演示套件
make demo-list          # 列出可用演示
make hyperframes-doctor # 验证 HyperFrames runtime
make test-contracts     # 运行 contract tests
make test-integration   # 运行显式 opt-in 的本地 runtime smoke tests
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

# 快速默认测试
make test

# 仅运行 contract tests
make test-contracts

# 显式 opt-in 的本地 runtime 检查（FFmpeg/browser/Node/HyperFrames）
make test-integration

# 手动/媒体 QA alias
make test-qa
```

默认测试会排除 `integration`、`qa`、`browser`、`ffmpeg`、`node`、
`hyperframes`、`slow` 和 `live_provider` markers。Mocked provider tests 仍在默认测试中，
用于确保路径校验和 payload contract 发生在凭据或网络调用之前。

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

织影基于开源项目 [OpenMontage](https://github.com/calesthio/OpenMontage) 开发。如果引用或基于本项目继续开发，也请同时致谢 OpenMontage：

```bibtex
@software{calesthio2026openmontage,
  title = {OpenMontage},
  author = {{Calesthio}},
  year = {2026},
  url = {https://github.com/calesthio/OpenMontage}
}
```

## 致谢

织影由浙江大学 [AI4GC Lab](https://ai4gc.org/) 开发。

本代码库基于优秀的 [OpenMontage](https://github.com/calesthio/OpenMontage) 项目构建；感谢其开源架构与实现基础。
