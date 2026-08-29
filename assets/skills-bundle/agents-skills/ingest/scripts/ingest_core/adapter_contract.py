from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Sequence

ADAPTER_ACTIVE_ENV = "LLM_WIKI_INGEST_ADAPTER_ACTIVE"
ADAPTER_ROOT_ENV = "LLM_WIKI_INGEST_ROOT"
GENERIC_RUNTIME_ENV = "LLM_WIKI_GENERIC_INGEST_RUNTIME"


class AdapterError(RuntimeError):
    """Raised when a manifest-declared ingest adapter is unsafe or unavailable."""


@dataclass(frozen=True)
class AdapterConfiguration:
    adapter_id: str
    adapter_version: int
    adapter_path: Path
    manifest: dict[str, Any]


def _read_manifest(root: Path) -> dict[str, Any]:
    path = root / ".llm-wiki.json"
    if not path.is_file():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise AdapterError(f"cannot read ingest adapter manifest: {path}: {error}") from error
    if not isinstance(value, dict):
        raise AdapterError(f"invalid ingest adapter manifest root: {path}")
    return value


def _safe_vault_relative(root: Path, value: str) -> Path:
    normalized = value.strip().replace("\\", "/")
    if not normalized:
        raise AdapterError("ingest adapter_path is empty")
    if normalized.startswith("/") or re.match(r"^[A-Za-z]:/", normalized):
        raise AdapterError("ingest adapter_path must be vault-relative")
    parts = PurePosixPath(normalized).parts
    if ".." in parts:
        raise AdapterError("ingest adapter_path escapes the vault")
    candidate = (root / PurePosixPath(*parts)).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError as error:
        raise AdapterError("ingest adapter_path escapes the vault") from error
    return candidate


def configured_adapter(root: Path) -> AdapterConfiguration | None:
    """Return the manifest-selected adapter, or None for generic ingest.

    A project mode may select an adapter without changing the shared Raw/Source
    engine. The adapter is a vault-local policy layer and is never loaded from
    project_root or another external path.
    """

    manifest = _read_manifest(root)
    ingest = manifest.get("ingest")
    if not isinstance(ingest, dict):
        return None
    adapter_id = str(ingest.get("adapter") or "generic").strip()
    if not adapter_id or adapter_id == "generic":
        return None
    path_value = ingest.get("adapter_path")
    if not isinstance(path_value, str):
        raise AdapterError(f"ingest adapter {adapter_id!r} has no adapter_path")
    adapter_path = _safe_vault_relative(root, path_value)
    if not adapter_path.is_file():
        raise AdapterError(f"configured ingest adapter is missing: {adapter_path}")
    version_value = ingest.get("adapter_version", 1)
    try:
        version = int(version_value)
    except (TypeError, ValueError) as error:
        raise AdapterError(f"invalid ingest adapter_version: {version_value!r}") from error
    return AdapterConfiguration(adapter_id, version, adapter_path, manifest)


def dispatch_configured_adapter(
    root: Path,
    argv: Sequence[str],
    *,
    runtime_path: Path,
) -> int | None:
    """Run the manifest adapter with the original CLI arguments.

    The generic runtime remains the single Raw/Source engine. The adapter process
    receives its resolved vault and the canonical runtime path through explicit
    environment variables, and a recursion guard prevents it from redispatching.
    """

    if os.environ.get(ADAPTER_ACTIVE_ENV) == "1":
        return None
    configuration = configured_adapter(root)
    if configuration is None:
        return None
    environment = os.environ.copy()
    environment[ADAPTER_ACTIVE_ENV] = "1"
    environment[ADAPTER_ROOT_ENV] = str(root.resolve())
    environment[GENERIC_RUNTIME_ENV] = str(runtime_path.resolve())
    completed = subprocess.run(
        [sys.executable, str(configuration.adapter_path), *list(argv)],
        cwd=root,
        env=environment,
        check=False,
    )
    return completed.returncode
