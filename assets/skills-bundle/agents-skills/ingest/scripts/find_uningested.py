#!/usr/bin/env python3
"""Read-only detector for raw files not represented by wiki/sources frontmatter."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote


WIKILINK_RE = re.compile(r"\[\[([^\]|#]+)(?:#[^\]|]+)?(?:\|[^\]]+)?\]\]")
PLAIN_RAW_PATH_RE = re.compile(
    r"(raw/[^\r\n\[\]\"']+?\.(?:md|markdown|txt|pdf|csv|json|ya?ml|png|jpe?g|gif|webp|svg|avif))",
    re.IGNORECASE,
)
EMBED_RE = re.compile(r"!\[\[([^\]|#]+)(?:#[^\]|]+)?(?:\|[^\]]+)?\]\]")
MD_IMAGE_RE = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")
TEXT_SUFFIXES = {".md", ".txt", ".markdown", ".csv", ".json", ".yaml", ".yml"}
ATTACHMENT_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".bmp", ".avif"}
HOST_INSTRUCTION_FILES = {"agents.md", "claude.md", "gemini.md"}


def configure_utf8_stdout() -> None:
    """Keep JSON/text output lossless on Windows consoles configured for CP949."""
    reconfigure = getattr(sys.stdout, "reconfigure", None)
    if callable(reconfigure):
        reconfigure(encoding="utf-8")


def is_wiki_root(candidate: Path) -> bool:
    return (candidate / "raw").is_dir() and (candidate / "wiki").is_dir()


def primary_git_worktree(start: Path) -> Path | None:
    """Return the primary checkout for start's Git repository, if available."""
    try:
        completed = subprocess.run(
            ["git", "-C", str(start), "worktree", "list", "--porcelain", "-z"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if completed.returncode != 0:
        return None

    for field in completed.stdout.split(b"\0"):
        if not field.startswith(b"worktree "):
            continue
        try:
            return Path(field[len(b"worktree ") :].decode("utf-8", errors="surrogateescape")).resolve()
        except (OSError, ValueError):
            return None
    return None


def resolve_wiki_root(value: str | Path | None = None, *, start: Path | None = None) -> Path:
    """Resolve an explicit root or the invoking project's LLM Wiki root."""
    if value is not None:
        candidate = Path(value).expanduser().resolve()
        if not is_wiki_root(candidate):
            raise ValueError(f"Not an LLM Wiki root (raw/ and wiki/ are required): {candidate}")
        return candidate

    current = (start or Path.cwd()).resolve()
    for candidate in (current, *current.parents):
        if is_wiki_root(candidate):
            return candidate

    primary = primary_git_worktree(current)
    if primary is not None and is_wiki_root(primary):
        return primary

    raise ValueError(
        "Could not find an LLM Wiki root in the invoking project "
        f"or its primary Git worktree from: {current}"
    )


def frontmatter(text: str) -> str:
    if not text.startswith("---"):
        return ""
    parts = text.split("---", 2)
    return parts[1] if len(parts) == 3 else ""


def normalized(value: str) -> str:
    return value.strip().strip('"\'').replace("\\", "/").removeprefix("./").casefold()


def keys(value: str) -> set[str]:
    value = normalized(value)
    result = {value}
    if value.endswith(".md"):
        result.add(value[:-3])
    return result


def is_blank(path: Path) -> bool:
    if path.stat().st_size == 0:
        return True
    if path.suffix.casefold() not in TEXT_SUFFIXES:
        return False
    try:
        return not path.read_text(encoding="utf-8-sig").strip()
    except UnicodeDecodeError:
        return False


def resolve_embeds(raw_root: Path, ingested_notes: list[Path], raw_files: list[Path]) -> set[str]:
    by_name: dict[str, list[Path]] = {}
    for path in raw_files:
        by_name.setdefault(path.name.casefold(), []).append(path)

    embedded: set[str] = set()
    for note in ingested_notes:
        if note.suffix.casefold() != ".md":
            continue
        try:
            text = note.read_text(encoding="utf-8-sig")
        except (OSError, UnicodeDecodeError):
            continue
        targets = EMBED_RE.findall(text) + MD_IMAGE_RE.findall(text)
        for target in targets:
            target = unquote(target.strip().strip("<>"))
            candidates = [note.parent / target, raw_root / target, raw_root / "assets" / Path(target).name]
            candidates.extend(by_name.get(Path(target).name.casefold(), []))
            for candidate in candidates:
                try:
                    candidate = candidate.resolve()
                    candidate.relative_to(raw_root.resolve())
                except (OSError, ValueError):
                    continue
                if candidate.is_file() and candidate.suffix.casefold() in ATTACHMENT_SUFFIXES:
                    rel = candidate.relative_to(raw_root.parent).as_posix()
                    embedded.update(keys(rel))
                    break
    return embedded


def scan(root: Path) -> dict[str, list[dict[str, object]]]:
    root = resolve_wiki_root(root)
    raw_root = root / "raw"
    wiki_root = root / "wiki"
    sources_root = root / "wiki" / "sources"
    raw_files = sorted((p for p in raw_root.rglob("*") if p.is_file()), key=lambda p: p.as_posix())

    referenced: set[str] = set()
    source_pages = list(sources_root.glob("*.md"))
    if source_pages:
        reference_pages = [(source, True) for source in source_pages]
    else:
        reference_pages = [
            (page, False)
            for page in wiki_root.rglob("*.md")
            if "graphify-out" not in {part.casefold() for part in page.relative_to(wiki_root).parts}
        ]
    for source, frontmatter_only in reference_pages:
        text = source.read_text(encoding="utf-8-sig")
        scope = frontmatter(text) if frontmatter_only else text
        targets = WIKILINK_RE.findall(scope) + PLAIN_RAW_PATH_RE.findall(scope)
        for target in targets:
            if normalized(target).startswith("raw/"):
                referenced.update(keys(target))

    ingested_notes = []
    for path in raw_files:
        rel = path.relative_to(root).as_posix()
        if keys(rel) & referenced:
            ingested_notes.append(path)
    embedded = resolve_embeds(raw_root, ingested_notes, raw_files)

    result: dict[str, list[dict[str, object]]] = {"pending": [], "ingested": [], "skipped": []}
    for path in raw_files:
        rel = path.relative_to(root).as_posix()
        item: dict[str, object] = {
            "path": rel,
            "modified": datetime.fromtimestamp(path.stat().st_mtime).astimezone().isoformat(timespec="seconds"),
            "size": path.stat().st_size,
        }
        path_keys = keys(rel)
        if path.parent == raw_root and path.name.casefold() in HOST_INSTRUCTION_FILES:
            item["reason"] = "folder instructions"
            result["skipped"].append(item)
        elif is_blank(path):
            item["reason"] = "empty file"
            result["skipped"].append(item)
        elif path_keys & referenced:
            item["reason"] = "represented by wiki/sources frontmatter"
            result["ingested"].append(item)
        elif path_keys & embedded:
            item["reason"] = "embedded attachment in an ingested raw note"
            result["skipped"].append(item)
        else:
            result["pending"].append(item)

    for group in result.values():
        group.sort(key=lambda item: str(item["modified"]), reverse=True)
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--root",
        default=None,
        help=(
            "LLM Wiki root. If omitted, use the invoking project; linked Git worktrees "
            "fall back to their primary checkout."
        ),
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON")
    args = parser.parse_args()
    configure_utf8_stdout()
    try:
        root = resolve_wiki_root(args.root)
    except ValueError as error:
        parser.error(str(error))
    result = scan(root)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    for name in ("pending", "ingested", "skipped"):
        print(f"{name}: {len(result[name])}")
        for item in result[name]:
            reason = f" - {item['reason']}" if "reason" in item else ""
            print(f"  - {item['path']} ({item['modified']}){reason}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
