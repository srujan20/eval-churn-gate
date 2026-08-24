"""Experiment 3: the smallest regression this eval set can detect, and the coin flip.

Two results, and the second is the one that should change a threshold somewhere.

The first is arithmetic. The smallest regression detectable at the configured power
falls as the square root of the item count, and it falls four times faster when the
comparison is made item by item rather than between two averages. Pairing costs
nothing but keeping the per item scores, which most pipelines already have and then
average away before writing them down.

The second is a property of a threshold gate that the arithmetic predicts and this
measures. A gate that blocks when the observed delta falls below minus tau detects
a true regression of exactly tau about half the time, because the observed value
lands either side of the threshold with equal probability. A gate set at the size
of the thing it is meant to catch is a coin flip on that thing.

Run: python experiments/exp03_what_the_eval_set_can_resolve.py
"""

from __future__ import annotations

from _shared import REPO, effect_sweep, setup, table, write_result

from churngate.config import with_items
from churngate.gates import items_needed_for, minimum_detectable_effect
from churngate.pipeline import block_rate

NAME = "exp03-what-the-eval-set-can-resolve"


def main() -> None:
    policy = setup()
    sizes = policy.evaluation.item_sweep

    power_rows = []
    for items in sizes:
        sized = with_items(policy, items)
        paired = minimum_detectable_effect(sized, paired=True)
        unpaired = minimum_detectable_effect(sized, paired=False)
        power_rows.append(
            {
                "items": items,
                "paired": paired,
                "unpaired": unpaired,
                "gain": unpaired / paired,
                "resolves_the_threshold": paired <= policy.gate.mean_drop,
            }
        )

    print(f"{NAME}: at {policy.gate.power:.0%} power and alpha {policy.gate.alpha}")
    print()
    print(
        table(
            ["items", "paired", "two averages", "pairing is worth", "resolves the threshold"],
            [
                [
                    row["items"],
                    f"{row['paired']:.4f}",
                    f"{row['unpaired']:.4f}",
                    f"{row['gain']:.1f}x",
                    "yes" if row["resolves_the_threshold"] else "no",
                ]
                for row in power_rows
            ],
        )
    )
    needed_paired = items_needed_for(policy, policy.gate.mean_drop, paired=True)
    needed_unpaired = items_needed_for(policy, policy.gate.mean_drop, paired=False)
    print()
    print(
        f"detecting the configured threshold of {policy.gate.mean_drop} needs "
        f"{needed_paired} items paired, or {needed_unpaired} comparing two averages. The "
        f"shipped eval set has {policy.evaluation.items}"
    )

    curves = effect_sweep(policy)
    print()
    detection_rows = []
    for effect, rows in sorted(curves.items()):
        detection_rows.append(
            [
                f"{effect:.3f}",
                block_rate(rows, "mean_threshold").render(),
                block_rate(rows, "paired_bootstrap").render(),
                block_rate(rows, "combined").render(),
            ]
        )
    print("detection rate against the size of a uniform regression")
    print(
        table(
            ["true drop", "mean threshold", "paired bootstrap", "combined"],
            detection_rows,
        )
    )

    at_threshold = curves.get(policy.gate.mean_drop)
    coin_flip = None
    if at_threshold is not None:
        coin_flip = block_rate(at_threshold, "mean_threshold")
        print()
        print(
            f"at a true drop of exactly {policy.gate.mean_drop}, the size the threshold was set "
            f"to catch, the mean threshold gate blocks {coin_flip.render()} of the time. The "
            "observed value lands either side of the threshold with equal probability, so a "
            "gate set at the size of the thing it is meant to catch is a coin flip on it"
        )

    payload = {
        "experiment": NAME,
        "question": "what can this eval set resolve, and what does a threshold gate detect",
        "alpha": policy.gate.alpha,
        "power": policy.gate.power,
        "shipped_items": policy.evaluation.items,
        "mean_drop": policy.gate.mean_drop,
        "power_by_items": power_rows,
        "items_needed_paired": needed_paired,
        "items_needed_unpaired": needed_unpaired,
        "detection_by_effect": {
            f"{effect:.3f}": {
                gate: block_rate(rows, gate).as_dict()
                for gate in ("mean_threshold", "paired_bootstrap", "combined")
            }
            for effect, rows in sorted(curves.items())
        },
        "coin_flip_at_the_threshold": None if coin_flip is None else coin_flip.as_dict(),
        "pairing_gain": power_rows[0]["gain"],
    }
    print()
    print(f"wrote {write_result(NAME, payload).relative_to(REPO)}")


if __name__ == "__main__":
    main()
