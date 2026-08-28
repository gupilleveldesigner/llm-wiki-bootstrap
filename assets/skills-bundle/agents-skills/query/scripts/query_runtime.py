#!/usr/bin/env python3
"""Schema-neutral helpers for frontmatter-first LLM Wiki queries."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


class QueryRuntimeError(RuntimeError):
    """Raised for invalid Wiki roots, paths, or frontmatter."""


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

    raise QueryRuntimeError(f"No LLM Wiki root containing wiki/ was found from: {candidate}")


def status_payload(root: Path) -> dict[str, Any]:
    instruction_candidates = (
        root / "AGENTS.md",
        root / "CLAUDE.md",
        root / "raw" / "AGENTS.md",
        root / "raw" / "CLAUDE.md",
        root / "wiki" / "AGENTS.md",
        root / "wiki" / "CLAUDE.md",
    )
    instructions = [
        path.relative_to(root).as_posix()
        for path in instruction_candidates
        if path.is_file()
    ]

    index = root / "wiki" / "index.md"
    graph = root / "graphify-out" / "graph.json"
    raw = root / "raw"
    return {
        "root": str(root),
        "raw": str(raw) if raw.is_dir() else None,
        "wiki": str(root / "wiki"),
        "catalog": str(index) if index.is_file() else None,
        "instructions": instructions,
        "graph": str(graph) if graph.is_file() else None,
    }


def resolve_wiki_document(root: Path, value: str) -> Path:
    supplied = Path(value).expanduser()
    if supplied.is_absolute():
        candidates = [supplied]
    elif supplied.parts and supplied.parts[0].lower() == "wiki":
        candidates = [root / supplied]
    else:
        candidates = [root / supplied, root / "wiki" / supplied]

    expanded: list[Path] = []
    for candidate in candidates:
        expanded.append(candidate)
        if candidate.suffix.lower() != ".md":
            expanded.append(candidate.with_name(candidate.name + ".md"))

    existing = next((path.resolve() for path in expanded if path.is_file()), None)
    if existing is None:
        raise QueryRuntimeError(f"Wiki Markdown file not found: {value}")

    wiki_root = (root / "wiki").resolve()
    if not existing.is_relative_to(wiki_root):
        raise QueryRuntimeError(f"Only Markdown files inside wiki/ may be inspected: {value}")
    if existing.suffix.lower() != ".md":
        raise QueryRuntimeError(f"Only Markdown files are supported: {value}")
    return existing


def extract_frontmatter(path: Path) -> str | None:
    with path.open("r", encoding="utf-8-sig") as handle:
        first = handle.readline()
        while first and not first.strip():
            first = handle.readline()

        if first.strip() != "---":
            return None

        lines = ["---"]
        for line in handle:
            stripped = line.rstrip("\r\n")
            lines.append(stripped)
            if stripped.strip() == "---":
                return "\n".join(lines)

    raise QueryRuntimeError(f"Unterminated YAML frontmatter: {path}")


def frontmatter_field(frontmatter: str | None, key: str) -> str:
    if frontmatter is None:
        return ""
    prefix = f"{key}:"
    for line in frontmatter.splitlines():
        if line.startswith(prefix):
            return line[len(prefix) :].strip().strip("\"'")
    return ""


def semantic_metadata(frontmatter: str | None) -> dict[str, Any]:
    document_type = (
        frontmatter_field(frontmatter, "type")
        or frontmatter_field(frontmatter, "kind")
    ).casefold()
    if document_type != "source":
        return {}
    declared = frontmatter_field(frontmatter, "semantic_status").casefold()
    if declared in {"pending", "partial", "reviewed"}:
        effective = declared
    else:
        status = frontmatter_field(frontmatter, "status").casefold()
        effective = "pending" if status in {"pending", "unverified"} else "partial"
    result: dict[str, Any] = {"semantic_status": effective}
    if effective != "reviewed":
        result["semantic_warning"] = (
            f"Source semantic_status is {effective}; structural presence is not semantic completion."
        )
    return result


def frontmatter_payload(root: Path, values: list[str]) -> tuple[list[dict[str, Any]], bool]:
    items: list[dict[str, Any]] = []
    failed = False

    for value in values:
        try:
            path = resolve_wiki_document(root, value)
            frontmatter = extract_frontmatter(path)
            items.append(
                {
                    "path": path.relative_to(root).as_posix(),
                    "has_frontmatter": frontmatter is not None,
                    "frontmatter": frontmatter,
                    **semantic_metadata(frontmatter),
                }
            )
        except QueryRuntimeError as exc:
            failed = True
            items.append(
                {
                    "path": value,
                    "has_frontmatter": False,
                    "frontmatter": None,
                    "error": str(exc),
                }
            )

    return items, failed


def render_frontmatter(items: list[dict[str, Any]]) -> str:
    sections: list[str] = []
    for item in items:
        sections.append(f"===== {item['path']} =====")
        if "error" in item:
            sections.append(f"ERROR: {item['error']}")
        elif not item["has_frontmatter"]:
            sections.append("NO_FRONTMATTER")
        else:
            if "semantic_status" in item:
                sections.append(f"SEMANTIC_STATUS: {item['semantic_status']}")
            if "semantic_warning" in item:
                sections.append(f"WARNING: {item['semantic_warning']}")
            sections.append(str(item["frontmatter"]))
    return "\n".join(sections)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Discover an LLM Wiki and read candidate frontmatter without emitting bodies."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    status_parser = subparsers.add_parser("status", help="Show the resolved Wiki root.")
    status_parser.add_argument("--root", default=".")

    frontmatter_parser = subparsers.add_parser(
        "frontmatter", help="Emit only YAML frontmatter for candidate Wiki documents."
    )
    frontmatter_parser.add_argument("--root", default=".")
    frontmatter_parser.add_argument("--file", action="append", required=True)
    frontmatter_parser.add_argument("--json", action="store_true")

    return parser


def main(argv: list[str] | None = None) -> int:
    configure_utf8_output()
    args = build_parser().parse_args(argv)
    try:
        root = find_wiki_root(args.root)
        if args.command == "status":
            print(json.dumps(status_payload(root), ensure_ascii=False, indent=2))
            return 0

        items, failed = frontmatter_payload(root, args.file)
        if args.json:
            print(
                json.dumps(
                    {"root": str(root), "documents": items},
                    ensure_ascii=False,
                    indent=2,
                )
            )
        else:
            print(render_frontmatter(items))
        return 1 if failed else 0
    except QueryRuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
