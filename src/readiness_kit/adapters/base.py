"""The adapter contract: each open scanner is run as a subprocess, its raw output kept next to the run, and its
findings normalised into one shape. An adapter that cannot run (tool not installed, token missing, nothing to
scan) reports ``skipped`` with the reason; it never fakes a clean result.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

SEVERITY_ORDER = ("high", "medium", "low", "info")


def norm_severity(value: Any) -> str:
    s = str(value or "").strip().lower()
    if s in ("critical", "high", "error", "severe"):
        return "high"
    if s in ("medium", "moderate", "warning", "warn"):
        return "medium"
    if s in ("low", "minor"):
        return "low"
    return "info"


@dataclass
class Finding:
    tool: str
    severity: str
    title: str
    component: str = ""
    detail: str = ""
    category: str = ""
    raw: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool": self.tool,
            "severity": self.severity,
            "title": self.title,
            "component": self.component,
            "detail": self.detail,
            "category": self.category,
        }


@dataclass
class ScanContext:
    path: Path
    out_dir: Path
    config_path: Path | None = None
    tools_json: Path | None = None
    server_url: str | None = None
    framework: str | None = None
    promptfoo_config: Path | None = None
    timeout: int = 600
    extra_args: dict[str, list[str]] = field(default_factory=dict)
    env: dict[str, str] = field(default_factory=lambda: dict(os.environ))


@dataclass
class ScanResult:
    tool: str
    status: str  # ok | skipped | failed
    reason: str = ""
    command: list[str] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)
    raw_path: str | None = None
    stats: dict[str, Any] = field(default_factory=dict)
    version: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool": self.tool,
            "status": self.status,
            "reason": self.reason,
            "command": self.command,
            "version": self.version,
            "findings": [f.to_dict() for f in self.findings],
            "counts": {s: sum(1 for f in self.findings if f.severity == s) for s in SEVERITY_ORDER},
            "raw_path": self.raw_path,
            "stats": self.stats,
        }


class Adapter:
    name = "adapter"
    install_hint = ""
    needs: list[str] = []  # binaries looked up on PATH; any one of them is enough

    def available(self, ctx: ScanContext) -> tuple[bool, str]:
        if self.needs and not any(shutil.which(b, path=ctx.env.get("PATH")) for b in self.needs):
            return False, f"{' or '.join(self.needs)} not found on PATH; {self.install_hint}"
        return True, ""

    def command(self, ctx: ScanContext) -> list[str]:
        raise NotImplementedError

    def parse(self, raw: Any, ctx: ScanContext) -> tuple[list[Finding], dict[str, Any]]:
        raise NotImplementedError

    def run(self, ctx: ScanContext) -> ScanResult:
        ok, why = self.available(ctx)
        if not ok:
            return ScanResult(self.name, "skipped", why)
        try:
            cmd = self.command(ctx)
        except SkipScan as e:
            return ScanResult(self.name, "skipped", str(e))
        ctx.out_dir.mkdir(parents=True, exist_ok=True)
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=ctx.timeout,
                env=ctx.env,
                cwd=str(ctx.path),
                check=False,
            )
        except subprocess.TimeoutExpired:
            return ScanResult(self.name, "failed", f"timed out after {ctx.timeout}s", command=cmd)
        except OSError as e:
            return ScanResult(self.name, "failed", f"could not start: {e}", command=cmd)
        raw_path = ctx.out_dir / f"{self.name}.stdout.txt"
        raw_path.write_text(proc.stdout, encoding="utf-8")
        (ctx.out_dir / f"{self.name}.stderr.txt").write_text(proc.stderr, encoding="utf-8")
        try:
            findings, stats = self.parse(self.load_output(proc, ctx), ctx)
        except SkipScan as e:
            return ScanResult(self.name, "skipped", str(e), command=cmd, raw_path=str(raw_path))
        except Exception as e:  # a parser gap is reported, not hidden
            status = "failed"
            reason = f"exit {proc.returncode}; could not parse output ({type(e).__name__}: {e}); stderr: {proc.stderr[-300:].strip()}"
            return ScanResult(self.name, status, reason, command=cmd, raw_path=str(raw_path))
        if proc.returncode != 0 and not findings and not stats:
            return ScanResult(
                self.name,
                "failed",
                f"exit {proc.returncode}: {(proc.stderr or proc.stdout)[-300:].strip()}",
                command=cmd,
                raw_path=str(raw_path),
            )
        stats["exit_code"] = proc.returncode
        return ScanResult(
            self.name, "ok", "", command=cmd, findings=findings, raw_path=str(raw_path), stats=stats
        )

    def load_output(self, proc: subprocess.CompletedProcess[str], ctx: ScanContext) -> Any:
        """Default: the JSON on stdout. Adapters that write a file override this."""
        import json

        text = proc.stdout.strip()
        start = text.find("{")
        start_l = text.find("[")
        if start_l >= 0 and (start < 0 or start_l < start):
            start = start_l
        if start < 0:
            raise ValueError("no JSON on stdout")
        return json.loads(text[start:])


class SkipScan(Exception):
    """Raised by an adapter when there is nothing it can scan in this context."""


def walk_findings(obj: Any, out: list[dict[str, Any]], depth: int = 0) -> None:
    """Collect every object carrying a ``severity`` key, for tools whose JSON shape varies by version."""
    if depth > 12:
        return
    if isinstance(obj, dict):
        if "severity" in obj and isinstance(obj["severity"], (str, int)):
            out.append(obj)
        for v in obj.values():
            walk_findings(v, out, depth + 1)
    elif isinstance(obj, list):
        for v in obj:
            walk_findings(v, out, depth + 1)
