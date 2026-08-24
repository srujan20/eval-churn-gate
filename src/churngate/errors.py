"""Error types, separated so the CLI can map a failure to an exit code.

The distinction the exit codes exist to keep is between "the sweep's reported
best survived correction" and "the log cannot support an answer". A tool that
returns the same code for both is a tool whose zero means nothing.
"""

from __future__ import annotations


class SweepshrinkError(Exception):
    """Base class for every error this package raises deliberately."""


class UsageError(SweepshrinkError):
    """The caller asked for something the tool does not offer. Exit code 4."""


class UnanswerableError(SweepshrinkError):
    """The inputs are valid in form and cannot support an answer. Exit code 3.

    Raised for an eval set with no items, two runs scored on different item sets,
    a run with a score outside the metric's range, or a churn calculation with no
    items left after the minimum movement filter.
    """


class PolicyError(SweepshrinkError):
    """The policy file is missing a key or holds a value out of range. Exit 4."""


class MissingDependencyError(SweepshrinkError):
    """An optional estimator family was asked for and is not installed. Exit 4.

    Reserved for an optional dependency. This package has none: everything it
    needs is numpy, scipy and a YAML parser, which ADR-004 explains was a
    deliberate constraint rather than an accident.
    """
