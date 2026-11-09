# 공고 유사도 선정 검증

검증일: 2026-11-07. 문서 정리·API 후속 결과 반영일: 2026-11-08 (KST). 기준 커밋: `337837ff18659d0f48c42ebb9ebd9fc5ec7ea09f`. 공식 정책은 [공고 유사도 선정](../posting-similarity.md), 후속 HTTP 검증은 [Comparison Candidates API 검증](comparison-candidates-api-verification.md)에 있다. 이 보고서의 전수 수치와 20건 점검은 2026-11-07 당시 결과이며 문서 정리 과정에서 DB 검증을 다시 실행하지 않았다.

## 판정

**v2는 참고 후보 조회에 사용할 수 있으며, 후속 API 구현과 2026-11-08 실DB HTTP 검증이 완료됐다.** confidence·featureMode·evidenceCount·근거·제외 사유를 그대로 전달하고 LOW 결과를 확정 추천과 구분하는 조건이다. 자동 합격자료 수집 대상을 확정하거나 검증된 유사도/정확도로 표현하는 API는 아직 보류를 권장한다. 일반 capability와 넓은 공고 분류에 따른 잔여 오판이 있으며 HIGH도 정책 통과 수준이지 정확도 보증이 아니다.

## 구현 정책

- 설정 한 곳에서 ML 엔지니어·머신러닝 엔지니어·Machine Learning Engineer를 ml_engineer로 인식한다. 모집 단위명 우선·복수 구체 직무 AMBIGUOUS 규칙을 유지한다.
- 일반 REQUIRED 후보는 capability coverage ≥0.5(축 존재 시), tech 교집합 ≥1(축 존재 시), 필수 근거 합계 ≥2를 모두 통과해야 한다.
- 필수 특징이 정확히 1개이면 그 필수 일치 외에 우대·업무의 다른 표준 ID 근거 ≥1을 요구한다. 이 예외만 필수+보조 근거로 최소 총 2개를 충족하며 LOW_EVIDENCE/LOW로 표시한다.
- 필수 특징이 없으면 동일 직무의 우대·업무만 사용한다. 고유 대상 특징 ≥2, 교집합 ≥2가 있어야 FALLBACK_FEATURES/LOW/LOW_CONFIDENCE로 선정한다. 부족하면 REQUIRED_FEATURES_MISSING이다.
- 근거는 유형(capability/tech)+ID로 구분한다. 우대·업무 중복과 이미 일치한 필수 ID 재등장은 추가 근거로 세지 않는다.
- 순위는 기존 필수 capability→필수 tech→우대→업무 순서를 유지한다. 회사 3개·회사별 공고 2개·최종 공고 5개 제한도 유지한다.
- 직무군 확장은 false이며 허용 조합표가 생기기 전에는 true 설정도 거부한다. SAME_IT_DOMAIN은 사용하지 않는다.

## 테스트와 DB 접근

Java 21에서 기존·신규 Backend 테스트 **128건 통과, 실패 0, 오류 0, skip 0**. 실제 PostgreSQL Repository 7건과 기존 PostgreSQL 회귀 1건도 포함한다. 테스트 DDL/합성 데이터 준비는 새 격리 로컬 PostgreSQL 18 DB에서만 수행했고 기존 DB·컨테이너는 보존했다.

팀 DB는 기존 env를 메모리에서 읽어 READ ONLY/REPEATABLE READ로 연결했다. 연결 직후·표본 호출 중·종료 시 read-only를 확인했으며 SELECT와 트랜잭션 제어만 실행했다. migration·쓰기 SQL은 실행하지 않았다. 현재 Repository 결과를 메모리에 재사용해 전수 서비스를 계산하고 20개 사례는 실제 Repository의 전체 DTO와 동일함을 대조했다. 원문·개인정보·접속값은 결과에 저장하지 않았다.

공고 1,945개, 현재 IT 모집 단위 2,602개로 전회 코퍼스 규모와 같다. 정책 `keyword-mvp-2`, 매핑 `roles-mvp-2`다. 전회와 개별 행 내용까지 동일하다는 별도 해시는 없으므로 기간별 스냅샷 비교이며 무작위 정확도 실험은 아니다.

## 이전 결과와 비교

| 항목 | 이전 v1 | 현재 v2 |
|---|---|---|
| 후보 선정 성공률 | 1,812 / 2,602 (69.64%) | 2,185 / 2,602 (83.97%) |
| 비교 불가 비율 | 790 / 2,602 (30.36%) | 347 / 2,602 (13.34%) |
| 후보 없음 | 0 | 70 (2.69%) |
| 필수 tech 존재·교집합 0인 선정 쌍 | 494 / 6,857 (7.20%) | 0 / 7,734 (0%) |
| LOW_EVIDENCE | 태그 미제공 | 131개 대상 / 457개 선정 쌍 |
| FALLBACK_FEATURES | 0 | 443개 대상 / 1635개 선정 쌍 |
| 직무군 확장 | 2개 대상 | 0개 대상 |
| 최종 선정 쌍 | 6857 | 7734 |

필수 특징이 없던 751개 중 **443개가 보조 비교로 선정**됐다. 297개는 REQUIRED_FEATURES_MISSING이며 나머지 11개는 직무가 모호해 제외된다. AMBIGUOUS_ROLE 전체는 50개다. 선정 증가를 정확도 향상으로 해석하지 않는다.
HIGH 선정 쌍은 5,642개, LOW 선정 쌍은 2,092개(27.05%)다. LOW_EVIDENCE와 FALLBACK_FEATURES는 서로 다른 대상 모드다.

## 직무별 선정 결과

| 직무 | 대상 | 선정 | 선정률 | 비교 불가 | 후보 없음 | LOW_EVIDENCE 대상 | FALLBACK 대상 |
|---|---|---|---|---|---|---|---|
| frontend | 29 | 25 | 86.21% | 2 | 2 | 3 | 2 |
| backend | 1430 | 1282 | 89.65% | 133 | 15 | 76 | 258 |
| ml_engineer | 100 | 89 | 89.00% | 11 | 0 | 2 | 17 |
| data_engineer | 569 | 430 | 75.57% | 114 | 25 | 31 | 98 |
| devops | 112 | 102 | 91.07% | 7 | 3 | 8 | 35 |
| qa | 17 | 3 | 17.65% | 6 | 8 | 1 | 0 |

ML 판별은 87→100개, backend는 1,437→1,430개, data_engineer는 575→569개로 바뀌었다. 13개가 공고 분류 fallback 대신 모집 단위명으로 직접 판별됐다. 전체 판별 성공은 2,552개, AMBIGUOUS 50개, UNKNOWN 0개다. 전회 직무별 전체 선정률은 보존되지 않았으므로 직무별 이전 성공률을 추정하지 않는다.

## 오판·누락 위험 20건 수동 점검

이전 문제와 경계 사례를 지정해 직무명·표준 특징·교집합·상위 후보를 수동으로 검토했다. 무작위 표본이나 20건의 확정 오판이라는 뜻은 아니며 원문 전체는 조회하지 않았다.

| # | 공고 | 모집 단위 | 직무 | 결과 | 모드 | 최종 후보 공고 | 1위 confidence | 수동 점검 |
|---|---|---|---|---|---|---|---|---|
| 1 | 1786 | 3356 / AI 프론트엔드 엔지니어 (인턴직) | frontend | NO_CANDIDATES | REQUIRED | 없음 | — | 제외 정상·추출 점검 필요 |
| 2 | 1447 | 2509 / ML 엔지니어 | ml_engineer | SELECTED | REQUIRED | 797, 1778, 187, 1530, 946 | HIGH | 매핑 개선·비교 가능 |
| 3 | 385 | 564 / QA | qa | NO_CANDIDATES | REQUIRED | 없음 | — | 직무군 확장 차단 정상 |
| 4 | 1772 | 3286 / QA Engineer | qa | NO_CANDIDATES | REQUIRED | 없음 | — | 직무군 확장 차단 정상 |
| 5 | 459 | 4006 / Telco & CP 업무지원 | backend | SELECTED | REQUIRED | 1115, 1757, 588, 836 | LOW | LOW 참고용·오판 위험 잔존 |
| 6 | 12 | 20 / 전산 | backend | SELECTED | FALLBACK_FEATURES | 1524, 1526, 113 | LOW | 보조 비교 유용·LOW |
| 7 | 510 | 804 / 프론트엔드 개발자 | frontend | SELECTED | FALLBACK_FEATURES | 1953, 632, 1013 | LOW | 보조 비교 가능·넓은 특징 주의 |
| 8 | 778 | 1261 / 데이터 엔지니어 | data_engineer | SELECTED | FALLBACK_FEATURES | 1820, 1425, 1154, 1320 | LOW | 보조 비교 유용·LOW |
| 9 | 1917 | 3864 / 공간지능연구센터 3D Point Cloud·멀티모달 비디오 생성 AI | data_engineer | SELECTED | FALLBACK_FEATURES | 1245, 1813 | LOW | 직무 매핑 주의·LOW |
| 10 | 210 | 309 / 딥러닝 기반 설치류 신경활성과 행동 연계분석 연구(1) [C-03] | ml_engineer | NOT_COMPARABLE | FALLBACK_FEATURES | 없음 | — | 정보 부족 제외 정상 |
| 11 | 75 | 93 / 시스템 엔지니어 (신입) | devops | SELECTED | FALLBACK_FEATURES | 1047, 1507, 957 | LOW | 보조 비교 약함·LOW |
| 12 | 1933 | 3913 / 시스템 엔지니어 (신입) | devops | SELECTED | FALLBACK_FEATURES | 23, 708, 1216 | LOW | 보조 비교 오판 위험·LOW |
| 13 | 1666 | 3096 / AI Agent 개발 (경력) | backend | SELECTED | REQUIRED | 954, 213, 1587 | HIGH | 필수 비교 통과·업무 분야 차이 주의 |
| 14 | 991 | 1756 / 백엔드(Backend) 개발자 모집 (책임급) | backend | SELECTED | REQUIRED | 704, 616, 618 | HIGH | 필수 비교 통과·기술 coverage 낮음 |
| 15 | 1782 | 3335 / 프론트엔드 개발자 | frontend | SELECTED | REQUIRED | 765, 216, 567, 1152 | HIGH | 동일 직무·기술 근거 확인 |
| 16 | 58 | 74 / 프론트엔드 개발(React) | frontend | SELECTED | REQUIRED | 1013, 632, 671 | HIGH | 동일 직무·기술 근거 확인 |
| 17 | 1464 | 2531 / AI 분석 서비스 개발자 (경력) | data_engineer | SELECTED | REQUIRED | 1463, 1143, 1346, 1341 | HIGH | ML 오분류 연결 제거·fallback 라벨 주의 |
| 18 | 1283 | 2242 / Data Platform Engineer (Senior) | data_engineer | NO_CANDIDATES | REQUIRED | 없음 | — | 보수적 제외·재현율 영향 |
| 19 | 1576 | 2809 / 인프라 구축/운영 (신입) | devops | SELECTED | REQUIRED | 1209, 1149, 957 | HIGH | 동일 직무·기술 근거 확인 |
| 20 | 88 | 119 / AI 엔지니어 | ml_engineer | SELECTED | REQUIRED | 172, 339 | HIGH | 공통 AI 개발 근거 확인·도메인 별도 |

## 후속 API와 잔여 조건

이번에 요청된 수치 조건·보조 비교·ML 명칭·확장 금지는 모두 구현·검증됐다. 후속 읽기 전용 endpoint는 confidence·근거·정책 정보를 노출하며 실제 HTTP 검증을 통과했다. 세부 결과는 [API 검증 보고서](comparison-candidates-api-verification.md)에 기록한다. 단, HIGH는 요청된 통과 조건을 충족했다는 의미로만 설명해야 한다.

- LOW_EVIDENCE와 FALLBACK_FEATURES는 기본 추천과 구분하고 근거 수·교집합·판별 근거를 함께 제공해야 한다.
- 459의 일반 capability 두 개, 1933의 업무 tech 0 교집합은 요청된 새 정책을 충족해도 실제 직무 적합성은 약하다. 자동 수집 대상 확정에는 바로 사용하지 않는 편이 적절하다.
- 991→616은 필수 tech 한 개만 겹쳐도 통과한다. 최소 tech coverage와 핵심 기술을 별도로 요구할지는 추가 정책 결정이 필요하다. 임의의 추가 임계값은 적용하지 않았다.
- AI Research/Engineering·SRE 등 넓은 공고 분류 fallback과 LLM/ML 세부 직무 분리가 남아 있다.
- 동일 회사의 재게시·동일 특징 공고가 두 슬롯을 차지하는 문제도 남는다. 기존 회사·공고 제한은 변경하지 않았다.
- 기존 외부자료 API·trigger·연결 구조는 수정하지 않았다. 크롤러 자동 연결은 provenance와 직무별 수집 상태를 다루는 별도 작업이다.

## 변경·보존

주요 변경: PostingCandidateEligibility 신규, PostingCandidateSelectionService/Response/Properties 수정, 직무 설정 수정, eligibility 테스트 신규와 서비스·매핑 테스트 갱신, 정책 문서 갱신. public 데이터·기존 외부자료 API·trigger·크롤러·Airflow·Frontend는 변경하지 않았다. 팀 DB migration·쓰기·commit·push는 하지 않았다. 당시 검증용 임시 실행 코드·클래스·classpath 파일은 삭제했다. Markdown 최종본은 이 폴더에만 보존하고 기존 JSON 증거는 work/에 유지한다.


## 검증 이력과 재현 근거

- v1 초기 구현의 자동 테스트는 109건이었다. 당시 정책은 `keyword-mvp-1`, 직무 매핑은 `roles-mvp-1`이며 현재 실행 정책이 아니다. v1의 비교에 필요한 지표는 위 전후 비교 표에 유지하고 중복된 별도 Markdown은 제거했다.
- v2 검증은 Backend 128건 통과, 실패·오류·skip 0건이다. 구성은 기존 회귀 52, 계산기 9, 직무 매핑 25, 선정 서비스 20, 통과 조건 15, PostgreSQL Repository 7건이다. 후속 API 17건을 포함한 145건 결과는 API 보고서에 따로 기록한다.
- v2 전수·수동 점검 JSON (`work/posting-similarity-quality-v2-20261107.json`; 로컬 검증 산출물, 커밋 제외)
- 격리 테스트 실행기 (`work/run_posting_similarity_tests.py`; 로컬 검증 산출물, 커밋 제외): 로컬 합성 fixture 준비와 Backend 테스트를 수행하며 팀 DB용 실행기가 아니다.
- [현재 정책 설정](../../src/main/resources/posting-similarity.properties)

이전 v1과 v2 사이의 행별 해시는 없으므로 두 시점의 내용 동일성은 주장하지 않는다. 후속 API 검증의 public 전체 행 수·해시 불변 확인은 같은 API 검증 실행의 전후 비교다.
