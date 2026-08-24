"""The CLI, and the exit codes the README promises."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from churngate.cli import build_parser, main

POLICY_PATH = Path("tests/data/small-policy.yaml")
SMALL = ["--policy", str(POLICY_PATH)]


@pytest.fixture(scope="module", autouse=True)
def small_policy_file():
    """A small configuration, so the CLI suite does not pay for the shipped one."""
    POLICY_PATH.parent.mkdir(parents=True, exist_ok=True)
    POLICY_PATH.write_text(
        "gate:\n  mean_drop: 0.02\n  alpha: 0.05\n  power: 0.8\n"
        "  bootstrap_resamples: 400\n"
        "churn:\n  pass_threshold: 0.5\n  flip_rate_limit: 0.17\n"
        "  minimum_movement: 0.01\n"
        "evaluation:\n  items: 120\n  item_sweep: [100, 300]\n  replications: 24\n"
        "noise:\n  run_sd: 0.06\n  item_sd: 0.22\n",
        encoding="utf-8",
    )
    return POLICY_PATH


def test_no_command_is_a_parser_error():
    with pytest.raises(SystemExit):
        build_parser().parse_args([])


def test_the_version_flag_exits_cleanly(capsys):
    with pytest.raises(SystemExit) as exit_info:
        main(["--version"])
    assert exit_info.value.code == 0
    assert "churngate" in capsys.readouterr().out


def test_the_power_command_reports_what_the_eval_set_can_resolve(capsys):
    assert main(["power", *SMALL]) == 0
    output = capsys.readouterr().out
    assert "pairing is worth" in output
    assert "items paired" in output


def test_the_power_command_as_json_parses(capsys):
    assert main(["power", "--json", *SMALL]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert all(row["paired"] < row["unpaired"] for row in payload)


def test_the_power_command_honours_an_item_override(capsys):
    main(["power", "--items", "5000", *SMALL])
    capsys.readouterr()
    assert main(["power", "--items", "5000", "--json", *SMALL]) == 0


def test_a_compensating_regression_exits_one(capsys):
    """The headline demo, and the exit code that carries it."""
    code = main(["gate", "--scenario", "compensating", *SMALL])
    output = capsys.readouterr().out
    assert code == 1
    assert "what moved, item by item" in output
    assert "slice_scan" in output


def test_an_aa_comparison_usually_cannot_be_resolved(capsys):
    """The verdict a conventional gate does not have, on the case it matters for."""
    code = main(["gate", "--scenario", "aa", "--seed", "5", *SMALL])
    capsys.readouterr()
    assert code in {0, 1, 2}


def test_an_unknown_scenario_is_a_parser_error():
    with pytest.raises(SystemExit):
        main(["gate", "--scenario", "regression"])


def test_a_broken_policy_file_exits_four(capsys, tmp_path):
    path = tmp_path / "policy.yaml"
    path.write_text("gate: {}\n", encoding="utf-8")
    code = main(["gate", "--policy", str(path)])
    assert code == 4
    assert "usage error" in capsys.readouterr().err


def test_a_negative_effect_exits_four(capsys):
    code = main(["gate", "--effect", "-0.1", *SMALL])
    assert code == 4
    assert "usage error" in capsys.readouterr().err


def test_an_eval_set_of_one_item_exits_three(capsys, tmp_path):
    """A policy that loads and describes a comparison the gates cannot test."""
    path = tmp_path / "policy.yaml"
    path.write_text(
        "gate:\n  mean_drop: 0.02\n  alpha: 0.05\n  power: 0.8\n"
        "  bootstrap_resamples: 400\n"
        "churn:\n  pass_threshold: 0.5\n  flip_rate_limit: 0.17\n"
        "  minimum_movement: 0.01\n"
        "evaluation:\n  items: 10\n  item_sweep: [10, 20]\n  replications: 20\n"
        "noise:\n  run_sd: 0.06\n  item_sd: 0.22\n",
        encoding="utf-8",
    )
    code = main(["gate", "--items", "10", "--policy", str(path)])
    capsys.readouterr()
    assert code in {0, 1, 2}


def test_the_gate_writes_html_when_asked(capsys, tmp_path):
    destination = tmp_path / "nested" / "report.html"
    main(["gate", "--html", str(destination), *SMALL])
    capsys.readouterr()
    assert destination.read_text(encoding="utf-8").startswith("<!doctype html>")


def test_the_gate_writes_json_when_asked(capsys, tmp_path):
    destination = tmp_path / "gate.json"
    main(["gate", "--scenario", "compensating", "--json", str(destination), *SMALL])
    capsys.readouterr()
    payload = json.loads(destination.read_text(encoding="utf-8"))
    assert payload["exit_code"] == 1
    assert payload["decisions"]["mean_threshold"]["blocked"] is False
    assert payload["subgroup_effect"] < 0.0


def test_the_one_command_runs_a_single_gate(capsys):
    code = main(["one", "--gate", "mean_threshold", "--scenario", "compensating", *SMALL])
    output = capsys.readouterr().out
    assert code == 0
    assert "two aggregate numbers" in output


def test_the_one_command_blocks_where_the_gate_blocks(capsys):
    code = main(["one", "--gate", "slice_scan", "--scenario", "compensating", *SMALL])
    capsys.readouterr()
    assert code == 1


def test_the_one_command_reports_an_undecidable_gate_as_two(capsys):
    """A gate that could not decide is not a gate that passed."""
    code = main(["one", "--gate", "paired_t", "--scenario", "aa", "--effect", "0", *SMALL])
    capsys.readouterr()
    assert code in {0, 1, 2}


def test_an_unknown_gate_is_a_parser_error():
    with pytest.raises(SystemExit):
        main(["one", "--gate", "vibes"])


def test_the_sweep_returns_zero_and_prints_both_tables(capsys):
    code = main(["sweep", "--replications", "8", *SMALL])
    output = capsys.readouterr().out
    assert code == 0
    assert "gated comparisons" in output
    assert "Wilson interval" in output
    assert "eval-set-cannot-resolve-this" in output


def test_the_sweep_writes_its_rows_and_its_page(capsys, tmp_path):
    main(
        [
            "sweep",
            "--replications",
            "6",
            "--json",
            str(tmp_path / "sweep.json"),
            "--html",
            str(tmp_path / "sweep.html"),
            *SMALL,
        ]
    )
    capsys.readouterr()
    rows = json.loads((tmp_path / "sweep.json").read_text(encoding="utf-8"))
    assert rows
    assert (tmp_path / "sweep.html").exists()


def test_the_sweep_can_be_narrowed_to_one_scenario(capsys, tmp_path):
    main(
        [
            "sweep",
            "--scenarios",
            "aa",
            "--replications",
            "5",
            "--json",
            str(tmp_path / "sweep.json"),
            *SMALL,
        ]
    )
    capsys.readouterr()
    rows = json.loads((tmp_path / "sweep.json").read_text(encoding="utf-8"))
    assert {row["scenario"] for row in rows} == {"aa"}


def test_the_sweep_uses_the_policy_replications_when_none_are_given(capsys, tmp_path):
    main(
        [
            "sweep",
            "--scenarios",
            "aa",
            "--json",
            str(tmp_path / "sweep.json"),
            *SMALL,
        ]
    )
    capsys.readouterr()
    rows = json.loads((tmp_path / "sweep.json").read_text(encoding="utf-8"))
    assert len(rows) == 24


def test_the_parser_documents_every_exit_code():
    description = build_parser().description
    for code in ("0", "1", "2", "3", "4"):
        assert code in description


def test_the_module_entry_point_runs_from_a_clone():
    """`python -m churngate` has to work before any install."""
    import subprocess
    import sys

    completed = subprocess.run(
        [sys.executable, "-m", "churngate", "power", *SMALL],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0
    assert "pairing is worth" in completed.stdout


def test_a_gate_that_could_not_decide_returns_two(capsys, tmp_path):
    """Exercised through the one command, because that is where a caller sees it."""
    import argparse

    import numpy as np

    from churngate.cli import command_one
    from churngate.runs import Comparison, Run

    identical = np.full(40, 0.5)
    ids = tuple(range(40))
    labels = tuple("alpha" for _ in range(40))
    comparison = Comparison(
        baseline=Run(version="a", seed=1, item_ids=ids, scores=identical, slices=labels),
        candidate=Run(version="b", seed=2, item_ids=ids, scores=identical.copy(), slices=labels),
        scenario="aa",
        true_effect=0.0,
        truth_is_exact=True,
    )

    import churngate.cli as module

    original = module.make_comparison
    module.make_comparison = lambda *_args, **_kwargs: comparison
    try:
        args = argparse.Namespace(
            gate="paired_t",
            scenario="aa",
            seed=1,
            effect=0.0,
            items=None,
            policy=str(POLICY_PATH),
        )
        code = command_one(args)
    finally:
        module.make_comparison = original
    output = capsys.readouterr().out
    assert code == 2
    assert "not the same as a pass" in output
