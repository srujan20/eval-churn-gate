"""Eval runs, and the scenarios whose true effect is known.

An eval run is a score per item, produced by one version of a system on one
occasion. Two runs of the *same* version do not agree, because sampling,
temperature, ordering or a cache all move a score without any change to the
model. That disagreement is the whole reason a regression gate is hard, and it is
the reason the A/A scenario below is the anchor for everything else.

The score model has two components and the split matters more than the numbers.
An item effect, which is how hard that item is, and a run effect, which is the
occasion. Both runs of a comparison are scored on the same items, so the item
effect cancels exactly when the comparison is made item by item and does not
cancel at all when two averages are compared. That single fact is worth a factor
of four in what a gate can detect, and exp05 measures it.

Scenarios exist so that every published rate is graded against a known truth:

    aa                  the same version twice. The true effect is exactly zero
    uniform             every item drops by the same amount
    compensating        one slice collapses while the rest rises to match, so the
                        aggregate moves by approximately nothing
    churn_only          the aggregate is unchanged and a different set of items
                        passes
    improvement         a real gain, so the gate can be caught blocking one
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .config import Policy
from .errors import UnanswerableError, UsageError

SCENARIOS = ("aa", "uniform", "compensating", "churn_only", "improvement")
BASE_SCORE = 0.55
# Eval items in the real world belong to slices: a language, a customer tier, a
# document source. That matters here for one reason. A compensating regression
# whose losing subgroup corresponds to no observable attribute is undetectable by
# anything, which would be an honest finding and a useless one. Attaching the
# subgroup to a slice label makes the case detectable by a gate that looks, which
# is what turns the impossibility into a recommendation.
SLICES = ("alpha", "beta", "gamma", "delta")


@dataclass(frozen=True)
class Run:
    """One version's scores over the eval set, with the items it was scored on."""

    version: str
    seed: int
    item_ids: tuple[int, ...]
    scores: np.ndarray
    slices: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.slices and len(self.slices) != len(self.item_ids):
            raise UnanswerableError(
                f"run {self.version} has {len(self.slices)} slice labels for "
                f"{len(self.item_ids)} items"
            )
        if self.scores.ndim != 1:
            raise UnanswerableError(
                f"a run's scores must be one dimensional, got shape {self.scores.shape}"
            )
        if self.scores.shape[0] != len(self.item_ids):
            raise UnanswerableError(
                f"run {self.version} has {self.scores.shape[0]} scores for "
                f"{len(self.item_ids)} items"
            )
        if not self.item_ids:
            raise UnanswerableError("an eval run with no items cannot be gated")
        if np.any(self.scores < 0.0) or np.any(self.scores > 1.0):
            raise UnanswerableError(
                f"run {self.version} has a score outside the metric's range: "
                f"[{self.scores.min():.3f}, {self.scores.max():.3f}]"
            )

    @property
    def items(self) -> int:
        return len(self.item_ids)

    @property
    def mean(self) -> float:
        return float(self.scores.mean())


@dataclass(frozen=True)
class Comparison:
    """A baseline run and a candidate run, plus the truth only a scenario knows."""

    baseline: Run
    candidate: Run
    scenario: str
    true_effect: float
    truth_is_exact: bool
    subgroup: np.ndarray | None = None
    subgroup_effect: float | None = None

    def __post_init__(self) -> None:
        if self.baseline.slices != self.candidate.slices:
            raise UnanswerableError(
                "the two runs disagree about which slice each item belongs to, so no "
                "per slice comparison is possible"
            )
        if self.baseline.item_ids != self.candidate.item_ids:
            raise UnanswerableError(
                "the two runs were scored on different item sets, so no paired comparison "
                "is possible. A gate that averages anyway is comparing two different "
                "populations and calling the difference a regression"
            )

    @property
    def items(self) -> int:
        return self.baseline.items

    @property
    def deltas(self) -> np.ndarray:
        """Per item change. The only place a compensating regression is visible."""
        return self.candidate.scores - self.baseline.scores

    @property
    def observed_delta(self) -> float:
        """The aggregate a dashboard shows, and all a mean threshold gate reads."""
        return float(self.deltas.mean())

    @property
    def slices(self) -> tuple[str, ...]:
        return self.baseline.slices

    def slice_mask(self, name: str) -> np.ndarray:
        if not self.slices:
            raise UnanswerableError("this comparison carries no slice labels")
        return np.array([label == name for label in self.slices], dtype=bool)


def _clip(scores: np.ndarray) -> np.ndarray:
    return np.clip(scores, 0.0, 1.0)


def make_comparison(
    scenario: str,
    policy: Policy,
    seed: int,
    *,
    effect: float = 0.03,
    subgroup_share: float = 0.25,
) -> Comparison:
    """Build one baseline and candidate pair for a scenario with a known truth.

    `effect` is the size of the regression, as a positive number, and is ignored
    by the scenarios that do not use one. The A/A scenario ignores it entirely and
    its true effect is exactly zero, which is what makes every rate measured on it
    a rate rather than an estimate.
    """
    if scenario not in SCENARIOS:
        raise UsageError(f"unknown scenario {scenario!r}, expected one of {list(SCENARIOS)}")
    if effect < 0.0:
        raise UsageError(f"effect must be a non negative size, got {effect}")
    if not 0.0 < subgroup_share < 1.0:
        raise UsageError(f"subgroup_share must lie strictly between 0 and 1, got {subgroup_share}")

    items = policy.evaluation.items
    rng = np.random.default_rng(seed)
    slice_labels = tuple(SLICES[index % len(SLICES)] for index in range(items))
    # The item effect is drawn once and used by both runs, because both runs are
    # scored on the same items. Drawing it twice would be modelling two different
    # eval sets and would quietly destroy the pairing the comparison relies on.
    item_effect = policy.noise.item_sd * rng.normal(size=items)
    baseline_noise = policy.noise.run_sd * rng.normal(size=items)
    candidate_noise = policy.noise.run_sd * rng.normal(size=items)

    baseline_true = BASE_SCORE + item_effect
    subgroup: np.ndarray | None = None

    if scenario == "aa":
        candidate_true = baseline_true.copy()
    elif scenario == "uniform":
        candidate_true = baseline_true - effect
    elif scenario == "improvement":
        candidate_true = baseline_true + effect
    elif scenario == "compensating":
        # The case the aggregate cannot see. One slice loses a lot, the others gain
        # just enough to pay for it, so the mean barely moves while a quarter of the
        # eval set has become materially worse. The losing group is a slice rather
        # than a random subset on purpose: see the note beside SLICES.
        target = SLICES[seed % len(SLICES)]
        subgroup = np.array([label == target for label in slice_labels], dtype=bool)
        realised = float(subgroup.mean())
        loss = effect / realised
        gain = effect / (1.0 - realised)
        candidate_true = baseline_true + np.where(subgroup, -loss, gain)
    else:  # churn_only
        # A permutation of each item's distance from the pass boundary. Permuting
        # rather than shifting is what makes this exact: the candidate's noiseless
        # scores are the baseline's own values in a different order, so the
        # aggregate is unchanged to the last bit while a large share of items
        # crosses the boundary.
        #
        # The first version shifted each score across the boundary and then
        # re-centred the mean. Clipping to the metric's range afterwards moved the
        # mean again, and the scenario that was supposed to have no aggregate
        # change showed an observed delta of about three hundredths. A scenario
        # whose defining property is broken by its own construction is worse than
        # no scenario.
        threshold = policy.churn.pass_threshold
        candidate_true = threshold + rng.permutation(baseline_true - threshold)

    # The truth is computed on the noiseless scores after clipping, not before.
    # A bounded metric attenuates an effect near its edges, and defining the truth
    # before the bound would have published a target the data could not reach.
    true_effect = float(np.mean(_clip(candidate_true) - _clip(baseline_true)))
    truth_is_exact = scenario in ("aa", "churn_only")
    if scenario == "compensating":
        # An exact record of what the losing slice actually lost, which is the
        # quantity a gate should be judged on catching. The aggregate effect being
        # near zero is the whole point, so grading against it would grade every
        # gate on detecting nothing.
        subgroup_effect = float(np.mean((_clip(candidate_true) - _clip(baseline_true))[subgroup]))
    else:
        subgroup_effect = None

    baseline = Run(
        version="baseline",
        seed=seed,
        item_ids=tuple(range(items)),
        scores=_clip(baseline_true + baseline_noise),
        slices=slice_labels,
    )
    candidate = Run(
        version="candidate",
        seed=seed + 1,
        item_ids=tuple(range(items)),
        scores=_clip(candidate_true + candidate_noise),
        slices=slice_labels,
    )
    return Comparison(
        baseline=baseline,
        candidate=candidate,
        scenario=scenario,
        true_effect=true_effect,
        truth_is_exact=truth_is_exact,
        subgroup=subgroup,
        subgroup_effect=subgroup_effect,
    )
