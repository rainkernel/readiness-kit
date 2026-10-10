"""Render a scorecard as Markdown (the shape of section 7 of the sample Evidence Report) and as terminal text."""

from __future__ import annotations

from typing import Any

from readiness_kit.rubric.score import Scorecard


def _basis_label(b: str) -> str:
    return {
        "measured": "measured",
        "declared": "declared",
        "mixed": "measured + declared",
        "not_measured": "not measured",
    }.get(b, b)


def scorecard_markdown(
    sc: Scorecard, attack: dict[str, Any] | None = None, title: str = "Readiness scorecard"
) -> str:
    v = sc.verdict()
    cov = sc.coverage()
    out: list[str] = []
    out.append(f"# {title}")
    out.append("")
    subj = sc.subject.get("name") or "agent"
    out.append(f"**Subject:** {subj}  ")
    out.append(f"**Score:** {v['score']} / 100 — **{v['band']}**  ")
    out.append(
        f"**Basis:** {cov['measured']} measured, {cov['mixed']} measured + declared, {cov['declared']} declared, {cov['not_measured']} not measured  "
    )
    out.append(
        f"**Findings:** {sc.findings['high']} high · {sc.findings['medium']} medium · {sc.findings['low']} low  "
    )
    out.append(f"**Generated:** {sc.created} · Readiness Kit · rubric v{sc.rubric.version}")
    out.append("")
    out.append(v["line"])
    out.append("")
    out.append("| Area | Weight | Points | Basis | Band | Notes |")
    out.append("| --- | ---: | ---: | --- | --- | --- |")
    for a in sc.areas:
        note = "; ".join(a.notes) if a.notes else next((ln["note"] for ln in a.lines if ln.get("note")), "")
        out.append(f"| {a.name} | {a.weight} | {a.points:g} | {_basis_label(a.basis)} | {a.band} | {note} |")
    out.append(f"| **Total** | **100** | **{sc.total}** | | **{v['band']}** | |")
    out.append("")
    out.append("## How each area was scored")
    out.append("")
    for a in sc.areas:
        out.append(f"### {a.name} — {a.points:g} of {a.weight}")
        out.append("")
        if not a.lines:
            out.append(f"- {'; '.join(a.notes) or 'not measured'}")
        for ln in a.lines:
            mx = f" of {ln['max']}" if ln.get("max") else ""
            note = f" — {ln['note']}" if ln.get("note") else ""
            out.append(f"- {ln['item']}: **{ln['points']:g}**{mx} ({_basis_label(ln['basis'])}){note}")
        out.append("")
    if attack is not None:
        out.append("## Attack classes (OWASP Top 10 for Agentic Applications)")
        out.append("")
        out.append("| Class | Cases | Followed | Outcome | Finding |")
        out.append("| --- | ---: | ---: | --- | --- |")
        for row in attack["summary"]["by_class"]:
            if not row["cases"]:
                out.append(f"| {row['asi']} {row['class']} | 0 | — | not run | |")
                continue
            finding = "; ".join(f"{f['case_id']}: {f['detail']}" for f in row["findings"])[:200]
            out.append(
                f"| {row['asi']} {row['class']} | {row['cases']} | {row['followed']} | {row['outcome']} | {finding} |"
            )
        out.append("")
    out.append("## What this is")
    out.append("")
    out.append(
        "The Readiness Kit's scorecard: the eight areas and weights of the Rainkernel readiness rubric applied to what the Kit measured "
        "(evaluation run, attack run, scanner run, cost baseline, Agent BOM) and what the team declared in assessment.yaml. "
        "Declared items are self-assessed. The licensed Agent Readiness Gate produces the full Evidence Report "
        "(findings, fixes in priority order, standards mapping, signed) from the same evidence: "
        "https://rainkernel.com/products/agent-readiness-gate/sample-report"
    )
    out.append("")
    return "\n".join(out)


def scorecard_text(sc: Scorecard) -> str:
    v = sc.verdict()
    width = max(len(a.name) for a in sc.areas) + 2
    rows = [f"{'Area':<{width}} {'Pts':>5} {'Max':>4}  Basis"]
    for a in sc.areas:
        rows.append(f"{a.name:<{width}} {a.points:>5g} {a.weight:>4}  {_basis_label(a.basis)}")
    rows.append(f"{'Total':<{width}} {sc.total:>5} {100:>4}  {v['band']}")
    rows.append("")
    rows.append(v["line"])
    return "\n".join(rows)
