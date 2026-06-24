#!/usr/bin/env python3
"""Tests: ad-video pipeline manifest structural validation.

Verifies:
  - YAML parses without error
  - Manifest validates against pipeline_manifest.schema.json
  - All 8 generic top-level stages present in correct order
  - Ad-video governance remains as checkpointable child gates
  - Artifact dependency graph: every required_artifact is produced by a prior stage
  - Key stage fields (checkpoint_required, human_approval_default, optional_tools)
  - Pre-production stages have correct required fields
  - compliance_check declared as optional_tool for script/scene_plan/edit
  - No stale artifact names (proposal_packet, brief, selected_idea)

Run: VPB_ALLOW_BROWSER_OPEN=0 PYTHONDONTWRITEBYTECODE=1 python -m pytest -p no:cacheprovider tests/contracts/test_pipeline_manifest.py -q
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import yaml

try:
    import jsonschema
    HAS_JSONSCHEMA = True
except ImportError:
    HAS_JSONSCHEMA = False

ROOT = Path(__file__).resolve().parent.parent.parent
MANIFEST_PATH = ROOT / "pipeline_defs" / "ad-video.yaml"
MANIFEST_SCHEMA_PATH = ROOT / "schemas" / "pipelines" / "pipeline_manifest.schema.json"
BILLED_TEXT_CHAT_TOOLS = {"qwen_chat", "minimax_chat"}
PIPELINE_TOOL_FIELDS = (
    "required_tools",
    "optional_tools",
    "preferred_tools",
    "fallback_tools",
    "tools_available",
)

EXPECTED_STAGE_ORDER = [
    "research", "proposal", "script", "scene_plan", "assets", "edit", "compose", "publish",
]

EXPECTED_GATE_ORDER = [
    "research.intake",
    "research.brief_enrichment",
    "research.intelligence",
    "proposal.bible",
    "proposal.idea",
    "proposal.technical_proposal",
    "script",
    "scene_plan",
    "assets",
    "edit",
    "compose",
    "publish",
]


def load_manifest() -> dict:
    with open(MANIFEST_PATH) as f:
        return yaml.safe_load(f)


def stage(m: dict, name: str) -> dict:
    return next(s for s in m["stages"] if s["name"] == name)


def child_gate(m: dict, parent: str, name: str) -> dict:
    return next(s for s in stage(m, parent)["sub_stages"] if s["name"] == name)


def unit(m: dict, unit_id: str) -> dict:
    if "." not in unit_id:
        return stage(m, unit_id)
    parent, child = unit_id.split(".", 1)
    return child_gate(m, parent, child)


def checkpoint_units(m: dict) -> list[tuple[str, dict]]:
    units: list[tuple[str, dict]] = []
    for s in m["stages"]:
        child_units = [
            (f"{s['name']}.{child['name']}", child)
            for child in s.get("sub_stages", [])
            if child.get("skill") or child.get("produces") or "checkpoint_required" in child
        ]
        if child_units:
            units.extend(child_units)
        else:
            units.append((s["name"], s))
    return units


def iter_manifest_dicts(node):
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from iter_manifest_dicts(value)
    elif isinstance(node, list):
        for item in node:
            yield from iter_manifest_dicts(item)


# ─────────────────────────────────────────────────────────────────────────────
# Basic parsing and schema validation
# ─────────────────────────────────────────────────────────────────────────────

def test_manifest_parses_without_error():
    """ad-video.yaml must load as valid YAML."""
    m = load_manifest()
    assert isinstance(m, dict) and "stages" in m


def test_manifest_has_required_top_level_fields():
    m = load_manifest()
    for field in ("name", "version", "stages"):
        assert field in m, f"Missing required field: {field}"
    assert isinstance(m["stages"], list)


def test_manifest_validates_against_json_schema():
    """Manifest validates against pipeline_manifest.schema.json."""
    if not HAS_JSONSCHEMA:
        print("  [SKIP] jsonschema not installed")
        return
    m = load_manifest()
    with open(MANIFEST_SCHEMA_PATH) as f:
        schema = json.load(f)
    jsonschema.validate(m, schema, format_checker=jsonschema.FormatChecker())


# ─────────────────────────────────────────────────────────────────────────────
# Stage presence and order
# ─────────────────────────────────────────────────────────────────────────────

def test_has_exactly_8_generic_top_level_stages():
    m = load_manifest()
    assert len(m["stages"]) == 8, f"Expected 8, got {len(m['stages'])}"


def test_stage_order_is_correct():
    m = load_manifest()
    actual = [s["name"] for s in m["stages"]]
    assert actual == EXPECTED_STAGE_ORDER, (
        f"Stage order mismatch.\nExpected: {EXPECTED_STAGE_ORDER}\nActual:   {actual}"
    )


def test_no_duplicate_stage_names():
    m = load_manifest()
    names = [s["name"] for s in m["stages"]]
    assert len(names) == len(set(names)), f"Duplicate stages: {names}"


def test_checkpoint_gate_order_preserves_ad_video_governance():
    m = load_manifest()
    actual = [unit_id for unit_id, _ in checkpoint_units(m)]
    assert actual == EXPECTED_GATE_ORDER


# ─────────────────────────────────────────────────────────────────────────────
# Artifact dependency graph
# ─────────────────────────────────────────────────────────────────────────────

def test_artifact_dependency_graph_complete():
    """Every required_artifact must be produced by a prior stage — no broken links."""
    m = load_manifest()
    produced = set()
    errors = []
    for unit_id, s in checkpoint_units(m):
        for req in s.get("required_artifacts_in", []):
            if req not in produced:
                errors.append(f"'{unit_id}' requires '{req}' but no prior gate produces it")
        for p in s.get("produces", []):
            produced.add(p)
    assert not errors, "Broken dependencies:\n" + "\n".join(f"  ❌ {e}" for e in errors)


def test_intake_produces_intake_brief():
    m = load_manifest()
    assert "intake_brief" in unit(m, "research.intake").get("produces", [])


def test_brief_enrichment_requires_intake_brief():
    m = load_manifest()
    assert "intake_brief" in unit(m, "research.brief_enrichment").get("required_artifacts_in", [])


def test_brief_enrichment_produces_enriched_brief():
    m = load_manifest()
    assert "enriched_brief" in unit(m, "research.brief_enrichment").get("produces", [])


def test_brief_enrichment_requires_human_approval():
    m = load_manifest()
    be = unit(m, "research.brief_enrichment")
    assert be.get("checkpoint_required") is True
    assert be.get("human_approval_default") is True


def test_brief_enrichment_review_focus_includes_user_approved():
    m = load_manifest()
    focus_text = " ".join(unit(m, "research.brief_enrichment").get("review_focus", []))
    assert "user_approved" in focus_text


def test_brief_enrichment_review_focus_includes_hypothesis_flags():
    m = load_manifest()
    focus_text = " ".join(unit(m, "research.brief_enrichment").get("review_focus", []))
    assert "hypothesis_flags" in focus_text


def test_intelligence_requires_intake_brief():
    m = load_manifest()
    assert "intake_brief" in unit(m, "research.intelligence").get("required_artifacts_in", [])


def test_intelligence_requires_enriched_brief():
    m = load_manifest()
    assert "enriched_brief" in unit(m, "research.intelligence").get("required_artifacts_in", [])


def test_bible_requires_intake_brief_and_intelligence_brief():
    m = load_manifest()
    reqs = unit(m, "proposal.bible").get("required_artifacts_in", [])
    assert "intake_brief" in reqs
    assert "enriched_brief" in reqs
    assert "intelligence_brief" in reqs


def test_bible_produces_production_bible():
    m = load_manifest()
    assert "production_bible" in unit(m, "proposal.bible").get("produces", [])


def test_idea_requires_production_bible():
    m = load_manifest()
    assert "production_bible" in unit(m, "proposal.idea").get("required_artifacts_in", [])


def test_idea_produces_idea_options():
    m = load_manifest()
    assert "idea_options" in unit(m, "proposal.idea").get("produces", [])


def test_proposal_requires_idea_options():
    m = load_manifest()
    assert "idea_options" in unit(m, "proposal.technical_proposal").get("required_artifacts_in", [])


def test_proposal_produces_production_proposal():
    m = load_manifest()
    produces = unit(m, "proposal.technical_proposal").get("produces", [])
    assert "production_proposal" in produces
    assert "proposal_packet" not in produces


def test_script_requires_production_bible():
    m = load_manifest()
    assert "production_bible" in stage(m, "script").get("required_artifacts_in", [])


def test_script_requires_idea_options():
    """script-director needs the selected concept scenario."""
    m = load_manifest()
    assert "idea_options" in stage(m, "script").get("required_artifacts_in", [])


def test_scene_plan_requires_production_bible():
    m = load_manifest()
    assert "production_bible" in stage(m, "scene_plan").get("required_artifacts_in", [])


def test_edit_requires_production_bible():
    m = load_manifest()
    assert "production_bible" in stage(m, "edit").get("required_artifacts_in", [])


# ─────────────────────────────────────────────────────────────────────────────
# Stale artifact names must not appear anywhere
# ─────────────────────────────────────────────────────────────────────────────

def test_no_stage_requires_proposal_packet():
    """proposal_packet was the old artifact name — must be fully eliminated."""
    m = load_manifest()
    violations = [
        unit_id for unit_id, s in checkpoint_units(m)
        if "proposal_packet" in s.get("required_artifacts_in", [])
    ]
    assert not violations, f"Stages still requiring stale 'proposal_packet': {violations}"


def test_no_stage_requires_selected_idea():
    """selected_idea was a non-existent artifact name — must be eliminated."""
    m = load_manifest()
    violations = [
        unit_id for unit_id, s in checkpoint_units(m)
        if "selected_idea" in s.get("required_artifacts_in", [])
    ]
    assert not violations, f"Stages requiring non-existent 'selected_idea': {violations}"


def test_no_stage_produces_brief():
    """'brief' was the old idea output — must be replaced by 'idea_options'."""
    m = load_manifest()
    violations = [
        unit_id for unit_id, s in checkpoint_units(m)
        if "brief" in s.get("produces", [])
    ]
    assert not violations, f"Stages still producing old 'brief' artifact: {violations}"


# ─────────────────────────────────────────────────────────────────────────────
# Key stage field values
# ─────────────────────────────────────────────────────────────────────────────

def test_bible_requires_human_approval():
    m = load_manifest()
    b = unit(m, "proposal.bible")
    assert b.get("checkpoint_required") is True
    assert b.get("human_approval_default") is True


def test_idea_requires_human_approval():
    """User must select a concept — cannot auto-proceed."""
    m = load_manifest()
    idea = unit(m, "proposal.idea")
    assert idea.get("checkpoint_required") is True, (
        "checkpoint_required must be True — may be False due to lingering duplicate YAML key"
    )
    assert idea.get("human_approval_default") is True


def test_idea_checkpoint_required_is_true_not_false():
    """Regression: fix commit removed duplicate checkpoint_required=false — must stay fixed."""
    m = load_manifest()
    idea = unit(m, "proposal.idea")
    assert idea.get("checkpoint_required") is True, (
        "checkpoint_required=False means the duplicate-key bug was re-introduced. "
        "Expected True because the fix commit should have resolved to True."
    )


def test_intake_runs_without_human_approval():
    """Intake interaction is embedded in the skill — no EP checkpoint gate."""
    m = load_manifest()
    intake_stage = unit(m, "research.intake")
    assert intake_stage.get("human_approval_default") is False
    assert intake_stage.get("checkpoint_required") is False


def test_intelligence_runs_without_human_approval():
    m = load_manifest()
    intel = unit(m, "research.intelligence")
    assert intel.get("human_approval_default") is False


def test_proposal_requires_human_approval():
    m = load_manifest()
    p = unit(m, "proposal.technical_proposal")
    assert p.get("checkpoint_required") is True
    assert p.get("human_approval_default") is True


# ─────────────────────────────────────────────────────────────────────────────
# compliance_check tool availability
# ─────────────────────────────────────────────────────────────────────────────

def test_compliance_check_available_to_script():
    m = load_manifest()
    assert "compliance_check" in stage(m, "script").get("optional_tools", [])


def test_compliance_check_available_to_scene_plan():
    m = load_manifest()
    assert "compliance_check" in stage(m, "scene_plan").get("optional_tools", [])


def test_compliance_check_available_to_edit():
    m = load_manifest()
    assert "compliance_check" in stage(m, "edit").get("optional_tools", [])


def test_pipeline_manifests_do_not_auto_wire_billed_text_chat_tools():
    """Billed chat tools must remain explicit ad-hoc tools, not stage defaults."""
    violations: list[str] = []
    for manifest_path in sorted((ROOT / "pipeline_defs").glob("*.yaml")):
        manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
        for node in iter_manifest_dicts(manifest):
            node_name = node.get("name", "<unnamed>")
            for field in PIPELINE_TOOL_FIELDS:
                values = node.get(field)
                if not isinstance(values, list):
                    continue
                found = sorted(BILLED_TEXT_CHAT_TOOLS.intersection(map(str, values)))
                if found:
                    violations.append(
                        f"{manifest_path.name}:{node_name}:{field}:{','.join(found)}"
                    )

    assert violations == []


# ─────────────────────────────────────────────────────────────────────────────
# Required skills list
# ─────────────────────────────────────────────────────────────────────────────

def test_required_skills_include_pre_production_directors():
    m = load_manifest()
    skills_str = " ".join(m.get("required_skills", []))
    for director in ("intake-director", "brief-enrichment-director",
                     "intelligence-director", "bible-director",
                     "technical-proposal-director"):
        assert director in skills_str, f"Missing from required_skills: {director}"


# ─────────────────────────────────────────────────────────────────────────────
# review_focus quality
# ─────────────────────────────────────────────────────────────────────────────

def test_idea_review_focus_does_not_mention_old_brief_fields():
    m = load_manifest()
    focus_text = " ".join(unit(m, "proposal.idea").get("review_focus", []))
    assert "brief artifact" not in focus_text
    assert "style_mode_candidate" not in focus_text
    assert "brand_context fields" not in focus_text


def test_idea_review_focus_references_bible_constraints():
    m = load_manifest()
    focus_text = " ".join(unit(m, "proposal.idea").get("review_focus", []))
    assert "production_bible" in focus_text or "bible" in focus_text.lower()


def test_bible_review_focus_includes_cta_check():
    m = load_manifest()
    focus_text = " ".join(unit(m, "proposal.bible").get("review_focus", []))
    assert "cta" in focus_text.lower()


def test_bible_review_focus_includes_both_approval_flags():
    m = load_manifest()
    focus_text = " ".join(unit(m, "proposal.bible").get("review_focus", []))
    assert "strategic_approved" in focus_text
    assert "execution_approved" in focus_text
