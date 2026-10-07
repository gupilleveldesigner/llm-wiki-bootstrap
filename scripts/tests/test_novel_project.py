from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).parents[1]))
import novel_project  # noqa: E402
import upgrade  # noqa: E402

REPO = Path(__file__).resolve().parents[2]


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def config(root: Path, **values: object) -> Path:
    path = root / "config.json"
    write(path, json.dumps({"project_name": '달의 "기록"', "domain_summary": "소설 집필", "novel_title": '달의 "기록"',
                           "genre": "판타지", **values}, ensure_ascii=False))
    return path


class NovelInstallationTests(unittest.TestCase):
    def test_new_supports_both_profiles_and_escaped_titles(self) -> None:
        for profile in ("standard", "evidence"):
            with self.subTest(profile=profile), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                target = root / "novel"
                result = novel_project.run_local_novel_project(target, config(root), "new", profile)
                self.assertTrue(result["ok"])
                self.assertFalse(result["project_mode_activation_pending"])
                self.assertTrue(result["post_apply_verification"]["ok"])
                self.assertEqual(result["verification"]["novel_status"]["summary"]["errors"], 0)
                self.assertEqual(len(list((target / "templates/novel").glob("*.md"))), 10)
                manifest = json.loads((target / ".llm-wiki.json").read_text(encoding="utf-8"))
                self.assertEqual(manifest["project_mode"], "novel")
                self.assertEqual(manifest["profile"], profile)
                self.assertIn('title: "달의 \\"기록\\""', (target / "wiki/novel/index.md").read_text(encoding="utf-8"))
                for relative in ("AGENTS.md", "CLAUDE.md", "wiki/CLAUDE.md", "wiki/index.md"):
                    self.assertIn(novel_project.ROUTER_MARKER, (target / relative).read_text(encoding="utf-8"))
                self.assertTrue((target / ".claude/skills/novel-project/SKILL.md").is_file())

    def test_dry_run_preserves_existing_files_and_does_not_create_missing_parents(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            cfg = config(root)
            target = root / "missing/parent/novel"
            result = novel_project.run_local_novel_project(target, cfg, "new", dry_run=True)
            self.assertFalse(target.parent.exists())
            self.assertFalse(result["mutation_started"])
            self.assertTrue(result["write_plan"]["changes"])
            existing = root / "existing"
            write(existing / "draft.md", "Original manuscript\n")
            before = novel_project.snapshot(existing)
            novel_project.run_local_novel_project(existing, cfg, "migrate", dry_run=True)
            self.assertEqual(novel_project.snapshot(existing), before)
            self.assertFalse(list(root.glob(".llm-wiki-novel-*")))

    def test_migrate_preserves_originals_and_never_executes_a_colliding_runtime(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / "novel"
            originals = {"raw/novel/imports/old.txt": "original", "manuscripts/novel/drafts/current.md": "draft",
                         "wiki/novel/model.md": "my model", "AGENTS.md": "my router",
                         "tools/novel_check.py": "raise RuntimeError('user runtime must not execute')\n",
                         "tools/novel_check.py.wiki-proposed": "my earlier proposal"}
            for path, content in originals.items():
                write(target / path, content)
            result = novel_project.run_local_novel_project(target, config(root), "migrate")
            self.assertTrue(result["project_mode_activation_pending"])
            for path, content in originals.items():
                self.assertEqual((target / path).read_text(encoding="utf-8"), content)
            self.assertIn("tools/novel_check.py.wiki-proposed.1", result["novel_proposals"])
            self.assertTrue((Path(result["rollback_backup"]) / "raw/novel/imports/old.txt").is_file())

    def test_upgrade_preserves_metadata_documents_raw_and_manuscripts_and_backs_up_runtime(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / "novel"
            cfg = config(root)
            novel_project.run_local_novel_project(target, cfg, "new")
            write(target / "tools/novel_check.py", "# customized runtime\n")
            write(target / "wiki/novel/model.md", "# author model\n")
            write(target / "raw/novel/imports/book.md", "original")
            write(target / "manuscripts/novel/drafts/chapter.md", "author draft")
            write(cfg, "{}")
            result = novel_project.run_local_novel_project(target, cfg, "upgrade")
            self.assertEqual(result["novel_project"]["genre"], "판타지")
            self.assertEqual(result["novel_project"]["novel_title"], '달의 "기록"')
            self.assertEqual((target / "wiki/novel/model.md").read_text(encoding="utf-8"), "# author model\n")
            self.assertEqual((target / "raw/novel/imports/book.md").read_text(encoding="utf-8"), "original")
            self.assertEqual((target / "manuscripts/novel/drafts/chapter.md").read_text(encoding="utf-8"), "author draft")
            backup = Path(result["novel_backup_dir"]) / "tools/novel_check.py"
            self.assertEqual(backup.read_text(encoding="utf-8"), "# customized runtime\n")
            self.assertIn("wiki/novel/model.md.wiki-proposed", result["novel_proposals"])
            self.assertEqual((target / "AGENTS.md").read_text(encoding="utf-8").count(novel_project.ROUTER_MARKER), 1)

    def test_unadopted_runtime_and_previous_base_proposals_survive_later_upgrades(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / "novel"
            cfg = config(root)
            write(target / "tools/novel_check.py", "# foreign runtime\n")
            novel_project.run_local_novel_project(target, cfg, "migrate")
            write(target / "wiki/taxonomy.json", '{"user": true}\n')
            write(target / "wiki/taxonomy.json.wiki-proposed", "my previous taxonomy proposal\n")
            result = novel_project.run_local_novel_project(target, cfg, "upgrade")
            self.assertEqual((target / "tools/novel_check.py").read_text(encoding="utf-8"), "# foreign runtime\n")
            self.assertTrue(result["project_mode_activation_pending"])
            self.assertEqual((target / "wiki/taxonomy.json.wiki-proposed").read_text(encoding="utf-8"), "my previous taxonomy proposal\n")
            self.assertIn("wiki/taxonomy.json.wiki-proposed.1", result["proposals"])

    def test_invalid_config_and_mode_contracts_fail_before_mutation(self) -> None:
        invalids = [{"genre": []}, {"novel_title": False}, {"project_mode": "game"}]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / "novel"
            write(target / "draft.txt", "keep")
            before = novel_project.snapshot(target)
            for invalid in invalids:
                with self.subTest(config=invalid), self.assertRaises(ValueError):
                    novel_project.run_local_novel_project(target, config(root, **invalid), "migrate")
                self.assertEqual(novel_project.snapshot(target), before)
            self.assertFalse(list(root.glob(".llm-wiki-novel-*")))

    def test_game_and_future_novel_modes_are_not_replaced(self) -> None:
        for manifest in ({"project_mode": "game"}, {"project_mode": "novel", "project_mode_version": 2},
                         {"project_mode": "novel", "project_mode_version": True}):
            with self.subTest(manifest=manifest), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                target = root / "vault"
                write(target / ".llm-wiki.json", json.dumps(manifest))
                (target / "raw").mkdir()
                (target / "wiki").mkdir()
                before = novel_project.snapshot(target)
                with self.assertRaises(ValueError):
                    novel_project.run_local_novel_project(target, config(root), "upgrade")
                self.assertEqual(novel_project.snapshot(target), before)

    def test_profile_downgrade_is_rejected_before_staging(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / "vault"
            cfg = config(root)
            novel_project.run_local_novel_project(target, cfg, "new", "evidence")
            before = novel_project.snapshot(target)
            with self.assertRaisesRegex(ValueError, "downgrade"):
                novel_project.run_local_novel_project(target, cfg, "upgrade", "standard")
            self.assertEqual(novel_project.snapshot(target), before)

    def test_symlink_target_ancestor_and_nested_links_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            real = root / "real"
            real.mkdir()
            link = root / "linked"
            try:
                link.symlink_to(real, target_is_directory=True)
            except OSError as error:
                self.skipTest(str(error))
            cfg = config(root)
            for target in (link, link / "child"):
                with self.subTest(path=target), self.assertRaisesRegex(ValueError, "symlink"):
                    novel_project.run_local_novel_project(target, cfg, "migrate")
            nested = root / "novel"
            nested.mkdir()
            (nested / "manuscripts").symlink_to(real, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, "symlink"):
                novel_project.run_local_novel_project(nested, cfg, "migrate")
            self.assertEqual(list(real.iterdir()), [])

    def test_post_apply_failure_restores_the_original_vault(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / "novel"
            write(target / "draft.txt", "original")
            cfg = config(root)
            before = novel_project.snapshot(target)
            actual_verify = novel_project.verify_installation

            def verify(path: Path) -> dict:
                return {"ok": False, "errors": ["injected final failure"]} if path == target else actual_verify(path)

            with mock.patch.object(novel_project, "verify_installation", side_effect=verify):
                with self.assertRaisesRegex(RuntimeError, "post-apply"):
                    novel_project.run_local_novel_project(target, cfg, "migrate")
            self.assertEqual(novel_project.snapshot(target), before)
            self.assertFalse(list(root.glob(".llm-wiki-novel-*")))

    def test_staging_collision_preserves_the_original_folder(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / "vault"
            (target / "tools/novel_check.py").mkdir(parents=True)
            write(target / "tools/novel_check.py/note.md", "keep")
            before = novel_project.snapshot(target)
            with self.assertRaisesRegex(ValueError, "collides"):
                novel_project.run_local_novel_project(target, config(root), "migrate")
            self.assertEqual(novel_project.snapshot(target), before)
            self.assertFalse(list(root.glob(".llm-wiki-novel-*")))

    def test_concurrent_change_is_preserved_and_installation_is_not_applied(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / "vault"
            write(target / "draft.txt", "original")
            actual_verify = novel_project.verify_installation

            def verify(path: Path) -> dict:
                result = actual_verify(path)
                write(target / "draft.txt", "new author edit")
                return result

            with mock.patch.object(novel_project, "verify_installation", side_effect=verify):
                with self.assertRaisesRegex(RuntimeError, "changed during staging"):
                    novel_project.run_local_novel_project(target, config(root), "migrate")
            self.assertEqual((target / "draft.txt").read_text(encoding="utf-8"), "new author edit")
            self.assertFalse((target / ".llm-wiki.json").exists())

    def test_bootstrap_cli_routes_explicit_and_config_selected_novel_mode(self) -> None:
        for explicit in (False, True):
            with self.subTest(explicit=explicit), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                target = root / "vault"
                cfg = config(root, **({} if explicit else {"project_mode": "novel"}))
                command = [sys.executable, str(REPO / "scripts/bootstrap.py"), "--target", str(target), "--config", str(cfg)]
                if explicit:
                    command.extend(("--project-mode", "novel"))
                completed = subprocess.run(command, capture_output=True, text=True, encoding="utf-8",
                                           env={**os.environ, "PYTHONIOENCODING": "ascii"})
                self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
                self.assertEqual(json.loads(completed.stdout)["project_mode"], "novel")
                self.assertEqual(json.loads(completed.stdout)["novel_project"]["genre"], "판타지")

    def test_generic_local_upgrade_refreshes_the_novel_runtime(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / "vault"
            cfg = config(root)
            novel_project.run_local_novel_project(target, cfg, "new")
            write(target / "tools/novel_check.py", "# old runtime")
            result = upgrade.upgrade_from_local_bundle(target, cfg)
            self.assertTrue(result["ok"])
            self.assertEqual(result["project_mode"], "novel")
            self.assertIn("NOVEL_RUNTIME_VERSION = 1", (target / "tools/novel_check.py").read_text(encoding="utf-8"))

    def test_online_failure_and_missing_remote_contract_do_not_mutate_the_vault(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / "vault"
            cfg = config(root)
            novel_project.run_local_novel_project(target, cfg, "new")
            before = novel_project.snapshot(target)
            with mock.patch.object(upgrade, "resolve_latest_commit", side_effect=RuntimeError("offline")):
                with self.assertRaisesRegex(RuntimeError, "offline"):
                    upgrade.upgrade_from_github(target, cfg)
            with self.assertRaisesRegex(RuntimeError, "lacks Novel"):
                upgrade.run_local_upgrade(root / "old-checkout", target, cfg, None)
            self.assertEqual(novel_project.snapshot(target), before)

    def test_exact_commit_remote_upgrade_and_remote_dry_run(self) -> None:
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w") as archive:
            for relative in ("SKILL.md", "scripts", "assets"):
                path = REPO / relative
                files = path.rglob("*") if path.is_dir() else [path]
                for file in files:
                    if file.is_file() and "__pycache__" not in file.parts and file.suffix != ".pyc":
                        archive.write(file, "bundle/" + file.relative_to(REPO).as_posix())
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / "vault"
            cfg = config(root)
            novel_project.run_local_novel_project(target, cfg, "new")
            before = novel_project.snapshot(target)
            with mock.patch.object(upgrade, "resolve_latest_commit", return_value=("master", "a" * 40)), \
                 mock.patch.object(upgrade, "download_commit_archive", return_value=stream.getvalue()):
                dry = novel_project.upgrade_novel_from_github(target, cfg, dry_run=True)
                self.assertTrue(dry["dry_run"])
                self.assertEqual(novel_project.snapshot(target), before)
                result = novel_project.upgrade_novel_from_github(target, cfg)
            self.assertEqual(result["bootstrap_commit"], "a" * 40)
            manifest = json.loads((target / ".llm-wiki.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["last_upgrade"]["commit"], "a" * 40)
            self.assertEqual(manifest["last_upgrade"]["source"], "github")


if __name__ == "__main__":
    unittest.main()
