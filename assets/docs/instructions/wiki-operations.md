# Wiki operations

## Three-layer model

1. `raw/` is immutable source material. Store inputs by type and do not modify them afterward.
2. `wiki/` is the AI-maintained knowledge layer. Summarize, connect, and update knowledge here.
3. `Output/` contains external deliverables grounded in verified wiki knowledge.

Folder-specific rules live in `raw/CLAUDE.md`, `wiki/CLAUDE.md`, and `Output/CLAUDE.md`.

## Vault profile

- Read `.llm-wiki.json` before broad Wiki work. If it is absent, treat the vault as legacy `standard` profile.
- `profile: standard` uses the normal `raw → wiki → Output` contract below.
- `profile: evidence` keeps the same three physical layers but adds an epistemic model inside `wiki/`: `sources → claims → evidence/conflict/experiment → reviewed canon`.
- For `profile: evidence`, **before ingest/query/lint/canon review**, read both `wiki/evidence-model.md` and `instructions/evidence-operations.md`. Those files define Claim states, source lineage, query modes, epistemic lint checks, and the no-auto-Canon-promotion gate.
- `.wiki-cache/` is disposable derived data. It is never a source of truth and must be rebuildable from persistent files.

## Workflow routing

- Ingest: store the source in `raw/`, update `wiki/`, then update `wiki/index.md` and `wiki/log.md`. Read the installed `ingest` skill before executing.
- Ingest evidence is file-level, not catalog-level: each raw source needs a one-to-one source summary (normally `wiki/sources/` with `type: source`) and a raw citation. A catalog that merely lists raw paths does not count.
- Evidence profile ingest additionally extracts atomic Claims, preserves provenance/lineage, records contradictions instead of overwriting them, and stops before Canon promotion. The detailed contract is in `instructions/evidence-operations.md`.
- For a batch completion, run `ingest_runtime.py finalize --complete-batch`; any `pending` or `catalog_only` source must keep the result `미완료`.
- `finalize --complete-batch` returns `agent_action_required` when Graphify has no graph. Run the host Graphify skill (`$graphify` on Codex, `/graphify` on Claude) so the current assistant authentication is used; never invoke bare `graphify <path>` from Python.
- Graphify의 상시 탐색 안내가 필요할 때만 `graphify codex install` 또는 `graphify claude install`을 선택적으로 실행한다. 이는 그래프 생성과 별개의 hook/라우터 설치다.
- Run the read-only independent gate `ingest_runtime.py verify --complete-batch --require-graph`. If it fails, reprocess only the returned sources and repeat `scan → ingest → finalize → verify`.
- After the host Graphify run, record it with `ingest_runtime.py record-graphify-run --host codex|claude`; verification rejects missing, stale, or hash-mismatched graph output.
- The runtime records the file ledger at `wiki/ingest-ledger.json`. Do not edit `raw/` to update statuses.
- Query: start from `wiki/index.md`; open `raw/` only when exact source verification is necessary. Read the installed `query` skill before executing.
- Evidence profile query supports `answer`, `research`, `verify`, `challenge`, `trace`, and `compare`; epistemic state must stay visible in the answer.
- Lint: use the installed `lint` skill for broken links, isolated documents, and stale claims. Evidence profile lint also checks provenance/Claim/Canon integrity as defined in `instructions/evidence-operations.md`.
- Canon Review (Evidence profile only): use the installed `canon-review` skill. Review is read-only by default; Canon changes require explicit user intent and preserved evidence links.
- Category audit: run `ingest_runtime.py category-audit`; only `wiki/taxonomy.json` labels are canonical. The model must not silently invent synonym categories.
- `wiki/taxonomy.json` follows a lightweight SKOS-shaped convention: preferred labels, alternate labels, direct broader concepts, and scope notes. See https://www.w3.org/TR/skos-reference/.

## Graphify

- When `graphify-out/graph.json` exists, use `graphify query` first for cross-file relationships, broad navigation, or architecture questions.
- Use `graphify path` for relationships and `graphify explain` for a focused concept.
- Prefer `graphify-out/wiki/index.md` for broad navigation when present.
- Read `graphify-out/GRAPH_REPORT.md` only for broad architecture review or when scoped graph commands are insufficient.
- Exact-file edits, formatting-only work, and established follow-ups should use targeted reads instead of repeating graph traversal.
- Never run `graphify update .` directly on the curated graph. Update it through the host Graphify skill (`$graphify <WIKI_ROOT> --update` or `/graphify <WIKI_ROOT> --update`), then run `ingest_runtime.py finalize` and `verify` for validation/promotion.
- For a single-source operation, Graphify may be absent and the result must say `validated_without_graph` plus `graph_status: not_installed`. For batch completion, the host Graphify skill must build the graph; missing host installation or build failure blocks completion.
