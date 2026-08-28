from __future__ import annotations

import argparse
import io
import json
import re
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
import zipfile
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any


OFFICIAL_REPOSITORY = "gupilleveldesigner/llm-wiki-bootstrap"
GITHUB_API = "https://api.github.com"
GITHUB_CODELOAD = "https://codeload.github.com"
USER_AGENT = "llm-wiki-bootstrap-upgrader/1"
DEFAULT_TIMEOUT = 20
MAX_ARCHIVE_BYTES = 32 * 1024 * 1024
REQUIRED_REMOTE_PATHS = (
    "SKILL.md",
    "scripts/bootstrap.py",
    "assets/skills-bundle/agents-skills",
    "assets/skills-bundle/claude-adapters",
    "assets/skills-bundle/agents-skills/ingest/scripts/semantic_contract.py",
    "assets/skills-bundle/agents-skills/ingest/scripts/stitch_explicit_links.py",
    "assets/profiles/evidence/docs/evidence-kb.md.template",
    "assets/profiles/evidence/runtime/kb.py",
    "assets/profiles/evidence/templates/decision.md",
)


def _request(url: str, *, accept: str | None = None, timeout: int = DEFAULT_TIMEOUT) -> bytes:
    headers = {"User-Agent": USER_AGENT}
    if accept:
        headers["Accept"] = accept
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = response.read(MAX_ARCHIVE_BYTES + 1)
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        raise RuntimeError(f"GitHub request failed before upgrade: {url}: {error}") from error
    if len(data) > MAX_ARCHIVE_BYTES:
        raise RuntimeError(f"GitHub response is unexpectedly large: {url}")
    return data


def _request_json(url: str) -> dict[str, Any]:
    payload = _request(url, accept="application/vnd.github+json")
    try:
        value = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RuntimeError(f"GitHub returned invalid JSON: {url}") from error
    if not isinstance(value, dict):
        raise RuntimeError(f"GitHub returned an unexpected JSON shape: {url}")
    return value


def resolve_latest_commit(repository: str = OFFICIAL_REPOSITORY) -> tuple[str, str]:
    repo = _request_json(f"{GITHUB_API}/repos/{repository}")
    default_branch = repo.get("default_branch")
    if not isinstance(default_branch, str) or not default_branch:
        raise RuntimeError("GitHub repository metadata did not include default_branch")

    commit = _request_json(f"{GITHUB_API}/repos/{repository}/commits/{default_branch}")
    sha = commit.get("sha")
    if not isinstance(sha, str) or not re.fullmatch(r"[0-9a-fA-F]{40}", sha):
        raise RuntimeError("GitHub did not return a valid 40-character commit SHA")
    return default_branch, sha.lower()


def download_commit_archive(repository: str, sha: str) -> bytes:
    if not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise ValueError("refusing to download an unvalidated GitHub commit SHA")
    return _request(f"{GITHUB_CODELOAD}/{repository}/zip/{sha}", accept="application/zip")


def _safe_members(archive: zipfile.ZipFile) -> list[zipfile.ZipInfo]:
    members: list[zipfile.ZipInfo] = []
    for member in archive.infolist():
        path = PurePosixPath(member.filename)
        if path.is_absolute() or ".." in path.parts:
            raise RuntimeError(f"unsafe path in GitHub archive: {member.filename}")
        if not path.parts:
            continue
        members.append(member)
    if not members:
        raise RuntimeError("GitHub archive is empty")
    return members


def extract_checkout(archive_bytes: bytes, destination: Path) -> Path:
    try:
        with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
            members = _safe_members(archive)
            roots = {PurePosixPath(member.filename).parts[0] for member in members}
            if len(roots) != 1:
                raise RuntimeError("GitHub archive must contain exactly one repository root")
            root_name = next(iter(roots))
            archive.extractall(destination, members=members)
    except zipfile.BadZipFile as error:
        raise RuntimeError("GitHub returned an invalid ZIP archive") from error

    checkout = destination / root_name
    validate_checkout(checkout)
    return checkout


def validate_checkout(checkout: Path) -> None:
    if not checkout.is_dir():
        raise RuntimeError("downloaded GitHub checkout root is missing")
    missing = [relative for relative in REQUIRED_REMOTE_PATHS if not (checkout / relative).exists()]
    if missing:
        raise RuntimeError("downloaded GitHub checkout is incomplete: " + ", ".join(missing))


def _parse_bootstrap_result(stdout: str) -> dict[str, Any]:
    lines = [line.strip() for line in stdout.splitlines() if line.strip()]
    if not lines:
        raise RuntimeError("latest bootstrap produced no JSON result")
    try:
        result = json.loads(lines[-1])
    except json.JSONDecodeError as error:
        raise RuntimeError("latest bootstrap did not end with a JSON result") from error
    if not isinstance(result, dict):
        raise RuntimeError("latest bootstrap returned an unexpected result shape")
    return result


def _write_upgrade_provenance(target: Path, *, repository: str, branch: str, commit: str) -> None:
    manifest_path = target / ".llm-wiki.json"
    if not manifest_path.is_file():
        return
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    if not isinstance(manifest, dict):
        return
    manifest["last_upgrade"] = {
        "source": "github",
        "repository": repository,
        "branch": branch,
        "commit": commit,
        "at": datetime.now().astimezone().isoformat(),
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def run_local_upgrade(checkout: Path, target: Path, config: Path, profile: str | None) -> dict[str, Any]:
    command = [
        sys.executable,
        str(checkout / "scripts/bootstrap.py"),
        "--target",
        str(target),
        "--config",
        str(config),
        "--mode",
        "upgrade",
    ]
    if profile:
        command.extend(("--profile", profile))
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    result = _parse_bootstrap_result(completed.stdout)
    if completed.returncode != 0 or not result.get("ok"):
        detail = completed.stderr.strip()
        if detail:
            result.setdefault("stderr", detail)
        return result
    return result


def upgrade_from_github(target: Path, config: Path, profile: str | None = None) -> dict[str, Any]:
    # All network retrieval and archive validation happen before the target Wiki is mutated.
    branch, commit = resolve_latest_commit(OFFICIAL_REPOSITORY)
    archive = download_commit_archive(OFFICIAL_REPOSITORY, commit)
    with tempfile.TemporaryDirectory(prefix="llm-wiki-bootstrap-upgrade-") as temporary:
        checkout = extract_checkout(archive, Path(temporary))
        result = run_local_upgrade(checkout, target, config, profile)

    result.update(
        {
            "upgrade_source": "github",
            "bootstrap_repository": OFFICIAL_REPOSITORY,
            "bootstrap_branch": branch,
            "bootstrap_commit": commit,
        }
    )
    if result.get("ok"):
        _write_upgrade_provenance(
            target,
            repository=OFFICIAL_REPOSITORY,
            branch=branch,
            commit=commit,
        )
    return result


def upgrade_from_local_bundle(target: Path, config: Path, profile: str | None = None) -> dict[str, Any]:
    checkout = Path(__file__).resolve().parent.parent
    result = run_local_upgrade(checkout, target, config, profile)
    result.update({"upgrade_source": "local", "bootstrap_repository": None, "bootstrap_branch": None, "bootstrap_commit": None})
    return result


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Upgrade an existing LLM Wiki. By default this resolves the official GitHub repository's "
            "current default-branch HEAD, downloads that exact commit, validates it, and runs its upgrade logic."
        )
    )
    parser.add_argument("--target", required=True, type=Path)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--profile", choices=("standard", "evidence"), default=None)
    parser.add_argument(
        "--source",
        choices=("github", "local"),
        default="github",
        help="github (default) fetches the latest official commit; local explicitly uses the currently installed bundle",
    )
    args = parser.parse_args()

    try:
        if args.source == "github":
            result = upgrade_from_github(args.target, args.config, args.profile)
        else:
            result = upgrade_from_local_bundle(args.target, args.config, args.profile)
    except Exception as error:
        result = {
            "ok": False,
            "mode": "upgrade",
            "profile": args.profile,
            "upgrade_source": args.source,
            "error": str(error),
        }

    print(json.dumps(result, ensure_ascii=False))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
