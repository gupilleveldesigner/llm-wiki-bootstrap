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

## 빠른 경로

대부분의 요청은 질문 없이 끝난다. 사용자가 말하지 않은 값은 아래 기본값으로 정하고, 정한 값을 결과 보고에 적는다.

| 정할 것 | 기본값 |
|---|---|
| lifecycle | 대상 폴더 상태로 판정한다 (§1 표). 비어 있으면 `new`, 일반 폴더면 `migrate`, 기존 Wiki면 `upgrade` |
| profile | `standard`. §2의 Evidence 신호가 요청에 있을 때만 `evidence` |
| project mode | `knowledge`. 실제 게임·엔진 프로젝트와 함께 쓰려는 요청일 때만 `game` |
| 이름 | 대상 폴더 이름 (`--project-name` 생략) |
| 목적 한 문장 | 사용자가 한 말에서 뽑는다. 없으면 생략한다 |

1. 위 표로 세 축을 정한다. 대상 경로를 모를 때만 묻는다.
2. 해당 명령 하나를 실행한다 (§5, Game은 §7·§8). **설정 JSON 파일을 만들거나 사용자에게 만들게 하지 않는다.** 값은 전부 플래그로 넘긴다.
3. Graphify를 자동 설치한다 (§5.2). 사용자에게 설치 명령을 넘기지 않는다.
4. 설치 직후 문서를 채운다 (§5.3).
5. Smoke check (§13) 뒤 결과와 "다음 할 일" 세 줄을 보고한다 (§14).

Game이 아니면 §6~§10과 §12는 읽지 않아도 된다. Evidence가 아니면 §11은 읽지 않아도 된다.

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
16. Knowledge mode도 target 내부 symlink를 따라 쓰지 않는다. symlink가 있으면 적용 전 중단하고 경로를 보고한다.
17. Knowledge mode upgrade는 sibling transaction staging에서 검증한 뒤 적용하며 실패 시 원래 Wiki를 복원한다.
18. Knowledge mode upgrade 전 staging 복제본을 위한 같은 파일시스템 여유 공간을 확인한다.

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

# 4. 묻는 것과 넘기는 값

이미 받은 정보는 다시 묻지 않는다. 기본값으로 정할 수 있는 것은 묻지 않고, 꼭 필요한 것만 한 번에 묻는다.

- 꼭 필요한 것: 대상 경로. Game이면 정확한 live project root.
- 있으면 쓰는 것: Wiki 주제와 목적 한 문장, 주요 자료 유형, 프로젝트 이름. Game이면 게임 제목·엔진·장르·플랫폼·제작 단계, source roots, sidecar/embedded/custom 배치 선호.

모르는 값은 생략한다. 스크립트가 `UNKNOWN`이나 빈 목록으로 시작한다. 엔진 표지를 근거 없이 추정하지 않는다.

값은 플래그로 넘긴다. 사용자가 JSON 파일을 쓰거나 고치는 단계는 없다.

| 플래그 | 뜻 | 생략 시 |
|---|---|---|
| `--project-name` | Wiki 이름 | 대상 폴더 이름 (Game은 `<프로젝트 폴더> Wiki`) |
| `--domain-summary` | 목적 한 문장 | 이름과 같게 |
| `--game-title`, `--game-engine`, `--game-genre`, `--target-platforms`, `--project-phase` | Game 문서에 들어갈 설명 | 제목은 이름, 나머지는 `UNKNOWN`·`prototype` |
| `--source-root` (반복) | 프로젝트 기준 소스 폴더 | 엔진 adapter 기본값. upgrade는 기록된 값 유지 |
| `--knowledge-graph graphify\|none` | WHAT 질문용 선택 provider | 새 설치는 비활성, upgrade는 기존 선택 유지 |
| `--code-intelligence codegraph\|none` | HOW 질문용 선택 provider | 위와 같음 |

`--config <파일>`은 예전 설정 파일을 가진 사용자를 위해 계속 받는다. 같이 주면 플래그가 이긴다. 새로 만들라고 안내하지 않는다.

# 5. Knowledge mode

## 5.1 new / migrate / upgrade

새 Wiki:

```bash
python "<SKILL_ROOT>/scripts/bootstrap.py" \
  --target "<VAULT_ROOT>" \
  --domain-summary "<목적 한 문장>" \
  --mode new \
  --profile standard
```

Evidence는 `--profile evidence`, 기존 일반 폴더는 `--mode migrate`를 쓴다.

`new`와 `migrate` 모두 적용 전에 target 및 하위 symlink를 검사한다. 하나라도 발견되면 vault 밖 쓰기 가능성을 막기 위해 중단하고 사용자가 실제 파일/폴더로 정리하도록 안내한다.

기존 Wiki 최신화:

```bash
python "<SKILL_ROOT>/scripts/upgrade.py" --target "<VAULT_ROOT>"
```

이름과 profile은 Wiki의 manifest에서 읽으므로 다른 인자가 필요 없다. Evidence로 승격할 때만 `--profile evidence`, 사용자가 오프라인 bundle을 명시했을 때만 `--source local`을 붙인다. Game mode Wiki는 이 명령이 아니라 §8을 쓴다.

## 5.2 Graphify 자동 설치

설치·전환·업그레이드가 성공하면 이어서 실행한다. 사용자에게 묻거나 명령을 넘기지 않는다.

```bash
python "<VAULT_ROOT>/.agents/skills/ingest/scripts/ingest_runtime.py" ensure-graphify
```

- Graphify CLI가 없으면 `uv tool install graphifyy` → `pipx install graphifyy` → `python -m pip install graphifyy` 순으로 시도하고, 홈 디렉터리가 있는 호스트(Claude, Codex)에 Graphify 스킬을 등록한다. 이미 있으면 아무것도 하지 않는다.
- 결과의 `status`가 `installed` 또는 `ready`면 끝이다. 새로 등록된 호스트 스킬은 그 호스트의 다음 세션부터 보인다는 점을 보고에 적는다.
- `failed`(네트워크 차단, Python 3.11 미만 등)여도 Wiki 설치는 유효하다. 실패 사유와 함께 "그래프 없이 시작, 단일 소스 인제스트는 가능"이라고 보고하고 넘어간다. 설치를 완료로 꾸미지 않는다.
- 그래프 생성은 여기서 하지 않는다. 첫 배치 인제스트에서 호스트 스킬(`/graphify`, `$graphify`)이 만든다.

**CodeGraph는 자동 설치하지 않는다(보류).** 플랫폼별 네이티브 바이너리와 호스트 MCP 설정 편집이 필요해서 Graphify처럼 한 번에 깔리지 않는다. 사용자가 직접 설치해 연결해 둔 경우에만 `--code-intelligence codegraph`로 선택한다.

## 5.3 설치 직후 채우기

`new`와 `migrate` 뒤에는 빈 틀을 사용자에게 넘기지 않는다.

1. `wiki/overview.md`와 `wiki/questions.md`의 `<!-- BOOTSTRAP:FILL … -->` 표시를 찾아, 사용자가 말한 주제·목적·자료 유형으로 내용을 채우고 표시를 지운다.
2. 사용자가 주제 분야를 말했으면 `wiki/taxonomy.json`에 그 분야의 상위 개념 몇 개를 넣는다. 형식은 파일 안의 기존 항목을 따른다.
3. 사용자가 말하지 않은 내용은 지어내지 않는다. 채울 근거가 없는 항목은 한 줄 안내만 남긴다.

`migrate`에서 `.wiki-proposed`가 생긴 문서는 덮어쓰지 않고 차이를 요약해 사용자가 고르게 한다.

## 5.4 Web Clipper는 선택 사항

자료를 넣는 기본 방법은 사용자가 URL이나 파일을 말하는 것이다. 설치된 `ingest` 스킬이 URL을 받아 `raw/reference/` 아래에 새 원문 파일로 저장하고 반영한다.

Obsidian Web Clipper를 쓰고 싶은 사용자에게만 `<VAULT_ROOT>/templates/web-clipper/`의 절대경로를 알려 준다. Clipper 설정의 Import에서 그 폴더의 파일 다섯 개를 한 번에 선택하면 된다. 브라우저 확장 저장소는 에이전트가 건드릴 수 없으므로 이 한 번의 가져오기만 사용자 몫이고, 쓰지 않아도 Wiki 기능은 같다.

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
  --game-title "<게임 제목>" \
  --knowledge-graph graphify \
  --mode migrate \
  --profile standard \
  --dry-run
```

아는 값만 플래그로 붙인다(§4 표). `--knowledge-graph graphify`는 새 Game 설치의 기본 선택이다. Graphify는 적용 뒤 자동 설치하며(§5.2), 설치에 실패해도 Game 완료 검사는 그래프 없이 통과한다. CodeGraph는 사용자가 이미 연결해 둔 경우에만 `--code-intelligence codegraph`를 붙인다.

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
  --game-title "<게임 제목>" \
  --knowledge-graph graphify \
  --mode migrate \
  --profile standard
```

Dry-run과 apply에는 같은 플래그를 준다. 적용이 끝나면 §5.2의 `ensure-graphify`를 실행하고, §5.3처럼 `wiki/game/`의 `overview.md`·`pillars.md`·`roadmap.md`를 사용자가 말한 내용으로 채운다.

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
  --mode upgrade
```

Evidence 승격:

```bash
python "<SKILL_ROOT>/scripts/game_project.py" \
  --project-root "<PROJECT_ROOT>" \
  --vault-root "<VAULT_ROOT>" \
  --mode upgrade \
  --profile evidence
```

명시적 local/offline:

```bash
python "<SKILL_ROOT>/scripts/game_project.py" \
  --project-root "<PROJECT_ROOT>" \
  --vault-root "<VAULT_ROOT>" \
  --mode upgrade \
  --source local
```

Upgrade는 이름·게임 정보·source roots·provider 선택을 manifest에서 이어받으므로 바꿀 값만 플래그로 준다. 선택을 해제할 때는 `--knowledge-graph none`처럼 명시한다. 적용 뒤 rollback backup이 `<프로젝트 옆>/.llm-wiki-transactions/` 아래에 남는다. 경로를 보고하고, 사용자가 필요 없다고 하면 지우거나 다음부터 `--discard-rollback-backup`을 쓴다.

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

Game mode v6는 공용 ingest engine과 vault-local Game adapter를 결합하며, v5의 trace/baseline 계약을 유지한다.

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

Game v6는 선택 provider를 추가한다. `--knowledge-graph graphify`, `--code-intelligence codegraph`
(또는 예전 config의 `providers.*`)를 manifest `game_project.providers`에 저장한다.
WHAT → Graphify / HOW → CodeGraph / WHY → Wiki를 따르며, 기존 config는 수정 없이
유효하다. 새 설치의 생략은 비활성화, upgrade의 생략은 기존 선택 유지, `none`(config의 null)은 해제다.
알 수 없는 provider ID는 실행하지 않는다. provider schema version은 1이다.

Graphify CLI와 호스트 스킬은 §5.2로 자동 설치한다. CodeGraph 자동 설치는 보류 상태이며
사용자가 직접 연결한 경우에만 선택한다.

설치된 `tools/game_providers.py status`와 `route`는 호스트 질의 요청안만 반환한다.
실제 도구 스키마와 connection_id·서버 기본 corpus를 확인하지 못하면 로컬 조회로 돌아간다.
이 planner 자체는 MCP 설치·시작·indexing·credential 탐색·graph 복제를 수행하지 않는다.
`instructions/game-providers.md`를 읽고, Game ingest의 graph 검사 생략과 명시적인
vault-local `verify --require-graph`를 구분한다. trace schema 2, baseline 1,
`live_paths`/`checked_paths` 형식과 수동 baseline 승인은 유지한다.

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

어느 디렉터리에서 실행해도 되도록 vault 절대경로를 넣는다.

공통:

```bash
python "<VAULT_ROOT>/.agents/skills/ingest/scripts/ingest_runtime.py" status --root "<VAULT_ROOT>"
python "<VAULT_ROOT>/.session-memory/scripts/session_memory.py" status --target "<VAULT_ROOT>"
python "<VAULT_ROOT>/.agents/skills/ingest/scripts/ingest_runtime.py" ensure-graphify --check
```

Evidence:

```bash
python -m unittest discover "<VAULT_ROOT>/.agents/skills/ingest/tests" -p "test_*.py"
python -m unittest discover "<VAULT_ROOT>/.agents/skills/lint/tests" -p "test_*.py"
python -m unittest discover "<VAULT_ROOT>/.agents/skills/query/tests" -p "test_*.py"
python "<VAULT_ROOT>/tools/kb.py" selftest
```

Game (vault를 작업 디렉터리로 두거나 `--vault-root`를 준다):

```bash
python "<VAULT_ROOT>/tools/game_trace.py" --vault-root "<VAULT_ROOT>" verify
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

사용자가 읽는 보고는 짧게, 실제로 실행해 확인한 것만 적는다.

Knowledge mode:

1. 만든(또는 갱신한) 위치와 lifecycle / profile, 기본값으로 정한 것
2. Graphify 상태 (`installed` / `ready` / `failed`와 사유)
3. 채운 문서와 사용자 확인이 필요한 `.wiki-proposed`
4. upgrade면 source와 exact commit
5. 다음 할 일 세 줄:
   - 자료를 `raw/inbox/`에 넣거나 URL을 말한다
   - "인제스트해줘"라고 한다
   - 세션을 마칠 때 "SAVE"라고 한다

Game mode는 위에 더해:

1. project root / vault root / layout / engine adapter
2. dry-run 또는 apply write plan 요약
3. protected path writes, collisions, symlink violations, deletes 여부
4. mutation_started와 rollback backup 위치
5. project integrity 결과
6. traceability scan/verify 결과
7. activation pending

GitHub 최신 upgrade에서 `bootstrap_commit`을 보고하지 못했거나, Game apply에서 `safe_to_apply`, post-apply verification, project integrity를 확인하지 못했다면 완료라고 말하지 않는다.
