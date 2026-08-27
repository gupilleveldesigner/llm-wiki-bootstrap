from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))
from bootstrap import bootstrap, upgrade  # noqa: E402


def write_config(root: Path, name: str = "Test Wiki") -> Path:
    path = root / "config.json"
    path.write_text(json.dumps({"project_name": name, "domain_summary": "test evidence research"}), encoding="utf-8")
    return path


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

    def test_evidence_profile_scaffolds_epistemic_layers(self) -> None:
        with tempfile.TemporaryDirectory(prefix="bootstrap-evidence-") as temporary:
            root = Path(temporary)
            target = root / "vault"
            config = write_config(root)
            result = bootstrap(target, config, "new", "evidence")

            self.assertTrue(result["ok"])
            self.assertEqual(result["profile"], "evidence")
            for relative in (
                "wiki/claims",
                "wiki/canon",
                "wiki/conflicts",
                "wiki/experiments",
                "wiki/questions/open",
                ".wiki-cache/normalized",
                ".wiki-cache/index",
                ".wiki-cache/embeddings",
            ):
                self.assertTrue((target / relative).is_dir(), relative)

            manifest = json.loads((target / ".llm-wiki.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["schema_version"], 2)
            self.assertEqual(manifest["profile"], "evidence")
            self.assertTrue(manifest["raw_immutable"])
            self.assertTrue((target / "wiki/evidence-model.md").is_file())
            self.assertTrue((target / "instructions/evidence-operations.md").is_file())
            self.assertTrue((target / ".agents/skills/canon-review/SKILL.md").is_file())
            self.assertTrue((target / ".claude/skills/canon-review/SKILL.md").is_file())
            self.assertTrue((target / "templates/evidence/claim.md").is_file())

    def test_standard_profile_does_not_install_canon_review(self) -> None:
        with tempfile.TemporaryDirectory(prefix="bootstrap-standard-") as temporary:
            root = Path(temporary)
            target = root / "vault"
            config = write_config(root)
            result = bootstrap(target, config, "new", "standard")

            self.assertEqual(result["profile"], "standard")
            self.assertFalse((target / "wiki/claims").exists())
            self.assertFalse((target / ".agents/skills/canon-review").exists())
            manifest = json.loads((target / ".llm-wiki.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["profile"], "standard")

    def test_upgrade_can_promote_legacy_standard_to_evidence_non_destructively(self) -> None:
        with tempfile.TemporaryDirectory(prefix="bootstrap-upgrade-evidence-") as temporary:
            root = Path(temporary)
            target = root / "vault"
            config = write_config(root)
            bootstrap(target, config, "new", "standard")
            raw_file = target / "raw/personal/original.md"
            raw_file.write_text("immutable source", encoding="utf-8")
            original = raw_file.read_text(encoding="utf-8")

            result = upgrade(target, config, "evidence")

            self.assertEqual(result["profile"], "evidence")
            self.assertTrue(result["profile_changed"])
            self.assertTrue(result["profile_activation_pending"])
            self.assertEqual(raw_file.read_text(encoding="utf-8"), original)
            self.assertTrue((target / "wiki/claims").is_dir())
            self.assertTrue((target / ".agents/skills/canon-review/SKILL.md").is_file())
            self.assertTrue(any(path.endswith("CLAUDE.md.wiki-proposed") for path in result["proposals"]))

    def test_upgrade_preserves_evidence_profile_when_profile_omitted(self) -> None:
        with tempfile.TemporaryDirectory(prefix="bootstrap-upgrade-preserve-") as temporary:
            root = Path(temporary)
            target = root / "vault"
            config = write_config(root)
            bootstrap(target, config, "new", "evidence")
            result = upgrade(target, config)
            self.assertEqual(result["profile"], "evidence")
            self.assertFalse(result["profile_changed"])
            self.assertTrue((target / ".agents/skills/canon-review/SKILL.md").is_file())

    def test_upgrade_preserves_user_managed_canon_overview(self) -> None:
        with tempfile.TemporaryDirectory(prefix="bootstrap-canon-preserve-") as temporary:
            root = Path(temporary)
            target = root / "vault"
            config = write_config(root)
            bootstrap(target, config, "new", "evidence")
            canon = target / "wiki/canon/overview.md"
            canon.write_text("# reviewed canon\nuser decision\n", encoding="utf-8")
            upgrade(target, config)
            self.assertEqual(canon.read_text(encoding="utf-8"), "# reviewed canon\nuser decision\n")
            self.assertFalse((target / "wiki/canon/overview.md.wiki-proposed").exists())

    def test_upgrade_refuses_evidence_downgrade(self) -> None:
        with tempfile.TemporaryDirectory(prefix="bootstrap-no-downgrade-") as temporary:
            root = Path(temporary)
            target = root / "vault"
            config = write_config(root)
            bootstrap(target, config, "new", "evidence")
            with self.assertRaisesRegex(ValueError, "cannot downgrade"):
                upgrade(target, config, "standard")


if __name__ == "__main__":
    unittest.main()
