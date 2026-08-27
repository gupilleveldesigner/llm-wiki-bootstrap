---
name: llm-wiki-bootstrap
description: LLM Wiki 볼트(Karpathy 3계층 raw/wiki/Output)를 구축·전환·업그레이드한다. lifecycle mode는 new/migrate/upgrade, vault profile은 standard/evidence로 분리한다. Evidence profile은 Raw→Source→Claim→Evidence/Conflict/Experiment→reviewed Canon 구조, source lineage, epistemic state, canon-review를 추가한다. 폴더 구조·CLAUDE.md/AGENTS.md 라우터·문서 템플릿 생성, ingest/query/lint/session-memory/brief-tuner/wiki-audit 스킬 설치, Obsidian Web Clipper 템플릿 배치, graphify 연결까지 처리한다. 사용자가 "LLM 위키 만들어줘", "세컨드브레인 구축", "지식 볼트 셋업", "이 폴더를 위키로 전환", "위키 업그레이드", "Evidence Wiki", "근거/가설/실험을 분리하는 연구 위키"를 말하거나 개인 지식관리/AI 연구 지식베이스를 새로 시작하거나 기존 폴더를 위키화하고 싶다는 의도를 보이면 사용한다. 기존 위키의 내용 수정·질의에는 사용하지 않는다(설치된 ingest/query/lint/canon-review 담당).
---

# LLM Wiki Bootstrap

폴더를 완전한 LLM Wiki 볼트로 만든다. 기본 결과물은 3계층 폴더 구조 + 라우터 문서 + 운영 스킬 6종(ingest/query/lint/session-memory/brief-tuner/wiki-audit) + Obsidian 편의 자산 + (가능하면) graphify 지식 그래프다. `evidence` profile에서는 `canon-review`와 Evidence 계층/템플릿이 추가된다.

이 스킬은 배포용이다 — 이 스킬을 실행하는 환경에 다른 위키가 있을 필요가 없다. 필요한 모든 자산은 `assets/`에 번들되어 있다.

## 핵심 모델: mode와 profile을 분리한다

두 축을 섞지 않는다.

### Lifecycle mode — 대상 폴더에 어떤 작업을 하는가

- `new` — 빈 폴더에 신규 구축
- `migrate` — 자료가 쌓인 일반 폴더를 비파괴 전환
- `upgrade` — 기존 LLM Wiki의 운영 자산을 백업 후 갱신

### Vault profile — 어떤 방식으로 지식을 관리하는가

- `standard` — 일반 `raw → wiki → Output`
- `evidence` — `Raw → Source → Claim → Evidence/Conflict/Experiment → reviewed Canon`

따라서 `new+evidence`, `migrate+evidence`, `upgrade+evidence`가 모두 가능하다. Evidence profile은 `.llm-wiki.json`에 기록한다. manifest가 없는 기존 위키는 호환성을 위해 `standard`로 취급한다. Evidence → Standard 다운그레이드는 `upgrade`로 자동 수행하지 않는다.

## 전제 조건

- Python 3.10+. 실행 명령을 이 순서로 찾는다: `python --version` → `py -3 --version` → `python3 --version` → (Windows) `%LOCALAPPDATA%\Programs\Python\Python3*\python.exe` 글롭 탐색 후 가장 높은 버전의 **전체 경로**. Microsoft Store 스텁(`...\WindowsApps\python.exe`)은 유효한 Python이 아니므로 건너뛴다. 성공한 명령/경로를 이후 모든 `python` 호출 자리에 그대로 사용한다. 전부 실패하면 설치를 안내하고 중단한다.
- graphify는 선택 사항이다. 없어도 위키는 동작하지만 배치 인제스트의 기존 Graphify 완료 게이트는 그대로 따른다.
- Claude Code와 Codex 어느 쪽에서 실행돼도 같은 절차를 따른다. 질문 도구가 없는 환경이면 채팅으로 묻고, 비대화형이면 합리적 기본값으로 진행하되 가정을 보고한다.
- 원문 보관·카탈로그 생성·그래프 파일 생성은 인제스트 완료의 증거가 아니다. 원문마다 `wiki/sources/<원문>.md` 1개를 만들고 완료 게이트의 수치를 확인한다.

## 1. 대상 폴더 확정과 lifecycle mode 판정

사용자가 경로를 줬으면 그 경로를 쓴다. 안 줬으면 어디에 만들지 물어본다.

| 대상 폴더 상태 | 사용자 의도 | mode |
|---|---|---|
| 비어 있거나 없음 | 새 위키 | **new** |
| 파일은 있지만 위키 마커(`raw/`, `wiki/`, `.agents/`) 없음 | 이 폴더를 위키로 전환 | **migrate** |
| 위키 마커 있음 | 재구축·업그레이드·최신화 | **upgrade** |
| 위키 마커 있음 | "새로 만들어줘" (전환·갱신 불명) | 중단하고 기존 지식을 덮지 않는 upgrade를 안내 |

의도가 모호하면 한 번 물어본다. 물을 수 없으면 위키 마커가 있는 대상엔 upgrade, 마커 없이 파일만 있는 대상엔 migrate를 택한다. 둘 다 기존 내용을 파괴하지 않는다.

## 2. Vault profile 판정

사용자가 profile을 명시하면 그대로 사용한다. 명시하지 않았으면 목적을 보고 판정한다.

### `standard` 기본값

다음과 같은 일반 지식관리/학습/자료 정리:

- 개인 공부 Wiki
- 기사/유튜브/책 요약·연결
- 프로젝트 메모 정리
- 세컨드 브레인

### `evidence`를 선택할 신호

다음 중 하나가 명확하면 Evidence profile을 권장/선택한다.

- 역공학 또는 내부 구현 추정
- 여러 LLM의 분석을 Source로 누적
- "관찰된 사실"과 "추론/가설"을 분리해야 함
- 출처 계보(provenance/lineage)가 중요함
- 상충 주장과 반증 기록을 보존해야 함
- 가설 → 통제 실험 → 결론의 연구 루프가 핵심임
- 모든 결론을 원문까지 trace해야 함

애매하면 `standard`를 기본으로 한다. 단, 기존 위키의 `upgrade`에서는 `.llm-wiki.json` profile을 보존하고, manifest가 없을 때만 standard로 본다.

Evidence profile의 핵심 문장은 다음이다.

> **“LLM이 말했다”와 “우리가 확인했다”를 같은 것으로 취급하지 않는다.**

## 3. 짧은 인터뷰

사용자의 요청에 이미 답이 들어 있으면 묻지 않는다. 빠진 항목만 한 번에 묻는다.

1. **위키 주제와 목적** — 무엇을 모으고 최종적으로 무엇을 만들고 싶은가?
2. **주로 모을 자료 유형** — 영상, 아티클, 개인 메모, 프로젝트 기록, 로그, LLM 분석, 실험 결과 등.
3. **프로젝트 이름** — 폴더명과 문서에 쓸 이름.

답을 받으면 한 문장의 `domain_summary`를 만든다.

## 4. 스캐폴드 실행

config JSON:

```json
{"project_name": "<프로젝트 이름>", "domain_summary": "<한 문장 도메인 요약>"}
```

Standard 신규 예:

```bash
python "<이 스킬 디렉터리>/scripts/bootstrap.py" --target "<대상>" --config "<config.json>" --mode new --profile standard
```

Evidence 신규 예:

```bash
python "<이 스킬 디렉터리>/scripts/bootstrap.py" --target "<대상>" --config "<config.json>" --mode new --profile evidence
```

`--profile`을 생략하면 new/migrate는 standard, upgrade는 기존 manifest profile을 보존한다.

stdout의 `"ok": true`를 확인한다. `false`면 error를 보고하고 중단한다.

스크립트는 다음을 처리한다.

- 기본 3계층/운영 폴더 생성
- profile별 추가 폴더 생성
- `.llm-wiki.json` manifest 생성/갱신
- base 스킬 6종 설치
- Evidence에서만 `canon-review` 설치
- profile-aware 라우터/문서 렌더링
- `.session-memory/` 초기화
- 기본 templates + Evidence Claim/Conflict/Experiment/Canon 템플릿 배치

## 5. 도메인 맞춤 문서 마무리

스크립트는 구조만 만든다. 서사는 실제 인터뷰 근거로 채운다.

- `wiki/overview.md` — `BOOTSTRAP:FILL`을 찾아 핵심 축 2~5개를 채운다.
- `wiki/questions.md` — 초기 정보 공백 질문 2~5개를 채운다.
- `wiki/taxonomy.json` — 실제로 들은 범위에서 초기 카테고리 3~7개를 만든다.
- 루트 `CLAUDE.md`의 볼트 소개가 실제 목적과 어긋나면 다듬는다.

Evidence profile이면 추가로 확인한다.

- `wiki/evidence-model.md`가 존재한다.
- `instructions/evidence-operations.md`가 존재한다.
- `wiki/canon/overview.md`는 아직 검토 지식이 없으면 비어 있는 상태를 유지한다. 빈 Canon을 억지로 채우지 않는다.
- `.wiki-cache/`는 정본이 아니라 재생성 가능한 영역으로 취급한다.

## 6. Evidence profile 운영 계약

Evidence profile의 실제 ingest/query/lint 규칙은 `instructions/wiki-operations.md`가 `instructions/evidence-operations.md`와 `wiki/evidence-model.md`를 필독하도록 라우팅한다. 기존 ingest/query/lint 스킬 정본을 복제해 별도 fork를 만들지 않는다.

### Ingest

`Raw → Source Record → atomic Claim → support/contradiction → Conflict/Experiment/Open Question`까지 만들 수 있다. **Canon 자동 승격은 금지한다.**

### Query

- `answer`
- `research`
- `verify`
- `challenge`
- `trace`
- `compare`

를 구분한다. 현재 결론을 답할 때도 epistemic state를 숨기지 않는다.

### Lint

일반 문서 위생 외에 source 없는 Claim, 끊긴 provenance, lineage cycle, 근거 없는 CONFIRMED, REJECTED Claim의 현재 Canon 사용, unresolved conflict 누락, orphan experiment 등을 검사한다. 의미 판단이 필요한 상태 변경은 자동 수정하지 않는다.

### Canon review

`canon-review`는 기본 읽기 전용 추천이다. source quality, source independence/lineage, contradictory evidence, experiment, direct observation, 기존 Canon 충돌을 확인한다. 사용자가 명시적으로 승격/채택을 요청한 경우에만 Canon 파일을 수정한다.

## 7. Graphify 연결 (선택)

`graphify --version`으로 CLI 존재를 확인한다.

- **Codex**: `python -m pip install graphifyy && graphify install --platform codex` 후 `$graphify <대상 폴더>`를 사용한다. Python에서 `graphify <대상 폴더>`를 직접 실행하지 않는다. 병렬 처리를 쓰려면 `~/.codex/config.toml`의 `[features] multi_agent = true`를 확인한다.
- 항상 그래프를 탐색에 사용하려면 선택적으로 `graphify codex install`을 실행한다. 이는 그래프 생성 자체가 아니라 탐색 hook/라우터 설치다.
- **Claude Code**: `python -m pip install graphifyy && graphify install` 후 `/graphify <대상 폴더>`를 사용한다.
- **갱신**: `$graphify <대상 폴더> --update` 또는 `/graphify <대상 폴더> --update`를 사용한다. `graphify update`를 Python subprocess로 직접 호출하지 않는다.
- Graphify 실행 후 `ingest_runtime.py record-graphify-run --host codex|claude`를 기록하고 `verify --complete-batch --require-graph`를 실행한다.
- Graphify가 없으면 기존 ingest 계약대로 batch completion을 거짓으로 선언하지 않는다.

Evidence profile에서도 Graphify는 **탐색/시각화 보조 수단**이지 truth database가 아니다. 정본은 Markdown/frontmatter와 Raw provenance다.

## 8. 스모크 체크

대상 폴더 기준:

```bash
python ".claude/skills/ingest/scripts/ingest_runtime.py" status
python ".session-memory/scripts/session_memory.py" status
```

확인:

- ingest status의 `root`가 대상 폴더인가?
- session-memory status가 정상인가?
- `wiki/index.md`, `CLAUDE.md`, `raw/CLAUDE.md`, `.llm-wiki.json`이 존재하는가?
- 렌더링 대상에 `{{` 플레이스홀더가 남지 않았는가?
- Evidence면 `wiki/evidence-model.md`, `instructions/evidence-operations.md`, `.agents/skills/canon-review/SKILL.md`가 존재하는가?
- 배치 ingest 후 `verify --complete-batch --require-graph`를 통과했는가?

실패한 항목은 숨기지 않는다.

## 9. 마무리 보고

사용자에게 다음을 보고한다.

1. lifecycle mode와 vault profile
2. 생성 구조 요약
3. 설치 스킬 — standard 6종, evidence 7종
4. `.llm-wiki.json` 위치
5. 첫 자료를 `raw/`에 넣고 `/ingest`하는 다음 단계
6. `SAVE` 세션 보존 안내
7. Graphify 연결 여부/완료 게이트 상태
8. Evidence이면 `canon-review`가 자동 승격이 아닌 검토 gate라는 점

인제스트 완료 보고에는 기존 계약대로 `입력 원문 / 처리 완료 / 검증 완료 / 제외 / 실패·미처리 / 그래프 노드 / 그래프 링크` 수치를 포함한다. 실패·미처리가 0이 아니면 `미완료`라고 보고한다.

## migrate mode — 기존 프로젝트 폴더를 위키로 전환

자료가 쌓여 있는 일반 폴더(위키 마커 없음)를 위키로 만든다. **기존 파일은 삭제·수정하지 않는다.**

1. 인터뷰와 profile 판정을 수행한다.
2. 스캐폴드:

   ```bash
   python "<이 스킬 디렉터리>/scripts/bootstrap.py" --target "<대상>" --config "<config.json>" --mode migrate --profile <standard|evidence>
   ```

3. 기존 루트 문서와 충돌하는 경우 `.wiki-proposed`를 확인한다. 기존 내용을 보존하면서 필요한 라우터 섹션을 병합하고, 충돌하는 부분은 사용자에게 보여준다.
4. 기존 파일들을 `raw/` 어디로 옮길지 파일별 목적지 표를 만든 뒤 **사용자 승인 후** 이동한다. 원래 경로를 복구 지도에 남긴다.
5. 이동 후 `/ingest` 배치 모드를 사용한다.
6. 도메인 문서, Graphify, 스모크 체크, 마무리 보고를 수행한다.

## upgrade mode — 기존 Wiki 갱신 / profile 승격

기존 Wiki의 지식·Raw를 보존하면서 스킬/런타임/profile 자산을 갱신한다.

### 같은 profile 유지

```bash
python "<이 스킬 디렉터리>/scripts/bootstrap.py" --target "<대상>" --config "<config.json>" --mode upgrade
```

manifest가 있으면 profile을 보존한다.

### Standard → Evidence 승격

```bash
python "<이 스킬 디렉터리>/scripts/bootstrap.py" --target "<대상>" --config "<config.json>" --mode upgrade --profile evidence
```

이때:

- `raw/`, 기존 `wiki/` 지식, `Output/`은 보존한다.
- 기존 스킬은 `.wiki-upgrade-bak/<timestamp>/`에 이동 백업한다.
- Evidence 폴더/템플릿/`canon-review`/manifest를 추가한다.
- 기존 루트 CLAUDE.md/AGENTS.md/wiki/CLAUDE.md는 직접 덮지 않고 Evidence router가 필요한 경우 `.wiki-proposed`를 만든다.
- `profile_activation_pending: true`이면 해당 router proposal을 검토/병합하기 전까지 Evidence profile 전환 완료라고 과장하지 않는다.
- 기존 `instructions/wiki-operations.md`가 새 번들과 다르면 `.wiki-proposed`를 만든다. 내용 차이를 보여주고 안전하게 병합한다.

Evidence → Standard 자동 downgrade는 거부한다. Evidence 기록을 제거하거나 의미를 축소하는 작업은 별도 마이그레이션 설계가 필요하다.

## 주의사항

- `raw/`는 불변이다.
- 외부 LLM 답변은 Evidence profile에서 Authority가 아니라 Source다.
- 같은 lineage의 반복 LLM 답변을 독립 evidence로 세지 않는다.
- 반증된 Claim도 삭제하지 않는다.
- Canon 자동 승격은 하지 않는다.
- `.wiki-cache/`는 정본이 아니다.
- migrate/upgrade가 있으므로 기존 폴더 요청을 임시 수동 복사 방식으로 우회하지 않는다.
- 인터뷰는 최대 한 번만 되묻고, 그래도 모호하면 안전한 기본값으로 진행하되 가정을 보고한다.
