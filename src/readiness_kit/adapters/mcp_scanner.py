"""Cisco AI Defense MCP Scanner (``mcp-scanner``, package ``cisco-ai-mcp-scanner``, Apache-2.0).

What the Kit runs, in order of preference:
  * ``--config-path`` given → ``mcp-scanner … config --config-path FILE`` (every server in an MCP client config)
  * ``--tools-json`` given  → ``mcp-scanner … static --tools FILE`` (a saved ``tools/list`` result; offline)
  * ``--server-url`` given  → ``mcp-scanner … remote --server-url URL``
  * otherwise, the first MCP config file found in the scanned directory (the list in bom/discover.py)
Analyzers: ``yara`` always (local rules, no key); ``api`` and ``llm`` are added when their keys are in the
environment (``MCP_SCANNER_API_KEY``, ``MCP_SCANNER_LLM_API_KEY``). Output is read from ``--format raw``.
"""

from __future__ import annotations

from typing import Any

from readiness_kit.adapters.base import Adapter, Finding, ScanContext, SkipScan, norm_severity
from readiness_kit.bom.discover import MCP_CONFIG_FILES


class McpScannerAdapter(Adapter):
    name = "mcp-scanner"
    needs = ["mcp-scanner"]
    install_hint = (
        "install with `uv tool install cisco-ai-mcp-scanner` (or `pipx install cisco-ai-mcp-scanner`)"
    )

    def analyzers(self, ctx: ScanContext) -> str:
        a = ["yara"]
        if ctx.env.get("MCP_SCANNER_API_KEY"):
            a.append("api")
        if ctx.env.get("MCP_SCANNER_LLM_API_KEY"):
            a.append("llm")
        return ",".join(a)

    def command(self, ctx: ScanContext) -> list[str]:
        base = [
            "mcp-scanner",
            "--analyzers",
            self.analyzers(ctx),
            "--format",
            "raw",
            *ctx.extra_args.get(self.name, []),
        ]
        if ctx.config_path:
            return [*base, "config", "--config-path", str(ctx.config_path)]
        if ctx.tools_json:
            return [*base, "static", "--tools", str(ctx.tools_json)]
        if ctx.server_url:
            return [*base, "remote", "--server-url", ctx.server_url]
        for rel in MCP_CONFIG_FILES:
            p = ctx.path / rel
            if p.is_file():
                return [*base, "config", "--config-path", str(p)]
        raise SkipScan(
            "nothing to scan: give --config-path (an MCP client config), --tools-json (a saved tools/list) or --server-url"
        )

    def parse(self, raw: Any, ctx: ScanContext) -> tuple[list[Finding], dict[str, Any]]:
        findings: list[Finding] = []
        results = raw.get("scan_results", []) if isinstance(raw, dict) else []
        if isinstance(raw, list):
            results = raw
        items = 0
        for r in results:
            if not isinstance(r, dict):
                continue
            items += 1
            comp = str(r.get("tool_name") or r.get("name") or r.get("item_type") or "")
            for analyzer, f in (r.get("findings") or {}).items():
                if not isinstance(f, dict):
                    continue
                sev = norm_severity(f.get("severity"))
                if sev == "info" and str(f.get("severity", "")).upper() in ("SAFE", "", "NONE"):
                    continue
                threats = f.get("threat_names") or []
                taxonomies = f.get("mcp_taxonomies") or []
                cat = ", ".join(
                    str(t.get("aitech_name") or t.get("scanner_category") or "")
                    for t in taxonomies
                    if isinstance(t, dict)
                )
                findings.append(
                    Finding(
                        tool=self.name,
                        severity=sev,
                        title=f"{analyzer}: {', '.join(str(t) for t in threats) or f.get('threat_summary') or 'finding'}",
                        component=comp,
                        detail=str(f.get("threat_summary") or ""),
                        category=cat,
                        raw={
                            "analyzer": analyzer,
                            "item_type": r.get("item_type"),
                            "server_url": raw.get("server_url") if isinstance(raw, dict) else None,
                        },
                    )
                )
        return findings, {
            "items_scanned": items,
            "analyzers": raw.get("requested_analyzers") if isinstance(raw, dict) else None,
        }
