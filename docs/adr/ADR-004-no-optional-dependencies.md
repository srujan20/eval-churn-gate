# ADR-004: No optional dependencies

Status: accepted

## Context

This repository is a statistics tool. The obvious dependencies are available and
good: statsmodels for the tests and the power arithmetic, pandas for the row
handling, a plotting library for the figures.

Its runtime needs numpy, scipy and a YAML parser. Nothing else, and there is no
optional extra beyond the development and evidence tooling.

## Decision

Keep it that way, and treat the absence as a claim the test suite checks.
`test_the_package_has_no_optional_dependencies_to_defer` asserts the extras are
exactly `dev` and `evidence`, so a future import of anything heavier fails a test
rather than passing unnoticed.

## Reasons, in order of how much they mattered

**The arithmetic is the subject.** `minimum_detectable_effect` is four lines: a
critical value, a power quantile, a standard error, a product. Importing it from a
library would mean the most quoted number in the repository comes from a function
nobody reading this can check. Written out, a reviewer can verify the formula
against a textbook in thirty seconds, and a test asserts that four times the items
halves the result, which is a check on the arithmetic rather than on the library.

**Reproducibility of published rates.** The rates here are re-measured in CI with
pinned versions. A statistical library that changes a default, a tie handling rule
or a random stream between minor versions makes a published rate a statement about
a version number. numpy and scipy are pinned in the receipts job for the same
reason and are small enough surfaces to be confident about.

**The Holm correction is nine lines and worth seeing.** The slice scan controls a
family wise error rate, and the specific thing that makes it correct is stopping at
the first p value that fails its threshold rather than continuing down the list. That
is the kind of detail that is easy to get wrong when hidden behind a keyword
argument, and there is a test asserting the stop happens.

**Install friction is real.** A gate is something a team drops into CI. A dependency
tree that pulls in a compiler or a hundred megabytes of wheels is a reason not to try
it.

## Alternatives considered

**statsmodels for the tests and the power analysis.** Its power module is better than
what is here: it handles more designs and more corrections. Rejected for the first
two reasons above. If this were a production tool rather than a repository whose
purpose is to show the reasoning, the trade would go the other way, and that sentence
is the honest version of this decision.

**pandas for the rows.** Rejected as unnecessary weight. The row type is a frozen
dataclass with a serialiser, the reductions are list comprehensions, and the whole
sweep of 5000 gated comparisons finishes in about a minute.

**A plotting library for the figures.** Rejected because the figures are HTML with
inline SVG and CSS, which is one self contained file with no template directory and
no font resolution to go wrong in CI. The bar chart in the report is a div with a
percentage width.

## Consequences

Some code here reimplements what a library does, and the README says which: the
Wilson interval, the Holm step down, the power formulas. That is a maintenance cost
and it is bounded, because each is under twenty lines and each has tests that pin its
behaviour against a hand computed case rather than against another implementation.

The one thing genuinely given up is breadth. There is no unequal variance test, no
non parametric alternative to the paired t beyond the bootstrap, and no correction
other than Holm. A user needing those should reach for statsmodels, and this document
is where they will find out that is the right call.
