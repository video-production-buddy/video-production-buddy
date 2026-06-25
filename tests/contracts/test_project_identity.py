from __future__ import annotations

import re
import subprocess
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

LEGACY_PROPER = "Open" + "Montage"
LEGACY_LOWER = "open" + "montage"
LEGACY_UPPER = "OPEN" + "MONTAGE"
LEGACY_SPACED = "Open " + "Montage"

FORBIDDEN_PATTERNS = (
    re.compile(LEGACY_PROPER),
    re.compile(LEGACY_LOWER),
    re.compile(LEGACY_UPPER),
    re.compile(LEGACY_SPACED),
)

ALLOWED_LINE_PATTERNS = {
    "README.md": (
        re.compile(r"built from and adapted from \[" + LEGACY_PROPER + r"\]"),
        re.compile(
            r"Our code is based off the excellent \["
            + LEGACY_PROPER
            + r" codebase\]"
        ),
    ),
    "README.zh-CN.md": (
        re.compile(r"我们的代码基于优秀的 \[" + LEGACY_PROPER + r" codebase\]"),
    ),
    "tests/contracts/test_project_identity.py": (
        re.compile(r"LEGACY_"),
        re.compile(r"FORBIDDEN_PATTERNS"),
        re.compile(r"ALLOWED_LINE_PATTERNS"),
    ),
}


def _tracked_files() -> list[Path]:
    output = subprocess.check_output(["git", "ls-files"], cwd=PROJECT_ROOT, text=True)
    return [
        PROJECT_ROOT / path
        for path in output.splitlines()
        if (PROJECT_ROOT / path).is_file()
    ]


def _is_text_file(path: Path) -> bool:
    try:
        path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return False
    return True


def _line_is_allowed(relative_path: str, line: str) -> bool:
    return any(pattern.search(line) for pattern in ALLOWED_LINE_PATTERNS.get(relative_path, ()))


def test_project_owned_identity_is_video_production_buddy() -> None:
    violations: list[str] = []
    for path in _tracked_files():
        if not _is_text_file(path):
            continue
        relative_path = path.relative_to(PROJECT_ROOT).as_posix()
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if not any(pattern.search(line) for pattern in FORBIDDEN_PATTERNS):
                continue
            if _line_is_allowed(relative_path, line):
                continue
            violations.append(f"{relative_path}:{line_number}: {line.strip()}")

    assert violations == []
