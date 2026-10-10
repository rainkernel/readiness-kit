"""`rk demo`: the whole pipeline on the bundled example agent, offline, in under a minute.

Copies examples/ticket-triage-agent into ./rk-demo (or --out), then runs split → eval → attack → bom → cost →
scan → score there and prints where the artefacts are. The scanners run only if they are installed; the demo
says which were skipped and why, because a skipped scanner is a fact about your machine, not about the agent.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from readiness_kit.cli import main as rk_main
from readiness_kit.paths import example_path
from readiness_kit.util import KitError

DEMO_SALT = "rk-demo-2026"


def run_demo(out: Path | None, keep: bool = False, quiet: bool = False) -> int:
    src = example_path()
    dest = (out or Path.cwd() / "rk-demo").resolve()
    if dest.exists() and not keep:
        shutil.rmtree(dest)
    if not dest.exists():
        shutil.copytree(
            src, dest, ignore=shutil.ignore_patterns("runs", "split.json", "__pycache__", "*.pyc")
        )
    print(f"demo   example agent copied to {dest}")
    print("       a deliberately weak ticket-triage agent: no model, no network, four known weaknesses\n")
    base = ["--config", str(dest / "rk.yaml")]
    steps: list[tuple[str, list[str]]] = [
        (
            "split",
            ["split", str(dest / "evalset.jsonl"), "--salt", DEMO_SALT, "--out", str(dest / "split.json")],
        ),
        ("eval", ["eval", *(["-q"] if quiet else [])]),
        ("attack", ["attack"]),
        ("bom", ["bom"]),
        ("cost", ["cost"]),
        ("scan", ["scan"]),
        ("score", ["score"]),
    ]
    for name, argv in steps:
        print(f"── rk {name} " + "─" * (60 - len(name)))
        code = rk_main([*base, *argv])
        if code not in (0, 2):
            raise KitError(f"rk {name} failed with exit code {code}")
        print()
    runs = dest / "runs"
    print("done   artefacts:")
    for f in (
        "eval.json",
        "attack.json",
        "bom.cdx.json",
        "cost.json",
        "scan.json",
        "scorecard.json",
        "scorecard.md",
    ):
        print(f"         {runs / f}")
    print()
    print(
        "next   point rk.yaml at your own agent (docs/WALKTHROUGH.md, step 4) and run the same seven commands."
    )
    print("       The licensed Gate turns these artefacts into the signed Evidence Report:")
    print("       https://rainkernel.com/products/agent-readiness-gate/sample-report")
    return 0
