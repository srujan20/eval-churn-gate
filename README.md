# eval-churn-gate

**An aggregate score delta is a function of two numbers, and two numbers cannot distinguish "nothing changed" from "half the items got better and half got worse by the same amount". This gates on the per item transitions as well as the aggregate, and publishes its own false block rate against comparisons whose true effect is exactly zero.**

[![CI](https://github.com/srujan20/eval-churn-gate/actions/workflows/ci.yml/badge.svg)](https://github.com/srujan20/eval-churn-gate/actions/workflows/ci.yml)
[![tests](https://img.shields.io/badge/tests-206-brightgreen)](tests)
[![coverage](https://img.shields.io/badge/coverage-99.3%25-brightgreen)](tools/collect_metrics.py)
[![python](https://img.shields.io/badge/python-3.11%20%7C%203.12%20%7C%203.13-blue)](pyproject.toml)
[![license](https://img.shields.io/badge/license-MIT-green)](LICENSE)

## The question a CI gate on an aggregate structurally cannot answer

A regression gate compares two numbers and blocks if the difference is bad
enough. The number of items whose outcome changed is a function of the *sum* of
the two transition counts; the difference of means is a function of their
*difference*. So four questions are not merely hard for such a gate, they are
outside what it is a function of:

1. Did the same items get better, or did a different set get better and worse in
   equal measure?
2. When this gate says pass, is that evidence of no regression or the absence of
   evidence either way?
3. What is this gate's own false block rate, on a release where nothing changed?
4. How small a regression can this eval set detect at all?

## The numbers, including the ones that are not flattering

The anchor is an A/A comparison: the same version scored twice. The true effect is
zero by construction, not by measurement, so every block is a false block and
every point of churn is noise.

**Over 1000 comparisons whose true effect is exactly zero, run to run variation
alone flips 0.1167 of items across the pass boundary**, with a ninety fifth
percentile of 0.1467. And 0.8889 of that movement is cancelled by the net, so a
pass rate reports approximately nothing while one item in nine changed side.

The gate that almost every pipeline ships is a threshold on the aggregate. Across
the three regression scenarios here it **catches 0.323 of** them, and it sees
neither of the two whose aggregate is about zero. On a slice collapse it sees it 0.0 of the time. Worse, at a true drop of exactly the size the threshold was set
to catch, it catches it 0.455 of the time it happens, against 0.99 for the paired
interval on the same data. A gate set at the size of the thing it is meant to
catch is a coin flip on that thing.

The combined gate here **catches 1.0, at a false block rate of 0.037**, and that
cost is stated rather than hidden: the paired interval alone blocks 0.039 of clean
releases, and the extra conditions are what buy the two scenarios it misses
entirely.

The most uncomfortable number is about the verdict. On A/A comparisons this tool
returns "the eval set cannot resolve a difference this small" 0.928 of the time the
honest answer is exactly that. It blocked 0.069 of them and passed only 0.003. A
gate with two outcomes returns pass for all of them, and pass is read as evidence.

Every figure below is produced by code in this repository, re-measured by CI on
every push, and guarded against the prose by phrase matching rather than digit
matching. 206 tests, 99.3 percent line coverage, over 5000 gated comparisons.

## Quickstart

Prerequisites: Python 3.11, 3.12 or 3.13. No API keys, no model weights, no
network at runtime, and no optional dependencies at all.

```bash
git clone https://github.com/srujan20/eval-churn-gate.git
cd eval-churn-gate
pip install -e ".[dev]"

# What your eval set can resolve, before running any comparison.
python -m churngate power

# The headline: a slice collapses, the aggregate does not move. Exit code 1.
python -m churngate gate --scenario compensating

# Every gate graded on every scenario, with an interval on every rate.
python -m churngate sweep --html report.html

# Re-measure every published number and check it against the documents.
make verify
```

## Claim 1: three of five gates cannot see a regression that keeps the mean

The compensating scenario drops one slice of the eval set and lifts the others just
enough to pay for it. **A slice loses 0.1173 while the aggregate moves by 0.0006
in the median case.**

| Gate | Sees the collapsed slice | Sees pure churn | False blocks on A/A |
| --- | --- | --- | --- |
| mean_threshold | 0.0 | 0.0 | 0.0 |
| paired_t | 0.022 | 0.0 | 0.04 |
| paired_bootstrap | 0.022 | 0.0 | 0.039 |
| churn | 0.135 | 1.0 | 0.003 |
| slice_scan | 1.0 | 0.028 | 0.039 |
| combined | 1.0 | 1.0 | 0.067 |

The three aggregate gates fire on the collapsed slice at or below their own false
block rate on A/A, which means they are not detecting anything. They are firing at
their own noise rate. The slice scan catches it 1.0 of the time, and the reason is
not cleverness: it tests a partition rather than a total.

The churn gate is the interesting failure. It counts crossings rather than
differencing them, so in principle it sees compensating movement, and it does catch
pure churn. On a slice losing a tenth of a point it manages 0.135, because too few
items cross the pass boundary to clear the noise floor its own threshold has to sit
above. Two blind spots, two gates, both measured.

Reproduce with `python experiments/exp02_the_regression_the_aggregate_cannot_see.py`.

## Claim 2: the aggregate carries no information about the churn

The strongest form of the claim, as a number rather than an argument. Across 2133
comparisons whose delta is within five thousandths of zero, the share of items that
changed side runs **from 0.0667 to 0.5933 of items**, and a rank correlation of 0.001 in magnitude
between the delta and the churn comes with a p value of 0.963.

Restricted to the 2000 comparisons whose true aggregate effect is exactly zero, the
correlation there is 0.0027 in magnitude.

No function of the aggregate, monotone or otherwise, can bound the churn. A
dashboard showing the delta reports the same number at both ends of that range.

Reproduce with
`python experiments/exp04_the_aggregate_carries_no_churn_information.py`.

## Claim 3: pairing is worth a factor of four and costs nothing

Both runs are scored on the same items, so the item to item spread cancels exactly
when the comparison is made item by item and not at all when two averages are
compared.

| Items | Paired | Two averages |
| --- | --- | --- |
| 100 | 0.0211 | 0.0802 |
| 300 | 0.0122 | 0.0463 |
| 1000 | 0.0067 | 0.0254 |
| 3000 | 0.0039 | 0.0146 |
| 10000 | 0.0021 | 0.008 |

At the shipped 300 item eval set the smallest detectable regression is 0.0122 paired,
against 0.0463 when two averages are compared. That is a factor of 3.8 on
the same data, and it costs nothing but keeping the per item scores, which most
pipelines already have and then average away before writing them down.

Detecting the configured threshold needs 112 items paired, or 1608 comparing two
averages.

## Claim 4: a threshold set at the regression size is a coin flip on it

| True drop | Mean threshold | Paired bootstrap |
| --- | --- | --- |
| 0.000 | 0.0 | 0.055 |
| 0.005 | 0.0 | 0.28 |
| 0.010 | 0.018 | 0.617 |
| 0.020 | 0.455 | 0.99 |
| 0.030 | 0.973 | 1.0 |
| 0.050 | 1.0 | 1.0 |
| 0.080 | 1.0 | 1.0 |

The observed value lands either side of the threshold with roughly equal
probability when the true effect equals the threshold, so a gate set there catches
about half of what it was built for. Reading down the first column also shows a
gate that is nearly blind below its threshold and nearly certain above it, which is
not how a regression arrives.

Reproduce with `python experiments/exp03_what_the_eval_set_can_resolve.py`.

## Claim 5: the churn gate's threshold has to be measured, not chosen

The A/A floor is the rate at which run to run noise alone moves items across the
pass boundary. Its median is 0.1167 with a ninety fifth percentile of 0.1467.

The first value was 0.06, written from intuition
before anything was measured. That is roughly half the floor, so the gate blocked
every comparison whose true effect was exactly zero. The shipped value is now a
limit of 0.17, above the measured ninety fifth percentile, and the policy file says
in a comment that it has to be recalibrated if the noise parameters change.

Two arithmetic checks that the model is doing what it claims: the observed standard
deviation of 0.0046 for the aggregate delta against the predicted 0.0049 from the
noise parameters alone.

## Claim 6: which gate to ship depends on which mistake costs more

| Gate | Catches a real regression | Blocks a clean release |
| --- | --- | --- |
| mean_threshold | 0.323 | 0.0 |
| paired_t | 0.341 | 0.02 |
| paired_bootstrap | 0.341 | 0.019 |
| churn | 0.384 | 0.005 |
| slice_scan | 0.674 | 0.019 |
| combined | 1.0 | 0.037 |

If shipping a regression is the expensive mistake, the combined gate is the answer.
If blocking a good release is, the churn gate catches 0.384 overall while blocking
only 0.005. The mean threshold gate blocked nothing at all across the clean
scenarios, which supports a claim of below 0.05 percent and nothing stronger over
2000 clean releases, and it is still the wrong choice because of what it misses.

This repository does not know which mistake costs more in anybody's pipeline, so
claim 6 ends in a table rather than in a recommendation.

Reproduce with `python experiments/exp05_what_the_combined_gate_costs.py`.

## Claim 7: an interval on every rate, because one number nearly became a finding

An early run of this suite measured the false block rate of the paired t test at
0.084 on comparisons whose true effect is exactly zero, which reads as a test
running at nearly twice its nominal level. At three thousand replications the same
measurement came out at 0.055. The first number was not a finding, it was two
hundred and fifty replications.

Every rate in this repository is now a `Rate` carrying a Wilson interval, and there
is an explicit method for asking whether an interval excludes a value. Claims of the
form "this gate runs hot" are made only when the interval excludes the nominal
level, and exp01 prints that column so a reader can see which claims are supported.

## The bugs the measurement found

**A churn threshold below its own noise floor.** The flip rate limit was written
from intuition at 0.06 and the measured A/A floor is about twice that, so the gate
blocked every comparison whose true effect was exactly zero. The policy loader now
refuses a limit far below what the configured run noise produces on its own, with
that reason in the message.

**A scenario broken by its own construction.** The churn_only scenario is supposed
to have no aggregate change at all. The first version shifted each score across the
pass boundary and re-centred the mean, and clipping to the metric's range then moved
the mean again, so the scenario showed an observed delta of about three hundredths.
It is now a permutation of each item's distance from the boundary, which keeps the
aggregate identical to the last bit because the candidate's scores are the
baseline's own values in a different order.

**A guard written as a comparison with zero.** The check for a set of deltas with no
variation tested for exactly zero variance. Deltas that are all identical come out
near 1e-18 instead, so the guard never fired and scipy raised a precision loss
warning from inside the t test that the suite treated as an error. There is no
sampling question when every item moved by the same amount: the sign is the answer,
and the tolerance now says so.

**A determinism test that was right for the wrong reason.** Two rates are undefined
rather than zero when nothing failed, and both came out as a nan, which compares
unequal to itself. The test failed on two sweeps identical in every other column. A
row that cannot be compared to itself is a row no downstream check can trust, so the
row type serialises a non finite float as null.

## Architecture

<img src="docs/diagrams/architecture.svg" alt="What the aggregate is a function of, what the transitions are a function of, and which gate reads which" width="1000">

The dividing line is what each gate is a function of. Everything on the left reads
two numbers; everything on the right reads the per item detail that the two numbers
were computed from.

## Evidence

![One gated comparison](docs/screenshots/gate-compensating.png)

One gated comparison on the compensating scenario, screenshotted from the HTML
report the tool produces. The framing is driven by named headings rather than pixel
offsets, and the capture script fails the run if the verdict badge is invisible or
falls below a contrast ratio of 4.5, because a screenshot tool is the only thing in
the pipeline that can see pixels.

![The four transition cells](docs/screenshots/gate-transitions.png)

The four cells the aggregate is computed from. The difference between the first two
is the delta; their sum is the number of people affected.

![The truth the gates cannot see](docs/screenshots/gate-truth.png)

The truth column, with the exact ones marked. Two of the five scenarios have a true
effect that is a construction rather than an estimate, and the report says which.

![Every gate on every scenario](docs/screenshots/sweep-grid.png)

Every gate against every scenario, with a Wilson interval on every rate. The top row
is the one whose true effect is exactly zero.
[docs/screenshots/manifest.json](docs/screenshots/manifest.json) records which
report each image came from and the measured contrast of the badge in it.

![A replay of the captured session](docs/video/demo.gif)

A replay, not a screen recording. Every line of terminal text is captured stdout
from a command that actually ran, and each segment is paced by that command's
measured wall time. [docs/video/manifest.json](docs/video/manifest.json) lists every
command with its exit code and duration, and the MP4 is at
[docs/video/demo.mp4](docs/video/demo.mp4).

## The scenarios, and specifically the awkward ones

| Scenario | True aggregate effect | Why it is here |
| --- | --- | --- |
| `aa` | exactly zero, by construction | the anchor. Every block is a false block |
| `uniform` | a real drop, attenuated by the metric's bound | the case every gate should catch |
| `compensating` | about zero, with one slice collapsed | the case three of five gates cannot see |
| `churn_only` | exactly zero, by construction | the aggregate is identical and half the items move |
| `improvement` | a real gain | so a gate can be caught blocking one |

Two of the five have a true effect that is exact rather than estimated, and the row
type records which, because averaging an exact quantity together with an estimated
one and reporting the result as one kind of number is a mistake that does not
announce itself.

The compensating scenario's losing group is a *slice*, not a random subset. A
compensating regression whose losing group corresponds to no observable attribute is
undetectable by anything, which would be an honest finding and a useless one.

## What this repository cannot establish

Its own section, because it is the part a senior reviewer reads first.

**The scores are generated.** Two scenarios have an exact true effect, and that
exactness is a property of the construction rather than of any dataset. The rates
here are properties of these noise parameters: a run to run standard deviation of
0.06 and an item to item spread of 0.22. What transfers is the method and the
arithmetic, and the tool reads a policy file precisely so a team can put their own
measured noise in it.

**The noise model has two components and reality has more.** A real eval has run
level effects that shift every item together, which pairing cannot remove and more
items cannot shrink. This model has no such term, so the minimum detectable effects
here are the optimistic case.

**The slice scan needs slices.** A regression confined to an unobservable subgroup
is invisible to every gate in this repository, and no amount of statistics recovers
it. The scan works because the corpus attaches the losing group to a label a
pipeline would actually have.

**The gates are graded on detection and false blocks, not on cost.** Claim 6 ends in
a table because the exchange rate between missing a regression and blocking a good
release is a property of a team, not of a method.

**Nothing here is about answer quality.** Containment of a regression in the score
is not the same as harm to a user. That is the Pivot.

## Layout, exit codes and reproduction

```
src/churngate/
  runs.py      five scenarios, two with an exact true effect
  churn.py     the four transition cells, and the net against gross split
  gates.py     five gates, the power arithmetic, and the churn floor
  rates.py     a rate that cannot be quoted without its interval
  audit.py     three verdicts and the exit codes they carry
  pipeline.py  the sweep, and the row type every experiment reduces
  report.py    text and HTML reports, transitions before the aggregate
  cli.py       the commands and the exit codes
configs/policy.yaml every threshold, with a comment on who picks it
experiments/       five experiments writing JSON to docs/experiments/
tools/             receipts, diagram, screenshots, demo recorder, PDF
docs/adr/          five decisions with their rejected alternatives
```

| Exit code | Meaning |
| --- | --- |
| 0 | the candidate passes, and the delta was large enough for that to mean something |
| 1 | a regression was detected, and the report names which gate caught it |
| 2 | nothing blocked and the delta is smaller than this eval set can resolve |
| 3 | the gate could not run: no items, two runs on different items, a score out of range |
| 4 | the invocation was wrong: an unknown scenario or gate, or a policy that will not load |

The separation between 0 and 2 is the whole point. A gate that returns the same code
for "the candidate passes" and "I could not tell" is a gate whose green tick means
nothing, and that is the most common way a regression reaches production with a pass
beside it.

```bash
make lint        # ruff check and format check
make test        # pytest with coverage
make experiments # re-run all five, writing docs/experiments/*.json
make receipts    # re-measure every figure, then check it against the documents
make verify      # lint, test, receipts
make evidence    # diagram, screenshots, demo and the README image check
make pdf         # lay out the defense guide for offline reading
```

`tools/check_numbers.py` matches anchor phrases rather than digits, because a digit
search passes while the sentence around the digits has gone stale. It collapses
whitespace first, so an anchor does not have to be lucky about where a markdown line
broke, and `tools/collect_metrics.py` refuses an anchor with no placeholder in it,
because such an anchor matches whatever the document says. CI runs the checker with
`--strict`, which makes the reverse direction load bearing: the forward check catches
a deleted figure and the reverse check catches an altered one.

The tables in claims 1, 3, 4 and 6 are guarded cell by cell, which is a weaker claim
than the prose anchors: a cell is checked for its value appearing as a table cell,
not for appearing in its own row. Guarding the row label too would mean generating
the README rather than writing it.

## Tech stack

| Technology | Role here | Why this one |
| --- | --- | --- |
| numpy | the score matrices and the bootstrap resampling | the bootstrap is one matrix index, which is why a thousand replications finish in a minute |
| scipy.stats | the t test, the normal quantiles, Spearman | the power arithmetic is written out rather than imported, and the quantiles come from here |
| PyYAML | the policy file | thresholds are the subject of this repository, so they cannot live in code |
| pytest, coverage | 206 tests, measured | the A/A anchor is a test as well as an experiment |
| ruff | lint and format | one tool, one config, no argument about style in review |
| GitHub Actions | three Pythons, then a pinned receipts job | the published numbers are re-measured on every push |
| Playwright, ffmpeg | screenshots and the replay video | the only way to check a badge is legible is to look at pixels |

No optional runtime dependencies at all, which ADR-004 explains was a constraint
rather than an accident.

## Decisions

- [ADR-001: Gate on transitions, not only on the aggregate](docs/adr/ADR-001-gate-on-transitions-not-only-on-the-aggregate.md)
- [ADR-002: The A/A comparison is the anchor](docs/adr/ADR-002-the-aa-comparison-is-the-anchor.md)
- [ADR-003: Three verdicts, because two cannot say I do not know](docs/adr/ADR-003-three-verdicts-because-two-cannot-say-i-do-not-know.md)
- [ADR-004: No optional dependencies](docs/adr/ADR-004-no-optional-dependencies.md)
- [ADR-005: Every rate carries an interval](docs/adr/ADR-005-every-rate-carries-an-interval.md)

## The Pivot, and future work

**Deliberately out of scope: more than two versions, and automated rollback.** No
multi-arm comparison and no action beyond an exit code. The trigger condition is a
third version in flight, at which point every threshold here needs a multiplicity
correction and the arithmetic would have to be redone rather than extended.

Where a second version would go, in order:

- Read a real eval log rather than generating one, since the per item scores are
  already there in most pipelines. First metric to watch: the share of real eval
  logs that still carry per item scores, because a pipeline that averaged them away
  cannot be helped at all.
- Add a run level noise term, which pairing cannot remove and more items cannot
  shrink, since that is the one place these minimum detectable effects are
  optimistic.
- Estimate the noise parameters from a team's own repeated runs instead of taking
  them from a policy file, which turns the power arithmetic from illustrative into
  theirs.
- Report the churn by slice as well as in aggregate, since a flip rate that is flat
  overall and concentrated in one slice is the same shape of problem one level down.
