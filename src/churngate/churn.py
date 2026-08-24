"""Per item transitions, and the net against gross decomposition.

An aggregate delta is one number. A set of transitions is four: items that passed
and now fail, items that failed and now pass, and the two that did not move. The
aggregate is a function of the difference between the first two. The number of
people affected is a function of their sum.

Those are different quantities, and the second cannot be recovered from the first.
A release where nothing changed and a release where six percent of items broke
while six percent were fixed produce the same net, the same pass rate and the same
dashboard. exp04 measures how uncorrelated they are, which is the impossibility
stated as a number rather than as an argument.

The minimum movement filter deserves its own note. An item sitting exactly on the
pass boundary crosses it on a rounding difference, and counting those inflates the
churn without any user experiencing a change. The filter is a policy value, it is
reported alongside every churn figure, and exp01 reports what the churn floor is
with and without it.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .config import Policy
from .errors import UnanswerableError
from .runs import Comparison


@dataclass(frozen=True)
class Transitions:
    """The four cells, plus what the filter removed."""

    items: int
    pass_to_fail: int
    fail_to_pass: int
    stayed_pass: int
    stayed_fail: int
    filtered_out: int
    threshold: float
    minimum_movement: float

    def __post_init__(self) -> None:
        counted = self.pass_to_fail + self.fail_to_pass + self.stayed_pass + self.stayed_fail
        if counted != self.items:
            raise UnanswerableError(
                f"the transition cells sum to {counted} for {self.items} items, so some "
                "item was counted twice or not at all"
            )

    @property
    def gross_flips(self) -> int:
        """How many items changed side. What a user downstream experiences."""
        return self.pass_to_fail + self.fail_to_pass

    @property
    def net_flips(self) -> int:
        """The change in the number of passing items. What the aggregate reflects."""
        return self.fail_to_pass - self.pass_to_fail

    @property
    def flip_rate(self) -> float:
        return self.gross_flips / self.items

    @property
    def net_rate(self) -> float:
        return self.net_flips / self.items

    @property
    def baseline_pass_rate(self) -> float:
        return (self.stayed_pass + self.pass_to_fail) / self.items

    @property
    def candidate_pass_rate(self) -> float:
        return (self.stayed_pass + self.fail_to_pass) / self.items

    @property
    def hidden_share(self) -> float:
        """Share of the movement that the net cancels away.

        One when the flips balance exactly, which is the case a pass rate cannot
        distinguish from no change at all. Zero when every flip goes one way, which
        is the only case where the net tells the whole story.
        """
        if self.gross_flips == 0:
            return 0.0
        return 1.0 - abs(self.net_flips) / self.gross_flips

    @property
    def resolution_floor(self) -> float:
        return 1.0 / self.items

    def as_dict(self) -> dict[str, object]:
        return {
            "items": self.items,
            "pass_to_fail": self.pass_to_fail,
            "fail_to_pass": self.fail_to_pass,
            "stayed_pass": self.stayed_pass,
            "stayed_fail": self.stayed_fail,
            "filtered_out": self.filtered_out,
            "threshold": self.threshold,
            "minimum_movement": self.minimum_movement,
            "gross_flips": self.gross_flips,
            "net_flips": self.net_flips,
            "flip_rate": self.flip_rate,
            "net_rate": self.net_rate,
            "baseline_pass_rate": self.baseline_pass_rate,
            "candidate_pass_rate": self.candidate_pass_rate,
            "hidden_share": self.hidden_share,
            "resolution_floor": self.resolution_floor,
        }


def transitions(comparison: Comparison, policy: Policy) -> Transitions:
    """Count the four cells for one comparison."""
    threshold = policy.churn.pass_threshold
    minimum = policy.churn.minimum_movement
    baseline_pass = comparison.baseline.scores >= threshold
    candidate_pass = comparison.candidate.scores >= threshold
    moved = np.abs(comparison.deltas) >= minimum

    # A crossing that the filter rejects is recorded as no change rather than
    # dropped from the denominator. Removing it from the denominator would raise
    # every rate by shrinking what they are rates of.
    crossed_down = baseline_pass & ~candidate_pass
    crossed_up = ~baseline_pass & candidate_pass
    filtered = int(np.sum((crossed_down | crossed_up) & ~moved))
    pass_to_fail = int(np.sum(crossed_down & moved))
    fail_to_pass = int(np.sum(crossed_up & moved))
    items = comparison.items
    stayed_pass = int(np.sum(baseline_pass)) - pass_to_fail
    stayed_fail = items - int(np.sum(baseline_pass)) - fail_to_pass

    return Transitions(
        items=items,
        pass_to_fail=pass_to_fail,
        fail_to_pass=fail_to_pass,
        stayed_pass=stayed_pass,
        stayed_fail=stayed_fail,
        filtered_out=filtered,
        threshold=threshold,
        minimum_movement=minimum,
    )
