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

### 점검 1: 공고 1786 / 모집 단위 3356

(주)아이피아 · [아이피아] AI 프론트엔드 엔지니어 (인턴직) · **AI 프론트엔드 엔지니어 (인턴직)**

직무 `frontend`, 근거 `RECRUIT_UNIT_NAME`. 상태 `NO_CANDIDATES`, 사유 `NO_ELIGIBLE_CANDIDATE`, 모드 `REQUIRED`.

**수동 판단: 제외 정상·추출 점검 필요** — 기존 frontend 후보 1013·1953·632는 더 이상 선정되지 않는다. 대상의 Java/Spring 계열 특징과 frontend 명칭의 불일치는 그대로라 원문/추출 검토는 별도 필요하다.

| 대상 범주 | 표준 capability명 | 표준 tech명 |
|---|---|---|
| REQUIRED | 프로그래밍 언어, 백엔드 프레임워크, 관계형 DB, DB 설계·튜닝, 데이터 마이그레이션, 클라우드, 컨테이너, 실시간 처리, 배치 처리, 디버깅·트러블슈팅 | Java, Python, Spring Boot, FastAPI, MySQL, PostgreSQL |
| PREFERRED | 버전 관리 | 없음 |
| DUTIES | API 설계, 보안·인증, 프론트엔드 프레임워크, 모바일 앱, CI/CD, 모니터링·관측, 외부 플랫폼 연동 | React, Next.js |

최종 후보 없음.


### 점검 2: 공고 1447 / 모집 단위 2509

(주)랩큐 · ML Engineer 채용 · **ML 엔지니어**

직무 `ml_engineer`, 근거 `RECRUIT_UNIT_NAME`. 상태 `SELECTED`, 사유 `NONE`, 모드 `REQUIRED`.

**수동 판단: 매핑 개선·비교 가능** — ML 엔지니어가 모집 단위명 근거의 ml_engineer로 바뀌었다. 상위 797은 필수 capability 4개와 Python·Git이 겹친다. 동일 회사 재게시 1778도 남아 중복 슬롯은 후속 검토 대상이다.

| 대상 범주 | 표준 capability명 | 표준 tech명 |
|---|---|---|
| REQUIRED | 프로그래밍 언어, 버전 관리, 머신러닝·딥러닝, 데이터 처리·분석 | Python, Git, PyTorch, Pandas |
| PREFERRED | 백엔드 프레임워크, 프론트엔드 프레임워크, 데이터베이스, 관계형 DB, 데이터 파이프라인, 클라우드, 컨테이너, 서버리스·호스팅, 버전 관리, 운영체제, 웹·WAS 서버, 머신러닝·딥러닝, LLM 응용, LLM 파인튜닝·서빙, 모델 경량화·최적화, MLOps, 벡터 DB, 백엔드 개발, 데이터 품질·표준화 | Node.js, FastAPI, Flask, React, Next.js, MySQL, PostgreSQL, Apache Airflow, Docker, Git, GitLab, Linux, Nginx, RAG, vLLM |
| DUTIES | 데이터 파이프라인, BI·시각화, 머신러닝·딥러닝, LLM 파인튜닝·서빙, 모델 경량화·최적화, 백엔드 개발, 데이터 수집·크롤링, 데이터 처리·분석 | 없음 |

| 순위 | 후보 공고 | 회사 | 제목 | 모집 단위 | 직무 근거 | confidence | 모드 | 근거 수 | 표시 | 필수 cap | 필수 tech | 우대 cap/tech | 업무 cap/tech |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 797 | (주)아성 | (주)아성에서 함께 성장할 AI 개발자를 찾고 있어요 | 1308 / AI 개발자 | RECRUIT_UNIT_NAME | HIGH | REQUIRED | 6 | 없음 | 100.00% | 50.00% | 10.53% / 0.00% | 50.00% / N/A |
| 2 | 1778 | (주)아성 | (주)아성에서 함께 성장할 AI 개발자를 찾고 있어요 | 3292 / AI 개발자 | RECRUIT_UNIT_NAME | HIGH | REQUIRED | 6 | 없음 | 100.00% | 50.00% | 10.53% / 0.00% | 50.00% / N/A |
| 3 | 187 | (주)넷코아테크 | [신입/경력]공공사업PM/공공사업PL/AI엔지니어/경영전략/마케팅/시스템운영/SW유지보수 | 278 / AI 엔지니어 | RECRUIT_UNIT_NAME | HIGH | REQUIRED | 5 | 없음 | 75.00% | 50.00% | 36.84% / 26.67% | 37.50% / N/A |
| 4 | 1530 | (주)넷코아테크 | [신입/경력] 공공사업PM/공공사업관리/AI엔지니어/경영전략/마케팅 | 3712 / AI 엔지니어 | RECRUIT_UNIT_NAME | HIGH | REQUIRED | 5 | 없음 | 75.00% | 50.00% | 36.84% / 26.67% | 37.50% / N/A |
| 5 | 946 | (주)디엠테크솔루션 | (주)디엠테크솔루션 (본사) AI개발자 경력직 채용 | 1703 / AX Lab AI개발자 | RECRUIT_UNIT_NAME | HIGH | REQUIRED | 5 | 없음 | 75.00% | 50.00% | 31.58% / 6.67% | 37.50% / N/A |

**후보 797 교집합**

| 범주 | capability명 | tech명 |
|---|---|---|
| REQUIRED | 프로그래밍 언어, 버전 관리, 머신러닝·딥러닝, 데이터 처리·분석 | Python, Git |
| PREFERRED | 클라우드, MLOps | 없음 |
| DUTIES | 데이터 파이프라인, 머신러닝·딥러닝, 데이터 수집·크롤링, 데이터 처리·분석 | 없음 |

**후보 1778 교집합**

| 범주 | capability명 | tech명 |
|---|---|---|
| REQUIRED | 프로그래밍 언어, 버전 관리, 머신러닝·딥러닝, 데이터 처리·분석 | Python, Git |
| PREFERRED | 클라우드, MLOps | 없음 |
| DUTIES | 데이터 파이프라인, 머신러닝·딥러닝, 데이터 수집·크롤링, 데이터 처리·분석 | 없음 |

**후보 187 교집합**

| 범주 | capability명 | tech명 |
|---|---|---|
| REQUIRED | 프로그래밍 언어, 버전 관리, 데이터 처리·분석 | Python, Git |
| PREFERRED | 백엔드 프레임워크, 관계형 DB, 컨테이너, 머신러닝·딥러닝, LLM 응용, LLM 파인튜닝·서빙, 벡터 DB | FastAPI, PostgreSQL, Docker, RAG |
| DUTIES | 머신러닝·딥러닝, 백엔드 개발, 데이터 처리·분석 | 없음 |

**후보 1530 교집합**

| 범주 | capability명 | tech명 |
|---|---|---|
| REQUIRED | 프로그래밍 언어, 버전 관리, 데이터 처리·분석 | Python, Git |
| PREFERRED | 백엔드 프레임워크, 관계형 DB, 컨테이너, 머신러닝·딥러닝, LLM 응용, LLM 파인튜닝·서빙, 벡터 DB | FastAPI, PostgreSQL, Docker, RAG |
| DUTIES | 머신러닝·딥러닝, 백엔드 개발, 데이터 처리·분석 | 없음 |

**후보 946 교집합**

| 범주 | capability명 | tech명 |
|---|---|---|
| REQUIRED | 프로그래밍 언어, 버전 관리, 머신러닝·딥러닝 | Python, Git |
| PREFERRED | 백엔드 프레임워크, 프론트엔드 프레임워크, 머신러닝·딥러닝, LLM 응용, 벡터 DB, 백엔드 개발 | RAG |
| DUTIES | 머신러닝·딥러닝, 백엔드 개발, 데이터 처리·분석 | 없음 |


### 점검 3: 공고 385 / 모집 단위 564

에이치알서비스(주) · [판교/대기업계열사] QA 업무 담당자 채용 · **QA**

직무 `qa`, 근거 `RECRUIT_UNIT_NAME`. 상태 `NO_CANDIDATES`, 사유 `NO_ELIGIBLE_CANDIDATE`, 모드 `REQUIRED`.

**수동 판단: 직무군 확장 차단 정상** — QA에서 backend로 확장되지 않는다. 개발 도구 하나를 근거로 한 기존 618 연결은 직무가 달라 제외된다.

| 대상 범주 | 표준 capability명 | 표준 tech명 |
|---|---|---|
| REQUIRED | 개발 도구 | 없음 |
| PREFERRED | 없음 | 없음 |
| DUTIES | 테스트 자동화, 데이터 품질·표준화 | 없음 |

최종 후보 없음.


### 점검 4: 공고 1772 / 모집 단위 3286

제이에이씨리크루트먼트코리아(주) · [유망 로보틱스AI] SW - Backend, Frontend, Platform SW, QA · **QA Engineer**

직무 `qa`, 근거 `RECRUIT_UNIT_NAME`. 상태 `NO_CANDIDATES`, 사유 `NO_ELIGIBLE_CANDIDATE`, 모드 `REQUIRED`.

**수동 판단: 직무군 확장 차단 정상** — QA Engineer→996 AI 플랫폼 백엔드 확장이 사라졌다. 비교할 동일 QA 후보가 없으면 NO_CANDIDATES를 유지한다.

| 대상 범주 | 표준 capability명 | 표준 tech명 |
|---|---|---|
| REQUIRED | 데이터 플랫폼, 운영체제 | Linux |
| PREFERRED | 테스트 자동화, 데이터 플랫폼, 클라우드, 모니터링·관측 | AWS |
| DUTIES | 테스트 자동화, 데이터 품질·표준화 | 없음 |

최종 후보 없음.


### 점검 5: 공고 459 / 모집 단위 4006

(주)유엔에이엔지니어링 · 신입 및 경력직원 채용공고 · **Telco & CP 업무지원**

직무 `backend`, 근거 `POSTING_CATEGORY`. 상태 `SELECTED`, 사유 `NONE`, 모드 `REQUIRED`.

**수동 판단: LOW 참고용·오판 위험 잔존** — 개발 도구에 네트워크 보조 근거가 추가되어 명시된 희소 예외를 통과한다. POS 기술지원 후보 1115·1757은 LOW_EVIDENCE/LOW, 근거 2개다. 여전히 일반적 특징뿐이므로 강한 추천으로 표현하면 안 된다.

| 대상 범주 | 표준 capability명 | 표준 tech명 |
|---|---|---|
| REQUIRED | 개발 도구 | 없음 |
| PREFERRED | 네트워크 | 없음 |
| DUTIES | 네트워크 | 없음 |

| 순위 | 후보 공고 | 회사 | 제목 | 모집 단위 | 직무 근거 | confidence | 모드 | 근거 수 | 표시 | 필수 cap | 필수 tech | 우대 cap/tech | 업무 cap/tech |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 1115 | (주)푸드테크 | ㈜푸드테크 하반기 신입/경력 전부문 채용 | 1991 / POS / Smart Order 하드웨어 & 기술지원 엔지니어 | POSTING_CATEGORY | LOW | REQUIRED | 2 | LOW_EVIDENCE | 100.00% | N/A | 100.00% / N/A | 0.00% / N/A |
| 2 | 1757 | (주)푸드테크 | ㈜푸드테크 하반기 신입/경력 전부문 채용 | 3248 / POS / Smart Order 하드웨어 & 기술지원 엔지니어 | POSTING_CATEGORY | LOW | REQUIRED | 2 | LOW_EVIDENCE | 100.00% | N/A | 100.00% / N/A | 0.00% / N/A |
| 3 | 588 | (주)토펙엔지니어링건축사사무소 | [토펙에이아이파워텍] AI &amp; IT 전문가 채용 | 922 / AI&IT전문가 | POSTING_CATEGORY | LOW | REQUIRED | 2 | LOW_EVIDENCE | 100.00% | N/A | 0.00% / N/A | 100.00% / N/A |
| 4 | 836 | (주)대영아이오티 | (주)대영IoT 2026년도 기술연구소 CS개발자 채용 | 1481 / 기술연구소 CS 개발자 | POSTING_CATEGORY | LOW | REQUIRED | 2 | LOW_EVIDENCE | 100.00% | N/A | 0.00% / N/A | 100.00% / N/A |

**후보 1115 교집합**

| 범주 | capability명 | tech명 |
|---|---|---|
| REQUIRED | 개발 도구 | 없음 |
| PREFERRED | 네트워크 | 없음 |
| DUTIES | 없음 | 없음 |

**후보 1757 교집합**

| 범주 | capability명 | tech명 |
|---|---|---|
| REQUIRED | 개발 도구 | 없음 |
| PREFERRED | 네트워크 | 없음 |
| DUTIES | 없음 | 없음 |

**후보 588 교집합**

| 범주 | capability명 | tech명 |
|---|---|---|
| REQUIRED | 개발 도구 | 없음 |
| PREFERRED | 없음 | 없음 |
| DUTIES | 네트워크 | 없음 |

**후보 836 교집합**

| 범주 | capability명 | tech명 |
|---|---|---|
| REQUIRED | 개발 도구 | 없음 |
| PREFERRED | 없음 | 없음 |
| DUTIES | 네트워크 | 없음 |


### 점검 6: 공고 12 / 모집 단위 20

풍림산업(주) · 풍림산업(주) 본사 전산(IT개발·데이터) 경력 인재를 찾고 있어요 · **전산**

직무 `backend`, 근거 `POSTING_CATEGORY`. 상태 `SELECTED`, 사유 `NONE`, 모드 `FALLBACK_FEATURES`.

**수동 판단: 보조 비교 유용·LOW** — 필수 없이 우대·업무로 비교한다. 상위 1524는 관계형 DB·운영체제·네트워크와 Oracle이 겹쳐 전산 업무 참고 대상으로는 설명 가능하다. 필수 충족을 뜻하지 않는다.

| 대상 범주 | 표준 capability명 | 표준 tech명 |
|---|---|---|
| REQUIRED | 없음 | 없음 |
| PREFERRED | 프로그래밍 언어 | 없음 |
| DUTIES | 프로그래밍 언어, 관계형 DB, 운영체제, 네트워크 | Oracle |

| 순위 | 후보 공고 | 회사 | 제목 | 모집 단위 | 직무 근거 | confidence | 모드 | 근거 수 | 표시 | 필수 cap | 필수 tech | 우대 cap/tech | 업무 cap/tech |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 1524 | (주)피어스넷 | 개발/보안(DB/Web/Auth) 기술자 - [ 정규직 ] | 2731 / 개발 및 보안 기술자 | POSTING_CATEGORY | LOW | FALLBACK_FEATURES | 5 | LOW_CONFIDENCE | N/A | N/A | 100.00% / N/A | 100.00% / 100.00% |
| 2 | 1526 | (주)맨파워그룹코리아 | [야탑/급여上] 글로벌반도체기업 데이터 엔지니어(1Y) | 2733 / FDC 시스템 구축 엔지니어 | POSTING_CATEGORY | LOW | FALLBACK_FEATURES | 5 | LOW_CONFIDENCE | N/A | N/A | 100.00% / N/A | 75.00% / 100.00% |
| 3 | 113 | (주)영광YKMC | (주)영광YKMC 전산관리 직무 채용 | 153 / 전산관리 | POSTING_CATEGORY | LOW | FALLBACK_FEATURES | 4 | LOW_CONFIDENCE | N/A | N/A | 100.00% / N/A | 75.00% / 0.00% |

**후보 1524 교집합**

| 범주 | capability명 | tech명 |
|---|---|---|
| REQUIRED | 없음 | 없음 |
| PREFERRED | 프로그래밍 언어 | 없음 |
| DUTIES | 프로그래밍 언어, 관계형 DB, 운영체제, 네트워크 | Oracle |

**후보 1526 교집합**

| 범주 | capability명 | tech명 |
|---|---|---|
| REQUIRED | 없음 | 없음 |
| PREFERRED | 프로그래밍 언어 | 없음 |
| DUTIES | 관계형 DB, 운영체제, 네트워크 | Oracle |

**후보 113 교집합**

| 범주 | capability명 | tech명 |
|---|---|---|
| REQUIRED | 없음 | 없음 |
| PREFERRED | 프로그래밍 언어 | 없음 |
| DUTIES | 관계형 DB, 운영체제, 네트워크 | 없음 |


### 점검 7: 공고 510 / 모집 단위 804

(주)태흥 · 주식회사 태흥 - 26년~27년 AI Full Stack 개발자 채용공고 · **프론트엔드 개발자**

직무 `frontend`, 근거 `RECRUIT_UNIT_NAME`. 상태 `SELECTED`, 사유 `NONE`, 모드 `FALLBACK_FEATURES`.

**수동 판단: 보조 비교 가능·넓은 특징 주의** — 프론트엔드끼리 우대 React와 업무 REST API 등의 교집합을 사용한다. 대상 우대·업무에 여러 영역이 섞여 있어 LOW 참고 결과로 제한해야 한다.

| 대상 범주 | 표준 capability명 | 표준 tech명 |
|---|---|---|
| REQUIRED | 없음 | 없음 |
| PREFERRED | 프로그래밍 언어, 백엔드 프레임워크, 프론트엔드 프레임워크, 메시지 브로커, 서버리스·호스팅, 운영체제, LLM 응용, 실시간 처리, 3D 데이터 처리, 방송·스트리밍 도구 | Kotlin, Node.js, React, Linux, WebSocket |
| DUTIES | 프로그래밍 언어, API 설계, 모바일 앱, 데이터베이스, 서버리스·호스팅, 네트워크, LLM 응용, 실시간 처리, 외부 플랫폼 연동, 백엔드 개발, 컴퓨터 비전, 방송·스트리밍 도구 | REST API |

| 순위 | 후보 공고 | 회사 | 제목 | 모집 단위 | 직무 근거 | confidence | 모드 | 근거 수 | 표시 | 필수 cap | 필수 tech | 우대 cap/tech | 업무 cap/tech |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 1953 | 브레인즈컴퍼니(주) | [상장사/성수역] 프론트엔드 개발자 | 3947 / 프론트엔드 개발자 | RECRUIT_UNIT_NAME | LOW | FALLBACK_FEATURES | 6 | LOW_CONFIDENCE | N/A | N/A | 20.00% / 20.00% | 16.67% / 100.00% |
| 2 | 632 | (주)캐치잇플레이 | AI 학습 플랫폼 -  프론트 엔지니어 (재택근무가능) | 971 / AI 학습 플랫폼 프론트엔드 엔지니어 (Mid-Senior) | RECRUIT_UNIT_NAME | LOW | FALLBACK_FEATURES | 3 | LOW_CONFIDENCE | N/A | N/A | 20.00% / 20.00% | 0.00% / 0.00% |
| 3 | 1013 | 메가존(주) | [메가존] [MZD] 프로젝트 투입 경력직 채용 | 1824 / Web/Front-End | RECRUIT_UNIT_NAME | LOW | FALLBACK_FEATURES | 6 | LOW_CONFIDENCE | N/A | N/A | 10.00% / 20.00% | 33.33% / 100.00% |

**후보 1953 교집합**

| 범주 | capability명 | tech명 |
|---|---|---|
| REQUIRED | 없음 | 없음 |
| PREFERRED | 프로그래밍 언어, 프론트엔드 프레임워크 | React |
| DUTIES | API 설계, 실시간 처리 | REST API |

**후보 632 교집합**

| 범주 | capability명 | tech명 |
|---|---|---|
| REQUIRED | 없음 | 없음 |
| PREFERRED | 프론트엔드 프레임워크, 실시간 처리 | WebSocket |
| DUTIES | 없음 | 없음 |

**후보 1013 교집합**

| 범주 | capability명 | tech명 |
|---|---|---|
| REQUIRED | 없음 | 없음 |
| PREFERRED | 실시간 처리 | WebSocket |
| DUTIES | 프로그래밍 언어, API 설계, 모바일 앱, 실시간 처리 | REST API |


### 점검 8: 공고 778 / 모집 단위 1261

(주)피비스 · AWS / Snowflake 데이터 엔지니어 경력 개발자 구인 · **데이터 엔지니어**

직무 `data_engineer`, 근거 `RECRUIT_UNIT_NAME`. 상태 `SELECTED`, 사유 `NONE`, 모드 `FALLBACK_FEATURES`.

**수동 판단: 보조 비교 유용·LOW** — Data Engineer끼리 AWS와 데이터 파이프라인·플랫폼·처리 특징이 겹친다. Snowflake 전체 스택 일치나 경력 수준 일치는 보장하지 않는다.

| 대상 범주 | 표준 capability명 | 표준 tech명 |
|---|---|---|
| REQUIRED | 없음 | 없음 |
| PREFERRED | 클라우드 | AWS |
| DUTIES | 프로그래밍 언어, 데이터베이스, DB 설계·튜닝, 데이터 파이프라인, 데이터 플랫폼, 클라우드, 데이터 수집·크롤링, 데이터 처리·분석 | Python, Apache Airflow, Snowflake, AWS, EC2 |

| 순위 | 후보 공고 | 회사 | 제목 | 모집 단위 | 직무 근거 | confidence | 모드 | 근거 수 | 표시 | 필수 cap | 필수 tech | 우대 cap/tech | 업무 cap/tech |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 1820 | (주)클루커스 | [클루커스] Data Engineer(Databricks) 모집 | 3486 / Data Engineer (Databricks) | RECRUIT_UNIT_NAME | LOW | FALLBACK_FEATURES | 9 | LOW_CONFIDENCE | N/A | N/A | 100.00% / 100.00% | 87.50% / 20.00% |
| 2 | 1425 | 넛지헬스케어(주) | [캐시워크] 데이터엔지니어 채용전환형 인턴 | 2472 / 데이터엔지니어 채용전환형 인턴 | RECRUIT_UNIT_NAME | LOW | FALLBACK_FEATURES | 7 | LOW_CONFIDENCE | N/A | N/A | 100.00% / 100.00% | 75.00% / 20.00% |
| 3 | 1154 | (주)아이엘로보틱스 | [아이엘로보틱스] 데이터플랫폼 엔지니어 채용 | 2066 / 데이터 플랫폼 엔지니어 | RECRUIT_UNIT_NAME | LOW | FALLBACK_FEATURES | 7 | LOW_CONFIDENCE | N/A | N/A | 100.00% / 100.00% | 75.00% / 0.00% |
| 4 | 1320 | 넛지헬스케어(주) | [캐시워크] 데이터엔지니어 | 2311 / 데이터 엔지니어 | RECRUIT_UNIT_NAME | LOW | FALLBACK_FEATURES | 5 | LOW_CONFIDENCE | N/A | N/A | 100.00% / 100.00% | 50.00% / 20.00% |

**후보 1820 교집합**

| 범주 | capability명 | tech명 |
|---|---|---|
| REQUIRED | 없음 | 없음 |
| PREFERRED | 클라우드 | AWS |
| DUTIES | 프로그래밍 언어, 데이터베이스, 데이터 파이프라인, 데이터 플랫폼, 클라우드, 데이터 수집·크롤링, 데이터 처리·분석 | Python |

**후보 1425 교집합**

| 범주 | capability명 | tech명 |
|---|---|---|
| REQUIRED | 없음 | 없음 |
| PREFERRED | 클라우드 | AWS |
| DUTIES | 데이터베이스, 데이터 파이프라인, 데이터 플랫폼, 클라우드, 데이터 수집·크롤링, 데이터 처리·분석 | AWS |

**후보 1154 교집합**

| 범주 | capability명 | tech명 |
|---|---|---|
| REQUIRED | 없음 | 없음 |
| PREFERRED | 클라우드 | AWS |
| DUTIES | 데이터베이스, 데이터 파이프라인, 데이터 플랫폼, 클라우드, 데이터 수집·크롤링, 데이터 처리·분석 | 없음 |

**후보 1320 교집합**

| 범주 | capability명 | tech명 |
|---|---|---|
| REQUIRED | 없음 | 없음 |
| PREFERRED | 클라우드 | AWS |
| DUTIES | 데이터 파이프라인, 데이터 플랫폼, 클라우드, 데이터 수집·크롤링 | AWS |


### 점검 9: 공고 1917 / 모집 단위 3864

한국전자기술연구원 · 한국전자기술연구원 전문계약직원 부문별 채용 공고 · **공간지능연구센터 3D Point Cloud·멀티모달 비디오 생성 AI**

직무 `data_engineer`, 근거 `POSTING_CATEGORY`. 상태 `SELECTED`, 사유 `NONE`, 모드 `FALLBACK_FEATURES`.

**수동 판단: 직무 매핑 주의·LOW** — CV·3D 업무가 겹치는 후보가 생겼지만 대상과 후보 모두 공고 분류로 data_engineer가 된 사례다. 역할 라벨의 정확성을 별도 확인해야 한다.

| 대상 범주 | 표준 capability명 | 표준 tech명 |
|---|---|---|
| REQUIRED | 없음 | 없음 |
| PREFERRED | 없음 | 없음 |
| DUTIES | 컴퓨터 비전, 3D 데이터 처리 | 없음 |

| 순위 | 후보 공고 | 회사 | 제목 | 모집 단위 | 직무 근거 | confidence | 모드 | 근거 수 | 표시 | 필수 cap | 필수 tech | 우대 cap/tech | 업무 cap/tech |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 1245 | (주)베오텍 | 비전 AI 제스처 인식 및 제어 분야 엔지니어 채용 | 2196 / 비전 AI 제스처 인식 및 제어 엔지니어 | POSTING_CATEGORY | LOW | FALLBACK_FEATURES | 2 | LOW_CONFIDENCE | N/A | N/A | N/A / N/A | 100.00% / N/A |
| 2 | 1813 | (주)고영테크놀러지 | 2026년 하반기 고영테크놀러지 신입사원 채용 | 3476 / AIVision 알고리즘 연구·개발 | POSTING_CATEGORY | LOW | FALLBACK_FEATURES | 2 | LOW_CONFIDENCE | N/A | N/A | N/A / N/A | 100.00% / N/A |

**후보 1245 교집합**

| 범주 | capability명 | tech명 |
|---|---|---|
| REQUIRED | 없음 | 없음 |
| PREFERRED | 없음 | 없음 |
| DUTIES | 컴퓨터 비전, 3D 데이터 처리 | 없음 |

**후보 1813 교집합**

| 범주 | capability명 | tech명 |
|---|---|---|
| REQUIRED | 없음 | 없음 |
| PREFERRED | 없음 | 없음 |
| DUTIES | 컴퓨터 비전, 3D 데이터 처리 | 없음 |


### 점검 10: 공고 210 / 모집 단위 309

대구경북과학기술원부설한국뇌연구원 · 2026년도 제5차 한국뇌연구원 직원(계약직) 공개채용 · **딥러닝 기반 설치류 신경활성과 행동 연계분석 연구(1) [C-03]**

직무 `ml_engineer`, 근거 `RECRUIT_UNIT_NAME`. 상태 `NOT_COMPARABLE`, 사유 `REQUIRED_FEATURES_MISSING`, 모드 `FALLBACK_FEATURES`.

**수동 판단: 정보 부족 제외 정상** — 머신러닝·딥러닝 업무 capability 하나뿐이라 최소 보조 특징 2개를 충족하지 못한다. REQUIRED_FEATURES_MISSING으로 유지한다.

| 대상 범주 | 표준 capability명 | 표준 tech명 |
|---|---|---|
| REQUIRED | 없음 | 없음 |
| PREFERRED | 없음 | 없음 |
| DUTIES | 머신러닝·딥러닝 | 없음 |

최종 후보 없음.


### 점검 11: 공고 75 / 모집 단위 93

(주)컴솔텍 · 2026년 하반기 신입/경력 공채 - SE(시스템 엔지니어) · **시스템 엔지니어 (신입)**

직무 `devops`, 근거 `RECRUIT_UNIT_NAME`. 상태 `SELECTED`, 사유 `NONE`, 모드 `FALLBACK_FEATURES`.

**수동 판단: 보조 비교 약함·LOW** — 서버리스·호스팅과 네트워크 두 capability로 인프라 후보를 선정한다. 우대·업무 반복을 4개가 아닌 2개로 계산했지만 기술 근거는 없다.

| 대상 범주 | 표준 capability명 | 표준 tech명 |
|---|---|---|
| REQUIRED | 없음 | 없음 |
| PREFERRED | 서버리스·호스팅, 네트워크 | 없음 |
| DUTIES | 서버리스·호스팅, 네트워크 | 없음 |

| 순위 | 후보 공고 | 회사 | 제목 | 모집 단위 | 직무 근거 | confidence | 모드 | 근거 수 | 표시 | 필수 cap | 필수 tech | 우대 cap/tech | 업무 cap/tech |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 1047 | 산일전기(주) | 2026년 시스템 개발자 채용 (DXTeam) | 1882 / 인프라 및 OA 관리 | RECRUIT_UNIT_NAME | LOW | FALLBACK_FEATURES | 2 | LOW_CONFIDENCE | N/A | N/A | 100.00% / N/A | 100.00% / N/A |
| 2 | 1507 | 월드파트너스주식회사(WORLDPARTNERSCO_LTD) | [일본도쿄정규직] IT 인프라 엔지니어 (경력자/일어영어가능자) | 2698 / IT 인프라 엔지니어 (네트워크·서버 운영/헬프데스크) | RECRUIT_UNIT_NAME | LOW | FALLBACK_FEATURES | 2 | LOW_CONFIDENCE | N/A | N/A | 100.00% / N/A | 100.00% / N/A |
| 3 | 957 | (주)필상 | [대전/IT] 서버 · 클라우드 엔지니어 채용(신입/경력 무관) | 1714 / 서버·클라우드 엔지니어 | RECRUIT_UNIT_NAME | LOW | FALLBACK_FEATURES | 2 | LOW_CONFIDENCE | N/A | N/A | 100.00% / N/A | 50.00% / N/A |

**후보 1047 교집합**

| 범주 | capability명 | tech명 |
|---|---|---|
| REQUIRED | 없음 | 없음 |
| PREFERRED | 서버리스·호스팅, 네트워크 | 없음 |
| DUTIES | 서버리스·호스팅, 네트워크 | 없음 |

**후보 1507 교집합**

| 범주 | capability명 | tech명 |
|---|---|---|
| REQUIRED | 없음 | 없음 |
| PREFERRED | 서버리스·호스팅, 네트워크 | 없음 |
| DUTIES | 서버리스·호스팅, 네트워크 | 없음 |

**후보 957 교집합**

| 범주 | capability명 | tech명 |
|---|---|---|
| REQUIRED | 없음 | 없음 |
| PREFERRED | 서버리스·호스팅, 네트워크 | 없음 |
| DUTIES | 서버리스·호스팅 | 없음 |


### 점검 12: 공고 1933 / 모집 단위 3913

주식회사 테코 · 일본에서 근무하실 시스템 엔지니어를 모집합니다. · **시스템 엔지니어 (신입)**

직무 `devops`, 근거 `RECRUIT_UNIT_NAME`. 상태 `SELECTED`, 사유 `NONE`, 모드 `FALLBACK_FEATURES`.

**수동 판단: 보조 비교 오판 위험·LOW** — C/C++ 업무 대상이 프로그래밍 언어·백엔드 개발 capability 두 개만으로 DevOps/AI 인프라 후보를 얻는다. 업무 tech 교집합은 0이므로 참고 수준 이상의 활용은 보류해야 한다.

| 대상 범주 | 표준 capability명 | 표준 tech명 |
|---|---|---|
| REQUIRED | 없음 | 없음 |
| PREFERRED | 없음 | 없음 |
| DUTIES | 프로그래밍 언어, 백엔드 개발 | C, C++ |

| 순위 | 후보 공고 | 회사 | 제목 | 모집 단위 | 직무 근거 | confidence | 모드 | 근거 수 | 표시 | 필수 cap | 필수 tech | 우대 cap/tech | 업무 cap/tech |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 23 | (주)제론엑스 | 백엔드·인프라(DevOps)엔지니어 | 33 / B/E, DevOps 엔지니어 | RECRUIT_UNIT_NAME | LOW | FALLBACK_FEATURES | 2 | LOW_CONFIDENCE | N/A | N/A | N/A / N/A | 100.00% / 0.00% |
| 2 | 708 | (주)텐 | AI Infra Researcher | 1128 / 인프라 연구원 | RECRUIT_UNIT_NAME | LOW | FALLBACK_FEATURES | 2 | LOW_CONFIDENCE | N/A | N/A | N/A / N/A | 100.00% / 0.00% |
| 3 | 1216 | (주)글로벌스카우트 | (주)글로벌스카우트  AI DT담당 AI인프라·플랫폼 운영 담당자를 찾고 있어요 | 2153 / AI인프라 및 플랫폼 운영 담당자 | RECRUIT_UNIT_NAME | LOW | FALLBACK_FEATURES | 2 | LOW_CONFIDENCE | N/A | N/A | N/A / N/A | 100.00% / 0.00% |

**후보 23 교집합**

| 범주 | capability명 | tech명 |
|---|---|---|
| REQUIRED | 없음 | 없음 |
| PREFERRED | 없음 | 없음 |
| DUTIES | 프로그래밍 언어, 백엔드 개발 | 없음 |

**후보 708 교집합**

| 범주 | capability명 | tech명 |
|---|---|---|
| REQUIRED | 없음 | 없음 |
| PREFERRED | 없음 | 없음 |
| DUTIES | 프로그래밍 언어, 백엔드 개발 | 없음 |

**후보 1216 교집합**

| 범주 | capability명 | tech명 |
|---|---|---|
| REQUIRED | 없음 | 없음 |
| PREFERRED | 없음 | 없음 |
| DUTIES | 프로그래밍 언어, 백엔드 개발 | 없음 |


### 점검 13: 공고 1666 / 모집 단위 3096

쿠도커뮤니케이션(주) · 2027 쿠도커뮤니케이션㈜ 신입/경력 공개채용 · **AI Agent 개발 (경력)**

직무 `backend`, 근거 `POSTING_CATEGORY`. 상태 `SELECTED`, 사유 `NONE`, 모드 `REQUIRED`.

**수동 판단: 필수 비교 통과·업무 분야 차이 주의** — 의료영상 Viewer 후보 954는 필수 Java·Python·Node.js·FastAPI가 모두 겹쳐 HIGH다. AI Agent·LLM 세부 업무의 적합성까지 높다는 뜻은 아니다.

| 대상 범주 | 표준 capability명 | 표준 tech명 |
|---|---|---|
| REQUIRED | 프로그래밍 언어, 백엔드 프레임워크, 백엔드 개발 | Java, Python, Node.js, FastAPI |
| PREFERRED | 클라우드, 컨테이너, 컨테이너 오케스트레이션, LLM 응용, 벡터 DB | AWS, Azure, Docker, Kubernetes, RAG |
| DUTIES | 데이터 파이프라인, LLM 응용, 외부 플랫폼 연동 | 없음 |

| 순위 | 후보 공고 | 회사 | 제목 | 모집 단위 | 직무 근거 | confidence | 모드 | 근거 수 | 표시 | 필수 cap | 필수 tech | 우대 cap/tech | 업무 cap/tech |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 954 | (주)엠아이텍 | 의료영상 Viewer/서버 개발자 채용 | 1711 / 의료영상 Viewer/서버 개발자 | RECRUIT_UNIT_NAME | HIGH | REQUIRED | 7 | 없음 | 100.00% | 100.00% | 0.00% / 0.00% | 66.67% / N/A |
| 2 | 213 | 올거나이즈코리아(주) | AI Native Back-end Engineer | 325 / AI Native Back-end Engineer | RECRUIT_UNIT_NAME | HIGH | REQUIRED | 6 | 없음 | 100.00% | 75.00% | 60.00% / 40.00% | 66.67% / N/A |
| 3 | 1587 | (주)헤스티아 | 2026 (주)헤스티아 개발자 채용 (정규직) | 2823 / 개발 | POSTING_CATEGORY | HIGH | REQUIRED | 6 | 없음 | 100.00% | 75.00% | 60.00% / 20.00% | 0.00% / N/A |

**후보 954 교집합**

| 범주 | capability명 | tech명 |
|---|---|---|
| REQUIRED | 프로그래밍 언어, 백엔드 프레임워크, 백엔드 개발 | Java, Python, Node.js, FastAPI |
| PREFERRED | 없음 | 없음 |
| DUTIES | 데이터 파이프라인, 외부 플랫폼 연동 | 없음 |

**후보 213 교집합**

| 범주 | capability명 | tech명 |
|---|---|---|
| REQUIRED | 프로그래밍 언어, 백엔드 프레임워크, 백엔드 개발 | Python, Node.js, FastAPI |
| PREFERRED | 클라우드, 컨테이너 오케스트레이션, LLM 응용 | Kubernetes, RAG |
| DUTIES | 데이터 파이프라인, LLM 응용 | 없음 |

**후보 1587 교집합**

| 범주 | capability명 | tech명 |
|---|---|---|
| REQUIRED | 프로그래밍 언어, 백엔드 프레임워크, 백엔드 개발 | Java, Python, FastAPI |
| PREFERRED | 컨테이너, 컨테이너 오케스트레이션, LLM 응용 | Docker |
| DUTIES | 없음 | 없음 |


### 점검 14: 공고 991 / 모집 단위 1756

(주)쉐코 · [SW팀] 백엔드(Backend) 개발자 모집 (책임급) · **백엔드(Backend) 개발자 모집 (책임급)**

직무 `backend`, 근거 `RECRUIT_UNIT_NAME`. 상태 `SELECTED`, 사유 `NONE`, 모드 `REQUIRED`.

**수동 판단: 필수 비교 통과·기술 coverage 낮음** — 704는 필수 capability 57.14%, tech 37.50%다. 616은 PostgreSQL 한 개로 tech 12.50%지만 정책 최소 1개를 통과한다. HIGH가 스택 전체 일치라는 의미는 아니다.

| 대상 범주 | 표준 capability명 | 표준 tech명 |
|---|---|---|
| REQUIRED | 프로그래밍 언어, 백엔드 프레임워크, 이벤트 기반 아키텍처, 보안·인증, 테스트 자동화, 데이터베이스, 관계형 DB, NoSQL DB, 데이터 마이그레이션, 클라우드, 컨테이너, 컨테이너 오케스트레이션, 서버리스·호스팅, CI/CD, 버전 관리, 모니터링·관측, 네트워크, 개발 방법론, 실시간 처리, 백엔드 개발, 디버깅·트러블슈팅 | Java, Spring Boot, PostgreSQL, MongoDB, Docker, Kubernetes, Git, WebSocket |
| PREFERRED | 프론트엔드 프레임워크, 클라우드, CI/CD, 실시간 처리, 디버깅·트러블슈팅, 방송·스트리밍 도구 | 없음 |
| DUTIES | API 설계, 데이터베이스, DB 설계·튜닝, BI·시각화, 실시간 처리, 백엔드 개발, 데이터 수집·크롤링, 데이터 처리·분석, 디버깅·트러블슈팅 | REST API, WebSocket |

| 순위 | 후보 공고 | 회사 | 제목 | 모집 단위 | 직무 근거 | confidence | 모드 | 근거 수 | 표시 | 필수 cap | 필수 tech | 우대 cap/tech | 업무 cap/tech |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 704 | [DB 공란] | [메타팩토리] Backend / Platform Engineer 모집 | 1124 / 백엔드/플랫폼 엔지니어 | RECRUIT_UNIT_NAME | HIGH | REQUIRED | 15 | 없음 | 57.14% | 37.50% | 33.33% / N/A | 22.22% / 0.00% |
| 2 | 616 | 에이블제이(주) | 에이블제이 백엔드 엔지니어 채용 | 952 / 백엔드 개발자 | RECRUIT_UNIT_NAME | HIGH | REQUIRED | 13 | 없음 | 57.14% | 12.50% | 66.67% / N/A | 55.56% / 0.00% |
| 3 | 618 | (주)이우소프트 | Backend Engineer(Platform · 인증/권한) | 954 / Backend Engineer(Platform · 인증/권한) | RECRUIT_UNIT_NAME | HIGH | REQUIRED | 14 | 없음 | 52.38% | 37.50% | 16.67% / N/A | 44.44% / 0.00% |

**후보 704 교집합**

| 범주 | capability명 | tech명 |
|---|---|---|
| REQUIRED | 프로그래밍 언어, 백엔드 프레임워크, 이벤트 기반 아키텍처, 데이터베이스, 관계형 DB, NoSQL DB, 클라우드, 컨테이너, 컨테이너 오케스트레이션, 네트워크, 백엔드 개발, 디버깅·트러블슈팅 | PostgreSQL, Docker, Kubernetes |
| PREFERRED | 클라우드, 디버깅·트러블슈팅 | 없음 |
| DUTIES | 데이터베이스, 디버깅·트러블슈팅 | 없음 |

**후보 616 교집합**

| 범주 | capability명 | tech명 |
|---|---|---|
| REQUIRED | 프로그래밍 언어, 백엔드 프레임워크, 보안·인증, 테스트 자동화, 데이터베이스, 관계형 DB, 클라우드, 서버리스·호스팅, 모니터링·관측, 네트워크, 개발 방법론, 디버깅·트러블슈팅 | PostgreSQL |
| PREFERRED | 클라우드, 실시간 처리, 디버깅·트러블슈팅, 방송·스트리밍 도구 | 없음 |
| DUTIES | API 설계, 데이터베이스, 백엔드 개발, 데이터 처리·분석, 디버깅·트러블슈팅 | 없음 |

**후보 618 교집합**

| 범주 | capability명 | tech명 |
|---|---|---|
| REQUIRED | 프로그래밍 언어, 백엔드 프레임워크, 보안·인증, 데이터베이스, 관계형 DB, 클라우드, 컨테이너, 컨테이너 오케스트레이션, 버전 관리, 백엔드 개발, 디버깅·트러블슈팅 | PostgreSQL, Docker, Git |
| PREFERRED | 클라우드 | 없음 |
| DUTIES | API 설계, 데이터베이스, DB 설계·튜닝, 백엔드 개발 | 없음 |


### 점검 15: 공고 1782 / 모집 단위 3335

극동건설(주) · 2026년 4분기 분야별 공개채용 · **프론트엔드 개발자**

직무 `frontend`, 근거 `RECRUIT_UNIT_NAME`. 상태 `SELECTED`, 사유 `NONE`, 모드 `REQUIRED`.

**수동 판단: 동일 직무·기술 근거 확인** — 프론트엔드 프레임워크와 React가 겹쳐 근거 2개다. React/Vue 중 React 하나의 일치이며 두 기술 모두 충족한 것으로 표현하면 안 된다.

| 대상 범주 | 표준 capability명 | 표준 tech명 |
|---|---|---|
| REQUIRED | 프론트엔드 프레임워크 | React, Vue |
| PREFERRED | API 설계, 네트워크, 외부 플랫폼 연동, 방송·스트리밍 도구 | 없음 |
| DUTIES | 프론트엔드 프레임워크, 네트워크, 실시간 처리, 외부 플랫폼 연동 | 없음 |

| 순위 | 후보 공고 | 회사 | 제목 | 모집 단위 | 직무 근거 | confidence | 모드 | 근거 수 | 표시 | 필수 cap | 필수 tech | 우대 cap/tech | 업무 cap/tech |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 765 | [DB 공란] | [INEEJI] 하반기 분야별 인재 채용 | 1227 / 프론트엔드 개발자 (선임, 책임급) | RECRUIT_UNIT_NAME | HIGH | REQUIRED | 2 | 없음 | 100.00% | 50.00% | 25.00% / N/A | 25.00% / N/A |
| 2 | 216 | (주)지엠피아이티 | [React] 품질관리시스템 (LIMS) 개발 | 336 / React 프론트엔드 개발자 | RECRUIT_UNIT_NAME | HIGH | REQUIRED | 2 | 없음 | 100.00% | 50.00% | 25.00% / N/A | 0.00% / N/A |
| 3 | 567 | (주)한국디지털거래소 | [한국디지털거래소] 프론트엔드 개발자를 모십니다. | 895 / 프론트엔드 개발자(Front-End Developer) | RECRUIT_UNIT_NAME | HIGH | REQUIRED | 2 | 없음 | 100.00% | 50.00% | 0.00% / N/A | 50.00% / N/A |
| 4 | 1152 | [DB 공란] | [데이터 엔지니어] 경력직 채용 | 2057 / 개발부문 프론트엔드 | RECRUIT_UNIT_NAME | HIGH | REQUIRED | 2 | 없음 | 100.00% | 50.00% | 0.00% / N/A | 25.00% / N/A |

**후보 765 교집합**

| 범주 | capability명 | tech명 |
|---|---|---|
| REQUIRED | 프론트엔드 프레임워크 | React |
| PREFERRED | API 설계 | 없음 |
| DUTIES | 프론트엔드 프레임워크 | 없음 |

**후보 216 교집합**

| 범주 | capability명 | tech명 |
|---|---|---|
| REQUIRED | 프론트엔드 프레임워크 | React |
| PREFERRED | 외부 플랫폼 연동 | 없음 |
| DUTIES | 없음 | 없음 |

**후보 567 교집합**

| 범주 | capability명 | tech명 |
|---|---|---|
| REQUIRED | 프론트엔드 프레임워크 | React |
| PREFERRED | 없음 | 없음 |
| DUTIES | 프론트엔드 프레임워크, 실시간 처리 | 없음 |

**후보 1152 교집합**

| 범주 | capability명 | tech명 |
|---|---|---|
| REQUIRED | 프론트엔드 프레임워크 | React |
| PREFERRED | 없음 | 없음 |
| DUTIES | 프론트엔드 프레임워크 | 없음 |


### 점검 16: 공고 58 / 모집 단위 74

엔투에이아이 주식회사 · 26년 하반기 N2AI IT개발본부 FE, BE 개발자(React, python AI) · **프론트엔드 개발(React)**

직무 `frontend`, 근거 `RECRUIT_UNIT_NAME`. 상태 `SELECTED`, 사유 `NONE`, 모드 `REQUIRED`.

**수동 판단: 동일 직무·기술 근거 확인** — 1013 Web/Front-End와 TypeScript·REST API·React가 겹쳐 필수 capability 100%, tech 75%다. 동일 공고의 Back-End 단위를 혼합하지 않는다.

| 대상 범주 | 표준 capability명 | 표준 tech명 |
|---|---|---|
| REQUIRED | 프로그래밍 언어, API 설계, 프론트엔드 프레임워크 | TypeScript, REST API, React, Tanstack Query |
| PREFERRED | 없음 | 없음 |
| DUTIES | 프론트엔드 프레임워크, 디자인 협업 | React, Figma |

| 순위 | 후보 공고 | 회사 | 제목 | 모집 단위 | 직무 근거 | confidence | 모드 | 근거 수 | 표시 | 필수 cap | 필수 tech | 우대 cap/tech | 업무 cap/tech |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 1013 | 메가존(주) | [메가존] [MZD] 프로젝트 투입 경력직 채용 | 1824 / Web/Front-End | RECRUIT_UNIT_NAME | HIGH | REQUIRED | 6 | 없음 | 100.00% | 75.00% | N/A / N/A | 50.00% / 50.00% |
| 2 | 632 | (주)캐치잇플레이 | AI 학습 플랫폼 -  프론트 엔지니어 (재택근무가능) | 971 / AI 학습 플랫폼 프론트엔드 엔지니어 (Mid-Senior) | RECRUIT_UNIT_NAME | HIGH | REQUIRED | 6 | 없음 | 100.00% | 75.00% | N/A / N/A | 50.00% / 0.00% |
| 3 | 671 | 프라임에셋(주) | 2026 프라임에셋(주) 하반기 정규직 채용 | 1071 / 시스템개발팀 프론트엔드 개발 | RECRUIT_UNIT_NAME | HIGH | REQUIRED | 5 | 없음 | 100.00% | 50.00% | N/A / N/A | 50.00% / 0.00% |

**후보 1013 교집합**

| 범주 | capability명 | tech명 |
|---|---|---|
| REQUIRED | 프로그래밍 언어, API 설계, 프론트엔드 프레임워크 | TypeScript, REST API, React |
| PREFERRED | 없음 | 없음 |
| DUTIES | 프론트엔드 프레임워크 | React |

**후보 632 교집합**

| 범주 | capability명 | tech명 |
|---|---|---|
| REQUIRED | 프로그래밍 언어, API 설계, 프론트엔드 프레임워크 | TypeScript, REST API, React |
| PREFERRED | 없음 | 없음 |
| DUTIES | 프론트엔드 프레임워크 | 없음 |

**후보 671 교집합**

| 범주 | capability명 | tech명 |
|---|---|---|
| REQUIRED | 프로그래밍 언어, API 설계, 프론트엔드 프레임워크 | TypeScript, REST API |
| PREFERRED | 없음 | 없음 |
| DUTIES | 프론트엔드 프레임워크 | 없음 |


### 점검 17: 공고 1464 / 모집 단위 2531

(주)디더블유아이 · (주)디더블유아이에서 AI 분석 서비스 개발자 모십니다 · **AI 분석 서비스 개발자 (경력)**

직무 `data_engineer`, 근거 `POSTING_CATEGORY`. 상태 `SELECTED`, 사유 `NONE`, 모드 `REQUIRED`.

**수동 판단: ML 오분류 연결 제거·fallback 라벨 주의** — 1447이 ml_engineer로 바뀌어 이 data_engineer 대상의 후보에서 빠졌다. AI Research/Engineering 후보 등은 여전히 공고 분류로 data_engineer가 되어 역할 세분화 검토가 남는다.

| 대상 범주 | 표준 capability명 | 표준 tech명 |
|---|---|---|
| REQUIRED | 프로그래밍 언어, 머신러닝·딥러닝, 데이터 처리·분석 | Python, Pandas |
| PREFERRED | 백엔드 프레임워크, BI·시각화, 클라우드, 딥러닝 프레임워크 | FastAPI, Flask, AWS, GCP, PyTorch, TensorFlow |
| DUTIES | 프로그래밍 언어, API 설계, 프론트엔드 프레임워크, 머신러닝·딥러닝, 데이터 처리·분석 | Python |

| 순위 | 후보 공고 | 회사 | 제목 | 모집 단위 | 직무 근거 | confidence | 모드 | 근거 수 | 표시 | 필수 cap | 필수 tech | 우대 cap/tech | 업무 cap/tech |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 1463 | 도프텍(주) | AI Research/Engineer 채용 | 2529 / AI Research / Engineering | POSTING_CATEGORY | HIGH | REQUIRED | 4 | 없음 | 100.00% | 50.00% | 50.00% / 16.67% | 40.00% / 0.00% |
| 2 | 1143 | [DB 공란] | KREAM 검수센터 데이터 수집 및 예측 담당자 | 2033 / KREAM 검수센터 데이터 수집 및 예측 담당자 | POSTING_CATEGORY | HIGH | REQUIRED | 4 | 없음 | 100.00% | 50.00% | 25.00% / 0.00% | 60.00% / 100.00% |
| 3 | 1346 | [DB 공란] | KREAM 검수센터 데이터 수집 및 예측 담당자 | 2355 / KREAM 검수센터 데이터 수집 및 예측 담당자 (계약직) | POSTING_CATEGORY | HIGH | REQUIRED | 4 | 없음 | 100.00% | 50.00% | 25.00% / 0.00% | 60.00% / 100.00% |
| 4 | 1341 | 시너지에이아이(주) | 디지털 헬스케어 R&amp;D 팀원(AI Research Engineer) 모집 | 2349 / 디지털 헬스케어 R&D 팀원 (AI Research Engineer) | POSTING_CATEGORY | HIGH | REQUIRED | 4 | 없음 | 100.00% | 50.00% | 25.00% / 0.00% | 40.00% / 0.00% |

**후보 1463 교집합**

| 범주 | capability명 | tech명 |
|---|---|---|
| REQUIRED | 프로그래밍 언어, 머신러닝·딥러닝, 데이터 처리·분석 | Python |
| PREFERRED | 백엔드 프레임워크, 딥러닝 프레임워크 | PyTorch |
| DUTIES | 머신러닝·딥러닝, 데이터 처리·분석 | 없음 |

**후보 1143 교집합**

| 범주 | capability명 | tech명 |
|---|---|---|
| REQUIRED | 프로그래밍 언어, 머신러닝·딥러닝, 데이터 처리·분석 | Python |
| PREFERRED | BI·시각화 | 없음 |
| DUTIES | 프로그래밍 언어, 머신러닝·딥러닝, 데이터 처리·분석 | Python |

**후보 1346 교집합**

| 범주 | capability명 | tech명 |
|---|---|---|
| REQUIRED | 프로그래밍 언어, 머신러닝·딥러닝, 데이터 처리·분석 | Python |
| PREFERRED | BI·시각화 | 없음 |
| DUTIES | 프로그래밍 언어, 머신러닝·딥러닝, 데이터 처리·분석 | Python |

**후보 1341 교집합**

| 범주 | capability명 | tech명 |
|---|---|---|
| REQUIRED | 프로그래밍 언어, 머신러닝·딥러닝, 데이터 처리·분석 | Python |
| PREFERRED | 클라우드 | 없음 |
| DUTIES | 머신러닝·딥러닝, 데이터 처리·분석 | 없음 |


### 점검 18: 공고 1283 / 모집 단위 2242

디토닉(주) · Junior / Senior Data Platform Engineer · **Data Platform Engineer (Senior)**

직무 `data_engineer`, 근거 `POSTING_CATEGORY`. 상태 `NO_CANDIDATES`, 사유 `NO_ELIGIBLE_CANDIDATE`, 모드 `REQUIRED`.

**수동 판단: 보수적 제외·재현율 영향** — 이전 상위 Data Engineer 후보들의 필수 capability coverage 46.15%가 50%에 못 미쳐 제외됐다. 낮은 일치 후보를 억지로 채우지 않는 대신 넓은 필수 목록에는 후보가 없어질 수 있다.

| 대상 범주 | 표준 capability명 | 표준 tech명 |
|---|---|---|
| REQUIRED | 프로그래밍 언어, 백엔드 프레임워크, API 설계, MSA, 관계형 DB, 데이터 플랫폼, 컨테이너 오케스트레이션, 버전 관리, 운영체제, AI 코딩 도구, 백엔드 개발, 데이터 처리·분석, 디버깅·트러블슈팅 | Python, Rust, FastAPI, REST API, PostgreSQL, Kubernetes, Git, Linux |
| PREFERRED | 프로그래밍 언어, SQL, 프론트엔드 프레임워크, 데이터베이스, 데이터 파이프라인, 데이터 플랫폼, BI·시각화, 메시지 브로커, 서버리스·호스팅, IaC, CI/CD, 모니터링·관측, 개발 방법론, 배치 처리, GIS·공간 데이터 | TypeScript, SQL, Spark, Iceberg, Kafka, Terraform, ArgoCD, Prometheus, Loki |
| DUTIES | 프로그래밍 언어, API 설계, 보안·인증, 데이터베이스, DB 설계·튜닝, 데이터 파이프라인, 데이터 플랫폼, 메시지 브로커, 컨테이너, 컨테이너 오케스트레이션, 버전 관리, 모니터링·관측, LLM 응용, 외부 플랫폼 연동, 데이터 처리·분석, 데이터 품질·표준화 | Python, Rust, REST API, Kafka, S3, Kubernetes, OAuth |

최종 후보 없음.


### 점검 19: 공고 1576 / 모집 단위 2809

티에이케이정보시스템(주) · [티에이케이정보시스템] 하반기 신입 및 경력사원 수시채용 · **인프라 구축/운영 (신입)**

직무 `devops`, 근거 `RECRUIT_UNIT_NAME`. 상태 `SELECTED`, 사유 `NONE`, 모드 `REQUIRED`.

**수동 판단: 동일 직무·기술 근거 확인** — 1209·1149와 보안·운영체제·네트워크 및 Linux·Windows가 겹친다. 기존 tech 교집합 0인 후보 1233은 선정되지 않는다.

| 대상 범주 | 표준 capability명 | 표준 tech명 |
|---|---|---|
| REQUIRED | 보안·인증, 운영체제, 네트워크 | Linux, Windows |
| PREFERRED | 프로그래밍 언어, 클라우드, 서버리스·호스팅, 네트워크 | Python, AWS, Azure |
| DUTIES | 보안·인증, 클라우드, 운영체제, 모니터링·관측, 네트워크, 디버깅·트러블슈팅 | 없음 |

| 순위 | 후보 공고 | 회사 | 제목 | 모집 단위 | 직무 근거 | confidence | 모드 | 근거 수 | 표시 | 필수 cap | 필수 tech | 우대 cap/tech | 업무 cap/tech |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 1209 | ㈜구구스 | [구구스/중고명품 플랫폼] DevOps Engineer 채용 | 2145 / 인프라·클라우드 운영 | RECRUIT_UNIT_NAME | HIGH | REQUIRED | 5 | 없음 | 100.00% | 100.00% | 50.00% / 33.33% | 100.00% / N/A |
| 2 | 1149 | (주)모닝인 | [서초] IT 인프라 엔지니어(정규직전환가능) | 2050 / IT 인프라 엔지니어(정규직전환가능) | RECRUIT_UNIT_NAME | HIGH | REQUIRED | 5 | 없음 | 100.00% | 100.00% | 25.00% / 0.00% | 83.33% / N/A |
| 3 | 957 | (주)필상 | [대전/IT] 서버 · 클라우드 엔지니어 채용(신입/경력 무관) | 1714 / 서버·클라우드 엔지니어 | RECRUIT_UNIT_NAME | HIGH | REQUIRED | 4 | 없음 | 100.00% | 50.00% | 75.00% / 0.00% | 50.00% / N/A |

**후보 1209 교집합**

| 범주 | capability명 | tech명 |
|---|---|---|
| REQUIRED | 보안·인증, 운영체제, 네트워크 | Linux, Windows |
| PREFERRED | 클라우드, 네트워크 | AWS |
| DUTIES | 보안·인증, 클라우드, 운영체제, 모니터링·관측, 네트워크, 디버깅·트러블슈팅 | 없음 |

**후보 1149 교집합**

| 범주 | capability명 | tech명 |
|---|---|---|
| REQUIRED | 보안·인증, 운영체제, 네트워크 | Linux, Windows |
| PREFERRED | 서버리스·호스팅 | 없음 |
| DUTIES | 보안·인증, 운영체제, 모니터링·관측, 네트워크, 디버깅·트러블슈팅 | 없음 |

**후보 957 교집합**

| 범주 | capability명 | tech명 |
|---|---|---|
| REQUIRED | 보안·인증, 운영체제, 네트워크 | Linux |
| PREFERRED | 클라우드, 서버리스·호스팅, 네트워크 | 없음 |
| DUTIES | 클라우드, 모니터링·관측, 디버깅·트러블슈팅 | 없음 |


### 점검 20: 공고 88 / 모집 단위 119

레피나 · AI 엔지니어 채용 · **AI 엔지니어**

직무 `ml_engineer`, 근거 `RECRUIT_UNIT_NAME`. 상태 `SELECTED`, 사유 `NONE`, 모드 `REQUIRED`.

**수동 판단: 공통 AI 개발 근거 확인·도메인 별도** — 172·339와 Python·SQL·REST API·RAG 등이 겹친다. 필수 capability 63.64%, tech 44.44%로 통과하며 OAuth/Webhook 등의 개별 미일치는 남는다.

| 대상 범주 | 표준 capability명 | 표준 tech명 |
|---|---|---|
| REQUIRED | 프로그래밍 언어, SQL, 백엔드 프레임워크, API 설계, 보안·인증, 데이터베이스, 클라우드, 서버리스·호스팅, LLM 응용, 벡터 DB, 외부 플랫폼 연동 | Python, TypeScript, SQL, Node.js, FastAPI, REST API, RAG, OAuth, Webhook |
| PREFERRED | 프론트엔드 프레임워크, LLM 응용 | React, Next.js, LangGraph |
| DUTIES | LLM 응용, 백엔드 개발, 데이터 수집·크롤링, 데이터 처리·분석 | 없음 |

| 순위 | 후보 공고 | 회사 | 제목 | 모집 단위 | 직무 근거 | confidence | 모드 | 근거 수 | 표시 | 필수 cap | 필수 tech | 우대 cap/tech | 업무 cap/tech |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 172 | (주)퍼브 | 2026 (주)퍼브 플랫폼본부 AI 개발자 정규직 채용 | 255 / AI 개발자 | RECRUIT_UNIT_NAME | HIGH | REQUIRED | 11 | 없음 | 63.64% | 44.44% | 50.00% / 33.33% | 100.00% / N/A |
| 2 | 339 | (주)아이플 | 2026 (주)아이플 AI 개발자 정규직 채용 | 504 / AI개발자 - 개발 | RECRUIT_UNIT_NAME | HIGH | REQUIRED | 11 | 없음 | 63.64% | 44.44% | 50.00% / 33.33% | 100.00% / N/A |

**후보 172 교집합**

| 범주 | capability명 | tech명 |
|---|---|---|
| REQUIRED | 프로그래밍 언어, SQL, 백엔드 프레임워크, API 설계, 데이터베이스, LLM 응용, 벡터 DB | Python, SQL, REST API, RAG |
| PREFERRED | LLM 응용 | LangGraph |
| DUTIES | LLM 응용, 백엔드 개발, 데이터 수집·크롤링, 데이터 처리·분석 | 없음 |

**후보 339 교집합**

| 범주 | capability명 | tech명 |
|---|---|---|
| REQUIRED | 프로그래밍 언어, SQL, 백엔드 프레임워크, API 설계, 데이터베이스, LLM 응용, 벡터 DB | Python, SQL, REST API, RAG |
| PREFERRED | LLM 응용 | LangGraph |
| DUTIES | LLM 응용, 백엔드 개발, 데이터 수집·크롤링, 데이터 처리·분석 | 없음 |

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
