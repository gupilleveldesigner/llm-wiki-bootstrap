import argparse
import json
import shutil
from datetime import datetime
from pathlib import Path


ASSETS = Path(__file__).resolve().parent.parent / "assets"
MANIFEST_NAME = ".llm-wiki.json"
SCHEMA_VERSION = 2

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
        "wiki/canon",
        "wiki/conflicts",
        "wiki/experiments",
        "wiki/questions/open",
        "wiki/questions/answered",
        "wiki/questions/blocked",
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
        ("profiles/evidence/docs/cache.gitignore", ".wiki-cache/.gitignore", False),
    ),
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
}

EVIDENCE_ROUTER_MARKER = "<!-- LLM-WIKI:EVIDENCE-PROFILE -->"


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as file:
        file.write(text.replace("\r\n", "\n").replace("\r", "\n"))


def seed_ingest_ledger(target: Path) -> None:
    ledger = {
        "version": 1,
        "updated": datetime.now().astimezone().isoformat(),
        "graphify": "not_checked",
        "counts": {"pending": 0, "verified": 0, "skipped": 0, "catalog_only": 0},
        "sources": [],
    }
    write_text(target / "wiki" / "ingest-ledger.json", json.dumps(ledger, ensure_ascii=False, indent=2) + "\n")


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


def install_skills(target: Path, profile: str) -> None:
    selected = skills_for_profile(profile)
    roots = (
        (ASSETS / "skills-bundle/agents-skills", target / ".agents/skills"),
        (ASSETS / "skills-bundle/claude-adapters", target / ".claude/skills"),
    )
    for source_root, destination_root in roots:
        for skill in selected:
            source = source_root / skill
            if not source.is_dir():
                raise FileNotFoundError(f"bundled skill is missing: {source}")
            shutil.copytree(source, destination_root / skill, dirs_exist_ok=True)
    for root in (target / ".agents/skills", target / ".claude/skills"):
        for path in root.rglob("SKILL.md.bundled"):
            destination = path.with_name("SKILL.md")
            if destination.exists():
                destination.unlink()
            path.rename(destination)


def profile_replacements(profile: str) -> dict[str, str]:
    if profile == "evidence":
        return {
            "{{VAULT_PROFILE}}": "evidence",
            "{{PROFILE_SUMMARY}}": "Evidence Research — Raw → Claim → Evidence/Conflict/Experiment → reviewed Canon",
            "{{PROFILE_ROUTER}}": (
                "- Evidence profile: `wiki/evidence-model.md`와 `instructions/evidence-operations.md`를 먼저 읽고, "
                "Canon 승격 검토에는 설치된 `canon-review` 스킬을 사용한다."
            ),
        }
    return {
        "{{VAULT_PROFILE}}": "standard",
        "{{PROFILE_SUMMARY}}": "Standard — raw 원문을 wiki 지식층으로 요약·연결",
        "{{PROFILE_ROUTER}}": "",
    }


def render_asset(source_name: str, replacements: dict[str, str]) -> str:
    content = (ASSETS / "docs" / source_name).read_text(encoding="utf-8")
    for placeholder, value in replacements.items():
        content = content.replace(placeholder, value)
    return content


def copy_profile_templates(target: Path, profile: str, *, overwrite: bool) -> int:
    source_root = ASSETS / "profiles" / profile / "templates"
    if not source_root.is_dir():
        return 0
    copied = 0
    destination_root = target / "templates" / profile
    for source in source_root.rglob("*"):
        if not source.is_file():
            continue
        destination = destination_root / source.relative_to(source_root)
        if destination.exists() and not overwrite:
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        copied += 1
    return copied


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
        content = source.read_text(encoding="utf-8")
        if render:
            for placeholder, value in replacements.items():
                content = content.replace(placeholder, value)
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


def upgrade(target: Path, config_path: Path, profile: str | None = None) -> dict:
    if not ((target / "raw").is_dir() and (target / "wiki").is_dir()):
        raise ValueError("target is not an LLM Wiki; use --mode new or migrate")

    resolved_profile, previous_profile = resolve_profile(target, profile, "upgrade")
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
    if backup_sources or runtime.is_file():
        backup_dir = target / ".wiki-upgrade-bak" / datetime.now().strftime("%Y%m%d-%H%M%S")
        for source in backup_sources:
            destination = backup_dir / source.relative_to(target)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(source, destination)
        if runtime.is_file():
            destination = backup_dir / runtime.relative_to(target)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(runtime, destination)

    for directory in BASE_DIRECTORIES + PROFILE_DIRECTORIES[resolved_profile]:
        (target / directory).mkdir(parents=True, exist_ok=True)

    install_skills(target, resolved_profile)
    for directory in ("pending", "sessions", "transactions", "scripts"):
        (target / ".session-memory" / directory).mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ASSETS / "session-memory-runtime/session_memory.py", runtime)

    config_destination = target / ".session-memory/config.json"
    if not config_destination.exists():
        content = (ASSETS / "docs/session-memory-config.json.template").read_text(encoding="utf-8")
        write_text(config_destination, content.replace("{{PROJECT_NAME}}", project_name))

    copied_templates = 0
    for source in (ASSETS / "templates").rglob("*"):
        if source.is_file():
            destination = target / "templates" / source.relative_to(ASSETS / "templates")
            if not destination.exists():
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, destination)
                copied_templates += 1
    copied_templates += copy_profile_templates(target, resolved_profile, overwrite=False)

    proposals: list[str] = []
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
    taxonomy_content = taxonomy_source.read_text(encoding="utf-8").replace("{{PROJECT_NAME}}", project_name)
    if not taxonomy_destination.exists():
        write_text(taxonomy_destination, taxonomy_content)
        taxonomy_status = "created"
    elif taxonomy_destination.read_text(encoding="utf-8") != taxonomy_content:
        proposal = taxonomy_destination.with_name(taxonomy_destination.name + ".wiki-proposed")
        write_text(proposal, taxonomy_content)
        proposals.append(proposal.relative_to(target).as_posix())
        taxonomy_status = "proposal"

    write_manifest(target, project_name, resolved_profile)

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
        "profile_activation_pending": bool(router_proposals),
        "refreshed_skills": list(skills_for_profile(resolved_profile)),
        "copied_templates": copied_templates,
        "graphifyignore": graphifyignore_status,
        "taxonomy": taxonomy_status,
    }


def bootstrap(target: Path, config_path: Path, mode: str = "new", profile: str | None = None) -> dict:
    if mode == "upgrade":
        return upgrade(target, config_path, profile)
    if mode not in ("new", "migrate"):
        raise ValueError(f"unsupported bootstrap mode: {mode}")
    if mode == "new" and target.exists() and any(target.iterdir()):
        raise ValueError("target is not empty; use --mode migrate for an existing folder")
    markers = ("raw", "wiki", ".agents", "CLAUDE.md", MANIFEST_NAME) if mode == "new" else ("raw", "wiki", ".agents", MANIFEST_NAME)
    if target.exists() and any((target / name).exists() for name in markers):
        if mode == "migrate":
            raise ValueError("target looks like an existing LLM Wiki; use --mode upgrade")
        raise ValueError("target already contains an LLM Wiki marker")

    resolved_profile, _ = resolve_profile(target, profile, mode)
    existing_entries = sorted(path.name for path in target.iterdir()) if target.exists() else []
    target.mkdir(parents=True, exist_ok=True)
    config = load_config(config_path, ("project_name", "domain_summary"))

    for directory in BASE_DIRECTORIES + PROFILE_DIRECTORIES[resolved_profile]:
        (target / directory).mkdir(parents=True, exist_ok=True)

    install_skills(target, resolved_profile)
    shutil.copytree(ASSETS / "templates", target / "templates", dirs_exist_ok=True)
    profile_template_count = copy_profile_templates(target, resolved_profile, overwrite=True)
    shutil.copyfile(
        ASSETS / "session-memory-runtime/session_memory.py",
        target / ".session-memory/scripts/session_memory.py",
    )

    replacements = {
        "{{PROJECT_NAME}}": config["project_name"],
        "{{DOMAIN_SUMMARY}}": config["domain_summary"],
        "{{TODAY}}": datetime.now().strftime("%Y-%m-%d"),
        **profile_replacements(resolved_profile),
    }
    rendered_docs: list[str] = []
    proposals: list[str] = []
    for source_name, destination_name, render in BASE_DOCS:
        content = render_asset(source_name, replacements) if render else (ASSETS / "docs" / source_name).read_text(encoding="utf-8")
        destination = target / destination_name
        if mode == "migrate" and destination_name in PROPOSABLE_DOCS and destination.exists():
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

    seed_ingest_ledger(target)
    write_manifest(target, config["project_name"], resolved_profile)

    result = {
        "ok": True,
        "target": str(target.resolve()),
        "mode": mode,
        "profile": resolved_profile,
        "installed_skills": list(skills_for_profile(resolved_profile)),
        "rendered_docs": rendered_docs,
        "copied_templates": sum(path.is_file() for path in (target / "templates").rglob("*")),
        "profile_templates": profile_template_count,
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
