---
name: atlas-cloud
description: Govern Atlas Cloud media generation through the registered project tools. Use when Atlas Cloud is selected for Seedream image generation or Seedance video generation, including credential preflight, supported operation and model selection, project-scoped outputs, cost review, and artifact verification.
---

# Atlas Cloud Media Generation

Use the registered `atlascloud_image` and `atlascloud_video` tools. Do not call
the provider API directly or invent model identifiers that are absent from the
tool metadata.

## Workflow

1. Confirm that Atlas Cloud is the selected provider and that
   `ATLASCLOUD_API_KEY` is available without printing or logging it.
2. Read the selected tool's live input schema and `model_options`.
3. Choose the operation and provide a project-scoped `output_path`.
4. Review the tool's cost estimate before generation.
5. Execute through the project pipeline and preserve its checkpoints.
6. Inspect the returned artifact and metadata before reporting success.

## Image generation

- Use `atlascloud_image` for the supported Seedream model.
- Provide a prompt, one of the declared sizes, and an output format matching
  the output filename.
- Do not attach FLUX-, Wanx-, or other provider-specific guidance.
- Treat image editing, unsupported models, and seed control as unsupported
  unless the live tool schema changes.

## Video generation

- Use `atlascloud_video` for the declared Seedance operations.
- Select `text_to_video`, `image_to_video`, or `reference_to_video` before
  choosing inputs.
- Supply the required first-frame or reference inputs for conditioned
  operations.
- Use only the URL, Base64, or asset-reference forms accepted by the live
  schema; do not assume that a local image output path is uploadable.
- Also load `ai-video-gen` for general video-generation guidance.

## Guardrails

- Let the tools manage asynchronous submission, polling, downloads, and output
  validation.
- Surface validation, provider, timeout, and download failures instead of
  bypassing them.
- Use a fallback provider only through the normal selector and approval flow.
