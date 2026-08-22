#!/usr/bin/env python3
"""Read-only audit for LLM Wiki skill/environment/Graphify alignment."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPT_ROOT = Path(__file__).resolve().parent
if str(SCRIPT_ROOT.parent.parent / "ingest" / "scripts") not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT.parent.parent / "ingest" / "scripts"))

from find_uningested import resolve_wiki_root  # noqa: E402


GRAPHIFY_README_URL = "https://raw.githubusercontent.com/Graphify-Labs/graphify/v8/docs/translations/README.ko-KR.md"
CONTRACT = {
    "codex_platform_install": "graphify install --platform codex",
    "codex_trigger": "$graphify",
    "claude_trigger": "/graphify",
    "update": "--update",
    "ignore": ".graphifyignore",
    "multi_agent": "multi_agent",
    "codex_always_on": "graphify codex install",
    "claude_always_on": "graphify claude install",
}
SKILLS = ("ingest", "query", "lint", "session-memory", "brief-tuner", "wiki-audit")
REQUIRED_GRAPHIFYIGNORE = (
    ".git/",
    ".agents/",
    ".claude/",
    ".session-memory/",
    "Output/",
    "templates/",
    "instructions/",
    "graphify-out/",
    "CLAUDE.md",
    "AGENTS.md",
    "README.md",
    "log.md",
    "changelog.md",
    "raw/CLAUDE.md",
    "wiki/CLAUDE.md",
    "wiki/index.md",
    "wiki/overview.md",
    "wiki/questions.md",
    "wiki/log.md",
    "wiki/taxonomy.json",
    "wiki/ingest-ledger.json",
)


def active_ignore_rules(text: str) -> set[str]:
    rules = set()
    for line in text.splitlines():
        rule = line.split("#", 1)[0].strip()
        if rule:
            rules.add(rule)
    return rules


def codex_multi_agent_enabled(config_body: str) -> bool:
    in_features = False
    for raw_line in config_body.splitlines():
        line = raw_line.strip()
        if not line or line.startswith(("#", ";")):
            continue
        section = re.fullmatch(r"\[([^\]]+)\]", line)
        if section:
            in_features = section.group(1).strip() == "features"
            continue
        if in_features:
            match = re.fullmatch(r"multi_agent\s*=\s*(true|false)\s*(?:#.*)?", line, flags=re.IGNORECASE)
            if match:
                return match.group(1).lower() == "true"
    return False


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def command_version(command: str) -> str | None:
    executable = shutil.which(command)
    if not executable:
        return None
    try:
        completed = subprocess.run([executable, "--version"], capture_output=True, text=True, check=False, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return None
    output = (completed.stdout or completed.stderr).strip()
    return output or None


def path_state(path: Path) -> dict[str, Any]:
    return {"path": str(path), "exists": path.exists(), "is_file": path.is_file(), "sha256": sha256(path) if path.is_file() else None}


def environment_audit(root: Path) -> dict[str, Any]:
    home = Path.home()
    skill_checks = {
        host: {skill: path_state(root / host / "skills" / skill / "SKILL.md") for skill in SKILLS}
        for host in (".agents", ".claude")
    }
    checks = {
        "skills": skill_checks,
        "root": path_state(root),
        "python": {"executable": sys.executable, "version": sys.version.split()[0]},
        "taxonomy": path_state(root / "wiki/taxonomy.json"),
        "graphifyignore": path_state(root / ".graphifyignore"),
        "graphify_cli": {"executable": shutil.which("graphify"), "version": command_version("graphify")},
        "codex_graphify_skill": path_state(home / ".codex/skills/graphify/SKILL.md"),
        "claude_graphify_skill": path_state(home / ".claude/skills/graphify/SKILL.md"),
        "codex_multi_agent_config": path_state(home / ".codex/config.toml"),
        "codex_hook": path_state(home / ".codex/hooks.json"),
    }
    errors: list[str] = []
    warnings: list[str] = []
    for host, skills in skill_checks.items():
        for skill, state in skills.items():
            if not state["exists"]:
                errors.append(f"missing installed skill: {host}/skills/{skill}")
    for key in ("root", "taxonomy", "graphifyignore"):
        if not checks[key]["exists"]:
            errors.append(f"missing required environment item: {key}")
    config_text = checks["codex_multi_agent_config"]["path"]
    config_path = Path(config_text)
    config_body = config_path.read_text(encoding="utf-8-sig", errors="replace") if config_path.is_file() else ""
    checks["codex_multi_agent_config"]["multi_agent_true"] = codex_multi_agent_enabled(config_body)
    if not checks["codex_multi_agent_config"]["multi_agent_true"]:
        warnings.append("Codex multi_agent=true is not enabled; Graphify can run sequentially but not in parallel.")
    if not checks["codex_hook"]["exists"]:
        warnings.append("Codex Graphify always-on hook is not installed; explicit $graphify still works.")
    return {"status": "ok" if not errors else "failed", "checks": checks, "warnings": warnings, "errors": errors}


def fetch_readme(offline: bool) -> tuple[str | None, str | None]:
    if offline:
        return None, "offline mode"
    try:
        request = urllib.request.Request(GRAPHIFY_README_URL, headers={"User-Agent": "llm-wiki-bootstrap/wiki-audit"})
        with urllib.request.urlopen(request, timeout=15) as response:
            return response.read().decode("utf-8"), None
    except (OSError, UnicodeDecodeError) as error:
        return None, str(error)


def alignment_audit(root: Path, offline: bool = False) -> dict[str, Any]:
    readme, fetch_error = fetch_readme(offline)
    local_paths = [
        root / "AGENTS.md",
        root / "CLAUDE.md",
        root / ".agents/skills/ingest/SKILL.md",
        root / ".claude/skills/ingest/SKILL.md",
        root / "instructions/wiki-operations.md",
        root / ".graphifyignore",
        Path.home() / ".codex/config.toml",
    ]
    local = "\n".join(path.read_text(encoding="utf-8-sig", errors="replace") for path in local_paths if path.is_file())
    errors: list[str] = []
    checks: dict[str, Any] = {}
    if readme is None:
        return {"status": "unknown", "source": GRAPHIFY_README_URL, "fetched_at": datetime.now(timezone.utc).isoformat(), "fetch_error": fetch_error, "checks": checks, "warnings": ["Latest Graphify README could not be fetched; alignment is unknown."], "errors": []}
    for name, marker in CONTRACT.items():
        remote_has = marker in readme
        if name == "ignore":
            ignore_path = root / ".graphifyignore"
            ignore_text = ignore_path.read_text(encoding="utf-8-sig", errors="replace") if ignore_path.is_file() else ""
            active_rules = active_ignore_rules(ignore_text)
            local_has = all(required in active_rules for required in REQUIRED_GRAPHIFYIGNORE)
        else:
            local_has = marker in local
        checks[name] = {"remote": remote_has, "local": local_has}
        if remote_has and not local_has:
            errors.append(f"local skill is missing Graphify contract marker: {marker}")
    runtime = root / ".agents/skills/ingest/scripts/ingest_runtime.py"
    runtime_text = runtime.read_text(encoding="utf-8-sig", errors="replace") if runtime.is_file() else ""
    if re.search(r"run_command\(\[[^\]]*graphify", runtime_text, flags=re.IGNORECASE | re.DOTALL):
        errors.append("ingest runtime still directly executes a Graphify subprocess")
    return {
        "status": "ok" if not errors else "failed",
        "source": GRAPHIFY_README_URL,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "readme_sha256": hashlib.sha256(readme.encode("utf-8")).hexdigest(),
        "checks": checks,
        "warnings": [],
        "errors": errors,
    }


def audit(root: Path, *, offline: bool = False) -> dict[str, Any]:
    environment = environment_audit(root)
    alignment = alignment_audit(root, offline=offline)
    errors = [*environment["errors"], *alignment["errors"]]
    warnings = [*environment.get("warnings", []), *alignment.get("warnings", [])]
    status = "unknown" if alignment["status"] == "unknown" and not environment["errors"] else ("ok" if not errors else "failed")
    return {"status": status, "root": str(root), "environment": environment, "graphify_alignment": alignment, "warnings": warnings, "errors": errors, "exit_code": 0 if status == "ok" else 2}


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit LLM Wiki environment and Graphify alignment")
    parser.add_argument("command", choices=("environment", "alignment", "all"))
    parser.add_argument("--root", default=None)
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        root = resolve_wiki_root(args.root)
    except ValueError as error:
        parser.error(str(error))
    result = environment_audit(root) if args.command == "environment" else alignment_audit(root, args.offline) if args.command == "alignment" else audit(root, offline=args.offline)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    return int(result.get("exit_code", 0)) if "exit_code" in result else (0 if result.get("status") == "ok" else 2)


if __name__ == "__main__":
    raise SystemExit(main())
