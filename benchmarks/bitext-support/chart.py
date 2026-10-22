"""Draw the benchmark result as one chart: held-out pass rate beside dev pass rate, with the citation line.

Reads runs/eval.json (what run.sh writes) and writes an SVG. Standard library only, so the chart is as
reproducible as the number: same run file, same picture.

    python chart.py                       # runs/eval.json -> ../../docs/benchmark-<kit version>.svg
    python chart.py --run runs/eval.json --out chart.svg
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

NAVY = "#0B1F3B"
AMBER = "#E8A33D"
INK2 = "#4B5563"
LINE = "#D9DEE7"
PAPER = "#FFFFFF"
FONT = "Manrope, 'Segoe UI', Arial, sans-serif"
MONO = "'IBM Plex Mono', Menlo, Consolas, monospace"


def esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def render(run: dict) -> str:
    s = run["summary"]
    holdout, dev = s["holdout"], s["dev"]
    split = run["split"]
    version = run.get("kit_version", "?")
    target = run.get("target", {})
    agent = target.get("label") or target.get("name") or f"{target.get('type', 'agent')} target"
    created = str(run.get("created", ""))[:10]

    w, h = 1200, 675  # LinkedIn's 16:9 image
    chart_left, chart_right, chart_top, chart_bottom = 140, 700, 150, 520
    scale = (chart_bottom - chart_top) / 1.0  # pass rate 0..1
    bar_w, gap, x0 = 170, 110, chart_left + 60

    bars = [
        ("Held-out", holdout, NAVY, ["the headline number: cases", "the agent was not tuned on"]),
        ("Dev", dev, AMBER, ["what most teams publish;", "always the kinder number"]),
    ]

    def text(x, y, s, size, fill=NAVY, weight="400", family=FONT, anchor="start"):
        out.append(
            f'<text x="{x}" y="{y}" text-anchor="{anchor}" font-family="{family}" font-size="{size}" '
            f'font-weight="{weight}" fill="{fill}">{s}</text>'
        )

    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" role="img" aria-labelledby="t d">',
        f'<title id="t">Readiness Kit benchmark: held-out pass rate {holdout["pass_rate"]:.2f} against dev pass rate {dev["pass_rate"]:.2f}</title>',
        f'<desc id="d">Two bars. Held-out {holdout["passed"]} of {holdout["cases"]} cases passed ({holdout["pass_rate"]:.2f}); dev {dev["passed"]} of {dev["cases"]} ({dev["pass_rate"]:.2f}). The same agent, the same set, the same grader. The gap is the point.</desc>',
        f'<rect width="{w}" height="{h}" fill="{PAPER}"/>',
    ]
    text(60, 64, "The same agent, measured twice", 30, weight="700")
    text(
        60,
        100,
        f"Readiness Kit {esc(version)} · Bitext customer-support set, {s['all']['cases']} cases · {esc(agent)}",
        19,
        fill=INK2,
    )
    text(w - 60, 64, "github.com/rainkernel/readiness-kit", 18, weight="700", anchor="end")
    # gridlines
    for i in range(0, 11, 2):
        v = i / 10
        y = chart_bottom - v * scale
        out.append(
            f'<line x1="{chart_left}" y1="{y:.1f}" x2="{chart_right}" y2="{y:.1f}" stroke="{LINE}" stroke-width="1"/>'
        )
        text(chart_left - 14, f"{y + 6:.1f}", f"{v:.1f}", 16, fill=INK2, family=MONO, anchor="end")
    # bars
    for i, (label, side, colour, _note) in enumerate(bars):
        x = x0 + i * (bar_w + gap)
        bh = side["pass_rate"] * scale
        y = chart_bottom - bh
        out.append(f'<rect x="{x}" y="{y:.1f}" width="{bar_w}" height="{bh:.1f}" rx="6" fill="{colour}"/>')
        text(
            x + bar_w / 2,
            f"{y - 16:.1f}",
            f"{side['pass_rate']:.2f}",
            40,
            weight="700",
            family=MONO,
            anchor="middle",
        )
        text(x + bar_w / 2, chart_bottom + 34, label, 22, weight="700", anchor="middle")
        text(
            x + bar_w / 2,
            chart_bottom + 60,
            f"{side['passed']} of {side['cases']} cases",
            17,
            fill=INK2,
            anchor="middle",
        )
    # right-hand notes
    nx = 770
    text(nx, 190, "Why two numbers", 22, weight="700")
    y = 228
    for label, _side, _colour, note in bars:
        first, second = note
        out.append(
            f'<text x="{nx}" y="{y}" font-family="{FONT}" font-size="18" fill="{NAVY}">'
            f'<tspan font-weight="700">{label}:</tspan> {esc(first)}</text>'
        )
        text(nx, y + 26, esc(second), 18)
        y += 62
    y += 6
    for ln in [
        f'Split: sha256(salt + ":" + id) < {split["holdout_fraction"]},',
        "salt recorded in the run, so anyone with",
        "the salt reproduces the held-out number.",
        "",
        "The example agent is a floor (eleven keyword",
        "rules, no model). It is published because it",
        "can be checked, not because it is good.",
    ]:
        if ln:
            text(nx, y, esc(ln), 17, fill=INK2)
        y += 26
    # citation
    cite = (
        f"set sha256 {split['evalset_sha256'][:16]}… · salt {split['salt']} · run {created} · "
        "reproduce: benchmarks/bitext-support/run.sh"
    )
    out.append(f'<line x1="60" y1="{h - 70}" x2="{w - 60}" y2="{h - 70}" stroke="{LINE}"/>')
    text(60, h - 40, esc(cite), 15, fill=INK2, family=MONO)
    out.append("</svg>")
    return "\n".join(out) + "\n"


def main() -> int:
    here = Path(__file__).resolve().parent
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--run", default=str(here / "runs" / "eval.json"))
    ap.add_argument(
        "--out", default=None, help="output SVG (default: docs/benchmark-<version>.svg in the repository)"
    )
    args = ap.parse_args()
    run = json.loads(Path(args.run).read_text(encoding="utf-8"))
    out = (
        Path(args.out)
        if args.out
        else here.parent.parent / "docs" / f"benchmark-{run.get('kit_version', 'dev')}.svg"
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(run), encoding="utf-8")
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
