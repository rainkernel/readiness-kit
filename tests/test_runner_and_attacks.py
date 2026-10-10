from __future__ import annotations

from pathlib import Path

from readiness_kit.harness.attacks import ASI_CLASSES, load_pack, run_attacks
from readiness_kit.harness.evalset import load_evalset
from readiness_kit.harness.runner import run_eval
from readiness_kit.harness.split import make_split
from readiness_kit.harness.targets import Request, Run, build_target
from readiness_kit.paths import starter_pack_path


def _target(example: Path):
    return build_target({"type": "python", "module": "agent", "cwd": str(example), "max_steps": 25})


def test_eval_summary_holdout_headline(example: Path) -> None:
    es = load_evalset(example / "evalset.jsonl")
    split = make_split(es, salt="rk-example-2026")
    res = run_eval(_target(example), es, split, label="example")
    s = res.summary()
    assert s["headline"]["side"] == "holdout" and s["headline"]["cases"] == len(split.holdout)
    assert 0.6 <= s["headline"]["pass_rate"] <= 1.0 and s["all"]["cases"] == 80 and s["all"]["errors"] == 0
    assert {r["category"] for r in s["by_category"]} == {
        c.lower()
        for c in (
            "ORDER",
            "SHIPPING_ADDRESS",
            "DELIVERY",
            "CANCELLATION_FEE",
            "INVOICE",
            "PAYMENT",
            "REFUND",
            "FEEDBACK",
            "ACCOUNT",
            "NEWSLETTER",
            "CONTACT",
        )
    }
    d = res.to_dict()
    assert (
        d["kind"] == "rk.eval"
        and d["split"]["salt"] == "rk-example-2026"
        and d["evalset"]["sha256"] == es.sha256
    )
    # concurrency gives the same answer
    res2 = run_eval(_target(example), es, split, concurrency=4)
    assert res2.summary()["all"]["passed"] == s["all"]["passed"]


def test_eval_side_and_limit(example: Path) -> None:
    es = load_evalset(example / "evalset.jsonl")
    split = make_split(es, salt="rk-example-2026")
    res = run_eval(_target(example), es, split, side="dev", limit=5)
    assert len(res.results) == 5 and all(r.side == "dev" for r in res.results)


def test_starter_pack_covers_ten_classes() -> None:
    cases = load_pack(starter_pack_path())
    assert {c.asi for c in cases} == set(ASI_CLASSES)
    assert len(cases) >= 10 and len({c.id for c in cases}) == len(cases)
    for c in cases:
        assert c.oracles and c.remediation and c.references


def test_attacks_on_example_find_the_known_weaknesses(example: Path) -> None:
    cases = load_pack(starter_pack_path())
    res = run_attacks(_target(example), cases, pack_path="starter", max_steps=25)
    status = {o.case.id: o.status for o in res.outcomes}
    assert {k for k, v in status.items() if v == "followed"} == {
        "ASI01-001",
        "ASI06-001",
        "ASI08-001",
        "ASI09-001",
    }
    assert all(v in ("followed", "pass") for v in status.values())
    s = res.summary()
    assert s["high"] == 2 and s["medium"] == 1 and s["low"] == 1 and s["classes_run"] == 10
    by = {r["asi"]: r for r in s["by_class"]}
    assert (
        by["ASI01"]["outcome"] == "high"
        and by["ASI02"]["outcome"] == "pass"
        and by["ASI08"]["findings"][0]["case_id"] == "ASI08-001"
    )
    d = res.to_dict()
    assert d["kind"] == "rk.attack" and d["pack"]["cases"] == len(cases)


class _TextOnly:
    name = "text-only"

    def run(self, request: Request) -> Run:
        return Run(case_id=request.case_id, output="category: REFUND\nreply: logged for the finance team")


def test_not_observable_never_becomes_pass() -> None:
    cases = load_pack(starter_pack_path())
    res = run_attacks(_TextOnly(), cases, pack_path="starter")
    s = res.summary()
    assert s["not_observable"] >= 1
    by = {r["asi"]: r for r in s["by_class"]}
    assert by["ASI08"]["outcome"] == "n/a"  # step oracles need steps
    assert by["ASI09"]["outcome"] == "pass"  # output-only oracle, no assertion in the reply


def test_only_filter(example: Path) -> None:
    cases = load_pack(starter_pack_path())
    res = run_attacks(_target(example), cases, only=["ASI08", "ASI01-002"])
    assert {o.case.id for o in res.outcomes} == {"ASI08-001", "ASI01-002"}
