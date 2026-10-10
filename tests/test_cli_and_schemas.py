from __future__ import annotations

import json
from pathlib import Path

from readiness_kit import __version__
from readiness_kit.cli import main
from readiness_kit.paths import starter_pack_path
from readiness_kit.schemas import validate_file


def test_version(capsys) -> None:
    assert main(["version"]) == 0
    assert __version__ in capsys.readouterr().out


def test_init_writes_templates(tmp_path: Path) -> None:
    assert main(["init", str(tmp_path / "proj")]) == 0
    for name in ("rk.yaml", "agent.yaml", "assessment.yaml", "prices.yaml"):
        assert (tmp_path / "proj" / name).exists()
    assert main(["init", str(tmp_path / "proj")]) == 0  # second run keeps files


def test_pipeline_through_cli(example: Path, monkeypatch, capsys) -> None:
    monkeypatch.chdir(example)
    assert main(["split", "evalset.jsonl", "--salt", "cli"]) == 0
    assert main(["eval", "-q"]) == 0
    assert main(["attack", "--fail-on-high"]) == 2  # the example agent has high findings
    assert main(["bom"]) == 0
    assert main(["cost", "traces.jsonl"]) == 0
    assert main(["scan", "--tools", "promptfoo"]) == 0
    assert main(["score"]) == 0
    out = capsys.readouterr().out
    assert "CONDITIONAL" in out or "NOT_READY" in out
    sc = json.loads((example / "runs" / "scorecard.json").read_text())
    assert sc["kind"] == "rk.scorecard" and (example / "runs" / "scorecard.md").exists()
    assert main(["validate", "scorecard", str(example / "runs" / "scorecard.json")]) == 0
    assert main(["validate", "bom", str(example / "runs" / "bom.cdx.json")]) == 0


def test_errors_are_one_line(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.chdir(tmp_path)
    assert main(["eval"]) == 1
    assert "rk.yaml" in capsys.readouterr().out
    assert main(["score"]) == 1


def test_schemas_accept_bundled_data(example: Path) -> None:
    for f in sorted(starter_pack_path().glob("*.yaml")):
        assert validate_file("pack", f) == [], f.name
    assert validate_file("evalset", example / "evalset.jsonl") == []
    assert validate_file("manifest", example / "agent.yaml") == []
    assert (
        validate_file(
            "rubric", Path(__import__("readiness_kit.paths", fromlist=["rubric_path"]).rubric_path())
        )
        == []
    )


def test_schemas_reject_bad_data(tmp_path: Path) -> None:
    bad = tmp_path / "bad.jsonl"
    bad.write_text('{"id": "a"}\n{"id": "a", "input": "x", "grader": "magic"}\n')
    errs = validate_file("evalset", bad)
    assert (
        any("input" in e for e in errs)
        and any("duplicate" in e for e in errs)
        and any("magic" in e for e in errs)
    )
    case = tmp_path / "case.yaml"
    case.write_text(
        "id: ASI99-001\nasi: ASI01\ntitle: t\nseverity: high\nchannel: user_input\ninput: x\noracles: []\n"
    )
    errs = validate_file("case", case)
    assert errs and any("ASI99" in e or "pattern" in e for e in errs)


def test_evidence_report_schema_accepts_a_minimal_report(tmp_path: Path) -> None:
    report = {
        "id": "RK-GATE-TEST-0001",
        "title": "Readiness Evidence Report",
        "subject": {"organisation": "Example Ltd", "agent": "triage agent"},
        "period": "1–10 Oct 2026",
        "verdict": {"score": 58, "band": "CONDITIONAL", "line": "Fix the high findings."},
        "summary": ["one"],
        "scope": {"description": "d", "stack": "s", "data": "d", "engines": "e"},
        "reliability": {"pass_rate": 0.91, "target": 0.9, "cases": 48},
        "security": {
            "classes": [
                {"asi": f"ASI{n:02d}", "class": "c", "cases": 1, "followed": 0, "outcome": "pass"}
                for n in range(1, 11)
            ]
        },
        "cost": {"per_task": 0.84, "currency": "USD"},
        "permissions": [],
        "bom": {"components": []},
        "scorecard": [{"area": a, "weight": 12, "points": 6} for a in range(8)],
        "remediation": [],
        "controls": [],
        "limitations": [],
        "signoff": {"prepared_by": "Rainkernel"},
    }
    report["scorecard"] = [{"area": str(x["area"]), "weight": 12, "points": 6} for x in report["scorecard"]]
    p = tmp_path / "r.json"
    p.write_text(json.dumps(report))
    assert validate_file("report", p) == []
