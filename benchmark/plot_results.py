"""Draw the latency chart from benchmark/results/gate_latency.json.

Nothing here computes a timing. It reads the JSON the benchmark wrote and draws
it, so the chart cannot disagree with the table in the README: both are rendered
from the same file, and `make bench` rewrites that file.

Matplotlib lives in the evidence extra, not in the runtime dependencies, for the
same reason Playwright does. A consumer running this gate in their own CI should
not install a plotting library to get an exit code.

Usage:
    python benchmark/plot_results.py
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
RESULTS = REPO / "benchmark/results/gate_latency.json"
DEFAULT_OUT = REPO / "docs/charts/gate-latency.png"

# Chosen for contrast against white at print size and against each other in
# greyscale, because a reader may be looking at a printed PDF of this repository.
INK = "#1c1c1a"
MUTED = "#6b6a66"
SERIES = {
    "p99_ms": ("#e34948", "combined gate, p99"),
    "p95_ms": ("#d98324", "combined gate, p95"),
    "p50_ms": ("#2a78d6", "combined gate, p50"),
}


def draw(payload: dict, out: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    rows = payload["rows"]
    items = [row["items"] for row in rows]

    figure, axes = plt.subplots(figsize=(9.0, 4.6), dpi=150)
    figure.patch.set_facecolor("white")
    axes.set_facecolor("white")

    for key, (colour, label) in SERIES.items():
        axes.plot(
            items,
            [row[key] for row in rows],
            marker="o",
            markersize=4,
            linewidth=1.8,
            color=colour,
            label=label,
        )

    # The slice scan is the one comparison worth drawing beside the total: it is the
    # gate that catches the regression this repository is about, and it costs two
    # orders of magnitude less than the total. The mean threshold gate is another
    # three decades below that and is left out of the chart on purpose. Plotting it
    # stretched the y axis over five decades and flattened the p50 to p99 spread
    # this chart exists to show. Its number is in the per gate table instead.
    axes.plot(
        items,
        [row["per_gate_ms"]["slice_scan"] for row in rows],
        marker="s",
        markersize=4,
        linewidth=1.6,
        linestyle="--",
        color="#1baf7a",
        label="slice scan alone, p50",
    )
    axes.set_xscale("log")
    axes.set_yscale("log")
    axes.set_xlabel("items in the eval set", color=INK)
    axes.set_ylabel("one gated comparison, milliseconds", color=INK)
    axes.set_title(
        "Cost of one verdict as the eval set grows"
        f"  ({payload['policy']['bootstrap_resamples']} bootstrap resamples,"
        f" {payload['repeats']} repeats, Python {payload['hardware']['python']})",
        color=INK,
        fontsize=10,
        loc="left",
    )
    axes.set_xticks(items)
    axes.set_xticklabels([f"{value:,}" for value in items], color=INK, fontsize=8)
    axes.tick_params(colors=INK, labelsize=8)
    axes.grid(True, which="major", linewidth=0.4, color="#d8d7d3")
    axes.grid(True, which="minor", linewidth=0.2, color="#ebeae7")
    for spine in ("top", "right"):
        axes.spines[spine].set_visible(False)
    for spine in ("left", "bottom"):
        axes.spines[spine].set_color(MUTED)

    shipped = rows[0]
    axes.annotate(
        f"shipped eval set: {shipped['items']} items, {shipped['p50_ms']:.1f} ms",
        xy=(shipped["items"], shipped["p50_ms"]),
        xytext=(shipped["items"] * 1.25, shipped["p50_ms"] * 0.22),
        color=INK,
        fontsize=8,
        arrowprops={"arrowstyle": "->", "color": MUTED, "linewidth": 0.8},
    )
    axes.legend(frameon=False, fontsize=8, labelcolor=INK, loc="upper left")
    figure.tight_layout()
    out.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(out, facecolor="white")
    plt.close(figure)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, default=RESULTS)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args(argv)

    if not args.results.is_file():
        raise SystemExit(f"no benchmark results at {args.results}, run: make bench")
    draw(json.loads(args.results.read_text(encoding="utf-8")), args.out)
    print(f"wrote {args.out.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
