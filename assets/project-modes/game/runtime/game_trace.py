from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Iterable

TRACEABILITY_SCHEMA_VERSION = 1
PROJECT_MODE = "game"
DEFAULT_INDEX = "wiki/game/traceability.json"
SOURCE_OF_TRUTH = (
    "vault game-spec frontmatter",
    "vault implementation-check frontmatter",
    "vault build, playtest, and decision frontmatter",
    "live project paths and Git revisions",
)
SPEC_FOLDERS = {
    "features": "feature",
    "systems": "system",
    "levels": "level",
    "content": "content",
    "narrative": "narrative",
    "ui-ux": "ui_ux",
    "technical": "technical",
    "assets": "asset",
}
STATUS_FIELDS = (
    "design_status",
    "implementation_status",
    "validation_status",
    "decision_status",
    "production_status",
)
KNOWN_CROSS_REFERENCE_IDS = {
    "build_id",
    "playtest_id",
    "decision_id",
    "check_id",
    "bug_id",
    "milestone_id",
}


class TraceError(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def normalize_rel_path(value: str) -> str:
    raw = value.strip().replace("\\", "/")
    while raw.startswith("./"):
        raw = raw[2:]
    if not raw:
        raise ValueError("path is empty")
    if raw.startswith("/") or re.match(r"^[A-Za-z]:/", raw):
        raise ValueError(f"path must be project-relative: {value}")
    parts = PurePosixPath(raw).parts
    if ".." in parts:
        raise ValueError(f"path escapes project root: {value}")
    return PurePosixPath(*parts).as_posix()


def _parse_scalar(raw: str) -> Any:
    value = raw.strip()
    if value == "":
        return ""
    if value in ("[]", "[ ]"):
        return []
    if value in ("{}", "{ }"):
        return {}
    lowered = value.lower()
    if lowered in ("true", "false"):
        return lowered == "true"
    if lowered in ("null", "none", "~"):
        return None
    if value.startswith("[") and value.endswith("]"):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return [item.strip().strip("\"'") for item in value[1:-1].split(",") if item.strip()]
    if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
        try:
            parsed = ast.literal_eval(value)
            return parsed if isinstance(parsed, str) else value[1:-1]
        except (SyntaxError, ValueError):
            return value[1:-1]
    if re.fullmatch(r"-?\d+", value):
        return int(value)
    if re.fullmatch(r"-?\d+\.\d+", value):
        return float(value)
    return value


def parse_frontmatter(path: Path) -> dict[str, Any]:
    lines = path.read_text(encoding="utf-8").splitlines()
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
        if ":" not in line or line[:1].isspace():
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


def as_string_list(value: Any) -> list[str]:
    if value is None or value == "":
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, (list, tuple)):
        return [str(item) for item in value if item not in (None, "")]
    return [str(value)]


def relative_to_root(root: Path, path: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def issue(severity: str, code: str, message: str, *, path: str | None = None, subject: str | None = None) -> dict[str, Any]:
    value: dict[str, Any] = {"severity": severity, "code": code, "message": message}
    if path:
        value["path"] = path
    if subject:
        value["subject"] = subject
    return value


def first_document_id(metadata: dict[str, Any], *, preferred: Iterable[str] = ()) -> str | None:
    for key in preferred:
        value = metadata.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    for key, value in metadata.items():
        if key.endswith("_id") and key not in KNOWN_CROSS_REFERENCE_IDS and isinstance(value, str) and value.strip():
            return value.strip()
    return None


def parse_code_ref(raw: str) -> dict[str, str | None]:
    value = raw.strip()
    path_part, separator, fragment = value.partition("#")
    path = normalize_rel_path(path_part)
    symbol: str | None = None
    locator: str | None = None
    if separator:
        symbol_part, locator_separator, locator_part = fragment.partition("@")
        symbol = symbol_part.strip() or None
        locator = locator_part.strip() if locator_separator and locator_part.strip() else None
    return {"path": path, "symbol": symbol, "locator": locator}


def code_node_id(ref: dict[str, str | None]) -> str:
    digest = hashlib.sha256(f"{ref['path']}#{ref.get('symbol') or ''}".encode("utf-8")).hexdigest()[:16]
    return f"CODE-{digest.upper()}"


def edge_id(source: str, relation: str, target: str) -> str:
    digest = hashlib.sha256(f"{source}|{relation}|{target}".encode("utf-8")).hexdigest()[:16]
    return f"TRACE-{digest.upper()}"


def run_git(project_root: Path, arguments: list[str], *, allow_failure: bool = False) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        ["git", "-C", str(project_root), *arguments],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0 and not allow_failure:
        raise TraceError(completed.stderr.strip() or completed.stdout.strip() or "git command failed")
    return completed


def current_revision(project_root: Path) -> str:
    completed = run_git(project_root, ["rev-parse", "HEAD"], allow_failure=True)
    return completed.stdout.strip() if completed.returncode == 0 else "UNKNOWN"


def changed_paths(project_root: Path, base: str, head: str) -> list[str]:
    completed = run_git(project_root, ["diff", "--name-only", f"{base}..{head}", "--"])
    values: list[str] = []
    for line in completed.stdout.splitlines():
        if line.strip():
            try:
                values.append(normalize_rel_path(line))
            except ValueError:
                continue
    return sorted(set(values))


def path_changed_since(project_root: Path, revision: str, head: str, path: str) -> tuple[bool | None, str | None]:
    if not revision or revision == "UNKNOWN" or head == "UNKNOWN":
        return None, "checked revision or current revision is unknown"
    completed = run_git(
        project_root,
        ["diff", "--name-only", f"{revision}..{head}", "--", path],
        allow_failure=True,
    )
    if completed.returncode != 0:
        return None, completed.stderr.strip() or "cannot compare checked revision"
    return any(line.strip() for line in completed.stdout.splitlines()), None


def _add_node(nodes: dict[str, dict[str, Any]], candidate: dict[str, Any], issues: list[dict[str, Any]]) -> None:
    node_id = str(candidate["id"])
    existing = nodes.get(node_id)
    if existing is None:
        nodes[node_id] = candidate
    elif existing != candidate:
        issues.append(
            issue(
                "error",
                "duplicate_node_id",
                f"node id {node_id} is defined by incompatible documents",
                path=str(candidate.get("path") or ""),
                subject=node_id,
            )
        )


def _ref_node(nodes: dict[str, dict[str, Any]], ref_id: str, kind: str, path: str | None = None) -> None:
    if ref_id in nodes:
        return
    node: dict[str, Any] = {"id": ref_id, "kind": kind, "resolved": False}
    if path:
        node["path"] = path
    nodes[ref_id] = node


def _add_simple_edge(edges: dict[str, dict[str, Any]], source: str, target: str, relation: str, source_path: str) -> None:
    identity = edge_id(source, relation, target)
    edge = edges.setdefault(
        identity,
        {"id": identity, "from": source, "to": target, "relation": relation, "sources": []},
    )
    edge["sources"] = sorted(set(as_string_list(edge.get("sources"))) | {source_path})


def _record_implementation_edge(
    edges: dict[str, dict[str, Any]],
    nodes: dict[str, dict[str, Any]],
    issues: list[dict[str, Any]],
    *,
    project_root: Path,
    head: str,
    spec_id: str,
    spec_path: str,
    code_raw: str,
    check: dict[str, Any] | None,
) -> None:
    try:
        ref = parse_code_ref(code_raw)
    except ValueError as error:
        issues.append(issue("error", "invalid_live_path", str(error), path=spec_path, subject=spec_id))
        return
    code_id = code_node_id(ref)
    code_path = str(ref["path"])
    code_file = project_root / code_path
    _add_node(
        nodes,
        {
            "id": code_id,
            "kind": "code",
            "path": code_path,
            "symbol": ref.get("symbol"),
            "exists": code_file.is_file(),
        },
        issues,
    )
    identity = edge_id(spec_id, "implemented_by", code_id)
    edge = edges.setdefault(
        identity,
        {
            "id": identity,
            "from": spec_id,
            "to": code_id,
            "relation": "implemented_by",
            "sources": [],
            "locators": [],
            "checks": [],
            "trace_status": "unverified",
            "stale_reasons": [],
        },
    )
    edge["sources"] = sorted(set(as_string_list(edge.get("sources"))) | {spec_path})
    if ref.get("locator"):
        edge["locators"] = sorted(set(as_string_list(edge.get("locators"))) | {str(ref["locator"])})
    if check:
        check_record = {
            "path": str(check["path"]),
            "check_id": check.get("check_id"),
            "checked_revision": check.get("source_revision") or "UNKNOWN",
            "checked_at": check.get("checked_at") or "UNKNOWN",
            "implementation_status": check.get("implementation_status") or "unknown",
            "validation_status": check.get("validation_status") or "untested",
            "build_id": check.get("build_id") or "UNKNOWN",
            "evidence_refs": sorted(as_string_list(check.get("evidence_refs"))),
        }
        edge["sources"] = sorted(set(edge["sources"]) | {str(check["path"])})
        encoded = {json.dumps(item, sort_keys=True, ensure_ascii=False) for item in edge["checks"]}
        if json.dumps(check_record, sort_keys=True, ensure_ascii=False) not in encoded:
            edge["checks"].append(check_record)

    if not code_file.is_file():
        edge["trace_status"] = "missing"
        edge["stale_reasons"] = [f"tracked live path does not exist: {code_path}"]
        issues.append(issue("error", "missing_live_path", edge["stale_reasons"][0], path=spec_path, subject=spec_id))
        return
    checks = sorted(edge["checks"], key=lambda item: (str(item.get("checked_at") or ""), str(item.get("path") or "")))
    edge["checks"] = checks
    if not checks:
        edge["trace_status"] = "unverified"
        edge["stale_reasons"] = ["no implementation check records this code relation"]
        return
    latest = checks[-1]
    edge["current_check"] = latest
    changed, comparison_error = path_changed_since(
        project_root,
        str(latest.get("checked_revision") or "UNKNOWN"),
        head,
        code_path,
    )
    if changed is True:
        edge["trace_status"] = "stale"
        edge["stale_reasons"] = [f"{code_path} changed after implementation check {latest.get('checked_revision') or 'UNKNOWN'}"]
    elif changed is False:
        edge["trace_status"] = "current"
        edge["stale_reasons"] = []
    else:
        edge["trace_status"] = "unverified"
        edge["stale_reasons"] = [comparison_error or "revision comparison unavailable"]


def _scan_documents(vault_root: Path, relative_dir: str) -> list[tuple[Path, dict[str, Any]]]:
    directory = vault_root / relative_dir
    if not directory.is_dir():
        return []
    values: list[tuple[Path, dict[str, Any]]] = []
    for path in sorted(directory.rglob("*.md")):
        if path.name.endswith(".wiki-proposed") or path.name.lower() in ("readme.md", "index.md", "claude.md"):
            continue
        values.append((path, parse_frontmatter(path)))
    return values


def _project_reference(vault_root: Path, project_root: Path) -> dict[str, str]:
    """Return the stable project reference declared by the vault layout.

    The vault is built under a temporary staging path and then atomically renamed
    into its final sidecar or embedded location. Recomputing a relative project
    path from the staging directory would change after that rename and make the
    newly generated traceability index stale immediately. The manifest stores the
    reference calculated for the final layout, so preserve that exact value.
    """
    manifest_path = vault_root / ".llm-wiki.json"
    if manifest_path.is_file():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            manifest = None
        game = manifest.get("game_project") if isinstance(manifest, dict) else None
        if isinstance(game, dict):
            value = game.get("project_root")
            kind = game.get("project_root_kind", "relative")
            if isinstance(value, str) and value and kind in ("relative", "absolute"):
                return {"kind": kind, "value": value}

    try:
        return {"kind": "relative", "value": os.path.relpath(project_root, vault_root).replace("\\", "/")}
    except ValueError:
        return {"kind": "absolute", "value": str(project_root)}


def build_index(vault_root: Path, project_root: Path | None = None) -> dict[str, Any]:
    vault = vault_root.resolve()
    project = (project_root or vault_root).resolve()
    head = current_revision(project)
    nodes: dict[str, dict[str, Any]] = {}
    edges: dict[str, dict[str, Any]] = {}
    issues: list[dict[str, Any]] = []
    specs: dict[str, dict[str, Any]] = {}

    for folder, subtype in SPEC_FOLDERS.items():
        for path, metadata in _scan_documents(vault, f"wiki/game/{folder}"):
            relative = relative_to_root(vault, path)
            spec_id = first_document_id(metadata, preferred=(f"{subtype}_id", "id"))
            if not spec_id:
                issues.append(issue("error", "missing_spec_id", "game spec has no stable *_id", path=relative))
                continue
            node: dict[str, Any] = {"id": spec_id, "kind": "spec", "subtype": subtype, "path": relative, "resolved": True}
            for field in STATUS_FIELDS:
                if field in metadata:
                    node[field] = metadata[field]
            for field in (
                "live_paths",
                "implementation_check_refs",
                "build_refs",
                "playtest_refs",
                "decision_refs",
                "evidence_refs",
            ):
                node[field] = sorted(as_string_list(metadata.get(field)))
            _add_node(nodes, node, issues)
            specs[spec_id] = {"node": node, "metadata": metadata}

    checks_by_subject: dict[str, list[dict[str, Any]]] = {}
    for path, metadata in _scan_documents(vault, "wiki/game/implementation"):
        relative = relative_to_root(vault, path)
        subject_id = str(metadata.get("subject_id") or "").strip()
        if not subject_id:
            issues.append(issue("error", "missing_subject_id", "implementation check has no subject_id", path=relative))
            continue
        check = dict(metadata)
        check["path"] = relative
        checks_by_subject.setdefault(subject_id, []).append(check)
        check_id = str(metadata.get("check_id") or f"CHECK:{relative}")
        _add_node(
            nodes,
            {
                "id": check_id,
                "kind": "implementation_check",
                "path": relative,
                "subject_id": subject_id,
                "source_revision": metadata.get("source_revision") or "UNKNOWN",
                "build_id": metadata.get("build_id") or "UNKNOWN",
                "implementation_status": metadata.get("implementation_status") or "unknown",
                "validation_status": metadata.get("validation_status") or "untested",
                "resolved": True,
            },
            issues,
        )
        if subject_id not in specs:
            issues.append(issue("warning", "unresolved_check_subject", f"implementation check references unknown spec {subject_id}", path=relative, subject=subject_id))

    for spec_id, spec in sorted(specs.items()):
        metadata = spec["metadata"]
        spec_path = str(spec["node"]["path"])
        by_ref: dict[str, list[dict[str, Any]]] = {}
        for check in checks_by_subject.get(spec_id, []):
            for raw in as_string_list(check.get("checked_paths")):
                try:
                    parsed = parse_code_ref(raw)
                except ValueError as error:
                    issues.append(issue("error", "invalid_checked_path", str(error), path=str(check["path"]), subject=spec_id))
                    continue
                key = f"{parsed['path']}#{parsed.get('symbol') or ''}"
                by_ref.setdefault(key, []).append(check)
        seen: set[str] = set()
        for raw in as_string_list(metadata.get("live_paths")):
            try:
                parsed = parse_code_ref(raw)
                key = f"{parsed['path']}#{parsed.get('symbol') or ''}"
            except ValueError as error:
                issues.append(issue("error", "invalid_live_path", str(error), path=spec_path, subject=spec_id))
                continue
            seen.add(key)
            for check in by_ref.get(key) or [None]:
                _record_implementation_edge(
                    edges,
                    nodes,
                    issues,
                    project_root=project,
                    head=head,
                    spec_id=spec_id,
                    spec_path=spec_path,
                    code_raw=raw,
                    check=check,
                )
        for key, matching in by_ref.items():
            if key in seen:
                continue
            path_part, _, symbol = key.partition("#")
            raw = path_part + (f"#{symbol}" if symbol else "")
            for check in matching:
                _record_implementation_edge(
                    edges,
                    nodes,
                    issues,
                    project_root=project,
                    head=head,
                    spec_id=spec_id,
                    spec_path=spec_path,
                    code_raw=raw,
                    check=check,
                )

    def scan_reference_documents(relative_dir: str, id_field: str, kind: str, relation: str, subject_field: str) -> None:
        for path, metadata in _scan_documents(vault, relative_dir):
            relative = relative_to_root(vault, path)
            node_id = first_document_id(metadata, preferred=(id_field,))
            if not node_id:
                issues.append(issue("error", f"missing_{id_field}", f"document has no {id_field}", path=relative))
                continue
            node: dict[str, Any] = {"id": node_id, "kind": kind, "path": relative, "resolved": True}
            for key in ("source_revision", "platform", "build_id", "validation_status", "decision_status"):
                if key in metadata:
                    node[key] = metadata[key]
            _add_node(nodes, node, issues)
            for spec_id in as_string_list(metadata.get(subject_field)):
                if spec_id not in specs:
                    issues.append(issue("warning", f"unresolved_{kind}_subject", f"{kind} references unknown spec {spec_id}", path=relative, subject=spec_id))
                _ref_node(nodes, spec_id, "spec")
                _add_simple_edge(edges, spec_id, node_id, relation, relative)

    scan_reference_documents("wiki/game/builds", "build_id", "build", "built_in", "subject_refs")
    scan_reference_documents("wiki/game/playtests", "playtest_id", "test", "validated_by", "subject_refs")
    scan_reference_documents("wiki/game/decisions", "decision_id", "decision", "governed_by", "affected_refs")

    for spec_id, spec in sorted(specs.items()):
        metadata = spec["metadata"]
        source_path = str(spec["node"]["path"])
        for field, kind, relation in (
            ("build_refs", "build", "built_in"),
            ("playtest_refs", "test", "validated_by"),
            ("decision_refs", "decision", "governed_by"),
        ):
            for ref_id in as_string_list(metadata.get(field)):
                _ref_node(nodes, ref_id, kind)
                _add_simple_edge(edges, spec_id, ref_id, relation, source_path)
        for check in checks_by_subject.get(spec_id, []):
            build_id = str(check.get("build_id") or "").strip()
            if build_id and build_id != "UNKNOWN":
                _ref_node(nodes, build_id, "build")
                _add_simple_edge(edges, spec_id, build_id, "built_in", str(check["path"]))
            for field, kind, relation in (
                ("playtest_refs", "test", "validated_by"),
                ("decision_refs", "decision", "governed_by"),
            ):
                for ref_id in as_string_list(check.get(field)):
                    _ref_node(nodes, ref_id, kind)
                    _add_simple_edge(edges, spec_id, ref_id, relation, str(check["path"]))

    for node in nodes.values():
        if node.get("kind") in ("spec", "build", "test", "decision") and node.get("resolved") is False:
            issues.append(issue("warning", "unresolved_reference", f"referenced {node['kind']} node {node['id']} has no matching document", subject=str(node["id"])))

    return {
        "schema_version": TRACEABILITY_SCHEMA_VERSION,
        "project_mode": PROJECT_MODE,
        "generated_at": utc_now(),
        "project_root": _project_reference(vault, project),
        "source_revision": head,
        "source_of_truth": list(SOURCE_OF_TRUTH),
        "nodes": sorted(nodes.values(), key=lambda item: (str(item.get("kind")), str(item.get("id")))),
        "edges": sorted(edges.values(), key=lambda item: str(item.get("id"))),
        "issues": sorted(
            issues,
            key=lambda item: (
                0 if item.get("severity") == "error" else 1,
                str(item.get("code")),
                str(item.get("path") or ""),
                str(item.get("subject") or ""),
            ),
        ),
    }


def write_index(path: Path, index: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_index(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise TraceError(f"traceability index is missing: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise TraceError(f"invalid traceability JSON: {error}") from error
    if not isinstance(value, dict):
        raise TraceError("traceability index root must be an object")
    if value.get("schema_version") != TRACEABILITY_SCHEMA_VERSION:
        raise TraceError(f"unsupported traceability schema: {value.get('schema_version')}")
    return value


def comparable_index(index: dict[str, Any]) -> dict[str, Any]:
    fields = ("schema_version", "project_mode", "project_root", "source_revision", "source_of_truth", "nodes", "edges", "issues")
    return {key: index.get(key) for key in fields}


def verification_summary(
    vault_root: Path,
    index_path: Path,
    project_root: Path | None = None,
    *,
    strict_stale: bool = False,
    strict_warnings: bool = False,
) -> dict[str, Any]:
    vault = vault_root.resolve()
    project = (project_root or vault_root).resolve()
    stored = load_index(index_path)
    current = build_index(vault, project)
    errors: list[str] = []
    warnings: list[str] = []
    if comparable_index(stored) != comparable_index(current):
        errors.append("traceability index is out of date; run rebuild")
    for item in current.get("issues", []):
        message = f"{item.get('code')}: {item.get('message')}"
        (errors if item.get("severity") == "error" else warnings).append(message)
    stale = [edge for edge in current.get("edges", []) if edge.get("trace_status") == "stale"]
    unverified = [edge for edge in current.get("edges", []) if edge.get("trace_status") in ("unverified", "missing")]
    if stale:
        (errors if strict_stale else warnings).append(f"{len(stale)} implementation relation(s) are stale")
    if strict_warnings and warnings:
        errors.extend(warnings)
    return {
        "ok": not errors,
        "index": relative_to_root(vault, index_path),
        "project_root": str(project),
        "source_revision": current.get("source_revision"),
        "node_count": len(current.get("nodes", [])),
        "edge_count": len(current.get("edges", [])),
        "stale_edge_count": len(stale),
        "unverified_edge_count": len(unverified),
        "errors": errors,
        "warnings": warnings,
    }


def _node_map(index: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(node["id"]): node for node in index.get("nodes", []) if isinstance(node, dict) and "id" in node}


def query_spec(index: dict[str, Any], spec_id: str) -> dict[str, Any]:
    nodes = _node_map(index)
    spec = nodes.get(spec_id)
    if not spec or spec.get("kind") != "spec":
        raise TraceError(f"spec not found: {spec_id}")
    edges = [edge for edge in index.get("edges", []) if edge.get("from") == spec_id]
    return {"spec": spec, "edges": edges, "linked_nodes": [nodes.get(str(edge.get("to")), {"id": edge.get("to"), "resolved": False}) for edge in edges]}


def query_path(index: dict[str, Any], raw_path: str) -> dict[str, Any]:
    query = parse_code_ref(raw_path)
    nodes = _node_map(index)
    matches = [
        node
        for node in nodes.values()
        if node.get("kind") == "code"
        and node.get("path") == query["path"]
        and (not query.get("symbol") or node.get("symbol") == query.get("symbol"))
    ]
    code_ids = {str(node["id"]) for node in matches}
    edges = [edge for edge in index.get("edges", []) if edge.get("to") in code_ids]
    return {"query": query, "code_nodes": matches, "edges": edges, "specs": [nodes.get(str(edge.get("from")), {"id": edge.get("from"), "resolved": False}) for edge in edges]}


def traceability_matrix(index: dict[str, Any]) -> list[dict[str, Any]]:
    nodes = _node_map(index)
    rows: list[dict[str, Any]] = []
    for spec in sorted((node for node in nodes.values() if node.get("kind") == "spec"), key=lambda item: str(item["id"])):
        spec_id = str(spec["id"])
        outbound = [edge for edge in index.get("edges", []) if edge.get("from") == spec_id]
        implementation = [edge for edge in outbound if edge.get("relation") == "implemented_by"]
        rows.append(
            {
                "spec_id": spec_id,
                "spec_path": spec.get("path"),
                "design_status": spec.get("design_status", "unknown"),
                "implementation_status": spec.get("implementation_status", "unknown"),
                "validation_status": spec.get("validation_status", "untested"),
                "code_relations": len(implementation),
                "current_code_relations": sum(edge.get("trace_status") == "current" for edge in implementation),
                "stale_code_relations": sum(edge.get("trace_status") == "stale" for edge in implementation),
                "unverified_code_relations": sum(edge.get("trace_status") in ("unverified", "missing") for edge in implementation),
                "builds": sorted(str(edge.get("to")) for edge in outbound if edge.get("relation") == "built_in"),
                "tests": sorted(str(edge.get("to")) for edge in outbound if edge.get("relation") == "validated_by"),
                "decisions": sorted(str(edge.get("to")) for edge in outbound if edge.get("relation") == "governed_by"),
            }
        )
    return rows


def affected_by_diff(project_root: Path, index: dict[str, Any], base: str, head: str) -> dict[str, Any]:
    changed = set(changed_paths(project_root, base, head))
    nodes = _node_map(index)
    reasons: dict[str, set[str]] = {}
    stale_edges: list[dict[str, Any]] = []
    for node in nodes.values():
        if node.get("kind") == "spec" and node.get("path") in changed:
            reasons.setdefault(str(node["id"]), set()).add(f"spec_changed:{node['path']}")
    for edge in index.get("edges", []):
        if edge.get("relation") != "implemented_by":
            continue
        code = nodes.get(str(edge.get("to")))
        if not code or code.get("path") not in changed:
            continue
        spec_id = str(edge.get("from"))
        reasons.setdefault(spec_id, set()).add(f"code_changed:{code.get('path')}")
        stale_edges.append(edge)
    return {
        "base": base,
        "head": head,
        "changed_paths": sorted(changed),
        "affected_specs": [{"spec_id": spec_id, "reasons": sorted(values)} for spec_id, values in sorted(reasons.items())],
        "stale_edges": sorted(stale_edges, key=lambda item: str(item.get("id"))),
    }


def resolve_directory(value: Path, label: str) -> Path:
    path = value.expanduser().resolve()
    if not path.is_dir():
        raise TraceError(f"{label} does not exist: {path}")
    return path


def project_root_from_manifest(vault_root: Path) -> Path | None:
    manifest_path = vault_root / ".llm-wiki.json"
    if not manifest_path.is_file():
        return None
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
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


def resolve_cli_roots(args: argparse.Namespace) -> tuple[Path, Path]:
    if args.root is not None:
        legacy = resolve_directory(args.root, "legacy root")
        return legacy, legacy
    vault = resolve_directory(args.vault_root, "vault root")
    project_value = args.project_root or project_root_from_manifest(vault)
    if project_value is None:
        raise TraceError("project root was not supplied and is missing from .llm-wiki.json")
    return vault, resolve_directory(project_value, "project root")


def print_json(value: Any, *, compact: bool) -> None:
    print(json.dumps(value, ensure_ascii=False, separators=(",", ":")) if compact else json.dumps(value, ensure_ascii=False, indent=2))


def main() -> int:
    parser = argparse.ArgumentParser(description="Build and query sidecar-safe game design-to-code traceability.")
    parser.add_argument("--vault-root", type=Path, default=Path.cwd(), help="LLM Wiki vault root. Defaults to cwd.")
    parser.add_argument("--project-root", type=Path, default=None, help="Live game project root. Defaults to the manifest reference.")
    parser.add_argument("--root", type=Path, default=None, help="Legacy alias that treats one root as both vault and project.")
    parser.add_argument("--index", default=DEFAULT_INDEX, help="Vault-relative traceability index path.")
    parser.add_argument("--compact", action="store_true")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("rebuild")
    verify = subparsers.add_parser("verify")
    verify.add_argument("--strict-stale", action="store_true")
    verify.add_argument("--strict-warnings", action="store_true")
    spec = subparsers.add_parser("spec")
    spec.add_argument("spec_id")
    path = subparsers.add_parser("path")
    path.add_argument("path")
    affected = subparsers.add_parser("affected")
    affected.add_argument("--base", required=True)
    affected.add_argument("--head", default="HEAD")
    subparsers.add_parser("matrix")
    args = parser.parse_args()
    try:
        vault_root, project_root = resolve_cli_roots(args)
        index_relative = normalize_rel_path(args.index)
        index_path = vault_root / index_relative
        if args.command == "rebuild":
            index = build_index(vault_root, project_root)
            write_index(index_path, index)
            result = {
                "ok": not any(item.get("severity") == "error" for item in index.get("issues", [])),
                "index": index_relative,
                "project_root": str(project_root),
                "source_revision": index.get("source_revision"),
                "node_count": len(index.get("nodes", [])),
                "edge_count": len(index.get("edges", [])),
                "issue_count": len(index.get("issues", [])),
                "stale_edge_count": sum(edge.get("trace_status") == "stale" for edge in index.get("edges", [])),
            }
            print_json(result, compact=args.compact)
            return 0
        if args.command == "verify":
            result = verification_summary(
                vault_root,
                index_path,
                project_root,
                strict_stale=args.strict_stale,
                strict_warnings=args.strict_warnings,
            )
            print_json(result, compact=args.compact)
            return 0 if result["ok"] else 1
        index = load_index(index_path)
        if args.command == "spec":
            result = query_spec(index, args.spec_id)
        elif args.command == "path":
            result = query_path(index, args.path)
        elif args.command == "affected":
            result = affected_by_diff(project_root, build_index(vault_root, project_root), args.base, args.head)
        else:
            result = {"rows": traceability_matrix(index)}
        print_json(result, compact=args.compact)
        return 0
    except (OSError, ValueError, TraceError) as error:
        print_json({"ok": False, "error": str(error)}, compact=getattr(args, "compact", False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
