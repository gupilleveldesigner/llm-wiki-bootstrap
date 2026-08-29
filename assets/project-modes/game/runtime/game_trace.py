from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Iterable

TRACEABILITY_SCHEMA_VERSION = 1
PROJECT_MODE = "game"
DEFAULT_INDEX = "wiki/game/traceability.json"
SOURCE_OF_TRUTH = (
    "wiki/game feature/system/level/content/narrative/ui-ux/technical/asset frontmatter",
    "wiki/game/implementation frontmatter",
    "wiki/game/builds, playtests, and decisions frontmatter",
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
            parsed = json.loads(value)
        except json.JSONDecodeError:
            parsed = [item.strip().strip("\"'") for item in value[1:-1].split(",") if item.strip()]
        return parsed
    if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
        try:
            parsed = ast.literal_eval(value)
            return parsed if isinstance(parsed, str) else value[1:-1]
        except (SyntaxError, ValueError):
            return value[1:-1]
    if re.fullmatch(r"-?\d+", value):
        try:
            return int(value)
        except ValueError:
            pass
    if re.fullmatch(r"-?\d+\.\d+", value):
        try:
            return float(value)
        except ValueError:
            pass
    return value


def parse_frontmatter(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
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
            item = stripped[1:].strip()
            result.setdefault(list_key, []).append(_parse_scalar(item))
            continue
        if ":" not in line or line[:1].isspace():
            list_key = None
            continue
        key, raw = line.split(":", 1)
        key = key.strip()
        if not key:
            list_key = None
            continue
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
    item: dict[str, Any] = {"severity": severity, "code": code, "message": message}
    if path:
        item["path"] = path
    if subject:
        item["subject"] = subject
    return item


def first_document_id(metadata: dict[str, Any], *, preferred: Iterable[str] = ()) -> str | None:
    for key in preferred:
        value = metadata.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    for key, value in metadata.items():
        if not key.endswith("_id") or key in KNOWN_CROSS_REFERENCE_IDS:
            continue
        if isinstance(value, str) and value.strip():
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
    identity = f"{ref['path']}#{ref.get('symbol') or ''}"
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:16]
    return f"CODE-{digest.upper()}"


def edge_id(source: str, relation: str, target: str) -> str:
    identity = f"{source}|{relation}|{target}"
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:16]
    return f"TRACE-{digest.upper()}"


def run_git(root: Path, arguments: list[str], *, allow_failure: bool = False) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        ["git", "-C", str(root), *arguments],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0 and not allow_failure:
        detail = completed.stderr.strip() or completed.stdout.strip() or "git command failed"
        raise TraceError(detail)
    return completed


def current_revision(root: Path) -> str:
    completed = run_git(root, ["rev-parse", "HEAD"], allow_failure=True)
    return completed.stdout.strip() if completed.returncode == 0 else "UNKNOWN"


def changed_paths(root: Path, base: str, head: str) -> list[str]:
    completed = run_git(root, ["diff", "--name-only", f"{base}..{head}", "--"])
    paths: list[str] = []
    for line in completed.stdout.splitlines():
        if not line.strip():
            continue
        try:
            paths.append(normalize_rel_path(line))
        except ValueError:
            continue
    return sorted(set(paths))


def path_changed_since(root: Path, revision: str, head: str, path: str) -> tuple[bool | None, str | None]:
    if not revision or revision == "UNKNOWN" or head == "UNKNOWN":
        return None, "checked revision or current revision is unknown"
    completed = run_git(root, ["diff", "--name-only", f"{revision}..{head}", "--", path], allow_failure=True)
    if completed.returncode != 0:
        detail = completed.stderr.strip() or "cannot compare checked revision"
        return None, detail
    changed = any(line.strip() for line in completed.stdout.splitlines())
    return changed, None


def _add_node(nodes: dict[str, dict[str, Any]], candidate: dict[str, Any], issues: list[dict[str, Any]]) -> None:
    node_id = str(candidate["id"])
    existing = nodes.get(node_id)
    if existing is None:
        nodes[node_id] = candidate
        return
    if existing != candidate:
        issues.append(
            issue(
                "error",
                "duplicate_node_id",
                f"node id {node_id} is defined by multiple incompatible documents",
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


def _add_simple_edge(
    edges: dict[str, dict[str, Any]],
    source: str,
    target: str,
    relation: str,
    source_path: str,
) -> None:
    identity = edge_id(source, relation, target)
    existing = edges.get(identity)
    if existing is None:
        edges[identity] = {
            "id": identity,
            "from": source,
            "to": target,
            "relation": relation,
            "sources": [source_path],
        }
        return
    sources = set(as_string_list(existing.get("sources")))
    sources.add(source_path)
    existing["sources"] = sorted(sources)


def _record_implementation_edge(
    edges: dict[str, dict[str, Any]],
    nodes: dict[str, dict[str, Any]],
    issues: list[dict[str, Any]],
    *,
    root: Path,
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
    code_file = root / code_path
    code_node: dict[str, Any] = {
        "id": code_id,
        "kind": "code",
        "path": code_path,
        "symbol": ref.get("symbol"),
        "exists": code_file.is_file(),
    }
    _add_node(nodes, code_node, issues)

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
    sources = set(as_string_list(edge.get("sources")))
    sources.add(spec_path)
    locators = set(as_string_list(edge.get("locators")))
    if ref.get("locator"):
        locators.add(str(ref["locator"]))
    if check:
        check_path = str(check["path"])
        sources.add(check_path)
        check_record = {
            "path": check_path,
            "check_id": check.get("check_id"),
            "checked_revision": check.get("source_revision") or "UNKNOWN",
            "checked_at": check.get("checked_at") or "UNKNOWN",
            "implementation_status": check.get("implementation_status") or "unknown",
            "validation_status": check.get("validation_status") or "untested",
            "build_id": check.get("build_id") or "UNKNOWN",
            "evidence_refs": sorted(as_string_list(check.get("evidence_refs"))),
        }
        existing_checks = {json.dumps(item, sort_keys=True, ensure_ascii=False) for item in edge["checks"]}
        encoded = json.dumps(check_record, sort_keys=True, ensure_ascii=False)
        if encoded not in existing_checks:
            edge["checks"].append(check_record)
    edge["sources"] = sorted(sources)
    edge["locators"] = sorted(locators)

    if not code_file.is_file():
        edge["trace_status"] = "missing"
        edge["stale_reasons"] = [f"tracked live path does not exist: {code_path}"]
        issues.append(
            issue(
                "error",
                "missing_live_path",
                f"tracked live path does not exist: {code_path}",
                path=spec_path,
                subject=spec_id,
            )
        )
        return

    checks = sorted(
        edge["checks"],
        key=lambda item: (str(item.get("checked_at") or ""), str(item.get("path") or "")),
    )
    edge["checks"] = checks
    if not checks:
        edge["trace_status"] = "unverified"
        edge["stale_reasons"] = ["no implementation check records this code relation"]
        return

    latest = checks[-1]
    edge["current_check"] = latest
    changed, comparison_error = path_changed_since(
        root,
        str(latest.get("checked_revision") or "UNKNOWN"),
        head,
        code_path,
    )
    if changed is True:
        edge["trace_status"] = "stale"
        edge["stale_reasons"] = [
            f"{code_path} changed after implementation check {latest.get('checked_revision') or 'UNKNOWN'}"
        ]
    elif changed is False:
        edge["trace_status"] = "current"
        edge["stale_reasons"] = []
    else:
        edge["trace_status"] = "unverified"
        edge["stale_reasons"] = [comparison_error or "revision comparison unavailable"]


def _scan_documents(root: Path, relative_dir: str) -> list[tuple[Path, dict[str, Any]]]:
    directory = root / relative_dir
    if not directory.is_dir():
        return []
    documents: list[tuple[Path, dict[str, Any]]] = []
    for path in sorted(directory.rglob("*.md")):
        if path.name.endswith(".wiki-proposed") or path.name.lower() in ("readme.md", "index.md", "claude.md"):
            continue
        documents.append((path, parse_frontmatter(path)))
    return documents


def build_index(root: Path) -> dict[str, Any]:
    root = root.resolve()
    head = current_revision(root)
    nodes: dict[str, dict[str, Any]] = {}
    edges: dict[str, dict[str, Any]] = {}
    issues: list[dict[str, Any]] = []
    specs: dict[str, dict[str, Any]] = {}

    for folder, subtype in SPEC_FOLDERS.items():
        for path, metadata in _scan_documents(root, f"wiki/game/{folder}"):
            relative = relative_to_root(root, path)
            spec_id = first_document_id(metadata, preferred=(f"{subtype}_id", "id"))
            if not spec_id:
                issues.append(issue("error", "missing_spec_id", "game spec has no stable *_id", path=relative))
                continue
            node: dict[str, Any] = {
                "id": spec_id,
                "kind": "spec",
                "subtype": subtype,
                "path": relative,
                "resolved": True,
            }
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

    implementation_checks: dict[str, list[dict[str, Any]]] = {}
    for path, metadata in _scan_documents(root, "wiki/game/implementation"):
        relative = relative_to_root(root, path)
        subject_id = str(metadata.get("subject_id") or "").strip()
        if not subject_id:
            issues.append(issue("error", "missing_subject_id", "implementation check has no subject_id", path=relative))
            continue
        check = dict(metadata)
        check["path"] = relative
        implementation_checks.setdefault(subject_id, []).append(check)
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
            issues.append(
                issue(
                    "warning",
                    "unresolved_check_subject",
                    f"implementation check references unknown spec {subject_id}",
                    path=relative,
                    subject=subject_id,
                )
            )

    for spec_id, spec in sorted(specs.items()):
        node = spec["node"]
        metadata = spec["metadata"]
        checks = implementation_checks.get(spec_id, [])
        by_path: dict[str, list[dict[str, Any]]] = {}
        for check in checks:
            for raw in as_string_list(check.get("checked_paths")):
                try:
                    parsed = parse_code_ref(raw)
                    key = f"{parsed['path']}#{parsed.get('symbol') or ''}"
                except ValueError as error:
                    issues.append(issue("error", "invalid_checked_path", str(error), path=str(check["path"]), subject=spec_id))
                    continue
                by_path.setdefault(key, []).append(check)

        seen_keys: set[str] = set()
        for raw in as_string_list(metadata.get("live_paths")):
            try:
                parsed = parse_code_ref(raw)
                key = f"{parsed['path']}#{parsed.get('symbol') or ''}"
            except ValueError as error:
                issues.append(issue("error", "invalid_live_path", str(error), path=str(node["path"]), subject=spec_id))
                continue
            seen_keys.add(key)
            matched_checks = by_path.get(key) or [None]
            for check in matched_checks:
                _record_implementation_edge(
                    edges,
                    nodes,
                    issues,
                    root=root,
                    head=head,
                    spec_id=spec_id,
                    spec_path=str(node["path"]),
                    code_raw=raw,
                    check=check,
                )
        for key, matching_checks in by_path.items():
            if key in seen_keys:
                continue
            parsed_path, _, parsed_symbol = key.partition("#")
            raw = parsed_path + (f"#{parsed_symbol}" if parsed_symbol else "")
            for check in matching_checks:
                _record_implementation_edge(
                    edges,
                    nodes,
                    issues,
                    root=root,
                    head=head,
                    spec_id=spec_id,
                    spec_path=str(node["path"]),
                    code_raw=raw,
                    check=check,
                )

    for path, metadata in _scan_documents(root, "wiki/game/builds"):
        relative = relative_to_root(root, path)
        build_id = first_document_id(metadata, preferred=("build_id",))
        if not build_id:
            issues.append(issue("error", "missing_build_id", "build report has no build_id", path=relative))
            continue
        _add_node(
            nodes,
            {
                "id": build_id,
                "kind": "build",
                "path": relative,
                "source_revision": metadata.get("source_revision") or "UNKNOWN",
                "platform": metadata.get("platform") or "UNKNOWN",
                "validation_status": metadata.get("validation_status") or "untested",
                "resolved": True,
            },
            issues,
        )
        for spec_id in as_string_list(metadata.get("subject_refs")):
            if spec_id not in specs:
                issues.append(issue("warning", "unresolved_build_subject", f"build references unknown spec {spec_id}", path=relative, subject=spec_id))
            _ref_node(nodes, spec_id, "spec")
            _add_simple_edge(edges, spec_id, build_id, "built_in", relative)

    for path, metadata in _scan_documents(root, "wiki/game/playtests"):
        relative = relative_to_root(root, path)
        playtest_id = first_document_id(metadata, preferred=("playtest_id",))
        if not playtest_id:
            issues.append(issue("error", "missing_playtest_id", "playtest report has no playtest_id", path=relative))
            continue
        _add_node(
            nodes,
            {
                "id": playtest_id,
                "kind": "test",
                "subtype": "playtest",
                "path": relative,
                "build_id": metadata.get("build_id") or "UNKNOWN",
                "validation_status": metadata.get("validation_status") or "untested",
                "resolved": True,
            },
            issues,
        )
        for spec_id in as_string_list(metadata.get("subject_refs")):
            if spec_id not in specs:
                issues.append(issue("warning", "unresolved_playtest_subject", f"playtest references unknown spec {spec_id}", path=relative, subject=spec_id))
            _ref_node(nodes, spec_id, "spec")
            _add_simple_edge(edges, spec_id, playtest_id, "validated_by", relative)

    for path, metadata in _scan_documents(root, "wiki/game/decisions"):
        relative = relative_to_root(root, path)
        decision_id = first_document_id(metadata, preferred=("decision_id",))
        if not decision_id:
            issues.append(issue("error", "missing_decision_id", "decision record has no decision_id", path=relative))
            continue
        _add_node(
            nodes,
            {
                "id": decision_id,
                "kind": "decision",
                "path": relative,
                "decision_status": metadata.get("decision_status") or "proposed",
                "resolved": True,
            },
            issues,
        )
        for spec_id in as_string_list(metadata.get("affected_refs")):
            if spec_id not in specs:
                issues.append(issue("warning", "unresolved_decision_subject", f"decision references unknown spec {spec_id}", path=relative, subject=spec_id))
            _ref_node(nodes, spec_id, "spec")
            _add_simple_edge(edges, spec_id, decision_id, "governed_by", relative)

    collection_fields = (
        ("build_refs", "build", "built_in"),
        ("playtest_refs", "test", "validated_by"),
        ("decision_refs", "decision", "governed_by"),
    )
    for spec_id, spec in sorted(specs.items()):
        node = spec["node"]
        metadata = spec["metadata"]
        for field, kind, relation in collection_fields:
            for ref_id in as_string_list(metadata.get(field)):
                _ref_node(nodes, ref_id, kind)
                _add_simple_edge(edges, spec_id, ref_id, relation, str(node["path"]))
        for check in implementation_checks.get(spec_id, []):
            build_id = str(check.get("build_id") or "").strip()
            if build_id and build_id != "UNKNOWN":
                _ref_node(nodes, build_id, "build")
                _add_simple_edge(edges, spec_id, build_id, "built_in", str(check["path"]))
            for field, kind, relation in (("playtest_refs", "test", "validated_by"), ("decision_refs", "decision", "governed_by")):
                for ref_id in as_string_list(check.get(field)):
                    _ref_node(nodes, ref_id, kind)
                    _add_simple_edge(edges, spec_id, ref_id, relation, str(check["path"]))

    for node in nodes.values():
        if node.get("kind") in ("spec", "build", "test", "decision") and node.get("resolved") is False:
            issues.append(
                issue(
                    "warning",
                    "unresolved_reference",
                    f"referenced {node['kind']} node {node['id']} has no matching document",
                    subject=str(node["id"]),
                )
            )

    ordered_nodes = sorted(nodes.values(), key=lambda item: (str(item.get("kind")), str(item.get("id"))))
    ordered_edges = sorted(edges.values(), key=lambda item: str(item.get("id")))
    ordered_issues = sorted(
        issues,
        key=lambda item: (
            0 if item.get("severity") == "error" else 1,
            str(item.get("code")),
            str(item.get("path") or ""),
            str(item.get("subject") or ""),
        ),
    )
    return {
        "schema_version": TRACEABILITY_SCHEMA_VERSION,
        "project_mode": PROJECT_MODE,
        "generated_at": utc_now(),
        "source_revision": head,
        "source_of_truth": list(SOURCE_OF_TRUTH),
        "nodes": ordered_nodes,
        "edges": ordered_edges,
        "issues": ordered_issues,
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
        raise TraceError(
            f"unsupported traceability schema: {value.get('schema_version')}; expected {TRACEABILITY_SCHEMA_VERSION}"
        )
    return value


def comparable_index(index: dict[str, Any]) -> dict[str, Any]:
    return {key: index.get(key) for key in ("schema_version", "project_mode", "source_revision", "source_of_truth", "nodes", "edges", "issues")}


def verification_summary(root: Path, index_path: Path, *, strict_stale: bool = False, strict_warnings: bool = False) -> dict[str, Any]:
    stored = load_index(index_path)
    current = build_index(root)
    errors: list[str] = []
    warnings: list[str] = []
    if comparable_index(stored) != comparable_index(current):
        errors.append("traceability index is out of date; run rebuild")
    for item in current.get("issues", []):
        message = f"{item.get('code')}: {item.get('message')}"
        if item.get("severity") == "error":
            errors.append(message)
        else:
            warnings.append(message)
    stale_edges = [edge for edge in current.get("edges", []) if edge.get("trace_status") == "stale"]
    unverified_edges = [edge for edge in current.get("edges", []) if edge.get("trace_status") in ("unverified", "missing")]
    if strict_stale and stale_edges:
        errors.append(f"{len(stale_edges)} implementation relation(s) are stale")
    elif stale_edges:
        warnings.append(f"{len(stale_edges)} implementation relation(s) are stale")
    if strict_warnings and warnings:
        errors.extend(warnings)
    return {
        "ok": not errors,
        "index": relative_to_root(root, index_path),
        "source_revision": current.get("source_revision"),
        "node_count": len(current.get("nodes", [])),
        "edge_count": len(current.get("edges", [])),
        "stale_edge_count": len(stale_edges),
        "unverified_edge_count": len(unverified_edges),
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
    outbound = [edge for edge in index.get("edges", []) if edge.get("from") == spec_id]
    linked = [nodes.get(str(edge.get("to")), {"id": edge.get("to"), "resolved": False}) for edge in outbound]
    return {"spec": spec, "edges": outbound, "linked_nodes": linked}


def query_path(index: dict[str, Any], raw_path: str) -> dict[str, Any]:
    query = parse_code_ref(raw_path)
    nodes = _node_map(index)
    matches = []
    for node in nodes.values():
        if node.get("kind") != "code" or node.get("path") != query["path"]:
            continue
        if query.get("symbol") and node.get("symbol") != query.get("symbol"):
            continue
        matches.append(node)
    code_ids = {str(node["id"]) for node in matches}
    incoming = [edge for edge in index.get("edges", []) if edge.get("to") in code_ids]
    specs = [nodes.get(str(edge.get("from")), {"id": edge.get("from"), "resolved": False}) for edge in incoming]
    return {"query": query, "code_nodes": matches, "edges": incoming, "specs": specs}


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


def affected_by_diff(root: Path, index: dict[str, Any], base: str, head: str) -> dict[str, Any]:
    changed = set(changed_paths(root, base, head))
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
        "affected_specs": [
            {"spec_id": spec_id, "reasons": sorted(values)} for spec_id, values in sorted(reasons.items())
        ],
        "stale_edges": sorted(stale_edges, key=lambda item: str(item.get("id"))),
    }


def resolve_root(value: Path) -> Path:
    root = value.resolve()
    if not root.is_dir():
        raise TraceError(f"project root does not exist: {root}")
    return root


def print_json(value: Any, *, compact: bool) -> None:
    if compact:
        print(json.dumps(value, ensure_ascii=False, separators=(",", ":")))
    else:
        print(json.dumps(value, ensure_ascii=False, indent=2))


def main() -> int:
    parser = argparse.ArgumentParser(description="Build and query game design-to-code traceability.")
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="Game project root. Defaults to the current directory.")
    parser.add_argument("--index", default=DEFAULT_INDEX, help="Project-relative traceability index path.")
    parser.add_argument("--compact", action="store_true", help="Emit compact JSON.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("rebuild", help="Rebuild the derived traceability index from canonical game documents.")

    verify_parser = subparsers.add_parser("verify", help="Verify the stored index, references, and staleness.")
    verify_parser.add_argument("--strict-stale", action="store_true", help="Treat stale implementation relations as errors.")
    verify_parser.add_argument("--strict-warnings", action="store_true", help="Treat warnings as errors.")

    spec_parser = subparsers.add_parser("spec", help="Show code, build, test, and decision links for one spec ID.")
    spec_parser.add_argument("spec_id")

    path_parser = subparsers.add_parser("path", help="Reverse-query specs linked to a live code path or path#symbol.")
    path_parser.add_argument("path")

    affected_parser = subparsers.add_parser("affected", help="Map a Git diff to affected specs and stale code relations.")
    affected_parser.add_argument("--base", required=True)
    affected_parser.add_argument("--head", default="HEAD")

    subparsers.add_parser("matrix", help="Emit one traceability summary row per spec.")

    args = parser.parse_args()
    try:
        root = resolve_root(args.root)
        index_relative = normalize_rel_path(args.index)
        index_path = root / index_relative
        if args.command == "rebuild":
            index = build_index(root)
            write_index(index_path, index)
            result = {
                "ok": not any(item.get("severity") == "error" for item in index.get("issues", [])),
                "index": index_relative,
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
                root,
                index_path,
                strict_stale=args.strict_stale,
                strict_warnings=args.strict_warnings,
            )
            print_json(result, compact=args.compact)
            return 0 if result["ok"] else 1

        index = load_index(index_path)
        if args.command == "spec":
            print_json(query_spec(index, args.spec_id), compact=args.compact)
        elif args.command == "path":
            print_json(query_path(index, args.path), compact=args.compact)
        elif args.command == "affected":
            current = build_index(root)
            print_json(affected_by_diff(root, current, args.base, args.head), compact=args.compact)
        elif args.command == "matrix":
            print_json({"rows": traceability_matrix(index)}, compact=args.compact)
        return 0
    except (OSError, ValueError, TraceError) as error:
        print_json({"ok": False, "error": str(error)}, compact=getattr(args, "compact", False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
