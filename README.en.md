# llm-wiki-bootstrap

[한국어](README.ko.md) · [English](README.en.md)

A Claude Code / Codex skill that builds an **AI-operated personal knowledge vault (LLM Wiki)**, migrates an existing folder non-destructively, and upgrades an existing Wiki's operational skills from the **latest official GitHub repository version**.

The default `standard` profile provides a lightweight `raw → wiki → Output` workflow. The `evidence` profile adds **source provenance, atomic Claims, Conflicts, Experiments, Open Questions, and reviewed Canon** for reverse engineering, technical research, multi-LLM analysis, and other work where verified observations must remain separate from inference and hypothesis.

> Core Evidence principle: **Never treat “an LLM said it” as equivalent to “we verified it.”**

## Highlights

- Three-layer `raw/` immutable source → `wiki/` AI-maintained knowledge → `Output/` deliverable model
- Separate lifecycle `mode` and knowledge-management `profile`
- Non-destructive `new`, `migrate`, and `upgrade` lifecycles
- `standard` and `evidence` vault profiles
- Six base operational skills: `ingest`, `query`, `lint`, `session-memory`, `brief-tuner`, `wiki-audit`
- Evidence-only `canon-review`
- Claude/Codex router documents and project-local skill installation
- One-to-one source summaries, SHA-256, ingest ledger, and completion gates
- SKOS-shaped controlled vocabulary in `wiki/taxonomy.json`
- Optional Graphify knowledge-graph integration
- Optional Obsidian Web Clipper templates
- Atomic cross-session handoff via `SAVE`
- `.wiki-proposed` proposals instead of destructive overwrites
- `.llm-wiki.json` manifest for profile/schema/upgrade provenance
- Evidence source lineage, epistemic states, trace/verify/challenge queries
- **GitHub latest upgrade** — resolve and pin the official repository's current default-branch HEAD commit

## Core model: lifecycle mode and vault profile are different axes

### Lifecycle mode

Lifecycle mode answers **what should happen to the target folder?**

| Mode | Target | Behavior |
|---|---|---|
| `new` | Empty or missing folder | Build a new Wiki |
| `migrate` | Existing non-Wiki folder with accumulated material | Add Wiki scaffolding while preserving existing files |
| `upgrade` | Existing Wiki with `raw/` + `wiki/` | Preserve knowledge/Raw and refresh operational skills/managed assets |

### Vault profile

Vault profile answers **how should knowledge be managed?**

| Profile | Best for | Core flow |
|---|---|---|
| `standard` | Study, personal Wiki, article/video/book notes, project notes, second brain | `raw → wiki → Output` |
| `evidence` | Reverse engineering, implementation inference, technical research, multi-LLM analysis, hypothesis/experiment/refutation tracking | `Raw → Source → Claim → Evidence/Conflict/Experiment → reviewed Canon` |

The axes are orthogonal:

```text
new + standard
new + evidence
migrate + standard
migrate + evidence
upgrade + standard
upgrade + evidence
```

`upgrade` never automatically downgrades Evidence → Standard. Removing or weakening Evidence records requires a separately designed migration.

## Exact upgrade meaning: GitHub latest

In this project, user-facing `upgrade`, `update to latest`, and `refresh the skills` mean:

> **Resolve the current default-branch HEAD of the official `gupilleveldesigner/llm-wiki-bootstrap` GitHub repository, pin the exact commit, and apply that commit's upgrade logic and bundled skills to the target Wiki.**

It does **not** mean “re-copy whatever possibly stale bundle happens to be installed locally.”

### GitHub latest upgrade flow

```text
upgrade request
   ↓
read GitHub repository metadata
   ↓
resolve current default branch
   ↓
resolve that branch's latest 40-char commit SHA
   ↓
download ZIP for that exact SHA
   ↓
validate ZIP safety + required bootstrap/skill bundle paths
   ↓
only now may target Wiki mutation begin
   ↓
run downloaded latest bootstrap.py --mode upgrade
   ↓
back up existing skills
   ↓
apply latest bundled skills/runtime/profile assets
   ↓
verify
   ↓
record exact commit provenance in .llm-wiki.json
```

### Why pin a commit SHA instead of applying a moving branch archive

The updater reads the current default branch first, but applies a ZIP addressed by the **validated exact commit SHA**. This avoids ambiguity if branch HEAD changes between discovery and download.

Successful results include:

```text
upgrade_source: github
bootstrap_repository: gupilleveldesigner/llm-wiki-bootstrap
bootstrap_branch: <current default branch>
bootstrap_commit: <exact 40-char SHA>
```

The target `.llm-wiki.json` also records:

```json
{
  "last_upgrade": {
    "source": "github",
    "repository": "gupilleveldesigner/llm-wiki-bootstrap",
    "branch": "master",
    "commit": "<40-char SHA>",
    "at": "<timestamp>"
  }
}
```

### GitHub failure behavior

If network access, the GitHub API, ZIP download, or archive validation fails, the updater **does not mutate the target Wiki**.

It also does not silently fall back to a stale local bundle. A GitHub-latest request cannot be reported as successful unless the exact GitHub commit was resolved.

### Explicit local/offline upgrade

Only when the user explicitly requests the currently installed local bundle or is intentionally working offline:

```bash
python scripts/upgrade.py \
  --target ./ExistingWiki \
  --config ./config.json \
  --source local
```

This returns `upgrade_source: local` and must **not** be described as GitHub latest.

## Installation

### Claude Code

```bash
git clone https://github.com/gupilleveldesigner/llm-wiki-bootstrap "$HOME/.claude/skills/llm-wiki-bootstrap"
```

### Codex

```bash
git clone https://github.com/gupilleveldesigner/llm-wiki-bootstrap "$HOME/.codex/skills/llm-wiki-bootstrap"
```

Windows PowerShell:

```powershell
git clone https://github.com/gupilleveldesigner/llm-wiki-bootstrap "$env:USERPROFILE\.codex\skills\llm-wiki-bootstrap"
```

For Claude Code, use `.claude` instead of `.codex` in the same command.

The repository includes `agents/openai.yaml` for Codex.

### Requirements

- Claude Code or Codex
- Python 3.10+
- GitHub HTTPS access for online upgrade
- Graphify is optional

The bootstrap can use `python`, `py -3`, or `python3`. A Windows Microsoft Store stub is not treated as a real Python installation.

## Usage

Claude Code:

```text
/llm-wiki-bootstrap
```

Codex:

```text
$llm-wiki-bootstrap
```

Natural-language examples:

```text
Build an LLM Wiki for my cooking research.
Convert this existing folder into a Wiki without losing files.
Build an Evidence Wiki that separates observations, hypotheses, experiments, and Canon.
Upgrade this Wiki's operational skills to the latest GitHub version.
Upgrade this Standard Wiki to the latest version and activate the Evidence profile.
```

Bootstrap does not re-ask information already supplied. If necessary it performs one short interview covering:

1. Wiki topic and purpose
2. Main source/material types
3. Project name

## CLI

Base config:

```json
{
  "project_name": "My Wiki",
  "domain_summary": "One-sentence project purpose"
}
```

The same base example is available as [`config.example.json`](config.example.json); [`config.game.example.json`](config.game.example.json) contains the fuller Game mode example. On Windows, `py -3` may replace `python` in the commands below.

### Create Standard

```bash
python scripts/bootstrap.py \
  --target ./MyWiki \
  --config ./config.json \
  --mode new \
  --profile standard
```

### Create Evidence

```bash
python scripts/bootstrap.py \
  --target ./ResearchWiki \
  --config ./config.json \
  --mode new \
  --profile evidence
```

### Migrate an existing folder into Evidence

```bash
python scripts/bootstrap.py \
  --target ./ExistingProject \
  --config ./config.json \
  --mode migrate \
  --profile evidence
```

### Upgrade an existing Wiki from GitHub latest

```bash
python scripts/upgrade.py \
  --target ./ExistingWiki \
  --config ./config.json
```

### Promote Standard → Evidence while applying GitHub latest

```bash
python scripts/upgrade.py \
  --target ./ExistingWiki \
  --config ./config.json \
  --profile evidence
```

### Internal local apply primitive

`scripts/bootstrap.py --mode upgrade` is **not the user-facing “find latest GitHub version” entry point**. It is the low-level local apply primitive invoked inside the exact checkout downloaded by `upgrade.py`.

Use `scripts/upgrade.py` for user-facing latest upgrade.

## Standard profile layout

```text
MyWiki/
├─ raw/
│  ├─ inbox/
│  ├─ personal/
│  ├─ journal/
│  ├─ archive/
│  ├─ assets/
│  └─ reference/
│     ├─ articles/
│     ├─ youtube/
│     ├─ podcasts/
│     ├─ books/
│     └─ research/
├─ wiki/
│  ├─ entities/
│  ├─ concepts/
│  ├─ projects/
│  ├─ sources/
│  ├─ index.md
│  ├─ overview.md
│  ├─ questions.md
│  ├─ log.md
│  ├─ taxonomy.json
│  └─ ingest-ledger.json
├─ Output/
├─ instructions/
├─ templates/
├─ .agents/skills/
├─ .claude/skills/
├─ .session-memory/
├─ CLAUDE.md
├─ AGENTS.md
├─ log.md
├─ changelog.md
└─ .llm-wiki.json
```

`raw/` is immutable source material, `wiki/` is curated AI-maintained knowledge, and `Output/` holds external deliverables.

## Evidence profile layout

Evidence extends Standard rather than replacing it.

```text
ResearchWiki/
├─ raw/                         # immutable originals
├─ wiki/
│  ├─ sources/                 # 1:1 source records
│  ├─ claims/                  # atomic claims
│  ├─ conflicts/               # conflicting claims
│  ├─ experiments/             # hypothesis tests
│  ├─ questions/
│  │  ├─ open/
│  │  ├─ answered/
│  │  └─ blocked/
│  ├─ canon/
│  │  └─ overview.md
│  └─ evidence-model.md
├─ instructions/
│  └─ evidence-operations.md
├─ templates/
│  └─ evidence/
│     ├─ source-record.md
│     ├─ claim.md
│     ├─ conflict.md
│     ├─ experiment.md
│     └─ canon-entry.md
└─ .wiki-cache/
   ├─ normalized/
   ├─ index/
   └─ embeddings/
```

`.wiki-cache/` is **disposable derived data**, never the source of truth.

## Evidence data model

### Source records

Each Raw source has a one-to-one record under `wiki/sources/`. When available, record:

- `raw_sha256`
- provider/model
- created/ingested time
- source locator (section, line, message, function, etc.)
- `parent_sources`
- verification/epistemic state

External LLMs are Sources, not Authorities. Their outputs return to Raw and do not edit Canon directly.

### Source lineage and independence

```text
ChatGPT answer
  ↓ forwarded
Qwen answer
  ↓ forwarded
Codex answer
```

These are not automatically three independent pieces of evidence. If they share an information lineage, record `parent_sources` or equivalent provenance and do not double-count dependent repetitions.

### Claims

Reusable knowledge is extracted as **atomic Claims**.

| State | Meaning |
|---|---|
| `OBSERVED` | Directly observed in source/code/log/runtime result |
| `INFERRED` | Reasonably inferred but not directly verified |
| `HYPOTHESIS` | Active hypothesis requiring validation |
| `SUPPORTED` | Multiple sources/experiments support it without decisive proof |
| `CONFIRMED` | Direct evidence or sufficiently controlled reproduction exists |
| `REJECTED` | Refuted; retained instead of deleted |
| `DISPUTED` | Valid contradictory evidence exists |
| `DEPRECATED` | Retained only as historical knowledge |
| `UNKNOWN` | Current evidence is insufficient |

Numeric confidence is secondary and never outranks the state.

At minimum, Claim-source relations distinguish:

```text
originates
supports
contradicts
derived_from
mentions
```

When evidence is missing, keep `UNKNOWN` instead of filling gaps with plausible guesses.

### Conflicts / Experiments / Questions

- `wiki/conflicts/` — preserve unresolved conflicting Claims instead of forcing a merge
- `wiki/experiments/` — record hypothesis, setup, control, variant, metrics, result
- `wiki/questions/open/` — unresolved research questions
- `wiki/questions/answered/` — answered questions
- `wiki/questions/blocked/` — blocked by missing evidence/tools

Failed experiments and rejected Claims remain research history.

### Canon

`wiki/canon/` stores the project's **currently adopted, reviewed knowledge** and should remain small.

Claims are never auto-promoted to Canon.

Minimum review criteria:

1. source quality
2. source independence / lineage
3. contradictory evidence
4. experiment evidence
5. direct observation
6. conflicts with existing Canon

`canon-review` produces recommendations and is read-only by default. Canon changes require an explicit promotion/status-change request.

## Operational skills

### `ingest`

Ingest keeps `raw/` immutable while reflecting source material into `wiki/`.

Base completion contract:

- never modify Raw
- each Raw source needs a one-to-one `wiki/sources/<source>.md` summary
- a catalog merely listing Raw paths is not completion evidence
- source summaries need real content evidence such as path and SHA-256
- categories come from controlled `wiki/taxonomy.json`
- batch completion passes category audit and an independent verification gate
- when Graphify is required, run host Graphify, record the run manifest, then pass `verify --complete-batch --require-graph`
- on failure, reprocess only failed sources through `scan → ingest → finalize → verify`

Evidence extends the pipeline through:

```text
Raw → Source Record → atomic Claim → support/contradiction → Conflict/Experiment/Open Question → review-needed
```

**Ingest never auto-edits Canon.**

### `query`

Standard query uses progressive disclosure:

```text
catalog/index → candidate frontmatter → selected body → Raw only when exact verification is needed
```

It never fills Wiki gaps from model memory and surfaces contradictions, stale knowledge, and unverified states.

Evidence query modes:

| Mode | Behavior |
|---|---|
| `answer` | Canon → CONFIRMED/SUPPORTED → OBSERVED |
| `research` | Canon, Claims, Conflicts, Experiments, Questions, relevant Raw |
| `verify` | Verify a Claim against supporting/contradicting evidence and Raw |
| `challenge` | Prioritize disputed/rejected Claims, conflicts, failed experiments, refutation |
| `trace` | Follow `Canon → Claim → Evidence/Experiment → Source → Raw locator` |
| `compare` | Compare source quality, independence, direct evidence, experiments, contradictions |

### `lint`

Standard lint checks links, frontmatter, index registration, orphan pages, source links, and freshness. Only mechanical fixes with one unambiguous answer are auto-applied.

Evidence additionally checks:

- Claims with no source
- nonexistent source/claim/experiment/conflict IDs
- broken Canon → Claim trace
- broken Claim → Raw locator trace
- `parent_sources` cycles/breaks
- `CONFIRMED` with no recorded validation evidence
- current Canon depending on a `REJECTED` Claim
- hidden unresolved conflicts
- orphan experiments/conflicts
- obvious duplicate Claim families
- `raw_sha256` mismatch

### `session-memory`

`SAVE` persists session state through a lock/journal-based atomic transaction. Unfinished work and unrun verification are not recorded as completed.

### `brief-tuner`

Interview-driven tuning of AI work briefs/templates to the user's work pattern.

### `wiki-audit`

Read-only audit of installed skills, runtimes, Graphify environment, and Wiki contracts.

### `canon-review` — Evidence only

Reviews source quality, source independence/lineage, contradictory evidence, experiments, direct observation, and Canon conflicts. It recommends by default rather than auto-promoting.

## Taxonomy

`wiki/taxonomy.json` uses a lightweight SKOS-shaped controlled vocabulary:

- `prefLabel`
- `altLabel`
- `broader`
- `scopeNote`

Graphify community names are discovery aids, not taxonomy or truth.

## Graphify

Graphify is an optional exploration/visualization aid.

Codex:

```text
$graphify <WIKI_ROOT>
$graphify <WIKI_ROOT> --update
```

Claude:

```text
/graphify <WIKI_ROOT>
/graphify <WIKI_ROOT> --update
```

Do not invoke bare `graphify <path>` from a Python subprocess. After the host Graphify run, record it with `ingest_runtime.py record-graphify-run --host codex|claude` and run required batch verification.

Even in Evidence, Graphify is not the truth database. Markdown/frontmatter and Raw provenance remain canonical.

## Migrate safety

- refuse apply when the target or any descendant is a symlink, preventing writes outside the Wiki root
- never delete or rewrite existing files
- root document conflicts become `.wiki-proposed`
- produce a per-file old-path → Raw destination migration map
- move files only after user approval
- run batch `/ingest` afterward
- do not move project configuration such as `.git` into Raw

## Upgrade safety

- GitHub latest is the default
- no target mutation until remote resolution/download/archive validation succeeds
- complete and verify the upgrade in sibling transaction staging, then apply with same-filesystem renames
- restore the original Wiki if apply or post-apply verification fails
- require temporary same-filesystem capacity for a staged vault copy during upgrade
- pin an exact SHA before execution
- back up existing operational skills under a collision-safe `.wiki-upgrade-bak/<timestamp>-<unique-id>/`
- preserve `raw/`, existing knowledge, and `Output/`
- customized router/operations documents use `.wiki-proposed`
- Standard → Evidence adds Evidence folders/templates/canon-review
- when router proposals are required, return `profile_activation_pending: true`
- refuse automatic Evidence → Standard downgrade
- never claim a GitHub-latest upgrade complete without reporting the exact `bootstrap_commit`

## Obsidian Web Clipper

Templates under `templates/web-clipper/` can collect web sources under `raw/reference/`. Collected Raw is still source material, not automatically accepted knowledge.

## Preservation and recovery boundary

### Preserve long-term

- `raw/`
- `wiki/sources/`
- `wiki/claims/` (Evidence)
- `wiki/canon/` (Evidence)
- `wiki/experiments/` (Evidence)
- relevant `.session-memory/` handoff records

### Regenerable

- `.wiki-cache/normalized/`
- `.wiki-cache/index/`
- `.wiki-cache/embeddings/`
- Graphify output
- derived indexes/caches

Raw and reviewed records are durable; caches/indexes are disposable.

## Smoke check

After build/migrate/upgrade:

```bash
python ".claude/skills/ingest/scripts/ingest_runtime.py" status
python ".session-memory/scripts/session_memory.py" status
```

Verify:

- correct target root
- `wiki/index.md`, `CLAUDE.md`, `raw/CLAUDE.md`, `.llm-wiki.json`
- no unresolved render placeholders
- Evidence has `wiki/evidence-model.md`, `instructions/evidence-operations.md`, `canon-review`
- upgrade result includes `upgrade_source`, `bootstrap_commit`, `backup_dir`
- GitHub result SHA matches `.llm-wiki.json.last_upgrade.commit`
- batch ingest completion gates actually passed before reporting completion

## Design principles

- Raw is immutable
- LLM output is a Source, not Authority, in Evidence
- Claim and Canon are separate
- dependent lineage is not over-counted as independent evidence
- conflicts, rejected Claims, and failed experiments are retained
- unknown stays `UNKNOWN`
- Canon is never auto-promoted
- migrate/upgrade remain non-destructive
- GitHub latest upgrade records exact commit provenance
- remote failure is never hidden by stale local fallback
- DB/embedding/Graphify never replace Raw/Markdown canonical data

## Non-goals

The default installation does not require:

- Kubernetes
- large Vector DBs
- Neo4j clusters
- microservices
- an external DB as source of truth

The system remains file/Markdown-centered, with indexes/caches designed to be regenerable.

## License

MIT
