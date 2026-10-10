"""Loading and checking the rubric YAML."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from readiness_kit.paths import rubric_path
from readiness_kit.util import KitError, read_yaml, sha256_file

AREA_IDS = (
    "evaluation_set",
    "guardrails",
    "cost_per_task",
    "observability",
    "data_access",
    "human_in_the_loop",
    "reliability",
    "compliance",
)


@dataclass
class Area:
    id: str
    name: str
    weight: int
    question: str = ""
    measured_by: list[str] = field(default_factory=list)
    declared_by: list[str] = field(default_factory=list)
    scoring: list[str] = field(default_factory=list)
    bands: list[dict[str, Any]] = field(default_factory=list)

    def band_for(self, points: float) -> str:
        frac = points / self.weight if self.weight else 0
        for b in sorted(self.bands, key=lambda b: -float(b.get("min", 0))):
            if frac >= float(b.get("min", 0)):
                return str(b.get("label", ""))
        return ""


@dataclass
class Rubric:
    name: str
    version: int
    areas: list[Area]
    verdict_bands: list[dict[str, Any]]
    path: str
    sha256: str

    def area(self, area_id: str) -> Area:
        for a in self.areas:
            if a.id == area_id:
                return a
        raise KitError(f"rubric has no area '{area_id}'")

    def verdict_band(self, total: float, high_findings: int) -> tuple[str, str]:
        for b in sorted(self.verdict_bands, key=lambda b: -float(b.get("min", 0))):
            if total >= float(b.get("min", 0)):
                if b.get("requires_no_high_findings") and high_findings > 0:
                    continue
                return str(b["id"]), str(b.get("means", ""))
        last = sorted(self.verdict_bands, key=lambda b: float(b.get("min", 0)))[0]
        return str(last["id"]), str(last.get("means", ""))


def load_rubric(path: str | Path | None = None) -> Rubric:
    p = Path(path) if path else rubric_path()
    if not p.exists():
        raise KitError(f"rubric not found: {p}")
    data = read_yaml(p)
    if not isinstance(data, dict) or "areas" not in data:
        raise KitError(f"{p}: a rubric is a YAML object with 'areas'")
    areas: list[Area] = []
    for a in data["areas"]:
        try:
            areas.append(
                Area(
                    id=str(a["id"]),
                    name=str(a["name"]),
                    weight=int(a["weight"]),
                    question=str(a.get("question", "")),
                    measured_by=list(a.get("measured_by") or []),
                    declared_by=list(a.get("declared_by") or []),
                    scoring=list(a.get("scoring") or []),
                    bands=list(a.get("bands") or []),
                )
            )
        except KeyError as e:
            raise KitError(f"{p}: area is missing '{e.args[0]}'") from e
    ids = [a.id for a in areas]
    missing = [i for i in AREA_IDS if i not in ids]
    if missing:
        raise KitError(f"{p}: rubric is missing areas {missing}")
    total = sum(a.weight for a in areas)
    if total != 100:
        raise KitError(f"{p}: area weights sum to {total}, not 100")
    bands = list((data.get("verdict") or {}).get("bands") or [])
    if not bands:
        raise KitError(f"{p}: rubric needs verdict.bands")
    return Rubric(
        name=str(data.get("name", "rubric")),
        version=int(data.get("version", 1)),
        areas=areas,
        verdict_bands=bands,
        path=str(p),
        sha256=sha256_file(p),
    )
