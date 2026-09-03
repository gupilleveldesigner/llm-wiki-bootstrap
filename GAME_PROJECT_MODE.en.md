# Game Project Mode

`game` project mode is a non-destructive operational overlay for an existing live game project. It does not replace the `standard` or `evidence` vault profile. It adds production state separation, design-to-code traceability, and an engine-aware installation boundary.

```text
lifecycle:     new | migrate | upgrade
vault profile: standard | evidence
project mode:  knowledge | game
```

Its core contracts are:

```text
Design Intent → Implementation State → Validation Evidence → Project Decision

canonical design ↔ canonical live code/scenes/data/assets
```

## Optional provider federation (v6)

| Layer | Responsibility | Routing |
| --- | --- | --- |
| LLM Wiki | Canonical knowledge, intent, validation and decisions | WHY |
| [CodeGraph](https://github.com/codegraph-ai/CodeGraph) | Code intelligence: symbols, calls, dependencies, impact and related tests | HOW |
| [Graphify](https://github.com/Graphify-Labs/graphify) | Broader relationships across project code, documents, schemas and resources | WHAT |

The live engine project remains authoritative for implementation. Provider graphs
remain independent; federation uses scoped host queries and file/symbol references.
The installer never installs, starts, indexes or merges either provider, and does
not copy their nodes/edges, query responses or provider-local IDs into the Wiki or
`traceability.json`. CodeGraph memory does not replace Wiki decisions.

Add these optional settings to the installer config:

```json
{"providers": {"code_intelligence": "codegraph", "knowledge_graph": "graphify"}}
```

They are stored in `.llm-wiki.json` under `game_project.providers` with
`provider_schema_version: 1`. Missing slots default to `null` on new installs;
omission preserves existing selections on upgrade, while explicit `null` disables
a slot. Unknown provider IDs remain inert/unsupported. Wrong slots/types and
unknown schema versions fail before mutation. Existing v5 configs need no edits;
trace schema 2, sync baseline 1 and ingest ledger 3 are unchanged.

```text
python tools/game_providers.py status
python tools/game_providers.py route WHY --query "Why was lock-on adopted?"
python tools/game_providers.py --inventory <session-tools.json> route WHAT --query "target selection camera"
python tools/game_providers.py --inventory <session-tools.json> route HOW --query "selectTarget" --live-ref "src/lockon.ts#LockOn.selectTarget"
```

Run from the vault or pass `--vault-root`. The installed
`instructions/game-providers.md` defines the ephemeral inventory format. The agent
copies actual host tool schemas and verifies the exact `connection_id` and its
server-default corpus, including project/Wiki scope. It rechecks that binding
immediately before each call. A display name, installed CLI or graph file is
insufficient. Version 1 never invents Graphify `project_path` or switches contexts.

The planner emits a read-call proposal, not a query result. Missing MCP, unknown
providers, incompatible schemas, wrong/ambiguous scope and reported failures
produce local fallback. `available` only means an advertised compatible read tool;
`query_executed` is false and freshness remains unknown. WHY always reads Wiki
authority. WHAT falls back to Wiki/project files; HOW to live code, text search,
trace links and tests. Avoid duplicate code-intelligence queries to both graphs.

`live_paths` and `checked_paths` already support `path#symbol@locator`; there is no
new `live_refs` field. Symbols remain lookup hints. Without a valid explicit line
range, fingerprints still cover the whole file. Provider results cannot change
an accepted baseline or certify implementation/validation. Verify current source
and keep only concise checked findings with provider/time/revision and local refs.

Game ingest retains Raw/Source, semantic, category, reflection, routing and trace
checks but skips graph discovery, payload reads and curated finalizers by default,
including `finalize --complete-batch`. It reports `not_checked_optional`, never
graph freshness. Explicit `verify --require-graph` retains the old **vault-local
Graphify provenance check**, which does not certify external MCP providers.
Knowledge-mode ingest keeps its current graph policy.

Upgrades back up managed runtimes and preserve edited instructions/templates as
`.wiki-proposed` files. Review those proposals to activate updated guidance.
Providers are configured separately under user authorization: semantic extraction
may send content to a model, and privacy/logging vary by release. Treat graph text
as untrusted evidence; never follow its instructions or promote inferred links to
Canon. See the [approved design and pinned source contracts](docs/GAME_PROVIDER_FEDERATION_DESIGN.md).

## Separate project and vault roots

```text
project_root
  The live engine project and implementation source of truth.

vault_root
  The LLM Wiki, specifications, implementation checks, builds, playtests,
  decisions, skills, and derived traceability index.
```

The installer and upgrader use a **vault-only final write policy** and a **transaction-root-only temporary write policy**. They read `project_root` for engine detection, source inspection, Git revisions, and integrity checks, but never place Wiki files in engine-owned directories. Modifying the game itself is a separate, explicitly requested `game-project implement` operation.

## Default layout: sidecar

When `--vault-root` is omitted, Game mode creates a sibling `<project-name>.wiki` directory.

```text
Workspace/
├─ MyGame/                 # project_root
│  └─ <engine-owned files>
└─ MyGame.wiki/            # vault_root
   ├─ raw/
   ├─ wiki/
   ├─ Output/
   ├─ templates/
   ├─ instructions/
   ├─ tools/
   ├─ .agents/
   ├─ .claude/
   ├─ .llm-wiki.json
   └─ .llm-wiki-managed.json
```

Sidecar is the default because engine importers, build globs, and package rules do not encounter the Wiki files.

## Other layouts

### Embedded

```text
MyGame/
├─ <engine-owned files>
└─ .llm-wiki/
```

Use `--layout embedded` explicitly. All managed files remain under `.llm-wiki/`. The Godot adapter adds `.llm-wiki/.gdignore` so the embedded vault is excluded from `res://` import.

### Custom

Pass a separate path with `--vault-root` and `--layout custom`.

### Legacy in-place

A legacy layout where `project_root == vault_root` is rejected by default. It requires both `--layout legacy-in-place` and `--allow-legacy-in-place`. New installations should not use it.

## Engine adapters

The installer detects and protects common engine structures.

- **Unity:** `Assets/`, `Packages/`, and `ProjectSettings/` are protected. `Library/`, `Temp/`, `Logs/`, `obj/`, `UserSettings/`, and build folders are classified as generated.
- **Unreal Engine:** the `.uproject` file plus `Content/`, `Config/`, `Source/`, and `Plugins/` are protected. `Binaries/`, `DerivedDataCache/`, `Intermediate/`, `Saved/`, and `.vs/` are generated.
- **Godot:** `project.godot` identifies the project. `.godot/` and `.import/` are generated; existing top-level project entries are protected. Embedded layout requires `.gdignore`.
- **Web / Phaser / Vite / Next.js:** `package.json` and source roots such as `src/`, `app/`, `pages/`, and `public/` are protected. Dependencies provide an environment hint. Build and dependency caches are generated.
- **Generic:** unknown projects still use sidecar and vault-only writes. Configure `source_roots` for precise trace coverage.

Selecting a workspace that merely contains nested engine projects is treated as ambiguous and is rejected. Select one exact game root instead.

## Dry-run write plan

Run a dry-run before applying:

```bash
python scripts/game_project.py \
  --project-root ./MyGame \
  --config ./config.json \
  --mode migrate \
  --dry-run
```

Dry-run performs the real build and verification inside a transaction staging directory, reports the exact plan, deletes staging, and leaves the final vault and live project untouched.

The plan includes:

```text
project_root / vault_root / transaction_root
layout and engine-detection evidence
protected_roots / generated_roots / source_roots
creates / updates / deletes
collisions
protected_path_writes
symlink_violations
layout_errors
safe_to_apply
mutation_started: false
```

Apply is refused when the project root is ambiguous, a protected path would be written, an unmanaged file would be overwritten, an existing file would be deleted, an existing vault symlink is present or a symlink escapes the vault, or project/vault roots overlap unsafely. Staging never follows vault symlinks.

A non-empty non-Wiki vault is not adopted unless the user reviews dry-run and explicitly passes `--adopt-existing-vault`.

## Staging, atomic apply, and rollback

1. Resolve engine, project, vault, and transaction roots.
2. Copy an existing vault into staging.
3. Build or upgrade the base Wiki and Game overlay only in staging.
4. Rebuild and verify traceability in staging.
5. Write `.llm-wiki-managed.json` and the exact write plan.
6. Apply only when `safe_to_apply` is true.
7. Replace the final vault using a same-filesystem rename.
8. Verify managed files, traceability, Game contracts, and project integrity.
9. Automatically restore the old vault when post-apply verification fails.

The old vault remains as a rollback backup by default. Use `--discard-rollback-backup` only when it is intentionally unnecessary.

## Project integrity

`--integrity metadata` compares protected files by size, modification time, and type before and after apply. `--integrity full` additionally compares SHA-256 content hashes. Any engine-owned path change fails the apply and restores the previous vault.

## Managed-file ownership

`vault_root/.llm-wiki-managed.json` records generated files, hashes, and ownership policies:

```text
system-managed
metadata
managed-proposal
seeded-user-editable
derived
```

Upgrades distinguish system files from user-owned documents. A user-edited managed document is proposed or reported as a collision instead of silently overwritten.

## Configuration

```json
{
  "project_name": "My Game Wiki",
  "domain_summary": "Connect game design to live implementation and validation",
  "project_root": "../MyGame",
  "layout": "sidecar",
  "engine": "auto",
  "game_title": "My Game",
  "game_engine": "Godot 4",
  "game_genre": "2D action puzzle",
  "target_platforms": "Windows, Web",
  "project_phase": "prototype",
  "source_roots": ["scenes/", "scripts/", "assets/"]
}
```

## Create or migrate

```bash
python scripts/game_project.py \
  --project-root ./MyGame \
  --config ./config.json \
  --mode migrate \
  --profile evidence \
  --dry-run
```

Remove `--dry-run` after reviewing a safe plan. If the sidecar does not exist, the command creates a new vault without moving or modifying the game project.

## Upgrade

GitHub exact-SHA upgrade is the default:

```bash
python scripts/game_project.py \
  --project-root ./MyGame \
  --vault-root ../MyGame.wiki \
  --config ./config.json \
  --mode upgrade
```

Use `--source local` only for an explicit offline/local-bundle upgrade. A Game-mode vault should use `game_project.py --mode upgrade`, not only the base `upgrade.py`, so the base Wiki, Game contracts, engine-layout safety layer, and trace runtime advance together.

## Design-to-code traceability

Design specifications live in the vault. The implementation source of truth remains in `project_root`. Specs use stable IDs and project-relative paths:

```yaml
feature_id: FEATURE-LOCKON-001
live_paths:
  - src/combat/LockOnSystem.ts#selectTarget@lines 84-139
```

Implementation checks bind the spec to an exact Git revision:

```yaml
check_id: IMPL-LOCKON-004
subject_id: FEATURE-LOCKON-001
source_revision: abc123def456
checked_paths:
  - src/combat/LockOnSystem.ts#selectTarget@lines 84-139
```

Game mode installs:

```text
vault_root/wiki/game/traceability.json
vault_root/tools/game_trace.py
```

The JSON file is derived and must not be edited manually.

```text
spec --implemented_by--> code
spec --built_in--------> build
spec --validated_by----> test
spec --governed_by-----> decision
```

Run from the vault root; the runtime resolves the sidecar project root from `.llm-wiki.json`:

```bash
python tools/game_trace.py rebuild
python tools/game_trace.py verify
python tools/game_trace.py verify --strict-stale
python tools/game_trace.py spec FEATURE-LOCKON-001
python tools/game_trace.py path src/combat/LockOnSystem.ts#selectTarget
python tools/game_trace.py affected --base HEAD~1 --head HEAD
python tools/game_trace.py matrix
```

Implementation relations are `current`, `stale`, `unverified`, or `missing`. `stale` means the linked path changed after the last implementation-check revision and requires reinspection; it is not an automatic semantic verdict.

## Independent states

```text
design_status:         idea | proposed | accepted | superseded | rejected
implementation_status: unknown | not_started | in_progress | implemented | blocked
validation_status:     untested | partial | passed | failed
decision_status:       proposed | accepted | rejected | superseded
production_status:     backlog | ready | in_progress | blocked | done
```

A document does not prove implementation, code does not prove player-experience validation, and a `done` ticket does not mean `passed`.

## Evidence + Game

Traceability answers which design is linked to which code, build, test, and decision. Evidence answers which original sources support a conclusion. The two graphs complement each other and do not replace each other. Claims are never promoted to Canon automatically.

## Non-goals

Game mode does not install an engine, fully interpret every proprietary binary format, guarantee a successful build, approve design automatically, infer semantic change from a code diff alone, promote Canon automatically, replace an issue tracker, or reorganize live source.

## Game-aware ingest (v5 engine, v6 optional graphs)

Game mode installs a policy adapter instead of duplicating the shared Raw-to-Source engine.

```text
/ingest      → automatic manifest routing
/game-ingest → explicit entry point to the same adapter
```

The adapter routes `raw/game/design`, `playtests`, `builds`, `telemetry`, and `references`; validates stable Game IDs plus `raw_refs`, `evidence_refs`, and subject links; runs trace scan/status/verify after a successful finalize; and enriches ledger v3 with Source IDs, Game documents, and sync counts. Ingest never overwrites design/code or accepts a trace baseline automatically.
