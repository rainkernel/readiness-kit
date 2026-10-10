"""The ``rk`` command.

rk init [DIR]            write rk.yaml, agent.yaml, assessment.yaml and prices.yaml templates
rk demo [--out DIR]      copy the example agent and run the whole pipeline on it, offline
rk split SET             make the held-out split
rk eval                  run the evaluation set against the target and grade it
rk attack                run the attack pack against the target
rk scan                  run the open scanners (mcp-scanner, snyk-agent-scan, agentic-radar, promptfoo)
rk bom                   emit the Agent BOM (CycloneDX 1.6)
rk cost TRACES…          cost per completed task from traces, projected to volume
rk score                 apply the rubric to everything in the runs folder → scorecard
rk validate KIND FILE    check a file against the Kit's schemas
rk version
"""

from __future__ import annotations

import argparse
import contextlib
import shutil
import sys
from pathlib import Path
from typing import Any

from readiness_kit import __version__
from readiness_kit.config import Config, load_config
from readiness_kit.paths import example_path, starter_pack_path
from readiness_kit.util import KitError, write_json, write_text_file

EXIT_OK, EXIT_ERROR, EXIT_FINDINGS = 0, 1, 2


def say(msg: str = "") -> None:
    print(msg, flush=True)


# --- helpers -------------------------------------------------------------------------------------------------


def _target(cfg: Config) -> Any:
    from readiness_kit.harness.targets import build_target

    if not cfg.target:
        raise KitError("no target in rk.yaml (target: {type: python, module: agent} …)")
    return build_target(cfg.target, base_dir=cfg.base_dir)


def _cfg(args: argparse.Namespace, required: bool = True) -> Config:
    return load_config(getattr(args, "config", None), required=required)


def _runs(cfg: Config, args: argparse.Namespace) -> Path:
    out = getattr(args, "runs", None)
    return Path(out) if out else cfg.runs


# --- commands ------------------------------------------------------------------------------------------------


def cmd_version(args: argparse.Namespace) -> int:
    say(f"readiness-kit {__version__}")
    return EXIT_OK


def cmd_init(args: argparse.Namespace) -> int:
    target = Path(args.dir or ".").resolve()
    target.mkdir(parents=True, exist_ok=True)
    src = example_path()
    written = []
    for name in ("rk.yaml", "agent.yaml", "assessment.yaml", "prices.yaml"):
        dst = target / name
        if dst.exists() and not args.force:
            say(f"keep   {dst} (exists; --force to overwrite)")
            continue
        shutil.copyfile(src / name, dst)
        written.append(dst)
        say(f"wrote  {dst}")
    say("")
    say(
        "Next: set target: in rk.yaml to your agent (python | http | openai-chat | command), list what it is made of in agent.yaml,"
    )
    say(
        "answer assessment.yaml, then run `rk split`, `rk eval`, `rk attack`, `rk bom`, `rk cost`, `rk score`, or `rk demo` to see it on the example first."
    )
    return EXIT_OK


def cmd_split(args: argparse.Namespace) -> int:
    from readiness_kit.harness.evalset import load_evalset
    from readiness_kit.harness.split import make_split, save_split

    cfg = _cfg(args, required=False)
    set_path = args.set or cfg.eval.get("set")
    if not set_path:
        raise KitError("give the evaluation set: rk split SET.jsonl (or eval.set in rk.yaml)")
    es = load_evalset(cfg.resolve(set_path) or set_path)
    split = make_split(es, holdout_fraction=args.holdout, salt=args.salt)
    out = Path(args.out) if args.out else (cfg.resolve(cfg.eval.get("split")) or cfg.base_dir / "split.json")
    save_split(split, out)
    say(
        f"split  {len(split.holdout)} held out, {len(split.dev)} dev of {len(es)} cases (fraction {args.holdout}, salt {split.salt}) → {out}"
    )
    say("Tune on dev; publish held-out. Keep the salt with the set.")
    return EXIT_OK


def _progress(i: int, n: int, r: Any) -> None:
    mark = "pass" if r.grade.passed else ("n/a " if r.grade.passed is None else "FAIL")
    sys.stderr.write(f"\r  {i}/{n} {mark} {r.case.id:<24}"[:100])
    sys.stderr.flush()
    if i == n:
        sys.stderr.write("\n")


def cmd_eval(args: argparse.Namespace) -> int:
    from readiness_kit.harness.evalset import load_evalset
    from readiness_kit.harness.runner import run_eval
    from readiness_kit.harness.split import load_split

    cfg = _cfg(args)
    set_path = cfg.resolve(args.set or cfg.eval.get("set"))
    if not set_path:
        raise KitError("give the evaluation set: --set SET.jsonl or eval.set in rk.yaml")
    es = load_evalset(set_path)
    split = None
    split_path = cfg.resolve(args.split or cfg.eval.get("split"))
    if split_path and split_path.exists():
        split = load_split(split_path)
        if split.evalset_sha256 and es.sha256 != split.evalset_sha256:
            say(
                "note   the evaluation set changed since the split was made (ids not in the split file are assigned by the same rule)"
            )
    elif not args.no_split:
        say(
            "note   no split file: the headline number is on all cases. Run `rk split` first for a held-out number."
        )
    target = _target(cfg)
    say(
        f"eval   {len(es)} cases → target '{cfg.target.get('type')}'"
        + (f" ({args.side} side only)" if args.side else "")
    )
    result = run_eval(
        target,
        es,
        split,
        concurrency=int(args.concurrency or cfg.eval.get("concurrency", 1)),
        limit=args.limit,
        side=args.side,
        max_steps=cfg.max_steps,
        label=cfg.name,
        progress=_progress if not args.quiet else None,
    )
    out = _runs(cfg, args) / "eval.json"
    write_json(out, result.to_dict())
    s = result.summary()
    h = s["headline"]
    say(
        f"result {h['side']} pass rate {h['pass_rate']:.2f} ({h['passed']}/{h['graded']} graded; {h['not_observable']} not observable; {h['errors']} errors)"
    )
    if s["dev"]:
        say(
            f"       dev pass rate {s['dev']['pass_rate']:.2f} ({s['dev']['passed']}/{s['dev']['graded']}) (tuning side, not the headline)"
        )
    for row in s["by_category"]:
        say(
            f"       {row['category']:<28} {row['pass_rate']:.2f}  ({row['passed']}/{row['graded']})"
            + (f"  failing: {', '.join(row['failing'][:4])}" if row["failing"] else "")
        )
    say(f"wrote  {out}")
    return EXIT_OK


def cmd_attack(args: argparse.Namespace) -> int:
    from readiness_kit.harness.attacks import load_pack, run_attacks

    cfg = _cfg(args)
    pack_arg = args.pack or cfg.attack.get("pack") or "starter"
    pack_path = starter_pack_path() if pack_arg == "starter" else (cfg.resolve(pack_arg) or Path(pack_arg))
    cases = load_pack(pack_path)
    target = _target(cfg)
    only = [x.strip() for x in args.only.split(",")] if args.only else None
    say(f"attack {len(cases)} cases from {pack_path} → target '{cfg.target.get('type')}'")
    result = run_attacks(target, cases, pack_path=str(pack_path), max_steps=cfg.max_steps, only=only)
    out = _runs(cfg, args) / "attack.json"
    write_json(out, result.to_dict())
    s = result.summary()
    for row in s["by_class"]:
        if not row["cases"]:
            continue
        say(
            f"       {row['asi']} {row['class']:<36} {row['followed']}/{row['cases']} followed  {row['outcome']}"
        )
        for f in row["findings"]:
            say(f"         ! {f['case_id']} {f['title']}: {f['detail'][:110]}")
    say(
        f"result {s['followed']} followed, {s['passed']} passed, {s['not_observable']} not observable, {s['errors']} errors; {s['high']} high, {s['medium']} medium, {s['low']} low"
    )
    say(f"wrote  {out}")
    return EXIT_FINDINGS if (s["high"] and args.fail_on_high) else EXIT_OK


def cmd_scan(args: argparse.Namespace) -> int:
    from readiness_kit.adapters import ADAPTERS, run_scanners
    from readiness_kit.adapters.base import ScanContext

    cfg = _cfg(args, required=False)
    path = Path(args.path or cfg.scan.get("path") or cfg.base_dir).resolve()
    runs = _runs(cfg, args)
    tools = [
        t.strip()
        for t in (args.tools or ",".join(cfg.scan.get("tools") or list(ADAPTERS))).split(",")
        if t.strip()
    ]
    ctx = ScanContext(
        path=path,
        out_dir=runs / "scan",
        config_path=cfg.resolve(args.config_path or cfg.scan.get("config_path")),
        tools_json=cfg.resolve(args.tools_json or cfg.scan.get("tools_json")),
        server_url=args.server_url or cfg.scan.get("server_url"),
        framework=args.framework or cfg.scan.get("framework"),
        promptfoo_config=cfg.resolve(args.promptfoo_config or cfg.scan.get("promptfoo_config")),
        timeout=int(args.timeout),
    )
    say(f"scan   {path} with {', '.join(tools)}")
    result = run_scanners(ctx, tools)
    for r in result["results"]:
        if r["status"] == "ok":
            c = r["counts"]
            say(
                f"       {r['tool']:<16} ok       {c['high']} high, {c['medium']} medium, {c['low']} low, {c['info']} info"
            )
            for f in r["findings"][:8]:
                say(f"         ! [{f['severity']}] {f['component']}: {f['title'][:100]}")
        else:
            say(f"       {r['tool']:<16} {r['status']:<8} {r['reason']}")
    out = runs / "scan.json"
    write_json(out, result)
    say(f"wrote  {out}")
    return EXIT_OK


def cmd_bom(args: argparse.Namespace) -> int:
    from readiness_kit.bom import discover, emit_cyclonedx, load_manifest, summarise

    cfg = _cfg(args, required=False)
    manifest_path = cfg.resolve(args.manifest or cfg.bom.get("manifest") or "agent.yaml")
    if manifest_path is None or not manifest_path.exists():
        raise KitError(f"agent manifest not found ({manifest_path}); run `rk init` or pass --manifest")
    m = load_manifest(manifest_path)
    disc = args.discover or cfg.bom.get("discover")
    radar = cfg.resolve(args.radar or cfg.bom.get("radar"))
    if disc or radar:
        root = cfg.resolve(disc) if disc else manifest_path.parent
        found = discover(
            root or manifest_path.parent, radar_graph=radar if radar and radar.exists() else None
        )
        m.merge(found)
        say(
            f"bom    {len(found)} component(s) discovered under {root}"
            + (f" and {radar.name}" if radar and radar.exists() else "")
        )
    bom = emit_cyclonedx(m)
    runs = _runs(cfg, args)
    cdx_path = Path(args.out) if args.out else runs / "bom.cdx.json"
    write_json(cdx_path, bom)
    summary = summarise(m, bom, bom_path=str(cdx_path))
    write_json(runs / "bom.json", summary)
    s = summary["summary"]
    say(
        f"bom    {m.name} {m.version or 'unversioned'}: {s['components']} components "
        + ", ".join(f"{v} {k}" for k, v in s["by_kind"].items())
    )
    for u in s["unversioned"]:
        say(f"         ! unversioned {u['kind']}: {u['name']}")
    for u in s["unpinned_sources"]:
        say(f"         ! skill from a remote source without a pinned hash: {u}")
    for u in s["missing_files"]:
        say(f"         ! file listed in the manifest is missing: {u}")
    say(f"wrote  {cdx_path} (CycloneDX 1.6) and {runs / 'bom.json'}")
    return EXIT_OK


def cmd_cost(args: argparse.Namespace) -> int:
    from readiness_kit.cost import baseline, load_prices, load_traces

    cfg = _cfg(args, required=False)
    traces = [str(cfg.resolve(t)) for t in (args.traces or cfg.cost.get("traces") or [])]
    if not traces:
        raise KitError(
            "give trace files: rk cost TRACES… (or cost.traces in rk.yaml); `rk cost runs/eval.json` uses the evaluation run"
        )
    prices = load_prices(cfg.resolve(args.prices or cfg.cost.get("prices")))
    ceiling = args.ceiling if args.ceiling is not None else cfg.cost.get("ceiling_per_task")
    volume = args.volume if args.volume is not None else cfg.cost.get("volume_per_month")
    spans, formats = load_traces(traces, fmt=args.format)
    result = baseline(
        spans,
        prices,
        ceiling=float(ceiling) if ceiling is not None else None,
        volume_per_month=int(volume) if volume else None,
        formats=formats,
    )
    s = result["summary"]
    p = s["per_task"]
    say(
        f"cost   {s['tasks']} tasks ({s['completed']} completed) from {', '.join(f'{Path(k).name} [{v}]' for k, v in formats.items())}"
    )
    say(
        f"       per completed task: {prices.currency} {p['cost']:.4f} · {p['input_tokens']:.0f} in / {p['output_tokens']:.0f} out tokens · {p['llm_calls']:.1f} LLM calls · {p['tool_calls']:.1f} tool calls · {p['retries']:.2f} retries"
    )
    if s["ceiling"] is not None:
        say(
            f"       ceiling {prices.currency} {s['ceiling']:.2f} → {s['ratio']:.2f}× "
            + ("inside" if s["ratio"] <= 1 else "OVER")
        )
    if s["projection"]:
        pr = s["projection"]
        say(
            f"       at {pr['volume_per_month']:,} tasks a month: {prices.currency} {pr['monthly_cost']:,.0f}"
            + (f" against a budget of {pr['monthly_budget']:,.0f}" if pr["monthly_budget"] else "")
        )
    if s["unpriced_models"]:
        say(
            f"       ! no price for {', '.join(s['unpriced_models'])} ({s['unpriced_tokens_share']:.0%} of tokens) ; add them to the price table"
        )
    if not s["has_usage"]:
        say(
            "       ! no token usage in the traces: the cost is zero because nothing was counted, not because it is free"
        )
    out = _runs(cfg, args) / "cost.json"
    write_json(out, result)
    say(f"wrote  {out}")
    return EXIT_OK


def cmd_score(args: argparse.Namespace) -> int:
    from readiness_kit.rubric import load_rubric, score
    from readiness_kit.rubric.render import scorecard_markdown, scorecard_text
    from readiness_kit.rubric.score import Evidence

    cfg = _cfg(args, required=False)
    runs = _runs(cfg, args)
    rubric = load_rubric(cfg.resolve(args.rubric) if args.rubric else None)
    ev = Evidence.load(runs, cfg.resolve(args.assessment or cfg.assessment))
    if not ev.inputs:
        raise KitError(
            f"nothing to score in {runs}: run rk eval / attack / scan / bom / cost first (or rk demo)"
        )
    sc = score(rubric, ev, subject={"name": cfg.name})
    out = Path(args.out) if args.out else runs / "scorecard.json"
    write_json(out, sc.to_dict())
    md = Path(args.md) if args.md else runs / "scorecard.md"
    write_text_file(md, scorecard_markdown(sc, attack=ev.attack, title=f"Readiness scorecard: {cfg.name}"))
    say(scorecard_text(sc))
    say("")
    say(f"wrote  {out} and {md}")
    return EXIT_OK


def cmd_validate(args: argparse.Namespace) -> int:
    from readiness_kit.schemas import validate_file

    errors = validate_file(args.kind, args.file)
    if errors:
        for e in errors:
            say(f"  ✗ {e}")
        say(f"{args.file}: {len(errors)} problem(s) as {args.kind}")
        return EXIT_ERROR
    say(f"{args.file}: valid {args.kind}")
    return EXIT_OK


def cmd_demo(args: argparse.Namespace) -> int:
    from readiness_kit.demo import run_demo

    return run_demo(Path(args.out) if args.out else None, keep=args.keep, quiet=args.quiet)


# --- parser --------------------------------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="rk", description="Readiness Kit: the open-source frame under the Agent Readiness Gate."
    )
    p.add_argument("--config", "-c", help="path to rk.yaml (default: ./rk.yaml)")
    p.add_argument("--runs", help="runs folder for artefacts (default: runs_dir in rk.yaml, or ./runs)")
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("version", help="print the version")
    s.set_defaults(fn=cmd_version)

    s = sub.add_parser("init", help="write rk.yaml, agent.yaml, assessment.yaml and prices.yaml templates")
    s.add_argument("dir", nargs="?", help="directory (default: .)")
    s.add_argument("--force", action="store_true", help="overwrite existing files")
    s.set_defaults(fn=cmd_init)

    s = sub.add_parser("demo", help="run the whole pipeline on the bundled example agent, offline")
    s.add_argument("--out", help="directory to copy the example into (default: ./rk-demo)")
    s.add_argument(
        "--keep", action="store_true", help="keep an existing demo directory instead of refreshing it"
    )
    s.add_argument("--quiet", "-q", action="store_true")
    s.set_defaults(fn=cmd_demo)

    s = sub.add_parser("split", help="make the held-out split")
    s.add_argument("set", nargs="?", help="evaluation set (JSONL or YAML)")
    s.add_argument("--holdout", type=float, default=0.33, help="held-out fraction (default 0.33)")
    s.add_argument("--salt", help="salt for the split (default: random; keep it with the set)")
    s.add_argument("--out", help="split file (default: eval.split in rk.yaml or ./split.json)")
    s.set_defaults(fn=cmd_split)

    s = sub.add_parser("eval", help="run the evaluation set against the target and grade it")
    s.add_argument("--set", help="evaluation set (default: eval.set in rk.yaml)")
    s.add_argument("--split", help="split file (default: eval.split in rk.yaml)")
    s.add_argument("--no-split", action="store_true", help="run without a split and say so")
    s.add_argument("--side", choices=["holdout", "dev"], help="run one side only")
    s.add_argument("--limit", type=int, help="first N cases only")
    s.add_argument("--concurrency", type=int, help="parallel requests (default 1)")
    s.add_argument("--quiet", "-q", action="store_true")
    s.set_defaults(fn=cmd_eval)

    s = sub.add_parser("attack", help="run the attack pack against the target")
    s.add_argument(
        "--pack", help="'starter' (bundled) or a folder/file of cases (default: attack.pack in rk.yaml)"
    )
    s.add_argument("--only", help="comma-separated ASI classes or case ids, e.g. ASI01,ASI08")
    s.add_argument(
        "--fail-on-high", action="store_true", help="exit 2 when a high finding is followed (for CI)"
    )
    s.set_defaults(fn=cmd_attack)

    s = sub.add_parser("scan", help="run the open scanners on a directory, config or server")
    s.add_argument("--path", help="directory to scan (default: the rk.yaml directory)")
    s.add_argument(
        "--tools", help="comma-separated: mcp-scanner,snyk-agent-scan,agentic-radar,promptfoo (default: all)"
    )
    s.add_argument("--config-path", help="an MCP client config file (mcpServers) to scan")
    s.add_argument("--tools-json", help="a saved MCP tools/list JSON for an offline scan")
    s.add_argument("--server-url", help="a remote MCP server URL")
    s.add_argument("--framework", help="for agentic-radar: langgraph|crewai|n8n|openai-agents|autogen")
    s.add_argument("--promptfoo-config", help="a promptfooconfig.yaml to run")
    s.add_argument("--timeout", default=600, help="seconds per scanner (default 600)")
    s.set_defaults(fn=cmd_scan)

    s = sub.add_parser("bom", help="emit the Agent BOM as CycloneDX 1.6")
    s.add_argument("--manifest", help="agent.yaml (default: bom.manifest in rk.yaml or ./agent.yaml)")
    s.add_argument("--discover", help="directory to discover MCP configs, skills and prompts in")
    s.add_argument("--radar", help="an Agentic Radar --export-graph-json file to add tools from")
    s.add_argument("--out", help="CycloneDX output (default: runs/bom.cdx.json)")
    s.set_defaults(fn=cmd_bom)

    s = sub.add_parser("cost", help="cost per completed task from traces")
    s.add_argument(
        "traces", nargs="*", help="trace files: OTel JSONL, OTLP JSON, Langfuse JSONL, or runs/eval.json"
    )
    s.add_argument("--format", default="auto", choices=["auto", "otel", "otlp", "langfuse", "rk"])
    s.add_argument("--prices", help="price table YAML (default: cost.prices in rk.yaml)")
    s.add_argument(
        "--ceiling", type=float, help="ceiling per completed task (default: cost.ceiling_per_task)"
    )
    s.add_argument(
        "--volume", type=int, help="tasks per month for the projection (default: cost.volume_per_month)"
    )
    s.set_defaults(fn=cmd_cost)

    s = sub.add_parser("score", help="apply the rubric to the runs folder")
    s.add_argument("--assessment", help="assessment.yaml with the declared answers")
    s.add_argument("--rubric", help="a rubric YAML other than the bundled one")
    s.add_argument("--out", help="scorecard JSON (default: runs/scorecard.json)")
    s.add_argument("--md", help="scorecard Markdown (default: runs/scorecard.md)")
    s.set_defaults(fn=cmd_score)

    s = sub.add_parser("validate", help="check a file against the Kit's schemas")
    s.add_argument(
        "kind", choices=["evalset", "case", "pack", "manifest", "scorecard", "report", "rubric", "bom"]
    )
    s.add_argument("file")
    s.set_defaults(fn=cmd_validate)
    return p


def _tolerant_console() -> None:
    """Keep the CLI running on consoles that cannot encode every character it prints.

    The output uses a few non-ASCII glyphs (arrows, multiplication sign). On a Windows console with a legacy
    code page they would raise UnicodeEncodeError; replacing them is better than a crash.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            with contextlib.suppress(ValueError, OSError):
                reconfigure(errors="replace")


def main(argv: list[str] | None = None) -> int:
    _tolerant_console()
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.fn(args))
    except KitError as e:
        say(f"rk: {e}")
        return EXIT_ERROR
    except KeyboardInterrupt:
        say("rk: interrupted")
        return 130


def _entry() -> None:
    sys.exit(main())


if __name__ == "__main__":
    _entry()
