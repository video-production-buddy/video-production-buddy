from __future__ import annotations

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _git_visible_text_files() -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    files: list[Path] = []
    for raw_path in result.stdout.split(b"\0"):
        if not raw_path:
            continue
        path = ROOT / raw_path.decode()
        if not path.is_file():
            continue
        data = path.read_bytes()
        if b"\0" not in data:
            files.append(path)
    return files


def test_git_visible_text_files_do_not_mix_crlf_and_lf_endings() -> None:
    offenders: list[str] = []
    for path in _git_visible_text_files():
        data = path.read_bytes()
        crlf_count = data.count(b"\r\n")
        bare_lf_count = data.count(b"\n") - crlf_count
        if crlf_count and bare_lf_count:
            offenders.append(str(path.relative_to(ROOT)))

    assert offenders == []


def test_git_visible_text_files_end_with_newline() -> None:
    offenders: list[str] = []
    for path in _git_visible_text_files():
        data = path.read_bytes()
        if data and not data.endswith(b"\n"):
            offenders.append(str(path.relative_to(ROOT)))

    assert offenders == []
