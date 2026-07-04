# DashScope

Use this skill when Video Production Buddy routes work to Alibaba Cloud
DashScope tools:

- `dashscope_image` for Qwen Image generation.
- `dashscope_tts` for Qwen TTS narration.
- `dashscope_asr` for DashScope ASR with word-level timestamps.

## Setup

Set `DASHSCOPE_API_KEY` before using these API-backed tools.

## Operating Notes

- Treat outputs as paid provider calls; estimate and disclose cost before use.
- Save generated media and transcripts under the project workspace paths
  required by the tool schema.
- For ASR, provide a public HTTPS audio URL because DashScope servers must be
  able to fetch the input.
