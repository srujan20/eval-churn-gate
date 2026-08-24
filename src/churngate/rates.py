"""Rates, with an interval attached, because a rate over a sample is an estimate.

This module exists because of a number this build got wrong. An early run measured
the false block rate of a paired t test at 0.084 on comparisons whose true effect
is exactly zero, and the honest reading of that is a test running at nearly twice
its nominal level. At three thousand replications the same measurement came out at
0.055, which is the nominal level plus sampling. The first number was not a
finding, it was two hundred and fifty replications.

So every rate in this repository is a `Rate`, and every `Rate` carries the
interval its sample supports. The Wilson interval rather than the normal
approximation, for the specific reason that the normal one is worst exactly where
these rates live: near zero, where it produces a lower bound below zero and a
width that does not reflect the asymmetry of the true interval.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class Rate:
    """A count over a denominator, with a Wilson interval and a resolution floor."""

    numerator: int
    denominator: int
    confidence: float = 0.95

    def __post_init__(self) -> None:
        if self.denominator < 0:
            raise ValueError(f"a denominator cannot be negative, got {self.denominator}")
        if not 0 <= self.numerator <= max(self.denominator, 0):
            raise ValueError(
                f"a numerator of {self.numerator} does not fit a denominator of {self.denominator}"
            )
        if not 0.0 < self.confidence < 1.0:
            raise ValueError(f"confidence must lie strictly between 0 and 1, got {self.confidence}")

    @property
    def value(self) -> float:
        if self.denominator == 0:
            return float("nan")
        return self.numerator / self.denominator

    @property
    def floor(self) -> float:
        """The smallest non zero rate this denominator can express."""
        if self.denominator == 0:
            return float("nan")
        return 1.0 / self.denominator

    @property
    def is_measured_zero(self) -> bool:
        return self.denominator > 0 and self.numerator == 0

    @property
    def interval(self) -> tuple[float, float]:
        """The Wilson score interval at the configured confidence.

        Written out rather than imported so a reader can check it. The z value is
        the two sided normal quantile, and the interval is the standard Wilson
        form: the centre is pulled toward one half by an amount that grows as the
        sample shrinks, which is what stops a measured zero from producing an
        interval of zero width.
        """
        if self.denominator == 0:
            return (float("nan"), float("nan"))
        from scipy import stats

        z = float(stats.norm.ppf(1.0 - (1.0 - self.confidence) / 2.0))
        n = float(self.denominator)
        p = self.value
        denominator = 1.0 + z * z / n
        centre = (p + z * z / (2.0 * n)) / denominator
        spread = (z / denominator) * np.sqrt(p * (1.0 - p) / n + z * z / (4.0 * n * n))
        return (max(0.0, centre - spread), min(1.0, centre + spread))

    @property
    def width(self) -> float:
        low, high = self.interval
        return high - low

    def samples_needed_for(self, claimed: float) -> int:
        if claimed <= 0.0:
            raise ValueError(f"claimed rate must be positive, got {claimed}")
        return int(np.ceil(1.0 / claimed))

    def excludes(self, value: float) -> bool:
        """True when the interval does not contain this value.

        Used for the one claim that needs it: whether a measured false block rate
        is distinguishable from the nominal significance level. Saying a gate runs
        hot needs the interval to exclude the nominal value, and saying so without
        checking is how the 0.084 above got believed for an afternoon.
        """
        low, high = self.interval
        return not low <= value <= high

    def as_dict(self) -> dict[str, object]:
        low, high = self.interval
        return {
            "numerator": self.numerator,
            "denominator": self.denominator,
            "value": self.value,
            "interval_low": low,
            "interval_high": high,
            "interval_width": self.width,
            "confidence": self.confidence,
            "resolution_floor": self.floor,
            "is_measured_zero": self.is_measured_zero,
        }

    def render(self, digits: int = 3) -> str:
        """The rate as a string that cannot be quoted without its interval."""
        if self.denominator == 0:
            return "n/a"
        low, high = self.interval
        return f"{self.value:.{digits}f} [{low:.{digits}f}, {high:.{digits}f}]"
