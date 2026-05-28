# Publish Director — Ad Video Pipeline

## When to Use

You receive `render_report`, `final_review`, `production_proposal`, `script`, `production_bible`, `scene_plan`, `asset_manifest`, `decision_log`, and `EP_STATE` and produce the final `publish_log`: output file matrix, platform metadata, and thumbnail concept.

Before writing `publish_log`, run `hallucination_contract_check` with `production_bible`, `scene_plan`, `asset_manifest`, and `decision_log`. A FAIL blocks publish. A WARN can proceed only if the warning is surfaced in the final publish review notes.

Also verify `final_review.status == "pass"` before writing `publish_log`. If
the compose self-review is missing, `revise`, or `fail`, return to compose; do
not publish a render that has not passed actual-output inspection.

When writing the completed publish checkpoint, include `render_report`,
`final_review`, `production_proposal`, and `production_bible` alongside
`publish_log`. The checkpoint validator uses `render_report.outputs` to prove
that `publish_log.output_file_matrix` and any `entries[].export_path` refer
only to files that were actually rendered, and uses the proposal/bible context
to prove the primary output and opted-in derivatives were rendered.

## Output File Matrix

For every file in `render_report.outputs`, assign platform targets and usage notes:

| File | Variant | Primary Platform Targets | Typical Use |
|------|---------|--------------------------|------------|
| `output_16x9.mp4` | 16:9 | YouTube, LinkedIn, TV | Hero placement |
| `output_9x16.mp4` | 9:16 | TikTok, Instagram Stories, YouTube Shorts | Vertical social |
| `output_1x1.mp4` | 1:1 | Instagram Feed, Twitter/X, LinkedIn feed | Square social |
| `output_15s.mp4` | 15s | Pre-roll, bumper | Short-form |
| `output_15s_9x16.mp4` | 15s 9:16 | TikTok, IG Stories short | Short vertical |
| `output_15s_1x1.mp4` | 15s 1:1 | Short square | Short square |

Include only files that were actually rendered (check `render_report.outputs`).

## Metadata

For each output file:

```json
{
  "file": "renders/output_16x9.mp4",
  "title": "{proposal.selected_concept.name}",
  "description": "{script.sections[hook].narration} ... {cta}",
  "tags": ["{brand_name}", "{product}", "{platform}", "ad", "commercial"],
  "cta_url": "{script.cta}",
  "brand_name": "{script.brand_name}",
  "target_platforms": ["youtube", "linkedin"],
  "duration_seconds": "{from render_report}",
  "variant": "16:9"
}
```

## Thumbnail Concept

Provide a written thumbnail concept for each output file's primary platform use:

Format:
```
Thumbnail concept for {variant}:
- Frame: {describe the ideal freeze-frame or custom thumbnail moment}
- Text overlay: {headline text if any, ≤5 words}
- Brand element: {how brand name/logo appears}
- Emotional tone: {what expression/action is shown}
```

Example:
```
Thumbnail concept for 16:9:
- Frame: Product hero shot from reveal scene, 70% into the video
- Text overlay: "4 HRS BACK EVERY WEEK"
- Brand element: Flowcut logo lower-right, 20% opacity overlay
- Emotional tone: Clean, confident, aspirational
```

## Publish Log Format

```json
{
  "version": "1.0",
  "pipeline": "ad-video",
  "brand_name": "Flowcut",
  "entries": [
    {
      "platform": "local-export",
      "status": "exported",
      "export_path": "renders/output_16x9.mp4",
      "timestamp": "2026-04-27T12:00:00Z",
      "metadata_used": {
        "title": "The Problem You Didn't Know You Had — Flowcut",
        "description": "Every morning, you're wasting 45 minutes. Start free at flowcut.io",
        "hashtags": ["Flowcut", "productivity", "workflow", "ad"]
      }
    }
  ],
  "output_file_matrix": [
    {
      "file": "renders/output_16x9.mp4",
      "variant": "16:9",
      "duration_seconds": 59.8,
      "target_platforms": ["youtube", "linkedin", "tv"],
      "metadata": {
        "title": "The Problem You Didn't Know You Had — Flowcut",
        "description": "Every morning, you're wasting 45 minutes. Start free at flowcut.io",
        "tags": ["Flowcut", "productivity", "workflow", "ad"],
        "cta_url": "https://flowcut.io"
      },
      "thumbnail_concept": "Product hero from reveal scene, '4 HRS BACK/WEEK' overlay"
    }
  ],
  "total_files_rendered": 2,
  "budget_summary": {
    "approved_usd": 2.50,
    "spent_usd": 2.18,
    "remaining_usd": 0.32
  }
}
```

## Validation Before Submitting

- [ ] `output_file_matrix` is non-empty
- [ ] `final_review.status == "pass"`
- [ ] Every file in `render_report.outputs` has an entry in the matrix
- [ ] Completed publish checkpoint includes `render_report`, `final_review`, `production_proposal`, and `production_bible`
- [ ] `hallucination_contract_check` returned PASS or WARN; FAIL blocks publishing
- [ ] No blocker `hallucination_review` FLAG or unapproved waiver remains in `asset_manifest`
- [ ] All metadata fields populated (title, description, tags, cta_url, brand_name)
- [ ] Thumbnail concept written for each entry
- [ ] Budget summary accurate (matches EP_STATE)
