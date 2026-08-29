# 게임 프로젝트 모드

`game` project mode는 LLM Wiki를 실제 게임 제작 프로젝트와 함께 쓰기 위한 운영 overlay입니다. 기존 `standard`/`evidence` profile을 대체하지 않고, 그 위에 게임 설계·구현·검증·결정과 **기획↔코드 traceability**를 추가합니다.

```text
lifecycle:     new | migrate | upgrade
vault profile: standard | evidence
project mode:  knowledge | game
```

가능한 조합 예:

```text
new + standard + game
new + evidence + game
migrate + standard + game
upgrade + evidence + game
```

## 왜 profile이 아니라 project mode인가

`standard`와 `evidence`는 지식을 얼마나 엄격하게 추적할지 정합니다.

- `standard`: Raw 원문을 Wiki 지식과 Output으로 연결
- `evidence`: Source·Claim·Conflict·Experiment·Decision·reviewed Canon까지 provenance 추적

`game`은 어떤 종류의 프로젝트를 운영할지 정합니다. 게임에는 다음 상태가 동시에 존재할 수 있습니다.

- 기획은 승인됐지만 아직 구현되지 않음
- 코드는 구현됐지만 플레이테스트하지 않음
- 테스트는 통과했지만 최종 방향으로 채택되지 않음
- 작업 티켓은 `done`이지만 다른 플랫폼에서는 검증하지 않음

이를 하나의 상태로 합치지 않습니다.

```text
Design Intent → Implementation State → Validation Evidence → Project Decision
```

작업 흐름은 별도의 `production_status`로 둡니다.

## 독립 상태

```text
design_status:
  idea | proposed | accepted | superseded | rejected

implementation_status:
  unknown | not_started | in_progress | implemented | blocked

validation_status:
  untested | partial | passed | failed

decision_status:
  proposed | accepted | rejected | superseded

production_status:
  backlog | ready | in_progress | blocked | done
```

문서가 존재해도 구현 증거는 아니고, 코드가 존재해도 플레이 경험 검증 증거는 아니며, `done`은 `passed`를 뜻하지 않습니다.

## Live game project와 Raw의 경계

> 실행 중인 엔진 프로젝트, 코드, 씬, 원본 에셋, 데이터 파일은 live source이며 `raw/`로 이동하지 않습니다.

`migrate`는 `Source/`, `Assets/`, `Content/`, `Packages/`, `addons/`, `src/` 등 기존 게임 프로젝트 구조를 그대로 보존합니다.

`raw/game/`에는 불변 증거만 둡니다.

- 외부 기획 원문과 참고자료
- 플레이테스트 원본 메모·설문 export·녹화 메타데이터
- 빌드 로그·크래시 리포트·텔레메트리 export
- 외부 LLM·도구 분석 원문
- 승인된 전달본이나 변경하지 않을 스냅샷

## 기획과 코드를 각각 추적하는 구조

### 기획 정본

```text
wiki/game/features/
wiki/game/systems/
wiki/game/levels/
wiki/game/content/
wiki/game/narrative/
wiki/game/ui-ux/
wiki/game/technical/
wiki/game/assets/
```

각 기획은 안정된 ID를 가집니다.

```yaml
feature_id: FEATURE-LOCKON-001
design_status: accepted
implementation_status: implemented
validation_status: partial
live_paths:
  - src/combat/LockOnSystem.ts#selectTarget@lines 84-139
implementation_check_refs:
  - wiki/game/implementation/IMPL-LOCKON-004.md
build_refs:
  - BUILD-2026-08-29-001
playtest_refs:
  - PLAYTEST-LOCKON-003
decision_refs:
  - GDEC-LOCKON-002
```

### 코드 정본

코드는 Wiki로 복사하지 않습니다. 실제 프로젝트의 live path, symbol, scene, data key, Git revision, build ID를 참조합니다.

코드 참조 형식:

```text
project/relative/path
project/relative/path#Symbol
project/relative/path#Symbol@locator
```

절대 경로와 `..` 탈출 경로는 허용하지 않습니다.

### 기획↔코드 연결 정본

`wiki/game/implementation/`의 구현 확인 문서가 기획 ID와 실제 코드를 연결합니다.

```yaml
check_id: IMPL-LOCKON-004
subject_id: FEATURE-LOCKON-001
expected_spec: wiki/game/features/FEATURE-LOCKON-001.md
source_revision: abc123def456
build_id: BUILD-2026-08-29-001
checked_paths:
  - src/combat/LockOnSystem.ts#selectTarget@lines 84-139
implementation_status: implemented
validation_status: partial
```

구현 확인에서는 항목마다 다음을 구분합니다.

```text
일치 | 부분 일치 | 불일치 | 확인 불가
```

## 자동 Traceability Index

Game mode v2는 다음을 설치합니다.

```text
wiki/game/traceability.json   # 파생 node/edge index
tools/game_trace.py           # rebuild/query/verify/impact runtime
```

`traceability.json`은 직접 편집하지 않습니다. 다음 canonical 문서의 frontmatter에서 재생성합니다.

- 기능·시스템·레벨·콘텐츠·에셋 등 spec
- implementation check
- build report
- playtest report
- decision record

### 파생 graph

```text
spec --implemented_by--> code
spec --built_in--------> build
spec --validated_by----> test
spec --governed_by-----> decision
```

따라서 다음을 양방향으로 조회할 수 있습니다.

- 이 기획을 구현하는 코드는 어디인가?
- 이 코드가 어떤 기획을 구현하는가?
- 어느 build와 playtest가 이 기획을 검증했는가?
- 어떤 결정이 이 기획에 영향을 줬는가?

### 명령

```bash
python tools/game_trace.py rebuild
python tools/game_trace.py verify
python tools/game_trace.py verify --strict-stale
python tools/game_trace.py spec FEATURE-LOCKON-001
python tools/game_trace.py path src/combat/LockOnSystem.ts#selectTarget
python tools/game_trace.py affected --base HEAD~1 --head HEAD
python tools/game_trace.py matrix
```

- `rebuild`: canonical 문서에서 index 재생성
- `verify`: index 최신성, ID, code path, 미해결 참조 검사
- `spec`: 기획→code/build/test/decision 조회
- `path`: code→기획 역조회
- `affected`: Git diffk�� 영향받는 기획 계산
- `matrix`: 기획별 대응 현황 요약

### stale 판정

구현 확인의 `source_revision` 이후 연결된 code path가 변경되면 relation을 `stale`로 표시합니다.

```text
current     마지막 확인 revision 이후 해당 path가 바뀌지 않음
stale       마지막 확인 revision 이후 해당 path가 바뀜
unverified  확인 기록 또는 비교 가능한 revision이 없음
missing     추적 중인 live path가 존재하지 않음
```

`stale`은 구현 오류라는 단정이 아니라 **기획과 코드의 일치 여부를 다시 확인해야 한다는 신호**입니다.

## 설치되는 구조

```text
MyGame/
├─ raw/game/
│  ├─ design/
│  ├─ playtests/
│  ├─ builds/
│  ├─ telemetry/
│  └─ references/
├─ wiki/game/
│  ├─ index.md
│  ├─ overview.md
│  ├─ vision.md
│  ├─ pillars.md
│  ├─ roadmap.md
│  ├─ model.md
│  ├─ traceability.json
│  ├─ features/
│  ├─ systems/
│  ├─ levels/
│  ├─ content/
│  ├─ narrative/
│  ├─ ui-ux/
│  ├─ technical/
│  ├─ implementation/
│  ├─ assets/
│  ├─ playtests/
│  ├─ builds/
│  ├─ bugs/
│  ├─ decisions/
│  ├─ proposals/
│  ├─ milestones/
│  └─ releases/
├─ templates/game/
├─ instructions/game-project.md
├─ tools/game_trace.py
├─ Output/game/
├─ .agents/skills/game-project/
├─ .claude/skils/game-project/
└─ .llm-wiki.json
```

Manifest에는 다음이 기로됩니다.

```json
{
  "project_mode": "game",
  "project_mode_version": 2,
  "game_traceability": {
    "schema_version": 1,
    "index": "wiki/game/traceability.json",
    "runtime": "tools/game_trace.py"
  }
}
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

`game_title` 이�: 필드는 선택 사항입니다. 모르는 값은 `UNKNOWN`, source roots는 빈 목록으로 시작할 수 있습니다.

## 생성과 전환

Standard + Game:

```bash
python scripts/game_project.py --target ./MyGame --config ./config.json --mode new --profile standard
```

Evidence + Game:

```bash
python scripts/game_project.py --target ./MyGameResearch --config ./config.json --mode new --profile evidence
```

기존 게임 폤더 비파관 전환:

```bash
python scripts/game_project.py --target ./ExistingGame --config ./config.json --mode migrate --profile standard
```

기존 파일은 이동·삭제·수정하지 않습니다. 관리 파일 충돌은 `.wiki-proposed`로 제욘됩니다.

## 기조 Wiki�에 추가 또는 갱신

GitHub 최신이 기본입니다.

```bash
python scripts/game_project.py --target ./ExistingWiki --config ./config.json --mode upgrade
```

Evidence 승격과 함께:

```bash
python scripts/game_project.py --target ./ExistingWiki --config ./config.json --mode upgrade --profile evidence
```

Game mode Wiki는 base `scripts/upgrade.py`만 실행하지 않습니다. `game_project.py --mode upgrade`가 base Wiki, game overlay, trace runtime을 같은 검증된 checkout에서 함께 갱신합니다.

명시적 offline/local 경로:

```bash
python scripts/game_project.py --target ./ExistingWiki --config ./config.json --mode upgrade --source local
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

설치된 스킬은 요청을 다음 operation으로 라우팅합니다.

- `define`: 기능·시스템·레벨·콘텐츠·UI·에셋 의도 정의
- `plan`: 마일스톤·의존성·리스크·출구 조건
- `implement`: live source 실제 변경
- `inspect`: spec 대비 구현 일치 확인
- `trace`: 기획→코드 또는 코드→기획 조회
- `impact`: Git diff 영향 분석
- `playtest`: 검증 질문·관찰·해석·후속 분리
- `build`: exact revision/build/platform과 스모크 결과
- `decide`: 옵션·기준·근거·부작용·supersedes
- `bug`: 재현·원인·수정·회귀 검증
- `release`: 계획 범위와 실제 포함 범위 고정

## Evidence + Game

Evidence profile에서는 다음이 추가됩니다.

```text
플레이테스트 원본 / 로그 / 텔레메트리
  ↓ Source
관찰에서 도출한 경험적 주장
  ↓ Claim
지지 / 반박 / Conflict / Experiment
  ↓
reviewed Canon 또는 Project Decision
```

Traceability graph는 **어떤 기획이 어떤 구현·빌드·테스트·결정과 연결되는지** 보여주고, Evidence graph는 **그 결론이 어떤 원문 근거에서 나왔는지** 보여줍니다. 둘을 같은 것으로 취급하지 않습니다.

## 업그레이드 안전성

Game upgrade는 대상 파일을 수정하기 전에 다음을 모두 확인합니다.

1. GitHub의 현재 default branch
2. 최신 정확한 40자 commit SHA
3. exact SHA archive
4. archive path traversal 안전성
5. base Wiki contract files
6. game wrapper와 installer
7. game docs/templates/skills
8. traceability template와 `game_trace.py` runtime

기존 managed skill과 trace runtime은 `.wiki-upgrade-bak/<timestamp>/`에 백업합니다. 검증 실패 시 대상 Wiki를 수정하지 않으며, 오래된 local bundle로 자동 fallback하지 않습니다.

## 비목표

Game mode는 다음을 자동으로 보장하지 않습니다.

- 게임 엔진 자체 설치
- 모든 엔진 전용 binary 포맷의 의미 해석
- 자동 빌드 성공 또는 테스트 통과
- 자동 설계 승인
- 자동 Canon 승격
- 외부 이슈 트래커 대체
- live source의 복사·재배치·정리
- code diff만 보고 기획 의미가 실제로 바뀌었다고 단정

정확한 완료 판단은 기획, live source, revision, build, 테스트와 사람의 결정을 연결해 얻습니다.
