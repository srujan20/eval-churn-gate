# ADR-002: The A/A comparison is the anchor

Status: accepted

## Context

Every gate in this repository makes a claim about its own accuracy, and an
accuracy claim needs a truth. Four of the five scenarios have a true effect that
is computed per replication and therefore estimated. One does not.

An A/A comparison is the same version scored twice. The noiseless scores are
identical, so the true effect is zero by construction, not by measurement, at
every seed and every eval set size. Every block a gate issues on it is a false
block, and every point of churn it observes is noise.

## Decision

The A/A scenario is the reference for three quantities that no gate normally
publishes about itself.

**Its own false block rate.** exp01 measures it for all five gates over 1000
comparisons whose true effect is exactly zero, and reports whether the interval
excludes the nominal significance level rather than eyeballing the point estimate.

**The churn floor.** Run to run variation alone flips 0.1167 of items across the
pass boundary, with a ninety fifth percentile of 0.1467. That is the number a churn
threshold has to sit above, and it is not guessable.

**The share of comparisons that cannot be resolved.** On A/A the tool answers "the
eval set cannot resolve a difference this small" 0.928 of the time the honest answer
is exactly that, blocked 0.069 of them, and passed only 0.003.

A second scenario, `churn_only`, also has an exact true effect, and getting that
right took two attempts. See ADR-005's neighbours in the README war story section:
the first construction shifted scores across the boundary and re-centred the mean,
and clipping to the metric's range moved the mean again, so a scenario defined by
having no aggregate change showed a delta of about three hundredths. It is now a
permutation of each item's distance from the boundary, which keeps the aggregate
identical to the last bit because the candidate's scores are the baseline's own
values reordered.

## What the anchor caught

The churn threshold. The first flip rate limit in the policy file was 0.06, written
from intuition before anything was measured, which is roughly half the floor. It
blocked every A/A comparison. The shipped value is a limit of 0.17, above the
measured ninety fifth percentile, and the policy loader now refuses a limit far
below what the configured run noise produces on its own, with that reason in the
message.

The anchor also validates the model rather than only the gates. The observed
standard deviation of 0.0046 for the aggregate delta sits against the predicted
0.0049 from the noise parameters alone, which is the check that the arithmetic in
`gates.minimum_detectable_effect` describes the thing being simulated.

## Alternatives considered

**Grade the gates against the four scenarios with estimated truths only.**
Rejected because the accuracy claims that matter most are about the null case, and
an estimated null is a worse null. A false block rate measured against an
approximately zero effect is contaminated by whatever the approximation was.

**Use a real pair of production runs as the reference.** Rejected because a real
A/A pair is only A/A if nothing else changed, which is exactly the thing nobody can
verify. The generated version is the only one where the claim is a construction.

**Calibrate the churn threshold analytically instead of measuring it.** It is
tempting: the crossing probability for an item at distance d from the boundary has a
closed form under this noise model. Rejected because the closed form depends on the
noise model being right, and the whole point of the anchor is to need as few
assumptions as possible. The measured floor holds for whatever the noise actually is.

## Consequences

Two of five scenarios carry an exact truth and three do not, so the row type records
which, and reductions have to respect the distinction. Averaging an exact quantity
together with an estimated one and reporting the result as one kind of number is a
mistake that does not announce itself.

The A/A floor is also a maintenance obligation. It is a function of the noise
parameters, so the flip limit is only correct for the configuration it was measured
under, and the policy file says so where the value is set rather than in a document
nobody opens.
