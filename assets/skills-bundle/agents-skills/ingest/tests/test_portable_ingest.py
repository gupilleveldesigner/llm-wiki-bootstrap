from __future__ import annotations

import json
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_ROOT = SKILL_ROOT / "scripts"
VAULT_ROOT = Path(__file__).resolve().parents[4]
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from find_uningested import resolve_wiki_root, scan  # noqa: E402
from audit_categories import frontmatter_labels  # noqa: E402
from ingest_runtime import finalize, graph_strategy, graph_workspace, record_graphify_run, semantic_plan, validate_changed_files, verify  # noqa: E402
from install_to_wiki import JOURNAL_NAME, LOCK_NAME, install, install_lock, recover_install  # noqa: E402
from stitch_explicit_links import stitch  # noqa: E402


def make_wiki(root: Path) -> None:
    (root / "raw" / "reference").mkdir(parents=True)
    (root / "wiki" / "sources").mkdir(parents=True)
    (root / "wiki" / "concepts").mkdir(parents=True)
    (root / "wiki" / "taxonomy.json").write_text(
        json.dumps(
            {
                "version": 1,
                "scheme": {"id": "vault-topics", "prefLabel": "Test", "scopeNote": "Test taxonomy"},
                "concepts": [
                    {"id": "test", "prefLabel": "Test", "altLabel": ["testing"], "scopeNote": "Test documents", "broader": []}
                ],
            }
        ),
        encoding="utf-8",
    )


def source_note(root: Path, raw_relative: str, title: str) -> str:
    raw_path = root / raw_relative
    raw_bytes = raw_path.read_bytes()
    digest = hashlib.sha256(raw_bytes).hexdigest()
    binary = raw_path.suffix.casefold() == ".png"
    unit_field = f"raw_byte_count: {len(raw_bytes)}" if binary else f"raw_line_count: {len(raw_path.read_text(encoding='utf-8').splitlines())}"
    locator = f"bytes 0-{len(raw_bytes) - 1}" if binary else "lines 1-1"
    evidence_locator = "bytes 1-3" if binary else "lines 1-1"
    evidence_quote = "PNG" if binary else "source"
    source_id = f"SOURCE-{digest[:12].upper()}"
    (root / "wiki" / "concepts" / "test.md").write_text(
        f"---\ntopics: [test]\nsources: [[{raw_relative}]]\nsource_ids: [{source_id}]\n---\n# Test concept\n",
        encoding="utf-8",
    )
    return (
        "---\n"
        "type: source\n"
        f"id: {source_id}\n"
        "topics: [test]\n"
        f"sources: [[{raw_relative}]]\n"
        f"raw_sha256: {digest}\n"
        "source_type: document\n"
        "structurally_verified: true\n"
        "semantic_status: reviewed\n"
        f"{unit_field}\n"
        "key_claims: 1\nentities: 1\nconcepts: 1\nreflected_docs: 1\nrelations: 0\nevidence_spans: 1\n"
        "coverage_spans: 1\nkey_decisions: 0\nnext_actions: 0\nchronology_entries: 0\n"
        "---\n"
        f"# {title}\n\n"
        "## 핵심 주장\n\n- 확인된 주장\n\n"
        "## 엔티티\n\n- 테스트 엔티티\n\n"
        "## 개념\n\n- [[concepts/test]]\n\n"
        "## 관계\n\n- 없음\n\n"
        f"## 의미 Coverage\n\n- full | {locator} | 원문 전체\n\n"
        "## 핵심 결정\n\n- 없음\n\n"
        "## 다음 행동\n\n- 없음\n\n"
        "## Chronology\n\n- 없음\n\n"
        f"## 근거\n\n> [{evidence_locator}] {evidence_quote}\n\n"
        "## Wiki에 반영된 문서\n\n- [[concepts/test]]\n"
    )


def conversation_note(
    root: Path,
    raw_relative: str,
    *,
    reverse_provenance: bool = True,
    head_only: bool = False,
) -> str:
    raw_path = root / raw_relative
    lines = raw_path.read_text(encoding="utf-8").splitlines()
    digest = hashlib.sha256(raw_path.read_bytes()).hexdigest()
    source_id = f"SOURCE-{digest[:12].upper()}"
    project = root / "wiki" / "projects" / "test.md"
    project.parent.mkdir(parents=True, exist_ok=True)
    provenance = f"sources: [[{raw_relative}]]\nsource_ids: [{source_id}]\n" if reverse_provenance else "sources: []\n"
    project.write_text(f"---\ntype: project\n{provenance}---\n# Test project\n", encoding="utf-8")
    if head_only:
        coverage = "- start | lines 1-20 | 시작만 검토"
        evidence = "> [lines 1-1] opening context"
        coverage_count = evidence_count = 1
    else:
        coverage = "\n".join(
            [
                "- start | lines 1-20 | 시작",
                "- middle | lines 150-250 | 중간",
                f"- end | lines 350-{len(lines)} | 끝",
            ]
        )
        evidence = "\n".join(
            [
                "> [lines 1-1] opening context",
                "> [lines 200-200] middle evidence 200",
                f"> [lines {len(lines)}-{len(lines)}] FINAL DECISION: build 2d-game-art",
            ]
        )
        coverage_count = evidence_count = 3
    return (
        "---\n"
        "type: source\n"
        f"id: {source_id}\n"
        "status: active\n"
        "topics: [test]\n"
        f"sources: [[{raw_relative}]]\n"
        f"raw_sha256: {digest}\n"
        "source_type: llm_conversation\n"
        "structurally_verified: true\n"
        "semantic_status: reviewed\n"
        f"raw_line_count: {len(lines)}\n"
        "key_claims: 0\nentities: 0\nconcepts: 1\nreflected_docs: 1\nrelations: 0\n"
        f"evidence_spans: {evidence_count}\ncoverage_spans: {coverage_count}\n"
        "key_decisions: 1\nnext_actions: 1\nchronology_entries: 1\n"
        "---\n"
        "# Long conversation\n\n"
        "## 핵심 주장\n\n- 없음\n\n"
        "## 엔티티\n\n- 없음\n\n"
        "## 개념\n\n- Long source coverage\n\n"
        "## 관계\n\n- 없음\n\n"
        f"## 의미 Coverage\n\n{coverage}\n\n"
        f"## 핵심 결정\n\n- DECISION-TEST | lines {len(lines)}-{len(lines)} | 2d-game-art 설계로 전환\n\n"
        f"## 다음 행동\n\n- ACTION-TEST | lines {len(lines)}-{len(lines)} | 전체 설계 작성\n\n"
        f"## Chronology\n\n- FINAL | lines {len(lines)}-{len(lines)} | 이전 실험보다 설계를 우선\n\n"
        f"## 근거\n\n{evidence}\n\n"
        "## Wiki에 반영된 문서\n\n- [[projects/test]]\n"
    )


class PortableIngestTests(unittest.TestCase):
    def test_category_audit_reads_yaml_block_lists_without_dashes(self) -> None:
        labels = frontmatter_labels("topics:\n  - 생산 문서·지식\n  - 아트 생산 파이프라인\nstatus: active\n")
        self.assertEqual(labels, ["생산 문서·지식", "아트 생산 파이프라인"])

    def test_complete_batch_rejects_image_review_without_typed_region_locator(self) -> None:
        with tempfile.TemporaryDirectory(prefix="wiki-attachment-") as temporary:
            root = Path(temporary)
            make_wiki(root)
            raw = root / "raw" / "reference" / "image.png"
            raw.write_bytes(b"\x89PNG\r\n\x1a\n")
            note = source_note(root, "raw/reference/image.png", "Image").replace("> source", "> PNG")
            (root / "wiki" / "sources" / "image.md").write_text(note, encoding="utf-8")
            result = verify(root, complete_batch=True, require_graph=False)
            self.assertEqual(result["status"], "verification_failed", result)
            self.assertEqual(result["coverage"]["structurally_verified"], 1, result)
            self.assertEqual(result["coverage"]["semantic_partial"], 1, result)
            self.assertTrue(any("typed image-region locator" in error for error in result["errors"]), result)
            plan = semantic_plan(root, ["raw/reference/image.png"])
            self.assertEqual(plan["plans"][0]["unit"], "bytes")

    def test_partial_binary_source_is_structural_without_a_fabricated_byte_quote(self) -> None:
        with tempfile.TemporaryDirectory(prefix="wiki-partial-image-") as temporary:
            root = Path(temporary)
            make_wiki(root)
            raw = root / "raw" / "reference" / "image.png"
            raw.write_bytes(b"\x89PNG\r\n\x1a\n")
            note = source_note(root, "raw/reference/image.png", "Image")
            note = note.replace("semantic_status: reviewed", "semantic_status: partial")
            note = note.replace("> [bytes 1-3] PNG", "> typed image-region locator pending")
            (root / "wiki" / "sources" / "image.md").write_text(note, encoding="utf-8")

            result = verify(root, changed_files=["wiki/sources/image.md"])
            self.assertEqual(result["coverage"]["structurally_verified"], 1, result)
            self.assertEqual(result["coverage"]["semantic_partial"], 1, result)
            self.assertFalse(any("Raw evidence quote mismatch" in error for error in result["errors"]))

    def test_stitch_explicit_links_adds_source_raw_and_wiki_edges(self) -> None:
        with tempfile.TemporaryDirectory(prefix="wiki-explicit-links-") as temporary:
            root = Path(temporary)
            make_wiki(root)
            raw = root / "raw" / "reference" / "source.md"
            raw.write_text("source", encoding="utf-8")
            (root / "wiki" / "sources" / "source.md").write_text(
                source_note(root, "raw/reference/source.md", "Source"), encoding="utf-8"
            )
            graph_out = root / "graphify-out"
            graph_out.mkdir()
            (graph_out / "graph.json").write_text(
                json.dumps({"nodes": [{"id": "source", "source_file": "wiki/sources/source.md", "community": 0}], "links": []}),
                encoding="utf-8",
            )
            result = stitch(root)
            self.assertGreaterEqual(result["added_nodes"], 2)
            graph = json.loads((graph_out / "graph.json").read_text(encoding="utf-8"))
            identities = {node["id"]: node.get("source_file") for node in graph["nodes"]}
            raw_id = next(node_id for node_id, value in identities.items() if value == "raw/reference/source.md")
            concept_id = next(node_id for node_id, value in identities.items() if value == "wiki/concepts/test.md")
            pairs = {(edge["source"], edge["target"]) for edge in graph["links"]}
            self.assertIn(("source", raw_id), pairs)
            self.assertIn(("source", concept_id), pairs)
            stitched = next(edge for edge in graph["links"] if edge["source"] == "source" and edge["target"] == raw_id)
            self.assertEqual(stitched["edge_origin"], "deterministic_stitch")
            self.assertFalse(stitched["semantic_evidence"])

    def test_discovers_nearest_wiki_root_and_classifies_host_files(self) -> None:
        with tempfile.TemporaryDirectory(prefix="wiki-portable-") as temporary:
            root = Path(temporary) / "다른 위키"
            make_wiki(root)
            (root / "raw" / "AGENTS.md").write_text("instructions", encoding="utf-8")
            (root / "raw" / "reference" / "인제스트됨.md").write_text("source", encoding="utf-8")
            (root / "raw" / "reference" / "새 문서—테스트.md").write_text("pending", encoding="utf-8")
            (root / "wiki" / "sources" / "인제스트됨.md").write_text(
                source_note(root, "raw/reference/인제스트됨.md", "인제스트됨"), encoding="utf-8"
            )
            nested = root / "wiki" / "concepts"

            self.assertEqual(resolve_wiki_root(None, start=nested), root.resolve())
            result = scan(root)
            self.assertEqual([item["path"] for item in result["ingested"]], ["raw/reference/인제스트됨.md"])
            self.assertEqual([item["path"] for item in result["pending"]], ["raw/reference/새 문서—테스트.md"])
            self.assertEqual([item["path"] for item in result["skipped"]], ["raw/AGENTS.md"])

    def test_explicit_root_overrides_the_invoking_project(self) -> None:
        with tempfile.TemporaryDirectory(prefix="wiki-explicit-") as temporary:
            first = Path(temporary) / "first"
            second = Path(temporary) / "second"
            make_wiki(first)
            make_wiki(second)

            self.assertEqual(resolve_wiki_root(second, start=first / "wiki"), second.resolve())

    def test_catalog_citations_do_not_count_as_ingest(self) -> None:
        with tempfile.TemporaryDirectory(prefix="wiki-catalog-") as temporary:
            root = Path(temporary)
            make_wiki(root)
            for name in ("one.md", "two.md"):
                (root / "raw" / "reference" / name).write_text("source", encoding="utf-8")
            (root / "wiki" / "sources" / "catalog.md").write_text(
                "---\ntype: overview\nsources:\n  - [[raw/reference/one.md]]\n  - [[raw/reference/two.md]]\n---\n",
                encoding="utf-8",
            )

            result = scan(root)
            self.assertEqual(result["ingested"], [])
            self.assertEqual({item["path"] for item in result["catalog_only"]}, {
                "raw/reference/one.md",
                "raw/reference/two.md",
            })

    def test_complete_batch_requires_source_coverage_and_handles_missing_graphify(self) -> None:
        with tempfile.TemporaryDirectory(prefix="wiki-batch-") as temporary:
            root = Path(temporary)
            make_wiki(root)
            (root / "raw" / "reference" / "done.md").write_text("source", encoding="utf-8")
            (root / "raw" / "reference" / "left.md").write_text("source", encoding="utf-8")
            changed = root / "wiki" / "sources" / "done.md"
            changed.write_text(source_note(root, "raw/reference/done.md", "Done"), encoding="utf-8")

            partial = finalize(root, ["wiki/sources/done.md"], complete_batch=True)
            self.assertEqual(partial["status"], "coverage_failed")
            self.assertEqual(partial["coverage"]["pending"], 1)

            (root / "wiki" / "sources" / "left.md").write_text(
                source_note(root, "raw/reference/left.md", "Left"), encoding="utf-8"
            )
            action = finalize(
                root,
                ["wiki/sources/done.md", "wiki/sources/left.md"],
                complete_batch=True,
            )
            self.assertEqual(action["status"], "agent_action_required")

            graph_out = root / "graphify-out"
            graph_out.mkdir()
            (graph_out / "graph.json").write_text(
                json.dumps(
                    {
                        "nodes": [
                            {"id": "source", "source_file": "wiki/sources/done.md"},
                            {"id": "left", "source_file": "wiki/sources/left.md"},
                            {"id": "concept", "source_file": "wiki/concepts/test.md"},
                            {"id": "raw-done", "source_file": "raw/reference/done.md"},
                            {"id": "raw-left", "source_file": "raw/reference/left.md"},
                        ],
                        "links": [
                            {"source": "source", "target": "concept"},
                            {"source": "left", "target": "concept"},
                            {"source": "source", "target": "raw-done"},
                            {"source": "left", "target": "raw-left"},
                        ],
                    }
                ),
                encoding="utf-8",
            )
            (root / "raw" / "CLAUDE.md").write_text("folder instructions", encoding="utf-8")
            self.assertEqual(record_graphify_run(root, "codex")["status"], "recorded")
            with patch("ingest_runtime.graphify_executable", return_value=None):
                complete = finalize(
                    root,
                    ["wiki/sources/done.md", "wiki/sources/left.md"],
                    complete_batch=True,
                )
            self.assertEqual(complete["status"], "graph_present", complete)
            self.assertEqual(complete["graph_status"], "graph_present")
            self.assertEqual(complete["graph_counts"], {"nodes": 5, "links": 4})
            self.assertEqual(complete["completion"], "complete")
            self.assertTrue((root / "wiki" / "ingest-ledger.json").is_file())
            fresh = verify(root, complete_batch=True, require_graph=True)
            self.assertEqual(fresh["status"], "verified", fresh)
            (root / "raw" / "reference" / "done.md").write_text("changed", encoding="utf-8")
            stale = verify(root, complete_batch=True, require_graph=True)
            self.assertEqual(stale["status"], "verification_failed")
            self.assertTrue(any("inputs are stale" in error for error in stale["errors"]))

    def test_quality_gate_rejects_placeholder_source_and_independent_verify_reports_it(self) -> None:
        with tempfile.TemporaryDirectory(prefix="wiki-quality-") as temporary:
            root = Path(temporary)
            make_wiki(root)
            raw = root / "raw" / "reference" / "source.md"
            raw.write_text("source", encoding="utf-8")
            page = root / "wiki" / "sources" / "source.md"
            page.write_text(
                "---\ntype: source\ntopics: [test]\nsources: [[raw/reference/source.md]]\n---\n# Placeholder\n",
                encoding="utf-8",
            )

            result = scan(root)
            self.assertEqual(result["ingested"], [])
            self.assertEqual(result["catalog_only"][0]["path"], "raw/reference/source.md")
            failed = finalize(root, ["wiki/sources/source.md"])
            ledger = json.loads((root / "wiki" / "ingest-ledger.json").read_text(encoding="utf-8"))
            self.assertEqual(failed["status"], "validation_failed")
            self.assertTrue(ledger["errors"])
            verified = verify(root, complete_batch=True, require_graph=True)
            self.assertEqual(verified["status"], "verification_failed")
            self.assertTrue(any("Source summary has invalid" in error for error in verified["errors"]))

    def test_graphify_host_action_is_required_before_complete_batch(self) -> None:
        with tempfile.TemporaryDirectory(prefix="wiki-graphify-") as temporary:
            root = Path(temporary)
            make_wiki(root)
            raw = root / "raw" / "reference" / "source.md"
            raw.write_text("source", encoding="utf-8")
            (root / "wiki" / "sources" / "source.md").write_text(
                source_note(root, "raw/reference/source.md", "Source"), encoding="utf-8"
            )

            with patch("ingest_runtime.graphify_executable", return_value=None):
                result = finalize(root, ["wiki/sources/source.md"], complete_batch=True)
            self.assertEqual(result["status"], "agent_action_required")
            self.assertIn("graphify install --platform codex", result["codex"]["install"])
            self.assertIn("$graphify", result["codex"]["build"])
            self.assertIn('"', result["codex"]["build"])
            self.assertEqual(result["exit_code"], 2)

    def test_category_audit_blocks_complete_batch(self) -> None:
        with tempfile.TemporaryDirectory(prefix="wiki-category-gate-") as temporary:
            root = Path(temporary)
            make_wiki(root)
            raw = root / "raw" / "reference" / "source.md"
            raw.write_text("source", encoding="utf-8")
            (root / "wiki" / "sources" / "source.md").write_text(
                source_note(root, "raw/reference/source.md", "Source"), encoding="utf-8"
            )
            (root / "wiki" / "taxonomy.json").write_text(
                json.dumps({"version": 1, "scheme": {}, "concepts": []}), encoding="utf-8"
            )
            result = finalize(root, ["wiki/sources/source.md"], complete_batch=True)
            self.assertEqual(result["status"], "category_failed")
            self.assertTrue(any("taxonomy.json" in error for error in result["errors"]))

    def test_independent_graph_gate_rejects_catalog_node_with_embedded_paths(self) -> None:
        with tempfile.TemporaryDirectory(prefix="wiki-graph-gate-") as temporary:
            root = Path(temporary)
            make_wiki(root)
            raw = root / "raw" / "reference" / "source.md"
            raw.write_text("source", encoding="utf-8")
            (root / "wiki" / "sources" / "source.md").write_text(
                source_note(root, "raw/reference/source.md", "Source"), encoding="utf-8"
            )
            graph_out = root / "graphify-out"
            graph_out.mkdir()
            (graph_out / "graph.json").write_text(
                json.dumps(
                    {
                        "nodes": [
                            {
                                "id": "Imported Episodes",
                                "description": "raw/reference/source.md concepts/test",
                            }
                        ],
                        "links": [],
                    }
                ),
                encoding="utf-8",
            )
            with patch("ingest_runtime.graphify_executable", return_value="graphify"):
                result = verify(root, complete_batch=True, require_graph=True)
            self.assertEqual(result["status"], "verification_failed")
            self.assertTrue(any("no node for source summary" in error for error in result["errors"]))

    def test_independent_gate_blocks_unexplained_empty_raw_file(self) -> None:
        with tempfile.TemporaryDirectory(prefix="wiki-rejected-") as temporary:
            root = Path(temporary)
            make_wiki(root)
            raw = root / "raw" / "reference" / "source.md"
            raw.write_text("source", encoding="utf-8")
            (root / "wiki" / "sources" / "source.md").write_text(
                source_note(root, "raw/reference/source.md", "Source"), encoding="utf-8"
            )
            (root / "raw" / "reference" / "empty.md").write_text("", encoding="utf-8")

            result = verify(root, complete_batch=True)
            self.assertEqual(result["status"], "verification_failed")
            self.assertEqual(result["coverage"]["rejected"], 1)

    def test_long_conversation_head_only_review_is_partial_and_eof_is_partitioned(self) -> None:
        with tempfile.TemporaryDirectory(prefix="wiki-long-tail-") as temporary:
            root = Path(temporary)
            make_wiki(root)
            raw = root / "raw" / "reference" / "long.md"
            raw.write_text(
                "\n".join(["opening context", *(f"middle evidence {index}" for index in range(2, 400)), "FINAL DECISION: build 2d-game-art"]),
                encoding="utf-8",
            )
            page = root / "wiki" / "sources" / "long.md"
            page.write_text(conversation_note(root, "raw/reference/long.md", head_only=True), encoding="utf-8")

            errors = validate_changed_files(root, ["wiki/sources/long.md"])
            self.assertTrue(any("end coverage" in error or "tail decision" in error for error in errors), errors)
            scanned = scan(root)
            self.assertEqual(scanned["ingested"][0]["semantic_status"], "partial")
            plan = semantic_plan(root, ["raw/reference/long.md"], max_lines=120, overlap_lines=10)
            self.assertTrue(plan["coverage_complete"])
            self.assertEqual(plan["plans"][0]["chunks"][-1]["end"], 400)

    def test_long_code_source_uses_line_coverage_and_reaches_eof(self) -> None:
        with tempfile.TemporaryDirectory(prefix="wiki-long-code-") as temporary:
            root = Path(temporary)
            make_wiki(root)
            raw = root / "raw/reference/long.py"
            raw.write_text(
                "\n".join(["opening context", *(f"middle evidence {index}" for index in range(2, 400)), "FINAL DECISION: build 2d-game-art"]),
                encoding="utf-8",
            )
            page = root / "wiki/sources/long-code.md"
            page.write_text(conversation_note(root, "raw/reference/long.py"), encoding="utf-8")

            result = verify(root, changed_files=["wiki/sources/long-code.md"])
            self.assertTrue(result["verified"], result)
            self.assertEqual(result["coverage"]["semantic_reviewed"], 1)
            plan = semantic_plan(root, ["raw/reference/long.py"], max_lines=120, overlap_lines=10)
            self.assertEqual(plan["plans"][0]["unit"], "lines")
            self.assertEqual(plan["plans"][0]["chunks"][-1]["end"], 400)

    def test_semantic_review_rejects_count_mismatch_and_missing_locators(self) -> None:
        with tempfile.TemporaryDirectory(prefix="wiki-semantic-count-") as temporary:
            root = Path(temporary)
            make_wiki(root)
            raw = root / "raw" / "reference" / "long.md"
            raw.write_text(
                "\n".join(["opening context", *(f"middle evidence {index}" for index in range(2, 400)), "FINAL DECISION: build 2d-game-art"]),
                encoding="utf-8",
            )
            page = root / "wiki" / "sources" / "long.md"
            note = conversation_note(root, "raw/reference/long.md").replace("key_decisions: 1", "key_decisions: 2")
            page.write_text(note, encoding="utf-8")
            errors = validate_changed_files(root, ["wiki/sources/long.md"])
            self.assertTrue(any("key_decisions=2" in error for error in errors), errors)

            page.write_text(conversation_note(root, "raw/reference/long.md").replace("[lines 200-200] ", ""), encoding="utf-8")
            errors = validate_changed_files(root, ["wiki/sources/long.md"])
            self.assertTrue(any("require [lines/bytes" in error for error in errors), errors)

    def test_reflected_doc_requires_reverse_provenance_and_stitch_is_not_semantic_evidence(self) -> None:
        with tempfile.TemporaryDirectory(prefix="wiki-reverse-provenance-") as temporary:
            root = Path(temporary)
            make_wiki(root)
            raw = root / "raw" / "reference" / "long.md"
            raw.write_text(
                "\n".join(["opening context", *(f"middle evidence {index}" for index in range(2, 400)), "FINAL DECISION: build 2d-game-art"]),
                encoding="utf-8",
            )
            page = root / "wiki" / "sources" / "long.md"
            page.write_text(
                conversation_note(root, "raw/reference/long.md", reverse_provenance=False), encoding="utf-8"
            )
            graph_out = root / "graphify-out"
            graph_out.mkdir()
            (graph_out / "graph.json").write_text(json.dumps({"nodes": [], "links": []}), encoding="utf-8")
            stitched = stitch(root)
            self.assertGreater(stitched["added_links"], 0)
            self.assertEqual(stitched["semantic_edges_added"], 0)

            errors = validate_changed_files(root, ["wiki/sources/long.md"])
            self.assertTrue(any("reverse Source/Raw provenance" in error for error in errors), errors)
            result = verify(root, complete_batch=True, require_graph=False)
            self.assertEqual(result["status"], "verification_failed")
            self.assertEqual(result["graph_contract"], "structural_only")

            claim = root / "wiki" / "claims" / "test.md"
            claim.parent.mkdir()
            claim.write_text("---\ntype: claim\nid: CLAIM-TEST\nsources: []\n---\n# Claim\n", encoding="utf-8")
            page.write_text(
                conversation_note(root, "raw/reference/long.md").replace("[[projects/test]]", "[[claims/test]]"),
                encoding="utf-8",
            )
            errors = validate_changed_files(root, ["wiki/sources/long.md"])
            self.assertTrue(any("reverse Source/Raw provenance" in error and "claims/test" in error for error in errors), errors)

    def test_external_git_worktree_uses_primary_checkout_wiki_without_root_argument(self) -> None:
        if shutil.which("git") is None:
            self.skipTest("git is required for the worktree discovery test")

        with tempfile.TemporaryDirectory(prefix="wiki-worktree-") as temporary:
            main = Path(temporary) / "Main Project"
            linked = Path(temporary) / "Claude Worktree"
            main.mkdir()

            def git(*arguments: str) -> None:
                completed = subprocess.run(
                    ["git", "-C", str(main), *arguments],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    check=False,
                )
                self.assertEqual(
                    completed.returncode,
                    0,
                    completed.stderr.decode("utf-8", errors="replace"),
                )

            git("init")
            (main / "tracked.txt").write_text("tracked", encoding="utf-8")
            git("add", "tracked.txt")
            git(
                "-c",
                "user.name=Wiki Test",
                "-c",
                "user.email=wiki-test@example.invalid",
                "commit",
                "-m",
                "initial",
            )
            git("worktree", "add", "--detach", str(linked), "HEAD")
            make_wiki(main)
            nested = linked / "Source" / "Feature"
            nested.mkdir(parents=True)

            self.assertFalse((linked / "raw").exists())
            self.assertFalse((linked / "wiki").exists())
            self.assertEqual(resolve_wiki_root(None, start=nested), main.resolve())

            completed = subprocess.run(
                [sys.executable, str(SCRIPTS_ROOT / "ingest_runtime.py"), "status"],
                cwd=nested,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr.decode(errors="replace"))
            payload = json.loads(completed.stdout.decode("utf-8"))
            self.assertEqual(Path(payload["root"]), main.resolve())

    def test_missing_wiki_does_not_select_an_unrelated_directory(self) -> None:
        with tempfile.TemporaryDirectory(prefix="not-a-wiki-") as temporary:
            start = Path(temporary) / "project" / "nested"
            start.mkdir(parents=True)
            with patch("find_uningested.primary_git_worktree", return_value=None):
                with self.assertRaisesRegex(ValueError, "invoking project"):
                    resolve_wiki_root(None, start=start)

    def test_portable_gate_validates_changed_docs_without_graph(self) -> None:
        with tempfile.TemporaryDirectory(prefix="wiki-portable-") as temporary:
            root = Path(temporary)
            make_wiki(root)
            (root / "raw" / "reference" / "source.md").write_text("source", encoding="utf-8")
            changed = root / "wiki" / "concepts" / "연결.md"
            changed.write_text(
                "---\ntype: concept\ntopics:\n  - 연결\nsources:\n  - \"[[raw/reference/source.md]]\"\n---\n",
                encoding="utf-8",
            )

            self.assertEqual(validate_changed_files(root, ["wiki/concepts/연결.md"]), [])
            self.assertEqual(graph_strategy(root), "none")
            result = finalize(root, ["wiki/concepts/연결.md"])
            self.assertEqual(result["status"], "validated_without_graph")
            self.assertEqual(result["exit_code"], 0)

            changed.write_text(
                "---\ntype: concept\ntopics: []\nsources: []\n---\n",
                encoding="utf-8",
            )
            errors = validate_changed_files(root, ["wiki/concepts/연결.md"])
            self.assertTrue(any("topics" in error for error in errors))
            self.assertTrue(any("source citation" in error for error in errors))

    def test_alternate_tags_source_schema_and_nested_graphify_layout(self) -> None:
        with tempfile.TemporaryDirectory(prefix="wiki-projectmoon-") as temporary:
            root = Path(temporary)
            (root / "raw" / "documents").mkdir(parents=True)
            (root / "wiki" / "concepts").mkdir(parents=True)
            (root / "raw" / "documents" / "정본.md").write_text("source", encoding="utf-8")
            (root / "wiki" / "concepts" / "test.md").write_text("# Test concept\n", encoding="utf-8")
            changed = root / "wiki" / "concepts" / "설계.md"
            changed.write_text(
                "---\n"
                "tags: [design, project]\n"
                "source: raw/documents/정본.md\n"
                f"raw_sha256: {hashlib.sha256(b'source').hexdigest()}\n"
                "key_claims: 1\nentities: 1\nconcepts: 1\nreflected_docs: 1\nrelations: 0\nevidence_spans: 1\n"
                "---\n# 설계\n\n## 핵심 주장\n내용\n\n## 엔티티와 개념\n내용\n\n## 근거\n> source\n\n## 반영 문서\n[[concepts/test]]\n",
                encoding="utf-8",
            )
            graph_out = root / "wiki" / "graphify-out"
            graph_out.mkdir()
            (graph_out / "graph.json").write_text("{}", encoding="utf-8")

            result = scan(root)
            self.assertEqual([item["path"] for item in result["ingested"]], ["raw/documents/정본.md"])
            self.assertEqual(validate_changed_files(root, ["wiki/concepts/설계.md"]), [])
            self.assertEqual(graph_strategy(root), "graphify-cli")
            self.assertEqual(graph_workspace(root), (root / "wiki").resolve())

            with patch("ingest_runtime.shutil.which", return_value="graphify"), patch(
                "ingest_runtime.run_command", return_value=0
            ) as run:
                finalized = finalize(root, ["wiki/concepts/설계.md"])
            self.assertEqual(finalized["status"], "graph_present")
            self.assertEqual(Path(finalized["graph_workspace"]), (root / "wiki").resolve())
            self.assertFalse(run.called)

    def test_portable_gate_rejects_empty_missing_and_escaped_sources(self) -> None:
        with tempfile.TemporaryDirectory(prefix="wiki-portable-") as temporary:
            root = Path(temporary)
            make_wiki(root)
            changed = root / "wiki" / "concepts" / "연결.md"

            self.assertTrue(any("changed-file" in error for error in validate_changed_files(root, [])))
            self.assertEqual(finalize(root, [])["status"], "validation_failed")

            changed.write_text(
                "---\ntype: concept\ntopics: [연결]\nsources: [\"[[raw/reference/missing.md]]\"]\n---\n",
                encoding="utf-8",
            )
            self.assertTrue(
                any("does not exist" in error for error in validate_changed_files(root, ["wiki/concepts/연결.md"]))
            )

            (root / "outside.md").write_text("outside", encoding="utf-8")
            changed.write_text(
                "---\ntype: concept\ntopics: [연결]\nsources: [\"[[raw/../outside.md]]\"]\n---\n",
                encoding="utf-8",
            )
            self.assertTrue(any("escapes raw/" in error for error in validate_changed_files(root, [str(changed)])))

    def test_scoped_verify_rejects_vacuous_and_zero_raw_source_records(self) -> None:
        with tempfile.TemporaryDirectory(prefix="wiki-scoped-zero-") as temporary:
            root = Path(temporary)
            make_wiki(root)
            concept = root / "wiki/concepts/only-concept.md"
            concept.write_text("---\ntype: concept\ntopics: [test]\nsources: []\n---\n# Concept\n", encoding="utf-8")

            vacuous = verify(root, changed_files=["wiki/concepts/only-concept.md"])
            self.assertFalse(vacuous["verified"])
            self.assertIn("exactly one Raw target", "\n".join(vacuous["errors"]))

            source = root / "wiki/sources/no-raw.md"
            source.write_text(
                "---\ntype: source\nid: SOURCE-NO-RAW\ntopics: [test]\nsources: []\n"
                "key_claims: 1\nentities: 1\nconcepts: 1\nreflected_docs: 1\nrelations: 0\nevidence_spans: 1\n"
                "---\n# Source\n\n## 핵심 주장\n\n- claim\n\n## 엔티티\n\n- entity\n\n## 개념\n\n- concept\n",
                encoding="utf-8",
            )
            zero_raw = verify(root, changed_files=["wiki/sources/no-raw.md"])
            self.assertFalse(zero_raw["verified"])
            self.assertEqual(zero_raw["coverage"]["input"], 1)
            self.assertIn("exactly one Raw target", "\n".join(zero_raw["errors"]))

    def test_scan_does_not_report_structural_verification_after_raw_hash_changes(self) -> None:
        with tempfile.TemporaryDirectory(prefix="wiki-scan-hash-") as temporary:
            root = Path(temporary)
            make_wiki(root)
            raw = root / "raw/reference/source.md"
            raw.write_text("source", encoding="utf-8")
            source = root / "wiki/sources/source.md"
            source.write_text(source_note(root, "raw/reference/source.md", "Source"), encoding="utf-8")
            raw.write_text("changed source", encoding="utf-8")

            result = scan(root)
            item = result["ingested"][0]
            self.assertFalse(item["structurally_verified"])
            self.assertEqual(item["semantic_status"], "partial")
            self.assertTrue(item["structural_errors"])

    def test_curated_marker_refuses_generic_graph_update(self) -> None:
        with tempfile.TemporaryDirectory(prefix="wiki-portable-") as temporary:
            root = Path(temporary)
            make_wiki(root)
            (root / "raw" / "reference" / "source.md").write_text("source", encoding="utf-8")
            changed = root / "wiki" / "concepts" / "연결.md"
            changed.write_text(
                "---\ntype: concept\ntopics: [연결]\nsources: [\"[[raw/reference/source.md]]\"]\n---\n",
                encoding="utf-8",
            )
            (root / "graphify-out").mkdir()
            (root / "graphify-out" / "CURATED_GRAPH_STATE.json").write_text("{}", encoding="utf-8")

            result = finalize(root, ["wiki/concepts/연결.md"])
            self.assertEqual(result["status"], "graph_finalizer_missing")
            self.assertEqual(result["exit_code"], 2)

    def test_cp949_environment_still_emits_lossless_utf8_json(self) -> None:
        with tempfile.TemporaryDirectory(prefix="wiki-portable-") as temporary:
            root = Path(temporary)
            make_wiki(root)
            filename = "새 문서—테스트.md"
            (root / "raw" / "reference" / filename).write_text("pending", encoding="utf-8")
            environment = os.environ.copy()
            environment["PYTHONIOENCODING"] = "cp949"
            completed = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS_ROOT / "find_uningested.py"),
                    "--root",
                    str(root),
                    "--json",
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
                env=environment,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr.decode(errors="replace"))
            payload = json.loads(completed.stdout.decode("utf-8"))
            self.assertEqual(payload["pending"][0]["path"], f"raw/reference/{filename}")

    def test_installer_provisions_codex_and_claude_adapters(self) -> None:
        with tempfile.TemporaryDirectory(prefix="wiki-install-") as temporary:
            root = Path(temporary)
            make_wiki(root)
            result = install(root, replace=False)
            self.assertEqual(result["status"], "installed")
            self.assertTrue((root / ".agents" / "skills" / "ingest" / "SKILL.md").is_file())
            claude_runtime = root / ".claude" / "skills" / "ingest" / "scripts" / "ingest_runtime.py"
            self.assertTrue(claude_runtime.is_file())

            completed = subprocess.run(
                [sys.executable, str(claude_runtime), "status", "--root", str(root)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr.decode(errors="replace"))
            payload = json.loads(completed.stdout.decode("utf-8"))
            self.assertEqual(Path(payload["root"]), root.resolve())

            with self.assertRaises(FileExistsError):
                install(root, replace=False)

    def test_installer_lock_rejects_concurrent_writer(self) -> None:
        with tempfile.TemporaryDirectory(prefix="wiki-install-") as temporary:
            root = Path(temporary)
            make_wiki(root)
            with install_lock(root):
                with self.assertRaises(RuntimeError):
                    with install_lock(root):
                        self.fail("Concurrent installer acquired the same lock")
            self.assertFalse((root / ".ingest-skill-install.lock").exists())

    def test_interrupted_dual_host_install_recovers_originals(self) -> None:
        with tempfile.TemporaryDirectory(prefix="wiki-install-") as temporary:
            root = Path(temporary)
            make_wiki(root)
            install(root, replace=False)
            agents_marker = root / ".agents" / "skills" / "ingest" / "old.marker"
            claude_marker = root / ".claude" / "skills" / "ingest" / "old.marker"
            agents_marker.write_text("agents-old", encoding="utf-8")
            claude_marker.write_text("claude-old", encoding="utf-8")

            script = (
                "import os,sys;"
                f"sys.path.insert(0,{str(SCRIPTS_ROOT)!r});"
                "from pathlib import Path;"
                "from install_to_wiki import install;"
                "install(Path(sys.argv[1]),replace=True,"
                "after_step=lambda step: os._exit(91) if step=='agents_installed' else None)"
            )
            completed = subprocess.run(
                [sys.executable, "-c", script, str(root)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            self.assertEqual(completed.returncode, 91, completed.stderr.decode(errors="replace"))
            self.assertTrue((root / JOURNAL_NAME).is_file())
            self.assertTrue((root / LOCK_NAME).is_file())

            result = recover_install(root)
            self.assertEqual(result["status"], "recovered")
            self.assertEqual(agents_marker.read_text(encoding="utf-8"), "agents-old")
            self.assertEqual(claude_marker.read_text(encoding="utf-8"), "claude-old")
            self.assertFalse((root / JOURNAL_NAME).exists())
            self.assertFalse((root / LOCK_NAME).exists())
            self.assertEqual(recover_install(root)["status"], "no_journal")

    def test_recovery_can_resume_after_recovery_process_is_killed(self) -> None:
        with tempfile.TemporaryDirectory(prefix="wiki-install-") as temporary:
            root = Path(temporary)
            make_wiki(root)
            install(root, replace=False)
            agents_marker = root / ".agents" / "skills" / "ingest" / "old.marker"
            claude_marker = root / ".claude" / "skills" / "ingest" / "old.marker"
            agents_marker.write_text("agents-old", encoding="utf-8")
            claude_marker.write_text("claude-old", encoding="utf-8")

            install_crash = (
                "import os,sys;"
                f"sys.path.insert(0,{str(SCRIPTS_ROOT)!r});"
                "from pathlib import Path;"
                "from install_to_wiki import install;"
                "install(Path(sys.argv[1]),replace=True,"
                "after_step=lambda step: os._exit(91) if step=='agents_installed' else None)"
            )
            self.assertEqual(
                subprocess.run([sys.executable, "-c", install_crash, str(root)], check=False).returncode,
                91,
            )

            recovery_crash = (
                "import os,sys;"
                f"sys.path.insert(0,{str(SCRIPTS_ROOT)!r});"
                "from pathlib import Path;"
                "from install_to_wiki import recover_install;"
                "recover_install(Path(sys.argv[1]),"
                "after_step=lambda step: os._exit(92) if step=='claude_rolled_back' else None)"
            )
            self.assertEqual(
                subprocess.run([sys.executable, "-c", recovery_crash, str(root)], check=False).returncode,
                92,
            )
            self.assertTrue((root / JOURNAL_NAME).is_file())
            self.assertTrue((root / LOCK_NAME).is_file())

            self.assertEqual(recover_install(root)["status"], "recovered")
            self.assertEqual(agents_marker.read_text(encoding="utf-8"), "agents-old")
            self.assertEqual(claude_marker.read_text(encoding="utf-8"), "claude-old")
            self.assertFalse((root / JOURNAL_NAME).exists())
            self.assertFalse((root / LOCK_NAME).exists())


if __name__ == "__main__":
    unittest.main()
