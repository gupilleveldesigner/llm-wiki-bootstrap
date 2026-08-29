---
type: game_feature_spec
feature_id: "FEATURE-000"
title: ""
design_status: proposed
implementation_status: unknown
validation_status: untested
decision_status: proposed
production_status: backlog
owners: []
depends_on: []
supersedes: []
live_paths: []
implementation_check_refs: []
build_refs: []
playtest_refs: []
decision_refs: []
evidence_refs: []
updated: "YYYY-MM-DD"
---

# 기능명

<!-- GAME-SYNC:DESIGN-START -->
## 플레이어 경험

이 기능으로 플레이어가 무엇을 느끼고 무엇을 할 수 있어야 하는가?

## 문제와 목표

- 해결하려는 문제:
- 성공 조건:
- 범위 밖:

## 동작 계약

### 진입 조건

### 핵심 흐름

### 상태와 전이

### 입력과 출력

### 실패·취소·예외

## 다른 시스템과의 관계

- 의존 시스템:
- 영향받는 콘텐츠:
- UI/피드백:
- 저장·네트워크·플랫폼 제약:
<!-- GAME-SYNC:DESIGN-END -->

## 기획 ↔ 코드 추적

- `live_paths`에는 `project/relative/path#symbol@locator` 형식으로 현재 구현 후보를 적는다.
- 실제 확인 결과는 `implementation_check_refs`의 구현 확인 문서에 기록한다.
- `live_paths`가 있다고 해서 자동으로 `implemented`가 되지는 않는다.
- `GAME-SYNC:DESIGN` 구간의 의미가 바뀌면 기획 digest가 바뀌어 기존 구현 관계가 `design_changed` 또는 `both_changed`가 된다.

## 실제 구현 상태

- 확인한 live path/symbol/scene/data:
- 확인한 revision/build:
- 구현과 설계의 차이:
- 확인 불가 항목:

## 검증 계획과 결과

- 검증 질문:
- 테스트 조건:
- 관찰 결과:
- 실패·제약:

## 결정과 변경 이력

- 관련 결정:
- 대체된 문서/결정:
- 다음 검토 조건:
