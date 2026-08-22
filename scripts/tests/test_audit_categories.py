from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[2] / "assets/skills-bundle/agents-skills/ingest/scripts"))
from audit_categories import audit  # noqa: E402


class CategoryAuditTests(unittest.TestCase):
    def make_root(self) -> Path:
        temporary = Path(tempfile.mkdtemp(prefix="category-audit-"))
        (temporary / "raw").mkdir()
        (temporary / "wiki" / "sources").mkdir(parents=True)
        (temporary / "wiki" / "concepts").mkdir()
        (temporary / "wiki" / "taxonomy.json").write_text(
            json.dumps(
                {
                    "version": 1,
                    "scheme": {"id": "topics", "prefLabel": "Topics", "scopeNote": "Test"},
                    "concepts": [
                        {"id": "design", "prefLabel": "Design", "altLabel": ["설계"], "scopeNote": "Design work", "broader": []}
                    ],
                }
            ),
            encoding="utf-8",
        )
        return temporary

    def test_accepts_preferred_and_alternate_labels(self) -> None:
        root = self.make_root()
        (root / "wiki" / "concepts" / "x.md").write_text("---\ntopics: [설계]\n---\n# X\n", encoding="utf-8")
        result = audit(root)
        self.assertTrue(result["valid"])

    def test_rejects_unmapped_label(self) -> None:
        root = self.make_root()
        (root / "wiki" / "concepts" / "x.md").write_text("---\ntopics: [unknown]\n---\n# X\n", encoding="utf-8")
        result = audit(root)
        self.assertFalse(result["valid"])
        self.assertTrue(any("unmapped category" in error for error in result["errors"]))

    def test_rejects_alias_collision_and_cycle(self) -> None:
        root = self.make_root()
        (root / "wiki" / "taxonomy.json").write_text(
            json.dumps(
                {
                    "version": 1,
                    "scheme": {"id": "topics", "prefLabel": "Topics", "scopeNote": "Test"},
                    "concepts": [
                        {"id": "a", "prefLabel": "A", "altLabel": ["same"], "scopeNote": "A", "broader": ["b"]},
                        {"id": "b", "prefLabel": "B", "altLabel": ["same"], "scopeNote": "B", "broader": ["a"]},
                    ],
                }
            ),
            encoding="utf-8",
        )
        result = audit(root)
        self.assertFalse(result["valid"])
        self.assertTrue(any("ambiguous taxonomy label" in error for error in result["errors"]))
        self.assertTrue(any("taxonomy cycle" in error for error in result["errors"]))

    def test_rejects_malformed_skos_fields_and_missing_topics(self) -> None:
        root = self.make_root()
        (root / "wiki" / "taxonomy.json").write_text(
            json.dumps(
                {
                    "version": 1,
                    "scheme": {"id": "topics", "prefLabel": "Topics", "scopeNote": "Test"},
                    "concepts": [{"id": "design", "prefLabel": None, "altLabel": "bad", "scopeNote": None, "broader": []}],
                }
            ),
            encoding="utf-8",
        )
        (root / "wiki" / "concepts" / "x.md").write_text("# X\n", encoding="utf-8")
        result = audit(root)
        self.assertFalse(result["valid"])
        self.assertTrue(any("altLabel must be" in error for error in result["errors"]))
        self.assertTrue(any("no prefLabel" in error for error in result["errors"]))
        self.assertTrue(any("no topics/tags" in error for error in result["errors"]))


if __name__ == "__main__":
    unittest.main()
