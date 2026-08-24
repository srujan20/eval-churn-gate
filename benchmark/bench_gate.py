"""Time one gated comparison as the eval set grows.

What a caller experiences is a single verdict on a single comparison, so that is
what this times: one call to `run_all`, which is every gate on one comparison,
measured one at a time rather than batched. Batching would flatter the numbers
and describe nothing anyone does.

Two design notes, both of which cost accuracy if you get them wrong.

The comparison is built outside the timed region. Building it draws three normal
vectors, which at a hundred thousand items is a measurable fraction of the gate
cost, and it is not work the gate does: in production the two score vectors
arrive from an eval harness that already ran. Timing construction would have
reported the random number generator as a property of the gate.

The bootstrap resample count is held at the shipped value rather than scaled
down at the large sizes. The paired bootstrap is the dominant term and it is
linear in items times resamples, so scaling it down would hide the exact thing
this benchmark exists to show.

Usage:
    python benchmark/bench_gate.py [--repeats 7] [--out benchmark/results/gate_latency.json]
"""

from __future__ import annotations

import argparse
import json
import platform
import statistics
import sys
import time
from dataclasses import replace
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from churngate.config import load_policy  # noqa: E402
from churngate.gates import GATES, run_all  # noqa: E402
from churngate.runs import make_comparison  # noqa: E402

# 300 is the shipped eval set size, so the first row is the configuration
# every rate in the README was measured at rather than a round number.
SIZES = (300, 500, 1000, 2000, 5000, 10000, 20000)
DEFAULT_OUT = REPO / "benchmark/results/gate_latency.json"


def percentile(values: list[float], fraction: float) -> float:
    """Nearest rank percentile, so a reported value is always one that was measured.

    Interpolating between two samples reports a duration nothing took, which for
    a latency table is a small lie that is easy to avoid.
    """
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round(fraction * (len(ordered) - 1))))
    return ordered[index]


def time_call(function, *args, repeats: int) -> list[float]:
    """Times `repeats` calls after one untimed warm up call.

    The warm up is not a courtesy. numpy allocates its scratch buffers and the
    interpreter resolves the call path on the first invocation, and including
    that made the first repeat several times the median, which then became the
    p95 of a seven sample set. Discarding it is standard practice and it is
    stated here because a benchmark that quietly drops a sample is worse than one
    that does not.
    """
    function(*args)
    durations = []
    for _ in range(repeats):
        start = time.perf_counter()
        function(*args)
        durations.append((time.perf_counter() - start) * 1000.0)
    return durations


def measure(repeats: int) -> dict[str, object]:
    policy = load_policy(REPO / "configs/policy.yaml")
    rows = []
    for items in SIZES:
        sized = replace(policy, evaluation=replace(policy.evaluation, items=items))
        # Built once, outside the timed region, and reused across repeats so every
        # repeat times the same arithmetic on the same numbers.
        comparison = make_comparison("compensating", sized, seed=101)
        durations = time_call(run_all, comparison, sized, repeats=repeats)
        per_gate = {
            name: statistics.median(time_call(gate, comparison, sized, repeats=repeats))
            for name, gate in GATES.items()
        }
        # `combined` runs the other gates, so including it in this comparison would
        # only ever report that the sum of the parts is larger than any one part.
        # The question worth asking is which primitive gate dominates.
        primitives = {name: value for name, value in per_gate.items() if name != "combined"}
        slowest = max(primitives, key=primitives.get)
        rows.append(
            {
                "items": items,
                "slices": len(set(comparison.baseline.slices)),
                "p50_ms": round(percentile(durations, 0.50), 3),
                "p95_ms": round(percentile(durations, 0.95), 3),
                "p99_ms": round(percentile(durations, 0.99), 3),
                "slowest_gate": slowest,
                "slowest_gate_ms": round(primitives[slowest], 3),
                "slowest_gate_share": round(primitives[slowest] / statistics.median(durations), 3),
                "per_gate_ms": {name: round(value, 3) for name, value in per_gate.items()},
                # The paired bootstrap materialises a resamples by items matrix of
                # float64. Reported because it, not the arithmetic, is what widens
                # the tail at the top of this table.
                "bootstrap_matrix_mb": round(
                    sized.gate.bootstrap_resamples * items * 8 / 1024 / 1024, 1
                ),
            }
        )
        print(
            f"  {items:>6} items  p50 {rows[-1]['p50_ms']:>8.3f} ms"
            f"  p95 {rows[-1]['p95_ms']:>8.3f} ms"
            f"  slowest {slowest} at {rows[-1]['slowest_gate_share']:.2f} of the total"
        )

    first, last = rows[0], rows[-1]
    growth = (last["p50_ms"] / first["p50_ms"]) / (last["items"] / first["items"])
    return {
        "hardware": {
            "python": platform.python_version(),
            "machine": platform.machine(),
            "platform": platform.system(),
        },
        "policy": {
            "bootstrap_resamples": policy.gate.bootstrap_resamples,
            "shipped_items": policy.evaluation.items,
        },
        "repeats": repeats,
        "rows": rows,
        # A value near 1.0 says the cost is linear in the item count. Reported as a
        # ratio rather than asserted in prose so a change in the dominant gate
        # shows up here instead of quietly contradicting the README.
        "linearity": round(growth, 3),
        "p99_over_p50_at_largest": round(last["p99_ms"] / last["p50_ms"], 3),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repeats", type=int, default=15)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args(argv)

    print(f"timing one gated comparison at {len(SIZES)} sizes, {args.repeats} repeats each")
    payload = measure(args.repeats)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {args.out.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
