"""Adapters for the open scanners the Kit orchestrates rather than re-implements."""

from __future__ import annotations

from typing import Any

from readiness_kit import __version__
from readiness_kit.adapters.agentic_radar import AgenticRadarAdapter
from readiness_kit.adapters.base import SEVERITY_ORDER, Adapter, Finding, ScanContext, ScanResult
from readiness_kit.adapters.mcp_scanner import McpScannerAdapter
from readiness_kit.adapters.promptfoo import PromptfooAdapter
from readiness_kit.adapters.snyk_agent_scan import SnykAgentScanAdapter
from readiness_kit.util import KitError, now_iso

ADAPTERS: dict[str, type[Adapter]] = {
    "snyk-agent-scan": SnykAgentScanAdapter,
    "mcp-scanner": McpScannerAdapter,
    "agentic-radar": AgenticRadarAdapter,
    "promptfoo": PromptfooAdapter,
}


def run_scanners(ctx: ScanContext, names: list[str] | None = None) -> dict[str, Any]:
    selected = names or list(ADAPTERS)
    unknown = [n for n in selected if n not in ADAPTERS]
    if unknown:
        raise KitError(f"unknown scanner(s) {unknown}; known: {', '.join(ADAPTERS)}")
    results: list[ScanResult] = [ADAPTERS[n]().run(ctx) for n in selected]
    findings = [f for r in results for f in r.findings]
    return {
        "kind": "rk.scan",
        "kit_version": __version__,
        "created": now_iso(),
        "path": str(ctx.path),
        "summary": {
            "tools_run": [r.tool for r in results if r.status == "ok"],
            "tools_skipped": [{"name": r.tool, "reason": r.reason} for r in results if r.status == "skipped"],
            "tools_failed": [{"name": r.tool, "reason": r.reason} for r in results if r.status == "failed"],
            "findings": {s: sum(1 for f in findings if f.severity == s) for s in SEVERITY_ORDER},
        },
        "results": [r.to_dict() for r in results],
    }


__all__ = ["ADAPTERS", "Adapter", "Finding", "ScanContext", "ScanResult", "run_scanners"]
