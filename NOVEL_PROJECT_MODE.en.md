# Novel project mode — v1

`novel` adds fiction planning, drafting and revision to a file-based LLM Wiki.
It is independent of lifecycle (`new`, `migrate`, `upgrade`) and vault profile (`standard`, `evidence`).
Use `standard + novel` by default. Evidence is useful for factual research; fictional author-approved
canon is not a verified real-world claim.

## Quick start

Python 3.10+ and Claude Code or Codex are required. No additional Python packages or graph service
are needed for Novel checks. Copy [config.novel.example.json](config.novel.example.json) and edit the
project name, domain summary, novel title, genre, audience and project phase.

```bash
python scripts/novel_project.py --target ./MyNovel --config ./config.novel.json --mode new --dry-run
python scripts/novel_project.py --target ./MyNovel --config ./config.novel.json --mode new
```

Dry-run performs installation and verification in staging, prints the write plan, then removes staging.
It does not create the final vault or missing parent directories. Use `migrate` for an existing folder;
original manuscripts and research are preserved without automatic relocation.
`bootstrap.py --project-mode novel` and config `project_mode: novel` also select this installer.

## Data and writing workflow

| Location | Purpose |
| --- | --- |
| `raw/novel/research/`, `raw/novel/imports/` | Immutable research and imported originals |
| `wiki/novel/characters/`, `locations/`, `world/` | Characters, places and world rules |
| `wiki/novel/arcs/`, `chapters/`, `scenes/` | Narrative structure and reading order |
| `wiki/novel/timeline/`, `foreshadowing/` | In-world event time, setup and payoff |
| `wiki/novel/reviews/`, `decisions/` | Review evidence and author decisions |
| `manuscripts/novel/drafts/`, `revisions/` | Editable drafts and revision versions |
| `Output/novel/` | Shareable outputs |
| `templates/novel/` | Ten templates for the document types above |

The installer adds `novel-project` under `.agents/skills/` and a canonical-pointer Claude adapter
under `.claude/skills/`. Read `wiki/novel/index.md`, `wiki/novel/model.md` and
`instructions/novel-project.md` first. Common ingest/query/lint/audit/session-memory skills remain available.
Research ingestion uses the generic engine. No Novel ingest adapter or automatic graph indexing is installed;
Novel does not change the common ingest graph policy or move working manuscripts to Raw.

Use `$novel-project` or `/novel-project` to plan characters and world rules, outline chapters and scenes,
draft a scene, revise prose while preserving the requested voice, or review continuity, causality,
timeline, point of view, motivation and foreshadowing. Semantic reviews cite actual files and passages
and separate observation, interpretation, suggestions and author decisions.

## Metadata contract

Every structured document has a unique stable ID: `character_id`, `location_id`, `rule_id`, `arc_id`,
`chapter_id`, `scene_id`, `event_id`, `foreshadow_id`, `review_id` or `decision_id`.
IDs start with a Latin letter and contain letters, digits, hyphens or underscores.
References use IDs; `manuscript_ref` is a vault-relative path inside `manuscripts/novel/`.

- A chapter has positive integer `order` and `scene_refs`.
- A scene has positive integer `sequence`, `chapter_ref`, optional `pov_ref`, `character_refs`,
  `location_ref`, `rule_refs`, `event_refs` and `manuscript_ref`.
- A timeline event has integer `time_start`/`time_end` in a shared author-defined unit.
- A foreshadow record has `setup_scene_refs`, `payoff_scene_refs` and optional `target_chapter_ref`.
- Reviews and decisions use `document_refs` for any Novel document type.
- Unassigned order/time is `null`. Keep story chronology separate from reading/revelation order.

Settings use `canon_status: proposed | accepted | deprecated`; only author adoption makes a setting accepted.
Chapters/scenes use `status: planned | drafted | revised | published | cut`.
Arcs use `planned | drafted | revised | completed | cut`; foreshadowing uses `planned | seeded | resolved | dropped`.
Reviews use `open | resolved | dismissed`; decisions use `proposed | accepted | rejected | superseded`.
The mere existence of a document or a passed structural check never marks prose complete or published.

Markdown frontmatter supports top-level scalars, JSON arrays and two-space block lists.
Nested objects, multiline values and inline comments are unsupported. Unicode titles and prose work.

## Read-only checks

Run from the vault, or put `--root <VAULT>` before the command.

```bash
python tools/novel_check.py status
python tools/novel_check.py check
python tools/novel_check.py outline
python tools/novel_check.py trace CHAR-001
```

Checks cover duplicate IDs/order, missing or mistyped references, chapter/scene mismatches,
manuscript existence and safe paths, reversed declared time ranges, missing foreshadow setup/payoff,
and unresolved foreshadowing whose target chapter is published. Early payoffs and overdue records are
warnings for author review. All commands return JSON without writing files.
`check` exits 1 for errors and 0 for warnings only. Successful status/outline/trace reads exit 0;
inspect `has_errors`, `summary` and `issues` too.

`semantic_review: not_performed` makes the limit explicit. The runtime does not judge prose quality,
contradictions in natural language, POV leaks, character motivation or publication readiness.

## Migration and upgrades

Installation validates config, bundle, profile, mode version, symlinks and free space before staging.
Existing Raw and manuscripts stay unchanged. Conflicting user documents become `.wiki-proposed` files;
existing proposals are preserved using numbered alternatives. Managed scripts/skills are backed up before
replacement. Post-apply verification failure restores the old vault. A successful migration/upgrade retains
a full prior-vault copy at `rollback_backup`; clean it separately after review.
`project_mode_activation_pending` means routing/instruction proposals still need review.
Game mode and future Novel versions are never silently replaced, and Evidence cannot downgrade to Standard.
Owned runtime/skill paths are recorded in `novel_managed_assets`. Files only proposed during migration
remain user-owned on subsequent upgrades until the proposed content is adopted.

```bash
python scripts/novel_project.py --target ./MyNovel --config ./config.novel.json --mode upgrade --dry-run
python scripts/novel_project.py --target ./MyNovel --config ./config.novel.json --mode upgrade
```

Upgrade resolves the official GitHub default branch's exact commit and runs that downloaded Novel installer.
Network/archive/contract failures happen before target mutation; a checkout without Novel support is rejected.
Generic `scripts/upgrade.py` also refreshes the base Wiki and Novel assets together.
For an unpublished development bundle or explicit offline operation, use `--source local`.
Omitted metadata survives upgrades; an empty `{}` config is supported. No silent local fallback is used.
