"""Graders: deterministic checks of an agent's run against a case's ``expected`` value.

Every grader returns a :class:`Grade`; ``passed`` is ``True``, ``False`` or ``None`` (not observable: the check
needs a signal the target did not report). No grader calls a model; a model-judged rubric is deliberately outside
v0.1 so that a published pass rate depends on nothing but the set, the split and the agent.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from readiness_kit.harness.evalset import Case
from readiness_kit.harness.targets import Run
from readiness_kit.util import KitError, glob_match


@dataclass
class Grade:
    passed: bool | None
    score: float
    reason: str
    grader: str


def _norm(s: Any, case_sensitive: bool = False) -> str:
    s = "" if s is None else str(s)
    s = " ".join(s.split())
    return s if case_sensitive else s.lower()


def _as_list(v: Any) -> list[str]:
    if v is None:
        return []
    if isinstance(v, (list, tuple)):
        return [str(x) for x in v]
    return [str(v)]


def _label_norm(s: Any) -> str:
    return re.sub(r"[\s\-]+", "_", str(s).strip().lower())


def _try_json(text: str) -> Any:
    text = text.strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # a JSON object embedded in prose, e.g. after "Result:"; take the first balanced {...}
    start = text.find("{")
    if start >= 0:
        depth = 0
        for i in range(start, len(text)):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start : i + 1])
                    except json.JSONDecodeError:
                        break
    return None


def _get_path(obj: Any, path: str) -> tuple[bool, Any]:
    cur = obj
    for part in path.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        elif isinstance(cur, list) and part.isdigit() and int(part) < len(cur):
            cur = cur[int(part)]
        else:
            return False, None
    return True, cur


def extract_label(output: str, field: str) -> str | None:
    """Find the value of ``field`` in the output: JSON first, then ``field: value`` in text, then nothing."""
    data = _try_json(output)
    if isinstance(data, dict):
        for k, v in data.items():
            if _label_norm(k) == _label_norm(field) and v is not None:
                return str(v)
    m = re.search(
        rf"(?im)^\s*\**{re.escape(field)}\**\s*[:=]\s*[\"'\*]*([A-Za-z0-9_\- ]+?)[\"'\*]*\s*$", output
    )
    if m:
        return m.group(1)
    m = re.search(rf"(?i)\b{re.escape(field)}\b\s*[:=]\s*[\"'\*]*([A-Za-z0-9_\-]+)", output)
    if m:
        return m.group(1)
    return None


# --- graders -------------------------------------------------------------------------------------------------


def grade_exact(case: Case, run: Run) -> Grade:
    strict = bool(case.options.get("strict", False))
    exp = _norm(case.expected, strict) if strict else _norm(case.expected)
    got = run.output if strict else _norm(run.output)
    ok = got == exp
    return Grade(
        ok,
        1.0 if ok else 0.0,
        "exact match" if ok else f"expected {case.expected!r}, got {run.output[:80]!r}",
        "exact",
    )


def grade_contains(case: Case, run: Run) -> Grade:
    cs = bool(case.options.get("case_sensitive", False))
    hay = _norm(run.output, cs)
    needles = _as_list(case.expected)
    missing = [n for n in needles if _norm(n, cs) not in hay]
    ok = not missing
    return Grade(
        ok,
        1.0 if ok else 1 - len(missing) / max(len(needles), 1),
        "all expected strings present" if ok else f"missing: {missing}",
        "contains",
    )


def grade_any_of(case: Case, run: Run) -> Grade:
    cs = bool(case.options.get("case_sensitive", False))
    hay = _norm(run.output, cs)
    options = _as_list(case.expected)
    hit = [o for o in options if _norm(o, cs) in hay]
    ok = bool(hit)
    return Grade(
        ok, 1.0 if ok else 0.0, f"found {hit[0]!r}" if ok else f"none of {options} present", "any_of"
    )


def grade_not_contains(case: Case, run: Run) -> Grade:
    cs = bool(case.options.get("case_sensitive", False))
    hay = _norm(run.output, cs)
    found = [n for n in _as_list(case.expected) if _norm(n, cs) in hay]
    ok = not found
    return Grade(
        ok,
        1.0 if ok else 0.0,
        "no forbidden string present" if ok else f"found forbidden: {found}",
        "not_contains",
    )


def grade_regex(case: Case, run: Run) -> Grade:
    flags = 0 if case.options.get("case_sensitive", False) else re.IGNORECASE
    patterns = _as_list(case.expected)
    try:
        misses = [p for p in patterns if not re.search(p, run.output, flags | re.MULTILINE)]
    except re.error as e:
        raise KitError(f"case {case.id}: invalid regex ({e})") from e
    ok = not misses
    return Grade(ok, 1.0 if ok else 0.0, "pattern matched" if ok else f"no match for: {misses}", "regex")


def grade_label(case: Case, run: Run) -> Grade:
    if isinstance(case.expected, dict):
        fields = case.options.get("fields") or list(case.expected.keys())
        expected = {f: case.expected[f] for f in fields if f in case.expected}
    else:
        field = case.options.get("field", "label")
        expected = {field: case.expected}
    if not expected:
        raise KitError(
            f'case {case.id}: label grader needs an expected object such as {{"category": "REFUND"}}'
        )
    wrong: list[str] = []
    for f, want in expected.items():
        got = extract_label(run.output, f)
        if got is None:
            # last resort: the label itself appears as a whole token in a short output
            short = len(run.output) <= 200
            if short and re.search(rf"\b{re.escape(_label_norm(want))}\b", _label_norm(run.output)):
                continue
            wrong.append(f"{f}: not found (expected {want})")
        elif _label_norm(got) != _label_norm(want):
            wrong.append(f"{f}: expected {want}, got {got}")
    ok = not wrong
    return Grade(ok, 1 - len(wrong) / len(expected), "labels match" if ok else "; ".join(wrong), "label")


def grade_json_field(case: Case, run: Run) -> Grade:
    data = _try_json(run.output)
    if data is None:
        return Grade(False, 0.0, "output is not JSON", "json_field")
    if not isinstance(case.expected, dict):
        raise KitError(f"case {case.id}: json_field grader needs an expected object of path: value")
    wrong = []
    for path, want in case.expected.items():
        found, got = _get_path(data, path)
        if not found:
            wrong.append(f"{path}: missing")
        elif isinstance(want, str) and isinstance(got, str):
            if _norm(want) != _norm(got):
                wrong.append(f"{path}: expected {want!r}, got {got!r}")
        elif got != want:
            wrong.append(f"{path}: expected {want!r}, got {got!r}")
    ok = not wrong
    return Grade(
        ok,
        1 - len(wrong) / max(len(case.expected), 1),
        "fields match" if ok else "; ".join(wrong),
        "json_field",
    )


_NUM_RE = re.compile(r"-?\d+(?:[.,]\d+)?")


def grade_number(case: Case, run: Run) -> Grade:
    try:
        want = float(case.expected)
    except (TypeError, ValueError) as e:
        raise KitError(f"case {case.id}: number grader needs a numeric expected value") from e
    tol = float(case.options.get("tolerance", 0))
    relative = bool(case.options.get("relative", False))
    nums = [float(m.group(0).replace(",", ".")) for m in _NUM_RE.finditer(run.output)]
    if not nums:
        return Grade(False, 0.0, "no number in the output", "number")
    allowed = abs(want) * tol if relative else tol
    ok = any(abs(n - want) <= allowed for n in nums)
    return Grade(
        ok,
        1.0 if ok else 0.0,
        "within tolerance" if ok else f"expected {want} ± {allowed}, numbers seen {nums[:5]}",
        "number",
    )


def _calls_matching(run: Run, patterns: list[str], with_text: str | None) -> list[str]:
    hits = []
    for tc in run.tool_calls:
        name_ok = any(glob_match(tc.name, p) for p in patterns)
        args_ok = (
            with_text is None or with_text.lower() in json.dumps(tc.arguments, ensure_ascii=False).lower()
        )
        if name_ok and args_ok:
            hits.append(tc.name)
    return hits


def grade_tool_called(case: Case, run: Run) -> Grade:
    if not run.observes("tool_calls"):
        return Grade(None, 0.0, "target does not report tool calls", "tool_called")
    patterns = _as_list(case.expected)
    with_text = case.options.get("with")
    missing = [p for p in patterns if not _calls_matching(run, [p], with_text)]
    ok = not missing
    return Grade(
        ok,
        1 - len(missing) / max(len(patterns), 1),
        "expected tools called" if ok else f"not called: {missing}",
        "tool_called",
    )


def grade_tool_not_called(case: Case, run: Run) -> Grade:
    if not run.observes("tool_calls"):
        return Grade(None, 0.0, "target does not report tool calls", "tool_not_called")
    hits = _calls_matching(run, _as_list(case.expected), case.options.get("with"))
    ok = not hits
    return Grade(
        ok, 1.0 if ok else 0.0, "forbidden tools not called" if ok else f"called: {hits}", "tool_not_called"
    )


GRADERS: dict[str, Callable[[Case, Run], Grade]] = {
    "exact": grade_exact,
    "contains": grade_contains,
    "any_of": grade_any_of,
    "not_contains": grade_not_contains,
    "regex": grade_regex,
    "label": grade_label,
    "json_field": grade_json_field,
    "number": grade_number,
    "tool_called": grade_tool_called,
    "tool_not_called": grade_tool_not_called,
}


def grade(case: Case, run: Run) -> Grade:
    if run.error:
        return Grade(False, 0.0, f"agent error: {run.error}", case.grader)
    fn = GRADERS.get(case.grader)
    if fn is None:
        raise KitError(f"case {case.id}: unknown grader '{case.grader}' (known: {', '.join(GRADERS)})")
    return fn(case, run)
