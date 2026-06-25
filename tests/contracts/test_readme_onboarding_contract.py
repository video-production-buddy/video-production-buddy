"""Contracts for the public README onboarding path."""

from __future__ import annotations

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_documented_virtualenv_directory_is_ignored() -> None:
    result = subprocess.run(
        ["git", "check-ignore", "-q", ".venv"],
        cwd=ROOT,
        check=False,
    )

    assert result.returncode == 0


def test_dev_requirements_include_test_collection_dependencies() -> None:
    requirements = (ROOT / "requirements-dev.txt").read_text(encoding="utf-8")

    assert "pytest" in requirements
    assert "setuptools" in requirements


def test_readmes_document_dev_install_before_test_commands() -> None:
    headers = {
        "README.md": "## Testing",
        "README.zh-CN.md": "## 测试",
    }
    for readme_name, header in headers.items():
        body = (ROOT / readme_name).read_text(encoding="utf-8")
        testing_section = body.split(header, 1)[1]

        assert "make install-dev" in testing_section
        assert testing_section.index("make install-dev") < testing_section.index(
            "make test-contracts"
        )
