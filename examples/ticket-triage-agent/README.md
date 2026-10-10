# Example: a deliberately weak ticket-triage agent

The agent `rk demo` runs. It classifies a support ticket into one of eleven categories, looks the customer up,
routes the ticket and drafts a reply (with keyword rules, no model, no network), and it follows the Kit's agent
contract (`handle(request) -> dict`), so every command works on it offline.

It is weak on purpose, so the walkthrough shows what a finding looks like: it acts on instructions embedded in
the ticket (ASI01), trusts memory notes (ASI06), retries a failing lookup without a bound (ASI08) and asserts a
refund decision it may not make (ASI09). It resists the other starter cases. Do not copy it into production.

| File | What it is |
| --- | --- |
| `agent.py` | The agent (`python agent.py < request.json` also works) |
| `rk.yaml` | The Kit configuration; copy it next to your own agent and change `target` |
| `evalset.jsonl` | 80 synthetic tickets written for this example (no real customer data), one expected category each; the last 14 are phrased the way customers write rather than the way rules expect |
| `traces.jsonl` | Synthetic OpenTelemetry spans for 40 tasks, written by `make_traces.py` (deterministic) |
| `agent.yaml` | The manifest `rk bom` starts from; two components left unversioned and one skill unpinned on purpose |
| `assessment.yaml` | The declared answers `rk score` reads |
| `prices.yaml` | An example price table for the example's pretend models, not any provider's list price |
| `mcp.json`, `mcp-tools.json` | An MCP client config (discovered by `rk bom`) and a saved `tools/list` with one poisoned description (scanned offline by mcp-scanner) |
| `prompts/system.md`, `skills/refund-policy/SKILL.md` | A prompt and a skill file, hashed into the BOM |

Expected results on the current Kit with `rk demo` (salt `rk-demo-2026`): held-out pass rate 0.84 (21 of 25 held-out cases),
four attack findings (two high), seventeen BOM components with three unversioned, about one cent per completed
task against a one-cent ceiling (1.23×), scorecard 53 (CONDITIONAL) with the two high findings open.
