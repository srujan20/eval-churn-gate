"""Every published figure must agree on a second run of the same command.

A repository that claims its numbers are re-measured by CI needs the second
measurement to match the first. Thread count, hash seed and wall clock are the
three usual culprits and none of them may appear in a result. The bootstrap is the
live risk here: a resampler seeded from anything other than the comparison itself
would give a different interval on every run.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys

import numpy as np
import pytest

from churngate.audit import audit
from churngate.gates import run_all, run_gate
from churngate.pipeline import sweep
from churngate.runs import SCENARIOS, make_comparison


def test_two_sweeps_agree_row_for_row(small_policy):
    left = sweep(small_policy, replications=6)
    right = sweep(small_policy, replications=6)
    assert [row.as_dict() for row in left] == [row.as_dict() for row in right]


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_a_comparison_is_identical_across_two_builds(small_policy, scenario):
    left = make_comparison(scenario, small_policy, 21)
    right = make_comparison(scenario, small_policy, 21)
    assert np.array_equal(left.baseline.scores, right.baseline.scores)
    assert np.array_equal(left.candidate.scores, right.candidate.scores)


def test_the_bootstrap_does_not_move_with_the_thread_count(small_policy, uniform, monkeypatch):
    baseline = run_gate("paired_bootstrap", uniform, small_policy).statistic
    monkeypatch.setenv("OMP_NUM_THREADS", "1")
    assert run_gate("paired_bootstrap", uniform, small_policy).statistic == baseline


def test_every_gate_decides_the_same_way_twice(small_policy, compensating):
    left = run_all(compensating, small_policy)
    right = run_all(compensating, small_policy)
    assert {name: item.as_dict() for name, item in left.items()} == {
        name: item.as_dict() for name, item in right.items()
    }


def test_an_audit_of_the_same_comparison_agrees(small_policy, compensating):
    assert audit(compensating, small_policy).as_dict() == (
        audit(compensating, small_policy).as_dict()
    )


def test_a_result_does_not_move_with_the_hash_seed(tmp_path):
    """Two gate runs in fresh interpreters with different hash seeds must agree."""
    policy = tmp_path / "policy.yaml"
    policy.write_text(
        "gate:\n  mean_drop: 0.02\n  alpha: 0.05\n  power: 0.8\n"
        "  bootstrap_resamples: 400\n"
        "churn:\n  pass_threshold: 0.5\n  flip_rate_limit: 0.17\n"
        "  minimum_movement: 0.01\n"
        "evaluation:\n  items: 120\n  item_sweep: [100, 300]\n  replications: 30\n"
        "noise:\n  run_sd: 0.06\n  item_sd: 0.22\n",
        encoding="utf-8",
    )
    outputs = []
    for seed in ("0", "556677"):
        environment = dict(os.environ, PYTHONHASHSEED=seed)
        target = tmp_path / f"out-{seed}.json"
        subprocess.run(
            [
                sys.executable,
                "-m",
                "churngate",
                "gate",
                "--scenario",
                "compensating",
                "--policy",
                str(policy),
                "--json",
                str(target),
            ],
            env=environment,
            capture_output=True,
            check=False,
        )
        outputs.append(json.loads(target.read_text(encoding="utf-8")))
    assert outputs[0] == outputs[1]
