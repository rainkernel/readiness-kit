# Benchmark

The v0.1 benchmark is a support-ticket classification task on the public Bitext customer-support data set, run
through the harness with a held-out split. Its purpose is to show that the harness produces a number anyone can
reproduce — same set, same split, same grader, same command — not to rank agents. `benchmarks/bitext-support/`
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

The table is filled from the run made on the day of the v0.1 tag and is not changed afterwards; later runs go in
new rows with their Kit version.

| Date | Kit | Agent | Held-out pass rate | Held out / total | Set sha256 | Salt |
| --- | --- | --- | --- | --- | --- | --- |
| (run on tag day, 18 Oct 2026) | 0.1.0 | example agent (rule-based, no model) | — | — | — | bitext-support-v0.1 |

The example agent is a floor: eleven keyword rules written for the walkthrough, not for this data set. Its number
is published because it is reproducible by anyone in under a minute; a model-backed target through the same
command gives a number that depends on the model and the prompt, which is why the Kit records both.

## Reproducing

```
pip install "readiness-kit[benchmark]"
cd benchmarks/bitext-support && ./run.sh
```

If the sha256 printed by `prepare.py` differs from the table, the upstream data set has changed since the run;
say so when citing, and prefer the pinned revision of the data set if one is available to you.
