"""The evaluation runner: every case through the target, graded, summarised by side of the split and by category."""

from __future__ import annotations

import statistics
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any

from readiness_kit import __version__
from readiness_kit.harness.evalset import Case, EvalSet
from readiness_kit.harness.graders import Grade, grade
from readiness_kit.harness.split import Split
from readiness_kit.harness.targets import Request, Run, Target, default_metadata
from readiness_kit.util import now_iso, pct


@dataclass
class CaseResult:
    case: Case
    run: Run
    grade: Grade
    side: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case.id,
            "side": self.side,
            "category": self.case.category,
            "tags": self.case.tags,
            "passed": self.grade.passed,
            "score": round(self.grade.score, 4),
            "grader": self.grade.grader,
            "reason": self.grade.reason,
            "expected": self.case.expected,
            "run": self.run.to_dict(),
        }


@dataclass
class EvalResult:
    results: list[CaseResult]
    evalset: EvalSet
    split: Split | None
    target_name: str
    target_label: str = ""
    created: str = field(default_factory=now_iso)

    # --- summaries ------------------------------------------------------------------------------------------

    @staticmethod
    def _summ(items: list[CaseResult]) -> dict[str, Any]:
        graded = [r for r in items if r.grade.passed is not None]
        passed = [r for r in graded if r.grade.passed]
        return {
            "cases": len(items),
            "graded": len(graded),
            "passed": len(passed),
            "failed": len(graded) - len(passed),
            "not_observable": len(items) - len(graded),
            "errors": sum(1 for r in items if r.run.error),
            "pass_rate": pct(len(passed), len(graded)),
        }

    def side(self, name: str) -> list[CaseResult]:
        return [r for r in self.results if r.side == name]

    def summary(self) -> dict[str, Any]:
        holdout, dev = self.side("holdout"), self.side("dev")
        headline_side = "holdout" if holdout else "all"
        headline = self._summ(holdout) if holdout else self._summ(self.results)
        by_cat: list[dict[str, Any]] = []
        for cat in sorted({r.case.category for r in self.results}):
            rows = [r for r in self.results if r.case.category == cat]
            h = [r for r in rows if r.side == "holdout"]
            use = h if h else rows
            s = self._summ(use)
            failing = [r for r in use if r.grade.passed is False]
            s.update(
                {
                    "category": cat,
                    "side": "holdout" if h else "all",
                    "failing": [r.case.id for r in failing][:10],
                }
            )
            by_cat.append(s)
        usage_in = [
            int(r.run.usage.get("input_tokens") or 0)
            for r in self.results
            if r.run.usage.get("input_tokens") is not None
        ]
        usage_out = [
            int(r.run.usage.get("output_tokens") or 0)
            for r in self.results
            if r.run.usage.get("output_tokens") is not None
        ]
        lat = sorted(r.run.latency_ms for r in self.results if r.run.latency_ms)
        return {
            "headline": {"side": headline_side, **headline},
            "holdout": self._summ(holdout) if holdout else None,
            "dev": self._summ(dev) if dev else None,
            "all": self._summ(self.results),
            "by_category": by_cat,
            "usage": {
                "runs_with_usage": len(usage_in),
                "input_tokens": sum(usage_in),
                "output_tokens": sum(usage_out),
            },
            "latency_ms": {
                "p50": round(statistics.median(lat), 1) if lat else None,
                "p95": round(lat[min(len(lat) - 1, int(len(lat) * 0.95))], 1) if lat else None,
            },
            "observed": sorted({s for r in self.results for s in r.run.observed}),
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": "rk.eval",
            "kit_version": __version__,
            "created": self.created,
            "target": {"type": self.target_name, "label": self.target_label},
            "evalset": {"path": self.evalset.path, "sha256": self.evalset.sha256, "cases": len(self.evalset)},
            "split": (
                {
                    "salt": self.split.salt,
                    "holdout_fraction": self.split.holdout_fraction,
                    "evalset_sha256": self.split.evalset_sha256,
                    "counts": {"holdout": len(self.split.holdout), "dev": len(self.split.dev)},
                }
                if self.split
                else None
            ),
            "summary": self.summary(),
            "results": [r.to_dict() for r in self.results],
        }


def run_eval(
    target: Target,
    evalset: EvalSet,
    split: Split | None = None,
    *,
    concurrency: int = 1,
    limit: int | None = None,
    side: str | None = None,
    max_steps: int | None = None,
    label: str = "",
    progress: Callable[[int, int, CaseResult], None] | None = None,
) -> EvalResult:
    """Run the cases (optionally one side of the split only), grade them and return the result."""
    cases = list(evalset.cases)
    if split and side in ("holdout", "dev"):
        cases = [c for c in cases if split.side(c.id) == side]
    if limit:
        cases = cases[:limit]
    metadata = default_metadata(max_steps)

    def one(case: Case) -> CaseResult:
        req = Request(
            case_id=case.id,
            input=case.input,
            context=dict(case.context),
            metadata={**metadata, **case.metadata},
        )
        run = target.run(req)
        g = grade(case, run)
        return CaseResult(case=case, run=run, grade=g, side=split.side(case.id) if split else "all")

    results: list[CaseResult] = []
    if concurrency > 1:
        with ThreadPoolExecutor(max_workers=concurrency) as ex:
            for i, r in enumerate(ex.map(one, cases), start=1):
                results.append(r)
                if progress:
                    progress(i, len(cases), r)
    else:
        for i, c in enumerate(cases, start=1):
            r = one(c)
            results.append(r)
            if progress:
                progress(i, len(cases), r)
    return EvalResult(
        results=results,
        evalset=evalset,
        split=split,
        target_name=getattr(target, "name", "target"),
        target_label=label,
    )
