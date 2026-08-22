from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))
from bootstrap import bootstrap, upgrade  # noqa: E402


class BootstrapSafetyTests(unittest.TestCase):
    def test_new_rejects_nonempty_folder(self) -> None:
        with tempfile.TemporaryDirectory(prefix="bootstrap-nonempty-") as temporary:
            target = Path(temporary) / "vault"
            target.mkdir()
            (target / "existing.md").write_text("existing", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "not empty"):
                bootstrap(target, target / "missing.json", "new")

    def test_upgrade_rejects_agents_only_folder(self) -> None:
        with tempfile.TemporaryDirectory(prefix="bootstrap-agents-only-") as temporary:
            target = Path(temporary) / "project"
            (target / ".agents").mkdir(parents=True)
            with self.assertRaisesRegex(ValueError, "not an LLM Wiki"):
                upgrade(target, target / "missing.json")


if __name__ == "__main__":
    unittest.main()
