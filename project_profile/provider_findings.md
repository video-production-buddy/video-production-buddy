# Provider Findings

Provider/account status can drift. Treat this file as dated evidence, not a
replacement for live preflight.

## Last Verified

- Date: 2026-06-18 / 2026-06-28
- Scope: local repo defaults and observed account/tool behavior for this
  checkout.

## Current Findings

- Public provider-doc audit on 2026-06-28 updated local model defaults for
  OpenAI image, Google image, FLUX, Recraft, xAI media, Bailian video/image,
  Runway video, and ElevenLabs TTS. See `model_defaults.md`.
- OpenAI TTS is not configured in this environment.
- Bailian/CosyVoice system male voices such as `longxiaocheng` and
  `longanyang` returned HTTP 400 / parse errors during prior checks because the
  relevant CosyVoice models were not enabled in the Bailian console.
- `cosyvoice-v3.5-plus` has no system voices in this setup; it requires a
  cloned or designed `voice_id`, and the current `cosyvoice_tts` path does not
  expose clone/design.
- MiniMax is the reliable configured path for Mandarin male narration in this
  project profile. See `voice_and_subtitles.md` for exact voice IDs and routing.

## Verification Commands

Use these before making current claims about provider availability:

```bash
python -c "from tools.tool_registry import registry; import json; registry.discover(); print(json.dumps(registry.provider_menu_summary(), indent=2, ensure_ascii=False))"
```

```bash
python - <<'PY'
from tools.tool_registry import registry
registry.discover()
for name in ("openai_tts", "cosyvoice_tts", "minimax_tts", "wan_video_api", "wanx_image", "minimax_video", "minimax_music"):
    tool = registry.get(name)
    print(name, tool.get_status().value if tool else "missing")
PY
```

For account-specific API behavior, run the relevant tool in a small sample mode
and record the exact date, input, provider/model, and error or success result in
this profile if it affects future routing.
