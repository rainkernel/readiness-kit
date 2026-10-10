# Changelog

All notable changes to the Readiness Kit. The format follows Keep a Changelog; versions follow SemVer.
A release exists when its tag exists.

## [Unreleased]

## [0.1.0] - 2026-10-18

The first release: the frame under the Agent Readiness Gate.

### Added
- `rk` command line: `init`, `demo`, `split`, `eval`, `attack`, `scan`, `bom`, `cost`, `score`, `validate`, `version`.
- Harness: five target types (`python`, `http`, `openai-chat`, `command`, `replay`) behind one agent contract; ten deterministic graders; the held-out split (`sha256(salt + ":" + id) < fraction`) with the set's hash and the salt recorded in every run.
- Starter attack pack: twelve cases over OWASP ASI01–ASI10 with deterministic oracles, remediation per case, and the case schema the full pack shares.
- Rubric: the eight areas and weights of the Evidence Report's scorecard, bands, scoring rules; scorecard as JSON (schema) and Markdown; measured/declared/not-measured labelled per area; the Evidence Report schema.
- Adapters: Cisco mcp-scanner, Snyk agent-scan, SPLX Agentic Radar, Promptfoo: subprocess runners with raw output kept and findings normalised; skipped tools named with the reason.
- Agent BOM: `agent.yaml` manifest, discovery of MCP client configs, skill files and prompts, Agentic Radar graph import, CycloneDX 1.6 emitter with hashes and `rk:` properties; unversioned and unpinned components flagged.
- Cost: parsers for OpenTelemetry JSONL, OTLP JSON, Langfuse exports and the Kit's own runs; price table by glob; cost per completed task with retries and tool calls; ceiling ratio and monthly projection; unpriced tokens reported.
- Example: a deliberately weak ticket-triage agent with an 80-case synthetic set, synthetic traces, manifest, assessment and example prices; `rk demo` runs everything on it offline.
- Benchmark: support-ticket classification on the Bitext data set, deterministic preparation and the published command.
- Documentation: design note, ten-minute walkthrough, file formats, adapters, benchmark.
- Tests (pytest, offline) and CI on Python 3.10–3.13 on Linux, plus Windows and macOS on 3.12, including a wheel install and demo run from a clean environment, and a dependency audit.
- Release workflow: the tag must match the version in three places; build and twine check; publish to PyPI through a trusted publisher (no API token); GitHub release with the artefacts and this changelog's section; install of the published version on Linux, Windows and macOS. RELEASING.md is the checklist.
