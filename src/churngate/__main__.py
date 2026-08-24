"""Entry point for `python -m churngate`, so the tool runs from a clone.

A reviewer following the README has not installed the package yet, and an extra
step between them and the headline number is an extra chance to stop.
"""

from __future__ import annotations

from .cli import main

raise SystemExit(main())
