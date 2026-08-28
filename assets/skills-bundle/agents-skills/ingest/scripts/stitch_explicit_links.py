#!/usr/bin/env python3
"""Add structural Source→Raw/Wiki edges without claiming semantic coverage."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from find_uningested import resolve_wiki_root
from ingest_runtime import graph_workspace, independent_source_records


def _normal(value: str) -> str:
    return value.replace("\\", "/").casefold().removeprefix("./")


def _matches(identity: str, target: str) -> bool:
    target = _normal(target)
    variants = {target, target.removeprefix("wiki/")}
    if not Path(target).suffix:
        variants.update(f"{value}.md" for value in tuple(variants))
    identity = _normal(identity)
    return identity in variants or identity.removeprefix("wiki/") in variants


def _node_id(relative: str) -> str:
    return "explicit_" + hashlib.sha256(relative.encode("utf-8")).hexdigest()[:16]


def _file_type(path: Path) -> str:
    if path.suffix.casefold() in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".bmp", ".avif"}:
        return "image"
    if path.suffix.casefold() in {".py", ".js", ".ts", ".go", ".rs", ".java", ".c", ".cpp"}:
        return "code"
    return "document"


def stitch(root: Path) -> dict[str, int]:
    workspace = graph_workspace(root) or root
    graph_path = workspace / "graphify-out" / "graph.json"
    payload = json.loads(graph_path.read_text(encoding="utf-8-sig"))
    nodes = payload.setdefault("nodes", [])
    links = payload.setdefault("links", payload.pop("edges", []))
    identity = {
        str(node.get("id")): _normal(str(node.get("source_file")))
        for node in nodes
        if isinstance(node, dict) and node.get("id") is not None and node.get("source_file")
    }
    node_by_id = {str(node.get("id")): node for node in nodes if isinstance(node, dict) and node.get("id") is not None}
    added_nodes = 0
    added_links = 0

    def ids_for(target: str) -> list[str]:
        return [node_id for node_id, source_file in identity.items() if _matches(source_file, target)]

    def ensure_node(target: str, *, community: int = 0) -> str:
        nonlocal added_nodes
        existing = ids_for(target)
        if existing:
            return existing[0]
        relative = _normal(target)
        path = root / relative
        node_id = _node_id(relative)
        node = {
            "id": node_id,
            "label": path.stem,
            "file_type": _file_type(path),
            "source_file": relative,
            "source_location": None,
            "source_url": None,
            "captured_at": None,
            "author": None,
            "contributor": None,
            "community": community,
        }
        nodes.append(node)
        node_by_id[node_id] = node
        identity[node_id] = relative
        added_nodes += 1
        return node_id

    def ensure_link(source_id: str, target_id: str, source_file: str) -> None:
        nonlocal added_links
        for link in links:
            if not isinstance(link, dict):
                continue
            left = str(link.get("source", link.get("from", "")))
            right = str(link.get("target", link.get("to", "")))
            if {left, right} == {source_id, target_id}:
                link["source"] = source_id
                link["target"] = target_id
                if link.get("edge_origin") == "deterministic_stitch":
                    link["confidence"] = "EXTRACTED"
                return
        links.append(
            {
                "source": source_id,
                "target": target_id,
                "relation": "structural_reference",
                "confidence": "EXTRACTED",
                "confidence_score": 1.0,
                "source_file": source_file,
                "source_location": "deterministic source-record link",
                "edge_origin": "deterministic_stitch",
                "semantic_evidence": False,
                "weight": 1.0,
            }
        )
        added_links += 1

    for record in independent_source_records(root):
        source_id = ensure_node(record["relative"])
        community = int(node_by_id[source_id].get("community", 0) or 0)
        for raw_target in record["raw_targets"]:
            ensure_link(source_id, ensure_node(raw_target, community=community), record["relative"])
        for wiki_target in record["wiki_targets"]:
            target = wiki_target if _normal(wiki_target).startswith("wiki/") else f"wiki/{wiki_target}"
            if not Path(target).suffix:
                target += ".md"
            ensure_link(source_id, ensure_node(target, community=community), record["relative"])

    temporary = graph_path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(graph_path)
    return {
        "added_nodes": added_nodes,
        "added_links": added_links,
        "semantic_edges_added": 0,
        "nodes": len(nodes),
        "links": len(links),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=None)
    args = parser.parse_args()
    root = resolve_wiki_root(args.root)
    print(json.dumps(stitch(root), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
