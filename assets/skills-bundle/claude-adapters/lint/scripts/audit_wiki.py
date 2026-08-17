#!/usr/bin/env python3
"""Claude adapter for the canonical host-neutral lint audit."""

from __future__ import annotations

import runpy
from pathlib import Path


CANONICAL = (
    Path(__file__).resolve().parents[4]
    / ".agents"
    / "skills"
    / "lint"
    / "scripts"
    / "audit_wiki.py"
)
if not CANONICAL.is_file():
    raise SystemExit(f"Canonical lint audit is missing: {CANONICAL}")
runpy.run_path(str(CANONICAL), run_name="__main__")
