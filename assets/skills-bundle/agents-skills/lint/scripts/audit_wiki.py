#!/usr/bin/env python3
"""Read-only, schema-neutral structural audit for Markdown LLM Wikis."""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from typing import Any


WIKILINK_RE = re.compile(r"\[\[([^\]|#]+)(?:#[^\]|]+)?(?:\|[^\]]+)?\]\]")
PLAIN_RAW_PATH_RE = re.compile(
    r"(raw/[^\r\n\[\]\"']+?\.(?:md|markdown|txt|pdf|csv|json|ya?ml|png|jpe?g|gif|webp|svg|avif|py|ps1|js|jsx|ts|tsx|html|xml|toml|ini|sh|sql|css))",
    re.IGNORECASE,
)
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


def frontmatter_field(frontmatter: str | None, key: str) -> str:
    match = re.search(rf"(?m)^{re.escape(key)}:\s*(.*)$", frontmatter or "")
    return match.group(1).strip().strip("\"'") if match else ""


def section_text(text: str, heading: str) -> str:
    match = re.search(
        rf"(?ms)^##\s+{re.escape(heading)}\s*$\n(.*?)(?=^##\s+|\Z)",
        text,
    )
    return match.group(1).strip() if match else ""


def effective_semantic_status(frontmatter: str | None) -> str:
    declared = frontmatter_field(frontmatter, "semantic_status").casefold()
    if declared in {"pending", "partial", "reviewed"}:
        return declared
    return "pending" if frontmatter_field(frontmatter, "status").casefold() in {"pending", "unverified"} else "partial"


def load_semantic_contract() -> Any | None:
    path = Path(__file__).resolve().parents[2] / "ingest" / "scripts" / "semantic_contract.py"
    if not path.is_file():
        return None
    spec = importlib.util.spec_from_file_location("llm_wiki_ingest_semantic_contract", path)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def validated_semantic_status(
    contract: Any | None,
    root: Path,
    source: Path,
    text: str,
    frontmatter: str,
    raw_targets: list[str],
) -> tuple[str, list[str]]:
    declared = effective_semantic_status(frontmatter)
    if declared != "reviewed" or contract is None:
        return declared, []
    if len(raw_targets) != 1:
        return "partial", ["semantic reviewed Source must cite exactly one Raw target"]
    raw_path = (root / raw_targets[0]).resolve()
    try:
        raw_path.relative_to((root / "raw").resolve())
    except ValueError:
        return "partial", ["semantic reviewed Source Raw target escapes raw/"]
    if not raw_path.is_file():
        return "partial", ["semantic reviewed Source Raw target is missing"]
    review = contract.review_source_record(root, source, raw_path, text)
    return str(review["semantic_status"]), [str(error) for error in review["errors"]]


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
        variants = [candidate]
        if candidate.suffix.casefold() != ".md":
            variants.append(candidate.with_name(candidate.name + ".md"))
        for variant in variants:
            try:
                resolved = variant.resolve()
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
    semantic_source_status: Counter[str] = Counter()
    semantic_incomplete_sources: list[dict[str, str]] = []
    semantic_contract_failures: list[dict[str, Any]] = []
    source_signatures: dict[str, list[str]] = defaultdict(list)
    reverse_provenance_missing: list[dict[str, str]] = []

    index = root / "wiki" / "index.md"
    indexed: set[Path] = set()
    semantic_contract = load_semantic_contract()

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

        is_source_record = (
            (root / "wiki" / "sources") in source.parents
            and frontmatter_field(frontmatter, "type").casefold() == "source"
        )
        if is_source_record:
            relative_source = source.relative_to(root).as_posix()
            raw_targets = list(
                dict.fromkeys(
                    target.strip().replace("\\", "/").removeprefix("./")
                    for target in WIKILINK_RE.findall(frontmatter) + PLAIN_RAW_PATH_RE.findall(frontmatter)
                    if target.strip().replace("\\", "/").removeprefix("./").casefold().startswith("raw/")
                )
            )
            semantic_status, contract_errors = validated_semantic_status(
                semantic_contract, root, source, text, frontmatter, raw_targets
            )
            semantic_source_status[semantic_status] += 1
            if semantic_status != "reviewed":
                semantic_incomplete_sources.append(
                    {"path": relative_source, "semantic_status": semantic_status}
                )
            if contract_errors:
                semantic_contract_failures.append(
                    {"path": relative_source, "errors": contract_errors}
                )

            summary = section_text(text, "핵심 내용") or section_text(text, "핵심 주장")
            signature = " ".join(summary.split()).casefold()
            if signature:
                source_signatures[signature].append(relative_source)

            source_id = frontmatter_field(frontmatter, "id").casefold()
            reflected = section_text(text, "Wiki에 반영된 문서") or section_text(text, "반영 문서")
            for target in WIKILINK_RE.findall(reflected):
                resolved = resolve_link(root, source, target, exact, by_stem)
                if resolved is None:
                    continue
                target_front = (get_frontmatter(resolved.read_text(encoding="utf-8-sig")) or "").replace("\\", "/").casefold()
                has_raw = any(raw_target.casefold() in target_front for raw_target in raw_targets)
                if not has_raw and (not source_id or source_id not in target_front):
                    reverse_provenance_missing.append(
                        {
                            "source": relative_source,
                            "target": resolved.relative_to(root).as_posix(),
                        }
                    )

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
    repeated_source_summaries = [
        {
            "count": len(paths),
            "examples": paths[:5],
            "signature_preview": signature[:160],
        }
        for signature, paths in source_signatures.items()
        if len(paths) >= 3
    ]
    repeated_source_summaries.sort(key=lambda item: (-int(item["count"]), str(item["signature_preview"])))
    reverse_provenance_sources = sorted({item["source"] for item in reverse_provenance_missing})

    warnings = []
    if not required_fields:
        warnings.append(
            "No required fields supplied; missing_fields detection was disabled."
        )
    if not index.is_file():
        warnings.append("wiki/index.md is missing; index coverage may be incomplete.")
    if semantic_incomplete_sources:
        warnings.append(
            f"{len(semantic_incomplete_sources)} Source records are semantic pending/partial; queries must disclose this."
        )
    if semantic_contract_failures:
        warnings.append(
            f"{len(semantic_contract_failures)} Source records declare reviewed but fail the ingest semantic contract."
        )
    if semantic_contract is None and semantic_source_status.get("reviewed", 0):
        warnings.append("Ingest semantic contract validator is unavailable; lint used declared Source status only.")
    if repeated_source_summaries:
        warnings.append("Repeated Source summary boilerplate is a systemic semantic-coverage risk.")
    if reverse_provenance_missing:
        warnings.append(
            f"{len(reverse_provenance_missing)} reflected Source→Wiki links lack reverse Source/Raw provenance."
        )

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
        "semantic_source_status": dict(sorted(semantic_source_status.items())),
        "semantic_incomplete_sources": sorted(semantic_incomplete_sources, key=lambda item: item["path"]),
        "semantic_contract_failures": sorted(semantic_contract_failures, key=lambda item: item["path"]),
        "repeated_source_summaries": repeated_source_summaries,
        "missing_reverse_provenance": sorted(
            reverse_provenance_missing,
            key=lambda item: (item["source"], item["target"]),
        ),
        "missing_reverse_provenance_sources": reverse_provenance_sources,
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
        "semantic_incomplete_sources",
        "semantic_contract_failures",
        "repeated_source_summaries",
        "missing_reverse_provenance",
        "missing_reverse_provenance_sources",
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
    lines.append(
        "semantic_source_status: "
        + json.dumps(result["semantic_source_status"], ensure_ascii=False, sort_keys=True)
    )
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
