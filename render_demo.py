"""Render the curated zero-key Remotion demos.

This script is Remotion-specific by design — the demos live in
`remotion-composer/public/demo-props/` as JSON props for existing React
scene components. It is NOT a cross-runtime demo harness.

For a HyperFrames demo, run `make hyperframes-doctor` to verify the runtime
floor, then either scaffold a real composition via `npx hyperframes init`
or drive `hyperframes_compose` from the Agent SDK. HyperFrames demos are
authored as HTML + GSAP in a project workspace, not as JSON props here.
"""

from __future__ import annotations

import argparse
import errno
import json
import re
import shutil
import socket
import subprocess
import sys
import zipfile
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent
COMPOSER_DIR = ROOT_DIR / "remotion-composer"
PROPS_DIR = COMPOSER_DIR / "public" / "demo-props"
OUTPUT_DIR = ROOT_DIR / "projects" / "demos" / "renders"
DEMO_PORT_START = 20_000
DEMO_PORT_END = 32_767

LOCAL_MEDIA_FIELDS = {
    "audioSrc",
    "backgroundImage",
    "backgroundVideo",
    "image",
    "imageSrc",
    "musicSrc",
    "poster",
    "productImage",
    "source",
    "src",
    "videoSrc",
}
REMOTE_OR_INLINE_PREFIXES = ("http://", "https://", "data:")
IPV6_PORT_TEST_HOSTS = ("::1", "::")
IPV4_PORT_TEST_HOSTS = ("127.0.0.1", "0.0.0.0")
REMOTION_BROWSER_VERSION_RE = re.compile(r"-(\d+\.\d+\.\d+\.\d+)\.zip")


def discover_demos() -> dict[str, Path]:
    if not PROPS_DIR.exists():
        return {}
    return {path.stem: path for path in sorted(PROPS_DIR.glob("*.json"))}


def find_command(*names: str) -> str | None:
    for name in names:
        resolved = shutil.which(name)
        if resolved:
            return resolved
    return None


def install_composer_dependencies(npx_cmd: str) -> None:
    print("Installing Remotion dependencies...")

    if (COMPOSER_DIR / "pnpm-lock.yaml").exists():
        pnpm_cmd = find_command("pnpm", "pnpm.cmd", "pnpm.exe")
        if pnpm_cmd:
            command = [pnpm_cmd, "install", "--frozen-lockfile"]
        else:
            corepack_cmd = find_command("corepack", "corepack.cmd", "corepack.exe")
            if corepack_cmd:
                command = [corepack_cmd, "pnpm", "install", "--frozen-lockfile"]
            else:
                command = [npx_cmd, "--yes", "pnpm", "install", "--frozen-lockfile"]
    else:
        npm_cmd = find_command("npm.cmd", "npm", "npm.exe")
        if not npm_cmd:
            raise SystemExit("Error: npm is required to install Remotion dependencies.")
        command = [npm_cmd, "install"]

    subprocess.run(command, cwd=COMPOSER_DIR, check=True)


def ensure_demo_environment() -> str:
    if not find_command("node", "node.exe"):
        raise SystemExit("Error: Node.js is required. Install it from https://nodejs.org/")

    npx_cmd = find_command("npx", "npx.cmd", "npx.exe")
    if not npx_cmd:
        raise SystemExit("Error: npx is required but was not found on PATH.")

    if not (COMPOSER_DIR / "node_modules").exists():
        install_composer_dependencies(npx_cmd)

    return npx_cmd


def _socket_family(host: str) -> socket.AddressFamily:
    return socket.AF_INET6 if ":" in host else socket.AF_INET


def _can_bind_host(host: str, port: int) -> bool:
    family = _socket_family(host)
    try:
        with socket.socket(family, socket.SOCK_STREAM) as server:
            server.bind((host, port))
    except OSError as exc:
        if family == socket.AF_INET6 and exc.errno in {
            errno.EAFNOSUPPORT,
            errno.EADDRNOTAVAIL,
            errno.EPROTONOSUPPORT,
        }:
            return True
        return False
    return True


def _port_test_hosts() -> tuple[str, ...]:
    ipv6_hosts = tuple(
        host for host in IPV6_PORT_TEST_HOSTS if socket.has_ipv6 and _can_bind_host(host, 0)
    )
    return (*ipv6_hosts, *IPV4_PORT_TEST_HOSTS)


def _can_bind_remotion_hosts(port: int) -> bool:
    return all(_can_bind_host(host, port) for host in _port_test_hosts())


def find_free_port() -> int:
    for port in range(DEMO_PORT_START, DEMO_PORT_END + 1):
        if _can_bind_remotion_hosts(port):
            return port
    raise SystemExit(
        f"Error: No free Remotion demo port found in {DEMO_PORT_START}-{DEMO_PORT_END}."
    )


def _format_json_path(parts: tuple[str, ...]) -> str:
    if not parts:
        return "$"

    rendered = "$"
    for part in parts:
        if part.isdigit():
            rendered += f"[{part}]"
        else:
            rendered += f".{part}"
    return rendered


def _iter_media_refs(value: object, path: tuple[str, ...] = ()) -> list[tuple[str, str]]:
    refs: list[tuple[str, str]] = []
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = (*path, key)
            if key == "images" and isinstance(child, list):
                for index, image_ref in enumerate(child):
                    if isinstance(image_ref, str):
                        refs.append((_format_json_path((*child_path, str(index))), image_ref))
            elif key in LOCAL_MEDIA_FIELDS and isinstance(child, str):
                refs.append((_format_json_path(child_path), child))
            refs.extend(_iter_media_refs(child, child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            refs.extend(_iter_media_refs(child, (*path, str(index))))
    return refs


def _is_local_media_dependency(value: str) -> bool:
    stripped = value.strip()
    if not stripped:
        return False
    return not stripped.startswith(REMOTE_OR_INLINE_PREFIXES)


def _load_props_file(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)

    if not isinstance(payload, dict):
        raise SystemExit(f"Error: {path} must contain a JSON object.")
    return payload


def validate_props_file(path: Path) -> dict:
    payload = _load_props_file(path)

    if not isinstance(payload.get("cuts"), list) or not payload["cuts"]:
        raise SystemExit(f"Error: {path} must define at least one cut.")

    local_refs = [
        f"{json_path}={media_ref}"
        for json_path, media_ref in _iter_media_refs(payload)
        if _is_local_media_dependency(media_ref)
    ]
    if local_refs:
        joined_refs = ", ".join(local_refs)
        raise SystemExit(
            f"Error: {path} references local media assets, which are not allowed "
            f"in checked-in zero-key demos: {joined_refs}"
        )

    return payload


def demo_description(payload: dict) -> str:
    metadata = payload.get("demo")
    if isinstance(metadata, dict):
        description = metadata.get("description")
        if isinstance(description, str) and description.strip():
            return description.strip()
    return "Checked-in component-only Remotion demo"


def _remotion_browser_root() -> Path:
    return COMPOSER_DIR / "node_modules" / ".remotion" / "chrome-headless-shell"


def _remotion_browser_zip_version(path: Path) -> str | None:
    match = REMOTION_BROWSER_VERSION_RE.search(path.name)
    return match.group(1) if match else None


def _browser_platform_from_zip(archive: zipfile.ZipFile) -> str | None:
    for name in archive.namelist():
        root = name.split("/", 1)[0]
        prefix = "chrome-headless-shell-"
        if root.startswith(prefix):
            return root.removeprefix(prefix)
    return None


def _browser_executable_name(platform_name: str) -> str:
    if platform_name == "win64":
        return "chrome-headless-shell.exe"
    if platform_name == "linux-arm64":
        return "headless_shell"
    return "chrome-headless-shell"


def repair_remotion_browser_install() -> bool:
    """Repair a partial Remotion Chrome Headless Shell extraction.

    Some first-run Remotion installs can leave the downloaded zip in place and
    only partially extract the browser payload while still exiting 0. When that
    happens, the next render repeats the download and exits before producing a
    video. If a complete zip is already present, extract it into Remotion's
    expected cache layout and write the VERSION marker it checks on startup.
    """
    browser_root = _remotion_browser_root()
    if not browser_root.exists():
        return False

    repaired = False
    for archive_path in sorted(browser_root.glob("*headless-shell*.zip*")):
        version = _remotion_browser_zip_version(archive_path)
        if not version:
            continue
        try:
            with zipfile.ZipFile(archive_path) as archive:
                platform_name = _browser_platform_from_zip(archive)
                if not platform_name:
                    continue
                target_dir = browser_root / platform_name
                archive.extractall(target_dir)
        except (OSError, zipfile.BadZipFile):
            continue

        executable = (
            browser_root
            / platform_name
            / f"chrome-headless-shell-{platform_name}"
            / _browser_executable_name(platform_name)
        )
        if not executable.exists():
            continue
        executable.chmod(executable.stat().st_mode | 0o111)
        (browser_root / "VERSION").write_text(version, encoding="utf-8")
        repaired = True

    return repaired


def render_demo(name: str, props_path: Path, npx_cmd: str) -> None:
    validate_props_file(props_path)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = OUTPUT_DIR / f"{name}.mp4"
    port = find_free_port()
    if output_path.exists():
        output_path.unlink()

    print()
    print(f"Rendering: {name}")
    print(f"Props:     {props_path}")
    print(f"Output:    {output_path}")
    print(f"Port:      {port}")
    print()

    command = [
        npx_cmd,
        "remotion",
        "render",
        "src/index.tsx",
        "Explainer",
        str(output_path),
        "--props",
        str(props_path),
        "--codec",
        "h264",
        "--port",
        str(port),
    ]

    for attempt in range(2):
        subprocess.run(command, cwd=COMPOSER_DIR, check=True)
        if output_path.exists():
            size_mb = output_path.stat().st_size / (1024 * 1024)
            print(f"Done: {output_path} ({size_mb:.1f} MB)")
            return

        if attempt == 0 and repair_remotion_browser_install():
            print("Remotion browser cache repaired; retrying render.")
            continue
        break

    raise SystemExit(
        f"Error: expected demo render was not created: {output_path}. "
        "Remotion exited without writing the MP4."
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Render zero-key Video Production Buddy demos from checked-in Remotion props."
    )
    parser.add_argument("demo", nargs="?", help="Render one named demo instead of all demos.")
    parser.add_argument("--list", action="store_true", help="List available demo fixtures and exit.")
    args = parser.parse_args(argv)

    demos = discover_demos()
    if not demos:
        raise SystemExit(f"Error: No demo prop files were found in {PROPS_DIR}.")

    if args.list:
        print("Available zero-key demos:")
        for name, props_path in demos.items():
            description = demo_description(validate_props_file(props_path))
            print(f"  {name:20} {description}")
        return 0

    if args.demo and args.demo not in demos:
        available = ", ".join(demos)
        raise SystemExit(f"Unknown demo '{args.demo}'. Available demos: {available}")

    npx_cmd = ensure_demo_environment()
    selected = {args.demo: demos[args.demo]} if args.demo else demos

    for name, props_path in selected.items():
        render_demo(name, props_path, npx_cmd)

    return 0


if __name__ == "__main__":
    sys.exit(main())
