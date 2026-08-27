# llm-wiki-bootstrap

[한국어](README.ko.md) · [English](README.en.md)

A Claude Code / Codex skill that turns a folder into an **AI-operated personal knowledge vault (LLM Wiki)**, migrates an existing folder non-destructively, or upgrades an existing Wiki.

The default `standard` profile provides a lightweight `raw → wiki → Output` personal knowledge workflow. The `evidence` profile adds **source provenance, atomic Claims, Conflicts, Experiments, Open Questions, and reviewed Canon** for reverse engineering, technical research, multi-LLM analysis, and other work where observed facts must remain separate from inference and hypothesis.

> Core Evidence principle: **Never treat “an LLM said it” as equivalent to “we verified it.”**

## Highlights

- Three-layer `raw/` immutable source → `wiki/` AI-maintained knowledge → `Output/` deliverable structure
- Lifecycle `mode` is separate from knowledge-management `profile`
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
- `.llm-wiki.json` manifest for schema/profile state
- Evidence source lineage, epistemic states, and trace/verify/challenge queries

## Core model: lifecycle mode and vault profile are different axes

### Lifecycle mode

Lifecycle mode answers **what should happen to the target folder?**

| Mode | Target | Behavior |
|---|---|---|
| `new` | Empty or missing folder | Build a new Wiki |
| `migrate` | Existing non-Wiki folder with accumulated material | Add Wiki scaffolding while preserving existing files |
| `upgrade` | Existing Wiki with `raw/` + `wiki/` | Preserve knowledge/Raw, back up operational assets, then refresh them |

### Vault profile

Vault profile answers **how should knowledge be managed?**

| Profile | Best for | Core flow |
|---|---|---|
| `standard` | Study, personal Wiki, article/video/book notes, project notes, second brain | `raw → wiki → Output` |
| `evidence` | Reverse engineering, implementation inference, technical research, multi-LLM analysis, hypothesis/experiment/refutation tracking | `Raw → Source → Claim → Evidence/Conflict/Experiment → reviewed Canon` |

The axes are orthogonal, so all of these are valid:

```text
new + standard
new + evidence
migrate + standard
migrate + evidence
upgrade + standard
upgrade + evidence
```

However, `upgrade` does **not** automatically downgrade Evidence → Standard. Removing or weakening Evidence records requires a separately designed migration.

## Automatic profile selection

If the user explicitly names a profile, that choice wins. Otherwise `standard` is the safe default for ordinary knowledge management.

`evidence` is appropriate when one or more of these are central:

- reverse engineering or inference about hidden implementation
- accumulating analyses from ChatGPT/Qwen/Claude/Codex or other LLMs
- separating direct observation from inference/hypothesis
- preserving provenance and source lineage
- keeping conflicting and rejected claims
- hypothesis → controlled experiment → conclusion loops
- tracing important conclusions back to original material

During `upgrade`, omitting `--profile` preserves the existing `.llm-wiki.json` profile. A legacy Wiki without a manifest is treated as `standard` for compatibility.

## Installation

### Claude Code

```bash
git clone https://github.com/gupilleveldesigner/llm-wiki-bootstrap "$HOME/.claude/skills/llm-wiki-bootstrap"
```

### Codex

```bash
git clone https://github.com/gupilleveldesigner/llm-wiki-bootstrap "$HOME/.codex/skills/llm-wiki-bootstrap"
```

The repository includes `agents/openai.yaml` for Codex.

### Requirements

- Claude Code or Codex
- Python 3.10+
- Graphify is optional

The bootstrap can use `python`, `py -3`, or `python3`. On Windows, use a real Python installation rather than the Microsoft Store stub.

## Usage

Claude Code:

```text
/llm-wiki-bootstrap
```

Codex can invoke the installed skill or use a natural-language request:

```text
$llm-wiki-bootstrap
```

Examples:

```text
Build an LLM Wiki for my cooking research.
Convert this folder into a Wiki without deleting or overwriting my existing files.
Build an Evidence Wiki that separates observations, hypotheses, experiments, and Canon.
Upgrade this existing Standard Wiki to the Evidence profile.
```

Bootstrap does not re-ask information already supplied. If needed, it performs one short interview covering:

1. Wiki topic and purpose
2. Main source/material types
3. Project name

Those answers drive `project_name`, `domain_summary`, and the initial overview/questions/taxonomy.

## CLI

Base config:

```json
{
  "project_name": "My Wiki",
  "domain_summary": "One-sentence purpose of the project"
}
```

Create a Standard Wiki:

```bash
python scripts/bootstrap.py \
  --target ./MyWiki \
  --config ./config.json \
  --mode new \
  --profile standard
```

Create an Evidence Wiki:

```bash
python scripts/bootstrap.py \
  --target ./ResearchWiki \
  --config ./config.json \
  --mode new \
  --profile evidence
```

Migrate an existing folder into Evidence:

```bash
python scripts/bootstrap.py \
  --target ./ExistingProject \
  --config ./config.json \
  --mode migrate \
  --profile evidence
```

Promote an existing Standard Wiki to Evidence:

```bash
python scripts/bootstrap.py \
  --target ./ExistingWiki \
  --config ./config.json \
  --mode upgrade \
  --profile evidence
```

For `new`/`migrate`, omitting `--profile` means `standard`. For `upgrade`, an existing manifest profile is preserved by default.

## Standard profile layout

Representative structure:

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

`raw/` is immutable source material, `wiki/` is curated AI-maintained knowledge, and `Output/` is for external deliverables.

## Evidence profile layout

Evidence extends the Standard structure rather than replacing it:

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

### Source records

Each Raw source has a one-to-one record under `wiki/sources/`. When available, it records:

- `raw_sha256`
- provider/model
- created/ingested time
- source locator (section, line, message, function, etc.)
- `parent_sources`
- verification/epistemic state

External LLMs are Sources, not Authorities. Their outputs return to Raw and do not edit Canon directly.

### Source lineage and independence

These are not automatically three independent pieces of evidence:

```text
ChatGPT answer
  ↓ forwarded
Qwen answer
  ↓ forwarded
Codex answer
```

When outputs share an information lineage, record `parent_sources` or equivalent provenance and do not count dependent repetitions as independent evidence.

### Claims

Reusable knowledge is extracted as **atomic Claims**, not by treating an entire summary as a single truth.

Allowed Claim states:

| State | Meaning |
|---|---|
| `OBSERVED` | Directly observed in source/code/log/runtime result |
| `INFERRED` | Reasonably inferred from observations but not directly verified |
| `HYPOTHESIS` | Active hypothesis requiring validation |
| `SUPPORTED` | Multiple sources/experiments support it, but no decisive proof |
| `CONFIRMED` | Direct evidence or sufficiently controlled reproduction exists |
| `REJECTED` | Refuted; retained rather than deleted |
| `DISPUTED` | Valid contradictory evidence exists |
| `DEPRECATED` | Kept only as historical knowledge |
| `UNKNOWN` | Current evidence is insufficient |

Numeric confidence is only a secondary signal and does not outrank the state.

At minimum, Claim-source relations distinguish:

```text
originates
supports
contradicts
derived_from
mentions
```

When the evidence is missing, leave the result `UNKNOWN` rather than filling gaps with plausible guesses.

### Conflicts, Experiments, and Questions

- `wiki/conflicts/` — preserves unresolved conflicting Claims instead of forcing a merge
- `wiki/experiments/` — records hypothesis, setup, control, variant, metrics, and result
- `wiki/questions/open/` — unresolved research questions
- `wiki/questions/answered/` — answered questions
- `wiki/questions/blocked/` — questions blocked by missing evidence/tools

Failed experiments and rejected Claims remain useful research history.

### Canon

`wiki/canon/` stores the project's **currently adopted, reviewed knowledge** and should remain small.

Claims are never auto-promoted to Canon, even when an LLM reports high confidence.

Minimum review criteria:

1. source quality
2. source independence / lineage
3. contradictory evidence
4. experiment evidence
5. direct observation
6. conflicts with existing Canon

`canon-review` produces a recommendation using these criteria. Its default behavior is read-only; Canon changes require an explicit promotion/status-change request.

## Operational skills

### `ingest`

Ingest keeps `raw/` immutable while reflecting source material into `wiki/`.

Base completion contract:

- never modify Raw
- each Raw source needs a one-to-one `wiki/sources/<source>.md` summary
- a catalog that merely lists Raw paths is not completion evidence
- source summaries must contain real content evidence such as the Raw path and SHA-256
- categories come from the controlled `wiki/taxonomy.json`
- batch completion must pass category audit and an independent verification gate
- when Graphify is required for a batch, run the host Graphify action, record its run manifest, then pass `verify --complete-batch --require-graph`
- on failure, reprocess only failed sources through `scan → ingest → finalize → verify`

Evidence adds:

```text
Raw
→ Source Record
→ atomic Claim
→ support / contradiction
→ Conflict / Experiment / Open Question
→ Canon candidate/review-needed state
```

Automation stops there. **Ingest never auto-edits Canon.**

### `query`

Standard query uses progressive disclosure:

```text
catalog/index
→ candidate frontmatter
→ selected body
→ Raw only when exact verification is necessary
```

It does not fill Wiki gaps from model memory, and it surfaces contradictions, stale knowledge, and unverified state.

Evidence query modes:

| Mode | Behavior |
|---|---|
| `answer` | Answer current knowledge via Canon → CONFIRMED/SUPPORTED → OBSERVED |
| `research` | Inspect Canon, Claims, Conflicts, Experiments, Questions, and relevant Raw |
| `verify` | Verify a specific Claim against supporting/contradicting evidence and Raw |
| `challenge` | Prioritize disputed/rejected Claims, conflicts, failed experiments, and possible refutation |
| `trace` | Follow `Canon → Claim → Evidence/Experiment → Source → Raw locator` |
| `compare` | Compare Claims using source quality, independence, direct evidence, experiments, and contradictions |

`answer` is the default. Questions such as “why do we think this?”, “trace the evidence”, or “is this actually true?” should prefer `trace`/`verify`.

### `lint`

Standard lint checks:

- broken Wiki links
- frontmatter
- missing index entries
- orphan pages
- source links
- freshness/staleness

Only mechanical fixes with one clear answer are applied automatically. Semantic merges, deletion, factual decisions, and meaningful status changes are not auto-fixed.

Evidence lint also checks epistemic integrity:

- Claims with no source
- nonexistent source/claim/experiment/conflict IDs
- broken Canon → Claim trace
- broken Claim → Raw locator trace
- `parent_sources` cycles/breaks
- `CONFIRMED` with no recorded direct/validation evidence
- current Canon depending on a `REJECTED` Claim
- unresolved conflicts hidden behind definitive language
- orphan experiments/conflicts
- obvious duplicate Claim families
- `raw_sha256` mismatch

### `session-memory`

Typing `SAVE` persists session state through a lock/journal-based atomic transaction. It does not record unfinished work or unexecuted validation as complete. New sessions resume from the root `log.md`.

### `brief-tuner`

Tunes work-brief templates to the user's workflow through an interview.

### `wiki-audit`

Read-only audit of installation state, operational skills, Graphify host prerequisites, and contract consistency.

### `canon-review` — Evidence only

Reviews Claim source quality, lineage independence, contradictions, experiments, direct observations, and existing Canon conflicts to recommend outcomes such as:

```text
promote
keep current state
dispute
reject
needs more evidence
```

The default is **review only**, not automatic promotion.

## Taxonomy

`wiki/taxonomy.json` uses a lightweight SKOS-shaped controlled vocabulary.

Core fields:

```text
prefLabel
altLabel
broader
scopeNote
```

Graphify community names are not copied into taxonomy automatically. Graphify is a discovery aid, not taxonomy and not truth.

## Graphify

Graphify is optional.

### Codex

```bash
python -m pip install graphifyy
graphify install --platform codex
```

Then use the host skill with the current Codex authentication:

```text
$graphify <WIKI_ROOT>
$graphify <WIKI_ROOT> --update
```

For parallel execution, check `[features] multi_agent = true` in `~/.codex/config.toml`.

Only if you want always-on graph-first routing, optionally run:

```bash
graphify codex install
```

That installs a hook/router; it does not build the graph.

### Claude Code

```bash
python -m pip install graphifyy
graphify install
```

Then:

```text
/graphify <WIKI_ROOT>
/graphify <WIKI_ROOT> --update
```

Do not invoke bare `graphify <path>` or `graphify update .` from a Python subprocess. Use the host assistant's Graphify skill so its authentication and execution contract are preserved.

After Graphify runs, record the run manifest in the ingest runtime and pass the independent verification gate before reporting batch completion. If Graphify is unavailable or fails, do not falsely report batch completion. A single-source operation may explicitly report local-only validation.

Graphify remains a **navigation/visualization aid** in Evidence; it is not the truth database.

## Obsidian Web Clipper

`templates/web-clipper/` includes templates for collecting web articles, YouTube, books, and podcasts under `raw/reference/`.

If you use Obsidian, open the generated folder as a Vault and import the JSON templates following `templates/web-clipper/` instructions.

Collected Raw remains unchanged; `/ingest` reflects it into the Wiki layer.

## `migrate` — non-destructive conversion of an existing folder

`migrate` adds Wiki scaffolding without deleting or modifying existing files.

1. Infer topic/material types from existing files and ask only for missing interview information
2. Scaffold the selected profile
3. When root documents conflict, create `.wiki-proposed` files
4. Build a per-file plan showing **destination under `raw/` + original path**
5. Move files **only after user approval**
6. Preserve original paths as a recovery map
7. Run `/ingest` batch after the move
8. Check Graphify/smoke/completion gates

Bootstrap itself does not silently move pre-existing content into Raw.

## `upgrade` — refresh an existing Wiki

`upgrade` preserves existing `raw/`, Wiki knowledge, and `Output/`.

Existing installed skills and the session-memory runtime are backed up before replacement under:

```text
.wiki-upgrade-bak/<timestamp>/
```

Keep the current profile:

```bash
python scripts/bootstrap.py \
  --target ./ExistingWiki \
  --config ./config.json \
  --mode upgrade
```

### Standard → Evidence

```bash
python scripts/bootstrap.py \
  --target ./ExistingWiki \
  --config ./config.json \
  --mode upgrade \
  --profile evidence
```

This adds:

- Evidence directories
- Evidence model/operations docs
- Evidence templates
- `canon-review`
- updated `.llm-wiki.json`

If existing `CLAUDE.md`, `AGENTS.md`, or `wiki/CLAUDE.md` lacks the Evidence router, bootstrap creates `.wiki-proposed` rather than overwriting the original.

If the result contains:

```text
profile_activation_pending: true
```

the Evidence transition should not be treated as fully activated until those router proposals are reviewed and merged.

Differences in existing `instructions/wiki-operations.md`, `.graphifyignore`, `wiki/taxonomy.json`, and other protected user-managed documents are also handled non-destructively where applicable.

## Manifest: `.llm-wiki.json`

New and migrated Wikis receive a root manifest.

Representative fields:

```json
{
  "schema_version": 2,
  "profile": "evidence",
  "raw_immutable": true,
  "created_with": "llm-wiki-bootstrap",
  "project_name": "Research Wiki",
  "created_at": "...",
  "updated_at": "..."
}
```

Known existing manifest data is preserved while bootstrap-managed fields are refreshed.

## Router documents

- `CLAUDE.md` — always-loaded Claude project router
- `AGENTS.md` — Codex router
- `raw/CLAUDE.md` — immutable Raw rules
- `wiki/CLAUDE.md` — Wiki operation rules
- `Output/CLAUDE.md` — deliverable-layer rules
- `instructions/wiki-operations.md` — shared Wiki operation contract
- Evidence adds `wiki/evidence-model.md` and `instructions/evidence-operations.md`

Evidence overlays use a stable marker so the same router block is not repeatedly proposed.

## Ingest completion criteria

“the file exists”, “the catalog exists”, or “the graph exists” is not enough to report successful ingest.

Batch completion requires at least:

1. each target Raw source is classified as processed/excluded/failed
2. every processed Raw source has a content-bearing one-to-one source summary
3. taxonomy/category audit passes
4. if the batch requires Graphify, host graph build/update succeeds
5. the Graphify run manifest is recorded
6. `verify --complete-batch --require-graph` passes
7. any remaining pending/catalog-only/failed item keeps the result incomplete

Completion reports include:

```text
input sources
processed
verified
excluded
failed/unprocessed
graph nodes
graph links
```

## Recovery and data durability

The core rule is **separate durable truth from rebuildable derived data**.

### Durable

Standard:

```text
raw/
wiki/
required Output artifacts
```

Evidence especially preserves:

```text
raw/
wiki/sources/
wiki/claims/
wiki/canon/
wiki/experiments/
```

### Rebuildable

```text
.wiki-cache/normalized/
.wiki-cache/index/
.wiki-cache/embeddings/
Graphify outputs
other derived caches/indexes
```

If cache or graph data is lost, it should be recoverable from Raw and reviewed records.

## Safety rules

- never mutate `raw/`
- never silently overwrite conflicting knowledge
- never move existing files during `migrate` without user approval
- never delete existing knowledge/Raw during `upgrade`
- prefer `.wiki-proposed` when user-maintained documents conflict
- external LLM output is a Source, not Authority, in Evidence
- do not over-count dependent LLM lineage as independent evidence
- leave unknowns as `UNKNOWN`
- retain rejected Claims
- never auto-promote Canon
- do not auto-apply semantic lint fixes
- do not treat `.wiki-cache/` or Graphify outputs as truth
- do not auto-downgrade Evidence → Standard

## Post-bootstrap smoke checks

At minimum:

```bash
python ".claude/skills/ingest/scripts/ingest_runtime.py" status
python ".session-memory/scripts/session_memory.py" status
```

Confirm:

- `wiki/index.md`
- `CLAUDE.md`
- `raw/CLAUDE.md`
- `.llm-wiki.json`

For Evidence also confirm:

- `wiki/evidence-model.md`
- `instructions/evidence-operations.md`
- `.agents/skills/canon-review/SKILL.md`

Do not report success if rendered documents still contain unresolved `{{...}}` placeholders.

## Design principles

1. **Raw immutable** — original evidence survives incorrect summaries.
2. **Non-destructive migration** — preserve existing data first.
3. **Filesystem as durable truth** — DB/cache/graph layers must be rebuildable.
4. **Progressive disclosure** — Query reads only what the task needs.
5. **Source before assertion** — reusable claims need provenance.
6. **Lineage-aware evidence** — dependent repetitions are not independent evidence.
7. **No automatic Canon promotion** — confidence is not truth.
8. **Conflict preservation** — do not silently erase or force-merge contradictions.
9. **Host-authenticated Graphify** — prefer current Claude/Codex host execution over headless provider-key workarounds.
10. **Self-contained distribution** — required operational assets are bundled in the repository.

## Deliberate non-goals

The default install does not require:

- external Vector DB
- Neo4j cluster
- separate MCP server
- microservices
- Kubernetes
- large backend services

Evidence `.wiki-cache/index` and `.wiki-cache/embeddings` reserve rebuildable extension points for future SQLite/FTS/embedding layers; they do not move the source of truth into a database today.

## Differences from related projects

Like `karpathy-llm-wiki` and `claude-obsidian`, this project follows the broader “LLM-managed Wiki” idea, but emphasizes:

- atomic `SAVE` session handoff
- non-destructive `migrate` / `upgrade`
- source-level ingest completion verification
- controlled taxonomy
- host-aware Graphify completion gate
- Evidence Research provenance/lineage/Claim/Conflict/Experiment/Canon model
- Canon review as an explicit gate rather than automatic truth promotion

## License

MIT
