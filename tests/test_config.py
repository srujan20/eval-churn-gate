"""Policy loading refuses a broken policy at the boundary, not at the point of use."""

from __future__ import annotations

import pytest

from churngate.config import DEFAULT_POLICY_PATH, load_policy, policy_from_mapping, with_items
from churngate.errors import PolicyError


def test_the_committed_policy_loads(policy):
    assert policy.gate.alpha > 0.0


def test_the_committed_policy_records_where_it_came_from(policy):
    assert policy.source == str(DEFAULT_POLICY_PATH)


def test_a_missing_policy_file_is_refused(tmp_path):
    with pytest.raises(PolicyError, match="not found"):
        load_policy(tmp_path / "absent.yaml")


def test_a_policy_file_that_is_not_yaml_is_refused(tmp_path):
    path = tmp_path / "broken.yaml"
    path.write_text("gate: [unclosed\n", encoding="utf-8")
    with pytest.raises(PolicyError, match="not valid YAML"):
        load_policy(path)


def test_a_policy_file_holding_a_list_is_refused(tmp_path):
    path = tmp_path / "list.yaml"
    path.write_text("- one\n- two\n", encoding="utf-8")
    with pytest.raises(PolicyError, match="mapping at the top level"):
        load_policy(path)


@pytest.mark.parametrize("section", ["gate", "churn", "evaluation", "noise"])
def test_every_top_level_section_is_required(minimal_policy_mapping, section):
    del minimal_policy_mapping[section]
    with pytest.raises(PolicyError, match=section):
        policy_from_mapping(minimal_policy_mapping)


def test_a_section_that_is_not_a_mapping_is_refused(minimal_policy_mapping):
    minimal_policy_mapping["noise"] = ["run_sd"]
    with pytest.raises(PolicyError, match="must be a mapping"):
        policy_from_mapping(minimal_policy_mapping)


def test_too_few_bootstrap_resamples_are_refused_with_the_reason(minimal_policy_mapping):
    minimal_policy_mapping["gate"]["bootstrap_resamples"] = 20
    with pytest.raises(PolicyError, match="Monte Carlo error"):
        policy_from_mapping(minimal_policy_mapping)


def test_an_eval_set_of_a_handful_of_items_is_refused_with_the_reason(minimal_policy_mapping):
    minimal_policy_mapping["evaluation"]["items"] = 4
    with pytest.raises(PolicyError, match="no power worth reporting"):
        policy_from_mapping(minimal_policy_mapping)


def test_a_single_entry_item_sweep_is_refused(minimal_policy_mapping):
    minimal_policy_mapping["evaluation"]["item_sweep"] = [300]
    with pytest.raises(PolicyError, match="at least two sizes"):
        policy_from_mapping(minimal_policy_mapping)


def test_an_item_sweep_that_is_not_a_list_is_refused(minimal_policy_mapping):
    minimal_policy_mapping["evaluation"]["item_sweep"] = 300
    with pytest.raises(PolicyError, match="at least two sizes"):
        policy_from_mapping(minimal_policy_mapping)


def test_a_tiny_size_in_the_item_sweep_is_refused(minimal_policy_mapping):
    minimal_policy_mapping["evaluation"]["item_sweep"] = [2, 300]
    with pytest.raises(PolicyError, match="at least 10"):
        policy_from_mapping(minimal_policy_mapping)


def test_a_descending_item_sweep_is_refused(minimal_policy_mapping):
    minimal_policy_mapping["evaluation"]["item_sweep"] = [300, 100]
    with pytest.raises(PolicyError, match="ascending"):
        policy_from_mapping(minimal_policy_mapping)


def test_too_few_replications_are_refused_with_the_reason(minimal_policy_mapping):
    minimal_policy_mapping["evaluation"]["replications"] = 5
    with pytest.raises(PolicyError, match="resolution floor"):
        policy_from_mapping(minimal_policy_mapping)


@pytest.mark.parametrize("field", ["run_sd", "item_sd"])
def test_a_non_positive_noise_term_is_refused(minimal_policy_mapping, field):
    minimal_policy_mapping["noise"][field] = 0.0
    with pytest.raises(PolicyError, match=field):
        policy_from_mapping(minimal_policy_mapping)


@pytest.mark.parametrize("field", ["alpha", "power"])
def test_a_probability_outside_the_open_interval_is_refused(minimal_policy_mapping, field):
    minimal_policy_mapping["gate"][field] = 1.0
    with pytest.raises(PolicyError, match=field):
        policy_from_mapping(minimal_policy_mapping)


def test_a_non_numeric_threshold_is_refused(minimal_policy_mapping):
    minimal_policy_mapping["gate"]["mean_drop"] = "small"
    with pytest.raises(PolicyError, match="must be a number"):
        policy_from_mapping(minimal_policy_mapping)


def test_a_flip_limit_below_its_own_noise_floor_is_refused_with_the_reason(
    minimal_policy_mapping,
):
    """The mistake this build actually made, refused at load time now.

    A flip rate limit of 0.06 was written from intuition and measured to be about
    half the rate that run to run noise produces on its own, so it blocked every
    comparison whose true effect was exactly zero.
    """
    minimal_policy_mapping["churn"]["flip_rate_limit"] = 0.005
    with pytest.raises(PolicyError, match="the gate blocks on noise"):
        policy_from_mapping(minimal_policy_mapping)


def test_a_movement_filter_as_large_as_the_metric_is_refused(minimal_policy_mapping):
    minimal_policy_mapping["churn"]["minimum_movement"] = 0.6
    with pytest.raises(PolicyError, match="discards real crossings"):
        policy_from_mapping(minimal_policy_mapping)


def test_the_paired_standard_error_falls_with_the_item_count(small_policy):
    assert with_items(small_policy, 1200).paired_standard_error < (
        small_policy.paired_standard_error
    )


def test_the_paired_standard_error_matches_the_formula(small_policy):
    expected = (2.0**0.5) * small_policy.noise.run_sd / (small_policy.evaluation.items**0.5)
    assert small_policy.paired_standard_error == pytest.approx(expected)


def test_the_resolution_floor_is_one_over_the_replications(small_policy):
    assert small_policy.resolution_floor == pytest.approx(1 / 60)


def test_changing_the_item_count_changes_nothing_else(small_policy):
    switched = with_items(small_policy, 900)
    assert switched.evaluation.items == 900
    assert switched.gate == small_policy.gate
    assert switched.churn == small_policy.churn
    assert switched.evaluation.replications == small_policy.evaluation.replications


def test_a_tiny_item_override_is_refused(small_policy):
    with pytest.raises(PolicyError, match="at least 10"):
        with_items(small_policy, 3)


def test_a_policy_is_frozen(small_policy):
    with pytest.raises(AttributeError):
        small_policy.gate.alpha = 0.5


def test_a_non_numeric_probability_is_refused(minimal_policy_mapping):
    minimal_policy_mapping["gate"]["alpha"] = "loose"
    with pytest.raises(PolicyError, match="must be a number"):
        policy_from_mapping(minimal_policy_mapping)
