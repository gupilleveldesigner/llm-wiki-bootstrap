#!/usr/bin/env python3
"""Claude adapter for the canonical host-neutral query runtime."""

from __future__ import annotations

import runpy
from pathlib import Path


CANONICAL = (
    Path(__file__).resolve().parents[4]
    / ".agents"
    / "skills"
    / "query"
    / "scripts"
    / "query_runtime.py"
)
if not CANONICAL.is_file():
    raise SystemExit(f"Canonical query runtime is missing: {CANONICAL}")
runpy.run_path(str(CANONICAL), run_name="__main__")
