from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import re
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Iterable

TRACEABILITY_SCHEMA_VERSION = 2
SYNC_BASELINE_VERSION = 1
SPEC_DIGEST_VERSION = 1
CODE_FINGERPRINT_VERSION = 1
PROJECT_MODE = "game"
DEFAULT_INDEX = "wiki/game/traceability.json"
DESIGN_START_MARKER = "<!-- GAME-SYNC:DESIGN-START -->"
DESIGN_END_MARKER = "<!-- GAME-SYNC:DESIGN-END -->"
SOURCE_OF_TRUTH = (
    "vault game-spec frontmatter and marked design body",
    "vault implementation-check frontmatter with accepted sync baselines",
    "vault build, playtest, and decision frontmatter",
    "live project paths, fingerprints, and Git revisions",
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
OPERATIONAL_FRONTMATTER_FIELDS = {
    *STATUS_FIELDS,
    "owners",
    "implementation_check_refs",
    "build_refs",
    "playtest_refs",
    "decision_refs",
    "evidence_refs",
    "updated",
    "checked_at",
    "source_revision",
    "checked_project_revision",
    "checked_vault_revision",
    "checked_project_dirty",
    "checked_spec_digest",
    "checked_spec_digest_version",
    "checked_code_fingerprints",
    "checked_code_fingerprint_version",
    "sync_baseline_status",
}
OPERATIONAL_SECTION_HEADINGS = {
    "기획 ↔ 코드 추적",
    "실제 구현 상태",
    "검증 계획과 결과",
    "플레이테스트 결과",
    "결정과 변경 이력",
    "결정 이력",
    "실제 상태",
    "검증",
    "design ↔ code traceability",
    "actual implementation status",
    "implementation status",
    "validation plan and results",
    "playtest results",
    "decisions and change history",
    "decision history",
    "actual state",
    "validation",
}
SYNC_CHANGED_STATUSES = {"design_changed", "code_changed", "both_changed"}
SYNC_BLOCKING_STATUSES = {"design_changed", "code_changed", "both_changed", "unverified", "missing"}


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


def split_frontmatter_text(text: str) -> tuple[list[str], list[str]]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return [], lines
    try:
        end = next(index for index in range(1, len(lines)) if lines[index].strip() == "---")
    except StopIteration:
        return [], lines
    return lines[1:end], lines[end + 1 :]


def parse_frontmatter_text(text: str) -> dict[str, Any]:
    frontmatter, _ = split_frontmatter_text(text)
    result: dict[str, Any] = {}
    list_key: str | None = None
    for line in frontmatter:
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


def parse_frontmatter(path: Path) -> dict[str, Any]:
    return parse_frontmatter_text(path.read_text(encoding="utf-8"))


def _yaml_scalar(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    return json.dumps(str(value), ensure_ascii=False)


def update_frontmatter_fields(path: Path, updates: dict[str, Any]) -> None:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise TraceError(f"document has no YAML frontmatter: {path}")
    try:
        end = next(index for index in range(1, len(lines)) if lines[index].strip() == "---")
    except StopIteration as error:
        raise TraceError(f"document has unterminated YAML frontmatter: {path}") from error

    kept: list[str] = []
    index = 1
    while index < end:
        line = lines[index]
        is_key = bool(line and not line[:1].isspace() and ":" in line)
        if not is_key:
            kept.append(line)
            index += 1
            continue
        key = line.split(":", 1)[0].strip()
        start = index
        index += 1
        while index < end:
            candidate = lines[index]
            if candidate and not candidate[:1].isspace() and ":" in candidate:
                break
            index += 1
        if key not in updates:
            kept.extend(lines[start:index])

    rendered = list(kept)
    if rendered and rendered[-1].strip():
        rendered.append("")
    for key, value in updates.items():
        if isinstance(value, list):
            if not value:
                rendered.append(f"{key}: []")
            else:
                rendered.append(f"{key}:")
                rendered.extend(f"  - {_yaml_scalar(item)}" for item in value)
        else:
            rendered.append(f"{key}: {_yaml_scalar(value)}")

    output = ["---", *rendered, "---", *lines[end + 1 :]]
    normalized = "\n".join(output).rstrip() + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", newline="\n", delete=False, dir=path.parent) as handle:
        handle.write(normalized)
        temporary = Path(handle.name)
    temporary.replace(path)


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


def canonical_code_ref(ref: dict[str, str | None]) -> str:
    value = str(ref["path"])
    if ref.get("symbol"):
        value += f"#{ref['symbol']}"
    if ref.get("locator"):
        value += f"@{ref['locator']}"
    return value


def code_ref_identity(ref: dict[str, str | None]) -> str:
    return f"{ref['path']}#{ref.get('symbol') or ''}"


def code_node_id(ref: dict[str, str | None]) -> str:
    digest = hashlib.sha256(code_ref_identity(ref).encode("utf-8")).hexdigest()[:16]
    return f"CODE-{digest.upper()}"


def edge_id(source: str, relation: str, target: str) -> str:
    digest = hashlib.sha256(f"{source}|{relation}|{target}".encode("utf-8")).hexdigest()[:16]
    return f"TRACE-{digest.upper()}"


def _canonicalize_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _canonicalize_value(value[key]) for key in sorted(value)}
    if isinstance(value, list):
        normalized = [_canonicalize_value(item) for item in value]
        if all(isinstance(item, (str, int, float, bool, type(None))) for item in normalized):
            return sorted(normalized, key=lambda item: json.dumps(item, ensure_ascii=False, sort_keys=True))
        return normalized
    return value


def _semantic_body(body_lines: list[str]) -> str:
    body = "\n".join(body_lines)
    if DESIGN_START_MARKER in body and DESIGN_END_MARKER in body:
        start = body.index(DESIGN_START_MARKER) + len(DESIGN_START_MARKER)
        end = body.index(DESIGN_END_MARKER, start)
        selected = body[start:end]
    else:
        selected_lines: list[str] = []
        skip = False
        for line in body_lines:
            heading = re.match(r"^##\s+(.+?)\s*$", line)
            if heading:
                title = heading.group(1).strip().casefold()
                skip = title in {item.casefold() for item in OPERATIONAL_SECTION_HEADINGS}
            if not skip:
                selected_lines.append(line)
        selected = "\n".join(selected_lines)
    normalized_lines = [re.sub(r"[ \t]+$", "", line) for line in selected.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    while normalized_lines and not normalized_lines[0].strip():
        normalized_lines.pop(0)
    while normalized_lines and not normalized_lines[-1].strip():
        normalized_lines.pop()
    return "\n".join(normalized_lines)


def spec_digest(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    metadata = parse_frontmatter_text(text)
    _, body_lines = split_frontmatter_text(text)
    semantic_metadata = {
        key: _canonicalize_value(value)
        for key, value in metadata.items()
        if key not in OPERATIONAL_FRONTMATTER_FIELDS
    }
    payload = {
        "version": SPEC_DIGEST_VERSION,
        "frontmatter": dict(sorted(semantic_metadata.items())),
        "body": _semantic_body(body_lines),
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _line_range(locator: str | None) -> tuple[int, int] | None:
    if not locator:
        return None
    match = re.search(r"(?:lines?|line|L)\s*(\d+)\s*(?:-|:|\.\.)\s*(\d+)", locator, re.IGNORECASE)
    if not match:
        return None
    start = int(match.group(1))
    end = int(match.group(2))
    if start < 1 or end < start:
        return None
    return start, end


def code_fingerprint(project_root: Path, raw_ref: str) -> dict[str, Any]:
    ref = parse_code_ref(raw_ref)
    canonical = canonical_code_ref(ref)
    path = project_root / str(ref["path"])
    if not path.is_file():
        return {
            "ref": canonical,
            "identity": code_ref_identity(ref),
            "exists": False,
            "digest": None,
            "scope": "missing",
        }
    line_range = _line_range(ref.get("locator"))
    if line_range:
        start, end = line_range
        text = path.read_text(encoding="utf-8", errors="replace").replace("\r\n", "\n").replace("\r", "\n")
        lines = text.split("\n")
        selected = "\n".join(lines[start - 1 : end]).encode("utf-8")
        scope = f"lines:{start}-{end}"
    else:
        selected = path.read_bytes()
        scope = "file"
    payload = canonical.encode("utf-8") + b"\0" + scope.encode("utf-8") + b"\0" + selected
    return {
        "ref": canonical,
        "identity": code_ref_identity(ref),
        "exists": True,
        "digest": "sha256:" + hashlib.sha256(payload).hexdigest(),
        "scope": scope,
        "size": len(selected),
    }


def encode_code_fingerprint(fingerprint: dict[str, Any]) -> str:
    digest = fingerprint.get("digest") or "MISSING"
    return f"{fingerprint['ref']}|{digest}"


def parse_code_fingerprint_entry(value: str) -> tuple[str, str] | None:
    if "|" not in value:
        return None
    ref_raw, digest = value.rsplit("|", 1)
    try:
        identity = code_ref_identity(parse_code_ref(ref_raw))
    except ValueError:
        return None
    if digest != "MISSING" and not re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
        return None
    return identity, digest


def fingerprint_map(values: Any) -> dict[str, str]:
    result: dict[str, str] = {}
    for value in as_string_list(values):
        parsed = parse_code_fingerprint_entry(value)
        if parsed:
            result[parsed[0]] = parsed[1]
    return result


def run_git(path: Path, arguments: list[str], *, allow_failure: bool = False) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        ["git", "-C", str(path), *arguments],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0 and not allow_failure:
        raise TraceError(completed.stderr.strip() or completed.stdout.strip() or "git command failed")
    return completed


def git_context(project_root: Path) -> tuple[Path, str] | None:
    completed = run_git(project_root, ["rev-parse", "--show-toplevel"], allow_failure=True)
    if completed.returncode != 0 or not completed.stdout.strip():
        return None
    repository_root = Path(completed.stdout.strip()).resolve()
    try:
        prefix = project_root.resolve().relative_to(repository_root).as_posix()
    except ValueError:
        return None
    return repository_root, "" if prefix == "." else prefix


def current_revision(root: Path) -> str:
    context = git_context(root)
    if not context:
        return "UNKNOWN"
    repository_root, _ = context
    completed = run_git(repository_root, ["rev-parse", "HEAD"], allow_failure=True)
    return completed.stdout.strip() if completed.returncode == 0 else "UNKNOWN"


def current_vault_revision(vault_root: Path) -> str:
    """Return a vault revision only when the vault is its own Git worktree.

    Embedded vaults are assembled in a staging directory and atomically renamed
    under the live project's repository. Inheriting a parent repository after the
    rename would make a freshly generated index appear out of date. The canonical
    design baseline is the spec digest, so parent-repository discovery is neither
    required nor safe here.
    """
    if not (vault_root / ".git").exists():
        return "UNKNOWN"
    return current_revision(vault_root)


def _repo_relative_path(project_root: Path, project_relative: str) -> tuple[Path, str] | None:
    context = git_context(project_root)
    if not context:
        return None
    repository_root, prefix = context
    value = normalize_rel_path(project_relative)
    return repository_root, f"{prefix}/{value}" if prefix else value


def changed_paths(project_root: Path, base: str, head: str) -> list[str]:
    context = git_context(project_root)
    if not context:
        raise TraceError("live project is not inside a Git repository")
    repository_root, prefix = context
    pathspec = prefix or "."
    completed = run_git(repository_root, ["diff", "--name-only", f"{base}..{head}", "--", pathspec])
    values: list[str] = []
    prefix_with_slash = f"{prefix}/" if prefix else ""
    for line in completed.stdout.splitlines():
        candidate = line.strip().replace("\\", "/")
        if not candidate:
            continue
        if prefix:
            if candidate == prefix:
                continue
            if not candidate.startswith(prefix_with_slash):
                continue
            candidate = candidate[len(prefix_with_slash) :]
        try:
            values.append(normalize_rel_path(candidate))
        except ValueError:
            continue
    return sorted(set(values))


def path_changed_since(project_root: Path, revision: str, head: str, path: str) -> tuple[bool | None, str | None]:
    if not revision or revision == "UNKNOWN" or head == "UNKNOWN":
        return None, "checked revision or current revision is unknown"
    resolved = _repo_relative_path(project_root, path)
    if not resolved:
        return None, "live project is not inside a Git repository"
    repository_root, repository_path = resolved
    completed = run_git(
        repository_root,
        ["diff", "--name-only", f"{revision}..{head}", "--", repository_path],
        allow_failure=True,
    )
    if completed.returncode != 0:
        return None, completed.stderr.strip() or "cannot compare checked revision"
    return any(line.strip() for line in completed.stdout.splitlines()), None


def linked_paths_dirty(project_root: Path, raw_refs: Iterable[str]) -> tuple[bool, list[str]]:
    context = git_context(project_root)
    if not context:
        return False, []
    repository_root, _ = context
    repository_paths: list[str] = []
    for raw in raw_refs:
        ref = parse_code_ref(raw)
        resolved = _repo_relative_path(project_root, str(ref["path"]))
        if resolved:
            repository_paths.append(resolved[1])
    if not repository_paths:
        return False, []
    completed = run_git(repository_root, ["status", "--porcelain", "--", *sorted(set(repository_paths))], allow_failure=True)
    dirty = [line for line in completed.stdout.splitlines() if line.strip()]
    return bool(dirty), dirty


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


def sync_status(design_changed: bool, code_changed: bool) -> str:
    if design_changed and code_changed:
        return "both_changed"
    if design_changed:
        return "design_changed"
    if code_changed:
        return "code_changed"
    return "in_sync"


def _trace_status_for_sync(value: str) -> str:
    if value == "in_sync":
        return "current"
    if value in SYNC_CHANGED_STATUSES:
        return "stale"
    return value


def _record_implementation_edge(
    edges: dict[str, dict[str, Any]],
    nodes: dict[str, dict[str, Any]],
    issues: list[dict[str, Any]],
    *,
    project_root: Path,
    project_revision: str,
    vault_revision: str,
    spec_id: str,
    spec_path: str,
    current_spec_digest: str,
    code_raw: str,
    check: dict[str, Any] | None,
    check_code_raw: str | None = None,
) -> None:
    effective_raw = check_code_raw or code_raw
    try:
        ref = parse_code_ref(effective_raw)
    except ValueError as error:
        issues.append(issue("error", "invalid_live_path", str(error), path=spec_path, subject=spec_id))
        return
    code_id = code_node_id(ref)
    code_path = str(ref["path"])
    current_code = code_fingerprint(project_root, effective_raw)
    _add_node(
        nodes,
        {
            "id": code_id,
            "kind": "code",
            "path": code_path,
            "symbol": ref.get("symbol"),
            "exists": current_code["exists"],
            "fingerprint": current_code.get("digest"),
            "fingerprint_scope": current_code.get("scope"),
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
            "sync_status": "unverified",
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
            "checked_project_revision": check.get("checked_project_revision") or check.get("source_revision") or "UNKNOWN",
            "checked_vault_revision": check.get("checked_vault_revision") or "UNKNOWN",
            "checked_spec_digest": check.get("checked_spec_digest") or "UNKNOWN",
            "checked_at": check.get("checked_at") or "UNKNOWN",
            "implementation_status": check.get("implementation_status") or "unknown",
            "validation_status": check.get("validation_status") or "untested",
            "build_id": check.get("build_id") or "UNKNOWN",
            "sync_baseline_status": check.get("sync_baseline_status") or "pending",
            "evidence_refs": sorted(as_string_list(check.get("evidence_refs"))),
        }
        edge["sources"] = sorted(set(edge["sources"]) | {str(check["path"])})
        encoded = {json.dumps(item, sort_keys=True, ensure_ascii=False) for item in edge["checks"]}
        if json.dumps(check_record, sort_keys=True, ensure_ascii=False) not in encoded:
            edge["checks"].append(check_record)

    edge["current"] = {
        "spec_digest": current_spec_digest,
        "project_revision": project_revision,
        "vault_revision": vault_revision,
        "code_fingerprint": current_code.get("digest"),
        "code_ref": current_code.get("ref"),
    }

    if not current_code["exists"]:
        edge["sync_status"] = "missing"
        edge["trace_status"] = "missing"
        edge["stale_reasons"] = [f"tracked live path does not exist: {code_path}"]
        issues.append(issue("error", "missing_live_path", edge["stale_reasons"][0], path=spec_path, subject=spec_id))
        return

    checks = sorted(edge["checks"], key=lambda item: (str(item.get("checked_at") or ""), str(item.get("path") or "")))
    edge["checks"] = checks
    if not checks or not check:
        edge["sync_status"] = "unverified"
        edge["trace_status"] = "unverified"
        edge["stale_reasons"] = ["no implementation check records an accepted design/code baseline"]
        return

    latest = checks[-1]
    edge["current_check"] = latest
    baseline_spec_digest = str(check.get("checked_spec_digest") or "UNKNOWN")
    baseline_fingerprints = fingerprint_map(check.get("checked_code_fingerprints"))
    baseline_code_digest = baseline_fingerprints.get(code_ref_identity(ref))
    baseline_status = str(check.get("sync_baseline_status") or "pending")
    if (
        baseline_status != "accepted"
        or not re.fullmatch(r"sha256:[0-9a-f]{64}", baseline_spec_digest)
        or baseline_code_digest is None
    ):
        edge["sync_status"] = "unverified"
        edge["trace_status"] = "unverified"
        edge["stale_reasons"] = ["latest implementation check has no accepted spec/code digest baseline"]
        return

    design_changed = current_spec_digest != baseline_spec_digest
    current_code_digest = str(current_code.get("digest") or "MISSING")
    code_changed = current_code_digest != baseline_code_digest
    value = sync_status(design_changed, code_changed)
    reasons: list[str] = []
    if design_changed:
        reasons.append("canonical design digest changed after the accepted implementation check")
    if code_changed:
        reasons.append(f"{code_path} fingerprint changed after the accepted implementation check")
    edge["sync_status"] = value
    edge["trace_status"] = _trace_status_for_sync(value)
    edge["stale_reasons"] = reasons
    edge["baseline"] = {
        "version": SYNC_BASELINE_VERSION,
        "check_id": check.get("check_id"),
        "check_path": check.get("path"),
        "spec_digest": baseline_spec_digest,
        "project_revision": check.get("checked_project_revision") or check.get("source_revision") or "UNKNOWN",
        "vault_revision": check.get("checked_vault_revision") or "UNKNOWN",
        "code_fingerprint": baseline_code_digest,
        "code_ref": current_code.get("ref"),
    }


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
    project_revision = current_revision(project)
    vault_revision = current_vault_revision(vault)
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
            digest = spec_digest(path)
            node: dict[str, Any] = {
                "id": spec_id,
                "kind": "spec",
                "subtype": subtype,
                "path": relative,
                "resolved": True,
                "spec_digest": digest,
                "spec_digest_version": SPEC_DIGEST_VERSION,
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
            specs[spec_id] = {"node": node, "metadata": metadata, "path": path, "digest": digest}

    checks_by_subject: dict[str, list[dict[str, Any]]] = {}
    for path, metadata in _scan_documents(vault, "wiki/game/implementation"):
        relative = relative_to_root(vault, path)
        subject_id = str(metadata.get("subject_id") or "").strip()
        if not subject_id:
            issues.append(issue("error", "missing_subject_id", "implementation check has no subject_id", path=relative))
            continue
        check = dict(metadata)
        check["path"] = relative
        check["absolute_path"] = str(path)
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
                "checked_project_revision": metadata.get("checked_project_revision") or metadata.get("source_revision") or "UNKNOWN",
                "checked_vault_revision": metadata.get("checked_vault_revision") or "UNKNOWN",
                "checked_spec_digest": metadata.get("checked_spec_digest") or "UNKNOWN",
                "sync_baseline_status": metadata.get("sync_baseline_status") or "pending",
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
        by_ref: dict[str, list[tuple[dict[str, Any], str]]] = {}
        for check in checks_by_subject.get(spec_id, []):
            for raw in as_string_list(check.get("checked_paths")):
                try:
                    parsed = parse_code_ref(raw)
                except ValueError as error:
                    issues.append(issue("error", "invalid_checked_path", str(error), path=str(check["path"]), subject=spec_id))
                    continue
                by_ref.setdefault(code_ref_identity(parsed), []).append((check, raw))
        seen: set[str] = set()
        for raw in as_string_list(metadata.get("live_paths")):
            try:
                parsed = parse_code_ref(raw)
                identity = code_ref_identity(parsed)
            except ValueError as error:
                issues.append(issue("error", "invalid_live_path", str(error), path=spec_path, subject=spec_id))
                continue
            seen.add(identity)
            matches = by_ref.get(identity)
            if matches:
                check, check_raw = sorted(
                    matches,
                    key=lambda item: (str(item[0].get("checked_at") or ""), str(item[0].get("path") or "")),
                )[-1]
                _record_implementation_edge(
                    edges,
                    nodes,
                    issues,
                    project_root=project,
                    project_revision=project_revision,
                    vault_revision=vault_revision,
                    spec_id=spec_id,
                    spec_path=spec_path,
                    current_spec_digest=str(spec["digest"]),
                    code_raw=raw,
                    check=check,
                    check_code_raw=check_raw,
                )
            else:
                _record_implementation_edge(
                    edges,
                    nodes,
                    issues,
                    project_root=project,
                    project_revision=project_revision,
                    vault_revision=vault_revision,
                    spec_id=spec_id,
                    spec_path=spec_path,
                    current_spec_digest=str(spec["digest"]),
                    code_raw=raw,
                    check=None,
                )
        for identity, matches in by_ref.items():
            if identity in seen:
                continue
            check, check_raw = sorted(
                matches,
                key=lambda item: (str(item[0].get("checked_at") or ""), str(item[0].get("path") or "")),
            )[-1]
            _record_implementation_edge(
                edges,
                nodes,
                issues,
                project_root=project,
                project_revision=project_revision,
                vault_revision=vault_revision,
                spec_id=spec_id,
                spec_path=spec_path,
                current_spec_digest=str(spec["digest"]),
                code_raw=check_raw,
                check=check,
                check_code_raw=check_raw,
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

    ordered_edges = sorted(edges.values(), key=lambda item: str(item.get("id")))
    sync_counts = {status: 0 for status in ("in_sync", "design_changed", "code_changed", "both_changed", "unverified", "missing")}
    for edge in ordered_edges:
        if edge.get("relation") == "implemented_by":
            sync_counts[str(edge.get("sync_status") or "unverified")] = sync_counts.get(str(edge.get("sync_status") or "unverified"), 0) + 1

    return {
        "schema_version": TRACEABILITY_SCHEMA_VERSION,
        "sync_baseline_version": SYNC_BASELINE_VERSION,
        "project_mode": PROJECT_MODE,
        "generated_at": utc_now(),
        "project_root": _project_reference(vault, project),
        "project_revision": project_revision,
        "vault_revision": vault_revision,
        "source_revision": project_revision,
        "source_of_truth": list(SOURCE_OF_TRUTH),
        "sync_counts": sync_counts,
        "nodes": sorted(nodes.values(), key=lambda item: (str(item.get("kind")), str(item.get("id")))),
        "edges": ordered_edges,
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
        raise TraceError(
            f"unsupported traceability schema: {value.get('schema_version')}; expected {TRACEABILITY_SCHEMA_VERSION}"
        )
    return value


def comparable_index(index: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "schema_version",
        "sync_baseline_version",
        "project_mode",
        "project_root",
        "project_revision",
        "vault_revision",
        "source_revision",
        "source_of_truth",
        "sync_counts",
        "nodes",
        "edges",
        "issues",
    )
    return {key: index.get(key) for key in keys}


def verification_summary(
    vault_root: Path,
    index_path: Path,
    project_root: Path | None = None,
    *,
    strict_stale: bool = False,
    strict_sync: bool = False,
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
    implementation = [edge for edge in current.get("edges", []) if edge.get("relation") == "implemented_by"]
    changed = [edge for edge in implementation if edge.get("sync_status") in SYNC_CHANGED_STATUSES]
    blocking = [edge for edge in implementation if edge.get("sync_status") in SYNC_BLOCKING_STATUSES]
    unverified = [edge for edge in implementation if edge.get("sync_status") == "unverified"]
    missing = [edge for edge in implementation if edge.get("sync_status") == "missing"]
    if strict_sync and blocking:
        errors.append(f"{len(blocking)} design/code relation(s) are not in_sync")
    elif strict_stale and changed:
        errors.append(f"{len(changed)} design/code relation(s) changed after their accepted baseline")
    else:
        if changed:
            warnings.append(f"{len(changed)} design/code relation(s) changed after their accepted baseline")
        if unverified:
            warnings.append(f"{len(unverified)} design/code relation(s) have no accepted baseline")
        if missing:
            warnings.append(f"{len(missing)} design/code relation(s) reference missing paths")
    if strict_warnings and warnings:
        errors.extend(warnings)
    return {
        "ok": not errors,
        "index": relative_to_root(vault, index_path),
        "project_root": str(project),
        "project_revision": current.get("project_revision"),
        "vault_revision": current.get("vault_revision"),
        "node_count": len(current.get("nodes", [])),
        "edge_count": len(current.get("edges", [])),
        "sync_counts": current.get("sync_counts", {}),
        "changed_edge_count": len(changed),
        "unverified_edge_count": len(unverified),
        "missing_edge_count": len(missing),
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
    return {
        "spec": spec,
        "edges": edges,
        "linked_nodes": [nodes.get(str(edge.get("to")), {"id": edge.get("to"), "resolved": False}) for edge in edges],
        "sync_proposals": [proposal for proposal in sync_proposals(index) if proposal.get("spec_id") == spec_id],
    }


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
    return {
        "query": query,
        "code_nodes": matches,
        "edges": edges,
        "specs": [nodes.get(str(edge.get("from")), {"id": edge.get("from"), "resolved": False}) for edge in edges],
    }


def traceability_matrix(index: dict[str, Any]) -> list[dict[str, Any]]:
    nodes = _node_map(index)
    rows: list[dict[str, Any]] = []
    for spec in sorted((node for node in nodes.values() if node.get("kind") == "spec"), key=lambda item: str(item["id"])):
        spec_id = str(spec["id"])
        outbound = [edge for edge in index.get("edges", []) if edge.get("from") == spec_id]
        implementation = [edge for edge in outbound if edge.get("relation") == "implemented_by"]
        counts = {status: sum(edge.get("sync_status") == status for edge in implementation) for status in (
            "in_sync", "design_changed", "code_changed", "both_changed", "unverified", "missing"
        )}
        rows.append(
            {
                "spec_id": spec_id,
                "spec_path": spec.get("path"),
                "spec_digest": spec.get("spec_digest"),
                "design_status": spec.get("design_status", "unknown"),
                "implementation_status": spec.get("implementation_status", "unknown"),
                "validation_status": spec.get("validation_status", "untested"),
                "code_relations": len(implementation),
                **{f"{key}_relations": value for key, value in counts.items()},
                "builds": sorted(str(edge.get("to")) for edge in outbound if edge.get("relation") == "built_in"),
                "tests": sorted(str(edge.get("to")) for edge in outbound if edge.get("relation") == "validated_by"),
                "decisions": sorted(str(edge.get("to")) for edge in outbound if edge.get("relation") == "governed_by"),
            }
        )
    return rows


def sync_proposals(index: dict[str, Any]) -> list[dict[str, Any]]:
    nodes = _node_map(index)
    proposals: list[dict[str, Any]] = []
    actions = {
        "design_changed": [
            "inspect the changed specification against the current implementation",
            "either implement the accepted design or supersede/revert the design change",
            "record a new implementation check and accept a new baseline",
        ],
        "code_changed": [
            "inspect the changed live implementation and its Git diff",
            "either update the design through an explicit proposal/decision or restore implementation conformance",
            "record a new implementation check and accept a new baseline",
        ],
        "both_changed": [
            "reconcile the changed design and changed implementation without assuming either side is authoritative",
            "record the chosen direction as a project decision",
            "create a new implementation check and accept a new baseline",
        ],
        "unverified": [
            "perform an implementation inspection for this design/code relation",
            "finalize the implementation check with the accept command",
        ],
        "missing": [
            "repair or remove the missing live-path relation",
            "inspect renamed/moved code before accepting a replacement baseline",
        ],
    }
    for edge in index.get("edges", []):
        if edge.get("relation") != "implemented_by":
            continue
        status = str(edge.get("sync_status") or "unverified")
        if status == "in_sync":
            continue
        code = nodes.get(str(edge.get("to")), {})
        proposals.append(
            {
                "proposal_id": "SYNC-" + str(edge.get("id", "TRACE-UNKNOWN")).removeprefix("TRACE-"),
                "spec_id": edge.get("from"),
                "spec_path": nodes.get(str(edge.get("from")), {}).get("path"),
                "code_path": code.get("path"),
                "symbol": code.get("symbol"),
                "sync_status": status,
                "reasons": edge.get("stale_reasons", []),
                "recommended_actions": actions.get(status, ["inspect and reconcile the relation"]),
                "automatic_mutation": False,
            }
        )
    return sorted(proposals, key=lambda item: (str(item.get("spec_id")), str(item.get("code_path"))))


def affected_by_diff(project_root: Path, index: dict[str, Any], base: str, head: str) -> dict[str, Any]:
    changed = set(changed_paths(project_root, base, head))
    nodes = _node_map(index)
    reasons: dict[str, set[str]] = {}
    changed_edges: list[dict[str, Any]] = []
    for edge in index.get("edges", []):
        if edge.get("relation") != "implemented_by":
            continue
        spec_id = str(edge.get("from"))
        status = str(edge.get("sync_status") or "unverified")
        if status in ("design_changed", "both_changed"):
            spec_path = nodes.get(spec_id, {}).get("path")
            reasons.setdefault(spec_id, set()).add(f"design_changed:{spec_path}")
            changed_edges.append(edge)
        code = nodes.get(str(edge.get("to")))
        if code and code.get("path") in changed:
            reasons.setdefault(spec_id, set()).add(f"code_changed:{code.get('path')}")
            if edge not in changed_edges:
                changed_edges.append(edge)
    return {
        "base": base,
        "head": head,
        "changed_project_paths": sorted(changed),
        "affected_specs": [{"spec_id": spec_id, "reasons": sorted(values)} for spec_id, values in sorted(reasons.items())],
        "changed_edges": sorted(changed_edges, key=lambda item: str(item.get("id"))),
        "note": "design changes are detected by canonical spec digest; project Git diff covers live implementation paths",
    }


def _find_spec_by_id(vault_root: Path, subject_id: str) -> Path | None:
    for folder in SPEC_FOLDERS:
        for path, metadata in _scan_documents(vault_root, f"wiki/game/{folder}"):
            if first_document_id(metadata, preferred=("id",)) == subject_id:
                return path
            if subject_id in {str(value) for key, value in metadata.items() if key.endswith("_id")}:
                return path
    return None


def accept_sync_baseline(
    vault_root: Path,
    project_root: Path,
    check_relative: str,
    *,
    allow_dirty: bool = False,
) -> dict[str, Any]:
    check_relative = normalize_rel_path(check_relative)
    check_path = (vault_root / check_relative).resolve()
    try:
        check_path.relative_to(vault_root.resolve())
    except ValueError as error:
        raise TraceError("implementation check path escapes the vault") from error
    if not check_path.is_file():
        raise TraceError(f"implementation check does not exist: {check_relative}")
    metadata = parse_frontmatter(check_path)
    subject_id = str(metadata.get("subject_id") or "").strip()
    if not subject_id:
        raise TraceError("implementation check has no subject_id")
    expected_spec = str(metadata.get("expected_spec") or "").strip()
    spec_path = (vault_root / normalize_rel_path(expected_spec)).resolve() if expected_spec else _find_spec_by_id(vault_root, subject_id)
    if spec_path is None or not spec_path.is_file():
        raise TraceError(f"cannot resolve specification for {subject_id}")
    try:
        spec_path.relative_to(vault_root.resolve())
    except ValueError as error:
        raise TraceError("expected_spec escapes the vault") from error
    checked_paths = as_string_list(metadata.get("checked_paths"))
    if not checked_paths:
        spec_metadata = parse_frontmatter(spec_path)
        checked_paths = as_string_list(spec_metadata.get("live_paths"))
    if not checked_paths:
        raise TraceError("implementation check has no checked_paths and the specification has no live_paths")

    fingerprints = [code_fingerprint(project_root, raw) for raw in checked_paths]
    missing = [item["ref"] for item in fingerprints if not item.get("exists")]
    if missing:
        raise TraceError("cannot accept a baseline with missing live paths: " + ", ".join(missing))
    dirty, dirty_lines = linked_paths_dirty(project_root, checked_paths)
    if dirty and not allow_dirty:
        raise TraceError("linked live paths have uncommitted changes; commit them or pass --allow-dirty explicitly")

    project_revision = current_revision(project_root)
    vault_revision = current_vault_revision(vault_root)
    digest = spec_digest(spec_path)
    updates = {
        "source_revision": project_revision,
        "checked_project_revision": project_revision,
        "checked_vault_revision": vault_revision,
        "checked_project_dirty": dirty,
        "checked_spec_digest": digest,
        "checked_spec_digest_version": SPEC_DIGEST_VERSION,
        "checked_code_fingerprints": sorted(encode_code_fingerprint(item) for item in fingerprints),
        "checked_code_fingerprint_version": CODE_FINGERPRINT_VERSION,
        "sync_baseline_status": "accepted",
        "checked_at": datetime.now().strftime("%Y-%m-%d"),
    }
    update_frontmatter_fields(check_path, updates)
    index = build_index(vault_root, project_root)
    write_index(vault_root / DEFAULT_INDEX, index)
    subject = query_spec(index, subject_id)
    statuses = sorted({str(edge.get("sync_status")) for edge in subject["edges"] if edge.get("relation") == "implemented_by"})
    return {
        "ok": statuses == ["in_sync"],
        "check": check_relative,
        "subject_id": subject_id,
        "spec": relative_to_root(vault_root, spec_path),
        "spec_digest": digest,
        "project_revision": project_revision,
        "vault_revision": vault_revision,
        "project_dirty": dirty,
        "dirty_entries": dirty_lines,
        "fingerprints": updates["checked_code_fingerprints"],
        "sync_statuses": statuses,
        "index": DEFAULT_INDEX,
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


def _rebuild_result(vault_root: Path, project_root: Path, index_relative: str) -> tuple[dict[str, Any], dict[str, Any]]:
    index = build_index(vault_root, project_root)
    write_index(vault_root / index_relative, index)
    result = {
        "ok": not any(item.get("severity") == "error" for item in index.get("issues", [])),
        "index": index_relative,
        "project_root": str(project_root),
        "project_revision": index.get("project_revision"),
        "vault_revision": index.get("vault_revision"),
        "node_count": len(index.get("nodes", [])),
        "edge_count": len(index.get("edges", [])),
        "issue_count": len(index.get("issues", [])),
        "sync_counts": index.get("sync_counts", {}),
    }
    return result, index


def main() -> int:
    parser = argparse.ArgumentParser(description="Build, query, and synchronize sidecar-safe game design-to-code traceability.")
    parser.add_argument("--vault-root", type=Path, default=Path.cwd(), help="LLM Wiki vault root. Defaults to cwd.")
    parser.add_argument("--project-root", type=Path, default=None, help="Live game project root. Defaults to the manifest reference.")
    parser.add_argument("--root", type=Path, default=None, help="Legacy alias that treats one root as both vault and project.")
    parser.add_argument("--index", default=DEFAULT_INDEX, help="Vault-relative traceability index path.")
    parser.add_argument("--compact", action="store_true")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("rebuild")
    subparsers.add_parser("scan")
    verify = subparsers.add_parser("verify")
    verify.add_argument("--strict-stale", action="store_true")
    verify.add_argument("--strict-sync", action="store_true")
    verify.add_argument("--strict-warnings", action="store_true")
    spec = subparsers.add_parser("spec")
    spec.add_argument("spec_id")
    path = subparsers.add_parser("path")
    path.add_argument("path")
    affected = subparsers.add_parser("affected")
    affected.add_argument("--base", required=True)
    affected.add_argument("--head", default="HEAD")
    subparsers.add_parser("matrix")
    subparsers.add_parser("status")
    subparsers.add_parser("proposals")
    accept = subparsers.add_parser("accept", help="Accept the current design/code pair as the baseline for one implementation check.")
    accept.add_argument("check", help="Vault-relative implementation-check path.")
    accept.add_argument("--allow-dirty", action="store_true", help="Allow linked project paths with uncommitted changes.")
    args = parser.parse_args()
    try:
        vault_root, project_root = resolve_cli_roots(args)
        index_relative = normalize_rel_path(args.index)
        index_path = vault_root / index_relative
        if args.command in ("rebuild", "scan"):
            result, _ = _rebuild_result(vault_root, project_root, index_relative)
        elif args.command == "verify":
            result = verification_summary(
                vault_root,
                index_path,
                project_root,
                strict_stale=args.strict_stale,
                strict_sync=args.strict_sync,
                strict_warnings=args.strict_warnings,
            )
        elif args.command == "accept":
            result = accept_sync_baseline(vault_root, project_root, args.check, allow_dirty=args.allow_dirty)
        else:
            index = load_index(index_path)
            if args.command == "spec":
                result = query_spec(index, args.spec_id)
            elif args.command == "path":
                result = query_path(index, args.path)
            elif args.command == "affected":
                current = build_index(vault_root, project_root)
                result = affected_by_diff(project_root, current, args.base, args.head)
            elif args.command == "matrix":
                result = {"rows": traceability_matrix(index)}
            elif args.command == "status":
                current = build_index(vault_root, project_root)
                result = {
                    "sync_counts": current.get("sync_counts", {}),
                    "rows": traceability_matrix(current),
                    "proposals": sync_proposals(current),
                }
            else:
                current = build_index(vault_root, project_root)
                result = {"proposals": sync_proposals(current)}
        print_json(result, compact=args.compact)
        if args.command == "verify":
            return 0 if result.get("ok") else 1
        return 0 if result.get("ok", True) else 1
    except (OSError, ValueError, TraceError) as error:
        print_json({"ok": False, "error": str(error)}, compact=getattr(args, "compact", False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
