"""Cost per completed task, from spans, and its projection to production volume.

A *task* is a trace. It is *completed* unless its root span (or any span, when there is no root) ended in error
or carries ``rk.task.status: failed``. Cost is summed over the LLM spans of completed tasks with the price table;
tool calls, retries and steps are counted so the report can say where the money goes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from readiness_kit import __version__
from readiness_kit.cost.prices import PriceTable
from readiness_kit.cost.traces import Span
from readiness_kit.util import now_iso, pct


@dataclass
class Task:
    trace_id: str
    completed: bool
    llm_calls: int = 0
    tool_calls: int = 0
    retries: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    retry_input_tokens: int = 0
    retry_output_tokens: int = 0
    cost: float = 0.0
    retry_cost: float = 0.0
    unpriced_tokens: int = 0
    models: dict[str, int] = field(default_factory=dict)
    duration_s: float | None = None


def _group(spans: list[Span]) -> dict[str, list[Span]]:
    out: dict[str, list[Span]] = {}
    for s in spans:
        out.setdefault(s.trace_id, []).append(s)
    return out


def _completed(spans: list[Span]) -> bool:
    roots = [s for s in spans if s.parent_id is None]
    judged = roots or spans
    for s in judged:
        if s.status == "error":
            return False
        if str(s.attrs.get("rk.task.status", "")).lower() in ("failed", "error", "abandoned"):
            return False
    return True


def _mark_consecutive_tool_retries(spans: list[Span]) -> None:
    """A tool span repeating the previous tool span's name and arguments in the same trace is a retry."""
    ordered = sorted(spans, key=lambda s: (s.start or 0.0, s.span_id))
    last: tuple[str, str] | None = None
    for s in ordered:
        if s.kind != "tool":
            continue
        args = (
            s.attrs.get("gen_ai.tool.call.arguments")
            or s.attrs.get("tool.arguments")
            or s.attrs.get("input")
            or ""
        )
        key = (str(s.attrs.get("gen_ai.tool.name") or s.name), str(args))
        if last is not None and key == last:
            s.retry = True
        last = key


def build_tasks(spans: list[Span], prices: PriceTable) -> list[Task]:
    tasks: list[Task] = []
    for trace_id, group in _group(spans).items():
        _mark_consecutive_tool_retries(group)
        t = Task(trace_id=trace_id, completed=_completed(group))
        starts = [s.start for s in group if s.start is not None]
        ends = [s.end for s in group if s.end is not None]
        if starts and ends:
            t.duration_s = round(max(ends) - min(starts), 3)
        for s in group:
            if s.kind == "llm":
                t.llm_calls += 1
                t.input_tokens += s.input_tokens
                t.output_tokens += s.output_tokens
                t.models[s.model or "unknown"] = (
                    t.models.get(s.model or "unknown", 0) + s.input_tokens + s.output_tokens
                )
                c = prices.cost(s.model, s.input_tokens, s.output_tokens)
                if c is None:
                    t.unpriced_tokens += s.input_tokens + s.output_tokens
                    c = 0.0
                t.cost += c
                if s.retry:
                    t.retries += 1
                    t.retry_input_tokens += s.input_tokens
                    t.retry_output_tokens += s.output_tokens
                    t.retry_cost += c
            elif s.kind == "tool":
                t.tool_calls += 1
                if s.retry:
                    t.retries += 1
        tasks.append(t)
    return tasks


def baseline(
    spans: list[Span],
    prices: PriceTable,
    *,
    ceiling: float | None = None,
    volume_per_month: int | None = None,
    formats: dict[str, str] | None = None,
) -> dict[str, Any]:
    tasks = build_tasks(spans, prices)
    done = [t for t in tasks if t.completed]
    n = len(done)
    total_tokens = sum(t.input_tokens + t.output_tokens for t in done)
    unpriced = sum(t.unpriced_tokens for t in done)
    per = {
        "cost": round(sum(t.cost for t in done) / n, 6) if n else 0.0,
        "input_tokens": round(sum(t.input_tokens for t in done) / n, 1) if n else 0.0,
        "output_tokens": round(sum(t.output_tokens for t in done) / n, 1) if n else 0.0,
        "llm_calls": round(sum(t.llm_calls for t in done) / n, 2) if n else 0.0,
        "tool_calls": round(sum(t.tool_calls for t in done) / n, 2) if n else 0.0,
        "retries": round(sum(t.retries for t in done) / n, 2) if n else 0.0,
        "retry_cost": round(sum(t.retry_cost for t in done) / n, 6) if n else 0.0,
        "duration_s": round(sum(t.duration_s or 0 for t in done) / n, 3)
        if n and any(t.duration_s for t in done)
        else None,
    }
    models: dict[str, int] = {}
    for t in done:
        for m, tok in t.models.items():
            models[m] = models.get(m, 0) + tok
    unpriced_models = sorted(m for m in models if prices.find(m) is None)
    # breakdown: input vs output (price-weighted by model, completed tasks only) and the part spent on retried calls
    breakdown = []
    if n:
        done_ids = {t.trace_id for t in done}
        in_cost_total = 0.0
        out_cost_total = 0.0
        for s in spans:
            if s.kind != "llm" or s.trace_id not in done_ids:
                continue
            p = prices.find(s.model)
            if p is None:
                continue
            in_cost_total += s.input_tokens / 1e6 * p.input_per_1m
            out_cost_total += s.output_tokens / 1e6 * p.output_per_1m
        breakdown = [
            {
                "bucket": "Input tokens",
                "per_task": round(in_cost_total / n, 6),
                "tokens_per_task": per["input_tokens"],
            },
            {
                "bucket": "Output tokens",
                "per_task": round(out_cost_total / n, 6),
                "tokens_per_task": per["output_tokens"],
            },
            {
                "bucket": "of which on retried calls",
                "per_task": per["retry_cost"],
                "calls_per_task": per["retries"],
            },
        ]
    ratio = round(per["cost"] / ceiling, 3) if ceiling and ceiling > 0 else None
    projection = None
    if volume_per_month:
        projection = {
            "volume_per_month": volume_per_month,
            "monthly_cost": round(per["cost"] * volume_per_month, 2),
            "monthly_budget": round(ceiling * volume_per_month, 2) if ceiling else None,
            "monthly_tokens": int((per["input_tokens"] + per["output_tokens"]) * volume_per_month),
        }
    return {
        "kind": "rk.cost",
        "kit_version": __version__,
        "created": now_iso(),
        "prices": {
            "path": prices.path,
            "as_of": prices.as_of,
            "currency": prices.currency,
            "models_priced": len(prices.prices),
        },
        "formats": formats or {},
        "summary": {
            "traces": len(tasks),
            "tasks": len(tasks),
            "completed": n,
            "completion_rate": pct(n, len(tasks)),
            "has_usage": total_tokens > 0,
            "per_task": per,
            "ceiling": ceiling,
            "ratio": ratio,
            "projection": projection,
            "models": models,
            "unpriced_models": unpriced_models,
            "unpriced_tokens_share": pct(unpriced, total_tokens),
            "breakdown": breakdown,
            "spans": {
                "llm": sum(1 for s in spans if s.kind == "llm"),
                "tool": sum(1 for s in spans if s.kind == "tool"),
                "task": sum(1 for s in spans if s.kind == "task"),
                "other": sum(1 for s in spans if s.kind == "other"),
            },
            "spans_without_usage": sum(1 for s in spans if s.kind == "llm" and not s.has_usage),
        },
        "tasks": [
            {
                "trace_id": t.trace_id,
                "completed": t.completed,
                "cost": round(t.cost, 6),
                "input_tokens": t.input_tokens,
                "output_tokens": t.output_tokens,
                "llm_calls": t.llm_calls,
                "tool_calls": t.tool_calls,
                "retries": t.retries,
                "duration_s": t.duration_s,
            }
            for t in tasks
        ],
    }
