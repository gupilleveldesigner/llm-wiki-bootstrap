from __future__ import annotations

import importlib.util
import subprocess
import tempfile
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).parents[2] / "assets/project-modes/game/runtime/game_trace.py"
spec = importlib.util.spec_from_file_location("game_trace", MODULE_PATH)
assert spec and spec.loader
trace = importlib.util.module_from_spec(spec)
spec.loader.exec_module(trace)


def run_git(root: Path, *args: str) -> str:
    completed = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, check=True)
    return completed.stdout.strip()


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


class GameTraceTests(unittest.TestCase):
    def make_project(self, workspace: Path, *, nested_git: bool = False) -> tuple[Path, Path, Path]:
        repository = workspace / "Repository"
        project = repository / "games/Game" if nested_git else workspace / "Game"
        vault = workspace / "Game.wiki"
        project.mkdir(parents=True)
        git_root = repository if nested_git else project
        git_root.mkdir(parents=True, exist_ok=True)
        run_git(git_root, "init")
        run_git(git_root, "config", "user.email", "test@example.com")
        run_git(git_root, "config", "user.name", "Trace Test")
        write(project / "src/combat/LockOnSystem.ts", "export function selectTarget() { return 1; }\n")
        run_git(git_root, "add", ".")
        run_git(git_root, "commit", "-m", "Add lock-on implementation")

        write(
            vault / "wiki/game/features/FEATURE-LOCKON-001.md",
            """---
type: game_feature_spec
feature_id: FEATURE-LOCKON-001
title: Lock-on
design_status: accepted
implementation_status: implemented
validation_status: partial
production_status: done
live_paths:
  - src/combat/LockOnSystem.ts#selectTarget@lines 1-1
updated: 2026-08-29
---
# Lock-on

<!-- GAME-SYNC:DESIGN-START -->
## 플레이어 경험

가장 가까운 유효 대상을 선택한다.

## 동작 계약

시야 안의 대상을 거리순으로 평가한다.
<!-- GAME-SYNC:DESIGN-END -->

## 실제 구현 상태

검사 전.
""",
        )
        write(
            vault / "wiki/game/implementation/IMPL-LOCKON-001.md",
            """---
type: game_implementation_check
check_id: IMPL-LOCKON-001
subject_id: FEATURE-LOCKON-001
expected_spec: wiki/game/features/FEATURE-LOCKON-001.md
source_revision: UNKNOWN
implementation_status: implemented
validation_status: partial
checked_paths:
  - src/combat/LockOnSystem.ts#selectTarget@lines 1-1
sync_baseline_status: pending
checked_at: 2026-08-29
---
# Check
""",
        )
        return project, vault, git_root

    def accept(self, project: Path, vault: Path) -> dict:
        return trace.accept_sync_baseline(
            vault,
            project,
            "wiki/game/implementation/IMPL-LOCKON-001.md",
        )

    def test_accept_creates_reproducible_bidirectional_in_sync_baseline(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project, vault, _ = self.make_project(Path(temporary))
            before = trace.build_index(vault, project)
            edge = next(edge for edge in before["edges"] if edge["relation"] == "implemented_by")
            self.assertEqual(edge["sync_status"], "unverified")

            accepted = self.accept(project, vault)
            self.assertTrue(accepted["ok"])
            self.assertEqual(accepted["sync_statuses"], ["in_sync"])

            check = trace.parse_frontmatter(vault / "wiki/game/implementation/IMPL-LOCKON-001.md")
            self.assertEqual(check["sync_baseline_status"], "accepted")
            self.assertRegex(check["checked_spec_digest"], r"^sha256:[0-9a-f]{64}$")
            self.assertEqual(len(check["checked_code_fingerprints"]), 1)

            index = trace.load_index(vault / trace.DEFAULT_INDEX)
            edge = next(edge for edge in index["edges"] if edge["relation"] == "implemented_by")
            self.assertEqual(edge["sync_status"], "in_sync")
            self.assertEqual(edge["trace_status"], "current")
            self.assertEqual(trace.query_path(index, "src/combat/LockOnSystem.ts#selectTarget")["specs"][0]["id"], "FEATURE-LOCKON-001")
            self.assertTrue(trace.verification_summary(vault, vault / trace.DEFAULT_INDEX, project, strict_sync=True)["ok"])

    def test_code_change_is_distinct_from_design_change(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project, vault, git_root = self.make_project(Path(temporary))
            self.accept(project, vault)
            write(project / "src/combat/LockOnSystem.ts", "export function selectTarget() { return 2; }\n")
            run_git(git_root, "add", ".")
            run_git(git_root, "commit", "-m", "Change targeting")

            current = trace.build_index(vault, project)
            edge = next(edge for edge in current["edges"] if edge["relation"] == "implemented_by")
            self.assertEqual(edge["sync_status"], "code_changed")
            self.assertIn("fingerprint changed", edge["stale_reasons"][0])
            self.assertFalse(trace.verification_summary(vault, vault / trace.DEFAULT_INDEX, project, strict_sync=True)["ok"])
            proposal = trace.sync_proposals(current)[0]
            self.assertEqual(proposal["sync_status"], "code_changed")
            self.assertFalse(proposal["automatic_mutation"])

    def test_semantic_design_change_is_detected_but_operational_metadata_is_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project, vault, _ = self.make_project(Path(temporary))
            self.accept(project, vault)
            spec_path = vault / "wiki/game/features/FEATURE-LOCKON-001.md"
            text = spec_path.read_text(encoding="utf-8")
            spec_path.write_text(text.replace("updated: 2026-08-29", "updated: 2026-08-30"), encoding="utf-8")
            current = trace.build_index(vault, project)
            edge = next(edge for edge in current["edges"] if edge["relation"] == "implemented_by")
            self.assertEqual(edge["sync_status"], "in_sync")

            text = spec_path.read_text(encoding="utf-8")
            spec_path.write_text(text.replace("가장 가까운 유효 대상을 선택한다.", "조준 방향과 가까운 유효 대상을 선택한다."), encoding="utf-8")
            current = trace.build_index(vault, project)
            edge = next(edge for edge in current["edges"] if edge["relation"] == "implemented_by")
            self.assertEqual(edge["sync_status"], "design_changed")

    def test_both_changed_requires_reconciliation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project, vault, git_root = self.make_project(Path(temporary))
            self.accept(project, vault)
            spec_path = vault / "wiki/game/features/FEATURE-LOCKON-001.md"
            spec_path.write_text(spec_path.read_text(encoding="utf-8").replace("거리순", "각도와 거리순"), encoding="utf-8")
            write(project / "src/combat/LockOnSystem.ts", "export function selectTarget() { return 3; }\n")
            run_git(git_root, "add", ".")
            run_git(git_root, "commit", "-m", "Change targeting again")

            current = trace.build_index(vault, project)
            edge = next(edge for edge in current["edges"] if edge["relation"] == "implemented_by")
            self.assertEqual(edge["sync_status"], "both_changed")
            self.assertEqual(len(edge["stale_reasons"]), 2)
            self.assertIn("reconcile", " ".join(trace.sync_proposals(current)[0]["recommended_actions"]))

    def test_dirty_linked_code_requires_explicit_baseline_acceptance(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project, vault, _ = self.make_project(Path(temporary))
            write(project / "src/combat/LockOnSystem.ts", "export function selectTarget() { return 9; }\n")
            with self.assertRaisesRegex(trace.TraceError, "uncommitted"):
                self.accept(project, vault)
            accepted = trace.accept_sync_baseline(
                vault,
                project,
                "wiki/game/implementation/IMPL-LOCKON-001.md",
                allow_dirty=True,
            )
            self.assertTrue(accepted["project_dirty"])
            self.assertTrue(accepted["ok"])

    def test_nested_monorepo_git_paths_are_normalized_to_project_relative_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project, vault, git_root = self.make_project(Path(temporary), nested_git=True)
            self.accept(project, vault)
            before = run_git(git_root, "rev-parse", "HEAD")
            write(project / "src/combat/LockOnSystem.ts", "export function selectTarget() { return 4; }\n")
            run_git(git_root, "add", ".")
            run_git(git_root, "commit", "-m", "Nested game change")
            after = run_git(git_root, "rev-parse", "HEAD")

            self.assertEqual(trace.changed_paths(project, before, after), ["src/combat/LockOnSystem.ts"])
            current = trace.build_index(vault, project)
            affected = trace.affected_by_diff(project, current, before, after)
            self.assertIn("code_changed:src/combat/LockOnSystem.ts", affected["affected_specs"][0]["reasons"])

    def test_missing_live_path_is_checked_in_project_root(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            project = workspace / "Game"
            vault = workspace / "Game.wiki"
            project.mkdir()
            write(
                vault / "wiki/game/systems/SYSTEM-MISSING-001.md",
                """---
type: game_system_spec
system_id: SYSTEM-MISSING-001
live_paths:
  - src/missing.py#Missing
---
# Missing
""",
            )
            index = trace.build_index(vault, project)
            errors = [item for item in index["issues"] if item["severity"] == "error"]
            self.assertEqual(errors[0]["code"], "missing_live_path")
            edge = next(edge for edge in index["edges"] if edge["relation"] == "implemented_by")
            self.assertEqual(edge["sync_status"], "missing")

    def test_manifest_resolves_sidecar_project_root(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            project = workspace / "Game"
            vault = workspace / "Game.wiki"
            project.mkdir()
            write(vault / ".llm-wiki.json", '{"game_project":{"project_root":"../Game","project_root_kind":"relative"}}')
            self.assertEqual(trace.project_root_from_manifest(vault), project.resolve())

    def test_invalid_absolute_path_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "project-relative"):
            trace.parse_code_ref("/tmp/game.py#run")


if __name__ == "__main__":
    unittest.main()
