# Video Production Buddy

Start by classifying the user's intent. This file is the router for Codex
agents; the deeper contracts live in `AGENT_GUIDE.md`, `PROJECT_CONTEXT.md`,
and `docs/ARCHITECTURE.md`.

## Route 1: Video Production User

Use this route when the user asks to make, edit, generate, render, analyze, or
publish video/media artifacts, including ads, trailers, explainers, clips,
screen demos, avatar videos, animations, reference-video requests, source-footage
edits, music, voiceover, subtitles, or final deliverables.

**First action:** read `AGENT_GUIDE.md`, then follow it exactly.

Production work must go through the pipeline system. Do not bypass pipeline
manifests, stage director skills, preflight, checkpoints, provider/runtime
governance, product-fidelity gates, or human approval rules.

## Route 2: Project Developer

Use this route when the user is working on this repository as code: bugs, tests,
refactors, audits, reviews, schemas, tools, tool registry or selectors,
pipeline manifests, skills, `.agents` components, docs, agent instruction
wrappers, CI, git operations, or any request that names files, functions,
commits, diffs, branches, or implementation details.

**First action:** read `PROJECT_CONTEXT.md` and `docs/ARCHITECTURE.md`, inspect
the relevant files, then work from the live repository state. For Codex
developer tasks, this Route 2 first action is intentional; use `AGENT_GUIDE.md`
as production contract context when the work touches the surfaces listed below.

Developer workflow:

- Check `git status --short` before editing and preserve unrelated dirty
  changes.
- Use `rg` and targeted file reads to understand the current implementation
  before changing it.
- Keep edits scoped to the requested surface and existing project patterns.
- Run focused tests, contract checks, or content checks that prove the touched
  behavior.
- For reviews, audits, and "check" requests, lead with findings. Implement fixes
  when the user asks for fixes or when the next action is clear from the
  conversation.
- For git operations, inspect status and relevant diffs, state the intended
  commit/push/rewrite scope, and keep unrelated dirty changes out of the
  operation. Destructive actions such as reset, amend, force-push, or history
  rewrite still need explicit user instruction.
- When editing agent instruction wrappers, inspect the sibling wrappers
  (`CLAUDE.md`, `CODEX.md`, `CURSOR.md`, `COPILOT.md`, `AGENTS.md`) and the
  platform-wrapper contract test before deciding the full update surface.
- Read `AGENT_GUIDE.md` as contract context, not as production-run instructions,
  when a development change affects production governance: pipeline manifests,
  director or meta skills, tool registry or selectors, tool contracts,
  checkpoints, canonical artifacts or schemas, GenUI interaction contracts,
  provider/runtime/preflight behavior, cost governance, knowledge alignment, or
  user-facing video-production instructions.
- Do not initialize `projects/`, record `user_request`, run provider preflight,
  call generation tools, or create media artifacts unless the user's request is
  actually production work.

## Ambiguous Requests

If the request could be either production or development, infer from concrete
signals:

- Mentions of repo files, tests, code, bugs, commits, schemas, or instructions
  mean Route 2.
- Requests for a video/media deliverable mean Route 1.
- Vague "make content" or "what can you do?" requests mean Route 1 onboarding in
  `AGENT_GUIDE.md`.

When ambiguity remains after checking local context, ask one concise clarifying
question before acting.
