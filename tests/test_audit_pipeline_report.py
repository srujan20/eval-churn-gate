"""The three verdicts, the sweep, and the report that gets photographed."""

from __future__ import annotations

import re

import pytest

from churngate.audit import EXIT_CODES, Verdict, audit, decide_verdict
from churngate.gates import GATE_NAMES, Decision
from churngate.pipeline import block_rate, row_from, sweep, verdict_rate
from churngate.report import (
    STYLED_CLASSES,
    STYLESHEET,
    VERDICT_CLASS,
    VERDICT_TEXT,
    render_html,
    render_sweep_html,
    render_text,
)
from churngate.runs import SCENARIOS, make_comparison


def _decisions(*blocked: str) -> dict[str, Decision]:
    return {
        name: Decision(
            gate=name,
            blocked=name in blocked,
            statistic=0.0,
            threshold=0.0,
            reads="test",
        )
        for name in GATE_NAMES
    }


def test_every_verdict_has_an_exit_code():
    for verdict in Verdict:
        assert verdict in EXIT_CODES


def test_the_three_exit_codes_are_distinct():
    assert sorted(EXIT_CODES.values()) == [0, 1, 2]


def test_a_block_beats_an_unresolvable_delta():
    """A gate that fired on evidence should not be argued out of it by arithmetic."""
    verdict = decide_verdict(_decisions("churn"), observed=0.0001, minimum_detectable=0.01)
    assert verdict is Verdict.BLOCK


def test_a_small_delta_with_no_block_is_undecidable():
    verdict = decide_verdict(_decisions(), observed=0.0001, minimum_detectable=0.01)
    assert verdict is Verdict.UNDECIDABLE


def test_a_large_delta_with_no_block_passes():
    verdict = decide_verdict(_decisions(), observed=0.05, minimum_detectable=0.01)
    assert verdict is Verdict.PASS


def test_an_unresolvable_improvement_is_also_undecidable():
    """Symmetric on purpose: an unmeasurable gain is not a measured gain."""
    verdict = decide_verdict(_decisions(), observed=0.001, minimum_detectable=0.01)
    assert verdict is Verdict.UNDECIDABLE


def test_the_compensating_scenario_is_blocked(small_policy):
    result = audit(make_comparison("compensating", small_policy, 11), small_policy)
    assert result.verdict is Verdict.BLOCK
    assert result.exit_code == 1


def test_the_compensating_scenario_is_not_blocked_by_the_aggregate(small_policy):
    """The impossibility, in the audit rather than in a unit test."""
    result = audit(make_comparison("compensating", small_policy, 11), small_policy)
    assert not result.decisions["mean_threshold"].blocked
    assert result.decisions["slice_scan"].blocked


def test_the_blocking_gate_is_never_reported_as_the_combined_one(small_policy):
    """Naming the combined gate first would hide which condition caught it."""
    result = audit(make_comparison("compensating", small_policy, 11), small_policy)
    assert result.blocking_gate != "combined"


def test_the_combined_gate_is_named_when_it_is_the_only_one(small_policy):
    from dataclasses import replace

    result = audit(make_comparison("aa", small_policy, 3), small_policy)
    forced = replace(result, decisions=_decisions("combined"))
    assert forced.blocked_by == ("combined",)


def test_an_audit_reports_the_pairing_gain(small_policy, aa):
    result = audit(aa, small_policy)
    assert result.pairing_gain > 1.0
    assert result.pairing_gain == pytest.approx(
        result.minimum_detectable_unpaired / result.minimum_detectable
    )


def test_an_audit_reports_whether_the_delta_is_resolvable(small_policy):
    result = audit(make_comparison("aa", small_policy, 3), small_policy)
    assert result.resolvable == (abs(result.observed_delta) >= result.minimum_detectable)


def test_an_audit_serialises_its_decisions_and_its_transitions(small_policy, aa):
    payload = audit(aa, small_policy).as_dict()
    assert set(payload["decisions"]) == set(GATE_NAMES)
    assert "gross_flips" in payload["transitions"]


def test_an_audit_records_whether_its_truth_is_exact(small_policy):
    exact = audit(make_comparison("aa", small_policy, 3), small_policy)
    estimated = audit(make_comparison("uniform", small_policy, 3), small_policy)
    assert exact.truth_is_exact
    assert not estimated.truth_is_exact


def test_the_sweep_covers_every_scenario(small_policy):
    rows = sweep(small_policy, replications=4)
    assert {row.scenario for row in rows} == set(SCENARIOS)
    assert len(rows) == len(SCENARIOS) * 4


def test_the_sweep_is_deterministic(small_policy):
    left = sweep(small_policy, scenarios=("aa",), replications=5)
    right = sweep(small_policy, scenarios=("aa",), replications=5)
    assert [row.as_dict() for row in left] == [row.as_dict() for row in right]


def test_a_scenario_seed_does_not_depend_on_position_in_the_tuple(small_policy):
    """Adding a scenario must not renumber another scenario's comparisons."""
    alone = sweep(small_policy, scenarios=("uniform",), replications=3)
    together = sweep(small_policy, scenarios=("aa", "uniform"), replications=3)
    filtered = [row for row in together if row.scenario == "uniform"]
    assert [row.observed_delta for row in alone] == [row.observed_delta for row in filtered]


def test_a_row_serialises_a_non_finite_value_as_null(small_policy):
    rows = sweep(small_policy, scenarios=("aa",), replications=2)
    payload = rows[0].as_dict()
    assert payload["subgroup_effect"] is None


def test_a_row_can_be_asked_about_any_gate(small_policy):
    row = sweep(small_policy, scenarios=("aa",), replications=1)[0]
    for gate in GATE_NAMES:
        assert isinstance(row.blocked_by(gate), bool)


def test_a_row_refuses_an_unknown_gate(small_policy):
    row = sweep(small_policy, scenarios=("aa",), replications=1)[0]
    with pytest.raises(KeyError, match="unknown gate"):
        row.blocked_by("vibes")


def test_a_block_rate_carries_its_interval(small_policy):
    rows = sweep(small_policy, scenarios=("aa",), replications=20)
    rate = block_rate(rows, "mean_threshold", scenario="aa")
    assert rate.denominator == 20
    assert rate.interval[0] <= rate.value <= rate.interval[1]


def test_a_verdict_rate_carries_its_interval(small_policy):
    rows = sweep(small_policy, scenarios=("aa",), replications=20)
    rate = verdict_rate(rows, "eval-set-cannot-resolve-this", scenario="aa")
    assert rate.denominator == 20


def test_the_verdict_rates_sum_to_one(small_policy):
    rows = sweep(small_policy, scenarios=("uniform",), replications=20)
    total = sum(
        verdict_rate(rows, verdict, scenario="uniform").numerator
        for verdict in (
            "candidate-passes",
            "regression-detected",
            "eval-set-cannot-resolve-this",
        )
    )
    assert total == 20


def test_row_from_records_the_replication_and_the_effect(small_policy, aa):
    row = row_from(audit(aa, small_policy), replication=7, effect=0.05)
    assert row.replication == 7
    assert row.effect == 0.05


def test_every_class_used_in_the_markup_has_a_stylesheet_rule():
    """Pins the failure a green-on-green verdict badge caused on earlier projects."""
    for name in STYLED_CLASSES:
        assert re.search(rf"\.{re.escape(name)}\s*[,{{\s]", STYLESHEET), name


def test_every_verdict_has_display_text_and_a_declared_class():
    for verdict in Verdict:
        assert verdict in VERDICT_TEXT
        assert VERDICT_CLASS[verdict] in STYLED_CLASSES


def test_the_text_report_prints_the_transitions_before_the_aggregate(small_policy, compensating):
    text = render_text(audit(compensating, small_policy))
    assert text.index("what moved, item by item") < text.index("the aggregate")


def test_the_text_report_names_every_gate(small_policy, compensating):
    text = render_text(audit(compensating, small_policy))
    for gate in GATE_NAMES:
        assert gate in text


def test_the_text_report_says_when_a_delta_is_unresolvable(small_policy):
    text = render_text(audit(make_comparison("aa", small_policy, 3), small_policy))
    assert "items would be needed" in text


def test_the_text_report_marks_an_exact_truth(small_policy):
    text = render_text(audit(make_comparison("aa", small_policy, 3), small_policy))
    assert "exact by construction" in text


def test_the_text_report_marks_an_estimated_truth(small_policy, uniform):
    assert "computed per replication" in render_text(audit(uniform, small_policy))


def test_the_text_report_ends_with_a_newline(small_policy, aa):
    assert render_text(audit(aa, small_policy)).endswith("\n")


def test_the_html_report_is_a_complete_document(small_policy, compensating):
    html = render_html(audit(compensating, small_policy))
    assert html.startswith("<!doctype html>")
    assert html.rstrip().endswith("</html>")


def test_the_html_report_inlines_its_stylesheet(small_policy, aa):
    assert "<style>" in render_html(audit(aa, small_policy))


def test_the_html_report_shows_the_four_transition_cells(small_policy, compensating):
    assert render_html(audit(compensating, small_policy)).count('class="flow-cell') == 4


def test_the_html_report_escapes_a_hostile_scenario_name(small_policy, aa):
    from dataclasses import replace

    injected = replace(audit(aa, small_policy), scenario="<script>alert(1)</script>")
    html = render_html(injected)
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


def test_the_html_report_shows_the_slice_effect_only_when_there_is_one(
    small_policy, compensating, aa
):
    assert "losing slice" in render_html(audit(compensating, small_policy))
    assert "losing slice" not in render_html(audit(aa, small_policy))


def test_the_sweep_report_is_a_complete_document(small_policy):
    rows = sweep(small_policy, replications=4)
    html = render_sweep_html(rows, scenarios=SCENARIOS)
    assert html.startswith("<!doctype html>")
    assert html.rstrip().endswith("</html>")


def test_the_sweep_report_names_every_gate(small_policy):
    rows = sweep(small_policy, replications=4)
    html = render_sweep_html(rows, scenarios=SCENARIOS)
    for gate in GATE_NAMES:
        assert gate in html


def test_the_sweep_report_refuses_an_empty_row_set():
    with pytest.raises(ValueError, match="no rows to render"):
        render_sweep_html([], scenarios=SCENARIOS)


def test_the_sweep_report_explains_why_every_rate_has_an_interval(small_policy):
    rows = sweep(small_policy, replications=4)
    html = render_sweep_html(rows, scenarios=SCENARIOS)
    assert "Wilson interval" in html


def test_the_pairing_gain_is_undefined_when_nothing_is_detectable(small_policy, aa):
    import math
    from dataclasses import replace

    result = replace(audit(aa, small_policy), minimum_detectable=0.0)
    assert math.isnan(result.pairing_gain)


def test_a_run_reports_its_own_mean(aa):
    assert aa.baseline.mean == pytest.approx(float(aa.baseline.scores.mean()))


def test_a_sweep_cell_is_uncoloured_when_it_has_no_denominator():
    from churngate.rates import Rate
    from churngate.report import _class_for

    assert _class_for("aa", "churn", Rate(0, 0)) == ""


def test_a_slice_with_one_item_is_skipped_by_the_scan(small_policy):
    """One item has no spread and no sign worth trusting, so it carries no vote."""
    from churngate.gates import slice_scan

    labels = ("alpha",) + tuple("beta" for _ in range(40))
    baseline = [0.5 + 0.001 * index for index in range(41)]
    candidate = [value - 0.05 for value in baseline]
    decision = slice_scan(_pair_with(baseline, candidate, labels), small_policy)
    assert "alpha" not in decision.note


def _pair_with(baseline, candidate, labels):
    import numpy as np

    from churngate.runs import Comparison, Run

    ids = tuple(range(len(baseline)))
    return Comparison(
        baseline=Run(version="a", seed=1, item_ids=ids, scores=np.array(baseline), slices=labels),
        candidate=Run(version="b", seed=2, item_ids=ids, scores=np.array(candidate), slices=labels),
        scenario="aa",
        true_effect=0.0,
        truth_is_exact=True,
    )
