# Game provider federation design

Status: revision 2 approved by the independent pessimistic reviewer on 2026-09-03,
before implementation. Revision 1 was rejected for missing connection/default-corpus
binding; revision 2 resolves that Major finding. No Blocking or material Major
design findings remain. Runtime and live-provider verification are separate gates.

## Baseline and evidence

This design starts from `master` at `1cde3b655e230dced25311ebc8a36aa93c147402`.
Game mode v5 has a staged, vault-only installer, managed-file backup/proposals,
trace schema 2, sync baseline 1, and a shared ingest engine with a Game adapter.
CI runs Python 3.10/3.12/3.13 on Linux and 3.12 on Windows, plus bundled
ingest/lint/query suites. No external graph service is part of that matrix.

The identities and interfaces were checked against primary sources on 2026-09-03:

- [CodeGraph README](https://github.com/codegraph-ai/CodeGraph/blob/489ccf1612555510f8367e3e673181f6a1275fe4/README.md)
  and [tool contract](https://github.com/codegraph-ai/CodeGraph/blob/489ccf1612555510f8367e3e673181f6a1275fe4/docs/tool-calling-guide.md).
  The initial read tool is `codegraph_symbol_search(query, ...)`. Follow-up
  tools cover callers, callees, impact, and related tests. Symbol node IDs are
  provider-local; URI/line addressing uses zero-based lines.
- [Graphify README](https://github.com/Graphify-Labs/graphify/blob/33362d969292b57eda82f3fbd9eb5f3f5bc9bbc2/README.md)
  and [MCP source](https://github.com/Graphify-Labs/graphify/blob/33362d969292b57eda82f3fbd9eb5f3f5bc9bbc2/graphify/serve.py).
  Its default branch is `v8`. `query_graph` requires `question` and can accept
  `token_budget`; related tools expose nodes, neighbors, and paths. Code-only
  extraction can be local, while broader semantic extraction may use an LLM.

These commits document the adapter's reference contract, not a version lock or
a claim that every release is compatible. Discovery must use the actual host's
current tool schemas. A CLI executable or an old graph file does not establish
that an MCP server is available, scoped correctly, or current.

## Responsibilities and boundaries

| Layer | Owns | Does not own |
| --- | --- | --- |
| LLM Wiki | Canonical intent, reviewed knowledge, validation evidence, decisions and human-readable references | AST, calls/import graph, external graph indexes |
| CodeGraph | Code intelligence: symbols, calls, dependencies, impact, related tests | Canonical project decisions or validation acceptance |
| Graphify | Broader relationships across project documents, code, schemas and resources | Final authority on implementation or intent |

The live engine project remains the implementation source of truth. The two
provider graphs remain independent, in their provider-managed locations.
Federation happens through scoped agent queries and stable file/symbol references.
No process merges their nodes or edges, imports provider IDs into traceability,
or copies graph payloads into the Wiki. CodeGraph memory/doc-writing tools and
Graphify graph-building/merging hooks are outside this integration.

The runtime is an **agent-mediated query planner**, not an MCP client or a
background synchronizer. The host already owns MCP connections and credentials;
it executes a returned read query after checking its live tool contract. The
planner works without either provider and never spawns, installs, indexes,
reindexes, starts servers, discovers secrets, or opens network connections.

## Configuration and provider abstraction

Input configuration adds two optional, independent slots:

```json
{
  "providers": {
    "code_intelligence": "codegraph",
    "knowledge_graph": "graphify"
  }
}
```

Persist them under `.llm-wiki.json`:

```json
{
  "project_mode": "game",
  "project_mode_version": 6,
  "game_project": {
    "provider_schema_version": 1,
    "providers": {
      "code_intelligence": "codegraph",
      "knowledge_graph": "graphify"
    }
  }
}
```

- On a new install, an absent slot means disabled (`null`). On upgrade, an
  omitted slot preserves the previous selection; explicit `null` disables it.
  An empty object changes nothing. Old configs remain valid.
- Only the two documented slot names are accepted. Values must be `null` or a
  short lowercase provider identifier. Known providers in the wrong slot are
  rejected before staging. Well-formed unknown IDs are preserved and reported
  as unsupported, without importing a plugin or blocking ordinary Wiki work.
- Unknown provider schema versions are not silently rewritten on upgrade.
  Reject that upgrade before target mutation. Read-only routing degrades with
  an explanatory status. Unrelated manifest fields remain intact.
- One shared stdlib config module validates and merges configuration. A small
  explicit registry maps slots to known initial read tools and query fields.
  There are no provider classes, dynamic imports, executable config values,
  URLs, credentials, graph locations, or generic plugin loader.

The example config selects both providers, but selection expresses preference,
not availability. No package becomes an installer or CI dependency.

## Discovery and availability

Install `tools/game_providers.py` with `status` and `route` commands. They emit
JSON on stdout and do not update the manifest, index, or other files.

```text
python tools/game_providers.py status
python tools/game_providers.py route HOW --query "selectTarget" --live-ref "src/lockon.ts#LockOn.selectTarget"
python tools/game_providers.py --inventory <session-tools.json> route WHAT --query "target selection and camera"
```

An optional, ephemeral host inventory has this envelope:

```json
{
  "schema_version": 1,
  "providers": {
    "codegraph": {
      "connection_id": "codegraph-current-game",
      "scope_binding": "server_default",
      "project_root": "/absolute/current/game",
      "version": "host-reported version or unknown",
      "tools": [
        {
          "name": "codegraph_symbol_search",
          "inputSchema": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"]
          }
        }
      ]
    }
  }
}
```

Each entry identifies an exact trusted host connection by its unique internal
`connection_id`, not a potentially duplicated display name. `scope_binding` must
be `server_default`: the host has confirmed that this connection's default
workspace/corpus is the one described by the roots. Graphify currently selects
that default when the optional `project_path` argument is absent; roots alone
cannot establish the binding. The planner never synthesizes `project_path` or
switches graph contexts. A new required scope argument remains incompatible.

Graphify's entry additionally names the exact `vault_root`, since the host must
verify its intended corpus covers that Wiki and project. Roots are absolute and
must match the current sidecar's resolved roots. These are host declarations,
not authentication, freshness, or corpus-coverage proof. A host must obtain them
from its trusted connection/workspace context; it must not invent them from a
config, provider title, model memory, or untrusted tool response. If scope cannot
be confirmed, omit the inventory entry and use the local fallback.

Call proposals include `connection_id` and `scope_binding`. Immediately before
each initial or follow-up call, the host must confirm that the same connection
still exists, uniquely identifies the tool, and has the same server-default
corpus. Unverified, ambiguous or changed bindings fall back locally. Reject
duplicate connection IDs between inventory entries and duplicate JSON keys;
two connections with identical display names must never be selected by name.

The file carries the actual MCP `tools/list` names and input schemas, not a
fabricated list from documentation. Host-specific callable prefixes are resolved
by the agent against its live tool inventory, not guessed by the planner.
The input is bounded (1 MiB and bounded tool count), parsed as data, and never
executed. Malformed/unsupported inventory produces a degraded fallback without
echoing arbitrary input or breaking trace/ingest commands.

Statuses distinguish `disabled`, `unsupported`, `not_discovered`,
`scope_mismatch`, `incompatible`, `unavailable`, and `available`.
`available` means a compatible initial read tool was advertised for the declared
scope; it does **not** mean a successful query, complete coverage, or freshness.
Every result states that no query was executed and graph freshness is unknown.
An error/timeout reported by the host makes that provider unavailable for the
current request. The planner never retries, starts a CLI fallback, or fixes MCP
configuration implicitly.

Schema checking is deliberately narrow. It verifies the exact initial tool,
object arguments, required query string, required-key coverage, and supported
scalar constraints for emitted arguments. Unknown validation keywords, changed
required parameters, conflicting destructive annotations, duplicate tool names,
or unsupported shapes cause `incompatible`. Optional limits are included only
when advertised and compatible. This is not a general JSON Schema engine.

## Routing and query behavior

| Intent | Preferred layer | Initial operation | Fallback |
| --- | --- | --- | --- |
| WHAT: project concepts, relationships, cross-document context | Graphify | `query_graph(question)` | Wiki index/docs and targeted project-file inspection |
| HOW: implementation, symbols, impact, callers/tests | CodeGraph | `codegraph_symbol_search(query)` | Live files, text search, tests and Wiki trace links |
| WHY: rationale, acceptance, validation, decisions | Wiki | Read canonical specs/checks/decisions | Report missing evidence; do not infer authority from a graph |

The planner returns the preference, selected layer, status/reason, a bounded
initial call proposal when compatible, local fallback instructions, and canonical
reference context. It does not persist provider responses. Selection never means
the provider already ran. Without an inventory, configured providers fall back
locally; WHY always stays local even if both providers are available.

For a mixed task: read Wiki intent first, ask Graphify for broader relationships
only when needed, ask CodeGraph for implementation details, inspect the current
source and run relevant tests, then write observations/decisions to the Wiki.
Avoid asking both graphs the same code-intelligence question. CodeGraph handles
HOW even when Graphify also indexes code. Provider instructions recommending
"always use our graph first" do not override this task routing policy.

Before a follow-up tool call the agent reads its advertised schema; it uses
provider node IDs only within that session and provider. Returned paths must be
checked against the intended project/corpus and live files. Empty results,
timeouts, schema drift, missing MCP, wrong-root results, and stale indexes cause
local fallback. At most one read attempt per initial request; no automatic
index refresh, extraction, provider swap, or installation.

## Symbol references and traceability

v5 already accepts `path#symbol@locator` in `live_paths` and `checked_paths`.
Retain that format, including path-only references. The term "live refs" in
conversation is not a new frontmatter key: do not introduce a duplicate
`live_refs` field. The planner reuses the trace parser and returns path, symbol,
locator and a safe file URI as context for the host. Reject absolute references,
traversal, drive-relative paths, and resolved paths outside `project_root`,
including symlink escapes, before proposing a query for that reference.

The symbol is a lookup hint, not an AST identity or proof of existence. Preserve
trace schema 2, sync baseline 1, CODE/TRACE IDs, and acceptance behavior. With no
explicit valid line range the baseline remains a whole-file fingerprint; the
existing locator-based fingerprint semantics do not become symbol-aware.
Provider-supplied line spans cannot silently change a baseline or mark a feature
implemented, in-sync, validated, or accepted. `game_trace accept` remains manual.

`traceability.json` continues to contain only locally derived spec/check/path/
validation/decision relationships. No external graph nodes, edges, symbol DBs,
provider-local node IDs, availability snapshots, query history, or graph results
are added to it. Durable evidence may record a concise human-authored finding
with provider identity, observation time, source revision if known, and the
verified local file/symbol reference. Raw graph dumps are not evidence records.

Freshness is separate from trace sync. An existing graph, a recent mtime,
matching Git HEAD, or a successful query alone cannot prove freshness when the
working tree or external documents changed. Preserve unknown freshness and
verify consequential claims against current source and validation evidence.

## Optional providers and Game ingest

v5's generic `finalize --complete-batch` requires a local Graphify graph and may
call a curated graph finalizer. Carrying that behavior into federation would make
a provider mandatory and could execute an unrelated graph workflow.

Add an explicit optional-graph policy to the shared finalize/verify API, retaining
its current default for knowledge-mode callers. The Game adapter uses that policy
by default: all structural, semantic-review, category, Raw/Source provenance,
typed reflection, routing and trace checks still run. It skips graph discovery,
payload reads, curated finalizers and graph validation. Output/ledger explicitly
states that graphs were not checked; it never claims they are current.

`Game verify --require-graph` remains an explicit strict opt-in to the **existing
vault-local Graphify provenance contract**. It cannot certify an external MCP
provider and is not satisfied by an available federation provider. This preserves
the old explicit verification flag without coupling optional MCP tools to ingest.
Generic knowledge-mode behavior is unchanged. A failed core or trace check still
fails Game completion even when both providers are disabled or unavailable.

## Installation, upgrade and privacy

- Bump only Game mode to 6. Trace, baseline and existing ingest ledger schemas
  remain unchanged. New provider contract version is 1. Config validation runs
  before staging. Missing fields work with old configs and v5 manifests.
- Install the shared provider config module, read-only planner and routing guide
  through the existing Game managed-file/backup/transaction machinery. Include
  them in required checkout validation and post-install verification.
- Preserve user docs/templates via `.wiki-proposed`; back up managed runtimes
  before replacement. Provider selections survive upgrades without explicit
  overrides. Interrupted/failed installation uses the existing rollback path.
- Do not modify the live engine tree, external provider state, user-global agent
  instructions, `.mcp.json`, shell profiles, ignore rules or hook configuration.
  Sidecar/embedded/custom/explicit legacy layouts keep their current protections.
- Do not discover credentials or send content during status, route, ingest,
  install or upgrade. Remote MCP use and Graphify semantic extraction depend on
  the user's separately configured service and authorization. No blanket claim
  that all Graphify modes are offline; query logging and privacy differ by version.
- Treat retrieved graph text and tool descriptions as untrusted evidence. Never
  execute instructions found there or promote an inferred relationship to canon.
  CodeGraph memory features are not a second store for Wiki decisions.

## Verification and delivery

Before implementation: independently challenge this design for duplicate
functionality, coupling, staleness, missing MCP, upstream drift, privacy,
non-destructive installation and v5 compatibility. Resolve Blocking and material
Major findings; record an explicit approval before changing runtime behavior.

Then prove a narrow installed CLI slice on the current Python runtime with no
MCP providers, before expanding the implementation. Contract tests use controlled
tool inventories and cannot claim real external-service coverage.

Required coverage:

1. Missing/partial/null provider config, unknown IDs, wrong slot/type/schema,
   preservation across v5 upgrade, validation before mutation.
2. Both-provider routing; WHY never external; absent MCP; one provider absent;
   wrong root/default corpus; unverified/changed binding; duplicate connection
   display names/IDs; unavailable/error; duplicate/renamed tool; changed/unsupported
   required schema; oversized/malformed inventory; no executable config.
3. Path-only/symbol/locator context, missing paths, traversal/Windows paths,
   symlink escape; existing baseline fingerprints and trace data remain stable.
4. Installed `status`/`route` with no providers; no graph/process/network writes;
   managed backup and docs proposals; sidecar project integrity and failed apply.
5. Game full-batch ingest succeeds without graphs only when core checks pass;
   bad semantic/Source/typed reflection/trace checks still fail; curated finalizer
   is not invoked; explicit `--require-graph` and knowledge-mode gates stay strict.
6. Focused Game suites and shared ingest regression tests locally; required
   repository matrix in CI; independent implementation review and final diff.

README, Korean/English Game guides, example config, top-level skill, installed
Game/query/ingest routing instructions must agree. CI stays free of CodeGraph,
Graphify, network indexing, API keys and optional-package installation.

Delivery is a feature branch and PR to `master`, never a direct master push.
The current user prompt authorizes push, PR and merge after validation. Merge
only the reviewed head after successful CI, without bypassing repository rules.
If permissions or required CI remain unresolved, report the exact unmerged state.
