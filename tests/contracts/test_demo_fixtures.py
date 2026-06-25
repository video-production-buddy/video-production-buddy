"""Contracts for checked-in zero-key Remotion demo fixtures."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import render_demo


def _write_props(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_demo_list_excludes_local_media_fixture(capsys: pytest.CaptureFixture[str]) -> None:
    demos = render_demo.discover_demos()

    assert "healing-anime-short" not in demos

    assert render_demo.main(["--list"]) == 0
    output = capsys.readouterr().out
    assert "healing-anime-short" not in output
    assert "world-in-numbers" in output


def test_checked_in_demo_props_are_component_only() -> None:
    demos = render_demo.discover_demos()

    assert demos
    for props_path in demos.values():
        render_demo.validate_props_file(props_path)


def test_validate_props_file_rejects_local_media_dependencies(tmp_path: Path) -> None:
    props_path = tmp_path / "local-media.json"
    _write_props(
        props_path,
        {
            "cuts": [
                {
                    "id": "scene-1",
                    "type": "anime_scene",
                    "in_seconds": 0,
                    "out_seconds": 4,
                    "images": ["some-local/frame.png"],
                },
                {
                    "id": "scene-2",
                    "type": "brand_card",
                    "in_seconds": 4,
                    "out_seconds": 8,
                    "brandName": "Local Media",
                    "productImage": "some-local/product.png",
                },
            ],
        },
    )

    with pytest.raises(SystemExit, match="local media assets"):
        render_demo.validate_props_file(props_path)


def test_demo_list_reads_description_from_props_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(render_demo, "PROPS_DIR", tmp_path)
    _write_props(
        tmp_path / "metadata-demo.json",
        {
            "demo": {"description": "Description loaded from the props file"},
            "cuts": [
                {
                    "id": "title",
                    "type": "hero_title",
                    "in_seconds": 0,
                    "out_seconds": 3,
                    "text": "Metadata Demo",
                }
            ],
        },
    )

    assert render_demo.main(["--list"]) == 0
    output = capsys.readouterr().out
    assert "metadata-demo" in output
    assert "Description loaded from the props file" in output


def test_find_free_port_scans_stable_remotion_port_range(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempts: list[int] = []

    def fake_can_bind(port: int) -> bool:
        attempts.append(port)
        return port == 20_001

    monkeypatch.setattr(render_demo, "DEMO_PORT_START", 20_000)
    monkeypatch.setattr(render_demo, "DEMO_PORT_END", 20_002)
    monkeypatch.setattr(render_demo, "_can_bind_remotion_hosts", fake_can_bind)

    assert render_demo.find_free_port() == 20_001
    assert attempts == [20_000, 20_001]


def test_render_demo_passes_explicit_free_port_to_remotion(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    props_path = tmp_path / "port-demo.json"
    output_dir = tmp_path / "renders"
    commands: list[list[str]] = []
    _write_props(
        props_path,
        {
            "cuts": [
                {
                    "id": "title",
                    "type": "hero_title",
                    "in_seconds": 0,
                    "out_seconds": 3,
                    "text": "Port Demo",
                }
            ],
        },
    )

    def fake_run(command: list[str], **_: object) -> None:
        commands.append(command)
        output_path = Path(command[5])
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"mp4")

    monkeypatch.setattr(render_demo, "OUTPUT_DIR", output_dir)
    monkeypatch.setattr(render_demo, "find_free_port", lambda: 49152, raising=False)
    monkeypatch.setattr(render_demo.subprocess, "run", fake_run)

    render_demo.render_demo("port-demo", props_path, "npx")

    assert len(commands) == 1
    assert "--port" in commands[0]
    assert commands[0][commands[0].index("--port") + 1] == "49152"


def test_render_demo_fails_when_remotion_exits_without_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    props_path = tmp_path / "missing-output-demo.json"
    output_dir = tmp_path / "renders"
    _write_props(
        props_path,
        {
            "cuts": [
                {
                    "id": "title",
                    "type": "hero_title",
                    "in_seconds": 0,
                    "out_seconds": 3,
                    "text": "Missing Output Demo",
                }
            ],
        },
    )

    monkeypatch.setattr(render_demo, "OUTPUT_DIR", output_dir)
    monkeypatch.setattr(render_demo, "find_free_port", lambda: 49152, raising=False)
    monkeypatch.setattr(render_demo.subprocess, "run", lambda *args, **kwargs: None)
    output_dir.mkdir()
    (output_dir / "missing-output-demo.mp4").write_bytes(b"stale")

    with pytest.raises(SystemExit, match="expected demo render was not created"):
        render_demo.render_demo("missing-output-demo", props_path, "npx")


def test_render_demo_repairs_incomplete_remotion_browser_extract(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cache_root = tmp_path / "remotion-composer" / "node_modules" / ".remotion"
    browser_root = cache_root / "chrome-headless-shell"
    incomplete_install = browser_root / "linux64" / "chrome-headless-shell-linux64"
    incomplete_install.mkdir(parents=True)
    (incomplete_install / "libGLESv2.so").write_text("partial", encoding="utf-8")

    archive_path = browser_root / "chromium-headless-shell-linux-x64-144.0.7559.20.zip?clearcache"
    executable_mode = 0o755
    import zipfile

    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("chrome-headless-shell-linux64/libGLESv2.so", "complete")
        archive.writestr(
            "chrome-headless-shell-linux64/chrome-headless-shell",
            "executable",
        )

    monkeypatch.setattr(render_demo, "COMPOSER_DIR", tmp_path / "remotion-composer")

    assert render_demo.repair_remotion_browser_install() is True

    executable = incomplete_install / "chrome-headless-shell"
    assert executable.exists()
    assert executable.stat().st_mode & executable_mode
    assert (browser_root / "VERSION").read_text(encoding="utf-8") == "144.0.7559.20"
