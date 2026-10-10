from __future__ import annotations

import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from readiness_kit.harness.targets import Request, Run, build_target
from readiness_kit.util import KitError, write_jsonl


def test_run_from_response_shapes() -> None:
    r = Run.from_response("c", "plain text")
    assert r.output == "plain text" and r.observed == ["output"] and not r.observes("tool_calls")
    r = Run.from_response(
        "c",
        {
            "output": "x",
            "tool_calls": [{"name": "a", "arguments": '{"k": 1}'}, "b"],
            "steps": 3,
            "usage": {"input_tokens": 5},
        },
    )
    assert [t.name for t in r.tool_calls] == ["a", "b"] and r.tool_calls[0].arguments == {"k": 1}
    assert r.steps == 3 and set(r.observed) == {"output", "tool_calls", "steps", "usage"}
    r = Run.from_response("c", {"content": {"a": 1}})
    assert r.output == '{"a": 1}'
    with pytest.raises(KitError):
        Run.from_response("c", 42)


def test_python_target_runs_example(example: Path) -> None:
    t = build_target({"type": "python", "module": "agent", "function": "handle", "cwd": str(example)})
    run = t.run(Request(case_id="x", input="Please unsubscribe me from the newsletter."))
    assert "category: NEWSLETTER" in run.output and run.observes("tool_calls") and run.steps >= 1
    assert run.usage["model"] == "demo-rules-v1"


def test_python_target_errors_are_results(tmp_path: Path) -> None:
    (tmp_path / "bad.py").write_text("def handle(req):\n    raise ValueError('nope')\n")
    t = build_target({"type": "python", "module": "bad", "cwd": str(tmp_path)})
    run = t.run(Request(case_id="x", input="hi"))
    assert run.error and "ValueError" in run.error
    with pytest.raises(KitError):
        build_target({"type": "python", "module": "does_not_exist_zz", "cwd": str(tmp_path)})


def test_command_target(example: Path) -> None:
    t = build_target({"type": "command", "command": f"{sys.executable} agent.py", "cwd": str(example)})
    run = t.run(Request(case_id="x", input="Where is my invoice for order 48213?"))
    assert "category: INVOICE" in run.output and run.observes("tool_calls")


def test_replay_target(tmp_path: Path) -> None:
    p = write_jsonl(
        tmp_path / "replay.jsonl", [{"case_id": "a", "output": "category: REFUND", "tool_calls": []}]
    )
    t = build_target({"type": "replay", "path": str(p)})
    assert t.run(Request(case_id="a", input="")).output == "category: REFUND"
    assert t.run(Request(case_id="missing", input="")).error


class _Handler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        if self.path.endswith("/chat/completions"):
            user = body["messages"][-1]["content"]
            out = {
                "choices": [
                    {
                        "message": {
                            "content": f"category: {'REFUND' if 'refund' in user else 'ORDER'}",
                            "tool_calls": [
                                {"function": {"name": "route_ticket", "arguments": '{"queue": "x"}'}}
                            ],
                        }
                    }
                ],
                "usage": {"prompt_tokens": 12, "completion_tokens": 3},
                "model": "fake-1",
            }
        else:
            out = {"output": f"echo {body['input']}", "tool_calls": [], "steps": 1}
        data = json.dumps(out).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *a) -> None:  # silence
        pass


@pytest.fixture
def server():
    srv = HTTPServer(("127.0.0.1", 0), _Handler)
    th = threading.Thread(target=srv.serve_forever, daemon=True)
    th.start()
    yield f"http://127.0.0.1:{srv.server_port}"
    srv.shutdown()


def test_http_and_openai_targets(server: str, monkeypatch) -> None:
    monkeypatch.setenv("FAKE_KEY", "secret")
    t = build_target({"type": "http", "url": f"{server}/agent", "headers": {"x-key": "${FAKE_KEY}"}})
    run = t.run(Request(case_id="x", input="hello"))
    assert run.output == "echo hello" and run.observes("tool_calls") and run.steps == 1
    o = build_target(
        {
            "type": "openai-chat",
            "base_url": f"{server}/v1",
            "model": "fake",
            "api_key": "${FAKE_KEY}",
            "tools": [],
        }
    )
    run = o.run(Request(case_id="x", input="I want a refund", context={"memory": "note"}))
    assert (
        "REFUND" in run.output
        and run.tool_calls[0].name == "route_ticket"
        and run.usage["input_tokens"] == 12
    )
    with pytest.raises(KitError):
        build_target({"type": "http", "url": "http://x", "headers": {"k": "${NOT_SET_ANYWHERE}"}})
