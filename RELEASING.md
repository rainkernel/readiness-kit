# Releasing

How a version of the Readiness Kit goes out. The principle on the README applies here first: a release exists
when its tag exists, and nothing is announced before that. Every box is ticked by a person; the workflow checks
the ones it can.

## The week before

- [ ] `main` is green on every CI job: tests on Linux, Windows and macOS, the build job, the dependency audit.
- [ ] The version is the same in three places: `pyproject.toml`, `src/readiness_kit/__init__.py` and the
      `## [x.y.z] - YYYY-MM-DD` heading in `CHANGELOG.md`. The release workflow refuses a tag that disagrees.
- [ ] `CHANGELOG.md` says what changed, in plain language. Nothing under `[Unreleased]` that belongs in the version.
- [ ] Docs read as the release: README, docs/WALKTHROUGH.md, docs/FORMATS.md, docs/ADAPTERS.md, docs/BENCHMARK.md
      and the example README state the numbers `rk demo` prints today (held-out pass rate, findings, components,
      cost ratio, score).
- [ ] `benchmarks/bitext-support/run.sh` has been run on tag day and its held-out pass rate, counts and set
      sha256 match the current row in docs/BENCHMARK.md. If the sha256 differs, the upstream data set changed:
      add a new row with the new figures and say so under the table; do not edit the old row.
- [ ] Someone who did not write the Kit has done docs/WALKTHROUGH.md on a fresh machine and every point where
      they hesitated has been fixed or written down as an issue.
- [ ] A fresh checkout passes `pip install -e ".[dev]" && pytest -q && ruff check src tests examples`.
- [ ] The repository is clean of anything that should not be public. This grep for credential shapes prints
      nothing, and `tests/fixtures/` contains no real server names or hostnames:

      ```
      git grep -n -I -E "AKIA[0-9A-Z]{16}|ghp_[A-Za-z0-9]{30,}|sk-[A-Za-z0-9]{32,}|-----BEGIN|(api[_-]?key|secret|password)\s*[:=]\s*['\"][A-Za-z0-9]{8,}"
      ```
- [ ] GitHub: the `pypi` environment exists under Settings → Environments; PyPI: the trusted publisher for
      this repository and `release.yml` is registered (pending for the first release).

## Tag day

1. Confirm `git status` is clean on `main` and `git log -1` is the commit you mean.
2. Tag and push the tag:

   ```
   git tag -s v0.1.0 -m "Readiness Kit v0.1.0"      # -a if you do not sign tags
   git push origin v0.1.0
   ```

3. Watch Actions → release. The jobs run in this order: version check, build and twine check, publish to PyPI
   through the trusted publisher, GitHub release with the artefacts and the changelog section, then an install
   of the published version on Linux, Windows and macOS with `rk demo`.
4. On a machine that has never seen the repository:

   ```
   python -m venv rk-check && . rk-check/bin/activate     # Windows: rk-check\Scripts\activate
   pip install readiness-kit==0.1.0
   rk version
   rk demo
   ```

5. Only now: the website release that references the version, the Lab entry, and the announcements.

## If something fails after the tag

- A failed job before `publish`: fix on `main`, delete the tag locally and remotely (`git tag -d v0.1.0`,
  `git push origin :refs/tags/v0.1.0`), retag the fixed commit. Nothing reached PyPI, so the version number
  can be reused.
- A failure after `publish`: the version is on PyPI and cannot be replaced. Fix on `main`, bump the patch
  version (0.1.1), add a changelog entry that says what was wrong, tag again. Do not delete the PyPI release
  unless it is unusable or unsafe; yank it instead, with the reason.

## Versioning

SemVer. 0.x releases may change interfaces between minor versions; the changelog says so when they do. A
file-format change bumps the minor version and the `kind` field of the artefacts says which version wrote them.
