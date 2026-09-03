from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Iterable


WORKSPACE_SCHEMA_VERSION = 1
MANAGED_MANIFEST_NAME = ".llm-wiki-managed.json"
MANAGED_MANIFEST_SCHEMA_VERSION = 1
TRANSACTION_DIRECTORY_NAME = ".llm-wiki-transactions"
SUPPORTED_LAYOUTS = ("auto", "sidecar", "embedded", "custom", "legacy-in-place")
SUPPORTED_ENGINES = ("auto", "unity", "unreal", "godot", "web", "generic")
INTEGRITY_MODES = ("off", "metadata", "full")


class WorkspaceError(RuntimeError):
    pass


@dataclass(frozen=True)
class WorkspacePaths:
    project_root: Path
    vault_root: Path
    transaction_root: Path
    layout: str
    project_root_reference: str
    project_root_reference_kind: str
    legacy_in_place: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_root": str(self.project_root),
            "vault_root": str(self.vault_root),
            "transaction_root": str(self.transaction_root),
            "layout": self.layout,
            "project_root_reference": self.project_root_reference,
            "project_root_reference_kind": self.project_root_reference_kind,
            "legacy_in_place": self.legacy_in_place,
        }


ENGINE_ADAPTERS: dict[str, dict[str, Any]] = {
    "unity": {
        "display_name": "Unity",
        "protected_roots": ["Assets", "Packages", "ProjectSettings"],
        "generated_roots": ["Library", "Temp", "Logs", "obj", "UserSettings", "Build", "Builds"],
        "default_source_roots": ["Assets"],
        "isolation_files": {},
    },
    "unreal": {
        "display_name": "Unreal Engine",
        "protected_roots": ["Content", "Config", "Source", "Plugins"],
        "generated_roots": ["Binaries", "DerivedDataCache", "Intermediate", "Saved", ".vs"],
        "default_source_roots": ["Source", "Content", "Plugins"],
        "isolation_files": {},
    },
    "godot": {
        "display_name": "Godot",
        "protected_roots": ["project.godot"],
        "generated_roots": [".godot", ".import"],
        "default_source_roots": ["."],
        "isolation_files": {".gdignore": ""},
    },
    "web": {
        "display_name": "Web/JavaScript",
        "protected_roots": [
            "src",
            "app",
            "pages",
            "public",
            "package.json",
            "package-lock.json",
            "pnpm-lock.yaml",
            "yarn.lock",
            "vite.config.js",
            "vite.config.ts",
            "next.config.js",
            "next.config.mjs",
            "next.config.ts",
            "tsconfig.json",
        ],
        "generated_roots": ["node_modules", "dist", "build", ".next", ".nuxt", ".vite", "coverage"],
        "default_source_roots": ["src", "app", "pages", "public"],
        "isolation_files": {},
    },
    "generic": {
        "display_name": "Generic game project",
        "protected_roots": [],
        "generated_roots": [],
        "default_source_roots": [],
        "isolation_files": {},
    },
}


KNOWN_MANAGED_PREFIXES = (
    ".agents/",
    ".claude/",
    ".session-memory/",
    ".wiki-upgrade-bak/",
    "instructions/",
    "templates/",
    "tools/",
    "wiki/game/",
)
KNOWN_MANAGED_FILES = {
    ".graphifyignore",
    ".llm-wiki.json",
    MANAGED_MANIFEST_NAME,
    "AGENTS.md",
    "CLAUDE.md",
    "changelog.md",
    "log.md",
    "wiki/CLAUDE.md",
    "wiki/index.md",
    "wiki/ingest-ledger.json",
    "wiki/log.md",
    "wiki/overview.md",
    "wiki/questions.md",
    "wiki/taxonomy.json",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def normalize_relative(value: str) -> str:
    raw = value.strip().replace("\\", "/")
    while raw.startswith("./"):
        raw = raw[2:]
    if raw in ("", "."):
        return "."
    if raw.startswith("/") or (len(raw) >= 3 and raw[1:3] == ":/"):
        raise ValueError(f"path must be relative: {value}")
    parts = PurePosixPath(raw).parts
    if ".." in parts:
        raise ValueError(f"path escapes its root: {value}")
    return PurePosixPath(*parts).as_posix()


def _portable_reference(vault_root: Path, project_root: Path) -> tuple[str, str]:
    try:
        reference = os.path.relpath(project_root, vault_root).replace("\\", "/")
        return reference, "relative"
    except ValueError:
        return str(project_root), "absolute"


def _manifest_project_root(vault_root: Path) -> Path | None:
    manifest_path = vault_root / ".llm-wiki.json"
    if not manifest_path.is_file():
        return None
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    game = manifest.get("game_project") if isinstance(manifest, dict) else None
    if not isinstance(game, dict):
        return None
    value = game.get("project_root")
    kind = game.get("project_root_kind", "relative")
    if not isinstance(value, str) or not value:
        return None
    candidate = Path(value)
    if kind == "relative" or not candidate.is_absolute():
        candidate = vault_root / candidate
    return candidate.resolve()


def resolve_workspace_paths(
    project_root: Path,
    *,
    vault_root: Path | None = None,
    layout: str = "auto",
    mode: str = "migrate",
    allow_legacy_in_place: bool = False,
) -> WorkspacePaths:
    if layout not in SUPPORTED_LAYOUTS:
        raise WorkspaceError(f"unsupported layout: {layout}")
    project = project_root.expanduser().resolve()
    if not project.is_dir():
        raise WorkspaceError(f"project root does not exist or is not a directory: {project}")

    explicit_vault = vault_root.expanduser().resolve() if vault_root is not None else None
    sidecar = project.parent / f"{project.name}.wiki"
    embedded = project / ".llm-wiki"

    resolved_layout = layout
    if layout == "auto":
        if explicit_vault is not None:
            if explicit_vault == embedded:
                resolved_layout = "embedded"
            elif explicit_vault == project:
                resolved_layout = "legacy-in-place"
            elif explicit_vault.parent == project.parent and explicit_vault.name == f"{project.name}.wiki":
                resolved_layout = "sidecar"
            else:
                resolved_layout = "custom"
        elif embedded.joinpath(".llm-wiki.json").is_file():
            resolved_layout = "embedded"
        elif sidecar.joinpath(".llm-wiki.json").is_file():
            resolved_layout = "sidecar"
        elif mode == "upgrade" and project.joinpath(".llm-wiki.json").is_file():
            resolved_layout = "legacy-in-place"
        else:
            resolved_layout = "sidecar"

    if resolved_layout == "sidecar":
        vault = explicit_vault or sidecar
    elif resolved_layout == "embedded":
        vault = explicit_vault or embedded
        if vault != embedded:
            raise WorkspaceError("embedded layout requires vault_root to be <project_root>/.llm-wiki")
    elif resolved_layout == "custom":
        if explicit_vault is None:
            raise WorkspaceError("custom layout requires --vault-root")
        vault = explicit_vault
    elif resolved_layout == "legacy-in-place":
        vault = explicit_vault or project
        if vault != project:
            raise WorkspaceError("legacy-in-place layout requires project_root == vault_root")
        if not allow_legacy_in_place:
            raise WorkspaceError(
                "legacy in-place game Wiki writes into the engine project root; migrate to sidecar or pass "
                "--allow-legacy-in-place explicitly"
            )
    else:  # pragma: no cover - guarded above
        raise WorkspaceError(f"unsupported resolved layout: {resolved_layout}")

    if vault.exists() and vault.is_symlink():
        raise WorkspaceError(f"vault root may not be a symlink: {vault}")
    vault = vault.resolve()
    if project == vault and resolved_layout != "legacy-in-place":
        raise WorkspaceError("project_root and vault_root must be separate")
    if project.is_relative_to(vault) and project != vault:
        raise WorkspaceError("project_root may not be nested inside vault_root")
    if vault.is_relative_to(project) and resolved_layout not in ("embedded", "legacy-in-place"):
        raise WorkspaceError("a vault inside project_root must use the isolated embedded layout")

    if resolved_layout == "embedded":
        transaction_root = project.parent / TRANSACTION_DIRECTORY_NAME
    else:
        transaction_root = vault.parent / TRANSACTION_DIRECTORY_NAME
    if transaction_root.exists() and transaction_root.is_symlink():
        raise WorkspaceError(f"transaction root may not be a symlink: {transaction_root}")
    transaction_root = transaction_root.resolve()

    reference, reference_kind = _portable_reference(vault, project)
    return WorkspacePaths(
        project_root=project,
        vault_root=vault,
        transaction_root=transaction_root,
        layout=resolved_layout,
        project_root_reference=reference,
        project_root_reference_kind=reference_kind,
        legacy_in_place=resolved_layout == "legacy-in-place",
    )


def _package_environment(project_root: Path) -> tuple[str, list[str]]:
    package_path = project_root / "package.json"
    if not package_path.is_file():
        return "web", []
    try:
        package = json.loads(package_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return "web", ["package.json"]
    names: set[str] = set()
    for field in ("dependencies", "devDependencies", "peerDependencies"):
        value = package.get(field)
        if isinstance(value, dict):
            names.update(str(key) for key in value)
    evidence = ["package.json"]
    if "phaser" in names:
        return "phaser", evidence + ["dependency:phaser"]
    if "next" in names:
        return "nextjs", evidence + ["dependency:next"]
    if "vite" in names:
        return "vite", evidence + ["dependency:vite"]
    return "web", evidence


def _direct_engine_candidates(project_root: Path) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    unity_evidence = [name for name in ("Assets", "Packages", "ProjectSettings") if (project_root / name).exists()]
    if len(unity_evidence) == 3:
        if (project_root / "ProjectSettings/ProjectVersion.txt").is_file():
            unity_evidence.append("ProjectSettings/ProjectVersion.txt")
        candidates.append({"id": "unity", "score": 100 + 10 * (len(unity_evidence) - 3), "evidence": unity_evidence})

    uprojects = sorted(path.name for path in project_root.glob("*.uproject") if path.is_file())
    if uprojects:
        evidence = [*uprojects]
        evidence.extend(name for name in ("Content", "Config", "Source", "Plugins") if (project_root / name).exists())
        candidates.append({"id": "unreal", "score": 110, "evidence": evidence})

    if (project_root / "project.godot").is_file():
        candidates.append({"id": "godot", "score": 110, "evidence": ["project.godot"]})

    if (project_root / "package.json").is_file():
        environment, evidence = _package_environment(project_root)
        if any((project_root / name).exists() for name in ("src", "app", "pages", "public")):
            evidence.extend(name for name in ("src", "app", "pages", "public") if (project_root / name).exists())
        candidates.append({"id": "web", "score": 80, "evidence": sorted(set(evidence)), "environment": environment})
    return candidates


def _nested_engine_roots(project_root: Path) -> list[dict[str, Any]]:
    roots: list[dict[str, Any]] = []
    try:
        children = sorted(path for path in project_root.iterdir() if path.is_dir() and not path.is_symlink())
    except OSError:
        return []
    for child in children:
        if child.name.startswith("."):
            continue
        candidates = _direct_engine_candidates(child)
        for candidate in candidates:
            roots.append({"path": child.relative_to(project_root).as_posix(), **candidate})
    return roots


def _dynamic_protected_roots(project_root: Path, engine_id: str, generated: Iterable[str]) -> list[str]:
    generated_set = set(generated)
    if engine_id not in ("godot", "generic"):
        return []
    roots: list[str] = []
    for path in sorted(project_root.iterdir()):
        if path.name in generated_set or path.name in (".git", ".llm-wiki", TRANSACTION_DIRECTORY_NAME):
            continue
        roots.append(path.name)
    return roots


def detect_engine(
    project_root: Path,
    *,
    requested: str = "auto",
    source_roots: Iterable[str] | None = None,
) -> dict[str, Any]:
    if requested not in SUPPORTED_ENGINES:
        raise WorkspaceError(f"unsupported engine adapter: {requested}")
    project = project_root.resolve()
    direct = _direct_engine_candidates(project)
    nested = _nested_engine_roots(project)
    warnings: list[str] = []
    ambiguous = False

    if requested != "auto":
        engine_id = requested
        selected = next((item for item in direct if item["id"] == requested), None)
        evidence = selected.get("evidence", []) if selected else []
        environment = selected.get("environment") if selected else None
        if requested != "generic" and selected is None:
            warnings.append(f"explicit adapter {requested} did not match its usual project markers")
    elif len(direct) == 1:
        selected = direct[0]
        engine_id = str(selected["id"])
        evidence = list(selected.get("evidence", []))
        environment = selected.get("environment")
    elif len(direct) > 1:
        ordered = sorted(direct, key=lambda item: (-int(item["score"]), str(item["id"])))
        if len(ordered) > 1 and ordered[0]["score"] == ordered[1]["score"]:
            ambiguous = True
            engine_id = "generic"
            evidence = []
            environment = None
            warnings.append("multiple engine markers were found at the selected project root")
        else:
            selected = ordered[0]
            engine_id = str(selected["id"])
            evidence = list(selected.get("evidence", []))
            environment = selected.get("environment")
            warnings.append("multiple engine markers were found; selected the highest-confidence adapter")
    else:
        engine_id = "generic"
        evidence = []
        environment = None
        if nested:
            ambiguous = True
            warnings.append("the selected root appears to be a workspace containing nested engine projects")
        else:
            warnings.append("no known engine markers were found; using the vault-only generic adapter")

    adapter = ENGINE_ADAPTERS[engine_id]
    generated = list(adapter["generated_roots"])
    protected = list(adapter["protected_roots"])
    if engine_id == "unreal":
        protected.extend(path.name for path in project.glob("*.uproject") if path.is_file())
    protected.extend(_dynamic_protected_roots(project, engine_id, generated))
    protected = sorted(set(normalize_relative(item) for item in protected if item))

    if source_roots is None:
        defaults = adapter["default_source_roots"]
        selected_sources = [item for item in defaults if item == "." or (project / item).exists()]
    else:
        selected_sources = [normalize_relative(str(item)) for item in source_roots]
        for item in selected_sources:
            if item != "." and not (project / item).exists():
                warnings.append(f"configured source root does not currently exist: {item}")

    return {
        "id": engine_id,
        "display_name": adapter["display_name"],
        "environment": environment,
        "confidence": 0.0 if engine_id == "generic" and not evidence else 1.0,
        "evidence": sorted(set(str(item) for item in evidence)),
        "protected_roots": protected,
        "generated_roots": sorted(set(normalize_relative(item) for item in generated)),
        "source_roots": sorted(set(selected_sources)),
        "isolation_files": dict(adapter.get("isolation_files", {})),
        "ambiguous": ambiguous,
        "nested_projects": nested,
        "warnings": warnings,
    }


def protected_absolute_paths(project_root: Path, engine: dict[str, Any]) -> list[Path]:
    paths: list[Path] = []
    for relative in engine.get("protected_roots", []):
        if relative == ".":
            paths.append(project_root.resolve())
        else:
            paths.append((project_root / relative).resolve())
    return paths


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _walk_files(root: Path) -> Iterable[Path]:
    if not root.exists():
        return []
    if root.is_file() or root.is_symlink():
        return [root]
    result: list[Path] = []
    for current, directories, files in os.walk(root, followlinks=False):
        current_path = Path(current)
        directories[:] = sorted(name for name in directories if not (current_path / name).is_symlink())
        for name in sorted(files):
            result.append(current_path / name)
        for name in sorted(path.name for path in current_path.iterdir() if path.is_symlink()):
            result.append(current_path / name)
    return result


def snapshot_project(
    project_root: Path,
    engine: dict[str, Any],
    *,
    exclude_roots: Iterable[Path] = (),
    mode: str = "metadata",
) -> dict[str, Any]:
    if mode not in INTEGRITY_MODES:
        raise WorkspaceError(f"unsupported integrity mode: {mode}")
    if mode == "off":
        return {"mode": mode, "files": {}}
    project = project_root.resolve()
    excluded = [path.resolve() for path in exclude_roots]
    records: dict[str, Any] = {}
    for protected in protected_absolute_paths(project, engine):
        if not protected.exists() and not protected.is_symlink():
            continue
        for path in _walk_files(protected):
            resolved = path.resolve(strict=False)
            if any(resolved == item or resolved.is_relative_to(item) for item in excluded):
                continue
            try:
                relative = path.relative_to(project).as_posix()
                info = path.lstat()
            except (OSError, ValueError):
                continue
            record: dict[str, Any] = {
                "size": info.st_size,
                "mtime_ns": info.st_mtime_ns,
                "mode": stat.S_IFMT(info.st_mode),
            }
            if path.is_symlink():
                try:
                    record["symlink"] = os.readlink(path)
                except OSError:
                    record["symlink"] = "UNKNOWN"
            elif mode == "full" and path.is_file():
                record["sha256"] = _file_sha256(path)
            records[relative] = record
    return {"mode": mode, "files": records}


def compare_snapshots(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    before_files = before.get("files", {})
    after_files = after.get("files", {})
    changed = sorted(path for path in set(before_files) | set(after_files) if before_files.get(path) != after_files.get(path))
    return {"ok": not changed, "changed_paths": changed, "mode": before.get("mode")}


def find_symlink_paths(root: Path) -> list[str]:
    if not root.exists() or not root.is_dir():
        return []
    found: list[str] = []
    for current, directories, files in os.walk(root, followlinks=False):
        current_path = Path(current)
        for name in list(directories):
            candidate = current_path / name
            if candidate.is_symlink():
                found.append(candidate.relative_to(root).as_posix())
                directories.remove(name)
        for name in files:
            candidate = current_path / name
            if candidate.is_symlink():
                found.append(candidate.relative_to(root).as_posix())
    return sorted(set(found))


def collect_file_records(root: Path) -> dict[str, dict[str, Any]]:
    if not root.exists():
        return {}
    records: dict[str, dict[str, Any]] = {}
    for path in _walk_files(root):
        try:
            relative = path.relative_to(root).as_posix()
            info = path.lstat()
        except (OSError, ValueError):
            continue
        if path.is_symlink():
            records[relative] = {
                "kind": "symlink",
                "target": os.readlink(path),
                "size": info.st_size,
            }
        elif path.is_file():
            records[relative] = {
                "kind": "file",
                "sha256": _file_sha256(path),
                "size": info.st_size,
            }
    return records


def compare_trees(existing_root: Path, staged_root: Path) -> dict[str, list[str]]:
    existing = collect_file_records(existing_root)
    staged = collect_file_records(staged_root)
    creates = sorted(path for path in staged if path not in existing)
    updates = sorted(path for path in staged if path in existing and staged[path] != existing[path])
    deletes = sorted(path for path in existing if path not in staged)
    unchanged = sorted(path for path in staged if path in existing and staged[path] == existing[path])
    return {"creates": creates, "updates": updates, "deletes": deletes, "unchanged": unchanged}


def read_managed_manifest(vault_root: Path) -> dict[str, Any]:
    path = vault_root / MANAGED_MANIFEST_NAME
    if not path.is_file():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _managed_policy(relative: str) -> str:
    if relative == "wiki/game/traceability.json":
        return "derived"
    if relative in (".llm-wiki.json", MANAGED_MANIFEST_NAME):
        return "metadata"
    if relative.startswith((".agents/", ".claude/", ".session-memory/scripts/")):
        return "system-managed"
    if relative in ("tools/game_trace.py", "tools/game_providers.py", "tools/game_provider_config.py", "tools/kb.py") or relative.startswith("tools/ingest-adapters/"):
        return "system-managed"
    if relative.startswith(("templates/", "instructions/")):
        return "managed-proposal"
    if relative in ("CLAUDE.md", "AGENTS.md", "wiki/CLAUDE.md", "wiki/game/model.md", "wiki/game/index.md"):
        return "managed-proposal"
    return "seeded-user-editable"


def write_managed_manifest(
    staged_vault: Path,
    existing_vault: Path,
    workspace: WorkspacePaths,
    engine: dict[str, Any],
    *,
    installation_mode: str,
) -> dict[str, Any]:
    previous = read_managed_manifest(existing_vault)
    previous_files = previous.get("managed_files") if isinstance(previous.get("managed_files"), dict) else {}
    diff = compare_trees(existing_vault, staged_vault)
    staged_records = collect_file_records(staged_vault)
    managed: dict[str, Any] = {
        key: value
        for key, value in previous_files.items()
        if isinstance(key, str) and isinstance(value, dict) and key in staged_records
    }
    for relative in sorted(set(diff["creates"]) | set(diff["updates"])):
        if relative == MANAGED_MANIFEST_NAME:
            continue
        record = staged_records.get(relative)
        if not record:
            continue
        managed[relative] = {
            "owner": "llm-wiki-bootstrap",
            "policy": _managed_policy(relative),
            **record,
        }
    for relative in diff["deletes"]:
        managed.pop(relative, None)

    manifest = {
        "schema_version": MANAGED_MANIFEST_SCHEMA_VERSION,
        "owner": "llm-wiki-bootstrap",
        "generated_at": utc_now(),
        "installation_mode": installation_mode,
        "write_policy": "vault-only",
        "temporary_write_policy": "transaction-root-only",
        "layout": workspace.layout,
        "project_root": workspace.project_root_reference,
        "project_root_kind": workspace.project_root_reference_kind,
        "vault_root": ".",
        "engine": {
            key: engine.get(key)
            for key in (
                "id",
                "display_name",
                "environment",
                "evidence",
                "protected_roots",
                "generated_roots",
                "source_roots",
            )
        },
        "managed_files": dict(sorted(managed.items())),
    }
    path = staged_vault / MANAGED_MANIFEST_NAME
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


def _known_managed_path(relative: str) -> bool:
    return relative in KNOWN_MANAGED_FILES or relative.startswith(KNOWN_MANAGED_PREFIXES)


def _symlink_ancestor(path: Path, stop: Path) -> str | None:
    current = path
    stop_resolved = stop.resolve()
    while True:
        if current.exists() and current.is_symlink():
            return str(current)
        if current == stop or current.parent == current:
            return None
        try:
            if not current.resolve(strict=False).is_relative_to(stop_resolved):
                return str(current)
        except OSError:
            return str(current)
        current = current.parent


def build_write_plan(
    existing_vault: Path,
    staged_vault: Path,
    workspace: WorkspacePaths,
    engine: dict[str, Any],
    *,
    backed_up_paths: Iterable[str] = (),
    adopt_existing_vault: bool = False,
) -> dict[str, Any]:
    diff = compare_trees(existing_vault, staged_vault)
    previous_manifest = read_managed_manifest(existing_vault)
    previous_files = previous_manifest.get("managed_files") if isinstance(previous_manifest.get("managed_files"), dict) else {}
    backed_up = set(backed_up_paths)
    collisions: list[dict[str, str]] = []
    warnings: list[str] = list(engine.get("warnings", []))

    if existing_vault.exists() and any(existing_vault.iterdir()) and not (existing_vault / ".llm-wiki.json").is_file():
        if not adopt_existing_vault:
            collisions.append(
                {
                    "path": str(existing_vault),
                    "reason": "vault root is non-empty but is not an LLM Wiki; pass --adopt-existing-vault after reviewing dry-run",
                }
            )

    existing_records = collect_file_records(existing_vault)
    for relative in diff["updates"]:
        prior = previous_files.get(relative) if isinstance(previous_files, dict) else None
        if isinstance(prior, dict):
            policy = prior.get("policy")
            current = existing_records.get(relative, {})
            expected_hash = prior.get("sha256")
            current_hash = current.get("sha256") if isinstance(current, dict) else None
            if policy in ("seeded-user-editable", "managed-proposal") and expected_hash and current_hash != expected_hash:
                collisions.append({"path": relative, "reason": "user-edited managed file would be changed instead of proposed"})
            continue
        if relative in backed_up or _known_managed_path(relative):
            warnings.append(f"legacy managed path will be updated with backup/proposal protection: {relative}")
            continue
        collisions.append({"path": relative, "reason": "existing unmanaged file would be changed"})
    for relative in diff["deletes"]:
        collisions.append({"path": relative, "reason": "installer does not delete existing vault files automatically"})

    protected_writes: list[str] = []
    symlink_violations: list[str] = [
        f"existing vault symlink is not followed: {relative}"
        for relative in find_symlink_paths(existing_vault)
    ]
    write_relatives = [*diff["creates"], *diff["updates"], *diff["deletes"]]
    protected = protected_absolute_paths(workspace.project_root, engine)
    for relative in write_relatives:
        final = (workspace.vault_root / relative).resolve(strict=False)
        if not workspace.legacy_in_place:
            for protected_root in protected:
                if final == protected_root or final.is_relative_to(protected_root):
                    protected_writes.append(relative)
                    break
        ancestor = _symlink_ancestor(workspace.vault_root / relative, workspace.vault_root.parent)
        if ancestor:
            symlink_violations.append(f"{relative} via {ancestor}")

    layout_errors: list[str] = []
    if engine.get("ambiguous"):
        layout_errors.append("engine/project-root detection is ambiguous")
    if workspace.legacy_in_place:
        warnings.append("legacy-in-place was explicitly enabled; sidecar remains the recommended layout")
    if workspace.layout == "embedded" and workspace.vault_root != workspace.project_root / ".llm-wiki":
        layout_errors.append("embedded vault is not isolated under .llm-wiki")

    safe = not (collisions or protected_writes or symlink_violations or layout_errors)
    return {
        "schema_version": WORKSPACE_SCHEMA_VERSION,
        "safe_to_apply": safe,
        "workspace": workspace.to_dict(),
        "engine": engine,
        "write_policy": "vault-only",
        "temporary_write_policy": "transaction-root-only",
        "reads": {
            "project_root": str(workspace.project_root),
            "source_roots": [str(workspace.project_root / item) for item in engine.get("source_roots", [])],
            "protected_roots": [str(path) for path in protected],
        },
        "writes": {
            "creates": diff["creates"],
            "updates": diff["updates"],
            "deletes": diff["deletes"],
            "unchanged_count": len(diff["unchanged"]),
            "final_root": str(workspace.vault_root),
            "temporary_root": str(workspace.transaction_root),
        },
        "collisions": collisions,
        "protected_path_writes": sorted(set(protected_writes)),
        "symlink_violations": sorted(set(symlink_violations)),
        "layout_errors": layout_errors,
        "warnings": sorted(set(warnings)),
    }


def make_staging_directory(workspace: WorkspacePaths) -> Path:
    workspace.transaction_root.mkdir(parents=True, exist_ok=True)
    stage = workspace.transaction_root / f"{workspace.vault_root.name}.stage-{uuid.uuid4().hex}"
    stage.mkdir(parents=True, exist_ok=False)
    return stage


def seed_staging_from_existing(existing_vault: Path, stage: Path) -> list[str]:
    """Copy an existing vault without ever following symlinks.

    Symlink locations are replaced by inert placeholders in staging so later
    installers cannot write through them. The write plan reports every original
    symlink as unsafe, therefore the staged tree can never be applied until the
    user removes or relocates the link.
    """
    if not existing_vault.exists():
        return []
    if not existing_vault.is_dir():
        raise WorkspaceError(f"vault root exists but is not a directory: {existing_vault}")
    symlinks: list[str] = []
    for current, directories, files in os.walk(existing_vault, followlinks=False):
        current_path = Path(current)
        relative_current = current_path.relative_to(existing_vault)
        stage_current = stage / relative_current
        stage_current.mkdir(parents=True, exist_ok=True)

        for name in list(directories):
            source = current_path / name
            destination = stage_current / name
            if source.is_symlink():
                symlinks.append(source.relative_to(existing_vault).as_posix())
                destination.mkdir(parents=True, exist_ok=True)
                directories.remove(name)
            else:
                destination.mkdir(parents=True, exist_ok=True)

        for name in files:
            source = current_path / name
            destination = stage_current / name
            if source.is_symlink():
                symlinks.append(source.relative_to(existing_vault).as_posix())
                destination.write_text("", encoding="utf-8")
            else:
                shutil.copy2(source, destination)
    return sorted(set(symlinks))


def verify_managed_manifest(vault_root: Path) -> dict[str, Any]:
    manifest = read_managed_manifest(vault_root)
    if not manifest:
        return {"ok": False, "errors": [f"missing or invalid {MANAGED_MANIFEST_NAME}"], "warnings": []}
    managed = manifest.get("managed_files")
    if not isinstance(managed, dict):
        return {"ok": False, "errors": ["managed_files must be an object"], "warnings": []}
    errors: list[str] = []
    warnings: list[str] = []
    for relative, metadata in managed.items():
        if not isinstance(relative, str) or not isinstance(metadata, dict):
            errors.append("invalid managed file entry")
            continue
        path = vault_root / relative
        policy = metadata.get("policy")
        if not path.exists() and not path.is_symlink():
            if policy in ("system-managed", "metadata", "derived"):
                errors.append(f"missing managed file: {relative}")
            else:
                warnings.append(f"seeded file no longer exists: {relative}")
            continue
        if path.is_file() and metadata.get("sha256"):
            current = _file_sha256(path)
            if current != metadata.get("sha256"):
                if policy in ("system-managed", "metadata", "derived"):
                    errors.append(f"managed file hash mismatch: {relative}")
                else:
                    warnings.append(f"user-editable seeded file changed: {relative}")
    return {"ok": not errors, "errors": errors, "warnings": warnings}


def apply_staged_vault(
    stage: Path,
    workspace: WorkspacePaths,
    plan: dict[str, Any],
    *,
    post_apply_verify: Callable[[Path], dict[str, Any]] | None = None,
    keep_backup: bool = True,
) -> dict[str, Any]:
    if not plan.get("safe_to_apply"):
        raise WorkspaceError("refusing to apply an unsafe write plan")
    vault = workspace.vault_root
    vault.parent.mkdir(parents=True, exist_ok=True)
    workspace.transaction_root.mkdir(parents=True, exist_ok=True)
    try:
        stage_device = stage.stat().st_dev
        parent_device = vault.parent.stat().st_dev
    except OSError as error:
        raise WorkspaceError(f"cannot verify atomic-rename filesystem: {error}") from error
    if stage_device != parent_device:
        raise WorkspaceError("staging and vault roots are on different filesystems; atomic rename is unavailable")

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    backup = workspace.transaction_root / f"{vault.name}.backup-{timestamp}"
    failed = workspace.transaction_root / f"{vault.name}.failed-{timestamp}"
    had_existing = vault.exists()
    if had_existing:
        vault.rename(backup)
    try:
        stage.rename(vault)
        verification = post_apply_verify(vault) if post_apply_verify else {"ok": True}
        if not verification.get("ok"):
            raise WorkspaceError("post-apply verification failed: " + "; ".join(verification.get("errors", [])))
    except Exception:
        if vault.exists():
            vault.rename(failed)
        if had_existing and backup.exists():
            backup.rename(vault)
        raise

    backup_result: str | None = None
    if had_existing and backup.exists():
        if keep_backup:
            backup_result = str(backup)
        else:
            shutil.rmtree(backup)
    return {
        "ok": True,
        "vault_root": str(vault),
        "backup_root": backup_result,
        "verification": verification,
        "mutation_started": True,
    }


def cleanup_staging(path: Path) -> None:
    parent = path.parent
    if path.exists():
        shutil.rmtree(path, ignore_errors=True)
    if parent.name == TRANSACTION_DIRECTORY_NAME and parent.is_dir():
        try:
            if not any(parent.iterdir()):
                parent.rmdir()
        except OSError:
            pass
