"""Experiment 1: what every gate does when the true effect is exactly zero.

The anchor. An A/A comparison is the same version scored twice, so the true effect
is not approximately zero, it is zero by construction. Every block a gate issues
here is a false block, and every point of churn it observes is noise.

That gives three numbers no gate publishes about itself: its own false block rate,
the churn floor below which an observed flip rate means nothing, and the share of
comparisons where the honest answer is that the eval set cannot tell.

The third is the one worth arguing about. A conventional gate returns pass on
almost all of these, and a pass reads as evidence of no regression when it is the
absence of evidence either way.

Run: python experiments/exp01_the_gate_graded_against_nothing.py
"""

from __future__ import annotations

import numpy as np
from _shared import (
    GATE_NAMES,
    REPO,
    VERDICTS,
    block_rate,
    main_sweep,
    pct,
    setup,
    table,
    verdict_rate,
    write_result,
)

NAME = "exp01-the-gate-graded-against-nothing"


def main() -> None:
    policy = setup()
    rows = main_sweep(policy)
    aa = [row for row in rows if row.scenario == "aa"]
    if not aa:
        raise SystemExit("the sweep contains no A/A comparisons")
    for row in aa:
        if row.true_effect != 0.0 or not row.truth_is_exact:
            raise SystemExit("an A/A row carried a non zero or estimated truth, which is a bug")

    false_block = {gate: block_rate(rows, gate, scenario="aa") for gate in GATE_NAMES}
    verdicts = {name: verdict_rate(rows, name, scenario="aa") for name in VERDICTS}
    flips = np.array([row.flip_rate for row in aa], dtype=float)
    hidden = np.array([row.hidden_share for row in aa], dtype=float)
    deltas = np.array([row.observed_delta for row in aa], dtype=float)

    print(f"{NAME}: {len(aa)} comparisons whose true effect is exactly zero")
    print()
    print(
        table(
            ["gate", "false block rate", "reads", "distinguishable from alpha"],
            [
                [
                    gate,
                    false_block[gate].render(),
                    "two numbers" if gate == "mean_threshold" else "per item",
                    "yes" if false_block[gate].excludes(policy.gate.alpha) else "no",
                ]
                for gate in GATE_NAMES
            ],
        )
    )
    print()
    print(
        "the last column is the discipline that matters. An early run of this suite "
        "measured 0.084 for a test whose true level is 0.05, at two hundred and fifty "
        "replications, and the interval is what stops that being read as a finding"
    )

    print()
    print(
        table(
            ["quantity", "value"],
            [
                ["median flip rate under no change", f"{float(np.median(flips)):.4f}"],
                ["ninety fifth percentile", f"{float(np.quantile(flips, 0.95)):.4f}"],
                ["worst observed", f"{float(flips.max()):.4f}"],
                ["configured flip limit", f"{policy.churn.flip_rate_limit:.4f}"],
                [
                    "median share of that movement the net cancels",
                    f"{float(np.median(hidden)):.4f}",
                ],
                ["standard deviation of the observed delta", f"{float(deltas.std()):.4f}"],
                ["predicted from the noise parameters", f"{policy.paired_standard_error:.4f}"],
            ],
        )
    )
    print()
    print(
        f"run to run variation alone moves {pct(float(np.median(flips)))} of items across the "
        f"pass boundary. The first flip limit in this repository was 0.06, written from "
        f"intuition, and it blocked every one of these comparisons"
    )

    print()
    print(
        table(
            ["verdict", "share"],
            [[name, verdicts[name].render()] for name in VERDICTS],
        )
    )
    print()
    print(
        "a gate with only pass and block would have returned pass on nearly all of these. "
        "The honest answer is that the eval set cannot resolve a difference this small, "
        "which is a different statement and a different exit code"
    )

    payload = {
        "experiment": NAME,
        "question": "what does each gate do when there is provably nothing to find",
        "comparisons": len(aa),
        "why_this_is_exact": (
            "an A/A comparison is the same version scored twice, so the noiseless scores "
            "are identical and the true effect is zero by construction rather than by "
            "measurement"
        ),
        "false_block_rates": {gate: false_block[gate].as_dict() for gate in GATE_NAMES},
        "distinguishable_from_alpha": {
            gate: false_block[gate].excludes(policy.gate.alpha) for gate in GATE_NAMES
        },
        "alpha": policy.gate.alpha,
        "verdicts": {name: verdicts[name].as_dict() for name in VERDICTS},
        "churn_floor": {
            "median": float(np.median(flips)),
            "p95": float(np.quantile(flips, 0.95)),
            "max": float(flips.max()),
            "configured_limit": policy.churn.flip_rate_limit,
            "first_limit_written_by_hand": 0.06,
        },
        "median_hidden_share": float(np.median(hidden)),
        "observed_delta_sd": float(deltas.std()),
        "predicted_delta_sd": policy.paired_standard_error,
    }
    print()
    print(f"wrote {write_result(NAME, payload).relative_to(REPO)}")


if __name__ == "__main__":
    main()
