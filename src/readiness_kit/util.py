"""Small shared helpers: file I/O for JSON, JSONL and YAML, hashing, time, environment substitution."""

from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml


class KitError(Exception):
    """An error the CLI reports as a one-line message and a non-zero exit code."""


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def read_text(path: str | Path) -> str:
    return Path(path).read_text(encoding="utf-8")


def write_text_file(path: str | Path, text: str) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


def read_json(path: str | Path) -> Any:
    try:
        return json.loads(read_text(path))
    except json.JSONDecodeError as e:
        raise KitError(f"{path}: not valid JSON ({e.msg} at line {e.lineno})") from e


def write_json(path: str | Path, data: Any) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2, ensure_ascii=False, sort_keys=False) + "\n", encoding="utf-8")
    return p


def read_jsonl(path: str | Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with open(path, encoding="utf-8") as f:
        for n, line in enumerate(f, start=1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as e:
                raise KitError(f"{path}:{n}: not valid JSON ({e.msg})") from e
            if not isinstance(row, dict):
                raise KitError(f"{path}:{n}: each line must be a JSON object")
            rows.append(row)
    return rows


def write_jsonl(path: str | Path, rows: list[dict[str, Any]]) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return p


def read_yaml(path: str | Path) -> Any:
    try:
        return yaml.safe_load(read_text(path))
    except yaml.YAMLError as e:
        raise KitError(f"{path}: not valid YAML ({e})") from e


def write_yaml(path: str | Path, data: Any) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True, width=100), encoding="utf-8")
    return p


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_file(path: str | Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_json(data: Any) -> str:
    """Hash of the canonical JSON form (sorted keys, no whitespace) — stable across re-serialisation."""
    return sha256_text(json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False))


_ENV_RE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::-([^}]*))?\}")


def expand_env(value: Any) -> Any:
    """Replace ``${NAME}`` and ``${NAME:-default}`` in strings, recursively through dicts and lists.

    An unset variable without a default raises, so a missing API key fails loudly before a run starts.
    """
    if isinstance(value, str):

        def sub(m: re.Match[str]) -> str:
            name, default = m.group(1), m.group(2)
            if name in os.environ:
                return os.environ[name]
            if default is not None:
                return default
            raise KitError(f"environment variable {name} is not set (referenced as ${{{name}}})")

        return _ENV_RE.sub(sub, value)
    if isinstance(value, dict):
        return {k: expand_env(v) for k, v in value.items()}
    if isinstance(value, list):
        return [expand_env(v) for v in value]
    return value


def pct(n: float, d: float) -> float:
    return round(n / d, 4) if d else 0.0


def glob_match(name: str, pattern: str) -> bool:
    """Case-insensitive shell-style match used for tool-name patterns such as ``send_*``."""
    from fnmatch import fnmatchcase

    return fnmatchcase(name.lower(), pattern.lower())
