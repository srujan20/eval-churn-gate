"""Photograph the real HTML report with Chromium, and check it is legible.

Three rules, each from a failure on an earlier project.

Frame by heading, not by pixel offset. The tool scrolls to a named h2, reads its
document offset, and clips from there to the next named heading. A hard coded
crop drifts silently the first time a paragraph gets longer, and then the README
shows half a table. A missing heading fails the run, because it means the report
changed shape and the shot is now meaningless.

Pass full_page even when a clip is given. Without it Chromium clamps the clip to
the viewport and every shot comes out exactly one viewport tall with the bottom
of the section missing.

Read back the computed style of the verdict badge and fail if it is invisible. A
badge class and a table cell class once collided at equal specificity, the later
rule won, and the verdict rendered green on green. The Python was correct, the
HTML was correct, the tests passed, and the headline number was invisible. A
screenshot tool is the only thing in the pipeline that can see pixels.

Usage:
    python tools/capture_screenshots.py
"""

from __future__ import annotations

import json
from pathlib import Path

from playwright.sync_api import sync_playwright

REPO = Path(__file__).resolve().parents[1]
SHOTS = REPO / "docs" / "screenshots"
BUILD = REPO / ".cache" / "reports"

VIEWPORT = {"width": 1120, "height": 900}
SCALE = 2

SHOT_PLAN = (
    {
        "name": "gate-compensating",
        "report": "gate",
        "from_heading": "What this eval set can and cannot resolve",
        "to_heading": "Graded against a truth no gate can see",
        "caption": "One gated comparison where a slice collapsed and the aggregate did not move",
    },
    {
        "name": "gate-transitions",
        "report": "gate",
        "from_heading": "Item by item, which is where a compensating change lives",
        "to_heading": "What this eval set can and cannot resolve",
        "caption": "The four cells the aggregate is computed from",
    },
    {
        "name": "gate-truth",
        "report": "gate",
        "from_heading": "Graded against a truth no gate can see",
        "to_heading": None,
        "caption": "The truth the gates cannot see, with the exact ones marked",
    },
    {
        "name": "sweep-grid",
        "report": "sweep",
        "from_heading": "Block rate by scenario and gate",
        "to_heading": None,
        "caption": "Every gate on every scenario, with a Wilson interval on every rate",
    },
)


def build_reports() -> dict[str, Path]:
    """Build the reports rather than photographing whatever is on disk."""
    import sys

    sys.path.insert(0, str(REPO / "src"))
    sys.path.insert(0, str(REPO / "experiments"))
    from _shared import main_sweep

    from churngate.audit import audit
    from churngate.config import load_policy
    from churngate.report import render_html, render_sweep_html
    from churngate.runs import SCENARIOS, make_comparison

    BUILD.mkdir(parents=True, exist_ok=True)
    policy = load_policy()

    comparison = make_comparison("compensating", policy, 11)
    gate_path = BUILD / "gate.html"
    gate_path.write_text(render_html(audit(comparison, policy)), encoding="utf-8")

    rows = main_sweep(policy)
    sweep_path = BUILD / "sweep.html"
    sweep_path.write_text(render_sweep_html(rows, scenarios=SCENARIOS), encoding="utf-8")
    return {"gate": gate_path, "sweep": sweep_path}


BADGE_PROBE = """() => {
  const badge = document.querySelector('.badge');
  if (!badge) return null;
  const style = getComputedStyle(badge);
  return {
    colour: style.color,
    background: style.backgroundColor,
    border: style.borderColor,
    visible: badge.offsetWidth > 0 && badge.offsetHeight > 0,
    text: badge.textContent.trim(),
  };
}"""

HEADING_PROBE = """(title) => {
  const found = Array.from(document.querySelectorAll('h2'))
    .find(node => node.textContent.trim() === title);
  if (!found) return null;
  const box = found.getBoundingClientRect();
  return {top: box.top + window.scrollY, height: document.body.scrollHeight};
}"""


def luminance(colour: str) -> float:
    numbers = [float(part) for part in colour.replace("rgba", "rgb").strip("rgb()").split(",")[:3]]
    channels = []
    for value in numbers:
        scaled = value / 255.0
        channels.append(scaled / 12.92 if scaled <= 0.03928 else ((scaled + 0.055) / 1.055) ** 2.4)
    return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]


def contrast(foreground: str, background: str) -> float:
    first, second = luminance(foreground), luminance(background)
    lighter, darker = max(first, second), min(first, second)
    return (lighter + 0.05) / (darker + 0.05)


def main() -> int:
    reports = build_reports()
    SHOTS.mkdir(parents=True, exist_ok=True)
    manifest: list[dict[str, object]] = []

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport=VIEWPORT, device_scale_factor=SCALE)
        badges: dict[str, dict[str, object]] = {}

        for name, path in reports.items():
            page.goto(path.resolve().as_uri())
            page.wait_for_load_state("load")
            badge = page.evaluate(BADGE_PROBE)
            if badge is None or not badge["visible"]:
                raise SystemExit(f"the verdict badge is missing or invisible in the {name} report")
            ratio = contrast(str(badge["colour"]), str(badge["background"]))
            if ratio < 4.5:
                raise SystemExit(
                    f"the verdict badge in the {name} report has a contrast ratio of "
                    f"{ratio:.2f}, below the 4.5 needed to read it"
                )
            badges[name] = {**badge, "contrast_ratio": round(ratio, 2)}

        for plan in SHOT_PLAN:
            path = reports[plan["report"]]
            page.goto(path.resolve().as_uri())
            page.wait_for_load_state("load")
            start = page.evaluate(HEADING_PROBE, plan["from_heading"])
            if start is None:
                raise SystemExit(
                    f"heading {plan['from_heading']!r} is gone, so the shot would be meaningless"
                )
            if plan["to_heading"] is None:
                end_top = start["height"]
            else:
                end = page.evaluate(HEADING_PROBE, plan["to_heading"])
                if end is None:
                    raise SystemExit(f"heading {plan['to_heading']!r} is gone")
                end_top = end["top"]
            top = max(start["top"] - 18, 0)
            height = max(end_top - top - 12, 80)
            destination = SHOTS / f"{plan['name']}.png"
            page.screenshot(
                path=str(destination),
                full_page=True,
                clip={"x": 40, "y": top, "width": VIEWPORT["width"] - 80, "height": height},
            )
            manifest.append(
                {
                    "image": str(destination.relative_to(REPO)),
                    "report": str(path.relative_to(REPO)),
                    "framed_by": [plan["from_heading"], plan["to_heading"]],
                    "caption": plan["caption"],
                    "device_scale_factor": SCALE,
                    "badge": badges[plan["report"]],
                    "bytes": destination.stat().st_size,
                }
            )
            print(f"wrote {destination.relative_to(REPO)} ({destination.stat().st_size} bytes)")

        browser.close()

    (SHOTS / "manifest.json").write_text(
        json.dumps({"shots": manifest}, indent=2) + "\n", encoding="utf-8"
    )
    print(f"wrote {(SHOTS / 'manifest.json').relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
