# Readiness Kit

The frame under the [Agent Readiness Gate](https://rainkernel.com/products/agent-readiness-gate), in public: the harness that runs an evaluation set against an AI agent and scores it, the adapters for the open scanners, the eight-area rubric, the Agent BOM emitter, the cost-per-task baseline and a starter attack pack. The engine — the full attack pack, the domain packs, the seed sets, the report generator and the CI gate — ships in the licensed Gate.

**Status: v0.1 is tagged on 18 October 2026.** Until that tag exists this repository holds only this README and the licence — we do not announce releases before they are tagged ([why](https://rainkernel.com/open-source)).

## What ships in v0.1

| Folder | What it does |
| --- | --- |
| `harness/` | Runs an evaluation set against an agent over HTTP or a local adapter; scores each run against expected outcomes; keeps a held-out split so the number cannot be gamed. The seed sets, and the seeding of a set from an agent's own traces, are part of the licensed Gate |
| `attack-pack/` | A starter set of agent-specific attack cases, one or more per OWASP ASI01–ASI10 entry, in the format the full pack uses — enough to run the harness end to end and see what a finding looks like |
| `rubric/` | The eight-area readiness scorecard — areas, weights, bands and what each band means — with the Evidence Report's schema (not its generator) |
| `bom/` | Emits a CycloneDX-shaped Agent Bill of Materials — models, prompts, tools, MCP servers, skills, data sources — from a running agent's configuration |
| `cost/` | Cost-per-task baseline: tokens, retries and tool calls per completed task from OpenTelemetry-style traces; projection to production volume |
| `adapters/` | Runners for snyk-agent-scan, Cisco mcp-scanner, Agentic Radar and Promptfoo, so the Kit orchestrates the open scanners rather than re-implementing them |

A worked example of the output — the Evidence Report on a fictional claims-triage agent — is published at [rainkernel.com/products/agent-readiness-gate/sample-report](https://rainkernel.com/products/agent-readiness-gate/sample-report).

## Releases

- **v0.1 · 18 Oct 2026** — the frame above, with a benchmark run on a public support-ticket set (data set, harness version and command published) and a ten-minute walkthrough.
- Later releases are announced when they are tagged, here and in the [Lab's log](https://rainkernel.com/lab) — never before.

## Principles

Frame open, engine licensed. Honest version numbers. Nothing moves behind a paywall once it has shipped. Upstream first — where an open scanner should have a feature, we contribute it there before wrapping it here.

## Security

Vulnerabilities in this tool: security@rainkernel.com or a private security advisory on this repository. We credit reporters. See [rainkernel.com/.well-known/security.txt](https://rainkernel.com/.well-known/security.txt).

## Licence

Apache-2.0 — see [LICENSE](LICENSE). © 2026 Rainkernel Technologies Private Limited.
