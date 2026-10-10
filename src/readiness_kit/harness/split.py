"""The held-out split.

A case is held out when ``sha256(salt + ":" + case_id)`` interpreted as a fraction of the hash space is below the
hold-out fraction. The split therefore depends only on the salt and the case ids: it does not change when cases are
re-ordered or when new cases are appended, every run on the same salt gets the same split, and anyone holding the
salt can reproduce it. The split file records the salt, the fraction, the ids on each side and the hash of the
evaluation set it was made from, and the evaluation result records the same hashes, so a published number can be
checked against the exact set and split that produced it.

Rule of use: tune prompts and code on the dev side; report the held-out side. The Kit prints the held-out pass
rate as the headline and the dev pass rate beside it, labelled, so the two are never confused.
"""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from readiness_kit.harness.evalset import EvalSet
from readiness_kit.util import KitError, now_iso, read_json, write_json

METHOD = "sha256(salt + ':' + id) / 2**256 < holdout_fraction"


def _fraction(salt: str, case_id: str) -> float:
    digest = hashlib.sha256(f"{salt}:{case_id}".encode()).digest()
    return int.from_bytes(digest[:8], "big") / 2**64


@dataclass
class Split:
    salt: str
    holdout_fraction: float
    holdout: list[str]
    dev: list[str]
    evalset_sha256: str | None = None
    evalset_path: str | None = None
    created: str = field(default_factory=now_iso)
    method: str = METHOD

    def side(self, case_id: str) -> str:
        """``holdout`` or ``dev`` for a known id; ids not in the file are assigned by the same rule."""
        if case_id in self._holdout_set:
            return "holdout"
        if case_id in self._dev_set:
            return "dev"
        return "holdout" if _fraction(self.salt, case_id) < self.holdout_fraction else "dev"

    def __post_init__(self) -> None:
        self._holdout_set = set(self.holdout)
        self._dev_set = set(self.dev)

    def to_dict(self) -> dict[str, Any]:
        return {
            "method": self.method,
            "salt": self.salt,
            "holdout_fraction": self.holdout_fraction,
            "evalset_path": self.evalset_path,
            "evalset_sha256": self.evalset_sha256,
            "created": self.created,
            "counts": {"holdout": len(self.holdout), "dev": len(self.dev)},
            "holdout": self.holdout,
            "dev": self.dev,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Split:
        try:
            return cls(
                salt=str(d["salt"]),
                holdout_fraction=float(d["holdout_fraction"]),
                holdout=[str(x) for x in d["holdout"]],
                dev=[str(x) for x in d["dev"]],
                evalset_sha256=d.get("evalset_sha256"),
                evalset_path=d.get("evalset_path"),
                created=d.get("created", now_iso()),
                method=d.get("method", METHOD),
            )
        except KeyError as e:
            raise KitError(f"split file is missing '{e.args[0]}'") from e


def make_split(evalset: EvalSet, holdout_fraction: float = 0.33, salt: str | None = None) -> Split:
    if not 0 < holdout_fraction < 1:
        raise KitError("holdout fraction must be between 0 and 1 (exclusive)")
    salt = salt or secrets.token_hex(8)
    holdout = [c.id for c in evalset.cases if _fraction(salt, c.id) < holdout_fraction]
    dev = [c.id for c in evalset.cases if c.id not in set(holdout)]
    if not holdout or not dev:
        raise KitError(
            f"the split left one side empty (holdout={len(holdout)}, dev={len(dev)}); use more cases, another fraction or another salt"
        )
    return Split(
        salt=salt,
        holdout_fraction=holdout_fraction,
        holdout=holdout,
        dev=dev,
        evalset_sha256=evalset.sha256,
        evalset_path=evalset.path,
    )


def load_split(path: str | Path) -> Split:
    p = Path(path)
    if not p.exists():
        raise KitError(f"split file not found: {p}")
    return Split.from_dict(read_json(p))


def save_split(split: Split, path: str | Path) -> Path:
    return write_json(path, split.to_dict())
