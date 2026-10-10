"""Promptfoo (``promptfoo``, MIT): evaluations and red-team runs defined in a ``promptfooconfig.yaml``.

The Kit runs ``npx --yes promptfoo@latest eval -c CONFIG -o <out>/promptfoo-results.json`` and reads the results
file: every failed test becomes a finding (severity ``medium`` by default; a red-team test carrying a severity
keeps it), and the pass/fail counts go into the stats. Promptfoo talks to the model providers itself, so the keys
it needs are its own (``OPENAI_API_KEY`` and friends). Pass ``--promptfoo-config`` or keep a
``promptfooconfig.yaml`` in the scanned directory.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from typing import Any

from readiness_kit.adapters.base import Adapter, Finding, ScanContext, SkipScan, norm_severity


class PromptfooAdapter(Adapter):
    name = "promptfoo"
    needs = ["promptfoo", "npx"]
    install_hint = "install Node.js (npx) or `npm install -g promptfoo`"

    def command(self, ctx: ScanContext) -> list[str]:
        cfg = ctx.promptfoo_config
        if cfg is None:
            for name in ("promptfooconfig.yaml", "promptfooconfig.yml", "promptfooconfig.json"):
                if (ctx.path / name).is_file():
                    cfg = ctx.path / name
                    break
        if cfg is None:
            raise SkipScan("no promptfooconfig.yaml in the scanned directory; pass --promptfoo-config")
        exe = (
            ["promptfoo"]
            if shutil.which("promptfoo", path=ctx.env.get("PATH"))
            else ["npx", "--yes", "promptfoo@latest"]
        )
        out = ctx.out_dir / "promptfoo-results.json"
        return [
            *exe,
            "eval",
            "-c",
            str(cfg),
            "-o",
            str(out),
            "--no-progress-bar",
            *ctx.extra_args.get(self.name, []),
        ]

    def load_output(self, proc: subprocess.CompletedProcess[str], ctx: ScanContext) -> Any:
        out = ctx.out_dir / "promptfoo-results.json"
        if not out.exists():
            raise ValueError(
                f"no results written ({proc.stderr.strip()[-200:] or proc.stdout.strip()[-200:]})"
            )
        return json.loads(out.read_text(encoding="utf-8"))

    def parse(self, raw: Any, ctx: ScanContext) -> tuple[list[Finding], dict[str, Any]]:
        results_obj = raw.get("results", raw) if isinstance(raw, dict) else {}
        rows = (
            results_obj.get("results", [])
            if isinstance(results_obj, dict)
            else (results_obj if isinstance(results_obj, list) else [])
        )
        stats_src = results_obj.get("stats", {}) if isinstance(results_obj, dict) else {}
        findings: list[Finding] = []
        passed = failed = 0
        for r in rows:
            if not isinstance(r, dict):
                continue
            ok = r.get("success")
            if ok is None:
                ok = bool(r.get("gradingResult", {}).get("pass"))
            if ok:
                passed += 1
                continue
            failed += 1
            gr = r.get("gradingResult") or {}
            vars_ = r.get("vars") or r.get("testCase", {}).get("vars") or {}
            desc = (
                r.get("description")
                or r.get("testCase", {}).get("description")
                or json.dumps(vars_, ensure_ascii=False)[:120]
            )
            md = (r.get("testCase") or {}).get("metadata") or {}
            sev = norm_severity(md.get("severity") or "medium")
            findings.append(
                Finding(
                    tool=self.name,
                    severity=sev,
                    title=str(desc)[:160],
                    component=str(
                        r.get("promptId") or r.get("provider", {}).get("id")
                        if isinstance(r.get("provider"), dict)
                        else r.get("provider") or ""
                    ),
                    detail=str(gr.get("reason") or "")[:500],
                    category=str(md.get("pluginId") or md.get("strategyId") or ""),
                    raw={"score": r.get("score"), "testIdx": r.get("testIdx")},
                )
            )
        stats = {
            "passed": stats_src.get("successes", passed),
            "failed": stats_src.get("failures", failed),
            "tests": passed + failed,
            "results_path": str(ctx.out_dir / "promptfoo-results.json"),
        }
        return findings, stats
