# Readiness Kit design note

*v0.1 · frozen 10 October 2026 · Rainkernel Technologies Private Limited*

This note fixes what the Kit is, where the open-core line runs, and the rules that keep its numbers honest. It is
the document a contributor reads before proposing a change and the one a buyer reads to understand what the
licensed Gate adds.

## 1. What the Kit is

The Kit is the **frame** under the Agent Readiness Gate: the part of the product that runs things and measures
things, published under Apache-2.0 so that a buyer can read exactly what the Gate runs and how it scores, and an
integrator can build on it. One command-line tool, `rk`, with seven working commands:

| Command | What it measures | Artefact |
| --- | --- | --- |
| `rk split` | (makes the held-out split) | `split.json` |
| `rk eval` | Pass rate on an evaluation set, held-out and dev, by category | `runs/eval.json` |
| `rk attack` | Which OWASP ASI01–ASI10 attack cases the agent followed | `runs/attack.json` |
| `rk scan` | Findings from the open scanners on the agent's tools and configuration | `runs/scan.json` (+ raw outputs) |
| `rk bom` | What the agent is made of (models, prompts, tools, MCP servers, skills, data) as CycloneDX 1.6 | `runs/bom.cdx.json`, `runs/bom.json` |
| `rk cost` | Cost per completed task from traces; projection to volume | `runs/cost.json` |
| `rk score` | The eight-area scorecard from everything above plus the declared assessment | `runs/scorecard.json`, `.md` |

`rk demo` runs all of them on a bundled, deliberately weak agent, offline, in a second. `rk init` writes the
templates. `rk validate` checks files against the schemas.

## 2. The open-core line

The line is drawn by a single rule: **the Kit shows an engineer the problem; the Gate is what their company
buys to solve it on every release.** Anything that *measures* is in the Kit. Anything that *produces the
deliverable a buyer pays for* (the full attack corpus, the generated report, the gate that blocks a release)
is in the Gate.

| In the Kit (Apache-2.0) | In the Gate (licensed) |
| --- | --- |
| Harness: targets, graders, runner, held-out split | Seed sets; seeding a set from the agent's own production failures |
| Starter attack pack: 12 cases, one or two per OWASP class, deterministic oracles | Full attack pack: tool-description poisoning families, context-file poisoning, form-input exfiltration families, cost amplification, over-permission probes; domain packs (customer support first) |
| Rubric: eight areas, weights, bands, scoring rules; scorecard JSON + Markdown | Evidence Report generator: findings with fixes in priority order, effort and owners, standards mapping (NIST AI RMF, ISO/IEC 42001, EU AI Act), signed |
| Adapters for snyk-agent-scan, mcp-scanner, agentic-radar, promptfoo | Permission-audit module (identities, roles, rotation, blast radius) |
| Agent BOM emitter (CycloneDX 1.6) and discovery | Continuous attestation of the BOM (MCPSentry) |
| Cost-per-task baseline and projection | Governor policy derivation (ceilings, caps) |
| Schemas: evaluation case, attack case, agent manifest, scorecard, Evidence Report | CI gate that fails a regressing release and re-generates the report |

Three consequences:

1. **Nothing moves behind the paywall.** What ships in v0.1 stays open. New licensed capability is added to
   the Gate, never taken out of the Kit.
2. **The Gate consumes the Kit's artefacts unchanged.** `eval.json`, `attack.json`, `scan.json`, `bom.cdx.json`,
   `cost.json` and `scorecard.json` are the Gate's inputs. A team that ran the Kit has done the Gate's first day.
3. **The schemas are public, the generator is not.** The Evidence Report schema is in `rubric/` so buyers know
   the shape of what they will receive and integrators can consume it; the generator is the licence.

## 3. The honesty rules

These are the rules that make a number from the Kit worth publishing. They are enforced in code, not in prose.

- **Held-out by construction.** The split is `sha256(salt + ":" + id) < fraction`: a function of the salt and the
  ids only, so it does not change when cases are re-ordered or appended, and anyone with the salt reproduces it.
  The headline is always the held-out pass rate; the dev rate is printed beside it, labelled.
- **Hashes in every artefact.** The evaluation set's sha256, the split's salt and the Kit's version are recorded
  in `eval.json`; the pack's hash in `attack.json`; the rubric's hash in `scorecard.json`. A published number
  cites them.
- **No model in the loop.** Every grader and every oracle is deterministic. A pass rate from the Kit depends on
  nothing but the set, the split and the agent. Model-judged rubrics belong in the Gate.
- **Not observable is not a pass.** An oracle that needs tool calls or steps from a target that reports none yields
  *not observable* and the class is marked n/a. The Kit never upgrades silence to safety.
- **Measured and declared are labelled.** The scorecard says, per area, whether its points came from an
  artefact (measured), from `assessment.yaml` (declared), or both; areas with neither score zero and the verdict
  line says the score is a floor.
- **Skipped scanners are reported, with the reason.** A scanner that is not installed or has no token is a fact
  about the machine; the Kit says so instead of counting it as clean.
- **Unpriced tokens are counted.** Cost is understated when a model has no price in the table; the share of such
  tokens is printed and noted in the scorecard.

## 4. The agent contract

The Kit talks to an agent through one small contract (docs/FORMATS.md):

```
request  → {"case_id", "input", "context": {...}, "metadata": {...}}
response ← {"output", "tool_calls": [{"name", "arguments", "result"}], "steps", "usage": {...}}
```

Only `output` is required. Five target types implement it: `python` (in-process), `http` (POST), `openai-chat`
(any OpenAI-compatible endpoint), `command` (stdin/stdout) and `replay` (a transcript file). The more an agent
reports, the more the Kit can judge; what it does not report is marked not observable, never guessed.

## 5. The rubric

Eight areas, weights summing to 100, the same areas and weights as section 7 of the published sample Evidence
Report: Evaluation set 16, Guardrails 14, Cost per task 12, Observability 12, Data access 12,
Human-in-the-loop 10, Reliability 12, Compliance 12. Verdict: READY at 80 or more with no high finding open;
CONDITIONAL at 50–79, or at 80+ with a high finding; NOT READY below 50. The scoring rules per area are in
`rubric/readiness-rubric.yaml` (summary) and `src/readiness_kit/rubric/score.py` (code); a change to one is a
change to both.

## 6. What v0.1 does not do

- It does not judge free-text quality with a model, and it does not seed an evaluation set from traces.
- It does not inject tool results or faults into an agent it does not control; the `context` field carries them,
  and an agent wired through `http` or `python` decides what to do with them. The example agent honours them.
- It does not attest a BOM over time, audit permissions in a cloud account, or enforce a cost ceiling. Those are
  products.
- It does not ship a provider price list as fact. The example table is labelled as an example.

## 7. Repository layout

```
rubric/           readiness-rubric.yaml, scorecard.schema.json, evidence-report.schema.json
attack-pack/      case.schema.json, README.md, starter/asi01…asi10 (12 cases)
schemas/          evalset.schema.json, agent-manifest.schema.json
src/readiness_kit/
  harness/        targets, evalset, split, graders, runner, attacks
  adapters/       base, snyk_agent_scan, mcp_scanner, agentic_radar, promptfoo
  bom/            manifest, discover, cyclonedx
  cost/           traces, prices, baseline
  rubric/         model, score, render
  cli.py, config.py, demo.py, schemas.py, paths.py, util.py
examples/ticket-triage-agent/   the demo agent, its set, traces, manifest, assessment, prices
benchmarks/bitext-support/      the published benchmark: prepare.py, rk.yaml, run.sh
docs/             DESIGN (this), WALKTHROUGH, FORMATS, ADAPTERS, BENCHMARK
tests/            pytest suite, offline, a few seconds
```

Python ≥ 3.10; dependencies pyyaml, jsonschema, httpx. The wheel bundles `rubric/`, `attack-pack/`, `schemas/`
and the example under `readiness_kit/_data/`, so `pip install readiness-kit && rk demo` works with no checkout.

## 8. Governance

Apache-2.0 with a Developer Certificate of Origin sign-off on commits (no separate CLA). CODEOWNERS routes every
change to a maintainer. Security reports go to the private advisory or security@rainkernel.com (SECURITY.md).
Releases are tagged before they are announced; v0.1.0 is the first tag.
