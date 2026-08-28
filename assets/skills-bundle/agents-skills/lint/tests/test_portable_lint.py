from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


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

    def test_non_markdown_raw_wikilink_resolves_as_the_raw_file(self) -> None:
        temporary, root = self.make_wiki()
        self.addCleanup(temporary.cleanup)
        raw = root / "raw" / "observation.json"
        raw.write_text('{"observed": true}\n', encoding="utf-8")
        source = root / "wiki" / "guides" / "observation.md"
        source.write_text("# Observation\n\n[[raw/observation.json]]\n", encoding="utf-8")
        (root / "wiki" / "index.md").write_text("# Index\n", encoding="utf-8")

        result = RUNTIME.audit(root)
        self.assertEqual(result["broken_links"], [])

    def test_evidence_audit_exposes_partial_boilerplate_and_reverse_provenance(self) -> None:
        temporary, root = self.make_wiki()
        self.addCleanup(temporary.cleanup)
        sources = root / "wiki" / "sources"
        projects = root / "wiki" / "projects"
        sources.mkdir()
        projects.mkdir()
        (projects / "target.md").write_text(
            "---\ntype: project\nsources: []\n---\n# Target\n", encoding="utf-8"
        )
        for index in range(3):
            raw = root / "raw" / f"source-{index}.md"
            raw.write_text(f"raw {index}", encoding="utf-8")
            semantic = "semantic_status: reviewed\n" if index == 0 else ""
            (sources / f"source-{index}.md").write_text(
                "---\n"
                "type: source\n"
                f"id: SOURCE-{index}\n"
                "status: active\n"
                f"{semantic}"
                f"sources: [[raw/source-{index}.md]]\n"
                "---\n"
                f"# Source {index}\n\n"
                "## 핵심 내용\n\n- 동일한 일반 boilerplate\n\n"
                "## Wiki에 반영된 문서\n\n- [[projects/target]]\n",
                encoding="utf-8",
            )
        (root / "wiki" / "index.md").write_text("# Index\n", encoding="utf-8")

        result = RUNTIME.audit(root)
        self.assertEqual(result["semantic_source_status"], {"partial": 3})
        self.assertEqual(len(result["semantic_contract_failures"]), 1)
        self.assertEqual(result["semantic_contract_failures"][0]["path"], "wiki/sources/source-0.md")
        self.assertEqual(result["repeated_source_summaries"][0]["count"], 3)
        self.assertEqual(len(result["missing_reverse_provenance"]), 3)
        self.assertTrue(any("queries must disclose" in warning for warning in result["warnings"]))

    def test_code_raw_path_participates_in_reverse_provenance(self) -> None:
        temporary, root = self.make_wiki()
        self.addCleanup(temporary.cleanup)
        sources = root / "wiki" / "sources"
        projects = root / "wiki" / "projects"
        sources.mkdir()
        projects.mkdir()
        (root / "raw" / "tool.py").write_text("print('ok')\n", encoding="utf-8")
        (projects / "target.md").write_text(
            "---\ntype: project\nsources: [\"raw/tool.py\"]\n---\n# Target\n", encoding="utf-8"
        )
        (sources / "tool.py.md").write_text(
            "---\ntype: source\nid: SOURCE-CODE\nsemantic_status: partial\nsources: [\"raw/tool.py\"]\n---\n"
            "# Code Source\n\n## 핵심 주장\n\n- partial\n\n## Wiki에 반영된 문서\n\n- [[projects/target]]\n",
            encoding="utf-8",
        )
        (root / "wiki" / "index.md").write_text("# Index\n", encoding="utf-8")

        result = RUNTIME.audit(root)
        self.assertEqual(result["missing_reverse_provenance"], [])

    def test_wikilink_raw_target_is_deduplicated_before_semantic_review(self) -> None:
        temporary, root = self.make_wiki()
        self.addCleanup(temporary.cleanup)
        sources = root / "wiki" / "sources"
        sources.mkdir()
        (root / "raw" / "source.md").write_text("source\n", encoding="utf-8")
        (sources / "source.md").write_text(
            "---\ntype: source\nid: SOURCE-ONE\nsemantic_status: reviewed\nsources: [[raw/source.md]]\n---\n# Source\n",
            encoding="utf-8",
        )
        (root / "wiki" / "index.md").write_text("# Index\n", encoding="utf-8")

        class Contract:
            @staticmethod
            def review_source_record(*_args):
                return {"semantic_status": "reviewed", "errors": []}

        with patch.object(RUNTIME, "load_semantic_contract", return_value=Contract()):
            result = RUNTIME.audit(root)
        self.assertEqual(result["semantic_source_status"], {"reviewed": 1})
        self.assertEqual(result["semantic_contract_failures"], [])


if __name__ == "__main__":
    unittest.main()
