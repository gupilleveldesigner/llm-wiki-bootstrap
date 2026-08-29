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

It installs game-specific specifications, implementation checks, playtest/build/decision templates, and a project-local `game-project` skill. It never treats the live game source tree as Raw or conflates “designed”, “implemented”, “validated”, and “done”. `standard + game` and `evidence + game` are both supported.

```bash
python scripts/game_project.py \
  --target ./MyGame \
  --config ./config.json \
  --mode new \
  --profile evidence
```

**Upgrade means GitHub latest by default.** The updater resolves the official repository's current default-branch HEAD, pins the exact commit SHA, validates the downloaded checkout before touching the target, backs up managed skills, and applies that commit's logic. Game-mode Wikis must use `scripts/game_project.py --mode upgrade` so the base Wiki and game overlay advance together. No updater silently falls back to a stale local bundle.
