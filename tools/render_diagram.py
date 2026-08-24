"""Render the architecture diagram to a committed SVG.

Written by hand rather than through a diagramming library, for four reasons that
each cost time on other projects.

GitHub's lazily loaded Mermaid renderer sometimes reports "Unable to render rich
display" for a diagram that parses correctly everywhere else. There is nothing to
fix in the source and no way to fix it from the repository, so the diagram is
committed as an image instead.

A diagram with HTML labels is not well formed XML, because the labels end up
inside a foreignObject with unclosed br tags. It displays when injected into a
live page and fails silently as an img src, with naturalWidth 0 and nothing in
any console. This file emits text and tspan only.

An img src needs intrinsic dimensions. A percentage width with no height leaves a
browser without an aspect ratio and it picks a default.

A transparent background is not theme neutral. Node fills are light with dark
text either way, so an unfilled label comes out dark grey on near black in a dark
theme. One opaque rectangle covers the whole viewBox.

Usage:
    python tools/render_diagram.py
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree

REPO = Path(__file__).resolve().parents[1]
OUTPUT = REPO / "docs" / "diagrams" / "architecture.svg"
MANIFEST = REPO / "docs" / "diagrams" / "manifest.json"

WIDTH = 1000
HEIGHT = 748
FONT = "-apple-system, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif"
MONO = "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace"

INK = "#14171a"
MUTED = "#5b636b"
LINE = "#9aa2aa"
PAPER = "#ffffff"
PANEL = "#f2f4f6"
BLIND_FILL = "#fdf0d8"
BLIND_EDGE = "#e5c583"
SEEING_FILL = "#eef4ea"
SEEING_EDGE = "#b3cba4"
DATA_FILL = "#e8eef5"
DATA_EDGE = "#a9bed4"
METHOD_FILL = "#ffffff"
METHOD_EDGE = "#8f9aa4"


@dataclass(frozen=True)
class Box:
    x: int
    y: int
    width: int
    height: int
    title: str
    lines: tuple[str, ...] = ()
    fill: str = METHOD_FILL
    edge: str = METHOD_EDGE
    mono: bool = False

    @property
    def centre_x(self) -> int:
        return self.x + self.width // 2

    @property
    def bottom(self) -> int:
        return self.y + self.height


RUNS = Box(
    40,
    62,
    920,
    92,
    "Two runs of an eval, scored on the same items",
    (
        "A baseline and a candidate. Both are scored on the same items, so the item to item",
        "spread cancels exactly when the comparison is made item by item and not at all when",
        "two averages are compared. That is worth a factor of four in what is detectable.",
    ),
    fill=DATA_FILL,
    edge=DATA_EDGE,
)

CELLS = Box(
    40,
    204,
    440,
    108,
    "Four transition cells",
    (
        "passed and now fails, failed and now",
        "passes, and the two that did not move.",
        "Their sum is who is affected.",
    ),
    fill=SEEING_FILL,
    edge=SEEING_EDGE,
)

AGGREGATE = Box(
    520,
    204,
    440,
    108,
    "One aggregate delta",
    (
        "the difference of two means, which is",
        "the difference between the first two",
        "cells. Their sum does not survive it.",
    ),
    fill=BLIND_FILL,
    edge=BLIND_EDGE,
)

GATES = (
    Box(
        40,
        374,
        222,
        112,
        "churn",
        ("counts crossings", "instead of differencing", "them. Sees pure churn"),
        fill=SEEING_FILL,
        edge=SEEING_EDGE,
    ),
    Box(
        278,
        374,
        222,
        112,
        "slice_scan",
        ("tests a partition", "rather than a total.", "Sees a collapsed slice"),
        fill=SEEING_FILL,
        edge=SEEING_EDGE,
    ),
    Box(
        516,
        374,
        222,
        112,
        "paired tests",
        ("read the per item", "deltas. Powerful, and", "still aggregate"),
        fill=BLIND_FILL,
        edge=BLIND_EDGE,
    ),
    Box(
        754,
        374,
        206,
        112,
        "mean_threshold",
        ("reads two numbers", "misses both zero", "aggregate regressions"),
        fill=BLIND_FILL,
        edge=BLIND_EDGE,
    ),
)

ANCHOR = Box(
    40,
    520,
    920,
    76,
    "Graded against an A/A comparison, where the true effect is exactly zero",
    (
        "Every block here is a false block and every point of churn is noise. That is what"
        " turns a false block rate",
        "from an assumption into a measurement, and it is where the churn floor comes from.",
    ),
    fill=PANEL,
    edge=METHOD_EDGE,
)

VERDICT = Box(
    250,
    620,
    500,
    92,
    "Verdict, and the exit code that carries it",
    (
        "0  the candidate passes, resolvably",
        "1  a regression was detected",
        "2  this eval set cannot resolve it",
    ),
    fill=PANEL,
    edge=METHOD_EDGE,
    mono=True,
)


def element(parent: ElementTree.Element, tag: str, **attributes: object) -> ElementTree.Element:
    return ElementTree.SubElement(
        parent, tag, {key.replace("_", "-"): str(value) for key, value in attributes.items()}
    )


def text(
    parent: ElementTree.Element,
    x: int,
    y: int,
    content: str,
    *,
    size: float = 13,
    weight: str = "400",
    fill: str = INK,
    anchor: str = "start",
    family: str = FONT,
) -> None:
    node = element(
        parent,
        "text",
        x=x,
        y=y,
        fill=fill,
        font_size=size,
        font_weight=weight,
        font_family=family,
        text_anchor=anchor,
    )
    span = ElementTree.SubElement(node, "tspan")
    span.text = content


def draw_box(parent: ElementTree.Element, box: Box) -> None:
    element(
        parent,
        "rect",
        x=box.x,
        y=box.y,
        width=box.width,
        height=box.height,
        rx=6,
        fill=box.fill,
        stroke=box.edge,
        stroke_width=1.2,
    )
    text(parent, box.x + 14, box.y + 25, box.title, size=13.5, weight="650")
    for index, line in enumerate(box.lines):
        text(
            parent,
            box.x + 14,
            box.y + 46 + index * (17 if box.mono else 19),
            line,
            size=11.5,
            fill=MUTED,
            family=MONO if box.mono else FONT,
        )


def draw_arrow(parent: ElementTree.Element, x1: int, y1: int, x2: int, y2: int) -> None:
    element(
        parent,
        "line",
        x1=x1,
        y1=y1,
        x2=x2,
        y2=y2,
        stroke=LINE,
        stroke_width=1.2,
        marker_end="url(#arrow)",
    )


def build() -> ElementTree.Element:
    svg = ElementTree.Element(
        "svg",
        {
            "xmlns": "http://www.w3.org/2000/svg",
            "viewBox": f"0 0 {WIDTH} {HEIGHT}",
            "width": str(WIDTH),
            "height": str(HEIGHT),
            "role": "img",
            "aria-label": (
                "What the aggregate is a function of, what the transitions are a function "
                "of, and which gate reads which"
            ),
        },
    )
    defs = element(svg, "defs")
    marker = element(
        defs,
        "marker",
        id="arrow",
        viewBox="0 0 10 10",
        refX=9,
        refY=5,
        markerWidth=7,
        markerHeight=7,
        orient="auto-start-reverse",
    )
    element(marker, "path", d="M 0 0 L 10 5 L 0 10 z", fill=LINE)

    element(svg, "rect", x=0, y=0, width=WIDTH, height=HEIGHT, fill=PAPER)
    text(
        svg,
        40,
        32,
        "churngate: the aggregate is the difference of two cells, and the churn is their sum",
        size=15,
        weight="650",
    )

    draw_box(svg, RUNS)
    draw_arrow(svg, CELLS.centre_x, RUNS.bottom + 2, CELLS.centre_x, CELLS.y - 4)
    draw_arrow(svg, AGGREGATE.centre_x, RUNS.bottom + 2, AGGREGATE.centre_x, AGGREGATE.y - 4)
    draw_box(svg, CELLS)
    draw_box(svg, AGGREGATE)
    # The one arrow that carries the whole argument: the aggregate is derived from
    # the cells, so it cannot hold anything they do not, and it drops their sum.
    draw_arrow(svg, CELLS.x + CELLS.width + 2, 258, AGGREGATE.x - 4, 258)
    text(svg, 500, 250, "derived from", size=10.5, fill=MUTED, anchor="middle")

    for box in GATES:
        source = CELLS if box.fill == SEEING_FILL else AGGREGATE
        draw_arrow(svg, source.centre_x, source.bottom + 2, box.centre_x, box.y - 4)
        draw_box(svg, box)
        draw_arrow(svg, box.centre_x, box.bottom + 2, box.centre_x, ANCHOR.y - 4)
    draw_box(svg, ANCHOR)
    draw_arrow(svg, ANCHOR.centre_x, ANCHOR.bottom + 2, VERDICT.centre_x, VERDICT.y - 4)
    draw_box(svg, VERDICT)
    text(
        svg,
        40,
        HEIGHT - 10,
        "Amber reads the aggregate and cannot see a regression that keeps the mean. Green reads "
        "the cells.",
        size=11.5,
        fill=MUTED,
    )
    return svg


def main() -> int:
    svg = build()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    ElementTree.indent(svg, space="  ")
    payload = ElementTree.tostring(svg, encoding="unicode", xml_declaration=False)
    OUTPUT.write_text('<?xml version="1.0" encoding="UTF-8"?>\n' + payload + "\n", encoding="utf-8")

    # Parsing the file back is the check that matters: an img src silently fails
    # to load a document that is not well formed, with nothing in any console.
    ElementTree.parse(OUTPUT)
    MANIFEST.write_text(
        json.dumps(
            {
                "file": str(OUTPUT.relative_to(REPO)),
                "width": WIDTH,
                "height": HEIGHT,
                "generated_by": "tools/render_diagram.py",
                "labels": "text and tspan only, no foreignObject",
                "background": "one opaque rectangle covering the whole viewBox",
                "boxes": len(GATES) + 4,
                "bytes": OUTPUT.stat().st_size,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"wrote {OUTPUT.relative_to(REPO)} ({OUTPUT.stat().st_size} bytes, {WIDTH}x{HEIGHT})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
