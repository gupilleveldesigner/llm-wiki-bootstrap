import argparse
import json
import os
import shutil
import tempfile
import uuid
from datetime import datetime
from pathlib import Path

from template_render import render_template


ASSETS = Path(__file__).resolve().parent.parent / "assets"
MANIFEST_NAME = ".llm-wiki.json"
SCHEMA_VERSION = 3

BASE_DIRECTORIES = (
    "raw/inbox",
    "raw/personal",
    "raw/journal",
    "raw/archive",
    "raw/assets",
    "raw/reference/articles",
    "raw/reference/youtube",
    "raw/reference/podcasts",
    "raw/reference/books",
    "raw/reference/research",
    "wiki/entities",
    "wiki/concepts",
    "wiki/projects",
    "wiki/sources",
    "Output",
    "instructions",
    "templates",
    ".agents/skills",
    ".claude/skills",
    ".session-memory/scripts",
    ".session-memory/pending",
    ".session-memory/sessions",
    ".session-memory/transactions",
)

PROFILE_DIRECTORIES = {
    "standard": (),
    "evidence": (
        "wiki/claims",
        "wiki/decisions",
        "wiki/canon",
        "wiki/conflicts",
        "wiki/experiments",
        "wiki/normalized",
        "wiki/questions/open",
        "wiki/questions/answered",
        "wiki/questions/blocked",
        "tools",
        ".evidence-kb",
        ".wiki-cache/normalized",
        ".wiki-cache/index",
        ".wiki-cache/embeddings",
    ),
}

BASE_DOCS = (
    ("CLAUDE.md.template", "CLAUDE.md", True),
    ("AGENTS.md.template", "AGENTS.md", True),
    ("raw-CLAUDE.md.template", "raw/CLAUDE.md", True),
    ("wiki-CLAUDE.md.template", "wiki/CLAUDE.md", True),
    ("output-CLAUDE.md.template", "Output/CLAUDE.md", True),
    ("instructions/wiki-operations.md", "instructions/wiki-operations.md", False),
    ("wiki-index.md.template", "wiki/index.md", True),
    ("wiki-overview.md.template", "wiki/overview.md", True),
    ("wiki-questions.md.template", "wiki/questions.md", True),
    ("wiki-log.md.template", "wiki/log.md", True),
    ("wiki-taxonomy.json.template", "wiki/taxonomy.json", True),
    ("root-log.md.template", "log.md", True),
    ("changelog.md.template", "changelog.md", True),
    ("graphifyignore.template", ".graphifyignore", False),
    ("session-memory-config.json.template", ".session-memory/config.json", True),
)

PROFILE_DOCS = {
    "standard": (),
    "evidence": (
        ("profiles/evidence/docs/evidence-model.md.template", "wiki/evidence-model.md", True),
        ("profiles/evidence/docs/canon-overview.md.template", "wiki/canon/overview.md", True),
        ("profiles/evidence/docs/evidence-operations.md", "instructions/evidence-operations.md", False),
        ("profiles/evidence/docs/evidence-kb.md.template", "instructions/evidence-kb.md", True),
        ("profiles/evidence/docs/cache.gitignore", ".wiki-cache/.gitignore", False),
    ),
}

PROFILE_RUNTIME_FILES = {
    "standard": (),
    "evidence": (("profiles/evidence/runtime/kb.py", "tools/kb.py"),),
}

BASE_SKILLS = ("ingest", "query", "lint", "session-memory", "brief-tuner", "wiki-audit")
PROFILE_SKILLS = {
    "standard": (),
    "evidence": ("canon-review",),
}
ALL_SKILLS = tuple(dict.fromkeys(BASE_SKILLS + tuple(skill for values in PROFILE_SKILLS.values() for skill in values)))
PROFILES = tuple(PROFILE_DIRECTORIES)

PROPOSABLE_DOCS = {
    "CLAUDE.md",
    "AGENTS.md",
    "log.md",
    "changelog.md",
    "instructions/wiki-operations.md",
    ".graphifyignore",
    "wiki/taxonomy.json",
}

PROFILE_PROPOSABLE_DOCS = {
    "wiki/evidence-model.md",
    "instructions/evidence-operations.md",
    "instructions/evidence-kb.md",
}

EVIDENCE_CONTRACT_FILES = (
    ("profiles/evidence/docs/evidence-model.md.template", "wiki/evidence-model.md"),
    ("profiles/evidence/docs/evidence-operations.md", "instructions/evidence-operations.md"),
    ("profiles/evidence/docs/evidence-kb.md.template", "instructions/evidence-kb.md"),
    ("profiles/evidence/runtime/kb.py", "tools/kb.py"),
    ("profiles/evidence/templates/source-record.md", "templates/evidence/source-record.md"),
    ("profiles/evidence/templates/decision.md", "templates/evidence/decision.md"),
    ("skills-bundle/agents-skills/ingest/scripts/semantic_contract.py", ".agents/skills/ingest/scripts/semantic_contract.py"),
    ("skills-bundle/agents-skills/ingest/scripts/stitch_explicit_links.py", ".agents/skills/ingest/scripts/stitch_explicit_links.py"),
)

EVIDENCE_CONTRACT_MARKERS = {
    "profiles/evidence/docs/evidence-model.md.template": "wiki/decisions/",
    "profiles/evidence/docs/evidence-operations.md": "semantic_status: pending|partial|reviewed",
    "profiles/evidence/docs/evidence-kb.md.template": "Project Decision 계약",
    "profiles/evidence/runtime/kb.py": "decision_to_project_to_evidence_to_raw",
    "profiles/evidence/templates/source-record.md": "semantic_status: pending",
    "profiles/evidence/templates/decision.md": "chronology:",
    "skills-bundle/agents-skills/ingest/scripts/semantic_contract.py": "long Source semantic review requires",
    "skills-bundle/agents-skills/ingest/scripts/stitch_explicit_links.py": "semantic_edges_added",
}

EVIDENCE_ROUTER_MARKER = "<!-- LLM-WIKI:EVIDENCE-PROFILE -->"


def find_symlink_paths(target: Path) -> list[str]:
    if target.is_symlink():
        return ["."]
    if not target.exists():
        return []
    links: list[str] = []
    for current, directories, files in os.walk(target, followlinks=False):
        current_path = Path(current)
        for name in [*directories, *files]:
            candidate = current_path / name
            if candidate.is_symlink():
                links.append(candidate.relative_to(target).as_posix())
    return sorted(set(links))


def assert_symlink_safe(target: Path) -> None:
    links = find_symlink_paths(target)
    if links:
        preview = ", ".join(links[:10])
        suffix = "" if len(links) <= 10 else f" (+{len(links) - 10} more)"
        raise ValueError(f"target contains symlinks; refusing writes that may escape the Wiki root: {preview}{suffix}")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as file:
        file.write(text.replace("\r\n", "\n").replace("\r", "\n"))


def seed_ingest_ledger(target: Path, *, propose_existing: bool = False) -> list[str]:
    ledger = {
        "version": 2,
        "updated": datetime.now().astimezone().isoformat(),
        "graphify": "not_checked",
        "counts": {
            "pending": 0,
            "verified": 0,
            "skipped": 0,
            "rejected": 0,
            "catalog_only": 0,
            "semantic_pending": 0,
            "semantic_partial": 0,
            "semantic_reviewed": 0,
        },
        "completion": "partial",
        "errors": [],
        "sources": [],
    }
    destination = target / "wiki" / "ingest-ledger.json"
    content = json.dumps(ledger, ensure_ascii=False, indent=2) + "\n"
    if destination.exists() and propose_existing and destination.read_text(encoding="utf-8") != content:
        proposal = destination.with_name(destination.name + ".wiki-proposed")
        write_text(proposal, content)
        return [proposal.relative_to(target).as_posix()]
    write_text(destination, content)
    return []


def load_config(config_path: Path, keys: tuple[str, ...]) -> dict:
    with config_path.open(encoding="utf-8", newline="") as file:
        config = json.load(file)
    for key in keys:
        if not isinstance(config.get(key), str):
            raise ValueError(f"config key '{key}' must be a string")
    return config


def read_manifest(target: Path) -> dict | None:
    path = target / MANIFEST_NAME
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ValueError(f"invalid {MANIFEST_NAME}: {error}") from error
    if not isinstance(data, dict):
        raise ValueError(f"invalid {MANIFEST_NAME}: root must be an object")
    profile = data.get("profile", "standard")
    if profile not in PROFILES:
        raise ValueError(f"unsupported vault profile in {MANIFEST_NAME}: {profile}")
    return data


def resolve_profile(target: Path, requested_profile: str | None, mode: str) -> tuple[str, str]:
    manifest = read_manifest(target) if target.exists() else None
    existing_profile = str(manifest.get("profile", "standard")) if manifest else "standard"
    profile = requested_profile or (existing_profile if mode == "upgrade" else "standard")
    if profile not in PROFILES:
        raise ValueError(f"unsupported vault profile: {profile}")
    if mode == "upgrade" and existing_profile == "evidence" and profile == "standard":
        raise ValueError("cannot downgrade an evidence profile to standard with upgrade")
    return profile, existing_profile


def write_manifest(target: Path, project_name: str, profile: str) -> None:
    path = target / MANIFEST_NAME
    previous = read_manifest(target) or {}
    now = datetime.now().astimezone().isoformat()
    manifest = dict(previous)
    manifest.update(
        {
            "schema_version": SCHEMA_VERSION,
            "profile": profile,
            "raw_immutable": True,
            "created_with": "llm-wiki-bootstrap",
            "project_name": project_name,
            "updated_at": now,
        }
    )
    manifest.setdefault("created_at", now)
    write_text(path, json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")


def skills_for_profile(profile: str) -> tuple[str, ...]:
    return BASE_SKILLS + PROFILE_SKILLS[profile]


def install_skills(target: Path, profile: str, *, propose_existing: bool = False) -> list[str]:
    selected = skills_for_profile(profile)
    proposals: list[str] = []
    roots = (
        (ASSETS / "skills-bundle/agents-skills", target / ".agents/skills"),
        (ASSETS / "skills-bundle/claude-adapters", target / ".claude/skills"),
    )
    for source_root, destination_root in roots:
        for skill in selected:
            source = source_root / skill
            if not source.is_dir():
                raise FileNotFoundError(f"bundled skill is missing: {source}")
            for source_file in source.rglob("*"):
                if not source_file.is_file() or "__pycache__" in source_file.parts or source_file.suffix == ".pyc":
                    continue
                relative = source_file.relative_to(source)
                if relative.name == "SKILL.md.bundled":
                    relative = relative.with_name("SKILL.md")
                destination = destination_root / skill / relative
                if destination.exists():
                    if destination.read_bytes() == source_file.read_bytes():
                        continue
                    if propose_existing:
                        proposal = destination.with_name(destination.name + ".wiki-proposed")
                        proposal.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(source_file, proposal)
                        proposals.append(proposal.relative_to(target).as_posix())
                        continue
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source_file, destination)
    return proposals


def validate_profile_bundle(profile: str) -> None:
    if profile != "evidence":
        return
    missing = [source for source, _ in EVIDENCE_CONTRACT_FILES if not (ASSETS / source).is_file()]
    marker_errors = [
        f"{source} missing marker {marker!r}"
        for source, marker in EVIDENCE_CONTRACT_MARKERS.items()
        if (ASSETS / source).is_file() and marker not in (ASSETS / source).read_text(encoding="utf-8")
    ]
    if missing or marker_errors:
        details = [*(f"missing {path}" for path in missing), *marker_errors]
        raise RuntimeError("invalid Evidence bundle: " + "; ".join(details))


def install_profile_runtime(
    target: Path,
    profile: str,
    *,
    propose_existing: bool = False,
) -> tuple[list[str], list[str]]:
    installed: list[str] = []
    proposals: list[str] = []
    for source_name, destination_name in PROFILE_RUNTIME_FILES[profile]:
        source = ASSETS / source_name
        if not source.is_file():
            raise FileNotFoundError(f"profile runtime is missing: {source}")
        destination = target / destination_name
        if destination.exists() and destination.read_bytes() != source.read_bytes() and propose_existing:
            proposal = destination.with_name(destination.name + ".wiki-proposed")
            write_text(proposal, source.read_text(encoding="utf-8"))
            proposals.append(proposal.relative_to(target).as_posix())
            continue
        write_text(destination, source.read_text(encoding="utf-8"))
        installed.append(destination_name)
    return installed, proposals


def verify_profile_installation(target: Path, profile: str) -> dict[str, object]:
    if profile != "evidence":
        return {"status": "not_applicable", "checked": [], "pending": [], "errors": []}
    missing = [destination for _, destination in EVIDENCE_CONTRACT_FILES if not (target / destination).is_file()]
    errors = [f"missing installed Evidence file: {path}" for path in missing]
    pending: list[str] = []
    for source_name, destination_name in EVIDENCE_CONTRACT_FILES:
        marker = EVIDENCE_CONTRACT_MARKERS.get(source_name)
        destination = target / destination_name
        if marker and destination.is_file() and marker not in destination.read_text(encoding="utf-8"):
            proposal = destination.with_name(destination.name + ".wiki-proposed")
            if proposal.is_file() and marker in proposal.read_text(encoding="utf-8"):
                pending.append(proposal.relative_to(target).as_posix())
            else:
                errors.append(f"installed Evidence file lacks marker {marker!r}: {destination_name}")
    if not (target / "wiki/decisions").is_dir():
        errors.append("missing installed Evidence directory: wiki/decisions")
    return {
        "status": "failed" if errors else ("pending" if pending else "ok"),
        "checked": [destination for _, destination in EVIDENCE_CONTRACT_FILES],
        "pending": pending,
        "errors": errors,
    }


def profile_replacements(profile: str) -> dict[str, str]:
    if profile == "evidence":
        return {
            "{{VAULT_PROFILE}}": "evidence",
            "{{PROFILE_SUMMARY}}": "Evidence Research — Raw → Source → Claim 또는 Project Decision → reviewed Canon",
            "{{PROFILE_ROUTER}}": (
                f"{EVIDENCE_ROUTER_MARKER}\n"
                "- Evidence profile: `wiki/evidence-model.md`와 `instructions/evidence-operations.md`를 먼저 읽고, "
                "Canon 승격 검토에는 설치된 `canon-review` 스킬을 사용한다.\n"
                "- Evidence KB 등록·Claim·Decision·Canon·검색·추적은 `instructions/evidence-kb.md`를 읽고 "
                "`tools/kb.py`를 사용한다."
            ),
        }
    return {
        "{{VAULT_PROFILE}}": "standard",
        "{{PROFILE_SUMMARY}}": "Standard — raw 원문을 wiki 지식층으로 요약·연결",
        "{{PROFILE_ROUTER}}": "",
    }


def render_asset(source_name: str, replacements: dict[str, str]) -> str:
    return render_template(ASSETS / "docs" / source_name, replacements)


def copy_profile_templates(
    target: Path,
    profile: str,
    *,
    overwrite: bool,
    propose_existing: bool = False,
) -> tuple[int, list[str]]:
    source_root = ASSETS / "profiles" / profile / "templates"
    if not source_root.is_dir():
        return 0, []
    copied = 0
    proposals: list[str] = []
    destination_root = target / "templates" / profile
    for source in source_root.rglob("*"):
        if not source.is_file():
            continue
        destination = destination_root / source.relative_to(source_root)
        if destination.exists():
            if destination.read_bytes() == source.read_bytes():
                continue
            if propose_existing:
                proposal = destination.with_name(destination.name + ".wiki-proposed")
                shutil.copy2(source, proposal)
                proposals.append(proposal.relative_to(target).as_posix())
                continue
            if not overwrite:
                continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        copied += 1
    return copied, proposals


def install_profile_docs(
    target: Path,
    profile: str,
    replacements: dict[str, str],
    *,
    propose_existing: bool,
) -> tuple[list[str], list[str]]:
    rendered: list[str] = []
    proposals: list[str] = []
    for source_name, destination_name, render in PROFILE_DOCS[profile]:
        source = ASSETS / source_name
        content = render_template(source, replacements) if render else source.read_text(encoding="utf-8")
        destination = target / destination_name
        if destination.exists():
            if destination.read_text(encoding="utf-8") == content:
                rendered.append(destination_name)
                continue
            if propose_existing and destination_name in PROFILE_PROPOSABLE_DOCS:
                proposal = destination.with_name(destination.name + ".wiki-proposed")
                write_text(proposal, content)
                proposals.append(proposal.relative_to(target).as_posix())
                continue
            rendered.append(destination_name)
            continue
        write_text(destination, content)
        rendered.append(destination_name)
    return rendered, proposals


def propose_profile_router_docs(target: Path, profile: str) -> list[str]:
    if profile != "evidence":
        return []
    block = (
        f"\n\n{EVIDENCE_ROUTER_MARKER}\n"
        "## Evidence profile overlay\n\n"
        "- `.llm-wiki.json`의 `profile: evidence`가 활성 상태다.\n"
        "- Wiki ingest/query/lint 전에 `wiki/evidence-model.md`와 "
        "`instructions/evidence-operations.md`를 읽는다.\n"
        "- Claim → Evidence/Conflict/Experiment → reviewed Canon 경계를 지키며 Canon 자동 승격을 금지한다.\n"
        "- Canon 검토에는 설치된 `canon-review` 스킬을 사용한다.\n"
    )
    proposals: list[str] = []
    for relative in ("CLAUDE.md", "AGENTS.md", "wiki/CLAUDE.md"):
        destination = target / relative
        if not destination.is_file():
            continue
        current = destination.read_text(encoding="utf-8")
        if EVIDENCE_ROUTER_MARKER in current:
            continue
        proposal = destination.with_name(destination.name + ".wiki-proposed")
        write_text(proposal, current.rstrip() + block)
        proposals.append(proposal.relative_to(target).as_posix())
    return proposals


def project_name_for_upgrade(target: Path, config_path: Path) -> str:
    manifest = read_manifest(target)
    if manifest and isinstance(manifest.get("project_name"), str) and manifest["project_name"]:
        return str(manifest["project_name"])
    config_destination = target / ".session-memory/config.json"
    if config_destination.is_file():
        try:
            configured = json.loads(config_destination.read_text(encoding="utf-8")).get("project_name")
            if isinstance(configured, str) and configured:
                return configured
        except (OSError, json.JSONDecodeError):
            pass
    return load_config(config_path, ("project_name",))["project_name"]


def _upgrade_in_place(target: Path, config_path: Path, profile: str | None = None) -> dict:
    if not ((target / "raw").is_dir() and (target / "wiki").is_dir()):
        raise ValueError("target is not an LLM Wiki; use --mode new or migrate")
    assert_symlink_safe(target)

    previous_manifest = read_manifest(target) or {}
    previous_schema_version = previous_manifest.get("schema_version", 1)
    try:
        previous_schema_version = int(previous_schema_version)
    except (TypeError, ValueError):
        previous_schema_version = 1
    resolved_profile, previous_profile = resolve_profile(target, profile, "upgrade")
    knowledge_migration_pending = resolved_profile == "evidence" and previous_schema_version < SCHEMA_VERSION
    validate_profile_bundle(resolved_profile)
    project_name = project_name_for_upgrade(target, config_path)
    replacements = {
        "{{PROJECT_NAME}}": project_name,
        "{{DOMAIN_SUMMARY}}": project_name,
        "{{TODAY}}": datetime.now().strftime("%Y-%m-%d"),
        **profile_replacements(resolved_profile),
    }

    backup_dir = None
    backup_sources = [
        target / root / skill
        for root in (".agents/skills", ".claude/skills")
        for skill in ALL_SKILLS
        if (target / root / skill).is_dir()
    ]
    runtime = target / ".session-memory/scripts/session_memory.py"
    profile_runtime_sources = [
        target / destination
        for _, destination in PROFILE_RUNTIME_FILES[resolved_profile]
        if (target / destination).is_file()
    ]
    if backup_sources or runtime.is_file() or profile_runtime_sources:
        backup_name = f"{datetime.now().strftime('%Y%m%d-%H%M%S-%f')}-{uuid.uuid4().hex[:8]}"
        backup_dir = target / ".wiki-upgrade-bak" / backup_name
        for source in backup_sources:
            destination = backup_dir / source.relative_to(target)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(source, destination)
        if runtime.is_file():
            destination = backup_dir / runtime.relative_to(target)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(runtime, destination)
        for source in profile_runtime_sources:
            destination = backup_dir / source.relative_to(target)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)

    for directory in BASE_DIRECTORIES + PROFILE_DIRECTORIES[resolved_profile]:
        (target / directory).mkdir(parents=True, exist_ok=True)

    install_skills(target, resolved_profile)
    profile_runtime, _ = install_profile_runtime(target, resolved_profile)
    for directory in ("pending", "sessions", "transactions", "scripts"):
        (target / ".session-memory" / directory).mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ASSETS / "session-memory-runtime/session_memory.py", runtime)

    config_destination = target / ".session-memory/config.json"
    if not config_destination.exists():
        source = ASSETS / "docs/session-memory-config.json.template"
        write_text(config_destination, render_template(source, {"{{PROJECT_NAME}}": project_name}))

    copied_templates = 0
    for source in (ASSETS / "templates").rglob("*"):
        if source.is_file():
            destination = target / "templates" / source.relative_to(ASSETS / "templates")
            if not destination.exists():
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, destination)
                copied_templates += 1
    copied_profile_templates, profile_template_proposals = copy_profile_templates(
        target,
        resolved_profile,
        overwrite=False,
        propose_existing=True,
    )
    copied_templates += copied_profile_templates

    proposals: list[str] = []
    proposals.extend(profile_template_proposals)
    router_proposals = propose_profile_router_docs(target, resolved_profile)
    proposals.extend(router_proposals)
    source = ASSETS / "docs/instructions/wiki-operations.md"
    destination = target / "instructions/wiki-operations.md"
    content = source.read_text(encoding="utf-8")
    if not destination.exists():
        write_text(destination, content)
    elif destination.read_text(encoding="utf-8") != content:
        proposal = destination.with_name(destination.name + ".wiki-proposed")
        write_text(proposal, content)
        proposals.append(proposal.relative_to(target).as_posix())

    profile_docs, profile_proposals = install_profile_docs(
        target,
        resolved_profile,
        replacements,
        propose_existing=True,
    )
    proposals.extend(profile_proposals)

    graphifyignore_source = ASSETS / "docs/graphifyignore.template"
    graphifyignore_destination = target / ".graphifyignore"
    graphifyignore_status = "unchanged"
    graphifyignore_content = graphifyignore_source.read_text(encoding="utf-8")
    if not graphifyignore_destination.exists():
        write_text(graphifyignore_destination, graphifyignore_content)
        graphifyignore_status = "created"
    elif graphifyignore_destination.read_text(encoding="utf-8") != graphifyignore_content:
        proposal = graphifyignore_destination.with_name(graphifyignore_destination.name + ".wiki-proposed")
        write_text(proposal, graphifyignore_content)
        proposals.append(proposal.relative_to(target).as_posix())
        graphifyignore_status = "proposal"

    taxonomy_source = ASSETS / "docs/wiki-taxonomy.json.template"
    taxonomy_destination = target / "wiki" / "taxonomy.json"
    taxonomy_status = "unchanged"
    taxonomy_content = render_template(taxonomy_source, {"{{PROJECT_NAME}}": project_name})
    if not taxonomy_destination.exists():
        write_text(taxonomy_destination, taxonomy_content)
        taxonomy_status = "created"
    elif taxonomy_destination.read_text(encoding="utf-8") != taxonomy_content:
        proposal = taxonomy_destination.with_name(taxonomy_destination.name + ".wiki-proposed")
        write_text(proposal, taxonomy_content)
        proposals.append(proposal.relative_to(target).as_posix())
        taxonomy_status = "proposal"

    write_manifest(target, project_name, resolved_profile)
    profile_verification = verify_profile_installation(target, resolved_profile)
    if profile_verification["status"] == "failed":
        raise RuntimeError("Evidence installation verification failed: " + "; ".join(profile_verification["errors"]))

    return {
        "ok": True,
        "target": str(target.resolve()),
        "mode": "upgrade",
        "profile": resolved_profile,
        "previous_profile": previous_profile,
        "profile_changed": resolved_profile != previous_profile,
        "backup_dir": str(backup_dir.resolve()) if backup_dir else None,
        "proposals": proposals,
        "profile_docs": profile_docs,
        "profile_runtime": profile_runtime,
        "profile_verification": profile_verification,
        "profile_activation_pending": profile_verification["status"] == "pending" or bool(router_proposals) or knowledge_migration_pending,
        "knowledge_migration_pending": knowledge_migration_pending,
        "previous_schema_version": previous_schema_version,
        "refreshed_skills": list(skills_for_profile(resolved_profile)),
        "copied_templates": copied_templates,
        "graphifyignore": graphifyignore_status,
        "taxonomy": taxonomy_status,
    }


def _remove_empty_transaction_root(path: Path) -> None:
    try:
        if path.is_dir() and not any(path.iterdir()):
            path.rmdir()
    except OSError:
        pass


def upgrade(
    target: Path,
    config_path: Path,
    profile: str | None = None,
    *,
    transactional: bool = True,
) -> dict:
    """Upgrade a Wiki through a verified sibling staging copy.

    The original target is not touched until the staged upgrade succeeds. The
    final swap uses same-filesystem renames and restores the original target if
    post-apply verification fails.
    """
    target = target.expanduser().absolute()
    if not transactional:
        return _upgrade_in_place(target, config_path, profile)
    if not ((target / "raw").is_dir() and (target / "wiki").is_dir()):
        raise ValueError("target is not an LLM Wiki; use --mode new or migrate")
    assert_symlink_safe(target)

    transaction_root = target.parent / ".llm-wiki-transactions"
    if transaction_root.is_symlink():
        raise ValueError(f"transaction root may not be a symlink: {transaction_root}")
    transaction_root.mkdir(parents=True, exist_ok=True)
    container = Path(tempfile.mkdtemp(prefix=f"{target.name}.upgrade-", dir=transaction_root))
    stage = container / "stage"
    rollback = container / "rollback"
    failed = container / "failed"
    mutation_started = False

    try:
        shutil.copytree(target, stage)
        result = _upgrade_in_place(stage, config_path, profile)
        staged_profile = str(result.get("profile", profile or "standard"))
        staged_verification = verify_profile_installation(stage, staged_profile)
        if staged_verification["status"] == "failed":
            raise RuntimeError("staged upgrade verification failed: " + "; ".join(staged_verification["errors"]))

        target.rename(rollback)
        mutation_started = True
        try:
            stage.rename(target)
            final_verification = verify_profile_installation(target, staged_profile)
            if final_verification["status"] == "failed":
                raise RuntimeError("post-apply verification failed: " + "; ".join(final_verification["errors"]))
        except Exception:
            if target.exists():
                target.rename(failed)
            elif stage.exists():
                stage.rename(failed)
            if rollback.exists():
                rollback.rename(target)
            raise

        backup_dir = result.get("backup_dir")
        if isinstance(backup_dir, str) and backup_dir:
            result["backup_dir"] = str(target / Path(backup_dir).relative_to(stage))
        result["target"] = str(target)
        result["mutation_started"] = mutation_started
        result["transactional"] = True
        result["transaction_backup"] = None

        try:
            shutil.rmtree(rollback)
        except OSError:
            result["transaction_backup"] = str(rollback)
        if result["transaction_backup"] is None:
            container.rmdir()
            _remove_empty_transaction_root(transaction_root)
        return result
    except Exception as error:
        if not mutation_started:
            shutil.rmtree(container, ignore_errors=True)
            _remove_empty_transaction_root(transaction_root)
        elif failed.exists():
            raise RuntimeError(f"upgrade failed and the original Wiki was restored; failed staging remains at {failed}: {error}") from error
        raise


def bootstrap(target: Path, config_path: Path, mode: str = "new", profile: str | None = None) -> dict:
    if mode == "upgrade":
        return upgrade(target, config_path, profile)
    if mode not in ("new", "migrate"):
        raise ValueError(f"unsupported bootstrap mode: {mode}")
    assert_symlink_safe(target)
    if mode == "new" and target.exists() and any(target.iterdir()):
        raise ValueError("target is not empty; use --mode migrate for an existing folder")
    markers = ("raw", "wiki", ".agents", "CLAUDE.md", MANIFEST_NAME)
    looks_like_wiki = (target / MANIFEST_NAME).is_file() or ((target / "raw").is_dir() and (target / "wiki").is_dir())
    if target.exists() and (any((target / name).exists() for name in markers) if mode == "new" else looks_like_wiki):
        if mode == "migrate":
            raise ValueError("target looks like an existing LLM Wiki; use --mode upgrade")
        raise ValueError("target already contains an LLM Wiki marker")

    resolved_profile, _ = resolve_profile(target, profile, mode)
    validate_profile_bundle(resolved_profile)
    existing_entries = sorted(path.name for path in target.iterdir()) if target.exists() else []
    target.mkdir(parents=True, exist_ok=True)
    config = load_config(config_path, ("project_name", "domain_summary"))

    for directory in BASE_DIRECTORIES + PROFILE_DIRECTORIES[resolved_profile]:
        (target / directory).mkdir(parents=True, exist_ok=True)

    skill_proposals = install_skills(target, resolved_profile, propose_existing=mode == "migrate")
    profile_runtime, profile_runtime_proposals = install_profile_runtime(
        target,
        resolved_profile,
        propose_existing=mode == "migrate",
    )
    template_proposals: list[str] = []
    for source in (ASSETS / "templates").rglob("*"):
        if not source.is_file():
            continue
        destination = target / "templates" / source.relative_to(ASSETS / "templates")
        if mode == "migrate" and destination.exists() and destination.read_bytes() != source.read_bytes():
            proposal = destination.with_name(destination.name + ".wiki-proposed")
            proposal.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, proposal)
            template_proposals.append(proposal.relative_to(target).as_posix())
            continue
        if not destination.exists():
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
    profile_template_count, profile_template_proposals = copy_profile_templates(
        target,
        resolved_profile,
        overwrite=mode == "new",
        propose_existing=mode == "migrate",
    )
    session_runtime_source = ASSETS / "session-memory-runtime/session_memory.py"
    session_runtime_destination = target / ".session-memory/scripts/session_memory.py"
    session_runtime_proposals: list[str] = []
    if mode == "migrate" and session_runtime_destination.exists() and session_runtime_destination.read_bytes() != session_runtime_source.read_bytes():
        proposal = session_runtime_destination.with_name(session_runtime_destination.name + ".wiki-proposed")
        shutil.copy2(session_runtime_source, proposal)
        session_runtime_proposals.append(proposal.relative_to(target).as_posix())
    elif not session_runtime_destination.exists():
        shutil.copyfile(session_runtime_source, session_runtime_destination)

    replacements = {
        "{{PROJECT_NAME}}": config["project_name"],
        "{{DOMAIN_SUMMARY}}": config["domain_summary"],
        "{{TODAY}}": datetime.now().strftime("%Y-%m-%d"),
        **profile_replacements(resolved_profile),
    }
    rendered_docs: list[str] = []
    proposals: list[str] = [
        *skill_proposals,
        *profile_runtime_proposals,
        *template_proposals,
        *profile_template_proposals,
        *session_runtime_proposals,
    ]
    for source_name, destination_name, render in BASE_DOCS:
        content = render_asset(source_name, replacements) if render else (ASSETS / "docs" / source_name).read_text(encoding="utf-8")
        destination = target / destination_name
        if mode == "migrate" and destination.exists():
            if destination.read_text(encoding="utf-8") == content:
                rendered_docs.append(destination_name)
                continue
            destination = destination.with_name(destination.name + ".wiki-proposed")
            proposals.append(destination.relative_to(target).as_posix())
        write_text(destination, content)
        rendered_docs.append(destination_name)

    profile_docs, profile_proposals = install_profile_docs(
        target,
        resolved_profile,
        replacements,
        propose_existing=mode == "migrate",
    )
    rendered_docs.extend(profile_docs)
    proposals.extend(profile_proposals)

    proposals.extend(seed_ingest_ledger(target, propose_existing=mode == "migrate"))
    write_manifest(target, config["project_name"], resolved_profile)
    profile_verification = verify_profile_installation(target, resolved_profile)
    if profile_verification["status"] == "failed":
        raise RuntimeError("Evidence installation verification failed: " + "; ".join(profile_verification["errors"]))

    result = {
        "ok": True,
        "target": str(target.resolve()),
        "mode": mode,
        "profile": resolved_profile,
        "installed_skills": list(skills_for_profile(resolved_profile)),
        "rendered_docs": rendered_docs,
        "copied_templates": sum(path.is_file() for path in (target / "templates").rglob("*")),
        "profile_templates": profile_template_count,
        "profile_runtime": profile_runtime,
        "profile_verification": profile_verification,
        "profile_activation_pending": profile_verification["status"] == "pending",
        "knowledge_migration_pending": False,
        "manifest": MANIFEST_NAME,
    }
    if mode == "migrate":
        result.update(existing_entries=existing_entries, proposals=proposals)
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", required=True, type=Path)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--mode", choices=("new", "migrate", "upgrade"), default="new")
    parser.add_argument("--profile", choices=PROFILES, default=None)
    args = parser.parse_args()
    try:
        result = bootstrap(args.target, args.config, args.mode, args.profile)
    except Exception as error:
        result = {"ok": False, "error": str(error), "mode": args.mode, "profile": args.profile}
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
