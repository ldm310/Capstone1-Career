# Comparison Candidates API 검증

검증일: 2026-11-08 (KST). 기준 HEAD: `337837ff18659d0f48c42ebb9ebd9fc5ec7ea09f`와 커밋 전 API 신규 파일 9개. 이 보고서는 직전 실DB 검증 결과와 구현 시 최종 자동 테스트 기록을 정리한 것이다. 문서 정리 과정에서 DB 연결이나 테스트를 다시 실행하지 않았다.

공식 계약은 [Comparison Candidates API](../comparison-candidates-api.md), 선정 품질과 잔여 위험은 [유사도 검증](posting-similarity-verification.md)을 참고한다.

## 자동 테스트

Java 21, 격리 PostgreSQL 18 합성 fixture 환경에서 Backend 전체 **145건 통과**, 실패·오류·skip 0건. 기존 128건에 Controller 13건, 실제 생성 OpenAPI 경로·전용 schema·예시 검증 1건, PostgreSQL GET 검증 3건을 추가했다. 전체 테스트는 캐시 없이 실행했으며 이 실행에서는 팀 DB에 연결하지 않았다.

최종 성공 기록: 자동 테스트 결과 (`work/comparison-candidates-api-tests-1f49dedc4f324314bf5d664434c0fbc6/verification.json`; 로컬 검증 산출물, 커밋 제외). 중간 실패 실행은 최종 결과에 합산하지 않는다.

## 실제 HTTP 응답

대상 경로: `GET /api/postings/{postingId}/recruit-units/{recruitUnitId}/comparison-candidates`.

| 공고 ID | 모집 단위 ID | HTTP | selectionStatus | 후보 수 | HIGH | LOW | 응답 시간(ms) |
|---|---|---|---|---|---|---|---|
| 1447 | 2509 | 200 | SELECTED | 5 | 5 | 0 | 2095.92 |
| 1786 | 3356 | 200 | NO_CANDIDATES | 0 | 0 | 0 | 775.22 |
| 210 | 309 | 200 | NOT_COMPARABLE | 0 | 0 | 0 | 1104.14 |
| 1447 | 3356 (다른 공고 소속) | 400 | 해당 없음 | 해당 없음 | 해당 없음 | 해당 없음 | 144.44 |
| 9223372036854775807 (없음) | 2509 | 404 | 해당 없음 | 해당 없음 | 해당 없음 | 해당 없음 | 49.33 |
| 1447 | 9223372036854775807 (없음) | 404 | 해당 없음 | 해당 없음 | 해당 없음 | 해당 없음 | 60.28 |
| 459 | 4006 | 200 | SELECTED | 4 | 0 | 4 | 969.15 |
| 12 | 20 | 200 | SELECTED | 3 | 0 | 3 | 790.36 |

각 요청을 한 번씩 측정했다. 첫 요청은 임시 서버 시작 후 최초 API 호출이다. 네트워크와 초기화 비용을 포함하며 반복 부하 실험이나 지연 시간 보장으로 해석하지 않는다.

## DB 불변과 응답 검증

- 접속값은 메모리와 자식 프로세스 환경에만 전달했다. JDBC 세션 기본값과 실제 연결의 `default_transaction_read_only=on`, `transaction_read_only=on`을 확인했다. 연결 검사 29회 통과. API 서비스는 READ ONLY·REPEATABLE READ로 실행했다.
- 초기화·migration을 비활성화하고 쓰기 SQL은 실행하지 않았다. API 호출 전후 별도의 새 트랜잭션으로 public 14개 테이블 각각의 행 수와 정렬된 JSON 행 내용 해시를 계산했다. 두 스냅샷은 동일했고 시퀀스 값도 동일했다. 같은 MVCC 스냅샷을 재사용해 불변으로 판단하지 않았다.
- 정책 `keyword-mvp-2`, 직무 매핑 `roles-mvp-2`를 확인했다. confidence·featureMode·evidenceCount·appliedCriteria를 검사하고, DB 표준 ID 집합으로 교집합·coverage·필수/보조 근거 수를 독립 계산해 대조했다.
- 계산 불가 coverage **26곳**이 필드 누락이나 0 변환 없이 `null`로 유지됐다. 후보 없는 응답의 confidence는 null, evidenceCount는 0이었다.
- 회사명·공고 제목을 응답과 DB 사이에서 메모리 해시로 대조했다. 값과 원문은 보고서에 보관하지 않았다. 후보가 있는 요청은 metadata IN 쿼리 **1회**, 후보 없는 요청은 **0회**였다.
- LOW 7개 후보의 LOW_EVIDENCE 또는 LOW_CONFIDENCE 표시를 확인했다. Swagger도 LOW를 참고 후보로 설명하며 추천·적합 판정이나 합격 확률을 뜻하지 않는다고 명시한다.

## Swagger와 판정

`/swagger-ui/index.html`, `/v3/api-docs`, `/v3/api-docs/swagger-config` 모두 HTTP 200. 신규 GET 경로와 응답 예시가 등록됐고 Swagger 설정은 `/v3/api-docs`를 참조했다.

최종 검증에서 API 문제는 발견하지 않았다. 참고 후보 조회 기능은 이 검증 범위에서 커밋 가능하다. 선정 품질의 잔여 위험까지 해소됐다는 뜻은 아니다. 실제 팀 DB에서는 409·과거 추출·비IT 사례를 추가 호출하지 않았으며 관련 분기는 자동 테스트의 검증 범위다.

API 소스 수정·commit·push는 수행하지 않았다. 검증용 실행기의 초기화 문제는 임시 실행기에서 해결했고, 종료 후 임시 서버와 소스·클래스·classpath 파일을 삭제했다. 실DB HTTP 검증의 별도 JSON은 생성하지 않아 이 보고서가 세션 결과의 보존본이다.
