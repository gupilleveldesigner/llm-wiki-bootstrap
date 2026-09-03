#!/usr/bin/env python3
"""Game-mode policy adapter for the shared LLM Wiki ingest runtime.

The adapter deliberately does not duplicate Raw scanning, Source-record semantic
review, Graphify, or the generic ingest ledger. It imports the installed generic
runtime, validates Game documents with their native schema, then updates the
Game traceability graph and enriches the generic ledger with production links.
"""

from __future__ import annotations

import argparse
import ast
import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from types import ModuleType
from typing import Any, Iterable, Sequence

GAME_INGEST_ADAPTER_ID = "game"
GAME_INGEST_ADAPTER_VERSION = 1
GAME_INGEST_SCHEMA_VERSION = 3
GAME_INGEST_LEDGER_VERSION = 3
GENERIC_RUNTIME_ENV = "LLM_WIKI_GENERIC_INGEST_RUNTIME"
ADAPTER_ROOT_ENV = "LLM_WIKI_INGEST_ROOT"
DEFAULT_ROUTING = "tools/ingest-adapters/game-routing.json"
DEFAULT_TRACE_RUNTIME = "tools/game_trace.py"

GAME_DOCUMENT_RULES: dict[str, dict[str, Any]] = {
    "game_feature_spec": {"id": "feature_id", "taxonomy": "game:feature", "provenance": True},
    "game_system_spec": {"id": "system_id", "taxonomy": "game:system", "provenance": True},
    "game_level_spec": {"id": "level_id", "taxonomy": "game:level", "provenance": True},
    "game_content_spec": {"id": "content_id", "taxonomy": "game:content", "provenance": True},
    "game_asset_brief": {"id": "asset_id", "taxonomy": "game:asset", "provenance": True},
    "game_playtest_report": {
        "id": "playtest_id",
        "taxonomy": "game:playtest",
        "provenance": True,
        "subject_field": "subject_refs",
    },
    "game_build_report": {
        "id": "build_id",
        "taxonomy": "game:build",
        "provenance": True,
        "subject_field": "subject_refs",
    },
    "game_decision_record": {
        "id": "decision_id",
        "taxonomy": "game:decision",
        "provenance": True,
        "subject_field": "affected_refs",
    },
    "game_implementation_check": {
        "id": "check_id",
        "taxonomy": "game:implementation-check",
        "provenance": False,
        "subject_field": "subject_id",
        "ingest_allowed": False,
    },
    "game_bug_report": {"id": "bug_id", "taxonomy": "game:validation", "provenance": True},
    "game_milestone": {"id": "milestone_id", "taxonomy": "game:milestone", "provenance": True},
    "game_proposal": {"id": "proposal_id", "taxonomy": "game:design", "provenance": True},
}

SPEC_ID_FIELDS = (
    "feature_id",
    "system_id",
    "level_id",
    "content_id",
    "asset_id",
    "narrative_id",
    "ui_ux_id",
    "technical_id",
)


class GameIngestError(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _load_module(path: Path, name: str) -> ModuleType:
    if not path.is_file():
        raise GameIngestError(f"generic ingest runtime is missing: {path}")
    scripts_root = path.parent
    if str(scripts_root) not in sys.path:
        sys.path.insert(0, str(scripts_root))
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise GameIngestError(f"cannot load Python module: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_generic_runtime(root: Path) -> ModuleType:
    configured = os.environ.get(GENERIC_RUNTIME_ENV)
    candidates = [Path(configured)] if configured else []
    candidates.extend(
        (
            root / ".agents/skills/ingest/scripts/ingest_runtime.py",
            root / ".claude/skills/ingest/scripts/ingest_runtime.py",
        )
    )
    runtime = next((candidate.resolve() for candidate in candidates if candidate and candidate.is_file()), None)
    if runtime is None:
        raise GameIngestError("cannot find the shared ingest runtime in this vault")
    return _load_module(runtime, "llm_wiki_generic_ingest_runtime")


def _parse_scalar(raw: str) -> Any:
    value = raw.strip()
    if value == "":
        return ""
    if value in ("[]", "[ ]"):
        return []
    if value in ("{}", "{ }"):
        return {}
    lowered = value.casefold()
    if lowered in ("true", "false"):
        return lowered == "true"
    if lowered in ("null", "none", "~"):
        return None
    if value.startswith("[") and value.endswith("]"):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            try:
                parsed = ast.literal_eval(value)
            except (ValueError, SyntaxError):
                parsed = [item.strip().strip("\"'") for item in value[1:-1].split(",") if item.strip()]
        return parsed if isinstance(parsed, list) else [parsed]
    if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
        try:
            return ast.literal_eval(value)
        except (ValueError, SyntaxError):
            return value[1:-1]
    if re.fullmatch(r"-?\d+", value):
        return int(value)
    return value


def parse_frontmatter_text(text: str) -> dict[str, Any]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    try:
        end = next(index for index in range(1, len(lines)) if lines[index].strip() == "---")
    except StopIteration:
        return {}
    result: dict[str, Any] = {}
    list_key: str | None = None
    for line in lines[1:end]:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        stripped = line.strip()
        if line[:1].isspace() and list_key and stripped.startswith("-"):
            result.setdefault(list_key, []).append(_parse_scalar(stripped[1:].strip()))
            continue
        if line[:1].isspace() or ":" not in line:
            list_key = None
            continue
        key, raw = line.split(":", 1)
        key = key.strip()
        if raw.strip() == "":
            result[key] = []
            list_key = key
        else:
            result[key] = _parse_scalar(raw)
            list_key = None
    return result


def parse_frontmatter(path: Path) -> dict[str, Any]:
    return parse_frontmatter_text(path.read_text(encoding="utf-8-sig"))


def as_list(value: Any) -> list[str]:
    if value in (None, ""):
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, (list, tuple)):
        return [str(item) for item in value if item not in (None, "")]
    return [str(value)]


def normalize_relative(value: str) -> str:
    raw = value.strip().replace("\\", "/")
    while raw.startswith("./"):
        raw = raw[2:]
    if not raw or raw.startswith("/") or re.match(r"^[A-Za-z]:/", raw):
        raise GameIngestError(f"path must be vault-relative: {value}")
    parts = PurePosixPath(raw).parts
    if ".." in parts:
        raise GameIngestError(f"path escapes the vault: {value}")
    return PurePosixPath(*parts).as_posix()


def read_manifest(root: Path) -> dict[str, Any]:
    path = root / ".llm-wiki.json"
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise GameIngestError(f"cannot read Game vault manifest: {path}: {error}") from error
    if not isinstance(value, dict) or value.get("project_mode") != "game":
        raise GameIngestError("configured Game ingest adapter requires project_mode: game")
    return value


def project_root_from_manifest(root: Path, manifest: dict[str, Any]) -> Path:
    game = manifest.get("game_project")
    if not isinstance(game, dict):
        raise GameIngestError("Game manifest has no game_project metadata")
    value = game.get("project_root")
    kind = game.get("project_root_kind", "relative")
    if not isinstance(value, str) or not value:
        raise GameIngestError("Game manifest has no project_root")
    path = Path(value)
    if kind == "relative" or not path.is_absolute():
        path = root / path
    path = path.resolve()
    if not path.is_dir():
        raise GameIngestError(f"live project root does not exist: {path}")
    return path


def routing_config(root: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    ingest = manifest.get("ingest") if isinstance(manifest.get("ingest"), dict) else {}
    value = ingest.get("routing") or DEFAULT_ROUTING
    path = root / normalize_relative(str(value))
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as error:
        raise GameIngestError(f"configured Game ingest routing is missing: {path}") from error
    except json.JSONDecodeError as error:
        raise GameIngestError(f"configured Game ingest routing is invalid JSON: {path}: {error}") from error
    if not isinstance(payload, dict):
        raise GameIngestError(f"configured Game ingest routing must be a JSON object: {path}")
    if payload.get("adapter") != GAME_INGEST_ADAPTER_ID:
        raise GameIngestError(f"configured Game ingest routing has the wrong adapter id: {path}")
    if int(payload.get("adapter_version", 0) or 0) != GAME_INGEST_ADAPTER_VERSION:
        raise GameIngestError(f"configured Game ingest routing version does not match the adapter: {path}")
    routes = payload.get("routes")
    if not isinstance(routes, list) or not routes:
        raise GameIngestError(f"configured Game ingest routing has no routes: {path}")
    return payload


def route_for_raw(relative: str, routing: dict[str, Any]) -> dict[str, Any] | None:
    normalized = relative.replace("\\", "/")
    for route in routing.get("routes", []) if isinstance(routing.get("routes"), list) else []:
        if not isinstance(route, dict):
            continue
        prefix = str(route.get("prefix") or "")
        if prefix and normalized.startswith(prefix):
            return route
    return None


def annotate_scan(result: dict[str, list[dict[str, Any]]], routing: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    for values in result.values():
        for item in values:
            relative = str(item.get("path") or "")
            route = route_for_raw(relative, routing)
            if route:
                item["game_route"] = {
                    "kind": route.get("kind"),
                    "required_outputs": route.get("required_outputs", []),
                    "optional_outputs": route.get("optional_outputs", []),
                }
    return result


def game_taxonomy_ids(root: Path) -> tuple[set[str], list[str]]:
    path = root / "wiki/game/taxonomy.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return set(), [f"wiki/game/taxonomy.json is missing or invalid: {error}"]
    concepts = payload.get("concepts") if isinstance(payload, dict) else None
    if not isinstance(concepts, list):
        return set(), ["wiki/game/taxonomy.json has no concepts list"]
    return {
        str(item.get("id"))
        for item in concepts
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }, []


def source_index(root: Path, generic: ModuleType) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    directory = root / "wiki/sources"
    if not directory.is_dir():
        return index
    for path in sorted(directory.rglob("*.md")):
        text = path.read_text(encoding="utf-8-sig")
        metadata = parse_frontmatter_text(text)
        source_id = str(metadata.get("id") or "").strip()
        if not source_id:
            continue
        index[source_id] = {
            "id": source_id,
            "path": path.relative_to(root).as_posix(),
            "metadata": metadata,
            "raw_targets": list(generic.independent_raw_targets(text)),
            "wiki_targets": list(generic.independent_wiki_targets(root, text)),
            "text": text,
        }
    return index



def _document_link_keys(value: str) -> set[str]:
    """Normalize Source reflected-doc links and vault-relative Game paths."""

    normalized = value.strip().replace("\\", "/").removeprefix("./")
    if normalized.startswith("wiki/"):
        normalized = normalized[len("wiki/") :]
    keys = {normalized}
    if normalized.endswith(".md"):
        keys.add(normalized[:-3])
    else:
        keys.add(normalized + ".md")
    return {item.casefold() for item in keys if item}


def _source_reflects_document(record: dict[str, Any], relative: str) -> bool:
    expected = _document_link_keys(relative)
    actual: set[str] = set()
    for target in record.get("wiki_targets", []):
        actual.update(_document_link_keys(str(target)))
    return bool(expected & actual)

def spec_ids(root: Path) -> set[str]:
    result: set[str] = set()
    for folder in ("features", "systems", "levels", "content", "narrative", "ui-ux", "technical", "assets"):
        directory = root / "wiki/game" / folder
        if not directory.is_dir():
            continue
        for path in directory.rglob("*.md"):
            metadata = parse_frontmatter(path)
            for field in SPEC_ID_FIELDS:
                value = metadata.get(field)
                if isinstance(value, str) and value.strip():
                    result.add(value.strip())
    return result


def _placeholder_id(value: str) -> bool:
    normalized = value.strip().upper()
    return not normalized or normalized.endswith("-000") or normalized in {"UNKNOWN", "TODO"}


def _raw_paths(metadata: dict[str, Any]) -> list[str]:
    values = [*as_list(metadata.get("raw_refs"))]
    for key in ("log_refs", "source_assets"):
        values.extend(item for item in as_list(metadata.get(key)) if item.replace("\\", "/").startswith("raw/"))
    return sorted(set(values))


def validate_game_documents(
    root: Path,
    values: Sequence[str],
    generic: ModuleType,
) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    reflections: list[dict[str, Any]] = []
    sources = source_index(root, generic)
    known_specs = spec_ids(root)
    taxonomy, taxonomy_errors = game_taxonomy_ids(root)
    errors.extend(taxonomy_errors)
    profile = str(read_manifest(root).get("profile") or "standard")

    for value in values:
        try:
            path, relative = generic.normalize_changed_file(root, value)
        except ValueError as error:
            errors.append(str(error))
            continue
        if not relative.startswith("wiki/game/"):
            errors.append(f"{relative}: Game adapter received a non-Game document")
            continue
        if path.name.casefold() in {"index.md", "claude.md", "model.md", "overview.md", "vision.md", "pillars.md", "roadmap.md"}:
            errors.append(f"{relative}: operational Game documents cannot complete an ingest")
            continue
        metadata = parse_frontmatter(path)
        doc_type = str(metadata.get("type") or "").strip()
        rule = GAME_DOCUMENT_RULES.get(doc_type)
        if rule is None:
            errors.append(f"{relative}: unsupported Game ingest document type: {doc_type or '<missing>'}")
            continue
        if rule.get("ingest_allowed") is False:
            errors.append(
                f"{relative}: {doc_type} belongs to the game-project inspect/accept-sync workflow, not ingest"
            )
            continue
        id_field = str(rule["id"])
        document_id = str(metadata.get(id_field) or "").strip()
        if _placeholder_id(document_id):
            errors.append(f"{relative}: {id_field} must be a stable non-placeholder ID")
        taxonomy_id = str(rule.get("taxonomy") or "")
        if taxonomy_id and taxonomy_id not in taxonomy:
            errors.append(f"{relative}: Game taxonomy is missing {taxonomy_id}")

        raw_refs = _raw_paths(metadata)
        evidence_refs = sorted(set(as_list(metadata.get("evidence_refs"))))
        for raw_ref in raw_refs:
            try:
                normalized = normalize_relative(raw_ref)
            except GameIngestError as error:
                errors.append(f"{relative}: {error}")
                continue
            if not normalized.startswith("raw/"):
                errors.append(f"{relative}: raw provenance must stay under raw/: {raw_ref}")
                continue
            raw_path = (root / normalized).resolve()
            try:
                raw_path.relative_to((root / "raw").resolve())
            except ValueError:
                errors.append(f"{relative}: raw provenance escapes raw/: {raw_ref}")
                continue
            if not raw_path.is_file():
                errors.append(f"{relative}: raw provenance does not exist: {raw_ref}")

        resolved_sources: list[dict[str, Any]] = []
        non_source_evidence: list[str] = []
        for evidence_id in evidence_refs:
            record = sources.get(evidence_id)
            if record is None:
                if evidence_id.upper().startswith(("RAW-", "SOURCE-")):
                    errors.append(f"{relative}: evidence_refs contains unknown Source ID: {evidence_id}")
                else:
                    non_source_evidence.append(evidence_id)
                continue
            if len(record["raw_targets"]) != 1:
                errors.append(f"{relative}: Source {evidence_id} does not resolve to exactly one Raw file")
            semantic = str(record["metadata"].get("semantic_status") or "partial")
            if profile == "evidence" and semantic != "reviewed":
                errors.append(f"{relative}: Evidence profile requires reviewed Source {evidence_id}, got {semantic}")
            elif semantic != "reviewed":
                warnings.append(f"{relative}: Source {evidence_id} is {semantic}; reflection remains provisional")
            if not _source_reflects_document(record, relative):
                errors.append(
                    f"{relative}: Source {evidence_id} does not list this Game document in its reflected documents"
                )
            resolved_sources.append(
                {
                    "source_id": evidence_id,
                    "source_record": record["path"],
                    "raw_targets": record["raw_targets"],
                    "semantic_status": semantic,
                }
            )

        if rule.get("provenance") and not (raw_refs or resolved_sources):
            errors.append(
                f"{relative}: ingest-reflected Game documents require an existing raw_refs/log_refs path "
                "or a resolvable Source ID in evidence_refs"
            )
        if non_source_evidence:
            warnings.append(
                f"{relative}: non-Source evidence_refs are preserved but do not prove direct ingest provenance: "
                + ", ".join(non_source_evidence)
            )

        subject_field = rule.get("subject_field")
        if subject_field:
            subjects = as_list(metadata.get(str(subject_field)))
            if not subjects:
                errors.append(f"{relative}: {subject_field} must not be empty")
            for subject in subjects:
                if subject not in known_specs:
                    errors.append(f"{relative}: {subject_field} references unknown Game spec ID: {subject}")
        else:
            subjects = []

        reflections.append(
            {
                "document": relative,
                "document_type": doc_type,
                "document_id": document_id,
                "taxonomy_id": taxonomy_id,
                "raw_refs": raw_refs,
                "evidence_refs": evidence_refs,
                "resolved_sources": resolved_sources,
                "non_source_evidence_refs": non_source_evidence,
                "subject_refs": subjects,
            }
        )

    return {
        "valid": not errors,
        "errors": errors,
        "warnings": warnings,
        "reflections": reflections,
    }



def _changed_source_records(
    root: Path,
    generic_files: Sequence[str],
    generic: ModuleType,
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for relative in generic_files:
        if not relative.startswith("wiki/sources/"):
            continue
        path = root / relative
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8-sig")
        metadata = parse_frontmatter_text(text)
        records.append(
            {
                "source_id": str(metadata.get("id") or "").strip(),
                "source_record": relative,
                "raw_targets": list(generic.independent_raw_targets(text)),
            }
        )
    return records


def split_changed_files(root: Path, values: Sequence[str], generic: ModuleType) -> tuple[list[str], list[str], list[str]]:
    generic_files: list[str] = []
    game_files: list[str] = []
    errors: list[str] = []
    for value in values:
        try:
            _, relative = generic.normalize_changed_file(root, value)
        except ValueError as error:
            errors.append(str(error))
            continue
        (game_files if relative.startswith("wiki/game/") else generic_files).append(relative)
    return generic_files, game_files, errors


ROUTE_OUTPUT_DOCUMENT_TYPES = {
    "game_playtest_report": "game_playtest_report",
    "game_build_report": "game_build_report",
}


def validate_route_fulfillment(
    root: Path,
    generic_files: Sequence[str],
    reflections: Sequence[dict[str, Any]],
    generic: ModuleType,
    routing: dict[str, Any],
) -> dict[str, Any]:
    """Ensure route-required Game reflections exist for changed Source records.

    The shared engine proves Raw→Source. The Game adapter owns only the
    domain-specific second hop. A playtest or build Source must therefore be
    accompanied by its typed Game report, while design/reference/telemetry
    routes may legitimately stop at a reviewed Source until a proposal or Claim
    is explicitly chosen.
    """

    errors: list[str] = []
    warnings: list[str] = []
    fulfilled: list[dict[str, Any]] = []
    for relative in generic_files:
        path = root / relative
        if not path.is_file() or not relative.startswith("wiki/sources/"):
            continue
        text = path.read_text(encoding="utf-8-sig")
        metadata = parse_frontmatter_text(text)
        if str(metadata.get("type") or "").casefold() != "source":
            continue
        source_id = str(metadata.get("id") or "").strip()
        for raw_target in generic.independent_raw_targets(text):
            route = route_for_raw(raw_target, routing)
            if route is None:
                continue
            required = [str(item) for item in route.get("required_outputs", [])]
            missing: list[str] = []
            matched_documents: list[str] = []
            for output in required:
                if output == "source_record":
                    continue
                document_type = ROUTE_OUTPUT_DOCUMENT_TYPES.get(output)
                if document_type is None:
                    warnings.append(
                        f"{relative}: routing declares unsupported required output {output!r}; adapter cannot verify it"
                    )
                    continue
                candidates = []
                for reflection in reflections:
                    if reflection.get("document_type") != document_type:
                        continue
                    direct = raw_target in reflection.get("raw_refs", [])
                    through_source = bool(source_id and source_id in reflection.get("evidence_refs", []))
                    resolved = any(
                        raw_target in record.get("raw_targets", [])
                        for record in reflection.get("resolved_sources", [])
                        if isinstance(record, dict)
                    )
                    if direct or through_source or resolved:
                        candidates.append(str(reflection.get("document")))
                if not candidates:
                    missing.append(output)
                else:
                    matched_documents.extend(candidates)
            if missing:
                errors.append(
                    f"{relative}: {raw_target} route {route.get('kind')} requires "
                    + ", ".join(missing)
                )
            fulfilled.append(
                {
                    "source_record": relative,
                    "source_id": source_id or None,
                    "raw_target": raw_target,
                    "route_kind": route.get("kind"),
                    "required_outputs": required,
                    "matched_game_documents": sorted(set(matched_documents)),
                    "complete": not missing,
                }
            )
    return {
        "valid": not errors,
        "errors": errors,
        "warnings": warnings,
        "routes": fulfilled,
    }


def validate_required_route_outputs(
    root: Path,
    generic_files: Sequence[str],
    reflections: Sequence[dict[str, Any]],
    routing: dict[str, Any],
    generic: ModuleType,
) -> list[str]:
    """Compatibility wrapper for the first Game-ingest adapter draft."""

    return validate_route_fulfillment(
        root, generic_files, reflections, generic, routing
    )["errors"]


def _parse_json_stdout(completed: subprocess.CompletedProcess[str], label: str) -> dict[str, Any]:
    lines = [line.strip() for line in completed.stdout.splitlines() if line.strip()]
    if not lines:
        return {
            "ok": False,
            "error": completed.stderr.strip() or f"{label} produced no JSON",
            "returncode": completed.returncode,
        }
    try:
        value = json.loads(lines[-1])
    except json.JSONDecodeError:
        return {
            "ok": False,
            "error": f"{label} did not end with JSON",
            "stdout": completed.stdout,
            "stderr": completed.stderr,
            "returncode": completed.returncode,
        }
    if not isinstance(value, dict):
        value = {"result": value}
    value["returncode"] = completed.returncode
    return value


def run_trace(root: Path, command: str, *arguments: str) -> dict[str, Any]:
    runtime = root / DEFAULT_TRACE_RUNTIME
    if not runtime.is_file():
        return {"ok": False, "error": f"Game trace runtime is missing: {runtime}", "returncode": 2}
    completed = subprocess.run(
        [sys.executable, str(runtime), "--vault-root", str(root), "--compact", command, *arguments],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    return _parse_json_stdout(completed, f"game_trace {command}")


def trace_bundle(root: Path, *, scan_first: bool) -> dict[str, Any]:
    values: dict[str, Any] = {}
    if scan_first:
        values["scan"] = run_trace(root, "scan")
    values["status"] = run_trace(root, "status")
    values["verify"] = run_trace(root, "verify")
    command_results = [
        item
        for item in values.values()
        if isinstance(item, dict) and "returncode" in item
    ]
    values["ok"] = all(int(item.get("returncode", 2)) in (0, 1) for item in command_results)
    status = values["status"]
    counts = status.get("sync_counts") if isinstance(status.get("sync_counts"), dict) else {}
    blocking = sum(
        int(counts.get(key, 0) or 0)
        for key in ("design_changed", "code_changed", "both_changed", "unverified", "missing")
    )
    values["sync_counts"] = counts
    values["game_sync_status"] = (
        "unavailable"
        if not values["ok"]
        else "actions_required"
        if blocking
        else "in_sync"
    )
    return values


def _source_id_for_ledger_entry(root: Path, entry: dict[str, Any]) -> str | None:
    source_record = entry.get("source_record")
    if not isinstance(source_record, str):
        return None
    path = root / source_record
    if not path.is_file():
        return None
    value = parse_frontmatter(path).get("id")
    return str(value) if isinstance(value, str) and value else None


def enrich_ledger(
    root: Path,
    reflections: Sequence[dict[str, Any]],
    trace: dict[str, Any],
    *,
    warnings: Sequence[str] = (),
) -> dict[str, Any]:
    path = root / "wiki/ingest-ledger.json"
    try:
        ledger = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        ledger = {"sources": [], "errors": []}
    if not isinstance(ledger, dict):
        ledger = {"sources": [], "errors": []}
    ledger["version"] = GAME_INGEST_LEDGER_VERSION
    ledger["adapter"] = {
        "id": GAME_INGEST_ADAPTER_ID,
        "version": GAME_INGEST_ADAPTER_VERSION,
        "schema_version": GAME_INGEST_SCHEMA_VERSION,
        "updated": utc_now(),
    }
    ledger["game_reflections"] = list(reflections)
    ledger["game_traceability"] = {
        "game_sync_status": trace.get("game_sync_status"),
        "sync_counts": trace.get("sync_counts", {}),
        "status": trace.get("status"),
        "verify": trace.get("verify"),
    }
    ledger["warnings"] = list(dict.fromkeys([*as_list(ledger.get("warnings")), *warnings]))

    sources = ledger.get("sources")
    if isinstance(sources, list):
        for entry in sources:
            if not isinstance(entry, dict):
                continue
            source_id = _source_id_for_ledger_entry(root, entry)
            if source_id:
                entry["source_id"] = source_id
            raw_path = str(entry.get("path") or "")
            related = [
                reflection
                for reflection in reflections
                if raw_path in reflection.get("raw_refs", [])
                or (source_id and source_id in reflection.get("evidence_refs", []))
                or any(raw_path in record.get("raw_targets", []) for record in reflection.get("resolved_sources", []))
            ]
            if related:
                entry["game_reflections"] = [
                    {
                        "document": item.get("document"),
                        "document_id": item.get("document_id"),
                        "document_type": item.get("document_type"),
                        "subject_refs": item.get("subject_refs", []),
                    }
                    for item in related
                ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", newline="\n", delete=False, dir=path.parent) as handle:
        json.dump(ledger, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
        temporary = Path(handle.name)
    temporary.replace(path)
    return ledger


def generic_status(root: Path, generic: ModuleType) -> dict[str, Any]:
    return {
        "root": str(root),
        "graph_strategy": "optional-provider",
        "graph_workspace": None,
        "graph_status": "not_checked_optional",
        "coverage": generic.coverage_summary(root),
        "graph_counts": None,
    }


def finalize_game(root: Path, args: argparse.Namespace, generic: ModuleType) -> dict[str, Any]:
    generic_files, game_files, split_errors = split_changed_files(root, args.changed_file, generic)
    manifest = read_manifest(root)
    routing = routing_config(root, manifest)
    game_validation = validate_game_documents(root, game_files, generic) if game_files else {
        "valid": True,
        "errors": [],
        "warnings": [],
        "reflections": [],
    }
    route_validation = validate_route_fulfillment(
        root,
        generic_files,
        game_validation["reflections"],
        generic,
        routing,
    )
    combined_warnings = [*game_validation["warnings"], *route_validation["warnings"]]
    errors = [*split_errors, *game_validation["errors"], *route_validation["errors"]]
    if not generic_files:
        errors.append(
            "Game ingest finalize requires at least one Source/general Wiki changed file; "
            "Game documents are reflections, not Source evidence"
        )
    if errors:
        scan_result = generic.scan(root)
        generic.write_ingest_ledger(
            root,
            scan_result,
            graph="not_checked",
            errors=errors,
            completion="incomplete",
        )
        trace = trace_bundle(root, scan_first=False)
        enrich_ledger(root, game_validation["reflections"], trace, warnings=combined_warnings)
        return {
            "status": "game_validation_failed",
            "ingest_status": "incomplete",
            "game_reflection_status": "failed",
            "game_sync_status": trace["game_sync_status"],
            "adapter": GAME_INGEST_ADAPTER_ID,
            "root": str(root),
            "errors": errors,
            "warnings": combined_warnings,
            "game_documents": game_validation["reflections"],
            "game_routing": route_validation,
            "traceability": trace,
            "exit_code": 2,
        }

    generic_result = generic.finalize(root, generic_files, complete_batch=args.complete_batch, graph_policy="optional")
    if int(generic_result.get("exit_code", 2)) != 0:
        trace = trace_bundle(root, scan_first=False)
        enrich_ledger(root, game_validation["reflections"], trace, warnings=combined_warnings)
        generic_result.update(
            {
                "ingest_status": "incomplete",
                "game_reflection_status": "pending",
                "game_sync_status": trace["game_sync_status"],
                "adapter": GAME_INGEST_ADAPTER_ID,
                "game_documents": game_validation["reflections"],
                "game_routing": route_validation,
                "traceability": trace,
                "warnings": combined_warnings,
            }
        )
        return generic_result

    trace = trace_bundle(root, scan_first=True)
    ledger = enrich_ledger(root, game_validation["reflections"], trace, warnings=combined_warnings)
    if not trace.get("ok"):
        trace_errors = [
            str(item.get("error") or item.get("errors") or f"game_trace {name} failed")
            for name, item in trace.items()
            if isinstance(item, dict) and int(item.get("returncode", 0)) == 2
        ]
        generic_result.update(
            {
                "status": "game_trace_failed",
                "ingest_status": "complete",
                "game_reflection_status": "complete",
                "game_sync_status": "unavailable",
                "adapter": GAME_INGEST_ADAPTER_ID,
                "adapter_version": GAME_INGEST_ADAPTER_VERSION,
                "game_documents": game_validation["reflections"],
                "game_routing": route_validation,
                "traceability": trace,
                "ledger_version": ledger.get("version"),
                "warnings": combined_warnings,
                "errors": list(
                    dict.fromkeys([*as_list(generic_result.get("errors")), *trace_errors])
                ),
                "exit_code": 2,
            }
        )
        return generic_result

    generic_result.update(
        {
            "ingest_status": "complete",
            "game_reflection_status": "complete",
            "game_sync_status": trace["game_sync_status"],
            "adapter": GAME_INGEST_ADAPTER_ID,
            "adapter_version": GAME_INGEST_ADAPTER_VERSION,
            "game_documents": game_validation["reflections"],
            "game_routing": route_validation,
            "traceability": trace,
            "ledger_version": ledger.get("version"),
            "warnings": combined_warnings,
            "exit_code": 0,
        }
    )
    return generic_result


def verify_game(root: Path, args: argparse.Namespace, generic: ModuleType) -> dict[str, Any]:
    generic_files, game_files, split_errors = split_changed_files(root, args.changed_file, generic)
    routing = routing_config(root, read_manifest(root))
    generic_result = generic.verify(
        root,
        require_graph=args.require_graph,
        inspect_graph=args.require_graph,
        complete_batch=args.complete_batch,
        changed_files=generic_files or None,
    )
    game_validation = validate_game_documents(root, game_files, generic) if game_files else {
        "valid": True,
        "errors": [],
        "warnings": [],
        "reflections": [],
    }
    route_validation = validate_route_fulfillment(
        root,
        generic_files,
        game_validation["reflections"],
        generic,
        routing,
    )
    trace = trace_bundle(root, scan_first=False)
    errors = [
        *generic_result.get("errors", []),
        *split_errors,
        *game_validation["errors"],
        *route_validation["errors"],
    ]
    if not trace.get("ok"):
        errors.append("Game trace verification is unavailable or failed")
    verified = not errors
    return {
        **generic_result,
        "status": "verified" if verified else "verification_failed",
        "verified": verified,
        "adapter": GAME_INGEST_ADAPTER_ID,
        "game_reflection_status": "verified" if game_validation["valid"] else "failed",
        "game_sync_status": trace["game_sync_status"],
        "game_documents": game_validation["reflections"],
        "game_routing": route_validation,
        "traceability": trace,
        "errors": errors,
        "warnings": [*game_validation["warnings"], *route_validation["warnings"]],
        "exit_code": 0 if verified else 2,
    }


def build_parser(generic: ModuleType) -> argparse.ArgumentParser:
    return generic.build_parser()


def print_json(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2))


def main() -> int:
    root_value = os.environ.get(ADAPTER_ROOT_ENV)
    provisional_root = Path(root_value).resolve() if root_value else Path.cwd().resolve()
    generic = load_generic_runtime(provisional_root)
    parser = build_parser(generic)
    args = parser.parse_args()
    try:
        root = generic.resolve_wiki_root(args.root or root_value, skill_root=Path(generic.__file__).resolve().parent.parent)
        manifest = read_manifest(root)
        project_root = project_root_from_manifest(root, manifest)
        routing = routing_config(root, manifest)
    except (ValueError, GameIngestError) as error:
        parser.error(str(error))

    if args.command == "status":
        result = generic_status(root, generic)
        result.update(
            {
                "adapter": GAME_INGEST_ADAPTER_ID,
                "adapter_version": GAME_INGEST_ADAPTER_VERSION,
                "project_root": str(project_root),
                "routing": routing,
                "traceability": trace_bundle(root, scan_first=False),
            }
        )
        print_json(result)
        return 0
    if args.command == "scan":
        result = annotate_scan(generic.scan(root), routing)
        if args.json:
            print_json(result)
        else:
            for name in (
                "pending",
                "ingested",
                "skipped",
                "rejected",
                "catalog_only",
                "semantic_pending",
                "semantic_partial",
                "semantic_reviewed",
            ):
                print(f"{name}: {len(result[name])}")
                for item in result[name]:
                    route = item.get("game_route")
                    suffix = f" -> {route.get('kind')}" if isinstance(route, dict) else ""
                    reason = f" - {item['reason']}" if "reason" in item else ""
                    print(f"  - {item['path']} ({item['modified']}){reason}{suffix}")
        return 0
    if args.command == "semantic-plan":
        try:
            print_json(
                generic.semantic_plan(
                    root,
                    args.source,
                    max_lines=args.max_lines,
                    overlap_lines=args.overlap_lines,
                )
            )
        except ValueError as error:
            parser.error(str(error))
        return 0
    if args.command == "finalize":
        result = finalize_game(root, args, generic)
        print_json(result)
        return int(result["exit_code"])
    if args.command == "verify":
        result = verify_game(root, args, generic)
        print_json(result)
        return int(result["exit_code"])
    if args.command == "category-audit":
        generic_result = generic.audit_categories(root)
        taxonomy, game_errors = game_taxonomy_ids(root)
        result = {
            "status": "ok" if generic_result.get("valid") and not game_errors else "failed",
            "valid": bool(generic_result.get("valid")) and not game_errors,
            "generic": generic_result,
            "game_taxonomy_concepts": len(taxonomy),
            "game_errors": game_errors,
            "exit_code": 0 if generic_result.get("valid") and not game_errors else 2,
        }
        print_json(result)
        return int(result["exit_code"])
    if args.command == "record-graphify-run":
        result = generic.record_graphify_run(root, args.host)
        print_json(result)
        return int(result["exit_code"])
    result = generic.recover(root)
    print_json(result)
    return int(result["exit_code"])


if __name__ == "__main__":
    raise SystemExit(main())
