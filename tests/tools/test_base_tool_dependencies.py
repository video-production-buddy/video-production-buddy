from __future__ import annotations

from tools.base_tool import BaseTool, ToolResult, ToolRuntime, ToolStatus
from tools.tool_registry import ToolRegistry


class BinaryDependencyTool(BaseTool):
    name = "binary_dependency_tool"
    dependencies = ["binary:definitely-not-a-real-video-production-buddy-command"]

    def execute(self, inputs: dict) -> ToolResult:
        return ToolResult(success=True)


class UnknownDependencyTool(BaseTool):
    name = "unknown_dependency_tool"
    dependencies = ["unknown:definitely-not-real"]

    def execute(self, inputs: dict) -> ToolResult:
        return ToolResult(success=True)


class EnvAnyDependencyTool(BaseTool):
    name = "env_any_dependency_tool"
    dependencies = [
        "env_any:VIDEO_PRODUCTION_BUDDY_PRIMARY_TEST_KEY,VIDEO_PRODUCTION_BUDDY_SECONDARY_TEST_KEY"
    ]

    def execute(self, inputs: dict) -> ToolResult:
        return ToolResult(success=True)


class EnvAnySetupTool(BaseTool):
    name = "env_any_setup_tool"
    capability = "video_generation"
    provider = "env_any_provider"
    runtime = ToolRuntime.API
    dependencies = [
        "env_any:VIDEO_PRODUCTION_BUDDY_PRIMARY_TEST_KEY,VIDEO_PRODUCTION_BUDDY_SECONDARY_TEST_KEY"
    ]
    install_instructions = (
        "Set VIDEO_PRODUCTION_BUDDY_PRIMARY_TEST_KEY or VIDEO_PRODUCTION_BUDDY_SECONDARY_TEST_KEY "
        "to your API key."
    )

    def execute(self, inputs: dict) -> ToolResult:
        return ToolResult(success=True)


def test_binary_dependency_prefix_is_checked_like_command():
    assert BinaryDependencyTool().get_status() == ToolStatus.UNAVAILABLE


def test_unknown_dependency_prefix_is_unavailable():
    assert UnknownDependencyTool().get_status() == ToolStatus.UNAVAILABLE


def test_env_any_dependency_prefix_accepts_any_configured_option(monkeypatch):
    monkeypatch.delenv("VIDEO_PRODUCTION_BUDDY_PRIMARY_TEST_KEY", raising=False)
    monkeypatch.delenv("VIDEO_PRODUCTION_BUDDY_SECONDARY_TEST_KEY", raising=False)
    assert EnvAnyDependencyTool().get_status() == ToolStatus.UNAVAILABLE

    monkeypatch.setenv("VIDEO_PRODUCTION_BUDDY_SECONDARY_TEST_KEY", "secondary")
    assert EnvAnyDependencyTool().get_status() == ToolStatus.AVAILABLE


def test_api_tools_with_env_setup_instructions_declare_env_dependencies():
    registry = ToolRegistry()
    registry.discover()

    setup_markers = (
        "api key",
        "environment variable",
        "env var",
        "_key",
        "token",
        "secret",
        "credentials",
        "endpoint_url",
    )
    offenders = []
    for tool in registry._tools.values():
        install_instructions = tool.install_instructions or ""
        if "no api key" in install_instructions.lower():
            continue
        if tool.runtime != ToolRuntime.API:
            continue
        if not any(marker in install_instructions.lower() for marker in setup_markers):
            continue
        if not any(
            str(dep).startswith(("env:", "env_any:")) for dep in tool.dependencies
        ):
            offenders.append(tool.name)

    assert offenders == []


def test_alternate_api_key_providers_use_env_any_dependency_contract():
    registry = ToolRegistry()
    registry.discover()

    offenders = []
    for tool in registry._tools.values():
        env_deps = [dep for dep in tool.dependencies if str(dep).startswith("env:")]
        if len(env_deps) > 1:
            offenders.append((tool.name, env_deps))

    assert offenders == []


def test_provider_menu_setup_offers_include_env_dependencies():
    registry = ToolRegistry()
    registry.discover()

    summary = registry.provider_menu_summary()
    offenders = [
        offer["tool"]
        for offer in summary["setup_offers"]
        if not any(
            str(dep).startswith(("env:", "env_any:"))
            for dep in offer.get("dependencies", [])
        )
    ]

    assert offenders == []


def test_idempotency_key_fields_are_declared_in_input_schema():
    registry = ToolRegistry()
    registry.discover()

    offenders = []
    for tool in registry._tools.values():
        properties = (tool.input_schema or {}).get("properties") or {}
        if not properties:
            continue
        missing = [
            field
            for field in tool.idempotency_key_fields
            if field not in properties
        ]
        if missing:
            offenders.append((tool.name, missing))

    assert offenders == []


def test_output_schema_required_fields_are_declared_as_properties():
    registry = ToolRegistry()
    registry.discover()

    offenders = []
    for tool in registry._tools.values():
        required = tool.output_schema.get("required", [])
        if not required:
            continue
        properties = (tool.output_schema or {}).get("properties") or {}
        missing = [
            field
            for field in required
            if field not in properties
        ]
        if missing:
            offenders.append((tool.name, missing))

    assert offenders == []


def test_provider_menu_setup_offers_exclude_local_runtime_setup():
    registry = ToolRegistry()
    registry.discover()

    summary = registry.provider_menu_summary()
    local_runtime_offers = [
        offer["tool"]
        for offer in summary["setup_offers"]
        if registry.get(offer["tool"]).runtime
        not in {ToolRuntime.API, ToolRuntime.HYBRID}
    ]

    assert local_runtime_offers == []


def test_provider_menu_setup_offers_include_env_any_dependencies(monkeypatch):
    monkeypatch.delenv("VIDEO_PRODUCTION_BUDDY_PRIMARY_TEST_KEY", raising=False)
    monkeypatch.delenv("VIDEO_PRODUCTION_BUDDY_SECONDARY_TEST_KEY", raising=False)
    registry = ToolRegistry()
    registry.register(EnvAnySetupTool())
    registry._discovered_packages.add("tools")

    summary = registry.provider_menu_summary()

    assert summary["setup_offers"] == [
        {
            "capability": "video_generation",
            "tool": "env_any_setup_tool",
            "provider": "env_any_provider",
            "install_instructions": (
                "Set VIDEO_PRODUCTION_BUDDY_PRIMARY_TEST_KEY or "
                "VIDEO_PRODUCTION_BUDDY_SECONDARY_TEST_KEY to your API key."
            ),
            "dependencies": [
                "env_any:VIDEO_PRODUCTION_BUDDY_PRIMARY_TEST_KEY,VIDEO_PRODUCTION_BUDDY_SECONDARY_TEST_KEY"
            ],
        }
    ]


def test_tools_declare_best_for_provider_menu_context():
    registry = ToolRegistry()
    registry.discover()

    offenders = [
        tool.name
        for tool in registry._tools.values()
        if not tool.best_for
    ]

    assert offenders == []


def test_hybrid_tools_explain_setup_path():
    registry = ToolRegistry()
    registry.discover()

    offenders = [
        tool.name
        for tool in registry._tools.values()
        if tool.runtime == ToolRuntime.HYBRID and not tool.install_instructions
    ]

    assert offenders == []
