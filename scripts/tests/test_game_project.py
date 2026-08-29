from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).parents[1]))
import game_project  # noqa: E402


def write_config(root: Path, **overrides: object) -> Path:
    config: dict[str, object] = {
        "project_name": "Test Game Wiki",
        "domain_summary": "A test game project",
        "game_title": "Test Game",
        "game_engine": "UNKNOWN",
        "game_genre": "Action Puzzle",
        "target_platforms": "Windows, Web",
        "project_phase": "prototype",
    }
    config.update(overrides)
    path = root / "config.json"
    path.write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")
    return path


def write(path: Path, content: str = "x") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def make_unity_project(root: Path) -> None:
    write(root / "Assets/Scripts/Player.cs", "class Player {}\n")
    write(root / "Packages/manifest.json", "{}\n")
    write(root / "ProjectSettings/ProjectVersion.txt", "m_EditorVersion: 6000\n")


class GameProjectModeTests(unittest.TestCase):
    def test_migrate_existing_unity_project_creates_sidecar_without_touching_engine_tree(self) -> None:
        with tempfile.TemporaryDirectory(prefix="game-sidecar-") as temporary:
            root = Path(temporary)
            project = root / "UnityGame"
            make_unity_project(project)
            config = write_config(root, source_roots=["Assets"])
            before = (project / "Assets/Scripts/Player.cs").read_bytes()

            result = game_project.run_local_game_project(
                project,
                config,
                "migrate",
                "evidence",
                integrity_mode="full",
            )

            vault = root / "UnityGame.wiki"
            self.assertTrue(result["ok"])
            self.assertEqual(result["base_mode"], "new")
            self.assertEqual(result["layout"], "sidecar")
            self.assertEqual(result["engine"]["id"], "unity")
            self.assertEqual((project / "Assets/Scripts/Player.cs").read_bytes(), before)
            self.assertTrue(result["post_apply_verification"]["project_integrity"]["ok"])
            self.assertTrue((vault / ".llm-wiki-managed.json").is_file())
            self.assertTrue((vault / "tools/game_trace.py").is_file())
            self.assertTrue((vault / "wiki/game/traceability.json").is_file())
            self.assertIn("checked_spec_digest", (vault / "templates/game/implementation-check.md").read_text(encoding="utf-8"))
            manifest = json.loads((vault / ".llm-wiki.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["project_mode_version"], 4)
            self.assertEqual(manifest["game_traceability"]["schema_version"], 2)
            self.assertEqual(manifest["game_traceability"]["sync_baseline_version"], 1)
            self.assertEqual(manifest["game_project"]["layout"], "sidecar")
            self.assertEqual(manifest["game_project"]["project_root"], "../UnityGame")
            self.assertEqual(manifest["game_project"]["engine_adapter"], "unity")
            self.assertEqual(manifest["game_project"]["write_policy"], "vault-only")
            trace_index = json.loads((vault / "wiki/game/traceability.json").read_text(encoding="utf-8"))
            self.assertEqual(trace_index["schema_version"], 2)
            self.assertIn("sync_counts", trace_index)

    def test_dry_run_reports_exact_plan_without_final_mutation(self) -> None:
        with tempfile.TemporaryDirectory(prefix="game-dry-run-") as temporary:
            root = Path(temporary)
            project = root / "UnityGame"
            make_unity_project(project)
            config = write_config(root, source_roots=["Assets"])

            result = game_project.run_local_game_project(project, config, "migrate", dry_run=True)

            self.assertTrue(result["ok"])
            self.assertTrue(result["dry_run"])
            self.assertFalse(result["mutation_started"])
            self.assertFalse((root / "UnityGame.wiki").exists())
            self.assertFalse((root / ".llm-wiki-transactions").exists())
            self.assertEqual(result["write_plan"]["protected_path_writes"], [])
            self.assertEqual(result["write_plan"]["write_policy"], "vault-only")

    def test_embedded_godot_vault_is_isolated_with_gdignore(self) -> None:
        with tempfile.TemporaryDirectory(prefix="game-godot-") as temporary:
            root = Path(temporary)
            project = root / "GodotGame"
            write(project / "project.godot", "[application]\n")
            write(project / "scenes/main.tscn", "[gd_scene]\n")
            config = write_config(root)

            result = game_project.run_local_game_project(
                project,
                config,
                "migrate",
                layout="embedded",
                integrity_mode="full",
            )

            vault = project / ".llm-wiki"
            self.assertTrue(result["ok"])
            self.assertEqual(result["engine"]["id"], "godot")
            self.assertTrue((vault / ".gdignore").is_file())
            self.assertTrue((project / "project.godot").is_file())
            self.assertTrue((project / "scenes/main.tscn").is_file())

    def test_local_upgrade_preserves_user_docs_and_backs_up_managed_runtime(self) -> None:
        with tempfile.TemporaryDirectory(prefix="game-upgrade-") as temporary:
            root = Path(temporary)
            project = root / "UnityGame"
            make_unity_project(project)
            config = write_config(root, source_roots=["Assets"])
            first = game_project.run_local_game_project(project, config, "migrate")
            vault = Path(first["vault_root"])
            model = vault / "wiki/game/model.md"
            runtime = vault / "tools/game_trace.py"
            model.write_text("# user-owned game model\n", encoding="utf-8")
            runtime.write_text("# user-modified trace runtime\n", encoding="utf-8")

            result = game_project.upgrade_game_from_local(
                project,
                vault,
                config,
                layout="sidecar",
                engine_name="unity",
                dry_run=False,
                integrity_mode="metadata",
                keep_rollback_backup=True,
                allow_legacy_in_place=False,
                adopt_existing_vault=False,
            )

            self.assertTrue(result["ok"])
            self.assertEqual(model.read_text(encoding="utf-8"), "# user-owned game model\n")
            self.assertTrue(model.with_name("model.md.wiki-proposed").is_file())
            self.assertIn("TRACEABILITY_SCHEMA_VERSION = 2", runtime.read_text(encoding="utf-8"))
            self.assertIn("accept_sync_baseline", runtime.read_text(encoding="utf-8"))
            base_backup = Path(result["backup_dir"])
            self.assertEqual(
                (base_backup / "tools/game_trace.py").read_text(encoding="utf-8"),
                "# user-modified trace runtime\n",
            )
            self.assertIsNotNone(result["rollback_backup"])

    def test_foreign_default_sidecar_requires_explicit_adoption(self) -> None:
        with tempfile.TemporaryDirectory(prefix="game-foreign-vault-") as temporary:
            root = Path(temporary)
            project = root / "UnityGame"
            make_unity_project(project)
            write(root / "UnityGame.wiki/user.txt", "unrelated\n")
            config = write_config(root, source_roots=["Assets"])

            result = game_project.run_local_game_project(project, config, "migrate", dry_run=True)

            self.assertFalse(result["ok"])
            self.assertTrue(result["write_plan"]["collisions"])
            self.assertEqual((root / "UnityGame.wiki/user.txt").read_text(encoding="utf-8"), "unrelated\n")

    def test_nested_workspace_is_unsafe_until_project_root_is_selected(self) -> None:
        with tempfile.TemporaryDirectory(prefix="game-workspace-") as temporary:
            root = Path(temporary) / "Workspace"
            make_unity_project(root / "Unity")
            write(root / "Godot/project.godot")
            config = write_config(root.parent)

            result = game_project.run_local_game_project(root, config, "migrate", dry_run=True)

            self.assertFalse(result["ok"])
            self.assertTrue(result["engine"]["ambiguous"])
            self.assertIn("ambiguous", " ".join(result["write_plan"]["layout_errors"]))

    def test_remote_checkout_requires_workspace_safe_contract_before_mutation(self) -> None:
        with tempfile.TemporaryDirectory(prefix="game-remote-contract-") as temporary:
            checkout = Path(temporary) / "checkout"
            checkout.mkdir()
            with self.assertRaisesRegex(RuntimeError, "lacks game project mode"):
                game_project.validate_game_checkout(checkout)

    def test_github_failure_occurs_before_local_upgrade(self) -> None:
        with tempfile.TemporaryDirectory(prefix="game-remote-failure-") as temporary:
            root = Path(temporary)
            project = root / "Game"
            project.mkdir()
            config = write_config(root)
            with mock.patch.object(
                game_project.wiki_upgrade,
                "resolve_latest_commit",
                side_effect=RuntimeError("offline"),
            ):
                with mock.patch.object(game_project, "run_checkout_game_upgrade") as run_upgrade:
                    with self.assertRaisesRegex(RuntimeError, "offline"):
                        game_project.upgrade_game_from_github(
                            project,
                            root / "Game.wiki",
                            config,
                            layout="sidecar",
                            engine_name="generic",
                            dry_run=False,
                            integrity_mode="metadata",
                            keep_rollback_backup=True,
                            allow_legacy_in_place=False,
                            adopt_existing_vault=False,
                        )
                    run_upgrade.assert_not_called()
            self.assertFalse((root / "Game.wiki").exists())

    def test_config_rejects_non_string_source_roots(self) -> None:
        with self.assertRaisesRegex(ValueError, "source_roots"):
            game_project.validate_config(
                {"project_name": "X", "domain_summary": "Y", "source_roots": ["Assets", 3]},
                require_base=True,
            )


if __name__ == "__main__":
    unittest.main()
