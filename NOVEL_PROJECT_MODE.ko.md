# 소설 프로젝트 모드 — Novel v1

`novel`은 소설·웹소설을 집필하는 프로젝트 모드다. 일반 Wiki의 원본 보존·지식 조회·세션 저장 위에
인물·설정·구성·원고·퇴고·검토·작가 결정을 추가한다.

```text
lifecycle:     new | migrate | upgrade
vault profile: standard | evidence
project mode:  knowledge | game | novel
```

기본 추천은 `standard + novel`이다. 역사·과학·기술 등 현실 참고자료의 출처와 주장을 엄격하게
검토하려면 `evidence + novel`을 사용한다. 작가 채택 설정은 허구 작품의 정본이지 현실의 사실 확인이 아니다.

## 빠른 시작

Python 3.10 이상과 Claude Code 또는 Codex가 필요하다. 추가 Python 패키지나 외부 그래프는 필요 없다.
[설정 예시](config.novel.example.json)를 복사하고 작품 정보를 입력한다.

```json
{
  "project_name": "달의 기록 Wiki",
  "domain_summary": "작품 설정과 플롯, 원고와 퇴고를 연결한다.",
  "project_mode": "novel",
  "novel_title": "달의 기록",
  "genre": "판타지",
  "audience": "성인",
  "project_phase": "planning"
}
```

```bash
python scripts/novel_project.py --target ./MyNovel --config ./config.novel.json --mode new --dry-run
python scripts/novel_project.py --target ./MyNovel --config ./config.novel.json --mode new
```

`--dry-run`은 staging에서 실제 설치·검증을 수행하고 쓰기 계획을 반환한 뒤 staging을 제거한다.
최종 vault와 아직 없는 상위 폴더는 생성하지 않는다. 기존 자료 폴더에는 `--mode migrate`를 사용한다.
자료를 자동 이동하지 않으므로 기존 원고를 계속 보존하면서 새 작업 원고를 명시적으로 연결할 수 있다.

기본 설치기도 Novel을 라우팅한다.

```bash
python scripts/bootstrap.py --target ./MyNovel --config ./config.novel.json --project-mode novel
```

config의 `project_mode: novel`이 있으면 `--project-mode`를 생략해도 된다.

## 구조

```text
MyNovel/
├─ raw/novel/research/ · imports/          불변 참고자료·가져온 원고
├─ wiki/novel/
│  ├─ characters/ · locations/ · world/    인물·장소·세계관 규칙
│  ├─ arcs/ · chapters/ · scenes/         서사 아크·회차·장면
│  ├─ timeline/ · foreshadowing/           실제 사건 시간선·복선
│  ├─ reviews/ · decisions/               검토와 작가 결정
│  └─ index.md · overview.md · model.md
├─ manuscripts/novel/drafts/ · revisions/ 편집 가능한 초고·수정본
├─ Output/novel/                          공유용 산출물
├─ templates/novel/                       템플릿 10종
├─ instructions/novel-project.md
├─ tools/novel_check.py
├─ .agents/skills/novel-project/           Codex 정본 스킬
├─ .claude/skills/novel-project/           Claude adapter
└─ .llm-wiki.json
```

기존 Wiki의 공통 디렉터리, ingest/query/lint/wiki-audit/session-memory도 설치된다.
참고자료 수집·Source 연결은 공통 ingest를 사용하며 Novel 전용 ingest adapter는 설치하지 않는다.
Novel은 공통 ingest의 그래프 정책을 바꾸지 않는다. 집필 원고를 Raw로 옮기지 않는다.

## 설정·구성·원고 연결하기

1. `character.md`, `location.md`, `world-rule.md`를 `wiki/novel/`의 대응 폴더로 복사한다.
2. `chapter.md`와 `scene.md`로 회차·장면을 계획하고 vault 안에서 유일한 ID를 붙인다.
3. 회차의 `scene_refs`에 장면 ID를 넣고 장면의 `chapter_ref`에 회차 ID를 넣는다.
4. 장면 원고를 `manuscripts/novel/drafts/`에 작성하고 `manuscript_ref`로 연결한다.
5. `timeline-event.md`로 세계 내 사건을, `foreshadow.md`로 심기·회수 장면을 연결한다.

예를 들어 회차 메타데이터는 다음과 같다.

```yaml
type: novel_chapter
chapter_id: CH-001
title: "첫 번째 단서"
status: drafted
order: 1
scene_refs: ["SCENE-001"]
```

장면의 연결은 다음과 같다. 두 메타데이터 모두 Markdown 파일의 `---` frontmatter에 둔다.

```yaml
type: novel_scene
scene_id: SCENE-001
title: "낡은 편지"
status: drafted
chapter_ref: "CH-001"
sequence: 1
pov_ref: "CHAR-001"
manuscript_ref: "manuscripts/novel/drafts/scene-001.md"
```

`CHAR-001` 인물 문서와 연결 원고도 실제로 있어야 한다. 템플릿의 미정 순서·시간은 `null`로 둔다.
ID는 영문으로 시작하는 영문·숫자·하이픈·밑줄 문자열이며 파일명과 독립적이다.
회차·장면의 읽기 순서와 실제 사건의 시간 순서를 분리한다.

## 일상 요청

Codex의 `$novel-project` 또는 Claude Code의 `/novel-project`를 사용할 수 있다.

```text
기존 설정을 바탕으로 주인공의 욕망과 결핍을 정리해줘.
1~5회차의 갈등과 전환점을 장면 단위로 구성해줘.
SCENE-001을 1인칭 시점으로 집필하고 원고를 연결해줘.
이 회차를 문체를 유지하며 퇴고하고 설정 변경은 따로 기록해줘.
복선의 심기와 회수, 인물별 정보와 사건 시간선을 검토해줘.
읽은 원고를 근거로 설정 충돌과 시점 누출을 찾아 검토 기록을 남겨줘.
```

설정·시간선·인과·시점·인물 동기·문체 검토는 실제 문서·원고 인용과 함께 기록한다.
수정 제안과 작가 결정을 구분하며, 이미 요청한 집필·퇴고 범위는 추가 확인 없이 수행한다.

## 자동 점검

vault에서 실행하거나 `--root <VAULT>`를 command 앞에 지정한다.

```bash
python tools/novel_check.py status
python tools/novel_check.py check
python tools/novel_check.py outline
python tools/novel_check.py trace CHAR-001
```

| 명령 | 결과 |
| --- | --- |
| `status` | 문서 종류별 개수, 구조 오류·경고 |
| `check` | 중복 ID·순서, 참조·유형, 회차↔장면, 원고 경로·존재, 선언된 시간·복선 연결 |
| `outline` | 회차와 장면의 읽기 순서 |
| `trace ID` | 문서와 그 문서로 들어오는/나가는 참조 |

모든 명령은 읽기 전용 JSON을 반환한다. `check`는 오류가 있으면 exit 1, 경고만 있으면 exit 0이다.
나머지 명령은 조회 성공 시 exit 0이므로 `has_errors`, `summary`, `issues`를 확인한다.
앞서 읽히는 복선 회수나 공개된 목표 회차의 미회수는 작가 의도를 검토할 경고로 남긴다.
`semantic_review: not_performed`는 본문 의미 검토가 실행되지 않았다는 뜻이다.

자동 점검은 선언된 구조만 다룬다. 원고의 문학적 완성도나 자연어 설정 모순, 시점 누출,
등장인물의 동기, 공개할 준비가 됐는지를 판정하지 않는다.

## 안전한 전환과 업그레이드

- `new`는 비어 있거나 없는 vault만 허용한다.
- `migrate`는 기존 원본을 삭제·자동 이동·덮어쓰지 않는다.
- 기존 Game mode나 미래 버전의 Novel 계약을 자동으로 대체하지 않는다.
- Standard와 Evidence를 모두 지원하며 Evidence를 Standard로 자동 축소하지 않는다.
- symlink를 따라 쓰지 않으며 config·번들·여유 공간을 변경 전에 확인한다.
- 단일 staging에서 설치한 뒤 원고·Raw 보존과 runtime을 검증한다. 대상의 동시 변경도 확인한다.
- 사용자 지침·템플릿 충돌은 `.wiki-proposed`로 제안하며 기존 제안도 보존한다.
- 관리 runtime·스킬을 교체하기 전에 백업하고, 적용 후 검증 실패 시 이전 vault를 복원한다.
- 설치기가 소유하는 관리 자산은 `novel_managed_assets`에 기록한다. 전환 시 제안만 한 파일은 다음 업그레이드에서도 자동 교체하지 않는다.
- 성공한 적용의 `rollback_backup`에는 이전 vault 전체가 남는다. 검토한 뒤 별도로 정리할 수 있다.
- `project_mode_activation_pending`이면 제안 지침을 검토한다. 구조 오류는 설치 상태와 별도로 점검한다.

```bash
python scripts/novel_project.py --target ./MyNovel --config ./config.novel.json --mode upgrade --dry-run
python scripts/novel_project.py --target ./MyNovel --config ./config.novel.json --mode upgrade
```

업그레이드는 GitHub의 현재 default branch와 정확한 commit을 고정한다. 조회·다운로드·계약 검증이
실패하면 대상 vault를 변경하지 않고 오래된 local bundle로 자동 전환하지 않는다.
공통 `scripts/upgrade.py`도 Novel Wiki의 기본·Novel 자산을 함께 갱신한다.

아직 GitHub에 게시되지 않은 개발 버전이나 오프라인 bundle은 명시적으로 local source를 사용한다.

```bash
python scripts/novel_project.py --target ./MyNovel --config ./config.novel.json --mode upgrade --source local --dry-run
```

기존 설정을 보존하려면 upgrade config에서 작품 메타데이터를 생략할 수 있다. `{}`도 지원한다.
개발 중 Novel 계약이 없는 GitHub 버전으로의 업데이트는 대상 변경 전에 거부한다.
