"""Read-only checks of declared Novel metadata; no semantic or literary judgments."""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

NOVEL_RUNTIME_VERSION = 1
SCHEMAS = {
    "characters": ("novel_character", "character_id"),
    "locations": ("novel_location", "location_id"),
    "world": ("novel_world_rule", "rule_id"),
    "arcs": ("novel_arc", "arc_id"),
    "chapters": ("novel_chapter", "chapter_id"),
    "scenes": ("novel_scene", "scene_id"),
    "timeline": ("novel_timeline_event", "event_id"),
    "foreshadowing": ("novel_foreshadow", "foreshadow_id"),
    "reviews": ("novel_review", "review_id"),
    "decisions": ("novel_decision", "decision_id"),
}
REFERENCES = {
    "character_refs": "novel_character", "pov_ref": "novel_character",
    "location_refs": "novel_location", "location_ref": "novel_location",
    "rule_refs": "novel_world_rule", "arc_refs": "novel_arc",
    "chapter_ref": "novel_chapter", "target_chapter_ref": "novel_chapter",
    "scene_refs": "novel_scene", "setup_scene_refs": "novel_scene",
    "payoff_scene_refs": "novel_scene", "event_refs": "novel_timeline_event",
    "document_refs": None,
}
SINGLES = {"pov_ref", "location_ref", "chapter_ref", "target_chapter_ref"}
STATES = {
    "novel_arc": {"planned", "drafted", "revised", "completed", "cut"},
    "novel_chapter": {"planned", "drafted", "revised", "published", "cut"},
    "novel_scene": {"planned", "drafted", "revised", "published", "cut"},
    "novel_foreshadow": {"planned", "seeded", "resolved", "dropped"},
    "novel_review": {"open", "resolved", "dismissed"},
    "novel_decision": {"proposed", "accepted", "rejected", "superseded"},
}


def scalar(value: str) -> Any:
    value = value.strip()
    if value.startswith('"') or value in ("true", "false", "null"):
        return json.loads(value)
    if value.startswith("'") and value.endswith("'"):
        return value[1:-1].replace("''", "'")
    if value.startswith("["):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            if not value.endswith("]") or any(mark in value[1:-1] for mark in ('"', "'", "[", "]")):
                raise ValueError("use a JSON array or a block list for complex list values")
            return [scalar(item) for item in value[1:-1].split(",") if item.strip()]
    if re.fullmatch(r"-?\d+", value):
        return int(value)
    if value.startswith(("{", "|", ">")):
        raise ValueError("nested objects and multiline frontmatter values are unsupported")
    return value


def frontmatter(path: Path) -> dict[str, Any]:
    """Accept top-level scalars and scalar lists, rejecting ambiguous metadata."""
    result: dict[str, Any] = {}
    with path.open(encoding="utf-8-sig") as stream:
        if stream.readline().strip() != "---":
            return result
        current: str | None = None
        size = 0
        for line in stream:
            size += len(line)
            if size > 65536:
                raise ValueError("frontmatter exceeds 64 KiB")
            if line.strip() == "---":
                return result
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            if line.startswith("  - "):
                if current is None or not isinstance(result[current], list):
                    raise ValueError("unexpected frontmatter list item")
                result[current].append(scalar(line[4:]))
                continue
            match = re.fullmatch(r"([a-z][a-z0-9_]*):\s*(.*?)\s*", line.rstrip("\n"))
            if not match:
                raise ValueError("expected top-level key: value or a two-space block list")
            key, value = match.groups()
            if key in result:
                raise ValueError(f"duplicate frontmatter key: {key}")
            result[key] = scalar(value) if value else []
            current = key if not value else None
    raise ValueError("frontmatter closing delimiter is missing")


def issue(issues: list[dict[str, Any]], severity: str, code: str, path: str, message: str) -> None:
    issues.append({"severity": severity, "code": code, "path": path, "message": message})


def safe_path(root: Path, value: str, *, prefix: str | None = None) -> Path:
    normalized = value.replace("\\", "/")
    parts = PurePosixPath(normalized).parts
    if not normalized or PurePosixPath(normalized).is_absolute() or PureWindowsPath(value).drive or ".." in parts or ":" in normalized:
        raise ValueError("path must be vault-relative without traversal or drive prefixes")
    relative = PurePosixPath(normalized)
    if prefix and not relative.is_relative_to(PurePosixPath(prefix)):
        raise ValueError(f"path must be inside {prefix}/")
    candidate = root / relative
    for parent in (candidate, *candidate.parents):
        if parent == root:
            break
        if parent.is_symlink():
            raise ValueError("symlink references are unsupported")
    if not candidate.resolve().is_relative_to(root.resolve()):
        raise ValueError("path escapes the vault")
    return candidate


def refs(metadata: dict[str, Any], field: str) -> list[str]:
    value = metadata.get(field)
    if isinstance(value, str):
        return [value] if value else []
    return [item for item in value if isinstance(item, str) and item] if isinstance(value, list) else []


def order(value: Any) -> int:
    return value if type(value) is int and value > 0 else 2**63


def inspect(root: Path) -> dict[str, Any]:
    manifest = json.loads((root / ".llm-wiki.json").read_text(encoding="utf-8"))
    if not isinstance(manifest, dict) or manifest.get("project_mode") != "novel":
        raise ValueError("expected a project_mode: novel vault")
    if type(manifest.get("project_mode_version")) is not int or manifest["project_mode_version"] != 1:
        raise ValueError("unsupported Novel project_mode_version")
    issues: list[dict[str, Any]] = []
    documents: dict[str, dict[str, Any]] = {}
    counts: Counter[str] = Counter()
    for folder, (kind, id_key) in SCHEMAS.items():
        directory = safe_path(root, f"wiki/novel/{folder}")
        if not directory.is_dir():
            issue(issues, "error", "missing_directory", f"wiki/novel/{folder}", "Novel document directory is missing")
            continue
        for path in sorted(directory.rglob("*")):
            relative = path.relative_to(root).as_posix()
            if path.is_symlink():
                issue(issues, "error", "unsafe_path", relative, "symlink documents are unsupported")
                continue
            if not path.is_file() or path.suffix.lower() != ".md":
                continue
            try:
                safe_path(root, relative)
                data = frontmatter(path)
            except (ValueError, OSError) as error:
                issue(issues, "error", "invalid_frontmatter", relative, str(error))
                continue
            if not data:
                issue(issues, "warning", "unstructured_document", relative, "not included in structured Novel checks")
                continue
            if data.get("type") != kind:
                issue(issues, "error", "wrong_document_type", relative, f"expected type: {kind}")
                continue
            identity = data.get(id_key)
            if not isinstance(identity, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]*", identity):
                issue(issues, "error", "invalid_id", relative, f"{id_key} must be a stable alphanumeric ID")
                continue
            if identity in documents:
                issue(issues, "error", "duplicate_id", relative, f"duplicate ID {identity}: {documents[identity]['path']}")
                continue
            documents[identity] = {"id": identity, "type": kind, "path": relative, "metadata": data}
            counts[kind] += 1
            if not isinstance(data.get("title"), str) or not data["title"].strip():
                issue(issues, "warning", "missing_title", relative, "document title is empty")
            if "canon_status" in data and data["canon_status"] not in ("proposed", "accepted", "deprecated"):
                issue(issues, "error", "invalid_canon_status", relative, "canon_status must be proposed, accepted or deprecated")
            if kind in STATES and (not isinstance(data.get("status"), str) or data["status"] not in STATES[kind]):
                issue(issues, "error", "invalid_status", relative, f"expected one of {', '.join(sorted(STATES[kind]))}")
            if folder in ("characters", "locations", "world", "timeline") and "canon_status" not in data:
                issue(issues, "warning", "missing_canon_status", relative, "author acceptance is not recorded")
            for field in REFERENCES:
                if field not in data:
                    continue
                value = data[field]
                valid = (isinstance(value, str) if field in SINGLES else
                         isinstance(value, list) and all(isinstance(item, str) and item for item in value))
                if not valid:
                    issue(issues, "error", "invalid_reference_field", relative, f"{field} has the wrong type")
            if kind in ("novel_chapter", "novel_scene"):
                field = "order" if kind == "novel_chapter" else "sequence"
                if data.get(field) is None:
                    issue(issues, "warning", "missing_order", relative, f"{field} is not assigned")
                elif type(data[field]) is not int or data[field] < 1:
                    issue(issues, "error", "invalid_order", relative, f"{field} must be a positive integer")

    positions: dict[tuple[str, int], str] = {}
    for identity, doc in documents.items():
        data, kind, relative = doc["metadata"], doc["type"], doc["path"]
        for field, expected in REFERENCES.items():
            for reference in refs(data, field):
                other = documents.get(reference)
                if other is None:
                    issue(issues, "error", "missing_reference", relative, f"{field}: {reference} does not exist")
                elif expected and other["type"] != expected:
                    issue(issues, "error", "wrong_reference_type", relative, f"{field}: {reference} must reference {expected}")
        if kind in ("novel_chapter", "novel_scene"):
            number = order(data.get("order" if kind == "novel_chapter" else "sequence"))
            group = "chapters" if kind == "novel_chapter" else str(data.get("chapter_ref", ""))
            if number != 2**63 and (kind == "novel_chapter" or group):
                key = (group, number)
                if key in positions:
                    issue(issues, "error", "duplicate_order", relative, f"same reading position as {positions[key]}")
                positions[key] = identity
        if kind == "novel_chapter":
            scene_refs = refs(data, "scene_refs")
            if len(scene_refs) != len(set(scene_refs)):
                issue(issues, "error", "duplicate_scene", relative, "scene_refs contains duplicates")
            for scene in scene_refs:
                other = documents.get(scene)
                if other and other["type"] == "novel_scene" and other["metadata"].get("chapter_ref") != identity:
                    issue(issues, "error", "chapter_scene_mismatch", relative, f"{scene} belongs to a different or unassigned chapter")
        if kind == "novel_scene":
            chapter = documents.get(data.get("chapter_ref")) if isinstance(data.get("chapter_ref"), str) else None
            if not data.get("chapter_ref"):
                issue(issues, "warning", "unassigned_scene", relative, "scene has no chapter_ref")
            elif chapter and chapter["type"] == "novel_chapter" and identity not in refs(chapter["metadata"], "scene_refs"):
                issue(issues, "warning", "unlisted_scene", relative, "scene is not listed in its chapter")
            manuscript = data.get("manuscript_ref", "")
            if not isinstance(manuscript, str):
                issue(issues, "error", "invalid_manuscript", relative, "manuscript_ref must be a string")
            elif manuscript:
                try:
                    linked = safe_path(root, manuscript, prefix="manuscripts/novel")
                    if not linked.is_file():
                        issue(issues, "error", "missing_manuscript", relative, f"missing manuscript: {manuscript}")
                except ValueError as error:
                    issue(issues, "error", "unsafe_manuscript", relative, str(error))
            elif data.get("status") in ("drafted", "revised", "published"):
                issue(issues, "warning", "unlinked_manuscript", relative, "written scene has no manuscript_ref")
        if kind == "novel_timeline_event":
            start, end = data.get("time_start"), data.get("time_end")
            if any(value is not None and type(value) is not int for value in (start, end)):
                issue(issues, "error", "invalid_time", relative, "time_start/time_end must be integers or null")
            elif start is not None and end is not None and start > end:
                issue(issues, "error", "reversed_time", relative, "time_start is after time_end")
        if kind == "novel_foreshadow":
            setups, payoffs = refs(data, "setup_scene_refs"), refs(data, "payoff_scene_refs")
            state = data.get("status")
            if state in ("seeded", "resolved") and not setups:
                issue(issues, "error", "missing_setup", relative, "seeded/resolved foreshadow needs a setup scene")
            if state == "resolved" and not payoffs:
                issue(issues, "error", "missing_payoff", relative, "resolved foreshadow needs a payoff scene")
            if payoffs and state not in ("resolved", "dropped"):
                issue(issues, "warning", "unreviewed_payoff", relative, "payoff scenes are listed but resolution is not recorded")
            setup_positions = [scene_position(documents.get(ref), documents) for ref in setups]
            payoff_positions = [scene_position(documents.get(ref), documents) for ref in payoffs]
            known_setup = [pos for pos in setup_positions if pos is not None]
            known_payoff = [pos for pos in payoff_positions if pos is not None]
            if known_setup and known_payoff and min(known_payoff) <= min(known_setup):
                issue(issues, "warning", "payoff_before_setup", relative, "payoff appears no later than setup in reading order; review intent")
            target = documents.get(data.get("target_chapter_ref")) if isinstance(data.get("target_chapter_ref"), str) else None
            if target and target["type"] == "novel_chapter" and target["metadata"].get("status") == "published" and state in ("planned", "seeded"):
                issue(issues, "warning", "overdue_foreshadow", relative, "target chapter is published but foreshadow remains unresolved")
    return {"documents": documents, "counts": dict(sorted(counts.items())), "issues": issues,
            "summary": {"errors": sum(x["severity"] == "error" for x in issues),
                        "warnings": sum(x["severity"] == "warning" for x in issues)}}


def scene_position(doc: dict[str, Any] | None, documents: dict[str, Any]) -> tuple[int, int] | None:
    if doc is None or doc["type"] != "novel_scene":
        return None
    data = doc["metadata"]
    chapter = documents.get(data.get("chapter_ref")) if isinstance(data.get("chapter_ref"), str) else None
    if chapter is None or chapter["type"] != "novel_chapter":
        return None
    position = (order(chapter["metadata"].get("order")), order(data.get("sequence")))
    return None if 2**63 in position else position


def outline(documents: dict[str, Any]) -> list[dict[str, Any]]:
    chapters = [doc for doc in documents.values() if doc["type"] == "novel_chapter"]
    result = []
    for chapter in sorted(chapters, key=lambda doc: (order(doc["metadata"].get("order")), doc["id"])):
        scenes = [doc for doc in documents.values() if doc["type"] == "novel_scene"
                  and doc["metadata"].get("chapter_ref") == chapter["id"]]
        result.append({**chapter, "scenes": sorted(scenes, key=lambda doc: (order(doc["metadata"].get("sequence")), doc["id"]))})
    return result


def trace(documents: dict[str, Any], identity: str) -> dict[str, Any]:
    if identity not in documents:
        raise ValueError(f"unknown Novel ID: {identity}")
    incoming = [{"id": doc["id"], "path": doc["path"], "field": field}
                for doc in documents.values() for field in REFERENCES if identity in refs(doc["metadata"], field)]
    outgoing = [{"id": ref, "field": field, "path": documents[ref]["path"] if ref in documents else None}
                for field in REFERENCES for ref in refs(documents[identity]["metadata"], field)]
    return {"document": documents[identity], "incoming": incoming, "outgoing": outgoing}


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("status", "check", "outline"):
        commands.add_parser(name)
    tracing = commands.add_parser("trace")
    tracing.add_argument("id")
    args = parser.parse_args()
    try:
        inspected = inspect(args.root.resolve())
        result = {key: inspected[key] for key in ("counts", "summary", "issues")}
        result.update(ok=not inspected["summary"]["errors"] if args.command == "check" else True,
                      has_errors=bool(inspected["summary"]["errors"]), read_only=True,
                      semantic_review="not_performed", runtime_version=NOVEL_RUNTIME_VERSION)
        if args.command == "outline":
            result["chapters"] = outline(inspected["documents"])
        elif args.command == "trace":
            result.update(trace(inspected["documents"], args.id))
    except (OSError, ValueError) as error:
        result = {"ok": False, "read_only": True, "error": str(error)}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
