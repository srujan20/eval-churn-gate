"""The command line interface, and the exit codes it promises.

    0  the candidate passes, and the delta was large enough for that to mean
       something
    1  a regression was detected, and the report names which gate caught it
    2  nothing blocked and the observed delta is smaller than this eval set can
       resolve, so a human is needed
    3  the gate could not run: an eval set with no items, two runs scored on
       different items, a score outside the metric's range
    4  the invocation was wrong: an unknown scenario or gate, a policy that will
       not load

The separation between 0 and 2 is the whole point of the tool. A gate that returns
the same code for "the candidate passes" and "I could not tell" is a gate whose
green tick means nothing, and that is the most common way a regression reaches
production with a pass beside it.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from . import __version__
from .audit import audit
from .config import Policy, load_policy, with_items
from .errors import MissingDependencyError, PolicyError, UnanswerableError, UsageError
from .gates import (
    GATE_NAMES,
    items_needed_for,
    minimum_detectable_effect,
    run_gate,
)
from .pipeline import DEFAULT_EFFECT, block_rate, sweep, verdict_rate
from .report import render_html, render_sweep_html, render_text
from .runs import SCENARIOS, make_comparison

EXIT_UNANSWERABLE = 3
EXIT_USAGE = 4
VERDICTS = (
    "candidate-passes",
    "regression-detected",
    "eval-set-cannot-resolve-this",
)


def _write(path: str | None, payload: str) -> None:
    if path is None:
        return
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(payload, encoding="utf-8")


def _policy(args: argparse.Namespace) -> Policy:
    policy = load_policy(getattr(args, "policy", None))
    items = getattr(args, "items", None)
    if items:
        policy = with_items(policy, items)
    return policy


def command_power(args: argparse.Namespace) -> int:
    """What this eval set can resolve, before any comparison is run."""
    policy = _policy(args)
    rows = []
    for items in policy.evaluation.item_sweep:
        sized = with_items(policy, items)
        rows.append(
            {
                "items": items,
                "paired": minimum_detectable_effect(sized, paired=True),
                "unpaired": minimum_detectable_effect(sized, paired=False),
            }
        )
    if args.json:
        print(json.dumps(rows, indent=2))
        return 0
    print(
        f"smallest regression detectable at {policy.gate.power:.0%} power and "
        f"alpha {policy.gate.alpha}"
    )
    print()
    print(f"  {'items':>7}{'paired':>10}{'two averages':>15}{'pairing is worth':>18}")
    for row in rows:
        gain = row["unpaired"] / row["paired"]
        print(f"  {row['items']:>7}{row['paired']:>10.4f}{row['unpaired']:>15.4f}{gain:>17.1f}x")
    print()
    print(
        f"the configured mean threshold is {policy.gate.mean_drop}. Detecting it needs "
        f"{items_needed_for(policy, policy.gate.mean_drop, paired=True)} items paired, or "
        f"{items_needed_for(policy, policy.gate.mean_drop, paired=False)} comparing two "
        "averages"
    )
    return 0


def command_gate(args: argparse.Namespace) -> int:
    policy = _policy(args)
    comparison = make_comparison(args.scenario, policy, args.seed, effect=args.effect)
    result = audit(comparison, policy)
    print(render_text(result), end="")
    _write(args.html, render_html(result))
    if args.json:
        _write(args.json, json.dumps(result.as_dict(), indent=2) + "\n")
    return result.exit_code


def command_one(args: argparse.Namespace) -> int:
    """Run a single named gate, for a caller that wants one decision and one code."""
    policy = _policy(args)
    comparison = make_comparison(args.scenario, policy, args.seed, effect=args.effect)
    decision = run_gate(args.gate, comparison, policy)
    print(f"gate: {decision.gate}")
    print(f"blocked: {decision.blocked}")
    print(f"statistic: {decision.statistic:.6f}  threshold: {decision.threshold:.6f}")
    print(f"reads: {decision.reads}")
    if decision.note:
        print(f"note: {decision.note}")
    if decision.undecidable:
        print("this gate could not decide, which is not the same as a pass")
        return 2
    return 1 if decision.blocked else 0


def command_sweep(args: argparse.Namespace) -> int:
    policy = _policy(args)
    rows = sweep(
        policy,
        scenarios=tuple(args.scenarios),
        replications=args.replications,
        effect=args.effect,
    )
    scenarios = tuple(args.scenarios)
    per_scenario = args.replications or policy.evaluation.replications
    print(f"{len(rows)} gated comparisons, {per_scenario} per scenario")
    print()
    header = f"  {'scenario':<14}" + "".join(f"{gate:>22}" for gate in GATE_NAMES)
    print(header)
    for scenario in scenarios:
        line = f"  {scenario:<14}"
        for gate in GATE_NAMES:
            line += f"{block_rate(rows, gate, scenario=scenario).render():>22}"
        print(line)
    print()
    print(f"  {'scenario':<14}" + "".join(f"{name:>32}" for name in VERDICTS))
    for scenario in scenarios:
        line = f"  {scenario:<14}"
        for verdict in VERDICTS:
            line += f"{verdict_rate(rows, verdict, scenario=scenario).render():>32}"
        print(line)
    print()
    print(
        "every rate carries a ninety five percent Wilson interval, because a rate over "
        "these replications is an estimate and an early run of this suite produced 0.084 "
        "for a test whose true level is 0.05"
    )
    _write(args.html, render_sweep_html(rows, scenarios=scenarios))
    if args.json:
        _write(args.json, json.dumps([row.as_dict() for row in rows], indent=2) + "\n")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="churngate",
        description=(
            "Gate a model evaluation on what changed item by item, not only on the "
            "aggregate. Exit codes: 0 the candidate passes, 1 a regression was detected, "
            "2 this eval set cannot resolve a difference this small, 3 the gate could not "
            "run, 4 the invocation was wrong."
        ),
    )
    parser.add_argument("--version", action="version", version=f"churngate {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    power_parser = subparsers.add_parser(
        "power", help="what this eval set can resolve, before running anything"
    )
    power_parser.add_argument("--json", action="store_true")
    power_parser.add_argument("--policy")
    power_parser.add_argument("--items", type=int)
    power_parser.set_defaults(handler=command_power)

    gate_parser = subparsers.add_parser("gate", help="run every gate on one comparison")
    gate_parser.add_argument("--scenario", default="compensating", choices=SCENARIOS)
    gate_parser.add_argument("--seed", type=int, default=11)
    gate_parser.add_argument("--effect", type=float, default=DEFAULT_EFFECT)
    gate_parser.add_argument("--items", type=int)
    gate_parser.add_argument("--policy")
    gate_parser.add_argument("--html")
    gate_parser.add_argument("--json")
    gate_parser.set_defaults(handler=command_gate)

    one_parser = subparsers.add_parser("one", help="run a single named gate")
    one_parser.add_argument("--gate", default="mean_threshold", choices=GATE_NAMES)
    one_parser.add_argument("--scenario", default="compensating", choices=SCENARIOS)
    one_parser.add_argument("--seed", type=int, default=11)
    one_parser.add_argument("--effect", type=float, default=DEFAULT_EFFECT)
    one_parser.add_argument("--items", type=int)
    one_parser.add_argument("--policy")
    one_parser.set_defaults(handler=command_one)

    sweep_parser = subparsers.add_parser("sweep", help="grade every gate on every scenario")
    sweep_parser.add_argument("--scenarios", nargs="+", default=list(SCENARIOS), choices=SCENARIOS)
    sweep_parser.add_argument("--replications", type=int)
    sweep_parser.add_argument("--effect", type=float, default=DEFAULT_EFFECT)
    sweep_parser.add_argument("--items", type=int)
    sweep_parser.add_argument("--policy")
    sweep_parser.add_argument("--html")
    sweep_parser.add_argument("--json")
    sweep_parser.set_defaults(handler=command_sweep)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.handler(args))
    except (UsageError, PolicyError, MissingDependencyError) as exc:
        print(f"usage error: {exc}", file=sys.stderr)
        return EXIT_USAGE
    except UnanswerableError as exc:
        print(f"cannot answer: {exc}", file=sys.stderr)
        return EXIT_UNANSWERABLE


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
