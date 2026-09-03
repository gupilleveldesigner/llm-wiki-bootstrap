from __future__ import annotations

import json
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from game_project_contract import (
    ASSETS,
    GAME_CONTRACT_FILES,
    GAME_CONTRACT_MARKERS,
    GAME_DIRECTORIES,
    GAME_DOCS,
    GAME_ENGINE_LAYOUT_DOC,
    GAME_INGEST_ADAPTER_DESTINATION,
    GAME_INGEST_ADAPTER_SOURCE,
    GAME_INGEST_ROUTING_DESTINATION,
    GAME_INGEST_ROUTING_SOURCE,
    GAME_INGEST_SKILL,
    GAME_PROVIDER_CONFIG_SOURCE,
    GAME_PROVIDER_CONFIG_DESTINATION,
    GAME_PROVIDERS_RUNTIME_SOURCE,
    GAME_PROVIDERS_RUNTIME_DESTINATION,
    GAME_PROVIDERS_DOC,
    GAME_PROVIDER_ROUTER_MARKER,
    GAME_ROUTER_MARKER,
    GAME_SKILL,
    GAME_TRACE_INDEX_DESTINATION,
    GAME_TRACE_RUNTIME_DESTINATION,
    GAME_TRACE_RUNTIME_SOURCE,
    PROJECT_MODE,
    PROJECT_MODE_VERSION,
    game_bundle_source,
    render_file,
    replacements,
    resolve_game_metadata,
    validate_game_bundle,
    write_game_manifest,
    write_text,
)
from game_workspace import WorkspacePaths


def _proposal_path(destination: Path) -> Path:
    return destination.with_name(destination.name + ".wiki-proposed")


def install_game_docs(target: Path, values: dict[str, str], *, propose_existing: bool) -> tuple[list[str], list[str]]:
    installed: list[str] = []
    proposals: list[str] = []
    for source_name, destination_name, should_render, managed in GAME_DOCS:
        source = ASSETS / source_name
        if not source.is_file():
            raise FileNotFoundError(f"game project document is missing: {source}")
        content = render_file(source, values) if should_render else source.read_text(encoding="utf-8")
        destination = target / destination_name
        if destination.exists():
            if destination.read_text(encoding="utf-8") == content:
                installed.append(destination_name)
                continue
            if propose_existing and managed:
                proposal = _proposal_path(destination)
                write_text(proposal, content)
                proposals.append(proposal.relative_to(target).as_posix())
            installed.append(destination_name)
            continue
        write_text(destination, content)
        installed.append(destination_name)
    return installed, proposals


def install_game_templates(target: Path, *, propose_existing: bool) -> tuple[int, list[str]]:
    source_root = ASSETS / "project-modes/game/templates"
    if not source_root.is_dir():
        raise FileNotFoundError(f"game template bundle is missing: {source_root}")
    copied = 0
    proposals: list[str] = []
    destination_root = target / "templates/game"
    for source in sorted(source_root.rglob("*")):
        if not source.is_file():
            continue
        destination = destination_root / source.relative_to(source_root)
        if destination.exists():
            if destination.read_bytes() == source.read_bytes():
                continue
            if propose_existing:
                proposal = _proposal_path(destination)
                proposal.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, proposal)
                proposals.append(proposal.relative_to(target).as_posix())
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        copied += 1
    return copied, proposals


def install_game_skills(target: Path, *, propose_existing: bool) -> list[str]:
    proposals: list[str] = []
    roots = (
        (ASSETS / "skills-bundle/agents-skills/game-project", target / ".agents/skills/game-project"),
        (ASSETS / "skills-bundle/claude-adapters/game-project", target / ".claude/skills/game-project"),
        (ASSETS / "skills-bundle/agents-skills/game-ingest", target / ".agents/skills/game-ingest"),
        (ASSETS / "skills-bundle/claude-adapters/game-ingest", target / ".claude/skills/game-ingest"),
    )
    for source_root, destination_root in roots:
        if not source_root.is_dir():
            raise FileNotFoundError(f"game project skill is missing: {source_root}")
        for source in sorted(source_root.rglob("*")):
            if not source.is_file() or "__pycache__" in source.parts or source.suffix == ".pyc":
                continue
            relative = source.relative_to(source_root)
            if relative.name == "SKILL.md.bundled":
                relative = relative.with_name("SKILL.md")
            destination = destination_root / relative
            if destination.exists():
                if destination.read_bytes() == source.read_bytes():
                    continue
                if propose_existing:
                    proposal = _proposal_path(destination)
                    proposal.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, proposal)
                    proposals.append(proposal.relative_to(target).as_posix())
                    continue
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
    return proposals


def install_game_runtime(target: Path, *, propose_existing: bool) -> tuple[list[str], list[str]]:
    managed = (
        (GAME_PROVIDER_CONFIG_SOURCE, GAME_PROVIDER_CONFIG_DESTINATION, "Game provider config"),
        (GAME_PROVIDERS_RUNTIME_SOURCE, GAME_PROVIDERS_RUNTIME_DESTINATION, "Game provider planner"),
        (GAME_TRACE_RUNTIME_SOURCE, GAME_TRACE_RUNTIME_DESTINATION, "game traceability runtime"),
        (GAME_INGEST_ADAPTER_SOURCE, GAME_INGEST_ADAPTER_DESTINATION, "Game ingest adapter"),
        (GAME_INGEST_ROUTING_SOURCE, GAME_INGEST_ROUTING_DESTINATION, "Game ingest routing"),
    )
    installed: list[str] = []
    proposals: list[str] = []
    for source_name, destination_name, label in managed:
        source = game_bundle_source(source_name)
        if not source.is_file():
            raise FileNotFoundError(f"{label} is missing: {source}")
        destination = target / destination_name
        if destination.exists():
            if destination.read_bytes() == source.read_bytes():
                installed.append(destination_name)
                continue
            if propose_existing:
                proposal = _proposal_path(destination)
                proposal.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, proposal)
                proposals.append(proposal.relative_to(target).as_posix())
                continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        installed.append(destination_name)
    return installed, proposals


def install_engine_isolation(target: Path, workspace: WorkspacePaths, engine: dict[str, Any]) -> list[str]:
    installed: list[str] = []
    if workspace.layout != "embedded":
        return installed
    for relative, content in engine.get("isolation_files", {}).items():
        destination = target / relative
        if destination.exists():
            continue
        write_text(destination, str(content))
        installed.append(relative)
    return installed


def ensure_backup_dir(target: Path, base_result: dict[str, Any]) -> Path:
    existing = base_result.get("backup_dir")
    if isinstance(existing, str) and existing:
        path = Path(existing)
    else:
        path = target / ".wiki-upgrade-bak" / datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        base_result["backup_dir"] = str(path.resolve())
    path.mkdir(parents=True, exist_ok=True)
    return path


def backup_game_managed_assets(target: Path, backup_dir: Path) -> list[str]:
    backed_up: list[str] = []
    for relative in (
        ".agents/skills/game-project",
        ".claude/skills/game-project",
        ".agents/skills/game-ingest",
        ".claude/skills/game-ingest",
    ):
        source = target / relative
        if not source.is_dir():
            continue
        destination = backup_dir / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            shutil.rmtree(destination)
        shutil.move(str(source), str(destination))
        backed_up.append(relative)
    for relative in (
        GAME_PROVIDER_CONFIG_DESTINATION,
        GAME_PROVIDERS_RUNTIME_DESTINATION,
        GAME_TRACE_RUNTIME_DESTINATION,
        GAME_INGEST_ADAPTER_DESTINATION,
        GAME_INGEST_ROUTING_DESTINATION,
    ):
        source = target / relative
        if not source.is_file():
            continue
        destination = backup_dir / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            destination.unlink()
        shutil.move(str(source), str(destination))
        backed_up.append(relative)
    return backed_up


# Compatibility with the first game-mode draft.
def backup_game_skills(target: Path, backup_dir: Path) -> list[str]:
    return backup_game_managed_assets(target, backup_dir)


def game_router_block() -> str:
    return (
        f"\n\n{GAME_ROUTER_MARKER}\n"
        "## Game project mode overlay\n\n"
        "- `.llm-wiki.json`의 `project_mode: game`과 `game_project.project_root`를 먼저 확인한다.\n"
        "- 게임 작업에는 설치된 `game-project` 스킬을 읽고 `wiki/game/model.md`, "
        f"`instructions/game-project.md`, `{GAME_ENGINE_LAYOUT_DOC}`를 따른다.\n"
        "- Raw 게임 자료 인제스트는 `/ingest`가 manifest를 통해 `game-ingest` adapter로 자동 라우팅하며, "
        "명시적 작업에는 설치된 `game-ingest` 스킬과 `instructions/game-ingest.md`를 사용한다.\n"
        "- 설치기와 업그레이더는 vault-only write policy를 지킨다. live project는 읽기·검사 대상이며 "
        "명시적인 implement 작업 외에는 수정하지 않는다.\n"
        "- 설계 의도, 실제 구현, 검증 결과, 채택 결정, production 상태를 분리한다.\n"
        "- 기획·코드·빌드·테스트·결정 연결은 `wiki/game/traceability.json`에서 조회하며, "
        "game 문서를 바꾼 뒤 `python tools/game_trace.py scan`, `status`, `verify`를 실행한다.\n"
    )


def game_provider_router_block() -> str:
    return (
        f"\n\n{GAME_PROVIDER_ROUTER_MARKER}\n"
        "## Optional Game providers\n\n"
        f"- Game 질의는 `{GAME_PROVIDERS_DOC}`의 WHAT → Graphify / HOW → CodeGraph / WHY → Wiki 정책을 따른다.\n"
        "- `python tools/game_providers.py status`로 선택 상태를 확인한다. MCP 연결·기본 corpus를 확인하지 못하면 로컬 조회로 돌아간다.\n"
        "- 외부 graph는 선택 기능이다. graph 데이터·node ID를 Wiki/traceability에 복제하거나 baseline을 자동 승인하지 않는다.\n"
        "- 이 정책이 Game 작업의 일반 graph-first 안내보다 우선한다. Game ingest는 graph 없이 핵심 검증을 완료한다.\n"
    )


def install_game_router(target: Path, *, propose_existing: bool) -> list[str]:
    proposals: list[str] = []
    blocks = ((GAME_ROUTER_MARKER, game_router_block()), (GAME_PROVIDER_ROUTER_MARKER, game_provider_router_block()))
    for relative in ("CLAUDE.md", "AGENTS.md", "wiki/CLAUDE.md"):
        destination = target / relative
        if not destination.is_file():
            raise RuntimeError(f"base router is missing: {relative}")
        current = destination.read_text(encoding="utf-8")
        missing = [block for marker, block in blocks if marker not in current]
        if not missing:
            continue
        if not propose_existing:
            write_text(destination, current.rstrip() + "".join(missing))
            continue
        proposal = _proposal_path(destination)
        proposal_base = proposal.read_text(encoding="utf-8") if proposal.is_file() else current
        missing = [block for marker, block in blocks if marker not in proposal_base]
        if missing:
            write_text(proposal, proposal_base.rstrip() + "".join(missing))
        proposals.append(proposal.relative_to(target).as_posix())
    return proposals


def _check_installed_marker(target: Path, destination_name: str, marker: str) -> tuple[str | None, str | None]:
    destination = target / destination_name
    if destination.is_file() and marker in destination.read_text(encoding="utf-8"):
        return None, None
    proposal = _proposal_path(destination)
    if proposal.is_file() and marker in proposal.read_text(encoding="utf-8"):
        return proposal.relative_to(target).as_posix(), None
    if not destination.is_file():
        return None, f"missing installed game project file: {destination_name}"
    return None, f"installed game project file lacks marker {marker!r}: {destination_name}"


def verify_game_installation(target: Path, workspace: WorkspacePaths, engine: dict[str, Any]) -> dict[str, Any]:
    pending: list[str] = []
    errors: list[str] = []
    checked: list[str] = []
    for source_name, destination_name in GAME_CONTRACT_FILES:
        marker = GAME_CONTRACT_MARKERS[source_name]
        checked.append(destination_name)
        proposal, error = _check_installed_marker(target, destination_name, marker)
        if proposal:
            pending.append(proposal)
        if error:
            errors.append(error)
    for directory in GAME_DIRECTORIES:
        if not (target / directory).is_dir():
            errors.append(f"missing installed game project directory: {directory}")
    for relative in ("CLAUDE.md", "AGENTS.md", "wiki/CLAUDE.md"):
        path = target / relative
        markers = (GAME_ROUTER_MARKER, GAME_PROVIDER_ROUTER_MARKER)
        if path.is_file() and all(marker in path.read_text(encoding="utf-8") for marker in markers):
            continue
        proposal = _proposal_path(path)
        if proposal.is_file() and all(marker in proposal.read_text(encoding="utf-8") for marker in markers):
            pending.append(proposal.relative_to(target).as_posix())
        else:
            errors.append(f"missing game project router marker: {relative}")
    if workspace.layout == "embedded":
        for relative in engine.get("isolation_files", {}):
            if not (target / relative).exists():
                errors.append(f"missing embedded engine-isolation file: {relative}")
    return {
        "status": "failed" if errors else ("pending" if pending else "ok"),
        "checked": checked,
        "pending": sorted(set(pending)),
        "errors": errors,
    }


def _parse_trace_result(stdout: str) -> dict[str, Any]:
    lines = [line.strip() for line in stdout.splitlines() if line.strip()]
    if not lines:
        raise RuntimeError("game traceability runtime produced no JSON result")
    try:
        result = json.loads(lines[-1])
    except json.JSONDecodeError as error:
        raise RuntimeError("game traceability runtime did not end with JSON") from error
    if not isinstance(result, dict):
        raise RuntimeError("game traceability runtime returned an unexpected result shape")
    return result


def run_traceability_command(
    vault_root: Path,
    project_root: Path,
    command: str,
    *arguments: str,
    runtime_path: Path | None = None,
) -> dict[str, Any]:
    runtime = runtime_path or (ASSETS / GAME_TRACE_RUNTIME_SOURCE)
    completed = subprocess.run(
        [
            sys.executable,
            str(runtime),
            "--vault-root",
            str(vault_root),
            "--project-root",
            str(project_root),
            "--index",
            GAME_TRACE_INDEX_DESTINATION,
            "--compact",
            command,
            *arguments,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    result = _parse_trace_result(completed.stdout)
    if completed.returncode == 2:
        detail = completed.stderr.strip()
        if detail:
            result.setdefault("stderr", detail)
        raise RuntimeError(result.get("error") or "game traceability runtime failed")
    result["returncode"] = completed.returncode
    return result


def install_game_overlay(
    target: Path,
    project_root: Path,
    config: dict[str, Any],
    workspace: WorkspacePaths,
    engine: dict[str, Any],
    *,
    mode: str,
    previous_project_mode: str,
    router_propose_existing: bool | None = None,
) -> dict[str, Any]:
    validate_game_bundle()
    metadata = resolve_game_metadata(target, config, workspace, engine)
    values = replacements(target, config, metadata)
    for directory in GAME_DIRECTORIES:
        (target / directory).mkdir(parents=True, exist_ok=True)

    propose_existing = mode in ("migrate", "upgrade")
    skill_proposals = install_game_skills(target, propose_existing=mode == "migrate")
    runtime_files, runtime_proposals = install_game_runtime(target, propose_existing=mode == "migrate")
    template_count, template_proposals = install_game_templates(target, propose_existing=propose_existing)
    docs, doc_proposals = install_game_docs(target, values, propose_existing=propose_existing)
    isolation_files = install_engine_isolation(target, workspace, engine)
    router_proposals = install_game_router(
        target,
        propose_existing=propose_existing if router_propose_existing is None else router_propose_existing,
    )
    write_game_manifest(target, metadata)

    trace_rebuild = run_traceability_command(target, project_root, "rebuild")
    trace_verification = run_traceability_command(target, project_root, "verify")
    verification = verify_game_installation(target, workspace, engine)
    if verification["status"] == "failed":
        raise RuntimeError("game project installation verification failed: " + "; ".join(verification["errors"]))
    verification["traceability"] = trace_verification
    if verification["status"] == "ok" and not trace_verification.get("ok"):
        verification["status"] = "pending"
        verification["pending"] = sorted(set(verification["pending"]) | {GAME_TRACE_INDEX_DESTINATION})

    proposals = [*skill_proposals, *runtime_proposals, *template_proposals, *doc_proposals, *router_proposals]
    return {
        "project_mode": PROJECT_MODE,
        "project_mode_version": PROJECT_MODE_VERSION,
        "previous_project_mode": previous_project_mode,
        "project_mode_changed": previous_project_mode != PROJECT_MODE,
        "project_mode_docs": docs,
        "project_mode_templates_copied": template_count,
        "project_mode_skill": GAME_SKILL,
        "project_mode_ingest_skill": GAME_INGEST_SKILL,
        "project_mode_runtime": runtime_files,
        "engine_isolation_files": isolation_files,
        "project_mode_verification": verification,
        "project_mode_activation_pending": verification["status"] == "pending" or bool(proposals) or not trace_verification.get("ok"),
        "traceability": {
            "index": GAME_TRACE_INDEX_DESTINATION,
            "runtime": GAME_TRACE_RUNTIME_DESTINATION,
            "rebuild": trace_rebuild,
            "verification": trace_verification,
        },
        "game_ingest": {
            "skill": GAME_INGEST_SKILL,
            "adapter": GAME_INGEST_ADAPTER_DESTINATION,
            "routing": GAME_INGEST_ROUTING_DESTINATION,
            "auto_route": True,
        },
        "game_project": metadata,
        "game_proposals": sorted(set(proposals)),
    }
