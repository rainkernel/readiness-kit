"""Build the benchmark evaluation set from the Bitext customer-support data set.

Source: https://huggingface.co/datasets/bitext/Bitext-customer-support-llm-chatbot-training-dataset
(26,872 rows; fields instruction, category, intent, response; licence CDLA-Sharing-1.0, © Bitext Innovations).
The data is downloaded at run time and is not redistributed here.

    pip install "readiness-kit[benchmark]"      # adds the `datasets` library
    python prepare.py --rows 550 --seed 20261018 --out data/evalset.jsonl

Sampling is stratified by category and deterministic for a given seed, so anyone can rebuild the same set;
the set's sha256 is printed and recorded by `rk eval` in the run. A local copy of the data (CSV or JSONL with
the same fields) can be used with --source.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
import sys
from collections import defaultdict
from pathlib import Path

DATASET = "bitext/Bitext-customer-support-llm-chatbot-training-dataset"


def load_rows(source: str | None) -> list[dict]:
    if source:
        p = Path(source)
        if p.suffix.lower() == ".csv":
            with open(p, encoding="utf-8", newline="") as f:
                return list(csv.DictReader(f))
        with open(p, encoding="utf-8") as f:
            return [json.loads(line) for line in f if line.strip()]
    try:
        from datasets import load_dataset  # type: ignore[import-not-found]
    except ImportError:
        sys.exit("the `datasets` library is needed to download: pip install 'readiness-kit[benchmark]' (or pass --source)")
    ds = load_dataset(DATASET, split="train")
    return [dict(r) for r in ds]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rows", type=int, default=550, help="total cases, spread evenly over the categories (default 550)")
    ap.add_argument("--seed", type=int, default=20261018)
    ap.add_argument("--source", help="local CSV/JSONL copy instead of downloading")
    ap.add_argument("--out", default="data/evalset.jsonl")
    args = ap.parse_args()

    rows = load_rows(args.source)
    by_cat: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        cat = str(r.get("category") or "").strip().upper()
        text = str(r.get("instruction") or "").strip()
        if cat and text:
            by_cat[cat].append(r)
    cats = sorted(by_cat)
    if not cats:
        sys.exit("no rows with category and instruction found")
    per = max(1, args.rows // len(cats))
    rng = random.Random(args.seed)
    cases = []
    for cat in cats:
        pool = sorted(by_cat[cat], key=lambda r: hashlib.sha256((r["instruction"] + "|" + str(r.get("intent", ""))).encode()).hexdigest())
        rng.shuffle(pool)
        for r in pool[:per]:
            cases.append(
                {
                    "id": f"bitext-{hashlib.sha256(r['instruction'].encode()).hexdigest()[:10]}",
                    "input": r["instruction"],
                    "expected": {"category": cat},
                    "grader": "label",
                    "category": cat.lower(),
                    "tags": ["bitext", str(r.get("intent") or "").strip()],
                }
            )
    seen: set[str] = set()
    unique = []
    for c in cases:
        if c["id"] not in seen:
            seen.add(c["id"])
            unique.append(c)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        for c in unique:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
    digest = hashlib.sha256(out.read_bytes()).hexdigest()
    print(f"{len(unique)} cases over {len(cats)} categories ({', '.join(cats)}) → {out}")
    print(f"sha256 {digest}")


if __name__ == "__main__":
    main()
