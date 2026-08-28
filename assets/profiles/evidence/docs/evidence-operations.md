# Evidence profile operations

이 문서는 `.llm-wiki.json`의 `profile`이 `evidence`일 때 `ingest`, `query`, `lint`, `canon-review`에 추가로 적용되는 계약이다. `wiki/evidence-model.md`와 함께 읽는다.

## Ingest: Raw → Source → Claim

1. `raw/`는 절대 수정하지 않는다.
2. 원문마다 `wiki/sources/`의 1:1 source record를 유지한다. `raw_sha256`과 `structurally_verified`를 의미 검토와 분리하고 `semantic_status: pending|partial|reviewed`를 기록한다. 기존 필드가 없는 Source는 근거 없이 reviewed로 승격하지 않는다.
3. `reviewed` Source는 frontmatter count와 실제 본문 항목 수가 일치해야 하며 모든 근거는 `lines N-M` 또는 `bytes N-M` locator에서 Raw와 일치해야 한다. 긴 텍스트는 start/middle/end와 EOF를 포함하고, 대화는 핵심 결정·다음 행동·chronology를 보존한다.
4. Source가 `Wiki에 반영된 문서`로 가리킨 Claim·Project·Decision은 같은 Raw 경로 또는 Source ID를 frontmatter provenance로 역기록해야 한다. 단순 outgoing 링크와 deterministic stitch edge는 의미 반영이 아니다.
5. 원문에서 재사용 가치가 있는 주장을 **원자적 Claim**으로 추출한다. 요약 문서 전체를 하나의 Claim으로 만들지 않는다.
6. Claim에는 source가 반드시 있어야 하며 evidence의 Source ID·`lines N-M` locator·excerpt가 실제 Raw와 일치해야 한다. 근거 없는 빈칸 채우기는 금지하며 자료가 없으면 `UNKNOWN`으로 남긴다.
7. 기존 Claim과 의미가 같은 경우 새 truth를 만들기보다 같은 Claim family에 source를 추가한다. 단, source 자체는 모두 보존한다.
8. relation은 최소 `originates`, `supports`, `contradicts`, `derived_from`, `mentions`를 구분한다.
9. 유효한 상충 Claim이 발견되면 한쪽을 덮어쓰지 말고 `wiki/conflicts/`에 conflict record를 만든다.
10. 검증 가능한 가설이면 필요에 따라 `wiki/questions/open/` 또는 `wiki/experiments/` 후보를 만든다.
11. 대화의 프로젝트 선택·권고·대체 이력은 `wiki/decisions/`에 저장한다. Decision은 Project, Source ID, Raw locator, next actions, chronology, supersedes/superseded_by를 가지며 Claim/Canon 상태와 섞지 않는다. 각 next action과 chronology도 자체 Source ID·`lines N-M`·excerpt를 가져 Raw와 대조 가능해야 한다.
12. Ingest는 **Canon을 자동 수정하지 않는다.** Canon candidate/review 필요 상태까지만 만든다.

## Query modes

질의 전 `wiki/evidence-model.md`를 읽고 모드를 정한다.

### answer

`wiki/canon/` → `CONFIRMED/SUPPORTED` Claim → `OBSERVED` Claim → 필요한 Raw 순으로 내려간다. 답변에는 확인됨/지지됨/추론/가설/미확인/충돌 중 같은 epistemic state를 구분한다.

### research

Canon뿐 아니라 `wiki/claims/`, `wiki/conflicts/`, `wiki/experiments/`, `wiki/questions/`, 관련 Raw까지 조사한다. Canon보다 최신인 evidence가 있으면 “Canon 재검토 필요”를 명시한다.

### verify

대상 Claim의 source locator를 따라 실제 Raw를 확인한다. supporting/contradicting evidence와 lineage를 함께 본다.

### challenge

현재 결론을 확인하는 자료보다 반증 가능성이 있는 `DISPUTED`, `REJECTED`, conflicts, 실패 실험, 최신 Raw를 우선 찾는다. 반대 근거가 없다는 사실을 곧바로 진실의 증명으로 취급하지 않는다.

### trace

다음 체인을 가능한 한 끊김 없이 보여준다.

```text
CANON → CLAIM → EVIDENCE / EXPERIMENT → SOURCE RECORD → RAW locator
PROJECT DECISION → PROJECT → SOURCE RECORD → RAW locator
```

### compare

복수 Claim을 statement 유사도만으로 비교하지 말고 source quality, independence/lineage, direct observation, experiment, contradiction을 함께 비교한다.

## Lint: epistemic integrity

일반 링크/frontmatter 검사에 더해 다음을 점검한다.

- source 없는 Claim
- 존재하지 않는 source/claim/experiment/conflict ID
- Canon entry에서 Claim으로 역추적 불가
- Claim에서 Raw locator까지 역추적 불가
- `parent_sources` cycle 또는 명백한 lineage 단절
- `CONFIRMED`인데 직접 근거/검증 근거가 전혀 기록되지 않은 Claim
- `REJECTED` Claim을 현재 Canon의 근거로 사용
- unresolved conflict의 Claim을 충돌 표시 없이 단정적으로 사용
- orphan experiment / orphan conflict
- 같은 statement의 명백한 중복 Claim family
- source record의 `raw_sha256`와 현재 Raw가 불일치
- Source의 structural/semantic 상태 혼합, semantic partial/pending 은폐
- 긴 Source의 start/middle/EOF coverage 또는 located quote 누락
- Source self-reported count와 실제 본문 항목 수 불일치
- Source가 반영했다고 한 Claim·Project·Decision의 역 provenance 누락
- 반복 Source boilerplate와 deterministic stitch를 semantic evidence로 오인

의미 판단이 필요한 문제는 자동 수정하지 않는다. 특히 Claim 상태 변경, conflict 해소, Canon 승격/강등은 review 대상으로 남긴다.

## Canon review

`canon-review`는 읽기 우선이다. 기본 동작은 recommendation 생성이며 자동 승격이 아니다. 사용자가 명시적으로 승격/상태 변경을 요청한 경우에만 대상 파일을 수정한다.
