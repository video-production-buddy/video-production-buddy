from __future__ import annotations

import runpy
from pathlib import Path
from typing import Any

import setuptools


REPO_ROOT = Path(__file__).resolve().parents[2]


def _setup_kwargs(monkeypatch) -> dict[str, Any]:
    captured: dict[str, Any] = {}

    def fake_setup(**kwargs: Any) -> None:
        captured.update(kwargs)

    monkeypatch.setattr(setuptools, "setup", fake_setup)
    runpy.run_path(str(REPO_ROOT / "setup.py"), run_name="__setup_contract__")
    return captured


def test_setup_packages_runtime_code_without_tests(monkeypatch):
    kwargs = _setup_kwargs(monkeypatch)
    packages = set(kwargs["packages"])

    assert {"lib", "tools", "schemas", "styles", "pipeline_defs", "skills", "knowledge"} <= packages
    assert not any(package == "tests" or package.startswith("tests.") for package in packages)


def test_setup_includes_runtime_data_files(monkeypatch):
    kwargs = _setup_kwargs(monkeypatch)
    package_data = kwargs.get("package_data") or {}

    assert "**/*.json" in package_data.get("schemas", [])
    assert "*.yaml" in package_data.get("pipeline_defs", [])
    assert "*.yaml" in package_data.get("styles", [])
    assert "**/*.md" in package_data.get("skills", [])
    assert "static/renderer/index.html" in package_data.get("lib.genui", [])
    assert "static/renderer/assets/*" in package_data.get("lib.genui", [])


def test_setup_includes_curated_ad_knowledge_cards(monkeypatch):
    kwargs = _setup_kwargs(monkeypatch)
    package_data = kwargs.get("package_data") or {}

    assert "ad-video/*.json" in package_data.get("knowledge", [])


def test_env_loader_is_self_contained_in_python_dependencies(monkeypatch):
    kwargs = _setup_kwargs(monkeypatch)
    install_requires = {
        requirement.split(";", 1)[0].strip().lower()
        for requirement in kwargs.get("install_requires", [])
    }
    requirements_txt = {
        line.strip().lower()
        for line in (REPO_ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    }
    architecture_doc = (REPO_ROOT / "docs" / "ARCHITECTURE.md").read_text(
        encoding="utf-8"
    ).lower()

    assert not any(req.startswith("python-dotenv") for req in install_requires)
    assert not any(req.startswith("python-dotenv") for req in requirements_txt)
    assert "python-dotenv" not in architecture_doc


def test_architecture_artifact_schema_counts_match_live_inventory():
    artifact_schema_count = len(
        list((REPO_ROOT / "schemas" / "artifacts").glob("*.schema.json"))
    )
    architecture_doc = (REPO_ROOT / "docs" / "ARCHITECTURE.md").read_text(
        encoding="utf-8"
    )

    assert f"{artifact_schema_count} artifact schemas" in architecture_doc
    assert (
        f"Artifact Schemas ({artifact_schema_count} types, all JSON-schema validated)"
        in architecture_doc
    )


def test_architecture_docs_mention_live_tool_packages():
    live_tool_packages = sorted(
        path.name
        for path in (REPO_ROOT / "tools").iterdir()
        if path.is_dir() and (path / "__init__.py").exists()
    )
    docs = {
        "PROJECT_CONTEXT.md": (REPO_ROOT / "PROJECT_CONTEXT.md").read_text(
            encoding="utf-8"
        ),
        "docs/ARCHITECTURE.md": (
            REPO_ROOT / "docs" / "ARCHITECTURE.md"
        ).read_text(encoding="utf-8"),
    }

    missing = {
        doc_name: [
            f"tools/{package}/"
            for package in live_tool_packages
            if f"tools/{package}/" not in contents
        ]
        for doc_name, contents in docs.items()
    }

    assert missing == {doc_name: [] for doc_name in docs}


def test_architecture_docs_keep_text_chat_tools_agent_routed():
    architecture_doc = (REPO_ROOT / "docs" / "ARCHITECTURE.md").read_text(
        encoding="utf-8"
    )

    assert "### 2. No Runtime LLM Orchestrator" in architecture_doc
    assert "must not auto-wire general chat models into" in architecture_doc
    assert "optional billed chat" in architecture_doc
    assert "`qwen_chat`, `minimax_chat`" in architecture_doc
    assert "announce the provider/model" in architecture_doc
    assert "does not call LLM APIs at runtime" not in architecture_doc


def test_setup_installs_genui_ag_ui_runtime_dependency(monkeypatch):
    kwargs = _setup_kwargs(monkeypatch)
    install_requires = {
        requirement.split(";", 1)[0].strip().lower()
        for requirement in kwargs.get("install_requires", [])
    }

    assert "ag-ui-protocol==0.1.19" in install_requires
