from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from game_workspace import (
    MANAGED_MANIFEST_NAME,
    MANAGED_MANIFEST_SCHEMA_VERSION,
    WorkspacePaths,
)

REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
ASSETS = REPOSITORY_ROOT / "assets"
MANIFEST_NAME = ".llm-wiki.json"
PROJECT_MODE = "game"
PROJECT_MODE_VERSION = 3
TRACEABILITY_SCHEMA_VERSION = 1
GAME_SKILL = "game-project"
GAME_ROUTER_MARKER = "<!-- LLM-WIKI:GAME-PROJECT-MODE -->"
GAME_TRACE_RUNTIME_SOURCE = "project-modes/game/runtime/game_trace.py"
GAME_TRACE_RUNTIME_DESTINATION = "tools/game_trace.py"
GAME_TRACE_INDEX_SOURCE = "project-modes/game/docs/traceability.json.template"
GAME_TRACE_INDEX_DESTINATION = "wiki/game/traceability.json"
GAME_ENGINE_LAYOUT_DOC = "instructions/game-engine-layouts.md"

GAME_DIRECTORIES = (
    "raw/game/design",
    "raw/game/playtests",
    "raw/game/builds",
    "raw/game/telemetry",
    "raw/game/references",
    "wiki/game/features",
    "wiki/game/systems",
    "wiki/game/levels",
    "wiki/game/content",
    "wiki/game/narrative",
    "wiki/game/ui-ux",
    "wiki/game/technical",
    "wiki/game/implementation",
    "wiki/game/assets",
    "wiki/game/playtests",
    "wiki/game/builds",
    "wiki/game/bugs",
    "wiki/game/milestones",
    "wiki/game/decisions",
    "wiki/game/proposals",
    "wiki/game/releases",
    "Output/game",
    "tools",
)

# managed=True means a changed existing file is proposed rather than silently replaced.
GAME_DOCS = (
    ("project-modes/game/docs/game-index.md.template", "wiki/game/index.md", True, True),
    ("project-modes/game/docs/game-overview.md.template", "wiki/game/overview.md", True, False),
    ("project-modes/game/docs/game-vision.md.template", "wiki/game/vision.md", True, False),
    ("project-modes/game/docs/game-pillars.md.template", "wiki/game/pillars.md", True, False),
    ("project-modes/game/docs/game-roadmap.md.template", "wiki/game/roadmap.md", True, False),
    ("project-modes/game/docs/game-model.md.template", "wiki/game/model.md", True, True),
    ("project-modes/game/docs/game-CLAUDE.md.template", "wiki/game/CLAUDE.md", True, True),
    ("project-modes/game/docs/game-operations.md.template", "instructions/game-project.md", True, True),
    ("project-modes/game/docs/game-engine-layouts.md.template", GAME_ENGINE_LAYOUT_DOC, True, True),
    ("project-modes/game/docs/game-taxonomy.json.template", "wiki/game/taxonomy.json", True, True),
)

GAME_CONTRACT_FILES = (
    ("project-modes/game/docs/game-model.md.template", "wiki/game/model.md"),
    ("project-modes/game/docs/game-operations.md.template", "instructions/game-project.md"),
    ("project-modes/game/docs/game-engine-layouts.md.template", GAME_ENGINE_LAYOUT_DOC),
    ("project-modes/game/docs/game-index.md.template", "wiki/game/index.md"),
    ("project-modes/game/docs/game-CLAUDE.md.template", "wiki/game/CLAUDE.md"),
    ("project-modes/game/docs/traceability.json.template", GAME_TRACE_INDEX_DESTINATION),
    (GAME_TRACE_RUNTIME_SOURCE, GAME_TRACE_RUNTIME_DESTINATION),
    ("project-modes/game/templates/feature-spec.md", "templates/game/feature-spec.md"),
    ("project-modes/game/templates/implementation-check.md", "templates/game/implementation-check.md"),
    ("project-modes/game/templates/playtest-report.md", "templates/game/playtest-report.md"),
    ("skills-bundle/agents-skills/game-project/SKILL.md.bundled", ".agents/skills/game-project/SKILL.md"),
    ("skills-bundle/claude-adapters/game-project/SKILL.md.bundled", ".claude/skills/game-project/SKILL.md"),
)

GAME_CONTRACT_MARKERS = {
    "project-modes/game/docs/game-model.md.template": "Design Intent → Implementation State → Validation Evidence → Project Decision",
    "project-modes/game/docs/game-operations.md.template": "vault-only write policy",
    "project-modes/game/docs/game-engine-layouts.md.template": "sidecar",
    "project-modes/game/docs/game-index.md.template": "project_mode: game",
    "project-modes/game/docs/game-CLAUDE.md.template": "game-project",
    "project-modes/game/docs/traceability.json.template": '"source_of_truth"',
    GAME_TRACE_RUNTIME_SOURCE: "TRACEABILITY_SCHEMA_VERSION = 1",
    "project-modes/game/templates/feature-spec.md": "implementation_status: unknown",
    "project-modes/game/templates/implementation-check.md": "checked_paths: []",
    "project-modes/game/templates/playtest-report.md": "## 관찰 — 해석을 섞지 않음",
    "skills-bundle/agents-skills/game-project/SKILL.md.bundled": "vault-only",
    "skills-bundle/claude-adapters/game-project/SKILL.md.bundled": "../../../.agents/skills/game-project/SKILL.md",
}

REQUIRED_GAME_REMOTE_PATHS = (
    "scripts/game_project.py",
    "scripts/game_project_contract.py",
    "scripts/game_project_install.py",
    "scripts/game_workspace.py",
    "assets/project-modes/game/docs/game-model.md.template",
    "assets/project-modes/game/docs/game-operations.md.template",
    "assets/project-modes/game/docs/game-engine-layouts.md.template",
    "assets/project-modes/game/docs/traceability.json.template",
    "assets/project-modes/game/runtime/game_trace.py",
    "assets/project-modes/game/templates/feature-spec.md",
    "assets/project-modes/game/templates/implementation-check.md",
    "assets/project-modes/game/templates/playtest-report.md",
    "assets/skills-bundle/agents-skills/game-project/SKILL.md.bundled",
    "assets/skills-bundle/claude-adapters/game-project/SKILL.md.bundled",
)

GAME_DEFAULTS: dict[str, Any] = {
    "game_engine": "UNKNOWN",
    "game_genre": "UNKNOWN",
    "target_platforms": "UNKNOWN",
    "project_phase": "prototype",
    "source_roots": [],
}


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as file:
        file.write(text.replace("\r\n", "\n").replace("\r", "\n"))


def read_json_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except OSError as error:
        raise ValueError(f"cannot read config: {path}: {error}") from error
    except json.JSONDecodeError as error:
        raise ValueError(f"invalid JSON config: {path}: {error}") from error
    if not isinstance(value, dict):
        raise ValueError("config root must be an object")
    return value


def validate_config(config: dict[str, Any], *, require_base: bool) -> None:
    if require_base:
        for key in ("project_name", "domain_summary"):
            if not isinstance(config.get(key), str) or not str(config[key]).strip():
                raise ValueError(f"config key '{key}' must be a non-empty string")
    for key in (
        "project_name",
        "domain_summary",
        "game_title",
        "game_engine",
        "game_genre",
        "target_platforms",
        "project_phase",
        "layout",
        "engine",
        "project_root",
        "vault_root",
    ):
        if key in config and not isinstance(config[key], str):
            raise ValueError(f"config key '{key}' must be a string")
    if "source_roots" in config:
        roots = config["source_roots"]
        if not isinstance(roots, list) or any(not isinstance(item, str) for item in roots):
            raise ValueError("config key 'source_roots' must be a list of strings")


def read_manifest(target: Path) -> dict[str, Any]:
    path = target / MANIFEST_NAME
    if not path.is_file():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ValueError(f"invalid {MANIFEST_NAME}: {error}") from error
    if not isinstance(value, dict):
        raise ValueError(f"invalid {MANIFEST_NAME}: root must be an object")
    project_mode = value.get("project_mode", "knowledge")
    if project_mode not in ("knowledge", PROJECT_MODE):
        raise ValueError(f"unsupported project_mode in {MANIFEST_NAME}: {project_mode}")
    return value


def resolve_game_metadata(
    target: Path,
    config: dict[str, Any],
    workspace: WorkspacePaths,
    engine: dict[str, Any],
) -> dict[str, Any]:
    manifest = read_manifest(target)
    previous = manifest.get("game_project")
    metadata = dict(previous) if isinstance(previous, dict) else {}
    project_name = config.get("project_name") or manifest.get("project_name") or workspace.project_root.name
    metadata.setdefault("game_title", project_name)
    for key, default in GAME_DEFAULTS.items():
        metadata.setdefault(key, default)
    for key in ("game_title", "game_engine", "game_genre", "target_platforms", "project_phase"):
        if key in config:
            metadata[key] = config[key]
    metadata.update(
        {
            "layout": workspace.layout,
            "project_root": workspace.project_root_reference,
            "project_root_kind": workspace.project_root_reference_kind,
            "vault_root": ".",
            "engine_adapter": engine.get("id"),
            "engine_environment": engine.get("environment"),
            "engine_evidence": engine.get("evidence", []),
            "protected_roots": engine.get("protected_roots", []),
            "generated_roots": engine.get("generated_roots", []),
            "source_roots": engine.get("source_roots", []),
            "write_policy": "vault-only",
            "temporary_write_policy": "transaction-root-only",
        }
    )
    return metadata


def replacements(target: Path, config: dict[str, Any], metadata: dict[str, Any]) -> dict[str, str]:
    manifest = read_manifest(target)
    project_name = str(config.get("project_name") or manifest.get("project_name") or metadata.get("game_title") or "Game Project")
    domain_summary = str(config.get("domain_summary") or project_name)
    source_roots = metadata.get("source_roots")
    source_roots_text = ", ".join(source_roots) if isinstance(source_roots, list) and source_roots else "UNKNOWN"
    return {
        "{{PROJECT_NAME}}": project_name,
        "{{DOMAIN_SUMMARY}}": domain_summary,
        "{{GAME_TITLE}}": str(metadata.get("game_title", project_name)),
        "{{GAME_ENGINE}}": str(metadata.get("game_engine", "UNKNOWN")),
        "{{GAME_GENRE}}": str(metadata.get("game_genre", "UNKNOWN")),
        "{{TARGET_PLATFORMS}}": str(metadata.get("target_platforms", "UNKNOWN")),
        "{{PROJECT_PHASE}}": str(metadata.get("project_phase", "prototype")),
        "{{SOURCE_ROOTS}}": source_roots_text,
        "{{LAYOUT}}": str(metadata.get("layout", "sidecar")),
        "{{PROJECT_ROOT_REFERENCE}}": str(metadata.get("project_root", "UNKNOWN")),
        "{{ENGINE_ADAPTER}}": str(metadata.get("engine_adapter", "generic")),
        "{{TODAY}}": datetime.now().strftime("%Y-%m-%d"),
    }


def render_file(source: Path, values: dict[str, str]) -> str:
    content = source.read_text(encoding="utf-8")
    for placeholder, value in values.items():
        content = content.replace(placeholder, value)
    return content


def validate_game_bundle(root: Path = REPOSITORY_ROOT) -> None:
    missing = [relative for relative in REQUIRED_GAME_REMOTE_PATHS if not (root / relative).is_file()]
    marker_errors: list[str] = []
    for source_name, marker in GAME_CONTRACT_MARKERS.items():
        source = root / "assets" / source_name
        if source.is_file() and marker not in source.read_text(encoding="utf-8"):
            marker_errors.append(f"{source_name} missing marker {marker!r}")
    if missing or marker_errors:
        details = [*(f"missing {path}" for path in missing), *marker_errors]
        raise RuntimeError("invalid game project bundle: " + "; ".join(details))


def validate_game_checkout(checkout: Path) -> None:
    missing = [relative for relative in REQUIRED_GAME_REMOTE_PATHS if not (checkout / relative).is_file()]
    if missing:
        raise RuntimeError("downloaded GitHub checkout lacks game project mode: " + ", ".join(missing))
    validate_game_bundle(checkout)


def write_game_manifest(target: Path, metadata: dict[str, Any]) -> None:
    path = target / MANIFEST_NAME
    manifest = read_manifest(target)
    if not manifest:
        raise RuntimeError(f"base bootstrap did not create {MANIFEST_NAME}")
    now = datetime.now().astimezone().isoformat()
    manifest["project_mode"] = PROJECT_MODE
    manifest["project_mode_version"] = PROJECT_MODE_VERSION
    manifest["game_project"] = metadata
    manifest["game_traceability"] = {
        "schema_version": TRACEABILITY_SCHEMA_VERSION,
        "index": GAME_TRACE_INDEX_DESTINATION,
        "runtime": GAME_TRACE_RUNTIME_DESTINATION,
        "source_of_truth": "vault specs/checks/builds/playtests/decisions plus live project paths and Git revisions",
    }
    manifest["managed_files"] = {
        "schema_version": MANAGED_MANIFEST_SCHEMA_VERSION,
        "manifest": MANAGED_MANIFEST_NAME,
    }
    manifest["updated_at"] = now
    write_text(path, json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")


def write_upgrade_provenance(target: Path, *, repository: str, branch: str, commit: str) -> None:
    path = target / MANIFEST_NAME
    manifest = read_manifest(target)
    if not manifest:
        raise RuntimeError(f"successful game upgrade did not leave {MANIFEST_NAME}")
    manifest["last_upgrade"] = {
        "source": "github",
        "repository": repository,
        "branch": branch,
        "commit": commit,
        "at": datetime.now().astimezone().isoformat(),
    }
    write_text(path, json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
