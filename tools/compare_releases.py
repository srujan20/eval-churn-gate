"""Say what moved between two releases, reading both sides out of git.

Every repository here re-measures its published figures into `docs/metrics.json`,
and every release tags a commit that carries one. So the honest way to describe a
release is not to write down what changed, it is to read the metrics file out of
the old tag, read the current one, and report the difference.

That is what this does. Nothing is typed, and neither side is a committed copy
that could drift: the baseline is `git show <tag>:docs/metrics.json`, so it is
whatever that tag actually published.

Three outcomes, and the middle one is the interesting column in a release note.

  held      the figure is byte identical to the tagged release
  moved     the figure changed, and by how much
  added     the figure did not exist at the tagged release
  removed   the figure existed at the tagged release and no longer does

A release whose findings all held, with only added figures beside them, is a
release that extended the work without disturbing it. A release with moved
figures has to say why in its notes, which is the point.

Usage:
    python tools/compare_releases.py                  # against the latest tag
    python tools/compare_releases.py --since v1.0.0
    python tools/compare_releases.py --since v1.0.0 --json docs/delta.json
    python tools/compare_releases.py --check docs/CHANGELOG.md
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
METRICS = REPO / "docs" / "metrics.json"


def git(*args: str) -> str:
    done = subprocess.run(
        ["git", "-C", str(REPO), *args], capture_output=True, text=True, check=False
    )
    if done.returncode != 0:
        raise SystemExit(f"git {' '.join(args)} failed: {done.stderr.strip()}")
    return done.stdout


def latest_tag() -> str:
    tags = [line.strip() for line in git("tag", "-l", "v*").splitlines() if line.strip()]
    if not tags:
        raise SystemExit(
            "no v* tag in this checkout, so there is no release to compare against. "
            "Fetch tags with: git fetch --tags"
        )

    def key(tag: str) -> tuple:
        return tuple(int(part) for part in re.findall(r"\d+", tag))

    return sorted(tags, key=key)[-1]


def metrics_at(tag: str) -> dict:
    raw = git("show", f"{tag}:docs/metrics.json")
    return json.loads(raw)["metrics"]


def current_metrics() -> dict:
    if not METRICS.is_file():
        raise SystemExit(
            f"{METRICS.relative_to(REPO)} is missing. Run tools/collect_metrics.py first."
        )
    return json.loads(METRICS.read_text(encoding="utf-8"))["metrics"]


def classify(before: dict, after: dict) -> dict[str, list]:
    held, moved, added, removed = [], [], [], []
    for name in sorted(set(before) | set(after)):
        was, now = before.get(name), after.get(name)
        if name not in before:
            added.append((name, now))
        elif name not in after:
            removed.append((name, was))
        elif was == now:
            held.append((name, now))
        else:
            moved.append((name, was, now))
    return {"held": held, "moved": moved, "added": added, "removed": removed}


def headline(name: str) -> bool:
    """Whether a figure is one a reader would recognise, rather than a table cell."""
    return not name.startswith(("cell_", "label_"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--since", help="tag to compare against (default: the latest v* tag)")
    parser.add_argument("--json", help="write the comparison here")
    parser.add_argument(
        "--check",
        help="a document whose 'held' and 'moved' counts must match this comparison",
    )
    args = parser.parse_args(argv)

    tag = args.since or latest_tag()
    before, after = metrics_at(tag), current_metrics()
    groups = classify(before, after)

    print(f"comparing the working tree against {tag}")
    print(
        f"  {len(groups['held'])} held, {len(groups['moved'])} moved, "
        f"{len(groups['added'])} added, {len(groups['removed'])} removed"
    )
    for kind in ("moved", "added", "removed"):
        rows = [row for row in groups[kind] if headline(row[0])]
        if not rows:
            continue
        print()
        print(f"  {kind}:")
        for row in rows:
            if kind == "moved":
                print(f"    {row[0]:38} {row[1]} -> {row[2]}")
            else:
                print(f"    {row[0]:38} {row[1]}")

    payload = {
        "baseline_tag": tag,
        "counts": {kind: len(rows) for kind, rows in groups.items()},
        "moved": [{"metric": n, "was": w, "now": c} for n, w, c in groups["moved"]],
        "added": dict(groups["added"]),
        "removed": dict(groups["removed"]),
        "note": "both sides are read from git, so neither is a copy that can drift",
    }
    if args.json:
        Path(args.json).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", "utf-8")
        print(f"\nwrote {args.json}")

    if args.check:
        document = Path(REPO / args.check)
        if not document.is_file():
            print(f"missing document to check: {args.check}", file=sys.stderr)
            return 2
        prose = re.sub(r"\s+", " ", document.read_text(encoding="utf-8"))
        problems = []
        for kind in ("held", "moved"):
            phrase = f"{len(groups[kind])} figures {kind}"
            if phrase not in prose:
                problems.append(f'{args.check} does not say "{phrase}"')
        for name, was, now in groups["moved"]:
            if not headline(name):
                continue
            if f"{was} to {now}" not in prose:
                problems.append(f'{args.check} does not record {name} moving "{was} to {now}"')
        for problem in problems:
            print(f"MISMATCH  {problem}")
        if problems:
            print(
                f"{len(problems)} claims in {args.check} do not match the comparison",
                file=sys.stderr,
            )
            return 1
        print(f"{args.check} matches the comparison")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
