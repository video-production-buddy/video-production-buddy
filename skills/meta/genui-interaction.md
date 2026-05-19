# GenUI Interaction Protocol

## When to Use

Use GenUI when a human gate contains many options, defaults, recommendations, or
approval details that would be tedious to review in a CLI message. Typical
cases: ad-video creative requirements, proposal lock points, product identity
reference choices, runtime selection, derivative variants, subtitle/dubbing
choices, budget approval, and voice/style sample approval.

Skip GenUI for one-question clarifications, source inspection, or short yes/no
approval gates where the CLI is clearer.

## Contract

GenUI is an interaction layer, not an orchestrator.

The agent still owns:
- pipeline selection and stage order,
- reading the pipeline manifest and stage director skill,
- preflight and provider/runtime decisions,
- self-review,
- canonical artifact writes,
- checkpoints and decision logs.

The form server writes only `ui_response`. It must not write canonical artifacts
such as `enriched_brief`, `production_proposal`, `decision_log`, or checkpoints.
The agent validates and summarizes `ui_response` before updating those files.

## Workflow

1. Generate a project-specific `ui_form_config` with defaults, recommended
   values, choices, help text, and bindings to the intended artifact fields.
2. Call `genui_form` in `serve` mode when a local browser is available.
3. If `genui_form` is unavailable or the user cannot open a browser, use the
   CLI fallback from the stage director skill.
4. After submission, read `projects/<project>/artifacts/ui/<config_id>/response.json`.
5. Validate it as `ui_response`.
6. Summarize the user's selected values and any revisions.
7. Only then write canonical artifacts, decision logs, and checkpoints.

## User-Facing Pattern

Keep the terminal message short:

```
I generated a visual form for Gate G-0.
Open: http://127.0.0.1:<port>/
Submit it when ready; I will validate the response before updating artifacts.
```

For CLI fallback, present the same fields in a compact numbered worksheet and
record that the form path was unavailable.
