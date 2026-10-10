"""Trace parsers. Every format is reduced to a flat list of :class:`Span`; the baseline works on that.

Formats (``--format auto`` picks by content):

* ``otel``     — one span per line (JSONL), as the OpenTelemetry SDK console/file exporters write it:
                 ``{"name", "context": {"trace_id", "span_id"}, "parent_id", "start_time", "end_time",
                 "status": {"status_code"}, "attributes": {...}}``; flat ``trace_id``/``span_id`` keys also work.
* ``otlp``     — the OTLP JSON envelope: ``resourceSpans[].scopeSpans[].spans[]`` with key/value attributes.
* ``langfuse`` — observations exported from Langfuse (JSONL): ``type`` GENERATION / SPAN / EVENT, ``traceId``,
                 ``model``, ``usage`` or ``usageDetails``, ``level``.
* ``rk``       — the Kit's own ``eval.json``: one task per case, usage from the agent's response.

Token counts come from the GenAI semantic conventions (``gen_ai.usage.input_tokens`` / ``output_tokens``) and the
older names (``llm.usage.prompt_tokens`` …); a span with no usage counts as zero tokens and the share of such
spans is reported, never hidden.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from readiness_kit.util import KitError, read_json, read_jsonl

LLM_OPS = {"chat", "text_completion", "generate_content", "completion", "embeddings", "invoke_agent"}


@dataclass
class Span:
    trace_id: str
    span_id: str
    parent_id: str | None
    name: str
    kind: str  # llm | tool | task | other
    model: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    start: float | None = None
    end: float | None = None
    status: str = "unset"  # ok | error | unset
    retry: bool = False
    attrs: dict[str, Any] = field(default_factory=dict)

    @property
    def has_usage(self) -> bool:
        return (self.input_tokens or self.output_tokens) > 0


def _int(v: Any) -> int:
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return 0


def _first(attrs: dict[str, Any], *keys: str) -> Any:
    for k in keys:
        if k in attrs and attrs[k] is not None:
            return attrs[k]
    return None


def _kind_from(name: str, attrs: dict[str, Any], parent_id: str | None) -> str:
    op = str(
        _first(attrs, "gen_ai.operation.name", "llm.request.type", "openinference.span.kind") or ""
    ).lower()
    if op in LLM_OPS or op == "llm":
        return "llm"
    if _first(attrs, "gen_ai.tool.name", "tool.name") or op in ("execute_tool", "tool"):
        return "tool"
    if _first(
        attrs,
        "gen_ai.usage.input_tokens",
        "gen_ai.usage.output_tokens",
        "llm.usage.prompt_tokens",
        "llm.token_count.prompt",
    ):
        return "llm"
    n = name.lower()
    if n.startswith(("tool", "execute_tool", "call_tool")) or ".tool" in n:
        return "tool"
    if parent_id is None:
        return "task"
    return "other"


def _is_retry(attrs: dict[str, Any]) -> bool:
    for k in ("rk.retry", "retry", "is_retry", "gen_ai.request.is_retry"):
        if str(attrs.get(k, "")).lower() in ("true", "1", "yes"):
            return True
    for k in ("retry.count", "retry_attempt", "http.request.resend_count"):
        if _int(attrs.get(k)) > 0:
            return True
    return _int(attrs.get("attempt")) > 1  # attempt 1 is the first try


def _status(raw: Any) -> str:
    code = raw.get("status_code", raw.get("code")) if isinstance(raw, dict) else raw
    s = str(code or "").upper()
    if s in ("ERROR", "2", "STATUS_CODE_ERROR"):
        return "error"
    if s in ("OK", "1", "STATUS_CODE_OK"):
        return "ok"
    return "unset"


def _time(v: Any) -> float | None:
    """Seconds since the epoch from ISO strings, unix seconds/millis/nanos."""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        x = float(v)
        if x > 1e17:
            return x / 1e9
        if x > 1e14:
            return x / 1e6
        if x > 1e11:
            return x / 1e3
        return x
    s = str(v)
    if s.isdigit():
        return _time(int(s))
    from datetime import datetime

    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


# --- otel JSONL -------------------------------------------------------------------------------------------------


def _otel_row(row: dict[str, Any]) -> Span | None:
    ctx = row.get("context") or {}
    trace_id = row.get("trace_id") or row.get("traceId") or ctx.get("trace_id") or ctx.get("traceId")
    span_id = row.get("span_id") or row.get("spanId") or ctx.get("span_id") or ctx.get("spanId")
    if not trace_id or not span_id:
        return None
    parent = (
        row.get("parent_id") or row.get("parentId") or row.get("parent_span_id") or row.get("parentSpanId")
    )
    if isinstance(parent, dict):
        parent = parent.get("span_id")
    attrs = dict(row.get("attributes") or {})
    name = str(row.get("name") or "")
    kind = _kind_from(name, attrs, parent)
    return Span(
        trace_id=str(trace_id),
        span_id=str(span_id),
        parent_id=str(parent) if parent else None,
        name=name,
        kind=kind,
        model=_first(attrs, "gen_ai.response.model", "gen_ai.request.model", "llm.model_name", "llm.model"),
        input_tokens=_int(
            _first(
                attrs,
                "gen_ai.usage.input_tokens",
                "gen_ai.usage.prompt_tokens",
                "llm.usage.prompt_tokens",
                "llm.token_count.prompt",
            )
        ),
        output_tokens=_int(
            _first(
                attrs,
                "gen_ai.usage.output_tokens",
                "gen_ai.usage.completion_tokens",
                "llm.usage.completion_tokens",
                "llm.token_count.completion",
            )
        ),
        start=_time(row.get("start_time") or row.get("startTime") or row.get("start_time_unix_nano")),
        end=_time(row.get("end_time") or row.get("endTime") or row.get("end_time_unix_nano")),
        status=_status(row.get("status")),
        retry=_is_retry(attrs),
        attrs=attrs,
    )


def parse_otel_jsonl(path: Path) -> list[Span]:
    spans = []
    for row in read_jsonl(path):
        s = _otel_row(row)
        if s:
            spans.append(s)
    return spans


# --- OTLP JSON --------------------------------------------------------------------------------------------------


def _otlp_value(v: Any) -> Any:
    if not isinstance(v, dict):
        return v
    for k in ("stringValue", "intValue", "doubleValue", "boolValue"):
        if k in v:
            return v[k]
    if "arrayValue" in v:
        return [_otlp_value(x) for x in (v["arrayValue"].get("values") or [])]
    return v


def parse_otlp_json(path: Path) -> list[Span]:
    data = read_json(path)
    spans: list[Span] = []
    for rs in data.get("resourceSpans") or []:
        for ss in rs.get("scopeSpans") or rs.get("instrumentationLibrarySpans") or []:
            for sp in ss.get("spans") or []:
                attrs = {
                    a["key"]: _otlp_value(a.get("value")) for a in (sp.get("attributes") or []) if "key" in a
                }
                parent = sp.get("parentSpanId") or None
                name = str(sp.get("name") or "")
                spans.append(
                    Span(
                        trace_id=str(sp.get("traceId")),
                        span_id=str(sp.get("spanId")),
                        parent_id=str(parent) if parent else None,
                        name=name,
                        kind=_kind_from(name, attrs, parent),
                        model=_first(attrs, "gen_ai.response.model", "gen_ai.request.model"),
                        input_tokens=_int(
                            _first(attrs, "gen_ai.usage.input_tokens", "gen_ai.usage.prompt_tokens")
                        ),
                        output_tokens=_int(
                            _first(attrs, "gen_ai.usage.output_tokens", "gen_ai.usage.completion_tokens")
                        ),
                        start=_time(sp.get("startTimeUnixNano")),
                        end=_time(sp.get("endTimeUnixNano")),
                        status=_status(sp.get("status")),
                        retry=_is_retry(attrs),
                        attrs=attrs,
                    )
                )
    return spans


# --- Langfuse ---------------------------------------------------------------------------------------------------


def parse_langfuse_jsonl(path: Path) -> list[Span]:
    spans: list[Span] = []
    for row in read_jsonl(path):
        typ = str(row.get("type") or "").upper()
        trace_id = row.get("traceId") or row.get("trace_id")
        if not trace_id or not typ:
            continue
        usage = row.get("usageDetails") or row.get("usage") or {}
        kind = (
            "llm"
            if typ == "GENERATION"
            else "tool"
            if "tool" in str(row.get("name", "")).lower()
            else "other"
        )
        parent = row.get("parentObservationId") or row.get("parent_observation_id")
        attrs = dict(row.get("metadata") or {})
        spans.append(
            Span(
                trace_id=str(trace_id),
                span_id=str(row.get("id") or row.get("observationId") or ""),
                parent_id=str(parent) if parent else None,
                name=str(row.get("name") or typ.lower()),
                kind=kind,
                model=row.get("model"),
                input_tokens=_int(usage.get("input", usage.get("promptTokens", usage.get("prompt_tokens")))),
                output_tokens=_int(
                    usage.get("output", usage.get("completionTokens", usage.get("completion_tokens")))
                ),
                start=_time(row.get("startTime")),
                end=_time(row.get("endTime")),
                status="error" if str(row.get("level", "")).upper() == "ERROR" else "ok",
                retry=_is_retry(attrs),
                attrs=attrs,
            )
        )
    # Langfuse has no root span: synthesise one task span per trace so completion can be judged
    traces = {s.trace_id for s in spans}
    for t in traces:
        if not any(s.trace_id == t and s.parent_id is None and s.kind == "task" for s in spans):
            errs = any(s.status == "error" for s in spans if s.trace_id == t)
            spans.append(
                Span(
                    trace_id=t,
                    span_id=f"task:{t}",
                    parent_id=None,
                    name="task",
                    kind="task",
                    status="error" if errs else "ok",
                )
            )
    return spans


# --- the Kit's own eval.json ---------------------------------------------------------------------------------------


def parse_rk_eval(path: Path) -> list[Span]:
    data = read_json(path)
    if not isinstance(data, dict) or data.get("kind") != "rk.eval":
        raise KitError(f"{path}: not an rk.eval artefact")
    spans: list[Span] = []
    for r in data.get("results", []):
        run = r.get("run") or {}
        cid = str(r["case_id"])
        status = "error" if run.get("error") else "ok"
        spans.append(
            Span(
                trace_id=cid,
                span_id=f"{cid}:task",
                parent_id=None,
                name="task",
                kind="task",
                status=status,
                attrs={"rk.passed": r.get("passed")},
            )
        )
        usage = run.get("usage") or {}
        spans.append(
            Span(
                trace_id=cid,
                span_id=f"{cid}:llm",
                parent_id=f"{cid}:task",
                name="llm",
                kind="llm",
                model=usage.get("model"),
                input_tokens=_int(usage.get("input_tokens")),
                output_tokens=_int(usage.get("output_tokens")),
                status=status,
            )
        )
        last: tuple[str, str] | None = None
        for i, tc in enumerate(run.get("tool_calls") or []):
            key = (str(tc.get("name")), json.dumps(tc.get("arguments"), sort_keys=True))
            spans.append(
                Span(
                    trace_id=cid,
                    span_id=f"{cid}:tool:{i}",
                    parent_id=f"{cid}:task",
                    name=f"tool {key[0]}",
                    kind="tool",
                    retry=key == last,
                    attrs={"gen_ai.tool.name": key[0]},
                )
            )
            last = key
    return spans


# --- entry point -------------------------------------------------------------------------------------------------


def detect_format(path: Path) -> str:
    text = path.read_text(encoding="utf-8", errors="replace")
    head = text.lstrip()[:4000]
    if head.startswith("{") and '"resourceSpans"' in head:
        return "otlp"
    if head.startswith("{") and '"kind": "rk.eval"' in head.replace("\n", "")[:200]:
        return "rk"
    first = head.splitlines()[0] if head else ""
    try:
        row = json.loads(first)
    except json.JSONDecodeError:
        try:
            row = json.loads(head)
        except json.JSONDecodeError:
            raise KitError(f"{path}: not JSON or JSONL") from None
        if isinstance(row, dict) and row.get("kind") == "rk.eval":
            return "rk"
        raise KitError(f"{path}: cannot tell the trace format; pass --format") from None
    if isinstance(row, dict):
        if row.get("kind") == "rk.eval":
            return "rk"
        if (
            "traceId" in row
            and ("type" in row or "usage" in row or "usageDetails" in row)
            and "attributes" not in row
        ):
            return "langfuse"
        if "name" in row and ("context" in row or "trace_id" in row or "traceId" in row):
            return "otel"
    raise KitError(f"{path}: cannot tell the trace format; pass --format otel|otlp|langfuse|rk")


def load_traces(paths: list[str | Path], fmt: str = "auto") -> tuple[list[Span], dict[str, str]]:
    spans: list[Span] = []
    formats: dict[str, str] = {}
    for p in paths:
        path = Path(p)
        if not path.exists():
            raise KitError(f"trace file not found: {path}")
        f = detect_format(path) if fmt == "auto" else fmt
        formats[str(path)] = f
        if f == "otel":
            spans += parse_otel_jsonl(path)
        elif f == "otlp":
            spans += parse_otlp_json(path)
        elif f == "langfuse":
            spans += parse_langfuse_jsonl(path)
        elif f == "rk":
            spans += parse_rk_eval(path)
        else:
            raise KitError(f"unknown trace format '{f}'")
    if not spans:
        raise KitError("no spans found in the trace files")
    return spans, formats
