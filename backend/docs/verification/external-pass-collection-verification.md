# 외부 합격자료 수집 연결·상태 API 검증

검증일: 2026-11-08 (KST). 기존 기준 커밋은 `337837ff18659d0f48c42ebb9ebd9fc5ec7ea09f`이며 H2 수정·문서 정리·비교 후보 API를 먼저 별도 커밋한 뒤 신규 기능을 검증했다. 접속값·비밀번호·로컬 사용자명·원문·개인정보는 이 보고서에 보관하지 않는다.

실행 흐름·수집 정책·Docker·Airflow·응답 계약은 [공식 기능 문서](../external-pass-collection.md)에 있다.

## 오늘 채용공고와 기존 데이터

| 항목 | 확인 결과 |
|---|---|
| 브랜치 | feature/BE |
| 팀 DB 공고 수, 실행 전후 | 1,945 → 1,945 |
| 최신 collected_at, KST | 2026-11-05 16:17:53.398485 |
| 2026-11-08 KST collected_at 공고 | 0건 |
| 현재 추출 연결 공고 | 1,944건 |
| 중복 공고 키·복수 현재 추출 | 각각 0건 |
| 기존 Backend 목록·상세 | 각각 HTTP 200, 목록 총수 1,945 |
| 기존 public pipeline 테이블 | 14개, migration·요청 등록 전후 행 수·내용 해시 동일 |

오늘 신규·변경·마감 반영과 신규 추출은 **실행하지 않았다**. 현재 계정에는 기존 공고·추출 INSERT/UPDATE/DELETE 권한이 없고 사용자도 이를 금지했다. 기존 Daily의 운영 실행 환경·실행 이력·LLM 키·비용 집계 파일에는 접근하지 못했다. 로컬에서 동작 중인 Airflow는 없으며 원격 실행 여부는 확인하지 못했다. DB의 오늘 0건은 원본 사이트에 신규 공고가 없다는 결론이 아니다. 신규·변경·마감·추출 성공/실패 수와 예상 비용은 미산정이다. 수집 형식·원본 pipeline 코드는 변경하지 않았다.

## 제한 권한과 실제 팀 DB migration

READ ONLY로 기존 공고 테이블의 SELECT·REFERENCES, public CREATE를 확인했다. `tech_capability`는 SELECT만 가능했고 REFERENCES는 없었다. 기존 공고 쓰기 권한은 부여하거나 우회하지 않았다.

`python -m external_pass_crawler.migrate`의 `public-07`을 팀 DB에 **실제로 적용**했다. SQL 04·07의 논리 계약을 고정 식별자 매핑으로 신규 소유 public 테이블에 설치했다. 신규 스키마 생성, 기존 객체 변경, DROP·TRUNCATE·기존 테이블 DELETE는 수행하지 않았다.

| 신규 소유 테이블 | 실제 행 수 |
|---|---|
| public.external_pass_company_collection | 3 |
| public.external_pass_material | 0 |
| public.external_pass_posting_material | 0 |
| public.external_pass_collection_request | 1 |
| public.external_pass_collection_candidate | 5 |
| public.external_pass_schema_migration | 1 |

6개 모두 실행 계정 소유다. FK는 기존 public 회사·공고·모집 단위와 신규 소유 객체만 참조하며 **tech_capability FK는 0개**다. 재적용은 already_applied=true로 끝났고 기존 pipeline 14개 테이블은 불변이었다. 설치 후에도 기존 posting INSERT·UPDATE 권한은 false다. 소유 테이블의 행 잠금·SKIP LOCKED는 유지하고 기존 pipeline에는 UPDATE 권한이 필요한 명시적 행 잠금을 사용하지 않았다.

## 실제 등록과 팀 DB API

임시 Backend를 팀 DB READ ONLY 설정으로 실행했다. 현재 Java 비교 후보 API에서 공고 1447·모집 단위 2509의 결과를 받아 Python이 유사도를 다시 계산하지 않고 요청 출처를 등록했다. 외부 네트워크를 금지한 register-only 경로로 처리했다.

- 선정 후보 5개, HIGH 5개, LOW 0개.
- 고유 회사 3곳을 PENDING으로 등록했다.
- 수집 attemptCount는 모두 0이며 실제 크롤링·자료 저장은 실행하지 않았다.
- 같은 대상 재등록은 같은 request ID를 사용했고 요청·후보·회사 작업 행 수가 증가하지 않았다.
- 기존 public pipeline 행 수·내용 해시는 등록 전후 동일했다.

요청 경로는 `GET /api/postings/{postingId}/recruit-units/{recruitUnitId}/external-pass-collection-status`다.

| 공고/모집 단위 | HTTP | candidateSelectionStatus | collectionStatus | 자료 수 |
|---|---|---|---|---|
| 1447/2509 | 200 | SELECTED | PENDING | 0 |
| 1786/3356 | 200 | NO_CANDIDATES | INSUFFICIENT | 0 |
| 210/309 | 200 | NOT_COMPARABLE | INSUFFICIENT | 0 |
| 1447/3356 | 400 | 해당 없음 | 해당 없음 | 해당 없음 |
| 없는 공고/2509 | 404 | 해당 없음 | 해당 없음 | 해당 없음 |
| 1447/없는 모집 단위 | 404 | 해당 없음 | 해당 없음 | 해당 없음 |

조회 전후 **신규 저장소까지 포함한 public 20개 테이블**의 행 수·내용 해시가 동일했다. 기존 자료·키워드 GET도 새 public 저장소를 사용해 각각 200이었다. `/v3/api-docs`에 새 상태 API가 등록됐다. 실제 팀 DB에 오류 데이터를 주입하지 않았으며 409는 격리 PostgreSQL 및 실제 로컬 HTTP 검증에서 확인했다.

실제 응답 요약:

```json
{
  "postingId": 1447,
  "recruitUnitId": 2509,
  "candidateSelectionStatus": "SELECTED",
  "collectionStatus": "PENDING",
  "selectedCandidateCount": 5,
  "highCandidateCount": 5,
  "lowCandidateCount": 0,
  "requestedCompanyCount": 3,
  "readyCompanyCount": 0,
  "materialCount": 0,
  "startedAt": null,
  "completedAt": null,
  "retryable": false,
  "safeErrorCode": null,
  "userMessage": "합격자료 수집을 기다리고 있습니다.",
  "policyVersion": "keyword-mvp-2"
}
```

## 테스트와 실제 사이트 제한

| 검증 | 최종 결과 |
|---|---|
| H2 수정 후 기존 Backend 전체 | 145건 통과, 실패·오류·skip 0 |
| 신규 기능 포함 Backend 전체 | 161건 통과, 실패·오류·skip 0 |
| 크롤러 전체 | 66건 통과, 실패·오류·skip 0 |
| PostgreSQL Repository 기존 7건 | 통과 |
| 상태 API 실제 PostgreSQL 2건 | 통과, public·자료·시퀀스 불변 |
| 제한 권한 역할 | public CREATE·SELECT·REFERENCES만으로 설치·재실행·자료 연결 통과 |
| 실제 HTTP 연동 | Java 후보 GET → Python 등록·fixture worker → 상태 200/400/404/409 통과 |
| 기존 자료·키워드 API의 public 저장소 | 실제 HTTP 200, 자료 수·unmappedKeywords 확인 |
| H2 public 스키마 삭제 오류 | 없음 |
| Docker | 빌드·비root UID 10001·읽기 전용 CLI 실행·register-only 확인 |
| 이미지 env/work/pyc 포함 | 없음 |
| Compose | 구성 검사 통과 |
| 동반 Airflow DAG | 문법 확인, 운영 설치·실행은 미수행 |

팀 DB 회사명을 외부 검색에 전달하는 dry-run은 자동 승인 검토가 정보 외부 전달 위험을 이유로 거부하여 실행하지 않았다. 팀 DB를 사용하지 않는 공개 기업명 기반 대체 dry-run은 기존 Adapter의 ACCESS_RESTRICTED를 감지해 즉시 중단했다. 우회·재시도·다른 회사 재요청은 하지 않았다. 실사이트 자료 저장은 0건이다. 팀 DB 요청 등록에는 외부 사이트 호출 자체가 없는 경로를 사용했다.

검증 중 발견한 Swagger JSON 미디어 타입 누락과 다중 직무 공고 재연결 문제를 수정하고 전체 검증을 통과했다. Backend가 판별한 후보 모집 단위의 표준 직무로 연결하므로 공고 제목에 직무명이 없어도 자료를 잘못 EXCLUDED로 바꾸지 않는다. 저장 자료는 있으나 작업 행이 없는 회사도 재크롤링 없이 재사용한다.

재현 코드는 [전체 검증 실행기](../../../db/tests/verify_external_collection.py), [실제 HTTP smoke](../../../db/tests/smoke_external_collection_http.py), [DB migration 테스트](../../../data-pipeline/external-pass-crawler/tests/test_collection_migration.py)에 있다. 실제 팀 접속정보를 읽지 않고 새 임시 PostgreSQL만 사용한다. 모든 검증용 DB·서버는 종료·제거했으며 기존 서비스는 보존했다.

## 남은 운영 작업

1. 기존 Daily 운영 계정으로 오늘 신규·변경·마감을 반영하고 저장 성공·비용·중복을 검증해야 한다. 현재 읽기 계정으로 기존 pipeline을 쓰거나 복제하지 않는다.
2. 운영 Backend에 새 코드와 동반 DAG를 배포해야 한다. 이번 팀 DB 검증용 Backend는 종료했으며 기존 서비스 컨테이너를 교체하지 않았다.
3. 공개 사이트 접근 제한의 원인을 검토하기 전 실제 수집 worker를 실행하지 않는다. 현재 세 회사는 PENDING이고 자료는 없다.
4. 대량 유입용 영구 dispatch cursor는 후속 작업이다. 현재 대상 한도와 같은 시간 창 재실행 절차는 공식 문서에 기록했다.
5. 임베딩은 추가하지 않았다. 이후 `PostingSimilarityScorer` 확장 지점에서 검토하며 정책·근거·HIGH/LOW·출처 계약은 유지한다.
