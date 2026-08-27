# llm-wiki-bootstrap

AI-operated personal knowledge vault bootstrap for Claude Code and Codex.

Choose a language:

- **한국어:** [README.ko.md](README.ko.md)
- **English:** [README.en.md](README.en.md)

`llm-wiki-bootstrap` supports non-destructive `new` / `migrate` / `upgrade` lifecycles and two vault profiles:

- `standard` — `raw → wiki → Output`
- `evidence` — `Raw → Source → Claim → Evidence/Conflict/Experiment → reviewed Canon`

**Upgrade means GitHub latest by default:** it resolves the official repository's current default-branch HEAD, pins the exact commit SHA, validates that checkout, backs up the existing Wiki skills, and applies that commit's upgrade logic and bundled skills. It never silently falls back to a stale local bundle.

For complete installation, workflow, safety, Graphify, migration/upgrade, and Evidence Research documentation, open one of the language-specific README files above.
