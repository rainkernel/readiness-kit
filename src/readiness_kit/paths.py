"""Where the Kit's bundled data lives (rubric, starter attack pack, the example agent).

Installed from a wheel, the data sits inside the package under ``_data/``. In a checkout (editable install)
it sits at the repository root, two levels above this file. Both are tried, in that order.
"""

from __future__ import annotations

from pathlib import Path

_PKG = Path(__file__).resolve().parent
_REPO = _PKG.parent.parent


class DataNotFound(FileNotFoundError):
    """A bundled data file could not be located in the wheel or the checkout."""


def data_path(*parts: str) -> Path:
    """Return the path of a bundled data file or folder, e.g. ``data_path("rubric", "readiness-rubric.yaml")``."""
    candidates = [_PKG / "_data" / Path(*parts), _REPO / Path(*parts)]
    for c in candidates:
        if c.exists():
            return c
    raise DataNotFound(
        f"bundled data not found: {'/'.join(parts)} (looked in {', '.join(str(c) for c in candidates)})"
    )


def rubric_path() -> Path:
    return data_path("rubric", "readiness-rubric.yaml")


def schema_path(name: str) -> Path:
    """Where each schema ships: the report and scorecard next to the rubric, the attack case with the pack,
    the evaluation set and the agent manifest under schemas/."""
    if name == "case":
        return data_path("attack-pack", "case.schema.json")
    if name in ("scorecard", "evidence-report"):
        return data_path("rubric", f"{name}.schema.json")
    return data_path("schemas", f"{name}.schema.json")


def starter_pack_path() -> Path:
    return data_path("attack-pack", "starter")


def example_path(name: str = "ticket-triage-agent") -> Path:
    return data_path("examples", name)
