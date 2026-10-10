# Adapters for the open scanners

The Kit orchestrates the open scanners rather than re-implementing them: each adapter runs the tool as a
subprocess, keeps the tool's raw output next to the run (`runs/scan/<tool>.stdout.txt` and any file the tool
writes), and normalises its findings into one shape — `severity` (high/medium/low/info), `title`, `component`,
`detail`, `category`. An adapter that cannot run reports **skipped** with the reason; a tool that ran and broke
reports **failed** with its last lines. Neither is ever counted as a clean result.

Versions and flags below were checked on 10 October 2026 against the tools' published help; a tool that changes
its interface will show up as *failed* with the parse error, and the raw output is kept so nothing is lost.

## Cisco AI Defense MCP Scanner — `mcp-scanner`

- Package `cisco-ai-mcp-scanner` (Apache-2.0); install with `uv tool install cisco-ai-mcp-scanner` or `pipx`.
- What the Kit runs, by what you give it:
  - `--config-path FILE` → `mcp-scanner --analyzers yara --format raw config --config-path FILE` — every server in an MCP client config (Claude Desktop/Code, Cursor, Windsurf, VS Code …), which the scanner starts and interrogates;
  - `--tools-json FILE` → `… static --tools FILE` — a saved `tools/list` result, fully offline (the example ships one with a poisoned description);
  - `--server-url URL` → `… remote --server-url URL`;
  - none of those → the first MCP config file found in the scanned directory (`.mcp.json`, `mcp.json`, `.cursor/mcp.json`, `.vscode/mcp.json`, `claude_desktop_config.json`, …).
- Analyzers: `yara` always (local rules, no key). `api` is added when `MCP_SCANNER_API_KEY` is set, `llm` when `MCP_SCANNER_LLM_API_KEY` is set.
- What is read: `scan_results[]` → per item (`tool_name`, `item_type`) and per analyzer: `severity`, `threat_names`, `threat_summary`, `mcp_taxonomies` (the taxonomy names become the finding's category). SAFE items are not findings.

## Snyk Agent Scan — `snyk-agent-scan`

- Published for `uvx` (`uvx snyk-agent-scan@latest`) and as a standalone binary; no npm or pip package. The analysis runs in Snyk's service, so `SNYK_TOKEN` must be set (a free account provides one) — without it the adapter is skipped and says so.
- What the Kit runs: `snyk-agent-scan scan <target> --json` (or `uvx snyk-agent-scan@latest scan …`), where the target is `--config-path` if given, else the scanned directory. It scans MCP servers (tools, prompts, resources), agent skills (`SKILL.md`), and auto-discovers agent configurations for Claude Code/Desktop, Cursor, Gemini CLI, Windsurf and others.
- What is read: Snyk notes that the JSON "schema depends on the CLI version", so the adapter walks the output for objects carrying a `severity` and takes `title`/`name`/`rule`/`message`, `tool`/`server`/`skill`/`path`, `description`. Any `summary`/`stats` object at the top level is kept in the stats.

## SPLX Agentic Radar — `agentic-radar`

- `pip install agentic-radar` (Apache-2.0). Static analysis of agent code for `langgraph`, `crewai`, `n8n`, `openai-agents` and `autogen`; the framework must be named with `--framework` because the tool scans one at a time.
- What the Kit runs: `agentic-radar scan <framework> -i <dir> -o runs/scan/agentic-radar-graph.json --export-graph-json`, then the HTML report with a second call (`-o runs/scan/agentic-radar-report.html`). "Didn't find any agentic workflow" is reported as skipped, not failed.
- What is read: the graph export — `tools[]` and `nodes[]` with their `vulnerabilities`; the graph also feeds `rk bom --radar runs/scan/agentic-radar-graph.json`, which adds the discovered tools and agents to the BOM. `--harden-prompts` (needs `OPENAI_API_KEY`) is not run by the Kit.

## Promptfoo — `promptfoo`

- Node.js; `npx --yes promptfoo@latest` (or a global install). MIT.
- What the Kit runs: `promptfoo eval -c <config> -o runs/scan/promptfoo-results.json --no-progress-bar`, with the config from `--promptfoo-config` or a `promptfooconfig.yaml` in the scanned directory. Promptfoo talks to the providers itself, so its keys are its own.
- What is read: the results file — every failed test is a finding (severity from the test's `metadata.severity` when a red-team plugin sets one, otherwise medium), with the grading reason as the detail and the plugin or strategy id as the category; pass/fail counts go into the stats.

## Passing extra arguments

In code, `ScanContext.extra_args` maps a tool name to a list of extra command-line arguments. A CLI flag for
this is on the list for v0.2; until then, run the tool by hand with the command the Kit prints and keep its
output next to the run.

## Adding an adapter

Subclass `readiness_kit.adapters.base.Adapter`: set `name`, `needs` (binaries, any one on PATH suffices) and
`install_hint`; implement `command(ctx)` (raise `SkipScan` when there is nothing to scan) and `parse(raw, ctx)`
(return findings and stats); override `load_output` when the tool writes a file instead of stdout. Register it in
`readiness_kit.adapters.ADAPTERS`. Open an issue first — see CONTRIBUTING.md.
