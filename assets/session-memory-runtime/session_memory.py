#!/usr/bin/env python3
"""Install and operate a durable, project-local session memory system."""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
import shutil
import sys
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator
from uuid import uuid4


VERSION = "1.0.0"
MEMORY_DIR = ".session-memory"
LOCK_NAME = "save.lock"
JOURNAL_NAME = "transaction.json"
INSTALL_MANIFEST = "install-manifest.json"
BLOCK_START = "<!-- session-memory:start -->"
BLOCK_END = "<!-- session-memory:end -->"
VALID_STATUSES = {"in_progress", "complete", "blocked", "paused"}
MAX_PAYLOAD_BYTES = 1_000_000
LIST_FIELDS = (
    "completion_criteria",
    "source_of_truth",
    "completed",
    "in_progress",
    "decisions",
    "constraints",
    "changed_files",
    "verification",
    "risks",
    "next_actions",
    "notes",
)


def configure_utf8_stdout() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure:
            reconfigure(encoding="utf-8")


def normalize_text(value: str) -> str:
    return value.replace("\r\n", "\n").replace("\r", "\n").rstrip() + "\n"


def json_bytes(value: object, *, compact: bool = False) -> bytes:
    if compact:
        return (json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n").encode("utf-8")
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def hash_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        with temporary.open("wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def safe_target(value: str | None, *, allow_home: bool = False) -> Path:
    start = Path(value or os.getcwd()).expanduser().resolve()
    if start.is_file():
        start = start.parent
    if value is None:
        for candidate in (start, *start.parents):
            signals = (
                candidate / MEMORY_DIR,
                candidate / ".git",
                candidate / "AGENTS.md",
                candidate / "CLAUDE.md",
                candidate / "raw",
                candidate / "wiki",
            )
            if any(path.exists() for path in signals):
                start = candidate
                break
    if not start.is_dir():
        raise ValueError(f"Target must be an existing directory: {start}")
    if start == Path(start.anchor):
        raise ValueError("Refusing to operate on a filesystem root.")
    if not allow_home and start == Path.home().resolve():
        raise ValueError("Refusing to operate on the user home directory.")
    return start


def process_is_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if pid == os.getpid():
        return True
    if os.name == "nt":
        process_query_limited_information = 0x1000
        handle = ctypes.windll.kernel32.OpenProcess(process_query_limited_information, False, pid)
        if handle:
            ctypes.windll.kernel32.CloseHandle(handle)
            return True
        return ctypes.get_last_error() == 5
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected a JSON object: {path}")
    return payload


def read_json_if_exists(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    return read_json(path)


@contextmanager
def memory_lock(root: Path, *, purpose: str, token: str | None = None) -> Iterator[str]:
    memory = root / MEMORY_DIR
    memory.mkdir(parents=True, exist_ok=True)
    lock = memory / LOCK_NAME
    owner_token = token or uuid4().hex
    payload = {
        "token": owner_token,
        "pid": os.getpid(),
        "purpose": purpose,
        "started_at": datetime.now().astimezone().isoformat(),
    }
    try:
        descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as error:
        raise RuntimeError(f"Session memory is locked: {lock}") from error
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, ensure_ascii=False)
            handle.flush()
            os.fsync(handle.fileno())
        yield owner_token
    finally:
        try:
            current = read_json(lock)
        except (FileNotFoundError, json.JSONDecodeError, OSError, ValueError):
            current = {}
        if current.get("token") == owner_token:
            try:
                lock.unlink()
            except FileNotFoundError:
                pass


def router_block(host: str) -> str:
    label = "Codex/AGENTS" if host == "agents" else "Claude"
    return normalize_text(
        f"""\
{BLOCK_START}
## Session memory router ({label})

- At every new session, read root `log.md` before acting.
- When the user enters `SAVE`, use the project-local `session-memory` skill.
- `SAVE` preserves the current goal, progress, decisions, changed files, verification, risks, and next actions.
- Read `.session-memory/index.jsonl` or run the session runtime `history` command only when older context is needed.
- Treat every file under `.session-memory/sessions/` as an immutable session artifact.
- Do not include secrets, authentication tokens, or raw environment-variable values in session records.
{BLOCK_END}"""
    )


def merge_block(existing: str, block: str) -> str:
    existing = existing.replace("\r\n", "\n").replace("\r", "\n")
    start = existing.find(BLOCK_START)
    end = existing.find(BLOCK_END)
    if start >= 0 or end >= 0:
        if start < 0 or end < start:
            raise ValueError("Found an incomplete session-memory managed block.")
        end += len(BLOCK_END)
        prefix = existing[:start].rstrip()
        merged = (prefix + "\n\n" if prefix else "") + block.rstrip() + existing[end:]
        return normalize_text(merged)
    if not existing.strip():
        return block
    return normalize_text(existing.rstrip() + "\n\n" + block.rstrip())


def session_operations() -> str:
    return normalize_text(
        """\
# Session operations

## Session start

- Read root `log.md` first.
- Use `.session-memory/index.jsonl` or `history` only when earlier context is necessary.
- Open a specific immutable session JSON only when detailed evidence is required.

## SAVE

When the user enters `SAVE`:

1. Summarize only confirmed current state into the session payload.
2. Preserve the current goal, completion criteria, source of truth, progress, decisions, constraints, changed files, verification, risks, and next actions.
3. Run the project-local `session-memory` skill.
4. Confirm the returned session ID and `verified: true`.
5. Stop after reporting the saved state unless the user requested more work.

Never store secrets or claim unexecuted work as complete.
"""
    )


def initial_log(project_name: str) -> str:
    now = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M %Z")
    return normalize_text(
        f"""\
# 세션 로그

업데이트: {now}

## 프로젝트 목표

- `{project_name}`의 첫 SAVE에서 현재 목표를 기록한다.

## 핵심 구조와 Source of Truth

- 최신 상태: `log.md`
- 세션 색인: `.session-memory/index.jsonl`
- 불변 기록: `.session-memory/sessions/`

## 현재 진행 상황

- 세션 메모리 체계 설치 완료
- 저장된 작업 세션 없음

## 주요 결정과 제약

- 확인된 상태만 기록한다.
- 비밀값은 세션 기록에 넣지 않는다.

## 다음 작업

1. 실제 작업을 진행한다.
2. 작업 종료 시 `SAVE`를 단독으로 입력한다.
"""
    )


def local_skill() -> str:
    return normalize_text(
        """\
---
name: session-memory
description: 사용자가 `SAVE`를 단독으로 입력하거나 세션 저장·다음 작업 인수인계를 요청하면 현재 상태를 log, changelog, index와 불변 JSON에 원자적으로 저장하고 검증한다. "SAVE", "세션 저장", "다음에 이어서", "작업 상태 보존" 요청에 사용한다.
---

# Session Memory

1. `.session-memory/scripts/session_memory.py status`로 저장 상태와 미완료 트랜잭션을 확인한다.
2. 현재 대화와 실제 실행 결과만 사용해 `.session-memory/pending/<unique>.json` payload를 만든다.
3. 다음을 실행한다.

   ```text
   python ".session-memory/scripts/session_memory.py" save \
     --payload-file ".session-memory/pending/<unique>.json" \
     --consume-payload
   ```

4. `verified: true`, 세션 ID, 순번, 다음 행동을 확인해 보고한다.

필수 payload 필드는 `title`, `objective`, `status`, `summary`다. 상태는 `in_progress|complete|blocked|paused`이며 진행 중이면 `next_actions`가 필요하다. 완료하지 않은 작업과 실행하지 않은 검증을 기록하지 않는다. 비밀값을 저장하지 않는다. SAVE 뒤에는 요청받지 않은 새 작업을 계속하지 않는다.
"""
    )


def local_openai_yaml() -> str:
    return normalize_text(
        """\
interface:
  display_name: "Session Memory"
  short_description: "Save and verify resumable project session state"
  default_prompt: "Use $session-memory to save the current project state for the next session."
"""
    )


def installer_files(root: Path, project_name: str) -> tuple[dict[str, bytes], set[str], list[str]]:
    config = {
        "schema_version": 1,
        "runtime_version": VERSION,
        "project_name": project_name,
        "latest_log": "log.md",
        "changelog": "changelog.md",
        "index": f"{MEMORY_DIR}/index.jsonl",
        "state": f"{MEMORY_DIR}/state.json",
        "sessions": f"{MEMORY_DIR}/sessions",
    }
    source = Path(__file__).read_text(encoding="utf-8-sig")
    files = {
        f"{MEMORY_DIR}/config.json": json_bytes(config),
        f"{MEMORY_DIR}/scripts/session_memory.py": normalize_text(source).encode("utf-8"),
        "instructions/session-operations.md": session_operations().encode("utf-8"),
        "log.md": initial_log(project_name).encode("utf-8"),
        "changelog.md": normalize_text(
            "# 세션 변경 이력\n\n각 `SAVE`의 핵심 상태와 불변 세션 JSON 링크를 아래에 누적한다.\n"
        ).encode("utf-8"),
        ".agents/skills/session-memory/SKILL.md": local_skill().encode("utf-8"),
        ".agents/skills/session-memory/agents/openai.yaml": local_openai_yaml().encode("utf-8"),
        ".claude/skills/session-memory/SKILL.md": local_skill().encode("utf-8"),
        ".claude/skills/session-memory/agents/openai.yaml": local_openai_yaml().encode("utf-8"),
    }
    mutable = {"instructions/session-operations.md", "log.md", "changelog.md"}
    directories = [
        f"{MEMORY_DIR}/pending",
        f"{MEMORY_DIR}/sessions",
        f"{MEMORY_DIR}/transactions",
    ]
    return files, mutable, directories


def safe_remove_transaction(root: Path, transaction: Path) -> None:
    transactions = (root / MEMORY_DIR / "transactions").resolve()
    resolved = transaction.resolve()
    if resolved.parent != transactions or not resolved.name:
        raise RuntimeError(f"Refusing to remove an invalid transaction path: {resolved}")
    if resolved.is_dir():
        shutil.rmtree(resolved)


def replace_target(stage: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    os.replace(stage, target)


def validate_journal(root: Path, journal: dict[str, Any]) -> list[dict[str, Any]]:
    if Path(str(journal.get("root", ""))).resolve() != root.resolve():
        raise RuntimeError("Transaction journal root does not match the target.")
    transaction_id = str(journal.get("transaction_id", ""))
    transaction = (root / MEMORY_DIR / "transactions" / transaction_id).resolve()
    expected_parent = (root / MEMORY_DIR / "transactions").resolve()
    if not transaction_id or transaction.parent != expected_parent:
        raise RuntimeError("Transaction journal has an invalid transaction path.")
    rows = journal.get("rows")
    if not isinstance(rows, list) or not rows:
        raise RuntimeError("Transaction journal has no rows.")
    for row in rows:
        if not isinstance(row, dict):
            raise RuntimeError("Transaction journal row is invalid.")
        target = Path(str(row.get("target", ""))).resolve()
        stage = Path(str(row.get("stage", ""))).resolve()
        backup = Path(str(row.get("backup", ""))).resolve()
        if not inside(target, root):
            raise RuntimeError(f"Transaction target escaped project root: {target}")
        if not inside(stage, transaction) or not inside(backup, transaction):
            raise RuntimeError("Transaction stage or backup escaped the transaction directory.")
    return rows


def rollback_journal(root: Path, journal: dict[str, Any]) -> None:
    rows = validate_journal(root, journal)
    for row in reversed(rows):
        target = Path(str(row["target"]))
        backup = Path(str(row["backup"]))
        existed = bool(row["existed"])
        old_hash = row.get("old_hash")
        new_hash = str(row["new_hash"])
        current_hash = hash_file(target) if target.is_file() else None
        if target.exists() and not target.is_file():
            raise RuntimeError(f"Recovery target is not a file: {target}")
        if existed:
            if not backup.is_file() or not isinstance(old_hash, str) or hash_file(backup) != old_hash:
                raise RuntimeError(f"Recovery backup failed verification: {backup}")
            if current_hash not in {old_hash, new_hash, None}:
                raise RuntimeError(f"Recovery found an independently changed target: {target}")
            if current_hash != old_hash:
                atomic_write(target, backup.read_bytes())
        else:
            if current_hash is not None and current_hash != new_hash:
                raise RuntimeError(f"Recovery found an independently created target: {target}")
            if current_hash == new_hash:
                target.unlink()
    journal_path = root / MEMORY_DIR / JOURNAL_NAME
    try:
        journal_path.unlink()
    except FileNotFoundError:
        pass
    transaction = root / MEMORY_DIR / "transactions" / str(journal["transaction_id"])
    try:
        safe_remove_transaction(root, transaction)
    except OSError:
        pass


def prepare_recovery(root: Path) -> dict[str, Any] | None:
    memory = root / MEMORY_DIR
    journal_path = memory / JOURNAL_NAME
    lock_path = memory / LOCK_NAME
    if not journal_path.is_file():
        if lock_path.is_file():
            lock = read_json(lock_path)
            pid = int(lock.get("pid", -1))
            if process_is_alive(pid):
                raise RuntimeError("Session memory lock owner is still active.")
            lock_path.unlink()
        return None
    journal = read_json(journal_path)
    if lock_path.is_file():
        lock = read_json(lock_path)
        pid = int(lock.get("pid", -1))
        if process_is_alive(pid):
            raise RuntimeError("A session transaction is still active.")
        if lock.get("token") != journal.get("owner_token"):
            raise RuntimeError("Stale lock token does not match the transaction journal.")
        lock_path.unlink()
    return journal


def recover(root: Path) -> dict[str, Any]:
    journal = prepare_recovery(root)
    if journal is None:
        return {"status": "no_recovery_needed", "target": str(root)}
    with memory_lock(root, purpose="recover"):
        rollback_journal(root, journal)
    return {
        "status": "recovered",
        "target": str(root),
        "transaction_id": journal.get("transaction_id"),
        "action": journal.get("action"),
    }


def commit_transaction(
    root: Path,
    updates: dict[str, bytes],
    *,
    action: str,
    owner_token: str,
) -> str:
    if not updates:
        raise ValueError("Transaction has no updates.")
    transaction_id = datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid4().hex[:8]
    transaction = root / MEMORY_DIR / "transactions" / transaction_id
    stage_root = transaction / "stage"
    backup_root = transaction / "backup"
    rows: list[dict[str, Any]] = []
    journal_path = root / MEMORY_DIR / JOURNAL_NAME
    journal: dict[str, Any] = {
        "schema_version": 1,
        "transaction_id": transaction_id,
        "root": str(root.resolve()),
        "action": action,
        "owner_token": owner_token,
        "started_at": datetime.now().astimezone().isoformat(),
        "rows": rows,
    }
    try:
        for relative, payload in sorted(updates.items()):
            target = (root / relative).resolve()
            if not inside(target, root):
                raise RuntimeError(f"Transaction target escaped project root: {target}")
            if target.exists() and not target.is_file():
                raise FileExistsError(f"Transaction target is not a file: {target}")
            stage = stage_root / relative
            backup = backup_root / relative
            existed = target.is_file()
            old_hash = hash_file(target) if existed else None
            if existed:
                atomic_write(backup, target.read_bytes())
            atomic_write(stage, payload)
            rows.append(
                {
                    "relative": relative,
                    "target": str(target),
                    "stage": str(stage.resolve()),
                    "backup": str(backup.resolve()),
                    "existed": existed,
                    "old_hash": old_hash,
                    "new_hash": hash_bytes(payload),
                    "applied": False,
                }
            )
        atomic_write(journal_path, json_bytes(journal))
        for row in rows:
            replace_target(Path(str(row["stage"])), Path(str(row["target"])))
            row["applied"] = True
            atomic_write(journal_path, json_bytes(journal))
        for row in rows:
            target = Path(str(row["target"]))
            if not target.is_file() or hash_file(target) != row["new_hash"]:
                raise RuntimeError(f"Transaction verification failed: {target}")
        try:
            journal_path.unlink()
        except FileNotFoundError:
            pass
        try:
            safe_remove_transaction(root, transaction)
        except OSError:
            pass
        return transaction_id
    except BaseException:
        if journal_path.is_file():
            rollback_journal(root, read_json(journal_path))
        elif transaction.is_dir():
            safe_remove_transaction(root, transaction)
        raise


def setup_plan(
    root: Path,
    *,
    project_name: str,
    force_managed: bool,
) -> tuple[dict[str, bytes], list[str], list[str], list[str], dict[str, str]]:
    files, mutable, directories = installer_files(root, project_name)
    manifest_path = root / MEMORY_DIR / INSTALL_MANIFEST
    old_manifest = read_json_if_exists(manifest_path)
    previous_hashes = old_manifest.get("managed_files", {})
    if not isinstance(previous_hashes, dict):
        previous_hashes = {}
    updates: dict[str, bytes] = {}
    preserved: list[str] = []
    conflicts: list[str] = []
    managed_hashes: dict[str, str] = {}

    for relative, host in (("AGENTS.md", "agents"), ("CLAUDE.md", "claude")):
        path = root / relative
        existing = path.read_text(encoding="utf-8-sig") if path.is_file() else ""
        merged = merge_block(existing, router_block(host)).encode("utf-8")
        if not path.is_file() or path.read_bytes() != merged:
            updates[relative] = merged
        managed_hashes[relative] = hash_bytes(merged)

    for relative, payload in files.items():
        path = root / relative
        if path.exists() and not path.is_file():
            conflicts.append(relative)
            continue
        if not path.is_file():
            updates[relative] = payload
            if relative not in mutable:
                managed_hashes[relative] = hash_bytes(payload)
            continue
        current = path.read_bytes()
        current_hash = hash_bytes(current)
        if current == payload:
            if relative not in mutable:
                managed_hashes[relative] = hash_bytes(payload)
            continue
        if relative in mutable:
            preserved.append(relative)
            continue
        previous = previous_hashes.get(relative)
        if force_managed or (isinstance(previous, str) and previous == current_hash):
            updates[relative] = payload
            managed_hashes[relative] = hash_bytes(payload)
        else:
            conflicts.append(relative)

    installed_at = old_manifest.get("installed_at")
    if not isinstance(installed_at, str):
        installed_at = datetime.now().astimezone().isoformat()
    manifest = {
        "schema_version": 1,
        "installer": "save-session-state",
        "installer_version": VERSION,
        "installed_at": installed_at,
        "project_name": project_name,
        "managed_files": dict(sorted(managed_hashes.items())),
    }
    manifest_payload = json_bytes(manifest)
    if not manifest_path.is_file() or manifest_path.read_bytes() != manifest_payload:
        updates[f"{MEMORY_DIR}/{INSTALL_MANIFEST}"] = manifest_payload
    return updates, preserved, conflicts, directories, managed_hashes


def setup_system(
    root: Path,
    *,
    project_name: str,
    force_managed: bool,
    dry_run: bool,
) -> dict[str, Any]:
    if not project_name.strip():
        raise ValueError("Project name cannot be empty.")
    if not dry_run and (
        (root / MEMORY_DIR / JOURNAL_NAME).is_file() or (root / MEMORY_DIR / LOCK_NAME).is_file()
    ):
        recover(root)
    if dry_run:
        updates, preserved, conflicts, directories, _managed = setup_plan(
            root,
            project_name=project_name,
            force_managed=force_managed,
        )
        result: dict[str, Any] = {
            "target": str(root),
            "version": VERSION,
            "created_files": [relative for relative in updates if not (root / relative).is_file()],
            "updated_files": [relative for relative in updates if (root / relative).is_file()],
            "created_directories": [relative for relative in directories if not (root / relative).is_dir()],
            "preserved_files": preserved,
            "conflicts": conflicts,
            "dry_run": True,
        }
        result["status"] = "dry_run"
        return result
    with memory_lock(root, purpose="setup") as token:
        updates, preserved, conflicts, directories, _managed = setup_plan(
            root,
            project_name=project_name,
            force_managed=force_managed,
        )
        created_directories = [relative for relative in directories if not (root / relative).is_dir()]
        result = {
            "target": str(root),
            "version": VERSION,
            "created_files": [relative for relative in updates if not (root / relative).is_file()],
            "updated_files": [relative for relative in updates if (root / relative).is_file()],
            "created_directories": created_directories,
            "preserved_files": preserved,
            "conflicts": conflicts,
            "dry_run": False,
        }
        for relative in directories:
            path = root / relative
            if path.exists() and not path.is_dir():
                raise FileExistsError(f"Required directory path is a file: {path}")
            path.mkdir(parents=True, exist_ok=True)
        if updates:
            transaction_id = commit_transaction(root, updates, action="setup", owner_token=token)
            result["transaction_id"] = transaction_id
    if conflicts:
        result["status"] = "completed_with_conflicts"
    elif updates or created_directories:
        result["status"] = "completed"
    else:
        result["status"] = "no_changes"
    result["configured"] = (root / MEMORY_DIR / "config.json").is_file()
    return result


def normalize_payload(payload: dict[str, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    for field in ("title", "objective", "status", "summary"):
        value = payload.get(field)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"Payload field must be a non-empty string: {field}")
        normalized[field] = value.strip()
    if normalized["status"] not in VALID_STATUSES:
        raise ValueError(f"Payload status must be one of: {', '.join(sorted(VALID_STATUSES))}")
    for field in LIST_FIELDS:
        value = payload.get(field, [])
        if value is None:
            value = []
        if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
            raise ValueError(f"Payload field must be a list of strings: {field}")
        normalized[field] = [item.strip() for item in value if item.strip()]
    if normalized["status"] == "in_progress" and not normalized["next_actions"]:
        raise ValueError("An in_progress session requires at least one next action.")
    source_thread = payload.get("source_thread")
    if source_thread is not None:
        if not isinstance(source_thread, str):
            raise ValueError("source_thread must be a string when provided.")
        source_thread = source_thread.strip()
    normalized["source_thread"] = source_thread or None
    return normalized


def load_payload(args: argparse.Namespace, root: Path) -> tuple[dict[str, Any], Path | None]:
    source_path: Path | None = None
    if args.payload_file:
        source_path = Path(args.payload_file).expanduser()
        if not source_path.is_absolute():
            source_path = root / source_path
        source_path = source_path.resolve()
        if not source_path.is_file():
            raise FileNotFoundError(source_path)
        if source_path.stat().st_size > MAX_PAYLOAD_BYTES:
            raise ValueError("Session payload exceeds the 1 MB limit.")
        payload = read_json(source_path)
    elif args.payload_json:
        if len(args.payload_json.encode("utf-8")) > MAX_PAYLOAD_BYTES:
            raise ValueError("Session payload exceeds the 1 MB limit.")
        payload = json.loads(args.payload_json)
        if not isinstance(payload, dict):
            raise ValueError("Payload JSON must be an object.")
    else:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("Payload JSON must be an object.")
        if len(json.dumps(payload, ensure_ascii=False).encode("utf-8")) > MAX_PAYLOAD_BYTES:
            raise ValueError("Session payload exceeds the 1 MB limit.")
    return normalize_payload(payload), source_path


def bullet_section(title: str, values: list[str], *, fallback: str = "- 없음") -> str:
    if values:
        body = "\n".join(f"- {value}" for value in values)
    else:
        body = fallback
    return f"## {title}\n\n{body}\n"


def numbered_section(title: str, values: list[str]) -> str:
    body = "\n".join(f"{index}. {value}" for index, value in enumerate(values, 1)) if values else "1. 없음"
    return f"## {title}\n\n{body}\n"


def render_log(payload: dict[str, Any], *, saved_at: str, session_id: str, session_file: str) -> str:
    progress = list(payload["completed"])
    progress.extend(f"[진행 중] {item}" for item in payload["in_progress"])
    decisions = list(payload["decisions"])
    decisions.extend(f"[제약] {item}" for item in payload["constraints"])
    return normalize_text(
        f"""\
# 세션 로그

업데이트: {saved_at}
세션 ID: `{session_id}`
상태: `{payload['status']}`

## 프로젝트 목표

- {payload['objective']}
- 현재 요약: {payload['summary']}

{bullet_section("완료 기준", payload["completion_criteria"])}
{bullet_section("핵심 구조와 Source of Truth", payload["source_of_truth"])}
{bullet_section("현재 진행 상황", progress)}
{bullet_section("주요 결정과 제약", decisions)}
{bullet_section("변경 파일", payload["changed_files"])}
{bullet_section("검증 결과", payload["verification"])}
{bullet_section("남은 위험 또는 확인 필요", payload["risks"])}
{numbered_section("다음 작업", payload["next_actions"])}
{bullet_section("추가 메모", payload["notes"])}
## 저장 위치

- 불변 기록: `{session_file}`
- 전체 색인: `.session-memory/index.jsonl`
- 누적 이력: `changelog.md`
"""
    )


def compact_list(values: list[str], limit: int = 3) -> str:
    if not values:
        return "없음"
    selected = values[:limit]
    suffix = f" 외 {len(values) - limit}건" if len(values) > limit else ""
    return "; ".join(selected) + suffix


def changelog_entry(
    payload: dict[str, Any],
    *,
    saved_at: str,
    session_id: str,
    sequence: int,
    session_file: str,
    previous_log_file: str | None,
) -> str:
    previous_line = f"- 교체 전 로그: `{previous_log_file}`\n" if previous_log_file else ""
    return normalize_text(
        f"""\
## {saved_at} — {payload['title']} [session:{session_id}]

- 순번: {sequence}
- 상태: `{payload['status']}`
- 목표: {payload['objective']}
- 요약: {payload['summary']}
- 완료: {compact_list(payload['completed'])}
- 주요 결정: {compact_list(payload['decisions'])}
- 검증: {compact_list(payload['verification'])}
- 다음 단계: {compact_list(payload['next_actions'])}
- 불변 기록: `{session_file}`
{previous_line}"""
    )


def verify_system(root: Path) -> dict[str, Any]:
    memory = root / MEMORY_DIR
    issues: list[str] = []
    state_path = memory / "state.json"
    if not state_path.is_file():
        configured = (memory / "config.json").is_file()
        if not configured:
            issues.append("Session memory is not configured.")
        if (memory / JOURNAL_NAME).exists():
            issues.append("An unfinished transaction journal exists.")
        return {
            "target": str(root),
            "configured": configured,
            "has_saved_sessions": False,
            "verified": configured and not issues,
            "issues": issues,
        }
    state = read_json(state_path)
    session_relative = state.get("latest_session_file")
    session_id = state.get("latest_session_id")
    if not isinstance(session_relative, str) or not isinstance(session_id, str):
        issues.append("State is missing the latest session reference.")
        session_path = None
    else:
        session_path = root / session_relative
        if not session_path.is_file():
            issues.append("Latest immutable session file is missing.")
        elif hash_file(session_path) != state.get("latest_session_sha256"):
            issues.append("Latest immutable session hash does not match state.")
        else:
            try:
                record = read_json(session_path)
            except (json.JSONDecodeError, OSError, ValueError):
                record = {}
                issues.append("Latest immutable session record is invalid.")
            if record.get("session_id") != session_id:
                issues.append("Latest immutable session ID does not match state.")
            if record.get("sequence") != state.get("latest_sequence"):
                issues.append("Latest immutable session sequence does not match state.")
            if record.get("log_sha256") != state.get("latest_log_sha256"):
                issues.append("Latest immutable session log hash does not match state.")
            previous_log_file = record.get("previous_log_file")
            previous_log_hash = record.get("previous_log_sha256")
            if previous_log_file is not None:
                if not isinstance(previous_log_file, str) or not isinstance(previous_log_hash, str):
                    issues.append("Previous log archive metadata is invalid.")
                else:
                    previous_path = root / previous_log_file
                    if not previous_path.is_file() or hash_file(previous_path) != previous_log_hash:
                        issues.append("Previous log archive is missing or has a hash mismatch.")
    log_path = root / "log.md"
    if not log_path.is_file():
        issues.append("Latest log.md is missing.")
    elif hash_file(log_path) != state.get("latest_log_sha256"):
        issues.append("Latest log.md hash does not match state.")
    index_path = memory / "index.jsonl"
    if not index_path.is_file():
        issues.append("Session index is missing.")
    else:
        lines = [line for line in index_path.read_text(encoding="utf-8-sig").splitlines() if line.strip()]
        try:
            latest_index = json.loads(lines[-1]) if lines else {}
        except json.JSONDecodeError:
            latest_index = {}
            issues.append("Latest index row is invalid JSON.")
        if latest_index.get("session_id") != session_id:
            issues.append("Session index latest ID does not match state.")
        if latest_index.get("sequence") != state.get("latest_sequence"):
            issues.append("Session index latest sequence does not match state.")
    changelog = root / "changelog.md"
    if not changelog.is_file() or f"[session:{session_id}]" not in changelog.read_text(encoding="utf-8-sig"):
        issues.append("Changelog does not contain the latest session marker.")
    if (memory / JOURNAL_NAME).exists():
        issues.append("An unfinished transaction journal exists.")
    if (memory / LOCK_NAME).exists():
        issues.append("A session-memory lock remains.")
    return {
        "target": str(root),
        "configured": (memory / "config.json").is_file(),
        "has_saved_sessions": True,
        "latest_session_id": session_id,
        "latest_sequence": state.get("latest_sequence"),
        "verified": not issues,
        "issues": issues,
    }


def build_save_updates(
    root: Path,
    payload: dict[str, Any],
) -> tuple[dict[str, bytes], dict[str, Any]]:
    memory = root / MEMORY_DIR
    state = read_json_if_exists(memory / "state.json")
    previous_sequence = state.get("latest_sequence", 0)
    if not isinstance(previous_sequence, int) or previous_sequence < 0:
        raise RuntimeError("Session state has an invalid sequence.")
    sequence = previous_sequence + 1
    now = datetime.now().astimezone()
    saved_at = now.isoformat(timespec="seconds")
    session_id = ""
    session_relative = ""
    for _attempt in range(10):
        session_id = now.strftime("%Y%m%d-%H%M%S") + "-" + uuid4().hex[:12]
        session_relative = f"{MEMORY_DIR}/sessions/{now:%Y}/{now:%m}/{session_id}.json"
        if not (root / session_relative).exists():
            break
    else:
        raise RuntimeError("Could not allocate a unique immutable session ID.")
    log_relative = "log.md"
    previous_log = (root / log_relative).read_bytes() if (root / log_relative).is_file() else b""
    previous_log_relative = (
        f"{MEMORY_DIR}/sessions/{now:%Y}/{now:%m}/{session_id}.previous-log.md" if previous_log else None
    )
    log_text = render_log(payload, saved_at=saved_at, session_id=session_id, session_file=session_relative)
    log_payload = log_text.encode("utf-8")

    record = {
        "schema_version": 1,
        "session_id": session_id,
        "sequence": sequence,
        "saved_at": saved_at,
        "runtime_version": VERSION,
        "previous_session_id": state.get("latest_session_id"),
        "previous_log_file": previous_log_relative,
        "previous_log_sha256": hash_bytes(previous_log) if previous_log else None,
        "log_sha256": hash_bytes(log_payload),
        **payload,
    }
    record_payload = json_bytes(record)
    existing_changelog = (
        (root / "changelog.md").read_text(encoding="utf-8-sig")
        if (root / "changelog.md").is_file()
        else "# 세션 변경 이력\n"
    )
    changelog_payload = normalize_text(
        existing_changelog.rstrip()
        + "\n\n"
        + changelog_entry(
            payload,
            saved_at=saved_at,
            session_id=session_id,
            sequence=sequence,
            session_file=session_relative,
            previous_log_file=previous_log_relative,
        ).rstrip()
    ).encode("utf-8")
    index_path = memory / "index.jsonl"
    existing_index = index_path.read_text(encoding="utf-8-sig") if index_path.is_file() else ""
    index_row = {
        "session_id": session_id,
        "sequence": sequence,
        "saved_at": saved_at,
        "title": payload["title"],
        "objective": payload["objective"],
        "status": payload["status"],
        "summary": payload["summary"],
        "session_file": session_relative,
        "source_thread": payload.get("source_thread"),
    }
    index_payload = (
        existing_index.rstrip() + ("\n" if existing_index.strip() else "")
    ).encode("utf-8") + json_bytes(index_row, compact=True)
    state_payload = json_bytes(
        {
            "schema_version": 1,
            "latest_sequence": sequence,
            "latest_session_id": session_id,
            "latest_session_file": session_relative,
            "latest_session_sha256": hash_bytes(record_payload),
            "latest_log_sha256": hash_bytes(log_payload),
            "saved_at": saved_at,
        }
    )
    updates = {
        session_relative: record_payload,
        log_relative: log_payload,
        "changelog.md": changelog_payload,
        f"{MEMORY_DIR}/index.jsonl": index_payload,
        f"{MEMORY_DIR}/state.json": state_payload,
    }
    if previous_log_relative is not None:
        updates[previous_log_relative] = previous_log
    metadata = {
        "session_id": session_id,
        "sequence": sequence,
        "session_file": session_relative,
    }
    return updates, metadata


def save_session(
    root: Path,
    payload: dict[str, Any],
    *,
    payload_path: Path | None,
    consume_payload: bool,
) -> dict[str, Any]:
    memory = root / MEMORY_DIR
    if not (memory / "config.json").is_file():
        raise RuntimeError("Session memory is not configured. Run setup first.")
    if consume_payload:
        if payload_path is None:
            raise ValueError("--consume-payload requires --payload-file.")
        pending = (memory / "pending").resolve()
        if payload_path.parent.resolve() != pending:
            raise ValueError("Only payload files directly inside .session-memory/pending may be consumed.")
    if (memory / JOURNAL_NAME).is_file() or (memory / LOCK_NAME).is_file():
        recover(root)
    with memory_lock(root, purpose="save") as token:
        updates, metadata = build_save_updates(root, payload)
        transaction_id = commit_transaction(root, updates, action="save", owner_token=token)
    verification = verify_system(root)
    if not verification["verified"]:
        raise RuntimeError("Save committed but verification failed: " + "; ".join(verification["issues"]))
    consumed = False
    cleanup_warning: str | None = None
    if consume_payload:
        assert payload_path is not None
        try:
            payload_path.unlink()
            consumed = True
        except OSError as error:
            cleanup_warning = f"Session was saved, but the pending payload could not be removed: {error}"
    return {
        "status": "saved",
        "target": str(root),
        "session_id": metadata["session_id"],
        "sequence": metadata["sequence"],
        "session_file": metadata["session_file"],
        "transaction_id": transaction_id,
        "verified": True,
        "payload_consumed": consumed,
        "cleanup_warning": cleanup_warning,
        "objective": payload["objective"],
        "session_status": payload["status"],
        "next_actions": payload["next_actions"],
    }


def history(root: Path, limit: int) -> dict[str, Any]:
    if limit < 1 or limit > 100:
        raise ValueError("History limit must be between 1 and 100.")
    index = root / MEMORY_DIR / "index.jsonl"
    if not index.is_file():
        return {"target": str(root), "count": 0, "sessions": []}
    rows: list[dict[str, Any]] = []
    for number, line in enumerate(index.read_text(encoding="utf-8-sig").splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as error:
            raise ValueError(f"Invalid JSONL at line {number}: {index}") from error
        if not isinstance(row, dict):
            raise ValueError(f"Invalid index row at line {number}: {index}")
        rows.append(row)
    selected = rows[-limit:]
    return {"target": str(root), "total": len(rows), "count": len(selected), "sessions": selected}


def show_session(root: Path, session_id: str) -> dict[str, Any]:
    state = read_json_if_exists(root / MEMORY_DIR / "state.json")
    wanted = state.get("latest_session_id") if session_id == "latest" else session_id
    if not isinstance(wanted, str) or not wanted:
        raise ValueError("No latest session exists.")
    entries = history(root, 100)["sessions"]
    match = next((row for row in reversed(entries) if row.get("session_id") == wanted), None)
    if match is None:
        candidates = list((root / MEMORY_DIR / "sessions").rglob(f"{wanted}.json"))
        if len(candidates) != 1:
            raise FileNotFoundError(f"Session not found: {wanted}")
        session_path = candidates[0]
    else:
        session_path = root / str(match["session_file"])
    record = read_json(session_path)
    return {
        "target": str(root),
        "session_file": session_path.relative_to(root).as_posix(),
        "record": record,
    }


def status(root: Path) -> dict[str, Any]:
    memory = root / MEMORY_DIR
    state = read_json_if_exists(memory / "state.json")
    journal = read_json_if_exists(memory / JOURNAL_NAME)
    lock = read_json_if_exists(memory / LOCK_NAME)
    return {
        "target": str(root),
        "configured": (memory / "config.json").is_file(),
        "runtime": str(memory / "scripts" / "session_memory.py"),
        "latest_log": str(root / "log.md"),
        "latest_session_id": state.get("latest_session_id"),
        "latest_sequence": state.get("latest_sequence", 0),
        "unfinished_transaction": journal.get("transaction_id"),
        "lock": {
            "present": bool(lock),
            "pid": lock.get("pid"),
            "alive": process_is_alive(int(lock.get("pid", -1))) if lock else False,
        },
    }


def main() -> int:
    configure_utf8_stdout()
    parser = argparse.ArgumentParser(description="Durable project session memory")
    subparsers = parser.add_subparsers(dest="command", required=True)

    for name in ("status", "verify", "recover"):
        child = subparsers.add_parser(name)
        child.add_argument("--target")
        child.add_argument("--allow-home", action="store_true")

    setup_parser = subparsers.add_parser("setup")
    setup_parser.add_argument("--target")
    setup_parser.add_argument("--project-name")
    setup_parser.add_argument("--force-managed", action="store_true")
    setup_parser.add_argument("--dry-run", action="store_true")
    setup_parser.add_argument("--allow-home", action="store_true")

    save_parser = subparsers.add_parser("save")
    save_parser.add_argument("--target")
    payload_group = save_parser.add_mutually_exclusive_group(required=True)
    payload_group.add_argument("--payload-file")
    payload_group.add_argument("--payload-json")
    payload_group.add_argument("--stdin", action="store_true")
    save_parser.add_argument("--consume-payload", action="store_true")
    save_parser.add_argument("--allow-home", action="store_true")

    history_parser = subparsers.add_parser("history")
    history_parser.add_argument("--target")
    history_parser.add_argument("--limit", type=int, default=10)
    history_parser.add_argument("--allow-home", action="store_true")

    show_parser = subparsers.add_parser("show")
    show_parser.add_argument("--target")
    show_parser.add_argument("--session-id", default="latest")
    show_parser.add_argument("--allow-home", action="store_true")

    args = parser.parse_args()
    try:
        root = safe_target(args.target, allow_home=args.allow_home)
        if args.command == "status":
            result = status(root)
        elif args.command == "setup":
            result = setup_system(
                root,
                project_name=(args.project_name or root.name).strip(),
                force_managed=args.force_managed,
                dry_run=args.dry_run,
            )
        elif args.command == "save":
            payload, payload_path = load_payload(args, root)
            result = save_session(
                root,
                payload,
                payload_path=payload_path,
                consume_payload=args.consume_payload,
            )
        elif args.command == "verify":
            result = verify_system(root)
        elif args.command == "recover":
            result = recover(root)
        elif args.command == "history":
            result = history(root, args.limit)
        else:
            result = show_session(root, args.session_id)
    except (FileNotFoundError, json.JSONDecodeError, OSError, RuntimeError, ValueError) as error:
        parser.error(str(error))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result.get("status") == "completed_with_conflicts":
        return 2
    if args.command == "verify" and not result.get("verified", False):
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
