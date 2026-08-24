"""One comparison gated, and the verdict that follows.

Three verdicts, and the third is the reason the module exists.

A gate that returns pass and block only is a gate that cannot say "your eval set
cannot resolve a difference this small". That case is not rare: at three hundred
items and this much run to run noise, the smallest regression a paired test can
detect at eighty percent power is larger than the drop most teams gate on. A gate
in that situation returns pass, and pass reads as "no regression" when it means
"no evidence either way".

So the verdict is UNDECIDABLE when nothing blocked and the observed delta sits
inside the band the eval set cannot resolve. It carries the item count that would
be needed, because a verdict that says "I cannot tell" without saying what would
help is a verdict nobody can act on.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .churn import Transitions, transitions
from .config import Policy
from .gates import (
    Decision,
    items_needed_for,
    minimum_detectable_effect,
    run_all,
)
from .runs import Comparison


class Verdict(str, Enum):
    PASS = "candidate-passes"
    BLOCK = "regression-detected"
    UNDECIDABLE = "eval-set-cannot-resolve-this"


EXIT_CODES = {
    Verdict.PASS: 0,
    Verdict.BLOCK: 1,
    Verdict.UNDECIDABLE: 2,
}


@dataclass(frozen=True)
class AuditResult:
    """Everything one gated comparison produced, with the truth kept separate."""

    scenario: str
    items: int
    observed_delta: float
    decisions: dict[str, Decision]
    transitions: Transitions
    verdict: Verdict
    blocking_gate: str | None
    minimum_detectable: float
    minimum_detectable_unpaired: float
    items_needed: int
    true_effect: float | None
    truth_is_exact: bool
    subgroup_effect: float | None

    @property
    def exit_code(self) -> int:
        return EXIT_CODES[self.verdict]

    @property
    def blocked_by(self) -> tuple[str, ...]:
        return tuple(name for name, decision in self.decisions.items() if decision.blocked)

    @property
    def pairing_gain(self) -> float:
        """How many times smaller an effect pairing lets the gate detect.

        The same data analysed two ways. Published because it is the cheapest
        improvement available to anybody running an eval: it costs nothing but
        keeping the per item scores, which most pipelines already have and then
        average away before writing them down.
        """
        if self.minimum_detectable <= 0.0:
            return float("nan")
        return self.minimum_detectable_unpaired / self.minimum_detectable

    @property
    def resolvable(self) -> bool:
        """Whether the observed delta is large enough for this eval set to speak.

        Compared against the paired minimum detectable effect, which is the most
        generous of the two, so this is the friendliest possible reading.
        """
        return abs(self.observed_delta) >= self.minimum_detectable

    def as_dict(self) -> dict[str, object]:
        return {
            "scenario": self.scenario,
            "items": self.items,
            "observed_delta": self.observed_delta,
            "verdict": self.verdict.value,
            "exit_code": self.exit_code,
            "blocking_gate": self.blocking_gate,
            "blocked_by": list(self.blocked_by),
            "decisions": {name: item.as_dict() for name, item in self.decisions.items()},
            "transitions": self.transitions.as_dict(),
            "minimum_detectable": self.minimum_detectable,
            "minimum_detectable_unpaired": self.minimum_detectable_unpaired,
            "pairing_gain": self.pairing_gain,
            "items_needed": self.items_needed,
            "resolvable": self.resolvable,
            "true_effect": self.true_effect,
            "truth_is_exact": self.truth_is_exact,
            "subgroup_effect": self.subgroup_effect,
        }


def decide_verdict(
    decisions: dict[str, Decision], *, observed: float, minimum_detectable: float
) -> Verdict:
    """Block if any gate blocked, otherwise pass only if the delta is resolvable.

    The ordering is deliberate. A block is a block regardless of resolvability,
    because a gate that fired on evidence it had should not be talked out of it by
    an arithmetic argument about power. The undecidable verdict applies only when
    nothing fired, which is exactly the case where a pass would be mistaken for
    evidence of no regression.
    """
    if any(decision.blocked for decision in decisions.values()):
        return Verdict.BLOCK
    if abs(observed) < minimum_detectable:
        return Verdict.UNDECIDABLE
    return Verdict.PASS


def audit(comparison: Comparison, policy: Policy) -> AuditResult:
    """Run every gate on one comparison and combine them into a verdict."""
    decisions = run_all(comparison, policy)
    counts = transitions(comparison, policy)
    paired = minimum_detectable_effect(policy, paired=True)
    unpaired = minimum_detectable_effect(policy, paired=False)
    observed = comparison.observed_delta
    verdict = decide_verdict(decisions, observed=observed, minimum_detectable=paired)
    blocked = [name for name, decision in decisions.items() if decision.blocked]
    # The combined gate is reported as the blocking one only when it is the only
    # one that fired, because naming it first would hide which specific condition
    # caught the regression, and that is the useful part of the message.
    leading = next((name for name in blocked if name != "combined"), None)
    if leading is None and blocked:
        leading = blocked[0]

    return AuditResult(
        scenario=comparison.scenario,
        items=comparison.items,
        observed_delta=observed,
        decisions=decisions,
        transitions=counts,
        verdict=verdict,
        blocking_gate=leading,
        minimum_detectable=paired,
        minimum_detectable_unpaired=unpaired,
        items_needed=items_needed_for(policy, max(policy.gate.mean_drop, 1e-9), paired=True),
        true_effect=comparison.true_effect,
        truth_is_exact=comparison.truth_is_exact,
        subgroup_effect=comparison.subgroup_effect,
    )
