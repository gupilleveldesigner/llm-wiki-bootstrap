from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

import bootstrap as wiki_bootstrap
import upgrade as wiki_upgrade
from novel_project_contract import (
    ASSETS, DIRECTORIES, PROJECT_MODE_VERSION, ROUTER_MARKER, RUNTIME_SOURCE,
    read_config, rendered_assets, resolve_metadata,
    router_block, validate_novel_checkout,
)


def safe_target(path: Path) -> Path:
    # Resolve only after checking the supplied path and ancestors for symlinks.
    target = Path(os.path.abspath(path.expanduser()))
    if target == target.parent:
        raise ValueError("a filesystem root cannot be a Novel vault")
    for parent in (target, *target.parents):
        if parent.is_symlink():
            raise ValueError(f"Novel vault path contains a symlink: {parent}")
    if target.exists() and not target.is_dir():
        raise ValueError("Novel target must be a directory")
    wiki_bootstrap.assert_symlink_safe(target)
    return target


def snapshot(target: Path) -> dict[str, str]:
    wiki_bootstrap.assert_symlink_safe(target)
    entries: dict[str, str] = {}
    if not target.exists():
        return entries
    for path in sorted(target.rglob("*")):
        relative = path.relative_to(target).as_posix()
        if path.is_dir():
            entries[relative] = "directory"
        elif path.is_file():
            digest = hashlib.sha256()
            with path.open("rb") as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(chunk)
            entries[relative] = digest.hexdigest()
        else:
            raise ValueError(f"unsupported filesystem entry: {relative}")
    return entries


def base_mode(target: Path, mode: str) -> str:
    if mode not in ("new", "migrate", "upgrade"):
        raise ValueError(f"unsupported lifecycle mode: {mode}")
    nonempty = target.exists() and any(target.iterdir())
    is_wiki = (target / "raw").is_dir() and (target / "wiki").is_dir()
    if mode == "new" and nonempty:
        raise ValueError("new requires an absent or empty Novel vault")
    if mode == "upgrade" and not is_wiki:
        raise ValueError("upgrade requires an existing LLM Wiki")
    if is_wiki:
        return "upgrade"
    if (target / ".llm-wiki.json").exists():
        raise ValueError("Wiki manifest exists without raw/ and wiki/; repair it before migration")
    return "migrate" if nonempty else "new"


def propose(root: Path, relative: str, content: str) -> str:
    destination = root / relative
    number = 0
    while True:
        suffix = ".wiki-proposed" + (f".{number}" if number else "")
        proposal = destination.with_name(destination.name + suffix)
        if not proposal.exists():
            wiki_bootstrap.write_text(proposal, content)
            return proposal.relative_to(root).as_posix()
        if proposal.is_file() and proposal.read_bytes() == content.encode("utf-8"):
            return proposal.relative_to(root).as_posix()
        number += 1


def install_overlay(stage: Path, config: dict[str, Any], previous: dict[str, Any],
                    original_files: dict[str, str]) -> dict[str, Any]:
    metadata = resolve_metadata(config, previous)
    base_manifest = wiki_bootstrap.read_manifest(stage) or {}
    replacements = {"{{PROJECT_NAME}}": base_manifest["project_name"],
                    "{{DOMAIN_SUMMARY}}": config.get("domain_summary", base_manifest["project_name"]),
                    "{{TODAY}}": datetime.now().strftime("%Y-%m-%d"),
                    **wiki_bootstrap.profile_replacements(base_manifest["profile"])}
    # Legacy raw/wiki vaults may lack routers. Seed only missing base documents.
    for source, relative, render in wiki_bootstrap.BASE_DOCS:
        if not (stage / relative).exists():
            content = (wiki_bootstrap.render_asset(source, replacements) if render
                       else (ASSETS / "docs" / source).read_text(encoding="utf-8"))
            wiki_bootstrap.write_text(stage / relative, content)
    for directory in DIRECTORIES:
        (stage / directory).mkdir(parents=True, exist_ok=True)
    proposals: list[str] = []
    refreshed: list[str] = []
    backup_dir: Path | None = None
    for relative, content, managed in rendered_assets(metadata):
        path = stage / relative
        if path.exists() and not path.is_file():
            raise ValueError(f"Novel asset collides with a directory: {relative}")
        if path.exists() and path.read_bytes() != content.encode("utf-8"):
            if managed and relative in previous.get("novel_managed_assets", []):
                if backup_dir is None:
                    backup_dir = stage / ".wiki-upgrade-bak" / ("novel-" + datetime.now().strftime("%Y%m%d-%H%M%S-%f"))
                backup = backup_dir / relative
                backup.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, backup)
            else:
                proposals.append(propose(stage, relative, content))
                continue
        wiki_bootstrap.write_text(path, content)
        if managed:
            refreshed.append(relative)
    for relative in ("AGENTS.md", "CLAUDE.md", "wiki/CLAUDE.md", "wiki/index.md"):
        path = stage / relative
        content = path.read_text(encoding="utf-8")
        if ROUTER_MARKER in content:
            continue
        addition = (f"\n\n{ROUTER_MARKER}\n## 소설 프로젝트\n\n- [[novel/index|소설 설정·구성·원고 색인]]\n"
                    if relative == "wiki/index.md" else router_block(wiki=relative.startswith("wiki/")))
        if relative in original_files:
            proposals.append(propose(stage, relative, content + addition))
        else:
            wiki_bootstrap.write_text(path, content + addition)
    manifest = wiki_bootstrap.read_manifest(stage) or {}
    manifest.update(project_mode="novel", project_mode_version=PROJECT_MODE_VERSION,
                    novel_project=metadata, novel_managed_assets=refreshed,
                    project_mode_activation_pending=bool(proposals))
    wiki_bootstrap.write_text(stage / ".llm-wiki.json", json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    return {"novel_project": metadata, "novel_proposals": proposals,
            "project_mode_activation_pending": bool(proposals), "novel_refreshed_assets": refreshed,
            "novel_backup_dir": str(backup_dir) if backup_dir else None}


def verify_installation(root: Path) -> dict[str, Any]:
    manifest = wiki_bootstrap.read_manifest(root) or {}
    errors: list[str] = []
    if manifest.get("project_mode") != "novel" or manifest.get("project_mode_version") != PROJECT_MODE_VERSION:
        errors.append("Novel manifest contract is missing")
    for directory in DIRECTORIES:
        if not (root / directory).is_dir():
            errors.append(f"missing Novel directory: {directory}")
    for relative, _, _ in rendered_assets(manifest.get("novel_project", {})):
        if not (root / relative).is_file():
            errors.append(f"missing Novel asset: {relative}")
    profile = wiki_bootstrap.verify_profile_installation(root, manifest.get("profile", "standard"))
    errors.extend(profile.get("errors", []))
    # The bundle is trusted; never execute a user-owned colliding runtime during migration.
    completed = subprocess.run([sys.executable, str(ASSETS / RUNTIME_SOURCE), "--root", str(root), "status"],
                               capture_output=True, text=True, encoding="utf-8", check=False)
    status: dict[str, Any] = {}
    try:
        status = json.loads(completed.stdout)
    except json.JSONDecodeError:
        errors.append("Novel runtime did not return JSON")
    if completed.returncode or not status.get("ok"):
        errors.append("Novel runtime status failed")
    return {"ok": not errors, "errors": errors, "novel_status": status, "profile": profile}


def remap(value: Any, stage: Path, target: Path) -> Any:
    if isinstance(value, str):
        return value.replace(str(stage), str(target))
    if isinstance(value, list):
        return [remap(item, stage, target) for item in value]
    if isinstance(value, dict):
        return {key: remap(item, stage, target) for key, item in value.items()}
    return value


def preserve_base_proposals(stage: Path, target: Path, original: dict[str, str], base: dict[str, Any]) -> None:
    # Older base installers reused proposal names; retain the user's previous proposals.
    for relative in original:
        if ".wiki-proposed" not in Path(relative).name or not (target / relative).is_file():
            continue
        previous = (target / relative).read_bytes()
        path = stage / relative
        generated = path.read_bytes() if path.is_file() else None
        if generated == previous:
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(previous)
        if generated is not None:
            replacement = propose(stage, relative.split(".wiki-proposed", 1)[0], generated.decode("utf-8"))
            base["proposals"] = [replacement if item == relative else item for item in base.get("proposals", [])]


def run_local_novel_project(target: Path, config_path: Path, mode: str,
                            profile: str | None = None, *, dry_run: bool = False,
                            provenance: dict[str, str] | None = None) -> dict[str, Any]:
    target = safe_target(target)
    resolved_mode = base_mode(target, mode)
    config = read_config(config_path, require_base=resolved_mode != "upgrade")
    previous = wiki_bootstrap.read_manifest(target) or {}
    resolve_metadata(config, previous)
    wiki_bootstrap.resolve_profile(target, profile, resolved_mode)
    validate_novel_checkout(Path(__file__).resolve().parent.parent)
    original = snapshot(target)
    original_exists = target.exists()
    ancestor = target.parent
    while not ancestor.exists():
        ancestor = ancestor.parent
    size = sum(path.stat().st_size for path in target.rglob("*") if path.is_file()) if original_exists else 0
    if shutil.disk_usage(ancestor).free < size * 2 + 5 * 1024 * 1024:
        raise ValueError("insufficient free space for Novel transaction staging and backups")
    container = Path(tempfile.mkdtemp(prefix=f".llm-wiki-novel-{target.name}-", dir=ancestor))
    stage, backup = container / "vault", container / "previous"
    retain_container = False
    try:
        if original_exists:
            shutil.copytree(target, stage)
        else:
            stage.mkdir()
        frozen_config = container / "config.json"
        wiki_bootstrap.write_text(frozen_config, json.dumps(config, ensure_ascii=False))
        # This is already an isolated transaction; avoid a second full vault copy.
        base = (wiki_bootstrap._upgrade_in_place(stage, frozen_config, profile) if resolved_mode == "upgrade"
                else wiki_bootstrap.bootstrap(stage, frozen_config, resolved_mode, profile))
        preserve_base_proposals(stage, target, original, base)
        overlay = install_overlay(stage, config, previous, original)
        if provenance:
            wiki_upgrade._write_upgrade_provenance(stage, **provenance)
        verification = verify_installation(stage)
        if not verification["ok"]:
            raise RuntimeError("Novel staging verification failed: " + "; ".join(verification["errors"]))
        staged = snapshot(stage)
        if any(staged.get(path) != digest for path, digest in original.items()
               if path == "raw" or path.startswith("raw/") or path.startswith("manuscripts/")):
            raise RuntimeError("Novel installation changed original Raw or manuscript files")
        changes = [{"path": path, "action": "modify" if path in original else "create"}
                   for path, digest in staged.items() if original.get(path) != digest]
        changes.extend({"path": path, "action": "delete"} for path in sorted(original.keys() - staged.keys()))
        result = {**base, **overlay, "ok": True, "target": str(target), "mode": mode,
                  "base_mode": resolved_mode, "project_mode": "novel", "project_mode_version": PROJECT_MODE_VERSION,
                  "dry_run": dry_run, "mutation_started": False, "transactional": True,
                  "write_plan": {"write_policy": "vault-only", "changes": changes,
                                 "transaction_root": str(container),
                                 "rollback_backup": str(backup) if original_exists else None},
                  "verification": verification}
        if mode == "upgrade":
            result.update(upgrade_source="github" if provenance else "local",
                          bootstrap_commit=provenance["commit"] if provenance else None)
        if dry_run:
            result["staging_cleaned"] = True
            return remap(result, stage, target)
        if target.exists() != original_exists or snapshot(safe_target(target)) != original:
            raise RuntimeError("Novel target changed during staging; no changes applied")
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.parent.stat().st_dev != stage.stat().st_dev:
            raise RuntimeError("Novel staging and target must be on the same filesystem")
        if original_exists:
            target.rename(backup)
        try:
            stage.rename(target)
            final_verification = verify_installation(target)
            if not final_verification["ok"]:
                raise RuntimeError("Novel post-apply verification failed")
        except Exception:
            if target.exists():
                target.rename(container / "failed")
            if backup.exists():
                try:
                    backup.rename(target)
                except OSError as error:
                    retain_container = True
                    raise RuntimeError(f"Novel rollback could not restore the original; backup preserved at {backup}") from error
            raise
        retain_container = original_exists
        result = remap(result, stage, target)
        result.update(mutation_started=True, post_apply_verification=final_verification,
                      rollback_backup=str(backup) if original_exists else None)
        return result
    finally:
        if not retain_container:
            shutil.rmtree(container)


def upgrade_novel_from_github(target: Path, config: Path, profile: str | None = None,
                             *, dry_run: bool = False) -> dict[str, Any]:
    target = safe_target(target)
    base_mode(target, "upgrade")
    resolve_metadata(read_config(config, require_base=False), wiki_bootstrap.read_manifest(target) or {})
    branch, commit = wiki_upgrade.resolve_latest_commit()
    archive = wiki_upgrade.download_commit_archive(wiki_upgrade.OFFICIAL_REPOSITORY, commit)
    with tempfile.TemporaryDirectory(prefix="novel-github-checkout-") as temporary:
        checkout = wiki_upgrade.extract_checkout(archive, Path(temporary))
        validate_novel_checkout(checkout)
        command = [sys.executable, str(checkout / "scripts/novel_project.py"), "--target", str(target),
                   "--config", str(config.resolve()), "--mode", "upgrade", "--source", "local",
                   "--bootstrap-repository", wiki_upgrade.OFFICIAL_REPOSITORY,
                   "--bootstrap-branch", branch, "--bootstrap-commit", commit]
        if profile:
            command.extend(("--profile", profile))
        if dry_run:
            command.append("--dry-run")
        completed = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", check=False)
        result = wiki_upgrade._parse_bootstrap_result(completed.stdout)
        if completed.returncode or not result.get("ok"):
            raise RuntimeError("downloaded Novel upgrade failed: " + str(result.get("error", completed.stderr)))
    result.update(upgrade_source="github", bootstrap_repository=wiki_upgrade.OFFICIAL_REPOSITORY,
                  bootstrap_branch=branch, bootstrap_commit=commit)
    return result


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Create, migrate or transactionally upgrade a Novel Wiki.")
    parser.add_argument("--target", required=True, type=Path)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--mode", choices=("new", "migrate", "upgrade"), default="new")
    parser.add_argument("--profile", choices=("standard", "evidence"))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--source", choices=("github", "local"), default="github")
    for field in ("repository", "branch", "commit"):
        parser.add_argument(f"--bootstrap-{field}", help=argparse.SUPPRESS)
    args = parser.parse_args()
    try:
        provenance = None
        if args.bootstrap_repository or args.bootstrap_branch or args.bootstrap_commit:
            if not all((args.bootstrap_repository, args.bootstrap_branch, args.bootstrap_commit)):
                raise ValueError("complete GitHub provenance is required")
            provenance = {"repository": args.bootstrap_repository, "branch": args.bootstrap_branch, "commit": args.bootstrap_commit}
        if args.mode == "upgrade" and args.source == "github":
            result = upgrade_novel_from_github(args.target, args.config, args.profile, dry_run=args.dry_run)
        else:
            result = run_local_novel_project(args.target, args.config, args.mode, args.profile,
                                            dry_run=args.dry_run, provenance=provenance)
    except Exception as error:
        result = {"ok": False, "project_mode": "novel", "error": str(error)}
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
