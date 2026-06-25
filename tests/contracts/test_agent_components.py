from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import jsonschema
import pytest
import yaml

from tools.tool_registry import registry


def _write_skill(root: Path, name: str, text: str = "demo skill") -> Path:
    skill_dir = root / name
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(f"# {name}\n\n{text}\n", encoding="utf-8")
    return skill_dir


def _write_manifest(path: Path, body: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


def test_manifest_rejects_duplicate_component_names_and_path_traversal(tmp_path: Path) -> None:
    from lib.agent_components import ComponentError, load_manifest

    manifest = _write_manifest(
        tmp_path / ".agents" / "components.yaml",
        """
version: 1
materialize:
  agents_dir: .agents/skills
  claude_dir: .claude/skills
sources:
  local-a:
    type: local
    root: .agents/local/skills
    components:
      demo:
        kind: skill
        path: demo
  local-b:
    type: local
    root: .agents/local/skills
    components:
      ../owned:
        kind: skill
        path: demo
      demo:
        kind: skill
        path: ../escape
        """,
    )

    with pytest.raises(ComponentError) as exc_info:
        load_manifest(manifest, repo_root=tmp_path)

    message = str(exc_info.value)
    assert "duplicate component name 'demo'" in message
    assert "component name '../owned' must match" in message
    assert "must stay under source root" in message


def test_lock_writes_stable_hashes_for_local_components(tmp_path: Path) -> None:
    from lib.agent_components import ComponentManager

    _write_skill(tmp_path / ".agents" / "local" / "skills", "demo", "lock me")
    manifest = _write_manifest(
        tmp_path / ".agents" / "components.yaml",
        """
version: 1
materialize:
  agents_dir: .agents/skills
  claude_dir: .claude/skills
sources:
  video-production-buddy-local:
    type: local
    root: .agents/local/skills
    components:
      demo:
        kind: skill
        path: demo
""",
    )
    lock_path = tmp_path / ".agents" / "components.lock.json"

    manager = ComponentManager(manifest, lock_path, repo_root=tmp_path)
    lock = manager.write_lock()

    assert lock_path.exists()
    assert lock["lockfileVersion"] == 1
    assert sorted(lock["components"]) == ["demo"]
    entry = lock["components"]["demo"]
    assert entry["type"] == "local"
    assert entry["kind"] == "skill"
    assert entry["sourcePath"] == ".agents/local/skills/demo"
    assert entry["treeSha256"].startswith("sha256:")
    assert entry["files"] == [
        {
            "path": "SKILL.md",
            "mode": "100644",
            "sha256": entry["files"][0]["sha256"],
        }
    ]

    raw = lock_path.read_text(encoding="utf-8")
    assert json.loads(raw) == lock
    assert raw.endswith("\n")


def test_load_lock_rejects_non_strict_json(tmp_path: Path) -> None:
    from lib.agent_components import ComponentError, ComponentManager

    lock_path = tmp_path / ".agents" / "components.lock.json"
    lock_path.parent.mkdir(parents=True)
    lock_path.write_text(
        """
{
  "lockfileVersion": 1,
  "components": {},
  "x-non-finite-sentinel": NaN
}
""".lstrip(),
        encoding="utf-8",
    )
    manager = ComponentManager(
        tmp_path / ".agents" / "components.yaml",
        lock_path,
        repo_root=tmp_path,
    )

    with pytest.raises(ComponentError, match="strict JSON"):
        manager.load_lock()


def test_lock_ignores_python_bytecode_cache_files(tmp_path: Path) -> None:
    from lib.agent_components import ComponentManager

    skill_dir = _write_skill(tmp_path / ".agents" / "local" / "skills", "demo", "lock me")
    cache_dir = skill_dir / "__pycache__"
    cache_dir.mkdir()
    (cache_dir / "demo.cpython-312.pyc").write_bytes(b"bytecode")
    manifest = _write_manifest(
        tmp_path / ".agents" / "components.yaml",
        """
version: 1
materialize:
  agents_dir: .agents/skills
  claude_dir: .claude/skills
sources:
  video-production-buddy-local:
    type: local
    root: .agents/local/skills
    components:
      demo:
        kind: skill
        path: demo
""",
    )

    lock = ComponentManager(manifest, tmp_path / ".agents" / "components.lock.json", repo_root=tmp_path).write_lock()

    assert [item["path"] for item in lock["components"]["demo"]["files"]] == ["SKILL.md"]


def test_lock_normalizes_non_script_files_to_non_executable_mode(tmp_path: Path) -> None:
    from lib.agent_components import ComponentManager

    skill_dir = _write_skill(tmp_path / ".agents" / "local" / "skills", "demo", "lock me")
    (skill_dir / "SKILL.md").chmod(0o755)
    script = skill_dir / "run.sh"
    script.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    script.chmod(0o644)
    manifest = _write_manifest(
        tmp_path / ".agents" / "components.yaml",
        """
version: 1
materialize:
  agents_dir: .agents/skills
  claude_dir: .claude/skills
sources:
  video-production-buddy-local:
    type: local
    root: .agents/local/skills
    components:
      demo:
        kind: skill
        path: demo
""",
    )

    lock = ComponentManager(manifest, tmp_path / ".agents" / "components.lock.json", repo_root=tmp_path).write_lock()
    modes = {item["path"]: item["mode"] for item in lock["components"]["demo"]["files"]}

    assert modes == {"SKILL.md": "100644", "run.sh": "100755"}


def test_install_materializes_agents_and_claude_targets_from_lock(tmp_path: Path) -> None:
    from lib.agent_components import ComponentManager

    _write_skill(tmp_path / ".agents" / "local" / "skills", "demo", "install me")
    manifest = _write_manifest(
        tmp_path / ".agents" / "components.yaml",
        """
version: 1
materialize:
  agents_dir: .agents/skills
  claude_dir: .claude/skills
  default_mode: copy
sources:
  video-production-buddy-local:
    type: local
    root: .agents/local/skills
    components:
      demo:
        kind: skill
        path: demo
""",
    )
    lock_path = tmp_path / ".agents" / "components.lock.json"
    manager = ComponentManager(manifest, lock_path, repo_root=tmp_path)
    manager.write_lock()

    manager.install(names=["demo"], frozen=True, targets=("agents", "claude"), mode="copy")

    agents_skill = tmp_path / ".agents" / "skills" / "demo" / "SKILL.md"
    claude_skill = tmp_path / ".claude" / "skills" / "demo" / "SKILL.md"
    assert agents_skill.read_text(encoding="utf-8") == "# demo\n\ninstall me\n"
    assert claude_skill.read_text(encoding="utf-8") == "# demo\n\ninstall me\n"
    assert (tmp_path / ".agents" / "skills" / ".video-production-buddy-agent-components.json").exists()
    assert (tmp_path / ".claude" / "skills" / ".video-production-buddy-agent-components.json").exists()
    assert manager.verify(frozen=True, offline=True) == []


def test_install_rejects_upstream_materialization_marker(tmp_path: Path) -> None:
    from lib.agent_components import ComponentError, ComponentManager

    _write_skill(tmp_path / ".agents" / "local" / "skills", "demo", "source")
    target = _write_skill(tmp_path / ".agents" / "skills", "demo", "legacy generated target")
    (target.parent / ("." + "open" + "montage-agent-components.json")).write_text(
        '{"generatedBy":"lib.agent_components","markerVersion":1}\n',
        encoding="utf-8",
    )
    manifest = _write_manifest(
        tmp_path / ".agents" / "components.yaml",
        """
version: 1
materialize:
  agents_dir: .agents/skills
  claude_dir: .claude/skills
  default_mode: copy
sources:
  video-production-buddy-local:
    type: local
    root: .agents/local/skills
    components:
      demo:
        kind: skill
        path: demo
""",
    )
    manager = ComponentManager(manifest, tmp_path / ".agents" / "components.lock.json", repo_root=tmp_path)
    manager.write_lock()

    with pytest.raises(ComponentError, match="refusing to replace unmarked materialization target"):
        manager.install(names=["demo"], frozen=True, targets=("agents",), mode="copy")


def test_install_refuses_to_replace_unmarked_nonmatching_target(tmp_path: Path) -> None:
    from lib.agent_components import ComponentError, ComponentManager

    _write_skill(tmp_path / ".agents" / "local" / "skills", "demo", "source")
    _write_skill(tmp_path / ".agents" / "skills", "demo", "user edited target")
    manifest = _write_manifest(
        tmp_path / ".agents" / "components.yaml",
        """
version: 1
materialize:
  agents_dir: .agents/skills
  claude_dir: .claude/skills
  default_mode: copy
sources:
  video-production-buddy-local:
    type: local
    root: .agents/local/skills
    components:
      demo:
        kind: skill
        path: demo
""",
    )
    manager = ComponentManager(manifest, tmp_path / ".agents" / "components.lock.json", repo_root=tmp_path)
    manager.write_lock()

    with pytest.raises(ComponentError) as exc_info:
        manager.install(names=["demo"], frozen=True, targets=("agents",), mode="copy")

    assert "refusing to replace unmarked materialization target" in str(exc_info.value)
    assert (tmp_path / ".agents" / "skills" / "demo" / "SKILL.md").read_text(encoding="utf-8") == (
        "# demo\n\nuser edited target\n"
    )


def test_install_skips_when_local_source_is_already_materialized_target(tmp_path: Path) -> None:
    from lib.agent_components import ComponentManager

    _write_skill(tmp_path / ".agents" / "skills", "demo", "already there")
    manifest = _write_manifest(
        tmp_path / ".agents" / "components.yaml",
        """
version: 1
materialize:
  agents_dir: .agents/skills
  claude_dir: .claude/skills
  default_mode: copy
sources:
  bootstrap:
    type: local
    root: .agents/skills
    components:
      demo:
        kind: skill
        path: demo
""",
    )
    manager = ComponentManager(manifest, tmp_path / ".agents" / "components.lock.json", repo_root=tmp_path)
    manager.write_lock()

    manager.install(names=["demo"], frozen=True, targets=("agents",), mode="copy")

    assert (tmp_path / ".agents" / "skills" / "demo" / "SKILL.md").read_text(encoding="utf-8") == (
        "# demo\n\nalready there\n"
    )


def test_git_source_resolves_ref_and_materializes_sparse_component(tmp_path: Path) -> None:
    from lib.agent_components import ComponentManager

    upstream = tmp_path / "upstream"
    _write_skill(upstream / "skills", "demo", "from git")
    subprocess.run(["git", "init", str(upstream)], check=True, stdout=subprocess.DEVNULL)
    subprocess.run(["git", "-C", str(upstream), "config", "user.email", "test@example.com"], check=True)
    subprocess.run(["git", "-C", str(upstream), "config", "user.name", "Test"], check=True)
    subprocess.run(["git", "-C", str(upstream), "add", "."], check=True)
    subprocess.run(["git", "-C", str(upstream), "commit", "-m", "initial"], check=True, stdout=subprocess.DEVNULL)
    subprocess.run(["git", "-C", str(upstream), "tag", "v1"], check=True)

    manifest = _write_manifest(
        tmp_path / "repo" / ".agents" / "components.yaml",
        f"""
version: 1
materialize:
  agents_dir: .agents/skills
  claude_dir: .claude/skills
  default_mode: copy
sources:
  demo-upstream:
    type: git
    url: file://{upstream}
    ref: v1
    components:
      demo:
        kind: skill
        path: skills/demo
""",
    )
    manager = ComponentManager(
        manifest,
        tmp_path / "repo" / ".agents" / "components.lock.json",
        repo_root=tmp_path / "repo",
        cache_dir=tmp_path / "cache",
    )

    lock = manager.write_lock()
    manager.install(names=["demo"], frozen=True, offline=True, mode="copy")

    entry = lock["components"]["demo"]
    assert entry["type"] == "git"
    assert entry["requestedRef"] == "v1"
    assert entry["resolvedCommit"]
    assert entry["sourcePath"] == "skills/demo"
    assert (tmp_path / "repo" / ".agents" / "skills" / "demo" / "SKILL.md").read_text(encoding="utf-8") == (
        "# demo\n\nfrom git\n"
    )


def test_git_mirror_clone_retries_transient_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from lib.agent_components import ComponentManager

    upstream = tmp_path / "upstream"
    _write_skill(upstream / "skills", "demo", "from retry")
    subprocess.run(["git", "init", str(upstream)], check=True, stdout=subprocess.DEVNULL)
    subprocess.run(["git", "-C", str(upstream), "config", "user.email", "test@example.com"], check=True)
    subprocess.run(["git", "-C", str(upstream), "config", "user.name", "Test"], check=True)
    subprocess.run(["git", "-C", str(upstream), "add", "."], check=True)
    subprocess.run(["git", "-C", str(upstream), "commit", "-m", "initial"], check=True, stdout=subprocess.DEVNULL)

    manifest = _write_manifest(
        tmp_path / "repo" / ".agents" / "components.yaml",
        f"""
version: 1
materialize:
  agents_dir: .agents/skills
  claude_dir: .claude/skills
sources:
  demo-upstream:
    type: git
    url: file://{upstream}
    ref: master
    components:
      demo:
        kind: skill
        path: skills/demo
""",
    )
    real_run = subprocess.run
    clone_attempts = 0

    def flaky_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        nonlocal clone_attempts
        command = args[0] if args else kwargs.get("args")
        if isinstance(command, list) and command[:3] == ["git", "clone", "--mirror"]:
            clone_attempts += 1
            if clone_attempts == 1:
                raise subprocess.CalledProcessError(
                    returncode=128,
                    cmd=command,
                    stderr="GnuTLS recv error (-110): The TLS connection was non-properly terminated.",
                )
        return real_run(*args, **kwargs)

    monkeypatch.setattr(subprocess, "run", flaky_run)
    manager = ComponentManager(
        manifest,
        tmp_path / "repo" / ".agents" / "components.lock.json",
        repo_root=tmp_path / "repo",
        cache_dir=tmp_path / "cache",
    )

    lock = manager.write_lock()

    assert clone_attempts == 2
    assert lock["components"]["demo"]["sourcePath"] == "skills/demo"


def test_git_source_fetches_shared_source_once_per_lock_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from lib.agent_components import ComponentManager

    upstream = tmp_path / "upstream"
    _write_skill(upstream / "skills", "first", "from git")
    _write_skill(upstream / "skills", "second", "from git")
    subprocess.run(["git", "init", str(upstream)], check=True, stdout=subprocess.DEVNULL)
    subprocess.run(["git", "-C", str(upstream), "config", "user.email", "test@example.com"], check=True)
    subprocess.run(["git", "-C", str(upstream), "config", "user.name", "Test"], check=True)
    subprocess.run(["git", "-C", str(upstream), "add", "."], check=True)
    subprocess.run(["git", "-C", str(upstream), "commit", "-m", "initial"], check=True, stdout=subprocess.DEVNULL)

    manifest = _write_manifest(
        tmp_path / "repo" / ".agents" / "components.yaml",
        f"""
version: 1
materialize:
  agents_dir: .agents/skills
  claude_dir: .claude/skills
sources:
  demo-upstream:
    type: git
    url: file://{upstream}
    ref: master
    components:
      first:
        kind: skill
        path: skills/first
      second:
        kind: skill
        path: skills/second
""",
    )
    real_run = subprocess.run
    fetches: list[list[str]] = []

    def tracking_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        command = args[0] if args else kwargs.get("args")
        if isinstance(command, list) and "fetch" in command:
            fetches.append(command)
        return real_run(*args, **kwargs)

    monkeypatch.setattr(subprocess, "run", tracking_run)

    manager = ComponentManager(
        manifest,
        tmp_path / "repo" / ".agents" / "components.lock.json",
        repo_root=tmp_path / "repo",
        cache_dir=tmp_path / "cache",
    )
    manager.write_lock()

    assert len(fetches) <= 1


def test_frozen_offline_verify_uses_locked_git_commit_after_ref_moves(tmp_path: Path) -> None:
    from lib.agent_components import ComponentManager

    upstream = tmp_path / "upstream"
    _write_skill(upstream / "skills", "demo", "from git")
    subprocess.run(["git", "init", str(upstream)], check=True, stdout=subprocess.DEVNULL)
    subprocess.run(["git", "-C", str(upstream), "config", "user.email", "test@example.com"], check=True)
    subprocess.run(["git", "-C", str(upstream), "config", "user.name", "Test"], check=True)
    subprocess.run(["git", "-C", str(upstream), "add", "."], check=True)
    subprocess.run(["git", "-C", str(upstream), "commit", "-m", "initial"], check=True, stdout=subprocess.DEVNULL)
    initial_commit = subprocess.run(
        ["git", "-C", str(upstream), "rev-parse", "HEAD"],
        check=True,
        stdout=subprocess.PIPE,
        text=True,
    ).stdout.strip()

    manifest = _write_manifest(
        tmp_path / "repo" / ".agents" / "components.yaml",
        f"""
version: 1
materialize:
  agents_dir: .agents/skills
  claude_dir: .claude/skills
  default_mode: copy
sources:
  demo-upstream:
    type: git
    url: file://{upstream}
    ref: master
    components:
      demo:
        kind: skill
        path: skills/demo
""",
    )
    lock_path = tmp_path / "repo" / ".agents" / "components.lock.json"
    cache_dir = tmp_path / "cache"
    manager = ComponentManager(manifest, lock_path, repo_root=tmp_path / "repo", cache_dir=cache_dir)
    lock = manager.write_lock()
    manager.install(names=["demo"], frozen=True, offline=True, mode="copy")

    (upstream / "skills" / "demo" / "SKILL.md").write_text("# demo\n\nupdated upstream\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(upstream), "add", "."], check=True)
    subprocess.run(["git", "-C", str(upstream), "commit", "-m", "update"], check=True, stdout=subprocess.DEVNULL)
    latest_commit = subprocess.run(
        ["git", "-C", str(upstream), "rev-parse", "HEAD"],
        check=True,
        stdout=subprocess.PIPE,
        text=True,
    ).stdout.strip()

    checker = ComponentManager(manifest, lock_path, repo_root=tmp_path / "repo", cache_dir=cache_dir)

    assert lock["components"]["demo"]["resolvedCommit"] == initial_commit
    assert checker.outdated() == [{"name": "demo", "current": initial_commit, "latest": latest_commit}]
    assert checker.verify(frozen=True, offline=True) == []


def test_update_lock_can_refresh_one_component_without_fetching_unrelated_sources(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from lib.agent_components import ComponentManager

    first_upstream = tmp_path / "first-upstream"
    second_upstream = tmp_path / "second-upstream"
    _write_skill(first_upstream / "skills", "first", "from first")
    _write_skill(second_upstream / "skills", "second", "from second")
    for upstream in (first_upstream, second_upstream):
        subprocess.run(["git", "init", str(upstream)], check=True, stdout=subprocess.DEVNULL)
        subprocess.run(["git", "-C", str(upstream), "config", "user.email", "test@example.com"], check=True)
        subprocess.run(["git", "-C", str(upstream), "config", "user.name", "Test"], check=True)
        subprocess.run(["git", "-C", str(upstream), "add", "."], check=True)
        subprocess.run(["git", "-C", str(upstream), "commit", "-m", "initial"], check=True, stdout=subprocess.DEVNULL)

    manifest = _write_manifest(
        tmp_path / "repo" / ".agents" / "components.yaml",
        f"""
version: 1
materialize:
  agents_dir: .agents/skills
  claude_dir: .claude/skills
sources:
  first-source:
    type: git
    url: file://{first_upstream}
    ref: master
    components:
      first:
        kind: skill
        path: skills/first
  second-source:
    type: git
    url: file://{second_upstream}
    ref: master
    components:
      second:
        kind: skill
        path: skills/second
""",
    )
    lock_path = tmp_path / "repo" / ".agents" / "components.lock.json"
    cache_dir = tmp_path / "cache"
    manager = ComponentManager(manifest, lock_path, repo_root=tmp_path / "repo", cache_dir=cache_dir)
    original = manager.write_lock()

    (first_upstream / "skills" / "first" / "SKILL.md").write_text("# first\n\nupdated first\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(first_upstream), "add", "."], check=True)
    subprocess.run(["git", "-C", str(first_upstream), "commit", "-m", "update"], check=True, stdout=subprocess.DEVNULL)

    real_run = subprocess.run
    second_fetches: list[list[str]] = []

    def tracking_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        command = args[0] if args else kwargs.get("args")
        command_text = " ".join(str(part) for part in command) if isinstance(command, list) else ""
        if isinstance(command, list) and "fetch" in command and str(second_mirror) in command_text:
            second_fetches.append(command)
        return real_run(*args, **kwargs)

    second_key = hashlib.sha256(f"file://{second_upstream}".encode("utf-8")).hexdigest()[:16]
    second_mirror = cache_dir / "git" / second_key / "repo.git"
    assert second_mirror.exists()
    monkeypatch.setattr(subprocess, "run", tracking_run)

    updated = manager.update_lock("first")

    assert updated["components"]["first"]["treeSha256"] != original["components"]["first"]["treeSha256"]
    assert updated["components"]["second"] == original["components"]["second"]
    assert second_fetches == []


def test_verify_detects_materialized_hash_mismatch(tmp_path: Path) -> None:
    from lib.agent_components import ComponentManager

    _write_skill(tmp_path / ".agents" / "local" / "skills", "demo", "original")
    manifest = _write_manifest(
        tmp_path / ".agents" / "components.yaml",
        """
version: 1
materialize:
  agents_dir: .agents/skills
  claude_dir: .claude/skills
  default_mode: copy
sources:
  video-production-buddy-local:
    type: local
    root: .agents/local/skills
    components:
      demo:
        kind: skill
        path: demo
""",
    )
    manager = ComponentManager(manifest, tmp_path / ".agents" / "components.lock.json", repo_root=tmp_path)
    manager.write_lock()
    manager.install(names=["demo"], frozen=True, mode="copy")

    (tmp_path / ".agents" / "skills" / "demo" / "SKILL.md").write_text(
        "# demo\n\nmutated\n",
        encoding="utf-8",
    )

    failures = manager.verify(frozen=True, offline=True)
    assert any("demo: materialized file hash mismatch" in failure for failure in failures)


def test_verify_detects_claude_materialized_hash_mismatch(tmp_path: Path) -> None:
    from lib.agent_components import ComponentManager

    _write_skill(tmp_path / ".agents" / "local" / "skills", "demo", "original")
    manifest = _write_manifest(
        tmp_path / ".agents" / "components.yaml",
        """
version: 1
materialize:
  agents_dir: .agents/skills
  claude_dir: .claude/skills
  default_mode: copy
sources:
  video-production-buddy-local:
    type: local
    root: .agents/local/skills
    components:
      demo:
        kind: skill
        path: demo
""",
    )
    manager = ComponentManager(manifest, tmp_path / ".agents" / "components.lock.json", repo_root=tmp_path)
    manager.write_lock()
    manager.install(names=["demo"], frozen=True, mode="copy")

    (tmp_path / ".claude" / "skills" / "demo" / "SKILL.md").write_text(
        "# demo\n\nmutated\n",
        encoding="utf-8",
    )

    failures = manager.verify(frozen=True, offline=True)
    assert any("demo: claude materialized file hash mismatch" in failure for failure in failures)


def test_registered_tool_agent_skills_are_declared_in_component_manifest() -> None:
    from lib.agent_components import load_manifest

    repo_root = Path(__file__).resolve().parents[2]
    manifest = load_manifest(repo_root / ".agents" / "components.yaml", repo_root=repo_root)
    declared = set(manifest.components)

    registry.clear()
    registry.discover()
    required = {
        skill
        for tool_name in registry.list_all()
        for skill in registry.get(tool_name).agent_skills
    }

    assert sorted(required - declared) == []


def test_project_verified_third_party_components_are_git_backed() -> None:
    from lib.agent_components import load_manifest

    repo_root = Path(__file__).resolve().parents[2]
    manifest = load_manifest(repo_root / ".agents" / "components.yaml", repo_root=repo_root)
    expected_sources = {
        "beautiful-mermaid": "intellectronica-agent-skills",
        "bfl-api": "black-forest-labs-skills",
        "flux-best-practices": "black-forest-labs-skills",
        "gsap-core": "greensock-gsap-skills",
        "gsap-frameworks": "greensock-gsap-skills",
        "gsap-performance": "greensock-gsap-skills",
        "gsap-plugins": "greensock-gsap-skills",
        "gsap-react": "greensock-gsap-skills",
        "gsap-scrolltrigger": "greensock-gsap-skills",
        "gsap-timeline": "greensock-gsap-skills",
        "gsap-utils": "greensock-gsap-skills",
        "hyperframes-registry": "heygen-hyperframes",
    }

    for component, source in expected_sources.items():
        spec = manifest.components[component]
        assert spec.source == source
        assert spec.source_type == "git"
        assert spec.url and spec.requested_ref


def test_project_agent_component_manifest_matches_schema() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    schema = json.loads((repo_root / "schemas" / "agent_components.schema.json").read_text(encoding="utf-8"))
    manifest_data = yaml.safe_load((repo_root / ".agents" / "components.yaml").read_text(encoding="utf-8"))

    jsonschema.validate(manifest_data, schema)


def test_project_agent_component_lock_is_canonical_and_complete() -> None:
    from lib.agent_components import ComponentManager, load_manifest

    repo_root = Path(__file__).resolve().parents[2]
    lock_path = repo_root / ".agents" / "components.lock.json"
    manifest = load_manifest(repo_root / ".agents" / "components.yaml", repo_root=repo_root)
    lock = json.loads(lock_path.read_text(encoding="utf-8"))

    assert lock["lockfileVersion"] == 1
    assert set(lock["components"]) == set(manifest.components)
    assert lock_path.read_text(encoding="utf-8") == json.dumps(lock, indent=2, sort_keys=True) + "\n"
    manager = ComponentManager(repo_root=repo_root)
    assert manager.verify(frozen=True, offline=True) == []
