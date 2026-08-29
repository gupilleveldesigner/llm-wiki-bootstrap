from __future__ import annotations

import io
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).parents[1]))
import upgrade  # noqa: E402


def make_archive(files: dict[str, str], root: str = "llm-wiki-bootstrap-deadbeef") -> bytes:
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        for relative, content in files.items():
            archive.writestr(f"{root}/{relative}", content)
    return stream.getvalue()


def valid_contract_files(bootstrap_script: str) -> dict[str, str]:
    return {
        "SKILL.md": "skill",
        "scripts/bootstrap.py": bootstrap_script,
        "scripts/template_render.py": "# template renderer",
        "assets/skills-bundle/agents-skills/ingest/scripts/semantic_contract.py": "# semantic contract",
        "assets/skills-bundle/agents-skills/ingest/scripts/stitch_explicit_links.py": "# structural stitch",
        "assets/skills-bundle/claude-adapters/.keep": "",
        "assets/profiles/evidence/docs/evidence-kb.md.template": "# Evidence KB",
        "assets/profiles/evidence/runtime/kb.py": "# KB runtime",
        "assets/profiles/evidence/templates/decision.md": "# Decision template",
    }


class LatestGitHubUpgradeTests(unittest.TestCase):
    def test_resolve_latest_commit_uses_default_branch(self) -> None:
        with mock.patch.object(
            upgrade,
            "_request_json",
            side_effect=[{"default_branch": "master"}, {"sha": "a" * 40}],
        ) as request_json:
            branch, sha = upgrade.resolve_latest_commit()

        self.assertEqual(branch, "master")
        self.assertEqual(sha, "a" * 40)
        self.assertIn("/repos/gupilleveldesigner/llm-wiki-bootstrap", request_json.call_args_list[0].args[0])
        self.assertTrue(request_json.call_args_list[1].args[0].endswith("/commits/master"))

    def test_extract_checkout_rejects_path_traversal(self) -> None:
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w") as archive:
            archive.writestr("../escape.txt", "no")
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(RuntimeError, "unsafe path"):
                upgrade.extract_checkout(stream.getvalue(), Path(temporary))

    def test_extract_checkout_requires_upgrade_contract_files(self) -> None:
        archive = make_archive({"SKILL.md": "x"})
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(RuntimeError, "incomplete"):
                upgrade.extract_checkout(archive, Path(temporary))

    def test_github_failure_happens_before_local_upgrade(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "vault"
            config = Path(temporary) / "config.json"
            config.write_text("{}", encoding="utf-8")
            with mock.patch.object(upgrade, "resolve_latest_commit", side_effect=RuntimeError("offline")):
                with mock.patch.object(upgrade, "run_local_upgrade") as run_local:
                    with self.assertRaisesRegex(RuntimeError, "offline"):
                        upgrade.upgrade_from_github(target, config)
                    run_local.assert_not_called()
            self.assertFalse(target.exists())

    def test_legacy_remote_bundle_is_rejected_before_target_mutation(self) -> None:
        legacy = make_archive(
            {
                "SKILL.md": "skill",
                "scripts/bootstrap.py": "print('legacy')",
                "assets/skills-bundle/agents-skills/.keep": "",
                "assets/skills-bundle/claude-adapters/.keep": "",
            }
        )
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "vault"
            config = Path(temporary) / "config.json"
            config.write_text("{}", encoding="utf-8")
            with mock.patch.object(upgrade, "resolve_latest_commit", return_value=("master", "d" * 40)):
                with mock.patch.object(upgrade, "download_commit_archive", return_value=legacy):
                    with self.assertRaisesRegex(RuntimeError, "incomplete"):
                        upgrade.upgrade_from_github(target, config, "evidence")
            self.assertFalse(target.exists())

    def test_success_records_exact_github_commit(self) -> None:
        required = valid_contract_files("print('stub')")
        archive = make_archive(required)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / "vault"
            target.mkdir()
            (target / ".llm-wiki.json").write_text(json.dumps({"profile": "standard"}), encoding="utf-8")
            config = root / "config.json"
            config.write_text("{}", encoding="utf-8")

            with mock.patch.object(upgrade, "resolve_latest_commit", return_value=("master", "b" * 40)):
                with mock.patch.object(upgrade, "download_commit_archive", return_value=archive):
                    with mock.patch.object(upgrade, "run_local_upgrade", return_value={"ok": True, "mode": "upgrade"}):
                        result = upgrade.upgrade_from_github(target, config)

            self.assertTrue(result["ok"])
            self.assertEqual(result["bootstrap_commit"], "b" * 40)
            manifest = json.loads((target / ".llm-wiki.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["last_upgrade"]["source"], "github")
            self.assertEqual(manifest["last_upgrade"]["commit"], "b" * 40)

    def test_remote_checkout_executes_downloaded_bootstrap(self) -> None:
        bootstrap_script = """import argparse, json
from pathlib import Path
p=argparse.ArgumentParser(); p.add_argument('--target'); p.add_argument('--config'); p.add_argument('--mode'); p.add_argument('--profile', default=None); a=p.parse_args()
t=Path(a.target); t.mkdir(parents=True, exist_ok=True); (t/'.llm-wiki.json').write_text(json.dumps({'profile': a.profile or 'standard'}), encoding='utf-8')
print(json.dumps({'ok': True, 'mode': a.mode, 'profile': a.profile or 'standard', 'backup_dir': 'fake-backup'}))
"""
        archive = make_archive(valid_contract_files(bootstrap_script))
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / "vault"
            config = root / "config.json"
            config.write_text("{}", encoding="utf-8")
            with mock.patch.object(upgrade, "resolve_latest_commit", return_value=("master", "c" * 40)):
                with mock.patch.object(upgrade, "download_commit_archive", return_value=archive):
                    result = upgrade.upgrade_from_github(target, config, "evidence")

            self.assertTrue(result["ok"])
            self.assertEqual(result["profile"], "evidence")
            self.assertEqual(result["bootstrap_commit"], "c" * 40)
            manifest = json.loads((target / ".llm-wiki.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["last_upgrade"]["commit"], "c" * 40)


if __name__ == "__main__":
    unittest.main()
