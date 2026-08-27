# Evidence profile operations

이 문서는 `.llm-wiki.json`의 `profile`이 `evidence`일 때 `ingest`, `query`, `lint`, `canon-review`에 추가로 적용되는 계약이다. `wiki/evidence-model.md`와 함께 읽는다.

## Ingest: Raw → Source → Claim

1. `raw/`는 절대 수정하지 않는다.
2. 원문마다 `wiki/sources/`의 1:1 source record를 유지한다. 기존 ingest 계약의 `raw_sha256`에 더해 가능한 경우 provider/model, created/ingested time, source locator, `parent_sources`, verification/epistemic 상태를 기록한다.
3. 원문에서 재사용 가치가 있는 주장을 **원자적 Claim**으로 추출한다. 요약 문서 전체를 하나의 Claim으로 만들지 않는다.
4. Claim에는 source가 반드시 있어야 한다. 근거 없는 빈칸 채우기는 금지하며 자료가 없으면 `UNKNOWN`으로 남긴다.
5. 기존 Claim과 의미가 같은 경우 새 truth를 만들기보다 같은 Claim family에 source를 추가한다. 단, source 자체는 모두 보존한다.
6. relation은 최소 `originates`, `supports`, `contradicts`, `derived_from`, `mentions`를 구분한다.
7. 유효한 상충 Claim이 발견되면 한쪽을 덮어쓰지 말고 `wiki/conflicts/`에 conflict record를 만든다.
8. 검증 가능한 가설이면 필요에 따라 `wiki/questions/open/` 또는 `wiki/experiments/` 후보를 만든다.
9. Ingest는 **Canon을 자동 수정하지 않는다.** Canon candidate/review 필요 상태까지만 만든다.

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

의미 판단이 필요한 문제는 자동 수정하지 않는다. 특히 Claim 상태 변경, conflict 해소, Canon 승격/강등은 review 대상으로 남긴다.

## Canon review

`canon-review`는 읽기 우선이다. 기본 동작은 recommendation 생성이며 자동 승격이 아니다. 사용자가 명시적으로 승격/상태 변경을 요청한 경우에만 대상 파일을 수정한다.
