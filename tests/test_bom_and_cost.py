from __future__ import annotations

import json
from pathlib import Path

from readiness_kit.bom import discover, emit_cyclonedx, load_manifest, summarise
from readiness_kit.bom.manifest import version_from_command
from readiness_kit.cost import baseline, load_prices, load_traces
from readiness_kit.cost.traces import detect_format
from readiness_kit.schemas import validate_file
from readiness_kit.util import write_json, write_jsonl


def test_manifest_components_and_version_inheritance(example: Path) -> None:
    m = load_manifest(example / "agent.yaml")
    kinds = {c.kind for c in m.components}
    assert kinds == {"model", "prompt", "tool", "mcp_server", "skill", "data"}
    by = {(c.kind, c.name): c for c in m.components}
    assert by[("mcp_server", "crm-server")].version == "1.4.2"
    assert (
        by[("tool", "lookup_customer")].version == "1.4.2"
        and by[("tool", "lookup_customer")].properties["rk:version-from"] == "server"
    )
    assert by[("tool", "send_email")].version == "0.3.0"  # internal tools ship with the agent
    assert by[("mcp_server", "docs-server")].unversioned and by[("model", "demo-small")].unversioned
    assert (
        by[("skill", "refund-policy")].hash
        and by[("skill", "tone-of-voice")].properties["rk:unpinned-source"] == "true"
    )
    assert by[("data", "procedures-index")].properties["rk:managed"] == "false"
    assert (
        version_from_command("uvx crm-mcp@1.4.2") == "1.4.2" and version_from_command("npx docs-mcp") is None
    )
    assert version_from_command("docker run ghcr.io/x/y@sha256:" + "a" * 64).startswith("sha256:")


def test_discovery_and_dedupe(example: Path) -> None:
    found = discover(example)
    names = {(c.kind, c.name) for c in found}
    assert (
        ("mcp_server", "crm-server") in names
        and ("skill", "refund-policy") in names
        and ("prompt", "system") in names
    )
    m = load_manifest(example / "agent.yaml")
    n = len(m.components)
    m.merge(found)
    # everything discovered was already declared (by name or by content hash) → nothing added
    assert len(m.components) == n


def test_cyclonedx_shape_and_summary(example: Path, tmp_path: Path) -> None:
    m = load_manifest(example / "agent.yaml")
    bom = emit_cyclonedx(m)
    assert (
        bom["bomFormat"] == "CycloneDX"
        and bom["specVersion"] == "1.6"
        and bom["serialNumber"].startswith("urn:uuid:")
    )
    types = {c["type"] for c in bom["components"]}
    assert types == {"machine-learning-model", "file", "library", "data"}
    refs = {c["bom-ref"] for c in bom["components"]}
    assert all(d in refs for d in bom["dependencies"][0]["dependsOn"])
    tool_dep = next(d for d in bom["dependencies"] if d["ref"] == "rk:tool:lookup-customer")
    assert tool_dep["dependsOn"] == ["rk:mcp_server:crm-server"]
    p = write_json(tmp_path / "bom.cdx.json", bom)
    assert validate_file("bom", p) == []
    s = summarise(m, bom)["summary"]
    assert {u["name"] for u in s["unversioned"]} == {"demo-small", "docs-server", "tone-of-voice"}
    assert s["unpinned_sources"] == ["tone-of-voice"] and len(s["data_sources"]) == 3


def test_cost_from_example_traces(example: Path) -> None:
    spans, formats = load_traces([example / "traces.jsonl"])
    assert formats[str(example / "traces.jsonl")] == "otel"
    prices = load_prices(example / "prices.yaml")
    res = baseline(spans, prices, ceiling=0.01, volume_per_month=50000)
    s = res["summary"]
    assert s["tasks"] == 40 and s["completed"] == 38 and s["has_usage"]
    assert 0.005 < s["per_task"]["cost"] < 0.03 and s["ratio"] > 1
    assert s["per_task"]["retries"] > 0 and s["projection"]["monthly_budget"] == 500.0
    assert s["unpriced_models"] == [] and s["unpriced_tokens_share"] == 0
    assert [b["bucket"] for b in s["breakdown"]][:2] == ["Input tokens", "Output tokens"]


def test_langfuse_otlp_and_rk_formats(tmp_path: Path, example: Path) -> None:
    lf = write_jsonl(
        tmp_path / "lf.jsonl",
        [
            {
                "id": "g1",
                "traceId": "t1",
                "type": "GENERATION",
                "model": "demo-large",
                "usage": {"input": 1000, "output": 100},
                "startTime": "2026-10-01T09:00:00Z",
                "endTime": "2026-10-01T09:00:02Z",
            },
            {
                "id": "s1",
                "traceId": "t1",
                "type": "SPAN",
                "name": "tool lookup",
                "startTime": "2026-10-01T09:00:02Z",
                "endTime": "2026-10-01T09:00:03Z",
            },
            {
                "id": "g2",
                "traceId": "t2",
                "type": "GENERATION",
                "model": "mystery-9",
                "usage": {"input": 500, "output": 50},
                "level": "ERROR",
            },
        ],
    )
    assert detect_format(lf) == "langfuse"
    spans, _ = load_traces([lf])
    res = baseline(spans, load_prices(example / "prices.yaml"))
    assert res["summary"]["tasks"] == 2 and res["summary"]["completed"] == 1
    otlp = write_json(
        tmp_path / "otlp.json",
        {
            "resourceSpans": [
                {
                    "scopeSpans": [
                        {
                            "spans": [
                                {
                                    "traceId": "a",
                                    "spanId": "1",
                                    "name": "task",
                                    "startTimeUnixNano": "1700000000000000000",
                                    "endTimeUnixNano": "1700000003000000000",
                                    "status": {"code": 1},
                                },
                                {
                                    "traceId": "a",
                                    "spanId": "2",
                                    "parentSpanId": "1",
                                    "name": "chat",
                                    "attributes": [
                                        {"key": "gen_ai.operation.name", "value": {"stringValue": "chat"}},
                                        {
                                            "key": "gen_ai.request.model",
                                            "value": {"stringValue": "demo-small"},
                                        },
                                        {"key": "gen_ai.usage.input_tokens", "value": {"intValue": "200"}},
                                        {"key": "gen_ai.usage.output_tokens", "value": {"intValue": "20"}},
                                    ],
                                },
                            ]
                        }
                    ]
                }
            ]
        },
    )
    assert detect_format(otlp) == "otlp"
    spans, _ = load_traces([otlp])
    res = baseline(spans, load_prices(example / "prices.yaml"))
    assert res["summary"]["completed"] == 1 and res["summary"]["per_task"]["input_tokens"] == 200
    # the Kit's own eval run as a trace source
    from readiness_kit.harness.evalset import load_evalset
    from readiness_kit.harness.runner import run_eval
    from readiness_kit.harness.targets import build_target

    es = load_evalset(example / "evalset.jsonl")
    r = run_eval(build_target({"type": "python", "module": "agent", "cwd": str(example)}), es, limit=5)
    ev = write_json(tmp_path / "eval.json", r.to_dict())
    assert detect_format(ev) == "rk"
    spans, _ = load_traces([ev])
    res = baseline(spans, load_prices(example / "prices.yaml"))
    assert res["summary"]["tasks"] == 5 and res["summary"]["per_task"]["tool_calls"] >= 1


def test_unpriced_models_are_reported(tmp_path: Path) -> None:
    p = write_jsonl(
        tmp_path / "t.jsonl",
        [
            {
                "name": "chat",
                "context": {"trace_id": "x", "span_id": "1"},
                "parent_id": None,
                "attributes": {
                    "gen_ai.operation.name": "chat",
                    "gen_ai.request.model": "unknown-model",
                    "gen_ai.usage.input_tokens": 100,
                    "gen_ai.usage.output_tokens": 10,
                },
            }
        ],
    )
    spans, _ = load_traces([p])
    res = baseline(spans, load_prices(None))
    assert (
        res["summary"]["unpriced_models"] == ["unknown-model"]
        and res["summary"]["unpriced_tokens_share"] == 1.0
    )
    assert json.dumps(res)  # serialisable
