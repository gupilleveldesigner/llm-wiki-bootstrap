from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parents[2] / "assets/skills-bundle/agents-skills/wiki-audit/scripts"))
from wiki_audit import alignment_audit, codex_multi_agent_enabled, environment_audit  # noqa: E402


class WikiAuditTests(unittest.TestCase):
    def make_root(self) -> Path:
        root = Path(tempfile.mkdtemp(prefix="wiki-audit-"))
        (root / "raw").mkdir()
        (root / "wiki").mkdir()
        for host in (".agents", ".claude"):
            for skill in ("ingest", "query", "lint", "session-memory", "brief-tuner", "wiki-audit"):
                (root / host / "skills" / skill).mkdir(parents=True, exist_ok=True)
        (root / "wiki/taxonomy.json").write_text(json.dumps({"concepts": []}), encoding="utf-8")
        (root / ".graphifyignore").write_text(
            ".git/\n.agents/\n.claude/\n.session-memory/\nOutput/\ntemplates/\ninstructions/\n"
            "graphify-out/\nCLAUDE.md\nAGENTS.md\nREADME.md\nlog.md\nchangelog.md\nraw/CLAUDE.md\n"
            "wiki/CLAUDE.md\nwiki/index.md\nwiki/overview.md\nwiki/questions.md\nwiki/log.md\n"
            "wiki/taxonomy.json\nwiki/ingest-ledger.json\n",
            encoding="utf-8",
        )
        for path in (
            root / host / "skills" / skill / "SKILL.md"
            for host in (".agents", ".claude")
            for skill in ("ingest", "query", "lint", "session-memory", "brief-tuner", "wiki-audit")
        ):
            path.write_text("graphify install --platform codex $graphify /graphify --update multi_agent graphify codex install graphify claude install", encoding="utf-8")
        return root

    def test_environment_audit_detects_required_local_items(self) -> None:
        result = environment_audit(self.make_root())
        self.assertEqual(result["status"], "ok")

    def test_alignment_uses_remote_contract_without_network(self) -> None:
        root = self.make_root()
        remote = " ".join(
            [
                "graphify install --platform codex",
                "$graphify",
                "/graphify",
                "--update",
                ".graphifyignore",
                "multi_agent",
                "graphify codex install",
                "graphify claude install",
            ]
        )
        with patch("wiki_audit.fetch_readme", return_value=(remote, None)):
            result = alignment_audit(root)
        self.assertEqual(result["status"], "ok")

    def test_environment_audit_does_not_accept_commented_ignore_rules(self) -> None:
        root = self.make_root()
        ignore = root / ".graphifyignore"
        ignore.write_text("\n".join(f"# {line}" for line in (".agents/", ".claude/", ".session-memory/", "Output/", "instructions/", "graphify-out/", "wiki/index.md", "wiki/taxonomy.json", "wiki/ingest-ledger.json")), encoding="utf-8")
        remote = " ".join(
            [
                "graphify install --platform codex",
                "$graphify",
                "/graphify",
                "--update",
                ".graphifyignore",
                "multi_agent",
                "graphify codex install",
                "graphify claude install",
            ]
        )
        with patch("wiki_audit.fetch_readme", return_value=(remote, None)):
            result = alignment_audit(root)
        self.assertEqual(result["status"], "failed")

    def test_multi_agent_does_not_cross_toml_sections(self) -> None:
        self.assertFalse(codex_multi_agent_enabled("[features]\nmulti_agent = false\n[other]\nmulti_agent = true\n"))
        self.assertTrue(codex_multi_agent_enabled("[features]\nmulti_agent = true\n[other]\nvalue = 1\n"))


if __name__ == "__main__":
    unittest.main()
