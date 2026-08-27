# llm-wiki-bootstrap

[한국어](README.ko.md) · [English](README.en.md)

Claude Code / Codex에서 폴더 하나를 **AI가 운영하는 개인 지식 볼트(LLM Wiki)** 로 구축·전환·업그레이드하는 스킬입니다.

기본 `standard` profile은 `raw → wiki → Output`의 가벼운 개인 지식관리 흐름을 제공합니다. `evidence` profile은 여기에 **Source provenance, atomic Claim, Conflict, Experiment, Open Question, reviewed Canon**을 추가해 역공학·기술 조사·다중 LLM 연구처럼 “무엇을 알고 무엇을 추측하는지”를 분리해야 하는 작업을 지원합니다.

> Evidence profile의 핵심 원칙: **“LLM이 말했다”와 “우리가 확인했다”를 같은 것으로 취급하지 않는다.**

## 핵심 기능

- `raw/` 불변 원문 → `wiki/` AI 유지 지식 → `Output/` 산출물의 3계층 구조
- lifecycle `mode`와 지식관리 `profile`을 분리
- `new`, `migrate`, `upgrade` 비파괴 lifecycle
- `standard`, `evidence` vault profile
- 기본 운영 스킬 6종: `ingest`, `query`, `lint`, `session-memory`, `brief-tuner`, `wiki-audit`
- Evidence 전용 `canon-review`
- Claude/Codex 라우터 문서와 프로젝트 로컬 스킬 설치
- 원문별 1:1 source summary, SHA-256, ingest ledger, 검증 gate
- SKOS 형태의 `wiki/taxonomy.json`
- 선택적 Graphify 지식 그래프 연동
- 선택적 Obsidian Web Clipper 템플릿
- `SAVE` 기반 원자적 세션 인수인계
- 기존 파일·Wiki를 덮어쓰지 않는 `.wiki-proposed` 제안 방식
- `.llm-wiki.json` manifest를 통한 profile/schema 기록
- Evidence에서 source lineage, epistemic state, trace/verify/challenge 질의

## 핵심 모델: lifecycle mode와 vault profile은 다른 축이다

### Lifecycle mode

대상 폴더에 **무슨 작업을 할지** 결정합니다.

| Mode | 대상 | 동작 |
|---|---|---|
| `new` | 비어 있거나 없는 폴더 | 새 Wiki를 구축 |
| `migrate` | 자료는 있지만 Wiki marker가 없는 일반 폴더 | 기존 파일을 보존하며 Wiki로 전환 |
| `upgrade` | `raw/` + `wiki/`가 있는 기존 Wiki | 지식/Raw를 보존하고 운영 자산을 백업 후 갱신 |

### Vault profile

Wiki가 **지식을 어떤 방식으로 관리할지** 결정합니다.

| Profile | 적합한 용도 | 핵심 흐름 |
|---|---|---|
| `standard` | 공부, 개인 Wiki, 기사/영상/책 정리, 프로젝트 메모, 세컨드브레인 | `raw → wiki → Output` |
| `evidence` | 역공학, 내부 구현 추정, 기술 조사, 다중 LLM 분석, 가설/실험/반증 관리 | `Raw → Source → Claim → Evidence/Conflict/Experiment → reviewed Canon` |

두 축은 직교하므로 다음이 모두 가능합니다.

```text
new + standard
new + evidence
migrate + standard
migrate + evidence
upgrade + standard
upgrade + evidence
```

단, `upgrade`로 **Evidence → Standard 자동 downgrade는 허용하지 않습니다.** Evidence 기록을 제거하거나 의미를 축소하는 작업은 별도 마이그레이션으로 설계해야 합니다.

## Profile 자동 판정

사용자가 profile을 명시하면 그대로 사용합니다. 명시하지 않으면 일반 지식관리에는 `standard`를 기본으로 사용합니다.

다음 신호가 명확하면 `evidence`가 적합합니다.

- 역공학 또는 내부 구현을 추정하는 프로젝트
- ChatGPT/Qwen/Claude/Codex 등 여러 LLM의 분석을 누적
- 직접 관찰과 추론/가설을 구분해야 함
- provenance/source lineage가 중요함
- 상충 주장과 반증 기록을 보존해야 함
- 가설 → 통제 실험 → 결론 루프가 핵심임
- 중요한 결론을 원문까지 역추적해야 함

기존 Wiki를 `upgrade`할 때 `--profile`을 생략하면 `.llm-wiki.json`의 기존 profile을 보존합니다. manifest가 없는 legacy Wiki는 호환성을 위해 `standard`로 취급합니다.

## 설치

### Claude Code

```bash
git clone https://github.com/gupilleveldesigner/llm-wiki-bootstrap "$HOME/.claude/skills/llm-wiki-bootstrap"
```

### Codex

```bash
git clone https://github.com/gupilleveldesigner/llm-wiki-bootstrap "$HOME/.codex/skills/llm-wiki-bootstrap"
```

Codex용 `agents/openai.yaml`이 포함되어 있습니다.

### 요구사항

- Claude Code 또는 Codex
- Python 3.10+
- Graphify는 선택 사항

Python 실행기는 `python`, `py -3`, `python3` 순으로 사용할 수 있으며 Windows에서는 Microsoft Store stub이 아닌 실제 Python 설치가 필요합니다.

## 사용

Claude Code에서는:

```text
/llm-wiki-bootstrap
```

Codex에서는 설치된 스킬을 호출하거나 자연어로 요청할 수 있습니다.

```text
$llm-wiki-bootstrap
```

자연어 예:

```text
요리 공부용 LLM 위키를 만들어줘.
이 자료 폴더를 기존 파일을 보존하면서 Wiki로 전환해줘.
역공학 자료를 관찰/가설/실험/Canon으로 분리하는 Evidence Wiki를 만들어줘.
기존 Standard Wiki를 Evidence profile로 업그레이드해줘.
```

Bootstrap은 이미 제공된 정보를 다시 묻지 않고, 부족한 경우 한 번의 짧은 인터뷰에서 다음을 수집합니다.

1. Wiki 주제와 목적
2. 주로 모을 자료 유형
3. 프로젝트 이름

이 답으로 `project_name`, `domain_summary`, 초기 `overview`, `questions`, taxonomy를 구성합니다.

## CLI

기본 config:

```json
{
  "project_name": "My Wiki",
  "domain_summary": "프로젝트의 한 문장 목적"
}
```

Standard 신규:

```bash
python scripts/bootstrap.py \
  --target ./MyWiki \
  --config ./config.json \
  --mode new \
  --profile standard
```

Evidence 신규:

```bash
python scripts/bootstrap.py \
  --target ./ResearchWiki \
  --config ./config.json \
  --mode new \
  --profile evidence
```

기존 폴더 Evidence 전환:

```bash
python scripts/bootstrap.py \
  --target ./ExistingProject \
  --config ./config.json \
  --mode migrate \
  --profile evidence
```

기존 Standard Wiki → Evidence 승격:

```bash
python scripts/bootstrap.py \
  --target ./ExistingWiki \
  --config ./config.json \
  --mode upgrade \
  --profile evidence
```

`new`/`migrate`에서 `--profile`을 생략하면 `standard`입니다. `upgrade`에서는 기존 manifest profile을 우선 보존합니다.

## Standard profile 구조

대표 구조:

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

`raw/`는 원문층, `wiki/`는 AI가 유지하는 정리된 지식층, `Output/`은 외부 결과물입니다.

## Evidence profile 구조

Evidence는 Standard 구조를 버리지 않고 검증 계층을 추가합니다.

```text
ResearchWiki/
├─ raw/                         # 불변 원문
├─ wiki/
│  ├─ sources/                 # Raw별 1:1 source record
│  ├─ claims/                  # 원자적 주장
│  ├─ conflicts/               # 상충 Claim
│  ├─ experiments/             # 가설 검증
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

`.wiki-cache/`는 **재생성 가능한 파생 데이터** 영역이며 정본이 아닙니다.

### Source record

원문마다 `wiki/sources/`에 1:1 source record를 유지합니다. 가능한 경우 다음을 기록합니다.

- `raw_sha256`
- provider/model
- created/ingested time
- source locator(섹션, 줄, 메시지, 함수 등)
- `parent_sources`
- verification/epistemic 상태

외부 LLM은 Authority가 아니라 Source입니다. 외부 모델의 결과도 Raw로 들어가고, 직접 Canon을 수정하지 않습니다.

### Source lineage와 독립성

다음 세 답변은 자동으로 독립 evidence 3개가 아닙니다.

```text
ChatGPT 답변
  ↓ 전달
Qwen 답변
  ↓ 전달
Codex 답변
```

같은 정보 계보에서 파생된 경우 `parent_sources` 또는 동등한 lineage를 기록하고 evidence independence 계산에서 중복으로 세지 않습니다.

### Claim

문서 전체를 하나의 진실로 저장하지 않고 재사용 가치가 있는 **원자적 주장**으로 분리합니다.

허용 Claim 상태:

| 상태 | 의미 |
|---|---|
| `OBSERVED` | 원문/코드/로그/실행 결과에서 직접 관찰 |
| `INFERRED` | 관찰에서 합리적으로 추론했지만 직접 확인되지 않음 |
| `HYPOTHESIS` | 검증이 필요한 적극적 가설 |
| `SUPPORTED` | 여러 근거/실험이 지지하지만 결정적 증거는 없음 |
| `CONFIRMED` | 직접 근거 또는 충분한 통제 검증이 있음 |
| `REJECTED` | 반증됨. 삭제하지 않음 |
| `DISPUTED` | 유효한 상충 근거가 있음 |
| `DEPRECATED` | 역사적 기록으로만 유지 |
| `UNKNOWN` | 현재 자료로 판정 불가 |

숫자 confidence는 보조 신호일 뿐 이 상태보다 우선하지 않습니다.

Claim-source relation은 최소 다음을 구분합니다.

```text
originates
supports
contradicts
derived_from
mentions
```

자료가 없으면 그럴듯하게 빈칸을 채우지 않고 `UNKNOWN`으로 남깁니다.

### Conflict, Experiment, Question

- `wiki/conflicts/` — 상충 Claim을 억지로 통합하지 않고 unresolved conflict로 보존
- `wiki/experiments/` — hypothesis, setup, control, variant, metrics, result를 기록
- `wiki/questions/open/` — 아직 답이 없는 연구 질문
- `wiki/questions/answered/` — 답이 정리된 질문
- `wiki/questions/blocked/` — 현재 근거/도구 부족으로 막힌 질문

실패한 실험과 반증된 Claim도 연구 이력으로 보존합니다.

### Canon

`wiki/canon/`은 현재 프로젝트가 채택한 **검토된 현재 지식**입니다. 작게 유지합니다.

Claim을 자동으로 Canon으로 승격하지 않습니다. LLM confidence가 높아도 자동 승격하지 않습니다.

최소 검토 기준:

1. source quality
2. source independence / lineage
3. contradictory evidence
4. experiment evidence
5. direct observation 여부
6. 기존 Canon과 충돌 여부

`canon-review`는 이 기준으로 recommendation을 만들지만 기본적으로 읽기 전용입니다. 사용자가 명시적으로 승격/상태 변경을 요청한 경우에만 Canon을 수정합니다.

## 운영 스킬

### `ingest`

`raw/` 원문을 불변으로 유지하며 `wiki/`에 반영합니다.

기본 완료 계약:

- raw는 수정하지 않음
- raw 원문마다 `wiki/sources/<원문>.md` 1:1 source summary가 필요
- 단순 catalog에 raw 경로만 나열한 것은 ingest 완료가 아님
- source summary는 raw path와 SHA-256 등 실제 content evidence를 가져야 함
- taxonomy는 `wiki/taxonomy.json`의 통제어휘를 사용
- batch 완료 전 category audit와 독립 verification gate를 통과
- Graphify가 필요한 batch에서는 host Graphify 실행과 run manifest 기록 후 `verify --complete-batch --require-graph`
- 실패하면 실패한 source만 다시 `scan → ingest → finalize → verify`

Evidence에서는 추가로:

```text
Raw
→ Source Record
→ atomic Claim
→ support / contradiction
→ Conflict / Experiment / Open Question
→ Canon candidate/review 필요 상태
```

까지만 자동화할 수 있습니다. **Canon 자동 변경은 금지합니다.**

### `query`

Standard에서는 컨텍스트를 한꺼번에 펼치지 않고 다음 순서로 읽습니다.

```text
catalog/index
→ candidate frontmatter
→ 선택된 본문
→ 정확한 검증이 필요할 때만 raw
```

Wiki에 없는 내용을 모델 기억으로 채우지 않습니다. 모순, stale 상태, 미검증 상태를 숨기지 않습니다.

Evidence에서는 질의 목적을 다음 모드로 구분합니다.

| Mode | 동작 |
|---|---|
| `answer` | Canon → CONFIRMED/SUPPORTED → OBSERVED 순으로 현재 지식 답변 |
| `research` | Canon, Claims, Conflicts, Experiments, Questions, Raw까지 폭넓게 조사 |
| `verify` | 특정 Claim의 지지/반박 evidence와 실제 Raw 검증 |
| `challenge` | 현재 결론을 반박할 수 있는 disputed/rejected/conflict/실패 실험을 우선 탐색 |
| `trace` | `Canon → Claim → Evidence/Experiment → Source → Raw locator` 추적 |
| `compare` | 복수 Claim의 source quality, independence, direct evidence, experiment, contradiction 비교 |

명시가 없으면 `answer`가 기본입니다. “왜 그렇게 생각하지?”, “근거 추적”, “진짜 맞아?” 같은 질문은 `trace`/`verify`를 우선합니다.

### `lint`

일반 Wiki에서는 다음을 점검합니다.

- 깨진 Wiki 링크
- frontmatter
- index 누락
- 고립 문서
- 원문 연결
- freshness/staleness

의미 판단이 필요 없는 기계적 수정만 자동 적용합니다. 사실 판단, 병합, 삭제, 의미 있는 상태 변경은 자동으로 하지 않습니다.

Evidence에서는 epistemic integrity까지 검사합니다.

- source 없는 Claim
- 존재하지 않는 source/claim/experiment/conflict ID
- Canon → Claim 역추적 실패
- Claim → Raw locator 역추적 실패
- `parent_sources` cycle/단절
- 근거 없는 `CONFIRMED`
- `REJECTED` Claim을 현재 Canon 근거로 사용
- unresolved conflict를 숨긴 단정
- orphan experiment/conflict
- 명백한 duplicate Claim family
- source record의 `raw_sha256` 불일치

### `session-memory`

`SAVE` 한 마디로 세션 상태를 락·저널 기반 원자적 트랜잭션으로 보존합니다. 완료하지 않은 작업이나 실행하지 않은 검증을 완료로 기록하지 않습니다. 다음 세션은 루트 `log.md`부터 이어받습니다.

### `brief-tuner`

작업 브리프 템플릿을 인터뷰로 사용자의 작업 패턴에 맞춥니다.

### `wiki-audit`

설치 환경, 운영 스킬, Graphify host prerequisite와 계약 정합성을 읽기 전용으로 점검합니다.

### `canon-review` — Evidence 전용

Claim의 source quality, lineage independence, contradiction, experiment, direct observation, 기존 Canon 충돌을 검토해 다음 같은 recommendation을 만듭니다.

```text
promote
keep current state
dispute
reject
needs more evidence
```

기본은 **review only**이며 자동 승격이 아닙니다.

## Taxonomy

`wiki/taxonomy.json`은 작은 SKOS 형태의 통제어휘를 사용합니다.

핵심 필드:

```text
prefLabel
altLabel
broader
scopeNote
```

Graphify community 이름을 taxonomy로 자동 복사하지 않습니다. Graphify는 탐색 보조이고 taxonomy나 truth source가 아닙니다.

## Graphify

Graphify는 선택 사항입니다.

### Codex

```bash
python -m pip install graphifyy
graphify install --platform codex
```

그 뒤 현재 Codex 인증을 사용하는 host skill로:

```text
$graphify <WIKI_ROOT>
$graphify <WIKI_ROOT> --update
```

병렬 처리를 쓰려면 `~/.codex/config.toml`의 `[features] multi_agent = true`를 확인합니다.

항상 그래프 우선 탐색을 원할 때만 선택적으로:

```bash
graphify codex install
```

을 사용합니다. 이것은 그래프 생성이 아니라 hook/router 설치입니다.

### Claude Code

```bash
python -m pip install graphifyy
graphify install
```

그 뒤:

```text
/graphify <WIKI_ROOT>
/graphify <WIKI_ROOT> --update
```

Python subprocess에서 bare `graphify <path>` 또는 `graphify update .`를 직접 호출하지 않습니다. host assistant의 인증을 사용하는 Graphify skill을 사용합니다.

Graphify 실행 뒤 ingest runtime에 run manifest를 기록하고 독립 verify gate를 통과해야 batch ingest 완료를 보고할 수 있습니다. Graphify가 없거나 build가 실패하면 batch completion을 거짓으로 선언하지 않습니다. 단일 source는 로컬 검증만 했음을 명시할 수 있습니다.

Evidence profile에서도 Graphify는 **탐색/시각화 보조 수단**이고 truth database가 아닙니다.

## Obsidian Web Clipper

`templates/web-clipper/`에 웹 아티클, YouTube, 책, 팟캐스트 등을 `raw/reference/`로 수집하기 위한 템플릿이 포함됩니다.

Obsidian을 사용한다면 생성된 폴더를 Vault로 열고 `templates/web-clipper/`의 안내와 JSON 템플릿을 Web Clipper 확장에 임포트할 수 있습니다.

수집된 Raw는 그대로 보존하고 `/ingest`가 Wiki 지식층으로 반영합니다.

## `migrate` — 기존 일반 폴더를 비파괴 전환

`migrate`는 기존 파일을 삭제하거나 수정하지 않고 Wiki scaffold를 추가합니다.

1. 기존 파일에서 주제/자료 유형을 추론하고 부족한 인터뷰 정보만 확인
2. 선택한 profile로 scaffold 생성
3. 기존 루트 문서와 충돌하면 `.wiki-proposed` 생성
4. 기존 파일을 `raw/` 어디로 옮길지 **파일별 목적지 + 원래 경로** 계획을 작성
5. **사용자 승인 후에만** 파일 이동
6. 원래 경로가 복구 지도가 되도록 보존
7. 이동 후 `/ingest` batch로 반영
8. Graphify/smoke/완료 gate 확인

Bootstrap 자체는 기존 자료를 임의로 raw로 이동하지 않습니다.

## `upgrade` — 기존 Wiki 갱신

`upgrade`는 기존 `raw/`, `wiki/` 지식, `Output/`을 보존합니다.

기존 설치 스킬과 session-memory runtime은 갱신 전 다음 위치에 백업됩니다.

```text
.wiki-upgrade-bak/<timestamp>/
```

같은 profile 유지:

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

추가되는 것:

- Evidence 디렉터리
- Evidence 모델/운영 문서
- Evidence 템플릿
- `canon-review`
- `.llm-wiki.json` profile 갱신

기존 `CLAUDE.md`, `AGENTS.md`, `wiki/CLAUDE.md`에 Evidence router가 없으면 원본을 덮어쓰지 않고 `.wiki-proposed`를 만듭니다.

결과의:

```text
profile_activation_pending: true
```

이면 router proposal을 검토·병합하기 전까지 Evidence profile 전환이 완전히 활성화됐다고 간주하지 않습니다.

기존 `instructions/wiki-operations.md`, `.graphifyignore`, `wiki/taxonomy.json` 등과 새 번들이 다를 때도 안전한 경우 proposal을 만들고 자동으로 사용자 수정본을 덮어쓰지 않습니다.

## Manifest: `.llm-wiki.json`

모든 신규/전환 Wiki는 root manifest를 가집니다.

대표 필드:

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

기존 manifest의 알 수 있는 필드는 유지하면서 bootstrap 관리 필드를 갱신합니다.

## Router 문서

- `CLAUDE.md` — Claude용 항상 로드되는 프로젝트 라우터
- `AGENTS.md` — Codex용 라우터
- `raw/CLAUDE.md` — Raw 불변 규칙
- `wiki/CLAUDE.md` — Wiki 운영 규칙
- `Output/CLAUDE.md` — 결과물 계층 규칙
- `instructions/wiki-operations.md` — 공통 Wiki 운영 계약
- Evidence에서는 `wiki/evidence-model.md`, `instructions/evidence-operations.md` 추가

Evidence router overlay는 명확한 marker를 사용해 중복 추가를 피합니다.

## Ingest 완료 조건

“파일이 들어갔다”, “catalog가 생성됐다”, “Graphify graph가 있다”만으로 ingest 완료가 아닙니다.

Batch completion은 최소 다음을 충족해야 합니다.

1. 각 대상 raw source가 처리/제외/실패 중 하나로 판정됨
2. 처리된 raw마다 content-bearing 1:1 source summary가 존재
3. taxonomy/category audit 통과
4. Graphify가 요구되는 batch라면 host graph build/update 완료
5. Graphify run manifest 기록
6. `verify --complete-batch --require-graph` 독립 gate 통과
7. pending/catalog-only/실패가 남으면 `미완료`라고 보고

완료 보고에는 다음 수치를 포함합니다.

```text
입력 원문
처리 완료
검증 완료
제외
실패·미처리
그래프 노드
그래프 링크
```

## 복구와 데이터 영속성

핵심 원칙은 **정본과 재생성 가능한 데이터를 분리하는 것**입니다.

### 장기 보존

Standard:

```text
raw/
wiki/
Output/의 필요한 결과물
```

Evidence에서는 특히:

```text
raw/
wiki/sources/
wiki/claims/
wiki/canon/
wiki/experiments/
```

을 장기 보존합니다.

### 재생성 가능

```text
.wiki-cache/normalized/
.wiki-cache/index/
.wiki-cache/embeddings/
Graphify 산출물
기타 파생 cache/index
```

Cache나 graph가 손상돼도 Raw와 검토 기록에서 다시 만들 수 있어야 합니다.

## 안전 규칙

- `raw/`는 절대 수정하지 않음
- 새 정보가 기존 지식과 충돌하면 조용히 덮어쓰지 않음
- migrate는 사용자 승인 없이 기존 파일을 이동하지 않음
- upgrade는 기존 지식/Raw를 삭제하지 않음
- 기존 사용자 문서와 충돌하면 `.wiki-proposed`를 우선
- Evidence에서 외부 LLM은 Authority가 아니라 Source
- 동일 lineage의 LLM 답변을 독립 evidence로 과대평가하지 않음
- 모르는 것은 `UNKNOWN`
- 반증된 Claim도 삭제하지 않음
- Canon 자동 승격 금지
- 의미 판단이 필요한 lint 수정은 자동 적용하지 않음
- `.wiki-cache/`와 Graphify 결과를 truth source로 취급하지 않음
- Evidence → Standard 자동 downgrade 금지

## 부트스트랩 후 스모크 체크

생성된 Wiki에서 최소 다음을 확인합니다.

```bash
python ".claude/skills/ingest/scripts/ingest_runtime.py" status
python ".session-memory/scripts/session_memory.py" status
```

그리고:

- `wiki/index.md`
- `CLAUDE.md`
- `raw/CLAUDE.md`
- `.llm-wiki.json`

이 존재하는지 확인합니다.

Evidence profile이면 추가로:

- `wiki/evidence-model.md`
- `instructions/evidence-operations.md`
- `.agents/skills/canon-review/SKILL.md`

를 확인합니다.

렌더링 대상에 `{{...}}` placeholder가 남아 있으면 성공으로 보고하지 않습니다.

## 설계 원칙

1. **Raw immutable** — 요약이 틀려도 원문이 남아야 한다.
2. **Non-destructive migration** — 기존 데이터를 먼저 보존한다.
3. **Filesystem as durable truth** — DB/cache/graph는 재생성 가능해야 한다.
4. **Progressive disclosure** — Query는 필요한 문서만 단계적으로 읽는다.
5. **Source before assertion** — 주장에는 근거가 있어야 한다.
6. **Lineage-aware evidence** — 같은 정보 계보를 독립 근거로 세지 않는다.
7. **No automatic Canon promotion** — confidence와 truth를 동일시하지 않는다.
8. **Conflict preservation** — 모순을 조용히 삭제하거나 억지 통합하지 않는다.
9. **Host-authenticated Graphify** — headless provider key 우회보다 현재 Claude/Codex host를 사용한다.
10. **Self-contained distribution** — 필요한 운영 자산을 저장소가 자체 번들한다.

## 이 프로젝트가 의도적으로 하지 않는 것

기본 설치는 다음을 필수 의존성으로 만들지 않습니다.

- 외부 Vector DB
- Neo4j cluster
- 별도 MCP 서버
- microservices
- Kubernetes
- 대규모 backend

Evidence profile의 `.wiki-cache/index`와 `.wiki-cache/embeddings`는 향후 SQLite/FTS/embedding 같은 재생성 가능한 확장층을 위한 위치이며, 현재 정본을 DB로 옮긴다는 의미가 아닙니다.

## 유사 프로젝트와의 차이

`karpathy-llm-wiki`, `claude-obsidian` 같은 프로젝트와 같은 “LLM이 관리하는 Wiki” 계열이지만 다음에 특히 힘을 줍니다.

- 원자적 세션 인수인계 `SAVE`
- 비파괴 `migrate` / `upgrade`
- source별 ingest 완료 검증
- controlled taxonomy
- host-aware Graphify gate
- Evidence Research profile의 provenance/lineage/Claim/Conflict/Experiment/Canon 모델
- Canon review를 자동 truth 승격이 아니라 명시적인 검토 gate로 분리

## License

MIT
