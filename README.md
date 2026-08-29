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

Game mode v4 keeps the live engine project and Wiki as separate roots while tracking both sides. The default sibling sidecar preserves Unity, Unreal, Godot, and web-project layouts. Installation and upgrade use dry-run planning, engine protected paths, transaction staging, managed-file ownership, project-integrity verification, and rollback.

```bash
python scripts/game_project.py \
  --project-root ./MyGame \
  --config ./config.json \
  --mode migrate \
  --profile evidence \
  --dry-run
```

`tools/game_trace.py` now records an accepted implementation-check baseline containing a canonical design digest and per-path code fingerprints. Rebuilds distinguish:

```text
in_sync | design_changed | code_changed | both_changed | unverified | missing
```

```bash
python tools/game_trace.py accept wiki/game/implementation/IMPL-001.md
python tools/game_trace.py scan
python tools/game_trace.py status
python tools/game_trace.py proposals
python tools/game_trace.py verify --strict-sync
```

The runtime also supports spec→code, code→spec, build/test/decision links, monorepo-safe Git-diff impact analysis, and non-Git change detection through fingerprints. It never automatically overwrites design with code or code with design; changed relations require inspection, proposal/decision, and a new accepted baseline.

**Upgrade means GitHub latest by default.** The updater pins and validates the official repository's exact default-branch HEAD before staging any target changes. Game-mode Wikis use `scripts/game_project.py --mode upgrade` so the base Wiki, engine-layout safety layer, Game overlay, and trace runtime advance together. No updater silently falls back to a stale local bundle.
