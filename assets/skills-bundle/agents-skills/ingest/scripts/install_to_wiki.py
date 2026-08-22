#!/usr/bin/env python3
"""Install or recover the portable ingest skill in another LLM Wiki root."""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
import shutil
import sys
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterator
from uuid import uuid4

SCRIPT_ROOT = Path(__file__).resolve().parent
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

from find_uningested import configure_utf8_stdout, resolve_wiki_root


JOURNAL_NAME = ".ingest-skill-install-journal.json"
LOCK_NAME = ".ingest-skill-install.lock"


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        with temporary.open("w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


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


@contextmanager
def install_lock(
    target_root: Path,
    *,
    purpose: str = "install",
    token: str | None = None,
) -> Iterator[str]:
    lock_path = target_root / LOCK_NAME
    lease_token = token or uuid4().hex
    payload = {
        "token": lease_token,
        "pid": os.getpid(),
        "purpose": purpose,
        "started_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as error:
        raise RuntimeError(f"Another ingest skill install may be active: {lock_path}") from error
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False)
            handle.flush()
            os.fsync(handle.fileno())
        yield lease_token
    finally:
        try:
            current = read_json(lock_path)
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            current = {}
        if current.get("token") == lease_token:
            try:
                lock_path.unlink()
            except FileNotFoundError:
                pass


def source_vault() -> Path:
    return Path(__file__).resolve().parents[4]


def ignored(_directory: str, names: list[str]) -> set[str]:
    return {name for name in names if name == "__pycache__" or name.endswith(".pyc")}


def normalize_bundle(stage: Path) -> None:
    for bundled in stage.rglob("SKILL.md.bundled"):
        bundled.rename(bundled.with_name("SKILL.md"))


def tree_hash(path: Path) -> str:
    digest = hashlib.sha256()
    for file_path in sorted((item for item in path.rglob("*") if item.is_file()), key=lambda item: item.as_posix()):
        relative = file_path.relative_to(path).as_posix().encode("utf-8")
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        with file_path.open("rb") as handle:
            while chunk := handle.read(1024 * 1024):
                digest.update(chunk)
    return digest.hexdigest()


def package_specs(target_root: Path, transaction_id: str) -> list[dict[str, Any]]:
    source_root = source_vault()
    if (source_root / "skills-bundle").is_dir():
        rows = [
            ("agents", source_root / "skills-bundle" / "agents-skills" / "ingest", target_root / ".agents" / "skills" / "ingest"),
            ("claude", source_root / "skills-bundle" / "claude-adapters" / "ingest", target_root / ".claude" / "skills" / "ingest"),
        ]
    else:
        rows = [
            ("agents", source_root / ".agents" / "skills" / "ingest", target_root / ".agents" / "skills" / "ingest"),
            ("claude", source_root / ".claude" / "skills" / "ingest", target_root / ".claude" / "skills" / "ingest"),
        ]
    specs: list[dict[str, Any]] = []
    for name, source, destination in rows:
        if not source.is_dir():
            raise FileNotFoundError(f"Source skill package is missing: {source}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        stage = destination.parent / f".ingest-stage-{transaction_id}-{name}"
        backup = destination.parent / f"ingest.backup-{transaction_id}"
        if stage.exists() or backup.exists():
            raise FileExistsError(f"Install transaction path already exists: {stage} or {backup}")
        specs.append(
            {
                "name": name,
                "source": str(source),
                "destination": str(destination),
                "stage": str(stage),
                "backup": str(backup),
                "had_existing": destination.exists(),
                "before_hash": tree_hash(destination) if destination.is_dir() else None,
                "stage_hash": None,
                "installed": False,
            }
        )
    return specs


def validate_transaction_paths(target_root: Path, payload: dict[str, Any]) -> list[dict[str, Any]]:
    expected_destinations = {
        "agents": (target_root / ".agents" / "skills" / "ingest").resolve(),
        "claude": (target_root / ".claude" / "skills" / "ingest").resolve(),
    }
    packages = payload.get("packages")
    if not isinstance(packages, list) or {row.get("name") for row in packages} != set(expected_destinations):
        raise RuntimeError("Install journal has an invalid package set.")
    for row in packages:
        name = str(row["name"])
        destination = Path(str(row["destination"])).resolve()
        stage = Path(str(row["stage"])).resolve()
        backup = Path(str(row["backup"])).resolve()
        expected = expected_destinations[name]
        if destination != expected:
            raise RuntimeError(f"Install journal destination is outside the expected package path: {destination}")
        if stage.parent != expected.parent or not stage.name.startswith(".ingest-stage-"):
            raise RuntimeError(f"Install journal stage path is invalid: {stage}")
        if backup.parent != expected.parent or not backup.name.startswith("ingest.backup-"):
            raise RuntimeError(f"Install journal backup path is invalid: {backup}")
    return packages


def remove_tree(path: Path) -> None:
    if path.is_dir():
        shutil.rmtree(path)
    elif path.exists():
        path.unlink()


def rollback_transaction(
    target_root: Path,
    payload: dict[str, Any],
    *,
    after_step: Callable[[str], None] | None = None,
) -> None:
    packages = validate_transaction_paths(target_root, payload)
    for row in reversed(packages):
        destination = Path(str(row["destination"]))
        stage = Path(str(row["stage"]))
        backup = Path(str(row["backup"]))
        had_existing = bool(row["had_existing"])

        if had_existing and backup.exists():
            expected_hash = row.get("before_hash")
            if not backup.is_dir() or not expected_hash or tree_hash(backup) != expected_hash:
                raise RuntimeError(f"Backup verification failed; recovery stopped before replacing: {destination}")
            remove_tree(destination)
            os.replace(backup, destination)
        elif had_existing and not destination.exists():
            raise RuntimeError(f"Both original and backup are missing; recovery cannot continue: {destination}")
        elif not had_existing:
            remove_tree(destination)
        remove_tree(stage)
        if after_step is not None:
            after_step(f"{row['name']}_rolled_back")


def clear_stale_lock_for_recovery(target_root: Path, journal: dict[str, Any]) -> None:
    lock_path = target_root / LOCK_NAME
    if not lock_path.exists():
        return
    try:
        lock = read_json(lock_path)
        pid = int(lock.get("pid", -1))
    except (ValueError, TypeError, json.JSONDecodeError, OSError) as error:
        raise RuntimeError(f"Install lock is unreadable; refusing automatic recovery: {lock_path}") from error
    if process_is_alive(pid):
        raise RuntimeError("The install lock owner is still active; recovery was refused.")
    if lock.get("token") != journal.get("owner_token"):
        raise RuntimeError("Install lock token does not match the journal; recovery was refused.")
    lock_path.unlink()


def install(
    target_root: Path,
    *,
    replace: bool,
    after_step: Callable[[str], None] | None = None,
) -> dict[str, object]:
    target_root = resolve_wiki_root(target_root)
    journal_path = target_root / JOURNAL_NAME
    if journal_path.exists():
        raise RuntimeError(f"An unfinished install exists; run --recover first: {journal_path}")

    with install_lock(target_root) as token:
        transaction_id = f"{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid4().hex[:8]}"
        packages = package_specs(target_root, transaction_id)
        if not replace:
            existing = [row["destination"] for row in packages if row["had_existing"]]
            if existing:
                raise FileExistsError(
                    "Target skill already exists; inspect it first or rerun with --replace: " + ", ".join(existing)
                )

        payload: dict[str, Any] = {
            "version": 1,
            "transaction_id": transaction_id,
            "target_root": str(target_root),
            "owner_token": token,
            "owner_pid": os.getpid(),
            "started_at": datetime.now(timezone.utc).isoformat(),
            "status": "preparing",
            "packages": packages,
        }
        atomic_write_json(journal_path, payload)

        try:
            for row in packages:
                source = Path(str(row["source"]))
                stage = Path(str(row["stage"]))
                shutil.copytree(source, stage, ignore=ignored)
                normalize_bundle(stage)
                row["stage_hash"] = tree_hash(stage)
                payload["status"] = f"{row['name']}_staged"
                atomic_write_json(journal_path, payload)
                if after_step is not None:
                    after_step(str(payload["status"]))

            for row in packages:
                destination = Path(str(row["destination"]))
                backup = Path(str(row["backup"]))
                if destination.exists():
                    os.replace(destination, backup)
                payload["status"] = f"{row['name']}_backed_up"
                atomic_write_json(journal_path, payload)
                if after_step is not None:
                    after_step(str(payload["status"]))

            for row in packages:
                stage = Path(str(row["stage"]))
                destination = Path(str(row["destination"]))
                os.replace(stage, destination)
                row["installed"] = True
                payload["status"] = f"{row['name']}_installed"
                atomic_write_json(journal_path, payload)
                if after_step is not None:
                    after_step(str(payload["status"]))

            for row in packages:
                destination = Path(str(row["destination"]))
                if not destination.is_dir() or tree_hash(destination) != row["stage_hash"]:
                    raise RuntimeError(f"Installed package hash mismatch: {destination}")

            payload["status"] = "committed"
            payload["completed_at"] = datetime.now(timezone.utc).isoformat()
            atomic_write_json(journal_path, payload)
            journal_path.unlink()
        except BaseException:
            rollback_transaction(target_root, payload)
            try:
                journal_path.unlink()
            except FileNotFoundError:
                pass
            raise

    return {
        "status": "installed",
        "target_root": str(target_root),
        "installed": [row["destination"] for row in packages],
        "backups": [row["backup"] for row in packages if row["had_existing"]],
    }


def recover_install(
    target_root: Path,
    *,
    after_step: Callable[[str], None] | None = None,
) -> dict[str, object]:
    target_root = resolve_wiki_root(target_root)
    journal_path = target_root / JOURNAL_NAME
    if not journal_path.exists():
        return {"status": "no_journal", "target_root": str(target_root)}
    journal = read_json(journal_path)
    if Path(str(journal.get("target_root", ""))).resolve() != target_root:
        raise RuntimeError("Install journal target does not match the requested Wiki root.")
    clear_stale_lock_for_recovery(target_root, journal)
    owner_token = str(journal.get("owner_token", ""))
    if not owner_token:
        raise RuntimeError("Install journal is missing its transaction owner token.")
    with install_lock(target_root, purpose="recover", token=owner_token):
        journal = read_json(journal_path)
        rollback_transaction(target_root, journal, after_step=after_step)
        journal_path.unlink()
    return {"status": "recovered", "target_root": str(target_root)}


def main() -> int:
    configure_utf8_stdout()
    parser = argparse.ArgumentParser(description="Install ingest for Codex/AGENTS and Claude")
    parser.add_argument("--target-root", required=True, help="Existing LLM Wiki root containing raw/ and wiki/")
    parser.add_argument("--replace", action="store_true", help="Back up and replace an existing ingest skill")
    parser.add_argument("--recover", action="store_true", help="Roll back an interrupted dual-host install")
    args = parser.parse_args()
    if args.recover and args.replace:
        parser.error("--recover cannot be combined with --replace")
    try:
        target_root = resolve_wiki_root(args.target_root)
        result = recover_install(target_root) if args.recover else install(target_root, replace=args.replace)
    except (FileExistsError, FileNotFoundError, RuntimeError, ValueError) as error:
        parser.error(str(error))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
