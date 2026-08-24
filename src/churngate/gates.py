"""Five gates, and what each one is a function of.

    mean_threshold      the two aggregate numbers, and nothing else
    paired_t            the per item deltas, under a normal approximation
    paired_bootstrap    the per item deltas, with no distributional assumption
    churn               the per item transitions, calibrated against the A/A floor
    slice_scan          one paired test per slice, with the multiplicity corrected
    combined            the paired bootstrap, the slice scan and the churn gate

The first is what almost every pipeline ships, and it is here to be measured
rather than mocked. It has one property worth stating plainly: a threshold set at
the size of the regression it is meant to catch detects that regression about half
the time, because the observed delta lands either side of the threshold with equal
probability. exp03 measures it, and the arithmetic says it in advance.

Every gate returns the same shape, so they can be graded against each other and
against a truth none of them can see. The statistic and the threshold travel with
the decision, because a block with no number attached is a block nobody can argue
with, and a gate people cannot argue with is a gate they route around.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
from scipy import stats

from .churn import Transitions, transitions
from .config import Policy
from .errors import UnanswerableError, UsageError
from .runs import Comparison


@dataclass(frozen=True)
class Decision:
    """One gate's verdict on one comparison, with the number it rests on."""

    gate: str
    blocked: bool
    statistic: float
    threshold: float
    reads: str
    note: str = ""
    undecidable: bool = False

    def as_dict(self) -> dict[str, object]:
        return {
            "gate": self.gate,
            "blocked": self.blocked,
            "statistic": self.statistic,
            "threshold": self.threshold,
            "reads": self.reads,
            "note": self.note,
            "undecidable": self.undecidable,
        }


# Below this, a set of deltas carries no sampling information: every item moved by
# the same amount. Written as a tolerance rather than as a comparison with zero,
# because the first version tested for exactly zero variance and floating point
# made it useless. Constructed deltas that are all identical came out with a
# variance near 1e-18, the guard did not fire, and scipy raised a precision loss
# warning from inside the t test that the suite then treated as an error.
NEGLIGIBLE_SPREAD = 1e-12


def _check(comparison: Comparison) -> np.ndarray:
    deltas = comparison.deltas
    if deltas.size < 2:
        raise UnanswerableError(f"a paired test needs at least two items, got {deltas.size}")
    return deltas


def _degenerate(deltas: np.ndarray, gate: str, policy: Policy) -> Decision | None:
    """Decide without a test when every delta is the same, or return None.

    There is no sampling question here: every item moved identically, so the sign
    of the shared movement is the answer and a p value would be an artefact of
    dividing by a rounding error. When the shared movement is itself zero the runs
    are identical and the honest report is that no test was performed.
    """
    if float(np.std(deltas, ddof=1)) > NEGLIGIBLE_SPREAD:
        return None
    mean = float(deltas.mean())
    if abs(mean) <= NEGLIGIBLE_SPREAD:
        return Decision(
            gate=gate,
            blocked=False,
            statistic=1.0,
            threshold=policy.gate.alpha,
            reads="per item deltas",
            note="every delta was zero, so no test was performed",
            undecidable=True,
        )
    return Decision(
        gate=gate,
        blocked=mean < 0.0,
        statistic=0.0 if mean < 0.0 else 1.0,
        threshold=policy.gate.alpha,
        reads="per item deltas",
        note=f"every item moved by exactly {mean:+.6f}, so there is nothing to test",
    )


def mean_threshold(comparison: Comparison, policy: Policy) -> Decision:
    """Block when the aggregate fell by more than the configured amount.

    A function of two numbers. It cannot distinguish a release where nothing moved
    from one where a quarter of the eval set collapsed and the rest rose to pay for
    it, because both produce the same difference of means.
    """
    observed = comparison.observed_delta
    limit = -policy.gate.mean_drop
    return Decision(
        gate="mean_threshold",
        blocked=observed < limit,
        statistic=observed,
        threshold=limit,
        reads="two aggregate numbers",
        note="cannot see a compensating change, by construction",
    )


def paired_t(comparison: Comparison, policy: Policy) -> Decision:
    """Block when a one sided paired t test says the drop is real.

    One sided, because a gate is asking whether things got worse and a two sided
    test spends half its power on the direction nobody is gating against.
    """
    deltas = _check(comparison)
    degenerate = _degenerate(deltas, "paired_t", policy)
    if degenerate is not None:
        return degenerate
    result = stats.ttest_1samp(deltas, 0.0, alternative="less")
    return Decision(
        gate="paired_t",
        blocked=bool(result.pvalue < policy.gate.alpha),
        statistic=float(result.pvalue),
        threshold=policy.gate.alpha,
        reads="per item deltas",
        note="the item effect cancels, which is where the power comes from",
    )


def paired_bootstrap(comparison: Comparison, policy: Policy) -> Decision:
    """Block when a bootstrap interval on the paired mean sits below zero.

    Resamples items rather than scores, because the item is the unit that was
    sampled. Resampling scores would treat the two runs as independent and throw
    away the pairing that makes the test worth running.
    """
    deltas = _check(comparison)
    rng = np.random.default_rng(_bootstrap_seed(comparison))
    draws = rng.integers(0, deltas.size, size=(policy.gate.bootstrap_resamples, deltas.size))
    means = deltas[draws].mean(axis=1)
    upper = float(np.quantile(means, 1.0 - policy.gate.alpha))
    return Decision(
        gate="paired_bootstrap",
        blocked=upper < 0.0,
        statistic=upper,
        threshold=0.0,
        reads="per item deltas",
        note=f"one sided upper bound from {policy.gate.bootstrap_resamples} resamples",
    )


def churn_gate(comparison: Comparison, policy: Policy) -> Decision:
    """Block when too many items changed side, in either direction.

    The only gate here that can see a compensating change, because it counts
    crossings rather than differencing them. Its threshold has to be calibrated
    against the A/A floor: run to run noise alone crosses the boundary for every
    item sitting near it, and a limit below that floor blocks on nothing else.
    """
    counts = transitions(comparison, policy)
    return Decision(
        gate="churn",
        blocked=counts.flip_rate > policy.churn.flip_rate_limit,
        statistic=counts.flip_rate,
        threshold=policy.churn.flip_rate_limit,
        reads="per item transitions",
        note=f"{counts.pass_to_fail} broke and {counts.fail_to_pass} were fixed",
    )


def slice_scan(comparison: Comparison, policy: Policy) -> Decision:
    """One paired test per slice, with the multiplicity corrected by Holm's method.

    The gate that can see a compensating regression. An aggregate cannot, by
    construction, and neither can the churn gate at a threshold calibrated against
    its own noise floor: a slice losing a tenth of a point moves few enough items
    across the pass boundary to disappear into run to run variation. Testing each
    slice separately puts the regression back inside a population where it is large.

    Holm rather than Bonferroni, because Bonferroni over four slices costs a
    quarter of the significance level for no reason: Holm is uniformly at least as
    powerful and controls the same family wise error rate. The cost is real and is
    measured rather than waved at: the family wise correction raises the smallest
    detectable per slice effect, and exp02 reports the false block rate the scan
    produces on comparisons whose true effect is exactly zero.
    """
    labels = comparison.slices
    if not labels:
        raise UnanswerableError(
            "this comparison carries no slice labels, so no scan is possible. A gate that "
            "silently falls back to the aggregate here would report a pass it never tested"
        )
    deltas = _check(comparison)
    names = sorted(set(labels))
    raw: list[tuple[str, float]] = []
    for name in names:
        mask = comparison.slice_mask(name)
        subset = deltas[mask]
        if subset.size < 2:
            continue
        if float(np.std(subset, ddof=1)) <= NEGLIGIBLE_SPREAD:
            shared = float(subset.mean())
            if abs(shared) <= NEGLIGIBLE_SPREAD:
                # Nothing moved in this slice at all, so it carries no information
                # and is skipped. If every slice is like this the scan reports that
                # it could not decide, which is not the same as a pass.
                continue
            # Every item in this slice moved identically. A p value here would be a
            # rounding artefact, so the sign decides and the extreme value is
            # recorded rather than the slice being dropped.
            raw.append((name, 0.0 if shared < 0.0 else 1.0))
            continue
        result = stats.ttest_1samp(subset, 0.0, alternative="less")
        raw.append((name, float(result.pvalue)))
    if not raw:
        return Decision(
            gate="slice_scan",
            blocked=False,
            statistic=1.0,
            threshold=policy.gate.alpha,
            reads="per item deltas, split by slice",
            note="no slice had enough variation to test",
            undecidable=True,
        )

    ordered = sorted(raw, key=lambda entry: entry[1])
    count = len(ordered)
    blocked_slices: list[str] = []
    for index, (name, pvalue) in enumerate(ordered):
        # Holm: compare the k-th smallest p value against alpha over (m - k), and
        # stop at the first failure. Continuing past it would be Sidak's mistake
        # and would break the family wise guarantee this gate is charged for.
        if pvalue < policy.gate.alpha / (count - index):
            blocked_slices.append(name)
        else:
            break
    smallest = ordered[0]
    return Decision(
        gate="slice_scan",
        blocked=bool(blocked_slices),
        statistic=smallest[1],
        threshold=policy.gate.alpha / count,
        reads="per item deltas, split by slice",
        note=(
            f"slices flagged: {', '.join(blocked_slices)}"
            if blocked_slices
            else f"smallest p value {smallest[1]:.4f} on slice {smallest[0]}"
        ),
    )


def combined(comparison: Comparison, policy: Policy) -> Decision:
    """Block when the paired interval, the slice scan or the churn gate blocks.

    The one worth shipping, and its cost is measured rather than assumed: blocking
    on any of three conditions raises the false block rate above what any of them
    does alone, and exp01 publishes by how much.
    """
    interval = paired_bootstrap(comparison, policy)
    scan = slice_scan(comparison, policy)
    flips = churn_gate(comparison, policy)
    reason = []
    if interval.blocked:
        reason.append("the paired interval sits below zero")
    if scan.blocked:
        reason.append("a slice regressed on its own")
    if flips.blocked:
        reason.append("the flip rate exceeds its limit")
    leading = next((item for item in (scan, interval, flips) if item.blocked), interval)
    return Decision(
        gate="combined",
        blocked=bool(reason),
        statistic=leading.statistic,
        threshold=leading.threshold,
        reads="per item deltas, slices and transitions",
        note=", and ".join(reason) if reason else "no condition fired",
    )


def _bootstrap_seed(comparison: Comparison) -> int:
    digest = 0
    for character in f"{comparison.scenario}:{comparison.baseline.seed}":
        digest = (digest * 131 + ord(character)) % 1_000_003
    return int(digest % (2**31 - 1))


GATES: dict[str, Callable[[Comparison, Policy], Decision]] = {
    "mean_threshold": mean_threshold,
    "paired_t": paired_t,
    "paired_bootstrap": paired_bootstrap,
    "churn": churn_gate,
    "slice_scan": slice_scan,
    "combined": combined,
}

GATE_NAMES = tuple(GATES)


def run_gate(name: str, comparison: Comparison, policy: Policy) -> Decision:
    try:
        function = GATES[name]
    except KeyError as exc:
        raise UsageError(f"unknown gate {name!r}, expected one of {sorted(GATES)}") from exc
    return function(comparison, policy)


def run_all(comparison: Comparison, policy: Policy) -> dict[str, Decision]:
    return {name: function(comparison, policy) for name, function in GATES.items()}


def minimum_detectable_effect(policy: Policy, *, paired: bool) -> float:
    """The smallest true regression a test of this size can detect at the set power.

    Paired, only the run to run component survives, because the item effect is the
    same in both runs and differences away. Unpaired, the item spread stays in, and
    it is the larger of the two by design, which is why the same data analysed two
    ways gives such different answers.

    Reported as a positive size. The arithmetic is the standard one sided formula,
    written out rather than imported so a reader can check it: the sum of the
    critical value and the power quantile, times the standard error of the estimate.
    """
    items = policy.evaluation.items
    if paired:
        standard_error = (2.0**0.5) * policy.noise.run_sd / (items**0.5)
    else:
        spread = (policy.noise.item_sd**2 + policy.noise.run_sd**2) ** 0.5
        standard_error = (2.0**0.5) * spread / (items**0.5)
    critical = float(stats.norm.ppf(1.0 - policy.gate.alpha))
    power_quantile = float(stats.norm.ppf(policy.gate.power))
    return (critical + power_quantile) * standard_error


def items_needed_for(policy: Policy, effect: float, *, paired: bool) -> int:
    """How many items a test would need to detect an effect of this size.

    The inverse of the formula above, and the number a team actually wants when
    told their eval set cannot resolve the difference they are gating on.
    """
    if effect <= 0.0:
        raise UsageError(f"effect must be positive, got {effect}")
    spread = (
        policy.noise.run_sd if paired else (policy.noise.item_sd**2 + policy.noise.run_sd**2) ** 0.5
    )
    critical = float(stats.norm.ppf(1.0 - policy.gate.alpha))
    power_quantile = float(stats.norm.ppf(policy.gate.power))
    return int(np.ceil(2.0 * ((critical + power_quantile) * spread / effect) ** 2))


def churn_floor(transitions_list: list[Transitions]) -> dict[str, float]:
    """The churn a set of A/A comparisons produced, which is the floor.

    Any observed churn below this says nothing at all, and a churn gate set below
    it blocks on noise. Returned as a summary rather than a single number, because
    a gate needs a high quantile of the floor and a reader wants its centre.
    """
    if not transitions_list:
        raise UnanswerableError("cannot compute a churn floor from no comparisons")
    rates = np.array([item.flip_rate for item in transitions_list], dtype=float)
    return {
        "comparisons": float(rates.size),
        "median": float(np.median(rates)),
        "mean": float(rates.mean()),
        "p95": float(np.quantile(rates, 0.95)),
        "max": float(rates.max()),
    }
