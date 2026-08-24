"""Experiment 5: the gate worth shipping, and what it costs.

Every gate here is a trade between missing a regression and blocking a release
that was fine. The combined gate blocks when any of three conditions fires, which
detects more and blocks more, and this puts numbers on both sides rather than
recommending it and hoping.

The discipline of ADR-005 applies throughout. Every rate carries a Wilson interval,
a measured zero is reported with the floor its sample supports, and the one claim
that needs an interval to be checked, whether a false block rate is
distinguishable from the nominal significance level, is checked rather than eyeballed.

The last table is the recommendation, and it is a table rather than a sentence
because which gate to ship depends on which mistake costs more, and this repository
does not know that about anybody's pipeline.

Run: python experiments/exp05_what_the_combined_gate_costs.py
"""

from __future__ import annotations

from _shared import (
    GATE_NAMES,
    REPO,
    Rate,
    block_rate,
    main_sweep,
    pct,
    setup,
    table,
    write_result,
)

NAME = "exp05-what-the-combined-gate-costs"
REGRESSIONS = ("uniform", "compensating", "churn_only")
CLEAN = ("aa", "improvement")
CLAIMS = (0.05, 0.01, 0.001)


def main() -> None:
    policy = setup()
    rows = main_sweep(policy)

    summary = {}
    for gate in GATE_NAMES:
        caught = sum(
            block_rate(rows, gate, scenario=scenario).numerator for scenario in REGRESSIONS
        )
        regression_total = sum(
            block_rate(rows, gate, scenario=scenario).denominator for scenario in REGRESSIONS
        )
        blocked_clean = sum(
            block_rate(rows, gate, scenario=scenario).numerator for scenario in CLEAN
        )
        clean_total = sum(
            block_rate(rows, gate, scenario=scenario).denominator for scenario in CLEAN
        )
        summary[gate] = {
            "detection": Rate(caught, regression_total),
            "false_block": Rate(blocked_clean, clean_total),
        }

    print(f"{NAME}: over {len(rows)} gated comparisons")
    print()
    print(
        table(
            ["gate", "catches a real regression", "blocks a clean release", "scenarios missed"],
            [
                [
                    gate,
                    summary[gate]["detection"].render(),
                    summary[gate]["false_block"].render(),
                    ", ".join(
                        scenario
                        for scenario in REGRESSIONS
                        if block_rate(rows, gate, scenario=scenario).value < 0.5
                    )
                    or "none",
                ]
                for gate in GATE_NAMES
            ],
        )
    )

    print()
    print("what the third condition costs, stated as the difference it makes")
    interval_only = block_rate(rows, "paired_bootstrap", scenario="aa")
    combined = block_rate(rows, "combined", scenario="aa")
    print(
        f"  the paired interval alone blocks {interval_only.render()} of clean A/A "
        f"comparisons, and the combined gate blocks {combined.render()}. That is the price "
        "of catching the two scenarios the interval misses entirely"
    )
    print(
        f"  the combined false block rate is "
        f"{'distinguishable' if combined.excludes(policy.gate.alpha) else 'not distinguishable'} "
        f"from the nominal {policy.gate.alpha} at ninety five percent confidence"
    )

    print()
    zeros = {
        gate: summary[gate]["false_block"]
        for gate in GATE_NAMES
        if summary[gate]["false_block"].is_measured_zero
    }
    if zeros:
        print("gates that blocked no clean release at all, with what that supports")
        print(
            table(
                ["gate", "blocked", "of", "supports", *[f"needs for {claim}" for claim in CLAIMS]],
                [
                    [
                        gate,
                        rate.numerator,
                        rate.denominator,
                        f"below {pct(rate.floor, 2)}",
                        *[rate.samples_needed_for(claim) for claim in CLAIMS],
                    ]
                    for gate, rate in zeros.items()
                ],
            )
        )
    else:
        print("every gate blocked at least one clean release, so no measured zero to qualify")

    print()
    print(
        table(
            ["if the expensive mistake is", "ship this", "because"],
            [
                [
                    "shipping a regression",
                    "combined",
                    f"catches {summary['combined']['detection'].render()} at a false block "
                    f"rate of {summary['combined']['false_block'].render()}",
                ],
                [
                    "blocking a good release",
                    "churn",
                    f"blocks only {summary['churn']['false_block'].render()} and still "
                    f"catches {summary['churn']['detection'].render()}",
                ],
                [
                    "a regression in one slice",
                    "slice_scan",
                    "the only single gate that sees a collapsed slice",
                ],
                [
                    "nothing, you have no budget",
                    "not mean_threshold",
                    f"it catches {summary['mean_threshold']['detection'].render()} across "
                    "the three regression scenarios",
                ],
            ],
        )
    )

    payload = {
        "experiment": NAME,
        "question": "which gate to ship, and what each one costs",
        "comparisons": len(rows),
        "regression_scenarios": list(REGRESSIONS),
        "clean_scenarios": list(CLEAN),
        "summary": {
            gate: {
                "detection": summary[gate]["detection"].as_dict(),
                "false_block": summary[gate]["false_block"].as_dict(),
                "scenarios_missed": [
                    scenario
                    for scenario in REGRESSIONS
                    if block_rate(rows, gate, scenario=scenario).value < 0.5
                ],
            }
            for gate in GATE_NAMES
        },
        "interval_only_false_block": interval_only.as_dict(),
        "combined_false_block": combined.as_dict(),
        "combined_distinguishable_from_alpha": combined.excludes(policy.gate.alpha),
        "alpha": policy.gate.alpha,
        "measured_zeros": {
            gate: {
                "rate": rate.as_dict(),
                "samples_needed": {f"{claim}": rate.samples_needed_for(claim) for claim in CLAIMS},
            }
            for gate, rate in zeros.items()
        },
    }
    print()
    print(f"wrote {write_result(NAME, payload).relative_to(REPO)}")


if __name__ == "__main__":
    main()
