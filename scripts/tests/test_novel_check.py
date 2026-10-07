from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
RUNTIME = REPO / "assets/project-modes/novel/runtime/novel_check.py"
spec = importlib.util.spec_from_file_location("novel_check", RUNTIME)
assert spec and spec.loader
novel = importlib.util.module_from_spec(spec)
spec.loader.exec_module(novel)


def document(root: Path, folder: str, name: str, **data: object) -> Path:
    kind, id_key = novel.SCHEMAS[folder]
    metadata = {"type": kind, id_key: name, "title": name, **data}
    content = "---\n" + "\n".join(f"{key}: {json.dumps(value, ensure_ascii=False)}" for key, value in metadata.items()) + "\n---\n\n# Fiction\n"
    path = root / "wiki/novel" / folder / f"{name}.md"
    path.write_text(content, encoding="utf-8")
    return path


def make_vault(root: Path) -> None:
    (root / ".llm-wiki.json").write_text(json.dumps({"project_mode": "novel", "project_mode_version": 1}), encoding="utf-8")
    for folder in novel.SCHEMAS:
        (root / "wiki/novel" / folder).mkdir(parents=True)
    manuscripts = root / "manuscripts/novel/drafts"
    manuscripts.mkdir(parents=True)
    (manuscripts / "scene1.md").write_text("Original prose\n", encoding="utf-8")
    (manuscripts / "scene2.md").write_text("Payoff prose\n", encoding="utf-8")
    document(root, "characters", "CHAR-001", canon_status="accepted")
    document(root, "locations", "LOC-001", canon_status="accepted")
    document(root, "world", "RULE-001", canon_status="accepted")
    document(root, "chapters", "CH-001", status="drafted", order=1, scene_refs=["SCENE-001"])
    document(root, "chapters", "CH-002", status="planned", order=2, scene_refs=["SCENE-002"])
    for number in (1, 2):
        document(root, "scenes", f"SCENE-00{number}", status="drafted", chapter_ref=f"CH-00{number}", sequence=1,
                 pov_ref="CHAR-001", character_refs=["CHAR-001"], location_ref="LOC-001", rule_refs=["RULE-001"],
                 manuscript_ref=f"manuscripts/novel/drafts/scene{number}.md")
    document(root, "timeline", "EVENT-001", canon_status="accepted", time_start=10, time_end=20, scene_refs=["SCENE-001"])
    document(root, "foreshadowing", "FORESHADOW-001", status="resolved", setup_scene_refs=["SCENE-001"], payoff_scene_refs=["SCENE-002"])


def codes(root: Path) -> set[str]:
    return {item["code"] for item in novel.inspect(root)["issues"]}


class NovelCheckTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        make_vault(self.root)

    def test_connected_outline_trace_and_read_only_cli(self) -> None:
        before = {str(path.relative_to(self.root)): path.read_bytes() for path in self.root.rglob("*") if path.is_file()}
        inspected = novel.inspect(self.root)
        self.assertEqual(inspected["summary"], {"errors": 0, "warnings": 0})
        self.assertEqual([chapter["id"] for chapter in novel.outline(inspected["documents"])], ["CH-001", "CH-002"])
        trace = novel.trace(inspected["documents"], "CHAR-001")
        self.assertEqual({item["id"] for item in trace["incoming"]}, {"SCENE-001", "SCENE-002"})
        for command in (["status"], ["check"], ["outline"], ["trace", "CHAR-001"]):
            result = subprocess.run([sys.executable, str(RUNTIME), "--root", str(self.root), *command], capture_output=True, text=True, encoding="utf-8")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            data = json.loads(result.stdout)
            self.assertTrue(data["read_only"])
            self.assertEqual(data["semantic_review"], "not_performed")
        after = {str(path.relative_to(self.root)): path.read_bytes() for path in self.root.rglob("*") if path.is_file()}
        self.assertEqual(before, after)

    def test_duplicate_ids_and_reading_positions_are_detected(self) -> None:
        original = self.root / "wiki/novel/characters/CHAR-001.md"
        (original.parent / "duplicate.md").write_bytes(original.read_bytes())
        document(self.root, "chapters", "CH-003", status="planned", order=1, scene_refs=[])
        document(self.root, "scenes", "SCENE-003", status="planned", chapter_ref="CH-001", sequence=1)
        self.assertTrue({"duplicate_id", "duplicate_order"}.issubset(codes(self.root)))

    def test_missing_and_wrong_type_references_and_chapter_mismatch(self) -> None:
        document(self.root, "scenes", "SCENE-001", status="planned", chapter_ref="CH-002", sequence=2,
                 pov_ref="LOC-001", character_refs=["CHAR-MISSING"])
        self.assertTrue({"missing_reference", "wrong_reference_type", "chapter_scene_mismatch", "unlisted_scene"}.issubset(codes(self.root)))

    def test_absent_manuscripts_and_unsafe_paths_are_not_followed(self) -> None:
        for path in ("manuscripts/novel/drafts/missing.md", "../outside.md", "/tmp/outside.md", "C:\\outside.md", "raw/book.md"):
            with self.subTest(path=path):
                document(self.root, "scenes", "SCENE-001", status="drafted", chapter_ref="CH-001", sequence=1, manuscript_ref=path)
                self.assertTrue({"missing_manuscript", "unsafe_manuscript"}.intersection(codes(self.root)))

    def test_symlink_manuscripts_and_document_directories_are_rejected(self) -> None:
        link = self.root / "manuscripts/novel/drafts/linked.md"
        try:
            link.symlink_to(self.root / ".llm-wiki.json")
        except OSError as error:
            self.skipTest(str(error))
        document(self.root, "scenes", "SCENE-001", status="drafted", chapter_ref="CH-001", sequence=1,
                 manuscript_ref="manuscripts/novel/drafts/linked.md")
        self.assertIn("unsafe_manuscript", codes(self.root))
        folder = self.root / "wiki/novel/reviews"
        folder.rmdir()
        folder.symlink_to(self.root / "wiki/novel/characters", target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "symlink"):
            novel.inspect(self.root)

    def test_declared_time_ranges_are_checked_without_requiring_chronological_narration(self) -> None:
        document(self.root, "timeline", "EVENT-001", canon_status="accepted", time_start=20, time_end=10)
        self.assertIn("reversed_time", codes(self.root))
        document(self.root, "timeline", "EVENT-001", canon_status="accepted", time_start=True, time_end=10)
        self.assertIn("invalid_time", codes(self.root))
        document(self.root, "timeline", "EVENT-001", canon_status="accepted", time_start=None, time_end=None,
                 scene_refs=["SCENE-002", "SCENE-001"])
        self.assertEqual(novel.inspect(self.root)["summary"]["errors"], 0)

    def test_foreshadow_requires_setup_and_payoff_but_reverse_revelation_is_a_warning(self) -> None:
        document(self.root, "foreshadowing", "FORESHADOW-001", status="resolved", setup_scene_refs=[], payoff_scene_refs=[])
        self.assertTrue({"missing_setup", "missing_payoff"}.issubset(codes(self.root)))
        document(self.root, "foreshadowing", "FORESHADOW-001", status="resolved", setup_scene_refs=["SCENE-002"], payoff_scene_refs=["SCENE-001"])
        result = novel.inspect(self.root)
        self.assertEqual(result["summary"]["errors"], 0)
        self.assertIn("payoff_before_setup", codes(self.root))

    def test_unresolved_foreshadow_warns_when_its_target_chapter_is_published(self) -> None:
        document(self.root, "chapters", "CH-002", status="published", order=2, scene_refs=["SCENE-002"])
        document(self.root, "foreshadowing", "FORESHADOW-001", status="seeded", setup_scene_refs=["SCENE-001"],
                 payoff_scene_refs=[], target_chapter_ref="CH-002")
        self.assertIn("overdue_foreshadow", codes(self.root))
        self.assertEqual(novel.inspect(self.root)["summary"]["errors"], 0)

    def test_malformed_metadata_is_reported_and_check_exits_unsuccessfully(self) -> None:
        document(self.root, "scenes", "SCENE-001", status=[], chapter_ref=[], sequence=True, character_refs="CHAR-001")
        self.assertTrue({"invalid_status", "invalid_reference_field", "invalid_order"}.issubset(codes(self.root)))
        result = subprocess.run([sys.executable, str(RUNTIME), "--root", str(self.root), "check"], capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(result.returncode, 1)
        self.assertFalse(json.loads(result.stdout)["ok"])

    def test_frontmatter_supports_block_lists_and_reports_duplicate_or_unclosed_fields(self) -> None:
        path = self.root / "wiki/novel/reviews/REVIEW-001.md"
        path.write_text('---\ntype: novel_review\nreview_id: REVIEW-001\ntitle: "검토"\nstatus: open\ndocument_refs:\n  - CHAR-001\n  - CH-001\n---\n', encoding="utf-8")
        self.assertEqual(novel.inspect(self.root)["summary"]["errors"], 0)
        path.write_text('---\ntype: novel_review\ntype: novel_review\n---\n', encoding="utf-8")
        self.assertIn("invalid_frontmatter", codes(self.root))
        path.write_text('---\ntype: novel_review\n', encoding="utf-8")
        self.assertIn("invalid_frontmatter", codes(self.root))

    def test_unknown_order_and_unstructured_notes_remain_explicit(self) -> None:
        document(self.root, "scenes", "SCENE-001", status="planned", chapter_ref="", sequence=None)
        (self.root / "wiki/novel/world/note.md").write_text("# Author note\n", encoding="utf-8")
        self.assertTrue({"missing_order", "unassigned_scene", "unstructured_document"}.issubset(codes(self.root)))


if __name__ == "__main__":
    unittest.main()
