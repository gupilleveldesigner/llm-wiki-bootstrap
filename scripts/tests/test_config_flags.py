"""The installers run from flags alone: nobody has to write or keep a config JSON."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))

import bootstrap  # noqa: E402


def run(script: str, *arguments: str) -> dict:
    completed = subprocess.run(
        [sys.executable, str(SCRIPTS / script), *arguments],
        capture_output=True, text=True, encoding="utf-8", check=False,
    )
    return json.loads(completed.stdout)


def manifest(vault: Path) -> dict:
    return json.loads((vault / ".llm-wiki.json").read_text(encoding="utf-8"))


class ResolvedConfigTests(unittest.TestCase):
    def test_existing_config_passes_through_untouched(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            config = Path(temporary) / "config.json"
            config.write_text("{}", encoding="utf-8")
            with bootstrap.resolved_config(config, {}, default_name="Folder") as resolved:
                self.assertEqual(resolved, config)

    def test_flags_win_and_relative_roots_keep_their_meaning(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            config = Path(temporary) / "config.json"
            config.write_text(json.dumps({"project_name": "File", "project_root": "../Game"}), encoding="utf-8")
            with bootstrap.resolved_config(config, {"project_name": "Flag"}, default_name="Folder") as resolved:
                merged = json.loads(resolved.read_text(encoding="utf-8"))
                self.assertNotEqual(resolved.parent, config.parent)
            self.assertEqual(merged["project_name"], "Flag")
            self.assertEqual(merged["domain_summary"], "Flag")
            self.assertEqual(Path(merged["project_root"]), (Path(temporary) / "../Game").resolve())
            self.assertFalse(resolved.exists())  # the merged file is temporary

    def test_no_default_name_leaves_values_absent(self) -> None:
        with bootstrap.resolved_config(None, {}, default_name=None) as resolved:
            self.assertEqual(json.loads(resolved.read_text(encoding="utf-8")), {})


class KnowledgeCliTests(unittest.TestCase):
    def test_new_and_upgrade_without_any_config_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            vault = Path(temporary) / "Study Notes"
            created = run("bootstrap.py", "--target", str(vault), "--domain-summary", "Level design study")
            self.assertTrue(created["ok"], created)
            self.assertEqual(manifest(vault)["project_name"], "Study Notes")
            self.assertIn("Level design study", (vault / "wiki" / "overview.md").read_text(encoding="utf-8"))
            self.assertEqual(list(vault.rglob("config.json")), [vault / ".session-memory" / "config.json"])
            upgraded = run("upgrade.py", "--target", str(vault), "--source", "local")
            self.assertTrue(upgraded["ok"], upgraded)
            self.assertEqual(manifest(vault)["project_name"], "Study Notes")

    def test_failed_new_does_not_leave_an_empty_target(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            config = Path(temporary) / "broken.json"
            config.write_text(json.dumps({"project_name": 3}), encoding="utf-8")
            vault = Path(temporary) / "vault"
            self.assertFalse(run("bootstrap.py", "--target", str(vault), "--config", str(config))["ok"])
            self.assertFalse(vault.exists())


class GameCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.project = Path(self.directory.name) / "MyGame"
        self.project.mkdir()
        (self.project / "project.godot").write_text("", encoding="utf-8")

    def tearDown(self) -> None:
        self.directory.cleanup()

    def test_flags_replace_the_game_config(self) -> None:
        result = run("game_project.py", "--project-root", str(self.project), "--mode", "new",
                     "--game-title", "My Game", "--source-root", "scenes/", "--knowledge-graph", "graphify")
        self.assertTrue(result["ok"], result)
        vault = Path(result["vault_root"])
        recorded = manifest(vault)
        self.assertEqual(recorded["project_name"], "MyGame Wiki")
        self.assertEqual(recorded["game_project"]["game_title"], "My Game")
        self.assertEqual(recorded["game_project"]["providers"], {"code_intelligence": None, "knowledge_graph": "graphify"})

        # An upgrade without flags keeps the recorded name and selection, and proposes nothing new.
        upgraded = run("game_project.py", "--project-root", str(self.project), "--vault-root", str(vault),
                       "--mode", "upgrade", "--source", "local")
        self.assertTrue(upgraded["ok"], upgraded)
        self.assertEqual(upgraded["proposals"], [])
        self.assertEqual(manifest(vault)["game_project"]["providers"]["knowledge_graph"], "graphify")

        cleared = run("game_project.py", "--project-root", str(self.project), "--vault-root", str(vault),
                      "--mode", "upgrade", "--source", "local", "--knowledge-graph", "none")
        self.assertTrue(cleared["ok"], cleared)
        self.assertIsNone(manifest(vault)["game_project"]["providers"]["knowledge_graph"])

    def test_command_line_layout_beats_config(self) -> None:
        config = Path(self.directory.name) / "config.json"
        config.write_text(json.dumps({"project_name": "G", "domain_summary": "G", "layout": "sidecar"}), encoding="utf-8")
        result = run("game_project.py", "--project-root", str(self.project), "--mode", "new",
                     "--config", str(config), "--layout", "embedded", "--dry-run")
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["layout"], "embedded")


if __name__ == "__main__":
    unittest.main()
