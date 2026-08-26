# Changelog

Every figure quoted below is read out of git rather than written down. The counts
come from `tools/compare_releases.py`, which reads `docs/metrics.json` from the
tagged commit and compares it against the working tree, so neither side is a copy
that can drift.

```bash
python tools/compare_releases.py --since v1.0.0
python tools/compare_releases.py --check CHANGELOG.md
```

This file follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the
versions follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.1.0]

Tooling and CI only. **146 figures held** and **0 figures moved**, which is
the claim this release is really making: what the repository finds did not change,
only how thoroughly it is checked.

### Added

- The composite action now runs in CI, three times, once per verdict. The
  `eval-set-cannot-resolve-this` case is the A/A scenario, where the true effect is
  exactly zero by construction, so the refusal is asserted on the one input where
  a pass would be provably wrong.
- `tools/compare_releases.py`, which reads `docs/metrics.json` out of a tag and
  reports what held, moved, was added and was removed since that release. It is
  how the counts in this file are produced, and `--check` verifies them against
  this document.

### Fixed

- The author check no longer fails on a commit made in the GitHub web editor. With
  email privacy on, GitHub authors such a commit as
  `<id>+<handle>@users.noreply.github.com`, and the allowlist held
  `noreply@github.com`, which that address does not contain: the real one is
  `users.noreply.github.com`, with a dot where the check expected an at sign. One
  README edit made in a browser turned four of five jobs red, which is a false
  positive, and a false positive is worse here than no test at all.
- The receipts check no longer requires the defense guide. It is an interview
  preparation document, so a public checkout may reasonably not carry it, and until
  now removing it returned exit 2 and took the whole job down. Checked documents are
  split into required and optional; the guide is optional, checked when present and
  skipped when not.

### Unchanged, and verified so

- Every published figure. `tools/compare_releases.py --since v1.0.0` reports
  146 held and 0 moved, and the comparison reads both sides out of git.
- Every experiment, corpus and threshold. No policy value moved.

## [1.0.0]

First release. 146 machine checked figures, 207 tests, 99.3 percent
line coverage, and a `make verify` target that reproduces every published figure
from a clean clone with no network access.

See the README for what this repository measures and the number that settles it,
and `docs/adr/` for the five decisions and the alternatives they rejected.
