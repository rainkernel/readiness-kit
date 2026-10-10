"""SPLX Agentic Radar (``agentic-radar``, Apache-2.0): static analysis of agent code for LangGraph, CrewAI, n8n,
OpenAI Agents and AutoGen: the workflow graph, the tools, and known vulnerabilities per tool.

The Kit runs ``agentic-radar scan <framework> -i <dir> -o <out>/agentic-radar-graph.json --export-graph-json``
and reads the graph: findings come from the ``vulnerabilities`` lists on tools and nodes; the graph file also feeds
``rk bom --radar``. The framework must be named (``--framework``), because the tool scans one at a time. The HTML
report is written alongside (``agentic-radar-report.html``) in a second call when the first succeeds.
"""

from __future__ import annotations

import contextlib
import json
import subprocess
from typing import Any

from readiness_kit.adapters.base import Adapter, Finding, ScanContext, SkipScan, norm_severity

FRAMEWORKS = ("langgraph", "crewai", "n8n", "openai-agents", "autogen")


class AgenticRadarAdapter(Adapter):
    name = "agentic-radar"
    needs = ["agentic-radar"]
    install_hint = "install with `pip install agentic-radar` (or `uv tool install agentic-radar`)"

    def command(self, ctx: ScanContext) -> list[str]:
        if not ctx.framework:
            raise SkipScan(
                f"pass --framework ({'|'.join(FRAMEWORKS)}) so Agentic Radar knows what to look for"
            )
        if ctx.framework not in FRAMEWORKS:
            raise SkipScan(f"unknown framework '{ctx.framework}' (one of {', '.join(FRAMEWORKS)})")
        out = ctx.out_dir / "agentic-radar-graph.json"
        return [
            "agentic-radar",
            "scan",
            ctx.framework,
            "-i",
            str(ctx.path),
            "-o",
            str(out),
            "--export-graph-json",
            *ctx.extra_args.get(self.name, []),
        ]

    def load_output(self, proc: subprocess.CompletedProcess[str], ctx: ScanContext) -> Any:
        out = ctx.out_dir / "agentic-radar-graph.json"
        if not out.exists():
            text = (proc.stdout + proc.stderr).lower()
            if "didn't find any agentic workflow" in text or "did not find any" in text:
                raise SkipScan(f"Agentic Radar found no {ctx.framework} workflow under {ctx.path}")
            raise ValueError(f"no graph written ({proc.stderr.strip()[-200:] or proc.stdout.strip()[-200:]})")
        # the HTML report, for people; failure here is not a scan failure
        with contextlib.suppress(OSError, subprocess.TimeoutExpired):
            subprocess.run(
                [
                    "agentic-radar",
                    "scan",
                    str(ctx.framework),
                    "-i",
                    str(ctx.path),
                    "-o",
                    str(ctx.out_dir / "agentic-radar-report.html"),
                ],
                capture_output=True,
                text=True,
                timeout=ctx.timeout,
                env=ctx.env,
                check=False,
            )
        return json.loads(out.read_text(encoding="utf-8"))

    def parse(self, raw: Any, ctx: ScanContext) -> tuple[list[Finding], dict[str, Any]]:
        findings: list[Finding] = []
        tools = raw.get("tools") or []
        nodes = raw.get("nodes") or []
        for item in [*tools, *nodes]:
            if not isinstance(item, dict):
                continue
            for v in item.get("vulnerabilities") or []:
                if isinstance(v, dict):
                    findings.append(
                        Finding(
                            tool=self.name,
                            severity=norm_severity(v.get("severity") or "medium"),
                            title=str(v.get("name") or v.get("title") or v.get("id") or "vulnerability"),
                            component=str(item.get("name") or ""),
                            detail=str(v.get("description") or v.get("remediation") or "")[:500],
                            category=str(v.get("category") or ""),
                            raw=v,
                        )
                    )
                else:
                    findings.append(
                        Finding(
                            tool=self.name,
                            severity="medium",
                            title=str(v),
                            component=str(item.get("name") or ""),
                        )
                    )
        stats = {
            "graph": raw.get("name"),
            "nodes": len(nodes),
            "edges": len(raw.get("edges") or []),
            "agents": len(raw.get("agents") or []),
            "tools": len(tools),
            "graph_path": str(ctx.out_dir / "agentic-radar-graph.json"),
        }
        return findings, stats
