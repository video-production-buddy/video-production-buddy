# Technical QC Context Review

## When to Use

Use this skill after `technical_qc` has inspected a rendered output and before
the compose-stage `final_review` is allowed to pass. The canonical scan finds
objective delivery failures and candidate signal anomalies. This skill teaches
the agent how to decide whether a candidate anomaly is a real defect, an
intentional editorial choice, or still uncertain.

This is a hybrid contract:

| Layer | Responsibility |
|-------|----------------|
| `technical_qc` | Repeatable FFmpeg/ffprobe measurement, parsing, and portable report output |
| This skill + the agent | Contextual interpretation against the approved plan and the rendered evidence |
| Capability extension | Audited, project-scoped supplemental diagnostics only when the registry has a real gap |

Hard-code measurement, not creative meaning. A detected interval is evidence,
not proof that the edit is wrong.

## Coverage Boundary

The canonical tool currently covers decode integrity, stream presence,
delivery-profile metadata, black/freeze/silence candidate intervals, integrated
loudness, and true peak. A clean report makes claims only about those checks.

It does not currently prove the absence of sub-threshold black flashes,
gradual-fade problems, audio/video synchronization errors, repeated scenes,
local loudness jumps, subtitle safe-area failures, generative visual defects,
or aesthetic pacing problems. Do not describe `technical_qc.status == "pass"`
as proof that the whole video is creatively or technically flawless. Route an
actually required uncovered check through the governed supplemental path in
Step 5. Keep that diagnostic project-only by default instead of expanding the
shared Python tool set.

## Required Inputs

- The saved `technical_qc` JSON report for the exact render under review
- The rendered video
- `scene_plan` when available
- `edit_decisions`, including cuts and transitions
- The approved audio/subtitle/delivery contract from the relevant proposal or brief
- `render_report` when reviewing a derivative or multi-output delivery

Do not reuse a review from another render or variant. Every output needs its own
scan and contextual disposition because crop, timing, audio, and transitions
can differ.

Save the report with `technical_qc`'s `report_path` option. The tool records
`input_sha256` for the scanned file; rerun it after replacing that file, and
rerun older reports that lack this fingerprint before submitting a new PASS.
Use project-relative paths (`renders/...`, `artifacts/...`), repository-relative
`projects/<project-id>/...` paths, or absolute paths inside the same project.
Checkpoint writes resolve these against the actual project, independent of cwd.

## Protocol

### 1. Keep deterministic failures deterministic

Treat these as tool or delivery failures, not taste calls:

- `ToolResult.success == false`
- `technical_qc.status == "fail"`
- missing or corrupt video streams
- a requested scan that did not complete
- explicit delivery-profile mismatches

Do not use visual judgment or a supplemental script to override these results.
Fix the source, configuration, or render and rerun the canonical scan.

Select `expected` values and threshold overrides from approved project facts.
Do not silently treat the defaults as platform requirements. For example, use
the approved loudness target and delivery profile when they exist. Record why
an override was chosen; never loosen a threshold merely to make a warning
disappear.

### 2. Build the editorial context map

Before interpreting warnings, map each reported time interval to the artifacts:

- `scene_plan.scenes[]`: scene purpose, motion intent, transition intent
- `edit_decisions.cuts[]`: cut boundaries, source, type, reason, and
  `transition_in` / `transition_out` / `transition_duration`
- `edit_decisions.transitions[]`: global transition windows
- `edit_decisions.audio`: expected narration, music, SFX, fades, and ducking
- proposal audio `pause_policy`: approved silence or breath room

Do not infer intent from the filename or from the detector label. If no artifact
supports the claimed intent, keep the finding `uncertain`.

### 3. Collect evidence at the reported interval

Representative opening/middle/ending frames are not enough for a timecoded
warning. For every black or freeze interval, use `visual_qa` to extract frames
immediately before it, near its start, at its midpoint, near its end, and
immediately after it. Clamp timestamps to the media duration and deduplicate
overlapping timestamps.

```python
visual_qa.execute({
    "operation": "review",
    "input_path": "<rendered-video>",
    "timestamps": [before_seconds, start_seconds, midpoint_seconds,
                   end_seconds, after_seconds],
    "output_dir": "projects/<project-name>/assets/qc_evidence/<variant>/<finding-id>",
})
```

Read every extracted frame. A successful extraction is not a completed review.
For silence, compare the interval with narration segments, music strategy,
fades, SFX, and the approved pause policy. Use an audio-level or waveform
diagnostic only when it answers a remaining question; amplitude alone does not
establish editorial intent.

Use these checks as guidance:

| Finding | Evidence that supports `intentional` | Evidence that supports `defect` |
|---------|---------------------------------------|---------------------------------|
| black | overlaps a declared fade/transition or approved black beat; adjacent frames show the planned transition | occurs inside an active scene, flashes between valid frames, or replaces expected content |
| freeze | overlaps an approved title/end-card hold or explicitly static beat | contradicts `motion_required`, interrupts expected motion, or appears inside a generated motion clip |
| silence | matches an approved pause, music break, or intentionally silent deliverable | overlaps expected narration/music/SFX or interrupts a spoken phrase |
| loudness/clipping | matches an explicit delivery/audio contract and has no unsafe peak | violates the approved loudness range, loses intelligibility, or carries clipping risk |

### 4. Assign a disposition

Every context-sensitive warning must receive exactly one disposition:

- `defect` — evidence contradicts the approved edit or delivery intent; revise
  and rerender.
- `intentional` — artifacts and inspected media both support the choice; record
  the reason and continue.
- `uncertain` — context or evidence is insufficient; request human review or
  gather more evidence. Never silently convert this to `intentional`.

Each disposition must include a concrete reason, at least one evidence
reference, and at least one artifact context reference. A statement such as
"reviewed and acceptable" without those references is not evidence.

### 5. Use Agent-authored diagnostics only as a governed supplement

The canonical tool is the baseline. If it cannot answer a project-specific
question, first confirm through registry/preflight that no existing tool covers
the gap. Then read and follow `skills/meta/capability-extension.md`.

Any Agent-authored diagnostic must:

1. Be project-scoped, idempotent, and saved under
   `projects/<project-name>/scripts/` or as a project tool.
2. Produce a project-scoped evidence artifact.
3. Be logged in `decision_log` with `category: "capability_extension"`.
4. Be disclosed to the user as a supplemental check.
5. Record its purpose, method, result, evidence, and limitations in
   the matching output entry under
   `final_review.checks.technical_qc_review.outputs[].supplemental_checks`.
6. Declare `lifecycle: "project_only"`; it creates no compatibility or
   maintenance promise outside the current project.
7. Never call an external API without approval.
8. Never override a canonical decode/profile failure or serve as the sole basis
   for a passing final review.

Do not promote supplemental diagnostics automatically, even if a similar need
appears again. Prefer adapting the Skill's reasoning recipe and composing the
existing stable tools. A shared tool is a separate maintainer-owned product
decision, outside this production workflow, and requires an explicit maintenance
owner and compatibility budget.

### 6. Record the review

Write the contextual result to
`final_review.checks.technical_qc_review`. Include exactly one `outputs[]`
entry for every render covered by `final_review`; its `output_path` and optional
`variant` must match `render_report.outputs[]`. Copy `status` and
`summary.warning_count` from the canonical report into `scan_status` and
`warning_count`; include exactly one `source: "technical_qc"` finding for each
reported warning. Example:

```json
{
  "outputs": [
    {
      "output_path": "renders/output_16x9.mp4",
      "variant": "16:9",
      "report_path": "artifacts/technical_qc_primary.json",
      "scan_status": "pass_with_warnings",
      "warning_count": 1,
      "findings": [
        {
          "code": "freeze_segment",
          "source": "technical_qc",
          "start_seconds": 28.0,
          "end_seconds": 31.0,
          "disposition": "intentional",
          "reason": "The interval is the approved static brand end-card hold.",
          "evidence_refs": [
            "assets/qc_evidence/primary/freeze-28/frame_29_5s.jpg"
          ],
          "context_refs": [
            "edit_decisions.cuts[end-card]"
          ],
          "recommended_action": "none"
        }
      ],
      "supplemental_checks": [],
      "unresolved_count": 0
    }
  ],
  "unresolved_count": 0
}
```

For a clean scan, keep that output entry's `findings` and
`supplemental_checks` empty, use `scan_status: "pass"` and `warning_count: 0`,
and set both the per-output and aggregate `unresolved_count` to `0`. The
aggregate count is the sum of the per-output counts. Do not invent findings
merely to populate the block.

### 7. Gate the final review

- Any deterministic failure: `final_review.status = "fail"` or `"revise"`.
- Any `defect`: revise/rerender, rerun `technical_qc`, and review the new report.
- Any `uncertain`: keep the review non-passing until more evidence or explicit
  human review resolves it.
- Only deterministic PASS plus zero unresolved findings may reach
  `final_review.status = "pass"`.

An intentional warning remains visible in the audit trail; it is not deleted
from the canonical report.

Before persisting a passing review, `write_checkpoint` loads each saved report
and verifies the render fingerprint, canonical status, completed requested
checks, and one-to-one warning coverage by code and exact interval. Copy the
reported timestamps without rounding. Audio checks skipped for a missing stream
are acceptable only when the scan explicitly requested `expected.has_audio=false`;
that expectation must come from the approved delivery contract.

For ad-video, `visual_spotcheck.black_frames_detected` remains a factual
observation about the primary output. Keep it true when black frames were seen;
PASS then requires matching `black_segment` findings with inspected evidence,
approved context, and `intentional` dispositions. Unreviewed or unresolved black
frames remain blocking, as do broken overlays, missing assets, and unreadable text.
