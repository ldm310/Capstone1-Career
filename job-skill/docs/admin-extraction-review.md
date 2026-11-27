# 관리자 추출 검토

웹 `/admin`과 GET/PATCH `/api/admin/extraction-reviews`는 로그인한 ADMIN만 사용한다.
공고 검토는 웹 namespace와 무관한 공유 데이터이며 `public.extraction_run`을 직접 조회·수정한다.
사용자 계정·권한은 기존 `career_lv_member`의 namespace를 그대로 사용한다.

| 관리자 동작 | review_result | review_feedback | reviewed_at |
|---|---|---|---|
| 넘기기 (PASS) | 제외 | NULL | DB 현재 시각 |
| 피드백 저장 및 재추출 요청 | 다시 | 입력한 피드백 | DB 현재 시각 |

`정상`은 팀의 검토 완료 값으로 읽어 표시한다. 쓰기는 세 컬럼만 사용하며,
검토 전의 현재 추출 결과에만 허용한다. 이미 검토됐거나 새 추출 결과로 교체됐거나,
목록을 조회한 뒤 검토 값이 바뀐 경우 409로 처리해 다른 판단을 덮어쓰지 않는다.

목록은 `is_current=true`이고 `review_reasons`가 있는 추출 결과가 대상이다.
기본 필터는 `review_result IS NULL`인 검토 대기이며 전체·제외·다시·정상 필터도 제공한다.
검색 조건별 총 건수, 전체 페이지 수, 20개 단위 이동을 지원한다.
‘처리 중’이나 실패 횟수는 해당 테이블에서 알 수 없으므로 표시하지 않는다.

Airflow는 `db_queries.pending_postings`에서 처리 가능한 진행 공고 중 `다시`를 읽고,
그 `review_feedback`을 추출 입력에 추가한다. 새 추출 결과가 저장되면 이전 실행은
`is_current=false`가 되며 새 결과의 검토 값은 NULL이다. `제외`는 수정·마감 확인 대상에서도 빠진다.
웹은 Airflow 실행·LLM 호출을 직접 시작하지 않는다. 별도 검토 namespace 설정은 필요 없다.

DB 컬럼과 팀원 권한은 팀원이 추가한 `010_review_decision.sql`을 사용한다.
웹 초기 설정은 공고 검토용 테이블을 만들거나 목록 조회 시 동기화하지 않는다.
`008_recruit_unit_job.sql`은 공고 직무용 마이그레이션으로 유지한다.

기존 보조 검토 테이블 정리 순서:

1. 새 웹을 배포하고 관리자 목록 응답의 `storage: extraction_run`과 표시 내용을 확인한다.
2. 기존 테이블에 보존할 관리자 처리 내역이 없는지 확인·백업한다.
3. 기존 테이블 소유자인 team으로 `deploy/web/retire-extraction-review.sql`을 실행한다.
   처리·피드백·이력이 있으면 삭제를 중단한다. 다른 종속 객체도 CASCADE로 지우지 않는다.
4. 관리자 목록을 다시 확인한다. 삭제 후에는 옛 검토 테이블을 쓰던 웹 버전으로 롤백하지 않는다.

검증: 프론트 API 계약 테스트의 격리 PostgreSQL 시험은 읽기와 세 컬럼 UPDATE만 허용한
역할로 실제 쿼리를 실행한다. RDS의 공고 검토 값을 바꾸거나 Airflow·LLM을 호출하지 않는다.
