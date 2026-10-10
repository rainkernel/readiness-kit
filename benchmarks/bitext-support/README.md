# Benchmark: support-ticket triage on the Bitext data set

The Kit's published benchmark for v0.1: a classification task on a public customer-support data set, run
through the harness with a held-out split, so that the harness, the split and the number can be checked by
anyone with the same command.

| | |
| --- | --- |
| Data set | [bitext/Bitext-customer-support-llm-chatbot-training-dataset](https://huggingface.co/datasets/bitext/Bitext-customer-support-llm-chatbot-training-dataset) — 26,872 customer utterances labelled with a category and an intent; licence CDLA-Sharing-1.0, © Bitext Innovations. Downloaded at run time, not redistributed. |
| Task | Given the utterance, output the category (`category: …`). Graded with the Kit's `label` grader. |
| Sample | 550 utterances, stratified by category, deterministic for seed 20261018 (`prepare.py`); sha256 printed and recorded in the run. |
| Split | Held-out fraction 0.33, salt `bitext-support-v0.1`; the headline number is the held-out pass rate. |
| Command | `./run.sh` (below) |
| Agent | The bundled example agent (rule-based, no model) — a floor, not a claim. Replace `target` in `rk.yaml` to benchmark yours. |

## Run it

```
pip install "readiness-kit[benchmark]"
./run.sh
```

`run.sh` rebuilds the set, makes the split, runs `rk eval` and prints the held-out pass rate; `runs/eval.json`
carries the set's sha256, the split's salt and the Kit version, which is what a published number must cite.

## Results

Recorded on the day of the v0.1 tag (see docs/BENCHMARK.md for the table and the Kit version used). A result is
cited as: *held-out pass rate, cases held out, set sha256, split salt, Kit version, agent*.

## Why a rule-based agent

The point of v0.1's benchmark is the harness, not the agent: that a set can be built deterministically, split
without leakage, run and graded without a model in the loop, and the number reproduced by someone else. A model-
backed target (`openai-chat` in rk.yaml) runs through exactly the same path; its number depends on the model
and the prompt, which is why the Kit records both in the run.
