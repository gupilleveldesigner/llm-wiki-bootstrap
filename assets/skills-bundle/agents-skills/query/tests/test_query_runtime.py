from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path


RUNTIME_PATH = Path(__file__).parents[1] / "scripts" / "query_runtime.py"
SPEC = importlib.util.spec_from_file_location("query_runtime", RUNTIME_PATH)
assert SPEC and SPEC.loader
RUNTIME = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RUNTIME)


class QueryRuntimeTests(unittest.TestCase):
    def make_wiki(
        self, *, include_raw: bool = True
    ) -> tuple[tempfile.TemporaryDirectory[str], Path]:
        temporary = tempfile.TemporaryDirectory()
        root = Path(temporary.name)
        if include_raw:
            (root / "raw").mkdir()
        (root / "wiki" / "guides").mkdir(parents=True)
        (root / "wiki" / "index.md").write_text(
            "# Index\n\n- [[guides/example]] — alternate-schema guide\n",
            encoding="utf-8",
        )
        return temporary, root

    def test_finds_root_from_nested_directory(self) -> None:
        temporary, root = self.make_wiki()
        self.addCleanup(temporary.cleanup)
        nested = root / "wiki" / "guides"
        self.assertEqual(RUNTIME.find_wiki_root(nested), root)

    def test_supports_wiki_without_raw_layer(self) -> None:
        temporary, root = self.make_wiki(include_raw=False)
        self.addCleanup(temporary.cleanup)
        nested = root / "wiki" / "guides"
        self.assertEqual(RUNTIME.find_wiki_root(nested), root)
        self.assertIsNone(RUNTIME.status_payload(root)["raw"])

    def test_extracts_only_frontmatter_from_alternate_schema(self) -> None:
        temporary, root = self.make_wiki()
        self.addCleanup(temporary.cleanup)
        document = root / "wiki" / "guides" / "example.md"
        document.write_text(
            "---\n"
            "kind: guide\n"
            "tags: [portable]\n"
            "source: raw/reference.md\n"
            "review_after: 2030-01-01\n"
            "---\n"
            "# SECRET_BODY_SENTINEL\n"
            "This body must not be emitted during candidate selection.\n",
            encoding="utf-8",
        )

        items, failed = RUNTIME.frontmatter_payload(root, ["guides/example"])
        self.assertFalse(failed)
        self.assertTrue(items[0]["has_frontmatter"])
        self.assertIn("kind: guide", items[0]["frontmatter"])
        self.assertNotIn("SECRET_BODY_SENTINEL", items[0]["frontmatter"])

    def test_reports_missing_frontmatter_without_reading_body(self) -> None:
        temporary, root = self.make_wiki()
        self.addCleanup(temporary.cleanup)
        document = root / "wiki" / "guides" / "plain.md"
        document.write_text("# PLAIN_BODY_SENTINEL\n", encoding="utf-8")

        items, failed = RUNTIME.frontmatter_payload(root, ["wiki/guides/plain.md"])
        self.assertFalse(failed)
        self.assertFalse(items[0]["has_frontmatter"])
        self.assertIsNone(items[0]["frontmatter"])
        self.assertNotIn("PLAIN_BODY_SENTINEL", RUNTIME.render_frontmatter(items))

    def test_rejects_files_outside_wiki(self) -> None:
        temporary, root = self.make_wiki()
        self.addCleanup(temporary.cleanup)
        source = root / "raw" / "reference.md"
        source.write_text("---\ntype: source\n---\n", encoding="utf-8")

        items, failed = RUNTIME.frontmatter_payload(root, ["raw/reference.md"])
        self.assertTrue(failed)
        self.assertIn("inside wiki/", items[0]["error"])


if __name__ == "__main__":
    unittest.main()
