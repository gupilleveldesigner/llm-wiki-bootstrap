#!/usr/bin/env python3
"""Deterministic semantic-review contract for one-to-one Source records."""

from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path
from typing import Any


SEMANTIC_STATUSES = {"pending", "partial", "reviewed"}
TEXT_SUFFIXES = {
    ".md", ".markdown", ".txt", ".csv", ".json", ".yaml", ".yml", ".log",
    ".py", ".ps1", ".js", ".jsx", ".ts", ".tsx", ".html", ".xml", ".toml", ".ini", ".sh", ".sql", ".css",
}
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".bmp", ".avif"}
LONG_SOURCE_LINES = 300
WIKILINK_RE = re.compile(r"\[\[([^\]|#]+)(?:#[^\]|]+)?(?:\|[^\]]+)?\]\]")
LOCATOR_RE = re.compile(r"^(lines|bytes)\s+(\d+)(?:-(\d+))?$", re.IGNORECASE)
EVIDENCE_RE = re.compile(r"^\s*>\s*(?:\[([^\]]+)\]\s*)?(.+?)\s*$")
ITEM_RE = re.compile(r"^-\s+(.+?)\s*$")
LOCATED_ITEM_RE = re.compile(r"^([^|]+?)\s*\|\s*((?:lines|bytes)\s+\d+(?:-\d+)?)\s*\|\s*(.+)$", re.IGNORECASE)
COUNT_SECTIONS = {
    "key_claims": ("핵심 주장", "claim 후보"),
    "entities": ("엔티티",),
    "concepts": ("개념",),
    "reflected_docs": ("wiki에 반영된 문서", "반영 문서"),
    "relations": ("관계",),
    "coverage_spans": ("coverage", "의미 coverage"),
    "key_decisions": ("핵심 결정",),
    "next_actions": ("다음 행동",),
    "chronology_entries": ("chronology", "의사결정 연혁"),
}


def frontmatter(text: str) -> str:
    if not text.startswith("---"):
        return ""
    parts = text.split("---", 2)
    return parts[1] if len(parts) == 3 else ""


def body(text: str) -> str:
    return text.split("---", 2)[-1] if text.startswith("---") else text


def field(text_or_frontmatter: str, key: str) -> str:
    scope = frontmatter(text_or_frontmatter) if text_or_frontmatter.startswith("---") else text_or_frontmatter
    match = re.search(rf"(?m)^{re.escape(key)}:\s*(.*)$", scope)
    return match.group(1).strip().strip("\"'") if match else ""


def int_field(text: str, key: str) -> int | None:
    try:
        return int(field(text, key))
    except ValueError:
        return None


def bool_field(text: str, key: str) -> bool | None:
    value = field(text, key).casefold()
    if value == "true":
        return True
    if value == "false":
        return False
    return None


def sections(text: str) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    current = ""
    for line in body(text).splitlines():
        heading = re.match(r"^##\s+(.+?)\s*$", line)
        if heading:
            current = heading.group(1).strip().casefold()
            result.setdefault(current, [])
        elif current:
            result[current].append(line)
    return result


def section_lines(parsed: dict[str, list[str]], aliases: tuple[str, ...]) -> list[str] | None:
    for alias in aliases:
        if alias.casefold() in parsed:
            return parsed[alias.casefold()]
    return None


def bullet_items(lines: list[str] | None) -> list[str]:
    if lines is None:
        return []
    items = [match.group(1).strip() for line in lines if (match := ITEM_RE.match(line))]
    return [item for item in items if item.casefold() not in {"없음", "none", "해당 없음", "n/a"}]


def parse_locator(value: str) -> tuple[str, int, int] | None:
    match = LOCATOR_RE.fullmatch(value.strip())
    if not match:
        return None
    kind = match.group(1).casefold()
    start = int(match.group(2))
    end = int(match.group(3) or start)
    return kind, start, end


def evidence_entries(text: str) -> list[dict[str, Any]]:
    parsed = sections(text)
    lines = section_lines(parsed, ("근거", "evidence")) or []
    entries: list[dict[str, Any]] = []
    for line in lines:
        match = EVIDENCE_RE.match(line)
        if match:
            entries.append({"locator": match.group(1) or "", "quote": match.group(2).strip()})
    return entries


def located_items(lines: list[str] | None) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    for item in bullet_items(lines):
        match = LOCATED_ITEM_RE.fullmatch(item)
        if match:
            result.append({"id": match.group(1).strip(), "locator": match.group(2).strip(), "summary": match.group(3).strip()})
    return result


def _read_text(path: Path) -> tuple[str | None, list[str]]:
    for encoding in ("utf-8-sig", "utf-16", "cp949", "latin-1"):
        try:
            value = path.read_text(encoding=encoding)
            return value, value.splitlines()
        except (OSError, UnicodeError):
            continue
    return None, []


def _normalized(value: str) -> str:
    return " ".join(value.split())


def _locator_content(raw_path: Path, raw_text: str | None, raw_lines: list[str], locator: tuple[str, int, int]) -> str | bytes | None:
    kind, start, end = locator
    if start < (0 if kind == "bytes" else 1) or end < start:
        return None
    if kind == "lines":
        if raw_text is None or end > len(raw_lines):
            return None
        return "\n".join(raw_lines[start - 1 : end])
    try:
        raw = raw_path.read_bytes()
    except OSError:
        return None
    if end >= len(raw):
        return None
    return raw[start : end + 1]


def _quote_matches(content: str | bytes | None, quote: str) -> bool:
    if content is None or not quote:
        return False
    if isinstance(content, bytes):
        return quote.isascii() and quote.encode("ascii") in content
    return _normalized(quote) in _normalized(content)


def effective_semantic_status(text: str) -> str:
    declared = field(text, "semantic_status").casefold()
    if declared in SEMANTIC_STATUSES:
        return declared
    status = field(text, "status").casefold()
    if status in {"pending", "unverified"}:
        return "pending"
    return "partial"


def _relative_by_identity(path: Path, root: Path) -> str:
    parts: list[str] = []
    current = path
    while True:
        try:
            if os.path.samefile(current, root):
                return "/".join(reversed(parts))
        except OSError:
            pass
        if current == current.parent:
            raise ValueError(f"path is outside root: {path}")
        parts.append(current.name)
        current = current.parent


def _resolve_wiki_target(root: Path, target: str) -> Path | None:
    normalized = target.strip().replace("\\", "/").removeprefix("./")
    candidates = [root / "wiki" / normalized, root / normalized]
    for candidate in tuple(candidates):
        if not candidate.suffix:
            candidates.append(candidate.with_suffix(".md"))
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
            _relative_by_identity(resolved, (root / "wiki").resolve())
        except (OSError, ValueError):
            continue
        if resolved.is_file():
            return resolved
    return None


def _provenance_errors(root: Path, source_text: str, raw_path: Path, reflected_lines: list[str] | None) -> list[str]:
    errors: list[str] = []
    raw_relative = _relative_by_identity(raw_path, root).casefold()
    source_id = field(source_text, "id").casefold()
    targets = WIKILINK_RE.findall("\n".join(reflected_lines or []))
    for target in targets:
        target_path = _resolve_wiki_target(root, target)
        if target_path is None:
            errors.append(f"reflected document does not exist: {target}")
            continue
        target_front = frontmatter(target_path.read_text(encoding="utf-8-sig")).replace("\\", "/").casefold()
        if raw_relative not in target_front and (not source_id or source_id not in target_front):
            errors.append(f"reflected document lacks reverse Source/Raw provenance: {target}")
    return errors


def review_source_record(root: Path, source_path: Path, raw_path: Path, text: str) -> dict[str, Any]:
    """Return an effective semantic state; only an error-free explicit review is reviewed."""
    declared = field(text, "semantic_status").casefold()
    effective = effective_semantic_status(text)
    raw_text, raw_lines = _read_text(raw_path) if raw_path.suffix.casefold() in TEXT_SUFFIXES else (None, [])
    raw_units = len(raw_lines) if raw_text is not None else raw_path.stat().st_size
    errors: list[str] = []
    parsed = sections(text)
    actual_counts: dict[str, int] = {}

    if declared and declared not in SEMANTIC_STATUSES:
        errors.append(f"unsupported semantic_status: {declared}")
    if declared != "reviewed":
        return {
            "declared_status": declared or None,
            "semantic_status": effective,
            "structurally_verified": bool_field(text, "structurally_verified"),
            "actual_counts": actual_counts,
            "errors": errors,
        }
    if bool_field(text, "structurally_verified") is not True:
        errors.append("semantic reviewed requires structurally_verified: true")
    if raw_path.suffix.casefold() in IMAGE_SUFFIXES:
        errors.append("image semantic reviewed requires a typed image-region locator contract; byte quotes are structural only")

    for key, aliases in COUNT_SECTIONS.items():
        lines = section_lines(parsed, aliases)
        if lines is None:
            errors.append(f"semantic reviewed requires section for {key}")
        actual_counts[key] = len(bullet_items(lines))
        declared_count = int_field(text, key)
        if declared_count is None:
            errors.append(f"semantic reviewed requires integer {key}")
        elif declared_count != actual_counts[key]:
            errors.append(f"declared {key}={declared_count} does not match body items={actual_counts[key]}")

    evidence = evidence_entries(text)
    actual_counts["evidence_spans"] = len(evidence)
    declared_evidence = int_field(text, "evidence_spans")
    if declared_evidence is None:
        errors.append("semantic reviewed requires integer evidence_spans")
    elif declared_evidence != len(evidence):
        errors.append(f"declared evidence_spans={declared_evidence} does not match located quotes={len(evidence)}")

    declared_units = int_field(text, "raw_line_count" if raw_text is not None else "raw_byte_count")
    unit_key = "raw_line_count" if raw_text is not None else "raw_byte_count"
    if declared_units != raw_units:
        errors.append(f"{unit_key}={declared_units} does not match Raw={raw_units}")

    coverage_lines = section_lines(parsed, COUNT_SECTIONS["coverage_spans"])
    coverage = located_items(coverage_lines)
    if len(coverage) != actual_counts.get("coverage_spans", 0):
        errors.append("every coverage item must use `label | lines/bytes start-end | summary`")
    located: list[tuple[str, int, int, str]] = []
    for item in coverage:
        locator = parse_locator(item["locator"])
        if locator is None or _locator_content(raw_path, raw_text, raw_lines, locator) is None:
            errors.append(f"invalid coverage locator: {item['locator']}")
        else:
            located.append((*locator, item["id"].casefold()))

    evidence_locators: list[tuple[str, int, int]] = []
    for entry in evidence:
        locator = parse_locator(entry["locator"])
        if locator is None:
            errors.append("semantic reviewed evidence quotes require [lines/bytes start-end] locators")
            continue
        content = _locator_content(raw_path, raw_text, raw_lines, locator)
        if not _quote_matches(content, entry["quote"]):
            errors.append(f"evidence quote does not match its Raw locator: {entry['locator']}")
        else:
            evidence_locators.append(locator)

    for key in ("key_decisions", "next_actions", "chronology_entries"):
        lines = section_lines(parsed, COUNT_SECTIONS[key])
        items = located_items(lines)
        if len(items) != actual_counts.get(key, 0):
            errors.append(f"every {key} item must use `id | lines/bytes start-end | summary`")
        for item in items:
            locator = parse_locator(item["locator"])
            if locator is None or _locator_content(raw_path, raw_text, raw_lines, locator) is None:
                errors.append(f"invalid {key} locator: {item['locator']}")

    if raw_text is not None and raw_units >= LONG_SOURCE_LINES:
        roles = {role: (kind, start, end) for kind, start, end, role in located}
        for role in ("start", "middle", "end"):
            if role not in roles:
                errors.append(f"long Source semantic review requires {role} coverage")
        if "start" in roles and roles["start"][1] > max(1, raw_units // 10):
            errors.append("start coverage does not reach the Raw head")
        if "middle" in roles:
            _, start, end = roles["middle"]
            if end < raw_units // 3 or start > (raw_units * 2) // 3:
                errors.append("middle coverage does not overlap the Raw middle third")
        if "end" in roles and roles["end"][2] != raw_units:
            errors.append("end coverage must reach Raw EOF")
        for role in ("start", "middle", "end"):
            if role not in roles:
                continue
            kind, start, end = roles[role]
            if not any(e_kind == kind and e_start <= end and e_end >= start for e_kind, e_start, e_end in evidence_locators):
                errors.append(f"{role} coverage lacks a matching located evidence quote")

        source_type = field(text, "source_type").casefold()
        if source_type in {"llm_conversation", "conversation", "chat"}:
            for key in ("key_decisions", "next_actions", "chronology_entries"):
                if actual_counts.get(key, 0) <= 0:
                    errors.append(f"long conversation semantic review requires {key}")
            tail_floor = raw_units - max(5, raw_units // 20)
            tail_locators: list[tuple[str, int, int]] = []
            for key in ("key_decisions", "next_actions"):
                for item in located_items(section_lines(parsed, COUNT_SECTIONS[key])):
                    locator = parse_locator(item["locator"])
                    if locator:
                        tail_locators.append(locator)
            if not any(kind == "lines" and end >= tail_floor for kind, _, end in tail_locators):
                errors.append("long conversation review misses a tail decision/action locator")

    reflected_lines = section_lines(parsed, COUNT_SECTIONS["reflected_docs"])
    reflected_links = WIKILINK_RE.findall("\n".join(reflected_lines or []))
    if len(reflected_links) != actual_counts.get("reflected_docs", 0):
        errors.append("reflected_docs must count only wikilinks in `Wiki에 반영된 문서`")
    errors.extend(_provenance_errors(root, text, raw_path, reflected_lines))

    if actual_counts.get("reflected_docs", 0) <= 0:
        errors.append("semantic reviewed requires at least one reflected document")
    if len(evidence) <= 0:
        errors.append("semantic reviewed requires located evidence")
    if sum(actual_counts.get(key, 0) for key in ("key_claims", "key_decisions", "next_actions")) <= 0:
        errors.append("semantic reviewed requires a claim, decision, or next action")

    return {
        "declared_status": declared,
        "semantic_status": "reviewed" if not errors else "partial",
        "structurally_verified": bool_field(text, "structurally_verified"),
        "actual_counts": actual_counts,
        "errors": errors,
    }


def semantic_partition(raw_path: Path, *, max_lines: int = 400, overlap_lines: int = 20) -> dict[str, Any]:
    """Return a range manifest that covers every line, including EOF, without writing Raw."""
    if max_lines <= 0 or overlap_lines < 0 or overlap_lines >= max_lines:
        raise ValueError("max_lines must be positive and overlap_lines must be between 0 and max_lines-1")
    raw_text, lines = _read_text(raw_path) if raw_path.suffix.casefold() in TEXT_SUFFIXES else (None, [])
    digest = hashlib.sha256(raw_path.read_bytes()).hexdigest()
    if raw_text is None:
        return {
            "path": raw_path.as_posix(),
            "sha256": digest,
            "unit": "bytes",
            "total": raw_path.stat().st_size,
            "chunks": [{"index": 1, "start": 0, "end": max(0, raw_path.stat().st_size - 1), "role": "full"}],
            "coverage_complete": True,
        }
    chunks: list[dict[str, Any]] = []
    start = 1
    while start <= len(lines):
        end = min(len(lines), start + max_lines - 1)
        role = "start" if start == 1 else "end" if end == len(lines) else "middle"
        chunk_text = "\n".join(lines[start - 1 : end]).encode("utf-8")
        chunks.append(
            {
                "index": len(chunks) + 1,
                "start": start,
                "end": end,
                "role": role,
                "sha256": hashlib.sha256(chunk_text).hexdigest(),
            }
        )
        if end == len(lines):
            break
        start = end - overlap_lines + 1
    complete = bool(chunks) and chunks[0]["start"] == 1 and chunks[-1]["end"] == len(lines)
    complete = complete and all(left["end"] + 1 >= right["start"] for left, right in zip(chunks, chunks[1:]))
    return {
        "path": raw_path.as_posix(),
        "sha256": digest,
        "unit": "lines",
        "total": len(lines),
        "max_lines": max_lines,
        "overlap_lines": overlap_lines,
        "chunks": chunks,
        "coverage_complete": complete,
    }
