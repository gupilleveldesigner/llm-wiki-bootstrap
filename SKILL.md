---
name: llm-wiki-bootstrap
description: LLM Wiki를 신규 구축(new), 기존 일반 폴더에서 비파괴 전환(migrate), 또는 GitHub 공식 저장소 최신 exact commit 기준으로 업그레이드(upgrade)한다. 지식관리 profile은 standard/evidence, 프로젝트 운영 mode는 knowledge/game으로 분리한다. Evidence는 Raw→Source→Claim/Project Decision→Evidence/Conflict/Experiment→reviewed Canon을 제공한다. Game mode는 실제 엔진 프로젝트와 Wiki를 project_root/vault_root로 분리하고, engine-aware sidecar 설치, dry-run write plan, protected paths, staging·rollback, managed-files manifest, 기획↔코드 traceability를 제공한다. 사용자가 LLM Wiki, 세컨드브레인, Evidence Wiki, 기존 폴더 전환, Wiki 최신화, 게임 프로젝트용 기획·구현·검증 지식베이스 구축을 요청할 때 사용한다. 설치 후 일상 ingest/query/lint/canon-review/game-project 작업에는 프로젝트 로컬 스킬을 사용한다.
---

# LLM Wiki Bootstrap

Claude Code / Codex가 운영하는 LLM Wiki를 구축·전환·업그레이드한다.

서로 다른 세 축을 섞지 않는다.

```text
lifecycle mode: new | migrate | upgrade
vault profile:  standard | evidence
project mode:   knowledge | game
```

예:

```text
new + standard + knowledge
migrate + evidence + knowledge
migrate + standard + game
upgrade + evidence + game
```

## 절대 규칙

1. `raw/`는 불변이다. 기존 Raw를 수정·삭제하지 않는다.
2. `migrate`는 기존 파일을 임의로 이동하지 않는다. 이동이 필요하면 파일별 계획과 승인을 먼저 받는다.
3. Game mode의 엔진 프로젝트·코드·씬·데이터·원본 에셋은 Raw가 아니다.
4. Game mode 설치·업그레이드는 기본적으로 **vault-only write policy**를 사용한다.
5. Game mode의 기본 배치는 project root 옆의 sidecar vault다. 엔진 프로젝트 루트에 Wiki 폴더를 흩어 놓지 않는다.
6. Game mode 적용 전 engine adapter, protected paths, 충돌, symlink, root 중첩을 포함한 dry-run write plan을 확인한다.
7. `upgrade`는 GitHub 공식 저장소의 현재 default branch HEAD를 조회하고 exact 40자 commit SHA를 고정한다.
8. GitHub 조회·다운로드·checkout 검증 실패 시 대상 Wiki를 수정하지 않는다. 오래된 local bundle로 자동 fallback하지 않는다.
9. local/offline bundle은 사용자가 명시한 `--source local`에서만 쓴다.
10. 기존 관리 스킬과 runtime은 upgrade 전 백업한다.
11. `.wiki-proposed`가 생기면 사용자 문서를 덮어쓰지 않고 검토한다.
12. Evidence Claim은 자동 Canon 승격하지 않는다.
13. Game의 design, implementation, validation, decision, production 상태를 하나로 합치지 않는다.
14. 실행하지 않은 검증을 성공으로 보고하지 않는다.
15. staging 또는 post-apply 검증이 실패하면 완료라고 말하지 않는다.

## 전제 조건

- Python 3.10+
- Claude Code 또는 Codex
- 온라인 upgrade에는 GitHub HTTPS 접근
- Game trace의 Git revision/stale 판정에는 Git 저장소 권장
- Graphify는 선택 사항이며 truth database가 아니다.

Python 실행기는 `python` → `py -3` → `python3` 순으로 찾고, Windows Microsoft Store stub은 실제 Python으로 취급하지 않는다.

# 1. Lifecycle mode

| 대상 | 의도 | mode |
|---|---|---|
| 비어 있거나 없음 | 새 Wiki | `new` |
| 기존 자료 폴더지만 Wiki marker 없음 | 비파괴 Wiki 전환 | `migrate` |
| 기존 `.llm-wiki.json` 또는 `raw/` + `wiki/` | 최신화·profile 승격·Game 갱신 | `upgrade` |

기존 Wiki에 “새로 만들어줘”가 와도 파괴적 재생성을 하지 않고 `upgrade`를 우선 설명한다.

Game mode에서 lifecycle은 **vault root 상태**를 기준으로 적용한다. Sidecar vault가 없고 live project만 존재한다면 사용자 의도는 migrate여도 base vault 생성은 `new`로 수행할 수 있다. live project는 이동·수정하지 않는다.

# 2. Vault profile

## standard

일반 공부, 자료 정리, 프로젝트 메모, 기사·영상·책 요약에 사용한다.

```text
raw → wiki → Output
```

## evidence

다음 신호가 핵심이면 사용한다.

- 역공학·숨겨진 구현 추정
- 여러 LLM 분석 누적
- 관찰과 추론·가설 분리
- source lineage와 provenance 필요
- conflicting/rejected claim 보존
- hypothesis → experiment → conclusion
- 결론을 원문 locator까지 trace

```text
Raw → Source → Claim 또는 Project Decision
    → Evidence/Conflict/Experiment → reviewed Canon
```

핵심 원칙:

> **“LLM이 말했다”와 “우리가 확인했다”를 같은 것으로 취급하지 않는다.**

Upgrade에서 profile을 생략하면 기존 `.llm-wiki.json` profile을 보존한다. manifest 없는 legacy Wiki는 standard로 본다. Evidence → Standard 자동 downgrade는 금지한다.

# 3. Project mode

## knowledge

일반 LLM Wiki다. `scripts/bootstrap.py`와 `scripts/upgrade.py`를 사용한다.

## game

다음 의도가 있으면 사용한다.

- 실제 Unity·Unreal·Godot·웹 게임 프로젝트와 함께 쓰는 Wiki
- 기능·시스템·레벨·콘텐츠·내러티브·UI/UX·기술·에셋 명세
- 기획과 코드·씬·데이터·에셋의 대응 관계 추적
- 빌드·플레이테스트·버그·결정·마일스톤·릴리스 기록
- 코드 diff가 어떤 기획에 영향을 주는지 분석
- “기획됨 / 구현됨 / 검증됨 / 채택됨 / 작업완료” 분리

핵심 추적선:

```text
Design Intent → Implementation State → Validation Evidence → Project Decision
```

Game mode는 profile을 대체하지 않는다.

```text
standard + game
evidence + game
```

Game → knowledge 자동 제거는 제공하지 않는다. Game 기록과 router를 없애는 작업은 별도 migration이다.

# 4. 짧은 인터뷰와 config

이미 받은 정보는 다시 묻지 않는다. 빠진 항목만 한 번에 묻는다.

공통:

1. Wiki 주제와 목적
2. 주요 자료 유형
3. 프로젝트 이름

Game에서 필요하면:

- 정확한 live project root
- 게임 제목·엔진·장르·플랫폼·제작 단계
- source roots
- sidecar/embedded/custom 배치 선호

모르면 `UNKNOWN` 또는 빈 목록으로 시작한다. 엔진 표지를 근거 없이 추정하지 않는다.

기본 config:

```json
{
  "project_name": "My Wiki",
  "domain_summary": "프로젝트 목적 한 문장"
}
```

Game config:

```json
{
  "project_name": "My Game Wiki",
  "domain_summary": "기획과 실제 구현·검증을 연결한다",
  "project_root": "../MyGame",
  "layout": "sidecar",
  "engine": "auto",
  "game_title": "My Game",
  "game_engine": "Godot 4",
  "game_genre": "2D action puzzle",
  "target_platforms": "Windows, Web",
  "project_phase": "prototype",
  "source_roots": ["scenes/", "scripts/", "assets/"]
}
```

# 5. Knowledge mode new / migrate

Standard:

```bash
python "<SKILL_ROOT>/scripts/bootstrap.py" \
  --target "<VAULT_ROOT>" \
  --config "<CONFIG>" \
  --mode new \
  --profile standard
```

Evidence:

```bash
python "<SKILL_ROOT>/scripts/bootstrap.py" \
  --target "<VAULT_ROOT>" \
  --config "<CONFIG>" \
  --mode new \
  --profile evidence
```

기존 일반 폴더는 `--mode migrate`를 사용한다.

# 6. Game mode layout safety

Game mode는 두 정본 루트를 분리한다.

```text
project_root
  live engine project와 implementation source of truth

vault_root
  Wiki, specs, implementation checks, tests, decisions, skills, trace index
```

## 기본 sidecar

```text
Workspace/
├─ MyGame/        # project_root
└─ MyGame.wiki/   # vault_root
```

`--vault-root`를 생략하면 sidecar를 선택한다.

## embedded

```text
MyGame/.llm-wiki/
```

`--layout embedded`에서만 사용한다. Godot에는 `.gdignore`를 설치한다.

## custom

프로젝트 밖 별도 경로를 `--vault-root`로 지정한다.

## legacy-in-place

`project_root == vault_root`인 과거 구조다. 기본 거부하며 `--layout legacy-in-place --allow-legacy-in-place`가 모두 필요하다.

## engine adapters

- Unity: `Assets`, `Packages`, `ProjectSettings` 보호
- Unreal: `.uproject`, `Content`, `Config`, `Source`, `Plugins` 보호
- Godot: `project.godot`과 기존 최상위 프로젝트 항목 보호, `.godot`/`.import` 생성 경로
- Web: `package.json`, `src`, `app`, `pages`, `public`, 주요 config 보호
- Generic: 기존 최상위 항목과 사용자가 지정한 source roots를 기준으로 보수적으로 처리

선택 root 아래 여러 엔진 프로젝트가 있으면 workspace로 판정하고 적용을 거부한다.

# 7. Game mode dry-run, staging, apply

실제 적용 전 dry-run을 우선한다.

```bash
python "<SKILL_ROOT>/scripts/game_project.py" \
  --project-root "<PROJECT_ROOT>" \
  --config "<CONFIG>" \
  --mode migrate \
  --profile standard \
  --dry-run
```

Dry-run은 transaction staging에서 실제 설치와 검증을 수행하지만 최종 vault를 만들거나 바꾸지 않는다.

확인 항목:

```text
write_plan.safe_to_apply
collisions
protected_path_writes
symlink_violations
layout_errors
writes.creates / updates / deletes
mutation_started: false
```

다음이 있으면 적용하지 않는다.

- 모호한 engine/project root
- protected path write
- unmanaged file overwrite
- 사용자 편집 관리 문서 direct overwrite
- delete 계획
- 기존 vault symlink 또는 vault 밖 symlink write. Staging은 symlink를 따라가지 않음
- 위험한 root 중첩
- 검토하지 않은 foreign non-Wiki vault

기존 비-Wiki 폴더를 의도적으로 vault로 채택할 때만 dry-run 검토 후 `--adopt-existing-vault`를 사용한다.

안전하면 `--dry-run`을 제거한다.

```bash
python "<SKILL_ROOT>/scripts/game_project.py" \
  --project-root "<PROJECT_ROOT>" \
  --config "<CONFIG>" \
  --mode migrate \
  --profile standard
```

적용 계약:

1. 기존 vault를 transaction staging에 복사
2. base Wiki와 Game overlay를 staging에서 생성·업그레이드
3. profile/runtime/trace 검증
4. `.llm-wiki-managed.json`과 write plan 생성
5. 같은 파일시스템 rename으로 vault 교체
6. 기존 vault rollback backup 유지
7. 적용 후 managed files, trace, Game contract, project integrity 재검증
8. 실패 시 이전 vault 자동 복구

기본 integrity는 `metadata`; 강한 검증은 `--integrity full`이다.

# 8. Game mode upgrade

Game mode 또는 Game 추가 upgrade:

```bash
python "<SKILL_ROOT>/scripts/game_project.py" \
  --project-root "<PROJECT_ROOT>" \
  --vault-root "<VAULT_ROOT>" \
  --config "<CONFIG>" \
  --mode upgrade
```

Evidence 승격:

```bash
python "<SKILL_ROOT>/scripts/game_project.py" \
  --project-root "<PROJECT_ROOT>" \
  --vault-root "<VAULT_ROOT>" \
  --config "<CONFIG>" \
  --mode upgrade \
  --profile evidence
```

명시적 local/offline:

```bash
python "<SKILL_ROOT>/scripts/game_project.py" \
  --project-root "<PROJECT_ROOT>" \
  --vault-root "<VAULT_ROOT>" \
  --config "<CONFIG>" \
  --mode upgrade \
  --source local
```

Game mode Wiki에 base `upgrade.py`만 사용하지 않는다. `game_project.py --mode upgrade`가 base Wiki, Game overlay, layout safety, managed manifest, trace runtime을 같은 exact checkout에서 함께 갱신한다.

## GitHub latest 계약

1. 저장소 metadata에서 현재 default branch 확인
2. 최신 40자 commit SHA 확인
3. exact SHA archive 다운로드
4. archive path traversal과 base 계약 검증
5. Game wrapper, workspace safety runtime, docs, templates, skills, trace runtime 추가 검증
6. 여기까지 성공 전에는 대상 vault에 최종 mutation 없음
7. 다운로드된 checkout의 local apply를 staging에서 실행
8. exact repository/branch/commit provenance 기록

실패 시 local fallback하지 않는다.

# 9. Game traceability와 dual baseline

기획 정본은 vault, 구현 정본은 project root다. 구현 확인 문서에서 실제 대조가 끝난 뒤 다음 명령으로 양쪽 기준점을 확정한다.

```bash
python tools/game_trace.py accept wiki/game/implementation/<CHECK>.md
```

기준점:

```text
canonical spec digest
checked path별 code fingerprint
project revision
독립 vault revision(있는 경우)
```

상태:

```text
in_sync
design_changed
code_changed
both_changed
unverified
missing
```

```bash
python tools/game_trace.py scan
python tools/game_trace.py status
python tools/game_trace.py proposals
python tools/game_trace.py verify
python tools/game_trace.py verify --strict-sync
python tools/game_trace.py spec <SPEC-ID>
python tools/game_trace.py path <path#symbol>
python tools/game_trace.py affected --base <REV> --head <REV>
python tools/game_trace.py matrix
```

변경 감지는 자동으로 어느 한쪽을 정본으로 승격하지 않는다. inspect, proposal/decision, 새 implementation check, 명시적 accept가 필요하다.

## Game-aware ingest

Game mode v5는 공용 ingest engine과 vault-local Game adapter를 결합한다.

```text
shared ingest: Raw scan → Source/SHA/semantic review → Graphify → ledger
Game adapter:  sidecar context → typed Game validation → trace scan/status/verify
```

- 일반 `/ingest`는 manifest의 `ingest.adapter: game`을 읽어 자동 라우팅한다.
- `/game-ingest`는 같은 engine의 명시적 UX다.
- `raw/game/design|playtests|builds|telemetry|references`를 유형별로 라우팅한다.
- Game 문서는 `topics/tags` 대신 안정된 Game ID와 `raw_refs/evidence_refs`를 검증한다.
- ledger v3는 Source ID, 반영된 Game ID, subject refs, sync counts를 기록한다.
- ingest는 `game_trace accept`를 자동 실행하지 않는다.

필독:

```text
instructions/game-ingest.md
.agents/skills/game-ingest/SKILL.md
```

# 10. Game 운영 계약

필독:

```text
wiki/game/index.md
wiki/game/model.md
instructions/game-project.md
instructions/game-engine-layouts.md
instructions/game-ingest.md
.agents/skills/game-project/SKILL.md
.agents/skills/game-ingest/SKILL.md
```

독립 상태:

```text
design_status:         idea | proposed | accepted | superseded | rejected
implementation_status: unknown | not_started | in_progress | implemented | blocked
validation_status:     untested | partial | passed | failed
decision_status:       proposed | accepted | rejected | superseded
production_status:     backlog | ready | in_progress | blocked | done
```

Operations:

- `define`
- `plan`
- `implement` — 명시적 요청에서만 project root 변경
- `inspect`
- `trace`
- `impact`
- `game-ingest` — 공용 ingest engine + Game adapter
- `playtest`
- `build`
- `decide`
- `bug`
- `release`

기획·implementation check·build·playtest·decision 변경 뒤 `game_trace.py scan`, `status`, `verify`를 실행한다. 완료·릴리스에는 `verify --strict-sync`를 사용한다. Raw 게임 자료 반영은 `/ingest` 자동 라우팅 또는 `/game-ingest`를 사용한다.

# 11. Evidence 운영 계약

Evidence이면 다음을 필독한다.

```text
wiki/evidence-model.md
instructions/evidence-operations.md
instructions/evidence-kb.md
tools/kb.py
```

Ingest:

```text
Raw → Source Record → atomic Claim → support/contradiction
Raw → Source Record → Project Decision → chronology/supersedes
```

- `structurally_verified`와 `semantic_status` 분리
- 긴 Source는 start/middle/EOF coverage와 실제 locator 필요
- Decision evidence와 next action에도 Source ID, locator, excerpt 필요
- 같은 lineage LLM 답변을 독립 evidence로 중복 계산하지 않음
- Canon 자동 수정 금지

Claim 상태:

```text
OBSERVED INFERRED HYPOTHESIS SUPPORTED CONFIRMED
REJECTED DISPUTED DEPRECATED UNKNOWN
```

Query mode:

```text
answer research verify challenge trace compare
```

`canon-review`는 기본 읽기 전용 recommendation이다.

# 12. Managed files와 사용자 문서

Game sidecar의 `.llm-wiki-managed.json`은 관리 파일 hash와 정책을 기록한다.

```text
system-managed
metadata
managed-proposal
seeded-user-editable
derived
```

업그레이드는 사용자 편집 문서와 system runtime을 구분한다. 사용자 편집 관리 문서를 직접 바꿔야 하면 `.wiki-proposed` 또는 collision으로 처리한다. 기존 파일 삭제를 자동 계획하지 않는다.

# 13. Smoke checks

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

Game:

```bash
python "tools/game_trace.py" verify
```

확인:

- 올바른 project root / vault root / layout / engine adapter
- sidecar 또는 isolated embedded placement
- dry-run plan에 protected writes, symlink violations, collisions, deletes 없음
- `.llm-wiki.json`, `.llm-wiki-managed.json`
- `wiki/game/index.md`, `model.md`, `traceability.json`
- `instructions/game-project.md`, `game-engine-layouts.md`
- 양 host의 `game-project` skill
- installed runtime과 trace verification
- project integrity unchanged
- upgrade exact commit provenance
- `.wiki-proposed`와 activation pending

# 14. 마무리 보고

1. lifecycle / profile / project mode
2. project root / vault root / layout / engine adapter
3. dry-run 또는 apply write plan 요약
4. protected path writes, collisions, symlink violations, deletes 여부
5. mutation_started와 rollback backup
6. project integrity 결과
7. 설치·갱신 skill/runtime/docs
8. traceability rebuild/verify 결과
9. `.wiki-proposed`와 activation pending
10. upgrade source와 exact commit
11. 다음 실제 행동

GitHub 최신 upgrade에서 `bootstrap_commit`을 보고하지 못했거나, Game apply에서 `safe_to_apply`, post-apply verification, project integrity를 확인하지 못했다면 완료라고 말하지 않는다.
