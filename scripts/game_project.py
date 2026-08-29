from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import bootstrap as wiki_bootstrap
import upgrade as wiki_upgrade
from game_project_contract import (
    GAME_TRACE_RUNTIME_DESTINATION,
    PROJECT_MODE,
    read_json_object,
    read_manifest,
    validate_config,
    validate_game_bundle,
    validate_game_checkout,
    write_upgrade_provenance,
)
from game_project_install import (
    backup_game_managed_assets,
    ensure_backup_dir,
    install_game_overlay,
    run_traceability_command,
    verify_game_installation,
)
from game_workspace import (
    INTEGRITY_MODES,
    SUPPORTED_ENGINES,
    SUPPORTED_LAYOUTS,
    WorkspaceError,
    WorkspacePaths,
    apply_staged_vault,
    build_write_plan,
    cleanup_staging,
    compare_snapshots,
    detect_engine,
    make_staging_directory,
    resolve_workspace_paths,
    seed_staging_from_existing,
    snapshot_project,
    verify_managed_manifest,
    write_managed_manifest,
)


def _path_from_config(config_path: Path, value: str | None) -> Path | None:
    if not value:
        return None
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = config_path.parent / path
    return path


def _project_from_vault_manifest(vault_root: Path) -> Path | None:
    manifest = read_manifest(vault_root)
    game = manifest.get("game_project") if isinstance(manifest, dict) else None
    if not isinstance(game, dict):
        return None
    value = game.get("project_root")
    kind = game.get("project_root_kind", "relative")
    if not isinstance(value, str) or not value:
        return None
    path = Path(value)
    if kind == "relative" or not path.is_absolute():
        path = vault_root / path
    return path.resolve()


def resolve_cli_roots(
    config_path: Path,
    config: dict[str, Any],
    *,
    target: Path | None,
    project_root: Path | None,
    vault_root: Path | None,
) -> tuple[Path, Path | None]:
    project = project_root
    vault = vault_root
    if target is not None:
        target_resolved = target.expanduser().resolve()
        if project is not None:
            raise WorkspaceError("use either --target or --project-root, not both")
        if (target_resolved / ".llm-wiki.json").is_file():
            manifest_project = _project_from_vault_manifest(target_resolved)
            if manifest_project is not None:
                project = manifest_project
                vault = vault or target_resolved
            else:
                project = target_resolved
        else:
            project = target_resolved
    if project is None:
        project = _path_from_config(config_path, config.get("project_root"))
    if vault is None:
        vault = _path_from_config(config_path, config.get("vault_root"))
    if project is None:
        raise WorkspaceError("game mode requires --project-root (or legacy --target/config project_root)")
    return project, vault


def determine_base_mode(vault_root: Path, requested_mode: str) -> str:
    exists = vault_root.exists()
    nonempty = exists and vault_root.is_dir() and any(vault_root.iterdir())
    looks_like_wiki = (vault_root / ".llm-wiki.json").is_file() or (
        (vault_root / "raw").is_dir() and (vault_root / "wiki").is_dir()
    )
    if requested_mode == "new":
        if nonempty:
            raise WorkspaceError("new game Wiki requires an absent or empty vault root")
        return "new"
    if requested_mode == "upgrade":
        if not looks_like_wiki:
            raise WorkspaceError("upgrade requires an existing LLM Wiki vault")
        return "upgrade"
    if looks_like_wiki:
        return "upgrade"
    if nonempty:
        return "migrate"
    return "new"


def _remap_paths(value: Any, source: Path, destination: Path) -> Any:
    source_text = str(source.resolve())
    destination_text = str(destination.resolve())
    if isinstance(value, str):
        return value.replace(source_text, destination_text)
    if isinstance(value, list):
        return [_remap_paths(item, source, destination) for item in value]
    if isinstance(value, dict):
        return {key: _remap_paths(item, source, destination) for key, item in value.items()}
    return value


def _post_apply_verification(
    vault_root: Path,
    project_root: Path,
    workspace: WorkspacePaths,
    engine: dict[str, Any],
    before_snapshot: dict[str, Any],
    integrity_mode: str,
) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    managed = verify_managed_manifest(vault_root)
    errors.extend(managed.get("errors", []))
    warnings.extend(managed.get("warnings", []))
    trace = run_traceability_command(
        vault_root,
        project_root,
        "verify",
        runtime_path=vault_root / GAME_TRACE_RUNTIME_DESTINATION,
    )
    if not trace.get("ok"):
        errors.extend(trace.get("errors", []))
        warnings.extend(trace.get("warnings", []))
    game = verify_game_installation(vault_root, workspace, engine)
    if game.get("status") == "failed":
        errors.extend(game.get("errors", []))
    after_snapshot = snapshot_project(
        project_root,
        engine,
        exclude_roots=(workspace.vault_root, workspace.transaction_root),
        mode=integrity_mode,
    )
    integrity = compare_snapshots(before_snapshot, after_snapshot)
    if not integrity.get("ok"):
        errors.append("engine-owned project paths changed during Wiki installation")
    return {
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "managed_files": managed,
        "traceability": trace,
        "game_installation": game,
        "project_integrity": integrity,
    }


def prepare_local_game_project(
    project_root: Path,
    config_path: Path,
    mode: str,
    profile: str | None = None,
    *,
    vault_root: Path | None = None,
    layout: str = "auto",
    engine_name: str = "auto",
    allow_legacy_in_place: bool = False,
    adopt_existing_vault: bool = False,
    provenance: dict[str, str] | None = None,
) -> tuple[dict[str, Any], Path, WorkspacePaths, dict[str, Any]]:
    validate_game_bundle()
    config = read_json_object(config_path)
    validate_config(config, require_base=mode in ("new", "migrate"))
    resolved_layout = str(config.get("layout") or layout)
    resolved_engine = str(config.get("engine") or engine_name)
    workspace = resolve_workspace_paths(
        project_root,
        vault_root=vault_root,
        layout=resolved_layout,
        mode=mode,
        allow_legacy_in_place=allow_legacy_in_place,
    )
    configured_sources = config.get("source_roots") if isinstance(config.get("source_roots"), list) else None
    engine = detect_engine(workspace.project_root, requested=resolved_engine, source_roots=configured_sources)
    base_mode = determine_base_mode(workspace.vault_root, mode)
    previous_manifest = read_manifest(workspace.vault_root) if workspace.vault_root.exists() else {}
    previous_project_mode = str(previous_manifest.get("project_mode", "knowledge"))
    stage = make_staging_directory(workspace)
    try:
        seed_staging_from_existing(workspace.vault_root, stage)
        if base_mode == "upgrade":
            # Game mode already applies its own verified staging transaction.
            base_result = wiki_bootstrap.upgrade(stage, config_path, profile, transactional=False)
            backup_dir = ensure_backup_dir(stage, base_result)
            base_result["game_managed_backup"] = backup_game_managed_assets(stage, backup_dir)
        else:
            base_result = wiki_bootstrap.bootstrap(stage, config_path, base_mode, profile)
            base_result["game_managed_backup"] = []

        overlay_result = install_game_overlay(
            stage,
            workspace.project_root,
            config,
            workspace,
            engine,
            mode=base_mode,
            previous_project_mode=previous_project_mode,
            router_propose_existing=base_mode in ("migrate", "upgrade"),
        )
        if provenance:
            write_upgrade_provenance(
                stage,
                repository=provenance["repository"],
                branch=provenance["branch"],
                commit=provenance["commit"],
            )
        write_managed_manifest(
            stage,
            workspace.vault_root,
            workspace,
            engine,
            installation_mode=mode,
        )
        backed_up = list(base_result.get("game_managed_backup", []))
        plan = build_write_plan(
            workspace.vault_root,
            stage,
            workspace,
            engine,
            backed_up_paths=backed_up,
            adopt_existing_vault=adopt_existing_vault,
        )
        stage_managed = verify_managed_manifest(stage)
        if not stage_managed.get("ok"):
            plan["safe_to_apply"] = False
            plan.setdefault("collisions", []).extend(
                {"path": ".llm-wiki-managed.json", "reason": message}
                for message in stage_managed.get("errors", [])
            )
        result = dict(base_result)
        result.update(overlay_result)
        result.update(
            {
                "ok": bool(plan.get("safe_to_apply")),
                "mode": mode,
                "base_mode": base_mode,
                "project_root": str(workspace.project_root),
                "vault_root": str(workspace.vault_root),
                "layout": workspace.layout,
                "engine": engine,
                "write_plan": plan,
                "managed_manifest_verification": stage_managed,
                "mutation_started": False,
            }
        )
        if mode in ("migrate", "upgrade"):
            result["proposals"] = sorted(
                set(result.get("proposals", [])) | set(overlay_result.get("game_proposals", []))
            )
        return result, stage, workspace, engine
    except Exception:
        cleanup_staging(stage)
        raise


def run_local_game_project(
    project_root: Path,
    config_path: Path,
    mode: str,
    profile: str | None = None,
    *,
    vault_root: Path | None = None,
    layout: str = "auto",
    engine_name: str = "auto",
    dry_run: bool = False,
    integrity_mode: str = "metadata",
    keep_rollback_backup: bool = True,
    allow_legacy_in_place: bool = False,
    adopt_existing_vault: bool = False,
    provenance: dict[str, str] | None = None,
) -> dict[str, Any]:
    if integrity_mode not in INTEGRITY_MODES:
        raise WorkspaceError(f"unsupported integrity mode: {integrity_mode}")
    result, stage, workspace, engine = prepare_local_game_project(
        project_root,
        config_path,
        mode,
        profile,
        vault_root=vault_root,
        layout=layout,
        engine_name=engine_name,
        allow_legacy_in_place=allow_legacy_in_place,
        adopt_existing_vault=adopt_existing_vault,
        provenance=provenance,
    )
    plan = result["write_plan"]
    if dry_run:
        cleanup_staging(stage)
        result.update(
            {
                "dry_run": True,
                "ok": bool(plan.get("safe_to_apply")),
                "mutation_started": False,
                "staging_cleaned": True,
            }
        )
        return result
    if not plan.get("safe_to_apply"):
        cleanup_staging(stage)
        raise WorkspaceError("unsafe write plan; run with --dry-run and resolve collisions")

    before_snapshot = snapshot_project(
        workspace.project_root,
        engine,
        exclude_roots=(workspace.vault_root, workspace.transaction_root),
        mode=integrity_mode,
    )

    def verify_applied(vault: Path) -> dict[str, Any]:
        return _post_apply_verification(
            vault,
            workspace.project_root,
            workspace,
            engine,
            before_snapshot,
            integrity_mode,
        )

    applied = apply_staged_vault(
        stage,
        workspace,
        plan,
        post_apply_verify=verify_applied,
        keep_backup=keep_rollback_backup,
    )
    result = _remap_paths(result, stage, workspace.vault_root)
    result.update(
        {
            "ok": True,
            "dry_run": False,
            "mutation_started": True,
            "rollback_backup": applied.get("backup_root"),
            "post_apply_verification": applied.get("verification"),
        }
    )
    return result


# Backward-compatible Python entrypoint: target is interpreted as project_root.
def apply_local_game_project(
    target: Path,
    config_path: Path,
    mode: str,
    profile: str | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    return run_local_game_project(target, config_path, mode, profile, **kwargs)


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
    project_root: Path,
    vault_root: Path | None,
    config: Path,
    profile: str | None,
    *,
    layout: str,
    engine_name: str,
    dry_run: bool,
    integrity_mode: str,
    keep_rollback_backup: bool,
    allow_legacy_in_place: bool,
    adopt_existing_vault: bool,
    repository: str,
    branch: str,
    commit: str,
) -> dict[str, Any]:
    command = [
        sys.executable,
        str(checkout / "scripts/game_project.py"),
        "--project-root",
        str(project_root),
        "--config",
        str(config),
        "--mode",
        "upgrade",
        "--source",
        "local",
        "--layout",
        layout,
        "--engine",
        engine_name,
        "--integrity",
        integrity_mode,
        "--bootstrap-repository",
        repository,
        "--bootstrap-branch",
        branch,
        "--bootstrap-commit",
        commit,
    ]
    if vault_root is not None:
        command.extend(("--vault-root", str(vault_root)))
    if profile:
        command.extend(("--profile", profile))
    if dry_run:
        command.append("--dry-run")
    if not keep_rollback_backup:
        command.append("--discard-rollback-backup")
    if allow_legacy_in_place:
        command.append("--allow-legacy-in-place")
    if adopt_existing_vault:
        command.append("--adopt-existing-vault")
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    result = parse_result(completed.stdout)
    if completed.returncode != 0 or not result.get("ok"):
        detail = completed.stderr.strip()
        if detail:
            result.setdefault("stderr", detail)
    return result


def upgrade_game_from_github(
    project_root: Path,
    vault_root: Path | None,
    config: Path,
    profile: str | None = None,
    **options: Any,
) -> dict[str, Any]:
    branch, commit = wiki_upgrade.resolve_latest_commit(wiki_upgrade.OFFICIAL_REPOSITORY)
    archive = wiki_upgrade.download_commit_archive(wiki_upgrade.OFFICIAL_REPOSITORY, commit)
    with tempfile.TemporaryDirectory(prefix="llm-wiki-game-upgrade-") as temporary:
        checkout = wiki_upgrade.extract_checkout(archive, Path(temporary))
        validate_game_checkout(checkout)
        result = run_checkout_game_upgrade(
            checkout,
            project_root,
            vault_root,
            config,
            profile,
            repository=wiki_upgrade.OFFICIAL_REPOSITORY,
            branch=branch,
            commit=commit,
            **options,
        )
    result.update(
        {
            "upgrade_source": "github",
            "bootstrap_repository": wiki_upgrade.OFFICIAL_REPOSITORY,
            "bootstrap_branch": branch,
            "bootstrap_commit": commit,
        }
    )
    return result


def upgrade_game_from_local(
    project_root: Path,
    vault_root: Path | None,
    config: Path,
    profile: str | None = None,
    **options: Any,
) -> dict[str, Any]:
    result = run_local_game_project(project_root, config, "upgrade", profile, vault_root=vault_root, **options)
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
            "Install or upgrade Game mode as a sidecar-safe LLM Wiki. The installer writes only to the "
            "vault root plus its transaction root; the live engine project remains structurally intact."
        )
    )
    parser.add_argument("--target", type=Path, default=None, help="Deprecated alias for --project-root, or an existing vault with a project-root manifest reference.")
    parser.add_argument("--project-root", type=Path, default=None, help="Live game/engine project root.")
    parser.add_argument("--vault-root", type=Path, default=None, help="Wiki vault root. Defaults to sidecar <project>.wiki.")
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--mode", choices=("new", "migrate", "upgrade"), default="migrate")
    parser.add_argument("--profile", choices=("standard", "evidence"), default=None)
    parser.add_argument("--layout", choices=SUPPORTED_LAYOUTS, default="auto")
    parser.add_argument("--engine", choices=SUPPORTED_ENGINES, default="auto")
    parser.add_argument("--dry-run", action="store_true", help="Build and verify a staged vault, emit the exact write plan, and do not mutate the final vault.")
    parser.add_argument("--integrity", choices=INTEGRITY_MODES, default="metadata", help="Verify engine-owned paths before/after apply.")
    parser.add_argument("--discard-rollback-backup", action="store_true")
    parser.add_argument("--allow-legacy-in-place", action="store_true")
    parser.add_argument("--adopt-existing-vault", action="store_true")
    parser.add_argument("--source", choices=("github", "local"), default="github")
    parser.add_argument("--bootstrap-repository", default=None, help=argparse.SUPPRESS)
    parser.add_argument("--bootstrap-branch", default=None, help=argparse.SUPPRESS)
    parser.add_argument("--bootstrap-commit", default=None, help=argparse.SUPPRESS)
    args = parser.parse_args()

    try:
        config_path = args.config.expanduser().resolve()
        config = read_json_object(config_path)
        validate_config(config, require_base=args.mode in ("new", "migrate"))
        project_root, vault_root = resolve_cli_roots(
            config_path,
            config,
            target=args.target,
            project_root=args.project_root,
            vault_root=args.vault_root,
        )
        layout = str(config.get("layout") or args.layout)
        engine_name = str(config.get("engine") or args.engine)
        options = {
            "layout": layout,
            "engine_name": engine_name,
            "dry_run": args.dry_run,
            "integrity_mode": args.integrity,
            "keep_rollback_backup": not args.discard_rollback_backup,
            "allow_legacy_in_place": args.allow_legacy_in_place,
            "adopt_existing_vault": args.adopt_existing_vault,
        }
        provenance = None
        if args.bootstrap_repository and args.bootstrap_branch and args.bootstrap_commit:
            provenance = {
                "repository": args.bootstrap_repository,
                "branch": args.bootstrap_branch,
                "commit": args.bootstrap_commit,
            }
        if args.mode == "upgrade" and args.source == "github":
            result = upgrade_game_from_github(project_root, vault_root, config_path, args.profile, **options)
        elif args.mode == "upgrade":
            result = upgrade_game_from_local(
                project_root,
                vault_root,
                config_path,
                args.profile,
                provenance=provenance,
                **options,
            )
        else:
            result = run_local_game_project(
                project_root,
                config_path,
                args.mode,
                args.profile,
                vault_root=vault_root,
                provenance=provenance,
                **options,
            )
    except Exception as error:
        result = {
            "ok": False,
            "mode": args.mode,
            "profile": args.profile,
            "project_mode": PROJECT_MODE,
            "upgrade_source": args.source if args.mode == "upgrade" else None,
            "mutation_started": False,
            "error": str(error),
        }

    print(json.dumps(result, ensure_ascii=False))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
