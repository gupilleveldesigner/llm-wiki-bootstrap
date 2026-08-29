# llm-wiki-bootstrap

AI-operated knowledge and project vault bootstrap for Claude Code and Codex.

Choose a language:

- **한국어:** [README.ko.md](README.ko.md)
- **English:** [README.en.md](README.en.md)
- **게임 프로젝트 모드:** [GAME_PROJECT_MODE.ko.md](GAME_PROJECT_MODE.ko.md)
- **Game project mode:** [GAME_PROJECT_MODE.en.md](GAME_PROJECT_MODE.en.md)

The system separates three orthogonal axes:

- lifecycle: `new` / `migrate` / `upgrade`
- vault profile: `standard` / `evidence`
- project mode: implicit `knowledge` / optional `game`

Profiles define how knowledge is trusted:

- `standard` — `raw → wiki → Output`
- `evidence` — `Raw → Source → Claim or Project Decision → Evidence/Conflict/Experiment → reviewed Canon`

Game project mode adds a production-aware trace:

```text
Design Intent → Implementation State → Validation Evidence → Project Decision
```

Game mode v2 keeps live code and design specifications as separate sources of truth, derives `wiki/game/traceability.json`, and installs `tools/game_trace.py` for `spec→code`, `code→spec`, build/test/decision links, Git-diff impact analysis, and stale implementation checks.

```bash
python scripts/game_project.py --target ./MyGame --config ./config.json --mode new --profile evidence
```

**Upgrade means GitHub latest by default.** The updater pins and validates the official repository's exact default-branch HEAD before touching the target. Game-mode Wikis use `scripts/game_project.py --mode upgrade` so the base Wiki, game overlay, and traceability runtime advance together. No updater silently falls back to a stale local bundle.
