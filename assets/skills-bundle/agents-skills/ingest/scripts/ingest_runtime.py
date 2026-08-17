#!/usr/bin/env python3
"""Host-neutral runtime for an LLM Wiki ingest skill."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Sequence
from urllib.parse import unquote

SCRIPT_ROOT = Path(__file__).resolve().parent
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

from find_uningested import PLAIN_RAW_PATH_RE, configure_utf8_stdout, resolve_wiki_root, scan


TOP_LEVEL_KEY_RE = re.compile(r"^[A-Za-z0-9_-]+:\s*", re.MULTILINE)
WIKILINK_RE = re.compile(r"\[\[([^\]|#]+)")


def read_frontmatter(path: Path) -> str:
    text = path.read_text(encoding="utf-8-sig")
    if not text.startswith("---"):
        return ""
    parts = text.split("---", 2)
    return parts[1] if len(parts) == 3 else ""


def frontmatter_value(frontmatter: str, key: str) -> str:
    match = re.search(rf"(?m)^{re.escape(key)}:\s*(.*)$", frontmatter)
    if not match:
        return ""
    value = match.group(1).strip()
    remainder = frontmatter[match.end() :]
    continuation: list[str] = []
    for line in remainder.splitlines():
        if line and not line[0].isspace() and TOP_LEVEL_KEY_RE.match(line):
            break
        if line.strip():
            continuation.append(line.strip())
    return "\n".join([value, *continuation]).strip()


def _has_meaningful_value(value: str) -> bool:
    return value.casefold() not in {"", "[]", "{}", "null", "none", "~"}


def normalize_changed_file(root: Path, value: str) -> tuple[Path, str]:
    candidate = Path(value)
    if not candidate.is_absolute():
        candidate = root / candidate
    candidate = candidate.resolve()
    wiki_root = (root / "wiki").resolve()
    try:
        relative = candidate.relative_to(root).as_posix()
        candidate.relative_to(wiki_root)
    except ValueError as error:
        raise ValueError(f"Changed file must stay under wiki/: {value}") from error
    if not candidate.is_file():
        raise ValueError(f"Changed wiki file does not exist: {relative}")
    return candidate, relative


def validate_changed_files(root: Path, changed_files: Sequence[str]) -> list[str]:
    """Apply portable minimum gates before any graph-specific finalizer."""
    if not changed_files:
        return ["At least one --changed-file is required to complete an ingest."]

    errors: list[str] = []
    raw_root = (root / "raw").resolve()
    for value in changed_files:
        try:
            path, relative = normalize_changed_file(root, value)
        except ValueError as error:
            errors.append(str(error))
            continue

        text = path.read_text(encoding="utf-8-sig")
        frontmatter = read_frontmatter(path)
        if not frontmatter:
            errors.append(f"{relative}: YAML frontmatter is required")
            continue

        topics = frontmatter_value(frontmatter, "topics") or frontmatter_value(frontmatter, "tags")
        source_fields = "\n".join(
            value
            for value in (
                frontmatter_value(frontmatter, "sources"),
                frontmatter_value(frontmatter, "source"),
            )
            if _has_meaningful_value(value)
        )
        if not _has_meaningful_value(topics):
            errors.append(f"{relative}: topics or tags must not be empty")
        source_scope = "\n".join(value for value in (source_fields, text) if value)
        if not _has_meaningful_value(source_scope):
            errors.append(f"{relative}: a raw source citation is required")
        else:
            cited_targets = WIKILINK_RE.findall(source_scope) + PLAIN_RAW_PATH_RE.findall(source_scope)
            raw_targets = list(
                dict.fromkeys(
                    unquote(target.strip()).replace("\\", "/").removeprefix("./")
                    for target in cited_targets
                    if target.strip().replace("\\", "/").removeprefix("./").casefold().startswith("raw/")
                )
            )
            if not raw_targets:
                errors.append(f"{relative}: source citation must include a raw/ file path")
            for target in raw_targets:
                candidate = (root / target).resolve()
                try:
                    candidate.relative_to(raw_root)
                except ValueError:
                    errors.append(f"{relative}: raw source escapes raw/: {target}")
                    continue
                candidates = [candidate]
                if not candidate.suffix:
                    candidates.append(candidate.with_suffix(".md"))
                if not any(path.is_file() for path in candidates):
                    errors.append(f"{relative}: raw source does not exist: {target}")
    return errors


def graph_strategy(root: Path) -> str:
    finalizer = root / "tools" / "graphify_knowledge" / "finalize_ingest.py"
    if finalizer.is_file():
        return "curated-finalizer"
    workspaces = graph_workspaces(root)
    if len(workspaces) > 1:
        return "ambiguous-graph-layout"
    if not workspaces:
        return "none"
    curated_marker = workspaces[0] / "graphify-out" / "CURATED_GRAPH_STATE.json"
    if curated_marker.is_file():
        return "curated-finalizer-missing"
    return "graphify-cli"


def graph_workspaces(root: Path) -> list[Path]:
    candidates: list[Path] = []
    for workspace in (root, root / "wiki"):
        graph_out = workspace / "graphify-out"
        if (graph_out / "graph.json").is_file() or (graph_out / "CURATED_GRAPH_STATE.json").is_file():
            candidates.append(workspace.resolve())
    return candidates


def graph_workspace(root: Path) -> Path | None:
    if (root / "tools" / "graphify_knowledge" / "finalize_ingest.py").is_file():
        return root.resolve()
    workspaces = graph_workspaces(root)
    return workspaces[0] if len(workspaces) == 1 else None


def graph_python(root: Path, workspace: Path | None = None) -> str:
    for graph_root in (workspace, root):
        if graph_root is None:
            continue
        marker = graph_root / "graphify-out" / ".graphify_python"
        if marker.is_file():
            value = marker.read_text(encoding="utf-8-sig").strip()
            if value:
                return value
    return sys.executable


def run_command(command: Sequence[str], *, cwd: Path) -> int:
    completed = subprocess.run(list(command), cwd=cwd, check=False)
    return completed.returncode


def finalize(root: Path, changed_files: Sequence[str]) -> dict[str, Any]:
    errors = validate_changed_files(root, changed_files)
    if errors:
        return {"status": "validation_failed", "root": str(root), "errors": errors, "exit_code": 2}

    strategy = graph_strategy(root)
    workspace = graph_workspace(root)
    if strategy == "curated-finalizer":
        command = [
            graph_python(root, workspace),
            str(root / "tools" / "graphify_knowledge" / "finalize_ingest.py"),
            "--workspace-root",
            str(root),
        ]
        for changed_file in changed_files:
            _, relative = normalize_changed_file(root, changed_file)
            command.extend(["--changed-file", relative])
        exit_code = run_command(command, cwd=root)
        return {
            "status": "promoted" if exit_code == 0 else "graph_finalizer_failed",
            "root": str(root),
            "strategy": strategy,
            "exit_code": exit_code,
        }

    if strategy == "curated-finalizer-missing":
        return {
            "status": "graph_finalizer_missing",
            "root": str(root),
            "strategy": strategy,
            "errors": ["Curated graph marker exists, so generic graphify update was refused."],
            "exit_code": 2,
        }

    if strategy == "ambiguous-graph-layout":
        return {
            "status": "ambiguous_graph_layout",
            "root": str(root),
            "strategy": strategy,
            "errors": ["Both root/graphify-out and wiki/graphify-out exist; choose one canonical graph first."],
            "exit_code": 2,
        }

    if strategy == "graphify-cli":
        if workspace is None:
            raise RuntimeError("Graphify workspace resolution failed.")
        executable = shutil.which("graphify")
        if executable is None:
            return {
                "status": "graphify_unavailable",
                "root": str(root),
                "strategy": strategy,
                "errors": ["graphify-out/graph.json exists but the graphify CLI is unavailable."],
                "exit_code": 2,
            }
        exit_code = run_command([executable, "update", str(workspace)], cwd=workspace)
        return {
            "status": "updated" if exit_code == 0 else "graphify_update_failed",
            "root": str(root),
            "graph_workspace": str(workspace),
            "strategy": strategy,
            "exit_code": exit_code,
        }

    return {
        "status": "validated_without_graph",
        "root": str(root),
        "strategy": strategy,
        "note": "Wiki files passed portable gates; this Wiki has no graph to update.",
        "exit_code": 0,
    }


def recover(root: Path) -> dict[str, Any]:
    recovery = root / "tools" / "graphify_knowledge" / "promote_candidate.py"
    if not recovery.is_file():
        return {
            "status": "recovery_unavailable",
            "root": str(root),
            "errors": ["This Wiki does not provide the curated Graphify recovery tool."],
            "exit_code": 2,
        }
    exit_code = run_command(
        [graph_python(root), str(recovery), "--workspace-root", str(root), "--recover"],
        cwd=root,
    )
    return {
        "status": "recovered" if exit_code == 0 else "recovery_failed",
        "root": str(root),
        "exit_code": exit_code,
    }


def print_json(payload: Any) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Portable LLM Wiki ingest support")
    subparsers = parser.add_subparsers(dest="command", required=True)

    for name in ("status", "scan", "finalize", "recover"):
        child = subparsers.add_parser(name)
        child.add_argument(
            "--root",
            default=None,
            help=(
                "LLM Wiki root. If omitted, use the invoking project; linked Git worktrees "
                "fall back to their primary checkout."
            ),
        )
        if name == "scan":
            child.add_argument("--json", action="store_true")
        if name == "finalize":
            child.add_argument("--changed-file", action="append", default=[])
    return parser


def main() -> int:
    configure_utf8_stdout()
    parser = build_parser()
    args = parser.parse_args()
    try:
        root = resolve_wiki_root(args.root)
    except ValueError as error:
        parser.error(str(error))

    if args.command == "status":
        workspace = graph_workspace(root)
        print_json(
            {
                "root": str(root),
                "graph_strategy": graph_strategy(root),
                "graph_workspace": str(workspace) if workspace is not None else None,
            }
        )
        return 0
    if args.command == "scan":
        result = scan(root)
        if args.json:
            print_json(result)
        else:
            for name in ("pending", "ingested", "skipped"):
                print(f"{name}: {len(result[name])}")
                for item in result[name]:
                    reason = f" - {item['reason']}" if "reason" in item else ""
                    print(f"  - {item['path']} ({item['modified']}){reason}")
        return 0
    if args.command == "finalize":
        result = finalize(root, args.changed_file)
        print_json(result)
        return int(result["exit_code"])
    result = recover(root)
    print_json(result)
    return int(result["exit_code"])


if __name__ == "__main__":
    raise SystemExit(main())
