# llm-wiki-bootstrap

빈 폴더를 AI가 운영하는 개인 지식 볼트(LLM Wiki)로 만들어주는 Claude Code / Codex 스킬.

*A Claude Code / Codex skill that turns any folder into an AI-operated personal knowledge vault. English below.*

## 무엇을 만들어주나

한 번의 대화로 다음이 셋업된다:

- **3계층 폴더 구조** — `raw/`(원문, 불변) → `wiki/`(요약·연결된 지식) → `Output/`(산출물). Karpathy의 "LLM이 관리하는 위키" 구조를 따른다.
- **두 가지 Vault Profile** — 일반 개인 지식관리용 `standard`, 출처 계보·가설·충돌·실험·Canon을 분리하는 `evidence`.
- **운영 스킬 6종** — 볼트 안에 설치되어 이후 세션에서 바로 쓸 수 있다:
  - `ingest` — raw에 넣은 원문을 위키로 요약·연결
  - `query` — frontmatter 우선 탐색으로 위키에서 근거 있는 답변
  - `lint` — 깨진 링크·고아 문서·신선도 점검
  - `session-memory` — `SAVE` 한 마디로 세션 상태를 원자적으로 보존
  - `brief-tuner` — AI 작업 브리프 템플릿을 인터뷰로 내 작업 패턴에 맞게 최적화
  - `wiki-audit` — 설치 환경과 Graphify 최신 계약의 읽기 전용 정합성 점검
- **Evidence 전용 `canon-review`** — Evidence profile에서만 설치되며 Claim의 source quality, lineage, conflict, experiment를 검토한 뒤 Canon 승격/유지/반려를 추천한다. 자동 승격은 하지 않는다.
- **라우터 문서** — CLAUDE.md / AGENTS.md가 매 세션 AI에게 볼트 규칙과 profile을 알려준다.
- **Obsidian Web Clipper 템플릿** — 웹 아티클·유튜브·책·팟캐스트를 `raw/reference/`로 자동 수집 (선택).
- **graphify 지식 그래프** — 설치돼 있으면 볼트 전체를 그래프로 연결 (선택).

## 설치

이 저장소를 스킬 폴더에 복사한다:

```bash
git clone https://github.com/gupilleveldesigner/llm-wiki-bootstrap "$HOME/.claude/skills/llm-wiki-bootstrap"
```

Codex CLI 사용자는 같은 폴더를 `~/.codex/skills/llm-wiki-bootstrap`에 복사하면 된다 (`agents/openai.yaml` 포함).

**요구사항**: Claude Code 또는 Codex CLI, Python 3.10+. Graphify는 선택이며, 사용할 때는 호스트 스킬로 설치한다(`graphify install --platform codex` 또는 `graphify install`).

## 사용

Claude Code에서:

```text
/llm-wiki-bootstrap
```

또는 자연어로 — "요리 공부용 LLM 위키 만들어줘", "이 폴더를 지식 볼트로 전환해줘", "역공학 자료를 근거/가설/실험으로 분리해서 관리하는 Evidence Wiki를 만들어줘".

### Lifecycle mode

세 가지 모드는 **폴더에 어떤 작업을 할지** 결정한다.

| 모드 | 대상 | 동작 |
|---|---|---|
| **new** | 빈 폴더 | 완전한 볼트 신규 구축 |
| **migrate** | 자료가 쌓인 일반 폴더 | 기존 파일을 보존하며 위키로 전환 (파일 이동은 승인 후) |
| **upgrade** | 기존 LLM Wiki | 지식·기록은 그대로, 운영 스킬/프로파일 자산을 최신 번들로 갱신 (교체 전 백업) |

### Vault profile

Profile은 **어떤 방식으로 지식을 관리할지** 결정한다. mode와 직교한다.

| Profile | 용도 | 지식 구조 |
|---|---|---|
| **standard** | 일반 개인 Wiki, 공부, 자료 정리 | `raw → wiki → Output` |
| **evidence** | 역공학, 기술 조사, 다중 LLM 연구, 검증 중심 프로젝트 | `Raw → Source → Claim → Evidence/Conflict/Experiment → reviewed Canon` |

CLI에서 명시할 수도 있다:

```bash
python scripts/bootstrap.py --target ./MyWiki --config ./config.json --mode new --profile evidence
```

따라서 `new+evidence`, `migrate+evidence`, `upgrade+evidence`가 모두 가능하다. 기존 Evidence Wiki를 `upgrade`할 때 `--profile`을 생략하면 manifest의 profile을 보존한다. Evidence → Standard 자동 다운그레이드는 거부한다.

구축 후에는 자료를 `raw/`에 넣고 `/ingest` → 위키가 채워진다. 세션을 마칠 때 `SAVE` → 다음 세션이 이어받는다.

## Evidence profile

Evidence profile은 기본 3계층을 버리지 않고 `wiki/` 내부에 검증 계층을 추가한다.

```text
raw/
  ↓ immutable
wiki/sources/
  ↓ provenance + raw_sha256 + lineage
wiki/claims/
  ├─ supports / contradicts
  ├─ wiki/conflicts/
  ├─ wiki/experiments/
  └─ wiki/questions/
  ↓ review gate
wiki/canon/
  ↓
Output/
```

추가로 `.wiki-cache/normalized`, `.wiki-cache/index`, `.wiki-cache/embeddings`를 **재생성 가능한 파생 데이터 영역**으로 만든다. Cache는 정본이 아니다.

Evidence profile의 핵심 규칙:

- 외부 LLM(ChatGPT/Qwen/Claude/Codex 등)은 Authority가 아니라 **Source**다.
- 동일한 lineage에서 파생된 여러 LLM 답변은 독립 evidence로 과대평가하지 않는다.
- Claim 상태는 `OBSERVED`, `INFERRED`, `HYPOTHESIS`, `SUPPORTED`, `CONFIRMED`, `REJECTED`, `DISPUTED`, `DEPRECATED`, `UNKNOWN`을 구분한다.
- 반증된 Claim도 삭제하지 않는다.
- Ingest는 Claim/Conflict/Experiment 후보까지 만들 수 있지만 **Canon을 자동 승격하지 않는다**.
- `canon-review`는 source quality, independence, contradiction, experiment, direct observation, 기존 Canon 충돌을 확인한다.
- Query는 `answer`, `research`, `verify`, `challenge`, `trace`, `compare` 모드를 사용한다.
- 중요한 결론은 `Canon → Claim → Evidence/Experiment → Source → Raw`까지 역추적 가능해야 한다.

볼트의 profile은 루트 `.llm-wiki.json`에 기록된다. 이 manifest가 없으면 기존 Wiki 호환성을 위해 `standard`로 취급한다.

## 설계 원칙

- **raw는 불변** — 원문은 절대 수정되지 않는다. 요약이 틀려도 근거가 남는다.
- **배포 자족성** — 필요한 모든 자산이 `assets/`에 번들되어 있어, 다른 위키가 있는 환경일 필요가 없다.
- **비파괴** — migrate/upgrade는 기존 내용을 삭제·덮어쓰기하지 않는다. 충돌은 `.wiki-proposed` 제안 파일로 우회한다.
- **Profile과 lifecycle 분리** — `new/migrate/upgrade`와 `standard/evidence`를 같은 축으로 섞지 않는다.
- **정본과 cache 분리** — Raw/검토 기록은 영구 데이터, `.wiki-cache/`는 재생성 가능 데이터다.

## 유사 프로젝트와의 차이

[karpathy-llm-wiki](https://github.com/Astro-Han/karpathy-llm-wiki), [claude-obsidian](https://github.com/AgriciDaniel/claude-obsidian) 같은 좋은 구현이 이미 있다. 이 프로젝트가 다르게 힘을 준 지점은 다음과 같다:

- **세션 인수인계 (`SAVE`)** — 세션 상태를 락·저널 기반 원자적 트랜잭션으로 저장하고 검증까지 마친 뒤에만 성공을 보고한다. 완료하지 않은 작업과 실행하지 않은 검증은 기록하지 않는다. 다음 세션은 `log.md` 하나로 이어받는다.
- **비파괴 전환** — migrate는 기존 파일을 삭제·수정 없이 위키로 전환하고(이동은 승인 후, 복구 지도 보고), upgrade는 스킬만 백업 후 교체한다. 충돌은 덮어쓰기 대신 `.wiki-proposed` 제안 파일로 우회한다.
- **Evidence Research profile** — 단순 RAG/요약을 넘어 Raw, Claim, Conflict, Experiment, Canon과 source genealogy를 명시적으로 분리한다.

그리고 작업 브리프를 인터뷰로 맞춤화하는 brief-tuner, 한국어 우선 문서가 있다. 벡터 검색·MCP 서버·대규모 DB는 기본 필수층으로 넣지 않는다 — 파일과 마크다운만으로 완결되고, cache/index는 나중에 재생성 가능한 확장층으로 남긴다.

---

## English

**llm-wiki-bootstrap** scaffolds a complete AI-operated knowledge vault (LLM Wiki) from a single conversation, for Claude Code or Codex CLI.

**Lifecycle modes** are **new** (empty folder), **migrate** (convert an existing folder non-destructively), and **upgrade** (refresh an existing Wiki with backup). They describe what happens to the target folder.

**Vault profiles** are orthogonal to lifecycle modes:

- **standard** — the normal `raw → wiki → Output` personal knowledge workflow.
- **evidence** — a research/evidence workflow that adds provenance-aware sources, atomic Claims, conflicts, experiments, open questions, reviewed Canon, and disposable `.wiki-cache/` layers.

Evidence profile installs an additional `canon-review` skill and records the profile in `.llm-wiki.json`. It never treats LLM output as authority, never counts dependent source lineage as independent evidence, and never auto-promotes Claims to Canon. Query behavior distinguishes `answer`, `research`, `verify`, `challenge`, `trace`, and `compare` modes.

**What you get**: the 3-layer structure, six base operational skills (`ingest`, `query`, `lint`, `session-memory`, `brief-tuner`, `wiki-audit`), profile-aware router docs, optional Obsidian Web Clipper templates, and optional Graphify integration. Evidence profile adds `canon-review` plus Claim/Canon/Conflict/Experiment templates.

**Install**: clone into `~/.claude/skills/llm-wiki-bootstrap` (Claude Code) or `~/.codex/skills/llm-wiki-bootstrap` (Codex). Requires Python 3.10+; Graphify is optional and should be installed through its host integration (`graphify install --platform codex` or `graphify install`).

Ingest completion remains file-level: a catalog that only lists raw paths is not evidence. Batch completion uses the one-to-one source-summary and content-evidence gates, asks the host Graphify skill to build/update the graph with the host assistant's authentication, and requires the read-only `verify --complete-batch --require-graph` gate before reporting success.

Categories use a small SKOS-shaped controlled vocabulary in `wiki/taxonomy.json` (`prefLabel`, `altLabel`, `broader`, `scopeNote`). Graphify communities remain discovery aids, not taxonomy or truth.

## License

MIT
