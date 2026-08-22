# Wiki operations

## Three-layer model

1. `raw/` is immutable source material. Store inputs by type and do not modify them afterward.
2. `wiki/` is the AI-maintained knowledge layer. Summarize, connect, and update knowledge here.
3. `Output/` contains external deliverables grounded in verified wiki knowledge.

Folder-specific rules live in `raw/CLAUDE.md`, `wiki/CLAUDE.md`, and `Output/CLAUDE.md`.

## Workflow routing

- Ingest: store the source in `raw/`, update `wiki/`, then update `wiki/index.md` and `wiki/log.md`. Read the installed `ingest` skill before executing.
- Ingest evidence is file-level, not catalog-level: each raw source needs a one-to-one source summary (normally `wiki/sources/` with `type: source`) and a raw citation. A catalog that merely lists raw paths does not count.
- For a batch completion, run `ingest_runtime.py finalize --complete-batch`; any `pending` or `catalog_only` source must keep the result `미완료`.
- `finalize --complete-batch` installs `graphifyy` and builds the initial graph when Graphify is missing. Installation or graph build failure blocks completion.
- Run the read-only independent gate `ingest_runtime.py verify --complete-batch --require-graph`. If it fails, reprocess only the returned sources and repeat `scan → ingest → finalize → verify`.
- The runtime records the file ledger at `wiki/ingest-ledger.json`. Do not edit `raw/` to update statuses.
- Query: start from `wiki/index.md`; open `raw/` only when exact source verification is necessary. Read the installed `query` skill before executing.
- Lint: use the installed `lint` skill for broken links, isolated documents, and stale claims.

## Graphify

- When `graphify-out/graph.json` exists, use `graphify query` first for cross-file relationships, broad navigation, or architecture questions.
- Use `graphify path` for relationships and `graphify explain` for a focused concept.
- Prefer `graphify-out/wiki/index.md` for broad navigation when present.
- Read `graphify-out/GRAPH_REPORT.md` only for broad architecture review or when scoped graph commands are insufficient.
- Exact-file edits, formatting-only work, and established follow-ups should use targeted reads instead of repeating graph traversal.
- Never run `graphify update .` directly on the curated graph. Update it only through the ingest skill's completion gate (`ingest_runtime.py finalize`) or the target wiki's dedicated finalizer, which validate and promote atomically.
- For a single-source operation, Graphify may be absent and the result must say `validated_without_graph` plus `graph_status: not_installed`. For batch completion, the runtime installs `graphifyy` and requires a built graph; installation/build failure blocks completion.
