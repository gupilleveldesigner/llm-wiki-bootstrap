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
    def make_project(self, workspace: Path) -> tuple[Path, Path, str, str]:
        project = workspace / "Game"
        vault = workspace / "Game.wiki"
        project.mkdir()
        run_git(project, "init")
        run_git(project, "config", "user.email", "test@example.com")
        run_git(project, "config", "user.name", "Trace Test")
        write(project / "src/combat/LockOnSystem.ts", "export function selectTarget() { return 1; }\n")
        run_git(project, "add", ".")
        run_git(project, "commit", "-m", "Add lock-on implementation")
        checked_revision = run_git(project, "rev-parse", "HEAD")

        write(
            vault / "wiki/game/features/FEATURE-LOCKON-001.md",
            """---
type: game_feature_spec
feature_id: FEATURE-LOCKON-001
design_status: accepted
implementation_status: implemented
validation_status: partial
production_status: done
live_paths:
  - src/combat/LockOnSystem.ts#selectTarget@lines 1-1
build_refs:
  - BUILD-001
playtest_refs:
  - PLAYTEST-001
decision_refs:
  - GDEC-001
---
# Lock-on
""",
        )
        write(
            vault / "wiki/game/implementation/IMPL-LOCKON-001.md",
            f"""---
type: game_implementation_check
check_id: IMPL-LOCKON-001
subject_id: FEATURE-LOCKON-001
expected_spec: wiki/game/features/FEATURE-LOCKON-001.md
source_revision: {checked_revision}
build_id: BUILD-001
implementation_status: implemented
validation_status: partial
checked_paths:
  - src/combat/LockOnSystem.ts#selectTarget@lines 1-1
playtest_refs:
  - PLAYTEST-001
decision_refs:
  - GDEC-001
checked_at: 2026-08-29
---
# Check
""",
        )
        write(
            vault / "wiki/game/builds/BUILD-001.md",
            f"""---
type: game_build_report
build_id: BUILD-001
source_revision: {checked_revision}
platform: Web
validation_status: partial
subject_refs:
  - FEATURE-LOCKON-001
---
# Build
""",
        )
        write(
            vault / "wiki/game/playtests/PLAYTEST-001.md",
            """---
type: game_playtest_report
playtest_id: PLAYTEST-001
subject_refs:
  - FEATURE-LOCKON-001
build_id: BUILD-001
validation_status: partial
---
# Playtest
""",
        )
        write(
            vault / "wiki/game/decisions/GDEC-001.md",
            """---
type: game_decision_record
decision_id: GDEC-001
decision_status: accepted
affected_refs:
  - FEATURE-LOCKON-001
---
# Decision
""",
        )
        return project, vault, checked_revision, run_git(project, "rev-parse", "HEAD")

    def test_rebuild_supports_separate_roots_and_bidirectional_trace(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project, vault, _, _ = self.make_project(Path(temporary))
            index = trace.build_index(vault, project)
            trace.write_index(vault / trace.DEFAULT_INDEX, index)

            self.assertEqual(index["schema_version"], 1)
            self.assertEqual(index["project_root"], {"kind": "relative", "value": "../Game"})
            implementation = [edge for edge in index["edges"] if edge["relation"] == "implemented_by"]
            self.assertEqual(implementation[0]["trace_status"], "current")
            self.assertEqual(implementation[0]["locators"], ["lines 1-1"])

            spec_result = trace.query_spec(index, "FEATURE-LOCKON-001")
            self.assertEqual(
                {edge["relation"] for edge in spec_result["edges"]},
                {"implemented_by", "built_in", "validated_by", "governed_by"},
            )
            path_result = trace.query_path(index, "src/combat/LockOnSystem.ts#selectTarget")
            self.assertEqual([item["id"] for item in path_result["specs"]], ["FEATURE-LOCKON-001"])
            self.assertTrue(trace.verification_summary(vault, vault / trace.DEFAULT_INDEX, project)["ok"])

    def test_code_change_marks_relation_stale_and_affected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project, vault, _, before_change = self.make_project(Path(temporary))
            initial = trace.build_index(vault, project)
            trace.write_index(vault / trace.DEFAULT_INDEX, initial)

            write(project / "src/combat/LockOnSystem.ts", "export function selectTarget() { return 2; }\n")
            run_git(project, "add", ".")
            run_git(project, "commit", "-m", "Change targeting")
            after_change = run_git(project, "rev-parse", "HEAD")

            current = trace.build_index(vault, project)
            implementation = [edge for edge in current["edges"] if edge["relation"] == "implemented_by"]
            self.assertEqual(implementation[0]["trace_status"], "stale")
            verification = trace.verification_summary(vault, vault / trace.DEFAULT_INDEX, project, strict_stale=True)
            self.assertFalse(verification["ok"])
            affected = trace.affected_by_diff(project, current, before_change, after_change)
            self.assertEqual(affected["affected_specs"][0]["spec_id"], "FEATURE-LOCKON-001")
            self.assertIn("code_changed:src/combat/LockOnSystem.ts", affected["affected_specs"][0]["reasons"])

    def test_missing_live_path_is_checked_in_project_root(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            project = workspace / "Game"
            vault = workspace / "Game.wiki"
            project.mkdir()
            run_git(project, "init")
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

    def test_manifest_resolves_sidecar_project_root(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            project = workspace / "Game"
            vault = workspace / "Game.wiki"
            project.mkdir()
            write(
                vault / ".llm-wiki.json",
                '{"game_project":{"project_root":"../Game","project_root_kind":"relative"}}',
            )
            self.assertEqual(trace.project_root_from_manifest(vault), project.resolve())

    def test_invalid_absolute_path_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "project-relative"):
            trace.parse_code_ref("/tmp/game.py#run")


if __name__ == "__main__":
    unittest.main()
