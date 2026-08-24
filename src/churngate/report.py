"""Rendering one gated comparison and a scenario sweep, as text and as HTML.

The HTML report is what `tools/capture_screenshots.py` photographs. Its job is to
put the aggregate delta, the transitions and the per gate decisions on one screen,
so a reader sees that the first of those is a summary of the second rather than a
separate fact.

The markup is f strings with `html.escape`, so the report is one self contained
file with no template directory to keep in step with the code, and escaping is the
author's job. A test asserts a hostile scenario name comes out inert. The palette
is fixed rather than inherited so a screenshot is legible in any theme, and every
class in the markup is listed in STYLED_CLASSES with a test asserting each has a
rule: on earlier projects a badge class and a table cell class collided at equal
specificity and a verdict rendered green on green while every test passed.
"""

from __future__ import annotations

from collections.abc import Sequence
from html import escape

from .audit import AuditResult, Verdict
from .gates import GATE_NAMES
from .pipeline import GateRow, block_rate
from .rates import Rate

VERDICT_TEXT = {
    Verdict.PASS: "The candidate passes",
    Verdict.BLOCK: "A regression was detected",
    Verdict.UNDECIDABLE: "This eval set cannot resolve a difference this small",
}

VERDICT_CLASS = {
    Verdict.PASS: "badge-clear",
    Verdict.BLOCK: "badge-alarm",
    Verdict.UNDECIDABLE: "badge-unknown",
}

STYLED_CLASSES = (
    "page",
    "masthead",
    "subtitle",
    "badge",
    "badge-clear",
    "badge-alarm",
    "badge-unknown",
    "tiles",
    "tile",
    "tile-label",
    "tile-value",
    "tile-note",
    "section",
    "grid",
    "numeric",
    "blocked",
    "passed",
    "exact",
    "footnote",
    "flow",
    "flow-cell",
    "flow-label",
    "flow-count",
    "flow-broke",
    "flow-fixed",
)

STYLESHEET = """
:root { color-scheme: only light; }
body { margin: 0; background: #f4f5f7; color: #14171a;
       font-family: -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; }
.page { max-width: 1000px; margin: 0 auto; padding: 32px 28px 56px; background: #ffffff; }
.masthead { font-size: 26px; font-weight: 650; letter-spacing: -0.2px; margin: 0 0 4px; }
.subtitle { color: #4a5159; font-size: 14px; margin: 0 0 22px; }
.badge { display: inline-block; padding: 5px 12px; border-radius: 4px; font-size: 13px;
         font-weight: 650; border: 1px solid transparent; }
.badge-clear { background: #e4f2e6; color: #16491f; border-color: #a9d4b0; }
.badge-alarm { background: #fae3e3; color: #6d1717; border-color: #e0a7a7; }
.badge-unknown { background: #fdf0d8; color: #6a4708; border-color: #e5c583; }
.tiles { display: flex; flex-wrap: wrap; gap: 12px; margin: 20px 0 26px; }
.tile { flex: 1 1 195px; border: 1px solid #dcdfe3; border-radius: 6px; padding: 12px 14px;
        background: #fbfbfc; }
.tile-label { font-size: 11px; text-transform: uppercase; letter-spacing: 0.7px; color: #5b636b; }
.tile-value { font-size: 23px; font-weight: 650; margin-top: 4px;
              font-variant-numeric: tabular-nums; }
.tile-note { font-size: 12px; color: #5b636b; margin-top: 3px; }
.section { margin: 30px 0 0; }
.section h2 { font-size: 16px; margin: 0 0 4px; }
.section p { font-size: 13.5px; color: #3c4349; margin: 0 0 12px; max-width: 72ch; }
.grid { width: 100%; border-collapse: collapse; font-size: 13px; }
.grid th, .grid td { border-bottom: 1px solid #e6e8eb; padding: 7px 9px; text-align: left; }
.grid th { background: #f0f1f3; font-weight: 600; font-size: 11.5px; text-transform: uppercase;
           letter-spacing: 0.5px; color: #40474e; }
.grid td.numeric { text-align: right; font-variant-numeric: tabular-nums; }
.grid td.blocked { color: #6d1717; font-weight: 650; }
.grid td.passed { color: #16491f; font-weight: 650; }
.grid td.exact { background: #eef4ea; font-weight: 650; }
.footnote { font-size: 12px; color: #5b636b; margin-top: 10px; max-width: 80ch; }
.flow { display: flex; gap: 10px; margin: 6px 0 14px; }
.flow-cell { flex: 1 1 0; border: 1px solid #dcdfe3; border-radius: 6px; padding: 10px 12px;
             background: #fbfbfc; }
.flow-label { font-size: 11.5px; color: #5b636b; }
.flow-count { font-size: 21px; font-weight: 650; font-variant-numeric: tabular-nums; }
.flow-broke { border-color: #e0a7a7; background: #fdf1f1; }
.flow-fixed { border-color: #a9d4b0; background: #f0f7f1; }
"""


def _tile(label: str, value: str, note: str) -> str:
    return (
        '<div class="tile">'
        f'<div class="tile-label">{escape(label)}</div>'
        f'<div class="tile-value">{escape(value)}</div>'
        f'<div class="tile-note">{escape(note)}</div>'
        "</div>"
    )


def _cell(label: str, count: int, extra: str = "") -> str:
    return (
        f'<div class="flow-cell {extra}">'
        f'<div class="flow-label">{escape(label)}</div>'
        f'<div class="flow-count">{count}</div>'
        "</div>"
    )


def render_text(result: AuditResult) -> str:
    """The CLI's report. The transitions are printed before the aggregate."""
    counts = result.transitions
    lines: list[str] = []
    lines.append(f"verdict: {result.verdict.value}")
    lines.append(f"scenario: {result.scenario}  items: {result.items}")
    lines.append("")
    lines.append("what moved, item by item")
    lines.append(f"  passed and now fails : {counts.pass_to_fail}")
    lines.append(f"  failed and now passes: {counts.fail_to_pass}")
    lines.append(f"  unchanged            : {counts.stayed_pass + counts.stayed_fail}")
    lines.append(f"  crossings the movement filter rejected: {counts.filtered_out}")
    lines.append(
        f"  gross flips {counts.gross_flips} ({counts.flip_rate:.4f}), "
        f"net {counts.net_flips:+d} ({counts.net_rate:+.4f})"
    )
    lines.append(f"  share of the movement the net cancels away: {counts.hidden_share:.4f}")
    lines.append("")
    lines.append("the aggregate, which is a summary of the above and not a separate fact")
    lines.append(f"  observed delta: {result.observed_delta:+.4f}")
    lines.append(
        f"  smallest effect this eval set can detect, paired: {result.minimum_detectable:.4f}"
    )
    lines.append(
        f"  the same, comparing two averages instead: {result.minimum_detectable_unpaired:.4f}"
    )
    lines.append(f"  pairing is worth a factor of {result.pairing_gain:.1f} on the same data")
    if not result.resolvable:
        lines.append(
            f"  this delta is below what {result.items} items can resolve. "
            f"{result.items_needed} items would be needed"
        )
    lines.append("")
    lines.append("what each gate decided, and what it reads")
    lines.append(f"  {'gate':<18}{'blocked':>9}{'statistic':>12}{'threshold':>12}  reads")
    for name, decision in result.decisions.items():
        lines.append(
            f"  {name:<18}{str(decision.blocked):>9}{decision.statistic:>12.4f}"
            f"{decision.threshold:>12.4f}  {decision.reads}"
        )
    if result.true_effect is not None:
        source = "exact by construction" if result.truth_is_exact else "computed per replication"
        lines.append("")
        lines.append(f"graded against a truth the gates cannot see ({source})")
        lines.append(f"  true aggregate effect: {result.true_effect:+.4f}")
        if result.subgroup_effect is not None:
            lines.append(f"  true effect on the losing slice: {result.subgroup_effect:+.4f}")
    return "\n".join(lines) + "\n"


def render_html(result: AuditResult) -> str:
    counts = result.transitions
    tiles = [
        _tile(
            "observed delta",
            f"{result.observed_delta:+.4f}",
            "what a dashboard shows",
        ),
        _tile(
            "items that changed side",
            f"{counts.gross_flips} of {counts.items}",
            "what a person downstream experiences",
        ),
        _tile(
            "net change in passing items",
            f"{counts.net_flips:+d}",
            "what the aggregate reflects",
        ),
        _tile(
            "movement the net cancels",
            f"{counts.hidden_share:.3f}",
            "one means the flips balanced exactly",
        ),
    ]
    gate_rows = "".join(
        "<tr>"
        f"<td>{escape(name)}</td>"
        f'<td class="{"blocked" if decision.blocked else "passed"}">'
        f"{'blocked' if decision.blocked else 'passed'}</td>"
        f'<td class="numeric">{decision.statistic:.4f}</td>'
        f'<td class="numeric">{decision.threshold:.4f}</td>'
        f"<td>{escape(decision.reads)}</td>"
        f"<td>{escape(decision.note)}</td>"
        "</tr>"
        for name, decision in result.decisions.items()
    )
    truth_class = "exact" if result.truth_is_exact else ""
    subgroup_row = (
        "<tr><td>true effect on the losing slice</td>"
        f'<td class="numeric">{result.subgroup_effect:+.4f}</td></tr>'
        if result.subgroup_effect is not None
        else ""
    )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>churngate</title>
<style>{STYLESHEET}</style>
</head><body><div class="page">
<h1 class="masthead">What actually changed</h1>
<p class="subtitle">scenario {escape(result.scenario)}, {result.items} items,
pass boundary at {counts.threshold}</p>
<span class="badge {VERDICT_CLASS[result.verdict]}">
{escape(VERDICT_TEXT[result.verdict])}</span>
<div class="tiles">{"".join(tiles)}</div>
<div class="section"><h2>Item by item, which is where a compensating change lives</h2>
<p>An aggregate delta is the difference between the first two cells below. The
number of people affected is their sum. Those are different quantities, and the
second cannot be recovered from the first.</p>
<div class="flow">
{_cell("passed, now fails", counts.pass_to_fail, "flow-broke")}
{_cell("failed, now passes", counts.fail_to_pass, "flow-fixed")}
{_cell("unchanged", counts.stayed_pass + counts.stayed_fail)}
{_cell("filtered as too small", counts.filtered_out)}
</div>
<p class="footnote">A crossing whose score moved by less than
{counts.minimum_movement} is counted as no change rather than dropped, because
removing it from the denominator would raise every rate by shrinking what they are
rates of.</p></div>
<div class="section"><h2>What this eval set can and cannot resolve</h2>
<table class="grid"><tbody>
<tr><td>observed delta</td>
<td class="numeric">{result.observed_delta:+.4f}</td></tr>
<tr><td>smallest detectable effect, paired</td>
<td class="numeric">{result.minimum_detectable:.4f}</td></tr>
<tr><td>smallest detectable effect, comparing two averages</td>
<td class="numeric">{result.minimum_detectable_unpaired:.4f}</td></tr>
<tr><td>what pairing is worth, on the same data</td>
<td class="numeric">{result.pairing_gain:.1f} times</td></tr>
<tr><td>items needed to resolve the configured threshold</td>
<td class="numeric">{result.items_needed}</td></tr>
</tbody></table></div>
<div class="section"><h2>Every gate, and what it is a function of</h2>
<table class="grid"><thead><tr><th>gate</th><th>decision</th><th>statistic</th>
<th>threshold</th><th>reads</th><th>note</th></tr></thead>
<tbody>{gate_rows}</tbody></table></div>
<div class="section"><h2>Graded against a truth no gate can see</h2>
<table class="grid"><tbody>
<tr><td>true aggregate effect</td>
<td class="numeric {truth_class}">{result.true_effect:+.4f}</td></tr>
{subgroup_row}
</tbody></table>
<p class="footnote">The green cell marks a truth that is exact by construction
rather than computed per replication. Two of the five scenarios have one, and they
are the only place a rate measured here is a rate rather than an estimate of
one.</p></div>
</div></body></html>
"""


def render_sweep_html(rows: Sequence[GateRow], *, scenarios: Sequence[str]) -> str:
    """The scenario sweep as one page: every gate against every scenario."""
    listed = list(rows)
    if not listed:
        raise ValueError("no rows to render")
    aa = [row for row in listed if row.scenario == "aa"]
    false_block = block_rate(listed, "combined", scenario="aa") if aa else Rate(0, 0)

    def cell(scenario: str, gate: str) -> str:
        rate = block_rate(listed, gate, scenario=scenario)
        return f'<td class="numeric {_class_for(scenario, gate, rate)}">{rate.render()}</td>'

    body = "".join(
        "<tr>"
        f"<td>{escape(scenario)}</td>"
        + "".join(cell(scenario, gate) for gate in GATE_NAMES)
        + "</tr>"
        for scenario in scenarios
    )
    tiles = [
        _tile("scenarios", str(len(scenarios)), "two with an exact true effect"),
        _tile(
            "replications each",
            str(sum(1 for row in listed if row.scenario == scenarios[0])),
            "every rate carries its interval",
        ),
        _tile(
            "false block rate, combined gate",
            false_block.render(),
            "on comparisons whose true effect is exactly zero",
        ),
        _tile(
            "gates compared",
            str(len(GATE_NAMES)),
            "graded on the same comparisons",
        ),
    ]
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>churngate sweep</title>
<style>{STYLESHEET}</style>
</head><body><div class="page">
<h1 class="masthead">Every gate, on scenarios whose truth is known</h1>
<p class="subtitle">Block rate with a Wilson interval. The top row's true effect is
exactly zero, so every block there is a false one.</p>
<span class="badge badge-alarm">The zero columns are the point</span>
<div class="tiles">{"".join(tiles)}</div>
<div class="section"><h2>Block rate by scenario and gate</h2>
<p>Green is the right answer for this scenario and red is the wrong one. The two
scenarios in the middle have an aggregate effect of about zero and a real
regression underneath it, which is why the first three columns read zero there.</p>
<table class="grid"><thead><tr><th>scenario</th>
{"".join(f"<th>{escape(gate)}</th>" for gate in GATE_NAMES)}
</tr></thead><tbody>{body}</tbody></table>
<p class="footnote">Every cell is a rate over the replications with a ninety five
percent Wilson interval. An interval rather than a point, because an early run of
this suite measured a false block rate of 0.084 at two hundred and fifty
replications for a test whose true level is 0.05, and the interval is what stops
that being read as a finding.</p></div>
</div></body></html>
"""


def _class_for(scenario: str, gate: str, rate: Rate) -> str:
    """Colour a cell by whether the gate did the right thing on this scenario.

    Right means blocking on the three scenarios that carry a real regression and
    not blocking on the two that do not. Encoded here rather than in the template
    so the rule is stated once and can be argued with.
    """
    del gate
    should_block = scenario in ("uniform", "compensating", "churn_only")
    if rate.denominator == 0:
        return ""
    high = rate.value > 0.5
    return "passed" if high == should_block else "blocked"
