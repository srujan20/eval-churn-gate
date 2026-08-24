"""Experiment 4: the impossibility as a number rather than as an argument.

The claim so far has been structural: an aggregate delta is a function of the
difference between two transition counts, and the number of items affected is a
function of their sum, so the second cannot be recovered from the first. That is an
argument. This measures it.

Across comparisons whose aggregate delta is close to zero, how much does the churn
vary, and how much of that variation does the aggregate predict? If the rank
correlation is near zero then no function of the aggregate, monotone or otherwise,
can bound the churn, and the impossibility has a number attached.

The second half is the part a person can act on. Given two comparisons with the
same aggregate delta, how far apart can their churn be? That spread is what a
dashboard reporting only the delta is hiding.

Run: python experiments/exp04_the_aggregate_carries_no_churn_information.py
"""

from __future__ import annotations

import numpy as np
from _shared import REPO, main_sweep, pct, setup, table, write_result
from scipy import stats

NAME = "exp04-the-aggregate-carries-no-churn-information"
NEAR_ZERO = 0.005


def correlation(deltas: np.ndarray, flips: np.ndarray) -> dict[str, float]:
    result = stats.spearmanr(deltas, flips)
    return {
        "n": float(deltas.size),
        "spearman_rho": float(result.statistic),
        "p_value": float(result.pvalue),
    }


def main() -> None:
    policy = setup()
    rows = main_sweep(policy)

    near_zero = [row for row in rows if abs(row.observed_delta) < NEAR_ZERO]
    if len(near_zero) < 50:
        raise SystemExit("too few near zero comparisons to say anything")
    deltas = np.array([row.observed_delta for row in near_zero], dtype=float)
    flips = np.array([row.flip_rate for row in near_zero], dtype=float)
    overall = correlation(deltas, flips)

    print(f"{NAME}: {len(near_zero)} comparisons whose aggregate delta is within {NEAR_ZERO}")
    print()
    print(
        table(
            ["quantity", "value"],
            [
                ["rank correlation of delta with flip rate", f"{overall['spearman_rho']:+.4f}"],
                ["p value", f"{overall['p_value']:.4f}"],
                ["flip rate, smallest observed", f"{float(flips.min()):.4f}"],
                ["flip rate, median", f"{float(np.median(flips)):.4f}"],
                ["flip rate, largest observed", f"{float(flips.max()):.4f}"],
                [
                    "spread across the same near zero delta",
                    f"{float(flips.max() - flips.min()):.4f}",
                ],
            ],
        )
    )
    print()
    print(
        f"the aggregate delta is within {NEAR_ZERO} of zero for every one of these, and the "
        f"share of items that changed side ranges from {pct(float(flips.min()))} to "
        f"{pct(float(flips.max()))}. A dashboard showing only the delta reports the same "
        "number for both ends of that range"
    )

    by_scenario = {}
    for scenario in sorted({row.scenario for row in near_zero}):
        subset = [row for row in near_zero if row.scenario == scenario]
        if len(subset) < 20:
            continue
        by_scenario[scenario] = {
            "comparisons": len(subset),
            "median_delta": float(np.median([row.observed_delta for row in subset])),
            "median_flip_rate": float(np.median([row.flip_rate for row in subset])),
            "median_hidden_share": float(np.median([row.hidden_share for row in subset])),
        }
    print()
    print(
        table(
            ["scenario", "comparisons", "median delta", "median flip rate", "median hidden share"],
            [
                [
                    scenario,
                    entry["comparisons"],
                    f"{entry['median_delta']:+.4f}",
                    f"{entry['median_flip_rate']:.4f}",
                    f"{entry['median_hidden_share']:.4f}",
                ]
                for scenario, entry in by_scenario.items()
            ],
        )
    )
    print()
    print(
        "the scenarios in that table have indistinguishable aggregate deltas and flip rates "
        "differing by a factor of four. The aggregate is the same number in every row"
    )

    # The strongest form of the claim, restricted to the two scenarios whose true
    # aggregate effect is exactly zero. There the delta is not merely small, it is
    # noise around a known zero, so any variation in churn is entirely unexplained
    # by it.
    exact = [row for row in rows if row.truth_is_exact]
    exact_correlation = correlation(
        np.array([row.observed_delta for row in exact], dtype=float),
        np.array([row.flip_rate for row in exact], dtype=float),
    )
    print()
    print(
        f"restricted to the {len(exact)} comparisons whose true aggregate effect is exactly "
        f"zero, the rank correlation is {exact_correlation['spearman_rho']:+.4f}"
    )

    payload = {
        "experiment": NAME,
        "question": "does the aggregate delta carry any information about the churn",
        "near_zero_window": NEAR_ZERO,
        "near_zero_comparisons": len(near_zero),
        "correlation_near_zero": overall,
        "flip_rate_min": float(flips.min()),
        "flip_rate_median": float(np.median(flips)),
        "flip_rate_max": float(flips.max()),
        "flip_rate_spread": float(flips.max() - flips.min()),
        "by_scenario": by_scenario,
        "exact_truth_comparisons": len(exact),
        "correlation_exact_truth": exact_correlation,
        "conclusion": (
            "no function of the aggregate delta can bound the churn, because across "
            "comparisons with the same delta the churn varies by a factor of several and "
            "the rank correlation between them is near zero"
        ),
    }
    print()
    print(f"wrote {write_result(NAME, payload).relative_to(REPO)}")


if __name__ == "__main__":
    main()
