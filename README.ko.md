# llm-wiki-bootstrap

[한국어](README.ko.md) · [English](README.en.md)

Claude Code 또는 Codex가 폴더 속 원문을 보존하면서 자료를 정리하고, 필요하면 출처와 검토 상태까지 추적하는 개인 지식 Wiki를 만들도록 돕는 스킬입니다.

자료가 쌓이면 어디에 무엇이 있는지 찾기 어렵습니다. AI가 정리한 내용과 실제 원문이 섞이기도 합니다. 기존 폴더를 Wiki로 바꾸거나 운영 도구를 업데이트할 때 파일이 손상될까 걱정될 수도 있습니다.

이 저장소는 다음 일을 합니다.

- 원문을 `raw/`에 보존하고 AI가 정리한 지식을 `wiki/`에 분리합니다.
- 공부와 메모에는 단순한 `standard`, 근거 검토에는 엄격한 `evidence`를 제공합니다.
- 빈 폴더 생성, 기존 자료 폴더 전환, 기존 Wiki 최신화를 `new`, `migrate`, `upgrade`로 구분합니다.
- 기존 파일을 자동으로 삭제하거나 덮어쓰지 않습니다. 충돌하는 관리 문서는 `.wiki-proposed`로 제안합니다.

> 가장 간단한 시작법: 설치한 뒤 **“이 기존 자료 폴더를 파일 손실 없이 Wiki로 바꿔줘”**라고 요청하세요. 명령어를 외울 필요는 없습니다.

## 바로 가기

- [30초 선택 가이드](#30초-선택-가이드)
- [빠른 시작](#빠른-시작)
- [Standard](#standard-일반적인-지식-정리)
- [Evidence](#evidence-ai-답변을-검토-가능한-지식으로-관리)
- [안전성](#기존-폴더와-기존-wiki의-안전성)
- [고급 CLI](#고급-cli)

## 30초 선택 가이드

먼저 서로 다른 두 가지를 고릅니다.

1. 대상 폴더에 무엇을 할지: 새로 만들기(`new`) / 기존 폴더 전환(`migrate`) / 기존 Wiki 최신화(`upgrade`)
2. 지식을 얼마나 엄격하게 관리할지: 일반 정리(`standard`) / 근거 검토형 연구(`evidence`)

| 선택 | 언제 고르나 | 기존 파일 | 대표 예 |
|---|---|---|---|
| `new` | 폴더가 없거나 비어 있을 때 | 새 구조만 만듦 | 새 공부 Wiki |
| `migrate` | 자료가 이미 있는 일반 폴더일 때 | 삭제·자동 이동·덮어쓰기 안 함 | 기존 프로젝트 메모 전환 |
| `upgrade` | `raw/`와 `wiki/`가 있는 LLM Wiki일 때 | 원문과 지식을 보존하고 운영 자산 갱신 | 설치된 스킬 최신화 |

| 선택 | 언제 고르나 | 흐름 | 기본 추천 |
|---|---|---|---|
| `standard` | 공부 자료, 프로젝트 메모, 기사·영상·책 정리 | `raw → wiki → Output` | 대부분 여기서 시작 |
| `evidence` | 역공학, 기술 조사, 여러 LLM 비교, 가설 검증 | `Raw → Source → Claim → 검토 → Canon` | 근거와 추론을 분리해야 할 때 |

[![새로 만들기·기존 폴더 전환·최신화와 Standard·Evidence를 조합하는 선택표](docs/images/lifecycle-profile-matrix.svg)](docs/images/lifecycle-profile-matrix.svg)

`mode`와 `profile`은 독립적인 축입니다. `new + standard`, `migrate + evidence`, `upgrade + evidence`처럼 조합할 수 있습니다. 다만 `upgrade`는 Evidence를 Standard로 자동 축소하지 않습니다.

게임 제작 프로젝트에는 세 번째 축인 프로젝트 모드(`project_mode: game`)가 있습니다. lifecycle mode나 profile이 아니라 실제 엔진 프로젝트와 Wiki를 함께 운영하기 위한 별도 설정입니다.

## 빠른 시작

### 요구사항

- Claude Code 또는 Codex
- Python 3.10 이상
- 온라인 `upgrade`에는 GitHub HTTPS 접근
- Graphify는 선택 사항

Python 실행기는 `python`, `py -3`, `python3`을 사용할 수 있습니다. Windows의 Microsoft Store 실행 별칭만 있고 실제 Python이 설치되지 않은 경우에는 동작하지 않습니다.

### Claude Code 설치

macOS / Linux:

```bash
git clone https://github.com/gupilleveldesigner/llm-wiki-bootstrap "$HOME/.claude/skills/llm-wiki-bootstrap"
```

Windows PowerShell:

```powershell
git clone https://github.com/gupilleveldesigner/llm-wiki-bootstrap "$env:USERPROFILE\.claude\skills\llm-wiki-bootstrap"
```

### Codex 설치

macOS / Linux:

```bash
git clone https://github.com/gupilleveldesigner/llm-wiki-bootstrap "$HOME/.codex/skills/llm-wiki-bootstrap"
```

Windows PowerShell:

```powershell
git clone https://github.com/gupilleveldesigner/llm-wiki-bootstrap "$env:USERPROFILE\.codex\skills\llm-wiki-bootstrap"
```

저장소에는 Codex용 `agents/openai.yaml`이 포함됩니다.

### 설치 후 이렇게 요청하세요

```text
요리 공부용 Wiki를 새로 만들어줘.
이 기존 자료 폴더를 파일 손실 없이 Wiki로 바꿔줘.
AI 답변과 직접 확인한 사실을 분리하는 Evidence Wiki를 만들어줘.
이 Wiki의 운영 스킬을 GitHub 최신 버전으로 업그레이드해줘.
```

Claude Code에서는 `/llm-wiki-bootstrap`, Codex에서는 `$llm-wiki-bootstrap`으로 직접 호출할 수도 있습니다. 이미 알려 준 정보는 다시 묻지 않습니다.

## Standard: 일반적인 지식 정리

```text
원문 보관(raw/) → AI가 정리하고 연결(wiki/) → 문서·보고서로 활용(Output/)
```

[![원문 보관 raw, 정리된 지식 wiki, 공유 결과물 Output의 세 단계](docs/images/standard-structure.svg)](docs/images/standard-structure.svg)

- `raw/`: 기사, 메모, 영상 기록 같은 원문을 수정하지 않고 보관합니다.
- `wiki/`: AI가 원문을 요약하고 서로 연결합니다.
- `Output/`: 외부에 공유할 문서와 보고서를 둡니다.

AI가 `wiki/`를 고쳐도 `raw/` 원문은 그대로 남습니다. 따라서 요약이 잘못되었는지 다시 확인할 수 있습니다.

<details>
<summary>Standard 전체 폴더 구조</summary>

```text
MyWiki/
├─ raw/
│  ├─ inbox/ · personal/ · journal/ · archive/ · assets/
│  └─ reference/articles/ · youtube/ · podcasts/ · books/ · research/
├─ wiki/
│  ├─ entities/ · concepts/ · projects/ · sources/
│  └─ index.md · overview.md · questions.md · taxonomy.json · ingest-ledger.json
├─ Output/ · instructions/ · templates/
├─ .agents/skills/ · .claude/skills/ · .session-memory/
├─ CLAUDE.md · AGENTS.md · log.md · changelog.md
└─ .llm-wiki.json
```

</details>

## Evidence: AI 답변을 검토 가능한 지식으로 관리

### AI가 말한 내용을 바로 사실로 저장하지 않습니다

원문을 보존하고, 확인할 문장으로 나눈 뒤, 근거를 검토한 내용만 현재 지식으로 채택합니다.

[![원문 보관에서 출처 연결, 주장 분리, 근거 검토, 현재 지식 채택으로 이어지는 Evidence 5단계](docs/images/evidence-workflow.svg)](docs/images/evidence-workflow.svg)

1. **원문 보관(Raw)**: 문서·코드·로그·AI 답변을 원래 형태로 보존합니다.
2. **출처 연결(Source record)**: 내용이 어디서 왔는지 원문과 연결합니다.
3. **주장 분리(Atomic Claim)**: 하나씩 따로 확인할 수 있는 문장으로 나눕니다.
4. **근거 검토(Evidence review)**: 직접 관찰, 지지·반대 근거, 실험 결과, 출처 독립성을 확인합니다.
5. **현재 채택 지식(Reviewed Canon)**: 검토를 통과한 내용만 프로젝트의 현재 지식으로 사용합니다.

현재 채택 지식은 절대적 진리가 아닙니다. 지금 확보한 근거를 바탕으로 프로젝트가 현재 채택한 결론입니다. 새 근거가 나오면 다시 검토하고 수정할 수 있습니다. 주장은 자동으로 현재 채택 지식이 되지 않습니다.

### 원자적 주장을 예로 이해하기

다음은 원자적 주장(Atomic Claim)을 설명하기 위한 예시이며, 이 저장소에서 실제로 발생한 사건이 아닙니다.

> “Windows에서 테스트가 실패했으므로 제품에 Windows 전용 회귀가 있다.”

이 문장에는 관찰과 추론이 섞여 있습니다. 다음처럼 나누면 각 문장을 별도로 확인할 수 있습니다.

- Windows-latest와 Python 3.12에서 테스트가 실패했다.
- 실패 단계는 repository tests였다.
- Ubuntu 작업은 통과했다.
- 실패 원인은 운영체제별 경로 표현 차이다.
- 제품 코드에 Windows 전용 회귀가 있다.
- 실패는 제품 문제가 아니라 테스트 가정 문제다.

앞의 세 문장은 로그에서 직접 확인할 수 있습니다. 경로 차이는 조사나 실험이 필요합니다. 제품 회귀인지 테스트 가정 문제인지는 수정 후 재실행으로 검증할 수 있습니다.

> 문장의 일부만 참이고 일부는 틀릴 수 있다면 둘 이상의 주장으로 나눕니다.

일부만 반박할 수 있는지, 서로 다른 근거가 필요한지, 각 부분의 상태가 따로 바뀔 수 있는지 확인하세요.

### 상태값은 숫자보다 먼저 읽습니다

처음에는 직접 본 것, 관찰에서 추론한 것, 시험할 가설, 근거가 쌓인 결론, 반증·상충한 내용, 지금은 모르는 내용으로 구분하면 됩니다. 숫자 `confidence`는 보조 신호이며 상태값보다 우선하지 않습니다. 자료가 부족하면 `UNKNOWN`으로 남깁니다.

<details>
<summary>실제 Claim 상태값</summary>

| 상태 | 뜻 |
|---|---|
| `OBSERVED` | 원문·코드·로그·실행 결과에서 직접 관찰 |
| `INFERRED` | 관찰에서 추론했지만 직접 확인하지 못함 |
| `HYPOTHESIS` | 검증이 필요한 가설 |
| `SUPPORTED` | 여러 근거가 지지하지만 결정적이지 않음 |
| `CONFIRMED` | 직접 근거나 충분한 통제 검증이 있음 |
| `REJECTED` | 반증되었으며 기록은 보존 |
| `DISPUTED` | 유효한 상충 근거가 있음 |
| `DEPRECATED` | 현재는 쓰지 않지만 이력으로 보존 |
| `UNKNOWN` | 현재 자료로 판단할 수 없음 |

</details>

### 같은 답변을 전달받은 모델은 독립 근거가 아닙니다

```text
ChatGPT 답변 → Qwen에 전달 → Codex에 전달
```

세 모델이 같은 말을 해도 하나의 답변에서 이어졌다면 독립 근거 세 개로 세지 않습니다. 정보가 어디서 시작되어 어떻게 전달됐는지를 나타내는 계보(lineage)를 `parent_sources` 등에 기록합니다.

외부 LLM 답변은 검증 권위(Authority)가 아니라 출처(Source)입니다. Raw로 보관하고 다른 원문과 같은 방식으로 확인합니다.

### 검토 기록은 한 줄짜리 직렬 절차가 아닙니다

[![Raw, Source, Claim과 선택적으로 연결되는 Evidence, Conflict, Experiment, Reviewed Canon의 데이터 관계](docs/images/evidence-data-model.svg)](docs/images/evidence-data-model.svg)

- 근거(Evidence)는 주장을 지지하거나 반박합니다.
- 충돌 기록(Conflict)은 양립할 수 없는 주장을 억지로 합치지 않습니다.
- 실험 기록(Experiment)은 가설을 시험할 조건·방법·지표·결과를 남깁니다.
- 현재 채택 지식(Reviewed Canon)은 검토를 통과한 주장만 참조합니다.

모든 Claim이 Conflict와 Experiment를 차례로 거치는 것은 아닙니다. 필요한 기록만 연결합니다. `canon-review`는 승격 의견을 만들지만 기본값은 읽기 전용입니다.

<details>
<summary>Evidence가 추가하는 주요 폴더</summary>

```text
wiki/sources/ · claims/ · decisions/ · conflicts/ · experiments/
wiki/questions/open/ · answered/ · blocked/
wiki/canon/ · evidence-model.md
templates/evidence/ · instructions/evidence-operations.md · tools/kb.py
.wiki-cache/normalized/ · index/ · embeddings/
```

`.wiki-cache/`는 원문에서 다시 만들 수 있는 파생 데이터이며 현재 지식의 기준이 아닙니다.

</details>

## 기존 폴더와 기존 Wiki의 안전성

### 기존 자료 폴더 전환(`migrate`)

- 기존 파일을 자동으로 삭제·수정·이동하지 않습니다.
- 같은 이름의 관리 문서가 있으면 `.wiki-proposed`를 만듭니다.
- 자료를 나중에 `raw/`로 옮겨야 한다면 파일별 이동 계획과 승인을 먼저 받습니다.
- `.git` 같은 프로젝트 설정은 Raw로 옮기지 않습니다.
- 대상 안에 symlink가 있으면 vault 밖 쓰기를 막기 위해 적용 전에 중단합니다.

### 기존 Wiki 최신화(`upgrade`)

- `raw/`, 기존 지식, `Output/`을 보존합니다.
- GitHub의 현재 default branch와 정확한 40자 commit SHA를 먼저 확인합니다.
- ZIP과 필수 bundle 검증이 끝나기 전에는 대상 Wiki를 수정하지 않습니다.
- 같은 파일시스템의 형제 staging 사본에서 적용과 검증을 마친 뒤 교체합니다.
- 기존 운영 스킬은 `.wiki-upgrade-bak/<timestamp>-<unique-id>/`에 백업합니다.
- 적용이나 사후 검증이 실패하면 원래 Wiki를 유지하거나 복원합니다.
- GitHub 확인 실패를 오래된 로컬 bundle 성공으로 처리하지 않습니다.

[![GitHub 최신 commit을 확인하고 검증한 뒤 Wiki에 적용하는 안전한 upgrade 흐름](docs/images/upgrade-flow.svg)](docs/images/upgrade-flow.svg)

정확한 SHA를 고정하면 branch가 움직여도 적용 버전을 다시 확인할 수 있습니다. 성공 시 `.llm-wiki.json.last_upgrade`와 결과의 `bootstrap_commit`에 버전이 남습니다.

`upgrade.py`는 GitHub 최신 버전을 찾고 검증하는 사용자용 진입점입니다. `bootstrap.py --mode upgrade`는 이미 준비된 버전을 대상 Wiki에 적용하는 내부 단계입니다.

Standard를 Evidence로 승격할 때 사용자 편집 문서와 새 계약이 충돌하면 `profile_activation_pending: true`가 남을 수 있습니다. 제안 문서를 검토하기 전에는 완전히 활성화됐다고 간주하지 않습니다.

<details>
<summary>GitHub latest upgrade 내부 단계</summary>

```text
metadata 조회 → default branch → exact SHA → ZIP 검증
→ sibling staging → 백업 → 적용·사후 검증 → rename 또는 복원
```

주요 결과는 `upgrade_source`, `bootstrap_commit`, `backup_dir`, `profile_activation_pending`입니다. `--source local`은 명시적인 오프라인용이며 GitHub 최신이라고 부르지 않습니다.

</details>

## 운영 스킬

[![원문 수집, Wiki 반영, 질문, 점검, 세션 저장으로 이어지는 운영 순환](docs/images/operations-loop.svg)](docs/images/operations-loop.svg)

| 스킬 | 언제 쓰나 | 하는 일 | 하지 않는 일 |
|---|---|---|---|
| `ingest` | 새 원문을 반영할 때 | Raw를 고치지 않고 Source record와 요약을 만듦 | Canon 자동 수정 |
| `query` | Wiki 근거로 답을 찾을 때 | 색인부터 필요한 본문·원문까지 확인 | 모델 기억으로 빈칸 채움 |
| `lint` | 링크·메타데이터·신선도를 점검할 때 | 안전한 기계적 문제를 진단·수정 | 사실 판단·임의 병합·삭제 |
| `session-memory` | 다음 세션에 이어갈 때 | `SAVE`로 상태를 원자적 트랜잭션에 저장 | 미실행 검증을 완료로 기록 |
| `brief-tuner` | 작업 브리프를 맞출 때 | 인터뷰로 템플릿을 조정 | 기준을 대신 결정 |
| `wiki-audit` | 설치·runtime을 점검할 때 | 환경과 계약을 읽기 전용 검사 | 자동 수정 |
| `canon-review` | Evidence 결론을 검토할 때 | 출처 품질·독립성·반대 근거 검토 | 자동 승격 |

대표 요청은 “방금 넣은 자료 인제스트해줘”, “결론과 근거를 찾아줘”, “깨진 링크를 점검해줘”, `SAVE`입니다. `session-memory`의 원자적 트랜잭션은 저장이 반쯤 적용되지 않는다는 뜻이며 원자적 주장과는 다른 말입니다.

Evidence의 `query`는 현재 결론(`answer`), 넓은 조사(`research`), 특정 주장 확인(`verify`), 반대 근거 탐색(`challenge`), 원문 역추적(`trace`), 출처 비교(`compare`)를 지원합니다.

## Game 프로젝트 지원

Game은 lifecycle mode나 profile이 아닙니다. `.llm-wiki.json`의 별도 프로젝트 모드(`project_mode: game`)이며 `standard + game`과 `evidence + game`을 모두 사용할 수 있습니다.

```text
Workspace/
├─ MyGame/       실제 코드·씬·데이터·원본 에셋(project_root)
└─ MyGame.wiki/  기획·구현 확인·빌드·플레이테스트·결정(vault_root)
```

- 기본값은 엔진 프로젝트 옆의 sidecar Wiki입니다.
- Unity, Unreal, Godot, 웹 프로젝트 표지를 확인해 보호 경로와 추적 root를 정합니다.
- 설치와 upgrade는 `vault_root`만 쓰며 엔진 프로젝트 구조를 바꾸지 않습니다.
- 기획과 실제 코드·씬·데이터를 별도 기준으로 추적합니다.
- ingest는 게임 원문을 연결하지만 기획이나 코드를 자동 덮어쓰지 않습니다.
- `game_project.py --mode upgrade`가 기본 Wiki와 Game overlay를 함께 갱신합니다.

먼저 dry-run으로 쓰기 계획을 확인하세요.

```bash
python scripts/game_project.py \
  --project-root ./MyGame \
  --config ./config.game.json \
  --mode migrate \
  --profile standard \
  --dry-run
```

설정 예시는 [`config.game.example.json`](config.game.example.json), 전체 계약은 [게임 프로젝트 모드](GAME_PROJECT_MODE.ko.md)에 있습니다.

## 선택 기능과 보존 경계

Graphify는 탐색·시각화를 돕는 선택 기능입니다. Codex는 `$graphify <WIKI_ROOT>`, Claude Code는 `/graphify <WIKI_ROOT>`로 실행합니다. Raw와 Markdown이 기준이며 Graphify나 embedding이 이를 대체하지 않습니다.

`templates/web-clipper/`의 Obsidian Web Clipper 템플릿은 웹 자료를 `raw/reference/`에 모읍니다. 수집만 된 Raw는 ingest와 검토 전까지 현재 지식이 아닙니다.

오래 보존할 데이터는 `raw/`, `wiki/sources/`, Evidence의 `wiki/claims/`, `wiki/canon/`, `wiki/experiments/`, 필요한 `.session-memory/` 기록입니다. `.wiki-cache/`, Graphify output, 파생 index와 embedding은 다시 만들 수 있습니다.

## 고급 CLI

기본 config는 [`config.example.json`](config.example.json)과 같습니다.

```json
{"project_name": "My Wiki", "domain_summary": "프로젝트 목적 한 문장"}
```

Windows에서는 `python` 대신 `py -3`을 사용할 수 있습니다.

```bash
python scripts/bootstrap.py --target ./MyWiki --config ./config.json --mode new --profile standard
python scripts/bootstrap.py --target ./ResearchWiki --config ./config.json --mode new --profile evidence
python scripts/bootstrap.py --target ./ExistingProject --config ./config.json --mode migrate --profile evidence
python scripts/upgrade.py --target ./ExistingWiki --config ./config.json
python scripts/upgrade.py --target ./ExistingWiki --config ./config.json --profile evidence
python scripts/upgrade.py --target ./ExistingWiki --config ./config.json --source local
```

## 설치 후 확인

```bash
python ".claude/skills/ingest/scripts/ingest_runtime.py" status
python ".session-memory/scripts/session_memory.py" status
```

- `wiki/index.md`, `CLAUDE.md`, `raw/CLAUDE.md`, `.llm-wiki.json` 존재 여부
- placeholder 잔존 여부
- Evidence의 `wiki/evidence-model.md`, `instructions/evidence-operations.md`, `tools/kb.py`, `canon-review`
- upgrade의 `upgrade_source`, `bootstrap_commit`, `backup_dir`와 `.llm-wiki.json.last_upgrade.commit`
- Game의 `tools/game_trace.py verify`와 project integrity

## 설계 원칙과 비목표

Raw는 불변입니다. LLM 답변은 Evidence에서 출처이지 검증 권위가 아닙니다. 같은 lineage를 독립 근거로 부풀리지 않고 반증·충돌·실패한 실험도 보존합니다. 모르면 `UNKNOWN`으로 남기며 Claim과 Canon을 분리합니다. `migrate`와 `upgrade`는 비파괴적으로 동작하고 GitHub 실패를 오래된 local fallback으로 숨기지 않습니다.

기본 설치는 Kubernetes, 대규모 Vector DB, Neo4j cluster, microservices, 외부 DB 정본을 요구하지 않습니다. 파일과 Markdown을 중심으로 운영합니다.

## 용어집

| 용어 | 쉬운 뜻 |
|---|---|
| Raw | 수정하지 않고 보존하는 원문 |
| Source record | 원문이 어디서 왔고 무엇을 담는지 연결하는 출처 기록 |
| Claim | 하나씩 참·거짓이나 상태를 판단할 수 있는 주장 |
| Atomic Claim | 한 가지 내용만 담은 주장 |
| Evidence | Claim을 지지하거나 반박하는 자료 또는 관찰 |
| Conflict | 양립하지 않는 Claim을 억지로 합치지 않고 보존한 기록 |
| Experiment | 가설을 확인할 조건·방법·지표·결과 기록 |
| Canon | 검토 후 프로젝트가 현재 채택한 지식. 절대적 진리가 아님 |
| provenance | 정보가 어디서 왔는지에 대한 기록 |
| lineage | 정보가 다른 출처와 AI를 거치며 전달된 계보 |
| locator | 원문의 정확한 섹션·줄·메시지·함수로 돌아가기 위한 위치 정보 |
| cache | 삭제되어도 원문에서 다시 만들 수 있는 파생 데이터 |

## License

MIT
