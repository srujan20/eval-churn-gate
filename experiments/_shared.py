"""Shared setup for the five experiments, with an on disk cache.

Every experiment reduces the same sweep. Building it five times would make
`make verify` five times slower for no extra information, so the rows are built
once and cached under a fingerprint of the parameters and thresholds that produced
them. The cache is not committed: it is derived, it is large, and a stale cache
that silently disagrees with the code is exactly the failure this repository
exists to complain about. The fingerprint means a change to any threshold
invalidates it rather than being quietly reused.
"""

from __future__ import annotations

import hashlib
import json
import math
import sys
from dataclasses import fields
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO / "src") not in sys.path:  # pragma: no cover
    sys.path.insert(0, str(REPO / "src"))

from churngate.config import Policy, load_policy  # noqa: E402
from churngate.gates import GATE_NAMES  # noqa: E402
from churngate.pipeline import (  # noqa: E402
    DEFAULT_EFFECT,
    GateRow,
    block_rate,
    sweep,
    verdict_rate,
)
from churngate.rates import Rate  # noqa: E402
from churngate.runs import SCENARIOS  # noqa: E402

CACHE_DIRECTORY = REPO / ".cache"
RESULTS_DIRECTORY = REPO / "docs" / "experiments"
VERDICTS = ("candidate-passes", "regression-detected", "eval-set-cannot-resolve-this")
EFFECT_SWEEP = (0.0, 0.005, 0.01, 0.02, 0.03, 0.05, 0.08)


def fingerprint(policy: Policy, extra: dict[str, object] | None = None) -> str:
    payload = {
        "mean_drop": policy.gate.mean_drop,
        "alpha": policy.gate.alpha,
        "power": policy.gate.power,
        "bootstrap_resamples": policy.gate.bootstrap_resamples,
        "pass_threshold": policy.churn.pass_threshold,
        "flip_rate_limit": policy.churn.flip_rate_limit,
        "minimum_movement": policy.churn.minimum_movement,
        "items": policy.evaluation.items,
        "item_sweep": list(policy.evaluation.item_sweep),
        "replications": policy.evaluation.replications,
        "run_sd": policy.noise.run_sd,
        "item_sd": policy.noise.item_sd,
        "effect": DEFAULT_EFFECT,
        "extra": extra or {},
    }
    encoded = json.dumps(payload, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:16]


def _rows_from(payload: list[dict[str, object]]) -> list[GateRow]:
    names = [item.name for item in fields(GateRow)]
    return [GateRow(**{name: row[name] for name in names}) for row in payload]


def setup() -> Policy:
    return load_policy()


def main_sweep(policy: Policy, *, refresh: bool = False) -> list[GateRow]:
    """The sweep every experiment reads, built once and cached."""
    CACHE_DIRECTORY.mkdir(parents=True, exist_ok=True)
    cache = CACHE_DIRECTORY / f"sweep-{fingerprint(policy)}.json"
    if cache.is_file() and not refresh:
        return _rows_from(json.loads(cache.read_text(encoding="utf-8")))
    rows = sweep(policy)
    cache.write_text(json.dumps([row.as_dict() for row in rows], indent=1), encoding="utf-8")
    return rows


def effect_sweep(policy: Policy, *, refresh: bool = False) -> dict[float, list[GateRow]]:
    """Uniform regressions of several sizes, for the detection curve in exp05."""
    CACHE_DIRECTORY.mkdir(parents=True, exist_ok=True)
    cache = CACHE_DIRECTORY / f"effects-{fingerprint(policy, {'effects': list(EFFECT_SWEEP)})}.json"
    if cache.is_file() and not refresh:
        payload = json.loads(cache.read_text(encoding="utf-8"))
        return {float(key): _rows_from(value) for key, value in payload.items()}

    result: dict[float, list[GateRow]] = {}
    for effect in EFFECT_SWEEP:
        result[effect] = sweep(
            policy,
            scenarios=("uniform",),
            effect=effect,
            seed_offset=int(effect * 100000),
        )
    cache.write_text(
        json.dumps({str(key): [row.as_dict() for row in value] for key, value in result.items()}),
        encoding="utf-8",
    )
    return result


def _finite(value: object) -> object:
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, dict):
        return {key: _finite(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_finite(item) for item in value]
    return value


def write_result(name: str, payload: dict[str, object]) -> Path:
    RESULTS_DIRECTORY.mkdir(parents=True, exist_ok=True)
    destination = RESULTS_DIRECTORY / f"{name}.json"
    destination.write_text(
        json.dumps(_finite(payload), indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return destination


def table(headers: list[str], rows: list[list[object]]) -> str:
    widths = [len(head) for head in headers]
    rendered = [[str(cell) for cell in row] for row in rows]
    for row in rendered:
        for index, cell in enumerate(row):
            widths[index] = max(widths[index], len(cell))
    line = "  ".join(head.ljust(widths[index]) for index, head in enumerate(headers))
    rule = "  ".join("-" * widths[index] for index in range(len(headers)))
    body = [
        "  ".join(cell.ljust(widths[index]) for index, cell in enumerate(row)) for row in rendered
    ]
    return "\n".join([line, rule, *body])


def pct(value: float, digits: int = 1) -> str:
    if value != value:
        return "n/a"
    return f"{100.0 * value:.{digits}f}%"


__all__ = [
    "EFFECT_SWEEP",
    "GATE_NAMES",
    "REPO",
    "SCENARIOS",
    "VERDICTS",
    "Rate",
    "block_rate",
    "effect_sweep",
    "main_sweep",
    "pct",
    "setup",
    "table",
    "verdict_rate",
    "write_result",
]
