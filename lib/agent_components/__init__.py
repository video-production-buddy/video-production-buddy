from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import yaml

from schemas.artifacts import load_strict_json_object


DEFAULT_MANIFEST = Path(".agents/components.yaml")
DEFAULT_LOCK = Path(".agents/components.lock.json")
DEFAULT_CACHE = Path.home() / ".cache" / "video-production-buddy" / "agent-components"
MATERIALIZATION_MARKER = ".video-production-buddy-agent-components.json"
COMPONENT_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
VALID_KINDS = {"skill", "plugin"}
VALID_SOURCE_TYPES = {"local", "git"}
VALID_MODES = {"copy", "symlink"}
VALID_TARGETS = {"agents", "claude"}


class ComponentError(RuntimeError):
    """Raised when component dependency metadata or materialization is invalid."""


@dataclass(frozen=True)
class ComponentSpec:
    name: str
    kind: str
    source: str
    source_type: str
    source_path: Path
    manifest_source_path: str
    url: str | None = None
    requested_ref: str | None = None


@dataclass(frozen=True)
class Manifest:
    path: Path
    repo_root: Path
    agents_dir: Path
    claude_dir: Path
    default_mode: str
    components: dict[str, ComponentSpec]
    profiles: dict[str, list[str]]


def load_manifest(path: str | Path = DEFAULT_MANIFEST, *, repo_root: str | Path | None = None) -> Manifest:
    manifest_path = Path(path)
    root = Path(repo_root) if repo_root is not None else manifest_path.resolve().parents[1]
    root = root.resolve()
    if not manifest_path.is_absolute():
        manifest_path = root / manifest_path

    if not manifest_path.exists():
        raise ComponentError(f"component manifest not found: {_display_path(manifest_path, root)}")

    data = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
    errors: list[str] = []
    if data.get("version") != 1:
        errors.append("manifest version must be 1")

    materialize = data.get("materialize") or {}
    agents_dir = _safe_repo_path(
        root,
        materialize.get("agents_dir", ".agents/skills"),
        label="materialize.agents_dir",
        errors=errors,
    )
    claude_dir = _safe_repo_path(
        root,
        materialize.get("claude_dir", ".claude/skills"),
        label="materialize.claude_dir",
        errors=errors,
    )
    default_mode = materialize.get("default_mode", "symlink")
    if default_mode not in VALID_MODES:
        errors.append("materialize.default_mode must be 'copy' or 'symlink'")

    components: dict[str, ComponentSpec] = {}
    sources = data.get("sources") or {}
    if not isinstance(sources, dict) or not sources:
        errors.append("manifest must declare at least one source")

    for source_name, source_data in sources.items():
        if not isinstance(source_data, dict):
            errors.append(f"source {source_name!r} must be an object")
            continue
        source_type = source_data.get("type")
        if source_type not in VALID_SOURCE_TYPES:
            errors.append(f"source {source_name!r} type must be one of {sorted(VALID_SOURCE_TYPES)}")
            continue

        source_root_text = source_data.get("root", "")
        source_root = root
        if source_type == "local":
            if not source_root_text:
                errors.append(f"local source {source_name!r} must declare root")
            source_root = _safe_repo_path(
                root,
                source_root_text,
                label=f"source {source_name!r} root",
                errors=errors,
            )
        else:
            if not source_data.get("url"):
                errors.append(f"git source {source_name!r} must declare url")
            if not source_data.get("ref"):
                errors.append(f"git source {source_name!r} must declare ref")

        declared = source_data.get("components", source_data.get("skills")) or {}
        if not isinstance(declared, dict) or not declared:
            errors.append(f"source {source_name!r} must declare components")
            continue

        for component_name, component_data in declared.items():
            if not isinstance(component_name, str) or not COMPONENT_NAME_RE.fullmatch(component_name):
                errors.append(
                    f"component name {component_name!r} must match "
                    f"{COMPONENT_NAME_RE.pattern!r}"
                )
            if component_name in components:
                errors.append(f"duplicate component name {component_name!r}")
            if not isinstance(component_data, dict):
                errors.append(f"component {component_name!r} must be an object")
                continue
            kind = component_data.get("kind", "skill")
            if kind not in VALID_KINDS:
                errors.append(f"component {component_name!r} kind must be one of {sorted(VALID_KINDS)}")
            rel_path = component_data.get("path")
            if not rel_path:
                errors.append(f"component {component_name!r} must declare path")
                continue
            source_path = _safe_child_path(
                source_root,
                rel_path,
                label=f"component {component_name!r} path",
                errors=errors,
            )
            if component_name not in components:
                components[component_name] = ComponentSpec(
                    name=component_name,
                    kind=kind,
                    source=source_name,
                    source_type=source_type,
                    source_path=source_path,
                    manifest_source_path=str(rel_path).replace("\\", "/"),
                    url=source_data.get("url"),
                    requested_ref=source_data.get("ref"),
                )

    raw_profiles = data.get("profiles") or {}
    profiles: dict[str, list[str]] = {}
    for profile_name, names in raw_profiles.items():
        if not isinstance(names, list) or not all(isinstance(name, str) for name in names):
            errors.append(f"profile {profile_name!r} must be a list of component names")
            continue
        unknown = sorted(set(names) - set(components))
        if unknown:
            errors.append(f"profile {profile_name!r} references unknown components: {unknown}")
        profiles[profile_name] = list(names)
    if "default" not in profiles and components:
        profiles["default"] = sorted(components)

    if errors:
        raise ComponentError("; ".join(errors))

    return Manifest(
        path=manifest_path,
        repo_root=root,
        agents_dir=agents_dir,
        claude_dir=claude_dir,
        default_mode=default_mode,
        components=components,
        profiles=profiles,
    )


class ComponentManager:
    def __init__(
        self,
        manifest_path: str | Path = DEFAULT_MANIFEST,
        lock_path: str | Path = DEFAULT_LOCK,
        *,
        repo_root: str | Path | None = None,
        cache_dir: str | Path = DEFAULT_CACHE,
    ) -> None:
        self.manifest_path = Path(manifest_path)
        self.repo_root = Path(repo_root).resolve() if repo_root is not None else Path.cwd().resolve()
        if not self.manifest_path.is_absolute():
            self.manifest_path = self.repo_root / self.manifest_path
        self.lock_path = Path(lock_path)
        if not self.lock_path.is_absolute():
            self.lock_path = self.repo_root / self.lock_path
        self.cache_dir = Path(cache_dir).expanduser().resolve()
        self._refreshed_mirrors: set[Path] = set()

    def write_lock(self, *, offline: bool = False) -> dict[str, Any]:
        lock = self.compute_lock(offline=offline)
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        self.lock_path.write_text(_canonical_json(lock), encoding="utf-8")
        return lock

    def compute_lock(self, *, offline: bool = False) -> dict[str, Any]:
        manifest = load_manifest(self.manifest_path, repo_root=self.repo_root)
        components: dict[str, Any] = {}
        for name in sorted(manifest.components):
            components[name] = self._compute_component_lock_entry(manifest.components[name], offline=offline)
        return {"lockfileVersion": 1, "components": components}

    def update_lock(self, selector: str | None = None, *, offline: bool = False) -> dict[str, Any]:
        if selector is None:
            return self.write_lock(offline=offline)

        manifest = load_manifest(self.manifest_path, repo_root=self.repo_root)
        selected = self._select_update_components(manifest, selector)
        try:
            lock = self.load_lock()
        except ComponentError:
            lock = {"lockfileVersion": 1, "components": {}}
        lock["components"] = {
            name: entry for name, entry in lock["components"].items() if name in manifest.components
        }
        for name in selected:
            spec = manifest.components[name]
            if spec.source_type == "git" and spec.url:
                self._refreshed_mirrors.discard(self.cache_dir / "git" / _short_hash(spec.url) / "repo.git")

        for name in selected:
            lock["components"][name] = self._compute_component_lock_entry(
                manifest.components[name],
                offline=offline,
            )
        for name in sorted(set(manifest.components) - set(lock["components"])):
            lock["components"][name] = self._compute_component_lock_entry(
                manifest.components[name],
                offline=offline,
            )

        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        self.lock_path.write_text(_canonical_json(lock), encoding="utf-8")
        return lock

    def load_lock(self) -> dict[str, Any]:
        if not self.lock_path.exists():
            raise ComponentError(f"component lockfile not found: {_display_path(self.lock_path, self.repo_root)}")
        try:
            data = load_strict_json_object(
                self.lock_path,
                context="component lockfile",
            )
        except ValueError as exc:
            raise ComponentError(str(exc)) from exc
        if data.get("lockfileVersion") != 1:
            raise ComponentError("component lockfile version must be 1")
        if not isinstance(data.get("components"), dict):
            raise ComponentError("component lockfile must declare components")
        return data

    def install(
        self,
        *,
        names: Iterable[str] | None = None,
        profile: str | None = None,
        frozen: bool = False,
        targets: tuple[str, ...] = ("agents", "claude"),
        mode: str | None = None,
        offline: bool = False,
    ) -> None:
        manifest = load_manifest(self.manifest_path, repo_root=self.repo_root)
        install_mode = mode or manifest.default_mode
        if install_mode not in VALID_MODES:
            raise ComponentError(f"install mode must be one of {sorted(VALID_MODES)}")
        bad_targets = set(targets) - VALID_TARGETS
        if bad_targets:
            raise ComponentError(f"unknown materialization targets: {sorted(bad_targets)}")

        selected = self._select_components(manifest, names=names, profile=profile)
        lock = self._lock_for_install(frozen=frozen, offline=offline)

        missing = sorted(set(selected) - set(lock["components"]))
        if missing:
            raise ComponentError(f"lockfile is missing components: {missing}")

        for name in selected:
            spec = manifest.components[name]
            entry = lock["components"][name]
            source_dir = self._locked_source_dir(spec, entry, offline=offline)
            _assert_tree_matches_lock(source_dir, entry, label=name, target_label="source")
            if "agents" in targets:
                self._materialize_tree(source_dir, manifest.agents_dir / name, mode=install_mode)
            if "claude" in targets:
                agents_target = manifest.agents_dir / name
                claude_target = manifest.claude_dir / name
                if install_mode == "symlink" and "agents" in targets:
                    self._materialize_symlink_or_copy(source_dir, agents_target, claude_target)
                else:
                    self._materialize_tree(source_dir, claude_target, mode="copy")

    def verify(self, *, frozen: bool = False, offline: bool = False) -> list[str]:
        failures: list[str] = []
        try:
            manifest = load_manifest(self.manifest_path, repo_root=self.repo_root)
        except ComponentError as exc:
            return [str(exc)]
        try:
            lock = self.load_lock()
        except ComponentError as exc:
            return [str(exc)]

        manifest_names = set(manifest.components)
        lock_names = set(lock["components"])
        for name in sorted(manifest_names - lock_names):
            failures.append(f"{name}: missing from lockfile")
        for name in sorted(lock_names - manifest_names):
            failures.append(f"{name}: lockfile entry missing from manifest")

        if frozen:
            for name in sorted(manifest_names & lock_names):
                spec = manifest.components[name]
                entry = lock["components"][name]
                failures.extend(_lock_entry_metadata_failures(spec, entry, self.repo_root))
                try:
                    source_dir = self._locked_source_dir(spec, entry, offline=offline)
                    _assert_tree_matches_lock(source_dir, entry, label=name, target_label="source")
                except ComponentError as exc:
                    failures.append(str(exc))

        for name in sorted(manifest_names & lock_names):
            entry = lock["components"][name]
            for target_label, target in (
                ("materialized", manifest.agents_dir / name),
                ("claude materialized", manifest.claude_dir / name),
            ):
                if not target.exists():
                    failures.append(f"{name}: {target_label} target missing")
                    continue
                try:
                    _assert_tree_matches_lock(target, entry, label=name, target_label=target_label)
                except ComponentError as exc:
                    failures.append(str(exc))
        return failures

    def outdated(self) -> list[dict[str, str]]:
        manifest = load_manifest(self.manifest_path, repo_root=self.repo_root)
        lock = self.load_lock()
        results: list[dict[str, str]] = []
        for name, spec in sorted(manifest.components.items()):
            if spec.source_type != "git":
                continue
            current = lock["components"].get(name, {}).get("resolvedCommit", "")
            latest = self._resolve_git_commit(spec, offline=False)
            if current and latest != current:
                results.append({"name": name, "current": current, "latest": latest})
        return results

    def _select_components(
        self,
        manifest: Manifest,
        *,
        names: Iterable[str] | None,
        profile: str | None,
    ) -> list[str]:
        if names:
            selected = list(names)
        elif profile:
            if profile not in manifest.profiles:
                raise ComponentError(f"unknown component profile {profile!r}")
            selected = list(manifest.profiles[profile])
        else:
            selected = sorted(manifest.components)
        unknown = sorted(set(selected) - set(manifest.components))
        if unknown:
            raise ComponentError(f"unknown components: {unknown}")
        return selected

    def _select_update_components(self, manifest: Manifest, selector: str) -> list[str]:
        if selector in manifest.components:
            return [selector]
        selected = sorted(name for name, spec in manifest.components.items() if spec.source == selector)
        if selected:
            return selected
        raise ComponentError(f"unknown component or source {selector!r}")

    def _lock_for_install(self, *, frozen: bool, offline: bool) -> dict[str, Any]:
        if frozen:
            return self.load_lock()
        lock = self.write_lock(offline=offline)
        return lock

    def _source_dir(self, spec: ComponentSpec, *, offline: bool) -> tuple[Path, str | None]:
        if spec.source_type == "local":
            if not spec.source_path.exists():
                raise ComponentError(f"{spec.name}: local source path does not exist: {spec.source_path}")
            return spec.source_path, None
        resolved_commit = self._resolve_git_commit(spec, offline=offline)
        return self._extract_git_component(spec, resolved_commit, offline=offline), resolved_commit

    def _compute_component_lock_entry(self, spec: ComponentSpec, *, offline: bool) -> dict[str, Any]:
        source_dir, resolved_commit = self._source_dir(spec, offline=offline)
        tree = _hash_tree(source_dir)
        entry: dict[str, Any] = {
            "kind": spec.kind,
            "source": spec.source,
            "sourcePath": _display_path(source_dir, self.repo_root)
            if spec.source_type == "local"
            else spec.manifest_source_path,
            "treeSha256": tree["treeSha256"],
            "type": spec.source_type,
            "files": tree["files"],
        }
        if spec.source_type == "git":
            entry.update(
                {
                    "url": spec.url,
                    "requestedRef": spec.requested_ref,
                    "resolvedCommit": resolved_commit,
                }
            )
        return entry

    def _locked_source_dir(self, spec: ComponentSpec, entry: dict[str, Any], *, offline: bool) -> Path:
        if entry.get("type") == "local":
            source = self.repo_root / entry["sourcePath"]
            if not source.exists():
                raise ComponentError(f"{spec.name}: local locked source path does not exist: {entry['sourcePath']}")
            return source
        if entry.get("type") == "git":
            resolved = entry.get("resolvedCommit")
            if not resolved:
                raise ComponentError(f"{spec.name}: git lock entry missing resolvedCommit")
            return self._extract_git_component(spec, resolved, offline=offline)
        raise ComponentError(f"{spec.name}: unsupported lock entry type {entry.get('type')!r}")

    def _resolve_git_commit(self, spec: ComponentSpec, *, offline: bool) -> str:
        mirror = self._git_mirror(spec, offline=offline)
        ref = spec.requested_ref or "HEAD"
        candidates = [
            ref,
            f"refs/heads/{ref}",
            f"refs/tags/{ref}^{{commit}}",
            f"refs/tags/{ref}",
            f"origin/{ref}",
        ]
        for candidate in candidates:
            result = subprocess.run(
                ["git", f"--git-dir={mirror}", "rev-parse", "--verify", candidate],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                check=False,
            )
            if result.returncode == 0:
                return result.stdout.strip()
        raise ComponentError(f"{spec.name}: could not resolve git ref {ref!r} from {spec.url}")

    def _run_git_with_retries(
        self,
        command: list[str],
        *,
        label: str,
        cleanup_path: Path | None = None,
        attempts: int = 3,
        timeout_seconds: int = 180,
    ) -> None:
        last_error: subprocess.CalledProcessError | subprocess.TimeoutExpired | None = None
        for attempt in range(1, attempts + 1):
            try:
                subprocess.run(
                    command,
                    check=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                    text=True,
                    timeout=timeout_seconds,
                )
                return
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
                last_error = exc
                if cleanup_path is not None:
                    shutil.rmtree(cleanup_path, ignore_errors=True)
                if attempt < attempts:
                    continue

        if last_error is None:
            raise ComponentError(f"{label}: git command failed")
        tail = _subprocess_error_tail(last_error)
        raise ComponentError(
            f"{label}: git command failed after {attempts} attempts: {tail}"
        ) from last_error

    def _git_mirror(self, spec: ComponentSpec, *, offline: bool) -> Path:
        if not spec.url:
            raise ComponentError(f"{spec.name}: git source missing url")
        mirror = self.cache_dir / "git" / _short_hash(spec.url) / "repo.git"
        if mirror.exists():
            if not offline and mirror not in self._refreshed_mirrors:
                self._run_git_with_retries(
                    ["git", f"--git-dir={mirror}", "fetch", "--prune", "--tags", "origin"],
                    label=f"{spec.name}: could not fetch git source {spec.url}",
                )
                self._refreshed_mirrors.add(mirror)
            return mirror
        if offline:
            raise ComponentError(f"{spec.name}: git cache missing for {spec.url}")
        mirror.parent.mkdir(parents=True, exist_ok=True)
        self._run_git_with_retries(
            ["git", "clone", "--mirror", spec.url, str(mirror)],
            label=f"{spec.name}: could not clone git source {spec.url}",
            cleanup_path=mirror,
        )
        self._refreshed_mirrors.add(mirror)
        return mirror

    def _extract_git_component(self, spec: ComponentSpec, commit: str, *, offline: bool) -> Path:
        if not spec.url:
            raise ComponentError(f"{spec.name}: git source missing url")
        path_key = _short_hash(spec.manifest_source_path)
        dest = self.cache_dir / "trees" / _short_hash(spec.url) / commit / path_key / spec.name
        if dest.exists():
            return dest
        if offline:
            raise ComponentError(f"{spec.name}: cached git tree missing for {commit}:{spec.manifest_source_path}")
        mirror = self._git_mirror(spec, offline=False)
        dest.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="agent-component-") as tmp:
            tmp_path = Path(tmp)
            archive = subprocess.run(
                ["git", f"--git-dir={mirror}", "archive", f"{commit}:{spec.manifest_source_path}"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            if archive.returncode != 0:
                raise ComponentError(
                    f"{spec.name}: could not archive {spec.manifest_source_path} "
                    f"from {spec.url}@{commit}: {archive.stderr.decode(errors='replace').strip()}"
                )
            tar = subprocess.run(
                ["tar", "-x", "-C", str(tmp_path)],
                input=archive.stdout,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                check=False,
            )
            if tar.returncode != 0:
                raise ComponentError(f"{spec.name}: could not extract git archive: {tar.stderr.decode().strip()}")
            shutil.move(str(tmp_path), str(dest))
        return dest

    def _materialize_tree(self, source_dir: Path, target_dir: Path, *, mode: str) -> None:
        if source_dir.resolve() == target_dir.resolve():
            return
        _remove_materialized_target(source_dir, target_dir)
        target_dir.parent.mkdir(parents=True, exist_ok=True)
        _write_materialization_marker(target_dir.parent)
        if mode == "symlink":
            try:
                rel = os.path.relpath(source_dir, target_dir.parent)
                target_dir.symlink_to(rel, target_is_directory=True)
                return
            except OSError:
                pass
        shutil.copytree(source_dir, target_dir, symlinks=True)

    def _materialize_symlink_or_copy(self, source_dir: Path, agents_target: Path, claude_target: Path) -> None:
        _remove_materialized_target(source_dir, claude_target)
        claude_target.parent.mkdir(parents=True, exist_ok=True)
        _write_materialization_marker(claude_target.parent)
        try:
            rel = os.path.relpath(agents_target, claude_target.parent)
            claude_target.symlink_to(rel, target_is_directory=True)
        except OSError:
            shutil.copytree(source_dir, claude_target, symlinks=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Manage Video Production Buddy agent component dependencies.")
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    parser.add_argument("--lock", default=str(DEFAULT_LOCK))
    parser.add_argument("--cache-dir", default=str(DEFAULT_CACHE))
    sub = parser.add_subparsers(dest="command", required=True)

    install = sub.add_parser("install", help="materialize components")
    install.add_argument("names", nargs="*")
    install.add_argument("--profile")
    install.add_argument("--frozen", action="store_true")
    install.add_argument("--offline", action="store_true")
    install.add_argument("--target", choices=sorted(VALID_TARGETS | {"all"}), default="all")
    install.add_argument("--mode", choices=sorted(VALID_MODES))

    verify = sub.add_parser("verify", help="verify manifest, lock, and materialized files")
    verify.add_argument("--frozen", action="store_true")
    verify.add_argument("--offline", action="store_true")

    lock = sub.add_parser("lock", help="write lockfile")
    lock.add_argument("--offline", action="store_true")

    use = sub.add_parser("use", help="change one component source ref and refresh lock")
    use.add_argument("name")
    use.add_argument("--ref", required=True)

    update = sub.add_parser("update", help="refresh lock for a component or source")
    update.add_argument("name", nargs="?")
    update.add_argument("--to")

    outdated = sub.add_parser("outdated", help="list git components whose requested ref moved")
    diff = sub.add_parser("diff", help="show installed/source diff for a component")
    diff.add_argument("name")

    args = parser.parse_args(argv)
    manager = ComponentManager(args.manifest, args.lock, cache_dir=args.cache_dir)

    try:
        if args.command == "install":
            targets = ("agents", "claude") if args.target == "all" else (args.target,)
            manager.install(
                names=args.names or None,
                profile=args.profile,
                frozen=args.frozen,
                offline=args.offline,
                targets=targets,
                mode=args.mode,
            )
        elif args.command == "verify":
            failures = manager.verify(frozen=args.frozen, offline=args.offline)
            if failures:
                for failure in failures:
                    print(failure)
                return 1
            print("agent components verified")
        elif args.command == "lock":
            manager.write_lock(offline=args.offline)
        elif args.command == "use":
            source = _rewrite_ref(manager.manifest_path, manager.repo_root, args.name, args.ref)
            manager.update_lock(source)
        elif args.command == "update":
            if args.to:
                if not args.name:
                    raise ComponentError("update --to requires a component name")
                selector = _rewrite_ref(manager.manifest_path, manager.repo_root, args.name, args.to)
            else:
                selector = args.name
            manager.update_lock(selector)
        elif args.command == "outdated":
            for row in manager.outdated():
                print(f"{row['name']}: {row['current']} -> {row['latest']}")
        elif args.command == "diff":
            _run_component_diff(manager, args.name)
    except (ComponentError, subprocess.CalledProcessError) as exc:
        print(str(exc))
        return 1
    return 0


def _rewrite_ref(manifest_path: Path, repo_root: Path, component_or_source: str, ref: str) -> str:
    manifest = load_manifest(manifest_path, repo_root=repo_root)
    data = yaml.safe_load(manifest.path.read_text(encoding="utf-8"))
    if component_or_source in data.get("sources", {}):
        source_name = component_or_source
        if data["sources"][source_name].get("type") != "git":
            raise ComponentError(f"{component_or_source}: only git sources support ref switching")
    elif component_or_source in manifest.components:
        spec = manifest.components[component_or_source]
        if spec.source_type != "git":
            raise ComponentError(f"{component_or_source}: only git components support ref switching")
        source_name = spec.source
    else:
        raise ComponentError(f"unknown component or source {component_or_source!r}")
    data["sources"][source_name]["ref"] = ref
    manifest.path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return source_name


def _run_component_diff(manager: ComponentManager, name: str) -> None:
    manifest = load_manifest(manager.manifest_path, repo_root=manager.repo_root)
    lock = manager.load_lock()
    if name not in manifest.components:
        raise ComponentError(f"unknown component {name!r}")
    if name not in lock["components"]:
        raise ComponentError(f"{name}: missing from lockfile")
    source = manager._locked_source_dir(manifest.components[name], lock["components"][name], offline=False)
    target = manifest.agents_dir / name
    subprocess.run(["diff", "-ru", str(target), str(source)], check=False)


def _lock_entry_metadata_failures(
    spec: ComponentSpec,
    entry: dict[str, Any],
    repo_root: Path,
) -> list[str]:
    expected: dict[str, Any] = {
        "kind": spec.kind,
        "source": spec.source,
        "sourcePath": _display_path(spec.source_path, repo_root)
        if spec.source_type == "local"
        else spec.manifest_source_path,
        "type": spec.source_type,
    }
    if spec.source_type == "git":
        expected.update(
            {
                "url": spec.url,
                "requestedRef": spec.requested_ref,
            }
        )

    failures = []
    for key, value in expected.items():
        if entry.get(key) != value:
            failures.append(f"{spec.name}: lockfile {key} mismatch")
    if spec.source_type == "git" and not entry.get("resolvedCommit"):
        failures.append(f"{spec.name}: git lock entry missing resolvedCommit")
    return failures


def _safe_repo_path(root: Path, value: str, *, label: str, errors: list[str]) -> Path:
    return _safe_child_path(root, value, label=label, errors=errors)


def _safe_child_path(base: Path, value: str, *, label: str, errors: list[str]) -> Path:
    path_text = str(value)
    if Path(path_text).is_absolute():
        errors.append(f"{label} must be relative")
        return base
    candidate = (base / path_text).resolve()
    try:
        candidate.relative_to(base.resolve())
    except ValueError:
        errors.append(f"{label} must stay under source root")
    return candidate


def _hash_tree(root: Path) -> dict[str, Any]:
    if not root.exists():
        raise ComponentError(f"source tree does not exist: {root}")
    if not root.is_dir():
        raise ComponentError(f"source tree is not a directory: {root}")
    files = []
    tree_hasher = hashlib.sha256()
    for path in sorted(p for p in root.rglob("*") if p.is_file() and not _is_ignored_component_file(p, root)):
        rel = path.relative_to(root).as_posix()
        digest = _sha256_file(path)
        mode = _locked_file_mode(path)
        files.append({"path": rel, "mode": mode, "sha256": f"sha256:{digest}"})
        tree_hasher.update(rel.encode("utf-8") + b"\0")
        tree_hasher.update(mode.encode("ascii") + b"\0")
        tree_hasher.update(digest.encode("ascii") + b"\0")
    return {"treeSha256": f"sha256:{tree_hasher.hexdigest()}", "files": files}


def _is_ignored_component_file(path: Path, root: Path) -> bool:
    rel_parts = path.relative_to(root).parts
    return "__pycache__" in rel_parts or path.suffix in {".pyc", ".pyo"}


def _locked_file_mode(path: Path) -> str:
    try:
        with path.open("rb") as handle:
            if handle.read(2) == b"#!":
                return "100755"
    except OSError:
        pass
    return "100644"


def _assert_tree_matches_lock(
    root: Path,
    entry: dict[str, Any],
    *,
    label: str,
    target_label: str = "materialized",
) -> None:
    expected_files = entry.get("files") or []
    actual = _hash_tree(root)
    expected_by_path = {item["path"]: item for item in expected_files}
    actual_by_path = {item["path"]: item for item in actual["files"]}
    for path, expected in expected_by_path.items():
        actual_file = actual_by_path.get(path)
        if actual_file is None:
            raise ComponentError(f"{label}: {target_label} file missing: {path}")
        if actual_file["sha256"] != expected["sha256"]:
            raise ComponentError(f"{label}: {target_label} file hash mismatch: {path}")
    unexpected = sorted(set(actual_by_path) - set(expected_by_path))
    if unexpected:
        raise ComponentError(f"{label}: {target_label} files not in lock: {unexpected}")
    expected_tree = entry.get("treeSha256")
    if actual["treeSha256"] != expected_tree:
        raise ComponentError(f"{label}: {target_label} tree hash mismatch")


def _sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _subprocess_error_tail(
    error: subprocess.CalledProcessError | subprocess.TimeoutExpired,
) -> str:
    if isinstance(error, subprocess.TimeoutExpired):
        return f"timeout after {error.timeout}s"

    stderr = error.stderr
    if isinstance(stderr, bytes):
        text = stderr.decode(errors="replace")
    else:
        text = str(stderr or "")
    tail = text.strip().splitlines()[-1][:300] if text.strip() else ""
    return tail or f"exit {error.returncode}"


def _canonical_json(data: dict[str, Any]) -> str:
    return json.dumps(data, indent=2, sort_keys=True, allow_nan=False) + "\n"


def _short_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def _display_path(path: Path, repo_root: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return str(path)


def _write_materialization_marker(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    marker = root / MATERIALIZATION_MARKER
    marker.write_text(
        _canonical_json({"generatedBy": "lib.agent_components", "markerVersion": 1}),
        encoding="utf-8",
    )


def _remove_materialized_target(source_dir: Path, target_dir: Path) -> None:
    if not target_dir.exists() and not target_dir.is_symlink():
        return
    if target_dir.is_symlink() or target_dir.is_file():
        _remove_path(target_dir)
        return
    marker = target_dir.parent / MATERIALIZATION_MARKER
    if not marker.exists() and _hash_tree(target_dir) != _hash_tree(source_dir):
        raise ComponentError(
            "refusing to replace unmarked materialization target: "
            f"{target_dir}. Move local edits aside or delete the directory before installing."
        )
    _remove_path(target_dir)


def _remove_path(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink()
    elif path.exists():
        shutil.rmtree(path)
