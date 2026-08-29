# Game Project Mode

The `game` project mode is an operational overlay for using an LLM Wiki with a live game project. It does not replace the `standard` or `evidence` vault profile. It adds game-specific design, implementation, validation, decision, and **design-to-code traceability** layers.

```text
lifecycle:     new | migrate | upgrade
vault profile: standard | evidence
project mode:  knowledge | game
```

## Independent states

Game mode keeps these states separate:

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

Its core trace is:

```text
Design Intent → Implementation State → Validation Evidence → Project Decision
```

A document does not prove implementation, code does not prove player-experience validation, and a `done` ticket does not mean `passed`.

## Live-source boundary

The live engine project, source code, scenes, original assets, and data remain in place. Migration and mode activation never move them under `raw/`.

`raw/game/` is reserved for immutable evidence such as external design originals, raw playtest notes, recording metadata, build logs, crash reports, telemetry exports, external analyses, and approved snapshots.

## Separate design and code sources of truth

Design specifications live under:

```text
wiki/game/features/
wiki/game/systems/
wiki/game/levels/
wiki/game/content/
wiki/game/narrative/
wiki/game/ui-ux/
wiki/game/technical/
wiki/game/assets/
```

Each specification has a stable ID and independent statuses. Live code remains the implementation source of truth. Specifications refer to code with project-relative references:

```text
project/relative/path
project/relative/path#Symbol
project/relative/path#Symbol@locator
```

Implementation checks under `wiki/game/implementation/` bind a specification ID to exact paths and a checked Git revision:

```yaml
check_id: IMPL-LOCKON-004
subject_id: FEATURE-LOCKON-001
expected_spec: wiki/game/features/FEATURE-LOCKON-001.md
source_revision: abc123def456
build_id: BUILD-2026-08-29-001
checked_paths:
  - src/combat/LockOnSystem.ts#selectTarget@lines 84-139
implementation_status: implemented
validation_status: partial
```

## Derived traceability index

Game mode v2 installs:

```text
wiki/game/traceability.json
tools/game_trace.py
```

The JSON index is derived, not manually edited. The runtime scans canonical spec, implementation-check, build, playtest, and decision frontmatter and produces these graph edges:

```text
spec --implemented_by--> code
spec --built_in--------> build
spec --validated_by----> test
spec --governed_by-----> decision
```

This supports both directions:

- Which code implements this design?
- Which designs are affected by this code path?
- Which builds and playtests validate this specification?
- Which decisions govern or supersede it?

### Commands

```bash
python tools/game_trace.py rebuild
python tools/game_trace.py verify
python tools/game_trace.py verify --strict-stale
python tools/game_trace.py spec FEATURE-LOCKON-001
python tools/game_trace.py path src/combat/LockOnSystem.ts#selectTarget
python tools/game_trace.py affected --base HEAD~1 --head HEAD
python tools/game_trace.py matrix
```

### Staleness

For an implementation edge with a checked `source_revision`, the runtime asks Git whether the linked path changed after that revision.

```text
current     the path did not change after the implementation check
stale       the path changed and the design-code match must be rechecked
unverified  no comparable implementation check or revision exists
missing     the tracked live path no longer exists
```

`stale` is a review signal, not an automatic claim that either the design or implementation is wrong.

## Installed structure

Game mode adds:

- `wiki/game/` sections for vision, features, systems, levels, content, narrative, UI/UX, technical work, implementation checks, assets, playtests, builds, bugs, decisions, proposals, milestones, and releases
- `wiki/game/traceability.json`
- `raw/game/` immutable evidence folders
- `templates/game/`
- `instructions/game-project.md`
- `tools/game_trace.py`
- project-local `game-project` skills for Codex and Claude
- `project_mode: game`, version, metadata, and traceability paths in `.llm-wiki.json`

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

Only `project_name` and `domain_summary` are required for `new` and `migrate`.

## Create, migrate, and upgrade

Standard + Game:

```bash
python scripts/game_project.py --target ./MyGame --config ./config.json --mode new --profile standard
```

Evidence + Game:

```bash
python scripts/game_project.py --target ./MyGameResearch --config ./config.json --mode new --profile evidence
```

Migrate an existing live game folder without moving source or assets:

```bash
python scripts/game_project.py --target ./ExistingGame --config ./config.json --mode migrate --profile standard
```

Upgrade or add game mode from the latest validated GitHub commit:

```bash
python scripts/game_project.py --target ./ExistingWiki --config ./config.json --mode upgrade
```

Explicit local/offline bundle:

```bash
python scripts/game_project.py --target ./ExistingWiki --config ./config.json --mode upgrade --source local
```

A game-mode Wiki should not use only `scripts/upgrade.py`; `game_project.py --mode upgrade` advances the base Wiki, game overlay, and traceability runtime together.

## Templates and skill operations

The overlay provides templates for features, systems, levels, content, implementation checks, playtests, builds, decisions, asset briefs, bugs, and milestones.

The project-local `game-project` skill routes work into:

- `define`
- `plan`
- `implement`
- `inspect`
- `trace`
- `impact`
- `playtest`
- `build`
- `decide`
- `bug`
- `release`

Canonical game documents must be followed by `game_trace.py rebuild` and `verify`. Release or completion gates can use `verify --strict-stale`.

## Evidence + Game

With the Evidence profile, raw playtests, logs, telemetry, and external analyses become Sources. Empirical generalizations become Claims; counterexamples remain contradictions or Conflicts; and revalidation can become Experiments.

The traceability graph answers **which design is connected to which code, build, test, and decision**. The Evidence graph answers **which original evidence supports a conclusion**. They complement each other but are not interchangeable.

## Safe GitHub upgrade

Before modifying the target, the game updater validates the repository's current default branch, exact 40-character HEAD SHA, exact-SHA archive, archive path safety, base Wiki contract, game wrapper, templates, skills, traceability template, and runtime. Existing managed game skills and `tools/game_trace.py` are backed up.

Failure leaves the target untouched and never silently falls back to an older local bundle.

## Non-goals

Game mode does not install a game engine, fully interpret every proprietary binary engine format, guarantee a successful build, approve design choices, promote Canon, replace an issue tracker, reorganize live source, or infer a semantic design change from a code diff alone.
