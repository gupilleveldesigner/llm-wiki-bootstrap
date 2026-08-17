from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path


RUNTIME_PATH = Path(__file__).parents[1] / "scripts" / "audit_wiki.py"
SPEC = importlib.util.spec_from_file_location("audit_wiki", RUNTIME_PATH)
assert SPEC and SPEC.loader
RUNTIME = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RUNTIME)


class PortableLintTests(unittest.TestCase):
    def make_wiki(
        self, *, include_raw: bool = True
    ) -> tuple[tempfile.TemporaryDirectory[str], Path]:
        temporary = tempfile.TemporaryDirectory()
        root = Path(temporary.name)
        if include_raw:
            (root / "raw").mkdir()
        (root / "wiki" / "concepts").mkdir(parents=True)
        (root / "wiki" / "guides").mkdir()
        return temporary, root

    def test_projectmoon_schema_does_not_require_current_vault_fields(self) -> None:
        temporary, root = self.make_wiki()
        self.addCleanup(temporary.cleanup)
        concept = root / "wiki" / "concepts" / "combat.md"
        concept.write_text(
            "---\n"
            "name: Combat\n"
            "description: Combat contract\n"
            "date: 2026-07-27\n"
            "tags: [gas]\n"
            "---\n"
            "# Combat\n",
            encoding="utf-8",
        )
        (root / "wiki" / "index.md").write_text(
            "# Index\n\n- [[concepts/combat]]\n", encoding="utf-8"
        )

        result = RUNTIME.audit(
            root,
            required_fields=("name", "description", "date", "tags"),
            managed_dirs=("concepts", "guides"),
        )
        self.assertEqual(result["missing_fields"], [])
        self.assertNotIn("type", result["schema"]["required_fields"])
        self.assertEqual(result["unindexed"], [])

    def test_current_schema_remains_supported(self) -> None:
        temporary, root = self.make_wiki()
        self.addCleanup(temporary.cleanup)
        concept = root / "wiki" / "concepts" / "context.md"
        concept.write_text(
            "---\n"
            "type: concept\n"
            "status: review\n"
            "topics: [context]\n"
            "sources: []\n"
            "created: 2026-07-27\n"
            "updated: 2026-07-27\n"
            "---\n"
            "# Context\n",
            encoding="utf-8",
        )
        (root / "wiki" / "index.md").write_text(
            "# Index\n\n- [[concepts/context]]\n", encoding="utf-8"
        )

        result = RUNTIME.audit(
            root,
            required_fields=(
                "type",
                "status",
                "topics",
                "sources",
                "created",
                "updated",
            ),
            managed_dirs=("concepts",),
        )
        self.assertEqual(result["missing_fields"], [])

    def test_required_fields_are_disabled_when_not_supplied(self) -> None:
        temporary, root = self.make_wiki()
        self.addCleanup(temporary.cleanup)
        (root / "wiki" / "guides" / "plain.md").write_text(
            "# Plain\n", encoding="utf-8"
        )
        (root / "wiki" / "index.md").write_text("# Index\n", encoding="utf-8")

        result = RUNTIME.audit(root)
        self.assertEqual(result["missing_fields"], [])
        self.assertTrue(result["warnings"])

    def test_wiki_without_raw_is_supported(self) -> None:
        temporary, root = self.make_wiki(include_raw=False)
        self.addCleanup(temporary.cleanup)
        (root / "wiki" / "index.md").write_text("# Index\n", encoding="utf-8")
        self.assertEqual(RUNTIME.find_wiki_root(root / "wiki"), root)
        self.assertIsNone(RUNTIME.status_payload(root)["raw"])

    def test_generated_graph_output_is_excluded(self) -> None:
        temporary, root = self.make_wiki()
        self.addCleanup(temporary.cleanup)
        (root / "wiki" / "index.md").write_text("# Index\n", encoding="utf-8")
        generated = root / "wiki" / "graphify-out"
        generated.mkdir()
        (generated / "GRAPH_REPORT.md").write_text("# Generated\n", encoding="utf-8")
        self.assertNotIn(generated / "GRAPH_REPORT.md", RUNTIME.note_files(root))


if __name__ == "__main__":
    unittest.main()
