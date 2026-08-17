# llm-wiki-bootstrap

빈 폴더를 AI가 운영하는 개인 지식 볼트(LLM Wiki)로 만들어주는 Claude Code / Codex 스킬.

*A Claude Code / Codex skill that turns any folder into an AI-operated personal knowledge vault. English below.*

## 무엇을 만들어주나

한 번의 대화로 다음이 셋업된다:

- **3계층 폴더 구조** — `raw/`(원문, 불변) → `wiki/`(요약·연결된 지식) → `Output/`(산출물). Karpathy의 "LLM이 관리하는 위키" 구조를 따른다.
- **운영 스킬 5종** — 볼트 안에 설치되어 이후 세션에서 바로 쓸 수 있다:
  - `ingest` — raw에 넣은 원문을 위키로 요약·연결
  - `query` — frontmatter 우선 탐색으로 위키에서 근거 있는 답변
  - `lint` — 깨진 링크·고아 문서·신선도 점검
  - `session-memory` — `SAVE` 한 마디로 세션 상태를 원자적으로 보존
  - `brief-tuner` — AI 작업 브리프 템플릿을 인터뷰로 내 작업 패턴에 맞게 최적화
- **라우터 문서** — CLAUDE.md / AGENTS.md가 매 세션 AI에게 볼트 규칙을 알려준다.
- **Obsidian Web Clipper 템플릿** — 웹 아티클·유튜브·책·팟캐스트를 `raw/reference/`로 자동 수집 (선택).
- **graphify 지식 그래프** — 설치돼 있으면 볼트 전체를 그래프로 연결 (선택).

## 설치

이 저장소를 스킬 폴더에 복사한다:

```bash
git clone https://github.com/OWNER/llm-wiki-bootstrap "$HOME/.claude/skills/llm-wiki-bootstrap"
```

Codex CLI 사용자는 같은 폴더를 `~/.codex/skills/llm-wiki-bootstrap`에 복사하면 된다 (`agents/openai.yaml` 포함).

**요구사항**: Claude Code 또는 Codex CLI, Python 3.10+. graphify는 선택(`pip install graphifyy`).

## 사용

Claude Code에서:

```
/llm-wiki-bootstrap
```

또는 자연어로 — "요리 공부용 LLM 위키 만들어줘", "이 폴더를 지식 볼트로 전환해줘".

세 가지 모드를 자동 판별한다:

| 모드 | 대상 | 동작 |
|---|---|---|
| **new** | 빈 폴더 | 완전한 볼트 신규 구축 |
| **migrate** | 자료가 쌓인 일반 폴더 | 기존 파일을 보존하며 위키로 전환 (파일 이동은 승인 후) |
| **upgrade** | 기존 LLM Wiki | 지식·기록은 그대로, 운영 스킬만 최신 번들로 교체 (교체 전 백업) |

구축 후에는: 자료를 `raw/`에 넣고 `/ingest` → 위키가 채워진다. 세션을 마칠 때 `SAVE` → 다음 세션이 이어받는다.

## 설계 원칙

- **raw는 불변** — 원문은 절대 수정되지 않는다. 요약이 틀려도 근거가 남는다.
- **배포 자족성** — 필요한 모든 자산이 `assets/`에 번들되어 있어, 다른 위키가 있는 환경일 필요가 없다.
- **비파괴** — migrate/upgrade는 기존 내용을 삭제·덮어쓰기하지 않는다. 충돌은 `.wiki-proposed` 제안 파일로 우회한다.

---

## English

**llm-wiki-bootstrap** scaffolds a complete AI-operated knowledge vault (LLM Wiki) from a single conversation, for Claude Code or Codex CLI.

**What you get**: a 3-layer structure (`raw/` immutable sources → `wiki/` distilled knowledge → `Output/` deliverables, after Karpathy's LLM-managed wiki idea), five operational skills installed into the vault (`ingest`, `query`, `lint`, `session-memory`, `brief-tuner`), router docs (CLAUDE.md / AGENTS.md), optional Obsidian Web Clipper templates, and optional graphify knowledge-graph integration.

**Install**: clone into `~/.claude/skills/llm-wiki-bootstrap` (Claude Code) or `~/.codex/skills/llm-wiki-bootstrap` (Codex). Requires Python 3.10+; graphify is optional (`pip install graphifyy`).

**Use**: run `/llm-wiki-bootstrap` or just say "set up a knowledge vault for my cooking research". Three modes are auto-detected: **new** (empty folder), **migrate** (convert an existing folder non-destructively), **upgrade** (refresh the installed skills of an existing wiki, with backup). After setup: drop sources into `raw/` and run `/ingest`; type `SAVE` to persist session state for the next session.

**Design principles**: immutable `raw/`, self-contained distribution (everything bundled under `assets/`), and non-destructive modes — conflicts become `.wiki-proposed` proposal files instead of overwrites.

## License

MIT
