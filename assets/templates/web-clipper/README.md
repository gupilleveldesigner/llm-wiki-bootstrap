# LLM Wiki용 Obsidian Web Clipper 템플릿

이 폴더의 JSON 5개를 Web Clipper 설정의 **Import**에서 불러오거나 템플릿 영역에 드래그한다.

## 저장 위치

| 템플릿 | `source_type` | 저장 경로 |
| --- | --- | --- |
| 아티클 | `article` | `raw/reference/articles` |
| 유튜브 | `youtube` | `raw/reference/youtube` |
| 팟캐스트 | `podcast` | `raw/reference/podcasts` |
| 책 | `book` | `raw/reference/books` |
| 연구 자료 | `research` | `raw/reference/research` |

## 운영 원칙

- `topics`는 의도적으로 비워 둔다. `/ingest`가 기존 Wiki 분류와 대조해 채운다.
- `ingest_status: pending`은 캡처 당시의 기록일 뿐이다. 실제 인제스트 여부는 `wiki/sources/`의 `sources` 링크로 판정한다.
- 본문의 `캡처 메모` 세 항목은 선택 사항이다. 미리 적어 두면 단일 소스 인제스트의 맥락 질문에 바로 활용할 수 있다.
- 자동 선택은 Web Clipper 템플릿 목록에서 먼저 일치한 템플릿이 우선한다. 연구 자료, 책, 팟캐스트, 유튜브를 아티클보다 위에 둔다.
- YouTube는 캡처 전 Web Clipper Reader에서 자막이 보이는지 확인한다. 자막이 없는 상태에서는 `영상 내용`에 설명이나 페이지 본문만 저장될 수 있다.
- 팟캐스트는 가능하면 대본 또는 상세 쇼 노트가 있는 에피소드 페이지에서 캡처한다.

프롬프트 변수는 사용하지 않는다. 캡처 단계에서는 원문 보존에 집중하고, 요약·엔티티 추출·개념 연결은 Vault의 `/ingest` 절차가 담당한다.
