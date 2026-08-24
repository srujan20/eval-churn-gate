# ADR-001: Gate on transitions, not only on the aggregate

Status: accepted

## Context

A regression gate is asked one question: is the candidate worse than the baseline?
The answer almost every pipeline computes is the difference between two mean
scores, compared against a threshold.

That difference is a function of two numbers, and there is a quantity a release
manager cares about that it cannot be a function of. When items cross a pass
boundary, the change in the pass rate is the *difference* between the crossings in
each direction, and the number of users who see a different outcome is their *sum*.
A release where nothing moved and a release where six percent of items broke while
six percent were fixed produce the same difference of means, the same pass rate,
and the same dashboard.

## Decision

The gate reads the per item transitions as well as the aggregate. `churn.py`
computes four cells rather than one number, and both reports print the transitions
before the aggregate, because the aggregate is a summary of them rather than a
separate fact.

Five gates are implemented and graded against each other on the same comparisons,
so the claim is a measurement rather than a preference.

## The evidence, and it is stronger than the argument

The argument above is structural. exp04 turns it into a number. Across 2133
comparisons whose delta is within five thousandths of zero, the share of items
that changed side runs from 0.0667 to 0.5933 of items, and a rank correlation of 0.001 in magnitude
between the delta and the churn comes with a p value of 0.963. Restricted
to comparisons whose true aggregate effect is exactly zero, the correlation there is
0.0027 in magnitude.

That is the impossibility with a coefficient attached: no function of the
aggregate, monotone or otherwise, can bound the churn.

## Alternatives considered

**Tighten the aggregate threshold instead.** Rejected because it does not address
the case. A compensating regression has an aggregate near zero, so no threshold on
the aggregate catches it at any tightness that does not block everything.

**Use a paired test on the aggregate, which is more powerful.** Adopted, and it is
not enough. Pairing is worth a factor of 3.8 on the same data, which is a large win
on the cases the aggregate can represent, and exp02 shows the paired gates firing
on a collapsed slice at 0.022 against their own false block rate of about 0.04.
They are not detecting it, they are firing at their own noise rate.

**Gate on the pass rate rather than the mean score.** Rejected for the same reason
and it is worth stating because it feels like an improvement. The pass rate is the
net of the transitions, so it is exactly the quantity that cancels compensating
movement. On A/A comparisons here 0.8889 of that movement is cancelled by the net.

**Report the transitions in a dashboard and leave the gate on the aggregate.**
This is the common compromise and it is where the design started. Rejected because
a number nobody gates on is a number nobody reads.

## Consequences

The gate needs per item scores, which is a real requirement. Most pipelines have
them and then average them away before writing anything down, and the README's
future work names the share of real eval logs that still carry them as the first
thing a second version should measure.

Reading the transitions also introduces a threshold that has to be calibrated
against noise rather than chosen, which ADR-002 covers, and it introduces a false
block cost that ADR-005 insists is published with an interval.
