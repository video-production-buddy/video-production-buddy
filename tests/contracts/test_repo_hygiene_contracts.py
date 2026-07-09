from __future__ import annotations

import ast
import re
import runpy
import subprocess
from pathlib import Path
from typing import Any

import setuptools


ROOT = Path(__file__).resolve().parents[2]
TESTS_DIR = ROOT / "tests"

LEGACY_PROPER = "Open" + "Montage"
LEGACY_LOWER = "open" + "montage"
LEGACY_UPPER = "OPEN" + "MONTAGE"
LEGACY_SPACED = "Open " + "Montage"

FORBIDDEN_LEGACY_PATTERNS = (
    re.compile(LEGACY_PROPER),
    re.compile(LEGACY_LOWER),
    re.compile(LEGACY_UPPER),
    re.compile(LEGACY_SPACED),
)

ALLOWED_LEGACY_LINES = {
    "README.md": (
        re.compile(r"built on the open-source \[" + LEGACY_PROPER + r"\]"),
        re.compile(r"please also acknowledge " + LEGACY_PROPER),
        re.compile(r"@software\{calesthio2026" + LEGACY_LOWER + r","),
        re.compile(r"title = \{" + LEGACY_PROPER + r"\},"),
        re.compile(r"github\.com/calesthio/" + LEGACY_PROPER),
        re.compile(r"builds on the excellent \[" + LEGACY_PROPER + r"\]"),
    ),
    "README_zh-CN.md": (
        re.compile(r"织影基于开源项目 \[" + LEGACY_PROPER + r"\]"),
        re.compile(r"同时致谢 " + LEGACY_PROPER),
        re.compile(r"@software\{calesthio2026" + LEGACY_LOWER + r","),
        re.compile(r"title = \{" + LEGACY_PROPER + r"\},"),
        re.compile(r"github\.com/calesthio/" + LEGACY_PROPER),
        re.compile(r"本代码库基于优秀的 \[" + LEGACY_PROPER + r"\]"),
    ),
    "tests/contracts/test_repo_hygiene_contracts.py": (
        re.compile(r"LEGACY_"),
        re.compile(r"FORBIDDEN_LEGACY_PATTERNS"),
        re.compile(r"ALLOWED_LEGACY_LINES"),
    ),
}


def _setup_kwargs(monkeypatch) -> dict[str, Any]:
    captured: dict[str, Any] = {}

    def fake_setup(**kwargs: Any) -> None:
        captured.update(kwargs)

    monkeypatch.setattr(setuptools, "setup", fake_setup)
    runpy.run_path(str(ROOT / "setup.py"), run_name="__setup_contract__")
    return captured


def _git_visible_files(pattern: str = "*") -> list[Path]:
    output = subprocess.check_output(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z", pattern],
        cwd=ROOT,
    )
    return [
        path
        for raw in output.split(b"\0")
        if raw
        for path in [ROOT / raw.decode("utf-8")]
        if path.exists()
    ]


def _git_visible_text_files() -> list[Path]:
    files: list[Path] = []
    for path in _git_visible_files():
        if not path.is_file():
            continue
        data = path.read_bytes()
        if b"\0" not in data:
            files.append(path)
    return files


def _line_is_allowed(relative_path: str, line: str) -> bool:
    return any(pattern.search(line) for pattern in ALLOWED_LEGACY_LINES.get(relative_path, ()))


def test_public_onboarding_documents_safe_test_entrypoints() -> None:
    assert subprocess.run(["git", "check-ignore", "-q", ".venv/"], cwd=ROOT).returncode == 0

    requirements = (ROOT / "requirements-dev.txt").read_text(encoding="utf-8")
    assert "pytest" in requirements
    assert "setuptools" in requirements

    sections = {
        "README.md": "## Testing",
        "README_zh-CN.md": "## 测试",
    }
    for readme_name, header in sections.items():
        body = (ROOT / readme_name).read_text(encoding="utf-8")
        testing_section = body.split(header, 1)[1]
        assert "make install-dev" in testing_section
        assert "make test-contracts" in testing_section
        assert "make test-integration" in testing_section
        assert testing_section.index("make install-dev") < testing_section.index(
            "make test-contracts"
        )


def test_platform_wrappers_point_to_shared_contracts() -> None:
    for path in ("CLAUDE.md", "CURSOR.md", "COPILOT.md", "AGENTS.md"):
        contents = (ROOT / path).read_text(encoding="utf-8")
        assert "AGENT_GUIDE.md" in contents

    for path in ("CURSOR.md", "COPILOT.md", "AGENTS.md"):
        contents = (ROOT / path).read_text(encoding="utf-8")
        assert "PROJECT_CONTEXT.md" in contents


def test_project_owned_identity_is_video_production_buddy() -> None:
    violations: list[str] = []
    for path in _git_visible_text_files():
        relative_path = path.relative_to(ROOT).as_posix()
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if not any(pattern.search(line) for pattern in FORBIDDEN_LEGACY_PATTERNS):
                continue
            if _line_is_allowed(relative_path, line):
                continue
            violations.append(f"{relative_path}:{line_number}: {line.strip()}")

    assert violations == []


def test_git_visible_text_files_have_stable_line_endings() -> None:
    mixed: list[str] = []
    missing_final_newline: list[str] = []

    for path in _git_visible_text_files():
        data = path.read_bytes()
        crlf_count = data.count(b"\r\n")
        bare_lf_count = data.count(b"\n") - crlf_count
        relative = str(path.relative_to(ROOT))
        if crlf_count and bare_lf_count:
            mixed.append(relative)
        if data and not data.endswith(b"\n"):
            missing_final_newline.append(relative)

    assert mixed == []
    assert missing_final_newline == []


def test_setup_packages_runtime_code_without_tests(monkeypatch) -> None:
    kwargs = _setup_kwargs(monkeypatch)
    packages = set(kwargs["packages"])
    package_data = kwargs.get("package_data") or {}

    assert {"lib", "tools", "schemas", "styles", "pipeline_defs", "skills", "knowledge"} <= packages
    assert not any(package == "tests" or package.startswith("tests.") for package in packages)
    assert "**/*.json" in package_data.get("schemas", [])
    assert "*.yaml" in package_data.get("pipeline_defs", [])
    assert "*.yaml" in package_data.get("styles", [])
    assert "**/*.md" in package_data.get("skills", [])
    assert "ad-video/*.json" in package_data.get("knowledge", [])


def test_pytest_examples_are_terminal_safe() -> None:
    offenders: list[str] = []
    for path in sorted(_git_visible_files("*.md")):
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if "python -m pytest" not in line:
                continue
            command = " ".join(line.strip().split())
            missing: list[str] = []
            if "VPB_ALLOW_BROWSER_OPEN=0" not in command:
                missing.append("VPB_ALLOW_BROWSER_OPEN=0")
            if "PYTHONDONTWRITEBYTECODE=1" not in command:
                missing.append("PYTHONDONTWRITEBYTECODE=1")
            if " -p no:cacheprovider " not in f" {command} ":
                missing.append("-p no:cacheprovider")
            if missing:
                offenders.append(f"{path.relative_to(ROOT)}:{lineno}: missing {', '.join(missing)}")

    assert offenders == []


def test_test_modules_do_not_define_script_entrypoints() -> None:
    offenders: list[str] = []
    for path in sorted(TESTS_DIR.rglob("test_*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in tree.body:
            if not isinstance(node, ast.If):
                continue
            comparison = node.test
            if not isinstance(comparison, ast.Compare):
                continue
            if not (
                isinstance(comparison.left, ast.Name)
                and comparison.left.id == "__name__"
                and len(comparison.ops) == 1
                and isinstance(comparison.ops[0], ast.Eq)
                and len(comparison.comparators) == 1
                and isinstance(comparison.comparators[0], ast.Constant)
                and comparison.comparators[0].value == "__main__"
            ):
                continue
            offenders.append(f"{path.relative_to(ROOT)}:{node.lineno}")

    assert offenders == []


def test_contract_helpers_do_not_hide_collected_tests() -> None:
    helper_offenders: list[str] = []
    wildcard_offenders: list[str] = []

    for path in sorted((TESTS_DIR / "contracts").glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        relative = path.relative_to(ROOT).as_posix()

        if not path.name.startswith("test_"):
            for node in tree.body:
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_"):
                    helper_offenders.append(f"{relative}:{node.lineno}: {node.name}")
                if isinstance(node, ast.ClassDef) and node.name.startswith("Test"):
                    helper_offenders.append(f"{relative}:{node.lineno}: {node.name}")

        for node in tree.body:
            if (
                isinstance(node, ast.ImportFrom)
                and node.module
                and node.module.startswith("tests.contracts.")
                and any(alias.name == "*" for alias in node.names)
            ):
                wildcard_offenders.append(f"{relative}:{node.lineno}: {node.module}")

    assert helper_offenders == []
    assert wildcard_offenders == []
