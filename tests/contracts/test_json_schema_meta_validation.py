from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema.validators import validator_for


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_FILES = tuple(sorted((PROJECT_ROOT / "schemas").rglob("*.json")))


def _schema_id(path: Path) -> str:
    return path.relative_to(PROJECT_ROOT).as_posix()


def test_schema_inventory_is_not_empty() -> None:
    assert SCHEMA_FILES


@pytest.mark.parametrize("schema_path", SCHEMA_FILES, ids=_schema_id)
def test_json_schema_file_is_meta_schema_valid(schema_path: Path) -> None:
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    validator_cls = validator_for(schema)
    validator_cls.check_schema(schema)
