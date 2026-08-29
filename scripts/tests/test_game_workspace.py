from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).parents[1]))
import game_workspace as workspace  # noqa: E402


def write(path: Path, content: str = "x") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


class EngineAdapterTests(unittest.TestCase):
    def test_detects_unity(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "Game"
            write(root / "Assets/Scripts/Player.cs")
            write(root / "Packages/manifest.json", "{}")
            write(root / "ProjectSettings/ProjectVersion.txt", "m_EditorVersion: 6000")
            result = workspace.detect_engine(root)
            self.assertEqual(result["id"], "unity")
            self.assertIn("Assets", result["protected_roots"])
            self.assertIn("Library", result["generated_roots"])

    def test_detects_unreal(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "Game"
            write(root / "Game.uproject", "{}")
            write(root / "Source/Game/Game.cpp")
            write(root / "Content/Maps/Test.umap")
            result = workspace.detect_engine(root)
            self.assertEqual(result["id"], "unreal")
            self.assertIn("Game.uproject", result["protected_roots"])

    def test_detects_godot_and_embedded_isolation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "Game"
            write(root / "project.godot", "[application]\n")
            write(root / "scenes/main.tscn")
            result = workspace.detect_engine(root)
            self.assertEqual(result["id"], "godot")
            self.assertEqual(result["isolation_files"], {".gdignore": ""})
            self.assertIn("scenes", result["protected_roots"])

    def test_detects_web_environment(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "Game"
            write(root / "package.json", json.dumps({"dependencies": {"phaser": "^3.80.0"}}))
            write(root / "src/main.ts")
            result = workspace.detect_engine(root)
            self.assertEqual(result["id"], "web")
            self.assertEqual(result["environment"], "phaser")

    def test_workspace_root_with_nested_engines_is_ambiguous(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "Workspace"
            write(root / "UnityGame/Assets/Scripts/A.cs")
            write(root / "UnityGame/Packages/manifest.json", "{}")
            write(root / "UnityGame/ProjectSettings/ProjectVersion.txt")
            write(root / "GodotGame/project.godot")
            result = workspace.detect_engine(root)
            self.assertTrue(result["ambiguous"])
            self.assertEqual({item["path"] for item in result["nested_projects"]}, {"GodotGame", "UnityGame"})


class WorkspaceTransactionTests(unittest.TestCase):
    def make_unity_project(self, root: Path) -> None:
        write(root / "Assets/Scripts/Player.cs", "class Player {}\n")
        write(root / "Packages/manifest.json", "{}\n")
        write(root / "ProjectSettings/ProjectVersion.txt", "version\n")

    def test_sidecar_apply_changes_only_vault(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            parent = Path(temporary)
            project = parent / "Game"
            self.make_unity_project(project)
            paths = workspace.resolve_workspace_paths(project, layout="sidecar")
            engine = workspace.detect_engine(project)
            before = workspace.snapshot_project(project, engine, mode="full")
            stage = workspace.make_staging_directory(paths)
            write(stage / "wiki/game/index.md", "# index\n")
            write(stage / ".llm-wiki.json", "{}\n")
            workspace.write_managed_manifest(stage, paths.vault_root, paths, engine, installation_mode="migrate")
            plan = workspace.build_write_plan(paths.vault_root, stage, paths, engine)
            self.assertTrue(plan["safe_to_apply"])
            self.assertEqual(plan["protected_path_writes"], [])

            result = workspace.apply_staged_vault(stage, paths, plan, post_apply_verify=lambda _: {"ok": True})
            self.assertTrue(result["ok"])
            self.assertTrue((paths.vault_root / "wiki/game/index.md").is_file())
            after = workspace.snapshot_project(project, engine, mode="full")
            self.assertEqual(workspace.compare_snapshots(before, after)["changed_paths"], [])

    def test_failed_post_apply_rolls_back_existing_vault(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            parent = Path(temporary)
            project = parent / "Game"
            self.make_unity_project(project)
            paths = workspace.resolve_workspace_paths(project, layout="sidecar")
            write(paths.vault_root / "existing.txt", "original\n")
            write(paths.vault_root / ".llm-wiki.json", "{}\n")
            stage = workspace.make_staging_directory(paths)
            workspace.seed_staging_from_existing(paths.vault_root, stage)
            write(stage / "existing.txt", "replacement\n")
            engine = workspace.detect_engine(project)
            workspace.write_managed_manifest(stage, paths.vault_root, paths, engine, installation_mode="upgrade")
            plan = workspace.build_write_plan(
                paths.vault_root,
                stage,
                paths,
                engine,
                backed_up_paths=["existing.txt"],
            )
            self.assertTrue(plan["safe_to_apply"])
            with self.assertRaises(workspace.WorkspaceError):
                workspace.apply_staged_vault(
                    stage,
                    paths,
                    plan,
                    post_apply_verify=lambda _: {"ok": False, "errors": ["forced failure"]},
                )
            self.assertEqual((paths.vault_root / "existing.txt").read_text(encoding="utf-8"), "original\n")


    def test_existing_vault_symlink_is_never_followed_and_plan_is_unsafe(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            parent = Path(temporary)
            project = parent / "Game"
            self.make_unity_project(project)
            paths = workspace.resolve_workspace_paths(project, layout="sidecar")
            paths.vault_root.mkdir()
            write(paths.vault_root / ".llm-wiki.json", "{}\n")
            outside = parent / "outside"
            outside.mkdir()
            try:
                (paths.vault_root / "tools").symlink_to(outside, target_is_directory=True)
            except OSError as error:
                self.skipTest(f"symlink creation is unavailable: {error}")

            stage = workspace.make_staging_directory(paths)
            links = workspace.seed_staging_from_existing(paths.vault_root, stage)
            write(stage / "tools/game_trace.py", "managed\n")
            self.assertEqual(links, ["tools"])
            self.assertFalse((outside / "game_trace.py").exists())

            engine = workspace.detect_engine(project)
            workspace.write_managed_manifest(stage, paths.vault_root, paths, engine, installation_mode="upgrade")
            plan = workspace.build_write_plan(paths.vault_root, stage, paths, engine)
            self.assertFalse(plan["safe_to_apply"])
            self.assertTrue(any("tools" in item for item in plan["symlink_violations"]))
            workspace.cleanup_staging(stage)

    def test_vault_root_symlink_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            parent = Path(temporary)
            project = parent / "Game"
            self.make_unity_project(project)
            real_vault = parent / "real-vault"
            real_vault.mkdir()
            sidecar = parent / "Game.wiki"
            try:
                sidecar.symlink_to(real_vault, target_is_directory=True)
            except OSError as error:
                self.skipTest(f"symlink creation is unavailable: {error}")
            with self.assertRaisesRegex(workspace.WorkspaceError, "symlink"):
                workspace.resolve_workspace_paths(project, layout="sidecar")

    def test_embedded_is_isolated_and_legacy_requires_opt_in(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary) / "Game"
            write(project / "project.godot")
            embedded = workspace.resolve_workspace_paths(project, layout="embedded")
            self.assertEqual(embedded.vault_root, project / ".llm-wiki")
            with self.assertRaisesRegex(workspace.WorkspaceError, "legacy"):
                workspace.resolve_workspace_paths(project, layout="legacy-in-place")


if __name__ == "__main__":
    unittest.main()
