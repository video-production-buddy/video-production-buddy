"""Tests for Remotion render debuggability in video_compose (issue #217).

Two creator-facing gaps:
  1. A failed `npx remotion render` surfaced only "returned non-zero exit
     status 1"; the useful Remotion diagnostics in stderr were dropped.
  2. There was no pass-through for Remotion's `--timeout`, so a slow headless
     browser setup failed opaquely with no way to raise the limit.
"""

import subprocess
import sys
import shutil
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from tools.video.video_compose import VideoCompose  # noqa: E402


@pytest.fixture
def tool(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda _: "/usr/bin/npx")
    return VideoCompose()


@pytest.fixture
def project_renders_dir(tmp_path):
    repo_root = Path(__file__).resolve().parents[2]
    project_dir = repo_root / "projects" / f"pytest-remotion-diagnostics-{tmp_path.name}"
    shutil.rmtree(project_dir, ignore_errors=True)
    renders_dir = project_dir / "renders"
    yield renders_dir
    shutil.rmtree(project_dir, ignore_errors=True)


def test_render_failure_surfaces_remotion_stderr_tail(tool, project_renders_dir, monkeypatch):
    stderr = "some npm noise\nError: Delayed render timed out\nRemotion actual cause here"

    def fake_run_command(cmd, *a, **k):
        raise subprocess.CalledProcessError(returncode=1, cmd=cmd, output="", stderr=stderr)

    monkeypatch.setattr(tool, "run_command", fake_run_command)
    result = tool._remotion_render(
        {"composition_data": {"cuts": []}, "output_path": str(project_renders_dir / "out.mp4")}
    )

    assert result.success is False
    assert "exit 1" in result.error
    assert "Remotion actual cause here" in result.error


def test_timeout_expired_gives_actionable_message(tool, project_renders_dir, monkeypatch):
    def fake_run_command(cmd, *a, **k):
        raise subprocess.TimeoutExpired(cmd=cmd, timeout=600)

    monkeypatch.setattr(tool, "run_command", fake_run_command)
    result = tool._remotion_render(
        {"composition_data": {"cuts": []}, "output_path": str(project_renders_dir / "out.mp4")}
    )

    assert result.success is False
    assert "timed out" in result.error.lower()
    assert "remotion_timeout_ms" in result.error


def test_remotion_timeout_ms_is_passed_through(tool, project_renders_dir, monkeypatch):
    seen = {}

    def fake_run_command(cmd, *a, **k):
        seen["cmd"] = cmd
        seen["timeout"] = k.get("timeout")
        return None  # output file intentionally absent

    monkeypatch.setattr(tool, "run_command", fake_run_command)
    tool._remotion_render(
        {
            "composition_data": {"cuts": []},
            "output_path": str(project_renders_dir / "out.mp4"),
            "remotion_timeout_ms": 120000,
        }
    )

    assert "--timeout=120000" in seen["cmd"]
    # subprocess timeout widened past the 120s render budget so run_command
    # does not kill Remotion before its own timeout fires.
    assert seen["timeout"] >= 180


def test_high_level_render_forwards_timeout_to_remotion(tool, project_renders_dir, monkeypatch):
    # The gap in the first cut: execute(operation="render") -> _render() builds a
    # fresh remotion_inputs dict, so the option must be forwarded there, not only
    # on a direct _remotion_render() call.
    captured = {}
    monkeypatch.setattr(tool, "_pre_compose_validation", lambda *a, **k: None)
    monkeypatch.setattr(tool, "_needs_remotion", lambda *a, **k: True)

    def fake_remotion_render(inputs):
        captured.update(inputs)
        from tools.base_tool import ToolResult

        return ToolResult(success=True, data={}, artifacts=[])

    monkeypatch.setattr(tool, "_remotion_render", fake_remotion_render)
    monkeypatch.setattr(tool, "_run_final_review", lambda *a, **k: {})

    tool._render(
        {
            "edit_decisions": {
                "render_runtime": "remotion",
                "renderer_family": "explainer-data",
                "cuts": [{"id": "c1", "source": "a1", "in_seconds": 0, "out_seconds": 2}],
            },
            "asset_manifest": {"assets": [{"id": "a1", "path": "/tmp/a1.mp4"}]},
            "output_path": str(project_renders_dir / "out.mp4"),
            "remotion_timeout_ms": 120000,
        }
    )

    assert captured.get("remotion_timeout_ms") == 120000


def test_no_timeout_flag_when_not_requested(tool, project_renders_dir, monkeypatch):
    seen = {}

    def fake_run_command(cmd, *a, **k):
        seen["cmd"] = cmd
        seen["timeout"] = k.get("timeout")
        return None

    monkeypatch.setattr(tool, "run_command", fake_run_command)
    tool._remotion_render(
        {"composition_data": {"cuts": []}, "output_path": str(project_renders_dir / "out.mp4")}
    )

    assert not any(str(c).startswith("--timeout") for c in seen["cmd"])
    assert seen["timeout"] == 600
