# Contributing

Thank you for looking under the hood. The Kit is small and opinionated, so the fastest way to land a change is to talk first.

## Before you write code

- **Bugs.** Open an issue with the bug template: the exact command, the output and what you expected.
- **Attack cases, graders, adapters, trace formats.** Open an issue first so we agree on the shape. A pull request that arrives without an issue may be closed with a pointer to one.
- **Security problems.** Not in an issue. See [SECURITY.md](SECURITY.md).

## Setting up

```
git clone https://github.com/rainkernel/readiness-kit && cd readiness-kit
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
pytest -q                      # the suite runs in a few seconds, offline
ruff check src tests examples  # lint; `ruff format` formats
rk demo -q                     # the whole pipeline on the example agent
```

## Pull requests

1. Fork, branch from `main`, one change per pull request.
2. Keep the tests green and add one for what you changed. CI runs lint, the tests, the demo and the schema checks on 3.10–3.13.
3. Write the description for the reviewer: what changed, why, how it was tested.
4. A maintainer reviews within a few working days. Squash-merge is the default.

## What belongs here, and what does not

The Kit is the *frame*: the harness, the starter pack, the rubric, the BOM emitter, the cost baseline and the adapters. Changes that make those more correct, more portable or clearer are welcome. The *engine* (the full attack pack, the domain packs, the seed sets, the report generator, the CI gate) is the licensed Gate; please do not send pull requests that re-implement it here, and please do not send attack cases that need a model to judge the outcome (the starter pack stays deterministic so its results are reproducible by anyone).

## Licence and sign-off

By contributing you agree that your contribution is licensed under Apache-2.0 and that you have the right to submit it. Say so with a `Signed-off-by:` line on each commit (`git commit -s`), the [Developer Certificate of Origin](https://developercertificate.org). No separate contributor licence agreement is required.

## Style

Plain language in docs, messages and names; no marketing words. Code style is `ruff`; run it before you push.
