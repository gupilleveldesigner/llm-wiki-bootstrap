# 게임 프로젝트 모드

`game` project mode는 LLM Wiki를 실제 게임 제작 프로젝트와 함께 운영하기 위한 비파괴 overlay다. 기존 `standard` / `evidence` vault profile을 대체하지 않으며, 그 위에 다음 두 계약을 추가한다.

```text
Design Intent → Implementation State → Validation Evidence → Project Decision

기획 정본 ↔ live 코드·씬·데이터·에셋 정본
```

Game mode v6는 v5의 비파괴 설치·trace 계약을 유지하고 선택 provider를 추가한다.

> **엔진 프로젝트의 기존 구조는 유지하고, Wiki는 기본적으로 별도 sidecar vault에 설치한다.**

## 선택 provider 연결 (v6)

| 계층 | 담당 | 질문 |
| --- | --- | --- |
| LLM Wiki | 정본 지식, 의도, 검증, 결정 | WHY |
| [CodeGraph](https://github.com/codegraph-ai/CodeGraph) | 심볼·호출·의존성·영향 범위·관련 테스트 | HOW |
| [Graphify](https://github.com/Graphify-Labs/graphify) | 코드·문서·스키마·자료를 아우르는 프로젝트 관계 | WHAT |

실제 구현의 기준은 live 엔진 프로젝트다. 두 provider의 그래프는 각각 유지하고,
호스트의 범위가 확인된 조회와 파일·심볼 참조로 연결한다. 설치기는 provider를
설치·시작·인덱싱하지 않는다. 노드·간선·쿼리 응답·provider 내부 ID를 Wiki나
`traceability.json`에 복제하지 않으며, CodeGraph memory에 결정을 이중 저장하지 않는다.

설치 config에서 두 역할을 각각 선택할 수 있다.

```json
{"providers": {"code_intelligence": "codegraph", "knowledge_graph": "graphify"}}
```

설정은 `.llm-wiki.json`의 `game_project.providers`와
`provider_schema_version: 1`에 저장한다. 새 설치에서 생략한 역할은 `null`이며,
업그레이드에서는 생략한 역할의 기존 선택을 보존한다. 명시적인 `null`은 비활성화다.
알 수 없는 provider ID는 실행하지 않고 unsupported로 표시한다. 잘못된 역할·자료형과
지원하지 않는 schema version은 변경 전에 거부한다. 기존 v5 config는 수정 없이
사용할 수 있고 trace schema 2, sync baseline 1, ingest ledger 3은 바뀌지 않는다.

```text
python tools/game_providers.py status
python tools/game_providers.py route WHY --query "락온을 채택한 이유"
python tools/game_providers.py --inventory <session-tools.json> route WHAT --query "target selection camera"
python tools/game_providers.py --inventory <session-tools.json> route HOW --query "selectTarget" --live-ref "src/lockon.ts#LockOn.selectTarget"
```

vault에서 실행하거나 `--vault-root`를 지정한다. 설치된
`instructions/game-providers.md`에 임시 inventory 형식이 있다. 에이전트는 현재
호스트의 실제 도구 스키마를 복사하고, 정확한 `connection_id`가 연결된 서버의
기본 corpus와 project/Wiki 범위를 확인한다. 실제 호출 직전과 후속 조회에서도
같은 연결인지 다시 확인한다. 표시 이름, 설치된 CLI, graph 파일만으로는 부족하다.
v1에서는 Graphify의 `project_path`를 추측하거나 다른 corpus로 전환하지 않는다.

이 도구는 조회 요청안을 반환한다. 직접 외부 질의를 실행하지 않는다. MCP 미설치,
알 수 없는 provider, 스키마 불일치, 잘못되거나 모호한 범위, 호스트 오류가 있으면
로컬 조회로 돌아간다. `available`은 호환되는 읽기 도구가 목록에 있다는 뜻이다.
`query_executed`는 false이고 그래프 최신 여부는 unknown으로 남는다. WHY는 Wiki,
WHAT의 대체 경로는 Wiki·프로젝트 파일, HOW의 대체 경로는 코드·검색·trace·테스트다.
두 그래프에 같은 코드 구조 질문을 중복해서 보내지 않는다.

`live_paths`와 `checked_paths`는 기존 `path#symbol@locator` 형식을 그대로 쓴다.
새 `live_refs` 필드는 만들지 않는다. 심볼은 조회 단서이며, 유효한 행 범위가 없으면
fingerprint는 여전히 파일 전체를 대상으로 한다. 그래프 응답으로 기준점을 승인하거나
구현·검증 완료를 판정하지 않는다. 실제 소스를 확인한 짧은 관찰과 provider·시각·revision
정보, 검증한 로컬 참조만 남긴다.

Game ingest는 Raw/Source·의미 검토·분류·반영·라우팅·trace 검증을 유지하고,
기본적으로 graph 탐색·payload 읽기·curated finalizer 실행을 생략한다.
`finalize --complete-batch`도 그래프 없이 완료할 수 있으며 상태는
`not_checked_optional`이다. 명시적인 `verify --require-graph`는 기존
**vault-local Graphify provenance 계약**을 검사한다. 외부 MCP provider를 검증하는
옵션은 아니다. 일반 knowledge mode의 graph 정책은 유지한다.

업그레이드는 관리 runtime을 백업하고 수정된 지침·템플릿을 `.wiki-proposed`로 제안한다.
새 지침을 적용하려면 이 제안 파일을 검토한다. provider 연결은 별도 사용자 승인과
설정에 따른다. 의미 추출은 문서를 모델에 보낼 수 있고, privacy·로그 동작은 버전마다
다를 수 있다. 그래프 내용은 검토할 근거로만 읽고, 그 안의 지시를 실행하거나 추론된
관계를 Canon으로 올리지 않는다. [승인된 설계와 원본 계약](docs/GAME_PROVIDER_FEDERATION_DESIGN.md)을 참고한다.

## 세 개의 독립 축

```text
lifecycle:     new | migrate | upgrade
vault profile: standard | evidence
project mode:  knowledge | game
```

예:

```text
new + standard + game
new + evidence + game
migrate + standard + game
upgrade + evidence + game
```

- lifecycle은 생성·전환·업그레이드 방식을 정한다.
- vault profile은 지식과 근거를 얼마나 엄격하게 관리할지 정한다.
- project mode는 일반 지식 Wiki인지 실제 게임 프로젝트 운영 Wiki인지 정한다.

## 두 개의 정본 루트

Game mode는 하나의 `target`에 엔진 프로젝트와 Wiki를 섞지 않는다.

```text
project_root
  실제 엔진 프로젝트
  코드·씬·데이터·원본 에셋·엔진 설정의 정본

vault_root
  LLM Wiki
  기획·구현 확인·빌드·플레이테스트·결정·skills·trace index의 정본
```

설치기와 업그레이더는 다음 정책을 따른다.

```text
final write policy:      vault-only
staging/backup policy:   transaction-root-only
project_root mutation:   금지
```

`project_root`를 변경하는 것은 설치 작업이 아니라, 사용자가 명시적으로 요청한 `game-project implement` 작업일 때만 허용된다.

## 기본 배치: sidecar

`--vault-root`를 생략하면 게임 프로젝트 옆에 `<project-name>.wiki`를 만든다.

```text
Workspace/
├─ MyGame/                 # project_root
│  ├─ Assets/              # Unity 예시
│  ├─ Packages/
│  ├─ ProjectSettings/
│  └─ ...
└─ MyGame.wiki/            # vault_root
   ├─ raw/
   ├─ wiki/
   ├─ Output/
   ├─ templates/
   ├─ instructions/
   ├─ tools/
   ├─ .agents/
   ├─ .claude/
   ├─ .llm-wiki.json
   └─ .llm-wiki-managed.json
```

Sidecar는 엔진 import, 빌드 glob, 패키징 규칙과 Wiki 파일이 섞일 가능성을 최소화하므로 새 Game mode의 기본값이다.

## 선택 배치

### Embedded

```text
MyGame/
├─ <engine-owned files>
└─ .llm-wiki/
```

```bash
python scripts/game_project.py \
  --project-root ./MyGame \
  --layout embedded \
  --config ./config.json \
  --mode migrate
```

모든 Game mode 관리 파일은 `.llm-wiki/` 아래에만 생성된다. Godot에서는 `.llm-wiki/.gdignore`를 만들어 해당 폴더가 `res://` import 대상에 포함되지 않게 한다.

### Custom

프로젝트 밖의 임의 경로를 명시한다.

```bash
python scripts/game_project.py \
  --project-root ./MyGame \
  --vault-root ../ProjectKnowledge/MyGame \
  --layout custom \
  --config ./config.json \
  --mode migrate
```

### Legacy in-place

과거처럼 `project_root == vault_root`인 구조다. 새 프로젝트에는 권장하지 않으며 기본적으로 거부한다.

```bash
python scripts/game_project.py \
  --project-root ./MyGame \
  --vault-root ./MyGame \
  --layout legacy-in-place \
  --allow-legacy-in-place \
  --config ./config.json \
  --mode upgrade
```

명시적인 opt-in 없이는 실행되지 않는다.

## Engine adapter와 보호 경로

설치 전 프로젝트 표지를 읽어 adapter를 선택한다.

### Unity

감지 표지:

```text
Assets/
Packages/
ProjectSettings/
```

보호 경로:

```text
Assets/
Packages/
ProjectSettings/
```

생성·파생 경로:

```text
Library/
Temp/
Logs/
obj/
UserSettings/
Build/
Builds/
```

기본 코드·에셋 추적 root는 `Assets/`다.

### Unreal Engine

감지 표지:

```text
*.uproject
Content/
Config/
Source/
Plugins/
```

보호 경로는 존재하는 `.uproject`, `Content/`, `Config/`, `Source/`, `Plugins/`다. `Binaries/`, `DerivedDataCache/`, `Intermediate/`, `Saved/`, `.vs/`는 생성 경로로 분류한다.

### Godot

감지 표지:

```text
project.godot
```

`.godot/`, `.import/`는 생성 경로로 분류하고, 기존 최상위 항목은 보호한다. embedded vault에는 `.gdignore`가 필수다.

### Web / Phaser / Vite / Next.js

감지 표지:

```text
package.json
src/ 또는 app/ 또는 pages/ 또는 public/
```

`package.json` dependency를 통해 Phaser, Vite, Next.js 환경을 보조 판정한다. `node_modules/`, `dist/`, `build/`, `.next/`, `.nuxt/`, `.vite/`, `coverage/`는 생성 경로다.

### Generic

알려진 표지가 없으면 generic adapter를 사용한다. Sidecar와 vault-only 정책은 그대로 적용되지만, 정확한 추적을 위해 `source_roots`를 명시하는 편이 좋다.

## 잘못된 프로젝트 루트 방지

선택한 폴더 아래에 Unity·Unreal·Godot 등의 중첩 프로젝트가 발견되면 해당 폴더를 workspace로 판정하고 적용을 거부한다.

```text
Workspace/                 # 잘못 선택
├─ UnityClient/
└─ GodotPrototype/
```

이 경우 실제 게임 폴더 하나를 `--project-root`로 다시 선택해야 한다. 여러 엔진 표지가 같은 root에서 동률로 발견돼도 모호한 것으로 보고 적용하지 않는다.

## Dry-run이 기본 사전 절차

실제 적용 전 먼저 write plan을 생성한다.

```bash
python scripts/game_project.py \
  --project-root ./MyGame \
  --config ./config.json \
  --mode migrate \
  --dry-run
```

Dry-run은 최종 vault를 만들거나 바꾸지 않는다. transaction staging에서 실제 설치와 검증을 수행한 뒤 정확한 계획을 JSON으로 반환하고 staging을 제거한다.

주요 결과:

```text
project_root
vault_root
transaction_root
layout
engine adapter와 감지 근거
protected_roots
source_roots
creates / updates / deletes
collisions
protected_path_writes
symlink_violations
layout_errors
safe_to_apply
mutation_started: false
```

다음 중 하나라도 존재하면 적용을 거부한다.

- 엔진 또는 project root가 모호함
- 보호 경로 쓰기
- 기존 unmanaged 파일 덮어쓰기
- 사용자가 수정한 관리 문서를 직접 덮어쓰기
- 기존 파일 삭제
- 기존 vault symlink 또는 symlink를 통해 vault 밖으로 쓰기. Staging은 symlink를 따라가지 않는다.
- project_root와 vault_root의 위험한 중첩
- 기존 비-Wiki 폴더를 검토 없이 vault로 채택

기존 비-Wiki 폴더를 의도적으로 vault로 전환할 때만 dry-run을 검토한 뒤 `--adopt-existing-vault`를 사용한다.

## Staging, 원자적 적용, rollback

적용 과정:

```text
1. engine/project/vault layout 감지
2. 기존 vault를 transaction staging으로 복사
3. staging에서 base Wiki 생성·업그레이드
4. staging에서 Game overlay·skills·runtime 설치
5. traceability rebuild/verify
6. managed manifest와 정확한 write plan 생성
7. safe_to_apply 확인
8. 같은 파일시스템의 rename으로 vault 교체
9. 적용 후 managed/runtime/trace/project-integrity 재검증
10. 실패 시 이전 vault 자동 복구
```

기존 vault는 기본적으로 transaction root의 rollback backup으로 남긴다. 필요 없을 때만 `--discard-rollback-backup`을 사용한다.

## Project integrity 검증

기본값:

```bash
--integrity metadata
```

보호 경로의 파일 크기, 수정 시각, 파일 종류를 적용 전후 비교한다.

내용까지 강하게 검증하려면:

```bash
--integrity full
```

SHA-256까지 비교한다. 엔진 소유 경로가 달라지면 새 vault의 적용을 실패 처리하고 이전 vault를 복구한다.

`--integrity off`도 존재하지만 엔진 프로젝트에 적용할 때는 권장하지 않는다.

## 관리 파일 소유권

`vault_root/.llm-wiki-managed.json`이 Game mode가 관리하는 파일과 설치 시점 hash를 기록한다.

정책:

```text
system-managed
  skills와 runtime

metadata
  .llm-wiki.json, managed manifest

managed-proposal
  사용자가 수정하면 직접 덮어쓰지 않고 제안 방식으로 갱신할 문서

seeded-user-editable
  최초 생성 후 사용자 소유가 되는 문서

derived
  traceability index처럼 재생성 가능한 파일
```

업그레이드는 이전 hash와 현재 파일을 비교해 사용자 변경을 구분한다. 사용자 편집 문서를 직접 덮어써야 하는 상황은 충돌로 보고 적용하지 않는다.

## Game config

```json
{
  "project_name": "DI LEMMATON Wiki",
  "domain_summary": "게임 설계와 실제 구현·검증을 연결한다",
  "project_root": "../DI_LEMMATON",
  "layout": "sidecar",
  "engine": "auto",
  "game_title": "DI:LEMMATON",
  "game_engine": "Phaser 3",
  "game_genre": "2D action puzzle",
  "target_platforms": "Web, Windows",
  "project_phase": "vertical-slice",
  "source_roots": ["src/", "public/assets/"]
}
```

`project_name`과 `domain_summary`는 new/migrate에서 필요하다. `project_root`, `vault_root`는 config 또는 CLI에서 지정할 수 있으며 CLI가 더 명확하다.

## 생성과 전환

### Standard + Game sidecar

```bash
python scripts/game_project.py \
  --project-root ./MyGame \
  --config ./config.json \
  --mode migrate \
  --profile standard \
  --dry-run
```

계획이 안전하면 `--dry-run`을 제거한다. Sidecar가 없으면 새 Wiki를 생성하고, 기존 게임 프로젝트는 이동·수정하지 않는다.

### Evidence + Game

```bash
python scripts/game_project.py \
  --project-root ./MyGame \
  --config ./config.json \
  --mode migrate \
  --profile evidence
```

## 업그레이드

GitHub 최신 exact SHA가 기본이다.

```bash
python scripts/game_project.py \
  --project-root ./MyGame \
  --vault-root ../MyGame.wiki \
  --config ./config.json \
  --mode upgrade
```

오프라인 local bundle을 명시할 때만:

```bash
python scripts/game_project.py \
  --project-root ./MyGame \
  --vault-root ../MyGame.wiki \
  --config ./config.json \
  --mode upgrade \
  --source local
```

Game mode Wiki는 base `scripts/upgrade.py`만 사용하지 않는다. `game_project.py --mode upgrade`가 base Wiki, Game overlay, engine-layout contract, trace runtime을 같은 checkout에서 함께 갱신한다.

## 기획과 코드의 별도 추적

기획 정본:

```text
vault_root/wiki/game/features/
vault_root/wiki/game/systems/
vault_root/wiki/game/levels/
vault_root/wiki/game/content/
vault_root/wiki/game/narrative/
vault_root/wiki/game/ui-ux/
vault_root/wiki/game/technical/
vault_root/wiki/game/assets/
```

구현 정본:

```text
project_root의 실제 코드·씬·데이터·원본 에셋
```

기획 문서는 안정된 ID와 project-relative path를 가진다.

```yaml
feature_id: FEATURE-LOCKON-001
live_paths:
  - src/combat/LockOnSystem.ts#selectTarget@lines 84-139
```

구현 확인은 정확한 Git revision에서 비교한다.

```yaml
check_id: IMPL-LOCKON-004
subject_id: FEATURE-LOCKON-001
source_revision: abc123def456
checked_paths:
  - src/combat/LockOnSystem.ts#selectTarget@lines 84-139
```

## Traceability index

설치 파일:

```text
vault_root/wiki/game/traceability.json
vault_root/tools/game_trace.py
```

`traceability.json`은 직접 편집하지 않는 파생 인덱스다.

```text
spec --implemented_by--> code
spec --built_in--------> build
spec --validated_by----> test
spec --governed_by-----> decision
```

실행기는 manifest에서 sidecar `project_root`를 해석하므로 vault에서 그대로 실행할 수 있다.

```bash
cd ../MyGame.wiki
python tools/game_trace.py rebuild
python tools/game_trace.py verify
python tools/game_trace.py verify --strict-stale
python tools/game_trace.py spec FEATURE-LOCKON-001
python tools/game_trace.py path src/combat/LockOnSystem.ts#selectTarget
python tools/game_trace.py affected --base HEAD~1 --head HEAD
python tools/game_trace.py matrix
```

관계 상태:

```text
current
  마지막 구현 확인 이후 연결된 코드 경로가 바뀌지 않음

stale
  코드 경로가 바뀌어 기획↔구현 비교를 다시 해야 함

unverified
  구현 확인 또는 비교 가능한 revision이 없음

missing
  추적한 live path가 존재하지 않음
```

`stale`은 의미상 오류를 자동 단정하지 않고 재검사를 요구하는 상태다.

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

기획 문서의 존재는 구현 증거가 아니며, 코드 존재는 플레이 경험 검증 증거가 아니다. `done`도 `passed`를 뜻하지 않는다.

## `game-project` operation

```text
define      기능·시스템·레벨·콘텐츠·UI·에셋 의도 정의
plan        마일스톤·의존성·리스크·출구 조건
implement   사용자가 명시한 범위에서 project_root 실제 변경
inspect     spec과 live source 비교
trace       기획↔코드·빌드·테스트·결정 조회
impact      Git diff에서 영향받는 spec 계산
playtest    검증 질문·관찰·해석·후속 분리
build       exact revision/build/platform과 스모크 결과
decide      옵션·기준·근거·부작용·supersedes
bug         재현·원인·수정·회귀 검증
release     계획 범위와 실제 포함 범위 고정
```

## Evidence + Game

Evidence profile과 결합하면 플레이테스트 원본, 로그, 텔레메트리, 외부 분석을 Raw/Source로 추적하고, 경험적 일반화를 Claim으로, 반례를 Conflict로, 재검증을 Experiment로 관리한다.

Traceability graph는 **어떤 기획이 어떤 코드·빌드·테스트·결정과 연결되는지** 답한다. Evidence graph는 **그 결론을 어떤 원본 근거가 지지하는지** 답한다. 둘은 보완 관계이지만 서로 대체하지 않는다.

## 비목표

Game mode는 다음을 자동으로 보장하지 않는다.

- 게임 엔진 설치
- 모든 proprietary binary 포맷의 의미 분석
- 빌드 성공
- 자동 설계 승인
- 코드 diff만으로 의미 변화 단정
- 자동 Canon 승격
- 외부 이슈 트래커 대체
- live source의 자동 재배치

Game mode v5의 설치 계약은 **기존 엔진 구조를 바꾸지 않고, 별도 vault에서 기획·구현·검증·결정을 추적하는 것**이다.

## Game-aware ingest v5

Game 모드는 공용 Raw→Source 엔진을 복제하지 않고 Game adapter를 설치한다.

```text
/ingest → manifest adapter 자동 라우팅
/game-ingest → 동일 adapter의 명시적 진입점
```

- `raw/game/design`, `playtests`, `builds`, `telemetry`, `references`를 유형별로 라우팅한다.
- Game 문서는 일반 `topics/tags` 대신 타입별 안정된 ID, `raw_refs`, `evidence_refs`, `subject_refs`를 검증한다.
- 성공한 finalize는 `game_trace scan/status/verify`를 수행하고 ledger v3에 Source ID, Game ID, sync counts를 기록한다.
- `ingest_status`, `game_reflection_status`, `game_sync_status`를 분리한다.
- ingest는 기획·코드를 자동 덮어쓰거나 `game_trace accept`를 자동 실행하지 않는다.

정본 절차는 `instructions/game-ingest.md`와 설치된 `game-ingest` 스킬에 있다.
