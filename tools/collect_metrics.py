"""Re-measure every published figure and write docs/metrics.json.

Nothing in this file types a number. It runs the test suite, reads the machine
readable reports it produces, runs all five experiments, reads their JSON, and
computes the derived values. `tools/check_numbers.py` then verifies that the
documents quote exactly these values.

Two details worth keeping. The test count and the coverage percentage come from
--junitxml and --cov-report=json rather than from parsing a progress line, because
a parsed progress line quietly becomes whatever the last run happened to print.
And every anchor phrase is checked for containing a placeholder, because an anchor
without one matches whatever the document says regardless of the value, which is a
guard that cannot fail.

Usage:
    python tools/collect_metrics.py [--skip-tests] [--skip-experiments]
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DOCS = REPO / "docs"
EXPERIMENTS = DOCS / "experiments"
REPORTS = REPO / "reports"

EXPERIMENT_SCRIPTS = (
    "exp01_the_gate_graded_against_nothing.py",
    "exp02_the_regression_the_aggregate_cannot_see.py",
    "exp03_what_the_eval_set_can_resolve.py",
    "exp04_the_aggregate_carries_no_churn_information.py",
    "exp05_what_the_combined_gate_costs.py",
)

# The exact wording a document must use with the value substituted in. Anchors are
# alternatives: one match is enough, because the same figure reads differently in a
# table and in a paragraph. Each anchor names the number plus two or three words,
# never a whole clause. The checker collapses whitespace before matching, so an
# anchor no longer has to be lucky about where a markdown line happened to break.
ANCHORS: dict[str, list[str]] = {
    "tests_total": ["{} tests"],
    "coverage_line_pct": ["{} percent line coverage", "{}% line coverage"],
    "comparisons": ["{} gated comparisons"],
    "aa_comparisons": ["{} comparisons whose true effect"],
    "items": ["{} item eval set", "eval set of {}"],
    "mean_threshold_detection": ["catches {} of"],
    "combined_detection": ["catches {}, at"],
    "combined_false_block": ["false block rate of {}"],
    "interval_false_block": ["blocks {} of clean"],
    "mean_threshold_on_compensating": ["sees it {} of the time"],
    "slice_scan_on_compensating": ["catches it {} of the time"],
    "churn_on_churn_only": ["catches that one {}"],
    "slice_scan_on_churn_only": ["only {} of it"],
    "undecidable_share": ["{} of the time the honest answer"],
    "aa_block_share": ["blocked {} of them"],
    "aa_pass_share": ["passed only {}"],
    "churn_floor_median": ["flips {} of items"],
    "churn_floor_p95": ["ninety fifth percentile of {}"],
    "flip_limit": ["a limit of {}"],
    "first_flip_limit": ["first value was {}"],
    "median_hidden_share": ["{} of that movement"],
    "observed_sd": ["standard deviation of {}"],
    "predicted_sd": ["predicted {} from"],
    "median_slice_effect": ["loses {} while the aggregate"],
    "median_aggregate_on_compensating": ["aggregate moves by {} in"],
    "correlation": ["rank correlation of {} in magnitude"],
    "correlation_p": ["a p value of {}"],
    "flip_min": ["from {} to"],
    "flip_max": ["to {} of items"],
    "near_zero_comparisons": ["{} comparisons whose delta"],
    "exact_comparisons": ["{} comparisons whose true aggregate"],
    "exact_correlation": ["correlation there is {} in magnitude"],
    "mde_paired": ["is {} paired"],
    "mde_unpaired": ["against {} when"],
    "pairing_gain": ["worth a factor of {}"],
    "items_needed_paired": ["needs {} items paired"],
    "items_needed_unpaired": ["or {} comparing two"],
    "coin_flip": ["catches it {} of the time it happens"],
    "detection_at_threshold_paired": ["against {} for the paired"],
    "mean_threshold_zero_floor": ["below {} percent"],
    "mean_threshold_zero_denominator": ["over {} clean releases"],
    "churn_detection": ["catches {} overall"],
    "churn_false_block": ["blocking only {}"],
    "bench_shipped_p50_ms": ["decides in {} ms"],
    "bench_shipped_p95_ms": ["p95 of {} ms"],
    "bench_largest_items": ["out to {} items"],
    "bench_largest_p50_ms": ["{} ms at the largest"],
    "bench_largest_p95_ms": ["p95 rises to {} ms"],
    "bench_linearity": ["a linearity ratio of {}"],
    "bench_tail_ratio": ["p99 is {} times p50"],
    "bench_bootstrap_share": ["{} of the total cost"],
    "bench_slice_scan_ms": ["slice scan costs {} ms"],
    "bench_mean_threshold_ms": ["mean threshold gate costs {} ms"],
    "bench_slice_scan_ratio": ["{} times cheaper than the total"],
    "bench_matrix_mb": ["allocates {} MB"],
    "bench_repeats": ["{} timed repeats"],
    "bench_python": ["Python {}"],
}

CELL_ANCHOR = ["| {} |"]


def run(command: list[str], *, cwd: Path = REPO) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=cwd, capture_output=True, text=True, check=False)


def run_tests() -> None:
    REPORTS.mkdir(parents=True, exist_ok=True)
    completed = run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            f"--junitxml={REPORTS / 'junit.xml'}",
            "--cov=churngate",
            "--cov-report=json:reports/coverage.json",
            "--cov-report=xml:reports/coverage.xml",
        ]
    )
    if completed.returncode != 0:
        sys.stderr.write(completed.stdout[-4000:])
        sys.stderr.write(completed.stderr[-4000:])
        raise SystemExit("the test suite failed, so no metrics were collected")


def read_test_reports() -> tuple[int, float]:
    junit = REPORTS / "junit.xml"
    coverage = REPORTS / "coverage.json"
    for path in (junit, coverage):
        if not path.is_file():
            raise SystemExit(
                f"{path.relative_to(REPO)} is missing. Run without --skip-tests, or run "
                "pytest with --junitxml and --cov-report=json first."
            )
    import xml.etree.ElementTree as ElementTree

    root = ElementTree.parse(junit).getroot()
    suite = root if root.tag == "testsuite" else root.find("testsuite")
    if suite is None:
        raise SystemExit("could not find a testsuite element in the junit report")
    payload = json.loads(coverage.read_text(encoding="utf-8"))
    return int(suite.get("tests", "0")), float(payload["totals"]["percent_covered"])


def run_experiments() -> None:
    for script in EXPERIMENT_SCRIPTS:
        completed = run([sys.executable, str(REPO / "experiments" / script)])
        if completed.returncode != 0:
            sys.stderr.write(completed.stdout[-4000:])
            sys.stderr.write(completed.stderr[-4000:])
            raise SystemExit(f"experiment {script} failed")


def load(name: str) -> dict:
    path = EXPERIMENTS / f"{name}.json"
    if not path.is_file():
        raise SystemExit(f"{path.relative_to(REPO)} is missing. Run without --skip-experiments.")
    return json.loads(path.read_text(encoding="utf-8"))


def three(value: float) -> float:
    return round(value, 3)


def ms(value: float) -> float:
    """A duration rounded for prose: one decimal above a millisecond, three below.

    The benchmark JSON keeps three decimals throughout. Rounding happens here, at
    the point where a number becomes a sentence, because "decides in 14.945 ms" is
    a false precision on a two vCPU container and "0.0 ms" would erase a gate that
    genuinely costs fifteen microseconds.
    """
    return round(value, 1) if value >= 1.0 else round(value, 3)


def four(value: float) -> float:
    return round(value, 4)


def build_metrics(*, skip_tests: bool, skip_experiments: bool) -> dict[str, object]:
    if not skip_tests:
        run_tests()
    tests_total, coverage = read_test_reports()
    if not skip_experiments:
        run_experiments()

    exp01 = load("exp01-the-gate-graded-against-nothing")
    exp02 = load("exp02-the-regression-the-aggregate-cannot-see")
    exp03 = load("exp03-what-the-eval-set-can-resolve")
    exp04 = load("exp04-the-aggregate-carries-no-churn-information")
    exp05 = load("exp05-what-the-combined-gate-costs")

    detection = exp02["detection_compensating"]
    churn_detection = exp02["detection_churn_only"]
    summary = exp05["summary"]
    at_threshold = exp03["detection_by_effect"][f"{exp03['mean_drop']:.3f}"]
    zero = exp05["measured_zeros"].get("mean_threshold")
    first_power = exp03["power_by_items"][1]
    # Read rather than re-run, and this is the one figure family in the registry
    # that is not re-measured on every push. A duration measured on a GitHub runner
    # is a different measurement from one measured on the machine the README
    # describes, so re-timing in CI would fail the check for the honest reason that
    # the hardware changed. The committed JSON is the measurement; `make bench`
    # rewrites it, and the diff is reviewed like any other file.
    latency = REPO / "benchmark/results/gate_latency.json"
    if not latency.is_file():
        raise SystemExit(
            f"{latency.relative_to(REPO)} is missing, so the latency table cannot be "
            "checked. Run: make bench"
        )
    bench = json.loads(latency.read_text(encoding="utf-8"))
    shipped_row = bench["rows"][0]
    largest_row = bench["rows"][-1]

    metrics: dict[str, object] = {
        "tests_total": tests_total,
        "coverage_line_pct": round(coverage, 1),
        "comparisons": exp05["comparisons"],
        "aa_comparisons": exp01["comparisons"],
        "items": exp03["shipped_items"],
        "mean_threshold_detection": three(summary["mean_threshold"]["detection"]["value"]),
        "combined_detection": three(summary["combined"]["detection"]["value"]),
        "combined_false_block": three(summary["combined"]["false_block"]["value"]),
        "interval_false_block": three(exp05["interval_only_false_block"]["value"]),
        "mean_threshold_on_compensating": three(detection["mean_threshold"]["value"]),
        "slice_scan_on_compensating": three(detection["slice_scan"]["value"]),
        "churn_on_churn_only": three(churn_detection["churn"]["value"]),
        "slice_scan_on_churn_only": three(churn_detection["slice_scan"]["value"]),
        "undecidable_share": three(exp01["verdicts"]["eval-set-cannot-resolve-this"]["value"]),
        "aa_block_share": three(exp01["verdicts"]["regression-detected"]["value"]),
        "aa_pass_share": three(exp01["verdicts"]["candidate-passes"]["value"]),
        "churn_floor_median": four(exp01["churn_floor"]["median"]),
        "churn_floor_p95": four(exp01["churn_floor"]["p95"]),
        "flip_limit": exp01["churn_floor"]["configured_limit"],
        "first_flip_limit": exp01["churn_floor"]["first_limit_written_by_hand"],
        "median_hidden_share": four(exp01["median_hidden_share"]),
        "observed_sd": four(exp01["observed_delta_sd"]),
        "predicted_sd": four(exp01["predicted_delta_sd"]),
        "median_slice_effect": four(abs(exp02["median_slice_effect"])),
        "median_aggregate_on_compensating": four(abs(exp02["median_aggregate_delta"])),
        "correlation": four(abs(exp04["correlation_near_zero"]["spearman_rho"])),
        "correlation_p": three(exp04["correlation_near_zero"]["p_value"]),
        "flip_min": four(exp04["flip_rate_min"]),
        "flip_max": four(exp04["flip_rate_max"]),
        "near_zero_comparisons": exp04["near_zero_comparisons"],
        "exact_comparisons": exp04["exact_truth_comparisons"],
        "exact_correlation": four(abs(exp04["correlation_exact_truth"]["spearman_rho"])),
        "mde_paired": four(first_power["paired"]),
        "mde_unpaired": four(first_power["unpaired"]),
        "pairing_gain": round(exp03["pairing_gain"], 1),
        "items_needed_paired": exp03["items_needed_paired"],
        "items_needed_unpaired": exp03["items_needed_unpaired"],
        "coin_flip": three(at_threshold["mean_threshold"]["value"]),
        "detection_at_threshold_paired": three(at_threshold["paired_bootstrap"]["value"]),
        "churn_detection": three(summary["churn"]["detection"]["value"]),
        "churn_false_block": three(summary["churn"]["false_block"]["value"]),
    }
    if zero is not None:
        metrics["mean_threshold_zero_floor"] = round(100 * zero["rate"]["resolution_floor"], 2)
        metrics["mean_threshold_zero_denominator"] = zero["rate"]["denominator"]

    # The tables in the README are one cell per gate. Guarding each cell with an
    # anchor that also pinned its row label would need the README to be generated
    # rather than written, so those cells carry the weaker claim that the value
    # appears as a table cell. The README says so rather than implying every guard
    # is equally strong.
    for gate, entry in summary.items():
        metrics[f"cell_{gate}_detection"] = three(entry["detection"]["value"])
        metrics[f"cell_{gate}_false_block"] = three(entry["false_block"]["value"])
    for gate, entry in detection.items():
        metrics[f"cell_{gate}_compensating"] = three(entry["value"])
    for gate, entry in churn_detection.items():
        metrics[f"cell_{gate}_churn_only"] = three(entry["value"])
    for gate, entry in exp01["false_block_rates"].items():
        metrics[f"cell_{gate}_aa"] = three(entry["value"])
    for row in exp03["power_by_items"]:
        metrics[f"cell_mde_{row['items']}_paired"] = four(row["paired"])
        metrics[f"cell_mde_{row['items']}_unpaired"] = four(row["unpaired"])
    for effect, entry in exp03["detection_by_effect"].items():
        key = effect.replace(".", "_")
        metrics[f"cell_effect_{key}_mean"] = three(entry["mean_threshold"]["value"])
        metrics[f"cell_effect_{key}_paired"] = three(entry["paired_bootstrap"]["value"])

    # The latency table. Every value is read from the benchmark's own JSON rather
    # than recomputed here, so the chart, the table and this registry are three
    # renderings of one measurement.
    metrics["bench_repeats"] = bench["repeats"]
    metrics["bench_python"] = bench["hardware"]["python"]
    metrics["bench_shipped_p50_ms"] = ms(shipped_row["p50_ms"])
    metrics["bench_shipped_p95_ms"] = ms(shipped_row["p95_ms"])
    metrics["bench_largest_items"] = largest_row["items"]
    metrics["bench_largest_p50_ms"] = ms(largest_row["p50_ms"])
    metrics["bench_largest_p95_ms"] = ms(largest_row["p95_ms"])
    metrics["bench_linearity"] = bench["linearity"]
    metrics["bench_tail_ratio"] = round(bench["p99_over_p50_at_largest"], 2)
    metrics["bench_bootstrap_share"] = largest_row["slowest_gate_share"]
    metrics["bench_slice_scan_ms"] = ms(largest_row["per_gate_ms"]["slice_scan"])
    metrics["bench_mean_threshold_ms"] = ms(largest_row["per_gate_ms"]["mean_threshold"])
    metrics["bench_slice_scan_ratio"] = int(
        round(largest_row["p50_ms"] / largest_row["per_gate_ms"]["slice_scan"])
    )
    metrics["bench_matrix_mb"] = largest_row["bootstrap_matrix_mb"]
    for row in bench["rows"]:
        metrics[f"cell_bench_{row['items']}_p50"] = ms(row["p50_ms"])
        metrics[f"cell_bench_{row['items']}_p95"] = ms(row["p95_ms"])
        metrics[f"cell_bench_{row['items']}_p99"] = ms(row["p99_ms"])
        metrics[f"cell_bench_{row['items']}_slice_scan"] = ms(row["per_gate_ms"]["slice_scan"])
        metrics[f"cell_bench_{row['items']}_matrix"] = row["bootstrap_matrix_mb"]

    for name in metrics:
        if name.startswith("cell_"):
            ANCHORS[name] = CELL_ANCHOR

    vacuous = sorted(
        name for name in metrics if any("{}" not in phrase for phrase in ANCHORS.get(name, ["{}"]))
    )
    if vacuous:
        raise SystemExit(
            "every anchor phrase must contain a placeholder, otherwise it matches any "
            "value. Offending metrics: " + ", ".join(vacuous)
        )

    missing_anchors = sorted(set(metrics) - set(ANCHORS))
    if missing_anchors:
        raise SystemExit(
            "every metric needs at least one anchor phrase, missing for: "
            + ", ".join(missing_anchors)
        )
    return metrics


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-tests", action="store_true")
    parser.add_argument("--skip-experiments", action="store_true")
    args = parser.parse_args(argv)

    metrics = build_metrics(skip_tests=args.skip_tests, skip_experiments=args.skip_experiments)
    payload = {
        "metrics": metrics,
        "anchors": {name: ANCHORS[name] for name in metrics},
        "checked_documents": [
            "README.md",
            "docs/adr/ADR-001-gate-on-transitions-not-only-on-the-aggregate.md",
            "docs/adr/ADR-002-the-aa-comparison-is-the-anchor.md",
            "docs/adr/ADR-003-three-verdicts-because-two-cannot-say-i-do-not-know.md",
            "docs/adr/ADR-004-no-optional-dependencies.md",
            "docs/adr/ADR-005-every-rate-carries-an-interval.md",
        ],
        # Checked when present, skipped when not. The defense guide is an
        # interview document rather than a deliverable, so a public checkout
        # may reasonably not carry it, and CI should not fail for that.
        "optional_documents": ["docs/defense-guide.md"],
        "note": "every value here is produced by running the suite and the five experiments",
    }
    destination = DOCS / "metrics.json"
    destination.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {destination.relative_to(REPO)} with {len(metrics)} metrics")
    for name, value in metrics.items():
        if not name.startswith("cell_"):
            print(f"  {name:<34} {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
