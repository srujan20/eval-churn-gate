# ADR-005: Every rate carries an interval

Status: accepted

## Context

An early run of this suite measured the false block rate of the paired t test at
0.084 on comparisons whose true effect is exactly zero. The nominal level is 0.05.
A test running at nearly twice its stated level is a real finding, and it would have
been the most interesting number in the repository.

At three thousand replications the same measurement came out at 0.055. The first
number was not a finding. It was two hundred and fifty replications, and a rate near
0.05 over 250 draws has a standard error of about 0.014, so 0.084 is under two and a
half standard errors from nominal. It looked like a discovery for about an hour.

## Decision

Three rules, two of them enforced by the type system rather than left to the caller.

**A rate is a type, not a float.** `rates.Rate` holds a numerator and a denominator
and exposes the value, a Wilson interval, the resolution floor and
`samples_needed_for`. Every rate in every report and every experiment is constructed
through it, so the denominator cannot be lost on the way to the page. Its `render`
method emits the value with its interval, so quoting a rate without one requires
deliberately reaching past the method that exists.

**A claim about a rate being different from something needs the interval to say so.**
`Rate.excludes` is the method that check goes through, and exp01 prints a column
saying, for each gate, whether its measured false block rate is distinguishable from
the nominal significance level at ninety five percent confidence. Three of the six
are; three are not, and the ones that are not are reported as not.

**A non finite rate serialises as null.** Two quantities here are undefined rather
than zero when nothing failed. Both came out as a nan, which `json.dumps` writes as
the bare token NaN, which Python reads back and nothing else does. It also compares
unequal to itself, which made the determinism test fail on two sweeps that were
identical in every other column. The test was right: a row that cannot be compared to
itself is a row no downstream check can trust.

## Why Wilson rather than the normal approximation

The rates here live near zero, and the normal approximation is worst exactly there.
It produces a lower bound below zero, and for a measured zero it produces an interval
of zero width, which would report a measured zero as certainty. The Wilson interval
pulls its centre toward one half by an amount that grows as the sample shrinks, so a
zero over 2000 clean releases comes back as an interval with an upper bound, which is
the truthful statement.

The measured zero itself is reported with the floor its sample supports. The mean
threshold gate blocked no clean release at all, which supports below 0.05 percent and
nothing stronger, and exp05 prints how many replications a stronger claim would need.

## Alternatives considered

**Report point estimates and put the replication count in the caption.** Rejected.
The point estimate is what gets quoted and the caption is what gets skimmed. The
0.084 above had its replication count in the same terminal output and it did not
help.

**Raise the replication count until the intervals are narrow enough to ignore.**
Rejected as the wrong lesson, and it is the tempting one because it works. The
interval is not a workaround for too few replications, it is the honest form of the
number. A wider sample would have made 0.084 into 0.055 and would not have made the
next borderline number safe.

**Bootstrap intervals on every rate rather than Wilson.** Rejected as unnecessary
machinery for a binomial proportion, where the closed form is exact enough and can be
checked by hand.

## Consequences

Every table in this repository is wider, and every rate takes three numbers to read
instead of one. That is the cost and it is small.

The rule also changed what the repository is willing to claim. There is no statement
of the form "this gate runs hot" that is not backed by an interval excluding the
nominal level, and there is one measured zero reported as "below 0.05 percent over
2000 clean releases" rather than as zero. Both are less impressive than the versions
that were nearly written.
