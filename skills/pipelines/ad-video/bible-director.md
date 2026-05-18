# Bible Director — Ad Video Pipeline

## When to Use

You are the **Bible Director**. You receive `intake_brief` + `intelligence_brief` and
synthesize them into a `production_bible` — the machine-readable contract governing all
downstream stages. You conduct two-step user review (Round 2a: narrative, Round 2b:
execution) before the pipeline advances.

## Prerequisites

| Layer | Resource | Purpose |
|-------|----------|---------|
| Schema | `schemas/artifacts/production_bible.schema.json` | Output validation |
| Input | `intake_brief` | Brand and platform baseline |
| Input | `enriched_brief` | User-approved creative hypothesis (G-0 artifact) |
| Input | `intelligence_brief` | Research validation: dimension_verdicts + psychographics |

## Arc Type Beat Ratios

```
// ── Configuration Note ──────────────────────────────────────────────────
// Beat ratio tables are inline in v1 (single pipeline consumer).
// When a second pipeline adopts the bible pattern, extract to
// config/arc_beat_ratios.yaml. Do not build abstraction for a single consumer.
// ────────────────────────────────────────────────────────────────────────

Arc type beat ratios (normalized to 1.0 — multiply by duration_target_seconds):

problem-solution:    hook=0.13, problem=0.25, solution_intro=0.17, proof=0.25, resolution=0.12, cta=0.08
desire-fulfillment:  hook=0.08, desire_paint=0.25, gap=0.17, fulfillment=0.30, brand=0.12, cta=0.08
contrast:            hook=0.12, before=0.22, contrast_moment=0.08, after=0.28, evidence=0.22, cta=0.08
journey:             hook=0.10, challenge=0.20, struggle=0.20, turning_point=0.15, triumph=0.25, cta=0.10
social-proof:        hook=0.10, social_scene=0.25, testimonial=0.30, product_reveal=0.20, brand=0.08, cta=0.07
demo-reveal:         hook=0.13, setup=0.17, demo=0.37, payoff=0.20, cta=0.13

Intensity curves (values distributed across beats in sequence order):
escalating:  0.3 → 0.5 → 0.7 → 0.9 → 0.7 → 0.5
wave:        0.5 → 0.8 → 0.4 → 0.9 → 0.6 → 0.5
punchy:      0.8 → 0.6 → 0.8 → 0.7 → 0.5 → 0.8
slow-burn:   0.2 → 0.4 → 0.6 → 0.8 → 0.9 → 0.7
```

## Synthesis Steps (internal — no user interaction until Step 7)

### Step 0 — Provenance audit (mandatory before Step 1)

The override rule below trusts `confidence == "research-grounded"` to gate
when intelligence overrides the user's brief. That tier is self-graded by
the agent that produced `intelligence_brief`. Before applying any override,
run the provenance auditor — it demotes claims marked research-grounded
that lack citable evidence (no URL, no named publication / report /
campaign in `rationale` or `challenge_evidence`):

```python
from lib.provenance_audit import audit_intelligence_provenance

flags = audit_intelligence_provenance(intelligence_brief)
for flag in flags:
    # In-place demotion: research-grounded → pattern-inferred.
    # The override rule below treats the result the same as if the
    # intelligence-director had emitted pattern-inferred originally.
    # Dispatch on `path_type` (stable enum), not on parsing `path` strings.
    if flag["path_type"] == "recommendation":
        key = flag["key"]
        intelligence_brief["recommendations"][key]["confidence"] = "pattern-inferred"
    elif flag["path_type"] == "dimension_verdict":
        idx = flag["index"]
        intelligence_brief["dimension_verdicts"][idx]["confidence"] = "pattern-inferred"
    # path is preserved on the flag for the audit trail (do not parse it).
```

Record the demotions in `production_bible.intelligence.provenance_demotions`
(a free-form array of the flag entries) so the audit trail is preserved.
Do not silently demote — surface the count to the user at Step 7a as part
of the FLAGGED section if any demotions occurred.

### Step 0b — Aggregate hit-ad narrative classification (Project B)

When intelligence-director ran `video_analyzer` on hit ads with public URLs,
each ad's `classification` block carries a rule-based narrative-pattern
classification (arc_type + hook_mechanic) derived from the actual video,
not from article inference. Aggregate these across ads — sample size +
agreement on the modal arc_type drives the confidence tier:

```python
from lib.hit_ad_classification import aggregate_classifications

aggregate = aggregate_classifications(intelligence_brief.get("hit_ads_analyzed", []))
# aggregate is None when no ad carries a classification block.
# Otherwise: {arc_type, arc_type_agreement, hook_mechanic,
#             hook_mechanic_agreement, sample_size, confidence, dissent}
if aggregate is not None:
    production_bible["intelligence"]["classification_aggregate"] = aggregate
```

**Override semantics — recorded, NOT auto-applied.** The aggregate is one
signal among many and the user's brand context is real signal that aggregate-
of-other-ads can't see. Do NOT silently overwrite `narrative.arc_type` or
`narrative.hook_mechanic` based on the aggregate. Step 7a presents it to
the user, and the user accepts or rejects per the existing CHALLENGED/FLAGGED
rules.

### Step 1 — Assemble identity

**Start from `enriched_brief`** as the baseline, not from scratch.

- `product_brief.product_name`, `product_brief.tagline`, `product_brief.target_demographic`,
  `narration_notes.voice_description` → use directly from enriched_brief
- `key_message` → use `enriched_brief.product_brief.product_description` as seed;
  refine with `intelligence_brief.audience_psychographics.core_pain_point` if SUPPORTED
- `cta` → check `intake_brief.cta`; if null, flag as "pending — must be collected at Round 2b"
- `brand_name` → from `enriched_brief.product_brief.product_name`; flag for confirmation at Round 2b if not stated by user

**Override rule:** only replace an enriched_brief field when
`intelligence_brief.dimension_verdicts` contains an entry for that dimension with
`verdict == "CONTRADICTED"` AND `confidence == "research-grounded"`. All other
dimensions carry forward from enriched_brief unchanged. The Step 0 provenance
audit ensures `research-grounded` actually means cited; uncited claims have
already been demoted to `pattern-inferred` and will not trigger an override.
When the challenged dimension has `status == "DELEGATED"` in
`enriched_brief.hypothesis_flags`, present it to the user as "Current recommended brief"
instead of "Your brief"; delegated choices are the director's recommendation, not a user
preference being contradicted.

### Step 2 — Design emotional beat sequence

**Start from `enriched_brief.narrative_arc`** as the hypothesis arc.

1. Check `intelligence_brief.dimension_verdicts` for `dimension == "arc_type"`:
   - SUPPORTED or INSUFFICIENT-DATA → use enriched_brief narrative_arc beats as-is;
     map to the matching arc type beat ratios for internal timing validation
   - CONTRADICTED + research-grounded → flag for Round 2a challenge; prepare both the
     enriched_brief arc AND the research-recommended arc for user choice at Step 7a
2. If arc_type is accepted (no challenge or user confirms at 7a):
   - Use enriched_brief beat timestamps; validate they sum to duration_target_seconds
   - Populate `script_constraint` and `visual_constraint` per beat from arc semantics
3. Set `tension_peak_at_seconds` = cumulative time at the highest-intensity beat
4. Populate `pacing_model` from `intelligence_brief.recommendations.pacing_model.value`
   unless that dimension is CONTRADICTED with research-grounded evidence against it
5. Derive `narrative.intensity_curve` from the finalized `emotional_beat_sequence`
   using `lib.intensity_curve.derive_intensity_curve(emotional_beat_sequence)`. This
   emits `[{t_seconds, value}, ...]` — one sample per beat boundary plus a closing
   sample at total duration. Path B downstream consumers (edit-director duck schedule,
   audio_mixer volume envelope, asset-director music-gen prompt) read this field; do
   not hand-author it. If the helper raises, the beat sequence is malformed — fix it
   before continuing.

### Step 3 — Build visual contract

- `visual_motifs`: from `hit_ads_analyzed`. `mandatory=true` only for motifs in ≥3 ads
  AND not in `rejected_approaches`
- `editing_rhythm`: map from `recommendations.editing_rhythm_by_beat`; carry
  `confidence` tier. Reconciliation rules (closes the parallel-signals gap
  between intensity and editing_rhythm).

  **Pre-step — measured-pacing aggregate.** If hit_ads_analyzed contains
  ads with `pacing_measured` (intelligence-director invoked video_analyzer),
  aggregate them first. The aggregate's `cuts_density` and confidence tier
  override the deterministic intensity-based fallback for **every beat where
  intelligence has no real per-beat signal** — measured ad-category pacing
  is honestly stronger than the curve-derived default.

  ```python
  from lib.hit_ad_pacing import aggregate_pacing_from_hit_ads

  measured_aggregate = aggregate_pacing_from_hit_ads(
      intelligence_brief.get("hit_ads_analyzed", [])
  )
  # measured_aggregate is None when no ad had pacing_measured;
  # otherwise: {avg_cuts_per_minute, avg_shot_duration_seconds,
  #             sample_size, confidence, cuts_density}
  ```

  Per beat:
  ```python
  from lib.intensity_curve import (
      check_editing_rhythm_consistency,
      derive_editing_rhythm_from_intensity,
  )

  intel = intelligence_brief["recommendations"].get("editing_rhythm_by_beat", {}).get(beat_id)
  if not intel or intel["confidence"] == "default-heuristic":
      if measured_aggregate is not None:
          # Measured ad-category pacing trumps the deterministic intensity
          # fallback. Carry the aggregate's confidence (research-grounded
          # when sample_size >= 2, else pattern-inferred).
          rhythm = {
              "cuts_density": measured_aggregate["cuts_density"],
              "avg_shot_duration_seconds": measured_aggregate["avg_shot_duration_seconds"],
              "transition_style": "hard_cut",  # default; refine per beat if needed
              "confidence": measured_aggregate["confidence"],
          }
      else:
          # No measured signal anywhere — derive from intensity per beat.
          rhythm = derive_editing_rhythm_from_intensity(beat["intensity"])
          rhythm["confidence"] = "default-heuristic"
  else:
      # Use intelligence's value, but flag sharp divergence from intensity.
      rhythm = dict(intel["value"])
      rhythm["confidence"] = intel["confidence"]
      warnings = check_editing_rhythm_consistency(beat["intensity"], rhythm)
      # Both axes (cuts_density and avg_shot_duration_seconds) can fire on the
      # same beat — record every entry, not just the first. Defensive
      # setdefault ensures the intelligence block exists; Step 0 may not have
      # initialized it if no provenance demotions occurred.
      if warnings:
          intelligence_block = production_bible.setdefault("intelligence", {})
          rhythm_warnings = intelligence_block.setdefault("rhythm_warnings", [])
          for warning in warnings:
              rhythm_warnings.append({
                  "beat_id": beat["beat_id"],
                  "warning": warning,
                  "rhythm": rhythm,
              })
  ```

  When `rhythm_warnings` is non-empty after Step 3, surface every entry to
  the user at Round 2a as part of the FLAGGED section (one line per beat
  per warning). A flagged beat with `confidence == "pattern-inferred"` still
  triggers `failure_action == "revise"` at edit-director's compliance gate
  — the Round 2a surface gives the user the chance to override before
  hitting that gate downstream.

  Backfill rule: bibles where every beat's editing_rhythm came from
  derive-from-intensity should set `editing_rhythm[].confidence = "default-heuristic"`
  uniformly so the failure_action policy picks `flag` (not `revise`).
- `key_visual_moments`: one mandatory moment per beat with a concrete visual requirement.
  **MANDATORY new field per KVM:** `required_motion_primitives: string[]` — list one or more
  motion primitives the scene must implement (e.g. `["counter_roll", "thumb_silhouette_swipe", "freeze_pulse"]`
  for KVM-1). Each entry must be a key in
  `remotion-composer/scene_type_registry.json#motion_primitives_index`. scene-director
  uses these to pick a component that supports them; the fidelity gate
  (`tools/validation/scene_fidelity_check.py`) rejects any scene whose chosen
  component lacks a required primitive.
- `style_mode` + `render_runtime`: from `intake_brief.style_mode_candidate` (confirmed at proposal)
- `atmosphere` (consumed by every dynamic scene component):
  - `default_layers`: array of style layer configs applied to all scenes by default
    (typical: `[{type:"grain",intensity:0.05}, {type:"vignette",strength:0.28}]`)
  - `per_beat_overrides`: map of beat_id → array of additional/replacement layers
    (e.g. `{B1: [{type:"ambient_glow", color:"#FF3B30", pulse:true}], B5: [{type:"light_rays", ...}]}`)
  - Layer types and full prop schemas: see
    `remotion-composer/scene_type_registry.json#style_layers`
    — `grain`, `vignette`, `ambient_glow`, `particle_field`, `light_rays`.

### Step 4 — Build audio contract

- `voice_character.tone`: from identity.tone + emotional_profile
- `music_direction.arc`: derived from intensity curve
- `music_direction.tempo` + `genre_direction`: from platform_trends + pacing_model.
  Filter and dedupe trends before consuming so stale or duplicate signals
  don't drive the choice:

```python
from datetime import date
from lib.trend_recency import dedupe_trends, filter_stale_trends

today = date.today()
fresh_trends = dedupe_trends(
    filter_stale_trends(intelligence_brief["platform_trends"], now=today)
)
# Use fresh_trends (not the raw intelligence_brief["platform_trends"]) when
# deriving music_direction.tempo / genre_direction. Trends without
# observed_at are treated as current; evergreen trends bypass decay.
```

### Step 5 — Build deliverables

Primary aspect ratio from platform:
- tiktok / instagram → `"9:16"`
- youtube / linkedin / tv / generic → `"16:9"`

Set `deliverables.primary`. Leave `deliverables.derivatives = []` — proposal fills this.

### Step 6 — Build brand constraints

- `brand_name_in_final_frame`: always `true`
- `mandatory_elements`, `prohibited_elements`, `tone_guardrails`: from intake_brief

### Step 7 — Generate compliance manifest

Evaluation method assignment:
```
check_type == "timing"     → evaluation_method = "structural"
check_type == "presence"   → evaluation_method = "structural"
check_type == "structural" → evaluation_method = "structural"
check_type == "content"    → evaluation_method = "semantic"
```

failure_action rule:
```
source_confidence == "default-heuristic"                          → failure_action = "flag"
source_confidence IN [research-grounded, pattern-inferred]        → failure_action = "revise"
```

For editing_rhythm checkpoints:
```
failure_action = rhythm.confidence == "default-heuristic" ? "flag" : "revise"
```

Generate at minimum:
- CP-S{n} (timing, structural) + CP-S{n}a (content, semantic) per beat
- CP-V{n} (presence, structural) per mandatory visual_motif
- CP-V{n} (structural, structural) per mandatory key_visual_moment
- CP-E{n} (timing, structural) per editing_rhythm entry
- CP-B1 (presence, structural) — brand name in final scene
- CP-B3 (presence, structural) — prohibited elements (negated check)

### v2 structured criteria (mandatory for every structural checkpoint)

For every checkpoint where `evaluation_method == "structural"`, emit a
`structured` block alongside the natural-language `criterion`. The
`compliance_check` tool short-circuits the regex parser when `structured` is
present; the natural-language `criterion` becomes informational only. This
eliminates the silent-failure class where slightly off-template English broke
the parser and reported a "content failure" that wasn't.

```json
// timing → structured form
{
  "id": "CP-S1",
  "applies_to_stage": "script",
  "check_type": "timing",
  "evaluation_method": "structural",
  "criterion": "Section covering beat hook must be within ±10% of 5s",
  "structured": {
    "kind": "timing",
    "beat_id": "hook",
    "target_seconds": 5.0,
    "tolerance": 0.10
  },
  "source_confidence": "research-grounded",
  "failure_action": "revise"
}

// presence → structured form (positive)
{
  "id": "CP-B1",
  "applies_to_stage": "edit",
  "check_type": "presence",
  "evaluation_method": "structural",
  "criterion": "Brand name 'Flowcut' must appear in final scene",
  "structured": {
    "kind": "presence",
    "terms": ["Flowcut"],
    "min_count": 1
  },
  ...
}

// presence → structured form (negated / prohibited)
{
  "id": "CP-B3",
  "structured": {
    "kind": "presence",
    "terms": ["beat the competition", "industry-leading"],
    "negated": true
  },
  ...
}

// structural beat-mapping → structured form
{
  "id": "CP-V2",
  "structured": {
    "kind": "beat_mapping",
    "beat_id": "cta_brand"
  },
  ...
}
```

Semantic checkpoints (`evaluation_method == "semantic"`) do NOT emit a
`structured` block — those are evaluated by LLM judgment, not the tool.

Do not hand-author values that don't match what `criterion` describes; the
two views must agree. The tool will use `structured` regardless of what the
prose says, so a mismatch is a self-inflicted bug.

## Round 2 — Two-Step User Review

### Step 7a — Research Alignment Review (G-I)

Present the results of reconciling `enriched_brief` against `intelligence_brief.dimension_verdicts`.
This replaces the old narrative design presentation — the user already approved the creative
direction at G-0. This step is about evidence, not re-design.

Build three sections from `dimension_verdicts`:

```
RESEARCH ALIGNMENT REVIEW — [Brand Name] [Platform] [Duration]s Ad
──────────────────────────────────────────────────────────────────

CONFIRMED ✓  (research supports your brief)
  [dimension]: [one-line evidence summary from challenge_evidence or rationale]
  [dimension]: [one-line evidence summary]
  ...

CHALLENGED ✗  (strong evidence contradicts your brief)
  [dimension]
    Your brief:          [enriched_brief value for this dimension]
    (Use "Current recommended brief" instead of "Your brief" when the dimension's
     hypothesis flag status is DELEGATED.)
    Research found:      [challenge_evidence — specific, named examples or metrics]
    Recommendation:      [specific alternative the research supports]
    Your choice:         [ Keep my choice ]  or  [ Accept recommendation ]

  [next challenged dimension — same structure]
  ...

FLAGGED ⚠  (moderate signal — your call)
  [dimension]
    Your brief:          [enriched_brief value]
    (Use "Current recommended brief" instead of "Your brief" when the dimension's
     hypothesis flag status is DELEGATED.)
    Research suggests:   [what intelligence found, with confidence tier noted]
    Your choice:         [ Keep ]  or  [ Update to: _____ ]

  [next flagged dimension — same structure]
  ...

All items reviewed. Reply CONFIRM to lock this direction and proceed to execution
details — or raise any additional concerns now.
```

**Section population rules:**

| `dimension_verdicts` entry | Which section |
|---------------------------|--------------|
| verdict=SUPPORTED (any confidence) | CONFIRMED ✓ |
| verdict=CONTRADICTED, confidence=research-grounded | CHALLENGED ✗ |
| verdict=CONTRADICTED, confidence=pattern-inferred | FLAGGED ⚠ |
| verdict=INSUFFICIENT-DATA (any confidence) | FLAGGED ⚠ |
| confidence=default-heuristic (any verdict) | **Silent** — resolve in favour of enriched_brief; do NOT surface |

**Project B — classification_aggregate population rules:**
When `production_bible.intelligence.classification_aggregate` is set
(Step 0b ran on hit ads with classification blocks), surface it as an
additional Round 2a entry on `arc_type` and `hook_mechanic`:

| Aggregate condition | Which section |
|---------------------|--------------|
| confidence=research-grounded AND aggregate.arc_type == enriched_brief.arc_type | CONFIRMED ✓ |
| confidence=research-grounded AND aggregate.arc_type ≠ enriched_brief.arc_type | CHALLENGED ✗ |
| confidence=pattern-inferred AND aggregate.arc_type ≠ enriched_brief.arc_type | FLAGGED ⚠ |
| confidence=pattern-inferred AND aggregate.arc_type == enriched_brief.arc_type | **Silent** — concurrence with low-sample evidence is informational only |

When CHALLENGED, present:
```
arc_type
  Your brief:           [enriched_brief.arc_type]
  Aggregate of N hit ads: [aggregate.arc_type]   (agreement: X%, sample: N)
  Dissent:              [list each {arc_type, hook_mechanic} from aggregate.dissent]
  Your choice:          [ Keep my choice ]  or  [ Accept the aggregate ]
```

The dissent list is mandatory — the user must see "these N ads went a
different way and here's what they chose" so they can weigh the aggregate
against their brand context. Never auto-override.

**All-green rule:** If there are zero CHALLENGED and zero FLAGGED items, still show the
CONFIRMED section and still end with the confirmation prompt. Never auto-advance.

**If the CONFIRMED and FLAGGED sections are both empty** (no verdicts at all):
Show a minimal message:
```
RESEARCH ALIGNMENT REVIEW
Research found no strong signals to challenge your brief.

All items reviewed. Reply CONFIRM to lock this direction and proceed to execution
details — or raise any additional concerns now.
```

**If user replies CONFIRM:**
Set `approval.strategic_approved = true`. Advance to Step 7b.

**If user selects "Keep my choice" on a CHALLENGED item:**
Accept the user's choice. Log in `production_bible` that the user overrode research on
this dimension. Do not re-present or re-argue.

**If user selects "Accept recommendation" on a CHALLENGED item:**
Update the relevant bible field (arc_type, beat sequence, music_direction, etc.) to the
research-recommended value. Re-execute the affected synthesis steps (1–6). Re-present 7a.

**If user requests any other narrative-level change:**
Re-execute Steps 1–7 (full re-derivation — no patching). Re-present 7a.
Do not advance to 7b until `approval.strategic_approved = true`.

**Round 2a Regression — when to re-run intelligence:**
- `product`, `platform`, or `demographic` changed materially → re-run intelligence-director
  with updated intake_brief before re-running bible-director.
- arc_type / pacing / hook / key_message / tone changed → re-run bible-director only.

### Step 7b — Execution Confirmation (can be fast-tracked)

Present: visual direction, audio direction, deliverables primary, compliance checkpoints
in plain English. Flag ⚠ on `default-heuristic` checkpoints.

**CTA collection** (insert between AUDIO and WHAT WILL BE DELIVERED):
```
CALL TO ACTION
  [If cta set:] CTA: "[cta text]" — exact text in final frame. Correct?
  [If cta null:] We need the exact call-to-action text for the final frame.
    Examples: "Try free for 30 days" / "Visit acme.com" / "Download the app"
    What should the CTA say?
```

CTA MUST be non-null before `approval.execution_approved = true`.

**If user requests execution-level changes** (visual, motifs, rhythm, audio, deliverables):
Re-execute Steps 3–7. Preserve narrative. Reset `approval.execution_approved = false` only.

**If user requests narrative-level changes at 7b** (arc_type, beats, hook_mechanic,
key_message, emotional_target on any beat, pacing_model):
Reset `approval.strategic_approved = false`. Re-execute Steps 1–7. Re-present 7a.
Tell user: "That change affects the story direction we agreed on — rebuilding and
re-confirming the narrative first."
The classification is deterministic: if the change maps to any field in
`production_bible.narrative` or `production_bible.identity.key_message`, it is narrative-level.

**Mixed changes** (narrative + execution in one message): treat as narrative-level.

### Step 8: Submit

Write to `projects/<project-name>/artifacts/production_bible.json`.
Set both `approval.strategic_approved` and `approval.execution_approved` to `true`
only after both rounds complete. EP gate G-I checks both flags AND verifies cta is non-null.

## Common Pitfalls

- **Patching after 7a changes**: Always re-derive from Step 1. Patching one section
  leaves audio, visual, and compliance out of sync.
- **Leaving cta null after 7b**: CTA null at bible completion blocks script-director.
- **Fabricating compliance**: Generate compliance_manifest mechanically from beat sequence
  and visual motifs, not from memory.
- **Applying narrative changes at 7b silently**: Detect them, reset strategic_approved,
  re-present 7a. Never slip narrative changes through the execution review back door.
