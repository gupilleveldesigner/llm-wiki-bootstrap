from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).parents[2]
INGEST_SCRIPTS = REPOSITORY_ROOT / "assets/skills-bundle/agents-skills/ingest/scripts"
GAME_ADAPTER_PATH = REPOSITORY_ROOT / "assets/project-modes/game/ingest/game_adapter.py"
GAME_ROUTING_PATH = REPOSITORY_ROOT / "assets/project-modes/game/ingest/routing.json"
GAME_TRACE_PATH = REPOSITORY_ROOT / "assets/project-modes/game/runtime/game_trace.py"
GAME_ROUTING_PATH = REPOSITORY_ROOT / "assets/project-modes/game/ingest/routing.json"
if str(INGEST_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(INGEST_SCRIPTS))

from find_uningested import resolve_wiki_root  # noqa: E402
from ingest_core.adapter_contract import configured_adapter, dispatch_configured_adapter  # noqa: E402
import ingest_runtime as generic  # noqa: E402

spec = importlib.util.spec_from_file_location("game_ingest_adapter", GAME_ADAPTER_PATH)
assert spec and spec.loader
adapter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(adapter)


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def make_taxonomies(vault: Path) -> None:
    write(
        vault / "wiki/taxonomy.json",
        json.dumps(
            {
                "version": 1,
                "scheme": {"id": "topics", "prefLabel": "Topics", "scopeNote": "test"},
                "concepts": [
                    {
                        "id": "game-playtest",
                        "prefLabel": "Game Playtest",
                        "altLabel": [],
                        "scopeNote": "test",
                        "broader": [],
                    }
                ],
            }
        ),
    )
    write(
        vault / "wiki/game/taxonomy.json",
        json.dumps(
            {
                "schema": "test-game-taxonomy",
                "concepts": [
                    {"id": "game:feature"},
                    {"id": "game:playtest"},
                    {"id": "game:implementation-check"},
                ],
            }
        ),
    )


def make_source(vault: Path, raw_relative: str, source_id: str, reflected: str) -> Path:
    raw = vault / raw_relative
    digest = hashlib.sha256(raw.read_bytes()).hexdigest()
    note = f"""---
type: source
id: {source_id}
topics: [game-playtest]
sources: [[{raw_relative}]]
raw_sha256: {digest}
source_type: playtest
structurally_verified: true
semantic_status: reviewed
raw_line_count: 1
key_claims: 1
entities: 0
concepts: 1
reflected_docs: 1
relations: 0
evidence_spans: 1
coverage_spans: 1
key_decisions: 0
next_actions: 0
chronology_entries: 0
---
# Lock-on playtest source

## 핵심 주장

- 플레이어가 락온 해제를 놓쳤다.

## 엔티티

- 없음

## 개념

- 락온 가독성

## 관계

- 없음

## 의미 Coverage

- full | lines 1-1 | 원문 전체

## 핵심 결정

- 없음

## 다음 행동

- 없음

## Chronology

- 없음

## 근거

> [lines 1-1] observed lock-on failure

## Wiki에 반영된 문서

- [[{reflected}]]
"""
    path = vault / "wiki/sources/lockon-test.md"
    write(path, note)
    return path


class GameIngestTests(unittest.TestCase):
    def make_vault(self, workspace: Path) -> tuple[Path, Path, Path]:
        project = workspace / "Game"
        vault = workspace / "Game.wiki"
        project.mkdir()
        (vault / "raw/game/playtests").mkdir(parents=True)
        (vault / "wiki/sources").mkdir(parents=True)
        (vault / "wiki/game/features").mkdir(parents=True)
        (vault / "wiki/game/playtests").mkdir(parents=True)
        make_taxonomies(vault)
        write(vault / "raw/game/playtests/lockon-test.md", "observed lock-on failure\n")
        write(
            vault / ".llm-wiki.json",
            json.dumps(
                {
                    "profile": "evidence",
                    "project_mode": "game",
                    "game_project": {
                        "project_root": "../Game",
                        "project_root_kind": "relative",
                    },
                    "ingest": {
                        "schema_version": 3,
                        "adapter": "game",
                        "adapter_version": 1,
                        "adapter_path": "tools/ingest-adapters/game_adapter.py",
                        "routing": "tools/ingest-adapters/game-routing.json",
                        "ledger_version": 3,
                    },
                }
            ),
        )
        write(
            vault / "wiki/game/features/FEATURE-LOCKON-001.md",
            """---
type: game_feature_spec
feature_id: FEATURE-LOCKON-001
design_status: accepted
implementation_status: unknown
validation_status: partial
live_paths: []
evidence_refs:
  - RAW-PLAYTEST-001
---
# Lock-on
<!-- GAME-SYNC:DESIGN-START -->
## Player experience
Lock-on release must be readable.
<!-- GAME-SYNC:DESIGN-END -->
""",
        )
        write(
            vault / "wiki/game/playtests/PLAYTEST-LOCKON-001.md",
            """---
type: game_playtest_report
playtest_id: PLAYTEST-LOCKON-001
subject_refs:
  - FEATURE-LOCKON-001
build_id: UNKNOWN
validation_status: partial
raw_refs:
  - raw/game/playtests/lockon-test.md
evidence_refs:
  - RAW-PLAYTEST-001
---
# Playtest

## 관찰 — 해석을 섞지 않음

- 플레이어가 락온 해제를 놓쳤다.
""",
        )
        source = make_source(
            vault,
            "raw/game/playtests/lockon-test.md",
            "RAW-PLAYTEST-001",
            "game/playtests/PLAYTEST-LOCKON-001",
        )
        (vault / "tools/ingest-adapters").mkdir(parents=True)
        shutil.copy2(GAME_ROUTING_PATH, vault / "tools/ingest-adapters/game-routing.json")
        shutil.copy2(GAME_ADAPTER_PATH, vault / "tools/ingest-adapters/game_adapter.py")
        shutil.copy2(GAME_TRACE_PATH, vault / "tools/game_trace.py")
        return project, vault, source

    def test_sidecar_vault_is_resolved_from_installed_skill_anchor(self) -> None:
        with tempfile.TemporaryDirectory(prefix="game-ingest-root-") as temporary:
            workspace = Path(temporary)
            project = workspace / "Game"
            vault = workspace / "Game.wiki"
            project.mkdir()
            (vault / "raw").mkdir(parents=True)
            (vault / "wiki").mkdir()
            skill = vault / ".agents/skills/ingest"
            skill.mkdir(parents=True)

            resolved = resolve_wiki_root(None, start=project, skill_root=skill)

            self.assertEqual(resolved, vault.resolve())

    def test_manifest_adapter_is_vault_local_and_resolvable(self) -> None:
        with tempfile.TemporaryDirectory(prefix="game-ingest-adapter-") as temporary:
            root = Path(temporary)
            (root / "raw").mkdir()
            (root / "wiki").mkdir()
            adapter_path = root / "tools/ingest-adapters/game_adapter.py"
            write(adapter_path, "GAME_INGEST_ADAPTER_VERSION = 1\n")
            write(
                root / ".llm-wiki.json",
                json.dumps(
                    {
                        "project_mode": "game",
                        "ingest": {
                            "adapter": "game",
                            "adapter_version": 1,
                            "adapter_path": "tools/ingest-adapters/game_adapter.py",
                        },
                    }
                ),
            )

            configuration = configured_adapter(root)

            self.assertIsNotNone(configuration)
            assert configuration is not None
            self.assertEqual(configuration.adapter_id, "game")
            self.assertEqual(configuration.adapter_path, adapter_path.resolve())

    def test_shared_runtime_dispatches_to_the_manifest_adapter(self) -> None:
        with tempfile.TemporaryDirectory(prefix="game-ingest-dispatch-") as temporary:
            root = Path(temporary)
            (root / "raw").mkdir()
            (root / "wiki").mkdir()
            adapter_path = root / "tools/ingest-adapters/probe.py"
            marker = root / "adapter-ran.json"
            write(
                adapter_path,
                "from pathlib import Path\n"
                "import json, os, sys\n"
                f"Path({str(marker)!r}).write_text(json.dumps({{'root': os.environ.get('LLM_WIKI_INGEST_ROOT'), 'args': sys.argv[1:]}}), encoding='utf-8')\n",
            )
            write(
                root / ".llm-wiki.json",
                json.dumps(
                    {
                        "project_mode": "game",
                        "ingest": {
                            "adapter": "game",
                            "adapter_version": 1,
                            "adapter_path": "tools/ingest-adapters/probe.py",
                        },
                    }
                ),
            )

            exit_code = dispatch_configured_adapter(
                root,
                ["status"],
                runtime_path=INGEST_SCRIPTS / "ingest_runtime.py",
            )

            self.assertEqual(exit_code, 0)
            payload = json.loads(marker.read_text(encoding="utf-8"))
            self.assertEqual(Path(payload["root"]), root.resolve())
            self.assertEqual(payload["args"], ["status"])

    def test_installed_shared_runtime_auto_routes_from_live_project_to_sidecar(self) -> None:
        with tempfile.TemporaryDirectory(prefix="game-ingest-installed-route-") as temporary:
            project, vault, _ = self.make_vault(Path(temporary))
            installed_scripts = vault / ".agents/skills/ingest/scripts"
            shutil.copytree(INGEST_SCRIPTS, installed_scripts)
            installed_adapter = vault / "tools/ingest-adapters/game_adapter.py"
            installed_adapter.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(GAME_ADAPTER_PATH, installed_adapter)
            shutil.copy2(GAME_ROUTING_PATH, installed_adapter.with_name("game-routing.json"))

            completed = subprocess.run(
                [sys.executable, str(installed_scripts / "ingest_runtime.py"), "status"],
                cwd=project,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr or completed.stdout)
            payload = json.loads(completed.stdout)
            self.assertEqual(payload["adapter"], "game")
            self.assertEqual(Path(payload["root"]), vault.resolve())
            self.assertEqual(Path(payload["project_root"]), project.resolve())

    def test_typed_playtest_needs_no_generic_topics_and_resolves_source_and_spec(self) -> None:
        with tempfile.TemporaryDirectory(prefix="game-ingest-validate-") as temporary:
            _, vault, _ = self.make_vault(Path(temporary))

            result = adapter.validate_game_documents(
                vault,
                ["wiki/game/playtests/PLAYTEST-LOCKON-001.md"],
                generic,
            )

            self.assertTrue(result["valid"], result)
            self.assertEqual(result["reflections"][0]["document_id"], "PLAYTEST-LOCKON-001")
            self.assertEqual(result["reflections"][0]["subject_refs"], ["FEATURE-LOCKON-001"])
            self.assertEqual(result["reflections"][0]["evidence_refs"], ["RAW-PLAYTEST-001"])

    def test_source_must_reflect_back_to_the_game_document(self) -> None:
        with tempfile.TemporaryDirectory(prefix="game-ingest-reverse-") as temporary:
            _, vault, source = self.make_vault(Path(temporary))
            source.write_text(
                source.read_text(encoding="utf-8").replace(
                    "- [[game/playtests/PLAYTEST-LOCKON-001]]",
                    "- [[game/features/FEATURE-LOCKON-001]]",
                ),
                encoding="utf-8",
            )

            result = adapter.validate_game_documents(
                vault,
                ["wiki/game/playtests/PLAYTEST-LOCKON-001.md"],
                generic,
            )

            self.assertFalse(result["valid"])
            self.assertTrue(any("does not list this Game document" in error for error in result["errors"]), result)

    def test_playtest_route_requires_a_typed_playtest_reflection(self) -> None:
        with tempfile.TemporaryDirectory(prefix="game-ingest-route-") as temporary:
            _, vault, source = self.make_vault(Path(temporary))
            routing = {
                "routes": [
                    {
                        "prefix": "raw/game/playtests/",
                        "kind": "playtest",
                        "required_outputs": ["source_record", "game_playtest_report"],
                    }
                ]
            }

            errors = adapter.validate_required_route_outputs(
                vault,
                [source.relative_to(vault).as_posix()],
                [],
                routing,
                generic,
            )

            self.assertTrue(any("requires game_playtest_report" in error for error in errors), errors)

    def test_standard_game_allows_provisional_source_but_evidence_game_requires_review(self) -> None:
        with tempfile.TemporaryDirectory(prefix="game-ingest-profile-") as temporary:
            _, vault, source = self.make_vault(Path(temporary))
            source.write_text(
                source.read_text(encoding="utf-8").replace(
                    "semantic_status: reviewed", "semantic_status: partial"
                ),
                encoding="utf-8",
            )

            evidence_result = adapter.validate_game_documents(
                vault,
                ["wiki/game/playtests/PLAYTEST-LOCKON-001.md"],
                generic,
            )
            self.assertFalse(evidence_result["valid"])
            self.assertTrue(any("requires reviewed Source" in error for error in evidence_result["errors"]))

            manifest_path = vault / ".llm-wiki.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["profile"] = "standard"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            standard_result = adapter.validate_game_documents(
                vault,
                ["wiki/game/playtests/PLAYTEST-LOCKON-001.md"],
                generic,
            )
            self.assertTrue(standard_result["valid"], standard_result)
            self.assertTrue(any("remains provisional" in warning for warning in standard_result["warnings"]))

    def test_non_source_evidence_is_preserved_but_direct_source_or_raw_provenance_is_still_required(self) -> None:
        with tempfile.TemporaryDirectory(prefix="game-ingest-mixed-evidence-") as temporary:
            _, vault, _ = self.make_vault(Path(temporary))
            playtest = vault / "wiki/game/playtests/PLAYTEST-LOCKON-001.md"
            playtest.write_text(
                playtest.read_text(encoding="utf-8").replace(
                    "  - RAW-PLAYTEST-001\n",
                    "  - RAW-PLAYTEST-001\n  - CLAIM-LOCKON-001\n  - EXPERIMENT-LOCKON-001\n",
                ),
                encoding="utf-8",
            )

            result = adapter.validate_game_documents(vault, [playtest.relative_to(vault).as_posix()], generic)

            self.assertTrue(result["valid"], result)
            reflection = result["reflections"][0]
            self.assertEqual(
                reflection["non_source_evidence_refs"],
                ["CLAIM-LOCKON-001", "EXPERIMENT-LOCKON-001"],
            )
            self.assertTrue(any("do not prove direct ingest provenance" in item for item in result["warnings"]), result)

    def test_configured_routing_is_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory(prefix="game-ingest-routing-") as temporary:
            _, vault, _ = self.make_vault(Path(temporary))
            (vault / "tools/ingest-adapters/game-routing.json").unlink()

            with self.assertRaisesRegex(adapter.GameIngestError, "routing is missing"):
                adapter.routing_config(vault, adapter.read_manifest(vault))

    def test_implementation_check_cannot_be_completed_by_ingest(self) -> None:
        with tempfile.TemporaryDirectory(prefix="game-ingest-check-") as temporary:
            _, vault, _ = self.make_vault(Path(temporary))
            check = vault / "wiki/game/implementation/IMPL-001.md"
            write(
                check,
                """---
type: game_implementation_check
check_id: IMPL-001
subject_id: FEATURE-LOCKON-001
checked_paths:
  - src/lockon.py#select
---
# Implementation check
""",
            )

            result = adapter.validate_game_documents(vault, [check.relative_to(vault).as_posix()], generic)

            self.assertFalse(result["valid"])
            self.assertTrue(any("inspect/accept-sync workflow" in item for item in result["errors"]), result)

    def test_unknown_source_id_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory(prefix="game-ingest-source-") as temporary:
            _, vault, _ = self.make_vault(Path(temporary))
            playtest = vault / "wiki/game/playtests/PLAYTEST-LOCKON-001.md"
            playtest.write_text(
                playtest.read_text(encoding="utf-8").replace("RAW-PLAYTEST-001", "RAW-MISSING-001"),
                encoding="utf-8",
            )

            result = adapter.validate_game_documents(vault, [playtest.relative_to(vault).as_posix()], generic)

            self.assertFalse(result["valid"])
            self.assertTrue(any("unknown Source ID" in error for error in result["errors"]), result)

    def test_finalize_requires_route_mandated_game_reflection(self) -> None:
        with tempfile.TemporaryDirectory(prefix="game-ingest-required-reflection-") as temporary:
            _, vault, source = self.make_vault(Path(temporary))
            result = adapter.finalize_game(
                vault,
                Namespace(changed_file=[source.relative_to(vault).as_posix()], complete_batch=False),
                generic,
            )

            self.assertEqual(result["exit_code"], 2, result)
            self.assertEqual(result["ingest_status"], "incomplete")
            self.assertEqual(result["game_reflection_status"], "failed")
            self.assertTrue(any("requires game_playtest_report" in error for error in result["errors"]))

    def test_trace_failure_does_not_erase_completed_ingest_but_blocks_integrated_finalize(self) -> None:
        with tempfile.TemporaryDirectory(prefix="game-ingest-trace-failure-") as temporary:
            _, vault, source = self.make_vault(Path(temporary))
            (vault / "tools/game_trace.py").unlink()
            result = adapter.finalize_game(
                vault,
                Namespace(
                    changed_file=[
                        source.relative_to(vault).as_posix(),
                        "wiki/game/playtests/PLAYTEST-LOCKON-001.md",
                    ],
                    complete_batch=False,
                ),
                generic,
            )

            self.assertEqual(result["exit_code"], 2, result)
            self.assertEqual(result["ingest_status"], "complete")
            self.assertEqual(result["game_reflection_status"], "complete")
            self.assertEqual(result["game_sync_status"], "unavailable")
            self.assertEqual(result["status"], "game_trace_failed")

    def test_finalize_reuses_generic_source_engine_and_enriches_ledger_without_accepting_sync(self) -> None:
        with tempfile.TemporaryDirectory(prefix="game-ingest-finalize-") as temporary:
            project, vault, source = self.make_vault(Path(temporary))
            before = list(project.rglob("*"))
            args = Namespace(
                changed_file=[
                    source.relative_to(vault).as_posix(),
                    "wiki/game/playtests/PLAYTEST-LOCKON-001.md",
                ],
                complete_batch=False,
            )

            result = adapter.finalize_game(vault, args, generic)

            self.assertEqual(result["exit_code"], 0, result)
            self.assertEqual(result["ingest_status"], "complete")
            self.assertEqual(result["game_reflection_status"], "complete")
            self.assertTrue(result["game_routing"]["valid"], result)
            self.assertTrue(result["game_routing"]["routes"][0]["complete"], result)
            self.assertIn(result["game_sync_status"], {"in_sync", "actions_required"})
            ledger = json.loads((vault / "wiki/ingest-ledger.json").read_text(encoding="utf-8"))
            self.assertEqual(ledger["version"], 3)
            self.assertEqual(ledger["adapter"]["id"], "game")
            self.assertEqual(ledger["game_reflections"][0]["document_id"], "PLAYTEST-LOCKON-001")
            self.assertEqual(ledger["sources"][0]["source_id"], "RAW-PLAYTEST-001")
            self.assertFalse(any(path.name == "IMPL-000.md" for path in vault.rglob("*")))
            self.assertEqual(before, list(project.rglob("*")))


if __name__ == "__main__":
    unittest.main()
