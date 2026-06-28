# Video Production Buddy Provider Guide

Use this after the zero-key demo works. You do not need every provider; most
projects start with one stock-media key and one generation provider.

> Provider pricing and model names change quickly. Use this guide for the
> Video Production Buddy tool/env-var contract, then verify final pricing in the provider
> dashboard before approving a production budget.

---

## Quick Start: What Should I Set Up?

**Start free, add paid providers only when a project needs them.**

| Step | Cost | What to set up | What it unlocks |
|------|------|----------------|-----------------|
| 1 | **free/local** | No API keys | Run the README demo with Remotion, FFmpeg, and optional Piper TTS |
| 2 | **free tier** | Pexels + Pixabay | Stock photos and videos for source-backed videos |
| 3 | **free tier / paid** | ElevenLabs or Google | Narration, music, sound effects, or Google TTS/image paths |
| 4 | **pay-as-you-go** | Alibaba Cloud Bailian / DashScope | Qwen TTS/ASR plus Wan/Wanxiang image and video under one key |
| 5 | **pay-as-you-go** | fal.ai | FLUX/Recraft images plus Seedance/Kling/Veo/MiniMax video |
| 6 | **paid** | MiniMax or Suno | Music generation, covers, instrumentals, and full songs |
| 7 | **paid** | Runway, HeyGen, Replicate, Higgsfield, xAI, OpenAI | Add only when a project needs that provider's specific output |
| 8 | **local GPU** | Local video/image models | WAN, Hunyuan, CogVideo, LTX, or local diffusion when you have suitable hardware |

### Where To Get API Keys

For your first real production run, do not set up every provider. Add one or two
keys for the capability you need, then run `make preflight` again so the agent
can see what is available.

Key safety rules:

- Put keys in `.env`; this repo ignores `.env`, `.env.local`, and `*.env`.
- Do not paste API keys into chat prompts, issues, screenshots, or committed files.
- Start with free or low-risk providers, then add paid video/image providers only
  when you are ready to approve generation costs.
- Provider dashboards change. If a direct link asks you to sign in or moves, look
  for a menu named **API Keys**, **Developers**, **Tokens**, **Credentials**, or
  **Billing / Usage**.

Recommended beginner order:

| Need | Provider | Get the key | Put this in `.env` | Beginner note |
|------|----------|-------------|--------------------|---------------|
| Free stock photos/video | Pexels | [Pexels API](https://www.pexels.com/api/) | `PEXELS_API_KEY=...` | Good first key because it is free and useful for source-backed videos. |
| Free stock photos/video | Pixabay | [Pixabay API docs](https://pixabay.com/api/docs/) | `PIXABAY_API_KEY=...` | Free backup stock source; login shows the key on the docs page. |
| Free stock photos | Unsplash | [Unsplash Developers](https://unsplash.com/developers) | `UNSPLASH_ACCESS_KEY=...` | Optional, useful when you want more photo variety. |
| Voice / music / SFX | ElevenLabs | [ElevenLabs API keys](https://elevenlabs.io/app/settings/api-keys) | `ELEVENLABS_API_KEY=...` | Good first voice key; free tier is enough for short narration tests. |
| Voice + Google images | Google AI Studio | [Google API keys](https://aistudio.google.com/app/apikey) | `GOOGLE_API_KEY=...` or `GEMINI_API_KEY=...` | For TTS, also enable the Text-to-Speech API in Google Cloud. |
| Image + video gateway | fal.ai | [fal.ai API keys](https://fal.ai/dashboard/keys) | `FAL_KEY=...` or `FAL_AI_API_KEY=...` | One broad pay-as-you-go key for FLUX/Recraft images and several video models. |
| Qwen speech + Wan/Wanxiang media | Alibaba Cloud Bailian / DashScope | [DashScope API key guide](https://www.alibabacloud.com/help/en/model-studio/get-api-key) | `DASHSCOPE_API_KEY=...` | Strong option for Mandarin, Qwen ASR/TTS, Wan video, and Wanxiang images. |
| TTS + images | OpenAI | [OpenAI API keys](https://platform.openai.com/api-keys) | `OPENAI_API_KEY=...` | Requires billing for most accounts; use only when you want OpenAI TTS/image paths. |
| Grok image/video | xAI | [xAI Console](https://console.x.ai/) | `XAI_API_KEY=...` | Sign in, open API keys in the console, then copy the generated key. |
| Video generation | Runway | [Runway developer portal](https://dev.runwayml.com/) | `RUNWAY_API_KEY=...` or `RUNWAYML_API_SECRET=...` | API access may require a paid developer/subscription setup. |
| Avatar/video gateway | HeyGen | [HeyGen API key docs](https://developers.heygen.com/docs/api-key) | `HEYGEN_API_KEY=...` | Often requires API balance separate from web-app credits. |
| Seedance fallback | Replicate | [Replicate API tokens](https://replicate.com/account/api-tokens) | `REPLICATE_API_TOKEN=...` | Useful if you prefer Replicate billing for hosted model runs. |
| Video gateway | Higgsfield | [Higgsfield Cloud](https://cloud.higgsfield.ai/) | `HIGGSFIELD_API_KEY=...` + `HIGGSFIELD_API_SECRET=...` or `HIGGSFIELD_KEY=key:secret` | Sign in, then open the API Keys section. Some plans/features may require subscription access. |
| Music | Suno API | [Suno API quickstart](https://docs.sunoapi.org/suno-api/quickstart) | `SUNO_API_KEY=...` | Third-party API route; check credits and commercial terms before client work. |
| Music | MiniMax | [MiniMax quickstart](https://platform.minimax.io/docs/guides/quickstart-preparation) | `MINIMAX_API_KEY=...` | Make sure the account has a token/paid plan for paid music models. |
| Mandarin TTS | Volcengine Doubao Speech | [Volcengine console](https://console.volcengine.com/) | `DOUBAO_SPEECH_API_KEY=...` and `DOUBAO_SPEECH_VOICE_TYPE=...` | Enable Speech Synthesis 2.0, then create a new-console API key. |
| Sound search | Freesound | [Freesound API access](https://freesound.org/apiv2/apply/) | `FREESOUND_API_KEY=...` | Optional fallback for sound effects and music search. |

After adding keys, verify what the project can see:

```bash
make preflight
```

Without `make`:

```bash
python -c "from tools.tool_registry import registry; import json; registry.discover(); print(json.dumps(registry.provider_menu_summary(), indent=2))"
```

### Environment Variable Summary

```bash
# .env — add your keys here

# FREE (no cost, ever)
PEXELS_API_KEY=              # Stock photos + videos
PIXABAY_API_KEY=             # Stock photos + videos

# GOOGLE (one key, two tools, generous free tier)
GOOGLE_API_KEY=              # Google TTS + Google Imagen
GEMINI_API_KEY=              # Optional Google AI Studio alias accepted by Google image/TTS tools

# VOICE + MUSIC
ELEVENLABS_API_KEY=          # TTS, music, sound effects (10K chars/month free)
OPENAI_API_KEY=              # OpenAI TTS + DALL-E 3 images
XAI_API_KEY=                 # xAI Grok image generation/editing + Grok video generation
DOUBAO_SPEECH_API_KEY=       # Volcengine Doubao Speech TTS (strong Mandarin narration)
DOUBAO_SPEECH_VOICE_TYPE=    # Default Doubao speaker/voice type
DASHSCOPE_API_KEY=           # Qwen3 TTS/ASR, Wan video, Wanxiang image generation/editing
MINIMAX_API_KEY=             # MiniMax Music 2.6 and music-cover generation

# MULTI-MODEL GATEWAY (one key, 6+ tools)
FAL_KEY=                     # FLUX, Recraft, Seedance, Kling, Veo, MiniMax video
FAL_AI_API_KEY=              # Optional fal.ai alias used by several provider tools

# VIDEO
HEYGEN_API_KEY=              # HeyGen avatar video gateway
RUNWAY_API_KEY=              # Runway Gen-4 video (direct)
RUNWAYML_API_SECRET=         # Optional Runway alias accepted by runway_video
REPLICATE_API_TOKEN=         # Replicate-hosted Seedance provider
HIGGSFIELD_API_KEY=          # Higgsfield video API key
HIGGSFIELD_API_SECRET=       # Higgsfield video API secret
HIGGSFIELD_KEY=              # Optional combined Higgsfield key:secret value
SUNO_API_KEY=                # Suno music generation

# LOCAL (no keys needed — just GPU + install)
VIDEO_GEN_LOCAL_ENABLED=     # Set to "true" for local video gen
VIDEO_GEN_LOCAL_MODEL=       # wan2.1-1.3b, wan2.1-14b, hunyuan-1.5, ltx2-local, cogvideo-5b

# STOCK / SEARCH
UNSPLASH_ACCESS_KEY=         # Unsplash stock images
FREESOUND_API_KEY=           # Freesound music/sound search fallback
COVERR_API_KEY=              # Optional Coverr stock video higher-rate/pro access
VIDEVO_API_KEY=              # Optional Videvo stock video search
NASA_API_KEY=                # Optional NASA higher-rate public media access
NARA_API_KEY=                # Optional NARA higher-rate public media access
POND5_API_KEY=               # Optional Pond5 public-domain stock access

# ANALYSIS / LOCAL TUNING
HF_TOKEN=                    # Optional HuggingFace token for speaker diarization
VIDEO_PRODUCTION_BUDDY_CACHE_DIR=       # Optional clip/media cache override
VIDEO_PRODUCTION_BUDDY_CACHE_MAX_GB=    # Optional cache size limit in GB
SUBTITLE_ALIGNER_DEVICE=     # Optional subtitle alignment device, e.g. cpu or cuda
SADTALKER_PATH=              # Optional local SadTalker repo path
WAV2LIP_PATH=                # Optional local Wav2Lip repo path
```

---

## Cloud Providers

### xAI — Grok Image + Video

> **Best if you want one provider for image edits and reference-conditioned short video.** Grok covers both image generation/editing and video generation under one key.

**Tools unlocked:** `grok_image`, `grok_video`
**Env var:** `XAI_API_KEY`

#### Setup

1. Create an xAI developer account
2. Generate an API key in the xAI developer console
3. Add to `.env`: `XAI_API_KEY=xai-...`

#### What it's best for

- Image editing and style transfer
- Multi-image composites into one generated frame
- Short reference-image videos where a person, garment, or product must carry into motion

#### Pricing

Current xAI docs pricing for the Grok media models:

| Model | Price |
|------|-------|
| `grok-imagine-image` | $0.02 per generated image |
| `grok-imagine-image` input images (edits/composites) | $0.002 per input image |
| `grok-imagine-video` at 480p | $0.05/sec |
| `grok-imagine-video` at 720p | $0.07/sec |
| `grok-imagine-video` input images | $0.002 per input image |

Video Production Buddy now uses those published rates in the Grok tool estimators.

---

### Alibaba Cloud Bailian / DashScope — Qwen + Wan + Wanxiang

> **Strong China-region media coverage under one key.** Bailian/DashScope unlocks Qwen speech, Wan video generation/editing, and Wanxiang image generation/editing.

**Tools unlocked:** `cosyvoice_tts`, `qwen_asr`, `wan_video_api`, `wanx_image`
**Env var:** `DASHSCOPE_API_KEY`

#### Setup

1. Create or open an Alibaba Cloud Bailian account
2. Generate an API key in the Bailian console
3. Enable the specific model families you plan to use: Qwen TTS/ASR, Wan video, and/or Wanxiang image
4. Add to `.env`: `DASHSCOPE_API_KEY=your-key-here`

#### What It's Best For

- Natural Mandarin and bilingual narration through Qwen3/CosyVoice models
- Fast Chinese and multilingual transcription with `qwen3-asr-flash`
- Wan API video generation: text-to-video, image-to-video, reference-to-video, and video editing
- Wanxiang image generation/editing with style presets, seeds, and multi-image references
- Product-visible ad workflows where a still reference can condition Wan image/video generation

#### API Notes

Video Production Buddy uses two DashScope patterns:

- Qwen TTS/ASR calls the multimodal generation endpoint directly
- Wan/Wanxiang media tools submit async tasks, poll the task endpoint, then download generated assets

Wanxiang image sizes use `*` separators such as `1024*1024`, not `1024x1024`.

#### Pricing

Pricing is model-specific in Bailian/DashScope. The tools estimate cost from the model metadata in code and prefer provider-returned usage when available; check the Bailian console before committing a production budget.

---

### fal.ai — Multi-Model Gateway

> **Broad single-key coverage.** One API key unlocks image and video providers across multiple models.

**Tools unlocked:** `flux_image`, `recraft_image`, `seedance_video`, `kling_video`, `veo_video`, `minimax_video`
**Env var:** `FAL_KEY` or `FAL_AI_API_KEY`

#### Setup

1. Go to [fal.ai](https://fal.ai/) and click **Sign up** (GitHub or Google)
2. Navigate to [fal.ai/dashboard/keys](https://fal.ai/dashboard/keys)
3. Click **Create Key**, copy it
4. Add to `.env`: `FAL_KEY=your-key-here` (or `FAL_AI_API_KEY=your-key-here`)

#### Pricing

No subscription — pure pay-as-you-go, no minimum spend.

**Image generation:**

| Model | Price | Per $1 |
|-------|-------|--------|
| FLUX Pro v1.1 | $0.05/image | 20 images |
| FLUX Dev | $0.03/image | 33 images |
| Recraft v3 | ~$0.04/image | 25 images |

**Video generation:**

| Model | Price | Per $1 |
|-------|-------|--------|
| Kling 2.5 Turbo Pro | $0.07/sec | 14 seconds |
| Seedance | varies by model page | varies |
| MiniMax | ~$0.05/sec | 20 seconds |
| Veo 3 | $0.40/sec | 2.5 seconds |
| WAN 2.5 | $0.05/sec | 20 seconds |

**Free tier:** None — but $0 to start, you only pay for what you use.

---

### Replicate — Seedance Video

> **Alternative Seedance route.** Use this when you prefer Replicate billing or when the fal.ai Seedance route is unavailable.

**Tools unlocked:** `seedance_replicate`
**Env var:** `REPLICATE_API_TOKEN`

#### Setup

1. Create or open a Replicate account
2. Generate an API token at [replicate.com/account/api-tokens](https://replicate.com/account/api-tokens)
3. Add to `.env`: `REPLICATE_API_TOKEN=your-token-here`

#### What It's Best For

- Premium cinematic video generation through Seedance
- A fallback route when `seedance_video` cannot use fal.ai
- Keeping Seedance access separate from other fal.ai-hosted video models

#### Pricing

Replicate charges through its own model billing. Check the Replicate model page and account dashboard before approving a production budget.

---

### ElevenLabs — Voice, Music, Sound Effects

> **Premium voice quality.** Best TTS for narration-heavy videos. Also generates music and sound effects.

**Tools unlocked:** `elevenlabs_tts`, `music_gen`
**Env var:** `ELEVENLABS_API_KEY`

#### Setup

1. Go to [elevenlabs.io](https://elevenlabs.io) and click **Sign up**
2. Go to **Profile** (bottom-left) > **API Keys**, or visit [elevenlabs.io/app/settings/api-keys](https://elevenlabs.io/app/settings/api-keys)
3. Click **Create API Key**, name it, copy it
4. Add to `.env`: `ELEVENLABS_API_KEY=xi_your-key-here`

#### Pricing

| Plan | Price | Characters/month | Key features |
|------|-------|-------------------|--------------|
| **Free** | $0 | 10,000 | 3 custom voices, API access, attribution required |
| Starter | $5/mo | 30,000 | No attribution |
| Creator | $22/mo | 100,000 | Professional voice cloning |
| Pro | $99/mo | 500,000 | 96kbps audio, usage analytics |
| Scale | $330/mo | 2,000,000 | Priority support |

**Free tier:** 10,000 characters/month (roughly 2-3 minutes of narration). API access included. Music generation and sound effects also available on free tier with limited credits.

---

### Doubao Speech — Mandarin TTS

> **Strong Mandarin narration.** Volcengine Doubao Speech is a good choice for Chinese explainer voiceovers and long-form narration that needs subtitle timing metadata.

**Tools unlocked:** `doubao_tts`
**Env vars:** `DOUBAO_SPEECH_API_KEY`, `DOUBAO_SPEECH_VOICE_TYPE`

#### Setup

1. Open the Volcengine Doubao Speech console and enable Speech Synthesis 2.0.
2. Create a new-console API Key.
3. Choose a Speech 2.0 voice type, for example `zh_female_vv_uranus_bigtts`.
4. Add to `.env`:
   ```bash
   DOUBAO_SPEECH_API_KEY=your-api-key
   DOUBAO_SPEECH_VOICE_TYPE=zh_female_vv_uranus_bigtts
   ```

#### API Notes

Video Production Buddy uses the new-console API key flow:

```text
X-Api-Key: ${DOUBAO_SPEECH_API_KEY}
X-Api-Resource-Id: seed-tts-2.0
```

Do not pass a new-console API Key as `X-Api-App-Id` or `X-Api-Access-Key`. That mismatch can produce `load grant: requested grant not found`.

#### What It Is Best For

- Natural Mandarin narration for Chinese-language explainers
- Async long-form narration via `/api/v3/tts/submit` and `/api/v3/tts/query`
- Character-level timing metadata for subtitle alignment
- Calm educational pacing where the video duration can follow the approved voice rhythm

#### Pacing

Start with `speech_rate: 0` for natural Mandarin delivery. If the approved format needs a tighter runtime, compare short samples at `speech_rate: 25` or `50` before generating the full narration. Do not force Doubao to match another provider's duration unless the user explicitly wants that tradeoff.

#### Pricing

Doubao Speech 2.0 is billed by character package or usage in Volcengine. Video Production Buddy estimates cost from text length and prefers provider-returned usage metadata when available.

---

### Google — TTS + Imagen (Shared Key)

> **One key, two tools.** Google Cloud TTS has 700+ voices in 50+ languages — the strongest localization option. Imagen 4 generates high-quality images.

**Tools unlocked:** `google_tts`, `google_imagen`
**Env var:** `GOOGLE_API_KEY` or `GEMINI_API_KEY`

#### Setup

1. Go to [Google AI Studio](https://aistudio.google.com/) and sign in
2. Navigate to [aistudio.google.com/apikey](https://aistudio.google.com/apikey)
3. Click **Create API Key**, select a Google Cloud project
4. Copy the key
5. Add to `.env`: `GOOGLE_API_KEY=AIza...` (or `GEMINI_API_KEY=AIza...`)

**For TTS specifically**, you also need to enable the Text-to-Speech API:
1. Visit [console.cloud.google.com/apis/library/texttospeech.googleapis.com](https://console.cloud.google.com/apis/library/texttospeech.googleapis.com)
2. Click **Enable**
3. Make sure your API key's restrictions allow the Text-to-Speech API

**For Imagen**, enable the Generative Language API:
1. Visit [console.cloud.google.com/apis/library/generativelanguage.googleapis.com](https://console.cloud.google.com/apis/library/generativelanguage.googleapis.com)
2. Click **Enable**

#### Google TTS Pricing

| Voice Type | Free tier | Paid (per 1M chars) | Notes |
|-----------|-----------|---------------------|-------|
| **Standard** | 1M chars/month | $4.00 | Basic quality, fast |
| **WaveNet** | 1M chars/month | $16.00 | Natural-sounding |
| **Neural2** | 1M chars/month | $16.00 | Best quality |
| **Studio** | — | $24.00 | Professional studio voices |
| **Chirp** | — | $4.00 | Conversational style |

The free tiers apply *independently* — you get 1M Standard AND 1M WaveNet AND 1M Neural2 characters per month free. That's roughly 250+ minutes of narration per month at zero cost.

#### Google Imagen Pricing

| Model | Price per image |
|-------|----------------|
| Imagen 4 Fast | $0.02 |
| Imagen 4 Standard | $0.04 |
| Imagen 4 Ultra | $0.06 |

**Free tier for Imagen:** None. Paid tier only.

**New account bonus:** Google Cloud offers **$300 in free credits** for new accounts (90-day trial), applicable to both TTS and Imagen.

#### Google TTS Voice Types

Google TTS offers 700+ voices across 50+ languages. Voice names follow the pattern `{language}-{type}-{letter}`:

| Type | Example | Quality | Cost |
|------|---------|---------|------|
| **Chirp 3 HD** | `en-US-Chirp3-HD-Orus` | **Best (2024, most natural)** | **Mid — default** |
| Standard | `en-US-Standard-A` | Good | Cheapest |
| WaveNet | `en-US-WaveNet-D` | Very good | Mid |
| Neural2 | `en-US-Neural2-D` | Excellent | Mid |
| Studio | `en-US-Studio-O` | Professional | Highest |
| Journey | `en-US-Journey-D` | Conversational (long-form) | Mid |

**Recommended voices:** `en-US-Chirp3-HD-Orus` (male, rich/cinematic), `en-US-Chirp3-HD-Aoede` (female, warm). These are Google's newest tier — most natural-sounding, uses the v1beta1 endpoint automatically.

**Languages include:** English (US, UK, AU, IN), Spanish, French, German, Italian, Portuguese, Japanese, Korean, Chinese (Mandarin, Cantonese), Arabic, Hindi, Russian, Dutch, Polish, Turkish, Vietnamese, Thai, Indonesian, and 30+ more.

---

### OpenAI — TTS + Image Generation

> **Solid all-rounder.** DALL-E 3 handles complex multi-element compositions well. TTS is fast and affordable.

**Tools unlocked:** `openai_tts`, `openai_image`
**Env var:** `OPENAI_API_KEY`

#### Setup

1. Go to [platform.openai.com/signup](https://platform.openai.com/signup) and create an account
2. Add a payment method at [platform.openai.com/account/billing](https://platform.openai.com/account/billing)
3. Navigate to [platform.openai.com/api-keys](https://platform.openai.com/api-keys)
4. Click **Create new secret key**, name it, copy it
5. Add to `.env`: `OPENAI_API_KEY=sk-...`

#### TTS Pricing

| Model | Price per 1M characters |
|-------|------------------------|
| tts-1 | $15.00 |
| tts-1-hd | $30.00 |
| gpt-4o-mini-tts | $12.00 |

#### Image Pricing

| Model | Size | Quality | Price per image |
|-------|------|---------|----------------|
| DALL-E 3 | 1024x1024 | standard | $0.040 |
| DALL-E 3 | 1024x1024 | hd | $0.080 |
| DALL-E 3 | 1024x1792 | standard | $0.080 |
| DALL-E 3 | 1024x1792 | hd | $0.120 |

**Free tier:** None. Requires prepaid billing. Previously offered $5 in free credits for new accounts (discontinued for most signups).

---

### Runway — Gen-3/Gen-4 Video

> **Highest-rated AI video quality.** #1 on Elo rankings. Professional-grade video generation with Gen-3 Alpha Turbo, Gen-4 Turbo, and Gen-4 Aleph models.

**Tools unlocked:** `runway_video`
**Env var:** `RUNWAY_API_KEY` or `RUNWAYML_API_SECRET`

#### Setup

1. Go to [dev.runwayml.com](https://dev.runwayml.com/) and create a developer account
2. Subscribe to a paid plan (Standard or above — API requires subscription)
3. Generate an API key from the developer portal
4. Add to `.env`: `RUNWAY_API_KEY=key_...` (or `RUNWAYML_API_SECRET=key_...`)

#### Pricing

| Plan | Price | Credits/month | Video capacity |
|------|-------|---------------|----------------|
| **Free** | $0 | 125 one-time | ~5 seconds Gen-4 |
| Standard | $12/mo | 625 | ~25 seconds Gen-4 |
| Pro | $28/mo | 2,250 | ~90 seconds Gen-4 |
| Unlimited | $76/mo | Unlimited (Explore Mode) | Unlimited Gen-4 Turbo |

**API pricing (approximate):**

| Model | Price per second |
|-------|-----------------|
| Gen-3 Alpha Turbo | ~$0.05 |
| Gen-4 Turbo | ~$0.05 |
| Gen-4 Aleph | ~$0.15 |

**Free tier:** 125 one-time credits (no monthly renewal). Enough for about 5 seconds of Gen-4 video. API access requires a paid subscription.

---

### Higgsfield — Multi-Model Video Orchestrator

> **Multi-model video platform.** Routes to Kling 3.0, Veo 3.1, Sora 2, WAN 2.5, and proprietary Soul Cinema through a single API. Includes Soul ID for character consistency across clips.

**Tools unlocked:** `higgsfield_video`
**Env vars:** `HIGGSFIELD_API_KEY` + `HIGGSFIELD_API_SECRET` (or combined `HIGGSFIELD_KEY=key:secret`)

#### Setup

1. Go to [cloud.higgsfield.ai](https://cloud.higgsfield.ai/) and create an account
2. Subscribe to a plan (Starter or above for API access)
3. Sign in to [Higgsfield Cloud](https://cloud.higgsfield.ai/) and open the API Keys section
4. Generate an API key and secret
5. Add to `.env`:
   ```
   HIGGSFIELD_API_KEY=your-api-key
   HIGGSFIELD_API_SECRET=your-api-secret
   # or:
   HIGGSFIELD_KEY=your-api-key:your-api-secret
   ```

#### Pricing

| Plan | Price | Notes |
|------|-------|-------|
| Free | $0 | Limited credits |
| Starter | $15/mo | Basic allocation |
| Plus | $34/mo | Mid-tier, ~33-56 Kling 3.0 clips |
| Ultra | $84/mo | High volume |

**Per-generation costs (approximate, via credits):**

| Model | Cost per clip |
|-------|--------------|
| Kling 3.0 | ~$0.10 (cheapest) |
| WAN 2.5 | ~$0.10 |
| Soul Cinema | ~$0.15 |
| Veo 3.1 | ~$0.50 |
| Sora 2 | ~$0.50 |

**Free tier:** Limited credits on signup. No monthly renewal on free plan.

---

### HeyGen — Avatar Video Gateway

> **Multi-model video gateway.** Access VEO, Sora, Runway, Kling, and Seedance through a single API.

**Tools unlocked:** `heygen_video`
**Env var:** `HEYGEN_API_KEY`

#### Setup

1. Go to [app.heygen.com/register](https://app.heygen.com/register) and create an account
2. Navigate to the API section in settings
3. Generate your API key
4. Add API balance (prepaid, separate from web plan credits)
5. Add to `.env`: `HEYGEN_API_KEY=your-key-here`

#### Pricing

| Service | Price |
|---------|-------|
| Avatar video (Engine III) | $0.017/sec |
| Avatar video (Engine IV) | $0.10/sec |
| Prompt to Video | $0.033/sec |
| Video Translation (Speed) | $0.05/sec |
| Video Translation (Precision) | $0.10/sec |

**Web plans:**

| Plan | Price | Notes |
|------|-------|-------|
| Free | $0 | 1 credit (demo) |
| Creator | $24/mo | Limited credits |
| Business | $72/mo | API access, more credits |

**Free tier:** 1 credit on web platform. API is pay-as-you-go with prepaid balance.

---

### MiniMax Music — Music 2.6 + Covers

> **Fast synchronous music generation.** MiniMax is useful for background tracks, instrumentals, structured lyric songs, and cover-style generations from reference audio.

**Tools unlocked:** `minimax_music`
**Env var:** `MINIMAX_API_KEY`

#### Setup

1. Create or sign in to a MiniMax API Platform account
2. Open **Account > API Keys** from the MiniMax API Platform and create a key
3. Add to `.env`: `MINIMAX_API_KEY=your-key-here`
4. For paid models such as `music-2.6` and `music-cover`, make sure the account has a Token Plan

#### What It's Best For

- Background music from a style/mood prompt
- Instrumental tracks under narration
- Songs with structured lyric tags such as `[Verse]`, `[Chorus]`, and `[Bridge]`
- Cover generations from a reference audio URL or local audio file
- Fast synchronous generation where you do not want to poll a long-running job

#### Pricing

Video Production Buddy's current estimator treats `music-2.6` and `music-cover` as paid generation models and also exposes `*-free` model variants. Check MiniMax account limits and plan details before proposing a production budget.

---

### Suno — AI Music Generation

> **Full songs with vocals and lyrics.** Any genre, up to 8 minutes. Instrumentals or vocal tracks.

**Tools unlocked:** `suno_music`
**Env var:** `SUNO_API_KEY`

#### Setup

1. Go to [suno.com](https://suno.com) and create a Suno account
2. For API access, go to [sunoapi.org](https://sunoapi.org) and create an account
3. Navigate to the dashboard and copy your API key
4. Add credits (1 credit = $0.005 USD)
5. Add to `.env`: `SUNO_API_KEY=your-key-here`

#### Pricing

**Suno platform:**

| Plan | Price | Credits | Notes |
|------|-------|---------|-------|
| Free | $0 | 50/day | ~10 songs/day, non-commercial only |
| Pro | $10/mo | 2,500/mo | Commercial license |
| Premier | $30/mo | 10,000/mo | Commercial license |

**API (via sunoapi.org):** Pay-as-you-go, 1 credit = $0.005. Each generation produces 2 tracks.

---

### Pexels — Free Stock Media

> **Completely free.** No cost, no attribution required, commercial use allowed.

**Tools unlocked:** `pexels_image`, `pexels_video`
**Env var:** `PEXELS_API_KEY`

#### Setup

1. Go to [pexels.com/join](https://www.pexels.com/join/) and create a free account
2. Navigate to [pexels.com/api](https://www.pexels.com/api/)
3. Click **Your API Key** or request API access
4. Copy your key from the dashboard
5. Add to `.env`: `PEXELS_API_KEY=your-key-here`

#### Pricing

**Completely free.** No paid tiers. No attribution required. Commercial use allowed.

- 200 requests/hour
- 20,000 requests/month
- Photo and video search + download

---

### Pixabay — Free Stock Media

> **Completely free.** 5M+ royalty-free images and videos.

**Tools unlocked:** `pixabay_image`, `pixabay_video`
**Env var:** `PIXABAY_API_KEY`

#### Setup

1. Go to [pixabay.com/accounts/register](https://pixabay.com/accounts/register/) and create a free account
2. Navigate to [pixabay.com/api/docs](https://pixabay.com/api/docs/)
3. Your API key is displayed at the top of the docs page (after login)
4. Copy the key
5. Add to `.env`: `PIXABAY_API_KEY=your-key-here`

#### Pricing

**Completely free.** No paid tiers. No attribution required. Commercial use allowed.

- ~100 requests/minute
- 5,000 requests/hour
- Photo and video search + download
- Standard API limited to 1280px images (full resolution requires editorial API)

---

## Local Providers (Free, No API Key)

These providers run entirely on your machine. No network, no API key, no cost. Some require a GPU.

### Remotion — Programmatic Video Composition

> **React-based video rendering.** Turns still images into animated video with spring physics, animated text cards, stat cards, charts, and transitions. **This is the key fallback when no video generation providers are configured** — the agent generates images and Remotion animates them into professional-looking video.

**Tool:** `video_compose` (with `operation="render"` — auto-routes to Remotion when needed)
**Runtime:** CPU (Node.js required)
**Env var:** None

#### Setup

```bash
# Included in make setup, or install manually:
cd remotion-composer
npx --yes pnpm install --frozen-lockfile
cd ..
```

Requires **Node.js 18+** and `npx`. Dependencies are locked by `remotion-composer/pnpm-lock.yaml`; `make install-remotion` automatically uses pnpm when that lockfile exists.

#### What Remotion Renders

| Component | What it produces |
|-----------|-----------------|
| **TextCard** | Animated title/body text with spring physics entrance |
| **StatCard** | Animated statistics with count-up animations |
| **ProgressBar** | Animated progress indicators |
| **CalloutBox** | Highlighted callout panels with icon animations |
| **ComparisonCard** | Side-by-side comparison layouts |
| **BarChart / LineChart / PieChart** | Animated data visualizations |
| **KPIGrid** | Multi-metric dashboard cards |
| **BrandCard / BrowserTabs / Dashboard / Notification** | Registry-backed product, software, and workflow scenes |
| **BadgeFreeze / Checkmark / LineConnection / StatRoll** | Short confirmation, comparison, and motion-graphics beats |
| **Image scenes** | Still images with spring-animated motion (replaces Ken Burns) |

#### When Does Remotion Activate?

The `video_compose` tool's `render` operation uses the proposal/edit runtime contract and routes to Remotion for rich scene work:
- Cuts contain still images (`.png`, `.jpg`, etc.)
- Cuts have `type` set to a Remotion registry scene such as `text_card`, `stat_card`, `brand_card`, `browser_tabs`, or `dashboard`
- Cuts specify `animation` or `transition_in`/`transition_out`

If `render_runtime="remotion"` was locked and Remotion is unavailable, that is a blocker; the agent must fix setup or get a user-approved runtime substitution. If no runtime was locked and Remotion is unavailable, `video_compose` can use FFmpeg for simpler fallback output.

**Cost:** Free. Always local.

---

### HyperFrames - HTML/CSS/GSAP Video Composition

> **GSAP-native local rendering.** HyperFrames is the preferred runtime for motion-graphics-heavy HTML compositions and the `character-animation` pipeline's rigged SVG character acting.

**Tool:** `hyperframes_compose` directly, or `video_compose` with `edit_decisions.render_runtime="hyperframes"`
**Runtime:** CPU (Node.js >= 22, FFmpeg, and `npx` required)
**Env var:** None

#### Setup

```bash
node --version
ffmpeg -version
npx --yes hyperframes doctor
```

The CLI is consumed as `npx hyperframes`. Do not use `npx @hyperframes/cli`; that package name is not the Video Production Buddy runtime path.

#### What HyperFrames Renders

| Use case | What it produces |
|----------|------------------|
| **Kinetic typography** | HTML/CSS text animation driven by GSAP timelines |
| **Product / launch videos** | Structured HTML scenes, registry blocks, and transitions |
| **Website-to-video** | Browser-captured site compositions with HyperFrames validation |
| **Character animation** | SVG character rigs, pose/action timelines, and GSAP acting beats rendered to `renders/final.mp4` |

HyperFrames workspaces live under `projects/<project-name>/hyperframes/`. Final videos still follow the normal Video Production Buddy convention: `projects/<project-name>/renders/final.mp4`.

**Cost:** Free. Always local.

---

### Piper TTS — Offline Text-to-Speech

> **Completely free, fully offline TTS.** No network required. Good quality for drafts and budget-constrained projects.

**Tool:** `piper_tts`
**Runtime:** CPU (no GPU needed)
**Env var:** None

#### Setup

```bash
# Install via pip
pip install piper-tts

# Or download the binary from GitHub
# https://github.com/rhasspy/piper/releases

# Download a voice model (first run downloads automatically)
piper --download-dir ~/.piper/models --model en_US-lessac-medium
```

**Available voices:** ~30 English voices plus voices for German, French, Spanish, Italian, and other languages. Lower variety than cloud providers but completely free and offline.

**Quality:** Good for drafts, internal videos, and budget projects. For client-facing narration, use ElevenLabs or Google TTS.

---

### Local Video Generation (GPU Required)

> **Free AI video generation.** Requires an NVIDIA GPU with sufficient VRAM.

**Tools:** `wan_video`, `hunyuan_video`, `cogvideo_video`, `ltx_video_local`
**Runtime:** Local GPU (CUDA required)
**Env vars:** `VIDEO_GEN_LOCAL_ENABLED=true`, `VIDEO_GEN_LOCAL_MODEL=<model>`

#### Setup

```bash
# 1. Install the GPU stack
make install-gpu
# Or manually:
pip install diffusers transformers accelerate torch pillow requests

# 2. Enable local generation in .env
VIDEO_GEN_LOCAL_ENABLED=true

# 3. Choose a model based on your GPU VRAM
VIDEO_GEN_LOCAL_MODEL=wan2.1-1.3b      # 6GB+ VRAM (entry-level)
VIDEO_GEN_LOCAL_MODEL=wan2.1-14b       # 24GB+ VRAM (best local quality)
VIDEO_GEN_LOCAL_MODEL=hunyuan-1.5      # 12GB+ VRAM
VIDEO_GEN_LOCAL_MODEL=ltx2-local       # 8GB+ VRAM (fastest)
VIDEO_GEN_LOCAL_MODEL=cogvideo-5b      # 10GB+ VRAM
VIDEO_GEN_LOCAL_MODEL=cogvideo-2b      # 6GB+ VRAM (lightest)
```

#### Model Comparison

| Model | VRAM | Quality | Speed | Best for |
|-------|------|---------|-------|----------|
| **WAN 2.1 (1.3B)** | 6GB | Good | Fast | Entry-level GPU, quick iteration |
| **WAN 2.1 (14B)** | 24GB | Excellent | Slow | Best quality-to-VRAM ratio |
| **Hunyuan 1.5** | 12GB | Very good | Medium | Mid-range GPUs |
| **LTX-2** | 8GB | Good | Fastest | Quick drafts, lowest latency |
| **CogVideo (5B)** | 10GB | Good | Medium | Balanced option |
| **CogVideo (2B)** | 6GB | Fair | Fast | Low-VRAM experimentation |

**All local models support:** Image-to-video, text-to-video, offline generation, seeded reproducibility.

---

### Local Diffusion — Offline Image Generation (GPU Required)

> **Free Stable Diffusion image generation.** No API cost, fully offline.

**Tool:** `local_diffusion`
**Runtime:** Local GPU (CUDA required)
**Env var:** None (enable by installing dependencies)

#### Setup

```bash
pip install diffusers transformers accelerate torch
```

First run downloads the model (~4GB). Subsequent runs use the cached model.

**VRAM requirement:** 4GB+ (8GB recommended for 1024x1024 images)

**Supports:** Negative prompts, seeds, custom sizes. Quality is lower than FLUX or DALL-E 3 but completely free and offline.

---

### LTX-2 on Modal — Self-Hosted Cloud GPU

> **Run LTX-2 on Modal's cloud GPUs.** Your own endpoint, your own scale. More consistent than local GPU, cheaper than commercial APIs.

**Tool:** `ltx_video_modal`
**Runtime:** Cloud (self-hosted)
**Env var:** `MODAL_LTX2_ENDPOINT_URL`

#### Setup

1. Create a [Modal](https://modal.com) account
2. Deploy the LTX-2 endpoint (see Modal docs)
3. Set the endpoint URL in `.env`: `MODAL_LTX2_ENDPOINT_URL=https://your-modal-endpoint`

**Modal pricing:** ~$0.99/hour for A100 GPU time. Cost per video depends on generation time.

---

### Other Local Tools (Always Available)

These tools require only FFmpeg or Python packages — no GPU, no API key.

| Tool | Install | What it does |
|------|---------|-------------|
| **FFmpeg tools** (video_compose, video_stitch, video_trimmer, audio_mixer, audio_enhance, color_grade, face_enhance, frame_sampler, scene_detect) | `brew install ffmpeg` / `sudo apt install ffmpeg` / `winget install FFmpeg` | Video editing, audio processing, color grading, analysis |
| **Transcriber** | `pip install faster-whisper` | Speech-to-text with word-level timestamps |
| **Subtitle Aligner** | `pip install faster-whisper` | ASS subtitle timing aligned to TTS audio instead of estimated word counts |
| **Background Remove** | `pip install rembg` (CPU) or `pip install rembg[gpu]` | Remove image/video backgrounds |
| **Upscale** | `pip install realesrgan` (requires PyTorch + CUDA) | Real-ESRGAN image/video upscaling |
| **Face Restore** | `pip install gfpgan` (requires PyTorch) | CodeFormer/GFPGAN face restoration |
| **Code Snippet** | `pip install Pygments Pillow` | Syntax-highlighted code images |
| **Diagram Gen** | `npm install -g @mermaid-js/mermaid-cli` | Mermaid diagram rendering |
| **Math Animate** | `pip install manim` | ManimCE mathematical animations |
| **Subtitle Gen** | No install needed | SRT/VTT subtitle file generation |
| **Video Understand** | `pip install transformers torch` | CLIP/BLIP-2 visual analysis |
| **Talking Head** | Clone [SadTalker](https://github.com/OpenTalker/SadTalker) and set `SADTALKER_PATH` | Avatar animation from photo + audio |
| **Lip Sync** | Clone [Wav2Lip](https://github.com/Rudrabha/Wav2Lip) and set `WAV2LIP_PATH`, or install an importable package | Audio-driven lip synchronization |

---

## Provider-to-Tool Mapping

| Provider | Env Var | Tools Unlocked | Cost |
|----------|---------|---------------|------|
| **Pexels** | `PEXELS_API_KEY` | `pexels_image`, `pexels_video` | Free |
| **Pixabay** | `PIXABAY_API_KEY` | `pixabay_image`, `pixabay_video` | Free |
| **Piper** | — (install only) | `piper_tts` | Free |
| **Google** | `GOOGLE_API_KEY` or `GEMINI_API_KEY` | `google_tts`, `google_imagen` | Free tier + paid |
| **ElevenLabs** | `ELEVENLABS_API_KEY` | `elevenlabs_tts`, `music_gen` | Free tier + paid |
| **fal.ai** | `FAL_KEY` or `FAL_AI_API_KEY` | `flux_image`, `recraft_image`, `seedance_video`, `kling_video`, `veo_video`, `minimax_video` | Pay-as-you-go |
| **Bailian / DashScope** | `DASHSCOPE_API_KEY` | `cosyvoice_tts`, `qwen_asr`, `wan_video_api`, `wanx_image` | Pay-as-you-go |
| **OpenAI** | `OPENAI_API_KEY` | `openai_tts`, `openai_image` | Paid only |
| **xAI** | `XAI_API_KEY` | `grok_image`, `grok_video` | Paid only |
| **Doubao Speech** | `DOUBAO_SPEECH_API_KEY` + `DOUBAO_SPEECH_VOICE_TYPE` | `doubao_tts` | Paid / package billing |
| **Runway** | `RUNWAY_API_KEY` or `RUNWAYML_API_SECRET` | `runway_video` | Free trial + paid |
| **Replicate** | `REPLICATE_API_TOKEN` | `seedance_replicate` | Pay-as-you-go |
| **Higgsfield** | `HIGGSFIELD_API_KEY` + `HIGGSFIELD_API_SECRET` or `HIGGSFIELD_KEY` | `higgsfield_video` | Subscription / pay-as-you-go |
| **HeyGen** | `HEYGEN_API_KEY` | `heygen_video` | Pay-as-you-go |
| **MiniMax** | `MINIMAX_API_KEY` | `minimax_music` | Pay-as-you-go |
| **Suno** | `SUNO_API_KEY` | `suno_music` | Pay-as-you-go |
| **Freesound** | `FREESOUND_API_KEY` | `freesound_music` | Free / API terms |
| **Additional stock sources** | `UNSPLASH_ACCESS_KEY`, `COVERR_API_KEY`, `VIDEVO_API_KEY`, `NASA_API_KEY`, `NARA_API_KEY`, `POND5_API_KEY` | stock-source adapters for source/clip acquisition | Free / provider-specific |
| **Local GPU** | `VIDEO_GEN_LOCAL_ENABLED` | `wan_video`, `hunyuan_video`, `cogvideo_video`, `ltx_video_local` | Free (GPU required) |
| **Local Diffusion** | — (install only) | `local_diffusion` | Free (GPU required) |
| **Modal** | `MODAL_LTX2_ENDPOINT_URL` | `ltx_video_modal` | Self-hosted cloud |
| **Local Avatar** | `SADTALKER_PATH`, `WAV2LIP_PATH` | `talking_head`, `lip_sync` | Free (local install) |

---

## Capability Coverage

Coverage is discovered from the live registry at preflight. This table groups the main provider families:

| Capability | Cloud Providers | Local Providers | Free Options |
|-----------|----------------|-----------------|--------------|
| **Image Generation** | FLUX, Grok, Google Imagen, DALL-E 3, Recraft, Wanxiang | Local Diffusion | Pexels, Pixabay (stock) |
| **Video Generation** | Grok, Kling, Runway, Veo, Higgsfield, MiniMax, HeyGen, Seedance, Wan API | WAN, Hunyuan, CogVideo, LTX | Pexels, Pixabay (stock) |
| **Text-to-Speech** | ElevenLabs, Google TTS, OpenAI, Doubao, Qwen/CosyVoice | Piper | Piper, Google free tier, ElevenLabs free tier |
| **Music Generation** | ElevenLabs, MiniMax, Suno | — | ElevenLabs free tier, Freesound/Pixabay search, provider-specific trial/free variants |
| **Post-Production** | — | FFmpeg (compose, stitch, trim, mix, enhance, grade) | All free |
| **Analysis and transcription** | Qwen ASR | WhisperX, Scene Detect, Frame Sampler, CLIP/BLIP-2, audio/video probes | Local analysis is free |
| **Enhancement** | — | Upscale, BG Remove, Face Enhance, Face Restore | All free |
| **Avatar** | — | SadTalker, Wav2Lip | All free |

---

## FAQ

**Q: What's the absolute minimum I need to produce a video?**
A: FFmpeg + Node.js (both free, local). FFmpeg handles video assembly, audio mixing, and subtitles. With Node.js, Remotion renders still images into animated video — so even without any video generation API, the agent generates images and Remotion turns them into professional-looking video with spring animations, text cards, and transitions. Add Piper TTS for free narration and Pexels/Pixabay for free stock footage.

**Q: I don't have any video generation providers. Can I still make videos?**
A: Yes. The agent generates still images (via any image provider — even free stock from Pexels/Pixabay) and Remotion composes them into animated video with spring physics transitions, text cards, stat cards, and charts. This is the default path for explainer and animation pipelines when no video gen is configured.

**Q: What's one low-friction way to get AI-generated images and video?**
A: fal.ai (`FAL_KEY` or `FAL_AI_API_KEY`) is one pay-as-you-go option with broad single-key coverage. It unlocks FLUX/Recraft images plus Seedance, Kling, Veo, and MiniMax video. Bailian/DashScope (`DASHSCOPE_API_KEY`) is another broad option if you want Qwen speech plus Wan/Wanxiang image/video coverage.

**Q: I have a GPU. What can I run locally for free?**
A: Set `VIDEO_GEN_LOCAL_ENABLED=true` and install `diffusers`. You get WAN 2.1, Hunyuan, CogVideo, and LTX video generation plus Stable Diffusion image generation — all free, all offline.

**Q: Which TTS provider should I use?**
A: For quality -> ElevenLabs. For localization (50+ languages) -> Google TTS. For Mandarin or bilingual Chinese/English work -> Doubao or Qwen/CosyVoice. For budget -> Google free tier (1M chars/month). For offline -> Piper.

**Q: Do I need all these providers?**
A: No. Start with what you have. The selector pattern auto-routes to whatever's available. Missing a provider? The system falls through to the next one automatically.
