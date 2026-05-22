import json
from pathlib import Path

import jsonschema

from craftsman.config import ROOT

_SCHEMA_CACHE: dict[str, dict] = {}


def _load_schema(name: str) -> dict:
    if name not in _SCHEMA_CACHE:
        path = ROOT / "schemas" / name
        _SCHEMA_CACHE[name] = json.loads(path.read_text(encoding="utf-8"))
    return _SCHEMA_CACHE[name]


def validate_requirement(data: dict) -> list[str]:
    schema = _load_schema("requirement.v1.json")
    validator = jsonschema.Draft202012Validator(schema)
    return [f"{'.'.join(str(p) for p in e.path)}: {e.message}" for e in validator.iter_errors(data)]


def validate_feedback(data: dict) -> list[str]:
    schema = _load_schema("craftsman-feedback.v1.json")
    validator = jsonschema.Draft202012Validator(schema)
    return [f"{'.'.join(str(p) for p in e.path)}: {e.message}" for e in validator.iter_errors(data)]
