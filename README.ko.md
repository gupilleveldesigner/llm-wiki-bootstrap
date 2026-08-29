# llm-wiki-bootstrap

[한국어](README.ko.md) · [English](README.en.md)

Claude Code / Codex에서 폴더 하나를 **AI가 운영하는 개인 지식 볼트(LLM Wiki)** 로 신규 구축하고, 기존 자료 폴더를 비파괴 전환하고, 기존 Wiki의 운영 스킬을 **GitHub 공식 저장소 최신 버전**으로 업그레이드하는 스킬입니다.

기본 `standard` profile은 `raw → wiki → Output`의 가벼운 개인 지식관리 흐름을 제공합니다. `evidence` profile은 여기에 **Source provenance, atomic Claim, Conflict, Experiment, Open Question, reviewed Canon**을 추가해 역공학·기술 조사·다중 LLM 연구처럼 “무엇을 확인했고 무엇을 추측했는지”를 분리해야 하는 작업을 지원합니다.

> Evidence profile의 핵심 원칙: **“LLM이 말했다”와 “우리가 확인했다”를 같은 것으로 취급하지 않는다.**

## 핵심 기능

- `raw/` 불변 원문 → `wiki/` AI 유지 지식 → `Output/` 산출물의 3계층 구조
- lifecycle `mode`와 지식관리 `profile` 분리
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
- `.llm-wiki.json` manifest를 통한 profile/schema/upgrade provenance 기록
- Evidence source lineage, epistemic state, trace/verify/challenge 질의
- **GitHub latest upgrade** — 공식 저장소의 현재 default branch 최신 commit SHA를 고정해 적용

## 핵심 모델: lifecycle mode와 vault profile은 다른 축이다

### Lifecycle mode

대상 폴더에 **무슨 작업을 할지** 결정합니다.

| Mode | 대상 | 동작 |
|---|---|---|
| `new` | 비어 있거나 없는 폴더 | 새 Wiki 구축 |
| `migrate` | 자료가 쌓였지만 Wiki marker가 없는 일반 폴더 | 기존 파일을 보존하며 Wiki 구조 추가 |
| `upgrade` | `raw/` + `wiki/`가 있는 기존 Wiki | 기존 지식/Raw를 보존하고 운영 스킬과 관리 자산을 최신화 |

### Vault profile

**지식을 어떤 방식으로 관리할지** 결정합니다.

| Profile | 적합한 용도 | 핵심 흐름 |
|---|---|---|
| `standard` | 공부, 개인 Wiki, 아티클/영상/책 정리, 프로젝트 메모, 세컨드브레인 | `raw → wiki → Output` |
| `evidence` | 역공학, 구현 추론, 기술 조사, 다중 LLM 분석, 가설/실험/반증 추적 | `Raw → Source → Claim → Evidence/Conflict/Experiment → reviewed Canon` |

두 축은 직교하므로 다음 조합이 가능합니다.

```text
new + standard
new + evidence
migrate + standard
migrate + evidence
upgrade + standard
upgrade + evidence
```

단, `upgrade`는 Evidence → Standard를 자동 downgrade하지 않습니다. Evidence 기록을 제거하거나 의미를 축소하는 작업은 별도 migration 설계가 필요합니다.

## Upgrade의 정확한 의미: GitHub 기준 최신

이 프로젝트에서 사용자 의도의 `upgrade`, `최신화`, `스킬 업데이트`는 기본적으로 다음 의미입니다.

> **`gupilleveldesigner/llm-wiki-bootstrap` GitHub 저장소의 현재 default branch 최신 commit을 확인하고, 그 정확한 commit의 upgrade logic과 bundled skills를 대상 Wiki에 적용한다.**

즉 단순히 현재 로컬에 설치돼 있는 오래된 bundle을 다시 복사하는 작업이 아닙니다.

### GitHub latest upgrade 흐름

```text
upgrade 요청
   ↓
GitHub 저장소 metadata 조회
   ↓
현재 default branch 확인
   ↓
그 branch의 최신 40자 commit SHA 확인
   ↓
정확한 SHA의 ZIP 다운로드
   ↓
ZIP 안전성 + 필수 파일/skills bundle 검증
   ↓
여기까지 성공해야 대상 Wiki 변경 시작
   ↓
다운로드한 최신 bootstrap.py --mode upgrade 실행
   ↓
기존 skills 백업
   ↓
최신 bundled skills/runtime/profile assets 적용
   ↓
검증
   ↓
.llm-wiki.json에 exact commit provenance 기록
```

### 왜 branch ZIP이 아니라 exact SHA를 고정하나

default branch를 먼저 확인하되 실제 적용 파일은 **검증한 commit SHA**로 다운로드합니다. 조회 시점과 다운로드 시점 사이에 branch HEAD가 바뀌더라도 “어떤 버전을 적용했는지”가 모호해지지 않도록 하기 위해서입니다.

성공 결과에는 다음이 포함됩니다.

```text
upgrade_source: github
bootstrap_repository: gupilleveldesigner/llm-wiki-bootstrap
bootstrap_branch: <현재 default branch>
bootstrap_commit: <정확한 40자 SHA>
```

그리고 대상 `.llm-wiki.json`에는 다음 provenance가 남습니다.

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

### GitHub 접근 실패 시

네트워크, GitHub API, ZIP 다운로드, archive 검증 단계에서 실패하면 **대상 Wiki를 수정하지 않습니다.**

그리고 오래된 로컬 bundle로 조용히 fallback하지 않습니다. 사용자가 “GitHub 최신”을 요청했다면 GitHub 최신을 확인하지 못한 상태를 성공으로 보고하면 안 됩니다.

### 명시적 local/offline upgrade

오프라인 환경이거나 사용자가 명시적으로 현재 설치 bundle을 쓰라고 한 경우에만:

```bash
python scripts/upgrade.py \
  --target ./ExistingWiki \
  --config ./config.json \
  --source local
```

을 사용할 수 있습니다. 이 결과는 `upgrade_source: local`이며 **GitHub 최신이라고 부르지 않습니다.**

## 설치

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

Claude Code는 같은 방식으로 `.codex` 대신 `.claude`를 사용합니다.

저장소에는 Codex용 `agents/openai.yaml`이 포함됩니다.

### 요구사항

- Claude Code 또는 Codex
- Python 3.10+
- 온라인 upgrade에는 GitHub HTTPS 접근 가능 환경
- Graphify는 선택 사항

Python 실행기는 `python`, `py -3`, `python3`을 사용할 수 있습니다. Windows의 Microsoft Store stub은 실제 Python으로 취급하지 않습니다.

## 사용법

Claude Code:

```text
/llm-wiki-bootstrap
```

Codex:

```text
$llm-wiki-bootstrap
```

또는 자연어로 요청할 수 있습니다.

```text
요리 공부용 LLM Wiki 만들어줘.
이 기존 폴더를 파일 손실 없이 Wiki로 바꿔줘.
관찰/가설/실험/Canon을 분리하는 Evidence Wiki를 만들어줘.
이 Wiki의 운영 스킬을 GitHub 최신 버전으로 업그레이드해줘.
이 Standard Wiki를 Evidence profile로 승격하면서 최신 버전으로 업그레이드해줘.
```

이미 요청에 들어 있는 정보는 다시 묻지 않습니다. 필요할 때만 한 번의 짧은 인터뷰로 다음을 확인합니다.

1. Wiki 주제와 목적
2. 주로 모을 자료 유형
3. 프로젝트 이름

## CLI

기본 config:

```json
{
  "project_name": "My Wiki",
  "domain_summary": "프로젝트 목적 한 문장"
}
```

동일한 예제는 [`config.example.json`](config.example.json)에 있으며, Game mode용 전체 예제는 [`config.game.example.json`](config.game.example.json)에 있습니다. Windows에서는 아래 명령의 `python`을 `py -3`으로 바꿔 실행할 수 있습니다.

### Standard 신규 생성

```bash
python scripts/bootstrap.py \
  --target ./MyWiki \
  --config ./config.json \
  --mode new \
  --profile standard
```

### Evidence 신규 생성

```bash
python scripts/bootstrap.py \
  --target ./ResearchWiki \
  --config ./config.json \
  --mode new \
  --profile evidence
```

### 기존 일반 폴더 → Evidence migrate

```bash
python scripts/bootstrap.py \
  --target ./ExistingProject \
  --config ./config.json \
  --mode migrate \
  --profile evidence
```

### 기존 Wiki → GitHub 최신 upgrade

```bash
python scripts/upgrade.py \
  --target ./ExistingWiki \
  --config ./config.json
```

### Standard → Evidence 승격 + GitHub 최신 upgrade

```bash
python scripts/upgrade.py \
  --target ./ExistingWiki \
  --config ./config.json \
  --profile evidence
```

### 내부 local apply primitive

`scripts/bootstrap.py --mode upgrade`는 **최신 GitHub 버전을 찾는 진입점이 아닙니다.** `upgrade.py`가 다운로드한 최신 checkout 내부에서 실제 적용을 수행하는 low-level local apply primitive로 취급합니다.

사용자 의도의 “최신 upgrade”에는 `scripts/upgrade.py`를 사용하십시오.

## Standard profile 구조

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

`raw/`는 불변 원문, `wiki/`는 AI가 정리·연결하는 지식층, `Output/`은 외부 산출물입니다.

## Evidence profile 구조

Evidence는 Standard를 대체하지 않고 확장합니다.

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

`.wiki-cache/`는 **재생성 가능한 파생 데이터**이며 정본이 아닙니다.

## Evidence 데이터 모델

### Source record

Raw 원문마다 `wiki/sources/`에 1:1 source record를 유지합니다. 가능한 경우 다음을 기록합니다.

- `raw_sha256`
- provider/model
- created/ingested time
- source locator(섹션, 줄, 메시지, 함수 등)
- `parent_sources`
- verification/epistemic 상태

외부 LLM은 Authority가 아니라 Source입니다. 외부 모델의 결과도 Raw로 들어가고 직접 Canon을 수정하지 않습니다.

### Source lineage와 독립성

```text
ChatGPT 답변
  ↓ 전달
Qwen 답변
  ↓ 전달
Codex 답변
```

이 셋이 같은 주장을 했더라도 자동으로 독립 evidence 3개가 아닙니다. 같은 정보 계보에서 파생된 경우 `parent_sources` 또는 동등 provenance를 기록하고 evidence independence에서 중복 계산하지 않습니다.

### Claim

문서 전체를 하나의 진실로 저장하지 않고 **원자적 주장**으로 분리합니다.

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

숫자 confidence는 보조 신호일 뿐 상태보다 우선하지 않습니다.

Claim-source relation은 최소 다음을 구분합니다.

```text
originates
supports
contradicts
derived_from
mentions
```

자료가 없으면 그럴듯하게 채우지 않고 `UNKNOWN`으로 남깁니다.

### Conflict / Experiment / Question

- `wiki/conflicts/` — 상충 Claim을 억지로 통합하지 않고 unresolved 상태로 보존
- `wiki/experiments/` — hypothesis, setup, control, variant, metrics, result 기록
- `wiki/questions/open/` — 미해결 연구 질문
- `wiki/questions/answered/` — 답이 정리된 질문
- `wiki/questions/blocked/` — 근거/도구 부족으로 막힌 질문

실패한 실험과 반증된 Claim도 연구 이력으로 보존합니다.

### Canon

`wiki/canon/`은 현재 프로젝트가 채택한 **검토된 현재 지식**입니다. 작게 유지합니다.

Claim은 자동으로 Canon으로 승격되지 않습니다.

최소 검토 기준:

1. source quality
2. source independence / lineage
3. contradictory evidence
4. experiment evidence
5. direct observation
6. 기존 Canon과의 충돌

`canon-review`는 recommendation을 만들지만 기본적으로 읽기 전용입니다. 사용자가 명시적으로 승격/상태 변경을 요청한 경우에만 Canon을 수정합니다.

## 운영 스킬

### `ingest`

`raw/`를 불변으로 유지하며 지식층에 반영합니다.

기본 완료 계약:

- raw 수정 금지
- raw 원문마다 `wiki/sources/<원문>.md` 1:1 source summary 필요
- catalog가 raw 경로만 나열한 것은 완료 근거가 아님
- source summary에 raw path, SHA-256 등 실제 content evidence 필요
- taxonomy는 `wiki/taxonomy.json` 통제어휘 사용
- batch 완료 전 category audit와 독립 verification gate 통과
- Graphify가 필요한 batch에서는 host Graphify 실행 + run manifest 기록 + `verify --complete-batch --require-graph`
- 실패 시 실패한 source만 `scan → ingest → finalize → verify`

Evidence에서는 다음까지 자동화할 수 있습니다.

```text
Raw → Source Record → atomic Claim → support/contradiction → Conflict/Experiment/Open Question → review-needed
```

**Canon 자동 수정은 금지합니다.**

### `query`

Standard는 progressive disclosure를 사용합니다.

```text
catalog/index → candidate frontmatter → 선택된 본문 → 정확한 검증이 필요할 때만 Raw
```

Wiki에 없는 내용을 모델 기억으로 채우지 않고, 모순·stale·미검증 상태를 숨기지 않습니다.

Evidence query mode:

| Mode | 동작 |
|---|---|
| `answer` | Canon → CONFIRMED/SUPPORTED → OBSERVED 순으로 현재 지식 답변 |
| `research` | Canon, Claims, Conflicts, Experiments, Questions, Raw까지 조사 |
| `verify` | 특정 Claim의 지지/반박 evidence와 실제 Raw 확인 |
| `challenge` | disputed/rejected/conflict/실패 실험을 우선 탐색 |
| `trace` | `Canon → Claim → Evidence/Experiment → Source → Raw locator` 추적 |
| `compare` | source quality, independence, direct evidence, experiment, contradiction 비교 |

### `lint`

일반 Wiki에서는 링크, frontmatter, index, orphan, source link, freshness를 점검합니다. 의미 판단이 없는 기계적 수정만 자동 적용합니다.

Evidence에서는 추가로:

- source 없는 Claim
- 없는 source/claim/experiment/conflict ID
- Canon → Claim trace 실패
- Claim → Raw locator trace 실패
- `parent_sources` cycle/단절
- 근거 없는 `CONFIRMED`
- `REJECTED` Claim을 현재 Canon이 사용
- unresolved conflict 은폐
- orphan experiment/conflict
- 명백한 duplicate Claim family
- `raw_sha256` mismatch

를 점검합니다.

### `session-memory`

`SAVE`는 lock/journal 기반 원자적 트랜잭션으로 세션 상태를 저장합니다. 완료하지 않은 작업이나 실행하지 않은 검증을 완료로 기록하지 않습니다.

### `brief-tuner`

인터뷰를 통해 AI 작업 brief/template를 사용자의 작업 패턴에 맞춥니다.

### `wiki-audit`

설치된 스킬, runtime, Graphify 환경, Wiki 계약의 정합성을 읽기 전용으로 점검합니다.

### `canon-review` — Evidence only

source quality, source independence/lineage, contradictory evidence, experiment, direct observation, 기존 Canon 충돌을 검토합니다. 기본은 recommendation이며 자동 승격이 아닙니다.

## Taxonomy

`wiki/taxonomy.json`은 작은 SKOS 형태의 통제어휘를 사용합니다.

- `prefLabel`
- `altLabel`
- `broader`
- `scopeNote`

Graphify community 이름은 taxonomy나 truth가 아닙니다.

## Graphify

Graphify는 선택적 탐색/시각화 보조 수단입니다.

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

Python subprocess에서 bare `graphify <path>`를 직접 호출하지 않습니다. Host Graphify 실행 뒤 `ingest_runtime.py record-graphify-run --host codex|claude`를 기록하고 필요한 batch verification을 수행합니다.

Evidence에서도 Graphify는 truth database가 아닙니다. 정본은 Markdown/frontmatter와 Raw provenance입니다.

## migrate 안전 규칙

- 대상 또는 그 하위에 symlink가 있으면 vault 밖 쓰기를 막기 위해 적용 전 중단
- 기존 파일 삭제/수정 금지
- 기존 루트 문서 충돌 시 `.wiki-proposed`
- raw 편입 전 파일별 원래 경로/목적지 migration map 제시
- 사용자 승인 후 이동
- 이동 후 `/ingest` batch 처리
- `.git` 등 프로젝트 설정을 raw로 옮기지 않음

## upgrade 안전 규칙

- GitHub latest가 기본
- 원격 확인/다운로드/검증 완료 전 대상 변경 금지
- sibling transaction staging에서 전체 upgrade와 검증을 마친 뒤 같은 파일시스템 rename으로 적용
- 적용 또는 사후 검증 실패 시 원래 Wiki 복원
- staging 동안 같은 파일시스템에 vault 복제본을 만들 수 있는 임시 여유 공간 필요
- 정확한 SHA를 고정한 뒤 실행
- 기존 운영 스킬을 충돌 없는 `.wiki-upgrade-bak/<timestamp>-<unique-id>/`에 백업
- `raw/`, 기존 지식, `Output/` 보존
- customized router/operation 문서는 `.wiki-proposed` 사용
- Standard → Evidence 승격 시 Evidence folders/templates/canon-review 추가
- router proposal이 필요한 경우 `profile_activation_pending: true`
- Evidence → Standard 자동 downgrade 거부
- GitHub latest 기대 작업에서 exact `bootstrap_commit`을 보고하지 못하면 완료 선언 금지

## Obsidian Web Clipper

`templates/web-clipper/`의 템플릿을 Obsidian Web Clipper에 import하면 웹 자료를 `raw/reference/` 아래로 수집할 수 있습니다. 수집된 Raw 역시 ingest 전에는 지식/진실로 취급하지 않습니다.

## 데이터 보존과 복구 경계

### 장기 보존 우선

- `raw/`
- `wiki/sources/`
- `wiki/claims/` (Evidence)
- `wiki/canon/` (Evidence)
- `wiki/experiments/` (Evidence)
- `.session-memory/` 중 필요한 인수인계 기록

### 재생성 가능

- `.wiki-cache/normalized/`
- `.wiki-cache/index/`
- `.wiki-cache/embeddings/`
- Graphify output
- derived indexes/caches

즉 **Raw/검토 기록은 영구 데이터, cache/index는 disposable data**라는 경계를 유지합니다.

## Smoke check

설치/전환/업그레이드 후:

```bash
python ".claude/skills/ingest/scripts/ingest_runtime.py" status
python ".session-memory/scripts/session_memory.py" status
```

확인합니다.

- target root가 맞는가
- `wiki/index.md`, `CLAUDE.md`, `raw/CLAUDE.md`, `.llm-wiki.json` 존재
- placeholder 미잔존
- Evidence면 `wiki/evidence-model.md`, `instructions/evidence-operations.md`, `canon-review` 존재
- upgrade면 `upgrade_source`, `bootstrap_commit`, `backup_dir` 확인
- GitHub upgrade면 결과 SHA와 `.llm-wiki.json.last_upgrade.commit` 일치
- batch ingest 완료라고 말할 때 completion gate 통과

## 설계 원칙

- Raw는 불변
- LLM output은 Evidence profile에서 Source이지 Authority가 아님
- Claim과 Canon 분리
- 같은 lineage를 독립 evidence로 과대평가하지 않음
- conflict/rejected/failure 보존
- 모르면 `UNKNOWN`
- Canon 자동 승격 금지
- migrate/upgrade 비파괴
- GitHub latest upgrade는 정확한 commit provenance를 남김
- 원격 실패를 오래된 local fallback으로 숨기지 않음
- DB/embedding/Graphify는 Raw/Markdown 정본을 대체하지 않음

## Non-goals

기본 설치가 다음을 요구하지는 않습니다.

- Kubernetes
- 대규모 Vector DB
- Neo4j cluster
- microservices
- 외부 DB를 source of truth로 사용

파일/Markdown 중심으로 동작하고 향후 index/cache 계층은 재생성 가능하게 유지합니다.

## License

MIT
