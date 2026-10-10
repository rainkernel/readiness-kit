from __future__ import annotations

import json
import os
import stat
import sys
from pathlib import Path

import pytest

from readiness_kit.adapters import run_scanners
from readiness_kit.adapters.agentic_radar import AgenticRadarAdapter
from readiness_kit.adapters.base import ScanContext
from readiness_kit.adapters.mcp_scanner import McpScannerAdapter
from readiness_kit.adapters.promptfoo import PromptfooAdapter
from readiness_kit.adapters.snyk_agent_scan import SnykAgentScanAdapter
from readiness_kit.cli import main
from readiness_kit.rubric import load_rubric, score
from readiness_kit.rubric.render import scorecard_markdown
from readiness_kit.rubric.score import Evidence
from readiness_kit.schemas import validate_file
from readiness_kit.util import write_json, write_yaml


@pytest.fixture
def demo_runs(tmp_path: Path) -> Path:
    assert main(["demo", "--out", str(tmp_path / "d"), "-q"]) == 0
    return tmp_path / "d"


def test_rubric_loads_and_weights_sum() -> None:
    r = load_rubric()
    assert sum(a.weight for a in r.areas) == 100 and len(r.areas) == 8
    assert r.verdict_band(85, 0)[0] == "READY" and r.verdict_band(85, 1)[0] == "CONDITIONAL"
    assert r.verdict_band(50, 0)[0] == "CONDITIONAL" and r.verdict_band(49, 0)[0] == "NOT_READY"


def test_scorecard_from_demo_runs(demo_runs: Path) -> None:
    ev = Evidence.load(demo_runs / "runs", demo_runs / "assessment.yaml")
    assert ev.eval and ev.attack and ev.cost and ev.bom and ev.scan and ev.assessment
    sc = score(load_rubric(), ev, subject={"name": "demo"})
    d = sc.to_dict()
    assert validate_file("scorecard", write_json(demo_runs / "sc.json", d)) == []
    assert 0 <= d["total"] <= 100 and d["verdict"]["band"] in ("READY", "CONDITIONAL", "NOT_READY")
    assert d["findings"]["high"] == 2  # the two high attack findings on the example agent
    assert d["verdict"]["band"] != "READY"
    areas = {a["id"]: a for a in d["areas"]}
    assert areas["guardrails"]["basis"] == "measured" and areas["guardrails"]["points"] <= 4
    assert areas["human_in_the_loop"]["basis"] == "declared"
    assert d["coverage"]["not_measured"] == 0
    md = scorecard_markdown(sc, attack=ev.attack)
    assert "| **Total** | **100** |" in md and "ASI08 Cascading failures" in md


def test_nothing_measured_is_a_floor(tmp_path: Path) -> None:
    runs = tmp_path / "runs"
    runs.mkdir()
    write_yaml(
        tmp_path / "a.yaml",
        {
            "human_in_the_loop": {
                "escalation_path": True,
                "operator_can_halt": True,
                "approval_for_irreversible_actions": True,
            }
        },
    )
    ev = Evidence.load(runs, tmp_path / "a.yaml")
    sc = score(load_rubric(), ev)
    d = sc.to_dict()
    assert d["coverage"]["not_measured"] >= 5 and d["total"] == 10
    assert "Not measured" in d["verdict"]["line"] and d["verdict"]["band"] == "NOT_READY"


def test_high_finding_blocks_ready(demo_runs: Path) -> None:
    ev = Evidence.load(demo_runs / "runs", demo_runs / "assessment.yaml")
    # pretend everything is perfect except one high finding
    ev.attack["summary"]["high"] = 1
    sc = score(load_rubric(), ev)
    sc.areas = [
        type(a)(id=a.id, name=a.name, weight=a.weight, points=a.weight, basis="measured", band="strong")
        for a in sc.areas
    ]
    assert sc.total == 100 and sc.verdict()["band"] == "CONDITIONAL"


# --- adapters ---------------------------------------------------------------------------------------------------


def _ctx(tmp_path: Path, **kw) -> ScanContext:
    env = dict(os.environ)
    env.pop("SNYK_TOKEN", None)
    return ScanContext(path=tmp_path, out_dir=tmp_path / "out", env=env, **kw)


def _fake_bin(tmp_path: Path, name: str, body: str) -> Path:
    """A fake scanner on PATH: a shebang script on POSIX, a .cmd wrapper around a .py file on Windows."""
    d = tmp_path / "bin"
    d.mkdir(exist_ok=True)
    if os.name == "nt":
        script = d / f"{name}.py"
        script.write_text(body, encoding="utf-8")
        (d / f"{name}.cmd").write_text(f'@"{sys.executable}" "{script}" %*\r\n', encoding="utf-8")
        return d
    p = d / name
    p.write_text(f"#!{sys.executable}\n{body}", encoding="utf-8")
    p.chmod(p.stat().st_mode | stat.S_IEXEC)
    return d


def test_mcp_scanner_parses_real_output(tmp_path: Path, fixtures: Path, monkeypatch) -> None:
    raw = (fixtures / "mcp-scanner-raw.json").read_text()
    bindir = _fake_bin(tmp_path, "mcp-scanner", f"import sys\nsys.stdout.write({raw!r})\n")
    monkeypatch.setenv("PATH", f"{bindir}{os.pathsep}{os.environ['PATH']}")
    tools = write_json(tmp_path / "tools.json", {"tools": []})
    ctx = _ctx(tmp_path, tools_json=tools)
    ctx.env["PATH"] = os.environ["PATH"]
    res = McpScannerAdapter().run(ctx)
    assert res.status == "ok" and res.command[-2:] == ["--tools", str(tools)]
    assert (
        len(res.findings) == 1
        and res.findings[0].severity == "high"
        and res.findings[0].component == "send_email"
    )
    assert "Data Exfiltration" in res.findings[0].category
    assert (tmp_path / "out" / "mcp-scanner.stdout.txt").exists()


def test_adapters_skip_with_reasons(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("PATH", str(tmp_path / "empty"))
    ctx = _ctx(tmp_path)
    ctx.env["PATH"] = str(tmp_path / "empty")
    for cls in (McpScannerAdapter, AgenticRadarAdapter, PromptfooAdapter, SnykAgentScanAdapter):
        r = cls().run(ctx)
        assert r.status == "skipped" and r.reason
    # with the binaries present but nothing to scan / no framework / no token
    bindir = _fake_bin(tmp_path, "mcp-scanner", "print('{}')\n")
    for n in ("agentic-radar", "npx", "uvx"):
        _fake_bin(tmp_path, n, "print('{}')\n")
    ctx.env["PATH"] = str(bindir)
    assert "nothing to scan" in McpScannerAdapter().run(ctx).reason
    assert "--framework" in AgenticRadarAdapter().run(ctx).reason
    assert "promptfooconfig" in PromptfooAdapter().run(ctx).reason
    assert "SNYK_TOKEN" in SnykAgentScanAdapter().run(ctx).reason


def test_agentic_radar_parse_and_promptfoo_parse(tmp_path: Path, fixtures: Path) -> None:
    graph = json.loads((fixtures / "agentic-radar-graph.json").read_text())
    graph["tools"][0]["vulnerabilities"] = [{"name": "Unsafe tool", "severity": "high", "description": "d"}]
    ctx = _ctx(tmp_path, framework="langgraph")
    findings, stats = AgenticRadarAdapter().parse(graph, ctx)
    assert (
        stats["tools"] == 2 and findings[0].severity == "high" and findings[0].component == "lookup_customer"
    )
    pf = {
        "results": {
            "results": [
                {"success": True, "score": 1, "vars": {"q": "a"}},
                {
                    "success": False,
                    "score": 0,
                    "vars": {"q": "b"},
                    "gradingResult": {"reason": "contains PII"},
                    "testCase": {"metadata": {"severity": "high", "pluginId": "pii"}},
                },
            ],
            "stats": {"successes": 1, "failures": 1},
        }
    }
    findings, stats = PromptfooAdapter().parse(pf, ctx)
    assert stats["failed"] == 1 and findings[0].severity == "high" and findings[0].category == "pii"
    findings, stats = SnykAgentScanAdapter().parse(
        {
            "results": [
                {"severity": "medium", "title": "Hidden instruction", "tool": "t1"},
                {"severity": "safe"},
            ]
        },
        ctx,
    )
    assert len(findings) == 2 and findings[0].severity == "medium" and findings[0].component == "t1"


def test_run_scanners_shape(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    ctx.env["PATH"] = str(tmp_path / "empty")
    out = run_scanners(ctx, ["mcp-scanner", "promptfoo"])
    assert out["kind"] == "rk.scan" and len(out["results"]) == 2 and out["summary"]["findings"]["high"] == 0
    assert {t["name"] for t in out["summary"]["tools_skipped"]} == {"mcp-scanner", "promptfoo"}
