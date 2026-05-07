from __future__ import annotations

import json
from pathlib import Path

from tools.base_tool import ToolStatus
from tools.analysis.composition_validator import CompositionValidator


def test_composition_validator_status_requires_ffprobe(monkeypatch) -> None:
    monkeypatch.setattr("tools.base_tool.shutil.which", lambda command: None)

    assert CompositionValidator().get_status() == ToolStatus.UNAVAILABLE


def test_composition_validator_allows_remotion_virtual_component_sources(
    tmp_path: Path,
) -> None:
    comp_path = tmp_path / "composition.json"
    comp_path.write_text(
        json.dumps(
            {
                "render_runtime": "remotion",
                "cuts": [
                    {
                        "id": "title",
                        "source": "remotion:text_card",
                        "type": "text_card",
                        "text": "Exact rendered text",
                        "in_seconds": 0,
                        "out_seconds": 3,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    result = CompositionValidator().execute(
        {"composition_path": str(comp_path), "assets_root": str(tmp_path)}
    )

    assert result.success, result.error


def test_composition_validator_rejects_overlapping_cuts(tmp_path: Path) -> None:
    source = tmp_path / "clip.mp4"
    source.write_bytes(b"stub")
    comp_path = tmp_path / "composition.json"
    comp_path.write_text(
        json.dumps(
            {
                "render_runtime": "ffmpeg",
                "cuts": [
                    {
                        "id": "cut-1",
                        "source": source.name,
                        "in_seconds": 0,
                        "out_seconds": 3,
                    },
                    {
                        "id": "cut-2",
                        "source": source.name,
                        "in_seconds": 2,
                        "out_seconds": 4,
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    result = CompositionValidator().execute(
        {"composition_path": str(comp_path), "assets_root": str(tmp_path)}
    )

    assert not result.success
    assert "overlaps previous cut" in (result.error or "")


def test_composition_validator_rejects_missing_explicit_assets_root(
    tmp_path: Path,
) -> None:
    (tmp_path / "hero.png").write_bytes(b"stub")
    comp_path = tmp_path / "composition.json"
    comp_path.write_text(
        json.dumps(
            {
                "render_runtime": "remotion",
                "cuts": [
                    {
                        "id": "cut-1",
                        "source": "hero.png",
                        "in_seconds": 0,
                        "out_seconds": 1,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    result = CompositionValidator().execute(
        {
            "composition_path": str(comp_path),
            "assets_root": str(tmp_path / "missing-assets"),
        }
    )

    assert not result.success
    assert "assets_root not found" in (result.error or "")
