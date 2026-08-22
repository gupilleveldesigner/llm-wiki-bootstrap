import argparse
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path


ASSETS = Path(__file__).resolve().parent.parent / "assets"

DIRECTORIES = (
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

DOCS = (
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
    ("root-log.md.template", "log.md", True),
    ("changelog.md.template", "changelog.md", True),
    ("graphifyignore.template", ".graphifyignore", False),
    ("session-memory-config.json.template", ".session-memory/config.json", True),
)

SKILLS = ("ingest", "query", "lint", "session-memory", "brief-tuner")
PROPOSABLE_DOCS = {
    "CLAUDE.md",
    "AGENTS.md",
    "log.md",
    "changelog.md",
    "instructions/wiki-operations.md",
    ".graphifyignore",
}


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


def install_skills(target: Path) -> None:
    shutil.copytree(ASSETS / "skills-bundle/agents-skills", target / ".agents/skills", dirs_exist_ok=True)
    shutil.copytree(ASSETS / "skills-bundle/claude-adapters", target / ".claude/skills", dirs_exist_ok=True)
    for root in (target / ".agents/skills", target / ".claude/skills"):
        for path in root.rglob("SKILL.md.bundled"):
            path.rename(path.with_name("SKILL.md"))


def upgrade(target: Path, config_path: Path) -> dict:
    if not ((target / "raw").is_dir() and (target / "wiki").is_dir()):
        raise ValueError("target is not an LLM Wiki; use --mode new or migrate")

    backup_dir = None
    backup_sources = [
        target / root / skill
        for root in (".agents/skills", ".claude/skills")
        for skill in SKILLS
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

    install_skills(target)
    for directory in ("pending", "sessions", "transactions", "scripts"):
        (target / ".session-memory" / directory).mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ASSETS / "session-memory-runtime/session_memory.py", runtime)

    config_destination = target / ".session-memory/config.json"
    if not config_destination.exists():
        project_name = load_config(config_path, ("project_name",))["project_name"]
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

    proposals = []
    source = ASSETS / "docs/instructions/wiki-operations.md"
    destination = target / "instructions/wiki-operations.md"
    content = source.read_text(encoding="utf-8")
    if not destination.exists():
        write_text(destination, content)
    elif destination.read_text(encoding="utf-8") != content:
        proposal = destination.with_name(destination.name + ".wiki-proposed")
        write_text(proposal, content)
        proposals.append(proposal.relative_to(target).as_posix())

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

    return {
        "ok": True,
        "target": str(target.resolve()),
        "mode": "upgrade",
        "backup_dir": str(backup_dir.resolve()) if backup_dir else None,
        "proposals": proposals,
        "refreshed_skills": list(SKILLS),
        "copied_templates": copied_templates,
        "graphifyignore": graphifyignore_status,
    }


def bootstrap(target: Path, config_path: Path, mode: str = "new") -> dict:
    if mode == "upgrade":
        return upgrade(target, config_path)
    if mode == "new" and target.exists() and any(target.iterdir()):
        raise ValueError("target is not empty; use --mode migrate for an existing folder")
    markers = ("raw", "wiki", ".agents", "CLAUDE.md") if mode == "new" else ("raw", "wiki", ".agents")
    if target.exists() and any((target / name).exists() for name in markers):
        if mode == "migrate":
            raise ValueError("target looks like an existing LLM Wiki; use --mode upgrade")
        raise ValueError("target already contains an LLM Wiki marker")
    existing_entries = sorted(path.name for path in target.iterdir()) if target.exists() else []
    target.mkdir(parents=True, exist_ok=True)
    config = load_config(config_path, ("project_name", "domain_summary"))

    for directory in DIRECTORIES:
        (target / directory).mkdir(parents=True, exist_ok=True)

    install_skills(target)
    shutil.copytree(ASSETS / "templates", target / "templates", dirs_exist_ok=True)
    shutil.copyfile(
        ASSETS / "session-memory-runtime/session_memory.py",
        target / ".session-memory/scripts/session_memory.py",
    )

    replacements = {
        "{{PROJECT_NAME}}": config["project_name"],
        "{{DOMAIN_SUMMARY}}": config["domain_summary"],
        "{{TODAY}}": datetime.now().strftime("%Y-%m-%d"),
    }
    rendered_docs = []
    proposals = []
    for source_name, destination_name, render in DOCS:
        with (ASSETS / "docs" / source_name).open(encoding="utf-8", newline="") as file:
            content = file.read()
        if render:
            for placeholder, value in replacements.items():
                content = content.replace(placeholder, value)
        destination = target / destination_name
        if mode == "migrate" and destination_name in PROPOSABLE_DOCS and destination.exists():
            destination = destination.with_name(destination.name + ".wiki-proposed")
            proposals.append(destination.relative_to(target).as_posix())
        write_text(destination, content)
        rendered_docs.append(destination_name)
    seed_ingest_ledger(target)

    result = {
        "ok": True,
        "target": str(target.resolve()),
        "mode": mode,
        "installed_skills": list(SKILLS),
        "rendered_docs": rendered_docs,
        "copied_templates": sum(path.is_file() for path in (target / "templates").rglob("*")),
    }
    if mode == "migrate":
        result.update(existing_entries=existing_entries, proposals=proposals)
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", required=True, type=Path)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--mode", choices=("new", "migrate", "upgrade"), default="new")
    args = parser.parse_args()
    try:
        result = bootstrap(args.target, args.config, args.mode)
    except Exception as error:
        result = {"ok": False, "error": str(error), "mode": args.mode}
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
