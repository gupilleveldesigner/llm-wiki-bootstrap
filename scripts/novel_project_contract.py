from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from template_render import render_template

ASSETS = Path(__file__).resolve().parent.parent / "assets"
PROJECT_MODE_VERSION = 1
ROUTER_MARKER = "<!-- LLM-WIKI:NOVEL-PROJECT-MODE -->"
RUNTIME_SOURCE = "project-modes/novel/runtime/novel_check.py"
RUNTIME_DESTINATION = "tools/novel_check.py"
NOVEL_DEFAULTS = {
    "novel_title": "",
    "genre": "UNKNOWN",
    "audience": "UNKNOWN",
    "project_phase": "planning",
}
DOCUMENT_KINDS = (
    "character", "location", "world-rule", "arc", "chapter", "scene",
    "timeline-event", "foreshadow", "review", "decision",
)
DOCS = (
    ("novel-index.md.template", "wiki/novel/index.md"),
    ("novel-overview.md.template", "wiki/novel/overview.md"),
    ("novel-model.md.template", "wiki/novel/model.md"),
    ("novel-operations.md.template", "instructions/novel-project.md"),
    ("novel-CLAUDE.md.template", "wiki/novel/CLAUDE.md"),
    ("manuscript-CLAUDE.md.template", "manuscripts/novel/CLAUDE.md"),
)
DIRECTORIES = (
    "raw/novel/research", "raw/novel/imports",
    "wiki/novel/characters", "wiki/novel/locations", "wiki/novel/world",
    "wiki/novel/arcs", "wiki/novel/chapters", "wiki/novel/scenes",
    "wiki/novel/timeline", "wiki/novel/foreshadowing", "wiki/novel/reviews",
    "wiki/novel/decisions", "manuscripts/novel/drafts",
    "manuscripts/novel/revisions", "Output/novel", "templates/novel", "tools",
)


def validate_config(config: Any, *, require_base: bool) -> dict[str, Any]:
    if not isinstance(config, dict):
        raise ValueError("config root must be an object")
    for key in ("project_name", "domain_summary", *NOVEL_DEFAULTS):
        if key in config and not isinstance(config[key], str):
            raise ValueError(f"config key '{key}' must be a string")
    if require_base:
        for key in ("project_name", "domain_summary"):
            if not config.get(key, "").strip():
                raise ValueError(f"config key '{key}' must be a non-empty string")
    if "project_mode" in config and config["project_mode"] != "novel":
        raise ValueError("Novel config project_mode must be novel")
    return config


def read_config(path: Path, *, require_base: bool) -> dict[str, Any]:
    return validate_config(json.loads(path.read_text(encoding="utf-8")), require_base=require_base)


def resolve_metadata(config: dict[str, Any], previous: dict[str, Any]) -> dict[str, Any]:
    mode = previous.get("project_mode", "knowledge")
    if mode not in ("knowledge", "novel"):
        raise ValueError(f"cannot replace project_mode {mode!r} with novel")
    if mode == "novel" and (type(previous.get("project_mode_version")) is not int
                            or previous["project_mode_version"] != PROJECT_MODE_VERSION):
        raise ValueError("unsupported Novel project_mode_version")
    owned = previous.get("novel_managed_assets", [])
    if not isinstance(owned, list) or any(not isinstance(item, str) for item in owned):
        raise ValueError("novel_managed_assets must be a list of paths")
    old = previous.get("novel_project", {})
    if not isinstance(old, dict):
        raise ValueError("novel_project must be an object")
    metadata = {key: config.get(key, old.get(key, default)) for key, default in NOVEL_DEFAULTS.items()}
    if any(not isinstance(value, str) for value in metadata.values()):
        raise ValueError("Novel metadata values must be strings")
    metadata["novel_title"] = metadata["novel_title"] or config.get("project_name") or previous.get("project_name", "My Novel")
    metadata.update({"manuscript_root": "manuscripts/novel", "canon_policy": "author-reviewed"})
    return metadata


def bundle_files() -> list[tuple[str, str, bool]]:
    files = [(f"project-modes/novel/docs/{source}", destination, False) for source, destination in DOCS]
    files.extend((f"project-modes/novel/templates/{kind}.md", f"templates/novel/{kind}.md", False)
                 for kind in DOCUMENT_KINDS)
    files.append((RUNTIME_SOURCE, RUNTIME_DESTINATION, True))
    for provider, destination in (("agents-skills", ".agents"), ("claude-adapters", ".claude")):
        files.extend([
            (f"skills-bundle/{provider}/novel-project/SKILL.md.bundled", f"{destination}/skills/novel-project/SKILL.md", True),
            (f"skills-bundle/{provider}/novel-project/agents/openai.yaml", f"{destination}/skills/novel-project/agents/openai.yaml", True),
        ])
    return files


def validate_novel_checkout(checkout: Path) -> None:
    required = ["scripts/novel_project.py", "scripts/novel_project_contract.py", "scripts/bootstrap.py",
                "scripts/template_render.py", *["assets/" + source for source, _, _ in bundle_files()]]
    missing = [relative for relative in required if not (checkout / relative).is_file()]
    if missing:
        raise RuntimeError("checkout lacks Novel mode contract: " + ", ".join(missing))


def rendered_assets(metadata: dict[str, Any]) -> list[tuple[str, str, bool]]:
    replacements = {"{{NOVEL_TITLE}}": metadata["novel_title"], "{{GENRE}}": metadata["genre"],
                    "{{AUDIENCE}}": metadata["audience"], "{{PROJECT_PHASE}}": metadata["project_phase"]}
    return [(destination, render_template(ASSETS / source, replacements), managed)
            for source, destination, managed in bundle_files()]


def router_block(*, wiki: bool = False) -> str:
    prefix = "../" if wiki else ""
    return (
        f"\n\n{ROUTER_MARKER}\n## Novel 프로젝트 라우터\n\n"
        "- 소설 설정·구성·집필·퇴고·연속성 검토는 `novel-project` 스킬을 읽는다.\n"
        f"- 먼저 `{prefix}instructions/novel-project.md`와 `{prefix}wiki/novel/index.md`를 읽는다.\n"
        "- Raw 원본은 불변이고, 집필 원고는 `manuscripts/novel/`에서 편집한다.\n"
        "- 작가가 채택한 설정과 제안·초고·화자의 주장을 구분한다. AI가 설정을 자동 확정하지 않는다.\n"
        "- `python tools/novel_check.py check`는 구조 점검이다. 의미·문체 검토는 근거를 남긴다.\n"
        "- Novel 탐색은 로컬 설정·구성·원고를 먼저 읽는다. 이 정책은 일반 graph-first 안내보다 우선한다.\n"
    )
