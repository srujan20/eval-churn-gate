"""Running the scenario sweep, and the row type every experiment reduces.

One place builds the comparisons, runs the gates and flattens the result, so five
experiments cannot disagree about how a figure was produced.

The row carries both the truth and whether that truth is exact. Two scenarios have
a true effect of exactly zero by construction, and two have one that is computed
per replication and therefore varies. A reduction that treated those the same
would be averaging an exact quantity together with an estimated one and reporting
the result as though both were the same kind of number.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass

from .audit import AuditResult, audit
from .config import Policy
from .gates import GATE_NAMES
from .rates import Rate
from .runs import SCENARIOS, make_comparison

DEFAULT_EFFECT = 0.03


@dataclass(frozen=True)
class GateRow:
    """One gated comparison, flattened to the columns the documents quote."""

    scenario: str
    replication: int
    items: int
    effect: float
    observed_delta: float
    true_effect: float
    truth_is_exact: bool
    subgroup_effect: float | None
    verdict: str
    blocking_gate: str | None
    flip_rate: float
    net_rate: float
    hidden_share: float
    gross_flips: int
    pass_to_fail: int
    fail_to_pass: int
    minimum_detectable: float
    minimum_detectable_unpaired: float
    resolvable: bool
    blocked_mean_threshold: bool
    blocked_paired_t: bool
    blocked_paired_bootstrap: bool
    blocked_churn: bool
    blocked_slice_scan: bool
    blocked_combined: bool

    def as_dict(self) -> dict[str, object]:
        return {
            key: None if isinstance(value, float) and not math.isfinite(value) else value
            for key, value in asdict(self).items()
        }

    def blocked_by(self, gate: str) -> bool:
        try:
            return bool(getattr(self, f"blocked_{gate}"))
        except AttributeError as exc:
            raise KeyError(f"unknown gate {gate!r}, expected one of {list(GATE_NAMES)}") from exc


def row_from(result: AuditResult, *, replication: int, effect: float) -> GateRow:
    counts = result.transitions
    return GateRow(
        scenario=result.scenario,
        replication=replication,
        items=result.items,
        effect=effect,
        observed_delta=result.observed_delta,
        true_effect=result.true_effect if result.true_effect is not None else float("nan"),
        truth_is_exact=result.truth_is_exact,
        subgroup_effect=result.subgroup_effect,
        verdict=result.verdict.value,
        blocking_gate=result.blocking_gate,
        flip_rate=counts.flip_rate,
        net_rate=counts.net_rate,
        hidden_share=counts.hidden_share,
        gross_flips=counts.gross_flips,
        pass_to_fail=counts.pass_to_fail,
        fail_to_pass=counts.fail_to_pass,
        minimum_detectable=result.minimum_detectable,
        minimum_detectable_unpaired=result.minimum_detectable_unpaired,
        resolvable=result.resolvable,
        blocked_mean_threshold=result.decisions["mean_threshold"].blocked,
        blocked_paired_t=result.decisions["paired_t"].blocked,
        blocked_paired_bootstrap=result.decisions["paired_bootstrap"].blocked,
        blocked_churn=result.decisions["churn"].blocked,
        blocked_slice_scan=result.decisions["slice_scan"].blocked,
        blocked_combined=result.decisions["combined"].blocked,
    )


def sweep(
    policy: Policy,
    *,
    scenarios: tuple[str, ...] = SCENARIOS,
    replications: int | None = None,
    effect: float = DEFAULT_EFFECT,
    seed_offset: int = 0,
) -> list[GateRow]:
    """Gate every scenario, `replications` times each.

    The seed is derived from the scenario name as well as the replication index, so
    adding a scenario does not renumber another scenario's comparisons and silently
    change every published figure.
    """
    count = replications if replications is not None else policy.evaluation.replications
    rows: list[GateRow] = []
    for scenario in scenarios:
        base = _scenario_seed(scenario) + seed_offset
        for replication in range(count):
            comparison = make_comparison(scenario, policy, base + replication * 7, effect=effect)
            rows.append(row_from(audit(comparison, policy), replication=replication, effect=effect))
    return rows


def _scenario_seed(scenario: str) -> int:
    digest = 0
    for character in scenario:
        digest = (digest * 131 + ord(character)) % 1_000_003
    return int(digest * 1000 % (2**31 - 1))


def block_rate(rows: list[GateRow], gate: str, *, scenario: str | None = None) -> Rate:
    """How often one gate blocked, over the rows given, with its interval."""
    selected = [row for row in rows if scenario is None or row.scenario == scenario]
    return Rate(sum(1 for row in selected if row.blocked_by(gate)), len(selected))


def verdict_rate(rows: list[GateRow], verdict: str, *, scenario: str | None = None) -> Rate:
    selected = [row for row in rows if scenario is None or row.scenario == scenario]
    return Rate(sum(1 for row in selected if row.verdict == verdict), len(selected))
