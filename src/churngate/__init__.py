"""churngate: a regression gate that publishes its own error rates.

An aggregate delta between two model versions is a function of two numbers. Two
numbers cannot distinguish "nothing changed" from "half the items got better and
half got worse by the same amount", because both produce the same difference. The
per item transitions are the only place that distinction lives, and computing the
aggregate is exactly the step that throws them away.

This gates on the transitions as well as the aggregate, and grades every gate,
including its own, against scenarios whose true effect is known.
"""

from __future__ import annotations

__version__ = "0.1.0"

__all__ = ["__version__"]
