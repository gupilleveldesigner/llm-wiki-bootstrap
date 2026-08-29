from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import bootstrap as wiki_bootstrap
import upgrade as wiki_upgrade
from game_project_contract import (
    GAME_ROUTER_MARKER,
    PROJECT_MODE,
    read_json_object,
    read_manifest,
    validate_config,
    validate_game_bundle,
    validate_game_checkout,
    write_upgrade_provenance,
)
from game_project_install import (
    backup_game_skills,
    ensure_backup_dir,
    install_game_overlay,
    install_game_router,
)


def apply_local_game_project(target: Path, config_path: Path, mode: str, profile: str | None = None) -> dict[str, Any]:
    validate_game_bundle()
    config = read_json_object(config_path)
    validate_config(config, require_base=mode in ("new", "migrate"))
    previous_manifest = read_manifest(target) if target.exists() else {}
    previous_project_mode = str(previous_manifest.get("project_mode", "knowledge"))
    router_paths = ("CLAUDE.md", "AGENTS.md", "wiki/CLAUDE.md")
    had_existing_router = target.exists() and any((target / relative).exists() for relative in router_paths)

    if mode == "upgrade":
        base_result = wiki_bootstrap.upgrade(target, config_path, profile)
        backup_dir = ensure_backup_dir(target, base_result)
        base_result["game_skill_backup"] = backup_game_skills(target, backup_dir)
    else:
        base_result = wiki_bootstrap.bootstrap(target, config_path, mode, profile)

    overlay_result = install_game_overlay(
        target,
        config,
        mode=mode,
        previous_project_mode=previous_project_mode,
        router_propose_existing=mode == "upgrade" or (mode == "migrate" and had_existing_router),
    )
    result = dict(base_result)
    result.update(overlay_result)
    if mode in ("migrate", "upgrade"):
        result["proposals"] = sorted(set(result.get("proposals", [])) | set(overlay_result["game_proposals"]))
    return result


def parse_result(stdout: str) -> dict[str, Any]:
    lines = [line.strip() for line in stdout.splitlines() if line.strip()]
    if not lines:
        raise RuntimeError("latest game project bootstrap produced no JSON result")
    try:
        result = json.loads(lines[-1])
    except json.JSONDecodeError as error:
        raise RuntimeError("latest game project bootstrap did not end with a JSON result") from error
    if not isinstance(result, dict):
        raise RuntimeError("latest game project bootstrap returned an unexpected result shape")
    return result


def run_checkout_game_upgrade(
    checkout: Path,
    target: Path,
    config: Path,
    profile: str | None,
) -> dict[str, Any]:
    command = [
        sys.executable,
        str(checkout / "scripts/game_project.py"),
        "--target",
        str(target),
        "--config",
        str(config),
        "--mode",
        "upgrade",
        "--source",
        "local",
    ]
    if profile:
        command.extend(("--profile", profile))
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    result = parse_result(completed.stdout)
    if completed.returncode != 0 or not result.get("ok"):
        detail = completed.stderr.strip()
        if detail:
            result.setdefault("stderr", detail)
    return result


def upgrade_game_from_github(target: Path, config: Path, profile: str | None = None) -> dict[str, Any]:
    # Resolve, download, and validate the exact remote checkout before mutating the target.
    branch, commit = wiki_upgrade.resolve_latest_commit(wiki_upgrade.OFFICIAL_REPOSITORY)
    archive = wiki_upgrade.download_commit_archive(wiki_upgrade.OFFICIAL_REPOSITORY, commit)
    with tempfile.TemporaryDirectory(prefix="llm-wiki-game-upgrade-") as temporary:
        checkout = wiki_upgrade.extract_checkout(archive, Path(temporary))
        validate_game_checkout(checkout)
        result = run_checkout_game_upgrade(checkout, target, config, profile)

    result.update(
        {
            "upgrade_source": "github",
            "bootstrap_repository": wiki_upgrade.OFFICIAL_REPOSITORY,
            "bootstrap_branch": branch,
            "bootstrap_commit": commit,
        }
    )
    if result.get("ok"):
        write_upgrade_provenance(
            target,
            repository=wiki_upgrade.OFFICIAL_REPOSITORY,
            branch=branch,
            commit=commit,
        )
    return result


def upgrade_game_from_local(target: Path, config: Path, profile: str | None = None) -> dict[str, Any]:
    result = apply_local_game_project(target, config, "upgrade", profile)
    result.update(
        {
            "upgrade_source": "local",
            "bootstrap_repository": None,
            "bootstrap_branch": None,
            "bootstrap_commit": None,
        }
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Install or upgrade the game project mode overlay while preserving the base LLM Wiki "
            "lifecycle and standard/evidence vault profile."
        )
    )
    parser.add_argument("--target", required=True, type=Path)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--mode", choices=("new", "migrate", "upgrade"), default="new")
    parser.add_argument("--profile", choices=("standard", "evidence"), default=None)
    parser.add_argument(
        "--source",
        choices=("github", "local"),
        default="github",
        help="For upgrade: github fetches the latest official commit; local uses the current bundle explicitly.",
    )
    args = parser.parse_args()

    try:
        if args.mode == "upgrade":
            if args.source == "github":
                result = upgrade_game_from_github(args.target, args.config, args.profile)
            else:
                result = upgrade_game_from_local(args.target, args.config, args.profile)
        else:
            result = apply_local_game_project(args.target, args.config, args.mode, args.profile)
    except Exception as error:
        result = {
            "ok": False,
            "mode": args.mode,
            "profile": args.profile,
            "project_mode": PROJECT_MODE,
            "upgrade_source": args.source if args.mode == "upgrade" else None,
            "error": str(error),
        }

    print(json.dumps(result, ensure_ascii=False))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
