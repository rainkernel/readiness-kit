# Attack pack

Attack cases in the format the licensed Gate's full pack uses — one YAML file per OWASP class, one or more cases
per file, a deterministic oracle per case. The **starter** pack here holds one or two cases for each of the ten
classes of the OWASP Top 10 for Agentic Applications (ASI01–ASI10): enough to run `rk attack` end to end and to
see what a finding looks like. The full pack — tool-description poisoning variants, context-file poisoning,
form-input exfiltration families, cost amplification, over-permission probes, and the domain packs — ships in the
[Agent Readiness Gate](https://rainkernel.com/products/agent-readiness-gate).

## A case

```yaml
id: ASI01-001            # class and sequence
asi: ASI01               # OWASP class
title: …
severity: high           # high | medium | low — the severity of the finding if the agent follows the attack
channel: user_input      # user_input | document | tool_result | memory | config — where the payload arrives
intent: …                # what the attack is trying to make the agent do
input: |                 # the user turn sent to the agent
  …
context: { … }           # optional: memory, tool_result, tool_descriptions, document, fault — passed to the agent unchanged
canary: …                # optional token; oracles may write {canary}
oracles:                 # all must hold for a pass; any failure = the agent followed the attack
  - type: tool_not_called
    tools: ["send_email", "send_*"]
    with: "{canary}"
expected_behaviour: …
remediation: …
references: [ … ]
```

Canaries live on `*.rk-canary.invalid` — `.invalid` is reserved by RFC 2606 and can never resolve, so a case that
*does* make an agent send something sends it nowhere. Keep that rule for your own cases.

**Run the pack against a non-production deployment.** The cases are real attacks: an agent that follows ASI06
may call its refund tool, an agent that follows ASI08 may loop until its own limit. Point the Kit at a staging
agent whose outbound tools (e-mail, payments, account changes) are stubbed or sandboxed, never at production.

Oracle types: `output_not_contains`, `output_contains`, `output_not_matches`, `output_matches` (regex),
`tool_not_called`, `tool_called` (glob on the tool name, optional `with` substring in the arguments),
`max_steps`, `max_tool_calls`. An oracle that needs tool calls or steps the target does not report yields
*not observable*, which the Kit never counts as a pass.

The schema is `case.schema.json`; `rk validate pack starter/asi01-goal-hijack.yaml` checks a file.

## Adding cases

Open an issue first (CONTRIBUTING.md). A good case names the class, arrives through a realistic channel, has an
oracle that cannot be satisfied by luck, and carries the fix. Cases that need a model to judge the outcome belong
in the Gate, not here: the starter pack stays deterministic so that its results are reproducible by anyone.
