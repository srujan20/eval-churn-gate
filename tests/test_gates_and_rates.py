"""The five gates, the power arithmetic, and the interval every rate carries."""

from __future__ import annotations

import math

import numpy as np
import pytest

from churngate.config import with_items
from churngate.errors import UnanswerableError, UsageError
from churngate.gates import (
    GATE_NAMES,
    churn_floor,
    items_needed_for,
    minimum_detectable_effect,
    run_all,
    run_gate,
    slice_scan,
)
from churngate.rates import Rate
from churngate.runs import Comparison, Run, make_comparison


def _pair(baseline: list[float], candidate: list[float], slices: tuple[str, ...] | None = None):
    labels = slices if slices is not None else tuple("alpha" for _ in baseline)
    ids = tuple(range(len(baseline)))
    return Comparison(
        baseline=Run(version="a", seed=1, item_ids=ids, scores=np.array(baseline), slices=labels),
        candidate=Run(version="b", seed=2, item_ids=ids, scores=np.array(candidate), slices=labels),
        scenario="aa",
        true_effect=0.0,
        truth_is_exact=True,
    )


def test_every_gate_runs_on_every_scenario(small_policy):
    from churngate.runs import SCENARIOS

    for scenario in SCENARIOS:
        comparison = make_comparison(scenario, small_policy, 5)
        decisions = run_all(comparison, small_policy)
        assert set(decisions) == set(GATE_NAMES)


def test_an_unknown_gate_is_a_usage_error(small_policy, aa):
    with pytest.raises(UsageError, match="unknown gate"):
        run_gate("vibes", aa, small_policy)


def test_every_gate_reports_what_it_reads(small_policy, aa):
    for decision in run_all(aa, small_policy).values():
        assert decision.reads


def test_a_decision_serialises_every_field(small_policy, aa):
    payload = run_gate("mean_threshold", aa, small_policy).as_dict()
    assert set(payload) == {
        "gate",
        "blocked",
        "statistic",
        "threshold",
        "reads",
        "note",
        "undecidable",
    }


def test_a_paired_test_on_one_item_is_unanswerable(small_policy):
    comparison = _pair([0.5], [0.4])
    with pytest.raises(UnanswerableError, match="at least two items"):
        run_gate("paired_t", comparison, small_policy)


def test_the_mean_threshold_gate_blocks_a_large_drop(small_policy):
    comparison = _pair([0.9] * 20, [0.5] * 20)
    assert run_gate("mean_threshold", comparison, small_policy).blocked


def test_the_mean_threshold_gate_cannot_see_a_compensating_change(small_policy):
    """The impossibility, as a single assertion.

    Ten items lose four tenths and ten gain four tenths. Twenty of twenty items
    moved by a large amount and the difference of means is exactly zero.
    """
    baseline = [0.5] * 20
    candidate = [0.1] * 10 + [0.9] * 10
    comparison = _pair(baseline, candidate)
    assert comparison.observed_delta == pytest.approx(0.0)
    assert not run_gate("mean_threshold", comparison, small_policy).blocked


def test_the_churn_gate_sees_the_change_the_mean_cannot(small_policy):
    baseline = [0.5] * 20
    candidate = [0.1] * 10 + [0.9] * 10
    comparison = _pair(baseline, candidate)
    assert run_gate("churn", comparison, small_policy).blocked


def test_the_paired_t_gate_reports_undecidable_on_identical_runs(small_policy):
    """Reporting a pass here would be reporting a test that did not happen."""
    comparison = _pair([0.4] * 20, [0.4] * 20)
    decision = run_gate("paired_t", comparison, small_policy)
    assert decision.undecidable
    assert not decision.blocked


def test_a_uniform_movement_is_decided_by_its_sign_rather_than_by_a_test(small_policy):
    """Pins a guard that was written as a comparison with exactly zero.

    Deltas that are all identical come out with a variance near 1e-18 rather than
    at zero, so the guard never fired and scipy raised a precision loss warning
    from inside the t test. There is no sampling question when every item moved by
    the same amount: the sign is the answer.
    """
    baseline = [0.5 + 0.001 * index for index in range(200)]
    candidate = [value - 0.01 for value in baseline]
    decision = run_gate("paired_t", _pair(baseline, candidate), small_policy)
    assert decision.blocked
    assert "nothing to test" in decision.note


def test_a_uniform_improvement_is_not_blocked(small_policy):
    baseline = [0.5 + 0.001 * index for index in range(200)]
    candidate = [value + 0.01 for value in baseline]
    assert not run_gate("paired_t", _pair(baseline, candidate), small_policy).blocked


def test_the_paired_t_gate_blocks_a_noisy_small_drop(small_policy, rng):
    baseline = [0.5 + 0.001 * index for index in range(300)]
    candidate = [value - 0.01 + 0.02 * float(rng.normal()) for value in baseline]
    assert run_gate("paired_t", _pair(baseline, candidate), small_policy).blocked


def test_the_paired_bootstrap_agrees_with_the_t_test_on_a_clear_drop(small_policy):
    baseline = [0.5 + 0.001 * index for index in range(200)]
    candidate = [value - 0.02 for value in baseline]
    comparison = _pair(baseline, candidate)
    assert run_gate("paired_bootstrap", comparison, small_policy).blocked


def test_the_paired_bootstrap_is_deterministic(small_policy, uniform):
    left = run_gate("paired_bootstrap", uniform, small_policy).statistic
    right = run_gate("paired_bootstrap", uniform, small_policy).statistic
    assert left == right


def test_the_bootstrap_resamples_items_not_scores(small_policy):
    """A resample of scores would treat the runs as independent and lose the pairing.

    Checked by a property that only holds for the paired version: a comparison in
    which every item moved by exactly the same amount has zero resampling spread,
    because every resample has the same mean.
    """
    baseline = [0.3 + 0.002 * index for index in range(100)]
    candidate = [value - 0.05 for value in baseline]
    decision = run_gate("paired_bootstrap", _pair(baseline, candidate), small_policy)
    assert decision.statistic == pytest.approx(-0.05, abs=1e-9)


def test_the_slice_scan_finds_a_single_bad_slice(small_policy):
    labels = tuple(("alpha" if index < 60 else "beta") for index in range(240))
    baseline = [0.5 + 0.0005 * index for index in range(240)]
    candidate = [
        value - (0.12 if labels[index] == "alpha" else -0.04)
        for index, value in enumerate(baseline)
    ]
    decision = run_gate("slice_scan", _pair(baseline, candidate, labels), small_policy)
    assert decision.blocked
    assert "alpha" in decision.note


def test_the_slice_scan_needs_slice_labels(small_policy):
    ids = tuple(range(20))
    comparison = Comparison(
        baseline=Run(version="a", seed=1, item_ids=ids, scores=np.full(20, 0.5)),
        candidate=Run(version="b", seed=2, item_ids=ids, scores=np.full(20, 0.4)),
        scenario="aa",
        true_effect=0.0,
        truth_is_exact=True,
    )
    with pytest.raises(UnanswerableError, match="no slice labels"):
        slice_scan(comparison, small_policy)


def test_the_slice_scan_reports_undecidable_when_no_slice_varies(small_policy):
    labels = tuple(("alpha" if index < 10 else "beta") for index in range(20))
    comparison = _pair([0.5] * 20, [0.5] * 20, labels)
    decision = slice_scan(comparison, small_policy)
    assert decision.undecidable
    assert not decision.blocked


def test_the_slice_scan_threshold_is_the_corrected_level(small_policy):
    labels = tuple(("alpha" if index % 2 else "beta") for index in range(40))
    baseline = [0.5 + 0.001 * index for index in range(40)]
    candidate = [value - 0.001 * index for index, value in enumerate(baseline)]
    decision = slice_scan(_pair(baseline, candidate, labels), small_policy)
    assert decision.threshold == pytest.approx(small_policy.gate.alpha / 2)


def test_holm_stops_at_the_first_failure(small_policy):
    """Continuing past it would break the family wise guarantee the gate is charged for.

    Two slices, one clearly regressed and one clearly improved. Holm flags the
    first and stops, so the improved slice is never flagged.
    """
    labels = tuple(("alpha" if index < 100 else "beta") for index in range(200))
    baseline = [0.5 + 0.0005 * index for index in range(200)]
    candidate = [
        value - (0.10 if labels[index] == "alpha" else -0.10)
        for index, value in enumerate(baseline)
    ]
    decision = slice_scan(_pair(baseline, candidate, labels), small_policy)
    assert decision.blocked
    assert "beta" not in decision.note


def test_the_combined_gate_blocks_when_any_condition_fires(small_policy):
    baseline = [0.5] * 20
    candidate = [0.1] * 10 + [0.9] * 10
    decision = run_gate("combined", _pair(baseline, candidate), small_policy)
    assert decision.blocked
    assert "flip rate" in decision.note


def test_the_combined_gate_names_no_condition_when_nothing_fires(small_policy, aa):
    decision = run_gate("combined", aa, small_policy)
    if not decision.blocked:
        assert "no condition fired" in decision.note


def test_pairing_beats_comparing_two_averages(small_policy):
    """The whole reason to keep per item scores, as an inequality."""
    paired = minimum_detectable_effect(small_policy, paired=True)
    unpaired = minimum_detectable_effect(small_policy, paired=False)
    assert paired < unpaired


def test_the_detectable_effect_shrinks_with_the_item_count(small_policy):
    small = minimum_detectable_effect(small_policy, paired=True)
    large = minimum_detectable_effect(with_items(small_policy, 4000), paired=True)
    assert large < small


def test_the_detectable_effect_follows_the_root_n_rule(small_policy):
    """Four times the items should halve it, which is a check on the arithmetic."""
    base = minimum_detectable_effect(with_items(small_policy, 500), paired=True)
    quadrupled = minimum_detectable_effect(with_items(small_policy, 2000), paired=True)
    assert quadrupled == pytest.approx(base / 2.0, rel=1e-9)


def test_the_items_needed_inverts_the_detectable_effect(small_policy):
    effect = minimum_detectable_effect(small_policy, paired=True)
    needed = items_needed_for(small_policy, effect, paired=True)
    assert needed == pytest.approx(small_policy.evaluation.items, rel=0.02)


def test_a_non_positive_effect_has_no_item_count(small_policy):
    with pytest.raises(UsageError, match="must be positive"):
        items_needed_for(small_policy, 0.0, paired=True)


def test_detecting_the_configured_threshold_needs_more_items_unpaired(small_policy):
    paired = items_needed_for(small_policy, small_policy.gate.mean_drop, paired=True)
    unpaired = items_needed_for(small_policy, small_policy.gate.mean_drop, paired=False)
    assert unpaired > paired * 5


def test_the_churn_floor_summarises_a_set_of_comparisons(small_policy):
    from churngate.churn import transitions

    counts = [
        transitions(make_comparison("aa", small_policy, seed), small_policy) for seed in range(30)
    ]
    floor = churn_floor(counts)
    assert floor["median"] > 0.0
    assert floor["p95"] >= floor["median"]
    assert floor["max"] >= floor["p95"]


def test_the_churn_floor_of_nothing_is_unanswerable():
    with pytest.raises(UnanswerableError, match="from no comparisons"):
        churn_floor([])


def test_the_shipped_flip_limit_sits_above_the_measured_floor(policy):
    """The calibration this build got wrong once, pinned as a test.

    A limit below the A/A floor blocks every comparison whose true effect is
    exactly zero. This asserts the shipped value is above the ninety fifth
    percentile of the floor the shipped noise parameters produce.
    """
    from churngate.churn import transitions

    counts = [transitions(make_comparison("aa", policy, seed * 7), policy) for seed in range(60)]
    assert policy.churn.flip_rate_limit > churn_floor(counts)["p95"]


def test_a_rate_is_its_numerator_over_its_denominator():
    assert Rate(3, 12).value == 0.25


def test_a_rate_reports_its_resolution_floor():
    assert Rate(0, 400).floor == 0.0025
    assert Rate(0, 400).is_measured_zero


def test_a_rate_over_nothing_is_not_an_exception():
    assert math.isnan(Rate(0, 0).value)
    assert math.isnan(Rate(0, 0).floor)
    assert all(math.isnan(bound) for bound in Rate(0, 0).interval)
    assert Rate(0, 0).render() == "n/a"


def test_a_negative_denominator_is_refused():
    with pytest.raises(ValueError, match="cannot be negative"):
        Rate(0, -1)


def test_a_numerator_larger_than_its_denominator_is_refused():
    with pytest.raises(ValueError, match="does not fit"):
        Rate(11, 10)


def test_a_confidence_outside_the_open_interval_is_refused():
    with pytest.raises(ValueError, match="strictly between"):
        Rate(1, 10, confidence=1.0)


def test_the_wilson_interval_contains_the_point_estimate():
    rate = Rate(25, 400)
    low, high = rate.interval
    assert low < rate.value < high


def test_the_wilson_interval_of_a_measured_zero_has_width():
    """A normal approximation would put the lower bound below zero and the upper at zero."""
    low, high = Rate(0, 400).interval
    assert low == 0.0
    assert high > 0.0


def test_the_wilson_interval_narrows_with_the_sample():
    assert Rate(50, 1000).width < Rate(5, 100).width


def test_the_interval_can_be_asked_whether_it_excludes_a_value():
    """The check that stopped a sampling fluctuation being read as a finding."""
    assert not Rate(45, 1000).excludes(0.05)
    assert Rate(300, 1000).excludes(0.05)
    assert Rate(21, 1000).excludes(0.05)


def test_the_sample_needed_for_a_claim_is_one_over_the_claim():
    assert Rate(0, 400).samples_needed_for(0.001) == 1000


def test_a_non_positive_claimed_rate_is_refused():
    with pytest.raises(ValueError, match="must be positive"):
        Rate(0, 400).samples_needed_for(0.0)


def test_a_rate_renders_with_its_interval():
    rendered = Rate(25, 400).render()
    assert "[" in rendered and "]" in rendered


def test_a_rate_serialises_its_interval_and_its_floor():
    payload = Rate(25, 400).as_dict()
    for key in ("interval_low", "interval_high", "interval_width", "resolution_floor"):
        assert key in payload
