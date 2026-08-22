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
from ingest_runtime import finalize, graph_strategy, graph_workspace, record_graphify_run, validate_changed_files, verify  # noqa: E402
from install_to_wiki import JOURNAL_NAME, LOCK_NAME, install, install_lock, recover_install  # noqa: E402


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
    digest = hashlib.sha256((root / raw_relative).read_bytes()).hexdigest()
    (root / "wiki" / "concepts" / "test.md").write_text(
        "---\ntopics: [test]\n---\n# Test concept\n", encoding="utf-8"
    )
    return (
        "---\n"
        "type: source\n"
        "topics: [test]\n"
        f"sources: [[{raw_relative}]]\n"
        f"raw_sha256: {digest}\n"
        "key_claims: 1\nentities: 1\nconcepts: 1\nreflected_docs: 1\nrelations: 0\nevidence_spans: 1\n"
        "---\n"
        f"# {title}\n\n"
        "## 핵심 주장\n\n확인된 주장\n\n"
        "## 엔티티와 개념\n\n확인된 엔티티와 개념\n\n"
        "## 근거\n\n> source\n\n"
        "## Wiki에 반영된 문서\n\n[[concepts/test]]\n"
    )


class PortableIngestTests(unittest.TestCase):
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
