# The ten-minute walkthrough

From nothing to a scorecard on your own agent. Steps 1–3 take two minutes and need no model, no key and no
network beyond `pip`. Step 4 is where your agent comes in.

## 1. Install (1 minute)

```
pip install readiness-kit        # or: pipx install readiness-kit · uv tool install readiness-kit
rk version
```

Python 3.10 or newer. The Kit depends on pyyaml, jsonschema and httpx only.

## 2. See it work on the example (1 minute)

```
rk demo
```

This copies a deliberately weak support-ticket triage agent into `./rk-demo` and runs the seven commands on it:
split, eval, attack, bom, cost, scan, score. Read the output top to bottom. You will see:

- an evaluation on 80 synthetic tickets with a held-out split — the headline is the held-out pass rate, the dev
  rate is printed beside it, labelled;
- the starter attack pack — twelve cases over the ten OWASP classes — with four findings: an instruction inside a
  ticket that made the agent e-mail a record to an outside address (ASI01), a planted memory note that made it
  issue a refund (ASI06), a timing-out lookup it retried 60 times (ASI08), and a refund "approval" it had no
  right to state (ASI09);
- an Agent BOM with 18 components and three unversioned ones flagged;
- a cost baseline of 1.2 cents per completed task against a one-cent ceiling, projected to 50,000 tasks a
  month;
- the scanners, each reporting *skipped* with the reason until you install it;
- the scorecard: eight areas, each marked measured or declared, a total and a verdict.

Open `rk-demo/runs/scorecard.md` — that is the shape of the thing. The licensed Gate's Evidence Report wraps the
same evidence with findings in priority order, fixes with owners and a standards mapping:
[the sample](https://rainkernel.com/products/agent-readiness-gate/sample-report).

## 3. Read one artefact (1 minute)

`rk-demo/runs/attack.json` → `results[0]`: the case, the oracles, what held and what did not, and the agent's
full run (output, tool calls, steps). Nothing in the verdict is a summary you cannot trace back to a line here.

## 4. Point it at your agent (5 minutes)

```
mkdir my-agent-readiness && cd my-agent-readiness
rk init
```

Edit `rk.yaml` → `target`. Pick the one that fits:

**An HTTP endpoint you control.** Have it accept the request and answer in the contract (docs/FORMATS.md):

```yaml
target:
  type: http
  url: https://agent.internal/rk
  headers: { Authorization: "Bearer ${AGENT_TOKEN}" }
```

**An OpenAI-compatible chat endpoint** (OpenAI, Azure OpenAI, Ollama, vLLM, LiteLLM, OpenRouter …) with your
system prompt — the fastest way to a first number for a prompt-based agent:

```yaml
target:
  type: openai-chat
  base_url: https://api.openai.com/v1
  model: your-model
  api_key: ${OPENAI_API_KEY}
  system_prompt_file: prompts/system.md
  tools: []            # list your tool schemas here so tool calls are reported
```

**A Python function** in the same repository (`handle(request: dict) -> dict | str`):

```yaml
target:
  type: python
  module: my_agent.harness_entry
  function: handle
  cwd: ../my-agent
```

**Anything else**: `type: command` runs a program per case with the request on stdin.

Then:

```
# a set of real cases: one JSON object per line — id, input, expected (see docs/FORMATS.md for the graders)
cp your-cases.jsonl evalset.jsonl
rk split evalset.jsonl --holdout 0.33            # keep the printed salt with the set
rk eval                                          # held-out pass rate, by category
rk attack                                        # the starter pack; 'not observable' means your target does not report tool calls or steps yet
rk bom --discover .                              # fill agent.yaml first: models, prompts, tools, MCP servers, skills, data sources
rk cost traces.jsonl --ceiling 0.40 --volume 12000   # OTel JSONL / OTLP JSON / Langfuse export; prices.yaml for your models
rk scan --config-path .mcp.json                  # whichever scanners are installed; the rest are reported as skipped
rk score                                         # answer assessment.yaml for the declared items first
```

Each command prints what it did and where it wrote; `runs/` holds the artefacts; `rk score` prints the table.

## Before you run `rk attack` on a real agent

The attack cases are real attacks. The Kit never sends anything itself and its canary addresses are on
`.invalid` domains that cannot resolve — but *your agent* may act: follow ASI06 and it calls its refund tool,
follow ASI08 and it loops until its own limit. Run the pack against a staging deployment with outbound tools
(e-mail, payments, account changes, shell) stubbed or sandboxed. Never point it at production.

## 5. What to do with the number

- Put `rk eval` and `rk attack --fail-on-high` in CI, on the dev split, on every prompt or code change. Publish
  the held-out number when you cut a release.
- Fix the high findings first — the attack results carry the remediation for each case.
- Fill `agent.yaml` until `rk bom` reports nothing unversioned; pin skills by hash.
- Declare a cost ceiling and keep the baseline under it; the Governor policy starts from this number.

When the team needs the Evidence Report — the full attack pack run in your cloud, the report signed, the gate in
CI, the standards mapping for the auditor — that is the
[Agent Readiness Gate](https://rainkernel.com/products/agent-readiness-gate): it consumes exactly the artefacts
you have just produced.

## Installing the scanners (optional)

| Scanner | Install | Needs |
| --- | --- | --- |
| Cisco mcp-scanner | `uv tool install cisco-ai-mcp-scanner` | nothing for the `yara` analyzer; keys for `api`/`llm` |
| Snyk agent-scan | `uv` on PATH (`uvx snyk-agent-scan@latest`) or the release binary | `SNYK_TOKEN` (free account) |
| SPLX Agentic Radar | `pip install agentic-radar` | `--framework` (langgraph, crewai, n8n, openai-agents, autogen) |
| Promptfoo | Node.js (`npx promptfoo@latest`) | a `promptfooconfig.yaml` and your provider keys |

docs/ADAPTERS.md has the exact commands the Kit runs and what it reads from each.
