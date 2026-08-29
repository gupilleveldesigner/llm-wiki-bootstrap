# 게임 프로젝트 모드

`game` project mode는 LLM Wiki를 실제 게임 제작 프로젝트와 함께 운영하기 위한 비파괴 overlay다. 기존 `standard` / `evidence` vault profile을 대체하지 않으며, 그 위에 다음 두 계약을 추가한다.

```text
Design Intent → Implementation State → Validation Evidence → Project Decision

기획 정본 ↔ live 코드·씬·데이터·에셋 정본
```

Game mode v5의 기본 원칙은 명확하다.

> **엔진 프로젝트의 기존 구조는 유지하고, Wiki는 기본적으로 별도 sidecar vault에 설치한다.**

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
