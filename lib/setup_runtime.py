"""Cross-platform helpers for the first-run setup path."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _which(command: str) -> str | None:
    return shutil.which(command)


def _run(command: list[str], *, cwd: Path | None = None, check: bool = True) -> int:
    result = subprocess.run(command, cwd=cwd, check=False)
    if check and result.returncode != 0:
        raise SystemExit(result.returncode)
    return result.returncode


def install_remotion() -> int:
    workdir = ROOT / "remotion-composer"
    lockfile = workdir / "pnpm-lock.yaml"

    if lockfile.is_file():
        print("Using pnpm-lock.yaml for Remotion dependencies...")
        pnpm = _which("pnpm")
        corepack = _which("corepack")
        npx = _which("npx")
        if pnpm:
            command = [pnpm, "install", "--frozen-lockfile"]
        elif corepack:
            command = [corepack, "pnpm", "install", "--frozen-lockfile"]
        elif npx:
            command = [npx, "--yes", "pnpm", "install", "--frozen-lockfile"]
        else:
            print("npm/npx was not found. Install Node.js 22+ and reopen the terminal.")
            return 1
    else:
        npm = _which("npm")
        if not npm:
            print("npm was not found. Install Node.js 22+ and reopen the terminal.")
            return 1
        command = [npm, "install"]

    return _run(command, cwd=workdir)


def install_piper() -> int:
    command = [sys.executable, "-m", "pip", "install", "piper-tts"]
    if _run(command, check=False) == 0:
        return 0
    print("  [skip] piper-tts install failed - TTS will use cloud providers instead")
    return 0


def warm_hyperframes() -> int:
    npx = _which("npx")
    if not npx:
        print("  [skip] HyperFrames cache-warm failed - npx unavailable")
        return 0

    result = subprocess.run(
        [npx, "--yes", "hyperframes", "--version"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if result.returncode == 0:
        print("    HyperFrames CLI cached (npx)")
    else:
        print(
            "  [skip] HyperFrames cache-warm failed - offline or npm unavailable; "
            "first render will fetch on demand"
        )
    return 0


def check_hyperframes() -> int:
    try:
        from tools.video.hyperframes_compose import HyperFramesCompose

        HyperFramesCompose._npm_resolve_cache = None
        check = HyperFramesCompose()._runtime_check()
        package = check.get("npm_package_version") or check.get("npm_resolve_error")
        print(f"    HyperFrames runtime_available={check['runtime_available']}, npm={package}")
        for reason in check["reasons"]:
            print(f"    note: {reason}")
    except Exception as exc:  # pragma: no cover - defensive setup helper
        print(f"  [skip] HyperFrames check failed - runtime can be set up later: {exc}")
    return 0


def ensure_env() -> int:
    env_path = ROOT / ".env"
    example_path = ROOT / ".env.example"
    if env_path.exists():
        print("==> .env already exists - skipping.")
        return 0
    shutil.copy(example_path, env_path)
    print("==> Created .env from .env.example - add your API keys there.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=[
            "install-remotion",
            "install-piper",
            "warm-hyperframes",
            "check-hyperframes",
            "ensure-env",
        ],
    )
    args = parser.parse_args(argv)

    os.chdir(ROOT)
    return {
        "install-remotion": install_remotion,
        "install-piper": install_piper,
        "warm-hyperframes": warm_hyperframes,
        "check-hyperframes": check_hyperframes,
        "ensure-env": ensure_env,
    }[args.command]()


if __name__ == "__main__":
    raise SystemExit(main())
