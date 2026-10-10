"""Write traces.jsonl: synthetic OpenTelemetry spans for 40 triage tasks, in the shape the OTel SDK's console
and file exporters produce (one span per line, GenAI semantic-convention attributes). Deterministic: the same
file comes out every time, so the walkthrough's cost figures are reproducible.

    python make_traces.py            # rewrites traces.jsonl next to this script
"""

from __future__ import annotations

import json
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

rng = random.Random(20261018)
T0 = datetime(2026, 10, 1, 9, 0, tzinfo=timezone.utc)


def hexid(n: int) -> str:
    return "".join(rng.choice("0123456789abcdef") for _ in range(n))


def span(
    trace_id: str,
    span_id: str,
    parent: str | None,
    name: str,
    start: datetime,
    dur_ms: int,
    attrs: dict,
    status: str = "OK",
) -> dict:
    end = start + timedelta(milliseconds=dur_ms)
    return {
        "name": name,
        "context": {"trace_id": trace_id, "span_id": span_id, "trace_state": "[]"},
        "kind": "SpanKind.INTERNAL",
        "parent_id": parent,
        "start_time": start.isoformat().replace("+00:00", "Z"),
        "end_time": end.isoformat().replace("+00:00", "Z"),
        "status": {"status_code": status},
        "attributes": attrs,
        "resource": {"attributes": {"service.name": "ticket-triage-agent", "service.version": "0.3.0"}},
    }


def main() -> None:
    rows: list[dict] = []
    t = T0
    for i in range(40):
        trace = hexid(32)
        root = hexid(16)
        t = t + timedelta(seconds=rng.randint(20, 90))
        failed = i in (13, 29)  # two tasks that did not complete
        timeouts = i in (5, 11, 22, 23, 31)  # tasks where the CRM lookup timed out and was retried
        cur = t
        children: list[dict] = []
        # extraction call on the small model
        ext_in, ext_out = rng.randint(380, 520), rng.randint(40, 70)
        children.append(
            span(
                trace,
                hexid(16),
                root,
                "chat demo-small",
                cur,
                rng.randint(300, 700),
                {
                    "gen_ai.operation.name": "chat",
                    "gen_ai.request.model": "demo-small",
                    "gen_ai.response.model": "demo-small-2026-08",
                    "gen_ai.usage.input_tokens": ext_in,
                    "gen_ai.usage.output_tokens": ext_out,
                },
            )
        )
        cur += timedelta(milliseconds=800)
        # CRM lookup, with retries on timeout
        attempts = rng.randint(3, 6) if timeouts else 1
        for a in range(attempts):
            ok = a == attempts - 1 or not timeouts
            attrs = {
                "gen_ai.tool.name": "lookup_customer",
                "gen_ai.tool.call.arguments": json.dumps({"key": f"c-{1000 + i}"}),
                "rpc.system": "mcp",
            }
            if a > 0:
                attrs["attempt"] = a + 1
            children.append(
                span(
                    trace,
                    hexid(16),
                    root,
                    "execute_tool lookup_customer",
                    cur,
                    5000 if not ok else rng.randint(80, 200),
                    attrs,
                    status="OK" if ok else "ERROR",
                )
            )
            cur += timedelta(milliseconds=5100 if not ok else 250)
        if rng.random() < 0.6:
            children.append(
                span(
                    trace,
                    hexid(16),
                    root,
                    "execute_tool lookup_order",
                    cur,
                    rng.randint(90, 220),
                    {
                        "gen_ai.tool.name": "lookup_order",
                        "gen_ai.tool.call.arguments": json.dumps({"order_id": str(40000 + i)}),
                        "rpc.system": "mcp",
                    },
                )
            )
            cur += timedelta(milliseconds=300)
        # classification + reply on the large model (a re-plan on some tasks doubles it)
        cls_in, cls_out = rng.randint(2600, 3400), rng.randint(140, 260)
        children.append(
            span(
                trace,
                hexid(16),
                root,
                "chat demo-large",
                cur,
                rng.randint(900, 2200),
                {
                    "gen_ai.operation.name": "chat",
                    "gen_ai.request.model": "demo-large",
                    "gen_ai.response.model": "demo-large-2026-06",
                    "gen_ai.usage.input_tokens": cls_in,
                    "gen_ai.usage.output_tokens": cls_out,
                },
            )
        )
        cur += timedelta(milliseconds=2300)
        if i % 4 == 0:
            children.append(
                span(
                    trace,
                    hexid(16),
                    root,
                    "chat demo-large",
                    cur,
                    rng.randint(900, 2200),
                    {
                        "gen_ai.operation.name": "chat",
                        "gen_ai.request.model": "demo-large",
                        "gen_ai.response.model": "demo-large-2026-06",
                        "gen_ai.usage.input_tokens": cls_in + 300,
                        "gen_ai.usage.output_tokens": rng.randint(120, 200),
                        "gen_ai.request.is_retry": True,
                    },
                )
            )
            cur += timedelta(milliseconds=2300)
        children.append(
            span(
                trace,
                hexid(16),
                root,
                "execute_tool route_ticket",
                cur,
                rng.randint(40, 90),
                {
                    "gen_ai.tool.name": "route_ticket",
                    "gen_ai.tool.call.arguments": json.dumps({"queue": "refund", "priority": "normal"}),
                },
            )
        )
        cur += timedelta(milliseconds=100)
        total_ms = int((cur - t).total_seconds() * 1000)
        rows.append(
            span(
                trace,
                root,
                None,
                "triage ticket",
                t,
                total_ms,
                {
                    "rk.task": "triage",
                    "ticket.id": f"T-{5000 + i}",
                    "rk.task.status": "failed" if failed else "completed",
                },
                status="ERROR" if failed else "OK",
            )
        )
        rows.extend(children)
    out = Path(__file__).with_name("traces.jsonl")
    with open(out, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    print(f"{len(rows)} spans for 40 tasks → {out}")


if __name__ == "__main__":
    main()
