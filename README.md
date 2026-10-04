# Readiness Kit

The engine of the [Agent Readiness Gate](https://rainkernel.com/products/agent-readiness-gate), in public: the attack corpus, the rubric and the scripts that turn an AI agent's real failures into an evaluation harness and a cost-per-task number.

**Status: v0.1 is tagged on 18 October 2026.** Until that tag exists this repository holds only this README and the licence — we do not announce releases before they are tagged ([why](https://rainkernel.com/open-source)).

## What ships in v0.1

| Folder | What it does |
| --- | --- |
| `attack-pack/` | Agent-specific attack cases mapped to OWASP ASI01–ASI10: tool-description poisoning, SKILL.md and CLAUDE.md context-file poisoning, form-input exfiltration, tool-chain cost amplification, over-permission probes |
| `harness/` | Seeds an evaluation set of 20–50 tasks from an agent's logged failures and real traffic; scores runs against expected outcomes; keeps a held-out split so the number cannot be gamed |
| `cost/` | Cost-per-task baseline: tokens, retries and tool calls per completed task from OpenTelemetry-style traces; projection to production volume |
| `bom/` | Emits a CycloneDX-shaped Agent Bill of Materials — models, prompts, tools, MCP servers, skills, data sources — from a running agent's configuration |
| `rubric/` | The 8-area readiness scorecard and the Evidence Report template for engineering, CISO and audit readers |
| `adapters/` | Runners for snyk-agent-scan, Cisco mcp-scanner, Agentic Radar and Promptfoo, so the Kit orchestrates the open scanners rather than re-implementing them |

A worked example of the output — the Evidence Report on a fictional claims-triage agent — is published at [rainkernel.com/products/agent-readiness-gate/sample-report](https://rainkernel.com/products/agent-readiness-gate/sample-report).

## Roadmap

- **v0.1 · 18 Oct 2026** — corpus, rubric, harness seeding, cost baseline, BOM emitter v0; benchmark on a public support-ticket set.
- **v0.2 · Nov 2026** — report generator, permission-audit checklist, multi-agent and MCP-estate cases.
- **v0.3 · Q1 2027** — multilingual test set (Hindi, Telugu, Tamil, Spanish, German, Japanese); Governor policy examples; the recorder's event schema.

The weekly log of what landed is at [rainkernel.com/lab](https://rainkernel.com/lab).

## Principles

Tools open, evidence paid. Honest version numbers. Upstream first — where an open scanner should have a feature, we contribute it there before wrapping it here.

## Security

Vulnerabilities in this tool: security@rainkernel.com or a private security advisory on this repository. We credit reporters. See [rainkernel.com/.well-known/security.txt](https://rainkernel.com/.well-known/security.txt).

## Licence

Apache-2.0 — see [LICENSE](LICENSE). © 2026 Rainkernel Technologies Private Limited.
