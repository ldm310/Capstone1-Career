# 모집 단위의 합격자료 비교 참고 후보 API

`GET /api/postings/{postingId}/recruit-units/{recruitUnitId}/comparison-candidates`

현재 `PostingCandidateSelectionService`의 결과 중 요청한 모집 단위만 반환한다. 취업 추천, 합격 가능성, 정확도가 검증된 유사도로 해석하지 않는다. GET에서 저장·크롤링·수집 작업을 실행하지 않는다. 기존 외부자료 API·trigger·스키마는 변경하지 않는다.

## HTTP 상태

| 상태 | 의미 |
|---|---|
| 200 SELECTED | 참고 후보가 있음 |
| 200 NO_CANDIDATES | 비교 가능한 대상이지만 통과 후보 없음 |
| 200 NOT_COMPARABLE | 특징/직무 불확실성, 과거 추출 모집 단위, 비IT 모집 단위 등 |
| 400 | 0 이하 ID, 또는 모집 단위가 다른 공고에 속함 |
| 404 | 공고 또는 모집 단위 자체가 없음 |
| 409 | 중복 현재 추출 등 DATA_ERROR, 또는 결과/후보 metadata 불일치 |

존재·소속 확인은 모든 추출 이력에 대해 수행한다. 과거 모집 단위를 404로 위장하지 않고 RECRUIT_UNIT_NOT_CURRENT로 구분한다. 비IT 모집 단위는 NOT_IT_RECRUIT_UNIT이다. 이 두 경우 특징을 계산하지 않아 featureMode/roleCode/confidence는 null이며 roleResolutionSource=UNKNOWN, evidenceCount=0이다. 데이터 오류가 있으면 다른 정상 단위의 결과를 대신 반환하지 않는다. 오류 본문은 기존 `ApiErrorResponse(status,message)` 형식을 사용한다.

## 응답 의미

최상위 postingId/recruitUnitId는 요청 대상이다. selectionStatus/reason/featureMode/roleCode/roleResolutionSource는 해당 모집 단위만의 결과다. confidence/evidenceCount는 **1위 후보 기준**이며 후보가 없으면 각각 null/0이다. roleResolutionSource는 RECRUIT_UNIT_NAME, POSTING_CATEGORY, POSTING_TITLE, UNKNOWN 중 하나다.

- HIGH: 필수 기준을 통과한 참고 후보. 통계적으로 검증된 정확도나 합격 가능성이 아니다.
- LOW: 근거가 적거나 우대·업무 기반으로 찾은 참고 후보. 확정 추천이나 적합 판정으로 표현하지 않는다.
- LOW_EVIDENCE / LOW_CONFIDENCE 표시를 candidate.evidenceFlags로 유지한다.
- coverage의 null은 대상 축이 없어 계산할 수 없다는 뜻이다. 0으로 바꾸지 않는다.
- exclusionReasons는 대상 사유이며 후보가 없으면 후보별 탈락 사유도 중복 제거해 포함한다. 선정 후보에 탈락 조건을 붙여 혼동시키지 않는다.
- policyVersion/taxonomyVersion과 appliedCriteria에 실제 적용된 회사·공고 제한, 최소 coverage·교집합·근거 수, 확장 설정을 반환한다.

각 candidate는 공고·회사 ID/회사명/제목, 모집 단위 ID/이름, confidence, featureMode, evidenceCount, requiredEvidenceCount, supportingEvidenceCount와 여섯 coverage를 포함한다. `intersections.required/preferred/duties`의 capabilityIds/techIds는 해당 범주의 교집합 ID 목록이다. 도메인 DTO·추출 본문·원문 quote·외부자료 content는 직렬화하지 않는다.

## 조회와 트랜잭션

API query service는 READ ONLY/REPEATABLE READ로 소속 검증·선정·후보 metadata를 동일 스냅샷에서 읽는다. 공고/모집 단위 존재 확인 후 기존 선정 서비스를 호출한다. 결과의 후보 모집 단위 ID를 모아 회사명·제목·단위명을 **한 번의 IN 쿼리**로 조회한다. 빈 후보면 metadata 쿼리는 실행하지 않는다. 개별 후보별 findById 반복 조회는 없다.

## Swagger와 검증

Swagger의 합격자료 비교 참고 후보 태그에 HIGH, LOW 보조 비교, 후보 없음, 비교 불가 응답 예시를 제공한다. 400/404/409 오류 schema도 기재한다.

Controller 테스트는 HTTP 상태·요청 단위 필터링·일괄 조회·null coverage·LOW 표시·예시 JSON을 확인한다. 실제 PostgreSQL 테스트는 기존 격리 합성 fixture DB에서 현재 서비스를 호출하는 GET 전후 public 전체 테이블 행 수/해시와 시퀀스 값이 불변인지 검증한다. 이 테스트는 실제 READ ONLY 트랜잭션에서 수행하며 스키마·fixture 변경을 추가하지 않는다.

구현 시 자동 테스트 집계와 실제 팀 DB HTTP 상태·응답 시간·행 수/해시 불변·Swagger 등록 결과는 [API 검증 보고서](verification/comparison-candidates-api-verification.md)에 기록한다. 선정 품질과 현재 정책은 [공고 유사도 선정](posting-similarity.md)을 참고한다.
