from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))
from bootstrap import bootstrap  # noqa: E402


def write_config(root: Path) -> Path:
    path = root / "config.json"
    path.write_text(
        json.dumps({"project_name": "Evidence Runtime Probe", "domain_summary": "long conversation evidence"}),
        encoding="utf-8",
    )
    return path


def run_json(command: list[str], *, cwd: Path) -> tuple[subprocess.CompletedProcess[str], dict]:
    completed = subprocess.run(command, cwd=cwd, capture_output=True, text=True, check=False)
    payload = json.loads(completed.stdout) if completed.stdout.strip() else {}
    return completed, payload


class EvidenceRuntimeIntegrationTests(unittest.TestCase):
    def test_generated_vault_runs_installed_regressions_and_kb_selftest(self) -> None:
        with tempfile.TemporaryDirectory(prefix="bootstrap-installed-runtime-") as temporary:
            root = Path(temporary)
            target = root / "vault"
            bootstrap(target, write_config(root), "new", "evidence")

            category, category_result = run_json(
                [
                    sys.executable,
                    str(target / ".agents/skills/ingest/scripts/ingest_runtime.py"),
                    "category-audit",
                    "--root",
                    str(target),
                ],
                cwd=target,
            )
            self.assertEqual(category.returncode, 0, category.stdout + category.stderr)
            self.assertTrue(category_result["valid"])

            for skill in ("ingest", "lint", "query"):
                completed = subprocess.run(
                    [
                        sys.executable,
                        "-m",
                        "unittest",
                        "discover",
                        str(target / ".agents" / "skills" / skill / "tests"),
                        "-p",
                        "test_*.py",
                    ],
                    cwd=target,
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)

            completed, result = run_json([sys.executable, str(target / "tools/kb.py"), "selftest"], cwd=target)
            self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
            self.assertEqual(result["status"], "ok")

    def test_long_source_requires_eof_and_decision_is_queryable(self) -> None:
        with tempfile.TemporaryDirectory(prefix="bootstrap-eof-decision-") as temporary:
            root = Path(temporary)
            target = root / "vault"
            bootstrap(target, write_config(root), "new", "evidence")

            taxonomy_path = target / "wiki/taxonomy.json"
            taxonomy = json.loads(taxonomy_path.read_text(encoding="utf-8"))
            taxonomy["concepts"].append(
                {
                    "id": "verification",
                    "prefLabel": "검증",
                    "altLabel": ["verification"],
                    "scopeNote": "Evidence runtime integration verification.",
                    "broader": ["wiki-operations"],
                }
            )
            taxonomy_path.write_text(json.dumps(taxonomy, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

            raw_path = target / "raw/inbox/long-conversation.md"
            raw_lines = ["시작 일반 질문"] + [f"중간 관찰 {number}" for number in range(2, 330)]
            raw_lines[164] = "중간 핵심 검토"
            raw_lines.append("최종 결정은 범용 `2d-game-art` Skill v0.1 설계를 우선한다.")
            raw_path.write_text("\n".join(raw_lines) + "\n", encoding="utf-8")
            raw_hash = hashlib.sha256(raw_path.read_bytes()).hexdigest()

            project = target / "wiki/projects/probe.md"
            project.write_text(
                "---\n"
                "type: project\nstatus: active\ntopics:\n  - 검증\n"
                "sources:\n  - \"raw/inbox/long-conversation.md\"\n"
                "source_ids:\n  - \"RAW-PROBE-LONG-0001\"\n"
                "created: \"2026-08-27\"\nupdated: \"2026-08-27\"\n---\n\n# Probe project\n",
                encoding="utf-8",
            )
            decision = target / "wiki/decisions/DECISION-PROBE-0001.md"
            decision.write_text(
                "---\n"
                "type: decision\nid: \"DECISION-PROBE-0001\"\nstatus: PROPOSED\n"
                "statement: \"범용 2d-game-art Skill v0.1 설계를 우선한다.\"\n"
                "project: \"wiki/projects/probe.md\"\n"
                "sources:\n  - \"raw/inbox/long-conversation.md\"\n"
                "source_ids:\n  - \"RAW-PROBE-LONG-0001\"\n"
                "evidence:\n  - \"RAW-PROBE-LONG-0001 | recommends | lines 330-330 | 최종 결정은 범용 `2d-game-art` Skill v0.1 설계를 우선한다.\"\n"
                "next_actions:\n  - \"ACTION-PROBE-0001 | RAW-PROBE-LONG-0001 | lines 330-330 | v0.1 설계 계약을 작성한다. | 최종 결정은 범용 `2d-game-art` Skill v0.1 설계를 우선한다.\"\n"
                "chronology:\n  - \"2026-08-27 | proposed | RAW-PROBE-LONG-0001 | lines 330-330 | 최종 결정은 범용 `2d-game-art` Skill v0.1 설계를 우선한다.\"\n"
                "supersedes: []\nsuperseded_by: []\ntopics:\n  - 검증\n"
                "decided_at: \"2026-08-27\"\ncreated: \"2026-08-27\"\nupdated: \"2026-08-27\"\n"
                "---\n\n# Probe decision\n",
                encoding="utf-8",
            )
            valid_decision_text = decision.read_text(encoding="utf-8")

            source_path = target / "wiki/sources/long-conversation.md"

            def source_text(*, full: bool) -> str:
                evidence = (
                    "> [lines 1-1] 시작 일반 질문\n"
                    "> [lines 165-165] 중간 핵심 검토\n"
                    "> [lines 330-330] 최종 결정은 범용 `2d-game-art` Skill v0.1 설계를 우선한다."
                    if full
                    else "> [lines 1-1] 시작 일반 질문"
                )
                coverage = (
                    "- start | lines 1-100 | 일반 질문과 초기 맥락\n"
                    "- middle | lines 101-250 | 중간 검토와 주제 전개\n"
                    "- end | lines 251-330 | 최종 권고와 EOF 결정"
                    if full
                    else "- start | lines 1-100 | 일반 질문과 초기 맥락"
                )
                locator = "lines 330-330" if full else "lines 1-1"
                return (
                    "---\n"
                    "type: source\nid: \"RAW-PROBE-LONG-0001\"\nstatus: active\ntopics:\n  - 검증\n"
                    "sources:\n  - \"raw/inbox/long-conversation.md\"\n"
                    f"raw_sha256: \"{raw_hash}\"\n"
                    "source_type: llm_conversation\nprovider: test\nmodel: none\n"
                    "created_at: \"2026-08-27\"\ningested_at: \"2026-08-27\"\n"
                    "verification_status: source_integrity_verified\nstructurally_verified: true\nsemantic_status: reviewed\n"
                    "raw_line_count: 330\nepistemic_observation: medium\nepistemic_inference: medium\n"
                    "parent_sources: []\nindependence_group: probe\nvisibility: private\nexternal_llm_allowed: false\n"
                    "key_claims: 1\nentities: 1\nconcepts: 1\nreflected_docs: 2\nrelations: 2\n"
                    f"evidence_spans: {3 if full else 1}\ncoverage_spans: {3 if full else 1}\n"
                    "key_decisions: 1\nnext_actions: 1\nchronology_entries: 1\n"
                    "created: \"2026-08-27\"\nupdated: \"2026-08-27\"\n---\n\n"
                    "# Long conversation Source\n\n## 원본\n\n- [[raw/inbox/long-conversation.md]]\n\n"
                    "## 핵심 주장\n\n- 최종 권고는 2d-game-art v0.1 설계다.\n\n"
                    "## 엔티티\n\n- 사용자\n\n## 개념\n\n- EOF decision coverage\n\n"
                    "## 관계\n\n- [[decisions/DECISION-PROBE-0001]]\n- [[projects/probe]]\n\n"
                    f"## 의미 Coverage\n\n{coverage}\n\n"
                    f"## 핵심 결정\n\n- DECISION-PROBE-0001 | {locator} | 범용 2d-game-art v0.1 설계를 우선한다.\n\n"
                    f"## 다음 행동\n\n- ACTION-PROBE-0001 | {locator} | v0.1 설계 계약을 작성한다.\n\n"
                    f"## Chronology\n\n- STEP-PROBE-0001 | {locator} | 최종 권고가 제안됐다.\n\n"
                    f"## 근거\n\n{evidence}\n\n"
                    "## Wiki에 반영된 문서\n\n- [[decisions/DECISION-PROBE-0001]]\n- [[projects/probe]]\n"
                )

            source_path.write_text(source_text(full=False), encoding="utf-8")
            runtime = target / ".agents/skills/ingest/scripts/ingest_runtime.py"
            head, head_result = run_json(
                [sys.executable, str(runtime), "verify", "--root", str(target), "--changed-file", "wiki/sources/long-conversation.md"],
                cwd=target,
            )
            self.assertNotEqual(head.returncode, 0)
            self.assertEqual(head_result["coverage"]["semantic_partial"], 1)
            self.assertTrue(any("middle coverage" in error or "end coverage" in error for error in head_result["errors"]))

            source_path.write_text(source_text(full=True), encoding="utf-8")
            reviewed, reviewed_result = run_json(
                [sys.executable, str(runtime), "verify", "--root", str(target), "--changed-file", "wiki/sources/long-conversation.md"],
                cwd=target,
            )
            self.assertEqual(reviewed.returncode, 0, reviewed.stdout + reviewed.stderr)
            self.assertEqual(reviewed_result["coverage"]["semantic_reviewed"], 1)

            kb = target / "tools/kb.py"
            decision.write_text(
                valid_decision_text
                .replace(
                    "  - \"ACTION-PROBE-0001 | RAW-PROBE-LONG-0001 | lines 330-330 | v0.1 설계 계약을 작성한다. | 최종 결정은 범용 `2d-game-art` Skill v0.1 설계를 우선한다.\"",
                    "  - \"v0.1 설계 계약을 작성한다.\"",
                )
                .replace(
                    "  - \"2026-08-27 | proposed | RAW-PROBE-LONG-0001 | lines 330-330 | 최종 결정은 범용 `2d-game-art` Skill v0.1 설계를 우선한다.\"",
                    "  - \"2026-08-27 | proposed\"",
                ),
                encoding="utf-8",
            )
            invalid_decision = subprocess.run(
                [sys.executable, str(kb), "rebuild"],
                cwd=target,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertNotEqual(invalid_decision.returncode, 0)
            self.assertIn("next_actions", invalid_decision.stderr)
            self.assertIn("chronology", invalid_decision.stderr)
            decision.write_text(valid_decision_text, encoding="utf-8")

            claim_dir = target / "wiki/claims/probe"
            claim_dir.mkdir(parents=True)
            claim = claim_dir / "CLAIM-PROBE-0001.md"
            invalid_claim_text = (
                "---\n"
                "type: claim\nid: CLAIM-PROBE-0001\nstatus: OBSERVED\nconfidence: 1.0\n"
                "claim_kind: decision_recall\ntopics:\n  - 검증\n"
                "statement: \"최종 결정은 2d-game-art v0.1 설계다.\"\n"
                "sources:\n  - \"raw/inbox/long-conversation.md\"\n"
                "evidence:\n  - \"RAW-PROBE-LONG-0001 | supports | lines 329-329 | 최종 결정은 범용 `2d-game-art` Skill v0.1 설계를 우선한다.\"\n"
                "claim_relations: []\ncreated: \"2026-08-27\"\nupdated: \"2026-08-27\"\n"
                "---\n\n# Probe claim\n"
            )
            claim.write_text(invalid_claim_text, encoding="utf-8")
            invalid_claim = subprocess.run(
                [sys.executable, str(kb), "rebuild"],
                cwd=target,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertNotEqual(invalid_claim.returncode, 0)
            self.assertIn("Claim evidence", invalid_claim.stderr)
            claim.write_text(invalid_claim_text.replace("lines 329-329", "lines 330-330"), encoding="utf-8")

            rebuilt, rebuild_result = run_json([sys.executable, str(kb), "rebuild"], cwd=target)
            self.assertEqual(rebuilt.returncode, 0, rebuilt.stdout + rebuilt.stderr)
            self.assertEqual(rebuild_result["decisions"], 1)
            self.assertEqual(rebuild_result["claims"], 1)
            searched, search_result = run_json([sys.executable, str(kb), "search", "2d-game-art"], cwd=target)
            self.assertEqual(searched.returncode, 0, searched.stdout + searched.stderr)
            self.assertTrue(any(row["doc_id"] == "DECISION-PROBE-0001" for row in search_result["results"]))
            traced, trace_result = run_json([sys.executable, str(kb), "trace", "DECISION-PROBE-0001"], cwd=target)
            self.assertEqual(traced.returncode, 0, traced.stdout + traced.stderr)
            self.assertTrue(trace_result["decision"]["project"]["provenance_matches"])
            self.assertEqual(trace_result["decision"]["evidence"][0]["locator"], "lines 330-330")
            self.assertEqual(trace_result["decision"]["evidence"][0]["semantic_status"], "reviewed")
            self.assertEqual(trace_result["decision"]["evidence"][0]["integrity"], "ok")
            self.assertEqual(hashlib.sha256(raw_path.read_bytes()).hexdigest(), raw_hash)


if __name__ == "__main__":
    unittest.main()
