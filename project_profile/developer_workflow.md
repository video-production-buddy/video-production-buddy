# Developer Workflow

These are project-side working rules for agents changing, auditing, testing, or
publishing this repository as code.

## Start From Live State

- Check `git status --short` before editing.
- Preserve unrelated dirty changes.
- Read `PROJECT_CONTEXT.md` and `docs/ARCHITECTURE.md` for developer tasks.
- Read `AGENT_GUIDE.md` as production contract context when a change touches
  production governance, stage skills, manifests, tools, schemas, checkpoints,
  GenUI, provider/runtime behavior, cost governance, or user-facing production
  instructions.

## Agent Autonomy and Tool Use

- Agents may use available subagents, superpowers or skills, MCPs, plugins,
  commands, and internet research when they materially improve planning,
  implementation, review, or verification.
- Treat those capabilities as tools, not ceremony. Use the smallest useful
  surface for the task and state material external-source or tool assumptions
  when relevant.
- Keep tests focused on touched behavior. Do not add repo-tracked throwaway,
  duplicate, or broad temporary tests; add or update durable tests only when
  they protect real behavior or prevent a likely regression.
- Discuss with human, ask human questions if you are not very confident about
  the plans.
- Based on the principle of concise, correct, friendly, short & clear & clean.
- Do not automatically commit and push. Human should manually check before commit and push.

## Audits

- Do not stop at file-local review. Follow adjacent contract consumers:
  manifests, schemas, registries, loaders, runtime callers, tests, and docs.
- Derive inventories from live sources such as manifests, registries, loaders,
  AST scans, and current test layout rather than fixed lists copied from memory.
- Use `provider_menu_summary()` as the compact truth source for current
  runtime/provider availability; use deeper registry inspection only for
  debugging specific tool contracts.
- Knowledge-card edits are contract edits, not prose-only edits. Preserve
  retrieval fields such as `principles`, `avoid_when`, `failure_patterns`, and
  `execution_techniques`; update hashes when the knowledge-card contract
  requires it.

## Fixes and Reviews

- When the user says `Fix.`, `Please fix.`, or asks to address review findings,
  implement the fix rather than only discussing it.
- Prefer the durable fix loop: add or run a focused regression, patch the real
  manifest/schema/tool/doc surface, rerun focused verification, then widen only
  as risk requires.
- Run `git diff --check` on the touched scope before closeout or commit.
- Report tests that were not run, especially when broad suites are skipped due
  to dirty worktree scope or time.

## Documentation Localization

- Treat `README.md` and `README_zh-CN.md` as a synchronized public-facing pair.
  Whenever updating English README content, update the Chinese README in the
  same change unless the user explicitly scopes the task otherwise.
- The Chinese README should use the project name `织影` while preserving the
  setup commands, paths, links, citation, acknowledgements, and verification
  guidance from the English README.

## Git Operations

- For commit/push requests, inspect branch, remote, status, and relevant diffs
  first. State the exact commit scope before committing.
- Keep unrelated dirty files out of staged snapshots unless the user explicitly
  asks for a whole-tree commit.
- Do not reset, amend, force-push, or rewrite history without explicit user
  instruction.
- For tree-preserving history rewrites, create a backup ref first, prove
  tree equality between the old and new tips, run focused verification, then
  use `--force-with-lease` rather than raw force push.

## Generated Artifacts and Root Hygiene

- Generated media and run artifacts belong under project output paths, not as
  root tracked files.
- When the user asks whether an artifact will not reappear, answer with current
  generator evidence and add or run a guard when practical.
- To stop tracking generated directories while preserving local files, use
  `git rm --cached -r <path>` plus `.gitignore` and verify with
  `git check-ignore -v <file>`.

## Identity Boundary

- For product identity-only cleanup, prefer a clean boundary with no legacy
  aliases unless the user explicitly asks for compatibility.
- After identity cleanup, scan config aliases, environment fallbacks, cache
  names, component markers, docs, and user-facing strings for stale product
  names.
