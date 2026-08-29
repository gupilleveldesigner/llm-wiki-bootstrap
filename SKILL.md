---
name: llm-wiki-bootstrap
description: LLM Wiki를 신규 구축(new), 기존 일반 폴더에서 비파괴 전환(migrate), 또는 GitHub 공식 저장소 최신 커밋 기준으로 업그레이드(upgrade)한다. 지식관리 profile은 standard/evidence, 프로젝트 운영 mode는 기본 knowledge와 선택적 game으로 분리한다. Evidence는 Raw→Source→Claim/Project Decision→Evidence/Conflict/Experiment→reviewed Canon을 제공하고, game mode는 Design Intent→Implementation State→Validation Evidence→Project Decision 추적과 게임 기능·시스템·레벨·에셋·빌드·플레이테스트 운영 계층을 추가한다. 사용자가 LLM Wiki/세컨드브레인/Evidence Wiki를 만들거나, 기존 폴더를 Wiki로 전환하거나, Wiki를 최신화하거나, 게임 프로젝트용 Wiki·게임 기획/구현/검증 지식베이스를 구축하려는 의도를 보이면 사용한다. 기존 Wiki의 일상 ingest/query/lint/canon-review/game-project 작업에는 설치된 프로젝트 로컬 스킬을 사용한다.
---

# LLM Wiki Bootstrap

폴더를 Claude Code / Codex가 운영하는 LLM Wiki로 구축·전환·업그레이드한다.

서로 다른 세 축을 섞지 않는다.

- lifecycle mode: `new` / `migrate` / `upgrade`
- vault profile: `standard` / `evidence`
- project mode: `knowledge`(기본·manifest 생략 가능) / `game`

예를 들어 `new + evidence + game`은 새 게임 프로젝트 Wiki에 Evidence 추적까지 함께 설치한다.

## 절대 규칙

1. `raw/`는 불변이다. 기존 Raw를 수정·삭제하지 않는다.
2. `migrate`는 기존 파일을 임의로 이동하지 않는다. 이동 계획을 제시하고 사용자 승인 후 수행한다.
3. **실행 중인 게임 코드·엔진 프로젝트·원본 에셋은 Raw가 아니다.** game mode 활성화나 migrate 중 `raw/`로 옮기지 않는다.
4. `upgrade`는 GitHub 공식 저장소의 최신 default-branch HEAD를 먼저 조회한다.
5. GitHub 조회·다운로드·검증이 실패하면 대상 Wiki를 수정하지 않는다. 로컬 bundle로 조용히 fallback하지 않는다.
6. 오프라인에서 로컬 bundle을 쓰려면 사용자가 명시적으로 요청했을 때만 `--source local`을 사용한다.
7. 기존 관리 스킬은 교체 전에 `.wiki-upgrade-bak/<timestamp>/`에 백업한다.
8. Evidence의 Claim은 자동으로 Canon으로 승격하지 않는다.
9. game mode에서 설계 의도, 실제 구현, 검증 결과, 채택 결정, production 상태를 하나의 완료 상태로 합치지 않는다.
10. `.wiki-proposed`가 생기면 기존 문서를 덮어쓰지 않고 차이를 검토한다.
11. 실패한 검증을 성공으로 보고하지 않는다.
12. Evidence 설치는 파일 존재만으로 완료하지 않는다. 설치된 ingest/lint/query 회귀 테스트, `tools/kb.py selftest`, profile verification을 실제 대상에서 통과해야 한다.
13. game mode 설치도 파일 존재만으로 완료하지 않는다. router, 전용 문서·템플릿·skill, project-mode verification을 확인한다.

## 전제 조건

- Python 3.10+
- Claude Code 또는 Codex
- 온라인 upgrade에는 GitHub HTTPS 접근 가능 환경
- Graphify는 선택 사항이지만 batch ingest 완료 계약이 요구하면 따른다.

Python 실행기는 `python` → `py -3` → `python3` 순으로 찾고, Windows Microsoft Store stub은 유효한 Python으로 취급하지 않는다.

# 1. Lifecycle mode 판정

| 대상 상태 | 사용자 의도 | mode |
|---|---|---|
| 비어 있거나 없음 | 새 Wiki | `new` |
| 파일은 있으나 Wiki marker 없음 | Wiki로 전환 | `migrate` |
| `raw/` + `wiki/` 등 기존 Wiki | 최신화/upgrade 또는 game mode 추가 | `upgrade` |

기존 Wiki에 “새로 만들어줘”처럼 파괴 가능성이 있는 표현이 오면 덮어쓰지 말고 `upgrade`가 비파괴 경로임을 설명한다.

# 2. Vault profile 판정

사용자가 명시하면 그대로 사용한다.

## `standard`

일반 공부, 자료 정리, 세컨드브레인, 프로젝트 메모, 기사·영상·책 요약에 사용한다.

```text
raw → wiki → Output
```

## `evidence`

다음 신호가 핵심이면 선택한다.

- 역공학·숨겨진 구현 추정
- 여러 LLM 분석 누적
- 관찰과 추론·가설 분리
- provenance/source lineage 필요
- conflicting/rejected claim 보존
- hypothesis → experiment → conclusion 연구 루프
- 모든 결론을 원문까지 trace

```text
Raw → Source → Claim 또는 Project Decision → Evidence/Conflict/Experiment → reviewed Canon
```

핵심 문장:

> **“LLM이 말했다”와 “우리가 확인했다”를 같은 것으로 취급하지 않는다.**

`upgrade`에서 profile을 생략하면 `.llm-wiki.json`의 기존 profile을 보존한다. manifest 없는 legacy Wiki는 `standard`로 본다. Evidence → Standard 자동 downgrade는 금지한다.

# 3. Project mode 판정

## `knowledge`

기본 LLM Wiki다. 기존 manifest에 `project_mode`가 없으면 `knowledge`로 해석한다. 기존 `scripts/bootstrap.py`와 `scripts/upgrade.py`를 사용한다.

## `game`

다음 의도가 있으면 선택한다.

- 실제 게임 프로젝트와 함께 쓰는 Wiki
- 게임 기획·시스템·레벨·콘텐츠·내러티브·UI/UX·기술 문서 운영
- 설계와 실제 코드/씬/데이터/에셋의 일치 여부 추적
- 플레이테스트·빌드·버그·마일스톤·릴리스 기록
- 에셋 브리프와 runtime 규격 관리
- “기획됨 / 구현됨 / 검증됨 / 채택됨”을 분리해야 함

Game mode의 핵심 추적선:

```text
Design Intent → Implementation State → Validation Evidence → Project Decision
```

별도로 `production_status`는 작업 흐름만 나타낸다. `done`은 자동으로 `implemented`나 `passed`가 아니다.

Game mode는 profile을 대체하지 않는다.

```text
standard + game  # 가벼운 게임 제작 Wiki
 evidence + game  # Source/Claim/Experiment/Decision provenance까지 포함
```

Game → knowledge 자동 제거/downgrade는 제공하지 않는다. game 기록과 router를 없애는 작업은 별도 migration 설계가 필요하다.

# 4. 짧은 인터뷰

이미 받은 정보는 다시 묻지 않는다. 빠진 항목만 최대 한 번에 묻는다.

공통:

1. Wiki 주제와 목적
2. 주로 모을 자료 유형
3. 프로젝트 이름

Game mode에서 사용자가 이미 알려주지 않은 경우에만 추가로 받을 수 있다.

- 게임 제목
- 엔진
- 장르
- 대상 플랫폼
- 현재 제작 단계
- live source roots

모르면 `UNKNOWN` 또는 빈 목록으로 시작한다. 그럴듯하게 추정하지 않는다.

기본 config:

```json
{
  "project_name": "My Wiki",
  "domain_summary": "프로젝트 목적 한 문장"
}
```

Game config 예:

```json
{
  "project_name": "My Game Wiki",
  "domain_summary": "게임 설계와 실제 구현·검증을 연결한다",
  "game_title": "My Game",
  "game_engine": "Godot 4",
  "game_genre": "2D action puzzle",
  "target_platforms": "Windows, Web",
  "project_phase": "prototype",
  "source_roots": ["game/", "addons/"]
}
```

# 5. `new` / `migrate`

## Knowledge mode

Standard:

```bash
python "<SKILL_ROOT>/scripts/bootstrap.py" --target "<TARGET>" --config "<CONFIG>" --mode new --profile standard
```

Evidence:

```bash
python "<SKILL_ROOT>/scripts/bootstrap.py" --target "<TARGET>" --config "<CONFIG>" --mode new --profile evidence
```

`migrate`는 `--mode migrate`를 사용한다.

## Game mode

Standard + Game:

```bash
python "<SKILL_ROOT>/scripts/game_project.py" --target "<TARGET>" --config "<CONFIG>" --mode new --profile standard
```

Evidence + Game:

```bash
python "<SKILL_ROOT>/scripts/game_project.py" --target "<TARGET>" --config "<CONFIG>" --mode new --profile evidence
```

기존 게임 폴더를 비파괴 전환할 때:

```bash
python "<SKILL_ROOT>/scripts/game_project.py" --target "<TARGET>" --config "<CONFIG>" --mode migrate --profile standard
```

stdout 마지막 JSON에서 `ok: true`를 확인한다.

공통 생성·설치:

- `raw/`, `wiki/`, `Output/`
- `.agents/skills/`, `.claude/skills/`
- `.session-memory/`
- `templates/`
- `.llm-wiki.json`
- base skills: ingest/query/lint/session-memory/brief-tuner/wiki-audit

Evidence 추가:

- canon-review
- claims/decisions/canon/conflicts/experiments/questions/.wiki-cache
- `instructions/evidence-kb.md`, `tools/kb.py`, Source/Decision templates

Game 추가:

- `wiki/game/`의 feature/system/level/content/narrative/ui-ux/technical/implementation/assets/playtests/builds/bugs/decisions/proposals/milestones/releases
- `raw/game/`의 design/playtests/builds/telemetry/references — 불변 증거용
- `templates/game/`
- `instructions/game-project.md`
- `game-project` skill과 router marker
- manifest의 `project_mode: game`, `project_mode_version`, `game_project` metadata

# 6. Upgrade — GitHub 최신 커밋이 정본

## Knowledge mode

```bash
python "<SKILL_ROOT>/scripts/upgrade.py" --target "<TARGET>" --config "<CONFIG>"
```

profile 전환을 함께 요청한 경우:

```bash
python "<SKILL_ROOT>/scripts/upgrade.py" --target "<TARGET>" --config "<CONFIG>" --profile evidence
```

## Game mode 또는 기존 Wiki에 Game mode 추가

```bash
python "<SKILL_ROOT>/scripts/game_project.py" --target "<TARGET>" --config "<CONFIG>" --mode upgrade
```

Evidence로 승격하면서 Game mode를 추가·갱신할 때:

```bash
python "<SKILL_ROOT>/scripts/game_project.py" --target "<TARGET>" --config "<CONFIG>" --mode upgrade --profile evidence
```

Game mode Wiki의 최신화에 base `upgrade.py`만 사용하지 않는다. base assets는 갱신되더라도 game overlay의 skill·templates·contract 문서는 갱신되지 않을 수 있다. `game_project.py --mode upgrade`가 base upgrade와 game overlay upgrade를 함께 수행한다.

## GitHub latest 계약

1. 저장소 메타데이터에서 현재 default branch를 읽는다.
2. 그 branch의 최신 40자 commit SHA를 조회한다.
3. branch 이름이 아니라 검증한 정확한 SHA의 ZIP을 받는다.
4. archive path traversal을 차단하고 base 계약 파일을 검증한다.
5. Game upgrade이면 game wrapper·docs·templates·skill까지 target 변경 전에 추가 검증한다.
6. 여기까지 성공하기 전에는 대상 Wiki를 건드리지 않는다.
7. 다운로드한 checkout의 local apply primitive를 실행한다.
8. 기존 관리 스킬은 `.wiki-upgrade-bak/<timestamp>/`에 백업한다.
9. 성공 결과와 `.llm-wiki.json.last_upgrade`에 repository/branch/exact commit을 남긴다.

즉 upgrade의 의미는:

> **현재 로컬 bundle 재복사가 아니라, GitHub 공식 저장소 기본 브랜치의 현재 최신 commit을 고정해 그 버전의 upgrade logic과 bundled assets를 적용한다.**

## GitHub 실패 시

네트워크, API, ZIP, checkout 검증 중 하나라도 실패하면:

- 대상 Wiki를 수정하지 않는다.
- 실패 이유를 그대로 보고한다.
- 로컬 bundle로 자동 fallback하지 않는다.
- 공식 HEAD가 현재 계약보다 오래돼 검증이 실패하면 upstream publication이 필요하다고 보고한다.

## 명시적 offline/local 경로

Knowledge:

```bash
python "<SKILL_ROOT>/scripts/upgrade.py" --target "<TARGET>" --config "<CONFIG>" --source local
```

Game:

```bash
python "<SKILL_ROOT>/scripts/game_project.py" --target "<TARGET>" --config "<CONFIG>" --mode upgrade --source local
```

이 결과는 `upgrade_source: local`이며 “GitHub 최신”이라고 부르지 않는다.

## Local apply primitive 직접 오용 금지

사용자 의도의 “최신 upgrade”에 `bootstrap.py --mode upgrade`를 직접 사용하지 않는다. 다운로드된 정확한 checkout 내부에서 실제 적용할 때만 쓰는 low-level primitive다.

# 7. Migrate 규칙

- 기존 파일 삭제·수정 금지
- 루트 문서 충돌은 `.wiki-proposed`
- templates, skills, session runtime, Output 문서 충돌도 원본 유지 + `.wiki-proposed`
- 기존 일반 자료를 raw로 옮기려면 파일별 원래 경로와 목적지를 표로 제시하고 사용자 승인 후 이동
- `.git`, 코드 저장소, 엔진 프로젝트 설정, 원본 에셋 폴더를 raw로 옮기지 않음
- Game mode에서 `Source/`, `Assets/`, `Content/`, `Packages/`, `addons/`, 엔진 프로젝트 파일 등 live source는 제자리에 둠
- 이동 뒤 ingest batch 처리
- router proposal이 생기면 검토 전에는 activation pending으로 보고

# 8. Evidence 운영 계약

Evidence profile이면 `wiki/evidence-model.md`, `instructions/evidence-operations.md`, `instructions/evidence-kb.md`를 필독한다.

## Ingest

```text
Raw → Source Record → atomic Claim → support/contradiction → Conflict/Experiment/Open Question
Raw → Source Record → Project Decision → next action/chronology/supersedes
```

Canon 자동 수정 금지.

- `structurally_verified`와 `semantic_status: pending|partial|reviewed`를 분리한다.
- 긴 Source는 start/middle/EOF coverage와 실제 locator 인용이 필요하다.
- 대화의 최종 결정·다음 행동·대체 이력은 Claim이 아니라 Decision 계약으로 보존한다.
- Claim/Decision evidence는 Source ID, locator, excerpt를 가져야 하며 Raw와 직접 대조한다.
- 코드 원문에도 line/EOF coverage를 적용한다.
- outgoing link와 deterministic stitch edge는 semantic completion 증거가 아니다.

Claim 상태:

`OBSERVED`, `INFERRED`, `HYPOTHESIS`, `SUPPORTED`, `CONFIRMED`, `REJECTED`, `DISPUTED`, `DEPRECATED`, `UNKNOWN`

같은 정보 계보에서 나온 여러 LLM 답변을 독립 evidence로 중복 계산하지 않는다. `parent_sources` 또는 동등 provenance를 기록한다.

Query mode:

`answer`, `research`, `verify`, `challenge`, `trace`, `compare`

Lint는 source 없는 Claim, broken provenance, lineage cycle, 근거 없는 CONFIRMED, REJECTED Claim을 사용하는 Canon, unresolved conflict, orphan experiment 등을 확인한다.

`canon-review`는 기본 읽기 전용 recommendation이다. 명시적 승격·상태 변경 요청 없이는 Canon을 수정하지 않는다.

# 9. Game 운영 계약

Game mode이면 `wiki/game/model.md`, `instructions/game-project.md`, 설치된 `game-project` 스킬을 필독한다.

## 독립 상태

- `design_status`: `idea | proposed | accepted | superseded | rejected`
- `implementation_status`: `unknown | not_started | in_progress | implemented | blocked`
- `validation_status`: `untested | partial | passed | failed`
- `decision_status`: `proposed | accepted | rejected | superseded`
- `production_status`: `backlog | ready | in_progress | blocked | done`

각 상태는 직접 근거가 있을 때만 갱신한다.

## Live source 경계

- 코드·씬·데이터·원본 에셋은 live project에서 읽고 수정한다.
- 구현 확인에는 가능한 한 path, symbol, scene, data key, revision/build ID를 남긴다.
- `raw/game/`에는 플레이테스트 원본, 로그, telemetry export, 외부 분석, 승인 스냅샷 같은 불변 증거만 둔다.

## Operation

- `define` — 기능·시스템·레벨·콘텐츠·UI·에셋 의도 정의
- `plan` — 마일스톤·의존성·리스크·출구 조건
- `implement` — live source 실제 변경
- `inspect` — spec 대비 실제 구현 확인
- `playtest` — 검증 질문·관찰·해석·후속 분리
- `build` — exact revision/build/platform과 스모크 결과
- `decide` — 옵션·기준·근거·부작용·supersedes
- `release` — 계획 범위와 실제 포함 범위 고정

새 문서는 `wiki/game/index.md`에 연결한다. 사용자가 승인하지 않은 설계 선택은 `proposed`로 둔다.

## Evidence + Game

- 플레이테스트·로그·텔레메트리·외부 분석을 Raw/Source로 추적
- 경험적 일반화를 Claim으로 분리
- 반례를 conflict/contradiction으로 보존
- 재검증을 Experiment로 연결
- game 문서의 `evidence_refs`에서 Source/Claim/Experiment/Decision 연결
- “현재 채택된 설계”와 “경험적으로 확인된 사실”을 같은 것으로 취급하지 않음

# 10. Graphify

Graphify는 선택적 탐색·시각화 보조다. truth database가 아니다.

- Codex: `$graphify <WIKI_ROOT>` / `$graphify <WIKI_ROOT> --update`
- Claude: `/graphify <WIKI_ROOT>` / `/graphify <WIKI_ROOT> --update`
- Python subprocess에서 bare `graphify <path>`를 직접 호출하지 않는다.
- 실행 뒤 `ingest_runtime.py record-graphify-run --host codex|claude`
- batch 완료는 필요 시 `verify --complete-batch --require-graph`

Game mode에서도 Graphify는 spec·live source·test evidence를 대체하지 않는다.

# 11. Smoke check

공통:

```bash
python ".claude/skills/ingest/scripts/ingest_runtime.py" status
python ".session-memory/scripts/session_memory.py" status
```

Evidence:

```bash
python -m unittest discover ".agents/skills/ingest/tests" -p "test_*.py"
python -m unittest discover ".agents/skills/lint/tests" -p "test_*.py"
python -m unittest discover ".agents/skills/query/tests" -p "test_*.py"
python "tools/kb.py" selftest
```

확인:

- 올바른 root
- `wiki/index.md`, `CLAUDE.md`, `raw/CLAUDE.md`, `.llm-wiki.json`
- placeholder 미잔존
- Evidence면 evidence docs/runtime/templates/canon-review와 profile verification
- Game이면 `project_mode: game`, `wiki/game/index.md`, `wiki/game/model.md`, `instructions/game-project.md`, 양 host의 game-project skill, templates/game, router marker
- Game migrate/upgrade의 `.wiki-proposed`와 `project_mode_activation_pending`
- upgrade의 `upgrade_source`, `bootstrap_commit`, `backup_dir`
- GitHub upgrade 결과 SHA와 manifest `last_upgrade.commit` 일치
- 기존 Raw를 대표하는 긴 Source에서 coverage·locator·query trace가 실제로 동작

실패를 숨기지 않는다.

# 12. 마무리 보고

1. lifecycle mode / vault profile / project mode
2. upgrade source가 `github`인지 `local`인지
3. GitHub이면 repository/default branch/exact commit SHA
4. backup 위치
5. 설치·갱신 스킬과 mode assets
6. `.wiki-proposed`, profile/project-mode activation pending
7. smoke/verification 결과
8. Game이면 live source를 이동하지 않았는지와 game metadata
9. 다음 단계 (`raw/` ingest, router proposal 검토, game index/spec 작성, `SAVE`, canon-review 등)

GitHub 최신을 기대한 upgrade에 `bootstrap_commit`을 보고하지 못했다면 완료라고 말하지 않는다.
