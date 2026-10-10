"""`rk validate`: check files against the Kit's JSON Schemas (and the rubric's own rules)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from readiness_kit.paths import schema_path
from readiness_kit.util import KitError, read_json, read_jsonl, read_yaml


def _load_any(path: Path) -> Any:
    if path.suffix.lower() in (".yaml", ".yml"):
        return read_yaml(path)
    if path.suffix.lower() == ".jsonl":
        return read_jsonl(path)
    return read_json(path)


def _validate(instance: Any, schema_name: str) -> list[str]:
    import jsonschema

    schema = read_json(schema_path(schema_name))
    validator = jsonschema.Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(instance), key=lambda e: list(e.path))
    out = []
    for e in errors:
        where = "/".join(str(x) for x in e.absolute_path) or "(root)"
        out.append(f"{where}: {e.message}")
    return out


def validate_file(kind: str, file: str | Path) -> list[str]:
    p = Path(file)
    if not p.exists():
        raise KitError(f"file not found: {p}")
    data = _load_any(p)
    if kind == "evalset":
        rows = data.get("cases", data) if isinstance(data, dict) else data
        if not isinstance(rows, list):
            return ["an evaluation set is a JSONL file or a YAML list"]
        errs = []
        ids: set[str] = set()
        for i, row in enumerate(rows):
            for e in _validate(row, "evalset"):
                errs.append(f"case {i + 1}: {e}")
            if isinstance(row, dict) and row.get("id") in ids:
                errs.append(f"case {i + 1}: duplicate id {row.get('id')}")
            if isinstance(row, dict):
                ids.add(row.get("id"))
        return errs
    if kind in ("case", "pack"):
        items = data.get("cases", [data]) if isinstance(data, dict) else data
        if not isinstance(items, list):
            return ["a pack file holds one case or {cases: [...]}"]
        errs = []
        for i, item in enumerate(items):
            for e in _validate(item, "case"):
                errs.append(f"case {i + 1}: {e}")
        return errs
    if kind == "manifest":
        return _validate(data, "agent-manifest")
    if kind == "scorecard":
        return _validate(data, "scorecard")
    if kind == "report":
        return _validate(data, "evidence-report")
    if kind == "rubric":
        from readiness_kit.rubric.model import load_rubric

        try:
            load_rubric(p)
        except KitError as e:
            return [str(e)]
        return []
    if kind == "bom":
        errs = []
        if not isinstance(data, dict):
            return ["a BOM is a JSON object"]
        for k in ("bomFormat", "specVersion", "serialNumber", "version", "metadata", "components"):
            if k not in data:
                errs.append(f"missing {k}")
        if data.get("bomFormat") != "CycloneDX":
            errs.append("bomFormat must be CycloneDX")
        if str(data.get("specVersion")) not in ("1.5", "1.6", "1.7"):
            errs.append("specVersion should be 1.5, 1.6 or 1.7")
        for i, c in enumerate(data.get("components") or []):
            for k in ("type", "name"):
                if k not in c:
                    errs.append(f"components/{i}: missing {k}")
        return errs
    raise KitError(f"unknown kind '{kind}'")
