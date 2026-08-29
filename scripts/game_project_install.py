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
    GAME_ROUTER_MARKER,
    GAME_SKILL,
    GAME_TRACE_INDEX_DESTINATION,
    GAME_TRACE_RUNTIME_DESTINATION,
    GAME_TRACE_RUNTIME_SOURCE,
    PROJECT_MODE,
    PROJECT_MODE_VERSION,
    render_file,
    replacements,
    resolve_game_metadata,
    validate_game_bundle,
    write_game_manifest,
    write_text,
)


def _proposal_path(destination: Path) -> Path:
    return destination.with_name(destination.name + ".wiki-proposed")


def install_game_docs(
    target: Path,
    values: dict[str, str],
    *,
    propose_existing: bool,
) -> tuple[list[str], list[str]]:
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
    source = ASSETS / GAME_TRACE_RUNTIME_SOURCE
    if not source.is_file():
        raise FileNotFoundError(f"game traceability runtime is missing: {source}")
    destination = target / GAME_TRACE_RUNTIME_DESTINATION
    installed: list[str] = []
    proposals: list[str] = []
    if destination.exists():
        if destination.read_bytes() == source.read_bytes():
            return [GAME_TRACE_RUNTIME_DESTINATION], []
        if propose_existing:
            proposal = _proposal_path(destination)
            proposal.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, proposal)
            proposals.append(proposal.relative_to(target).as_posix())
            return [], proposals
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    installed.append(GAME_TRACE_RUNTIME_DESTINATION)
    return installed, proposals


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
    for relative in (".agents/skills/game-project", ".claude/skills/game-project"):
        source = target / relative
        if not source.is_dir():
            continue
        destination = backup_dir / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            shutil.rmtree(destination)
        shutil.move(str(source), str(destination))
        backed_up.append(relative)
    for relative in (GAME_TRACE_RUNTIME_DESTINATION,):
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


# Compatibility for callers created by the first game-mode draft.
def backup_game_skills(target: Path, backup_dir: Path) -> list[str]:
    return backup_game_managed_assets(target, backup_dir)


def game_router_block() -> str:
    return (
        f"\n\n{GAME_ROUTER_MARKER}\n"
        "## Game project mode overlay\n\n"
        "- `.llm-wiki.json`의 `project_mode: game`이 활성 상태다.\n"
        "- 게임 설계·레벨·시스템·콘텐츠·에셋 브리프·구현 확인·빌드·플레이테스트·결정 기록에는 "
        "설치된 `game-project` 스킬을 먼저 읽는다.\n"
        "- 작업 전 `wiki/game/model.md`와 `instructions/game-project.md`를 읽는다.\n"
        "- 설계 의도, 실제 구현, 검증 결과, 채택 결정을 서로 다른 상태로 기록한다.\n"
        "- 실행 중인 게임 코드·에셋·엔진 프로젝트를 `raw/`로 이동하지 않는다. `raw/game/`에는 "
        "불변 증거 사본·로그·리포트만 둔다.\n"
        "- 기획·코드·빌드·테스트·결정 연결은 `wiki/game/traceability.json`에서 조회하며, "
        "game 문서를 바꾼 뒤 `python tools/game_trace.py rebuild`와 `verify`를 실행한다.\n"
    )


def install_game_router(target: Path, *, propose_existing: bool) -> list[str]:
    proposals: list[str] = []
    block = game_router_block()
    for relative in ("CLAUDE.md", "AGENTS.md", "wiki/CLAUDE.md"):
        destination = target / relative
        if not destination.is_file():
            raise RuntimeError(f"base router is missing: {relative}")
        current = destination.read_text(encoding="utf-8")
        if GAME_ROUTER_MARKER in current:
            continue
        if not propose_existing:
            write_text(destination, current.rstrip() + block)
            continue
        proposal = _proposal_path(destination)
        proposal_base = proposal.read_text(encoding="utf-8") if proposal.is_file() else current
        if GAME_ROUTER_MARKER not in proposal_base:
            write_text(proposal, proposal_base.rstrip() + block)
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


def verify_game_installation(target: Path) -> dict[str, Any]:
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
        if path.is_file() and GAME_ROUTER_MARKER in path.read_text(encoding="utf-8"):
            continue
        proposal = _proposal_path(path)
        if proposal.is_file() and GAME_ROUTER_MARKER in proposal.read_text(encoding="utf-8"):
            pending.append(proposal.relative_to(target).as_posix())
        else:
            errors.append(f"missing game project router marker: {relative}")
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


def run_traceability_command(target: Path, command: str, *arguments: str) -> dict[str, Any]:
    runtime = ASSETS / GAME_TRACE_RUNTIME_SOURCE
    completed = subprocess.run(
        [
            sys.executable,
            str(runtime),
            "--root",
            str(target),
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
    config: dict[str, Any],
    *,
    mode: str,
    previous_project_mode: str,
    router_propose_existing: bool | None = None,
) -> dict[str, Any]:
    validate_game_bundle()
    metadata = resolve_game_metadata(target, config)
    values = replacements(target, config, metadata)
    for directory in GAME_DIRECTORIES:
        (target / directory).mkdir(parents=True, exist_ok=True)

    propose_existing = mode in ("migrate", "upgrade")
    skill_proposals = install_game_skills(target, propose_existing=mode == "migrate")
    runtime_files, runtime_proposals = install_game_runtime(target, propose_existing=mode == "migrate")
    template_count, template_proposals = install_game_templates(target, propose_existing=propose_existing)
    docs, doc_proposals = install_game_docs(target, values, propose_existing=propose_existing)
    router_proposals = install_game_router(
        target,
        propose_existing=propose_existing if router_propose_existing is None else router_propose_existing,
    )
    write_game_manifest(target, metadata)

    trace_rebuild = run_traceability_command(target, "rebuild")
    trace_verification = run_traceability_command(target, "verify")
    verification = verify_game_installation(target)
    if verification["status"] == "failed":
        raise RuntimeError("game project installation verification failed: " + "; ".join(verification["errors"]))
    verification["traceability"] = trace_verification
    if verification["status"] == "ok" and not trace_verification.get("ok"):
        verification["status"] = "pending"
        verification["pending"] = sorted(set(verification["pending"]) | {GAME_TRACE_INDEX_DESTINATION})

    proposals = [
        *skill_proposals,
        *runtime_proposals,
        *template_proposals,
        *doc_proposals,
        *router_proposals,
    ]
    return {
        "project_mode": PROJECT_MODE,
        "project_mode_version": PROJECT_MODE_VERSION,
        "previous_project_mode": previous_project_mode,
        "project_mode_changed": previous_project_mode != PROJECT_MODE,
        "project_mode_docs": docs,
        "project_mode_templates_copied": template_count,
        "project_mode_skill": GAME_SKILL,
        "project_mode_runtime": runtime_files,
        "project_mode_verification": verification,
        "project_mode_activation_pending": (
            verification["status"] == "pending" or bool(proposals) or not trace_verification.get("ok")
        ),
        "traceability": {
            "index": GAME_TRACE_INDEX_DESTINATION,
            "runtime": GAME_TRACE_RUNTIME_DESTINATION,
            "rebuild": trace_rebuild,
            "verification": trace_verification,
        },
        "game_project": metadata,
        "game_proposals": sorted(set(proposals)),
    }
