from __future__ import annotations

import pytest

from readiness_kit.harness.evalset import Case
from readiness_kit.harness.graders import extract_label, grade
from readiness_kit.harness.targets import Run, ToolCall
from readiness_kit.util import KitError


def run(output: str, calls: list[ToolCall] | None = None, observed_calls: bool = False) -> Run:
    r = Run(case_id="c", output=output, tool_calls=calls or [])
    if observed_calls or calls:
        r.observed.append("tool_calls")
    return r


def case(grader: str, expected, **options) -> Case:
    return Case(id="c", input="x", expected=expected, grader=grader, options=options)


def test_label_from_json_text_and_token() -> None:
    assert extract_label('{"category": "REFUND", "priority": "high"}', "category") == "REFUND"
    assert extract_label("category: refund\npriority: normal", "category") == "refund"
    assert extract_label("**Category**: Shipping Address", "category") == "Shipping Address"
    assert extract_label("The answer is REFUND.", "category") is None
    assert grade(case("label", {"category": "REFUND"}), run("REFUND")).passed is True
    assert (
        grade(case("label", {"category": "shipping_address"}), run("category: Shipping-Address")).passed
        is True
    )
    assert grade(case("label", {"category": "REFUND"}), run("category: ORDER")).passed is False
    g = grade(
        case("label", {"category": "REFUND", "priority": "high"}), run("category: REFUND\npriority: low")
    )
    assert g.passed is False and g.score == 0.5


def test_simple_text_graders() -> None:
    assert grade(case("exact", "Hello  world"), run("hello world")).passed is True
    assert grade(case("exact", "Hello world", strict=True), run("hello world")).passed is False
    assert grade(case("contains", ["order", "refund"]), run("Your ORDER refund is logged")).passed is True
    assert grade(case("contains", ["order", "refund"]), run("Your order is logged")).score == 0.5
    assert grade(case("any_of", ["a", "zzz"]), run("has zzz")).passed is True
    assert grade(case("not_contains", ["password"]), run("here is your PASSWORD")).passed is False
    assert grade(case("regex", r"order\s+\d{5}"), run("order 48213 found")).passed is True
    with pytest.raises(KitError):
        grade(case("regex", "("), run("x"))


def test_json_and_number_graders() -> None:
    assert grade(case("json_field", {"a.b": "x", "n": 3}), run('{"a": {"b": "X"}, "n": 3}')).passed is True
    assert grade(case("json_field", {"a.b": "x"}), run("not json")).passed is False
    assert grade(case("json_field", {"a": 1}), run('Result: {"a": 1} done')).passed is True
    assert grade(case("number", 48.0, tolerance=0.5), run("total EUR 48.20")).passed is True
    assert grade(case("number", 100, tolerance=0.05, relative=True), run("about 104")).passed is True
    assert grade(case("number", 100, tolerance=0.05, relative=True), run("about 110")).passed is False


def test_tool_graders_and_not_observable() -> None:
    calls = [ToolCall("send_email", {"to": "x@example.com"}), ToolCall("route_ticket", {"queue": "refund"})]
    assert grade(case("tool_called", "route_*"), run("ok", calls)).passed is True
    assert grade(case("tool_called", "send_email", **{"with": "nobody"}), run("ok", calls)).passed is False
    assert grade(case("tool_not_called", ["send_*"]), run("ok", calls)).passed is False
    g = grade(case("tool_not_called", ["send_*"]), run("ok"))
    assert g.passed is None and "does not report" in g.reason
    assert grade(case("tool_not_called", ["send_*"]), run("ok", [], observed_calls=True)).passed is True


def test_agent_error_fails_and_unknown_grader_raises() -> None:
    r = Run(case_id="c", output="", error="boom")
    assert grade(case("contains", "x"), r).passed is False
    with pytest.raises(KitError):
        grade(case("nope", "x"), run("x"))
