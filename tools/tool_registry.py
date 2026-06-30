"""Tool registry with status, stability, and support-envelope reporting.

The registry discovers all registered tools, reports their availability,
and lets the orchestrator/agents query capabilities by tier, status, etc.
"""

from __future__ import annotations

import importlib
import inspect
import pkgutil
from collections.abc import Mapping
from types import ModuleType
from typing import Any, Optional

from tools.base_tool import (
    BaseTool,
    ToolStatus,
    ToolTier,
    ToolStability,
    _coerce_tool_status,
    _json_safe,
)


def _enum_value(value: Any) -> Any:
    return getattr(value, "value", value)


def _error_message(exc: Exception) -> str:
    return f"{exc.__class__.__name__}: {exc}"


def _safe_attr(tool: BaseTool, attr: str, default: Any) -> Any:
    try:
        return getattr(tool, attr)
    except Exception:
        return default


def _safe_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, Mapping):
        return []
    try:
        return list(value)
    except Exception:
        return []


def _safe_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    return {}


def _safe_optional_dict(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    return _safe_dict(value)


_LIST_INFO_FIELDS = (
    "dependencies",
    "capabilities",
    "best_for",
    "not_good_for",
    "model_options",
    "idempotency_key_fields",
    "side_effects",
    "fallback_tools",
    "agent_skills",
    "related_skills",
    "user_visible_verification",
)

_DICT_INFO_FIELDS = (
    "input_schema",
    "output_schema",
    "artifact_schema",
    "supports",
    "provider_matrix",
)


_MODEL_FIELD_NAMES = ("model_variant", "model_id", "model", "resource_id")


def _normalize_info_shape(info: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(info)
    for field in _LIST_INFO_FIELDS:
        normalized[field] = _safe_list(normalized.get(field))
    for field in _DICT_INFO_FIELDS:
        normalized[field] = _safe_dict(normalized.get(field))
    normalized["progress_schema"] = _safe_optional_dict(
        normalized.get("progress_schema")
    )

    retry_policy = _safe_dict(normalized.get("retry_policy"))
    if retry_policy:
        retry_policy["retryable_errors"] = _safe_list(
            retry_policy.get("retryable_errors")
        )
    normalized["retry_policy"] = retry_policy
    return normalized


def _schema_model_options(input_schema: Mapping[str, Any]) -> list[dict[str, Any]]:
    properties = input_schema.get("properties")
    if not isinstance(properties, Mapping):
        return []

    for field in _MODEL_FIELD_NAMES:
        prop = properties.get(field)
        if not isinstance(prop, Mapping):
            continue

        default = prop.get("default")
        description = prop.get("description")
        enum_values = prop.get("enum")
        if isinstance(enum_values, list) and enum_values:
            options: list[dict[str, Any]] = []
            for raw_value in enum_values:
                option: dict[str, Any] = {
                    "id": raw_value,
                    "field": field,
                    "default": raw_value == default,
                }
                if description:
                    option["description"] = description
                options.append(option)
            return options

        if default is not None:
            option = {
                "id": default,
                "field": field,
                "default": True,
            }
            if description:
                option["description"] = description
            return [option]

    return []


def _model_options_for_info(info: Mapping[str, Any]) -> list[dict[str, Any]]:
    explicit = _safe_list(info.get("model_options"))
    if explicit:
        return explicit
    return _schema_model_options(_safe_dict(info.get("input_schema")))


def _model_choice_field(options: list[dict[str, Any]]) -> str | None:
    for option in options:
        field = option.get("field")
        if field:
            return str(field)
    return None


def _model_choice_default(options: list[dict[str, Any]]) -> Any:
    for option in options:
        if option.get("default") is True:
            return option.get("id")
    defaults_by_operation = [
        option.get("id")
        for option in options
        if option.get("default_for_operations")
    ]
    if defaults_by_operation:
        return defaults_by_operation
    return None


# Unicode punctuation that breaks on Windows cp1252 stdout. Map each to an
# ASCII equivalent. This only touches strings rendered by registry helpers
# that an agent is likely to print to the user at preflight — not docstrings,
# comments, or markdown.
_UNICODE_DASH_REPLACEMENTS = {
    "\u2014": "--",   # em dash
    "\u2013": "-",    # en dash
    "\u2212": "-",    # minus sign
    "\u2018": "'",    # left single quote
    "\u2019": "'",    # right single quote
    "\u201c": '"',    # left double quote
    "\u201d": '"',    # right double quote
    "\u2026": "...",  # ellipsis
}


def _scrub_unicode_dashes(value: Any) -> Any:
    """Recursively normalize unicode punctuation in str leaves to ASCII.

    Used to keep `provider_menu_summary()` output readable on Windows cp1252
    stdout. Does NOT modify dict/list structure or non-string values.
    """
    if isinstance(value, str):
        out = value
        for needle, repl in _UNICODE_DASH_REPLACEMENTS.items():
            if needle in out:
                out = out.replace(needle, repl)
        return out
    if isinstance(value, list):
        return [_scrub_unicode_dashes(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_scrub_unicode_dashes(item) for item in value)
    if isinstance(value, dict):
        return {k: _scrub_unicode_dashes(v) for k, v in value.items()}
    return value


class ToolRegistry:
    """Central registry of all Video Production Buddy tools."""

    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}
        self._discovered_packages: set[str] = set()

    def register(self, tool: BaseTool) -> None:
        """Register a tool instance."""
        if not tool.name:
            raise ValueError("Tool must have a non-empty name")
        existing = self._tools.get(tool.name)
        if existing is not None and existing.__class__ is not tool.__class__:
            raise ValueError(
                f"Tool name {tool.name!r} is already registered by "
                f"{existing.__class__.__module__}.{existing.__class__.__name__}; "
                f"cannot also register {tool.__class__.__module__}.{tool.__class__.__name__}"
            )
        self._tools[tool.name] = tool

    def clear(self) -> None:
        """Clear registered tools and discovery state."""
        self._tools.clear()
        self._discovered_packages.clear()

    def register_module(self, module: ModuleType) -> list[str]:
        """Register all concrete BaseTool subclasses defined in a module."""
        registered: list[str] = []
        for _, cls in inspect.getmembers(module, inspect.isclass):
            if cls is BaseTool or not issubclass(cls, BaseTool):
                continue
            if cls.__module__ != module.__name__ or inspect.isabstract(cls):
                continue
            tool = cls()
            self.register(tool)
            registered.append(tool.name)
        return registered

    @staticmethod
    def _load_dotenv() -> None:
        """Load .env file into os.environ if present, so tools can find API keys."""
        from lib.dotenv_loader import load_dotenv as _load

        _load()

    def discover(self, package_name: str = "tools") -> list[str]:
        """Import a package tree and register any concrete tools it defines."""
        self._load_dotenv()
        package = importlib.import_module(package_name)
        discovered: list[str] = []
        package_paths = getattr(package, "__path__", None)
        if package_paths is None:
            return self.register_module(package)

        for module_info in pkgutil.walk_packages(package_paths, f"{package.__name__}."):
            if module_info.name.endswith(".base_tool") or module_info.name.endswith(".tool_registry"):
                continue
            module = importlib.import_module(module_info.name)
            discovered.extend(self.register_module(module))

        self._discovered_packages.add(package_name)
        return discovered

    def ensure_discovered(self, package_name: str = "tools") -> None:
        """Load tool modules once before reporting capabilities."""
        if package_name not in self._discovered_packages:
            self.discover(package_name)

    def get(self, name: str) -> Optional[BaseTool]:
        """Get a tool by name."""
        return self._tools.get(name)

    def list_all(self) -> list[str]:
        """List all registered tool names."""
        return list(self._tools.keys())

    def get_by_tier(self, tier: ToolTier) -> list[BaseTool]:
        """Get all tools in a given tier."""
        return [
            t for t in self._tools.values()
            if _safe_attr(t, "tier", None) == tier
        ]

    def get_by_capability(self, capability: str) -> list[BaseTool]:
        """Get all tools registered for a top-level capability family."""
        return [
            t for t in self._tools.values()
            if _safe_attr(t, "capability", None) == capability
        ]

    def get_by_provider(self, provider: str) -> list[BaseTool]:
        """Get all tools backed by a specific provider."""
        return [
            t for t in self._tools.values()
            if _safe_attr(t, "provider", None) == provider
        ]

    def get_by_status(self, status: ToolStatus) -> list[BaseTool]:
        """Get all tools with a given status."""
        return [t for t in self._tools.values() if self._tool_status(t)[0] == status]

    def get_available(self) -> list[BaseTool]:
        """Get all tools that are currently available."""
        return self.get_by_status(ToolStatus.AVAILABLE)

    def get_unavailable(self) -> list[BaseTool]:
        """Get all tools that are currently unavailable."""
        return self.get_by_status(ToolStatus.UNAVAILABLE)

    def get_by_stability(self, stability: ToolStability) -> list[BaseTool]:
        """Get all tools at a given stability level."""
        return [
            t for t in self._tools.values()
            if _safe_attr(t, "stability", None) == stability
        ]

    def find_by_capability(self, capability: str) -> list[BaseTool]:
        """Find tools that declare a given capability."""
        return [
            t for t in self._tools.values()
            if capability in (_safe_attr(t, "capabilities", []) or [])
        ]

    def find_fallback(self, tool_name: str) -> Optional[BaseTool]:
        """Find the fallback tool for a given tool, if declared and available."""
        tool = self.get(tool_name)
        if tool is None:
            return None
        candidates = list(tool.fallback_tools or [])
        if tool.fallback and tool.fallback not in candidates:
            candidates.append(tool.fallback)
        for name in candidates:
            fb = self.get(name)
            if fb and self._tool_status(fb)[0] == ToolStatus.AVAILABLE:
                return fb
        return None

    def _tool_status(self, tool: BaseTool) -> tuple[ToolStatus, str | None]:
        try:
            return _coerce_tool_status(tool.get_status()), None
        except Exception as exc:
            return ToolStatus.DEGRADED, _error_message(exc)

    def _fallback_info(
        self,
        tool: BaseTool,
        error: Exception | None,
    ) -> dict[str, Any]:
        status, status_error = self._tool_status(tool)
        if status_error is None and error is not None:
            status_error = _error_message(error)

        usage_location: str | None
        try:
            usage_location = inspect.getfile(tool.__class__)
        except Exception:
            usage_location = None

        resource_profile = _safe_attr(tool, "resource_profile", None)
        retry_policy = _safe_attr(tool, "retry_policy", None)
        fallback = _safe_attr(tool, "fallback", None)
        fallback_tools = _safe_list(_safe_attr(tool, "fallback_tools", []))
        if fallback and fallback not in fallback_tools:
            fallback_tools.append(fallback)

        info = {
            "name": _safe_attr(tool, "name", tool.__class__.__name__),
            "version": _safe_attr(tool, "version", "unknown"),
            "tier": _enum_value(_safe_attr(tool, "tier", ToolTier.CORE)),
            "capability": _safe_attr(tool, "capability", "generic"),
            "provider": _safe_attr(tool, "provider", "unknown"),
            "stability": _enum_value(
                _safe_attr(tool, "stability", ToolStability.EXPERIMENTAL)
            ),
            "status": status.value,
            "status_error": status_error,
            "execution_mode": _enum_value(_safe_attr(tool, "execution_mode", "unknown")),
            "determinism": _enum_value(_safe_attr(tool, "determinism", "unknown")),
            "runtime": _enum_value(_safe_attr(tool, "runtime", "unknown")),
            "module_path": tool.__class__.__module__,
            "usage_location": usage_location,
            "dependencies": _safe_list(_safe_attr(tool, "dependencies", [])),
            "install_instructions": _safe_attr(tool, "install_instructions", ""),
            "capabilities": _safe_list(_safe_attr(tool, "capabilities", [])),
            "input_schema": _safe_dict(_safe_attr(tool, "input_schema", {})),
            "output_schema": _safe_dict(_safe_attr(tool, "output_schema", {})),
            "artifact_schema": _safe_dict(_safe_attr(tool, "artifact_schema", {})),
            "progress_schema": _safe_optional_dict(
                _safe_attr(tool, "progress_schema", None)
            ),
            "supports": _safe_dict(_safe_attr(tool, "supports", {})),
            "best_for": _safe_list(_safe_attr(tool, "best_for", [])),
            "not_good_for": _safe_list(_safe_attr(tool, "not_good_for", [])),
            "model_options": _safe_list(_safe_attr(tool, "model_options", [])),
            "provider_matrix": _safe_dict(_safe_attr(tool, "provider_matrix", {})),
            "resource_profile": {
                "cpu_cores": _safe_attr(resource_profile, "cpu_cores", 0),
                "ram_mb": _safe_attr(resource_profile, "ram_mb", 0),
                "vram_mb": _safe_attr(resource_profile, "vram_mb", 0),
                "disk_mb": _safe_attr(resource_profile, "disk_mb", 0),
                "network_required": _safe_attr(resource_profile, "network_required", False),
            },
            "retry_policy": {
                "max_retries": _safe_attr(retry_policy, "max_retries", 0),
                "backoff_seconds": _safe_attr(retry_policy, "backoff_seconds", 0),
                "retryable_errors": _safe_list(
                    _safe_attr(retry_policy, "retryable_errors", [])
                ),
            },
            "resume_support": _enum_value(_safe_attr(tool, "resume_support", "unknown")),
            "idempotency_key_fields": _safe_list(
                _safe_attr(tool, "idempotency_key_fields", [])
            ),
            "side_effects": _safe_list(_safe_attr(tool, "side_effects", [])),
            "fallback": fallback,
            "fallback_tools": fallback_tools,
            "agent_skills": _safe_list(_safe_attr(tool, "agent_skills", [])),
            "related_skills": _safe_list(_safe_attr(tool, "agent_skills", [])),
            "user_visible_verification": _safe_list(
                _safe_attr(tool, "user_visible_verification", [])
            ),
            "quality_score": _safe_attr(tool, "quality_score", None),
            "historical_success_rate": _safe_attr(tool, "historical_success_rate", None),
            "latency_p50_seconds": _safe_attr(tool, "latency_p50_seconds", None),
        }
        return _json_safe(info)

    def _tool_info(self, tool: BaseTool) -> dict[str, Any]:
        try:
            info = tool.get_info()
            if not isinstance(info, dict):
                raise TypeError(
                    f"get_info returned {type(info).__name__}, expected dict"
                )
            defaults = self._fallback_info(tool, None)
            defaults.update(info)
            normalized = _normalize_info_shape(defaults)
            if not normalized.get("model_options"):
                normalized["model_options"] = _schema_model_options(
                    normalized.get("input_schema", {})
                )
            return _json_safe(normalized)
        except Exception as exc:
            return self._fallback_info(tool, exc)

    def support_envelope(self) -> dict[str, Any]:
        """Generate a full support-envelope report for all tools.

        Returns a dict mapping tool name to its contract info + live status.
        This is the primary report the orchestrator uses to understand
        what the system can and cannot do.
        """
        self.ensure_discovered()
        report: dict[str, Any] = {}
        for name, tool in self._tools.items():
            info = self._tool_info(tool)
            report[name] = info
        return report

    def capability_catalog(self) -> dict[str, list[dict[str, Any]]]:
        """Group the support envelope by top-level capability."""
        self.ensure_discovered()
        grouped: dict[str, list[dict[str, Any]]] = {}
        for tool in self._tools.values():
            info = self._tool_info(tool)
            grouped.setdefault(info["capability"], []).append(info)
        for items in grouped.values():
            items.sort(key=lambda item: (item["provider"], item["name"]))
        return dict(sorted(grouped.items()))

    def provider_catalog(self) -> dict[str, list[dict[str, Any]]]:
        """Group the support envelope by provider."""
        self.ensure_discovered()
        grouped: dict[str, list[dict[str, Any]]] = {}
        for tool in self._tools.values():
            info = self._tool_info(tool)
            grouped.setdefault(info["provider"], []).append(info)
        for items in grouped.values():
            items.sort(key=lambda item: (item["capability"], item["name"]))
        return dict(sorted(grouped.items()))

    def tier_summary(self) -> dict[str, dict[str, int]]:
        """Summarize tool counts by tier and status.

        Returns:
            {"core": {"available": 5, "unavailable": 2, "degraded": 0}, ...}
        """
        summary: dict[str, dict[str, int]] = {}
        for tier in ToolTier:
            tier_tools = self.get_by_tier(tier)
            counts = {"available": 0, "unavailable": 0, "degraded": 0}
            for t in tier_tools:
                status = self._tool_status(t)[0].value
                counts[status] = counts.get(status, 0) + 1
            if tier_tools:
                summary[tier.value] = counts
        return summary

    def provider_menu(self) -> dict[str, dict[str, Any]]:
        """Generate a capability-grouped provider menu for user-facing display.

        Returns a dict like:
        {
            "video_generation": {
                "available": [{"name": ..., "provider": ..., "best_for": ...}],
                "unavailable": [{"name": ..., "provider": ..., "install_instructions": ...}],
                "total": 12,
                "configured": 2,
            },
            ...
        }

        This powers the agent's preflight provider menu — the agent reads this
        output and presents it to the user.  Adding a new tool to tools/ is
        enough; this method auto-discovers it.
        """
        self.ensure_discovered()
        menu: dict[str, dict[str, Any]] = {}

        for tool in self._tools.values():
            info = self._tool_info(tool)
            # Skip selectors — they aggregate, they aren't providers themselves.
            if info.get("provider") == "selector":
                continue

            cap = str(info.get("capability") or "generic")
            if cap not in menu:
                menu[cap] = {"available": [], "unavailable": [], "total": 0, "configured": 0}

            try:
                status = ToolStatus(str(info.get("status")))
            except ValueError:
                status = ToolStatus.DEGRADED
            entry = {
                "name": info["name"],
                "provider": info["provider"],
                "runtime": info["runtime"],
                "best_for": info["best_for"],
                "install_instructions": info["install_instructions"],
                "dependencies": info.get("dependencies", []),
                "status": status.value,
            }
            model_options = _model_options_for_info(info)
            if model_options:
                entry["model_options"] = model_options
            if info.get("status_error"):
                entry["status_error"] = info["status_error"]
            for extra_key in (
                "source_provider_menu",
                "source_provider_summary",
                "render_engines",
                "remotion_note",
                "provider_matrix",
                "setup_offer",
                "operation_statuses",
                "resource_profiles",
                "resource_profile_note",
            ):
                if extra_key in info:
                    entry[extra_key] = info[extra_key]

            if status == ToolStatus.AVAILABLE:
                menu[cap]["available"].append(entry)
                menu[cap]["configured"] += 1
            else:
                menu[cap]["unavailable"].append(entry)
            menu[cap]["total"] += 1

        for bucket in menu.values():
            bucket["available"].sort(key=lambda entry: (entry["provider"], entry["name"]))
            bucket["unavailable"].sort(key=lambda entry: (entry["provider"], entry["name"]))

        return dict(sorted(menu.items()))

    def provider_menu_summary(self) -> dict[str, Any]:
        """Compact, human-ready rollup of provider_menu() for onboarding/preflight.

        Returns a dict shaped for the "N of M configured" capability menu the
        agent is supposed to present to the user per AGENT_GUIDE.md → "Provider
        Menu (Mandatory at Preflight)". Collapses the firehose of
        support_envelope() into something the agent can paraphrase in plain
        language in a few lines.

        Example output (abbreviated):
        {
          "composition_runtimes": {
            "ffmpeg": True,
            "remotion": True,
            "hyperframes": True,
          },
          "capabilities": [
            {"capability": "video_generation", "configured": 10, "total": 16,
             "available_providers": ["fal", "heygen", ...],
             "unavailable_providers": ["openai", ...]},
            ...
          ],
          "setup_offers": [
             {"capability": "music_generation", "tool": "suno_music",
              "install_instructions": "Add SUNO_API_KEY to .env"},
             ...
          ],
          "runtime_warnings": [
             "hyperframes: npm package `hyperframes` not resolvable: ...",
             ...
          ],
        }

        Agents should use this as the source for the preflight capability
        menu rather than rendering `support_envelope()` or `provider_menu()`
        raw. See AGENT_GUIDE.md > "Provider Menu (Mandatory at Preflight)".
        """
        self.ensure_discovered()
        menu = self.provider_menu()

        # Composition runtimes — lift from video_compose.get_info() since
        # they're the signal the runtime-selection contract depends on.
        comp_runtimes: dict[str, bool] = {}
        runtime_warnings: list[str] = []
        vc = self._tools.get("video_compose")
        if vc is not None:
            info = self._tool_info(vc)
            engines = info.get("render_engines") or {}
            comp_runtimes = {k: bool(v) for k, v in engines.items()}
        # If hyperframes_compose is registered, surface its npm-resolve reasons
        # explicitly — those are the "looks available but isn't" failures.
        hf = self._tools.get("hyperframes_compose")
        if hf is not None:
            hf_info = self._tool_info(hf)
            rc = hf_info.get("hyperframes_runtime") or {}
            for reason in rc.get("reasons") or []:
                runtime_warnings.append(f"hyperframes: {reason}")

        # Capabilities rollup (configured/total + provider lists).
        # When a provider has multiple tools (e.g. seedance-fal and
        # seedance-replicate both reporting provider="seedance"), a
        # naive set-split shows the provider in BOTH available and
        # unavailable — confusing for users. Dedupe: if the provider has
        # any available tool, do NOT list it as unavailable.
        capabilities: list[dict[str, Any]] = []
        for cap, bucket in menu.items():
            available_providers = {
                e.get("provider") for e in bucket.get("available", [])
            } - {None}
            unavailable_providers = (
                {e.get("provider") for e in bucket.get("unavailable", [])}
                - {None}
                - available_providers  # provider with any available tool wins
            )
            capabilities.append(
                {
                    "capability": cap,
                    "configured": bucket.get("configured", 0),
                    "total": bucket.get("total", 0),
                    "available_providers": sorted(available_providers),
                    "unavailable_providers": sorted(unavailable_providers),
                }
            )

        # Model choices — keep explicit provider/model variants visible in the
        # same preflight payload users already inspect after setting API keys.
        model_choices: list[dict[str, Any]] = []
        for cap, bucket in menu.items():
            entries = list(bucket.get("available", [])) + list(
                bucket.get("unavailable", [])
            )
            for entry in entries:
                options = _safe_list(entry.get("model_options"))
                if not options:
                    continue
                choice: dict[str, Any] = {
                    "capability": cap,
                    "tool": entry.get("name"),
                    "provider": entry.get("provider"),
                    "status": entry.get("status"),
                    "field": _model_choice_field(options),
                    "default": _model_choice_default(options),
                    "options": options,
                }
                model_choices.append(choice)
        model_choices.sort(
            key=lambda choice: (
                str(choice.get("capability") or ""),
                str(choice.get("provider") or ""),
                str(choice.get("tool") or ""),
            )
        )

        # Setup offers — unavailable tools that would be 1-minute env-var fixes.
        # Filter for short install instructions referencing an env var so the
        # agent can lead with the easy wins.
        setup_offers: list[dict[str, Any]] = []
        for cap, bucket in menu.items():
            for entry in bucket.get("unavailable", []):
                offer = entry.get("setup_offer")
                if offer:
                    setup_offers.append(
                        {
                            "capability": cap,
                            "tool": entry.get("name"),
                            "provider": entry.get("provider"),
                            "runtime": entry.get("runtime"),
                            "install_instructions": entry.get("install_instructions") or "",
                            **offer,
                        }
                    )
                    continue

                env_vars = [
                    dep[4:]
                    for dep in entry.get("dependencies", [])
                    if isinstance(dep, str) and dep.startswith("env:")
                ]
                if env_vars:
                    setup_offers.append(
                        {
                            "capability": cap,
                            "tool": entry.get("name"),
                            "provider": entry.get("provider"),
                            "runtime": entry.get("runtime"),
                            "kind": "env_var",
                            "fix_complexity": "1-minute env-var",
                            "env_vars": env_vars,
                            "install_instructions": entry.get("install_instructions") or "",
                        }
                    )
                    continue

                hint = entry.get("install_instructions") or ""
                dependencies = entry.get("dependencies", [])
                env_dependencies = [
                    dep
                    for dep in dependencies
                    if str(dep).startswith(("env:", "env_any:"))
                ]
                # Heuristic: 1-minute fixes mention an env var or API key.
                if (
                    entry.get("runtime") in {"api", "hybrid"}
                    and env_dependencies
                    and any(
                        k in hint.lower()
                        for k in ["api key", "env", "_key=", "_api"]
                    )
                ):
                    setup_offers.append(
                        {
                            "capability": cap,
                            "tool": entry.get("name"),
                            "provider": entry.get("provider"),
                            "runtime": entry.get("runtime"),
                            "install_instructions": hint,
                            "dependencies": dependencies,
                        }
                    )

            for entry in bucket.get("available", []) + bucket.get("unavailable", []):
                if entry.get("resource_profile_note"):
                    runtime_warnings.append(
                        f"{entry.get('name')}: {entry.get('resource_profile_note')}"
                    )

        result = {
            "composition_runtimes": comp_runtimes,
            "capabilities": capabilities,
            "model_choices": model_choices,
            "setup_offers": setup_offers,
            "runtime_warnings": runtime_warnings,
        }
        # Normalize em-dashes and en-dashes to ASCII so preflight output prints
        # cleanly on Windows cp1252 stdout (the default on Git Bash / PowerShell
        # without PYTHONIOENCODING=utf-8). Agents paste this dict into chat; a
        # mojibake `�` in an install_instructions string looks like a bug.
        # Markdown docs keep their typographic dashes; this only touches the
        # runtime-reported strings.
        return _scrub_unicode_dashes(result)

    # Post-hoc fix: narrow helper that keeps the registry output stdout-safe on
    # Windows cp1252 without imposing a new style rule on every tool author.

    def gpu_required_tools(self) -> list[str]:
        """List tools that require GPU (VRAM > 0)."""
        return [
            t.name for t in self._tools.values()
            if _safe_attr(_safe_attr(t, "resource_profile", None), "vram_mb", 0) > 0
        ]

    def network_required_tools(self) -> list[str]:
        """List tools that require network access."""
        return [
            t.name for t in self._tools.values()
            if _safe_attr(
                _safe_attr(t, "resource_profile", None),
                "network_required",
                False,
            )
        ]


# Singleton registry instance
registry = ToolRegistry()
