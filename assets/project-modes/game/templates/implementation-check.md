---
type: game_implementation_check
check_id: "IMPL-000"
subject_id: ""
subject_type: "feature|system|level|content|ui|asset|technical"
relation: implements
expected_spec: ""
source_revision: "UNKNOWN"
checked_project_revision: "UNKNOWN"
checked_vault_revision: "UNKNOWN"
checked_project_dirty: false
checked_spec_digest: "UNKNOWN"
checked_spec_digest_version: 1
checked_code_fingerprints: []
checked_code_fingerprint_version: 1
sync_baseline_status: pending
build_id: "UNKNOWN"
implementation_status: unknown
validation_status: untested
checked_paths: []
playtest_refs: []
decision_refs: []
evidence_refs: []
checked_at: "YYYY-MM-DD"
---

# 구현 확인 — 대상명

## 확인 범위

- 기준 설계 문서:
- 확인한 저장소/프로젝트:
- revision/branch:
- build/platform/configuration:
- 제외 범위:

## 동기화 기준점

- `subject_id`는 기준 기획 문서의 안정된 ID다.
- `checked_paths`는 `project/relative/path#symbol@locator` 형식으로 적는다.
- 실제 기획과 구현을 함께 검사한 뒤에만 다음 명령으로 기준점을 확정한다.

```bash
python tools/game_trace.py accept wiki/game/implementation/IMPL-000.md
```

이 명령은 검사 당시의 canonical 기획 digest, 각 코드 경로의 fingerprint, project/vault revision을 이 문서 frontmatter에 기록한다. 이후 `rebuild`는 이 기준점과 현재 기획·코드를 비교해 `in_sync`, `design_changed`, `code_changed`, `both_changed`, `unverified`, `missing`을 판정한다.

- `sync_baseline_status: accepted`는 기획과 코드를 사람이 실제로 대조했다는 뜻이다.
- dirty working tree를 기준으로 확정하는 것은 기본 거부된다. 반드시 필요한 경우에만 `--allow-dirty`를 명시한다.
- 동일 기획·코드 관계를 다시 확인할 때는 새 확인 문서를 남겨 이력을 보존한다.

## 기대 동작

설계 문서에서 검증할 수 있는 문장만 요약한다.

## 확인한 live source

| 경로/심볼/씬/데이터 | 직접 확인한 사실 | locator |
|---|---|---|
| | | |

## 비교 결과

| 항목 | 판정 | 근거 |
|---|---|---|
| | 일치 / 부분 일치 / 불일치 / 확인 불가 | |

## 런타임 검증

- 실행한 명령/테스트:
- 실행 결과:
- 재현 절차:
- 로그/캡처/빌드 참조:

## 차이와 위험

- 설계에는 있으나 구현에 없음:
- 구현에는 있으나 설계에 없음:
- 조건부 또는 플랫폼 차이:
- 회귀 위험:

## 결론

- `implementation_status` 근거:
- `validation_status` 근거:
- 확인하지 못한 것:
- 다음 행동:
