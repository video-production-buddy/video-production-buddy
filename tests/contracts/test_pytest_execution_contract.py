from __future__ import annotations

import ast
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TESTS_DIR = ROOT / "tests"


def test_pytest_test_modules_do_not_define_script_entrypoints() -> None:
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


def test_pytest_test_module_run_guidance_uses_pytest_module_invocation() -> None:
    offenders: list[str] = []
    for path in sorted(TESTS_DIR.rglob("test_*.py")):
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            normalized = " ".join(line.strip().split())
            if "Run:" not in normalized:
                continue
            if "python tests/" in normalized or "python3 tests/" in normalized:
                offenders.append(f"{path.relative_to(ROOT)}:{lineno}: {normalized}")

    assert offenders == []


def test_markdown_pytest_command_examples_are_terminal_safe() -> None:
    offenders: list[str] = []
    paths_output = subprocess.check_output(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z", "*.md"],
        cwd=ROOT,
    )
    markdown_paths = [
        ROOT / raw.decode("utf-8")
        for raw in paths_output.split(b"\0")
        if raw
    ]

    for path in sorted(markdown_paths):
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
                offenders.append(
                    f"{path.relative_to(ROOT)}:{lineno}: missing {', '.join(missing)}"
                )

    assert offenders == []
