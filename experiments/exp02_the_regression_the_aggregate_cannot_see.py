"""Experiment 2: a slice collapses, the aggregate does not move, who notices.

The impossibility made concrete. One slice of the eval set loses about a tenth of
a point and the other three gain just enough to pay for it, so the difference of
means is close to zero while a quarter of the items have become materially worse.

Three of the five gates are functions of the aggregate or of quantities dominated
by it, and they cannot see this. One can, and the reason it can is not cleverness:
it looks at a partition rather than at a total.

The churn gate is the interesting failure. It counts crossings rather than
differencing them, so in principle it sees compensating movement. In practice a
slice losing a tenth of a point moves few enough items across the pass boundary to
disappear into the run to run floor exp01 measured, and its threshold has to sit
above that floor or it blocks on noise. Two blind spots, two different gates, both
measured.

Run: python experiments/exp02_the_regression_the_aggregate_cannot_see.py
"""

from __future__ import annotations

import numpy as np
from _shared import (
    GATE_NAMES,
    REPO,
    VERDICTS,
    block_rate,
    main_sweep,
    setup,
    table,
    verdict_rate,
    write_result,
)

NAME = "exp02-the-regression-the-aggregate-cannot-see"


def main() -> None:
    policy = setup()
    rows = main_sweep(policy)
    compensating = [row for row in rows if row.scenario == "compensating"]
    churn_only = [row for row in rows if row.scenario == "churn_only"]
    if not compensating or not churn_only:
        raise SystemExit("the sweep is missing one of the zero aggregate scenarios")

    aggregate = np.array([row.observed_delta for row in compensating], dtype=float)
    slice_effect = np.array([row.subgroup_effect for row in compensating], dtype=float)
    detection = {gate: block_rate(rows, gate, scenario="compensating") for gate in GATE_NAMES}
    churn_detection = {gate: block_rate(rows, gate, scenario="churn_only") for gate in GATE_NAMES}
    false_block = {gate: block_rate(rows, gate, scenario="aa") for gate in GATE_NAMES}

    print(f"{NAME}: {len(compensating)} comparisons with a collapsed slice and no aggregate move")
    print()
    print(
        table(
            ["quantity", "median", "worst"],
            [
                [
                    "aggregate delta",
                    f"{float(np.median(aggregate)):+.4f}",
                    f"{float(np.min(aggregate)):+.4f}",
                ],
                [
                    "true effect on the losing slice",
                    f"{float(np.median(slice_effect)):+.4f}",
                    f"{float(np.min(slice_effect)):+.4f}",
                ],
            ],
        )
    )
    print()
    print(
        table(
            ["gate", "sees the collapsed slice", "sees pure churn", "false blocks on A/A"],
            [
                [
                    gate,
                    detection[gate].render(),
                    churn_detection[gate].render(),
                    false_block[gate].render(),
                ]
                for gate in GATE_NAMES
            ],
        )
    )
    print()
    aggregate_gates = ("mean_threshold", "paired_t", "paired_bootstrap")
    for gate in aggregate_gates:
        print(
            f"  {gate} sees the collapsed slice {detection[gate].render()} of the time, "
            f"against a false block rate of {false_block[gate].render()}. It is not detecting "
            "anything, it is firing at its own noise rate"
        )
    print()
    print(
        table(
            ["scenario", *VERDICTS],
            [
                [
                    scenario,
                    *[verdict_rate(rows, name, scenario=scenario).render() for name in VERDICTS],
                ]
                for scenario in ("compensating", "churn_only")
            ],
        )
    )

    payload = {
        "experiment": NAME,
        "question": "who notices a regression the aggregate cannot represent",
        "compensating_comparisons": len(compensating),
        "churn_only_comparisons": len(churn_only),
        "median_aggregate_delta": float(np.median(aggregate)),
        "worst_aggregate_delta": float(np.min(aggregate)),
        "median_slice_effect": float(np.median(slice_effect)),
        "worst_slice_effect": float(np.min(slice_effect)),
        "detection_compensating": {gate: detection[gate].as_dict() for gate in GATE_NAMES},
        "detection_churn_only": {gate: churn_detection[gate].as_dict() for gate in GATE_NAMES},
        "false_block_aa": {gate: false_block[gate].as_dict() for gate in GATE_NAMES},
        "aggregate_gates_indistinguishable_from_noise": [
            gate
            for gate in aggregate_gates
            if not detection[gate].excludes(false_block[gate].value)
        ],
        "verdicts": {
            scenario: {
                name: verdict_rate(rows, name, scenario=scenario).as_dict() for name in VERDICTS
            }
            for scenario in ("compensating", "churn_only")
        },
    }
    print()
    print(f"wrote {write_result(NAME, payload).relative_to(REPO)}")


if __name__ == "__main__":
    main()
