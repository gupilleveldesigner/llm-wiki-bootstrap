#!/usr/bin/env python3
"""Minimal local Evidence KB: immutable raw registration, FTS5, and tracing."""

from __future__ import annotations

import argparse
from contextlib import closing
import hashlib
import json
import os
import re
import shutil
import sqlite3
import sys
import tempfile
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable


SCHEMA_VERSION = "3"
CLAIM_STATUSES = {
    "OBSERVED",
    "INFERRED",
    "HYPOTHESIS",
    "SUPPORTED",
    "CONFIRMED",
    "REJECTED",
    "DISPUTED",
    "DEPRECATED",
    "UNKNOWN",
}
EVIDENCE_RELATIONS = {"supports", "contradicts", "context", "derived_from"}
CLAIM_RELATIONS = {"supports", "contradicts", "supersedes", "duplicates", "related"}
DECISION_STATUSES = {"PROPOSED", "ADOPTED", "SUPERSEDED", "REJECTED", "BLOCKED", "PAUSED"}


def configure_utf8_stdout() -> None:
    """Keep JSON output lossless on Windows consoles using a legacy code page."""
    reconfigure = getattr(sys.stdout, "reconfigure", None)
    if callable(reconfigure):
        reconfigure(encoding="utf-8")
DECISION_SOURCE_RELATIONS = {"records", "recommends", "adopts", "context"}
TEXT_SUFFIXES = {
    ".txt", ".md", ".json", ".yaml", ".yml", ".log", ".csv",
    ".py", ".ps1", ".js", ".ts", ".html", ".xml",
}


class KBError(RuntimeError):
    pass


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def find_root(explicit: str | None = None) -> Path:
    if explicit:
        root = Path(explicit).expanduser().resolve()
        if not (root / "raw").is_dir() or not (root / "wiki").is_dir():
            raise KBError(f"LLM Wiki root가 아닙니다: {root}")
        return root
    current = Path.cwd().resolve()
    for candidate in (current, *current.parents):
        if (candidate / "raw").is_dir() and (candidate / "wiki").is_dir():
            return candidate
    raise KBError("현재 경로에서 raw/와 wiki/가 있는 LLM Wiki를 찾지 못했습니다.")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def relative_posix(path: Path, root: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def require_inside(path: Path, parent: Path, label: str) -> Path:
    resolved = path.resolve()
    try:
        resolved.relative_to(parent.resolve())
    except ValueError as error:
        raise KBError(f"{label} 경계를 벗어났습니다: {path}") from error
    return resolved


def yaml_scalar(value: str) -> Any:
    value = value.strip()
    if value in {"", "null", "~"}:
        return ""
    if value == "[]":
        return []
    if value == "{}":
        return {}
    if value.lower() in {"true", "false"}:
        return value.lower() == "true"
    if value.startswith("[") and value.endswith("]"):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return [part.strip().strip("\"'") for part in value[1:-1].split(",") if part.strip()]
    if value.startswith('"') and value.endswith('"'):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value[1:-1]
    if value.startswith("'") and value.endswith("'"):
        return value[1:-1]
    if re.fullmatch(r"-?\d+", value):
        return int(value)
    if re.fullmatch(r"-?(?:\d+\.\d*|\d*\.\d+)", value):
        return float(value)
    return value


def parse_document(path: Path) -> tuple[dict[str, Any], str]:
    text = path.read_text(encoding="utf-8-sig")
    if not text.startswith("---"):
        return {}, text
    parts = text.split("---", 2)
    if len(parts) != 3:
        return {}, text
    lines = parts[1].strip("\r\n").splitlines()
    metadata: dict[str, Any] = {}
    index = 0
    while index < len(lines):
        line = lines[index]
        match = re.match(r"^([A-Za-z0-9_-]+):\s*(.*)$", line)
        if not match:
            index += 1
            continue
        key, raw_value = match.groups()
        if raw_value.strip():
            metadata[key] = yaml_scalar(raw_value)
            index += 1
            continue
        items: list[Any] = []
        index += 1
        while index < len(lines):
            item = re.match(r"^\s+-\s+(.*)$", lines[index])
            if not item:
                break
            items.append(yaml_scalar(item.group(1)))
            index += 1
        metadata[key] = items
    return metadata, parts[2].lstrip("\r\n")


def as_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if value in {None, ""}:
        return []
    return [str(value).strip()]


def first_heading(body: str, fallback: str) -> str:
    match = re.search(r"(?m)^#\s+(.+?)\s*$", body)
    return match.group(1).strip() if match else fallback


def quote(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def yaml_list(key: str, values: Iterable[str]) -> str:
    values = list(values)
    if not values:
        return f"{key}: []"
    return "\n".join([f"{key}:", *(f"  - {quote(value)}" for value in values)])


def safe_component(value: str, *, upper: bool = False, limit: int = 48) -> str:
    cleaned = re.sub(r"[^0-9A-Za-z가-힣_-]+", "-", value).strip("-_") or "source"
    cleaned = cleaned[:limit]
    return cleaned.upper() if upper else cleaned


def source_note_by_hash(root: Path, digest: str) -> tuple[str, str] | None:
    for path in sorted((root / "wiki" / "sources").glob("**/*.md")):
        metadata, _ = parse_document(path)
        if str(metadata.get("raw_sha256", "")).lower() == digest.lower():
            return str(metadata.get("id", "")), relative_posix(path, root)
    return None


def next_raw_id(root: Path, provider: str, timestamp: datetime) -> str:
    provider_code = safe_component(provider, upper=True, limit=12)
    date_code = timestamp.strftime("%Y%m%d")
    prefix = f"RAW-{provider_code}-{date_code}-"
    highest = 0
    for path in (root / "wiki" / "sources").glob("**/*.md"):
        metadata, _ = parse_document(path)
        source_id = str(metadata.get("id", ""))
        if source_id.startswith(prefix):
            try:
                highest = max(highest, int(source_id.removeprefix(prefix)))
            except ValueError:
                pass
    return f"{prefix}{highest + 1:04d}"


def decode_text(path: Path) -> str | None:
    if path.suffix.lower() not in TEXT_SUFFIXES:
        return None
    try:
        return path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError:
        return None


def register_source(
    root: Path,
    input_path: Path,
    provider: str,
    source_type: str,
    category: str,
    title: str | None,
    model: str,
    parent_sources: list[str],
) -> dict[str, Any]:
    source = input_path.expanduser().resolve()
    if not source.is_file():
        raise KBError(f"입력 파일이 없습니다: {source}")

    raw_root = (root / "raw").resolve()
    digest = sha256(source)
    existing = source_note_by_hash(root, digest)
    if existing:
        return {
            "status": "duplicate",
            "source_id": existing[0],
            "source_note": existing[1],
            "sha256": digest,
        }

    timestamp = datetime.now().astimezone()
    source_id = next_raw_id(root, provider, timestamp)
    category_path = Path(category.replace("\\", "/"))
    if category_path.is_absolute() or ".." in category_path.parts:
        raise KBError(f"잘못된 raw 분류 경로입니다: {category}")
    raw_dir = require_inside(raw_root / category_path, raw_root, "raw")
    raw_dir.mkdir(parents=True, exist_ok=True)

    try:
        source.relative_to(raw_root)
        raw_path = source
    except ValueError:
        filename = f"{source_id}__{safe_component(source.stem)}{source.suffix.lower()}"
        raw_path = raw_dir / filename
        if raw_path.exists():
            raise KBError(f"대상 raw 파일이 이미 있습니다: {raw_path}")
        temporary = raw_path.with_name(f".{raw_path.name}.{uuid.uuid4().hex}.tmp")
        shutil.copyfile(source, temporary)
        if sha256(temporary) != digest:
            temporary.unlink(missing_ok=True)
            raise KBError("raw 복사 후 SHA-256 검증에 실패했습니다.")
        os.replace(temporary, raw_path)

    raw_relative = relative_posix(raw_path, root)
    display_title = title or source.stem
    created_at = datetime.fromtimestamp(source.stat().st_mtime).astimezone().isoformat(timespec="seconds")
    ingested_at = now_iso()

    normalized_dir = root / "wiki" / "normalized"
    source_dir = root / "wiki" / "sources"
    normalized_dir.mkdir(parents=True, exist_ok=True)
    source_dir.mkdir(parents=True, exist_ok=True)
    normalized_path = normalized_dir / f"{source_id}.md"
    text = decode_text(raw_path)
    normalized_relative = ""
    if text is not None:
        normalized_id = source_id.replace("RAW-", "NORM-", 1)
        normalized = "\n".join(
            [
                "---",
                "type: normalized",
                f"id: {quote(normalized_id)}",
                yaml_list("derived_from", [source_id]),
                f"raw_path: {quote(raw_relative)}",
                f"raw_sha256: {quote(digest)}",
                f"created_at: {quote(ingested_at)}",
                "rebuildable: true",
                "---",
                "",
                f"# Normalized — {display_title}",
                "",
                "> UTF-8 텍스트 원본을 검색용 Markdown으로 감싼 재생성 가능 파생본이다.",
                "",
                "## 원문 텍스트",
                "",
                text,
            ]
        )
        with normalized_path.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(normalized.rstrip() + "\n")
        normalized_relative = relative_posix(normalized_path, root)

    source_note_path = source_dir / f"{source_id}.md"
    note = "\n".join(
        [
            "---",
            "type: source",
            f"id: {quote(source_id)}",
            "status: pending",
            "topics: []",
            yaml_list("sources", [raw_relative]),
            f"normalized_path: {quote(normalized_relative)}",
            f"raw_sha256: {quote(digest)}",
            f"source_type: {quote(source_type)}",
            f"provider: {quote(provider)}",
            f"model: {quote(model)}",
            f"created_at: {quote(created_at)}",
            f"ingested_at: {quote(ingested_at)}",
            "verification_status: unverified",
            "structurally_verified: false",
            "semantic_status: pending",
            "coverage_spans: 0",
            "key_decisions: 0",
            "next_actions: 0",
            "chronology_entries: 0",
            "epistemic_observation: unknown",
            "epistemic_inference: unknown",
            yaml_list("parent_sources", parent_sources),
            f"independence_group: {quote(source_id)}",
            "visibility: private",
            "external_llm_allowed: false",
            "key_claims: 0",
            "entities: 0",
            "concepts: 0",
            "reflected_docs: 0",
            "relations: 0",
            "evidence_spans: 0",
            f"created: {quote(timestamp.date().isoformat())}",
            f"updated: {quote(timestamp.date().isoformat())}",
            "---",
            "",
            f"# 원본 요약 — {display_title}",
            "",
            "## 원본",
            "",
            f"- [[{raw_relative}]]",
            f"- Source ID: `{source_id}`",
            f"- SHA-256: `{digest}`",
            "",
            "## 핵심 내용",
            "",
            "- 확인 필요",
            "",
            "## Claim 후보",
            "",
            "- 확인 필요",
            "",
            "## 기존 Wiki와의 연결",
            "",
            "- 확인 필요",
            "",
            "## 근거",
            "",
            "> 원문에서 일치하는 짧은 인용으로 교체한다.",
            "",
            "## 충돌 또는 확인 필요",
            "",
            "- 의미 검토 전이므로 아직 인제스트 완료가 아니다.",
            "",
            "## 갱신한 문서",
            "",
            "- 확인 필요",
        ]
    )
    with source_note_path.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(note.rstrip() + "\n")

    return {
        "status": "registered_pending_semantic_review",
        "source_id": source_id,
        "raw_path": raw_relative,
        "normalized_path": normalized_relative or None,
        "source_note": relative_posix(source_note_path, root),
        "sha256": digest,
        "next": "source note를 검토하고 Claim 문서를 만든 뒤 rebuild를 실행하세요.",
    }


def db_path(root: Path) -> Path:
    return root / ".evidence-kb" / "knowledge.db"


def create_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        PRAGMA foreign_keys = ON;
        CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE sources (
            id TEXT PRIMARY KEY,
            source_doc_path TEXT NOT NULL UNIQUE,
            raw_path TEXT NOT NULL UNIQUE,
            normalized_path TEXT,
            declared_sha256 TEXT NOT NULL,
            actual_sha256 TEXT,
            integrity_status TEXT NOT NULL,
            source_type TEXT,
            provider TEXT,
            model TEXT,
            verification_status TEXT,
            structurally_verified INTEGER NOT NULL,
            semantic_status TEXT NOT NULL,
            coverage_json TEXT NOT NULL,
            epistemic_observation TEXT,
            epistemic_inference TEXT,
            parent_sources_json TEXT NOT NULL,
            independence_group TEXT,
            visibility TEXT,
            external_llm_allowed INTEGER NOT NULL,
            title TEXT NOT NULL,
            body TEXT NOT NULL
        );
        CREATE TABLE claims (
            id TEXT PRIMARY KEY,
            path TEXT NOT NULL UNIQUE,
            statement TEXT NOT NULL,
            status TEXT NOT NULL,
            confidence REAL,
            claim_kind TEXT,
            topics_json TEXT NOT NULL,
            title TEXT NOT NULL,
            body TEXT NOT NULL
        );
        CREATE TABLE claim_sources (
            claim_id TEXT NOT NULL REFERENCES claims(id),
            source_id TEXT NOT NULL REFERENCES sources(id),
            relation TEXT NOT NULL,
            locator TEXT,
            excerpt TEXT,
            PRIMARY KEY (claim_id, source_id, relation, locator)
        );
        CREATE TABLE claim_relations (
            claim_id TEXT NOT NULL REFERENCES claims(id),
            related_claim_id TEXT NOT NULL REFERENCES claims(id),
            relation TEXT NOT NULL,
            PRIMARY KEY (claim_id, related_claim_id, relation)
        );
        CREATE TABLE decisions (
            id TEXT PRIMARY KEY,
            path TEXT NOT NULL UNIQUE,
            statement TEXT NOT NULL,
            status TEXT NOT NULL,
            project_path TEXT NOT NULL,
            decided_at TEXT,
            topics_json TEXT NOT NULL,
            next_actions_json TEXT NOT NULL,
            chronology_json TEXT NOT NULL,
            title TEXT NOT NULL,
            body TEXT NOT NULL
        );
        CREATE TABLE decision_sources (
            decision_id TEXT NOT NULL REFERENCES decisions(id),
            source_id TEXT NOT NULL REFERENCES sources(id),
            relation TEXT NOT NULL,
            locator TEXT NOT NULL,
            excerpt TEXT NOT NULL,
            PRIMARY KEY (decision_id, source_id, relation, locator)
        );
        CREATE TABLE decision_relations (
            decision_id TEXT NOT NULL REFERENCES decisions(id),
            related_decision_id TEXT NOT NULL REFERENCES decisions(id),
            relation TEXT NOT NULL,
            PRIMARY KEY (decision_id, related_decision_id, relation)
        );
        CREATE TABLE canon (
            id TEXT PRIMARY KEY,
            path TEXT NOT NULL UNIQUE,
            title TEXT NOT NULL,
            body TEXT NOT NULL,
            manual_reviewed INTEGER NOT NULL
        );
        CREATE TABLE canon_claims (
            canon_id TEXT NOT NULL REFERENCES canon(id),
            claim_id TEXT NOT NULL REFERENCES claims(id),
            PRIMARY KEY (canon_id, claim_id)
        );
        CREATE VIRTUAL TABLE search_index USING fts5(
            doc_type UNINDEXED,
            doc_id UNINDEXED,
            title,
            body,
            path UNINDEXED,
            tokenize='unicode61'
        );
        """
    )


def raw_reference(metadata: dict[str, Any]) -> str:
    for value in as_list(metadata.get("sources")) + as_list(metadata.get("source")):
        normalized = value.replace("\\", "/").removeprefix("./")
        if normalized.startswith("raw/"):
            return normalized
    return ""


def parse_evidence(value: str) -> tuple[str, str, str, str]:
    parts = [part.strip() for part in value.split("|", 3)]
    parts.extend([""] * (4 - len(parts)))
    return parts[0], parts[1].lower(), parts[2], parts[3]


def parse_located_action(value: str) -> tuple[str, str, str, str, str]:
    parts = [part.strip() for part in value.split("|", 4)]
    parts.extend([""] * (5 - len(parts)))
    return parts[0], parts[1], parts[2], parts[3], parts[4]


def parse_located_chronology(value: str) -> tuple[str, str, str, str, str]:
    parts = [part.strip() for part in value.split("|", 4)]
    parts.extend([""] * (5 - len(parts)))
    return parts[0], parts[1], parts[2], parts[3], parts[4]


def parse_relation(value: str) -> tuple[str, str]:
    parts = [part.strip() for part in value.split("|", 1)]
    parts.extend([""] * (2 - len(parts)))
    return parts[0], parts[1].lower()


def effective_semantic_status(metadata: dict[str, Any]) -> str:
    declared = str(metadata.get("semantic_status", "")).casefold()
    if declared in {"pending", "partial", "reviewed"}:
        return declared
    return "pending" if str(metadata.get("status", "")).casefold() in {"pending", "unverified"} else "partial"


def line_evidence_matches(raw_path: Path, locator: str, excerpt: str) -> bool:
    match = re.fullmatch(r"lines\s+(\d+)(?:-(\d+))?", locator.strip(), re.IGNORECASE)
    if not match or raw_path.suffix.casefold() not in TEXT_SUFFIXES:
        return False
    try:
        lines = raw_path.read_text(encoding="utf-8-sig").splitlines()
    except (OSError, UnicodeError):
        return False
    start = int(match.group(1))
    end = int(match.group(2) or start)
    if start < 1 or end < start or end > len(lines):
        return False
    scope = " ".join("\n".join(lines[start - 1 : end]).split())
    return bool(excerpt.strip()) and " ".join(excerpt.split()) in scope


def rebuild(root: Path) -> dict[str, Any]:
    kb_dir = root / ".evidence-kb"
    kb_dir.mkdir(parents=True, exist_ok=True)
    target = db_path(root)
    temporary = kb_dir / f"knowledge.{uuid.uuid4().hex}.tmp"
    connection = sqlite3.connect(temporary)
    errors: list[str] = []
    counts = {
        "sources": 0,
        "normalized": 0,
        "claims": 0,
        "decisions": 0,
        "canon": 0,
        "evidence_links": 0,
        "decision_links": 0,
    }
    try:
        create_schema(connection)
        built_at = now_iso()
        connection.executemany(
            "INSERT INTO metadata(key, value) VALUES (?, ?)",
            [("schema_version", SCHEMA_VERSION), ("built_at", built_at)],
        )

        source_ids: set[str] = set()
        source_raw_paths: dict[str, Path] = {}
        parent_links: dict[str, list[str]] = {}
        for path in sorted((root / "wiki" / "sources").glob("**/*.md")):
            metadata, body = parse_document(path)
            if str(metadata.get("type", "")).lower() != "source":
                continue
            source_id = str(metadata.get("id", "")).strip()
            raw_path_value = raw_reference(metadata)
            declared = str(metadata.get("raw_sha256", "")).lower()
            relative = relative_posix(path, root)
            if not source_id:
                errors.append(f"{relative}: id가 없습니다.")
                continue
            if source_id in source_ids:
                errors.append(f"{relative}: 중복 Source ID {source_id}")
                continue
            source_ids.add(source_id)
            actual = ""
            integrity = "missing"
            if raw_path_value:
                candidate = require_inside(root / raw_path_value, root / "raw", "raw source")
                if candidate.is_file():
                    actual = sha256(candidate)
                    integrity = "ok" if actual == declared else "mismatch"
            if not raw_path_value:
                errors.append(f"{relative}: raw/ 원문 경로가 없습니다.")
            elif integrity != "ok":
                errors.append(f"{relative}: raw 무결성 상태가 {integrity}입니다.")
            parents = as_list(metadata.get("parent_sources"))
            parent_links[source_id] = parents
            if raw_path_value:
                source_raw_paths[source_id] = require_inside(root / raw_path_value, root / "raw", "raw source")
            title = first_heading(body, path.stem)
            semantic_status = effective_semantic_status(metadata)
            structurally_verified = bool(metadata.get("structurally_verified", integrity == "ok"))
            coverage = {
                key: metadata.get(key, 0)
                for key in (
                    "raw_line_count",
                    "raw_byte_count",
                    "coverage_spans",
                    "evidence_spans",
                    "key_decisions",
                    "next_actions",
                    "chronology_entries",
                )
                if key in metadata
            }
            connection.execute(
                """INSERT INTO sources VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    source_id,
                    relative,
                    raw_path_value,
                    str(metadata.get("normalized_path", "")),
                    declared,
                    actual,
                    integrity,
                    str(metadata.get("source_type", "")),
                    str(metadata.get("provider", "")),
                    str(metadata.get("model", "")),
                    str(metadata.get("verification_status", "")),
                    int(structurally_verified),
                    semantic_status,
                    json.dumps(coverage, ensure_ascii=False),
                    str(metadata.get("epistemic_observation", "")),
                    str(metadata.get("epistemic_inference", "")),
                    json.dumps(parents, ensure_ascii=False),
                    str(metadata.get("independence_group", source_id)),
                    str(metadata.get("visibility", "private")),
                    int(bool(metadata.get("external_llm_allowed", False))),
                    title,
                    body,
                ),
            )
            connection.execute(
                "INSERT INTO search_index VALUES (?,?,?,?,?)",
                ("source", source_id, title, body, relative),
            )
            counts["sources"] += 1

        for source_id, parents in parent_links.items():
            for parent in parents:
                if parent not in source_ids:
                    errors.append(f"{source_id}: 존재하지 않는 parent source {parent}")

        for path in sorted((root / "wiki" / "normalized").glob("**/*.md")):
            metadata, body = parse_document(path)
            if str(metadata.get("type", "")).lower() != "normalized":
                continue
            derived = as_list(metadata.get("derived_from"))
            normalized_id = str(metadata.get("id", path.stem))
            if len(derived) != 1 or derived[0] not in source_ids:
                errors.append(f"{relative_posix(path, root)}: 유효한 derived_from Source ID 1개가 필요합니다.")
                continue
            title = first_heading(body, path.stem)
            connection.execute(
                "INSERT INTO search_index VALUES (?,?,?,?,?)",
                ("normalized", normalized_id, title, body, relative_posix(path, root)),
            )
            counts["normalized"] += 1

        claim_documents: list[tuple[Path, dict[str, Any], str]] = []
        claim_ids: set[str] = set()
        for path in sorted((root / "wiki" / "claims").glob("**/*.md")):
            metadata, body = parse_document(path)
            if str(metadata.get("type", "")).lower() != "claim":
                continue
            claim_id = str(metadata.get("id", "")).strip()
            status = str(metadata.get("status", "")).upper()
            statement = str(metadata.get("statement", "")).strip()
            relative = relative_posix(path, root)
            if not claim_id or claim_id in claim_ids:
                errors.append(f"{relative}: Claim ID가 없거나 중복입니다: {claim_id}")
                continue
            if status not in CLAIM_STATUSES:
                errors.append(f"{relative}: 허용되지 않은 Claim 상태 {status}")
            if not statement:
                errors.append(f"{relative}: statement가 없습니다.")
            confidence_value = metadata.get("confidence", "")
            confidence: float | None = None
            if confidence_value != "":
                try:
                    confidence = float(confidence_value)
                    if not 0 <= confidence <= 1:
                        raise ValueError
                except (TypeError, ValueError):
                    errors.append(f"{relative}: confidence는 0~1이어야 합니다.")
                    confidence = None
            claim_ids.add(claim_id)
            claim_documents.append((path, metadata, body))
            title = first_heading(body, claim_id)
            connection.execute(
                "INSERT INTO claims VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    claim_id,
                    relative,
                    statement,
                    status,
                    confidence,
                    str(metadata.get("claim_kind", "")),
                    json.dumps(as_list(metadata.get("topics")), ensure_ascii=False),
                    title,
                    body,
                ),
            )
            connection.execute(
                "INSERT INTO search_index VALUES (?,?,?,?,?)",
                ("claim", claim_id, title, f"{statement}\n{body}", relative),
            )
            counts["claims"] += 1

        for path, metadata, _ in claim_documents:
            claim_id = str(metadata["id"])
            evidence = as_list(metadata.get("evidence"))
            if not evidence:
                errors.append(f"{relative_posix(path, root)}: 모든 Claim에는 evidence가 필요합니다.")
            for item in evidence:
                source_id, relation, locator, excerpt = parse_evidence(item)
                if source_id not in source_ids:
                    errors.append(f"{claim_id}: 존재하지 않는 Source ID {source_id}")
                    continue
                if relation not in EVIDENCE_RELATIONS:
                    errors.append(f"{claim_id}: 허용되지 않은 evidence relation {relation}")
                    continue
                raw_path = source_raw_paths.get(source_id)
                if raw_path is None:
                    errors.append(f"{claim_id}: Source에 유효한 Raw 경로가 없습니다: {source_id}")
                    continue
                if not line_evidence_matches(raw_path, locator, excerpt):
                    errors.append(f"{claim_id}: Claim evidence가 Raw locator와 일치하지 않습니다: {locator}")
                    continue
                connection.execute(
                    "INSERT OR REPLACE INTO claim_sources VALUES (?,?,?,?,?)",
                    (claim_id, source_id, relation, locator, excerpt),
                )
                counts["evidence_links"] += 1
            for item in as_list(metadata.get("claim_relations")):
                related, relation = parse_relation(item)
                if related not in claim_ids:
                    errors.append(f"{claim_id}: 존재하지 않는 관련 Claim {related}")
                elif relation not in CLAIM_RELATIONS:
                    errors.append(f"{claim_id}: 허용되지 않은 Claim relation {relation}")
                else:
                    connection.execute(
                        "INSERT OR REPLACE INTO claim_relations VALUES (?,?,?)",
                        (claim_id, related, relation),
                    )

        decision_documents: list[tuple[Path, dict[str, Any], str, str]] = []
        decision_ids: set[str] = set()
        for path in sorted((root / "wiki" / "decisions").glob("**/*.md")):
            metadata, body = parse_document(path)
            if str(metadata.get("type", "")).lower() != "decision":
                continue
            decision_id = str(metadata.get("id", "")).strip()
            status = str(metadata.get("status", "")).upper()
            statement = str(metadata.get("statement", "")).strip()
            project_value = str(metadata.get("project", metadata.get("project_path", ""))).replace("\\", "/").removeprefix("./")
            if project_value and not project_value.startswith("wiki/"):
                project_value = f"wiki/{project_value}"
            relative = relative_posix(path, root)
            if not decision_id or decision_id in decision_ids:
                errors.append(f"{relative}: Decision ID가 없거나 중복입니다: {decision_id}")
                continue
            if status not in DECISION_STATUSES:
                errors.append(f"{relative}: 허용되지 않은 Decision 상태 {status}")
            if not statement:
                errors.append(f"{relative}: Decision statement가 없습니다.")
            project_path = root / project_value if project_value else Path()
            if not project_value or not project_path.is_file() or not project_value.casefold().startswith("wiki/projects/"):
                errors.append(f"{relative}: 존재하는 wiki/projects 경로가 필요합니다: {project_value}")
            next_actions = as_list(metadata.get("next_actions"))
            chronology = as_list(metadata.get("chronology"))
            if not next_actions:
                errors.append(f"{relative}: Decision에는 next_actions가 필요합니다.")
            if not chronology:
                errors.append(f"{relative}: Decision에는 chronology가 필요합니다.")
            decision_ids.add(decision_id)
            decision_documents.append((path, metadata, body, project_value))
            title = first_heading(body, decision_id)
            connection.execute(
                "INSERT INTO decisions VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (
                    decision_id,
                    relative,
                    statement,
                    status,
                    project_value,
                    str(metadata.get("decided_at", "")),
                    json.dumps(as_list(metadata.get("topics")), ensure_ascii=False),
                    json.dumps(next_actions, ensure_ascii=False),
                    json.dumps(chronology, ensure_ascii=False),
                    title,
                    body,
                ),
            )
            connection.execute(
                "INSERT INTO search_index VALUES (?,?,?,?,?)",
                (
                    "decision",
                    decision_id,
                    title,
                    "\n".join([statement, *next_actions, *chronology, body]),
                    relative,
                ),
            )
            counts["decisions"] += 1

        decision_metadata_by_id = {
            str(metadata["id"]): metadata for _, metadata, _, _ in decision_documents
        }
        for path, metadata, _, project_value in decision_documents:
            decision_id = str(metadata["id"])
            evidence = as_list(metadata.get("evidence"))
            if not evidence:
                errors.append(f"{relative_posix(path, root)}: 모든 Decision에는 evidence가 필요합니다.")
            project_front = ""
            if project_value and (root / project_value).is_file():
                project_front = parse_document(root / project_value)[0]
            decision_sources = [value.replace("\\", "/") for value in as_list(metadata.get("sources"))]
            decision_source_ids = as_list(metadata.get("source_ids"))
            project_scope = json.dumps(project_front, ensure_ascii=False).replace("\\", "/").casefold()
            for item in evidence:
                source_id, relation, locator, excerpt = parse_evidence(item)
                if source_id not in source_ids:
                    errors.append(f"{decision_id}: 존재하지 않는 Source ID {source_id}")
                    continue
                if relation not in DECISION_SOURCE_RELATIONS:
                    errors.append(f"{decision_id}: 허용되지 않은 Decision evidence relation {relation}")
                    continue
                raw_path = source_raw_paths.get(source_id)
                if raw_path is None:
                    errors.append(f"{decision_id}: Source에 유효한 Raw 경로가 없습니다: {source_id}")
                    continue
                if not line_evidence_matches(raw_path, locator, excerpt):
                    errors.append(f"{decision_id}: Decision evidence가 Raw locator와 일치하지 않습니다: {locator}")
                    continue
                raw_relative = relative_posix(raw_path, root)
                if raw_relative not in decision_sources and source_id not in decision_source_ids:
                    errors.append(f"{decision_id}: Decision frontmatter가 Source/Raw provenance를 기록하지 않습니다.")
                if raw_relative.casefold() not in project_scope and source_id.casefold() not in project_scope:
                    errors.append(f"{decision_id}: Project가 Decision Source/Raw provenance를 기록하지 않습니다.")
                connection.execute(
                    "INSERT OR REPLACE INTO decision_sources VALUES (?,?,?,?,?)",
                    (decision_id, source_id, relation, locator, excerpt),
                )
                counts["decision_links"] += 1

            action_ids: set[str] = set()
            for item in as_list(metadata.get("next_actions")):
                action_id, source_id, locator, action, excerpt = parse_located_action(item)
                if not re.fullmatch(r"[A-Za-z0-9_-]+", action_id) or not action or not excerpt:
                    errors.append(
                        f"{decision_id}: next_actions는 ACTION-ID | SOURCE-ID | lines N-M | action | excerpt 형식이어야 합니다."
                    )
                    continue
                if action_id in action_ids:
                    errors.append(f"{decision_id}: 중복 next action ID {action_id}")
                    continue
                action_ids.add(action_id)
                if source_id not in source_ids:
                    errors.append(f"{decision_id}: next action의 Source ID가 없습니다: {source_id}")
                    continue
                raw_path = source_raw_paths.get(source_id)
                if raw_path is None:
                    errors.append(f"{decision_id}: next action Source에 유효한 Raw 경로가 없습니다: {source_id}")
                    continue
                if not line_evidence_matches(raw_path, locator, excerpt):
                    errors.append(f"{decision_id}: next action이 Raw locator와 일치하지 않습니다: {locator}")
                    continue
                raw_relative = relative_posix(raw_path, root)
                if raw_relative not in decision_sources and source_id not in decision_source_ids:
                    errors.append(f"{decision_id}: next action provenance가 Decision frontmatter에 없습니다.")
                if raw_relative.casefold() not in project_scope and source_id.casefold() not in project_scope:
                    errors.append(f"{decision_id}: next action provenance가 Project에 없습니다.")

            for item in as_list(metadata.get("chronology")):
                event_date, event, source_id, locator, excerpt = parse_located_chronology(item)
                if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", event_date) or not event or not excerpt:
                    errors.append(
                        f"{decision_id}: chronology는 YYYY-MM-DD | event | SOURCE-ID | lines N-M | excerpt 형식이어야 합니다."
                    )
                    continue
                if source_id not in source_ids:
                    errors.append(f"{decision_id}: chronology의 Source ID가 없습니다: {source_id}")
                    continue
                raw_path = source_raw_paths.get(source_id)
                if raw_path is None:
                    errors.append(f"{decision_id}: chronology Source에 유효한 Raw 경로가 없습니다: {source_id}")
                    continue
                if not line_evidence_matches(raw_path, locator, excerpt):
                    errors.append(f"{decision_id}: chronology가 Raw locator와 일치하지 않습니다: {locator}")
                    continue
                raw_relative = relative_posix(raw_path, root)
                if raw_relative not in decision_sources and source_id not in decision_source_ids:
                    errors.append(f"{decision_id}: chronology provenance가 Decision frontmatter에 없습니다.")
                if raw_relative.casefold() not in project_scope and source_id.casefold() not in project_scope:
                    errors.append(f"{decision_id}: chronology provenance가 Project에 없습니다.")

            for related in as_list(metadata.get("supersedes")):
                if related not in decision_ids:
                    errors.append(f"{decision_id}: 존재하지 않는 superseded Decision {related}")
                elif related == decision_id:
                    errors.append(f"{decision_id}: Decision은 자신을 supersede할 수 없습니다.")
                else:
                    reverse = as_list(decision_metadata_by_id[related].get("superseded_by"))
                    if decision_id not in reverse:
                        errors.append(f"{decision_id}: {related}.superseded_by에 역관계가 없습니다.")
                    connection.execute(
                        "INSERT OR REPLACE INTO decision_relations VALUES (?,?,?)",
                        (decision_id, related, "supersedes"),
                    )
            for related in as_list(metadata.get("superseded_by")):
                if related not in decision_ids:
                    errors.append(f"{decision_id}: 존재하지 않는 superseding Decision {related}")
                else:
                    reverse = as_list(decision_metadata_by_id[related].get("supersedes"))
                    if decision_id not in reverse:
                        errors.append(f"{decision_id}: {related}.supersedes에 역관계가 없습니다.")
                    connection.execute(
                        "INSERT OR REPLACE INTO decision_relations VALUES (?,?,?)",
                        (decision_id, related, "superseded_by"),
                    )

        for path in sorted((root / "wiki" / "canon").glob("**/*.md")):
            metadata, body = parse_document(path)
            if str(metadata.get("type", "")).lower() != "canon":
                continue
            canon_id = str(metadata.get("id", "")).strip()
            relative = relative_posix(path, root)
            reviewed = bool(metadata.get("manual_reviewed", False))
            linked_claims = as_list(metadata.get("claim_ids"))
            if not canon_id:
                errors.append(f"{relative}: Canon ID가 없습니다.")
                continue
            if not reviewed:
                errors.append(f"{relative}: Canon은 manual_reviewed: true가 필요합니다.")
            if not linked_claims:
                errors.append(f"{relative}: Canon에는 claim_ids가 필요합니다.")
            title = first_heading(body, canon_id)
            connection.execute("INSERT INTO canon VALUES (?,?,?,?,?)", (canon_id, relative, title, body, int(reviewed)))
            connection.execute(
                "INSERT INTO search_index VALUES (?,?,?,?,?)",
                ("canon", canon_id, title, body, relative),
            )
            for claim_id in linked_claims:
                if claim_id not in claim_ids:
                    errors.append(f"{canon_id}: 존재하지 않는 Claim {claim_id}")
                else:
                    connection.execute("INSERT INTO canon_claims VALUES (?,?)", (canon_id, claim_id))
            counts["canon"] += 1

        foreign_key_errors = connection.execute("PRAGMA foreign_key_check").fetchall()
        if foreign_key_errors:
            errors.append(f"SQLite foreign key 오류: {foreign_key_errors}")
        if errors:
            raise KBError("Evidence KB rebuild 실패:\n- " + "\n- ".join(errors))
        if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise KBError("SQLite integrity_check 실패")
        connection.commit()
        connection.close()
        os.replace(temporary, target)
        return {
            "status": "ok",
            "database": relative_posix(target, root),
            "built_at": built_at,
            **counts,
        }
    except Exception:
        connection.close()
        temporary.unlink(missing_ok=True)
        raise


def connect_db(root: Path) -> sqlite3.Connection:
    path = db_path(root)
    if not path.is_file():
        raise KBError("knowledge.db가 없습니다. 먼저 rebuild를 실행하세요.")
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    return connection


def fts_query(query: str) -> str:
    terms = [term.replace('"', "").strip() for term in query.split() if term.strip()]
    if not terms:
        raise KBError("검색어가 비어 있습니다.")
    return " AND ".join(f'"{term}"' for term in terms)


def search(root: Path, query: str, limit: int) -> dict[str, Any]:
    with closing(connect_db(root)) as connection:
        rows = connection.execute(
            """SELECT doc_type, doc_id, title, path,
                      snippet(search_index, 3, '[', ']', ' … ', 18) AS snippet,
                      bm25(search_index) AS rank
               FROM search_index
               WHERE search_index MATCH ?
               ORDER BY rank LIMIT ?""",
            (fts_query(query), limit),
        ).fetchall()
        results = [dict(row) for row in rows]
        for item in results:
            if item["doc_type"] == "source":
                row = connection.execute(
                    "SELECT structurally_verified, semantic_status FROM sources WHERE id = ?",
                    (item["doc_id"],),
                ).fetchone()
                if row:
                    item.update(dict(row))
            elif item["doc_type"] == "decision":
                row = connection.execute(
                    "SELECT status, project_path FROM decisions WHERE id = ?",
                    (item["doc_id"],),
                ).fetchone()
                if row:
                    item.update(dict(row))
                item["locators"] = [
                    value[0]
                    for value in connection.execute(
                        "SELECT locator FROM decision_sources WHERE decision_id = ? ORDER BY locator",
                        (item["doc_id"],),
                    ).fetchall()
                ]
    return {"query": query, "count": len(results), "results": results}


def live_source(root: Path, row: sqlite3.Row) -> dict[str, Any]:
    raw_path = require_inside(root / row["raw_path"], root / "raw", "raw source")
    actual = sha256(raw_path) if raw_path.is_file() else None
    return {
        "id": row["id"],
        "provider": row["provider"],
        "model": row["model"],
        "source_type": row["source_type"],
        "raw_path": row["raw_path"],
        "source_doc_path": row["source_doc_path"],
        "declared_sha256": row["declared_sha256"],
        "actual_sha256": actual,
        "integrity": "ok" if actual == row["declared_sha256"] else "mismatch_or_missing",
        "verification_status": row["verification_status"],
        "structurally_verified": bool(row["structurally_verified"]),
        "semantic_status": row["semantic_status"],
        "coverage": json.loads(row["coverage_json"]),
        "parent_sources": json.loads(row["parent_sources_json"]),
        "independence_group": row["independence_group"],
    }


def claim_trace(connection: sqlite3.Connection, root: Path, claim_id: str) -> dict[str, Any]:
    claim = connection.execute("SELECT * FROM claims WHERE id = ?", (claim_id,)).fetchone()
    if not claim:
        raise KBError(f"Claim을 찾지 못했습니다: {claim_id}")
    evidence_rows = connection.execute(
        """SELECT cs.relation, cs.locator, cs.excerpt, s.*
           FROM claim_sources cs JOIN sources s ON s.id = cs.source_id
           WHERE cs.claim_id = ? ORDER BY s.id""",
        (claim_id,),
    ).fetchall()
    evidence = []
    for row in evidence_rows:
        item = live_source(root, row)
        item.update({"relation": row["relation"], "locator": row["locator"], "excerpt": row["excerpt"]})
        evidence.append(item)
    relations = [
        dict(row)
        for row in connection.execute(
            "SELECT related_claim_id, relation FROM claim_relations WHERE claim_id = ?",
            (claim_id,),
        ).fetchall()
    ]
    return {
        "id": claim["id"],
        "statement": claim["statement"],
        "status": claim["status"],
        "confidence": claim["confidence"],
        "claim_kind": claim["claim_kind"],
        "path": claim["path"],
        "evidence": evidence,
        "claim_relations": relations,
    }


def decision_trace(connection: sqlite3.Connection, root: Path, decision_id: str) -> dict[str, Any]:
    decision = connection.execute("SELECT * FROM decisions WHERE id = ?", (decision_id,)).fetchone()
    if not decision:
        raise KBError(f"Decision을 찾지 못했습니다: {decision_id}")
    evidence_rows = connection.execute(
        """SELECT ds.relation, ds.locator, ds.excerpt, s.*
           FROM decision_sources ds JOIN sources s ON s.id = ds.source_id
           WHERE ds.decision_id = ? ORDER BY s.id, ds.locator""",
        (decision_id,),
    ).fetchall()
    evidence = []
    for row in evidence_rows:
        item = live_source(root, row)
        item.update({"relation": row["relation"], "locator": row["locator"], "excerpt": row["excerpt"]})
        evidence.append(item)
    project_path = root / decision["project_path"]
    project_metadata, project_body = parse_document(project_path)
    project_raw_sources = [
        value.replace("\\", "/")
        for value in as_list(project_metadata.get("sources")) + as_list(project_metadata.get("source"))
        if value.replace("\\", "/").startswith("raw/")
    ]
    project_source_ids = as_list(project_metadata.get("source_ids"))
    provenance_matches = all(
        item["raw_path"] in project_raw_sources or item["id"] in project_source_ids
        for item in evidence
    )
    relations = [
        dict(row)
        for row in connection.execute(
            "SELECT related_decision_id, relation FROM decision_relations WHERE decision_id = ? ORDER BY relation, related_decision_id",
            (decision_id,),
        ).fetchall()
    ]
    return {
        "id": decision["id"],
        "statement": decision["statement"],
        "status": decision["status"],
        "path": decision["path"],
        "decided_at": decision["decided_at"],
        "next_actions": json.loads(decision["next_actions_json"]),
        "chronology": json.loads(decision["chronology_json"]),
        "evidence": evidence,
        "decision_relations": relations,
        "project": {
            "path": decision["project_path"],
            "title": first_heading(project_body, project_path.stem),
            "raw_sources": project_raw_sources,
            "source_ids": project_source_ids,
            "provenance_matches": provenance_matches,
        },
    }


def trace(root: Path, item_id: str) -> dict[str, Any]:
    with closing(connect_db(root)) as connection:
        source = connection.execute("SELECT * FROM sources WHERE id = ?", (item_id,)).fetchone()
        if source:
            linked_decisions = [
                dict(row)
                for row in connection.execute(
                    """SELECT d.id, d.status, d.path, d.project_path, ds.relation, ds.locator
                       FROM decision_sources ds JOIN decisions d ON d.id = ds.decision_id
                       WHERE ds.source_id = ? ORDER BY d.id""",
                    (item_id,),
                ).fetchall()
            ]
            return {
                "trace_type": "source_to_decision_project_to_raw",
                "source": live_source(root, source),
                "decisions": linked_decisions,
            }
        claim = connection.execute("SELECT id FROM claims WHERE id = ?", (item_id,)).fetchone()
        if claim:
            return {"trace_type": "claim_to_evidence_to_raw", "claim": claim_trace(connection, root, item_id)}
        decision = connection.execute("SELECT id FROM decisions WHERE id = ?", (item_id,)).fetchone()
        if decision:
            return {
                "trace_type": "decision_to_project_to_evidence_to_raw",
                "decision": decision_trace(connection, root, item_id),
            }
        canon = connection.execute("SELECT * FROM canon WHERE id = ?", (item_id,)).fetchone()
        if canon:
            claim_ids = [
                row[0]
                for row in connection.execute(
                    "SELECT claim_id FROM canon_claims WHERE canon_id = ? ORDER BY claim_id",
                    (item_id,),
                ).fetchall()
            ]
            return {
                "trace_type": "canon_to_claim_to_evidence_to_raw",
                "canon": {"id": canon["id"], "title": canon["title"], "path": canon["path"]},
                "claims": [claim_trace(connection, root, claim_id) for claim_id in claim_ids],
            }
    raise KBError(f"Source/Claim/Decision/Canon ID를 찾지 못했습니다: {item_id}")


def status(root: Path) -> dict[str, Any]:
    with closing(connect_db(root)) as connection:
        built_at = connection.execute("SELECT value FROM metadata WHERE key='built_at'").fetchone()[0]
        counts = {
            table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in ("sources", "claims", "claim_sources", "decisions", "decision_sources", "canon")
        }
        claim_statuses = {
            row[0]: row[1]
            for row in connection.execute("SELECT status, COUNT(*) FROM claims GROUP BY status ORDER BY status")
        }
        integrity = {
            row[0]: row[1]
            for row in connection.execute("SELECT integrity_status, COUNT(*) FROM sources GROUP BY integrity_status")
        }
        semantic_statuses = {
            row[0]: row[1]
            for row in connection.execute("SELECT semantic_status, COUNT(*) FROM sources GROUP BY semantic_status ORDER BY semantic_status")
        }
        decision_statuses = {
            row[0]: row[1]
            for row in connection.execute("SELECT status, COUNT(*) FROM decisions GROUP BY status ORDER BY status")
        }
    return {
        "built_at": built_at,
        **counts,
        "claim_statuses": claim_statuses,
        "decision_statuses": decision_statuses,
        "source_integrity": integrity,
        "source_semantic_statuses": semantic_statuses,
    }


def selftest() -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="evidence-kb-") as temporary:
        root = Path(temporary) / "vault"
        (root / "raw").mkdir(parents=True)
        (root / "wiki").mkdir()
        incoming = Path(temporary) / "qwen.txt"
        incoming.write_text("첫 프레임은 anchor 역할을 할 가능성이 있다.\n", encoding="utf-8")
        registered = register_source(root, incoming, "qwen", "llm_analysis", "inbox", None, "unknown", [])
        source_id = registered["source_id"]
        source_note = root / registered["source_note"]
        raw_path = registered["raw_path"]
        digest = registered["sha256"]
        source_note.write_text(
            "\n".join(
                [
                    "---", "type: source", f"id: {quote(source_id)}", "status: active",
                    yaml_list("topics", ["애니메이션"]), yaml_list("sources", [raw_path]),
                    f"normalized_path: {quote(registered['normalized_path'])}", f"raw_sha256: {quote(digest)}",
                    "source_type: llm_analysis", "provider: qwen", "model: unknown",
                    "verification_status: unverified", "epistemic_observation: low", "epistemic_inference: high",
                    "parent_sources: []", f"independence_group: {quote(source_id)}", "visibility: private",
                    "external_llm_allowed: false", "key_claims: 1", "entities: 1", "concepts: 1",
                    "reflected_docs: 1", "relations: 1", "evidence_spans: 1", "---", "",
                    "# 원본 요약 — Qwen", "", "## 핵심 내용", "", "Anchor 가설.", "",
                    "## 근거", "", "> 첫 프레임은 anchor 역할을 할 가능성이 있다.", "",
                    "## 갱신한 문서", "", "- [[claims/animation/CLAIM-ANIM-0001]]", "",
                ]
            ),
            encoding="utf-8",
        )
        claim_dir = root / "wiki" / "claims" / "animation"
        claim_dir.mkdir(parents=True)
        claim_dir.joinpath("CLAIM-ANIM-0001.md").write_text(
            "\n".join(
                [
                    "---", "type: claim", "id: CLAIM-ANIM-0001", "status: HYPOTHESIS",
                    "confidence: 0.4", "claim_kind: implementation", yaml_list("topics", ["애니메이션"]),
                    f"statement: {quote('첫 프레임이 후속 프레임의 anchor로 사용될 가능성이 있다.')}",
                    yaml_list("evidence", [f"{source_id} | supports | lines 1-1 | 첫 프레임은 anchor 역할을 할 가능성이 있다."]),
                    "claim_relations: []", "---", "", "# Anchor frame 가설", "",
                ]
            ),
            encoding="utf-8",
        )
        project_dir = root / "wiki" / "projects"
        project_dir.mkdir()
        project_dir.joinpath("animation.md").write_text(
            "\n".join(
                [
                    "---", "type: project", yaml_list("sources", [raw_path]),
                    yaml_list("source_ids", [source_id]), "---", "", "# Animation project", "",
                ]
            ),
            encoding="utf-8",
        )
        decision_dir = root / "wiki" / "decisions"
        decision_dir.mkdir()
        decision_dir.joinpath("DECISION-ANIM-0001.md").write_text(
            "\n".join(
                [
                    "---", "type: decision", "id: DECISION-ANIM-0001", "status: PROPOSED",
                    f"statement: {quote('2d-game-art anchor workflow를 설계한다.')}",
                    "project: wiki/projects/animation.md", yaml_list("topics", ["애니메이션"]),
                    yaml_list("sources", [raw_path]), yaml_list("source_ids", [source_id]),
                    yaml_list("evidence", [f"{source_id} | recommends | lines 1-1 | 첫 프레임은 anchor 역할을 할 가능성이 있다."]),
                    yaml_list("next_actions", [f"ACTION-ANIM-0001 | {source_id} | lines 1-1 | anchor contract 작성 | 첫 프레임은 anchor 역할을 할 가능성이 있다."]),
                    yaml_list("chronology", [f"2026-08-27 | proposed | {source_id} | lines 1-1 | 첫 프레임은 anchor 역할을 할 가능성이 있다."]),
                    "supersedes: []", "superseded_by: []", "---", "", "# Animation decision", "",
                ]
            ),
            encoding="utf-8",
        )
        canon_dir = root / "wiki" / "canon"
        canon_dir.mkdir()
        canon_dir.joinpath("animation.md").write_text(
            "\n".join(
                [
                    "---", "type: canon", "id: CANON-ANIM-0001", "manual_reviewed: true",
                    yaml_list("claim_ids", ["CLAIM-ANIM-0001"]), "---", "", "# Animation 연구 상태", "",
                ]
            ),
            encoding="utf-8",
        )
        built = rebuild(root)
        found = search(root, "anchor", 10)
        traced = trace(root, "CANON-ANIM-0001")
        decision_found = search(root, "2d-game-art", 10)
        decision_traced = trace(root, "DECISION-ANIM-0001")
        assert built["sources"] == 1 and built["claims"] == 1 and built["decisions"] == 1
        assert found["count"] >= 1
        assert decision_found["count"] >= 1
        assert traced["claims"][0]["evidence"][0]["integrity"] == "ok"
        assert decision_traced["decision"]["project"]["provenance_matches"]
        decision_dir.joinpath("DECISION-ANIM-0002.md").write_text(
            "\n".join(
                [
                    "---", "type: decision", "id: DECISION-ANIM-0002", "status: ADOPTED",
                    f"statement: {quote('2d-game-art anchor workflow를 채택한다.')}",
                    "project: wiki/projects/animation.md", yaml_list("topics", ["애니메이션"]),
                    yaml_list("sources", [raw_path]), yaml_list("source_ids", [source_id]),
                    yaml_list("evidence", [f"{source_id} | adopts | lines 1-1 | 첫 프레임은 anchor 역할을 할 가능성이 있다."]),
                    yaml_list("next_actions", [f"ACTION-ANIM-0002 | {source_id} | lines 1-1 | anchor contract 채택 | 첫 프레임은 anchor 역할을 할 가능성이 있다."]),
                    yaml_list("chronology", [f"2026-08-28 | adopted | {source_id} | lines 1-1 | 첫 프레임은 anchor 역할을 할 가능성이 있다."]),
                    yaml_list("supersedes", ["DECISION-ANIM-0001"]), "superseded_by: []", "---", "", "# Adopted animation decision", "",
                ]
            ),
            encoding="utf-8",
        )
        try:
            rebuild(root)
        except KBError as error:
            assert "역관계" in str(error)
        else:
            raise AssertionError("Decision supersedes without reciprocal superseded_by must fail")
        first_decision = decision_dir / "DECISION-ANIM-0001.md"
        first_decision.write_text(
            first_decision.read_text(encoding="utf-8").replace(
                "superseded_by: []", yaml_list("superseded_by", ["DECISION-ANIM-0002"])
            ),
            encoding="utf-8",
        )
        symmetric = rebuild(root)
        assert symmetric["decisions"] == 2
        return {
            "status": "ok",
            "checks": ["register", "normalize", "rebuild", "fts5", "canon-trace", "decision-trace", "decision-relation-symmetry"],
        }


def emit(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(description=__doc__)
    command.add_argument("--root", help="raw/와 wiki/가 있는 볼트 루트")
    subcommands = command.add_subparsers(dest="command", required=True)

    register = subcommands.add_parser("register", help="원본 바이트를 raw/에 보존하고 검토 대기 문서를 생성")
    register.add_argument("file")
    register.add_argument("--provider", default="user")
    register.add_argument("--source-type", default="document")
    register.add_argument("--category", default="inbox")
    register.add_argument("--title")
    register.add_argument("--model", default="unknown")
    register.add_argument("--parent-source", action="append", default=[])

    subcommands.add_parser("rebuild", help="Markdown 정본을 검증하고 SQLite/FTS5를 원자적으로 재구축")
    search_command = subcommands.add_parser("search", help="Canon, Claim, Source, Normalized 문서를 FTS5 검색")
    search_command.add_argument("query")
    search_command.add_argument("--limit", type=int, default=10)
    trace_command = subcommands.add_parser("trace", help="Canon/Claim/Source에서 raw 원문까지 역추적")
    trace_command.add_argument("id")
    subcommands.add_parser("status", help="현재 인덱스와 Claim 상태 집계")
    subcommands.add_parser("selftest", help="임시 실제 스키마에서 최소 수직 슬라이스 검사")
    return command


def main() -> int:
    configure_utf8_stdout()
    args = parser().parse_args()
    try:
        if args.command == "selftest":
            emit(selftest())
            return 0
        root = find_root(args.root)
        if args.command == "register":
            result = register_source(
                root,
                Path(args.file),
                args.provider,
                args.source_type,
                args.category,
                args.title,
                args.model,
                args.parent_source,
            )
        elif args.command == "rebuild":
            result = rebuild(root)
        elif args.command == "search":
            result = search(root, args.query, args.limit)
        elif args.command == "trace":
            result = trace(root, args.id)
        elif args.command == "status":
            result = status(root)
        else:
            raise KBError(f"알 수 없는 명령: {args.command}")
        emit(result)
        return 0
    except (KBError, OSError, sqlite3.Error) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

