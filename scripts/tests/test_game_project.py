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
        "project_name": "Test Game",
        "domain_summary": "A test game project",
        "game_title": "Test Game",
        "game_engine": "Godot 4",
        "game_genre": "Action Puzzle",
        "target_platforms": "Windows, Web",
        "project_phase": "prototype",
        "source_roots": ["game/", "addons/"],
    }
    config.update(overrides)
    path = root / "config.json"
    path.write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")
    return path


class GameProjectModeTests(unittest.TestCase):
    def test_new_evidence_game_scaffolds_orthogonal_project_mode(self) -> None:
        with tempfile.TemporaryDirectory(prefix="game-mode-new-") as temporary:
            root = Path(temporary)
            target = root / "vault"
            config = write_config(root)

            result = game_project.apply_local_game_project(target, config, "new", "evidence")

            self.assertTrue(result["ok"])
            self.assertEqual(result["profile"], "evidence")
            self.assertEqual(result["project_mode"], "game")
            self.assertEqual(result["project_mode_verification"]["status"], "ok")
            self.assertFalse(result["project_mode_activation_pending"])
            manifest = json.loads((target / ".llm-wiki.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["profile"], "evidence")
            self.assertEqual(manifest["project_mode"], "game")
            self.assertEqual(manifest["game_project"]["game_engine"], "Godot 4")
            self.assertEqual(manifest["game_project"]["source_roots"], ["game/", "addons/"])
            for relative in (
                "wiki/game/features",
                "wiki/game/systems",
                "wiki/game/levels",
                "wiki/game/implementation",
                "wiki/game/playtests",
                "wiki/game/decisions",
                "raw/game/builds",
                "Output/game",
            ):
                self.assertTrue((target / relative).is_dir(), relative)
            self.assertTrue((target / "templates/game/feature-spec.md").is_file())
            self.assertTrue((target / "templates/game/playtest-report.md").is_file())
            self.assertTrue((target / ".agents/skills/game-project/SKILL.md").is_file())
            self.assertTrue((target / ".claude/skills/game-project/SKILL.md").is_file())
            self.assertTrue((target / ".agents/skills/canon-review/SKILL.md").is_file())
            self.assertIn("LLM-WIKI:GAME-PROJECT-MODE", (target / "CLAUDE.md").read_text(encoding="utf-8"))
            self.assertIn("LLM-WIKI:GAME-PROJECT-MODE", (target / "AGENTS.md").read_text(encoding="utf-8"))

    def test_migrate_preserves_live_game_source_tree(self) -> None:
        with tempfile.TemporaryDirectory(prefix="game-mode-migrate-") as temporary:
            root = Path(temporary)
            target = root / "project"
            source = target / "Source/player.gd"
            asset = target / "Assets/hero.png"
            source.parent.mkdir(parents=True)
            asset.parent.mkdir(parents=True)
            source.write_text("extends CharacterBody2D\n", encoding="utf-8")
            asset.write_bytes(b"not-a-real-png-but-user-owned")
            config = write_config(root, source_roots=["Source/", "Assets/"])

            result = game_project.apply_local_game_project(target, config, "migrate", "standard")

            self.assertEqual(source.read_text(encoding="utf-8"), "extends CharacterBody2D\n")
            self.assertEqual(asset.read_bytes(), b"not-a-real-png-but-user-owned")
            self.assertFalse((target / "raw/Source/player.gd").exists())
            self.assertFalse((target / "raw/Assets/hero.png").exists())
            self.assertEqual(result["project_mode"], "game")
            self.assertFalse(result["project_mode_activation_pending"])
            self.assertFalse((target / "CLAUDE.md.wiki-proposed").exists())
            self.assertIn(
                "LLM-WIKI:GAME-PROJECT-MODE",
                (target / "CLAUDE.md").read_text(encoding="utf-8"),
            )

    def test_game_router_composes_with_existing_evidence_proposal(self) -> None:
        with tempfile.TemporaryDirectory(prefix="game-mode-router-") as temporary:
            target = Path(temporary)
            for relative in ("CLAUDE.md", "AGENTS.md", "wiki/CLAUDE.md"):
                path = target / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("# user router\n", encoding="utf-8")
                path.with_name(path.name + ".wiki-proposed").write_text(
                    "# user router\n\n<!-- LLM-WIKI:EVIDENCE-PROFILE -->\n",
                    encoding="utf-8",
                )

            proposals = game_project.install_game_router(target, propose_existing=True)

            self.assertEqual(len(proposals), 3)
            for relative in ("CLAUDE.md", "AGENTS.md", "wiki/CLAUDE.md"):
                current = (target / relative).read_text(encoding="utf-8")
                proposal_path = (target / relative).with_name(Path(relative).name + ".wiki-proposed")
                proposal = proposal_path.read_text(encoding="utf-8")
                self.assertNotIn("LLM-WIKI:GAME-PROJECT-MODE", current)
                self.assertIn("LLM-WIKI:EVIDENCE-PROFILE", proposal)
                self.assertIn("LLM-WIKI:GAME-PROJECT-MODE", proposal)

    def test_local_upgrade_preserves_user_game_docs_and_backs_up_game_skill(self) -> None:
        with tempfile.TemporaryDirectory(prefix="game-mode-upgrade-") as temporary:
            root = Path(temporary)
            target = root / "vault"
            config = write_config(root)
            game_project.apply_local_game_project(target, config, "new", "standard")
            model = target / "wiki/game/model.md"
            agent_skill = target / ".agents/skills/game-project/SKILL.md"
            model.write_text("# user-owned game model\n", encoding="utf-8")
            agent_skill.write_text("# user-modified game skill\n", encoding="utf-8")

            result = game_project.upgrade_game_from_local(target, config)

            self.assertTrue(result["ok"])
            self.assertEqual(result["project_mode_verification"]["status"], "pending")
            self.assertTrue(result["project_mode_activation_pending"])
            self.assertEqual(model.read_text(encoding="utf-8"), "# user-owned game model\n")
            proposal = model.with_name("model.md.wiki-proposed")
            self.assertTrue(proposal.is_file())
            self.assertIn(
                "Design Intent → Implementation State → Validation Evidence → Project Decision",
                proposal.read_text(encoding="utf-8"),
            )
            backup = Path(result["backup_dir"]) / ".agents/skills/game-project/SKILL.md"
            self.assertEqual(backup.read_text(encoding="utf-8"), "# user-modified game skill\n")
            self.assertIn("design_status", agent_skill.read_text(encoding="utf-8"))

    def test_remote_checkout_requires_game_overlay_before_target_mutation(self) -> None:
        with tempfile.TemporaryDirectory(prefix="game-mode-checkout-") as temporary:
            checkout = Path(temporary) / "checkout"
            checkout.mkdir()
            with self.assertRaisesRegex(RuntimeError, "lacks game project mode"):
                game_project.validate_game_checkout(checkout)

    def test_github_game_upgrade_rejects_legacy_checkout_before_target_mutation(self) -> None:
        with tempfile.TemporaryDirectory(prefix="game-mode-remote-legacy-") as temporary:
            root = Path(temporary)
            checkout = root / "legacy-checkout"
            checkout.mkdir()
            target = root / "target"
            config = root / "config.json"
            config.write_text("{}", encoding="utf-8")
            with mock.patch.object(
                game_project.wiki_upgrade,
                "resolve_latest_commit",
                return_value=("master", "a" * 40),
            ):
                with mock.patch.object(
                    game_project.wiki_upgrade,
                    "download_commit_archive",
                    return_value=b"archive",
                ):
                    with mock.patch.object(
                        game_project.wiki_upgrade,
                        "extract_checkout",
                        return_value=checkout,
                    ):
                        with mock.patch.object(game_project, "run_checkout_game_upgrade") as run_upgrade:
                            with self.assertRaisesRegex(RuntimeError, "lacks game project mode"):
                                game_project.upgrade_game_from_github(target, config)
                            run_upgrade.assert_not_called()
            self.assertFalse(target.exists())

    def test_config_rejects_non_string_source_roots(self) -> None:
        with self.assertRaisesRegex(ValueError, "source_roots"):
            game_project.validate_config(
                {"project_name": "X", "domain_summary": "Y", "source_roots": ["Game/", 3]},
                require_base=True,
            )


if __name__ == "__main__":
    unittest.main()
