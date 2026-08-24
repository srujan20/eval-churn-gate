"""Loading and validating the gate policy.

Strict at load time. An alpha of 1.0, a flip rate limit of zero, or an item count
of one are all typos, and finding one partway through four hundred replications
costs more than refusing it at the boundary.

One validation rule is worth reading rather than skimming: the churn flip rate
limit is checked against the run noise, and a limit far below what run to run
variation alone produces is refused with that reason. A churn gate set below its
own noise floor blocks on nothing but noise, and it is the single easiest way to
build a gate that everybody learns to ignore.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

import yaml

from .errors import PolicyError

DEFAULT_POLICY_PATH = Path(__file__).resolve().parents[2] / "configs" / "policy.yaml"


def _require(mapping: Any, key: str, where: str) -> Any:
    if not isinstance(mapping, dict):
        raise PolicyError(
            f"policy section {where!r} must be a mapping, got {type(mapping).__name__}"
        )
    if key not in mapping:
        raise PolicyError(f"policy section {where!r} is missing the key {key!r}")
    return mapping[key]


def _open_unit(value: Any, name: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise PolicyError(f"{name} must be a number, got {value!r}") from exc
    if not 0.0 < number < 1.0:
        raise PolicyError(f"{name} must lie strictly between 0 and 1, got {number}")
    return number


def _positive(value: Any, name: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise PolicyError(f"{name} must be a number, got {value!r}") from exc
    if number <= 0.0:
        raise PolicyError(f"{name} must be positive, got {number}")
    return number


@dataclass(frozen=True)
class GatePolicy:
    mean_drop: float
    alpha: float
    power: float
    bootstrap_resamples: int


@dataclass(frozen=True)
class ChurnPolicy:
    pass_threshold: float
    flip_rate_limit: float
    minimum_movement: float


@dataclass(frozen=True)
class EvaluationPolicy:
    items: int
    item_sweep: tuple[int, ...]
    replications: int


@dataclass(frozen=True)
class NoisePolicy:
    run_sd: float
    item_sd: float


@dataclass(frozen=True)
class Policy:
    gate: GatePolicy
    churn: ChurnPolicy
    evaluation: EvaluationPolicy
    noise: NoisePolicy
    source: str = field(default="<defaults>")

    @property
    def resolution_floor(self) -> float:
        """The smallest non zero rate the replication count can express.

        Published next to every measured zero, because a zero over four hundred
        replications is a different statement from a zero over a million.
        """
        return 1.0 / self.evaluation.replications

    @property
    def paired_standard_error(self) -> float:
        """Standard error of a paired mean delta at the shipped item count.

        Pairing cancels the item term, so only the run to run component survives,
        and it survives twice because both runs carry it. This is the number the
        minimum detectable effect is built from, and it is published so a reader
        can check the arithmetic rather than trust it.
        """
        return (2.0**0.5) * self.noise.run_sd / (self.evaluation.items**0.5)


def load_policy(path: str | os.PathLike[str] | None = None) -> Policy:
    resolved = Path(path) if path is not None else DEFAULT_POLICY_PATH
    if not resolved.is_file():
        raise PolicyError(f"policy file not found: {resolved}")
    try:
        raw = yaml.safe_load(resolved.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise PolicyError(f"policy file {resolved} is not valid YAML: {exc}") from exc
    if not isinstance(raw, dict):
        raise PolicyError(f"policy file {resolved} must contain a mapping at the top level")
    return policy_from_mapping(raw, source=str(resolved))


def policy_from_mapping(raw: dict[str, Any], *, source: str = "<mapping>") -> Policy:
    gate_raw = _require(raw, "gate", "<root>")
    churn_raw = _require(raw, "churn", "<root>")
    evaluation_raw = _require(raw, "evaluation", "<root>")
    noise_raw = _require(raw, "noise", "<root>")

    resamples = int(_require(gate_raw, "bootstrap_resamples", "gate"))
    if resamples < 200:
        raise PolicyError(
            f"gate.bootstrap_resamples must be at least 200, got {resamples}. Below that the "
            "Monte Carlo error of the interval is comparable to the effect being tested"
        )

    items = int(_require(evaluation_raw, "items", "evaluation"))
    if items < 10:
        raise PolicyError(
            f"evaluation.items must be at least 10, got {items}. A paired test on fewer "
            "items has no power worth reporting"
        )

    sweep_raw = _require(evaluation_raw, "item_sweep", "evaluation")
    if not isinstance(sweep_raw, list) or len(sweep_raw) < 2:
        raise PolicyError("evaluation.item_sweep must be a list of at least two sizes")
    item_sweep = tuple(int(value) for value in sweep_raw)
    if any(value < 10 for value in item_sweep):
        raise PolicyError(
            f"every size in evaluation.item_sweep must be at least 10, got {item_sweep}"
        )
    if sorted(item_sweep) != list(item_sweep):
        raise PolicyError(f"evaluation.item_sweep must be ascending, got {item_sweep}")

    replications = int(_require(evaluation_raw, "replications", "evaluation"))
    if replications < 20:
        raise PolicyError(
            f"evaluation.replications must be at least 20, got {replications}. Every "
            "published rate has a resolution floor of one over this number"
        )

    run_sd = _positive(_require(noise_raw, "run_sd", "noise"), "noise.run_sd")
    item_sd = _positive(_require(noise_raw, "item_sd", "noise"), "noise.item_sd")

    minimum_movement = _positive(
        _require(churn_raw, "minimum_movement", "churn"), "churn.minimum_movement"
    )
    if minimum_movement >= 0.5:
        raise PolicyError(
            f"churn.minimum_movement must be well below the metric's range, got "
            f"{minimum_movement}. A filter that large discards real crossings"
        )

    flip_limit = _open_unit(
        _require(churn_raw, "flip_rate_limit", "churn"), "churn.flip_rate_limit"
    )
    # A single run's noise crosses the pass boundary for any item sitting within
    # about one standard deviation of it. A flip limit far below that blocks on
    # noise alone, which is the fastest way to build a gate people route around.
    noise_floor_guess = 0.15 * run_sd / 0.06
    if flip_limit < 0.2 * noise_floor_guess:
        raise PolicyError(
            f"churn.flip_rate_limit of {flip_limit} sits far below what run to run noise of "
            f"{run_sd} produces on its own. Calibrate it against the A/A floor exp01 "
            "measures, or the gate blocks on noise"
        )

    return Policy(
        gate=GatePolicy(
            mean_drop=_positive(_require(gate_raw, "mean_drop", "gate"), "gate.mean_drop"),
            alpha=_open_unit(_require(gate_raw, "alpha", "gate"), "gate.alpha"),
            power=_open_unit(_require(gate_raw, "power", "gate"), "gate.power"),
            bootstrap_resamples=resamples,
        ),
        churn=ChurnPolicy(
            pass_threshold=_open_unit(
                _require(churn_raw, "pass_threshold", "churn"), "churn.pass_threshold"
            ),
            flip_rate_limit=flip_limit,
            minimum_movement=minimum_movement,
        ),
        evaluation=EvaluationPolicy(items=items, item_sweep=item_sweep, replications=replications),
        noise=NoisePolicy(run_sd=run_sd, item_sd=item_sd),
        source=source,
    )


def with_items(policy: Policy, items: int) -> Policy:
    """A copy of the policy with a different eval set size.

    exp03 needs several policies differing in exactly this field, because the
    minimum detectable effect is a function of it and the whole finding is that
    the shipped size is too small for the deltas people gate on.
    """
    if items < 10:
        raise PolicyError(f"items must be at least 10, got {items}")
    return replace(policy, evaluation=replace(policy.evaluation, items=items))
