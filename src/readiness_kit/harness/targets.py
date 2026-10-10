"""Targets: the five ways the harness can talk to an agent under test.

Every target receives a :class:`Request` and returns a :class:`Run`. The agent contract is deliberately
small so that any agent can be wired in an afternoon (docs/FORMATS.md, "The agent contract"):

    request  = {"case_id": str, "input": str, "context": {...}, "metadata": {...}}
    response = {"output": str, "tool_calls": [{"name": str, "arguments": {...}, "result": str?}],
                "steps": int, "usage": {"input_tokens": int, "output_tokens": int, "model": str}}

Only ``output`` is required in the response. What the agent does not report, the Kit does not guess:
an oracle that needs tool calls from a target that reports none yields ``not_observable``, never ``pass``.

Target types (``target.type`` in rk.yaml):

* ``python``   — ``module:function`` called in-process; the function takes the request dict and returns
                 a response dict or a plain string.
* ``http``     — the request is POSTed as JSON; the response body is the contract above.
* ``openai-chat`` — an OpenAI-compatible chat-completions endpoint (OpenAI, Azure OpenAI, Ollama, vLLM,
                 LiteLLM, OpenRouter …); the Kit builds the messages and reads content, tool calls and usage.
* ``command``  — a shell command; the request JSON goes to stdin, stdout is the response (JSON or text).
* ``replay``   — responses read from a JSONL file by ``case_id`` (transcripts captured elsewhere, CI).
"""

from __future__ import annotations

import importlib
import json
import os
import shlex
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from readiness_kit import __version__
from readiness_kit.util import KitError, expand_env, read_jsonl


@dataclass
class Request:
    case_id: str
    input: str
    context: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "input": self.input,
            "context": self.context,
            "metadata": self.metadata,
        }


@dataclass
class ToolCall:
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)
    result: str | None = None
    error: str | None = None

    @classmethod
    def from_any(cls, item: Any) -> ToolCall:
        if isinstance(item, ToolCall):
            return item
        if isinstance(item, str):
            return cls(name=item)
        if not isinstance(item, dict):
            raise KitError(f"tool call must be an object or a name, got {type(item).__name__}")
        name = item.get("name") or item.get("tool") or (item.get("function") or {}).get("name")
        if not name:
            raise KitError(f"tool call without a name: {item!r}")
        args = item.get("arguments", item.get("args", item.get("input", {})))
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except json.JSONDecodeError:
                args = {"_raw": args}
        if not isinstance(args, dict):
            args = {"_value": args}
        res = item.get("result", item.get("output"))
        return cls(
            name=str(name),
            arguments=args,
            result=None if res is None else (res if isinstance(res, str) else json.dumps(res)),
            error=item.get("error"),
        )

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"name": self.name, "arguments": self.arguments}
        if self.result is not None:
            d["result"] = self.result
        if self.error:
            d["error"] = self.error
        return d


@dataclass
class Run:
    """What one call of the agent produced, plus which signals the target actually reported."""

    case_id: str
    output: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    steps: int | None = None
    usage: dict[str, Any] = field(default_factory=dict)
    latency_ms: float = 0.0
    error: str | None = None
    observed: list[str] = field(default_factory=lambda: ["output"])
    raw: Any = None

    @classmethod
    def from_response(cls, case_id: str, body: Any, latency_ms: float = 0.0) -> Run:
        """Build a Run from an agent response (contract dict, or a bare string)."""
        if isinstance(body, str):
            return cls(case_id=case_id, output=body, latency_ms=latency_ms, raw=body)
        if not isinstance(body, dict):
            raise KitError(f"agent response must be an object or a string, got {type(body).__name__}")
        output = body.get("output", body.get("content", body.get("response", "")))
        if output is None:
            output = ""
        if not isinstance(output, str):
            output = json.dumps(output, ensure_ascii=False)
        observed = ["output"]
        calls: list[ToolCall] = []
        if "tool_calls" in body and body["tool_calls"] is not None:
            observed.append("tool_calls")
            calls = [ToolCall.from_any(t) for t in body["tool_calls"]]
        steps = body.get("steps")
        if steps is not None:
            observed.append("steps")
            steps = int(steps)
        usage = body.get("usage") or {}
        if usage:
            observed.append("usage")
        return cls(
            case_id=case_id,
            output=output,
            tool_calls=calls,
            steps=steps,
            usage=dict(usage),
            latency_ms=latency_ms,
            error=body.get("error"),
            observed=observed,
            raw=body,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "output": self.output,
            "tool_calls": [t.to_dict() for t in self.tool_calls],
            "steps": self.steps,
            "usage": self.usage,
            "latency_ms": round(self.latency_ms, 1),
            "error": self.error,
            "observed": self.observed,
        }

    def observes(self, signal: str) -> bool:
        return signal in self.observed


class Target(Protocol):
    name: str

    def run(self, request: Request) -> Run: ...


def _timed(fn: Any, request: Request) -> Run:
    t0 = time.perf_counter()
    try:
        body = fn(request)
    except KitError:
        raise
    except Exception as e:  # the agent failed; that is a result, not a harness crash
        return Run(
            case_id=request.case_id,
            error=f"{type(e).__name__}: {e}",
            latency_ms=(time.perf_counter() - t0) * 1000,
        )
    run = Run.from_response(request.case_id, body, latency_ms=(time.perf_counter() - t0) * 1000)
    return run


class PythonTarget:
    """``module:function`` imported in-process. ``cwd`` is added to ``sys.path`` so an agent next to rk.yaml imports."""

    name = "python"

    def __init__(self, module: str, function: str = "handle", cwd: str | None = None) -> None:
        if cwd:
            p = str(Path(cwd).resolve())
            if p not in sys.path:
                sys.path.insert(0, p)
        try:
            mod = importlib.import_module(module)
        except ImportError as e:
            raise KitError(f"cannot import agent module '{module}': {e}") from e
        try:
            self.fn = getattr(mod, function)
        except AttributeError as e:
            raise KitError(f"module '{module}' has no function '{function}'") from e

    def run(self, request: Request) -> Run:
        return _timed(lambda r: self.fn(r.to_dict()), request)


class HttpTarget:
    """POST the request JSON to ``url``; the body must follow the agent contract."""

    name = "http"

    def __init__(
        self, url: str, headers: dict[str, str] | None = None, timeout: float = 120.0, method: str = "POST"
    ) -> None:
        import httpx

        self.url = url
        self.headers = {"content-type": "application/json", **(headers or {})}
        self.timeout = timeout
        self.method = method.upper()
        self.client = httpx.Client(timeout=timeout)

    def run(self, request: Request) -> Run:
        def call(r: Request) -> Any:
            resp = self.client.request(self.method, self.url, json=r.to_dict(), headers=self.headers)
            if resp.status_code >= 400:
                raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:300]}")
            try:
                return resp.json()
            except ValueError:
                return resp.text

        return _timed(call, request)


class OpenAIChatTarget:
    """An OpenAI-compatible ``/chat/completions`` endpoint.

    The Kit presents the case as the user message. Context the case carries (memory, a tool result, injected
    tool descriptions) is appended to the system prompt as labelled blocks, which is an approximation of a real
    agent loop; wire your own agent through ``http`` or ``python`` when exactness matters.
    """

    name = "openai-chat"

    def __init__(
        self,
        base_url: str,
        model: str,
        api_key: str | None = None,
        api_key_header: str = "Authorization",
        headers: dict[str, str] | None = None,
        system_prompt: str | None = None,
        system_prompt_file: str | None = None,
        temperature: float | None = 0.0,
        tools: list[dict[str, Any]] | None = None,
        extra: dict[str, Any] | None = None,
        timeout: float = 120.0,
    ) -> None:
        import httpx

        self.url = base_url.rstrip("/") + "/chat/completions"
        self.model = model
        self.headers = {"content-type": "application/json", **(headers or {})}
        if api_key:
            if api_key_header.lower() == "authorization":
                self.headers["Authorization"] = f"Bearer {api_key}"
            else:
                self.headers[api_key_header] = api_key
        self.system_prompt = system_prompt
        if system_prompt_file:
            self.system_prompt = Path(system_prompt_file).read_text(encoding="utf-8")
        self.temperature = temperature
        self.tools = tools
        self.extra = extra or {}
        self.client = httpx.Client(timeout=timeout)

    def messages(self, request: Request) -> list[dict[str, Any]]:
        system = self.system_prompt or request.context.get("system") or "You are a helpful assistant."
        blocks: list[str] = []
        ctx = request.context
        if ctx.get("tool_descriptions"):
            blocks.append(
                "Available tools:\n" + json.dumps(ctx["tool_descriptions"], ensure_ascii=False, indent=2)
            )
        if ctx.get("memory"):
            mem = ctx["memory"]
            blocks.append(
                "Notes from memory:\n"
                + (mem if isinstance(mem, str) else json.dumps(mem, ensure_ascii=False))
            )
        if ctx.get("tool_result"):
            tr = ctx["tool_result"]
            blocks.append(
                "Result of the last tool call:\n"
                + (tr if isinstance(tr, str) else json.dumps(tr, ensure_ascii=False))
            )
        if ctx.get("document"):
            blocks.append("Attached document:\n" + str(ctx["document"]))
        if blocks:
            system = system + "\n\n" + "\n\n".join(blocks)
        return [{"role": "system", "content": system}, {"role": "user", "content": request.input}]

    def run(self, request: Request) -> Run:
        def call(r: Request) -> Any:
            payload: dict[str, Any] = {"model": self.model, "messages": self.messages(r), **self.extra}
            if self.temperature is not None:
                payload["temperature"] = self.temperature
            if self.tools:
                payload["tools"] = self.tools
            resp = self.client.post(self.url, json=payload, headers=self.headers)
            if resp.status_code >= 400:
                raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:300]}")
            data = resp.json()
            choice = (data.get("choices") or [{}])[0]
            msg = choice.get("message") or {}
            calls = []
            for tc in msg.get("tool_calls") or []:
                fn = tc.get("function") or {}
                calls.append({"name": fn.get("name"), "arguments": fn.get("arguments", "{}")})
            usage = data.get("usage") or {}
            out: dict[str, Any] = {
                "output": msg.get("content") or "",
                "usage": {
                    "input_tokens": usage.get("prompt_tokens"),
                    "output_tokens": usage.get("completion_tokens"),
                    "model": data.get("model", self.model),
                },
            }
            if self.tools is not None:
                out["tool_calls"] = calls
            return out

        return _timed(call, request)


class CommandTarget:
    """Run a command per case: request JSON on stdin, the response (JSON or plain text) on stdout."""

    name = "command"

    def __init__(
        self,
        command: str | list[str],
        cwd: str | None = None,
        timeout: float = 300.0,
        env: dict[str, str] | None = None,
    ) -> None:
        self.argv = shlex.split(command) if isinstance(command, str) else list(command)
        self.cwd = cwd
        self.timeout = timeout
        self.env = {**os.environ, **(env or {})}

    def run(self, request: Request) -> Run:
        def call(r: Request) -> Any:
            proc = subprocess.run(
                self.argv,
                input=json.dumps(r.to_dict()),
                capture_output=True,
                text=True,
                cwd=self.cwd,
                env=self.env,
                timeout=self.timeout,
                check=False,
            )
            if proc.returncode != 0:
                raise RuntimeError(f"exit {proc.returncode}: {(proc.stderr or proc.stdout)[:300]}")
            out = proc.stdout.strip()
            try:
                return json.loads(out)
            except json.JSONDecodeError:
                return out

        return _timed(call, request)


class ReplayTarget:
    """Responses from a JSONL file keyed by ``case_id``; a case with no row is reported as an error."""

    name = "replay"

    def __init__(self, path: str) -> None:
        self.rows: dict[str, dict[str, Any]] = {}
        for row in read_jsonl(path):
            cid = row.get("case_id") or row.get("id")
            if not cid:
                raise KitError(f"{path}: replay rows need a case_id")
            self.rows[str(cid)] = row

    def run(self, request: Request) -> Run:
        row = self.rows.get(request.case_id)
        if row is None:
            return Run(case_id=request.case_id, error="no replay row for this case")
        body = {k: v for k, v in row.items() if k not in ("case_id", "id")}
        return Run.from_response(request.case_id, body)


def build_target(cfg: dict[str, Any], base_dir: str | Path | None = None) -> Target:
    """Build a target from the ``target:`` section of rk.yaml (``${ENV}`` references are expanded here)."""
    if not isinstance(cfg, dict) or "type" not in cfg:
        raise KitError("rk.yaml: target needs a 'type' (python | http | openai-chat | command | replay)")
    cfg = expand_env(dict(cfg))
    t = str(cfg.pop("type"))
    base = Path(base_dir) if base_dir else Path.cwd()

    def rel(p: str | None) -> str | None:
        if p is None:
            return None
        pp = Path(p)
        return str(pp if pp.is_absolute() else base / pp)

    try:
        if t == "python":
            return PythonTarget(
                module=cfg["module"], function=cfg.get("function", "handle"), cwd=rel(cfg.get("cwd", "."))
            )
        if t == "http":
            return HttpTarget(
                url=cfg["url"],
                headers=cfg.get("headers"),
                timeout=float(cfg.get("timeout", 120)),
                method=cfg.get("method", "POST"),
            )
        if t == "openai-chat":
            return OpenAIChatTarget(
                base_url=cfg["base_url"],
                model=cfg["model"],
                api_key=cfg.get("api_key"),
                api_key_header=cfg.get("api_key_header", "Authorization"),
                headers=cfg.get("headers"),
                system_prompt=cfg.get("system_prompt"),
                system_prompt_file=rel(cfg.get("system_prompt_file")),
                temperature=cfg.get("temperature", 0.0),
                tools=cfg.get("tools"),
                extra=cfg.get("extra"),
                timeout=float(cfg.get("timeout", 120)),
            )
        if t == "command":
            return CommandTarget(
                command=cfg["command"],
                cwd=rel(cfg.get("cwd", ".")),
                timeout=float(cfg.get("timeout", 300)),
                env=cfg.get("env"),
            )
        if t == "replay":
            return ReplayTarget(path=rel(cfg["path"]) or "")
    except KeyError as e:
        raise KitError(f"rk.yaml: target type '{t}' needs '{e.args[0]}'") from e
    raise KitError(f"rk.yaml: unknown target type '{t}'")


def default_metadata(max_steps: int | None = None) -> dict[str, Any]:
    md: dict[str, Any] = {"kit_version": __version__}
    if max_steps is not None:
        md["max_steps"] = max_steps
    return md
