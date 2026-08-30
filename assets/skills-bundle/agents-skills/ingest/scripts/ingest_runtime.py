#!/usr/bin/env python3
"""Host-neutral runtime for an LLM Wiki ingest skill."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence
from urllib.parse import unquote

SCRIPT_ROOT = Path(__file__).resolve().parent
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

from find_uningested import (
    HOST_INSTRUCTION_FILES,
    OPERATIONAL_WIKI_FILES,
    PLAIN_RAW_PATH_RE,
    configure_utf8_stdout,
    resolve_wiki_root,
    scan,
    source_summary_quality,
)
from audit_categories import audit as audit_categories
from semantic_contract import review_source_record, semantic_partition
from ingest_core.adapter_contract import AdapterError, dispatch_configured_adapter


TOP_LEVEL_KEY_RE = re.compile(r"^[A-Za-z0-9_-]+:\s*", re.MULTILINE)
WIKILINK_RE = re.compile(r"\[\[([^\]|#]+)")


def read_frontmatter(path: Path) -> str:
    text = path.read_text(encoding="utf-8-sig")
    if not text.startswith("---"):
        return ""
    parts = text.split("---", 2)
    return parts[1] if len(parts) == 3 else ""


def frontmatter_value(frontmatter: str, key: str) -> str:
    match = re.search(rf"(?m)^{re.escape(key)}:\s*(.*)$", frontmatter)
    if not match:
        return ""
    value = match.group(1).strip()
    remainder = frontmatter[match.end() :]
    continuation: list[str] = []
    for line in remainder.splitlines():
        if line and not line[0].isspace() and TOP_LEVEL_KEY_RE.match(line):
            break
        if line.strip():
            continuation.append(line.strip())
    return "\n".join([value, *continuation]).strip()


def _has_meaningful_value(value: str) -> bool:
    return value.casefold() not in {"", "[]", "{}", "null", "none", "~"}


def normalize_changed_file(root: Path, value: str) -> tuple[Path, str]:
    raw_candidate = Path(value)
    if not raw_candidate.is_absolute():
        raw_candidate = root / raw_candidate
    raw_wiki_root = root / "wiki"
    candidate = raw_candidate.resolve()
    wiki_root = raw_wiki_root.resolve()
    try:
        relative = "wiki/" + raw_candidate.relative_to(raw_wiki_root).as_posix()
    except ValueError as error:
        # Windows runners can expose the same directory through a short
        # (8.3) path and a long path.  Path.relative_to compares strings and
        # rejects that harmless spelling difference.  The input is still
        # checked lexically, while the resolved path is checked for symlink
        # escapes by comparing its ancestors to the real wiki root.
        try:
            relative_candidate = Path(value).as_posix()
            if Path(value).is_absolute() or relative_candidate.startswith("../") or "/../" in relative_candidate:
                raise ValueError
            relative = "wiki/" + relative_candidate.removeprefix("wiki/")
        except (OSError, ValueError) as fallback_error:
            raise ValueError(f"Changed file must stay under wiki/: {value}") from fallback_error
    current = candidate
    while True:
        try:
            if os.path.samefile(current, wiki_root):
                break
        except OSError:
            pass
        if current == current.parent:
            raise ValueError(f"Changed file must stay under wiki/: {value}")
        current = current.parent
    if not candidate.is_file():
        raise ValueError(f"Changed wiki file does not exist: {relative}")
    return candidate, relative


def graph_status(root: Path, strategy: str | None = None) -> str:
    strategy = strategy or graph_strategy(root)
    if strategy == "curated-finalizer":
        return "configured"
    if strategy == "graphify-cli":
        return "configured" if graphify_executable() else "graph_present"
    if strategy == "curated-finalizer-missing":
        return "blocked"
    if strategy == "ambiguous-graph-layout":
        return "ambiguous"
    return "not_installed" if graphify_executable() is None else "not_configured"


def graphify_executable() -> str | None:
    candidates = [shutil.which("graphify")]
    executable_root = Path(sys.executable).resolve().parent
    candidates.extend(
        str(executable_root / name)
        for name in ("graphify", "graphify.exe", "Scripts/graphify", "Scripts/graphify.exe")
    )
    return next((candidate for candidate in candidates if candidate and Path(candidate).is_file()), None)


def graphify_agent_action(root: Path) -> dict[str, Any]:
    target = f'"{root}"'
    runtime = 'python "<SKILL_ROOT>/scripts/ingest_runtime.py"'
    return {
        "status": "agent_action_required",
        "root": str(root),
        "codex": {
            "install": "python -m pip install graphifyy && graphify install --platform codex",
            "build": f"$graphify {target}",
            "update": f"$graphify {target} --update",
            "record": f'{runtime} record-graphify-run --root {target} --host codex',
            "always_on_optional": "graphify codex install",
        },
        "claude": {
            "install": "python -m pip install graphifyy && graphify install",
            "build": f"/graphify {target}",
            "update": f"/graphify {target} --update",
            "record": f'{runtime} record-graphify-run --root {target} --host claude',
            "always_on_optional": "graphify claude install",
        },
        "note": "Run Graphify through the host AI skill so its platform authentication is used. Do not run bare graphify <path> from Python.",
    }


def graph_counts(root: Path, workspace: Path | None = None) -> dict[str, int]:
    graph = (workspace or root) / "graphify-out" / "graph.json"
    if not graph.is_file():
        return {"nodes": 0, "links": 0}
    try:
        payload = json.loads(graph.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return {"nodes": 0, "links": 0}
    nodes = payload.get("nodes", []) if isinstance(payload, dict) else []
    links = payload.get("links", payload.get("edges", [])) if isinstance(payload, dict) else []
    return {
        "nodes": len(nodes) if isinstance(nodes, (list, dict)) else 0,
        "links": len(links) if isinstance(links, (list, dict)) else 0,
    }


def record_graphify_run(root: Path, host: str) -> dict[str, Any]:
    graph_path = (graph_workspace(root) or root) / "graphify-out" / "graph.json"
    if not graph_path.is_file():
        return {"status": "graph_missing", "root": str(root), "exit_code": 2}
    payload = {
        "version": 1,
        "host": host,
        "graph": graph_path.relative_to(root).as_posix(),
        "graph_sha256": raw_sha256(graph_path),
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "inputs": {
            path.relative_to(root).as_posix(): raw_sha256(path)
            for path in independent_graph_input_files(root)
            if path.is_file()
        },
    }
    destination = graph_path.with_name(".graphify-host-run.json")
    destination.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"status": "recorded", "root": str(root), "host": host, "manifest": str(destination), "exit_code": 0}


def coverage_summary(root: Path) -> dict[str, int]:
    result = scan(root)
    return {
        name: len(result.get(name, []))
        for name in (
            "pending",
            "ingested",
            "skipped",
            "rejected",
            "catalog_only",
            "semantic_pending",
            "semantic_partial",
            "semantic_reviewed",
        )
    }


def write_ingest_ledger(
    root: Path,
    scan_result: dict[str, list[dict[str, object]]],
    *,
    graph: str,
    errors: Sequence[str] = (),
    completion: str | None = None,
) -> None:
    """Persist file-level evidence without touching raw/ files."""
    entries: list[dict[str, object]] = []
    for state in ("pending", "ingested", "skipped", "rejected", "catalog_only"):
        for item in scan_result.get(state, []):
            entry = {
                "path": item["path"],
                "status": "verified" if state == "ingested" else state,
                "reason": item.get("reason"),
                "modified": item.get("modified"),
            }
            for key in ("structurally_verified", "semantic_status", "source_record", "semantic_errors"):
                if key in item:
                    entry[key] = item[key]
            entries.append(entry)
    counts = {state: 0 for state in ("pending", "verified", "skipped", "rejected", "catalog_only")}
    for entry in entries:
        counts[str(entry["status"])] = counts.get(str(entry["status"]), 0) + 1
        related = [
            error
            for error in errors
            if str(entry["path"]).casefold() in error.casefold()
            or Path(str(entry["path"])).name.casefold() in error.casefold()
        ]
        if related:
            entry["errors"] = related
    counts.update(
        {
            state: len(scan_result.get(state, []))
            for state in ("semantic_pending", "semantic_partial", "semantic_reviewed")
        }
    )
    ledger = {
        "version": 2,
        "updated": datetime.now(timezone.utc).isoformat(),
        "graphify": graph,
        "counts": counts,
        "completion": completion or ("complete" if not errors else "incomplete"),
        "errors": list(errors),
        "sources": sorted(entries, key=lambda entry: str(entry["path"])),
    }
    destination = root / "wiki" / "ingest-ledger.json"
    temporary = destination.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(destination)


def raw_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_changed_files(root: Path, changed_files: Sequence[str]) -> list[str]:
    """Apply portable minimum gates before any graph-specific finalizer."""
    if not changed_files:
        return ["At least one --changed-file is required to complete an ingest."]

    errors: list[str] = []
    raw_root = (root / "raw").resolve()
    for value in changed_files:
        try:
            path, relative = normalize_changed_file(root, value)
        except ValueError as error:
            errors.append(str(error))
            continue

        text = path.read_text(encoding="utf-8-sig")
        frontmatter = read_frontmatter(path)
        if not frontmatter:
            errors.append(f"{relative}: YAML frontmatter is required")
            continue

        if path.name.casefold() in OPERATIONAL_WIKI_FILES and not relative.casefold().startswith("wiki/sources/"):
            errors.append(f"{relative}: catalog/operational documents cannot complete an ingest")
            continue

        topics = frontmatter_value(frontmatter, "topics") or frontmatter_value(frontmatter, "tags")
        source_fields = "\n".join(
            value
            for value in (
                frontmatter_value(frontmatter, "sources"),
                frontmatter_value(frontmatter, "source"),
            )
            if _has_meaningful_value(value)
        )
        if not _has_meaningful_value(topics):
            errors.append(f"{relative}: topics or tags must not be empty")
        source_scope = "\n".join(value for value in (source_fields, text) if value)
        if not _has_meaningful_value(source_scope):
            errors.append(f"{relative}: a raw source citation is required")
        else:
            cited_targets = WIKILINK_RE.findall(source_scope) + PLAIN_RAW_PATH_RE.findall(source_scope)
            raw_paths = list(
                dict.fromkeys(
                    unquote(target.strip()).replace("\\", "/").removeprefix("./")
                    for target in cited_targets
                    if target.strip().replace("\\", "/").removeprefix("./").casefold().startswith("raw/")
                )
            )
            if not raw_paths:
                errors.append(f"{relative}: source citation must include a raw/ file path")
            if relative.casefold().startswith("wiki/sources/"):
                source_type = frontmatter_value(frontmatter, "type").strip("\"'").casefold()
                if source_type != "source":
                    errors.append(f"{relative}: source summaries must have type: source")
                if len(raw_paths) != 1:
                    errors.append(f"{relative}: source summaries must cite exactly one raw file; catalogs are not ingest evidence")
                if not source_summary_quality(text):
                    errors.append(
                        f"{relative}: source evidence must include non-placeholder claims, entities, concepts, reflected_docs, raw_sha256, and Wiki links"
                    )
                body = text.split("---", 2)[-1] if text.startswith("---") else text
                for link in WIKILINK_RE.findall(body):
                    target = link.strip().replace("\\", "/").removeprefix("./")
                    if target.casefold().startswith("raw/"):
                        continue
                    target_path = Path(target)
                    candidates = [
                        root / "wiki" / target_path,
                        root / "wiki" / target_path.with_suffix(".md"),
                        root / target_path,
                        root / target_path.with_suffix(".md"),
                    ]
                    if not any(candidate.is_file() for candidate in candidates):
                        errors.append(f"{relative}: reflected Wiki link does not exist: {target}")
            for target in raw_paths:
                candidate = (root / target).resolve()
                try:
                    candidate.relative_to(raw_root)
                except ValueError:
                    errors.append(f"{relative}: raw source escapes raw/: {target}")
                    continue
                candidates = [candidate]
                if not candidate.suffix:
                    candidates.append(candidate.with_suffix(".md"))
                if not any(path.is_file() for path in candidates):
                    errors.append(f"{relative}: raw source does not exist: {target}")
                elif relative.casefold().startswith("wiki/sources/"):
                    declared_hash = frontmatter_value(frontmatter, "raw_sha256").strip("\"'").casefold()
                    raw_path = next(path for path in candidates if path.is_file())
                    actual_hash = raw_sha256(raw_path)
                    if declared_hash != actual_hash:
                        errors.append(f"{relative}: raw_sha256 does not match the cited raw file")
                    semantic = review_source_record(root, path, raw_path, text)
                    if semantic["semantic_status"] != "reviewed":
                        errors.append(f"{relative}: semantic review is {semantic['semantic_status']}, not reviewed")
                    errors.extend(f"{relative}: {error}" for error in semantic["errors"])
    return errors


def graph_strategy(root: Path) -> str:
    finalizer = root / "tools" / "graphify_knowledge" / "finalize_ingest.py"
    if finalizer.is_file():
        return "curated-finalizer"
    workspaces = graph_workspaces(root)
    if len(workspaces) > 1:
        return "ambiguous-graph-layout"
    if not workspaces:
        return "none"
    curated_marker = workspaces[0] / "graphify-out" / "CURATED_GRAPH_STATE.json"
    if curated_marker.is_file():
        return "curated-finalizer-missing"
    return "graphify-cli"


def graph_workspaces(root: Path) -> list[Path]:
    candidates: list[Path] = []
    for workspace in (root, root / "wiki"):
        graph_out = workspace / "graphify-out"
        if (graph_out / "graph.json").is_file() or (graph_out / "CURATED_GRAPH_STATE.json").is_file():
            candidates.append(workspace.resolve())
    return candidates


def graph_workspace(root: Path) -> Path | None:
    if (root / "tools" / "graphify_knowledge" / "finalize_ingest.py").is_file():
        return root.resolve()
    workspaces = graph_workspaces(root)
    return workspaces[0] if len(workspaces) == 1 else None


def graph_python(root: Path, workspace: Path | None = None) -> str:
    for graph_root in (workspace, root):
        if graph_root is None:
            continue
        marker = graph_root / "graphify-out" / ".graphify_python"
        if marker.is_file():
            value = marker.read_text(encoding="utf-8-sig").strip()
            if value:
                return value
    return sys.executable


def run_command(command: Sequence[str], *, cwd: Path) -> int:
    completed = subprocess.run(list(command), cwd=cwd, check=False)
    return completed.returncode


def finalize(root: Path, changed_files: Sequence[str], *, complete_batch: bool = False) -> dict[str, Any]:
    errors = validate_changed_files(root, changed_files)
    if errors:
        scan_result = scan(root)
        write_ingest_ledger(root, scan_result, graph="not_checked", errors=errors, completion="incomplete")
        return {"status": "validation_failed", "root": str(root), "errors": errors, "exit_code": 2}

    scan_result = scan(root)
    coverage = {
        name: len(scan_result.get(name, []))
        for name in (
            "pending",
            "ingested",
            "skipped",
            "rejected",
            "catalog_only",
            "semantic_pending",
            "semantic_partial",
            "semantic_reviewed",
        )
    }
    structural_incomplete = coverage["pending"] or coverage["rejected"] or coverage["catalog_only"]
    semantic_incomplete = coverage["semantic_pending"] or coverage["semantic_partial"]
    if complete_batch and (structural_incomplete or semantic_incomplete):
        errors = [
            "Batch completion requires structural coverage and zero pending/partial semantic reviews.",
            (
                f"pending={coverage['pending']}, rejected={coverage['rejected']}, "
                f"catalog_only={coverage['catalog_only']}, semantic_pending={coverage['semantic_pending']}, "
                f"semantic_partial={coverage['semantic_partial']}"
            ),
        ]
        write_ingest_ledger(root, scan_result, graph="not_checked", errors=errors, completion="incomplete")
        return {
            "status": "coverage_failed",
            "root": str(root),
            "coverage": coverage,
            "errors": errors,
            "exit_code": 2,
        }

    category_result = audit_categories(root)
    if complete_batch and not category_result["valid"]:
        errors = ["Category audit failed.", *category_result["errors"]]
        write_ingest_ledger(root, scan_result, graph="category_failed", errors=errors, completion="incomplete")
        return {
            "status": "category_failed",
            "root": str(root),
            "coverage": coverage,
            "category_audit": category_result,
            "errors": errors,
            "exit_code": 2,
        }

    strategy = graph_strategy(root)
    if complete_batch and strategy == "none":
        action = graphify_agent_action(root)
        errors = ["Graphify has no graph.json; run the host Graphify skill before finalization."]
        write_ingest_ledger(root, scan_result, graph="agent_action_required", errors=errors, completion="incomplete")
        return {
            **action,
            "coverage": coverage,
            "graph_status": "agent_action_required",
            "errors": errors,
            "exit_code": 2,
        }
    workspace = graph_workspace(root)
    graph = graph_status(root, strategy)

    def completed_payload(payload: dict[str, Any], *, write_ledger: bool = True) -> dict[str, Any]:
        payload["coverage"] = coverage
        payload["graph_status"] = graph
        payload["graph_counts"] = graph_counts(root, workspace)
        payload["completion"] = (
            "complete_without_graph"
            if graph in {"not_installed", "not_configured"} and not (structural_incomplete or semantic_incomplete)
            else "complete"
            if not (structural_incomplete or semantic_incomplete)
            else "partial"
        )
        if payload.get("exit_code") == 0:
            verification = verify(
                root,
                require_graph=complete_batch,
                complete_batch=complete_batch,
                changed_files=None if complete_batch else changed_files,
            )
            payload["verification"] = verification
            if not verification["verified"]:
                payload["status"] = "verification_failed"
                payload["completion"] = "incomplete"
                payload["errors"] = list(dict.fromkeys([*(payload.get("errors") or []), *verification["errors"]]))
                payload["exit_code"] = 2
                write_ledger = False
        if write_ledger:
            write_ingest_ledger(root, scan_result, graph=graph, completion=str(payload["completion"]))
        elif payload.get("exit_code") != 0:
            write_ingest_ledger(root, scan_result, graph=graph, errors=payload.get("errors", ()), completion="incomplete")
        return payload
    if strategy == "curated-finalizer":
        command = [
            graph_python(root, workspace),
            str(root / "tools" / "graphify_knowledge" / "finalize_ingest.py"),
            "--workspace-root",
            str(root),
        ]
        for changed_file in changed_files:
            _, relative = normalize_changed_file(root, changed_file)
            command.extend(["--changed-file", relative])
        exit_code = run_command(command, cwd=root)
        return completed_payload({
            "status": "promoted" if exit_code == 0 else "graph_finalizer_failed",
            "root": str(root),
            "strategy": strategy,
            "exit_code": exit_code,
        }, write_ledger=exit_code == 0)

    if strategy == "curated-finalizer-missing":
        return completed_payload({
            "status": "graph_finalizer_missing",
            "root": str(root),
            "strategy": strategy,
            "errors": ["Curated graph marker exists, so generic graphify update was refused."],
            "exit_code": 2,
        }, write_ledger=False)

    if strategy == "ambiguous-graph-layout":
        return completed_payload({
            "status": "ambiguous_graph_layout",
            "root": str(root),
            "strategy": strategy,
            "errors": ["Both root/graphify-out and wiki/graphify-out exist; choose one canonical graph first."],
            "exit_code": 2,
        }, write_ledger=False)

    if strategy == "graphify-cli":
        if workspace is None:
            raise RuntimeError("Graphify workspace resolution failed.")
        return completed_payload({
            "status": "graph_present",
            "root": str(root),
            "graph_workspace": str(workspace),
            "strategy": strategy,
            "note": "Graphify was run by the host AI; this gate only verifies its output.",
            "exit_code": 0,
        })

    return completed_payload({
        "status": "validated_without_graph",
        "root": str(root),
        "strategy": strategy,
        "note": "Wiki files passed portable gates; this Wiki has no graph to update.",
        "exit_code": 0,
    })


def independent_frontmatter(text: str) -> str:
    if not text.startswith("---"):
        return ""
    parts = text.split("---", 2)
    return parts[1] if len(parts) == 3 else ""


def independent_field(frontmatter: str, key: str) -> str:
    match = re.search(rf"(?m)^{re.escape(key)}:\s*(.*)$", frontmatter)
    return match.group(1).strip().strip("\"'") if match else ""


def independent_int(frontmatter: str, key: str) -> int | None:
    value = independent_field(frontmatter, key)
    try:
        return int(value)
    except ValueError:
        return None


def independent_raw_targets(text: str) -> list[str]:
    front = independent_frontmatter(text)
    scope = "\n".join(part for part in (front, text) if part)
    targets = WIKILINK_RE.findall(scope) + PLAIN_RAW_PATH_RE.findall(scope)
    return list(dict.fromkeys(
        unquote(target.strip()).replace("\\", "/").removeprefix("./")
        for target in targets
        if target.strip().replace("\\", "/").removeprefix("./").casefold().startswith("raw/")
    ))


def independent_wiki_targets(root: Path, text: str) -> list[str]:
    body = text.split("---", 2)[-1] if text.startswith("---") else text
    return [target.strip().replace("\\", "/").removeprefix("./") for target in WIKILINK_RE.findall(body) if not target.casefold().startswith("raw/")]


def independent_raw_files(root: Path) -> list[Path]:
    excluded = {"agents.md", "claude.md", "gemini.md"}
    attachments = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".bmp", ".avif"}
    files: list[Path] = []
    for path in sorted((root / "raw").rglob("*"), key=lambda item: item.as_posix()):
        if not path.is_file() or (path.parent == root / "raw" and path.name.casefold() in excluded):
            continue
        if path.suffix.casefold() in attachments:
            continue
        try:
            if not path.read_bytes().strip():
                continue
        except OSError:
            continue
        files.append(path)
    return files


def independent_raw_exclusions(root: Path) -> dict[str, list[str]]:
    attachments = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".bmp", ".avif"}
    result = {"rejected": [], "skipped": []}
    for path in sorted((root / "raw").rglob("*"), key=lambda item: item.as_posix()):
        if not path.is_file() or (path.parent == root / "raw" and path.name.casefold() in {"agents.md", "claude.md", "gemini.md"}):
            continue
        relative = path.relative_to(root).as_posix()
        if path.suffix.casefold() in attachments:
            result["skipped"].append(relative)
            continue
        try:
            if not path.read_bytes().strip():
                result["rejected"].append(relative)
        except OSError:
            result["rejected"].append(relative)
    return result


def independent_graph_input_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for layer in (root / "raw", root / "wiki"):
        if not layer.is_dir():
            continue
        for path in sorted(layer.rglob("*"), key=lambda item: item.as_posix()):
            if not path.is_file():
                continue
            relative = path.relative_to(root).as_posix()
            parts = {part.casefold() for part in path.relative_to(layer).parts}
            if "graphify-out" in parts:
                continue
            if layer.name == "raw" and path.parent == layer and path.name.casefold() in HOST_INSTRUCTION_FILES:
                continue
            if layer.name == "wiki" and not (layer / "sources") in path.parents and path.name.casefold() in OPERATIONAL_WIKI_FILES:
                continue
            if relative.casefold() == "wiki/taxonomy.json":
                continue
            if relative.casefold() == "wiki/ingest-ledger.json":
                continue
            if relative.casefold() == ".graphifyignore":
                continue
            files.append(path)
    return files


def independent_source_records(root: Path) -> list[dict[str, Any]]:
    sources_root = root / "wiki" / "sources"
    pages = list(sources_root.rglob("*.md")) if sources_root.is_dir() else []
    if not pages:
        pages = [
            path
            for path in (root / "wiki").rglob("*.md")
            if "graphify-out" not in {part.casefold() for part in path.relative_to(root / "wiki").parts}
            and path.name.casefold() not in OPERATIONAL_WIKI_FILES
        ]
    records: list[dict[str, Any]] = []
    for page in pages:
        text = page.read_text(encoding="utf-8-sig")
        front = independent_frontmatter(text)
        records.append(
            {
                "path": page,
                "relative": page.relative_to(root).as_posix(),
                "text": text,
                "frontmatter": front,
                "raw_targets": independent_raw_targets(text),
                "wiki_targets": independent_wiki_targets(root, text),
            }
        )
    return records


def independent_graph_check(root: Path, records: Sequence[dict[str, Any]]) -> list[str]:
    workspace = graph_workspace(root)
    graph_path = (workspace or root) / "graphify-out" / "graph.json"
    try:
        payload = json.loads(graph_path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return [f"Graphify graph is unreadable: {graph_path}"]
    if not isinstance(payload, dict):
        return ["Graphify graph root must be an object"]
    nodes = payload.get("nodes", [])
    links = payload.get("links", payload.get("edges", []))
    if not isinstance(nodes, list) or not isinstance(links, list):
        return ["Graphify graph must expose list-shaped nodes and links"]
    node_identity: dict[str, str] = {}
    for index, node in enumerate(nodes):
        if not isinstance(node, dict):
            continue
        node_id = str(node.get("id", node.get("key", index)))
        source_file = node.get("source_file")
        if isinstance(source_file, str) and source_file.strip():
            node_identity[node_id] = source_file.replace("\\", "/").casefold().removeprefix("./")

    def matches(identity: str, target: str) -> bool:
        target = target.replace("\\", "/").casefold().removeprefix("./")
        variants = {target, target.removeprefix("wiki/")}
        if not Path(target).suffix:
            variants.update({f"{variant}.md" for variant in tuple(variants)})
        return identity in variants or identity.removeprefix("wiki/") in variants

    errors: list[str] = []
    for record in records:
        source_targets = [record["relative"]]
        source_ids = {
            node_id
            for node_id, identity in node_identity.items()
            if any(matches(identity, target) for target in source_targets)
        }
        if not source_ids:
            errors.append(f"Graphify has no node for source summary: {record['relative']}")
            continue
        raw_ids = {
            node_id
            for node_id, identity in node_identity.items()
            if record["raw_targets"] and matches(identity, record["raw_targets"][0])
        }
        if not raw_ids:
            errors.append(f"Graphify has no raw node for source: {record['raw_targets'][0] if record['raw_targets'] else record['relative']}")
        elif not any(
            isinstance(link, dict)
            and str(link.get("source", link.get("from", ""))) in source_ids
            and str(link.get("target", link.get("to", ""))) in raw_ids
            for link in links
        ):
            errors.append(f"Graphify has no source-to-raw edge: {record['relative']}")
        reflected_targets: list[set[str]] = []
        for target in record["wiki_targets"]:
            ids = {node_id for node_id, identity in node_identity.items() if matches(identity, target)}
            reflected_targets.append(ids)
            if not ids:
                errors.append(f"Graphify has no node for reflected doc of {record['relative']}: {target}")
        for target, reflected_ids in zip(record["wiki_targets"], reflected_targets):
            if not reflected_ids:
                continue
            connected = False
            for link in links:
                if not isinstance(link, dict):
                    continue
                left = str(link.get("source", link.get("from", "")))
                right = str(link.get("target", link.get("to", "")))
                if (left in source_ids and right in reflected_ids) or (right in source_ids and left in reflected_ids):
                    connected = True
                    break
            if not connected:
                errors.append(f"Graphify has no source-to-reflected-document edge: {record['relative']} -> {target}")
    return errors


def graph_freshness_error(root: Path) -> str | None:
    workspace = graph_workspace(root)
    graph_path = (workspace or root) / "graphify-out" / "graph.json"
    if not graph_path.is_file():
        return f"Graphify graph is missing: {graph_path}"
    inputs = independent_graph_input_files(root)
    latest = max((path.stat().st_mtime for path in inputs if path.is_file()), default=0)
    if graph_path.stat().st_mtime + 1 < latest:
        return "Graphify graph is older than the latest raw/Wiki input; run the host Graphify --update skill."
    return None


def graphify_host_manifest_error(root: Path) -> str | None:
    workspace = graph_workspace(root)
    graph_path = (workspace or root) / "graphify-out" / "graph.json"
    manifest_path = graph_path.with_name(".graphify-host-run.json")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return "Graphify host-run manifest is missing; record the completed $graphify or /graphify run."
    if manifest.get("host") not in {"codex", "claude"}:
        return "Graphify host-run manifest has an unsupported host."
    if manifest.get("graph_sha256") != raw_sha256(graph_path):
        return "Graphify host-run manifest does not match the current graph.json."
    current_inputs = {
        path.relative_to(root).as_posix(): raw_sha256(path)
        for path in independent_graph_input_files(root)
        if path.is_file()
    }
    if manifest.get("inputs") != current_inputs:
        return "Graphify host-run manifest inputs are stale or incomplete; rerun the host Graphify skill."
    return None


def verify(root: Path, *, require_graph: bool = False, complete_batch: bool = False, changed_files: Sequence[str] | None = None) -> dict[str, Any]:
    """Independent read-only verifier; deliberately does not call scan() or finalize gates."""
    raw_files = independent_raw_files(root)
    exclusions = independent_raw_exclusions(root)
    records = independent_source_records(root)
    errors: list[str] = []
    scoped_verification = bool(changed_files and not complete_batch)
    if scoped_verification:
        changed = {Path(value).as_posix().casefold() for value in changed_files}
        records = [record for record in records if record["relative"].casefold() in changed]
        if not records:
            errors.append("Scoped verification matched no Source records.")
    category_result = audit_categories(root)
    if complete_batch and not category_result["valid"]:
        errors.extend(["Category audit failed.", *category_result["errors"]])
    verified = 0
    structurally_verified = 0
    semantic_counts = {"pending": 0, "partial": 0, "reviewed": 0}
    covered: set[str] = set()
    catalog_only: set[str] = set()
    for record in records:
        record_error_count = len(errors)
        targets = record["raw_targets"]
        if len(targets) != 1:
            if len(targets) > 1:
                catalog_only.update(target.casefold() for target in targets)
            errors.append(f"Source record must cite exactly one Raw target: {record['relative']}")
            continue
        target = targets[0]
        raw_path = (root / target).resolve()
        if not raw_path.is_file() or root.joinpath("raw") not in raw_path.parents:
            errors.append(f"Missing or escaped raw source: {target}")
            continue
        front = record["frontmatter"]
        if root.joinpath("wiki", "sources") in record["path"].parents and independent_field(front, "type").casefold() != "source":
            errors.append(f"Source summary type is not source: {record['relative']}")
        strict_record = complete_batch or root.joinpath("wiki", "sources") in record["path"].parents
        if strict_record:
            if len(re.findall(r"(?m)^##+\s+", record["text"].split("---", 2)[-1])) < 3:
                errors.append(f"Source summary has too few sections: {record['relative']}")
            for key in ("concepts", "reflected_docs", "evidence_spans"):
                value = independent_int(front, key)
                if value is None or value <= 0:
                    errors.append(f"Source summary has invalid {key}: {record['relative']}")
            key_claims = independent_int(front, "key_claims")
            if key_claims is None or key_claims < 0:
                errors.append(f"Source summary has invalid key_claims: {record['relative']}")
            meaning_count = sum(
                independent_int(front, key) or 0
                for key in ("key_claims", "key_decisions", "next_actions")
            )
            if meaning_count <= 0:
                errors.append(f"Source summary has no Claim, Decision, or next action: {record['relative']}")
            declared_hash = independent_field(front, "raw_sha256").casefold()
            if declared_hash != raw_sha256(raw_path):
                errors.append(f"Source hash mismatch: {record['relative']}")
        for target_doc in record["wiki_targets"]:
            candidates = [root / "wiki" / target_doc, root / "wiki" / f"{target_doc}.md", root / target_doc, root / f"{target_doc}.md"]
            if not any(candidate.is_file() for candidate in candidates):
                errors.append(f"Reflected Wiki document is missing: {target_doc}")
        if not any(target.casefold().startswith("raw/") for target in targets):
            errors.append(f"Source summary has no raw citation: {record['relative']}")
        structural_ok = len(errors) == record_error_count
        if structural_ok:
            structurally_verified += 1
        semantic_required = (
            root.joinpath("wiki", "sources") in record["path"].parents
            or independent_field(front, "type").casefold() == "source"
            or bool(independent_field(front, "semantic_status"))
        )
        if semantic_required:
            semantic = review_source_record(root, record["path"], raw_path, record["text"])
            semantic_status = str(semantic["semantic_status"])
            semantic_counts[semantic_status] = semantic_counts.get(semantic_status, 0) + 1
            if semantic_status != "reviewed":
                errors.append(f"Semantic review is {semantic_status}: {record['relative']}")
            errors.extend(f"{record['relative']}: {error}" for error in semantic["errors"])
        if len(errors) == record_error_count:
            verified += 1
        covered.add(target.casefold())

    raw_keys = (
        {
            target.casefold()
            for record in records
            for target in record["raw_targets"]
            if len(record["raw_targets"]) == 1
        }
        if scoped_verification
        else {path.relative_to(root).as_posix().casefold() for path in raw_files}
    )
    missing = raw_keys - covered
    uncovered_attachments = {
        path.casefold()
        for path in exclusions["skipped"]
        if path.casefold() not in covered
    }
    if complete_batch:
        errors.extend(f"Raw source is rejected or empty: {path}" for path in exclusions["rejected"])
        errors.extend(
            f"Raw attachment lacks independent evidence: {path}"
            for path in sorted(uncovered_attachments)
        )
        errors.extend(f"Raw source has no independent source record: {path}" for path in sorted(missing))
        errors.extend(f"Catalog-only raw source: {path}" for path in sorted(catalog_only))

    strategy = graph_strategy(root)
    graph = graph_status(root, strategy)
    counts = graph_counts(root, graph_workspace(root))
    if require_graph:
        if graph not in {"configured", "graph_present"}:
            errors.append(f"Graphify is not ready: {graph}")
        host_manifest_error = graphify_host_manifest_error(root)
        if host_manifest_error:
            errors.append(host_manifest_error)
        freshness_error = graph_freshness_error(root)
        if freshness_error:
            errors.append(freshness_error)
        if verified and counts["nodes"] == 0:
            errors.append("Graphify has no verified source nodes")
        if verified and counts["links"] == 0:
            errors.append("Graphify has no verified source links")
        errors.extend(independent_graph_check(root, records))

    coverage = {
        "input": len(records) if scoped_verification else len(raw_files) + len(exclusions["skipped"]),
        "verified": verified,
        "structurally_verified": structurally_verified,
        "semantic_reviewed": semantic_counts["reviewed"],
        "semantic_partial": semantic_counts["partial"],
        "semantic_pending": semantic_counts["pending"],
        "pending": len(missing) + (0 if scoped_verification else len(uncovered_attachments)),
        "catalog_only": len(catalog_only),
        "rejected": 0,
        "skipped": 0 if scoped_verification else len(uncovered_attachments),
    }
    coverage["rejected"] = len(exclusions["rejected"])
    return {
        "status": "verified" if not errors else "verification_failed",
        "verified": not errors,
        "coverage": coverage,
        "graph_status": graph,
        "graph_contract": "structural_only",
        "graph_counts": counts,
        "category_audit": category_result,
        "errors": errors,
        "exit_code": 0 if not errors else 2,
    }


def semantic_plan(
    root: Path,
    values: Sequence[str] = (),
    *,
    max_lines: int = 400,
    overlap_lines: int = 20,
) -> dict[str, Any]:
    """Plan intra-file ranges so batch workers cannot silently skip a long tail."""
    raw_root = (root / "raw").resolve()
    if values:
        files: list[Path] = []
        for value in values:
            candidate = Path(value)
            if not candidate.is_absolute():
                candidate = root / candidate
            candidate = candidate.resolve()
            try:
                candidate.relative_to(raw_root)
            except ValueError as error:
                raise ValueError(f"Semantic-plan source must stay under raw/: {value}") from error
            if not candidate.is_file():
                raise ValueError(f"Semantic-plan source does not exist: {value}")
            files.append(candidate)
    else:
        files = independent_raw_files(root)
    plans = [semantic_partition(path, max_lines=max_lines, overlap_lines=overlap_lines) for path in files]
    for plan, path in zip(plans, files):
        plan["path"] = path.relative_to(root).as_posix()
    return {
        "root": str(root),
        "sources": len(plans),
        "long_sources": sum(plan["unit"] == "lines" and plan["total"] >= 300 for plan in plans),
        "coverage_complete": all(plan["coverage_complete"] for plan in plans),
        "plans": plans,
    }


def recover(root: Path) -> dict[str, Any]:
    recovery = root / "tools" / "graphify_knowledge" / "promote_candidate.py"
    if not recovery.is_file():
        return {
            "status": "recovery_unavailable",
            "root": str(root),
            "errors": ["This Wiki does not provide the curated Graphify recovery tool."],
            "exit_code": 2,
        }
    exit_code = run_command(
        [graph_python(root), str(recovery), "--workspace-root", str(root), "--recover"],
        cwd=root,
    )
    return {
        "status": "recovered" if exit_code == 0 else "recovery_failed",
        "root": str(root),
        "exit_code": exit_code,
    }


def print_json(payload: Any) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Portable LLM Wiki ingest support")
    subparsers = parser.add_subparsers(dest="command", required=True)

    for name in (
        "status",
        "scan",
        "semantic-plan",
        "finalize",
        "verify",
        "category-audit",
        "record-graphify-run",
        "recover",
    ):
        child = subparsers.add_parser(name)
        child.add_argument(
            "--root",
            default=None,
            help=(
                "LLM Wiki root. If omitted, use the invoking project; linked Git worktrees "
                "fall back to their primary checkout."
            ),
        )
        if name == "scan":
            child.add_argument("--json", action="store_true")
        if name == "semantic-plan":
            child.add_argument("--source", action="append", default=[])
            child.add_argument("--max-lines", type=int, default=400)
            child.add_argument("--overlap-lines", type=int, default=20)
        if name == "finalize":
            child.add_argument("--changed-file", action="append", default=[])
            child.add_argument(
                "--complete-batch",
                action="store_true",
                help="Fail unless no raw files remain pending or catalog-only.",
            )
        if name == "verify":
            child.add_argument("--require-graph", action="store_true")
            child.add_argument("--complete-batch", action="store_true")
            child.add_argument("--changed-file", action="append", default=[])
        if name == "record-graphify-run":
            child.add_argument("--host", choices=("codex", "claude"), required=True)
    return parser


def main() -> int:
    configure_utf8_stdout()
    parser = build_parser()
    args = parser.parse_args()
    try:
        root = resolve_wiki_root(args.root, skill_root=SCRIPT_ROOT.parent)
        adapter_exit = dispatch_configured_adapter(root, sys.argv[1:], runtime_path=Path(__file__))
    except (ValueError, AdapterError) as error:
        parser.error(str(error))
    if adapter_exit is not None:
        return adapter_exit

    if args.command == "status":
        workspace = graph_workspace(root)
        print_json(
            {
                "root": str(root),
                "graph_strategy": graph_strategy(root),
                "graph_workspace": str(workspace) if workspace is not None else None,
                "graph_status": graph_status(root),
                "coverage": coverage_summary(root),
                "graph_counts": graph_counts(root, workspace),
            }
        )
        return 0
    if args.command == "scan":
        result = scan(root)
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
                    reason = f" - {item['reason']}" if "reason" in item else ""
                    print(f"  - {item['path']} ({item['modified']}){reason}")
        return 0
    if args.command == "semantic-plan":
        try:
            print_json(
                semantic_plan(
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
        result = finalize(root, args.changed_file, complete_batch=args.complete_batch)
        print_json(result)
        return int(result["exit_code"])
    if args.command == "verify":
        result = verify(
            root,
            require_graph=args.require_graph,
            complete_batch=args.complete_batch,
            changed_files=args.changed_file,
        )
        print_json(result)
        return int(result["exit_code"])
    if args.command == "category-audit":
        result = audit_categories(root)
        print_json(result)
        return int(result["exit_code"])
    if args.command == "record-graphify-run":
        result = record_graphify_run(root, args.host)
        print_json(result)
        return int(result["exit_code"])
    result = recover(root)
    print_json(result)
    return int(result["exit_code"])


if __name__ == "__main__":
    raise SystemExit(main())
