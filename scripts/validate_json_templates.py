from __future__ import annotations

import json
from pathlib import Path


def main() -> int:
    repository_root = Path(__file__).resolve().parent.parent
    assets = repository_root / "assets"
    paths = [*assets.rglob("*.json.template"), *(assets / "project-modes/game/ingest").rglob("*.json")]
    for path in paths:
        json.loads(path.read_text(encoding="utf-8"))
    print(f"validated_json_files={len(paths)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
