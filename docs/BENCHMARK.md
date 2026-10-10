# Benchmark

The v0.1 benchmark is a support-ticket classification task on the public Bitext customer-support data set, run
through the harness with a held-out split. Its purpose is to show that the harness produces a number anyone can
reproduce (same set, same split, same grader, same command), not to rank agents. `benchmarks/bitext-support/`
holds the preparation script, the configuration and the command; this page holds the method and the results.

## Method

1. **Set.** 550 customer utterances sampled from the Bitext data set, stratified by category (the same number per
   category), deterministic for seed 20261018. `prepare.py` downloads the data at run time (CDLA-Sharing-1.0,
   © Bitext Innovations; not redistributed) and prints the set's sha256.
2. **Task.** Output the category of the utterance. Graded with the Kit's `label` grader: the category must appear
   as a `category: …` line or a JSON field (or, in a short reply, as the bare label); case, spaces and hyphens
   are ignored.
3. **Split.** Held-out fraction 0.33, salt `bitext-support-v0.1`, method `sha256(salt + ":" + id) < fraction`.
   The headline number is the held-out pass rate; the dev rate is reported beside it.
4. **Command.** `benchmarks/bitext-support/run.sh`, which is:

   ```
   python prepare.py --rows 550 --seed 20261018 --out data/evalset.jsonl
   rk split data/evalset.jsonl --holdout 0.33 --salt bitext-support-v0.1 --out data/split.json
   rk --config rk.yaml eval -q
   ```

5. **Citation.** A result is cited with: held-out pass rate, cases held out, set sha256, split salt, Kit version,
   agent (and model and prompt hash for a model-backed target). `runs/eval.json` carries all of them.

## Results

A row is written from a run of the command above and is not edited afterwards; a later Kit version or a changed
data set gets a new row. The first row was run on the v0.1 release candidate and is repeated on tag day as part
of the release checklist; if the two differ, the tag-day row is added and the difference explained.

| Date | Kit | Agent | Held-out pass rate | Held out / total | Set sha256 | Salt |
| --- | --- | --- | --- | --- | --- | --- |
| 2026-10-10 | 0.1.0 (release candidate) | example agent (rule-based, no model) | 0.35 (63 of 178) | 178 / 550 | `b1ef757821c83cdb57ac4dc6753ba689de87b93da3f9f609088a5f933e708a72` | bitext-support-v0.1 |

The example agent is a floor: eleven keyword rules written for the walkthrough's synthetic tickets, not for this
data set. Three of the eleven Bitext categories (CANCEL, SHIPPING, SUBSCRIPTION) have no counterpart in its label
set, so they score zero, and the dev rate (0.44) sits above the held-out rate as it usually does. The number is
published because anyone can reproduce it exactly in under a minute, which is what the harness is for. A
model-backed target through the same command gives a number that depends on the model and the prompt, which is
why the Kit records both.

## Reproducing

```
pip install "readiness-kit[benchmark]"
cd benchmarks/bitext-support && ./run.sh
```

If the sha256 printed by `prepare.py` differs from the table, the upstream data set has changed since the run.
Say so when citing, and prefer the pinned revision of the data set if one is available to you.
