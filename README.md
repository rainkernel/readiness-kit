# Readiness Kit

The frame under the [Agent Readiness Gate](https://rainkernel.com/products/agent-readiness-gate), in public:
a command-line tool that runs an evaluation set against an AI agent and scores it on a held-out split, runs a
starter attack pack mapped to the OWASP Top 10 for Agentic Applications, orchestrates the open agent scanners,
emits a CycloneDX Agent Bill of Materials, computes a cost-per-task baseline from traces, and applies the
eight-area readiness rubric to all of it. The engine — the full attack pack, the domain packs, the seed sets,
the Evidence Report generator and the CI gate — ships in the licensed Gate.

**Release: v0.1.0 · 18 October 2026.** Apache-2.0. Python 3.10+.

```
pip install readiness-kit
rk demo
```

`rk demo` runs the whole pipeline on a bundled, deliberately weak support-ticket agent — offline, no model, no
key — and prints a scorecard in about a second. Then `rk init` and point `rk.yaml` at your own agent:
[the ten-minute walkthrough](docs/WALKTHROUGH.md).

## What it does

| Command | What it measures |
| --- | --- |
| `rk split SET` | Makes the held-out split — `sha256(salt + ":" + id) < fraction` — so the headline number is on cases the agent was not tuned on, and anyone with the salt reproduces it |
| `rk eval` | Runs every case against the agent and grades it (ten deterministic graders); pass rate held-out and dev, by category, with the set's hash in the result |
| `rk attack` | Runs the attack pack — twelve starter cases over ASI01–ASI10, one deterministic oracle set each — and reports which the agent followed, by class and severity |
| `rk scan` | Runs the open scanners you have installed — Cisco mcp-scanner, Snyk agent-scan, SPLX Agentic Radar, Promptfoo — keeps their raw output and normalises the findings; skipped ones are named with the reason |
| `rk bom` | Emits the Agent BOM (CycloneDX 1.6) from `agent.yaml` plus what it discovers on disk — MCP configs, skill files, prompts — and flags everything unversioned or unpinned |
| `rk cost` | Cost per completed task from OpenTelemetry, OTLP or Langfuse traces (or the Kit's own run): tokens, calls, retries; against a ceiling; projected to volume |
| `rk score` | Applies the rubric — eight areas, weights summing to 100 — to the artefacts above and the declared assessment; every area says whether it was measured or declared |

Every command writes a JSON artefact into `runs/` with the hashes and versions a published number must cite;
`rk score` writes the scorecard as JSON and Markdown. The licensed Gate consumes these artefacts unchanged.

## How an agent is wired in

One small contract (docs/FORMATS.md): the Kit sends `{case_id, input, context, metadata}` and reads
`{output, tool_calls, steps, usage}` — only `output` is required. Five target types: `python` (a function
in-process), `http` (an endpoint you control), `openai-chat` (any OpenAI-compatible chat endpoint with your
system prompt), `command` (stdin → stdout), `replay` (a transcript). What an agent does not report, the Kit
marks *not observable*; it never upgrades silence to a pass.

## Repository

| Folder | What it holds |
| --- | --- |
| `src/readiness_kit/harness/` | Targets, evaluation sets, the split, graders, the runner, the attack runner |
| `attack-pack/` | The starter pack — `starter/asi01…asi10.yaml`, twelve cases — and the case schema, in the format the full pack uses |
| `rubric/` | `readiness-rubric.yaml` (areas, weights, bands, scoring rules) and the schemas of the scorecard and the Evidence Report |
| `src/readiness_kit/bom/` | Manifest, discovery, CycloneDX 1.6 emitter |
| `src/readiness_kit/cost/` | Trace parsers (OTel JSONL, OTLP JSON, Langfuse, rk), price table, baseline and projection |
| `src/readiness_kit/adapters/` | The four scanner adapters and the adapter contract |
| `examples/ticket-triage-agent/` | The demo agent, its 80-case set, traces, manifest, assessment and example price table |
| `benchmarks/bitext-support/` | The published benchmark: data preparation, configuration, the one command |
| `docs/` | [DESIGN](docs/DESIGN.md) · [WALKTHROUGH](docs/WALKTHROUGH.md) · [FORMATS](docs/FORMATS.md) · [ADAPTERS](docs/ADAPTERS.md) · [BENCHMARK](docs/BENCHMARK.md) |

A worked example of what the Gate produces from these artefacts — the Evidence Report on a fictional
claims-triage agent — is at
[rainkernel.com/products/agent-readiness-gate/sample-report](https://rainkernel.com/products/agent-readiness-gate/sample-report).

## Principles

**Frame open, engine licensed.** The harness, the starter pack, the rubric, the BOM emitter, the cost baseline
and the adapters are public; the full attack pack, the domain packs, the seed sets, the report generator and the
CI gate are what a licence buys. **Honest version numbers** — v0.1 means v0.1; no release is announced before it
is tagged. **Nothing moves behind a paywall** — what ships in the open tier stays there. **Upstream first** —
where an open scanner should have a feature, we contribute it there before wrapping it here. The full note:
[docs/DESIGN.md](docs/DESIGN.md).

## Releases

- **v0.1.0 · 18 October 2026** — the frame above, with the benchmark on a public support-ticket set
  (docs/BENCHMARK.md) and the ten-minute walkthrough.
- Later releases are announced when they are tagged, here and in the [Lab's log](https://rainkernel.com/lab) —
  never before. CHANGELOG.md has the detail.

## Developing

```
git clone https://github.com/rainkernel/readiness-kit && cd readiness-kit
pip install -e ".[dev]"
pytest -q && ruff check src tests examples
```

CONTRIBUTING.md has the rest: issues first, DCO sign-off, what belongs in the Kit and what belongs in the Gate.

## Security

What the Kit itself does and does not do: no telemetry and no calls home — the only network traffic is to the
target you configure and whatever scanners you install make themselves; scanners run as subprocesses with
explicit arguments, never through a shell; secrets are read from environment variables you name in rk.yaml and
a missing one stops the run before it starts; attack canaries sit on `.invalid` domains that cannot resolve.
Run the attack pack against a staging agent with outbound tools stubbed — the cases are real attacks and your
agent may act on them (docs/WALKTHROUGH.md).

Vulnerabilities in this tool: security@rainkernel.com or a private security advisory on this repository. We
credit reporters. See [SECURITY.md](SECURITY.md) and
[rainkernel.com/.well-known/security.txt](https://rainkernel.com/.well-known/security.txt).

## Licence

Apache-2.0 — see [LICENSE](LICENSE) and [NOTICE](NOTICE). © 2026 Rainkernel Technologies Private Limited.
