"""Snyk Agent Scan (``snyk-agent-scan``): MCP servers, agent skills and the auto-discovered agent configurations
of Claude Code/Desktop, Cursor, Gemini CLI, Windsurf and others.

Snyk publishes it for ``uvx`` (``uvx snyk-agent-scan@latest``) and as a standalone binary, and the analysis needs
a Snyk account: ``SNYK_TOKEN`` must be set, or the adapter is skipped with that reason. The Kit runs
``scan <target> --json`` on the MCP config, skill folder or directory it is pointed at. The JSON shape
"depends on the CLI version", so findings are collected by walking the output for objects with a severity.
"""

from __future__ import annotations

import shutil
from typing import Any

from readiness_kit.adapters.base import Adapter, Finding, ScanContext, norm_severity, walk_findings


class SnykAgentScanAdapter(Adapter):
    name = "snyk-agent-scan"
    needs = ["snyk-agent-scan", "uvx"]
    install_hint = "install uv (https://docs.astral.sh/uv/) and run `uvx snyk-agent-scan@latest`, or download the binary from github.com/snyk/agent-scan/releases"

    def available(self, ctx: ScanContext) -> tuple[bool, str]:
        ok, why = super().available(ctx)
        if not ok:
            return ok, why
        if not ctx.env.get("SNYK_TOKEN"):
            return (
                False,
                "SNYK_TOKEN is not set (a free Snyk account provides one; the analysis runs in Snyk's service)",
            )
        return True, ""

    def command(self, ctx: ScanContext) -> list[str]:
        exe = (
            ["snyk-agent-scan"]
            if shutil.which("snyk-agent-scan", path=ctx.env.get("PATH"))
            else ["uvx", "snyk-agent-scan@latest"]
        )
        target = str(ctx.config_path or ctx.path)
        return [*exe, "scan", target, "--json", *ctx.extra_args.get(self.name, [])]

    def parse(self, raw: Any, ctx: ScanContext) -> tuple[list[Finding], dict[str, Any]]:
        objs: list[dict[str, Any]] = []
        walk_findings(raw, objs)
        findings: list[Finding] = []
        for o in objs:
            sev = norm_severity(o.get("severity"))
            title = str(
                o.get("title")
                or o.get("name")
                or o.get("rule")
                or o.get("id")
                or o.get("message")
                or "finding"
            )
            comp = str(
                o.get("tool")
                or o.get("tool_name")
                or o.get("server")
                or o.get("skill")
                or o.get("path")
                or o.get("component")
                or ""
            )
            detail = str(o.get("description") or o.get("message") or o.get("details") or "")
            findings.append(
                Finding(
                    tool=self.name,
                    severity=sev,
                    title=title,
                    component=comp,
                    detail=detail[:500],
                    category=str(o.get("category") or o.get("type") or ""),
                    raw={k: o[k] for k in list(o)[:12]},
                )
            )
        stats = {"objects_with_severity": len(objs)}
        if isinstance(raw, dict):
            for k in ("summary", "stats", "counts"):
                if k in raw:
                    stats[k] = raw[k]
        return findings, stats
