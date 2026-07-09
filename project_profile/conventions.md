# Project Conventions

This file is the profile index and general convention layer. Read
`README.md` first for authority rules, then read the focused files relevant to
the current task.

## Memory Mechanism

- Do not generate or write agent-side private memory for durable project
  behavior.
- Cross-session and cross-agent consistency information lives in repo files:
  - Global conventions and technical findings: `project_profile/`.
  - Per-video-project artifacts and decisions:
    `projects/<project-id>/artifacts/` and `decision_log`.
- Different agents reading the same in-repo files should reach the same
  production decisions.
- If project profile files conflict with agent-side private memory, the project
  profile wins.

## Profile Map

- `agent_behavior.md` - explanation style, terminal-only verification, local UI
  behavior, and closeout expectations.
- `developer_workflow.md` - code audits, fixes, tests, git operations,
  generated-artifact hygiene, and identity cleanup.
- `brand.md` - active product identity, tagline, visual identity, and forbidden
  brand/IP usage.
- `provider_findings.md` - dated provider/account availability findings and
  verification commands.
- `voice_and_subtitles.md` - Mandarin male voice routing, MiniMax TTS, and CJK
  subtitle font requirements.
- `model_defaults.md` - dated model/default observations plus re-check
  commands.
- `hyperframes.md` - HyperFrames CJK font packaging and video-heavy render
  findings.
- `update_checklist.md` - checklist for deciding what belongs in this profile
  and how to update it safely.
- `migration_audit.md` - what was migrated from agent-side memory and what was
  intentionally left out.

## Changelog

- 2026-06-17: Created the no-agent-memory and in-repo profile mechanism;
  recorded TTS male-voice findings; extended `audio_contract` and
  asset-director routing to support MiniMax; audited generation-model defaults.
- 2026-06-18: Fixed Chinese subtitle rendering by installing/using Noto Sans SC;
  recorded the CJK subtitle requirement for future agents.
- 2026-06-18: Renamed active product identity from 灵境 AI to 织影
  (English: Video Production Buddy), tagline 一言成片，万象成章.
- 2026-06-18: Migrated Codex-side reusable project behavior into repo-side
  profile files and split the profile into focused documents.
- 2026-06-18: Migrated HyperFrames CJK font packaging and video-heavy render
  findings from Claude Code session state into repo-side profile and tool
  behavior.
- 2026-06-23: Added the bilingual README maintenance rule: keep `README.md` and
  `README_zh-CN.md` synchronized, and use `织影` as the Chinese project name.
