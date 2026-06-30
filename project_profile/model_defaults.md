# Model Defaults

These are dated observations about configured model defaults in this checkout.
They are not permanent claims about provider state. Re-check provider docs,
account access, and tool defaults before saying a model is current, latest, or
strongest.

## Last Verified

- Date: 2026-06-30
- Scope: public provider docs plus local registry defaults in this repo state.

## Observed Defaults

- `wan_video_api` -> operation defaults:
  - `text_to_video`: `happyhorse-1.1-t2v`
  - `image_to_video`: `happyhorse-1.1-i2v`
  - `reference_to_video`: `happyhorse-1.1-r2v`
  - `video_editing`: `happyhorse-1.0-video-edit`
  - Notes: HappyHorse/Wan native audio may need muting under this project's
    final mix when appropriate.
- `wanx_image` -> dynamic default:
  - `qwen-image-2.0-pro` when Qwen workspace endpoint settings are configured.
  - `wan2.7-image-pro` for key-only DashScope setups.
  - Notes: Qwen Image 2.0 uses workspace-scoped Model Studio endpoints; set
    `DASHSCOPE_WORKSPACE_ID` and `DASHSCOPE_REGION` with the API key to make it
    the default.
- `minimax_video` -> `MiniMax-Hailuo-2.3`
  - Notes: good fit for human/performance scenes; supports `[command]` camera
    syntax.
- `minimax_tts` -> `speech-2.8-hd`
- `minimax_music` -> `music-2.6`
- `cosyvoice_tts` -> `qwen3-tts-flash`
  - Stronger delivery-control path: `qwen3-tts-instruct-flash`.
- `openai_image` -> `gpt-image-2`
- `google_imagen` -> `gemini-3-pro-image`
- `flux_image` -> `flux-2-pro`
- `recraft_image` -> `v4.1`
- `grok_image` -> `grok-imagine-image-quality`
- `grok_video` -> operation defaults:
  - `text_to_video`: `grok-imagine-video`
  - `image_to_video`: `grok-imagine-video-1.5`
  - `reference_to_video`: `grok-imagine-video`
- `runway_video` -> `seedance2`
- `elevenlabs_tts` -> `eleven_v3`

The June 28 audit found several stale defaults and changed project code. Treat
`release_stage`, `deprecated`, `last_verified`, and `source_url` in
`model_options` as the first local freshness signal, then re-check provider docs
before saying a model is current, latest, or strongest.

## Verification Commands

Use live code inspection plus registry preflight before relying on this list:

```bash
rg -n "model|default|happyhorse|Hailuo|speech-2.8|music-2.6|qwen-image|gpt-image|flux-2|recraft|grok-imagine|eleven_v3" tools schemas skills project_profile
```

```bash
python -c "from tools.tool_registry import registry; import json; registry.discover(); print(json.dumps(registry.provider_menu_summary(), indent=2, ensure_ascii=False))"
```

When a tool exposes `get_info()` or a dry-run/sample mode, prefer that over
static text inspection for current account/runtime availability.
