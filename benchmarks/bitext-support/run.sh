#!/usr/bin/env sh
# The published benchmark command. Rebuilds the set deterministically, splits it with a fixed salt, runs the
# evaluation and prints the held-out pass rate. Replace `target` in rk.yaml to benchmark another agent.
set -eu
cd "$(dirname "$0")"
python prepare.py --rows 550 --seed 20261018 --out data/evalset.jsonl
rk split data/evalset.jsonl --holdout 0.33 --salt bitext-support-v0.1 --out data/split.json
rk --config rk.yaml eval -q
rk version
