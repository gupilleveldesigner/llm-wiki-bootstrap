from __future__ import annotations

import json
from pathlib import Path


def _escaped_double_quoted(value: str) -> str:
    """Escape a value that is already surrounded by JSON/YAML double quotes."""
    return json.dumps(value, ensure_ascii=False)[1:-1]


def _replace(content: str, replacements: dict[str, str], *, escaped: bool) -> str:
    for placeholder, value in replacements.items():
        rendered = _escaped_double_quoted(value) if escaped else value
        content = content.replace(placeholder, rendered)
    return content


def render_template(source: Path, replacements: dict[str, str]) -> str:
    """Render repository templates without corrupting JSON or YAML frontmatter.

    JSON templates keep placeholders inside double-quoted string values. Markdown
    templates may do the same in their leading YAML frontmatter. Those regions
    need string escaping; ordinary Markdown bodies should retain the user's text.
    """
    content = source.read_text(encoding="utf-8")

    if source.name.endswith(".json.template"):
        rendered = _replace(content, replacements, escaped=True)
        try:
            json.loads(rendered)
        except json.JSONDecodeError as error:
            raise ValueError(f"rendered JSON template is invalid: {source}: {error}") from error
        return rendered

    if source.name.endswith(".md.template") and content.startswith("---"):
        boundary = content.find("\n---", 3)
        if boundary != -1:
            boundary_end = boundary + len("\n---")
            frontmatter = _replace(content[:boundary_end], replacements, escaped=True)
            body = _replace(content[boundary_end:], replacements, escaped=False)
            return frontmatter + body

    return _replace(content, replacements, escaped=False)
