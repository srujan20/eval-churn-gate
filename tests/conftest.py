"""Shared fixtures.

Every fixture is smaller than the shipped configuration. The properties under test
are properties of the code rather than of the replication count, and a suite that
takes four minutes gets run less often than one that takes thirty seconds.
"""

from __future__ import annotations

import numpy as np
import pytest

from churngate.config import Policy, load_policy, policy_from_mapping
from churngate.runs import Comparison, make_comparison

SMALL_MAPPING: dict[str, object] = {
    "gate": {
        "mean_drop": 0.02,
        "alpha": 0.05,
        "power": 0.80,
        "bootstrap_resamples": 400,
    },
    "churn": {
        "pass_threshold": 0.5,
        "flip_rate_limit": 0.17,
        "minimum_movement": 0.01,
    },
    "evaluation": {"items": 120, "item_sweep": [100, 300], "replications": 60},
    "noise": {"run_sd": 0.06, "item_sd": 0.22},
}


@pytest.fixture(scope="session")
def policy() -> Policy:
    return load_policy()


@pytest.fixture(scope="session")
def small_policy() -> Policy:
    return policy_from_mapping(SMALL_MAPPING, source="<small fixture>")


@pytest.fixture(scope="session")
def aa(small_policy: Policy) -> Comparison:
    return make_comparison("aa", small_policy, 11)


@pytest.fixture(scope="session")
def uniform(small_policy: Policy) -> Comparison:
    return make_comparison("uniform", small_policy, 11)


@pytest.fixture(scope="session")
def compensating(small_policy: Policy) -> Comparison:
    return make_comparison("compensating", small_policy, 11)


@pytest.fixture(scope="session")
def churn_only(small_policy: Policy) -> Comparison:
    return make_comparison("churn_only", small_policy, 11)


@pytest.fixture
def minimal_policy_mapping() -> dict[str, object]:
    import copy

    return copy.deepcopy(SMALL_MAPPING)


@pytest.fixture
def rng() -> np.random.Generator:
    return np.random.default_rng(24680)
