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
    def make_project(self, root: Path) -> tuple[str, str]:
        run_git(root, "init")
        run_git(root, "config", "user.email", "test@example.com")
        run_git(root, "config", "user.name", "Trace Test")
        write(root / "src/combat/LockOnSystem.ts", "export function selectTarget() { return 1; }\n")
        write(
            root / "wiki/game/features/FEATURE-LOCKON-001.md",
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
        run_git(root, "add", ".")
        run_git(root, "commit", "-m", "Add lock-on implementation")
        checked_revision = run_git(root, "rev-parse", "HEAD")
        write(
            root / "wiki/game/implementation/IMPL-LOCKON-001.md",
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
            root / "wiki/game/builds/BUILD-001.md",
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
            root / "wiki/game/playtests/PLAYTEST-001.md",
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
            root / "wiki/game/decisions/GDEC-001.md",
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
        run_git(root, "add", ".")
        run_git(root, "commit", "-m", "Add trace documents")
        return checked_revision, run_git(root, "rev-parse", "HEAD")

    def test_rebuild_supports_bidirectional_trace_and_matrix(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.make_project(root)
            index = trace.build_index(root)
            trace.write_index(root / trace.DEFAULT_INDEX, index)

            self.assertEqual(index["schema_version"], 1)
            implementation = [edge for edge in index["edges"] if edge["relation"] == "implemented_by"]
            self.assertEqual(len(implementation), 1)
            self.assertEqual(implementation[0]["trace_status"], "current")
            self.assertEqual(implementation[0]["locators"], ["lines 1-1"])

            spec_result = trace.query_spec(index, "FEATURE-LOCKON-001")
            self.assertEqual({edge["relation"] for edge in spec_result["edges"]}, {"implemented_by", "built_in", "validated_by", "governed_by"})

            path_result = trace.query_path(index, "src/combat/LockOnSystem.ts#selectTarget")
            self.assertEqual([item["id"] for item in path_result["specs"]], ["FEATURE-LOCKON-001"])

            matrix = trace.traceability_matrix(index)
            self.assertEqual(matrix[0]["current_code_relations"], 1)
            self.assertEqual(matrix[0]["builds"], ["BUILD-001"])
            self.assertEqual(matrix[0]["tests"], ["PLAYTEST-001"])
            self.assertEqual(matrix[0]["decisions"], ["GDEC-001"])

            verification = trace.verification_summary(root, root / trace.DEFAULT_INDEX)
            self.assertTrue(verification["ok"])

    def test_code_change_marks_relation_stale_and_affected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _, before_change = self.make_project(root)
            initial = trace.build_index(root)
            trace.write_index(root / trace.DEFAULT_INDEX, initial)

            write(root / "src/combat/LockOnSystem.ts", "export function selectTarget() { return 2; }\n")
            run_git(root, "add", ".")
            run_git(root, "commit", "-m", "Change targeting")
            after_change = run_git(root, "rev-parse", "HEAD")

            current = trace.build_index(root)
            implementation = [edge for edge in current["edges"] if edge["relation"] == "implemented_by"]
            self.assertEqual(implementation[0]["trace_status"], "stale")

            verification = trace.verification_summary(root, root / trace.DEFAULT_INDEX, strict_stale=True)
            self.assertFalse(verification["ok"])
            self.assertIn("traceability index is out of date; run rebuild", verification["errors"])

            affected = trace.affected_by_diff(root, current, before_change, after_change)
            self.assertEqual(affected["affected_specs"][0]["spec_id"], "FEATURE-LOCKON-001")
            self.assertIn("code_changed:src/combat/LockOnSystem.ts", affected["affected_specs"][0]["reasons"])
            self.assertEqual(len(affected["stale_edges"]), 1)

    def test_missing_live_path_is_an_error(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            run_git(root, "init")
            run_git(root, "config", "user.email", "test@example.com")
            run_git(root, "config", "user.name", "Trace Test")
            write(
                root / "wiki/game/systems/SYSTEM-MISSING-001.md",
                """---
type: game_system_spec
system_id: SYSTEM-MISSING-001
live_paths:
  - src/missing.py#Missing
---
# Missing
""",
            )
            run_git(root, "add", ".")
            run_git(root, "commit", "-m", "Add missing relation")
            index = trace.build_index(root)
            errors = [item for item in index["issues"] if item["severity"] == "error"]
            self.assertEqual(errors[0]["code"], "missing_live_path")
            implementation = [edge for edge in index["edges"] if edge["relation"] == "implemented_by"]
            self.assertEqual(implementation[0]["trace_status"], "missing")

    def test_invalid_absolute_path_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "project-relative"):
            trace.parse_code_ref("/tmp/game.py#run")


if __name__ == "__main__":
    unittest.main()
