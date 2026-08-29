# Game Project Mode

The `game` project mode is an operational overlay for using an LLM Wiki alongside a live game project. It does not replace the `standard` or `evidence` vault profile. It adds game-specific design, implementation, validation, and decision layers.

```text
lifecycle:     new | migrate | upgrade
vault profile: standard | evidence
project mode:  knowledge | game
```

Supported combinations include `standard + game` and `evidence + game` across all non-destructive lifecycle modes.

## Why this is a project mode, not a vault profile

Vault profiles define how knowledge is trusted:

- `standard`: immutable Raw → maintained Wiki → Output
- `evidence`: Source, Claim, Conflict, Experiment, Project Decision, and reviewed Canon provenance

Game mode defines what kind of project the Wiki operates. A game project can simultaneously have an accepted design, incomplete implementation, an untested build, and a production ticket marked done. Collapsing those into one status causes false completion claims.

Game mode therefore enforces this trace:

```text
Design Intent → Implementation State → Validation Evidence → Project Decision
```

Production workflow remains a separate state.

## Independent states

```text
design_status:
  idea | proposed | accepted | superseded | rejected

implementation_status:
  unknown | not_started | in_progress | implemented | blocked

validation_status:
  untested | partial | passed | failed

decision_status:
  proposed | accepted | rejected | superseded

production_status:
  backlog | ready | in_progress | blocked | done
```

Each state changes only when its own evidence supports the change. A document does not prove implementation, code does not prove player-experience validation, and `done` does not mean `passed`.

## The live-source boundary

The live engine project, source code, original assets, scenes, and data remain in place. They are not moved under `raw/` during migration or mode activation.

`raw/game/` is reserved for immutable evidence such as:

- external design originals and references
- raw playtest notes, survey exports, and recording metadata
- build logs, crash reports, and telemetry exports
- unmodified external LLM or tool analyses
- approved handoff snapshots

Implementation claims should cite the live path and an exact revision or build whenever possible.

## Installed structure

Game mode adds:

- `wiki/game/` sections for features, systems, levels, content, narrative, UI/UX, technical work, implementation checks, assets, playtests, builds, bugs, decisions, proposals, milestones, and releases
- `raw/game/` evidence folders
- `templates/game/`
- `instructions/game-project.md`
- project-local `game-project` skills for Codex and Claude
- `project_mode: game` plus game metadata in `.llm-wiki.json`

## Configuration

```json
{
  "project_name": "My Game Wiki",
  "domain_summary": "Connect game design to actual implementation and validation",
  "game_title": "My Game",
  "game_engine": "Godot 4",
  "game_genre": "2D action puzzle",
  "target_platforms": "Windows, Web",
  "project_phase": "prototype",
  "source_roots": ["game/", "addons/"]
}
```

Only `project_name` and `domain_summary` are required for `new` and `migrate`. Unknown game metadata can remain `UNKNOWN` or an empty list.

## Create a game Wiki

Standard + Game:

```bash
python scripts/game_project.py \
  --target ./MyGame \
  --config ./config.json \
  --mode new \
  --profile standard
```

Evidence + Game:

```bash
python scripts/game_project.py \
  --target ./MyGameResearch \
  --config ./config.json \
  --mode new \
  --profile evidence
```

## Migrate an existing game folder

```bash
python scripts/game_project.py \
  --target ./ExistingGame \
  --config ./config.json \
  --mode migrate \
  --profile standard
```

Existing source and assets remain untouched. Conflicting managed files are emitted as `.wiki-proposed`; activation remains pending until those proposals are reviewed.

## Add or upgrade game mode

GitHub latest is the default:

```bash
python scripts/game_project.py \
  --target ./ExistingWiki \
  --config ./config.json \
  --mode upgrade
```

Promote to Evidence at the same time:

```bash
python scripts/game_project.py \
  --target ./ExistingWiki \
  --config ./config.json \
  --mode upgrade \
  --profile evidence
```

A game-mode Wiki should not use only `scripts/upgrade.py`: `game_project.py --mode upgrade` advances the base Wiki and game overlay together from the same validated checkout.

Explicit offline/local upgrade:

```bash
python scripts/game_project.py \
  --target ./ExistingWiki \
  --config ./config.json \
  --mode upgrade \
  --source local
```

This is reported as `upgrade_source: local`, not GitHub latest.

## Templates

The overlay includes templates for:

- feature, system, level, and content specifications
- implementation checks against live source
- playtest reports that separate observation from interpretation
- build reports with exact revision/platform/configuration
- decision records with alternatives and supersession
- asset briefs with source/runtime boundaries
- bugs and regression validation
- milestones with testable exit criteria

## The `game-project` skill

The installed skill routes work into these operations:

- `define`: feature/system/level/content/UI/asset intent
- `plan`: milestones, dependencies, risks, and exit criteria
- `implement`: changes to the live source tree
- `inspect`: design-versus-implementation checks
- `playtest`: questions, observations, interpretations, and follow-up
- `build`: exact revision/build/platform and smoke results
- `decide`: options, criteria, evidence, consequences, and supersession
- `bug`: reproduction, root cause, fix, and regression validation
- `release`: planned scope versus actual shipped scope

## Evidence + Game

With the Evidence profile, raw playtests, logs, telemetry, and external analyses become Sources. Empirical generalizations become Claims; counterexamples remain contradictions or Conflicts; revalidation can become Experiments; and game documents link those records through `evidence_refs`.

An accepted design decision and an empirically supported fact are different records. Neither automatically becomes Canon.

## Safe GitHub upgrade

Before modifying the target, the game updater validates:

1. the repository's current default branch
2. its exact 40-character HEAD SHA
3. the exact-SHA archive
4. archive path safety
5. the base Wiki contract
6. the game wrapper, docs, templates, and both host skill adapters

Failure leaves the target untouched and never silently falls back to an older local bundle.

## Non-goals

Game mode does not automatically install an engine, parse every proprietary engine format, guarantee a successful build, approve design choices, promote Canon, replace an external issue tracker, or reorganize the live source tree. It provides a traceable contract for reaching accurate conclusions from real source, builds, tests, and decisions.
