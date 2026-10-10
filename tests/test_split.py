from __future__ import annotations

import json
from pathlib import Path

import pytest

from readiness_kit.harness.evalset import load_evalset
from readiness_kit.harness.split import Split, load_split, make_split, save_split
from readiness_kit.util import KitError


def test_split_is_deterministic_and_order_independent(example: Path) -> None:
    es = load_evalset(example / "evalset.jsonl")
    a = make_split(es, holdout_fraction=0.33, salt="s1")
    b = make_split(es, holdout_fraction=0.33, salt="s1")
    assert a.holdout == b.holdout and a.dev == b.dev
    es.cases.reverse()
    c = make_split(es, holdout_fraction=0.33, salt="s1")
    assert set(c.holdout) == set(a.holdout)
    assert len(a.holdout) + len(a.dev) == len(es)
    assert 0.15 < len(a.holdout) / len(es) < 0.55


def test_different_salt_different_split(example: Path) -> None:
    es = load_evalset(example / "evalset.jsonl")
    a = make_split(es, salt="one")
    b = make_split(es, salt="two")
    assert set(a.holdout) != set(b.holdout)


def test_appending_cases_keeps_existing_assignment(example: Path) -> None:
    es = load_evalset(example / "evalset.jsonl")
    before = make_split(es, salt="stable")
    es.cases.append(type(es.cases[0])(id="t-999", input="new case", expected={"category": "ORDER"}))
    after = make_split(es, salt="stable")
    for cid in before.holdout:
        assert cid in after.holdout
    for cid in before.dev:
        assert cid in after.dev


def test_unknown_id_assigned_by_rule(example: Path) -> None:
    es = load_evalset(example / "evalset.jsonl")
    s = make_split(es, salt="rule")
    side = s.side("never-seen")
    assert side in ("holdout", "dev")
    assert side == Split(salt="rule", holdout_fraction=s.holdout_fraction, holdout=[], dev=[]).side(
        "never-seen"
    )


def test_split_round_trip(example: Path, tmp_path: Path) -> None:
    es = load_evalset(example / "evalset.jsonl")
    s = make_split(es, salt="rt")
    p = save_split(s, tmp_path / "split.json")
    data = json.loads(p.read_text())
    assert data["evalset_sha256"] == es.sha256 and data["counts"]["holdout"] == len(s.holdout)
    back = load_split(p)
    assert back.holdout == s.holdout and back.salt == "rt"


def test_bad_fraction_rejected(example: Path) -> None:
    es = load_evalset(example / "evalset.jsonl")
    with pytest.raises(KitError):
        make_split(es, holdout_fraction=1.0)
