"""Fast unit tests for the HyperFrames runtime integration.

These tests do NOT invoke the HyperFrames CLI — they verify schema
acceptance, tool contract wiring, governance routing in video_compose, the
style bridge, and workspace scaffolding. Subprocess-based smoke tests live
under tests/integration/ and are opt-in.
"""

from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import jsonschema
import pytest

from tools.base_tool import ToolStatus
from lib.hyperframes_gsap_shim import gsap_shim_script
from tools.video.hyperframes_compose import HyperFramesCompose
from tools.video.video_compose import VideoCompose


@pytest.fixture
def project_renders_dir(tmp_path):
    repo_root = Path(__file__).resolve().parents[2]
    project_dir = repo_root / "projects" / f"pytest-hyperframes-compose-{tmp_path.name}"
    shutil.rmtree(project_dir, ignore_errors=True)
    renders_dir = project_dir / "renders"
    yield renders_dir
    shutil.rmtree(project_dir, ignore_errors=True)


# ------------------------------------------------------------------
# Tool contract
# ------------------------------------------------------------------


def test_hyperframes_tool_identity():
    t = HyperFramesCompose()
    assert t.name == "hyperframes_compose"
    assert t.capability == "video_post"
    assert t.provider == "hyperframes"
    assert "hyperframes" in t.agent_skills
    assert "hyperframes-cli" in t.agent_skills


def test_hyperframes_get_info_reports_runtime():
    info = HyperFramesCompose().get_info()
    assert "hyperframes_runtime" in info
    rc = info["hyperframes_runtime"]
    assert set(rc.keys()) >= {
        "runtime_available",
        "node_major",
        "ffmpeg_available",
        "npx_available",
        "reasons",
    }


def test_hyperframes_layer2_skill_names_correct_package():
    """Regression: skills/core/hyperframes.md previously claimed HyperFrames
    was 'consumable via `npx @hyperframes/cli`' which is the 404-ing name.
    A Layer 2 skill reader would get bad advice even after the
    install_instructions fix. Must name the real published package."""
    from pathlib import Path
    body = (
        Path(__file__).resolve().parent.parent.parent
        / "skills" / "core" / "hyperframes.md"
    ).read_text(encoding="utf-8")
    # The dangerous invocation must be called out, not recommended.
    # If `@hyperframes/cli` appears it must be in a warning context.
    if "@hyperframes/cli" in body:
        # Only OK if it's named as a trap, not a recommendation.
        assert (
            "404" in body
            or "NOT" in body
            or "do not" in body.lower()
            or "trap" in body.lower()
        ), (
            "skills/core/hyperframes.md still recommends `@hyperframes/cli` "
            "(the 404-ing monorepo name) without a warning. Replace with "
            "`npx hyperframes` or flag it as a trap."
        )
    # Must mention the correct published name.
    assert "npx hyperframes" in body, (
        "skills/core/hyperframes.md must reference `npx hyperframes` (the real "
        "published package). A Layer 2 skill missing this would leave agents "
        "stuck if they bypass the tool's install_instructions."
    )


def test_hyperframes_preview_guidance_does_not_launch_browser_by_default():
    """HyperFrames previews are useful, but project guidance must not pop a
    local browser unless the user explicitly asks for an interactive preview."""
    from pathlib import Path

    skill_body = (
        Path(__file__).resolve().parent.parent.parent
        / "skills"
        / "core"
        / "hyperframes.md"
    ).read_text(encoding="utf-8").lower()
    verification_text = " ".join(HyperFramesCompose.user_visible_verification).lower()

    assert "open the launch preview panel" not in skill_body
    assert "npx hyperframes preview" not in verification_text
    assert "do not launch" in skill_body
    assert "explicitly requests" in skill_body
    assert "explicitly requests" in verification_text


def test_local_gsap_shim_exposes_hyperframes_timeline_introspection():
    script = gsap_shim_script()

    assert "getChildren: function" in script


def test_hyperframes_scaffold_rejects_unknown_media_profile(tmp_path):
    workspace_path = tmp_path / "hyperframes"

    result = HyperFramesCompose().execute(
        {
            "operation": "scaffold_workspace",
            "workspace_path": str(workspace_path),
            "profile": "not-a-real-profile",
            "edit_decisions": {
                "cuts": [
                    {
                        "id": "cut-1",
                        "type": "text_card",
                        "in_seconds": 0,
                        "out_seconds": 1,
                        "text": "Hello",
                    }
                ]
            },
        }
    )

    assert not result.success
    assert "Unknown profile" in (result.error or "")
    assert "ValueError" not in (result.error or "")
    assert not workspace_path.exists()


@pytest.mark.parametrize(
    "inputs",
    [
        {"edit_decisions": "not-an-object"},
        {"edit_decisions": {"cuts": "not-a-list"}},
        {"edit_decisions": {"cuts": ["not-an-object"]}},
        {"edit_decisions": {"cuts": [{"out_seconds": "not-a-number"}]}},
    ],
)
def test_hyperframes_estimate_runtime_tolerates_malformed_edit_decisions(
    inputs: dict[str, Any],
) -> None:
    assert HyperFramesCompose().estimate_runtime(inputs) == pytest.approx(30.0)


def test_hyperframes_idempotency_key_includes_workspace_render_inputs():
    tool = HyperFramesCompose()
    base = {
        "operation": "render",
        "workspace_path": "workspace-a",
        "output_path": "out-a.mp4",
        "edit_decisions": {"cuts": [{"id": "cut-1", "out_seconds": 1}]},
        "asset_manifest": {"assets": [{"id": "video-1", "path": "a.mp4"}]},
        "playbook": {"visual_style": {"palette": "a"}},
        "profile": "youtube_landscape",
        "quality": "standard",
        "fps": 30,
        "strict": False,
        "skip_contrast": False,
        "workers": 2,
    }
    variants = [
        {"output_path": "out-b.mp4"},
        {"asset_manifest": {"assets": [{"id": "video-1", "path": "b.mp4"}]}},
        {"playbook": {"visual_style": {"palette": "b"}}},
        {"profile": "tiktok"},
        {"quality": "high"},
        {"fps": 60},
        {"strict": True},
        {"skip_contrast": True},
        {"workers": 4},
    ]

    base_key = tool.idempotency_key(base)

    for variant in variants:
        assert tool.idempotency_key({**base, **variant}) != base_key


def test_animation_proposal_director_has_no_hardcoded_costs_or_keys():
    """Regression: multiple audit rounds found hardcoded per-unit dollar costs
    and specific API key names in the animation proposal-director. Uses a
    regex to catch the ENTIRE class of drift, not just specific strings. Covers
    the whole file, not just Step 3 — dry-run round 3 found hardcoded values
    surviving in the decision matrix and Common Pitfalls after Step 3 was
    cleaned."""
    from pathlib import Path
    import re

    body = (
        Path(__file__).resolve().parent.parent.parent
        / "skills" / "pipelines" / "animation" / "proposal-director.md"
    ).read_text(encoding="utf-8")

    # Only flag NON-ZERO dollar figures. `$0` and `$0.00` labeling something
    # as free is fine (local tools don't drift in cost), but any real price
    # ($0.05, $3-15, etc.) is drift-prone and must come from estimate_cost.
    dollar_pattern = re.compile(
        r"\$(?!0(?!\.?\d*[1-9]))"          # dollar sign
        r"\d+(?:[.,]\d+)?"                  # integer or decimal part
        r"(?:\s*-\s*\$?\d+(?:[.,]\d+)?)?"   # optional range tail
    )
    env_var_pattern = re.compile(
        r"\b(FAL_KEY|OPENAI_API_KEY|RUNWAY_API_KEY|KLING_API_KEY|"
        r"REPLICATE_API_TOKEN|ANTHROPIC_API_KEY|GEMINI_API_KEY|"
        r"ELEVENLABS_API_KEY|HEYGEN_API_KEY)\b"
    )
    # Lines in anti-pattern bullets or registry-pointer bullets are allowed
    # to mention banned shapes as counter-examples.
    anti_pattern_markers = [
        "do not hardcode",
        "do not fill in",
        "don't type them from memory",
        "drift between releases",
        "governance regression",
        "if you find yourself typing",
        "read each missing tool",
        "do not fill in a dollar figure",
    ]

    violations: list[tuple[int, str]] = []
    for lineno, line in enumerate(body.splitlines(), start=1):
        if not (dollar_pattern.search(line) or env_var_pattern.search(line)):
            continue
        if any(marker in line.lower() for marker in anti_pattern_markers):
            continue
        if line.strip() in ("```", "```python", "```bash"):
            continue
        violations.append((lineno, line.strip()[:140]))

    if violations:
        formatted = "\n".join(f"  line {n}: {text}" for n, text in violations)
        raise AssertionError(
            f"Hardcoded cost figures or env var names in "
            f"animation/proposal-director.md. Director skills must pull these "
            f"from the registry (estimate_cost / install_instructions) because "
            f"provider pricing drifts between releases. Violations:\n{formatted}"
        )
    assert "provider_menu_summary" in body or "estimate_cost" in body, (
        "Animation proposal-director must reference provider_menu_summary() "
        "or estimate_cost so agents know where live pricing comes from."
    )


def test_provider_menu_summary_deduplicates_providers_across_buckets():
    """Regression: when a provider has multiple tools (e.g. two seedance tools
    both reporting provider='seedance'), the summary previously listed the
    provider as BOTH available and unavailable — reads as a contradiction to
    users. Any-available wins over any-unavailable."""
    from tools.tool_registry import registry

    registry.discover()
    s = registry.provider_menu_summary()
    for cap_entry in s["capabilities"]:
        both = set(cap_entry["available_providers"]) & set(
            cap_entry["unavailable_providers"]
        )
        assert not both, (
            f"Capability {cap_entry['capability']!r} lists providers in BOTH "
            f"available and unavailable buckets: {sorted(both)}. A provider "
            f"with any available tool must not also show as unavailable."
        )


def test_provider_menu_summary_is_cp1252_safe():
    """Regression: on Windows cp1252 stdout, printing any string with an
    em-dash crashes with UnicodeEncodeError (or renders as `?` / mojibake).
    provider_menu_summary() post-processes its output via
    _scrub_unicode_dashes so preflight pasting works on every shell.
    This protects preflight even if a future tool author writes em-dashes
    into install_instructions."""
    import json
    from tools.tool_registry import registry, _scrub_unicode_dashes

    # Direct unit test of the helper.
    dirty = "one \u2014 two \u2013 three \u2018quoted\u2019"
    clean = _scrub_unicode_dashes(dirty)
    assert "\u2014" not in clean
    assert "\u2013" not in clean
    assert "--" in clean

    # And the summary itself is scrubbed.
    registry.discover()
    summary_json = json.dumps(registry.provider_menu_summary())
    assert "\u2014" not in summary_json, (
        "em-dash leaked into provider_menu_summary — Windows cp1252 users "
        "will see mojibake in preflight."
    )
    assert "\u2013" not in summary_json, "en-dash leaked"
    # Nested structures must also be scrubbed.
    nested = _scrub_unicode_dashes({"a": ["x \u2014 y", {"b": "c \u2014 d"}]})
    assert "\u2014" not in json.dumps(nested)


def test_install_instructions_reference_correct_npm_package_name():
    """Regression: install_instructions previously pointed at `npx @hyperframes/cli`,
    which returns a 404 on the public npm registry. The real published package
    name is `hyperframes`. A fresh-session agent reading install_instructions
    and trying to verify setup would hit 404 and conclude HyperFrames isn't
    available.
    """
    hint = HyperFramesCompose.install_instructions
    # Must name the correct published package name.
    assert "`npx hyperframes" in hint or "npm package: `hyperframes`" in hint, (
        "install_instructions must reference `npx hyperframes` / npm package "
        "`hyperframes` — NOT the monorepo-internal `@hyperframes/cli` name."
    )
    # And ideally warns about the 404 trap so agents don't re-introduce it.
    assert "404" in hint or "@hyperframes/cli" in hint, (
        "install_instructions should mention that the monorepo-internal name "
        "`@hyperframes/cli` is NOT the published name — this is the exact trap "
        "that misled a previous audit."
    )


def test_runtime_check_fails_when_npm_package_unresolvable(monkeypatch):
    """Regression: `_runtime_check()` previously returned runtime_available=True
    based only on local binaries (node/ffmpeg/npx). That meant the tool lied
    when the machine was offline, npm was down, or the package name was wrong.
    The check must now include a real npm resolve."""
    # Clear process cache and force _resolve_npm_package to return a 404.
    monkeypatch.setattr(
        HyperFramesCompose, "_npm_resolve_cache", None, raising=False
    )
    monkeypatch.setattr(
        HyperFramesCompose,
        "_resolve_npm_package",
        classmethod(lambda cls: {"error": "npm package `hyperframes` not found (404)"}),
    )
    rc = HyperFramesCompose()._runtime_check()
    assert rc["runtime_available"] is False, (
        "Runtime must report NOT available when the npm package can't be "
        "resolved — even if node/ffmpeg/npx are all on PATH."
    )
    assert any("404" in r for r in rc["reasons"]), (
        "reasons must include the actual npm-resolve failure, not just a "
        "generic 'runtime unavailable' message."
    )
    assert rc["npm_resolve_error"] is not None
    assert rc["npm_package"] == "hyperframes"


def test_runtime_check_fails_when_cli_smoke_fails(monkeypatch):
    """The npm package can resolve while the actual CLI still exits nonzero."""
    monkeypatch.setattr(HyperFramesCompose, "_npm_resolve_cache", None, raising=False)
    monkeypatch.setattr(HyperFramesCompose, "_cli_smoke_cache", None, raising=False)
    monkeypatch.setattr(
        HyperFramesCompose,
        "_resolve_npm_package",
        classmethod(lambda cls: {"version": "0.7.6"}),
    )
    monkeypatch.setattr(
        HyperFramesCompose,
        "_probe_cli",
        classmethod(lambda cls: {"error": "npx hyperframes --version exit 1"}),
    )

    rc = HyperFramesCompose()._runtime_check()

    assert rc["runtime_available"] is False
    assert rc["cli_smoke_error"] == "npx hyperframes --version exit 1"
    assert any("CLI smoke check failed" in reason for reason in rc["reasons"])


def test_hyperframes_doctor_runtime_check_payload_matches_output_schema(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tool = HyperFramesCompose()
    runtime_check = {
        "runtime_available": False,
        "node_major": None,
        "ffmpeg_available": True,
        "npx_available": False,
        "npm_package": "hyperframes",
        "npm_package_version": None,
        "npm_resolve_error": None,
        "cli_available": False,
        "cli_smoke_error": None,
        "reasons": ["node not found on PATH", "npx not found on PATH"],
    }
    monkeypatch.setattr(tool, "_runtime_check", lambda: runtime_check)

    result = tool.execute({"operation": "doctor"})

    assert result.success is False
    assert result.data == {"runtime_check": runtime_check}
    jsonschema.validate(instance=result.data, schema=tool.output_schema)

    malformed_payload = {"runtime_check": {"runtime_available": False}}
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance=malformed_payload, schema=tool.output_schema)


def test_hyperframes_doctor_cli_payload_matches_output_schema(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tool = HyperFramesCompose()
    runtime_check = {
        "runtime_available": True,
        "node_major": 24,
        "ffmpeg_available": True,
        "npx_available": True,
        "npm_package": "hyperframes",
        "npm_package_version": "0.4.5",
        "npm_resolve_error": None,
        "cli_available": True,
        "cli_smoke_error": None,
        "reasons": [],
    }
    monkeypatch.setattr(tool, "_runtime_check", lambda: runtime_check)
    monkeypatch.setattr(
        tool,
        "_run_hf",
        lambda args, cwd=None, timeout=None, check=False: SimpleNamespace(
            returncode=0,
            stdout="doctor ok",
            stderr="",
        ),
    )

    result = tool.execute({"operation": "doctor"})

    assert result.success is True
    assert result.data is not None
    assert result.data["cli_doctor"] == {
        "exit_code": 0,
        "stdout_tail": "doctor ok",
        "stderr_tail": "",
    }
    jsonschema.validate(instance=result.data, schema=tool.output_schema)

    malformed_payload = dict(result.data)
    malformed_payload["cli_doctor"] = {"stdout_tail": "doctor ok"}
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance=malformed_payload, schema=tool.output_schema)


@pytest.mark.integration
@pytest.mark.node
@pytest.mark.ffmpeg
@pytest.mark.hyperframes
def test_runtime_check_succeeds_when_npm_resolves(monkeypatch):
    monkeypatch.setattr(
        HyperFramesCompose, "_npm_resolve_cache", None, raising=False
    )
    monkeypatch.setattr(
        HyperFramesCompose,
        "_resolve_npm_package",
        classmethod(lambda cls: {"version": "0.4.5"}),
    )
    rc = HyperFramesCompose()._runtime_check()
    # Local binaries must still pass for this to go green.
    if rc["node_major"] is None or not rc["ffmpeg_available"] or not rc["npx_available"]:
        pytest.skip("Local runtime floor not met on this machine")
    if not rc["runtime_available"]:
        pytest.skip("HyperFrames runtime is not available on this machine")
    assert rc["runtime_available"] is True
    assert rc["npm_package_version"] == "0.4.5"
    assert rc["reasons"] == []


def test_video_compose_render_engines_follow_hyperframes_runtime_check(monkeypatch):
    """Regression: `video_compose.get_info()['render_engines']['hyperframes']`
    must track the true availability, not just the local-binary floor.
    Without this, the 'Present Both Composition Runtimes' HARD RULE surfaces
    a runtime that cannot actually render."""
    monkeypatch.setattr(
        HyperFramesCompose, "_npm_resolve_cache", None, raising=False
    )
    monkeypatch.setattr(
        HyperFramesCompose,
        "_resolve_npm_package",
        classmethod(lambda cls: {"error": "npm package not found (404)"}),
    )
    info = VideoCompose().get_info()
    assert info["render_engines"]["hyperframes"] is False, (
        "video_compose must mark hyperframes as unavailable when the real "
        "runtime check fails. Otherwise the HARD RULE lies."
    )


def test_provider_menu_summary_returns_expected_shape():
    """Regression: AGENT_GUIDE.md line 246 points agents at provider_menu_summary
    for the capability menu. The shape must be stable and cover the fields
    the guide references."""
    from tools.tool_registry import registry

    registry.discover()
    s = registry.provider_menu_summary()

    assert set(s.keys()) == {
        "composition_runtimes",
        "capabilities",
        "model_choices",
        "setup_offers",
        "runtime_warnings",
    }
    # Composition runtimes MUST include all three engines so the HARD RULE
    # presentation has the data it needs.
    for engine in ("ffmpeg", "remotion", "hyperframes"):
        assert engine in s["composition_runtimes"]
        assert isinstance(s["composition_runtimes"][engine], bool)

    # Capabilities rollup is a list of dicts with configured/total counts.
    assert isinstance(s["capabilities"], list)
    assert len(s["capabilities"]) > 0
    for entry in s["capabilities"]:
        assert set(entry.keys()) >= {
            "capability",
            "configured",
            "total",
            "available_providers",
            "unavailable_providers",
        }
        assert entry["configured"] <= entry["total"]

    # setup_offers and runtime_warnings must be lists (possibly empty).
    assert isinstance(s["model_choices"], list)
    assert isinstance(s["setup_offers"], list)
    assert isinstance(s["runtime_warnings"], list)


def test_agent_guide_references_provider_menu_summary():
    """Regression: AGENT_GUIDE.md must route agents to provider_menu_summary
    instead of dumping support_envelope raw. If this gets reverted a fresh-
    session agent will paste the firehose into chat."""
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent.parent
    guide = (root / "AGENT_GUIDE.md").read_text(encoding="utf-8")
    assert "provider_menu_summary" in guide, (
        "AGENT_GUIDE.md must reference provider_menu_summary() as the primary "
        "preflight helper — without this, agents fall back to the firehose."
    )


def test_hyperframes_unknown_operation_returns_error():
    result = HyperFramesCompose().execute({"operation": "bogus"})
    assert not result.success
    assert "Unknown operation" in (result.error or "")


def test_hyperframes_missing_operation_returns_error():
    result = HyperFramesCompose().execute({})
    assert not result.success
    assert "operation" in (result.error or "")


def test_hyperframes_lint_requires_workspace():
    # No workspace_path → ValueError surfaced through execute as a ToolResult.
    result = HyperFramesCompose().execute({"operation": "lint"})
    assert not result.success
    assert "workspace_path" in (result.error or "")


def test_hyperframes_lint_cli_payload_matches_output_schema(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    tool = HyperFramesCompose()
    workspace_path = tmp_path / "hyperframes"
    workspace_path.mkdir()
    (workspace_path / "index.html").write_text("<div></div>", encoding="utf-8")

    monkeypatch.setattr(
        tool,
        "_run_hf",
        lambda args, cwd=None, timeout=None, check=False: SimpleNamespace(
            returncode=0,
            stdout='{"ok": true}',
            stderr="",
        ),
    )

    result = tool.execute({"operation": "lint", "workspace_path": str(workspace_path)})

    assert result.success is True
    assert result.data == {
        "workspace_path": str(workspace_path),
        "exit_code": 0,
        "report": {"ok": True},
        "stderr_tail": "",
    }
    jsonschema.validate(instance=result.data, schema=tool.output_schema)

    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance={"exit_code": 0}, schema=tool.output_schema)

    malformed_add_block = {
        "operation": "add_block",
        "exit_code": 0,
        "stdout_tail": "",
        "stderr_tail": "",
    }
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance=malformed_add_block, schema=tool.output_schema)


def test_hyperframes_render_requires_workspace():
    result = HyperFramesCompose().execute({"operation": "render"})
    assert not result.success
    # Depending on runtime availability, error mentions either workspace or runtime.
    err = (result.error or "").lower()
    assert ("workspace" in err) or ("runtime" in err) or ("hyperframes" in err)


def test_hyperframes_add_block_rejects_non_string_block_name_before_cli(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    tool = HyperFramesCompose()
    workspace_path = tmp_path / "hyperframes"
    workspace_path.mkdir()
    run_calls: list[list[str]] = []

    def fake_run_hf(args, cwd=None, timeout=None, check=False):
        run_calls.append(args)
        return SimpleNamespace(returncode=0, stdout='{"ok": true}', stderr="")

    monkeypatch.setattr(tool, "_run_hf", fake_run_hf)

    result = tool.execute(
        {
            "operation": "add_block",
            "workspace_path": str(workspace_path),
            "block_name": 123,
        }
    )

    assert result.success is False
    assert "block_name" in (result.error or "").lower()
    assert "string" in (result.error or "").lower()
    assert "attributeerror" not in (result.error or "").lower()
    assert run_calls == []


def test_hyperframes_scaffold_rejects_non_object_edit_decisions(tmp_path: Path) -> None:
    workspace_path = tmp_path / "hyperframes"

    result = HyperFramesCompose().execute(
        {
            "operation": "scaffold_workspace",
            "workspace_path": str(workspace_path),
            "edit_decisions": "not-an-object",
            "asset_manifest": {"assets": []},
        }
    )

    assert result.success is False
    assert "edit_decisions" in (result.error or "").lower()
    assert "object" in (result.error or "").lower()
    assert "attributeerror" not in (result.error or "").lower()
    assert not workspace_path.exists()


def test_hyperframes_scaffold_rejects_non_list_edit_decisions_cuts(
    tmp_path: Path,
) -> None:
    workspace_path = tmp_path / "hyperframes"

    result = HyperFramesCompose().execute(
        {
            "operation": "scaffold_workspace",
            "workspace_path": str(workspace_path),
            "edit_decisions": {"cuts": "not-a-list"},
            "asset_manifest": {"assets": []},
        }
    )

    assert result.success is False
    assert "edit_decisions.cuts" in (result.error or "").lower()
    assert "array" in (result.error or "").lower()
    assert "attributeerror" not in (result.error or "").lower()
    assert not workspace_path.exists()


def test_hyperframes_scaffold_rejects_non_object_edit_decisions_cut_entry(
    tmp_path: Path,
) -> None:
    workspace_path = tmp_path / "hyperframes"

    result = HyperFramesCompose().execute(
        {
            "operation": "scaffold_workspace",
            "workspace_path": str(workspace_path),
            "edit_decisions": {"cuts": ["not-an-object"]},
            "asset_manifest": {"assets": []},
        }
    )

    assert result.success is False
    assert "edit_decisions.cuts[0]" in (result.error or "").lower()
    assert "object" in (result.error or "").lower()
    assert "attributeerror" not in (result.error or "").lower()
    assert not workspace_path.exists()


def test_hyperframes_scaffold_rejects_non_string_edit_decisions_cut_source(
    tmp_path: Path,
) -> None:
    workspace_path = tmp_path / "hyperframes"

    result = HyperFramesCompose().execute(
        {
            "operation": "scaffold_workspace",
            "workspace_path": str(workspace_path),
            "edit_decisions": {
                "cuts": [{"id": "cut-1", "source": ["not", "a", "string"]}],
            },
            "asset_manifest": {"assets": []},
        }
    )

    assert result.success is False
    assert "edit_decisions.cuts[0].source" in (result.error or "").lower()
    assert "string" in (result.error or "").lower()
    assert "typeerror" not in (result.error or "").lower()
    assert not workspace_path.exists()


def test_hyperframes_scaffold_rejects_non_string_edit_decisions_cut_type(
    tmp_path: Path,
) -> None:
    workspace_path = tmp_path / "hyperframes"

    result = HyperFramesCompose().execute(
        {
            "operation": "scaffold_workspace",
            "workspace_path": str(workspace_path),
            "edit_decisions": {
                "cuts": [{"id": "cut-1", "type": ["not", "a", "string"]}],
            },
            "asset_manifest": {"assets": []},
        }
    )

    assert result.success is False
    assert "edit_decisions.cuts[0].type" in (result.error or "").lower()
    assert "string" in (result.error or "").lower()
    assert "attributeerror" not in (result.error or "").lower()
    assert not workspace_path.exists()


def test_hyperframes_scaffold_rejects_non_numeric_edit_decisions_cut_out_seconds(
    tmp_path: Path,
) -> None:
    workspace_path = tmp_path / "hyperframes"

    result = HyperFramesCompose().execute(
        {
            "operation": "scaffold_workspace",
            "workspace_path": str(workspace_path),
            "edit_decisions": {
                "cuts": [{"id": "cut-1", "out_seconds": "not-a-number"}],
            },
            "asset_manifest": {"assets": []},
        }
    )

    assert result.success is False
    assert "edit_decisions.cuts[0].out_seconds" in (result.error or "").lower()
    assert "number" in (result.error or "").lower()
    assert "valueerror" not in (result.error or "").lower()
    assert not workspace_path.exists()


def test_hyperframes_scaffold_rejects_non_numeric_edit_decisions_cut_in_seconds(
    tmp_path: Path,
) -> None:
    workspace_path = tmp_path / "hyperframes"

    result = HyperFramesCompose().execute(
        {
            "operation": "scaffold_workspace",
            "workspace_path": str(workspace_path),
            "edit_decisions": {
                "cuts": [
                    {
                        "id": "cut-1",
                        "in_seconds": "not-a-number",
                        "out_seconds": 1,
                    }
                ],
            },
            "asset_manifest": {"assets": []},
        }
    )

    assert result.success is False
    assert "edit_decisions.cuts[0].in_seconds" in (result.error or "").lower()
    assert "number" in (result.error or "").lower()
    assert "valueerror" not in (result.error or "").lower()
    assert not workspace_path.exists()


def test_hyperframes_scaffold_rejects_non_string_edit_decisions_cut_text(
    tmp_path: Path,
) -> None:
    workspace_path = tmp_path / "hyperframes"

    result = HyperFramesCompose().execute(
        {
            "operation": "scaffold_workspace",
            "workspace_path": str(workspace_path),
            "edit_decisions": {
                "cuts": [{"id": "cut-1", "text": ["not", "a", "string"]}],
            },
            "asset_manifest": {"assets": []},
        }
    )

    assert result.success is False
    assert "edit_decisions.cuts[0].text" in (result.error or "").lower()
    assert "string" in (result.error or "").lower()
    assert "attributeerror" not in (result.error or "").lower()
    assert not workspace_path.exists()


def test_hyperframes_scaffold_rejects_non_object_edit_decisions_audio(
    tmp_path: Path,
) -> None:
    workspace_path = tmp_path / "hyperframes"

    result = HyperFramesCompose().execute(
        {
            "operation": "scaffold_workspace",
            "workspace_path": str(workspace_path),
            "edit_decisions": {
                "cuts": [{"id": "cut-1", "out_seconds": 1}],
                "audio": "not-an-object",
            },
            "asset_manifest": {"assets": []},
        }
    )

    assert result.success is False
    assert "edit_decisions.audio" in (result.error or "").lower()
    assert "object" in (result.error or "").lower()
    assert "attributeerror" not in (result.error or "").lower()
    assert not workspace_path.exists()


def test_hyperframes_scaffold_rejects_non_object_audio_narration(
    tmp_path: Path,
) -> None:
    workspace_path = tmp_path / "hyperframes"

    result = HyperFramesCompose().execute(
        {
            "operation": "scaffold_workspace",
            "workspace_path": str(workspace_path),
            "edit_decisions": {
                "cuts": [{"id": "cut-1", "out_seconds": 1}],
                "audio": {"narration": "not-an-object"},
            },
            "asset_manifest": {"assets": []},
        }
    )

    assert result.success is False
    assert "edit_decisions.audio.narration" in (result.error or "").lower()
    assert "object" in (result.error or "").lower()
    assert "attributeerror" not in (result.error or "").lower()
    assert not workspace_path.exists()


def test_hyperframes_scaffold_rejects_non_list_audio_narration_segments(
    tmp_path: Path,
) -> None:
    workspace_path = tmp_path / "hyperframes"

    result = HyperFramesCompose().execute(
        {
            "operation": "scaffold_workspace",
            "workspace_path": str(workspace_path),
            "edit_decisions": {
                "cuts": [{"id": "cut-1", "out_seconds": 1}],
                "audio": {"narration": {"segments": "not-a-list"}},
            },
            "asset_manifest": {"assets": []},
        }
    )

    assert result.success is False
    assert "edit_decisions.audio.narration.segments" in (result.error or "").lower()
    assert "array" in (result.error or "").lower()
    assert "attributeerror" not in (result.error or "").lower()
    assert not workspace_path.exists()


def test_hyperframes_scaffold_rejects_non_object_audio_narration_segment_entry(
    tmp_path: Path,
) -> None:
    workspace_path = tmp_path / "hyperframes"

    result = HyperFramesCompose().execute(
        {
            "operation": "scaffold_workspace",
            "workspace_path": str(workspace_path),
            "edit_decisions": {
                "cuts": [{"id": "cut-1", "out_seconds": 1}],
                "audio": {"narration": {"segments": ["not-an-object"]}},
            },
            "asset_manifest": {"assets": []},
        }
    )

    assert result.success is False
    assert "edit_decisions.audio.narration.segments[0]" in (
        result.error or ""
    ).lower()
    assert "object" in (result.error or "").lower()
    assert "attributeerror" not in (result.error or "").lower()
    assert not workspace_path.exists()


def test_hyperframes_scaffold_rejects_non_string_audio_narration_segment_asset_id(
    tmp_path: Path,
) -> None:
    workspace_path = tmp_path / "hyperframes"

    result = HyperFramesCompose().execute(
        {
            "operation": "scaffold_workspace",
            "workspace_path": str(workspace_path),
            "edit_decisions": {
                "cuts": [{"id": "cut-1", "out_seconds": 1}],
                "audio": {
                    "narration": {
                        "segments": [{"asset_id": ["not", "a", "string"]}],
                    },
                },
            },
            "asset_manifest": {"assets": []},
        }
    )

    assert result.success is False
    assert "edit_decisions.audio.narration.segments[0].asset_id" in (
        result.error or ""
    ).lower()
    assert "string" in (result.error or "").lower()
    assert "typeerror" not in (result.error or "").lower()
    assert not workspace_path.exists()


def test_hyperframes_scaffold_rejects_non_numeric_audio_narration_segment_start_seconds(
    tmp_path: Path,
) -> None:
    workspace_path = tmp_path / "hyperframes"
    narration_asset = tmp_path / "narration.wav"
    narration_asset.write_bytes(b"not-a-real-wave-but-present")

    result = HyperFramesCompose().execute(
        {
            "operation": "scaffold_workspace",
            "workspace_path": str(workspace_path),
            "edit_decisions": {
                "cuts": [{"id": "cut-1", "out_seconds": 1}],
                "audio": {
                    "narration": {
                        "segments": [
                            {
                                "asset_id": "narration-1",
                                "start_seconds": "not-a-number",
                            },
                        ],
                    },
                },
            },
            "asset_manifest": {
                "assets": [{"id": "narration-1", "path": str(narration_asset)}],
            },
        }
    )

    assert result.success is False
    assert "edit_decisions.audio.narration.segments[0].start_seconds" in (
        result.error or ""
    ).lower()
    assert "number" in (result.error or "").lower()
    assert "valueerror" not in (result.error or "").lower()
    assert not workspace_path.exists()


def test_hyperframes_scaffold_rejects_non_object_audio_music(
    tmp_path: Path,
) -> None:
    workspace_path = tmp_path / "hyperframes"

    result = HyperFramesCompose().execute(
        {
            "operation": "scaffold_workspace",
            "workspace_path": str(workspace_path),
            "edit_decisions": {
                "cuts": [{"id": "cut-1", "out_seconds": 1}],
                "audio": {"music": "not-an-object"},
            },
            "asset_manifest": {"assets": []},
        }
    )

    assert result.success is False
    assert "edit_decisions.audio.music" in (result.error or "").lower()
    assert "object" in (result.error or "").lower()
    assert "attributeerror" not in (result.error or "").lower()
    assert not workspace_path.exists()


def test_hyperframes_scaffold_rejects_non_string_audio_music_asset_id(
    tmp_path: Path,
) -> None:
    workspace_path = tmp_path / "hyperframes"

    result = HyperFramesCompose().execute(
        {
            "operation": "scaffold_workspace",
            "workspace_path": str(workspace_path),
            "edit_decisions": {
                "cuts": [{"id": "cut-1", "out_seconds": 1}],
                "audio": {"music": {"asset_id": ["not", "a", "string"]}},
            },
            "asset_manifest": {"assets": []},
        }
    )

    assert result.success is False
    assert "edit_decisions.audio.music.asset_id" in (result.error or "").lower()
    assert "string" in (result.error or "").lower()
    assert "typeerror" not in (result.error or "").lower()
    assert not workspace_path.exists()


def test_hyperframes_scaffold_rejects_non_string_audio_music_src(
    tmp_path: Path,
) -> None:
    workspace_path = tmp_path / "hyperframes"

    result = HyperFramesCompose().execute(
        {
            "operation": "scaffold_workspace",
            "workspace_path": str(workspace_path),
            "edit_decisions": {
                "cuts": [{"id": "cut-1", "out_seconds": 1}],
                "audio": {"music": {"src": ["not", "a", "string"]}},
            },
            "asset_manifest": {"assets": []},
        }
    )

    assert result.success is False
    assert "edit_decisions.audio.music.src" in (result.error or "").lower()
    assert "string" in (result.error or "").lower()
    assert "typeerror" not in (result.error or "").lower()
    assert not workspace_path.exists()


def test_hyperframes_scaffold_rejects_non_numeric_audio_music_volume(
    tmp_path: Path,
) -> None:
    workspace_path = tmp_path / "hyperframes"
    music_asset = tmp_path / "music.mp3"
    music_asset.write_bytes(b"not-a-real-mp3-but-present")

    result = HyperFramesCompose().execute(
        {
            "operation": "scaffold_workspace",
            "workspace_path": str(workspace_path),
            "edit_decisions": {
                "cuts": [{"id": "cut-1", "out_seconds": 1}],
                "audio": {
                    "music": {
                        "src": str(music_asset),
                        "volume": "not-a-number",
                    },
                },
            },
            "asset_manifest": {"assets": []},
        }
    )

    assert result.success is False
    assert "edit_decisions.audio.music.volume" in (result.error or "").lower()
    assert "number" in (result.error or "").lower()
    assert "valueerror" not in (result.error or "").lower()
    assert not workspace_path.exists()


def test_hyperframes_scaffold_rejects_non_object_edit_decisions_metadata(
    tmp_path: Path,
) -> None:
    workspace_path = tmp_path / "hyperframes"

    result = HyperFramesCompose().execute(
        {
            "operation": "scaffold_workspace",
            "workspace_path": str(workspace_path),
            "edit_decisions": {
                "cuts": [{"id": "cut-1", "out_seconds": 1}],
                "metadata": "not-an-object",
            },
            "asset_manifest": {"assets": []},
        }
    )

    assert result.success is False
    assert "edit_decisions.metadata" in (result.error or "").lower()
    assert "object" in (result.error or "").lower()
    assert "attributeerror" not in (result.error or "").lower()
    assert not workspace_path.exists()


def test_hyperframes_scaffold_rejects_non_string_edit_decisions_metadata_title(
    tmp_path: Path,
) -> None:
    workspace_path = tmp_path / "hyperframes"

    result = HyperFramesCompose().execute(
        {
            "operation": "scaffold_workspace",
            "workspace_path": str(workspace_path),
            "edit_decisions": {
                "cuts": [{"id": "cut-1", "out_seconds": 1}],
                "metadata": {"title": ["not", "a", "string"]},
            },
            "asset_manifest": {"assets": []},
        }
    )

    assert result.success is False
    assert "edit_decisions.metadata.title" in (result.error or "").lower()
    assert "string" in (result.error or "").lower()
    assert "attributeerror" not in (result.error or "").lower()
    assert not workspace_path.exists()


def test_hyperframes_scaffold_rejects_non_object_asset_manifest(tmp_path: Path) -> None:
    workspace_path = tmp_path / "hyperframes"

    result = HyperFramesCompose().execute(
        {
            "operation": "scaffold_workspace",
            "workspace_path": str(workspace_path),
            "edit_decisions": {
                "cuts": [{"id": "cut-1", "out_seconds": 1}],
            },
            "asset_manifest": "not-an-object",
        }
    )

    assert result.success is False
    assert "asset_manifest" in (result.error or "").lower()
    assert "object" in (result.error or "").lower()
    assert "attributeerror" not in (result.error or "").lower()
    assert not workspace_path.exists()


def test_hyperframes_scaffold_rejects_non_list_asset_manifest_assets(
    tmp_path: Path,
) -> None:
    workspace_path = tmp_path / "hyperframes"

    result = HyperFramesCompose().execute(
        {
            "operation": "scaffold_workspace",
            "workspace_path": str(workspace_path),
            "edit_decisions": {
                "cuts": [{"id": "cut-1", "out_seconds": 1}],
            },
            "asset_manifest": {"assets": "not-a-list"},
        }
    )

    assert result.success is False
    assert "asset_manifest.assets" in (result.error or "").lower()
    assert "array" in (result.error or "").lower()
    assert "attributeerror" not in (result.error or "").lower()
    assert not workspace_path.exists()


def test_hyperframes_scaffold_rejects_non_object_asset_manifest_asset_entry(
    tmp_path: Path,
) -> None:
    workspace_path = tmp_path / "hyperframes"

    result = HyperFramesCompose().execute(
        {
            "operation": "scaffold_workspace",
            "workspace_path": str(workspace_path),
            "edit_decisions": {
                "cuts": [{"id": "cut-1", "out_seconds": 1}],
            },
            "asset_manifest": {"assets": ["not-an-object"]},
        }
    )

    assert result.success is False
    assert "asset_manifest.assets[0]" in (result.error or "").lower()
    assert "object" in (result.error or "").lower()
    assert "attributeerror" not in (result.error or "").lower()
    assert not workspace_path.exists()


def test_hyperframes_scaffold_rejects_non_string_asset_manifest_asset_id(
    tmp_path: Path,
) -> None:
    workspace_path = tmp_path / "hyperframes"

    result = HyperFramesCompose().execute(
        {
            "operation": "scaffold_workspace",
            "workspace_path": str(workspace_path),
            "edit_decisions": {
                "cuts": [{"id": "cut-1", "out_seconds": 1}],
            },
            "asset_manifest": {"assets": [{"id": ["not", "a", "string"]}]},
        }
    )

    assert result.success is False
    assert "asset_manifest.assets[0].id" in (result.error or "").lower()
    assert "string" in (result.error or "").lower()
    assert "typeerror" not in (result.error or "").lower()
    assert not workspace_path.exists()


def test_hyperframes_scaffold_rejects_non_string_asset_manifest_asset_path(
    tmp_path: Path,
) -> None:
    workspace_path = tmp_path / "hyperframes"

    result = HyperFramesCompose().execute(
        {
            "operation": "scaffold_workspace",
            "workspace_path": str(workspace_path),
            "edit_decisions": {
                "cuts": [{"id": "cut-1", "source": "asset-1", "out_seconds": 1}],
            },
            "asset_manifest": {
                "assets": [{"id": "asset-1", "path": ["not", "a", "string"]}],
            },
        }
    )

    assert result.success is False
    assert "asset_manifest.assets[0].path" in (result.error or "").lower()
    assert "string" in (result.error or "").lower()
    assert "typeerror" not in (result.error or "").lower()
    assert not workspace_path.exists()


def test_hyperframes_scaffold_rejects_directory_asset_manifest_asset_path(
    tmp_path: Path,
) -> None:
    workspace_path = tmp_path / "hyperframes"
    asset_dir = tmp_path / "asset-dir"
    asset_dir.mkdir()

    result = HyperFramesCompose().execute(
        {
            "operation": "scaffold_workspace",
            "workspace_path": str(workspace_path),
            "edit_decisions": {
                "cuts": [{"id": "cut-1", "source": "asset-1", "out_seconds": 1}],
            },
            "asset_manifest": {
                "assets": [{"id": "asset-1", "path": str(asset_dir)}],
            },
        }
    )

    assert result.success is False
    assert "asset_manifest.assets[0].path" in (result.error or "").lower()
    assert "file" in (result.error or "").lower()
    assert "isadirectoryerror" not in (result.error or "").lower()
    assert not workspace_path.exists()


def test_hyperframes_scaffold_rejects_non_object_playbook(tmp_path: Path) -> None:
    workspace_path = tmp_path / "hyperframes"

    result = HyperFramesCompose().execute(
        {
            "operation": "scaffold_workspace",
            "workspace_path": str(workspace_path),
            "edit_decisions": {
                "cuts": [{"id": "cut-1", "out_seconds": 1}],
            },
            "asset_manifest": {"assets": []},
            "playbook": "not-an-object",
        }
    )

    assert result.success is False
    assert "playbook" in (result.error or "").lower()
    assert "object" in (result.error or "").lower()
    assert "attributeerror" not in (result.error or "").lower()
    assert not workspace_path.exists()


def test_hyperframes_scaffold_rejects_invalid_fps_before_workspace_creation(
    tmp_path: Path,
) -> None:
    workspace_path = tmp_path / "hyperframes"

    result = HyperFramesCompose().execute(
        {
            "operation": "scaffold_workspace",
            "workspace_path": str(workspace_path),
            "fps": 25,
            "edit_decisions": {
                "cuts": [{"id": "cut-1", "out_seconds": 1}],
            },
            "asset_manifest": {"assets": []},
        }
    )

    assert result.success is False
    assert "fps" in (result.error or "").lower()
    assert "24" in (result.error or "")
    assert not workspace_path.exists()


@pytest.mark.parametrize(
    "inputs",
    [
        {"operation": "render", "workspace_path": "projects/demo/hyperframes"},
        {
            "operation": "render",
            "workspace_path": "projects/demo/hyperframes",
            "output_path": "renders/final.mp4",
        },
    ],
)
def test_hyperframes_render_requires_project_output_path_before_runtime_check(
    inputs, monkeypatch, tmp_path
):
    monkeypatch.chdir(tmp_path)
    runtime_calls = []

    def fake_runtime_check(self):
        runtime_calls.append("runtime")
        return {"runtime_available": False, "reasons": ["should not be checked first"]}

    monkeypatch.setattr(HyperFramesCompose, "_runtime_check", fake_runtime_check)

    result = HyperFramesCompose().execute(inputs)

    assert not result.success
    assert "output_path" in (result.error or "")
    assert "projects/<project-name>/" in (result.error or "")
    assert runtime_calls == []
    assert not (tmp_path / "renders").exists()


def test_hyperframes_render_rejects_unknown_media_profile_before_output_dir_creation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    tool = HyperFramesCompose()
    output_path = Path("projects/demo/renders/final.mp4")
    workspace_path = Path("projects/demo/hyperframes")
    run_calls: list[list[str]] = []

    monkeypatch.setattr(
        tool,
        "_runtime_check",
        lambda: {"runtime_available": True, "reasons": []},
    )

    def fake_run_hf(args, cwd=None, timeout=None, check=False):
        run_calls.append(args)
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(tool, "_run_hf", fake_run_hf)

    result = tool.execute(
        {
            "operation": "render",
            "workspace_path": str(workspace_path),
            "output_path": str(output_path),
            "profile": "not-a-real-profile",
            "edit_decisions": {
                "render_runtime": "hyperframes",
                "renderer_family": "animation-first",
                "cuts": [{"id": "cut-1", "out_seconds": 1}],
            },
            "asset_manifest": {"assets": []},
        }
    )

    assert result.success is False
    assert "Unknown profile" in (result.error or "")
    assert "ValueError" not in (result.error or "")
    assert not output_path.parent.exists()
    assert not workspace_path.exists()
    assert run_calls == []


def test_hyperframes_render_success_payload_includes_output_path(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    tool = HyperFramesCompose()
    output_path = Path("projects/demo/renders/final.mp4")
    workspace_path = Path("projects/demo/hyperframes")

    monkeypatch.setattr(
        tool,
        "_runtime_check",
        lambda: {"runtime_available": True, "reasons": []},
    )
    monkeypatch.setattr(
        tool,
        "_scaffold",
        lambda inputs: SimpleNamespace(success=True, error=None, data={"ok": True}),
    )
    monkeypatch.setattr(
        tool,
        "_lint",
        lambda inputs: SimpleNamespace(success=True, error=None, data={"ok": True}),
    )
    monkeypatch.setattr(
        tool,
        "_validate",
        lambda inputs: SimpleNamespace(success=True, error=None, data={"ok": True}),
    )

    def fake_run_hf(args, cwd=None, timeout=None, check=False):
        rendered = Path(args[args.index("--output") + 1])
        rendered.parent.mkdir(parents=True, exist_ok=True)
        rendered.write_bytes(b"rendered")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(tool, "_run_hf", fake_run_hf)

    result = tool.execute(
        {
            "operation": "render",
            "workspace_path": str(workspace_path),
            "output_path": str(output_path),
            "edit_decisions": {
                "render_runtime": "hyperframes",
                "renderer_family": "animation-first",
                "cuts": [{"id": "cut-1", "out_seconds": 1}],
            },
            "asset_manifest": {"assets": []},
        }
    )

    assert result.success is True
    assert result.data is not None
    assert result.data["output"] == str(output_path)
    assert result.data["output_path"] == str(output_path)
    assert result.data["workspace"] == str(workspace_path.resolve())
    assert result.data["workspace_path"] == str(workspace_path.resolve())
    assert result.artifacts == [str(output_path)]
    assert {
        "operation",
        "output",
        "output_path",
        "workspace",
        "workspace_path",
        "width",
        "height",
        "fps",
        "quality",
        "workers",
        "steps",
    } <= set(tool.output_schema["properties"])
    jsonschema.validate(instance=result.data, schema=tool.output_schema)

    malformed_payload = dict(result.data)
    malformed_steps = dict(result.data["steps"])
    malformed_steps.pop("render")
    malformed_payload["steps"] = malformed_steps
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance=malformed_payload, schema=tool.output_schema)

    malformed_payload = dict(result.data)
    malformed_steps = {
        step_name: dict(step_data)
        for step_name, step_data in result.data["steps"].items()
    }
    malformed_steps["render"]["exit_code"] = 1
    malformed_payload["steps"] = malformed_steps
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance=malformed_payload, schema=tool.output_schema)

    malformed_payload = dict(result.data)
    malformed_payload["operation"] = "scaffold_workspace"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance=malformed_payload, schema=tool.output_schema)


def test_hyperframes_render_passes_absolute_output_path_to_cli(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    tool = HyperFramesCompose()
    output_path = Path("projects/demo/renders/final.mp4")
    workspace_path = Path("projects/demo/hyperframes")

    monkeypatch.setattr(
        tool,
        "_runtime_check",
        lambda: {"runtime_available": True, "reasons": []},
    )
    monkeypatch.setattr(
        tool,
        "_scaffold",
        lambda inputs: SimpleNamespace(success=True, error=None, data={"ok": True}),
    )
    monkeypatch.setattr(
        tool,
        "_lint",
        lambda inputs: SimpleNamespace(success=True, error=None, data={"ok": True}),
    )
    monkeypatch.setattr(
        tool,
        "_validate",
        lambda inputs: SimpleNamespace(success=True, error=None, data={"ok": True}),
    )

    def fake_run_hf(args, cwd=None, timeout=None, check=False):
        cli_output = Path(args[args.index("--output") + 1])
        assert cli_output.is_absolute()
        assert cwd == workspace_path.resolve(strict=False)
        cli_output.parent.mkdir(parents=True, exist_ok=True)
        cli_output.write_bytes(b"rendered")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(tool, "_run_hf", fake_run_hf)

    result = tool.execute(
        {
            "operation": "render",
            "workspace_path": str(workspace_path),
            "output_path": str(output_path),
            "edit_decisions": {
                "render_runtime": "hyperframes",
                "renderer_family": "animation-first",
                "cuts": [{"id": "cut-1", "out_seconds": 1}],
            },
            "asset_manifest": {"assets": []},
        }
    )

    assert result.success is True
    assert result.data is not None
    assert result.data["output_path"] == str(output_path)
    render_step = result.data["steps"]["render"]
    assert Path(render_step["cli_output_path"]).is_absolute()
    assert render_step["cli_output_path"] == str(output_path.resolve(strict=False))
    assert output_path.read_bytes() == b"rendered"


def test_hyperframes_render_missing_output_error_names_cli_output_path(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    tool = HyperFramesCompose()
    output_path = Path("projects/demo/renders/final.mp4")
    workspace_path = Path("projects/demo/hyperframes")

    monkeypatch.setattr(
        tool,
        "_runtime_check",
        lambda: {"runtime_available": True, "reasons": []},
    )
    monkeypatch.setattr(
        tool,
        "_scaffold",
        lambda inputs: SimpleNamespace(success=True, error=None, data={"ok": True}),
    )
    monkeypatch.setattr(
        tool,
        "_lint",
        lambda inputs: SimpleNamespace(success=True, error=None, data={"ok": True}),
    )
    monkeypatch.setattr(
        tool,
        "_validate",
        lambda inputs: SimpleNamespace(success=True, error=None, data={"ok": True}),
    )
    monkeypatch.setattr(
        tool,
        "_run_hf",
        lambda args, cwd=None, timeout=None, check=False: SimpleNamespace(
            returncode=0,
            stdout="render claimed success",
            stderr="",
        ),
    )

    result = tool.execute(
        {
            "operation": "render",
            "workspace_path": str(workspace_path),
            "output_path": str(output_path),
            "edit_decisions": {
                "render_runtime": "hyperframes",
                "renderer_family": "animation-first",
                "cuts": [{"id": "cut-1", "out_seconds": 1}],
            },
            "asset_manifest": {"assets": []},
        }
    )

    assert result.success is False
    expected_cli_path = str(output_path.resolve(strict=False))
    assert expected_cli_path in (result.error or "")
    assert "stdout_tail" not in (result.error or "")
    assert result.data is not None
    assert result.data["steps"]["render"]["cli_output_path"] == expected_cli_path


def test_hyperframes_scaffold_packages_cjk_font_for_chinese_text(tmp_path: Path) -> None:
    project_dir = tmp_path / "projects" / "demo"
    workspace_path = project_dir / "hyperframes"
    font_path = project_dir / "fonts" / "NotoSansSC.ttf"
    font_path.parent.mkdir(parents=True)
    font_path.write_bytes(b"fake-font")

    result = HyperFramesCompose().execute(
        {
            "operation": "scaffold_workspace",
            "workspace_path": str(workspace_path),
            "edit_decisions": {
                "renderer_family": "animation-first",
                "cuts": [
                    {
                        "id": "cut-1",
                        "type": "text_card",
                        "in_seconds": 0,
                        "out_seconds": 1,
                        "text": "一言成片",
                    }
                ],
            },
            "asset_manifest": {"assets": []},
        }
    )

    assert result.success is True
    staged_font = workspace_path / "assets" / "NotoSansSC.ttf"
    assert staged_font.read_bytes() == b"fake-font"
    html = (workspace_path / "index.html").read_text(encoding="utf-8")
    assert "@font-face" in html
    assert "Noto Sans SC" in html
    assert "assets/NotoSansSC.ttf" in html
    assert result.data is not None
    assert result.data["workspace"] == str(workspace_path)
    assert result.data["workspace_path"] == str(workspace_path)
    font_assets = result.data["font_assets"]
    assert font_assets[0]["family"] == "Noto Sans SC"
    assert font_assets[0]["from"] == str(font_path)
    assert font_assets[0]["to"] == str(staged_font)
    assert font_assets[0]["src"] == "assets/NotoSansSC.ttf"
    assert font_assets[0]["format"] == "truetype"
    jsonschema.validate(instance=result.data, schema=HyperFramesCompose.output_schema)

    malformed_payload = dict(result.data)
    malformed_payload["font_assets"] = [{"src": "assets/NotoSansSC.ttf"}]
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(
            instance=malformed_payload,
            schema=HyperFramesCompose.output_schema,
        )


def test_hyperframes_scaffold_emits_lint_safe_font_families(tmp_path: Path) -> None:
    workspace_path = tmp_path / "projects" / "demo" / "hyperframes"

    result = HyperFramesCompose().execute(
        {
            "operation": "scaffold_workspace",
            "workspace_path": str(workspace_path),
            "edit_decisions": {
                "renderer_family": "animation-first",
                "cuts": [
                    {
                        "id": "cut-1",
                        "type": "text_card",
                        "in_seconds": 0,
                        "out_seconds": 1,
                        "text": "Hello HyperFrames",
                    }
                ],
            },
            "asset_manifest": {"assets": []},
            "playbook": {
                "typography": {
                    "headings": {"font": "Inter"},
                    "body": {"font": "Inter"},
                }
            },
        }
    )

    assert result.success is True
    html = (workspace_path / "index.html").read_text(encoding="utf-8")
    font_lines = [line.strip() for line in html.splitlines() if "font-family:" in line]
    assert font_lines
    assert all("var(--font" not in line for line in font_lines)
    assert all("Noto Sans SC" not in line for line in font_lines)
    assert all("Microsoft YaHei" not in line for line in font_lines)
    assert all("PingFang SC" not in line for line in font_lines)
    assert any("font-family: Inter, sans-serif;" in line for line in font_lines)


def test_hyperframes_scaffold_fails_cjk_without_packaged_font(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    workspace_path = tmp_path / "projects" / "demo" / "hyperframes"
    monkeypatch.setattr(
        HyperFramesCompose,
        "_find_cjk_font_source",
        staticmethod(lambda workspace: None),
    )

    result = HyperFramesCompose().execute(
        {
            "operation": "scaffold_workspace",
            "workspace_path": str(workspace_path),
            "edit_decisions": {
                "cuts": [
                    {
                        "id": "cut-1",
                        "type": "text_card",
                        "in_seconds": 0,
                        "out_seconds": 1,
                        "text": "万象成章",
                    }
                ]
            },
            "asset_manifest": {"assets": []},
        }
    )

    assert result.success is False
    assert "CJK text detected" in (result.error or "")
    assert "NotoSansSC.ttf" in (result.error or "")
    assert "FileNotFoundError" not in (result.error or "")
    assert not workspace_path.exists()


def test_hyperframes_scaffold_prepares_sparse_keyframe_video(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    source_video = tmp_path / "source.mp4"
    source_video.write_bytes(b"sparse-video")
    workspace_path = tmp_path / "projects" / "demo" / "hyperframes"

    monkeypatch.setattr(
        HyperFramesCompose,
        "_needs_dense_keyframes",
        lambda self, src_path: True,
    )

    def fake_reencode(src_path: Path, dest: Path) -> None:
        assert src_path == source_video
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"dense-video")

    monkeypatch.setattr(
        HyperFramesCompose,
        "_reencode_video_dense_keyframes",
        staticmethod(fake_reencode),
    )

    result = HyperFramesCompose().execute(
        {
            "operation": "scaffold_workspace",
            "workspace_path": str(workspace_path),
            "edit_decisions": {
                "renderer_family": "animation-first",
                "cuts": [
                    {
                        "id": "cut-1",
                        "type": "video",
                        "source": str(source_video),
                        "in_seconds": 0,
                        "out_seconds": 1,
                    }
                ],
            },
            "asset_manifest": {"assets": []},
        }
    )

    assert result.success is True
    dense_video = workspace_path / "assets" / "source.dense.mp4"
    assert dense_video.read_bytes() == b"dense-video"
    html = (workspace_path / "index.html").read_text(encoding="utf-8")
    assert "assets/source.dense.mp4" in html
    assert result.data is not None
    assert result.data["asset_copies"][0]["transform"] == "dense_keyframes"


def test_hyperframes_single_keyframe_interval_uses_clip_duration(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    source_video = tmp_path / "single-keyframe.mp4"
    source_video.write_bytes(b"video")

    monkeypatch.setattr(
        "tools.video.hyperframes_compose.shutil.which",
        lambda name: "/usr/bin/ffprobe" if name == "ffprobe" else None,
    )

    def fake_run(*args: Any, **kwargs: Any) -> SimpleNamespace:
        cmd = args[0]
        assert "-skip_frame" in cmd
        return SimpleNamespace(returncode=0, stdout="0.000000\n")

    monkeypatch.setattr("tools.video.hyperframes_compose.subprocess.run", fake_run)
    monkeypatch.setattr(
        HyperFramesCompose,
        "_video_duration_seconds",
        staticmethod(lambda src_path: 12.0),
    )

    assert HyperFramesCompose._max_keyframe_interval_seconds(source_video) == 12.0
    assert HyperFramesCompose()._needs_dense_keyframes(source_video) is True


def test_hyperframes_scaffold_stages_same_basename_assets_without_collision(
    tmp_path: Path,
) -> None:
    first_asset = tmp_path / "first" / "hero.png"
    second_asset = tmp_path / "second" / "hero.png"
    first_asset.parent.mkdir()
    second_asset.parent.mkdir()
    first_asset.write_bytes(b"first-image-bytes")
    second_asset.write_bytes(b"second-image-data")
    workspace_path = tmp_path / "projects" / "demo" / "hyperframes"

    result = HyperFramesCompose().execute(
        {
            "operation": "scaffold_workspace",
            "workspace_path": str(workspace_path),
            "edit_decisions": {
                "renderer_family": "animation-first",
                "cuts": [
                    {
                        "id": "cut-1",
                        "type": "image",
                        "source": "first-hero",
                        "in_seconds": 0,
                        "out_seconds": 1,
                    },
                    {
                        "id": "cut-2",
                        "type": "image",
                        "source": "second-hero",
                        "in_seconds": 1,
                        "out_seconds": 2,
                    },
                ],
            },
            "asset_manifest": {
                "assets": [
                    {"id": "first-hero", "path": str(first_asset)},
                    {"id": "second-hero", "path": str(second_asset)},
                ]
            },
        }
    )

    assert result.success is True, result.error
    assert result.data is not None
    staged_paths = [Path(copy["to"]) for copy in result.data["asset_copies"]]
    assert len(staged_paths) == 2
    assert len({path.name for path in staged_paths}) == 2
    assert staged_paths[0].read_bytes() == first_asset.read_bytes()
    assert staged_paths[1].read_bytes() == second_asset.read_bytes()
    html = (workspace_path / "index.html").read_text(encoding="utf-8")
    assert all(f"assets/{path.name}" in html for path in staged_paths)
    jsonschema.validate(instance=result.data, schema=HyperFramesCompose.output_schema)

    malformed_payload = dict(result.data)
    malformed_payload["asset_copies"] = [{"to": str(staged_paths[0])}]
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(
            instance=malformed_payload,
            schema=HyperFramesCompose.output_schema,
        )


def test_hyperframes_scaffold_stages_same_basename_narration_without_collision(
    tmp_path: Path,
) -> None:
    import re

    first_audio = tmp_path / "first" / "voice.wav"
    second_audio = tmp_path / "second" / "voice.wav"
    first_audio.parent.mkdir()
    second_audio.parent.mkdir()
    first_audio.write_bytes(b"first-voice-bytes")
    second_audio.write_bytes(b"second-voice-data")
    workspace_path = tmp_path / "projects" / "demo" / "hyperframes"

    result = HyperFramesCompose().execute(
        {
            "operation": "scaffold_workspace",
            "workspace_path": str(workspace_path),
            "edit_decisions": {
                "renderer_family": "animation-first",
                "cuts": [
                    {
                        "id": "cut-1",
                        "type": "text_card",
                        "text": "Hello",
                        "in_seconds": 0,
                        "out_seconds": 2,
                    }
                ],
                "audio": {
                    "narration": {
                        "segments": [
                            {
                                "asset_id": "voice-1",
                                "start_seconds": 0,
                                "end_seconds": 1,
                            },
                            {
                                "asset_id": "voice-2",
                                "start_seconds": 1,
                                "end_seconds": 2,
                            },
                        ]
                    }
                },
            },
            "asset_manifest": {
                "assets": [
                    {"id": "voice-1", "path": str(first_audio)},
                    {"id": "voice-2", "path": str(second_audio)},
                ]
            },
        }
    )

    assert result.success is True, result.error
    html = (workspace_path / "index.html").read_text(encoding="utf-8")
    narration_sources = re.findall(r'<audio id="nar-\d"[^>]+src="([^"]+)"', html)
    assert len(narration_sources) == 2
    assert len(set(narration_sources)) == 2
    staged_paths = [workspace_path / src for src in narration_sources]
    assert staged_paths[0].read_bytes() == first_audio.read_bytes()
    assert staged_paths[1].read_bytes() == second_audio.read_bytes()


def test_hyperframes_scaffold_reports_staged_audio_assets_in_payload_and_schema(
    tmp_path: Path,
) -> None:
    narration = tmp_path / "audio" / "voice.wav"
    music = tmp_path / "audio" / "music.wav"
    narration.parent.mkdir()
    narration.write_bytes(b"voice-bytes")
    music.write_bytes(b"music-bytes")
    workspace_path = tmp_path / "projects" / "demo" / "hyperframes"
    tool = HyperFramesCompose()

    result = tool.execute(
        {
            "operation": "scaffold_workspace",
            "workspace_path": str(workspace_path),
            "edit_decisions": {
                "renderer_family": "animation-first",
                "cuts": [
                    {
                        "id": "cut-1",
                        "type": "text_card",
                        "text": "Hello",
                        "in_seconds": 0,
                        "out_seconds": 2,
                    }
                ],
                "audio": {
                    "narration": {
                        "segments": [
                            {
                                "asset_id": "voice",
                                "start_seconds": 0,
                                "end_seconds": 2,
                            }
                        ]
                    },
                    "music": {"asset_id": "music", "volume": 0.2},
                },
            },
            "asset_manifest": {
                "assets": [
                    {"id": "voice", "path": str(narration)},
                    {"id": "music", "path": str(music)},
                ]
            },
        }
    )

    assert result.success is True, result.error
    assert result.data is not None
    assert "audio_assets" in tool.output_schema["properties"]
    audio_assets = result.data["audio_assets"]
    assert [asset["track"] for asset in audio_assets] == ["narration", "music"]
    assert [asset["asset_id"] for asset in audio_assets] == ["voice", "music"]
    assert [asset["from"] for asset in audio_assets] == [str(narration), str(music)]
    assert [Path(asset["to"]).read_bytes() for asset in audio_assets] == [
        narration.read_bytes(),
        music.read_bytes(),
    ]
    assert [asset["src"] for asset in audio_assets] == [
        "assets/voice.wav",
        "assets/music.wav",
    ]
    jsonschema.validate(instance=result.data, schema=tool.output_schema)

    malformed_payload = dict(result.data)
    malformed_payload["audio_assets"] = [{"track": "music", "src": "assets/music.wav"}]
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance=malformed_payload, schema=tool.output_schema)


def test_hyperframes_render_auto_workers_one_for_video_heavy(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    tool = HyperFramesCompose()
    output_path = Path("projects/demo/renders/final.mp4")
    workspace_path = Path("projects/demo/hyperframes")

    monkeypatch.setattr(
        tool,
        "_runtime_check",
        lambda: {"runtime_available": True, "reasons": []},
    )
    monkeypatch.setattr(
        tool,
        "_scaffold",
        lambda inputs: SimpleNamespace(success=True, error=None, data={"ok": True}),
    )
    monkeypatch.setattr(
        tool,
        "_lint",
        lambda inputs: SimpleNamespace(success=True, error=None, data={"ok": True}),
    )
    monkeypatch.setattr(
        tool,
        "_validate",
        lambda inputs: SimpleNamespace(success=True, error=None, data={"ok": True}),
    )

    render_args: list[str] = []

    def fake_run_hf(args, cwd=None, timeout=None, check=False):
        render_args[:] = args
        rendered = Path(args[args.index("--output") + 1])
        rendered.parent.mkdir(parents=True, exist_ok=True)
        rendered.write_bytes(b"rendered")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(tool, "_run_hf", fake_run_hf)

    result = tool.execute(
        {
            "operation": "render",
            "workspace_path": str(workspace_path),
            "output_path": str(output_path),
            "edit_decisions": {
                "render_runtime": "hyperframes",
                "renderer_family": "animation-first",
                "cuts": [
                    {
                        "id": f"cut-{i}",
                        "type": "video",
                        "source": f"clip-{i}.mp4",
                        "in_seconds": i,
                        "out_seconds": i + 1,
                    }
                    for i in range(6)
                ],
            },
            "asset_manifest": {"assets": []},
        }
    )

    assert result.success is True
    assert "--workers" in render_args
    assert render_args[render_args.index("--workers") + 1] == "1"
    assert result.data is not None
    assert result.data["workers"] == 1


def test_hyperframes_render_forwards_strict_flag_to_cli(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    tool = HyperFramesCompose()
    output_path = Path("projects/demo/renders/final.mp4")
    workspace_path = Path("projects/demo/hyperframes")

    monkeypatch.setattr(
        tool,
        "_runtime_check",
        lambda: {"runtime_available": True, "reasons": []},
    )
    monkeypatch.setattr(
        tool,
        "_scaffold",
        lambda inputs: SimpleNamespace(success=True, error=None, data={"ok": True}),
    )
    monkeypatch.setattr(
        tool,
        "_lint",
        lambda inputs: SimpleNamespace(success=True, error=None, data={"ok": True}),
    )
    monkeypatch.setattr(
        tool,
        "_validate",
        lambda inputs: SimpleNamespace(success=True, error=None, data={"ok": True}),
    )

    render_args: list[str] = []

    def fake_run_hf(args, cwd=None, timeout=None, check=False):
        render_args[:] = args
        rendered = Path(args[args.index("--output") + 1])
        rendered.parent.mkdir(parents=True, exist_ok=True)
        rendered.write_bytes(b"rendered")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(tool, "_run_hf", fake_run_hf)

    result = tool.execute(
        {
            "operation": "render",
            "workspace_path": str(workspace_path),
            "output_path": str(output_path),
            "strict": True,
            "edit_decisions": {
                "render_runtime": "hyperframes",
                "renderer_family": "animation-first",
                "cuts": [{"id": "cut-1", "out_seconds": 1}],
            },
            "asset_manifest": {"assets": []},
        }
    )

    assert result.success is True
    assert "--strict" in render_args


def test_hyperframes_render_rejects_invalid_quality_before_cli(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    tool = HyperFramesCompose()
    output_path = Path("projects/demo/renders/final.mp4")
    workspace_path = Path("projects/demo/hyperframes")

    monkeypatch.setattr(
        tool,
        "_runtime_check",
        lambda: {"runtime_available": True, "reasons": []},
    )
    setup_calls: list[str] = []

    def record_setup(name: str):
        def _record(inputs):
            setup_calls.append(name)
            return SimpleNamespace(success=True, error=None, data={"ok": True})

        return _record

    monkeypatch.setattr(tool, "_scaffold", record_setup("scaffold"))
    monkeypatch.setattr(tool, "_lint", record_setup("lint"))
    monkeypatch.setattr(tool, "_validate", record_setup("validate"))
    render_calls: list[list[str]] = []

    def fake_run_hf(args, cwd=None, timeout=None, check=False):
        render_calls.append(args)
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(tool, "_run_hf", fake_run_hf)

    result = tool.execute(
        {
            "operation": "render",
            "workspace_path": str(workspace_path),
            "output_path": str(output_path),
            "quality": "cinema",
            "edit_decisions": {
                "render_runtime": "hyperframes",
                "renderer_family": "animation-first",
                "cuts": [{"id": "cut-1", "out_seconds": 1}],
            },
            "asset_manifest": {"assets": []},
        }
    )

    assert result.success is False
    assert "quality" in (result.error or "")
    assert "draft" in (result.error or "")
    assert setup_calls == []
    assert render_calls == []


def test_hyperframes_render_rejects_invalid_fps_before_cli(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    tool = HyperFramesCompose()
    output_path = Path("projects/demo/renders/final.mp4")
    workspace_path = Path("projects/demo/hyperframes")

    monkeypatch.setattr(
        tool,
        "_runtime_check",
        lambda: {"runtime_available": True, "reasons": []},
    )
    setup_calls: list[str] = []

    def record_setup(name: str):
        def _record(inputs):
            setup_calls.append(name)
            return SimpleNamespace(success=True, error=None, data={"ok": True})

        return _record

    monkeypatch.setattr(tool, "_scaffold", record_setup("scaffold"))
    monkeypatch.setattr(tool, "_lint", record_setup("lint"))
    monkeypatch.setattr(tool, "_validate", record_setup("validate"))
    render_calls: list[list[str]] = []

    def fake_run_hf(args, cwd=None, timeout=None, check=False):
        render_calls.append(args)
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(tool, "_run_hf", fake_run_hf)

    result = tool.execute(
        {
            "operation": "render",
            "workspace_path": str(workspace_path),
            "output_path": str(output_path),
            "fps": 25,
            "edit_decisions": {
                "render_runtime": "hyperframes",
                "renderer_family": "animation-first",
                "cuts": [{"id": "cut-1", "out_seconds": 1}],
            },
            "asset_manifest": {"assets": []},
        }
    )

    assert result.success is False
    assert "fps" in (result.error or "").lower()
    assert "24" in (result.error or "")
    assert setup_calls == []
    assert render_calls == []


def test_hyperframes_render_rejects_invalid_workers_before_cli(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    tool = HyperFramesCompose()
    output_path = Path("projects/demo/renders/final.mp4")
    workspace_path = Path("projects/demo/hyperframes")

    monkeypatch.setattr(
        tool,
        "_runtime_check",
        lambda: {"runtime_available": True, "reasons": []},
    )
    setup_calls: list[str] = []

    def record_setup(name: str):
        def _record(inputs):
            setup_calls.append(name)
            return SimpleNamespace(success=True, error=None, data={"ok": True})

        return _record

    monkeypatch.setattr(tool, "_scaffold", record_setup("scaffold"))
    monkeypatch.setattr(tool, "_lint", record_setup("lint"))
    monkeypatch.setattr(tool, "_validate", record_setup("validate"))
    render_calls: list[list[str]] = []

    def fake_run_hf(args, cwd=None, timeout=None, check=False):
        render_calls.append(args)
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(tool, "_run_hf", fake_run_hf)

    result = tool.execute(
        {
            "operation": "render",
            "workspace_path": str(workspace_path),
            "output_path": str(output_path),
            "workers": 0,
            "edit_decisions": {
                "render_runtime": "hyperframes",
                "renderer_family": "animation-first",
                "cuts": [{"id": "cut-1", "out_seconds": 1}],
            },
            "asset_manifest": {"assets": []},
        }
    )

    assert result.success is False
    assert "workers" in (result.error or "").lower()
    assert "1" in (result.error or "")
    assert setup_calls == []
    assert render_calls == []


def test_hyperframes_render_rejects_string_workers_before_cli(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    tool = HyperFramesCompose()
    output_path = Path("projects/demo/renders/final.mp4")
    workspace_path = Path("projects/demo/hyperframes")

    monkeypatch.setattr(
        tool,
        "_runtime_check",
        lambda: {"runtime_available": True, "reasons": []},
    )
    setup_calls: list[str] = []

    def record_setup(name: str):
        def _record(inputs):
            setup_calls.append(name)
            return SimpleNamespace(success=True, error=None, data={"ok": True})

        return _record

    monkeypatch.setattr(tool, "_scaffold", record_setup("scaffold"))
    monkeypatch.setattr(tool, "_lint", record_setup("lint"))
    monkeypatch.setattr(tool, "_validate", record_setup("validate"))
    render_calls: list[list[str]] = []

    def fake_run_hf(args, cwd=None, timeout=None, check=False):
        render_calls.append(args)
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(tool, "_run_hf", fake_run_hf)

    result = tool.execute(
        {
            "operation": "render",
            "workspace_path": str(workspace_path),
            "output_path": str(output_path),
            "workers": "2",
            "edit_decisions": {
                "render_runtime": "hyperframes",
                "renderer_family": "animation-first",
                "cuts": [{"id": "cut-1", "out_seconds": 1}],
            },
            "asset_manifest": {"assets": []},
        }
    )

    assert result.success is False
    assert "workers" in (result.error or "").lower()
    assert "integer" in (result.error or "").lower()
    assert setup_calls == []
    assert render_calls == []


def test_hyperframes_render_rejects_invalid_strict_before_cli(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    tool = HyperFramesCompose()
    output_path = Path("projects/demo/renders/final.mp4")
    workspace_path = Path("projects/demo/hyperframes")

    monkeypatch.setattr(
        tool,
        "_runtime_check",
        lambda: {"runtime_available": True, "reasons": []},
    )
    setup_calls: list[str] = []

    def record_setup(name: str):
        def _record(inputs):
            setup_calls.append(name)
            return SimpleNamespace(success=True, error=None, data={"ok": True})

        return _record

    monkeypatch.setattr(tool, "_scaffold", record_setup("scaffold"))
    monkeypatch.setattr(tool, "_lint", record_setup("lint"))
    monkeypatch.setattr(tool, "_validate", record_setup("validate"))
    render_calls: list[list[str]] = []

    def fake_run_hf(args, cwd=None, timeout=None, check=False):
        render_calls.append(args)
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(tool, "_run_hf", fake_run_hf)

    result = tool.execute(
        {
            "operation": "render",
            "workspace_path": str(workspace_path),
            "output_path": str(output_path),
            "strict": "false",
            "edit_decisions": {
                "render_runtime": "hyperframes",
                "renderer_family": "animation-first",
                "cuts": [{"id": "cut-1", "out_seconds": 1}],
            },
            "asset_manifest": {"assets": []},
        }
    )

    assert result.success is False
    assert "strict" in (result.error or "").lower()
    assert "boolean" in (result.error or "").lower()
    assert setup_calls == []
    assert render_calls == []


def test_hyperframes_render_rejects_invalid_skip_contrast_before_cli(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    tool = HyperFramesCompose()
    output_path = Path("projects/demo/renders/final.mp4")
    workspace_path = Path("projects/demo/hyperframes")

    monkeypatch.setattr(
        tool,
        "_runtime_check",
        lambda: {"runtime_available": True, "reasons": []},
    )
    setup_calls: list[str] = []

    def record_setup(name: str):
        def _record(inputs):
            setup_calls.append(name)
            return SimpleNamespace(success=True, error=None, data={"ok": True})

        return _record

    monkeypatch.setattr(tool, "_scaffold", record_setup("scaffold"))
    monkeypatch.setattr(tool, "_lint", record_setup("lint"))
    monkeypatch.setattr(tool, "_validate", record_setup("validate"))
    render_calls: list[list[str]] = []

    def fake_run_hf(args, cwd=None, timeout=None, check=False):
        render_calls.append(args)
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(tool, "_run_hf", fake_run_hf)

    result = tool.execute(
        {
            "operation": "render",
            "workspace_path": str(workspace_path),
            "output_path": str(output_path),
            "skip_contrast": "true",
            "edit_decisions": {
                "render_runtime": "hyperframes",
                "renderer_family": "animation-first",
                "cuts": [{"id": "cut-1", "out_seconds": 1}],
            },
            "asset_manifest": {"assets": []},
        }
    )

    assert result.success is False
    assert "skip_contrast" in (result.error or "").lower()
    assert "boolean" in (result.error or "").lower()
    assert setup_calls == []
    assert render_calls == []


def test_hyperframes_validate_rejects_invalid_skip_contrast_before_cli(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    tool = HyperFramesCompose()
    workspace_path = tmp_path / "hyperframes"
    workspace_path.mkdir()
    (workspace_path / "index.html").write_text("<div id='root'></div>", encoding="utf-8")

    run_calls: list[list[str]] = []

    def fake_run_hf(args, cwd=None, timeout=None, check=False):
        run_calls.append(args)
        return SimpleNamespace(returncode=0, stdout='{"ok": true}', stderr="")

    monkeypatch.setattr(tool, "_run_hf", fake_run_hf)

    result = tool.execute(
        {
            "operation": "validate",
            "workspace_path": str(workspace_path),
            "skip_contrast": "true",
        }
    )

    assert result.success is False
    assert "skip_contrast" in (result.error or "").lower()
    assert "boolean" in (result.error or "").lower()
    assert run_calls == []


# ------------------------------------------------------------------
# video_compose runtime routing
# ------------------------------------------------------------------


def test_video_compose_reports_hyperframes_engine():
    info = VideoCompose().get_info()
    assert "render_engines" in info
    assert "hyperframes" in info["render_engines"]
    assert "hyperframes_note" in info
    # Both legacy key and new alias must be present.
    assert "render_runtimes" in info
    assert info["render_engines"] == info["render_runtimes"]


def test_video_compose_governance_note_present():
    info = VideoCompose().get_info()
    assert "runtime_governance" in info
    assert "silent swap" in info["runtime_governance"].lower()


def test_video_compose_has_no_root_render_defaults():
    body = (
        Path(__file__).resolve().parent.parent.parent
        / "tools"
        / "video"
        / "video_compose.py"
    ).read_text(encoding="utf-8")

    assert '"renders/output.mp4"' not in body
    assert '"renders/remotion_output.mp4"' not in body


def test_render_requires_output_path_before_creating_default_renders(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)

    result = VideoCompose().execute(
        {
            "operation": "render",
            "edit_decisions": {
                "version": "1.0",
                "render_runtime": "ffmpeg",
                "cuts": [],
            },
            "asset_manifest": {"assets": []},
        }
    )

    assert not result.success
    assert "output_path required" in (result.error or "")
    assert not (tmp_path / "renders").exists()


def test_render_rejects_repo_root_renders_output_path(monkeypatch):
    repo_root = Path(__file__).resolve().parent.parent.parent
    root_renders = repo_root / "renders"
    had_root_renders = root_renders.exists()
    output_name = f"would-create-root-folder-{uuid.uuid4().hex}.mp4"
    rejected_output = root_renders / output_name
    assert not rejected_output.exists()

    monkeypatch.chdir(repo_root)
    result = VideoCompose().execute(
        {
            "operation": "render",
            "edit_decisions": {
                "version": "1.0",
                "render_runtime": "ffmpeg",
                "cuts": [],
            },
            "asset_manifest": {"assets": []},
            "output_path": f"renders/{output_name}",
        }
    )

    assert not result.success
    assert "project root" in (result.error or "").lower()
    assert not rejected_output.exists()
    assert root_renders.exists() == had_root_renders


def test_video_compose_rejects_unknown_render_runtime(project_renders_dir):
    """Governance: an unknown render_runtime must fail, not silently fall back."""
    comp_out = project_renders_dir / "out.mp4"
    result = VideoCompose().execute(
        {
            "operation": "render",
            "edit_decisions": {
                "version": "1.0",
                "cuts": [
                    {
                        "id": "c1",
                        "source": "nonexistent",
                        "in_seconds": 0,
                        "out_seconds": 3,
                    }
                ],
                "render_runtime": "totally-made-up",
                "renderer_family": "explainer-data",
            },
            "asset_manifest": {"assets": []},
            "output_path": str(comp_out),
        }
    )
    assert not result.success
    assert "Unknown render_runtime" in (result.error or "")


def test_video_compose_rejects_missing_render_runtime(project_renders_dir):
    """Regression: missing render_runtime MUST NOT silently fall back to Remotion.

    Prior behavior: empty/missing render_runtime fell through to the
    Remotion-default path, which defeated the auditable-runtime-selection
    governance contract.
    """
    comp_out = project_renders_dir / "out.mp4"
    result = VideoCompose().execute(
        {
            "operation": "render",
            "edit_decisions": {
                "version": "1.0",
                "cuts": [
                    {
                        "id": "c1",
                        "source": "nonexistent",
                        "in_seconds": 0,
                        "out_seconds": 3,
                    }
                ],
                # NOTE: no render_runtime field
                "renderer_family": "explainer-data",
            },
            "asset_manifest": {"assets": []},
            "output_path": str(comp_out),
        }
    )
    assert not result.success
    err = (result.error or "").lower()
    assert "render_runtime" in err
    assert "not set" in err or "must be" in err
    # Explicitly NOT treated as a Remotion request.
    assert "remotion render failed" not in err


def test_video_compose_blocks_unapproved_runtime_swap_before_render(
    tmp_path, monkeypatch, project_renders_dir
):
    composer = VideoCompose()

    def fail_if_rendered(*_args, **_kwargs):
        raise AssertionError("renderer should not run before runtime governance")

    monkeypatch.setattr(composer, "_compose", fail_if_rendered)
    monkeypatch.setattr(composer, "_remotion_render", fail_if_rendered)

    output_path = project_renders_dir / "out.mp4"
    result = composer.execute(
        {
            "operation": "render",
            "edit_decisions": {
                "version": "1.0",
                "render_runtime": "ffmpeg",
                "renderer_family": "screen-demo",
                "cuts": [
                    {
                        "id": "c1",
                        "source": "a1",
                        "in_seconds": 0,
                        "out_seconds": 2,
                    }
                ],
            },
            "asset_manifest": {"assets": [{"id": "a1", "path": "missing.mp4"}]},
            "brief": {"metadata": {"render_runtime": "remotion"}},
            "output_path": str(output_path),
        }
    )

    assert not result.success
    err = (result.error or "").lower()
    assert "unapproved render_runtime swap" in err
    assert "before render" in err
    assert not output_path.exists()


def test_video_compose_blocks_revise_final_review(
    monkeypatch,
    project_renders_dir,
):
    composer = VideoCompose()
    output_path = project_renders_dir / "out.mp4"

    monkeypatch.setattr(composer, "_pre_compose_validation", lambda *args, **kwargs: None)

    def fake_compose(_inputs):
        output_path.write_bytes(b"rendered")
        return SimpleNamespace(success=True, error=None, data={"output": str(output_path)})

    monkeypatch.setattr(composer, "_compose", fake_compose)
    monkeypatch.setattr(
        composer,
        "_run_final_review",
        lambda *args, **kwargs: {
            "status": "revise",
            "issues_found": ["runtime lock missing"],
        },
    )

    result = composer.execute(
        {
            "operation": "render",
            "edit_decisions": {
                "version": "1.0",
                "render_runtime": "ffmpeg",
                "renderer_family": "screen-demo",
                "cuts": [
                    {
                        "id": "c1",
                        "source": "a1",
                        "in_seconds": 0,
                        "out_seconds": 2,
                    }
                ],
            },
            "asset_manifest": {"assets": [{"id": "a1", "path": "source.mp4"}]},
            "output_path": str(output_path),
        }
    )

    assert not result.success
    assert result.data["final_review_status"] == "revise"
    assert "not presentable as complete" in (result.error or "")


def test_schemas_require_render_runtime():
    """Regression: both proposal_packet and edit_decisions schemas must
    REQUIRE render_runtime, not just declare it as an optional property."""
    import json
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent.parent

    ed = json.loads(
        (root / "schemas" / "artifacts" / "edit_decisions.schema.json").read_text(
            encoding="utf-8"
        )
    )
    assert "render_runtime" in ed["required"], (
        "edit_decisions.schema.json must require render_runtime — missing means "
        "governance bypass (silent Remotion fallback)."
    )

    pp = json.loads(
        (root / "schemas" / "artifacts" / "proposal_packet.schema.json").read_text(
            encoding="utf-8"
        )
    )
    pp_prod = pp["properties"]["production_plan"]
    assert "render_runtime" in pp_prod["required"], (
        "proposal_packet.production_plan must require render_runtime — "
        "the proposal stage MUST pick a runtime explicitly."
    )


def test_video_compose_input_schema_accepts_all_runtime_lock_artifacts():
    props = VideoCompose.input_schema["properties"]

    assert "proposal_packet" in props
    assert "production_proposal" in props
    assert "brief" in props
    assert "decision_log" in props


def test_video_compose_input_schema_exposes_hyperframes_render_options():
    props = VideoCompose.input_schema["properties"]

    assert {
        "workspace_path",
        "playbook",
        "playbook_name",
        "quality",
        "fps",
        "strict",
        "skip_contrast",
        "workers",
    } <= set(props)
    assert props["quality"]["enum"] == ["draft", "standard", "high"]
    assert props["fps"]["enum"] == [24, 30, 60]
    assert props["workers"]["minimum"] == 1


def test_video_compose_idempotency_key_includes_runtime_lock_artifacts():
    fields = set(VideoCompose.idempotency_key_fields)

    assert {"proposal_packet", "production_proposal", "brief", "decision_log"} <= fields


def test_video_compose_idempotency_key_includes_hyperframes_render_options():
    fields = set(VideoCompose.idempotency_key_fields)

    assert {
        "workspace_path",
        "playbook",
        "playbook_name",
        "quality",
        "fps",
        "strict",
        "skip_contrast",
        "workers",
    } <= fields


@pytest.mark.integration
@pytest.mark.ffmpeg
def test_runtime_swap_detected_flips_when_proposal_packet_disagrees(tmp_path):
    """Regression: runtime_swap_detected was previously dead code because the
    check read a metadata field no one writes. The fix accepts
    `proposal_packet` directly so the signal actually fires."""
    # Build a minimal real MP4 so final_review can probe it.
    import subprocess

    mp4 = tmp_path / "tiny.mp4"
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", "color=c=#000000:s=320x240:d=2",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            "-shortest", str(mp4),
        ],
        capture_output=True, check=True, timeout=30,
    )

    edit_decisions = {
        "version": "1.0",
        "render_runtime": "hyperframes",  # what compose actually ran
        "renderer_family": "animation-first",
        "cuts": [{"id": "c1", "source": "x", "in_seconds": 0, "out_seconds": 2}],
    }
    proposal_packet = {
        "production_plan": {
            "render_runtime": "remotion",  # what proposal approved
        },
    }

    review = VideoCompose()._run_final_review(
        mp4, edit_decisions, proposal_packet
    )
    pp = review["checks"]["promise_preservation"]
    assert pp.get("runtime_swap_detected") is True
    assert "runtime_swap_check" in pp
    assert "detected" in pp["runtime_swap_check"]
    # And the human-readable issues list mentions the swap.
    assert any("render_runtime changed" in i for i in pp.get("issues", []))
    assert review["status"] == "revise"
    assert review["recommended_action"] != "present_to_user"


@pytest.mark.integration
@pytest.mark.ffmpeg
def test_runtime_swap_detected_flips_when_production_proposal_disagrees(tmp_path):
    import subprocess

    mp4 = tmp_path / "tiny.mp4"
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", "color=c=#000000:s=320x240:d=2",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            "-shortest", str(mp4),
        ],
        capture_output=True, check=True, timeout=30,
    )

    edit_decisions = {
        "version": "1.0",
        "render_runtime": "hyperframes",
        "renderer_family": "product-reveal",
        "cuts": [{"id": "c1", "source": "x", "in_seconds": 0, "out_seconds": 2}],
    }
    production_proposal = {"render_runtime": "remotion"}

    review = VideoCompose()._run_final_review(
        mp4,
        edit_decisions,
        production_proposal=production_proposal,
    )
    pp = review["checks"]["promise_preservation"]
    assert pp.get("runtime_swap_detected") is True
    assert "production_proposal.render_runtime" in pp["runtime_swap_check"]


@pytest.mark.integration
@pytest.mark.ffmpeg
def test_final_review_honors_approved_runtime_decision_log_swap(tmp_path):
    import subprocess

    mp4 = tmp_path / "tiny.mp4"
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", "color=c=#000000:s=320x240:d=2",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            "-shortest", str(mp4),
        ],
        capture_output=True, check=True, timeout=30,
    )

    review = VideoCompose()._run_final_review(
        mp4,
        {
            "version": "1.0",
            "render_runtime": "hyperframes",
            "renderer_family": "product-reveal",
            "cuts": [{"id": "c1", "source": "x", "in_seconds": 0, "out_seconds": 2}],
        },
        production_proposal={"render_runtime": "remotion"},
        decision_log={
            "version": "1.0",
            "project_id": "approved-runtime-swap",
            "decisions": [
                {
                    "decision_id": "d-runtime-swap",
                    "stage": "compose",
                    "category": "render_runtime_selection",
                    "subject": "composition runtime",
                    "user_visible": True,
                    "user_approved": True,
                    "options_considered": [
                        {
                            "option_id": "remotion",
                            "label": "Remotion",
                            "score": 0.4,
                            "reason": "Original approved runtime",
                        },
                        {
                            "option_id": "hyperframes",
                            "label": "HyperFrames",
                            "score": 0.8,
                            "reason": "Approved fallback for the blocked runtime",
                        },
                    ],
                    "selected": "hyperframes",
                    "reason": "User approved rerouting before compose.",
                }
            ],
        },
    )

    pp = review["checks"]["promise_preservation"]
    assert pp["render_runtime_used"] == "hyperframes"
    assert pp["runtime_swap_detected"] is False
    assert "decision_log.render_runtime_selection" in pp["runtime_swap_check"]
    assert not any("render_runtime changed" in i for i in pp.get("issues", []))
    assert review["status"] == "pass"


@pytest.mark.integration
@pytest.mark.ffmpeg
def test_runtime_swap_detected_flips_when_brief_metadata_disagrees(tmp_path):
    import subprocess

    mp4 = tmp_path / "tiny.mp4"
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", "color=c=#000000:s=320x240:d=2",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            "-shortest", str(mp4),
        ],
        capture_output=True, check=True, timeout=30,
    )

    edit_decisions = {
        "version": "1.0",
        "render_runtime": "ffmpeg",
        "renderer_family": "screen-demo",
        "cuts": [{"id": "c1", "source": "x", "in_seconds": 0, "out_seconds": 2}],
    }
    brief = {"metadata": {"render_runtime": "remotion"}}

    review = VideoCompose()._run_final_review(mp4, edit_decisions, brief=brief)
    pp = review["checks"]["promise_preservation"]
    assert pp.get("runtime_swap_detected") is True
    assert "brief.metadata.render_runtime" in pp["runtime_swap_check"]


@pytest.mark.integration
@pytest.mark.ffmpeg
def test_brief_runtime_lock_prefers_direct_metadata_over_legacy_nested_plan(tmp_path):
    import subprocess

    mp4 = tmp_path / "tiny.mp4"
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", "color=c=#000000:s=320x240:d=2",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            "-shortest", str(mp4),
        ],
        capture_output=True, check=True, timeout=30,
    )

    review = VideoCompose()._run_final_review(
        mp4,
        {
            "version": "1.0",
            "render_runtime": "ffmpeg",
            "renderer_family": "screen-demo",
            "cuts": [{"id": "c1", "source": "x", "in_seconds": 0, "out_seconds": 2}],
        },
        brief={
            "metadata": {
                "render_runtime": "remotion",
                "production_plan": {"render_runtime": "ffmpeg"},
            },
        },
    )

    pp = review["checks"]["promise_preservation"]
    assert pp.get("runtime_swap_detected") is True
    assert "brief.metadata.render_runtime" in pp["runtime_swap_check"]
    assert "brief.metadata.production_plan.render_runtime" not in pp["runtime_swap_check"]


@pytest.mark.integration
@pytest.mark.ffmpeg
def test_final_review_revises_when_brief_runtime_lock_missing(tmp_path):
    import subprocess

    mp4 = tmp_path / "tiny.mp4"
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", "color=c=#000000:s=320x240:d=2",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            "-shortest", str(mp4),
        ],
        capture_output=True, check=True, timeout=30,
    )

    review = VideoCompose()._run_final_review(
        mp4,
        {
            "version": "1.0",
            "render_runtime": "ffmpeg",
            "renderer_family": "screen-demo",
            "cuts": [{"id": "c1", "source": "x", "in_seconds": 0, "out_seconds": 2}],
        },
        brief={"version": "1.0", "metadata": {}},
    )

    pp = review["checks"]["promise_preservation"]
    assert pp["runtime_swap_check"].startswith("missing")
    assert any("render_runtime lock missing" in i for i in pp["issues"])
    assert review["status"] == "revise"


@pytest.mark.integration
@pytest.mark.ffmpeg
def test_runtime_swap_detected_stays_false_when_proposal_matches(tmp_path):
    import subprocess

    mp4 = tmp_path / "tiny.mp4"
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", "color=c=#000000:s=320x240:d=2",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            "-shortest", str(mp4),
        ],
        capture_output=True, check=True, timeout=30,
    )
    edit_decisions = {
        "version": "1.0",
        "render_runtime": "remotion",
        "cuts": [{"id": "c1", "source": "x", "in_seconds": 0, "out_seconds": 2}],
    }
    proposal_packet = {"production_plan": {"render_runtime": "remotion"}}
    review = VideoCompose()._run_final_review(
        mp4, edit_decisions, proposal_packet
    )
    pp = review["checks"]["promise_preservation"]
    assert pp.get("runtime_swap_detected", False) is False
    assert "ok" in pp["runtime_swap_check"]


def test_both_runtimes_visible_in_render_engines_when_available():
    """Regression for the 'silently picks Remotion' failure mode.

    A fresh-session agent decides which runtime to present based on
    `video_compose.get_info()["render_engines"]`. That dict MUST expose
    BOTH remotion and hyperframes as separate boolean entries — not
    collapse them under one 'composition' key or hide hyperframes behind
    a remotion-specific note. If this test fails on a machine where both
    should be available, the agent's runtime discovery is broken and it
    will likely silently default to Remotion.
    """
    info = VideoCompose().get_info()
    engines = info["render_engines"]
    # Both entries must exist as keys regardless of availability.
    assert "remotion" in engines, (
        "render_engines dict is missing 'remotion' — agents won't see it as "
        "an option."
    )
    assert "hyperframes" in engines, (
        "render_engines dict is missing 'hyperframes' — agents won't see it "
        "as an option and will silently default to Remotion."
    )
    assert "ffmpeg" in engines
    # Both notes must exist independently so onboarding can surface both.
    assert "remotion_note" in info
    assert "hyperframes_note" in info
    # Governance note must be present — this is what reminds the agent
    # not to silently pick a default.
    assert "runtime_governance" in info
    assert "silent" in info["runtime_governance"].lower()


def test_video_compose_remotion_components_info_is_snapshot(monkeypatch):
    monkeypatch.setattr(VideoCompose, "_remotion_available", lambda self: True)
    monkeypatch.setattr(VideoCompose, "_hyperframes_available", lambda self: False)

    tool = VideoCompose()
    original_components = list(tool._REMOTION_COMPONENTS)
    info = tool.get_info()

    info["remotion_components"].append("leaked_component")

    assert tool._REMOTION_COMPONENTS == original_components


def test_video_compose_render_runtime_aliases_are_independent(monkeypatch):
    monkeypatch.setattr(VideoCompose, "_remotion_available", lambda self: True)
    monkeypatch.setattr(VideoCompose, "_hyperframes_available", lambda self: False)

    info = VideoCompose().get_info()
    info["render_runtimes"]["remotion"] = False

    assert info["render_engines"]["remotion"] is True


def _valid_runtime_decision(options: list[dict]) -> dict:
    """Build a minimal schema-valid decision_log entry with given options."""
    return {
        "decision_id": "d-runtime-1",
        "stage": "proposal",
        "category": "render_runtime_selection",
        "subject": "composition runtime",
        "options_considered": options,
        "selected": options[0]["option_id"],
        "reason": "fit-for-brief",
    }


def test_decision_log_accepts_render_runtime_selection_with_both_options():
    """Schema-level: a decision_log with BOTH runtimes in options_considered
    must validate. This is the contract the reviewer enforces."""
    import json
    from pathlib import Path
    try:
        import jsonschema
    except ImportError:  # pragma: no cover
        pytest.skip("jsonschema not installed")

    root = Path(__file__).resolve().parent.parent.parent
    schema = json.loads(
        (root / "schemas" / "artifacts" / "decision_log.schema.json").read_text(
            encoding="utf-8"
        )
    )

    log = {
        "version": "1.0",
        "project_id": "p-test",
        "decisions": [
            _valid_runtime_decision(
                [
                    {
                        "option_id": "remotion",
                        "label": "Remotion",
                        "score": 0.6,
                        "reason": "existing React scene stack fits",
                    },
                    {
                        "option_id": "hyperframes",
                        "label": "HyperFrames",
                        "score": 0.4,
                        "reason": "GSAP motion is natural but caption parity deferred",
                    },
                ]
            )
        ],
    }
    # No raise = valid.
    jsonschema.validate(log, schema)


def test_brief_schema_requires_metadata_render_runtime():
    from copy import deepcopy

    from schemas.artifacts import validate_artifact

    brief = {
        "version": "1.0",
        "title": "Brief Runtime Lock",
        "hook": "Show the workflow clearly.",
        "key_points": ["Point"],
        "tone": "direct",
        "style": "clean-professional",
        "target_platform": "youtube",
        "target_duration_seconds": 30,
        "metadata": {"render_runtime": "remotion"},
    }

    validate_artifact("brief", brief)

    missing = deepcopy(brief)
    del missing["metadata"]["render_runtime"]
    with pytest.raises(Exception, match="render_runtime"):
        validate_artifact("brief", missing)


def test_transcript_comparison_catches_literal_punctuation_leak(tmp_path):
    """Regression: Chirp3-HD (and some other TTS engines) read literal `...`
    as the word 'dot' in audio output. This failure is invisible to
    volume-based audio spotchecks but ships audio that literally says
    'dot dot dot' twelve times. The transcript_comparison check catches
    this automatically before the video is marked pass."""
    import json

    # Real-world example: user's script had `...` everywhere for dramatic
    # pause, Chirp read them all as "dot", transcript contains "dot dot dot"
    # phrases the script never had.
    script_text = (
        "A computer just did in five minutes what would take every machine on Earth, "
        "running since the Big Bang, ten septillion years to finish. "
        "We may have gotten help from parallel universes."
    )
    transcript_data = {
        "word_timestamps": [
            {"word": "A", "start": 0.0, "end": 0.1},
            {"word": "computer", "start": 0.1, "end": 0.5},
            {"word": "just", "start": 0.5, "end": 0.7},
            {"word": "did", "start": 0.7, "end": 0.9},
            {"word": "in", "start": 0.9, "end": 1.0},
            {"word": "five", "start": 1.0, "end": 1.3},
            {"word": "minutes", "start": 1.3, "end": 1.7},
            {"word": "dot", "start": 1.7, "end": 1.9},    # leak!
            {"word": "dot", "start": 1.9, "end": 2.1},    # leak!
            {"word": "dot", "start": 2.1, "end": 2.3},    # leak!
            {"word": "what", "start": 2.5, "end": 2.8},
            {"word": "would", "start": 2.8, "end": 3.0},
            {"word": "take", "start": 3.0, "end": 3.3},
            {"word": "every", "start": 3.3, "end": 3.6},
            {"word": "machine", "start": 3.6, "end": 4.0},
            {"word": "on", "start": 4.0, "end": 4.2},
            {"word": "Earth", "start": 4.2, "end": 4.6},
            {"word": "running", "start": 4.7, "end": 5.1},
            {"word": "since", "start": 5.1, "end": 5.4},
            {"word": "the", "start": 5.4, "end": 5.5},
            {"word": "Big", "start": 5.5, "end": 5.8},
            {"word": "Bang", "start": 5.8, "end": 6.2},
            {"word": "ten", "start": 6.2, "end": 6.5},
            {"word": "septillion", "start": 6.5, "end": 7.3},
            {"word": "years", "start": 7.3, "end": 7.7},
            {"word": "to", "start": 7.7, "end": 7.9},
            {"word": "finish", "start": 7.9, "end": 8.3},
            {"word": "dot", "start": 8.3, "end": 8.5},    # another leak
            {"word": "We", "start": 9.0, "end": 9.2},
            {"word": "may", "start": 9.2, "end": 9.4},
            {"word": "have", "start": 9.4, "end": 9.6},
            {"word": "gotten", "start": 9.6, "end": 9.9},
            {"word": "help", "start": 9.9, "end": 10.3},
            {"word": "from", "start": 10.3, "end": 10.5},
            {"word": "parallel", "start": 10.5, "end": 11.0},
            {"word": "universes", "start": 11.0, "end": 11.7},
        ]
    }
    transcript_path = tmp_path / "transcript.json"
    transcript_path.write_text(json.dumps(transcript_data), encoding="utf-8")

    result = VideoCompose._compare_transcript_to_script(transcript_path, script_text)

    # Must catch the punctuation leak
    assert result["spurious_punctuation_words"], (
        "transcript_comparison failed to detect the 'dot' leak from literal ... punctuation."
    )
    leak_counts = {
        entry["word"]: entry["count"]
        for entry in result["spurious_punctuation_words"]
    }
    assert leak_counts.get("dot") == 4, f"Expected 4 'dot' leaks, got {leak_counts}"

    # Must produce a CRITICAL-severity issue message
    issue_text = " ".join(result["issues"]).lower()
    assert "tts punctuation leak" in issue_text
    assert "not in the script" in issue_text

    # Must NOT mark the transcript as matching
    assert result["transcript_matches_script"] is False


def test_transcript_comparison_passes_clean_audio(tmp_path):
    """Clean audio with no punctuation leaks must NOT trigger a false
    positive."""
    import json

    script_text = "The quick brown fox jumps over the lazy dog."
    transcript_data = {
        "word_timestamps": [
            {"word": "The", "start": 0.0, "end": 0.1},
            {"word": "quick", "start": 0.1, "end": 0.4},
            {"word": "brown", "start": 0.4, "end": 0.7},
            {"word": "fox", "start": 0.7, "end": 1.0},
            {"word": "jumps", "start": 1.0, "end": 1.3},
            {"word": "over", "start": 1.3, "end": 1.6},
            {"word": "the", "start": 1.6, "end": 1.7},
            {"word": "lazy", "start": 1.7, "end": 2.0},
            {"word": "dog", "start": 2.0, "end": 2.3},
        ]
    }
    transcript_path = tmp_path / "transcript.json"
    transcript_path.write_text(json.dumps(transcript_data), encoding="utf-8")

    result = VideoCompose._compare_transcript_to_script(transcript_path, script_text)
    assert result["spurious_punctuation_words"] == []
    assert result["transcript_matches_script"] is True
    assert result["word_accuracy"] >= 0.9
    # issues may still have informational content but no CRITICAL TTS leak
    assert not any("tts punctuation leak" in i.lower() for i in result["issues"])


def test_transcript_comparison_rejects_non_strict_transcript_json(tmp_path):
    transcript_path = tmp_path / "transcript.json"
    transcript_path.write_text(
        '{"word_timestamps":[{"word":NaN,"start":0.0,"end":0.1}]}\n',
        encoding="utf-8",
    )

    try:
        result = VideoCompose._compare_transcript_to_script(transcript_path, "hello")
    except Exception as exc:  # pragma: no cover - this is the regression symptom.
        pytest.fail(
            "transcript_comparison should report a parse issue instead of "
            f"raising {type(exc).__name__}: {exc}"
        )

    assert result["transcript_matches_script"] is False
    assert any(
        "could not parse transcript" in issue and "strict JSON" in issue
        for issue in result["issues"]
    )


def test_transcript_comparison_graceful_when_inputs_missing(tmp_path):
    """When transcript or script is unavailable, the check should NOT
    crash — it should record the skip in issues so the silence is visible."""
    # No transcript
    result = VideoCompose._compare_transcript_to_script(None, "some script text")
    assert any("not provided" in i for i in result["issues"])

    # No script
    dummy = tmp_path / "t.json"
    dummy.write_text('{"word_timestamps": []}', encoding="utf-8")
    result = VideoCompose._compare_transcript_to_script(dummy, "")
    assert any("not provided" in i for i in result["issues"])

    # Transcript file missing
    result = VideoCompose._compare_transcript_to_script(tmp_path / "nonexistent.json", "script")
    assert any("not provided" in i for i in result["issues"])


@pytest.mark.integration
@pytest.mark.ffmpeg
def test_run_final_review_includes_transcript_comparison_section(tmp_path):
    """Regression: the `transcript_comparison` section must ALWAYS appear in
    the final_review output — even when the caller doesn't provide a
    transcript. A missing section = silent governance failure."""
    import subprocess
    from schemas.artifacts import validate_artifact

    # Build a minimal MP4 so _run_final_review can probe it.
    mp4 = tmp_path / "out.mp4"
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", "color=c=#000000:s=320x240:d=2",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-shortest", str(mp4),
        ],
        capture_output=True, check=True, timeout=30,
    )

    review = VideoCompose()._run_final_review(
        mp4,
        edit_decisions={
            "version": "1.0",
            "renderer_family": "animation-first",
            "render_runtime": "hyperframes",
            "cuts": [{"id": "c1", "source": "x", "in_seconds": 0, "out_seconds": 2}],
        },
    )
    assert "transcript_comparison" in review["checks"], (
        "final_review must always include a transcript_comparison section. "
        "When the caller doesn't provide a transcript, the section should "
        "still appear with a 'skipped' issue entry — not be omitted."
    )
    tc = review["checks"]["transcript_comparison"]
    assert any("not provided" in i for i in tc["issues"])
    validate_artifact("final_review", review)


@pytest.mark.integration
@pytest.mark.ffmpeg
def test_run_final_review_payload_validates_for_ad_video_context(tmp_path):
    import subprocess
    from schemas.artifacts import validate_artifact

    mp4 = tmp_path / "ad-video-review.mp4"
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", "testsrc=size=640x360:rate=30:duration=2",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-shortest", str(mp4),
        ],
        capture_output=True, check=True, timeout=30,
    )

    review = VideoCompose()._run_final_review(
        mp4,
        edit_decisions={
            "version": "1.0",
            "renderer_family": "product-reveal",
            "render_runtime": "ffmpeg",
            "metadata": {
                "proposal_render_runtime": "ffmpeg",
                "delivery_promise": {
                    "promise_type": "source_led",
                    "motion_required": False,
                    "source_required": False,
                    "tone_mode": "corporate",
                    "quality_floor": "presentable",
                },
            },
            "subtitles": {"enabled": False},
            "cuts": [
                {
                    "id": "c1",
                    "source": str(mp4),
                    "in_seconds": 0,
                    "out_seconds": 2,
                }
            ],
        },
    )

    assert review["status"] == "pass"
    assert review["issues_found"] == []
    assert review["checks"]["subtitle_check"] == {
        "subtitles_expected": False,
        "subtitles_present": False,
        "coverage_ratio": 0.0,
        "timing_drift_detected": False,
        "issues": [],
    }
    assert any(
        "transcript_comparison skipped" in issue
        for issue in review["checks"]["transcript_comparison"]["issues"]
    )
    validate_artifact(
        "final_review",
        review,
        pipeline_type="ad-video",
        related_artifacts={
            "production_proposal": {
                "subtitles": {"mode": "off"},
                "music_strategy": "generative_loose",
            },
        },
    )


@pytest.mark.integration
@pytest.mark.ffmpeg
def test_run_final_review_does_not_mark_narration_as_music_when_strategy_none(tmp_path):
    import subprocess

    mp4 = tmp_path / "ad-video-no-music.mp4"
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", "testsrc=size=640x360:rate=30:duration=2",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-shortest", str(mp4),
        ],
        capture_output=True, check=True, timeout=30,
    )

    review = VideoCompose()._run_final_review(
        mp4,
        edit_decisions={
            "version": "1.0",
            "renderer_family": "product-reveal",
            "render_runtime": "ffmpeg",
            "music_strategy": "none",
            "metadata": {"proposal_render_runtime": "ffmpeg"},
            "subtitles": {"enabled": False},
            "cuts": [
                {
                    "id": "c1",
                    "source": str(mp4),
                    "in_seconds": 0,
                    "out_seconds": 2,
                }
            ],
        },
    )

    assert review["checks"]["audio_spotcheck"]["narration_present"] is True
    assert review["checks"]["audio_spotcheck"]["music_present"] is False


@pytest.mark.integration
@pytest.mark.ffmpeg
def test_run_final_review_validates_without_delivery_promise_metadata(tmp_path):
    import subprocess
    from schemas.artifacts import validate_artifact

    mp4 = tmp_path / "ad-video-no-promise.mp4"
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", "testsrc=size=640x360:rate=30:duration=2",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-shortest", str(mp4),
        ],
        capture_output=True, check=True, timeout=30,
    )

    review = VideoCompose()._run_final_review(
        mp4,
        edit_decisions={
            "version": "1.0",
            "renderer_family": "product-reveal",
            "render_runtime": "ffmpeg",
            "metadata": {"proposal_render_runtime": "ffmpeg"},
            "subtitles": {"enabled": False},
            "cuts": [
                {
                    "id": "c1",
                    "source": str(mp4),
                    "in_seconds": 0,
                    "out_seconds": 2,
                }
            ],
        },
    )

    assert review["status"] == "pass"
    assert "motion_ratio_actual" not in review["checks"]["promise_preservation"]
    validate_artifact("final_review", review, pipeline_type="ad-video")


@pytest.mark.integration
@pytest.mark.ffmpeg
def test_final_review_flags_audio_truncation_as_rerender_issue(tmp_path):
    import subprocess

    mp4 = tmp_path / "truncated-audio.mp4"
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", "color=c=#000000:s=320x240:d=4",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-c:a", "aac", str(mp4),
        ],
        capture_output=True, check=True, timeout=30,
    )

    review = VideoCompose()._run_final_review(
        mp4,
        edit_decisions={
            "version": "1.0",
            "total_duration_seconds": 4.0,
            "render_runtime": "remotion",
            "cuts": [{"id": "c1", "source": "x", "in_seconds": 0, "out_seconds": 4}],
        },
    )

    technical_probe = review["checks"]["technical_probe"]
    assert "audio_truncation_check" in technical_probe
    assert any("Audio truncation" in issue for issue in review["issues_found"])
    assert review["status"] == "revise"
    assert review["recommended_action"] == "re_render"


def test_hyperframes_root_composition_has_data_start_and_duration(tmp_path):
    """Regression: the generated root composition was missing data-start
    and data-duration, violating the HyperFrames contract (SKILL.md table)."""
    asset = tmp_path / "hero.png"
    asset.write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 512)
    workspace = tmp_path / "hyperframes"
    result = HyperFramesCompose().execute(
        {
            "operation": "scaffold_workspace",
            "workspace_path": str(workspace),
            "edit_decisions": {
                "version": "1.0",
                "render_runtime": "hyperframes",
                "renderer_family": "animation-first",
                "cuts": [
                    {
                        "id": "c1",
                        "source": "a1",
                        "in_seconds": 0,
                        "out_seconds": 5,
                        "type": "image",
                    }
                ],
            },
            "asset_manifest": {"assets": [{"id": "a1", "path": str(asset)}]},
        }
    )
    assert result.success, result.error
    html = (workspace / "index.html").read_text(encoding="utf-8")
    # Must have all four required root attributes per the HyperFrames contract.
    assert 'data-composition-id="root"' in html
    assert 'data-start="0"' in html  # per SKILL.md: root composition: use "0"
    # data-duration must match the timeline total; value can be '5' or '5.0' etc.
    import re
    m = re.search(r'data-duration="([^"]+)"', html)
    assert m, "root composition missing data-duration"
    assert float(m.group(1)) == pytest.approx(5.0)
    assert 'data-width="1920"' in html
    assert 'data-height="1080"' in html


def test_video_compose_blocks_hyperframes_when_runtime_unavailable(
    monkeypatch,
    project_renders_dir,
):
    """Governance: if render_runtime='hyperframes' is locked but runtime is
    missing, the tool must NOT silently substitute another engine."""

    # Force HyperFrames availability to False regardless of the machine state.
    monkeypatch.setattr(
        VideoCompose, "_hyperframes_available", lambda self: False, raising=True
    )

    result = VideoCompose().execute(
        {
            "operation": "render",
            "edit_decisions": {
                "version": "1.0",
                "cuts": [
                    {
                        "id": "c1",
                        "source": "a1",
                        "in_seconds": 0,
                        "out_seconds": 3,
                    }
                ],
                "render_runtime": "hyperframes",
                "renderer_family": "animation-first",
            },
            "asset_manifest": {"assets": [{"id": "a1", "path": "does-not-matter.png"}]},
            "output_path": str(project_renders_dir / "out.mp4"),
        }
    )
    assert not result.success
    err = (result.error or "").lower()
    assert "hyperframes" in err
    assert "blocker" in err or "not available" in err


# ------------------------------------------------------------------
# Scaffold / workspace generation (no CLI invocation)
# ------------------------------------------------------------------


def test_scaffold_workspace_generates_html_and_assets(tmp_path: Path):
    # Build a minimal asset manifest + edit decisions referencing a real
    # file so the staging copy has something to move.
    asset = tmp_path / "hero.png"
    asset.write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 1024)

    workspace = tmp_path / "hyperframes"
    edit_decisions: dict[str, Any] = {
        "version": "1.0",
        "renderer_family": "animation-first",
        "render_runtime": "hyperframes",
        "cuts": [
            {
                "id": "c1",
                "source": "asset_hero",
                "in_seconds": 0,
                "out_seconds": 3,
                "type": "image",
            },
            {
                "id": "c2",
                "source": "",
                "in_seconds": 3,
                "out_seconds": 6,
                "type": "text_card",
                "text": "Hello HyperFrames",
            },
        ],
    }
    asset_manifest = {
        "assets": [{"id": "asset_hero", "path": str(asset)}],
    }

    result = HyperFramesCompose().execute(
        {
            "operation": "scaffold_workspace",
            "workspace_path": str(workspace),
            "edit_decisions": edit_decisions,
            "asset_manifest": asset_manifest,
            "playbook": {
                "name": "test-playbook",
                "visual_language": {
                    "color_palette": {
                        "background": "#0B0F1A",
                        "text": "#F5F5F5",
                        "accent": "#F59E0B",
                    }
                },
                "typography": {
                    "heading": {"font": "Inter"},
                    "body": {"font": "Inter"},
                },
            },
        }
    )

    assert result.success, result.error
    index = workspace / "index.html"
    assert index.is_file()
    html = index.read_text(encoding="utf-8")

    # HyperFrames authoring contract requirements we MUST emit:
    assert 'data-composition-id="root"' in html
    assert '<div id="root" data-composition-id="root"' in html
    assert "#root {" in html
    assert '[data-composition-id="root"] {' not in html
    assert 'window.__timelines["root"]' in html
    assert "tl.from(" not in html
    assert 'paused: true' in html
    assert "timeScale: function" in html
    assert "totalDuration: function" in html
    assert "totalTime: function" in html
    assert "getChildren: function" in html
    assert "paused: function" in html
    assert 'class="clip' in html
    assert "gsap" in html.lower()
    assert "https://cdn.jsdelivr.net" not in html

    # Text card for c2 must carry data-start and data-duration.
    assert 'data-start="3"' in html
    assert 'Hello HyperFrames' in html

    # Image asset was staged into the workspace.
    staged = workspace / "assets" / "hero.png"
    assert staged.is_file()
    # And index.html references it via a relative path.
    assert "assets/hero.png" in html

    # hyperframes.json registry config was written.
    hf_json = workspace / "hyperframes.json"
    assert hf_json.is_file()
    config = json.loads(hf_json.read_text(encoding="utf-8"))
    assert config["paths"]["blocks"] == "compositions"

    # DESIGN.md was written from the playbook.
    design = workspace / "DESIGN.md"
    assert design.is_file()
    design_text = design.read_text(encoding="utf-8")
    assert "#0B0F1A" in design_text or "test-playbook" in design_text


def test_scaffold_rejects_empty_cuts(tmp_path: Path):
    result = HyperFramesCompose().execute(
        {
            "operation": "scaffold_workspace",
            "workspace_path": str(tmp_path / "hyperframes"),
            "edit_decisions": {"version": "1.0", "cuts": []},
            "asset_manifest": {"assets": []},
        }
    )
    assert not result.success
    assert "cuts" in (result.error or "").lower()


# ------------------------------------------------------------------
# Style bridge
# ------------------------------------------------------------------


def test_style_bridge_fallback_has_all_required_vars():
    from lib.hyperframes_style_bridge import style_bridge

    css, design = style_bridge(None, None)
    for key in (
        "--color-bg",
        "--color-fg",
        "--color-accent",
        "--color-primary",
        "--font-heading",
        "--font-body",
        "--ease-primary",
        "--duration-entrance",
    ):
        assert key in css, f"missing CSS var: {key}"
    assert "# DESIGN" in design


def test_style_bridge_picks_up_playbook_palette():
    from lib.hyperframes_style_bridge import style_bridge

    playbook = {
        "identity": {
            "name": "Neon Test",
            "pace": "fast",
        },
        "visual_language": {
            "color_palette": {
                "background": "#000000",
                "text": "#FFFFFF",
                "muted": "#999999",
                "accent": ["#FF00FF", "#FF66FF"],
                "primary": "#00FFFF",
            }
        },
        "typography": {
            "headings": {"font": "Space Grotesk"},
            "body": {"font": "Inter"},
        },
        "motion": {
            "pacing_rules": {"transition_duration_seconds": 0.25},
        },
        "chart_palette": ["#111111", "#222222", "#333333"],
    }
    css, design = style_bridge(playbook, None)
    assert css["--color-bg"] == "#000000"
    assert css["--color-accent"] == "#FF00FF"  # list → first
    assert css["--color-primary"] == "#00FFFF"
    assert css["--color-secondary"] == "#FF66FF"
    assert css["--color-muted"] == "#999999"
    assert css["--font-heading"] == "Space Grotesk"
    assert css["--chart-color-1"] == "#111111"
    assert css["--chart-color-3"] == "#333333"
    # Fast pace → shorter entrance duration.
    assert css["--duration-entrance"] == "0.25s"
    assert "Neon Test" in design


def test_style_bridge_edit_decision_override_wins():
    from lib.hyperframes_style_bridge import style_bridge

    playbook = {
        "visual_language": {"color_palette": {"background": "#111", "text": "#eee"}},
    }
    edit = {"metadata": {"background_color": "#fff", "accent_color": "#09f"}}
    css, _ = style_bridge(playbook, edit)
    assert css["--color-bg"] == "#fff"
    assert css["--color-accent"] == "#09f"


# ------------------------------------------------------------------
# Schema acceptance for render_runtime
# ------------------------------------------------------------------


def test_proposal_packet_schema_accepts_render_runtime():
    schema_path = (
        Path(__file__).resolve().parent.parent.parent
        / "schemas"
        / "artifacts"
        / "proposal_packet.schema.json"
    )
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    props = schema["properties"]["production_plan"]["properties"]
    assert "render_runtime" in props
    assert "renderer_family" in props
    assert props["render_runtime"]["enum"] == ["remotion", "hyperframes", "ffmpeg"]


def test_edit_decisions_schema_accepts_render_runtime():
    schema_path = (
        Path(__file__).resolve().parent.parent.parent
        / "schemas"
        / "artifacts"
        / "edit_decisions.schema.json"
    )
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    assert "render_runtime" in schema["properties"]
    assert schema["properties"]["render_runtime"]["enum"] == [
        "remotion",
        "hyperframes",
        "ffmpeg",
    ]


def test_final_review_tracks_runtime_and_swap():
    schema_path = (
        Path(__file__).resolve().parent.parent.parent
        / "schemas"
        / "artifacts"
        / "final_review.schema.json"
    )
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    pp = schema["properties"]["checks"]["properties"]["promise_preservation"][
        "properties"
    ]
    assert "render_runtime_used" in pp
    assert "runtime_swap_detected" in pp


def test_decision_log_has_render_runtime_category():
    schema_path = (
        Path(__file__).resolve().parent.parent.parent
        / "schemas"
        / "artifacts"
        / "decision_log.schema.json"
    )
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    category_enum = schema["properties"]["decisions"]["items"]["properties"][
        "category"
    ]["enum"]
    assert "render_runtime_selection" in category_enum


# ------------------------------------------------------------------
# Slideshow risk runtime threading
# ------------------------------------------------------------------


def test_slideshow_risk_accepts_render_runtime():
    from lib.slideshow_risk import score_slideshow_risk

    scenes = [
        {
            "type": "image",
            "description": "Opening shot of city",
            "shot_language": {"shot_size": "wide"},
            "shot_intent": "establish",
        },
        {
            "type": "text_card",
            "description": "Title overlay",
            "shot_language": {"shot_size": "medium"},
            "shot_intent": "announce",
        },
    ]
    out = score_slideshow_risk(scenes, render_runtime="hyperframes")
    assert out["render_runtime"] == "hyperframes"
    assert out["verdict"] in {"strong", "acceptable", "revise", "fail"}


# ------------------------------------------------------------------
# Composition validator runtime awareness
# ------------------------------------------------------------------


def test_composition_validator_hyperframes_asset_root(tmp_path: Path):
    """With render_runtime='hyperframes', the validator should look for
    assets next to index.html, not under remotion-composer/public."""
    from tools.analysis.composition_validator import CompositionValidator

    # Set up a fake HyperFrames workspace: hyperframes/ with index.html +
    # assets/. Composition JSON lives a sibling directory away.
    workspace = tmp_path / "hyperframes"
    (workspace / "assets").mkdir(parents=True)
    (workspace / "index.html").write_text("<!-- stub -->", encoding="utf-8")
    asset = workspace / "assets" / "hero.png"
    asset.write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 10)

    artifacts_dir = tmp_path / "artifacts"
    artifacts_dir.mkdir()
    comp_json = artifacts_dir / "comp.json"
    comp_json.write_text(
        json.dumps(
            {
                "render_runtime": "hyperframes",
                "cuts": [
                    {
                        "id": "c1",
                        "source": "hero.png",
                        "in_seconds": 0,
                        "out_seconds": 3,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    result = CompositionValidator().execute({"composition_path": str(comp_json)})
    # Asset exists in workspace/assets/ — should resolve without errors.
    assert result.success, result.error
    info_lines = " ".join(result.data.get("info", []))
    assert "hyperframes" in info_lines.lower() or "assets" in info_lines.lower()
