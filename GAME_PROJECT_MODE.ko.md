# 게임 프로젝트 모드

`game` project mode는 LLM Wiki를 실제 게임 제작 프로젝트와 함께 쓰기 위한 운영 overlay입니다. 기존 `standard`/`evidence` profile을 대체하지 않고, 그 위에 게임 설계·구현·검증·결정 계층을 추가합니다.

```text
lifecycle:    new | migrate | upgrade
vault profile: standard | evidence
project mode: knowledge | game
```

가능한 조합 예:

```text
new + standard + game
new + evidence + game
migrate + standard + game
upgrade + evidence + game
```

## 왜 profile이 아니라 project mode인가

`standard`와 `evidence`는 **지식을 얼마나 엄격하게 추적할지**를 정합니다.

- `standard`: Raw 원문을 Wiki 지식과 Output으로 연결
- `evidence`: Source·Claim·Conflict·Experiment·Decision·reviewed Canon까지 provenance 추적

반면 `game`은 **어떤 종류의 프로젝트를 운영할지**를 정합니다. 게임에는 다음처럼 서로 다른 상태가 동시에 존재합니다.

- 기획서는 승인됐지만 아직 구현되지 않음
- 코드는 구현됐지만 플레이테스트하지 않음
- 테스트는 통과했지만 최종 방향으로 채택되지 않음
- 작업 티켓은 done이지만 다른 플랫폼에서는 검증하지 않음

이를 하나의 `status`로 합치면 AI가 쉽게 잘못된 완료 판단을 내립니다. Game mode는 다음 추적선을 강제합니다.

```text
Design Intent → Implementation State → Validation Evidence → Project Decision
```

그리고 작업 흐름은 별도의 `production_status`로 둡니다.

## 상태 모델

### Design Intent

플레이어가 무엇을 경험해야 하고, 기능·시스템·레벨·콘텐츠가 어떤 규칙을 가져야 하는지 나타냅니다.

```text
design_status: idea | proposed | accepted | superseded | rejected
```

### Implementation State

현재 live game project의 코드·씬·데이터·에셋이 실제로 무엇을 하는지 나타냅니다.

```text
implementation_status: unknown | not_started | in_progress | implemented | blocked
```

`implemented`에는 가능한 한 path, symbol, scene, data key, commit/revision 또는 build ID가 필요합니다.

### Validation Evidence

실제로 실행한 테스트·빌드·플레이테스트·로그·텔레메트리에서 확인한 결과입니다.

```text
validation_status: untested | partial | passed | failed
```

관찰과 해석을 분리하고, `passed`는 확인한 플랫폼·빌드·조건에서만 유효합니다.

### Project Decision

대안 중 무엇을 왜 채택·기각했는지 기록합니다.

```text
decision_status: proposed | accepted | rejected | superseded
```

결정은 설계 방향을 바꿀 수 있지만 구현·검증을 자동 완료시키지 않습니다.

### Production Status

백로그와 마일스톤의 작업 흐름입니다.

```text
production_status: backlog | ready | in_progress | blocked | done
```

`done`은 작업이 종료됐다는 뜻이지 `implementation_status: implemented` 또는 `validation_status: passed`의 증거가 아닙니다.

## Live game project와 Raw의 경계

Game mode에서 가장 중요한 안전 규칙입니다.

> 실행 중인 엔진 프로젝트, 코드, 원본 에셋, 데이터 파일은 live source이며 `raw/`로 이동하지 않습니다.

`migrate`는 기존 게임 폴더의 `Source/`, `Assets/`, `Content/`, `Packages/`, `addons/`, 프로젝트 설정과 저장소 구조를 그대로 보존합니다.

`raw/game/`에는 불변 증거로 보관할 자료만 둡니다.

- 외부 기획 원문과 참고자료
- 플레이테스트 원본 메모·설문 export·녹화 메타데이터
- 빌드 로그·크래시 리포트·텔레메트리 export
- 외부 LLM·도구 분석 원문
- 승인된 전달본이나 변경하지 않을 스냅샷

현재 구현을 설명할 때는 live source를 직접 읽고 정확한 revision을 기록합니다.

## 설치되는 구조

```text
MyGame/
├─ raw/
│  └─ game/
│     ├─ design/
│     ├─ playtests/
│     ├─ builds/
│     ├─ telemetry/
│     └─ references/
├─ wiki/
│  └─ game/
│     ├─ index.md
│     ├─ overview.md
│     ├─ vision.md
│     ├─ pillars.md
│     ├─ roadmap.md
│     ├─ model.md
│     ├─ features/
│     ├─ systems/
│     ├─ levels/
│     ├─ content/
│     ├─ narrative/
│     ├─ ui-ux/
│     ├─ technical/
│     ├─ implementation/
│     ├─ assets/
│     ├─ playtests/
│     ├─ builds/
│     ├─ bugs/
│     ├─ decisions/
│     ├─ proposals/
│     ├─ milestones/
│     └─ releases/
├─ templates/
│  └─ game/
├─ instructions/
│  └─ game-project.md
├─ Output/
│  └─ game/
├─ .agents/skills/game-project/
├─ .claude/skills/game-project/
└─ .llm-wiki.json
```

## 기본 config

```json
{
  "project_name": "DI LEMMATON Wiki",
  "domain_summary": "게임 설계와 실제 구현·검증을 연결한다",
  "game_title": "DI:LEMMATON",
  "game_engine": "Phaser 3",
  "game_genre": "2D action puzzle",
  "target_platforms": "Web, Windows",
  "project_phase": "vertical-slice",
  "source_roots": ["src/", "public/assets/"]
}
```

`game_title` 이하 필드는 선택 사항입니다. 모르는 값은 `UNKNOWN`, source roots는 빈 목록으로 시작할 수 있습니다.

## 새 게임 Wiki 생성

### Standard + Game

```bash
python scripts/game_project.py \
  --target ./MyGame \
  --config ./config.json \
  --mode new \
  --profile standard
```

### Evidence + Game

```bash
python scripts/game_project.py \
  --target ./MyGameResearch \
  --config ./config.json \
  --mode new \
  --profile evidence
```

## 기존 게임 폴더 비파괴 전환

```bash
python scripts/game_project.py \
  --target ./ExistingGame \
  --config ./config.json \
  --mode migrate \
  --profile standard
```

기존 파일은 이동·삭제·수정하지 않습니다. router나 template 충돌은 `.wiki-proposed`로 제안됩니다. 제안이 있으면 `project_mode_activation_pending: true`가 정상입니다.

## 기존 Wiki에 Game mode 추가 또는 갱신

GitHub 최신이 기본입니다.

```bash
python scripts/game_project.py \
  --target ./ExistingWiki \
  --config ./config.json \
  --mode upgrade
```

Evidence로 승격하면서 추가할 수도 있습니다.

```bash
python scripts/game_project.py \
  --target ./ExistingWiki \
  --config ./config.json \
  --mode upgrade \
  --profile evidence
```

Game mode Wiki는 base `scripts/upgrade.py`만 실행하지 마십시오. `game_project.py --mode upgrade`가 base Wiki와 game overlay를 같은 최신 checkout에서 함께 갱신합니다.

오프라인 로컬 bundle을 명시할 때만:

```bash
python scripts/game_project.py \
  --target ./ExistingWiki \
  --config ./config.json \
  --mode upgrade \
  --source local
```

이 결과는 GitHub latest가 아닙니다.

## 템플릿

| 작업 | 템플릿 |
|---|---|
| 플레이어 기능 | `templates/game/feature-spec.md` |
| 규칙·상태 시스템 | `templates/game/system-spec.md` |
| 레벨·스테이지 | `templates/game/level-spec.md` |
| 캐릭터·적·아이템·퀘스트 | `templates/game/content-spec.md` |
| 설계 대비 실제 구현 확인 | `templates/game/implementation-check.md` |
| 플레이테스트 | `templates/game/playtest-report.md` |
| 빌드·스모크 | `templates/game/build-report.md` |
| 채택·기각·대체 결정 | `templates/game/decision-record.md` |
| 2D/3D/UI/오디오 에셋 | `templates/game/asset-brief.md` |
| 버그·회귀 | `templates/game/bug-report.md` |
| 마일스톤 | `templates/game/milestone.md` |

## `game-project` 스킬

설치된 프로젝트 로컬 스킬은 요청을 다음 operation으로 라우팅합니다.

- `define`: 기능·시스템·레벨·콘텐츠·UI·에셋 의도 정의
- `plan`: 마일스톤·의존성·리스크·출구 조건
- `implement`: live source 실제 변경
- `inspect`: spec 대비 구현 일치 확인
- `playtest`: 검증 질문, 관찰, 해석, 후속 분리
- `build`: exact revision/build/platform과 스모크 결과
- `decide`: 옵션·기준·근거·부작용·supersedes
- `bug`: 재현·원인·수정·회귀 검증
- `release`: 계획 범위와 실제 포함 범위 고정

## Evidence + Game

Evidence profile과 결합하면 다음이 추가됩니다.

```text
플레이테스트 원본 / 로그 / 텔레메트리
  ↓ Source
관찰에서 도출한 경험적 주장
  ↓ Claim
지지 / 반박 / Conflict / Experiment
  ↓
reviewed Canon 또는 Project Decision
```

Game 문서의 `evidence_refs`가 Source·Claim·Experiment·Decision을 연결합니다. 현재 채택된 설계와 경험적으로 확인된 사실은 서로 다른 종류의 기록입니다.

예:

- “이 전투방은 시야가 좁아 측면 적을 놓친다” → 플레이테스트 관찰/Claim
- “측면 적을 제거하고 중앙 위협으로 바꾼다” → Project Decision
- “새 배치가 문제를 줄였다” → 새 build에서 다시 검증해야 하는 Claim

Canon 자동 승격은 여전히 금지됩니다.

## 업그레이드 안전성

Game upgrade는 대상 파일을 수정하기 전에 다음을 모두 확인합니다.

1. GitHub의 현재 default branch
2. 최신 정확한 40자 commit SHA
3. exact SHA archive
4. archive path traversal 안전성
5. base Wiki contract files
6. `scripts/game_project.py`
7. game docs/templates/agent/Claude adapter contract markers

검증 실패 시 대상 Wiki를 수정하지 않으며, 오래된 local bundle로 자동 fallback하지 않습니다.

## 검증 결과

성공 JSON에는 base 결과와 함께 다음 필드가 포함됩니다.

```json
{
  "project_mode": "game",
  "project_mode_version": 1,
  "previous_project_mode": "knowledge",
  "project_mode_changed": true,
  "project_mode_skill": "game-project",
  "project_mode_verification": {"status": "ok"},
  "project_mode_activation_pending": false,
  "game_project": {
    "game_title": "My Game",
    "game_engine": "Godot 4"
  }
}
```

`migrate` 또는 충돌이 있는 `upgrade`에서는 verification이 `pending`이고 `.wiki-proposed` 목록이 반환될 수 있습니다. 이는 실패가 아니라 사용자 문서를 보존하기 위한 검토 게이트입니다.

## 비목표

Game mode는 다음을 자동으로 보장하지 않습니다.

- 게임 엔진 자체 설치
- 모든 엔진 포맷의 완전한 파싱
- 빌드 성공 또는 테스트 통과
- 자동 설계 승인
- 자동 Canon 승격
- Jira/Linear/GitHub Projects 같은 외부 이슈 트래커 대체
- live source의 복사·재배치·정리

정확한 완료 판단은 실제 source, build, 테스트와 사람의 결정을 연결해 얻습니다.
