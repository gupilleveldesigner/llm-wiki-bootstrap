---
name: llm-wiki-bootstrap
description: LLM Wiki 볼트를 신규 구축(new), 기존 일반 폴더에서 비파괴 전환(migrate), 또는 기존 Wiki를 GitHub의 gupilleveldesigner/llm-wiki-bootstrap 최신 기본 브랜치 커밋 기준으로 업그레이드(upgrade)한다. Vault profile은 standard/evidence로 분리한다. Evidence profile은 Raw→Source→Claim→Evidence/Conflict/Experiment→reviewed Canon 구조와 source lineage, epistemic state, canon-review를 추가한다. 사용자가 "LLM 위키 만들어줘", "세컨드브레인 구축", "이 폴더를 위키로 전환", "위키 최신버전으로 업그레이드", "스킬 최신화", "Evidence Wiki", "근거/가설/실험을 분리하는 연구 위키"를 말하거나 개인 지식관리/AI 연구 지식베이스를 새로 시작·전환·업그레이드하려는 의도를 보이면 사용한다. 기존 Wiki의 일상 ingest/query/lint/canon-review 작업에는 해당 설치 스킬을 사용한다.
---

# LLM Wiki Bootstrap

폴더를 Claude Code / Codex가 운영하는 LLM Wiki로 구축·전환·업그레이드한다.

핵심 축은 두 개다.

- lifecycle mode: `new` / `migrate` / `upgrade`
- vault profile: `standard` / `evidence`

둘을 섞지 않는다.

## 절대 규칙

1. `raw/`는 불변이다. 기존 Raw를 수정·삭제하지 않는다.
2. `migrate`는 기존 파일을 임의로 이동하지 않는다. 이동 계획을 제시하고 사용자 승인 후 수행한다.
3. `upgrade`는 **GitHub 공식 저장소의 최신 기본 브랜치 HEAD**를 먼저 조회한다.
4. `upgrade`는 GitHub 조회/다운로드/검증이 실패하면 대상 Wiki를 수정하지 않는다. 로컬 번들로 조용히 fallback하지 않는다.
5. 오프라인에서 로컬 번들을 쓰려면 사용자가 명시적으로 요청했을 때만 `--source local`을 사용한다.
6. 기존 운영 스킬은 교체 전에 `.wiki-upgrade-bak/<timestamp>/`에 백업한다.
7. Evidence의 Claim은 자동으로 Canon으로 승격하지 않는다.
8. `.wiki-proposed`가 생기면 기존 문서를 덮어쓰지 않고 차이를 검토한다.
9. 실패한 검증을 성공으로 보고하지 않는다.

## 전제 조건

- Python 3.10+
- Claude Code 또는 Codex
- 온라인 `upgrade`에는 GitHub HTTPS 접근 가능 환경
- Graphify는 선택 사항이지만 batch ingest의 기존 완료 계약이 Graphify를 요구하면 그 계약을 따른다.

Python 실행기는 `python` → `py -3` → `python3` 순으로 찾고, Windows Microsoft Store stub은 유효한 Python으로 취급하지 않는다.

# 1. Lifecycle mode 판정

| 대상 상태 | 사용자 의도 | mode |
|---|---|---|
| 비어 있거나 없음 | 새 Wiki | `new` |
| 파일은 있으나 Wiki marker 없음 | Wiki로 전환 | `migrate` |
| `raw/` + `wiki/` 등 기존 Wiki | 최신화/업그레이드 | `upgrade` |

기존 Wiki에 "새로 만들어줘"처럼 파괴 가능성이 있는 표현이 오면 덮어쓰지 말고 `upgrade`가 비파괴 경로임을 설명한다.

# 2. Vault profile 판정

사용자가 명시하면 그대로 사용한다.

## standard

일반 공부, 자료 정리, 세컨드브레인, 프로젝트 메모, 기사/영상/책 요약에 사용한다.

```text
raw → wiki → Output
```

## evidence

다음 신호가 핵심이면 Evidence profile을 선택한다.

- 역공학/숨겨진 구현 추정
- 여러 LLM 분석을 누적
- 관찰과 추론/가설을 분리
- provenance/source lineage 필요
- conflicting/rejected claim 보존
- hypothesis → experiment → conclusion 연구 루프
- 모든 결론을 원문까지 trace

```text
Raw → Source → Claim → Evidence/Conflict/Experiment → reviewed Canon
```

핵심 문장:

> **“LLM이 말했다”와 “우리가 확인했다”를 같은 것으로 취급하지 않는다.**

`upgrade`에서 profile을 생략하면 `.llm-wiki.json`의 기존 profile을 보존한다. manifest 없는 legacy Wiki는 `standard`로 본다. Evidence → Standard 자동 downgrade는 금지한다.

# 3. 짧은 인터뷰

이미 받은 정보는 다시 묻지 않는다. 빠진 항목만 최대 한 번에 묻는다.

1. Wiki 주제와 목적
2. 주로 모을 자료 유형
3. 프로젝트 이름

이 정보로 `project_name`, `domain_summary`, 초기 overview/questions/taxonomy를 만든다.

# 4. new / migrate 스캐폴드

config 예:

```json
{"project_name":"My Wiki","domain_summary":"프로젝트 목적 한 문장"}
```

Standard:

```bash
python "<SKILL_ROOT>/scripts/bootstrap.py" --target "<TARGET>" --config "<CONFIG>" --mode new --profile standard
```

Evidence:

```bash
python "<SKILL_ROOT>/scripts/bootstrap.py" --target "<TARGET>" --config "<CONFIG>" --mode new --profile evidence
```

migrate는 `--mode migrate`를 사용한다.

stdout 마지막 JSON에서 `ok: true`를 확인한다.

생성/설치:

- `raw/`, `wiki/`, `Output/`
- `.agents/skills/`, `.claude/skills/`
- `.session-memory/`
- `templates/`
- `.llm-wiki.json`
- base 스킬 6종: ingest/query/lint/session-memory/brief-tuner/wiki-audit
- Evidence면 canon-review와 claims/canon/conflicts/experiments/questions/.wiki-cache

# 5. upgrade — GitHub 최신 커밋이 정본

사용자가 기존 Wiki를 "업그레이드", "최신화", "스킬 업데이트"해 달라고 하면 **반드시 이 절차**를 사용한다.

## 기본 경로: GitHub latest

```bash
python "<SKILL_ROOT>/scripts/upgrade.py" --target "<TARGET>" --config "<CONFIG>"
```

profile 전환을 함께 요청한 경우:

```bash
python "<SKILL_ROOT>/scripts/upgrade.py" --target "<TARGET>" --config "<CONFIG>" --profile evidence
```

`upgrade.py`의 계약:

1. `gupilleveldesigner/llm-wiki-bootstrap` 저장소 메타데이터에서 **현재 default branch**를 읽는다.
2. 그 default branch의 최신 commit SHA를 조회한다.
3. branch 이름이 아니라 **검증된 정확한 40자 SHA**의 ZIP을 GitHub codeload에서 받는다.
4. archive path traversal을 차단하고 필수 파일/skills bundle 존재를 검증한다.
5. 여기까지 전부 성공하기 전에는 대상 Wiki를 건드리지 않는다.
6. 다운로드한 그 커밋의 `scripts/bootstrap.py --mode upgrade`를 실행한다.
7. 기존 스킬은 최신 bootstrap logic에 의해 `.wiki-upgrade-bak/<timestamp>/`로 백업된 뒤 교체된다.
8. 성공 결과에 `bootstrap_repository`, `bootstrap_branch`, `bootstrap_commit`을 기록한다.
9. 대상 `.llm-wiki.json`에도 `last_upgrade.source=github`와 정확한 commit SHA를 남긴다.

즉 `upgrade`의 의미는:

> **“현재 로컬 bundle로 덮어쓰기”가 아니라 “GitHub 공식 저장소 기본 브랜치의 현재 최신 commit을 고정해 그 버전의 upgrade logic과 skills bundle을 적용한다.”**

## GitHub 실패 시

네트워크, GitHub API, ZIP, checkout 검증 중 하나라도 실패하면:

- 대상 Wiki를 수정하지 않는다.
- 실패 이유를 그대로 보고한다.
- 로컬 bundle로 자동 fallback하지 않는다.

## 명시적 offline/local 경로

사용자가 GitHub를 사용하지 않거나 오프라인 local bundle을 명시한 경우에만:

```bash
python "<SKILL_ROOT>/scripts/upgrade.py" --target "<TARGET>" --config "<CONFIG>" --source local
```

이 모드는 "GitHub 최신"이 아니다. 보고할 때 반드시 `upgrade_source: local`임을 구분한다.

## bootstrap.py --mode upgrade 직접 호출 금지

사용자 의도의 "최신 업그레이드"에 `bootstrap.py --mode upgrade`를 직접 사용하지 않는다. 그것은 다운로드된 최신 checkout 내부에서 실제 적용을 수행하는 local apply primitive다.

# 6. migrate 규칙

migrate는 기존 일반 폴더를 Wiki로 만든다.

- 기존 파일 삭제/수정 금지
- 루트 문서 충돌은 `.wiki-proposed`
- 기존 파일을 raw로 옮길 때 파일별 원래 경로와 목적지를 표로 제시
- 사용자 승인 후 이동
- 이동 뒤 `/ingest` batch 처리

# 7. Evidence 운영 계약

Evidence profile이면 `wiki/evidence-model.md`와 `instructions/evidence-operations.md`를 필독한다.

## Ingest

```text
Raw → Source Record → atomic Claim → support/contradiction → Conflict/Experiment/Open Question
```

Canon 자동 수정 금지.

## Claim 상태

`OBSERVED`, `INFERRED`, `HYPOTHESIS`, `SUPPORTED`, `CONFIRMED`, `REJECTED`, `DISPUTED`, `DEPRECATED`, `UNKNOWN`

## Source lineage

같은 정보 계보에서 나온 여러 LLM 답변을 독립 evidence로 중복 계산하지 않는다. `parent_sources` 또는 동등 provenance를 기록한다.

## Query mode

- `answer`
- `research`
- `verify`
- `challenge`
- `trace`
- `compare`

## Lint

일반 문서 위생 외에 source 없는 Claim, broken provenance, lineage cycle, 근거 없는 CONFIRMED, REJECTED Claim을 현재 Canon이 사용하는 문제, unresolved conflict, orphan experiment 등을 점검한다.

## Canon review

`canon-review`는 기본 읽기 전용 recommendation이다. 명시적 승격/상태 변경 요청 없이는 Canon을 수정하지 않는다.

# 8. Graphify

Graphify는 선택적 탐색/시각화 보조다. truth database가 아니다.

- Codex: `$graphify <WIKI_ROOT>` / `$graphify <WIKI_ROOT> --update`
- Claude: `/graphify <WIKI_ROOT>` / `/graphify <WIKI_ROOT> --update`
- Python subprocess에서 bare `graphify <path>`를 직접 호출하지 않는다.
- 실행 뒤 `ingest_runtime.py record-graphify-run --host codex|claude`
- batch 완료는 필요 시 `verify --complete-batch --require-graph`

# 9. 스모크 체크

new/migrate/upgrade 후 대상 기준으로:

```bash
python ".claude/skills/ingest/scripts/ingest_runtime.py" status
python ".session-memory/scripts/session_memory.py" status
```

확인:

- 올바른 root
- `wiki/index.md`, `CLAUDE.md`, `raw/CLAUDE.md`, `.llm-wiki.json`
- 렌더링 placeholder 없음
- Evidence면 `wiki/evidence-model.md`, `instructions/evidence-operations.md`, `canon-review`
- upgrade면 결과의 `upgrade_source`, `bootstrap_commit`, `backup_dir`
- GitHub upgrade 성공이면 `.llm-wiki.json.last_upgrade.commit`과 결과 commit이 일치

실패를 숨기지 않는다.

# 10. 마무리 보고

보고 항목:

1. mode/profile
2. upgrade면 source가 `github`인지 `local`인지
3. GitHub upgrade면 repository/default branch/exact commit SHA
4. backup 위치
5. 설치/갱신 스킬 목록
6. `.wiki-proposed` / `profile_activation_pending`
7. smoke/verification 결과
8. 다음 단계 (`raw/` → ingest, `SAVE`, canon-review 등)

GitHub 최신을 기대한 upgrade에 `bootstrap_commit`을 보고하지 못했다면 완료라고 말하지 않는다.
