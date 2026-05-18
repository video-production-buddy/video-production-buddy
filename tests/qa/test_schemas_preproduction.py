#!/usr/bin/env python3
"""Tests: validate enriched_brief, intake_brief, intelligence_brief, production_bible schemas."""

import json
import sys
import copy
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

try:
    import jsonschema
    HAS_JSONSCHEMA = True
except ImportError:
    HAS_JSONSCHEMA = False
    print("WARNING: jsonschema not installed. Run: pip install jsonschema")

ROOT = Path(__file__).resolve().parent.parent.parent
SCHEMAS_DIR = ROOT / "schemas" / "artifacts"


def load_schema(name: str) -> dict:
    path = SCHEMAS_DIR / f"{name}.schema.json"
    assert path.exists(), f"Schema not found: {path}"
    with open(path) as f:
        return json.load(f)


def load_schema_at(path: Path) -> dict:
    assert path.exists(), f"Schema not found: {path}"
    with open(path) as f:
        return json.load(f)


def validate(instance: dict, schema: dict) -> None:
    if not HAS_JSONSCHEMA:
        raise RuntimeError("jsonschema not installed")
    jsonschema.validate(instance, schema, format_checker=jsonschema.FormatChecker())


# ============================================================
# TestEnrichedBriefSchema
# ============================================================

def _minimal_beat(n: int, start: int, end: int) -> dict:
    return {
        "beat_name": f"BEAT {n}",
        "time_range": f"{start}-{end}s",
        "visual_description": "Close-up of product on textured surface, soft natural light.",
        "emotional_target": "curiosity",
        "key_action": "Camera slowly zooms in on product label.",
    }


def _minimal_creative_requirements() -> dict:
    def delegated() -> dict:
        return {
            "value": "Recommend a category-fit value from the brief.",
            "source": "DELEGATED",
            "basis": "User explicitly delegated this worksheet dimension to the creative director.",
        }

    return {
        "product_model": {
            "value": "Acme Floral Water summer edition",
            "source": "FROM BRIEF",
            "basis": "User specified the exact product name.",
        },
        "core_selling_points": {
            "value": "Cooling sensation, natural citronella, pocketable frosted bottle",
            "source": "FROM BRIEF",
            "basis": "User listed the product benefits.",
        },
        "platform_duration": {
            "value": "TikTok, 9:16, 30 seconds",
            "source": "FROM BRIEF",
            "basis": "User selected TikTok and 30s delivery.",
        },
        "target_audience": {
            "value": "Urban women 20-35, active outdoors in summer evenings",
            "source": "FROM BRIEF",
            "basis": "User described the audience and usage occasion.",
        },
        "tone_style": delegated(),
        "visual_approach": delegated(),
        "language_voiceover": {
            "value": "English narration with English burnt-in subtitles",
            "source": "FROM BRIEF",
            "basis": "User requested English narration.",
        },
        "mandatory_marketing": {
            "value": "Include 'Cool. Calm. Protected.' and show the product bottle clearly.",
            "source": "FROM BRIEF",
            "basis": "User supplied slogan and product-visibility requirement.",
        },
        "cta": {
            "value": "Shop Acme Floral Water today",
            "source": "FROM BRIEF",
            "basis": "User supplied CTA copy.",
        },
        "product_fidelity_references": delegated(),
    }


def _minimal_enriched_brief() -> dict:
    return {
        "creative_requirements": _minimal_creative_requirements(),
        "product_brief": {
            "product_name": "Acme Floral Water",
            "product_type": "Personal care / mosquito-repellent floral water",
            "tagline": "Cool. Calm. Protected.",
            "product_description": (
                "Acme Floral Water combines natural citronella extract with a cooling "
                "rose-water base. A single spritz leaves skin pleasantly chilled for up "
                "to four hours. Packaged in a frosted emerald glass bottle."
            ),
            "target_demographic": "Urban women 20-35, active outdoors in summer evenings.",
        },
        "ad_specification": {
            "duration_seconds": 30,
            "platform": "tiktok",
            "language": "English",
            "visual_style": "cinematic",
            "aspect_ratio": "9:16",
            "tone": "fresh, playful, confident",
            "music_direction": (
                "Opens with light guzheng plucks over ambient summer sounds (0-5s). "
                "Mid-section builds to upbeat indie-pop energy (5-22s). "
                "Climaxes at the product hero moment with a bright synth sting (22-26s). "
                "Outro resolves to a gentle fade (26-30s). "
                "Music ducks to -18 dB under narration."
            ),
        },
        "narrative_arc": [
            _minimal_beat(1, 0, 6),
            _minimal_beat(2, 6, 13),
            _minimal_beat(3, 13, 20),
            _minimal_beat(4, 20, 26),
            _minimal_beat(5, 26, 30),
        ],
        "brand_guideline": {
            "primary_color": "#006B3F",
            "accent_color": "#F5E6C8",
            "font_style": "Headline: light sans-serif; Body: clean sans-serif",
            "logo_placement": "Bottom-right from beat 4 onward",
            "prohibited_elements": [
                "No competitor brand names or logos",
                "No claims of medical efficacy (e.g. 'kills mosquitoes')",
                "No dark or threatening imagery of insects",
            ],
        },
        "narration_notes": {
            "voice_description": "Female, mid-20s. Warm, clear, gently energetic. Delivery: conversational.",
            "key_lines": [
                "Summer nights just got a whole lot cooler.",
                "One spritz and you're protected — naturally.",
                "Cool. Calm. Protected. Acme Floral Water.",
            ],
            "target_word_count": 75,
        },
        "hypothesis_flags": [
            {"dimension": "arc_type", "status": "INFERRED", "basis": "problem-solution dominant in personal-care TikTok ads"},
            {"dimension": "music_direction", "status": "INFERRED", "basis": "platform norm: upbeat for summer personal-care"},
            {"dimension": "target_demographic", "status": "FROM BRIEF", "basis": "user stated 'young women'"},
            {"dimension": "visual_approach", "status": "DELEGATED", "basis": "user chose recommend-for-me in the creative requirements worksheet"},
        ],
        "user_approved": False,
    }


class TestEnrichedBriefSchema:
    def setup_method(self):
        self.schema = load_schema_at(ROOT / "schemas" / "artifacts" / "enriched_brief.schema.json")

    def test_valid_minimal(self):
        validate(_minimal_enriched_brief(), self.schema)

    def test_user_approved_true_is_valid(self):
        instance = _minimal_enriched_brief()
        instance["user_approved"] = True
        validate(instance, self.schema)

    def test_rejects_fewer_than_5_narrative_beats(self):
        instance = _minimal_enriched_brief()
        instance["narrative_arc"] = instance["narrative_arc"][:4]  # 4 beats — below minItems:5
        try:
            validate(instance, self.schema)
            assert False, "Expected ValidationError for fewer than 5 beats"
        except jsonschema.ValidationError:
            pass

    def test_rejects_more_than_5_narrative_beats(self):
        instance = _minimal_enriched_brief()
        instance["narrative_arc"].append(_minimal_beat(6, 30, 35))  # 6 beats — above maxItems:5
        try:
            validate(instance, self.schema)
            assert False, "Expected ValidationError for more than 5 beats"
        except jsonschema.ValidationError:
            pass

    def test_rejects_invalid_primary_color_hex(self):
        instance = _minimal_enriched_brief()
        instance["brand_guideline"]["primary_color"] = "green"  # not #RRGGBB
        try:
            validate(instance, self.schema)
            assert False, "Expected ValidationError for non-hex primary_color"
        except jsonschema.ValidationError:
            pass

    def test_rejects_fewer_than_3_prohibited_elements(self):
        instance = _minimal_enriched_brief()
        instance["brand_guideline"]["prohibited_elements"] = ["rule1", "rule2"]  # below minItems:3
        try:
            validate(instance, self.schema)
            assert False, "Expected ValidationError for fewer than 3 prohibited_elements"
        except jsonschema.ValidationError:
            pass

    def test_rejects_fewer_than_3_key_lines(self):
        instance = _minimal_enriched_brief()
        instance["narration_notes"]["key_lines"] = ["line1", "line2"]  # below minItems:3
        try:
            validate(instance, self.schema)
            assert False, "Expected ValidationError for fewer than 3 key_lines"
        except jsonschema.ValidationError:
            pass

    def test_rejects_invalid_platform_enum(self):
        instance = _minimal_enriched_brief()
        instance["ad_specification"]["platform"] = "snapchat"  # not in enum
        try:
            validate(instance, self.schema)
            assert False, "Expected ValidationError for platform 'snapchat'"
        except jsonschema.ValidationError:
            pass

    def test_rejects_invalid_visual_style_enum(self):
        instance = _minimal_enriched_brief()
        instance["ad_specification"]["visual_style"] = "3d"  # not in enum
        try:
            validate(instance, self.schema)
            assert False, "Expected ValidationError for visual_style '3d'"
        except jsonschema.ValidationError:
            pass

    def test_rejects_invalid_hypothesis_flag_status(self):
        instance = _minimal_enriched_brief()
        instance["hypothesis_flags"][0]["status"] = "ASSUMED"  # not in enum
        try:
            validate(instance, self.schema)
            assert False, "Expected ValidationError for status 'ASSUMED'"
        except jsonschema.ValidationError:
            pass

    def test_rejects_empty_hypothesis_flags(self):
        instance = _minimal_enriched_brief()
        instance["hypothesis_flags"] = []  # below minItems:1
        try:
            validate(instance, self.schema)
            assert False, "Expected ValidationError for empty hypothesis_flags"
        except jsonschema.ValidationError:
            pass

    def test_rejects_missing_product_brief(self):
        instance = _minimal_enriched_brief()
        del instance["product_brief"]
        try:
            validate(instance, self.schema)
            assert False, "Expected ValidationError for missing product_brief"
        except jsonschema.ValidationError:
            pass

    def test_user_edits_optional(self):
        instance = _minimal_enriched_brief()
        instance["user_edits"] = [
            {"section": "Narrative Arc", "field": "arc_type", "original": "problem-solution", "revised": "contrast"}
        ]
        validate(instance, self.schema)

    def test_rejects_missing_creative_requirement_dimension(self):
        instance = _minimal_enriched_brief()
        del instance["creative_requirements"]["cta"]
        try:
            validate(instance, self.schema)
            assert False, "Expected ValidationError for missing cta creative requirement"
        except jsonschema.ValidationError:
            pass

    def test_rejects_inferred_required_creative_requirement(self):
        instance = _minimal_enriched_brief()
        instance["creative_requirements"]["tone_style"]["source"] = "INFERRED"
        try:
            validate(instance, self.schema)
            assert False, "Expected ValidationError because required worksheet dimensions must be FROM_BRIEF or DELEGATED"
        except jsonschema.ValidationError:
            pass

    def test_accepts_delegated_hypothesis_flag_status(self):
        instance = _minimal_enriched_brief()
        instance["hypothesis_flags"] = [
            {"dimension": "tone_style", "status": "DELEGATED", "basis": "user asked the creative director to recommend it"}
        ]
        validate(instance, self.schema)


# ============================================================
# TestIntakeBriefSchema
# ============================================================

class TestIntakeBriefSchema:
    def setup_method(self):
        self.schema = load_schema("intake_brief")

    def _minimal(self) -> dict:
        return {
            "product": "Acme App",
            "platform": "tiktok",
            "duration_target_seconds": 30,
            "intake_completeness": "thin",
            "round1_questions_asked": ["What are you advertising?"],
        }

    def test_valid_minimal(self):
        validate(self._minimal(), self.schema)

    def test_valid_rich(self):
        rich = {
            "product": "Acme App",
            "brand_name": "Acme Inc.",
            "platform": "youtube",
            "duration_target_seconds": 60,
            "demographic": "25-34 urban professionals",
            "emotional_intent": "aspiration",
            "key_message": "Work smarter, not harder.",
            "cta": "Download free",
            "tone": "confident",
            "reference_files": [
                {
                    "filename": "brand_guide.pdf",
                    "inferred_role": "brand_guideline",
                    "reason": "Contains logo usage and typography rules",
                }
            ],
            "style_mode_candidate": "animated",
            "round1_questions_asked": [
                "What is your core message?",
                "Who is the target audience?",
            ],
            "intake_completeness": "rich",
        }
        validate(rich, self.schema)

    def test_rejects_more_than_3_questions(self):
        instance = self._minimal()
        instance["round1_questions_asked"] = [
            "Q1?",
            "Q2?",
            "Q3?",
            "Q4?",  # exceeds maxItems: 3
        ]
        try:
            validate(instance, self.schema)
            assert False, "Expected ValidationError for more than 3 questions"
        except jsonschema.ValidationError:
            pass

    def test_rejects_invalid_platform(self):
        instance = self._minimal()
        instance["platform"] = "snapchat"  # not in enum
        try:
            validate(instance, self.schema)
            assert False, "Expected ValidationError for invalid platform 'snapchat'"
        except jsonschema.ValidationError:
            pass

    def test_rejects_missing_required(self):
        instance = {"product": "X"}  # missing platform, duration_target_seconds, etc.
        try:
            validate(instance, self.schema)
            assert False, "Expected ValidationError for missing required fields"
        except jsonschema.ValidationError:
            pass


# ============================================================
# TestIntelligenceBriefSchema
# ============================================================

class TestIntelligenceBriefSchema:
    def setup_method(self):
        self.schema = load_schema("intelligence_brief")

    def _valid_base(self) -> dict:
        return {
            "audience_psychographics": {
                "emotional_profile": "Overwhelmed but optimistic",
                "core_pain_point": "Too much admin work steals creative time",
                "aspiration": "Reclaim hours to do meaningful work",
            },
            "platform_trends": [
                {
                    "signal": "Hook-first short videos under 3 seconds dominate",
                    "source": "TikTok Insights Q1 2026",
                    "relevance": "Audiences skip after 2s — hook must be immediate",
                }
            ],
            "hit_ads_analyzed": [
                {
                    "title": "Notion — Feel the difference",
                    "platform": "youtube",
                    "arc_type": "problem-solution",
                    "hook_mechanic": "question",
                    "what_works": "Relatable chaos before calm payoff",
                    "adopted": True,
                    "adaptation": "Adapt problem montage to product's context",
                }
            ],
            "rejected_approaches": [
                {
                    "approach": "Celebrity testimonial",
                    "reason": "Budget constraint and low brand recognition fit",
                }
            ],
            "recommendations": {
                "arc_type": {
                    "value": "problem-solution",
                    "confidence": "research-grounded",
                    "rationale": "Dominant pattern in top-performing SaaS ads",
                },
                "pacing_model": {
                    "value": "punchy",
                    "confidence": "pattern-inferred",
                    "rationale": "TikTok audience retention drops after 2s",
                },
                "hook_mechanic": {
                    "value": "question",
                    "confidence": "research-grounded",
                    "rationale": "Questions create cognitive gap",
                },
                "hook_window_seconds": {
                    "value": 2,
                    "confidence": "research-grounded",
                    "rationale": "Platform data shows 2s drop-off",
                },
                "overall_rationale": "Pattern from 5 analyzed hit ads converges on fast hook + social proof.",
            },
        }

    def test_valid_base(self):
        validate(self._valid_base(), self.schema)

    def test_rejects_empty_rejected_approaches(self):
        instance = self._valid_base()
        instance["rejected_approaches"] = []  # minItems: 1 violated
        try:
            validate(instance, self.schema)
            assert False, "Expected ValidationError for empty rejected_approaches"
        except jsonschema.ValidationError:
            pass

    def test_rejects_invalid_confidence_tier(self):
        instance = self._valid_base()
        instance["recommendations"]["arc_type"]["confidence"] = "guessed"  # not in enum
        try:
            validate(instance, self.schema)
            assert False, "Expected ValidationError for invalid confidence tier 'guessed'"
        except jsonschema.ValidationError:
            pass

    def test_valid_with_dimension_verdicts(self):
        instance = self._valid_base()
        instance["dimension_verdicts"] = [
            {"dimension": "arc_type", "confidence": "research-grounded", "verdict": "SUPPORTED"},
            {"dimension": "music_direction", "confidence": "pattern-inferred", "verdict": "INSUFFICIENT-DATA"},
            {
                "dimension": "hook_mechanic",
                "confidence": "research-grounded",
                "verdict": "CONTRADICTED",
                "challenge_evidence": "Notion 2024 TikTok campaign used question hook with 52% completion rate vs 31% for statement hook.",
            },
        ]
        validate(instance, self.schema)

    def test_dimension_verdicts_rejects_invalid_verdict(self):
        instance = self._valid_base()
        instance["dimension_verdicts"] = [
            {"dimension": "arc_type", "confidence": "research-grounded", "verdict": "MAYBE"}
        ]
        try:
            validate(instance, self.schema)
            assert False, "Expected ValidationError for verdict 'MAYBE'"
        except jsonschema.ValidationError:
            pass

    def test_note_default_heuristic_contradicted_passes_schema(self):
        # The rule "default-heuristic → verdict must be INSUFFICIENT-DATA" is enforced by
        # intelligence-director skill logic, not the JSON schema.
        # Schema cannot express cross-field conditionals without if/then/else.
        # EP runtime and skill instructions enforce this — schema intentionally allows it.
        instance = self._valid_base()
        instance["dimension_verdicts"] = [
            {"dimension": "pacing_model", "confidence": "default-heuristic", "verdict": "CONTRADICTED"}
        ]
        validate(instance, self.schema)  # must pass schema validation


# ============================================================
# TestProductionBibleSchema
# ============================================================

MINIMAL_BIBLE = {
    "version": "1.0",
    "pipeline": "ad-video",
    "project_id": "proj-acme-001",
    "approval": {
        "strategic_approved": False,
        "execution_approved": False,
        "modifications_log": [],
    },
    "identity": {
        "product": "Acme App",
        "platform": "tiktok",
        "duration_target_seconds": 30,
        "key_message": "Work smarter with Acme.",
        "cta": "Download free",
        "tone": "energetic",
    },
    "narrative": {
        "arc_type": "problem-solution",
        "pacing_model": "punchy",
        "hook_mechanic": "question",
        "hook_window_seconds": 2,
        "tension_peak_at_seconds": 15,
        "resolution_type": "relief",
        "emotional_beat_sequence": [
            {
                "beat_id": "b1",
                "name": "hook",
                "duration_seconds": 3,
                "emotional_target": "curiosity",
                "intensity": 0.7,
                "script_constraint": "Open with a provocative question",
                "visual_constraint": "Single tight face shot",
            },
            {
                "beat_id": "b2",
                "name": "resolution",
                "duration_seconds": 5,
                "emotional_target": "relief",
                "intensity": 0.9,
                "script_constraint": "Deliver the payoff line",
                "visual_constraint": "Product UI reveal",
            },
        ],
    },
    "intelligence": {
        "rejected_approaches": [
            {"approach": "Celebrity endorsement", "reason": "Budget out of scope"}
        ]
    },
    "visual": {
        "style_mode": "animated",
        "render_runtime": "remotion",
    },
    "audio": {},
    "brand_constraints": {
        "brand_name_in_final_frame": True,
    },
    "deliverables": {
        "primary": {
            "aspect_ratio": "9:16",
            "duration_seconds": 30,
        }
    },
    "compliance_manifest": {
        "checkpoints": [
            {
                "id": "C-001",
                "applies_to_stage": "script",
                "description": "Hook must appear within first 2 seconds",
                "check_type": "timing",
                "evaluation_method": "structural",
                "criterion": "first_scene.start_seconds <= 2",
                "source_confidence": "research-grounded",
                "failure_action": "revise",
            }
        ]
    },
}


class TestProductionBibleSchema:
    def setup_method(self):
        self.schema = load_schema("production_bible")

    def test_valid_minimal_bible(self):
        validate(MINIMAL_BIBLE, self.schema)

    def test_rejects_wrong_pipeline(self):
        instance = copy.deepcopy(MINIMAL_BIBLE)
        instance["pipeline"] = "animated-explainer"  # const: "ad-video" violated
        try:
            validate(instance, self.schema)
            assert False, "Expected ValidationError for pipeline != 'ad-video'"
        except jsonschema.ValidationError:
            pass

    def test_rejects_invalid_arc_type(self):
        instance = copy.deepcopy(MINIMAL_BIBLE)
        instance["narrative"]["arc_type"] = "mystery-reveal"  # not in enum
        try:
            validate(instance, self.schema)
            assert False, "Expected ValidationError for invalid arc_type 'mystery-reveal'"
        except jsonschema.ValidationError:
            pass

    def test_rejects_invalid_evaluation_method(self):
        instance = copy.deepcopy(MINIMAL_BIBLE)
        instance["compliance_manifest"]["checkpoints"][0]["evaluation_method"] = "heuristic"
        try:
            validate(instance, self.schema)
            assert False, "Expected ValidationError for invalid evaluation_method 'heuristic'"
        except jsonschema.ValidationError:
            pass

    def test_brand_name_in_final_frame_must_be_true(self):
        instance = copy.deepcopy(MINIMAL_BIBLE)
        instance["brand_constraints"]["brand_name_in_final_frame"] = False  # const: true violated
        try:
            validate(instance, self.schema)
            assert False, "Expected ValidationError: brand_name_in_final_frame must be true"
        except jsonschema.ValidationError:
            pass

    def test_accepts_arc_specific_beat_names(self):
        # Beat name is not enum-constrained — the schema accepts any non-empty string.
        # This confirms that all arc-type-specific beat names pass validation.
        instance = copy.deepcopy(MINIMAL_BIBLE)
        instance["narrative"]["emotional_beat_sequence"] = [
            {
                "beat_id": "b1",
                "name": "hook",
                "duration_seconds": 3,
                "emotional_target": "curiosity",
                "intensity": 0.7,
                "script_constraint": "Open provocatively",
                "visual_constraint": "Tight face shot",
            },
            {
                "beat_id": "b2",
                "name": "problem",
                "duration_seconds": 5,
                "emotional_target": "frustration",
                "intensity": 0.6,
                "script_constraint": "Show the pain point",
                "visual_constraint": "Chaotic screen montage",
            },
            {
                "beat_id": "b3",
                "name": "solution_intro",
                "duration_seconds": 5,
                "emotional_target": "curiosity",
                "intensity": 0.5,
                "script_constraint": "Introduce the product gently",
                "visual_constraint": "Product first glimpse",
            },
            {
                "beat_id": "b4",
                "name": "proof",
                "duration_seconds": 7,
                "emotional_target": "confidence",
                "intensity": 0.8,
                "script_constraint": "Social proof stats",
                "visual_constraint": "Testimonial split-screen",
            },
            {
                "beat_id": "b5",
                "name": "resolution",
                "duration_seconds": 5,
                "emotional_target": "relief",
                "intensity": 0.9,
                "script_constraint": "Payoff line",
                "visual_constraint": "Product UI reveal",
            },
            {
                "beat_id": "b6",
                "name": "cta",
                "duration_seconds": 5,
                "emotional_target": "motivation",
                "intensity": 0.85,
                "script_constraint": "Clear call to action",
                "visual_constraint": "Brand end card",
            },
        ]
        # Must pass — no enum constraint on beat name.
        validate(instance, self.schema)

    def test_note_cta_null_with_execution_approved_passes_schema(self):
        # Schema allows this — cta is null but execution_approved is true.
        # EP gate G-I MUST reject this at runtime.
        instance = copy.deepcopy(MINIMAL_BIBLE)
        instance["approval"]["strategic_approved"] = True
        instance["approval"]["execution_approved"] = True
        instance["identity"]["cta"] = None  # null CTA is valid per schema
        # Must pass schema validation — the runtime gate, not the schema, enforces CTA presence.
        validate(instance, self.schema)


# ============================================================
# Standalone runner (no pytest required)
# ============================================================

if __name__ == "__main__":
    if not HAS_JSONSCHEMA:
        print("FATAL: jsonschema not installed. Run: pip install jsonschema")
        sys.exit(1)

    PASS = 0
    FAIL = 0

    def run_test(instance, method_name: str) -> None:
        global PASS, FAIL
        try:
            instance.setup_method()
            getattr(instance, method_name)()
            print(f"  [PASS] {type(instance).__name__}.{method_name}")
            PASS += 1
        except Exception as exc:
            print(f"  [FAIL] {type(instance).__name__}.{method_name} — {exc}")
            FAIL += 1

    print("\n--- TestEnrichedBriefSchema ---")
    for method in [
        "test_valid_minimal",
        "test_user_approved_true_is_valid",
        "test_rejects_fewer_than_5_narrative_beats",
        "test_rejects_more_than_5_narrative_beats",
        "test_rejects_invalid_primary_color_hex",
        "test_rejects_fewer_than_3_prohibited_elements",
        "test_rejects_fewer_than_3_key_lines",
        "test_rejects_invalid_platform_enum",
        "test_rejects_invalid_visual_style_enum",
        "test_rejects_invalid_hypothesis_flag_status",
        "test_rejects_empty_hypothesis_flags",
        "test_rejects_missing_product_brief",
        "test_user_edits_optional",
        "test_rejects_missing_creative_requirement_dimension",
        "test_rejects_inferred_required_creative_requirement",
        "test_accepts_delegated_hypothesis_flag_status",
    ]:
        run_test(TestEnrichedBriefSchema(), method)

    print("\n--- TestIntakeBriefSchema ---")
    for method in [
        "test_valid_minimal",
        "test_valid_rich",
        "test_rejects_more_than_3_questions",
        "test_rejects_invalid_platform",
        "test_rejects_missing_required",
    ]:
        run_test(TestIntakeBriefSchema(), method)

    print("\n--- TestIntelligenceBriefSchema ---")
    for method in [
        "test_valid_base",
        "test_rejects_empty_rejected_approaches",
        "test_rejects_invalid_confidence_tier",
        "test_valid_with_dimension_verdicts",
        "test_dimension_verdicts_rejects_invalid_verdict",
        "test_note_default_heuristic_contradicted_passes_schema",
    ]:
        run_test(TestIntelligenceBriefSchema(), method)

    print("\n--- TestProductionBibleSchema ---")
    for method in [
        "test_valid_minimal_bible",
        "test_rejects_wrong_pipeline",
        "test_rejects_invalid_arc_type",
        "test_rejects_invalid_evaluation_method",
        "test_brand_name_in_final_frame_must_be_true",
        "test_accepts_arc_specific_beat_names",
        "test_note_cta_null_with_execution_approved_passes_schema",
    ]:
        run_test(TestProductionBibleSchema(), method)

    total = PASS + FAIL
    print(f"\nResults: {PASS}/{total} passed, {FAIL} failed")
    sys.exit(0 if FAIL == 0 else 1)
