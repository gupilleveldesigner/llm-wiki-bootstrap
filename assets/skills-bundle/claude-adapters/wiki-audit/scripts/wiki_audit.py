#!/usr/bin/env python3
"""Claude adapter for the canonical Wiki Audit script."""

from __future__ import annotations

import runpy
from pathlib import Path


CANONICAL = Path(__file__).resolve().parents[4] / ".agents" / "skills" / "wiki-audit" / "scripts" / "wiki_audit.py"
if not CANONICAL.is_file():
    raise SystemExit(f"Canonical Wiki Audit script is missing: {CANONICAL}")
runpy.run_path(str(CANONICAL), run_name="__main__")
