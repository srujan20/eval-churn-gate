"""The scenarios whose truth is known, and the transitions the aggregate hides."""

from __future__ import annotations

import numpy as np
import pytest

from churngate.churn import Transitions, transitions
from churngate.errors import UnanswerableError, UsageError
from churngate.runs import SCENARIOS, SLICES, Comparison, Run, make_comparison


def test_every_scenario_builds(small_policy):
    for scenario in SCENARIOS:
        assert make_comparison(scenario, small_policy, 3).items == small_policy.evaluation.items


def test_an_unknown_scenario_is_a_usage_error(small_policy):
    with pytest.raises(UsageError, match="unknown scenario"):
        make_comparison("regression", small_policy, 1)


def test_a_negative_effect_is_refused(small_policy):
    with pytest.raises(UsageError, match="non negative size"):
        make_comparison("uniform", small_policy, 1, effect=-0.1)


@pytest.mark.parametrize("share", [0.0, 1.0, 1.5])
def test_a_subgroup_share_outside_the_open_interval_is_refused(small_policy, share):
    with pytest.raises(UsageError, match="strictly between 0 and 1"):
        make_comparison("compensating", small_policy, 1, subgroup_share=share)


def test_a_run_with_no_items_is_refused():
    with pytest.raises(UnanswerableError, match="no items cannot be gated"):
        Run(version="v", seed=1, item_ids=(), scores=np.array([]))


def test_a_run_with_a_score_out_of_range_is_refused():
    with pytest.raises(UnanswerableError, match="outside the metric's range"):
        Run(version="v", seed=1, item_ids=(0,), scores=np.array([1.5]))


def test_a_run_with_mismatched_score_count_is_refused():
    with pytest.raises(UnanswerableError, match="scores for"):
        Run(version="v", seed=1, item_ids=(0, 1), scores=np.array([0.5]))


def test_a_two_dimensional_score_array_is_refused():
    with pytest.raises(UnanswerableError, match="one dimensional"):
        Run(version="v", seed=1, item_ids=(0,), scores=np.zeros((1, 2)))


def test_mismatched_slice_labels_are_refused():
    with pytest.raises(UnanswerableError, match="slice labels for"):
        Run(version="v", seed=1, item_ids=(0, 1), scores=np.array([0.4, 0.6]), slices=("a",))


def test_two_runs_on_different_items_cannot_be_compared():
    """A gate that averaged anyway would be comparing two populations."""
    left = Run(version="a", seed=1, item_ids=(0, 1), scores=np.array([0.4, 0.6]))
    right = Run(version="b", seed=2, item_ids=(0, 2), scores=np.array([0.4, 0.6]))
    with pytest.raises(UnanswerableError, match="different item sets"):
        Comparison(
            baseline=left, candidate=right, scenario="aa", true_effect=0.0, truth_is_exact=True
        )


def test_two_runs_disagreeing_about_slices_cannot_be_compared():
    left = Run(version="a", seed=1, item_ids=(0, 1), scores=np.array([0.4, 0.6]), slices=("x", "y"))
    right = Run(
        version="b", seed=2, item_ids=(0, 1), scores=np.array([0.4, 0.6]), slices=("x", "z")
    )
    with pytest.raises(UnanswerableError, match="disagree about which slice"):
        Comparison(
            baseline=left, candidate=right, scenario="aa", true_effect=0.0, truth_is_exact=True
        )


def test_the_aa_scenario_has_a_true_effect_of_exactly_zero(small_policy):
    """The anchor. Not close to zero, exactly zero, at every seed."""
    for seed in range(20):
        comparison = make_comparison("aa", small_policy, seed)
        assert comparison.true_effect == 0.0
        assert comparison.truth_is_exact


def test_the_churn_only_scenario_has_a_true_effect_of_exactly_zero(small_policy):
    """A permutation of the same values, so the mean is unchanged to the last bit.

    The first version shifted scores and re-centred, and clipping to the metric's
    range then moved the mean by about three hundredths. A scenario whose defining
    property is broken by its own construction is worse than no scenario.
    """
    for seed in range(20):
        comparison = make_comparison("churn_only", small_policy, seed)
        assert comparison.true_effect == pytest.approx(0.0, abs=1e-12)
        assert comparison.truth_is_exact


def test_the_churn_only_scenario_moves_many_items_across_the_boundary(small_policy, churn_only):
    counts = transitions(churn_only, small_policy)
    assert counts.flip_rate > 0.3


def test_the_uniform_scenario_has_a_negative_true_effect(small_policy):
    assert make_comparison("uniform", small_policy, 5, effect=0.03).true_effect < -0.02


def test_the_improvement_scenario_has_a_positive_true_effect(small_policy):
    assert make_comparison("improvement", small_policy, 5, effect=0.03).true_effect > 0.02


def test_a_bounded_metric_attenuates_the_effect(small_policy):
    """The truth is computed after clipping, so it is reachable rather than nominal."""
    comparison = make_comparison("uniform", small_policy, 5, effect=0.03)
    assert comparison.true_effect > -0.03


def test_the_compensating_scenario_has_a_near_zero_aggregate(small_policy):
    effects = [
        make_comparison("compensating", small_policy, seed).true_effect for seed in range(20)
    ]
    assert abs(float(np.mean(effects))) < 0.005


def test_the_compensating_scenario_has_a_large_slice_effect(small_policy):
    for seed in range(10):
        comparison = make_comparison("compensating", small_policy, seed, effect=0.03)
        assert comparison.subgroup_effect < -0.05


def test_the_compensating_subgroup_is_a_whole_slice(small_policy):
    """Attached to an observable attribute, or nothing could ever detect it."""
    comparison = make_comparison("compensating", small_policy, 7)
    labels = np.array(comparison.slices)
    affected = set(labels[comparison.subgroup])
    assert len(affected) == 1


def test_only_the_compensating_scenario_reports_a_slice_effect(small_policy):
    for scenario in SCENARIOS:
        comparison = make_comparison(scenario, small_policy, 3)
        if scenario == "compensating":
            assert comparison.subgroup_effect is not None
        else:
            assert comparison.subgroup_effect is None


def test_every_comparison_carries_slice_labels(small_policy):
    for scenario in SCENARIOS:
        comparison = make_comparison(scenario, small_policy, 3)
        assert set(comparison.slices) == set(SLICES)


def test_asking_for_a_slice_mask_without_labels_is_refused():
    left = Run(version="a", seed=1, item_ids=(0, 1), scores=np.array([0.4, 0.6]))
    right = Run(version="b", seed=2, item_ids=(0, 1), scores=np.array([0.4, 0.6]))
    comparison = Comparison(
        baseline=left, candidate=right, scenario="aa", true_effect=0.0, truth_is_exact=True
    )
    with pytest.raises(UnanswerableError, match="no slice labels"):
        comparison.slice_mask("alpha")


def test_the_same_seed_builds_the_same_comparison(small_policy):
    left = make_comparison("uniform", small_policy, 9)
    right = make_comparison("uniform", small_policy, 9)
    assert np.array_equal(left.deltas, right.deltas)


def test_a_different_seed_builds_a_different_comparison(small_policy):
    left = make_comparison("uniform", small_policy, 9)
    right = make_comparison("uniform", small_policy, 10)
    assert not np.array_equal(left.deltas, right.deltas)


def test_the_observed_delta_is_the_mean_of_the_per_item_deltas(uniform):
    assert uniform.observed_delta == pytest.approx(float(uniform.deltas.mean()))


def test_the_transition_cells_sum_to_the_item_count(small_policy, compensating):
    counts = transitions(compensating, small_policy)
    assert (
        counts.pass_to_fail + counts.fail_to_pass + counts.stayed_pass + counts.stayed_fail
        == counts.items
    )


def test_transitions_that_do_not_sum_are_refused():
    with pytest.raises(UnanswerableError, match="counted twice or not at all"):
        Transitions(
            items=10,
            pass_to_fail=1,
            fail_to_pass=1,
            stayed_pass=1,
            stayed_fail=1,
            filtered_out=0,
            threshold=0.5,
            minimum_movement=0.01,
        )


def test_gross_flips_are_the_sum_and_net_is_the_difference():
    counts = Transitions(
        items=10,
        pass_to_fail=3,
        fail_to_pass=2,
        stayed_pass=2,
        stayed_fail=3,
        filtered_out=0,
        threshold=0.5,
        minimum_movement=0.01,
    )
    assert counts.gross_flips == 5
    assert counts.net_flips == -1
    assert counts.flip_rate == 0.5
    assert counts.net_rate == -0.1


def test_the_hidden_share_is_one_when_the_flips_balance():
    """The case a pass rate cannot distinguish from no change at all."""
    counts = Transitions(
        items=10,
        pass_to_fail=3,
        fail_to_pass=3,
        stayed_pass=2,
        stayed_fail=2,
        filtered_out=0,
        threshold=0.5,
        minimum_movement=0.01,
    )
    assert counts.net_flips == 0
    assert counts.hidden_share == 1.0


def test_the_hidden_share_is_zero_when_every_flip_goes_one_way():
    counts = Transitions(
        items=10,
        pass_to_fail=4,
        fail_to_pass=0,
        stayed_pass=2,
        stayed_fail=4,
        filtered_out=0,
        threshold=0.5,
        minimum_movement=0.01,
    )
    assert counts.hidden_share == 0.0


def test_the_hidden_share_is_zero_when_nothing_flipped():
    counts = Transitions(
        items=10,
        pass_to_fail=0,
        fail_to_pass=0,
        stayed_pass=5,
        stayed_fail=5,
        filtered_out=0,
        threshold=0.5,
        minimum_movement=0.01,
    )
    assert counts.hidden_share == 0.0


def test_the_pass_rates_are_recoverable_from_the_cells():
    counts = Transitions(
        items=10,
        pass_to_fail=2,
        fail_to_pass=1,
        stayed_pass=3,
        stayed_fail=4,
        filtered_out=0,
        threshold=0.5,
        minimum_movement=0.01,
    )
    assert counts.baseline_pass_rate == 0.5
    assert counts.candidate_pass_rate == 0.4


def test_a_crossing_below_the_movement_filter_counts_as_no_change(small_policy):
    """And stays in the denominator, or every rate would rise by shrinking it."""
    left = Run(
        version="a",
        seed=1,
        item_ids=(0, 1),
        scores=np.array([0.5005, 0.9]),
        slices=("alpha", "beta"),
    )
    right = Run(
        version="b",
        seed=2,
        item_ids=(0, 1),
        scores=np.array([0.4995, 0.9]),
        slices=("alpha", "beta"),
    )
    comparison = Comparison(
        baseline=left, candidate=right, scenario="aa", true_effect=0.0, truth_is_exact=True
    )
    counts = transitions(comparison, small_policy)
    assert counts.filtered_out == 1
    assert counts.pass_to_fail == 0
    assert counts.items == 2


def test_transitions_serialise_every_derived_field(small_policy, compensating):
    payload = transitions(compensating, small_policy).as_dict()
    for key in ("gross_flips", "net_flips", "hidden_share", "resolution_floor"):
        assert key in payload
