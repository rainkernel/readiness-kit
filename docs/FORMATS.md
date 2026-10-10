# File formats

Everything the Kit reads or writes, in one place. Schemas for the inputs are in `schemas/`, `rubric/` and
`attack-pack/`; `rk validate KIND FILE` checks a file.

## The agent contract

What the harness sends to the agent and what it expects back. Only `output` is required in the response.

```json
// request
{"case_id": "t-001", "input": "My parcel never arrived …",
 "context": {"memory": ["…"], "tool_result": "…", "tool_descriptions": {"send_email": "…"}, "document": "…", "fault": "timeout", "channel": "user_input"},
 "metadata": {"kit_version": "0.1.0", "max_steps": 25, "attack": true, "asi": "ASI08"}}

// response
{"output": "category: DELIVERY\npriority: normal\nreply: …",
 "tool_calls": [{"name": "lookup_customer", "arguments": {"key": "c-1"}, "result": "…"}, {"name": "route_ticket", "arguments": {"queue": "delivery"}}],
 "steps": 3,
 "usage": {"input_tokens": 812, "output_tokens": 64, "model": "demo-large"}}
```

`context` carries whatever the case defines; the Kit does not interpret it. An agent that honours `memory`,
`tool_result`, `tool_descriptions`, `document` and `fault` is testable on every starter case; one that ignores
them is still testable on the user-input cases. The Kit records which signals (`output`, `tool_calls`, `steps`,
`usage`) the agent reported, and any oracle or grader that needs a missing one yields *not observable*.

## rk.yaml

```yaml
name: ticket-triage-agent
target:                      # one of:
  type: python               #   python     module:function in-process (cwd added to sys.path)
  module: agent              #   http       POST url, headers (${ENV} expanded), timeout
  function: handle           #   openai-chat base_url, model, api_key, api_key_header, system_prompt[_file], temperature, tools, extra
  cwd: .                     #   command    command (stdin JSON → stdout JSON/text), cwd, timeout, env
  max_steps: 25              #   replay     path (JSONL of {case_id, output, tool_calls, steps, usage})
eval:
  set: evalset.jsonl
  split: split.json
  target_pass_rate: 0.90
  concurrency: 1
attack:
  pack: starter              # or a folder/file of cases
cost:
  traces: [traces.jsonl]
  prices: prices.yaml
  ceiling_per_task: 0.01
  volume_per_month: 50000
bom:
  manifest: agent.yaml
  discover: .
  radar: runs/scan/agentic-radar-graph.json   # optional
scan:
  tools: [mcp-scanner, snyk-agent-scan, agentic-radar, promptfoo]
  config_path: mcp.json      # or tools_json / server_url
  framework: langgraph
  promptfoo_config: promptfooconfig.yaml
assessment: assessment.yaml
runs_dir: runs
```

Paths are relative to the file. Flags override the file. `${NAME}` and `${NAME:-default}` in target values are
read from the environment; an unset variable without a default stops the run before it starts.

## Evaluation set (JSONL, or a YAML list)

```json
{"id": "t-001", "input": "…", "expected": {"category": "DELIVERY"}, "grader": "label", "category": "delivery", "tags": ["real"], "context": {}, "metadata": {}}
```

| Grader | `expected` | Options | Passes when |
| --- | --- | --- | --- |
| `label` | object `{field: value, …}` or a string (field from `options.field`, default `label`) | `fields` to restrict | each field's value is found in the output (JSON key, `field: value` line, or the bare label in a short output) and matches, ignoring case, spaces and hyphens |
| `exact` | string | `strict` (byte-exact) | the whole output equals it (default: case- and whitespace-insensitive) |
| `contains` | string or list | `case_sensitive` | every string appears (score = fraction present) |
| `any_of` | list | `case_sensitive` | at least one appears |
| `not_contains` | string or list | `case_sensitive` | none appears |
| `regex` | pattern or list | `case_sensitive` | every pattern matches |
| `json_field` | object `{dot.path: value}` | none | the output (or its first `{…}`) is JSON and every path equals its value |
| `number` | number | `tolerance`, `relative` | some number in the output is within tolerance |
| `tool_called` | tool name/glob or list | `with` (substring of arguments) | each named tool was called (needs reported tool calls) |
| `tool_not_called` | tool name/glob or list | `with` | none of them was called (needs reported tool calls) |

Default grader: `label` when `expected` is an object, `contains` when it is a string.

## Split file

```json
{"method": "sha256(salt + ':' + id) / 2**256 < holdout_fraction", "salt": "…", "holdout_fraction": 0.33,
 "evalset_path": "…", "evalset_sha256": "…", "created": "…", "counts": {"holdout": 26, "dev": 54},
 "holdout": ["t-002", …], "dev": ["t-001", …]}
```

## Attack case (YAML): see attack-pack/README.md

## Agent manifest (agent.yaml): see the example and schemas/agent-manifest.schema.json

## Assessment (assessment.yaml)

The declared answers, scored as "declared". Keys: `evaluation_set.{source, gated_in_ci, target_pass_rate}`,
`observability.{traces, cost_per_task_recorded, step_and_tool_alerts, eval_metrics_tracked}`,
`data_access.{dedicated_identity, least_privilege, credential_rotation_days, decommission_runbook}`,
`human_in_the_loop.{approval_for_irreversible_actions, escalation_path, operator_can_halt}`,
`compliance.{records_retention_defined, inventory_owner}`, `cost.{ceiling_per_task, volume_per_month}`.

## Traces

| `--format` | What it reads |
| --- | --- |
| `otel` | one span per line: `name`, `context.trace_id/span_id` (or flat keys), `parent_id`, `start_time`, `end_time`, `status.status_code`, `attributes` with `gen_ai.operation.name`, `gen_ai.request.model`, `gen_ai.usage.input_tokens/output_tokens`, `gen_ai.tool.name`, `gen_ai.tool.call.arguments`; a retry is `attempt > 1`, `retry.count > 0` or `gen_ai.request.is_retry` |
| `otlp` | the OTLP JSON envelope (`resourceSpans[].scopeSpans[].spans[]`, key/value attributes) |
| `langfuse` | observations: `type` (GENERATION/SPAN/EVENT), `traceId`, `model`, `usage` or `usageDetails`, `level`, `startTime`, `endTime` |
| `rk` | the Kit's own `runs/eval.json` (usage from the agent's responses, tool calls as tool spans) |

A task is a trace; it is completed unless its root span ended in error or carries `rk.task.status: failed`.
Consecutive identical tool calls in a trace count as retries.

## Price table (prices.yaml)

```yaml
as_of: 2026-10-10
currency: USD
models:
  - { match: "demo-large*", input_per_1m: 2.50, output_per_1m: 10.00 }
```

## Outputs

| File | Kind | Content |
| --- | --- | --- |
| `runs/eval.json` | `rk.eval` | target, set (path, sha256, cases), split (salt, fraction), summary (headline, holdout, dev, all, by_category, usage, latency), results per case with the run |
| `runs/attack.json` | `rk.attack` | pack (path, cases, sha256), summary (counts by status and severity, by_class with findings), results per case with oracles and the run |
| `runs/scan.json` | `rk.scan` | per tool: status, reason, command, findings (severity, title, component, detail, category), counts, raw output path |
| `runs/bom.cdx.json` | CycloneDX 1.6 | the Agent BOM; `runs/bom.json` (`rk.bom`) is the Kit's summary (counts, unversioned, unpinned, data sources) |
| `runs/cost.json` | `rk.cost` | prices used, formats, summary (tasks, completed, per_task, ceiling, ratio, projection, models, unpriced, breakdown), tasks |
| `runs/scorecard.json` | `rk.scorecard` | verdict, total, coverage, findings, the eight areas with points, basis, band, notes and lines; inputs with hashes; schema in `rubric/scorecard.schema.json` |
| `runs/scorecard.md` | Markdown | the same, readable |
