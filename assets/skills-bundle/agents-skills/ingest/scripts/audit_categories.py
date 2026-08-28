#!/usr/bin/env python3
"""Read-only controlled-vocabulary and document-category audit."""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path
from typing import Any

SCRIPT_ROOT = Path(__file__).resolve().parent
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

from find_uningested import OPERATIONAL_WIKI_FILES, resolve_wiki_root  # noqa: E402


TOP_LEVEL_KEY_RE = re.compile(r"^[A-Za-z0-9_-]+:\s*", re.MULTILINE)


def normalize(value: str) -> str:
    return re.sub(r"[\s_-]+", " ", value.strip()).casefold()


def read_frontmatter(text: str) -> str:
    if not text.startswith("---"):
        return ""
    parts = text.split("---", 2)
    return parts[1] if len(parts) == 3 else ""


def frontmatter_labels(frontmatter: str) -> list[str]:
    # Keep whitespace matching on the key's physical line. ``\s`` also
    # consumes newlines, which made the first block-list item (``- label``)
    # look like an inline value including its YAML dash.
    match = re.search(r"(?m)^(topics|tags):[ \t]*(.*)$", frontmatter)
    if not match:
        return []
    first = match.group(2).strip()
    values: list[str] = []
    if first.startswith("[") and first.endswith("]"):
        try:
            parsed = ast.literal_eval(first)
            if isinstance(parsed, (list, tuple)):
                values.extend(str(value) for value in parsed)
        except (ValueError, SyntaxError):
            values.extend(part.strip(" \"'") for part in first[1:-1].split(",") if part.strip())
    elif first:
        values.append(first.strip(" \"'"))
    remainder = frontmatter[match.end() :]
    for line in remainder.splitlines():
        if line and not line[0].isspace() and TOP_LEVEL_KEY_RE.match(line):
            break
        list_item = re.match(r"^\s*-\s+(.+?)\s*$", line)
        if list_item:
            values.append(list_item.group(1).strip(" \"'"))
    return [value for value in values if value]


def taxonomy_concepts(root: Path) -> tuple[dict[str, dict[str, Any]], list[str]]:
    path = root / "wiki" / "taxonomy.json"
    if not path.is_file():
        return {}, ["wiki/taxonomy.json is missing"]
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as error:
        return {}, [f"wiki/taxonomy.json is invalid JSON: {error}"]
    concepts = payload.get("concepts") if isinstance(payload, dict) else None
    if not isinstance(concepts, list) or not concepts:
        return {}, ["wiki/taxonomy.json must contain a non-empty concepts list"]
    result: dict[str, dict[str, Any]] = {}
    errors: list[str] = []
    labels: dict[str, str] = {}
    for concept in concepts:
        if not isinstance(concept, dict):
            errors.append("taxonomy concepts must be objects")
            continue
        concept_id_value = concept.get("id")
        preferred_value = concept.get("prefLabel")
        concept_id = concept_id_value.strip() if isinstance(concept_id_value, str) else ""
        preferred = preferred_value.strip() if isinstance(preferred_value, str) else ""
        if not re.fullmatch(r"[a-z0-9][a-z0-9._-]*", concept_id):
            errors.append(f"invalid taxonomy id: {concept_id or '<empty>'}")
            continue
        if concept_id in result:
            errors.append(f"duplicate taxonomy id: {concept_id}")
        if not preferred:
            errors.append(f"taxonomy concept has no prefLabel: {concept_id}")
        alt_labels = concept.get("altLabel", [])
        if not isinstance(alt_labels, list) or any(not isinstance(label, str) or not label.strip() for label in alt_labels):
            errors.append(f"altLabel must be a list of non-empty strings: {concept_id}")
            alt_labels = []
        scope_note = concept.get("scopeNote")
        if not isinstance(scope_note, str) or not scope_note.strip():
            errors.append(f"taxonomy concept has no scopeNote: {concept_id}")
        result[concept_id] = concept
        for label in [preferred, *alt_labels]:
            key = normalize(str(label))
            if not key:
                continue
            previous = labels.get(key)
            if previous and previous != concept_id:
                errors.append(f"ambiguous taxonomy label {label!r}: {previous} vs {concept_id}")
            labels[key] = concept_id
        id_key = normalize(concept_id)
        previous = labels.get(id_key)
        if previous and previous != concept_id:
            errors.append(f"taxonomy id collides with label {concept_id!r}: {previous} vs {concept_id}")
        labels[id_key] = concept_id
    for concept_id, concept in result.items():
        broader = concept.get("broader", [])
        if not isinstance(broader, list):
            errors.append(f"broader must be a list: {concept_id}")
            continue
        for parent in broader:
            if str(parent) not in result:
                errors.append(f"unknown broader concept {parent!r} referenced by {concept_id}")

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node: str) -> None:
        if node in visiting:
            errors.append(f"taxonomy cycle detected at: {node}")
            return
        if node in visited:
            return
        visiting.add(node)
        for parent in result.get(node, {}).get("broader", []) or []:
            if str(parent) in result:
                visit(str(parent))
        visiting.remove(node)
        visited.add(node)

    for concept_id in result:
        visit(concept_id)
    return result, errors


def knowledge_files(root: Path) -> list[Path]:
    wiki_root = root / "wiki"
    files: list[Path] = []
    for path in wiki_root.rglob("*.md"):
        relative = path.relative_to(wiki_root)
        parts = {part.casefold() for part in relative.parts}
        if "graphify-out" in parts:
            continue
        if path.name.casefold() in OPERATIONAL_WIKI_FILES and "sources" not in parts:
            continue
        if any(part in {"sources", "entities", "concepts", "projects"} for part in parts):
            files.append(path)
    return sorted(files, key=lambda item: item.as_posix())


def audit(root: Path) -> dict[str, Any]:
    concepts, errors = taxonomy_concepts(root)
    label_map: dict[str, str] = {}
    for concept_id, concept in concepts.items():
        label_map[normalize(concept_id)] = concept_id
        label_map[normalize(str(concept.get("prefLabel", "")))] = concept_id
        for label in concept.get("altLabel", []) if isinstance(concept.get("altLabel", []), list) else []:
            label_map[normalize(str(label))] = concept_id
    unmapped: list[dict[str, str]] = []
    documents = 0
    labeled_documents = 0
    used: set[str] = set()
    for path in knowledge_files(root):
        documents += 1
        labels = frontmatter_labels(read_frontmatter(path.read_text(encoding="utf-8-sig")))
        if not labels:
            errors.append(f"document has no topics/tags: {path.relative_to(root).as_posix()}")
            continue
        labeled_documents += 1
        for label in labels:
            concept_id = label_map.get(normalize(label))
            if concept_id is None:
                unmapped.append({"document": path.relative_to(root).as_posix(), "label": label})
            else:
                used.add(concept_id)
    for item in unmapped:
        errors.append(f"unmapped category {item['label']!r} in {item['document']}")
    orphaned = sorted(set(concepts) - used)
    return {
        "status": "ok" if not errors else "failed",
        "valid": not errors,
        "taxonomy": str((root / "wiki" / "taxonomy.json").relative_to(root)).replace("\\", "/"),
        "concepts": len(concepts),
        "documents": documents,
        "labeled_documents": labeled_documents,
        "orphaned_concepts": orphaned,
        "unmapped": unmapped,
        "errors": errors,
        "warnings": [f"unused taxonomy concept: {concept_id}" for concept_id in orphaned],
        "exit_code": 0 if not errors else 2,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit the LLM Wiki controlled vocabulary")
    parser.add_argument("--root", default=None)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        root = resolve_wiki_root(args.root)
    except ValueError as error:
        parser.error(str(error))
    result = audit(root)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"status: {result['status']}")
        print(f"concepts: {result['concepts']}, documents: {result['documents']}, labeled: {result['labeled_documents']}")
        for error in result["errors"]:
            print(f"error: {error}")
        for warning in result["warnings"]:
            print(f"warning: {warning}")
    return int(result["exit_code"])


if __name__ == "__main__":
    raise SystemExit(main())
