# ADR-003: Three verdicts, because two cannot say I do not know

Status: accepted

## Context

A CI gate conventionally has two outcomes. It passes or it fails, and the pass is
rendered as a green tick that a human reads as "no regression".

There is a third state, and it is the common one. At a 300 item eval set with this
much run to run noise the smallest regression detectable at the configured power is
0.0122. Teams routinely gate on smaller differences than that, and a two outcome
gate in that situation returns pass. The pass is true in the sense that nothing
blocked, and false in the sense a human reads it: there was no evidence either way.

## Decision

Three verdicts, and three exit codes.

    0  the candidate passes, and the delta was large enough for that to mean something
    1  a regression was detected, and the report names which gate caught it
    2  nothing blocked and the observed delta is smaller than this eval set can resolve

The third verdict carries the item count that would be needed, because a verdict
saying "I cannot tell" without saying what would help is a verdict nobody can act
on. Detecting the configured threshold needs 112 items paired, or 1608 comparing two
averages.

## The ordering, which is deliberate

A block beats an unresolvable delta. A gate that fired on evidence it had should not
be talked out of it by an arithmetic argument about power, so the undecidable verdict
applies only when nothing fired. That is exactly the case where a pass would be
mistaken for evidence.

The verdict is also symmetric about zero: an improvement too small to resolve is
undecidable rather than a pass. An unmeasurable gain is not a measured gain, and a
pipeline that ships on the strength of one is making the same mistake in the
comfortable direction.

## What it costs, measured

On A/A comparisons, where the true effect is exactly zero, this tool returns the
undecidable verdict 0.928 of the time the honest answer is exactly that. A two
outcome gate returns pass for all of those.

That is a large behavioural change and it is the point. It is also a real cost: a
team wiring this into CI will see exit code 2 far more often than they expected, and
the honest response is either a larger eval set or an explicit decision to treat 2
as a pass. Both are better than not knowing which case they are in.

## Alternatives considered

**Return pass and put a warning in the log.** Rejected because the exit code is what
the pipeline reads and the log is what nobody reads. A distinction that does not
reach the exit code does not exist.

**Return a failure for the unresolvable case.** Rejected as the wrong direction. It
would block every release where the change was small, which is most of them, and a
gate that blocks everything is removed within a week.

**Report a confidence interval on the delta and let the caller decide.** Adopted in
part: the interval is in the JSON output and the report. Rejected as the only
mechanism, because a gate exists to make a decision, and pushing the decision back
to a caller who has to write their own arithmetic is how the aggregate threshold
became the default in the first place.

## Consequences

The exit code contract has five values rather than three, and the README states all
five in a table, because an exit code nobody documented is an exit code somebody
will treat as a failure.

The undecidable verdict also depends on the noise parameters through the minimum
detectable effect, so it is only as good as the policy file. That is stated in the
README's section on what this repository cannot establish, and it is the reason the
future work names estimating the noise from a team's own repeated runs.
