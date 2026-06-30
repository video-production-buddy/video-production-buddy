"""Base tool class implementing the expanded ToolContract.

Every tool in Video Production Buddy inherits from BaseTool. This enforces a uniform
interface for discovery, execution, cost estimation, and health reporting.
"""

from __future__ import annotations

import base64
import copy
import hashlib
import inspect
import json
import math
import os
import platform
import subprocess
import shutil
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, is_dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from fractions import Fraction
from pathlib import Path, PurePath
from typing import Any, Callable, Optional
from uuid import UUID


def _load_dotenv() -> None:
    """Load .env into os.environ once at import time.

    Delegates to the shared loader in lib/dotenv_loader.py.
    """
    from lib.dotenv_loader import load_dotenv as _load

    _load()


_load_dotenv()


class ToolTier(str, Enum):
    CORE = "core"
    VOICE = "voice"
    ENHANCE = "enhance"
    GENERATE = "generate"
    SOURCE = "source"
    ANALYZE = "analyze"
    PUBLISH = "publish"


class ToolStability(str, Enum):
    EXPERIMENTAL = "experimental"
    BETA = "beta"
    PRODUCTION = "production"


class ToolStatus(str, Enum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    DEGRADED = "degraded"


class ToolRuntime(str, Enum):
    """Where and how a tool executes."""
    LOCAL = "local"            # Runs entirely on-device, free, no network
    LOCAL_GPU = "local_gpu"    # Runs on-device but needs GPU (VRAM)
    API = "api"                # Calls an external API, requires API key, costs money
    HYBRID = "hybrid"          # Can run locally OR via API (e.g., image_selector)


class ExecutionMode(str, Enum):
    SYNC = "sync"
    ASYNC = "async"


class Determinism(str, Enum):
    DETERMINISTIC = "deterministic"
    SEEDED = "seeded"
    STOCHASTIC = "stochastic"


class ResumeSupport(str, Enum):
    NONE = "none"
    FROM_START = "from_start"
    FROM_CHECKPOINT = "from_checkpoint"


@dataclass
class ResourceProfile:
    """Hardware resource envelope for a tool."""
    cpu_cores: int = 1
    ram_mb: int = 512
    vram_mb: int = 0
    disk_mb: int = 100
    network_required: bool = False


@dataclass
class RetryPolicy:
    """Safe retry behavior for a tool."""
    max_retries: int = 0
    backoff_seconds: float = 1.0
    retryable_errors: list[str] = field(default_factory=list)


def _coerce_tool_status(value: Any) -> ToolStatus:
    """Normalize loose status values into the ToolStatus enum."""
    try:
        raw_value = getattr(value, "value", value)
    except Exception:
        return ToolStatus.DEGRADED
    try:
        return ToolStatus(str(raw_value))
    except (TypeError, ValueError):
        return ToolStatus.DEGRADED


def _json_safe_key(value: Any) -> Any:
    if isinstance(value, str):
        return value
    if isinstance(value, float) and not math.isfinite(value):
        return str(value)
    return str(value)


def _json_safe(value: Any) -> Any:
    if isinstance(value, PurePath):
        return str(value)
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, Decimal):
        return str(value) if value.is_finite() else None
    if isinstance(value, Fraction):
        return str(value)
    if isinstance(value, (bytes, bytearray, memoryview)):
        raw = bytes(value)
        return {
            "encoding": "base64",
            "data": base64.b64encode(raw).decode("ascii"),
            "size_bytes": len(raw),
        }
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, Enum):
        return _json_safe(value.value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if is_dataclass(value) and not isinstance(value, type):
        return {
            field_name: _json_safe(getattr(value, field_name))
            for field_name in value.__dataclass_fields__
        }
    if isinstance(value, dict):
        return {
            _json_safe_key(key): _json_safe(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, set):
        return [_json_safe(item) for item in sorted(value, key=repr)]
    return str(value)


@dataclass
class ToolResult:
    """Standard result returned by tool execution."""
    success: bool
    data: dict[str, Any] = field(default_factory=dict)
    artifacts: list[str] = field(default_factory=list)
    error: Optional[str] = None
    cost_usd: float = 0.0
    duration_seconds: float = 0.0
    seed: Optional[int] = None
    model: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-safe snapshot for checkpoint/report persistence."""
        return _json_safe(self)


class BaseTool(ABC):
    """Abstract base class for all Video Production Buddy tools."""

    _MUTABLE_CONTRACT_ATTRS = (
        "dependencies",
        "capabilities",
        "input_schema",
        "output_schema",
        "artifact_schema",
        "progress_schema",
        "supports",
        "best_for",
        "not_good_for",
        "model_options",
        "provider_matrix",
        "resource_profile",
        "retry_policy",
        "idempotency_key_fields",
        "side_effects",
        "fallback_tools",
        "agent_skills",
        "user_visible_verification",
    )

    # --- Identity (override in subclasses) ---
    name: str = ""
    version: str = "0.1.0"
    tier: ToolTier = ToolTier.CORE
    stability: ToolStability = ToolStability.EXPERIMENTAL
    execution_mode: ExecutionMode = ExecutionMode.SYNC
    determinism: Determinism = Determinism.DETERMINISTIC
    runtime: ToolRuntime = ToolRuntime.LOCAL

    # --- Dependencies ---
    # For API tools, add "env:ENVVAR_NAME" to signal required API keys
    dependencies: list[str] = []
    install_instructions: str = ""

    # --- Capabilities ---
    capability: str = "generic"
    provider: str = "video_production_buddy"
    capabilities: list[str] = []
    input_schema: dict = {"type": "object", "properties": {}}
    output_schema: dict = {"type": "object", "properties": {}}
    artifact_schema: dict = {}
    progress_schema: Optional[dict] = None
    supports: dict[str, Any] = {}
    best_for: list[str] = []
    not_good_for: list[str] = []
    model_options: list[dict[str, Any]] = []
    provider_matrix: dict[str, Any] = {}

    # --- Resource & retry ---
    resource_profile: ResourceProfile = ResourceProfile()
    retry_policy: RetryPolicy = RetryPolicy()

    # --- Resume & idempotency ---
    resume_support: ResumeSupport = ResumeSupport.NONE
    idempotency_key_fields: list[str] = []

    # --- Side effects & fallback ---
    side_effects: list[str] = []
    fallback: Optional[str] = None
    fallback_tools: list[str] = []

    # --- Agent skills (Layer 3 references) ---
    # Names of Layer 3 agent skills declared in .agents/components.yaml and
    # materialized under .agents/skills/. The orchestrator uses these to load
    # relevant API knowledge when planning tool usage.
    agent_skills: list[str] = []

    # --- Verification ---
    user_visible_verification: list[str] = []

    # --- Optional telemetry / quality hints for the scoring engine ---
    # If set (0.0-1.0), lib/scoring.py uses these directly instead of falling
    # back to stability-based heuristics. Leave unset unless the tool has a
    # real measured or well-calibrated value.
    quality_score: Optional[float] = None
    historical_success_rate: Optional[float] = None
    latency_p50_seconds: Optional[float] = None

    def __init__(self) -> None:
        for attr in self._MUTABLE_CONTRACT_ATTRS:
            descriptor = inspect.getattr_static(self.__class__, attr, None)
            if isinstance(descriptor, property):
                continue
            setattr(self, attr, copy.deepcopy(getattr(self.__class__, attr)))

    # ---- Status reporting ----

    def get_status(self) -> ToolStatus:
        """Check if this tool's dependencies are satisfied."""
        try:
            self.check_dependencies()
            return ToolStatus.AVAILABLE
        except DependencyError:
            return ToolStatus.UNAVAILABLE

    def check_dependencies(self) -> None:
        """Verify all dependencies are installed. Raises DependencyError if not."""
        for dep in self.dependencies:
            if dep.startswith("cmd:") or dep.startswith("binary:"):
                cmd_name = dep.split(":", 1)[1]
                if shutil.which(cmd_name) is None:
                    raise DependencyError(
                        f"Command {cmd_name!r} not found. {self.install_instructions}"
                    )
            elif dep.startswith("env:"):
                env_name = dep[4:]
                if not os.environ.get(env_name):
                    raise DependencyError(
                        f"Environment variable {env_name!r} not set. {self.install_instructions}"
                    )
            elif dep.startswith("env_any:"):
                groups = _parse_env_any_dependency(dep)
                if not groups:
                    raise DependencyError(
                        f"Malformed env_any dependency declaration {dep!r}."
                    )
                if not any(
                    all(os.environ.get(env_name) for env_name in group)
                    for group in groups
                ):
                    options = [
                        "+".join(group)
                        for group in groups
                    ]
                    raise DependencyError(
                        "At least one environment variable option must be set "
                        f"from {options!r}. {self.install_instructions}"
                    )
            elif dep.startswith("python:"):
                module_name = dep[7:]
                try:
                    __import__(module_name)
                except ImportError:
                    raise DependencyError(
                        f"Python module {module_name!r} not installed. {self.install_instructions}"
                    )
            else:
                raise DependencyError(
                    f"Unknown dependency declaration {dep!r}. "
                    "Use cmd:, binary:, env:, env_any:, or python: prefixes."
                )

    def get_info(self) -> dict[str, Any]:
        """Return full tool contract info for registry/discovery."""
        usage_location = inspect.getfile(self.__class__)
        status_error: str | None = None
        try:
            status = _coerce_tool_status(self.get_status())
        except Exception as exc:
            status = ToolStatus.DEGRADED
            status_error = f"{exc.__class__.__name__}: {exc}"
        info = {
            "name": self.name,
            "version": self.version,
            "tier": self.tier.value,
            "capability": self.capability,
            "provider": self.provider,
            "stability": self.stability.value,
            "status": status.value,
            "execution_mode": self.execution_mode.value,
            "determinism": self.determinism.value,
            "runtime": self.runtime.value,
            "module_path": self.__class__.__module__,
            "usage_location": usage_location,
            "dependencies": copy.deepcopy(self.dependencies),
            "install_instructions": self.install_instructions,
            "capabilities": copy.deepcopy(self.capabilities),
            "input_schema": copy.deepcopy(self.input_schema),
            "output_schema": copy.deepcopy(self.output_schema),
            "artifact_schema": copy.deepcopy(self.artifact_schema),
            "progress_schema": copy.deepcopy(self.progress_schema),
            "supports": copy.deepcopy(self.supports),
            "best_for": copy.deepcopy(self.best_for),
            "not_good_for": copy.deepcopy(self.not_good_for),
            "model_options": copy.deepcopy(self.model_options),
            "provider_matrix": copy.deepcopy(self.provider_matrix),
            "resource_profile": {
                "cpu_cores": self.resource_profile.cpu_cores,
                "ram_mb": self.resource_profile.ram_mb,
                "vram_mb": self.resource_profile.vram_mb,
                "disk_mb": self.resource_profile.disk_mb,
                "network_required": self.resource_profile.network_required,
            },
            "retry_policy": {
                "max_retries": self.retry_policy.max_retries,
                "backoff_seconds": self.retry_policy.backoff_seconds,
                "retryable_errors": copy.deepcopy(self.retry_policy.retryable_errors),
            },
            "resume_support": self.resume_support.value,
            "idempotency_key_fields": copy.deepcopy(self.idempotency_key_fields),
            "side_effects": copy.deepcopy(self.side_effects),
            "fallback": self.fallback,
            "fallback_tools": copy.deepcopy(
                self.fallback_tools or ([self.fallback] if self.fallback else [])
            ),
            "agent_skills": copy.deepcopy(self.agent_skills),
            "related_skills": copy.deepcopy(self.agent_skills),
            "user_visible_verification": copy.deepcopy(self.user_visible_verification),
            "quality_score": self.quality_score,
            "historical_success_rate": self.historical_success_rate,
            "latency_p50_seconds": self.latency_p50_seconds,
        }
        if status_error:
            info["status_error"] = status_error
        return _json_safe(info)

    # ---- Cost estimation ----

    def estimate_cost(self, inputs: dict[str, Any]) -> float:
        """Estimate cost in USD for the given inputs. Override for paid tools."""
        return 0.0

    def estimate_runtime(self, inputs: dict[str, Any]) -> float:
        """Estimate runtime in seconds. Override for long-running tools."""
        return 0.0

    @staticmethod
    def _safe_estimate(
        label: str,
        estimator: Callable[[dict[str, Any]], Any],
        inputs: dict[str, Any],
        errors: dict[str, str],
    ) -> Any:
        try:
            return estimator(inputs)
        except Exception as exc:
            errors[label] = f"{exc.__class__.__name__}: {exc}"
            return None

    # ---- Idempotency ----

    def idempotency_key(self, inputs: dict[str, Any]) -> str:
        """Compute a cache key from idempotency fields."""
        key_data = {k: inputs.get(k) for k in self.idempotency_key_fields}
        raw = json.dumps(_json_safe(key_data), sort_keys=True, allow_nan=False)
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    # ---- Execution ----

    @abstractmethod
    def execute(self, inputs: dict[str, Any]) -> ToolResult:
        """Run the tool. Subclasses must implement this."""
        ...

    def dry_run(self, inputs: dict[str, Any]) -> dict[str, Any]:
        """Preflight check without side effects. Override for paid/publishing tools."""
        status_error: str | None = None
        try:
            status = _coerce_tool_status(self.get_status())
        except Exception as exc:
            status = ToolStatus.DEGRADED
            status_error = f"{exc.__class__.__name__}: {exc}"
        estimate_errors: dict[str, str] = {}
        estimated_cost = self._safe_estimate(
            "estimated_cost_usd",
            self.estimate_cost,
            inputs,
            estimate_errors,
        )
        estimated_runtime = self._safe_estimate(
            "estimated_runtime_seconds",
            self.estimate_runtime,
            inputs,
            estimate_errors,
        )
        if estimate_errors and status == ToolStatus.AVAILABLE:
            status = ToolStatus.DEGRADED
        payload = {
            "tool": self.name,
            "estimated_cost_usd": estimated_cost,
            "estimated_runtime_seconds": estimated_runtime,
            "status": status.value,
            "would_execute": status == ToolStatus.AVAILABLE,
        }
        if status_error:
            payload["status_error"] = status_error
        if estimate_errors:
            payload["estimate_errors"] = estimate_errors
        return _json_safe(payload)

    # ---- CLI helper ----

    def run_command(
        self,
        cmd: list[str],
        *,
        timeout: Optional[int] = None,
        cwd: Optional[Path] = None,
    ) -> subprocess.CompletedProcess:
        """Run a subprocess command with standard error handling.

        On Windows, resolves .cmd/.bat wrappers (e.g. npx, npm) via
        shutil.which() so subprocess.run() can find them without shell=True.
        """
        resolved_cmd = list(cmd)
        if platform.system() == "Windows" and resolved_cmd:
            exe = shutil.which(resolved_cmd[0])
            if exe:
                resolved_cmd[0] = exe
        return subprocess.run(
            resolved_cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd,
            check=True,
        )


class DependencyError(Exception):
    """Raised when a tool's dependency is not satisfied."""
    pass


def _parse_env_any_dependency(dep: str) -> list[list[str]]:
    """Parse env_any: declarations into alternative env-var groups.

    Syntax examples:
    - env_any:FAL_KEY,FAL_AI_API_KEY means either variable is enough.
    - env_any:HIGGSFIELD_KEY,HIGGSFIELD_API_KEY+HIGGSFIELD_API_SECRET means
      either the combined key or the key+secret pair is enough.
    """
    raw = dep.split(":", 1)[1]
    groups: list[list[str]] = []
    for option in raw.replace("|", ",").split(","):
        group = [part.strip() for part in option.split("+") if part.strip()]
        if group:
            groups.append(group)
    return groups
