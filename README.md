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

Game mode v6 keeps the live engine project and Wiki as separate roots, retains v5 trace/baseline compatibility, and adds optional provider federation. The default sibling sidecar preserves Unity, Unreal, Godot, and web-project layouts. Installation and upgrade use dry-run planning, engine protected paths, transaction staging, managed-file ownership, project-integrity verification, and rollback.

| Question | Layer |
| --- | --- |
| WHAT: broader project relationships | Graphify (`Graphify-Labs/graphify`) |
| HOW: code structure, symbols, impact and tests | CodeGraph (`codegraph-ai/CodeGraph`) |
| WHY: canonical intent, validation and decisions | LLM Wiki |

Select both in [`config.game.example.json`](config.game.example.json). `tools/game_providers.py` plans scoped host queries and falls back to local files when MCP is missing or incompatible. It never starts providers or merges/copies their graph data. See the [reviewed design](docs/GAME_PROVIDER_FEDERATION_DESIGN.md) and [Game guide](GAME_PROJECT_MODE.en.md#optional-provider-federation-v6).

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

Game vaults install a `game-ingest` skill and configure generic `/ingest` to auto-route through `tools/ingest-adapters/game_adapter.py`. Raw scanning, Source records, SHA and semantic review, and the base ledger remain shared; the adapter adds sidecar resolution, `raw_refs`/`evidence_refs`, typed Game validation, routing, trace post-processing, and ledger v3. Game completion checks work without external graphs and report `not_checked_optional`. Explicit `verify --require-graph` retains the old vault-local Graphify provenance check; knowledge-mode ingest keeps its existing policy.

```bash
python .agents/skills/ingest/scripts/ingest_runtime.py scan --json
python .agents/skills/ingest/scripts/ingest_runtime.py finalize \
  --changed-file wiki/sources/playtest.md \
  --changed-file wiki/game/playtests/PLAYTEST-001.md
```

Ingest completion and design-code synchronization are separate outcomes. The adapter reports drift but never accepts a new trace baseline automatically.

**Upgrade means GitHub latest by default.** The updater pins and validates the official repository's exact default-branch HEAD before staging any target changes. Game-mode Wikis use `scripts/game_project.py --mode upgrade` so the base Wiki, engine-layout safety layer, Game overlay, and trace runtime advance together. No updater silently falls back to a stale local bundle.
