#!/usr/bin/env python3
"""Claude adapter for the canonical ingest skill installer."""

from __future__ import annotations

import runpy
from pathlib import Path


CANONICAL = (
    Path(__file__).resolve().parents[4]
    / ".agents"
    / "skills"
    / "ingest"
    / "scripts"
    / "install_to_wiki.py"
)
if not CANONICAL.is_file():
    raise SystemExit(f"Canonical ingest installer is missing: {CANONICAL}")
runpy.run_path(str(CANONICAL), run_name="__main__")
