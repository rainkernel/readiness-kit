"""Evaluation sets: one JSON object per line (JSONL), or a YAML list.

    {"id": "t-001", "input": "My parcel never arrived …", "expected": {"category": "DELIVERY"},
     "grader": "label", "category": "delivery", "tags": ["real"], "context": {}, "metadata": {}}

* ``id`` and ``input`` are required.
* ``expected`` is what the grader compares against (docs/FORMATS.md lists the graders and their options).
* ``grader`` defaults to ``label`` when ``expected`` is an object, ``contains`` when it is a string.
* ``category`` groups the result table (the sample report's "by category" rows); ``tags`` are free.
* ``context`` is passed to the agent unchanged (memory, documents, a system prompt override).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from readiness_kit.util import KitError, read_jsonl, read_yaml, sha256_file


@dataclass
class Case:
    id: str
    input: str
    expected: Any = None
    grader: str = "contains"
    options: dict[str, Any] = field(default_factory=dict)
    category: str = "uncategorised"
    tags: list[str] = field(default_factory=list)
    context: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, row: dict[str, Any], where: str = "") -> Case:
        for k in ("id", "input"):
            if k not in row:
                raise KitError(f"{where}case without '{k}': {str(row)[:120]}")
        expected = row.get("expected")
        grader = row.get("grader")
        if grader is None:
            grader = "label" if isinstance(expected, dict) else "contains"
        opts = row.get("options") or {}
        if not isinstance(opts, dict):
            raise KitError(f"{where}case {row['id']}: options must be an object")
        return cls(
            id=str(row["id"]),
            input=str(row["input"]),
            expected=expected,
            grader=str(grader),
            options=opts,
            category=str(row.get("category") or "uncategorised"),
            tags=[str(t) for t in row.get("tags") or []],
            context=dict(row.get("context") or {}),
            metadata=dict(row.get("metadata") or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "id": self.id,
            "input": self.input,
            "expected": self.expected,
            "grader": self.grader,
        }
        if self.options:
            d["options"] = self.options
        d["category"] = self.category
        if self.tags:
            d["tags"] = self.tags
        if self.context:
            d["context"] = self.context
        if self.metadata:
            d["metadata"] = self.metadata
        return d


@dataclass
class EvalSet:
    cases: list[Case]
    path: str | None = None
    sha256: str | None = None

    def __len__(self) -> int:
        return len(self.cases)

    def ids(self) -> list[str]:
        return [c.id for c in self.cases]

    def by_id(self, cid: str) -> Case | None:
        for c in self.cases:
            if c.id == cid:
                return c
        return None


def load_evalset(path: str | Path) -> EvalSet:
    p = Path(path)
    if not p.exists():
        raise KitError(f"evaluation set not found: {p}")
    rows = read_yaml(p) if p.suffix.lower() in (".yaml", ".yml") else read_jsonl(p)
    if isinstance(rows, dict) and "cases" in rows:
        rows = rows["cases"]
    if not isinstance(rows, list):
        raise KitError(f"{p}: an evaluation set is a JSONL file or a YAML list of cases")
    cases = [Case.from_dict(r, where=f"{p.name}: ") for r in rows]
    seen: set[str] = set()
    for c in cases:
        if c.id in seen:
            raise KitError(f"{p}: duplicate case id '{c.id}'")
        seen.add(c.id)
    if not cases:
        raise KitError(f"{p}: the evaluation set is empty")
    return EvalSet(cases=cases, path=str(p), sha256=sha256_file(p))
