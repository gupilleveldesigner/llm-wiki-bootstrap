#!/usr/bin/env python3
"""Read-only, schema-neutral structural audit for Markdown LLM Wikis."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from typing import Any


WIKILINK_RE = re.compile(r"\[\[([^\]|#]+)(?:#[^\]|]+)?(?:\|[^\]]+)?\]\]")
FIELD_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_-]*):", re.MULTILINE)
DATE_RE = re.compile(
    r"^(?:updated|date|last_updated):\s*[\"']?(\d{4}-\d{2}-\d{2})",
    re.MULTILINE,
)
OPERATION_FILES = {
    "AGENTS.md",
    "CLAUDE.md",
    "index.md",
    "log.md",
    "overview.md",
    "questions.md",
}
GENERATED_DIRS = {".git", "graphify-out", "__pycache__"}


class AuditError(RuntimeError):
    """Raised when the target is not a readable LLM Wiki."""


def configure_utf8_output() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8")


def find_wiki_root(start: str | Path) -> Path:
    candidate = Path(start).expanduser().resolve()
    if candidate.is_file():
        candidate = candidate.parent

    wiki_only: Path | None = None
    for directory in (candidate, *candidate.parents):
        if (directory / "raw").is_dir() and (directory / "wiki").is_dir():
            return directory
        if wiki_only is None and (directory / "wiki").is_dir():
            wiki_only = directory

    if wiki_only is not None:
        return wiki_only
    raise AuditError(f"No LLM Wiki root containing wiki/ was found from: {candidate}")


def get_frontmatter(text: str) -> str | None:
    lines = text.splitlines()
    position = 0
    while position < len(lines) and not lines[position].strip():
        position += 1
    if position >= len(lines) or lines[position].strip() != "---":
        return None

    start = position + 1
    for position in range(start, len(lines)):
        if lines[position].strip() == "---":
            return "\n".join(lines[start:position])
    return None


def note_files(root: Path) -> list[Path]:
    wiki = root / "wiki"
    return sorted(
        path
        for path in wiki.rglob("*.md")
        if not any(
            part in GENERATED_DIRS for part in path.relative_to(wiki).parts
        )
    )


def is_knowledge_document(path: Path) -> bool:
    return path.name not in OPERATION_FILES


def detect_managed_dirs(root: Path) -> list[str]:
    wiki = root / "wiki"
    return sorted(
        path.name
        for path in wiki.iterdir()
        if path.is_dir() and path.name not in GENERATED_DIRS
    )


def status_payload(root: Path) -> dict[str, Any]:
    instructions = []
    for path in (
        root / "AGENTS.md",
        root / "CLAUDE.md",
        root / "raw" / "AGENTS.md",
        root / "raw" / "CLAUDE.md",
        root / "wiki" / "AGENTS.md",
        root / "wiki" / "CLAUDE.md",
    ):
        if path.is_file():
            instructions.append(path.relative_to(root).as_posix())

    raw = root / "raw"
    index = root / "wiki" / "index.md"
    return {
        "root": str(root),
        "wiki": str(root / "wiki"),
        "raw": str(raw) if raw.is_dir() else None,
        "catalog": str(index) if index.is_file() else None,
        "instructions": instructions,
        "suggested_managed_dirs": detect_managed_dirs(root),
    }


def build_lookup(root: Path) -> tuple[dict[str, Path], dict[str, list[Path]]]:
    exact: dict[str, Path] = {}
    by_stem: dict[str, list[Path]] = defaultdict(list)
    for path in root.rglob("*.md"):
        if any(part in GENERATED_DIRS for part in path.relative_to(root).parts):
            continue
        relative = path.relative_to(root).as_posix()
        exact[relative.casefold()] = path
        exact[relative.removesuffix(".md").casefold()] = path
        by_stem[path.stem.casefold()].append(path)
    return exact, by_stem


def resolve_link(
    root: Path,
    source: Path,
    target: str,
    exact: dict[str, Path],
    by_stem: dict[str, list[Path]],
) -> Path | None:
    normalized = target.strip().strip("\"'").replace("\\", "/")
    if not normalized or "://" in normalized:
        return None

    candidates: list[Path] = []
    if normalized.startswith("/"):
        candidates.append(root / normalized.lstrip("/"))
    else:
        candidates.extend(
            (source.parent / normalized, root / normalized, root / "wiki" / normalized)
        )

    for candidate in candidates:
        if candidate.suffix.casefold() != ".md":
            candidate = candidate.with_name(candidate.name + ".md")
        try:
            resolved = candidate.resolve()
            resolved.relative_to(root.resolve())
        except (OSError, ValueError):
            continue
        if resolved.is_file():
            return resolved

    key = normalized.removesuffix(".md").casefold()
    if key in exact:
        return exact[key]
    matches = by_stem.get(Path(normalized).stem.casefold(), [])
    return matches[0] if len(matches) == 1 else None


def audit(
    root: Path,
    *,
    required_fields: tuple[str, ...] = (),
    managed_dirs: tuple[str, ...] = (),
) -> dict[str, Any]:
    files = note_files(root)
    knowledge_files = [path for path in files if is_knowledge_document(path)]
    exact, by_stem = build_lookup(root)
    selected_dirs = tuple(managed_dirs) or tuple(detect_managed_dirs(root))

    missing_frontmatter: list[str] = []
    missing_fields: list[dict[str, Any]] = []
    broken_links: list[dict[str, str]] = []
    missing_sources: list[dict[str, str]] = []
    stale_sources: list[dict[str, Any]] = []
    incoming: Counter[Path] = Counter()
    observed_fields: Counter[str] = Counter()

    index = root / "wiki" / "index.md"
    indexed: set[Path] = set()

    for source in files:
        text = source.read_text(encoding="utf-8-sig")
        frontmatter = get_frontmatter(text)
        fields = set(FIELD_RE.findall(frontmatter or ""))

        if source in knowledge_files:
            if frontmatter is None:
                missing_frontmatter.append(source.relative_to(root).as_posix())
            else:
                observed_fields.update(fields)
                missing = [field for field in required_fields if field not in fields]
                if missing:
                    missing_fields.append(
                        {
                            "path": source.relative_to(root).as_posix(),
                            "fields": missing,
                        }
                    )

        for target in WIKILINK_RE.findall(text):
            resolved = resolve_link(root, source, target, exact, by_stem)
            if resolved is None:
                broken_links.append(
                    {"path": source.relative_to(root).as_posix(), "target": target}
                )
                continue
            if resolved in files:
                incoming[resolved] += 1
            if source == index:
                indexed.add(resolved)

        if source not in knowledge_files or frontmatter is None:
            continue

        updated_match = DATE_RE.search(frontmatter)
        updated = (
            date.fromisoformat(updated_match.group(1)) if updated_match else None
        )
        for target in WIKILINK_RE.findall(frontmatter):
            if not target.replace("\\", "/").casefold().startswith("raw/"):
                continue
            resolved = resolve_link(root, source, target, exact, by_stem)
            if resolved is None:
                missing_sources.append(
                    {"path": source.relative_to(root).as_posix(), "target": target}
                )
            elif resolved.stat().st_mtime > source.stat().st_mtime + 1:
                stale_sources.append(
                    {
                        "path": source.relative_to(root).as_posix(),
                        "source": resolved.relative_to(root).as_posix(),
                        "updated": updated.isoformat() if updated else None,
                        "note_modified": date.fromtimestamp(
                            source.stat().st_mtime
                        ).isoformat(),
                        "source_modified": date.fromtimestamp(
                            resolved.stat().st_mtime
                        ).isoformat(),
                    }
                )

    managed_set = set(selected_dirs)
    unindexed = []
    for path in knowledge_files:
        relative_to_wiki = path.relative_to(root / "wiki")
        if (
            len(relative_to_wiki.parts) > 1
            and relative_to_wiki.parts[0] in managed_set
            and path not in indexed
        ):
            unindexed.append(path.relative_to(root).as_posix())

    orphans = [
        path.relative_to(root).as_posix()
        for path in knowledge_files
        if incoming[path] == 0
    ]
    by_semantic_stem: dict[str, list[Path]] = defaultdict(list)
    for path in knowledge_files:
        by_semantic_stem[path.stem.casefold()].append(path)
    duplicate_stems = {
        stem: [path.relative_to(root).as_posix() for path in paths]
        for stem, paths in by_semantic_stem.items()
        if len(paths) > 1
    }

    warnings = []
    if not required_fields:
        warnings.append(
            "No required fields supplied; missing_fields detection was disabled."
        )
    if not index.is_file():
        warnings.append("wiki/index.md is missing; index coverage may be incomplete.")

    return {
        "documents": len(files),
        "knowledge_documents": len(knowledge_files),
        "schema": {
            "required_fields": list(required_fields),
            "observed_field_counts": dict(sorted(observed_fields.items())),
            "managed_dirs": list(selected_dirs),
        },
        "missing_frontmatter": missing_frontmatter,
        "missing_fields": missing_fields,
        "broken_links": broken_links,
        "missing_source_targets": missing_sources,
        "stale_source_candidates": stale_sources,
        "unindexed": sorted(unindexed),
        "orphans": sorted(orphans),
        "duplicate_stems": duplicate_stems,
        "warnings": warnings,
    }


def render_summary(result: dict[str, Any]) -> str:
    lines = [
        f"documents: {result['documents']}",
        f"knowledge_documents: {result['knowledge_documents']}",
    ]
    for key in (
        "missing_frontmatter",
        "missing_fields",
        "broken_links",
        "missing_source_targets",
        "stale_source_candidates",
        "unindexed",
        "orphans",
        "duplicate_stems",
        "warnings",
    ):
        value = result[key]
        lines.append(f"{key}: {len(value)}")
        if isinstance(value, dict):
            for name, items in value.items():
                lines.append(f"  - {name}: {', '.join(items)}")
        else:
            for item in value:
                rendered = (
                    json.dumps(item, ensure_ascii=False)
                    if isinstance(item, dict)
                    else str(item)
                )
                lines.append(f"  - {rendered}")
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Audit a Markdown LLM Wiki without modifying it."
    )
    parser.add_argument("--root", default=".", help="Wiki root or nested path.")
    parser.add_argument("--status", action="store_true", help="Show target discovery.")
    parser.add_argument("--json", action="store_true", help="Emit JSON.")
    parser.add_argument("--required-field", action="append", default=[])
    parser.add_argument("--managed-dir", action="append", default=[])
    return parser


def main(argv: list[str] | None = None) -> int:
    configure_utf8_output()
    args = build_parser().parse_args(argv)
    try:
        root = find_wiki_root(args.root)
        if args.status:
            print(json.dumps(status_payload(root), ensure_ascii=False, indent=2))
            return 0
        result = audit(
            root,
            required_fields=tuple(dict.fromkeys(args.required_field)),
            managed_dirs=tuple(dict.fromkeys(args.managed_dir)),
        )
        print(
            json.dumps(result, ensure_ascii=False, indent=2)
            if args.json
            else render_summary(result)
        )
        return 0
    except AuditError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
