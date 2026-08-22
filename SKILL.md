---
name: llm-wiki-bootstrap
description: LLM Wiki 볼트(Karpathy 3계층 raw/wiki/Output)를 구축·전환·업그레이드한다. 세 모드 — new(빈 폴더에 신규 구축), migrate(자료가 쌓인 기존 프로젝트 폴더를 위키로 전환), upgrade(기존 위키의 운영 스킬을 최신 번들로 갱신). 폴더 구조·CLAUDE.md/AGENTS.md 라우터·문서 템플릿 생성, ingest/query/lint/session-memory/brief-tuner 스킬 설치, Obsidian Web Clipper 템플릿 배치, graphify 연결까지 처리한다. 사용자가 "LLM 위키 만들어줘", "세컨드브레인 구축", "지식 볼트 셋업", "위키 부트스트랩", "이 폴더를 위키로 전환", "위키 업그레이드/재구축", /llm-wiki-bootstrap 을 말하거나, 개인 지식관리 시스템·AI 위키를 새로 시작하거나 기존 폴더를 위키화하고 싶다는 의도를 보이면 — 명시적으로 "위키"라는 단어를 쓰지 않아도 — 반드시 이 스킬을 사용한다. 기존 위키의 내용 수정·질의에는 사용하지 않는다(그건 설치된 ingest/query/lint 스킬 담당).
---

# LLM Wiki Bootstrap

폴더를 완전한 LLM Wiki 볼트로 만든다. 결과물: 3계층 폴더 구조 + 라우터 문서 + 운영 스킬 6종(ingest/query/lint/session-memory/brief-tuner/wiki-audit) + Obsidian 편의 자산 + (가능하면) graphify 지식 그래프.

이 스킬은 배포용이다 — 이 스킬을 실행하는 환경에 다른 위키가 있을 필요가 없다. 필요한 모든 자산은 `assets/`에 번들되어 있다.

## 전제 조건

- Python 3.10+. 실행 명령을 이 순서로 찾는다: `python --version` → `py -3 --version` → `python3 --version` → (Windows) `%LOCALAPPDATA%\Programs\Python\Python3*\python.exe` 글롭 탐색 후 가장 높은 버전의 **전체 경로**. Microsoft Store 스텁(`...\WindowsApps\python.exe` — 실행하면 스토어 안내가 뜨거나 프로세스 생성이 실패)은 유효한 Python이 아니므로 건너뛴다. 성공한 명령/경로를 이후 모든 `python` 호출 자리에 그대로 사용한다. 전부 실패하면 설치를 안내하고 중단한다.
- graphify는 선택 사항이다 — 5단계에서 다룬다. 없어도 위키는 완전히 동작한다.
- 이 스킬은 Claude Code와 Codex 어느 쪽에서 실행돼도 같은 절차를 따른다. 질문 도구(AskUserQuestion 등)가 없는 환경이면 채팅으로 묻고, 비대화형 실행이라 물을 수 없으면 합리적 기본값으로 진행하되 가정한 값을 보고에 명시한다.
- 원문 보관·카탈로그 생성·그래프 파일 생성은 인제스트 완료의 증거가 아니다. 원문마다 `wiki/sources/<원문>.md` 1개를 만들고 완료 게이트의 수치를 확인한다.

## 1. 대상 폴더 확정과 모드 판정

사용자가 경로를 줬으면 그 경로를 쓴다. 안 줬으면 어디에 만들지 물어본다 (예: `~/Documents/<위키 이름>`).

대상 폴더 상태와 사용자 의도로 모드를 정한다:

| 대상 폴더 상태 | 사용자 의도 | 모드 |
|---|---|---|
| 비어 있거나 없음 | 새 위키 | **new** (기본, 아래 2~7단계) |
| 파일은 있지만 위키 마커(`raw/`, `wiki/`, `.agents/`) 없음 | 이 폴더를 위키로 전환 | **migrate** (아래 migrate 모드 절) |
| 위키 마커 있음 (기존 LLM Wiki) | 재구축·업그레이드·최신화 | **upgrade** (아래 upgrade 모드 절) |
| 위키 마커 있음 | "새로 만들어줘" (전환·갱신 의도 불명) | 중단하고 보고 — 기존 위키를 덮어쓰는 신규 구축은 하지 않는다. 내용 무손실로 스킬만 갱신하는 upgrade 모드가 있음을 안내하고, 사용자가 원하면 upgrade로 진행한다 |

의도가 모호하면 한 번 물어본다. 물을 수 없는 상황이면: 위키 마커가 있는 대상엔 upgrade(비파괴), 마커 없이 파일만 있는 대상엔 migrate를 택한다 — 어느 쪽도 기존 내용을 파괴하지 않기 때문이다. bootstrap.py도 모드별로 같은 검사를 하고 어긋나면 거부한다.

new 모드는 아래 2~7단계를 그대로 따른다. migrate/upgrade는 문서 하단의 해당 절을 따른다.

## 2. 짧은 인터뷰

사용자의 요청에 이미 아래 답이 들어 있으면 **묻지 말고 그대로 사용한다.** 빠진 항목만 **한 번에** 묻는다 (AskUserQuestion 도구가 있으면 그것을 사용):

1. **위키 주제와 목적** — 무엇에 관한 지식을 모으는가? 최종적으로 무엇을 만들어내고 싶은가? (예: "요리 레시피와 기법 연구 → 나만의 레시피북", "취업 준비 → 자소서·포트폴리오")
2. **주로 모을 자료 유형** — 유튜브 영상, 아티클, 개인 메모, 프로젝트 기록 등.
3. **프로젝트 이름** — 폴더명과 문서에 쓸 볼트 이름 (예: "Cooking Wiki").

답을 받으면 한 문장으로 도메인 요약(`domain_summary`)을 만들어 확인받지 말고 바로 진행한다 — 4단계에서 문서로 보여주므로 거기서 고칠 수 있다.

## 3. 스캐폴드 실행

config JSON을 임시 파일로 쓴 뒤 번들 스크립트를 실행한다:

```json
{"project_name": "<프로젝트 이름>", "domain_summary": "<한 문장 도메인 요약>"}
```

```bash
python "<이 스킬 디렉터리>/scripts/bootstrap.py" --target "<대상 폴더>" --config "<config.json 경로>"
```

stdout의 JSON에서 `"ok": true`를 확인한다. `false`면 `error`를 사용자에게 보고하고 중단한다. 스크립트가 하는 일: 폴더 구조 생성, 스킬 6종 설치(`.agents/skills/` 정본 + `.claude/skills/` 어댑터), 문서 템플릿 렌더링, `.session-memory/` 초기화, `templates/`(문서 템플릿 + web-clipper)를 배치.

## 4. 도메인 맞춤 문서 마무리

스크립트는 구조만 만든다. 서사는 네가 쓴다:

- `wiki/overview.md` — `BOOTSTRAP:FILL` 주석을 찾아 인터뷰 내용 기반으로 "핵심 축" 섹션을 2~5개 항목으로 채우고 주석을 삭제한다.
- `wiki/questions.md` — 같은 방식으로 초기 정보 공백 질문 2~5개를 채우고 주석을 삭제한다.
- `wiki/taxonomy.json` — 인터뷰에서 실제로 들은 범위를 바탕으로 초기 카테고리 3~7개를 만들고, 각 개념의 `prefLabel`, `altLabel`, `scopeNote`, `broader`를 채운다. taxonomy는 Graphify community와 별개다.
- 루트 `CLAUDE.md`의 "볼트 소개"가 인터뷰 내용과 어긋나면 다듬는다.

과장하지 않는다 — 아직 빈 위키다. 인터뷰에서 실제로 들은 것만 쓴다.

## 5. Graphify 연결 (선택)

`graphify --version`으로 CLI 존재를 확인한다.

- **Codex**: `python -m pip install graphifyy && graphify install --platform codex` 후 `$graphify <대상 폴더>`를 사용한다. Codex의 현재 인증과 병렬 서브에이전트를 Graphify 스킬이 사용하므로, Python에서 `graphify <대상 폴더>`를 직접 실행하지 않는다. 병렬 처리를 쓰려면 `~/.codex/config.toml`의 `[features] multi_agent = true`를 먼저 확인한다.
- 항상 그래프를 탐색에 사용하려면 선택적으로 `graphify codex install`을 실행해 `AGENTS.md`/Codex hook을 설치한다. 이 명령은 그래프 생성 자체가 아니라 탐색 시 `GRAPH_REPORT.md`를 먼저 읽게 하는 상시 안내다.
- **Claude Code**: `python -m pip install graphifyy && graphify install` 후 `/graphify <대상 폴더>`를 사용한다.
- **갱신**: 원문/Wiki 변경 후 호스트에 맞는 `$graphify <대상 폴더> --update` 또는 `/graphify <대상 폴더> --update`를 실행한다. `graphify update`를 Python subprocess로 직접 호출하지 않는다.
- Graphify 실행 후 `ingest_runtime.py record-graphify-run --host codex|claude`를 기록하고, 그 뒤 `verify --complete-batch --require-graph`를 실행한다.
- **없으면**: Graphify 설치·호스트 스킬 실행을 안내하고 완료 게이트를 `agent_action_required`로 중단한다. 설치·빌드가 실패하면 완료를 선언하지 않는다. 단일 소스 작업은 로컬 검증만 가능하지만 `validated_without_graph`로 명시한다.

## 6. 스모크 체크

세 가지를 실행해 설치를 검증한다 (모두 대상 폴더 기준):

```bash
python ".claude/skills/ingest/scripts/ingest_runtime.py" status
python ".session-memory/scripts/session_memory.py" status
```

- ingest status가 대상 폴더를 `root`로 반환하는지 확인.
- session-memory status가 오류 없이 상태를 반환하는지 확인.
- `wiki/index.md`, `CLAUDE.md`, `raw/CLAUDE.md`가 실제로 존재하고 플레이스홀더(`{{`)가 남아 있지 않은지 확인.
- 배치 인제스트 후에는 반드시 `ingest_runtime.py verify --complete-batch --require-graph`를 실행한다. 실패한 원문만 다시 읽어 `scan → ingest → finalize → verify` 루프를 통과시킨다.

실패한 항목은 숨기지 말고 그대로 보고한다.

## 7. 마무리 보고

사용자에게 보고한다:

1. 생성된 구조 요약 (트리 형태, 핵심 폴더만).
2. 설치된 스킬 6종과 각각의 용도 한 줄씩.
3. **다음 단계 안내**:
   - 첫 자료를 `raw/`(또는 `raw/inbox/`)에 넣고 `/ingest` 실행 → 위키가 채워지기 시작한다.
   - 작업을 마칠 때 `SAVE`를 입력하면 세션 상태가 보존된다.
   - `templates/`의 작업 브리프 템플릿을 자기 작업 패턴에 맞추고 싶으면 `/brief-tuner` 인터뷰를 실행한다.
   - Obsidian 사용자라면: 이 폴더를 볼트로 열고, `templates/web-clipper/`의 JSON을 Obsidian Web Clipper 확장에 임포트하면 웹 자료가 `raw/reference/` 하위로 자동 수집된다 (임포트 방법은 `templates/web-clipper/README.md`).
   - graphify를 연결하지 않았다면 연결 방법 한 줄.
   - 인제스트 완료 보고에는 `입력 원문 / 처리 완료 / 검증 완료 / 제외 / 실패·미처리 / 그래프 노드 / 그래프 링크` 수치를 포함한다. 실패·미처리가 0이 아니면 반드시 `미완료`라고 보고한다.

## migrate 모드 — 기존 프로젝트 폴더를 위키로 전환

자료가 쌓여 있는 일반 폴더(위키 마커 없음)를 위키로 만든다. **기존 파일은 어떤 것도 삭제·수정하지 않는다.**

1. **인터뷰** — new 모드 2단계와 같되, 폴더 안 기존 파일들을 훑어보면 주제·자료 유형을 상당 부분 추론할 수 있다. 추론한 내용을 요약해 보여주고 빠진 것만 묻는다.
2. **스캐폴드** — `--mode migrate`로 실행한다:
   ```bash
   python "<이 스킬 디렉터리>/scripts/bootstrap.py" --target "<대상>" --config "<config.json>" --mode migrate
   ```
   기존에 있던 루트 문서(CLAUDE.md 등)는 덮어쓰지 않고 `<이름>.wiki-proposed`로 생성된다 — 결과 JSON의 `proposals`와 `existing_entries`(기존 최상위 항목)를 확인한다.
3. **제안 문서 병합** — 각 `.wiki-proposed`에 대해: 기존 문서 내용을 보존하면서 위키 라우터 섹션을 추가하는 병합본을 만들어 원본을 교체하고 `.wiki-proposed`를 삭제한다. 기존 내용과 충돌하는 부분은 임의로 지우지 말고 사용자에게 보여준다.
4. **기존 파일 편입 계획** — `existing_entries`의 자료 파일들을 `raw/` 하위 어디로 옮길지 분류 계획(파일별 목적지 표)을 만들어 **사용자 승인을 받은 뒤** 이동한다. 이동은 복사가 아닌 이동이되, 계획 표가 곧 복구 지도가 되도록 원래 경로를 함께 기록해 보고한다. 스캐폴드 산출물·설정 파일(.git 등)은 옮기지 않는다.
5. **배치 ingest 안내** — 이동이 끝나면 `/ingest`(배치 모드)로 옮긴 원문들을 위키에 반영하도록 안내한다. 파일이 많으면 이번 세션에서 전부 하지 말고 ingest 스킬의 배치 규칙에 맡긴다.
6. new 모드의 4(도메인 문서)·5(graphify)·6(스모크)·7(보고)를 그대로 수행한다.

## upgrade 모드 — 기존 위키의 스킬·런타임 갱신

기존 LLM Wiki의 운영 스킬과 session-memory 런타임을 최신 번들로 교체한다. **`raw/`, `wiki/`, `Output/`, 루트 문서(CLAUDE.md, AGENTS.md, log.md, changelog.md)는 절대 건드리지 않는다** — 지식·기록은 전부 보존된다.

1. `--mode upgrade`로 실행한다 (config의 project_name은 `.session-memory/config.json`이 없을 때만 쓰인다):
   ```bash
   python "<이 스킬 디렉터리>/scripts/bootstrap.py" --target "<대상>" --config "<config.json>" --mode upgrade
   ```
2. 결과 JSON을 보고한다: `backup_dir`(교체 전 스킬이 이동 보관된 위치 — 롤백 지점), `refreshed_skills`, `proposals`(있다면 `instructions/wiki-operations.md.wiki-proposed` — 대상 위키가 자체 수정한 운영 문서라 자동으로 덮지 않은 것이니 차이를 보여주고 병합 여부를 사용자에게 맡긴다), 신규 복사된 템플릿 수.
3. new 모드 6단계 스모크 체크를 수행한다. 단, 대상 위키가 자체 스키마(예: `tags` 기반)를 쓰더라도 ingest 스킬은 대상 스키마를 따르도록 설계돼 있으므로 문서 구조를 바꾸지 않는다.
4. 업그레이드 전에 대상 위키가 설치된 스킬을 커스텀 수정해서 쓰고 있었는지 물어볼 수 있으면 물어본다. 커스텀이 있었다면 백업 디렉터리와 새 스킬의 차이를 보여주고 재적용을 돕는다.

## 주의사항

- `raw/`는 불변이다 — 부트스트랩 이후 어떤 작업도 `raw/` 내용을 수정하면 안 된다.
- migrate·upgrade 모드가 있으므로, 기존 폴더/위키 요청을 만나도 스킬 밖의 임시방편(수동 복사, `install_to_wiki.py` 직접 실행)으로 우회하지 않는다.
- 인터뷰 답이 모호해도 최대 한 번만 되묻는다. 그래도 모호하면 합리적 기본값으로 진행하고 4단계 문서에서 사용자가 고칠 수 있음을 알린다.
