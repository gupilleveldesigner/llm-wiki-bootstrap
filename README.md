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

Game mode adds:

```text
Design Intent → Implementation State → Validation Evidence → Project Decision
```

Game mode v3 keeps the live engine project and the Wiki as separate roots. The default layout is a sibling sidecar vault, so Unity, Unreal, Godot, and web-project directory structures remain intact. Installation and upgrade use a dry-run write plan, engine protected paths, transaction staging, managed-file ownership, project-integrity verification, and rollback.

```bash
python scripts/game_project.py \
  --project-root ./MyGame \
  --config ./config.json \
  --mode migrate \
  --profile evidence \
  --dry-run
```

Game mode also derives `wiki/game/traceability.json` and installs `tools/game_trace.py` for spec→code, code→spec, build/test/decision links, Git-diff impact analysis, and stale implementation checks.

**Upgrade means GitHub latest by default.** The updater pins and validates the official repository's exact default-branch HEAD before staging any target changes. Game-mode Wikis use `scripts/game_project.py --mode upgrade` so the base Wiki, engine-layout safety layer, Game overlay, and trace runtime advance together. No updater silently falls back to a stale local bundle.
