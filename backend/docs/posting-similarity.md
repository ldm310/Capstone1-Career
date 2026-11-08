# 타사 유사 공고 선정 MVP

## 범위와 호출

`PostingCandidateSelectionService.select(postingId)`는 현재 공고의 IT 모집 단위별로 타사 후보 공고를 선정한다. 선정 서비스 자체는 외부 사이트 호출이나 결과 저장을 하지 않는다. HTTP 조회는 [Comparison Candidates API](comparison-candidates-api.md)가 이 서비스를 호출한다. 기존 외부자료 API·연결·trigger와 독립적이며 public 스키마에 SELECT만 실행한다. 서비스는 `@Transactional(readOnly=true)`다.

## 조회 계약

전용 JDBC Repository가 단일 SQL 문으로 대상 공고와 타사 공고의 현재 추출 결과를 읽는다. 따라서 여러 조회 사이에 현재 추출 결과가 바뀌어 서로 다른 실행을 섞는 문제가 없다.

- 비교 대상과 후보 모두 `extraction_run.is_current=true`, `recruit_unit.is_it=true`만 포함한다.
- 후보 회사는 `posting.company_id`로 제외한다. 회사명은 조회하지도 점수에 사용하지도 않는다.
- `필수`, `우대`, `업무`별로 capability ID와 tech ID를 독립적인 집합으로 만든다.
- 비활성 capability, 이름이 `기타`인 capability, 비활성 tech, NULL tech ID는 해당 ID 공간에서 제외한다.
- capability가 기타·비활성이어도 연결된 활성 tech는 보존한다. capability에 tech가 없어도 활성 capability는 보존한다.
- 같은 ID가 반복되어도 범주 안에서 한 번만 센다. 같은 ID가 필수와 우대에 각각 있으면 두 범주의 근거를 모두 보존한다.
- 특징이 없는 IT 모집 단위도 LEFT JOIN으로 보존하고 사유를 반환한다. 본문, quote, 원문 자유 문자열로 ID를 추측하지 않는다.

현재 실행 개수는 IT 모집 단위를 필터링하기 **전**에 공고별로 계산한다. 대상 또는 조회 범위의 타사 공고에 현재 실행이 두 개 이상 있으면 `DATA_ERROR/DUPLICATE_CURRENT_EXTRACTION`과 공고 ID·실행 개수를 반환하고 전체 선정을 중단한다. 실행 시각이나 ID로 임의 선택하지 않는다. 같은 회사의 다른 공고는 탐색 범위가 아니므로 이 검사에도 포함하지 않는다.

실제 public DDL의 `extraction_run_one_current` unique index는 중복을 예방한다. 이 검사는 index가 없거나 잘못된 과거 DB에 대한 추가 방어다. 기존 index나 trigger는 변경하지 않는다.

## 직무 매핑과 근거

직무 코드·직무군·정규식의 유일한 원본은 `backend/src/main/resources/posting-similarity.properties`다. Java에는 같은 매핑을 재작성하지 않는다. 테스트도 같은 리소스를 읽는다. 이는 공인 직무 분류가 아닌 버전 있는 MVP 내부 분류다.

판별 순서는 모집 단위명 → 공고 직무 분류 → 공고 제목이다. 앞선 입력에서 직무를 하나 찾았으면 이후 입력으로 바꾸지 않는다. 한 입력에서 여러 직무가 발견되면 `AMBIGUOUS`로 제외하고 metadata fallback도 하지 않는다. 어떤 입력에서도 찾지 못하면 `UNKNOWN`이다. metadata를 사용하더라도 공고의 특징 집합을 모집 단위에 합치지 않는다.

결과에는 `roleCode`, `familyCode`, `status`, `evidence`, `matchedRoleCodes`, `taxonomyVersion`이 포함된다. `evidence`는 `RECRUIT_UNIT_NAME`, `POSTING_CATEGORY`, `POSTING_TITLE`, `UNKNOWN` 중 하나이며 원문 자체는 복제하지 않는다.

`roles-mvp-2`는 ML 엔지니어, 머신러닝 엔지니어, Machine Learning Engineer를 ml_engineer로 인식한다. alias·패턴은 기존 설정 파일에만 정의한다.

| 직무군 | 설정된 직무 코드 |
|---|---|
| software | backend, frontend, fullstack, mobile, embedded, qa, software |
| data | data_engineer, data_scientist, ml_engineer |
| infrastructure | devops, security |

위 표는 설명이며 실행 시 매핑은 설정 파일에서만 읽는다. 모집 단위가 단일 직무로 판별되지 않으면 후보를 넓히기 위해 임의 분류하지 않는다. 포괄적인 software 패턴은 단독 일반 직무명에만 매칭되어 구체 직무명과 불필요하게 중복되지 않게 한다.

## 계산식과 순위

각 범주와 각 ID 공간에 대해 대상 집합 T, 후보 집합 C를 사용한다.

```
intersection = T ∩ C
coverage = |intersection| / |T|   (|T| > 0)
coverage = null                  (|T| = 0)
```

대상의 빈 집합끼리는 일치가 아니며 `comparable=false`다. 대상 집합이 존재하고 후보 집합이 비면 coverage는 0이다. 결과에는 양쪽 집합 크기, 교집합 ID, 교집합 수, coverage, 비교 가능 여부를 제공한다.

정책 `keyword-mvp-2`에서는 `PostingCandidateEligibility`가 순위 계산 전에 아래 통과 조건을 모두 검사한다.

- 대상에 필수 capability가 있으면 coverage가 설정된 최소 0.5 이상이어야 한다.
- 대상에 필수 tech가 있으면 tech 교집합이 최소 1개여야 한다.
- 필수 capability·tech의 전체 교집합 근거는 최소 2개다. 두 ID 공간은 분리하며 같은 범주 내 반복은 세지 않는다.
- 대상 필수 특징이 정확히 1개면, 그 필수 특징 일치 외에 우대·업무에서 다른 근거가 최소 1개 있어야 한다. 이 경우만 전체 근거에 추가 보조 근거를 포함하여 최소 2개를 충족한다. `confidence=LOW`, `LOW_EVIDENCE`로 표시한다.
- 보조 근거는 우대·업무의 같은 유형·같은 ID를 범주 간에도 중복 계산하지 않으며, 이미 일치한 필수 ID는 추가 근거에서 제외한다. 같은 숫자의 capability ID와 tech ID는 서로 다른 근거다.
- 일반 REQUIRED 모드에서는 우대·업무가 필수 coverage·tech 교집합·필수 근거 부족을 구제하지 않는다. 필수 특징이 1개인 예외만 위 규칙을 적용한다.

대상 필수 특징이 전혀 없으면 같은 직무 안에서 `FALLBACK_FEATURES` 모드로 우대·업무의 동일 범주끼리만 비교한다. 대상의 고유 보조 특징이 최소 2개, 보조 교집합도 최소 2개여야 한다. 이 모드는 `confidence=LOW`, `LOW_CONFIDENCE`를 반환한다. 대상 특징이 부족하거나 통과 후보가 없으면 `NOT_COMPARABLE/REQUIRED_FEATURES_MISSING`이다. 필수 근거를 가진 일반 후보는 통과 조건을 만족할 때 `confidence=HIGH`다. HIGH/LOW는 정책 근거 수준이며 통계적으로 검증된 정확도나 합격 확률이 아니다.

총점과 가중합을 만들지 않고 아래 순서를 사전식으로 비교한다.

1. 직무 단계: 현재는 EXACT_ROLE만 사용
2. 필수 capability coverage 내림차순
3. 필수 tech coverage 내림차순
4. 우대 capability coverage, 우대 tech coverage 내림차순
5. 업무 capability coverage, 업무 tech coverage 내림차순
6. 동률이면 후보 공고 ID, 후보 모집 단위 ID 오름차순

대상에 없는 특징 축은 모든 후보에서 비어 있으므로 순위에 기여하지 않는다. 우대·업무가 아무리 높아도 더 낮은 필수 일치도를 역전하지 못한다. capability와 tech의 숫자가 같아도 서로 일치한 것으로 보지 않는다. 공고 문장의 택1/모두·경력·학력 등 논리 조건을 이 점수로 판정하지 않는다.

## 선정과 제한

각 대상 모집 단위에 대해 따로 비교한다. 동일 후보 공고의 여러 모집 단위 중 순위가 가장 높은 하나만 대표로 남긴 뒤, 정렬된 목록을 순회하며 제한을 적용한다. 그러므로 최종 최대 개수는 모집 단위 개수가 아닌 **고유 공고 수**다. 대상 모집 단위가 달라지면 같은 후보 공고의 다른 모집 단위가 대표가 될 수 있다.

| 설정 키 (`posting-similarity.` 접두어) | 초기값 |
|---|---:|
| max-companies | 3 |
| max-postings-per-company | 2 |
| max-postings | 5 |
| required-capability-min-coverage | 0.5 |
| required-tech-min-intersection | 1 |
| minimum-total-evidence | 2 |
| sparse-required-supporting-evidence | 1 |
| fallback-minimum-target-features | 2 |
| fallback-minimum-intersection | 2 |
| job-family-expansion-enabled | false |

제한값은 시작 시 검증한다. 명시적인 허용 직무 조합표가 없으므로 동일 직무 결과가 0건이어도 직무군으로 확장하지 않는다. 현재 `job-family-expansion-enabled=true` 설정은 시작 시 검증 오류로 거부하며, 설정을 우회한 직접 서비스 호출에서도 다른 직무를 선정하지 않는다. SAME_IT_DOMAIN도 사용하지 않는다.

`SAME_JOB_FAMILY` enum은 응답 모델의 확장 지점으로 남아 있지만 현재 반환되지 않는다. 최종 stage는 EXACT_ROLE 또는 NONE이며 `familyExpansionAttempted=false`다.

## 동일 공고 합격자료

현재 외부자료에는 검증된 원본 공고 ID/URL 연결 계약이 없다. 이 MVP는 기존 `EXACT_ROLE`이나 회사명·직무 일치를 동일 공고 근거로 사용하지 않는다. `exactPostingEvidenceStatus=NOT_AVAILABLE`로 명시하고 타사 탐색을 수행한다. 기존 자료를 읽거나 연결을 변경하지 않는다.

향후 실제로 검증된 동일 공고 근거가 추가되면 별도 검증 계약을 서비스 앞단에 연결해야 한다. 지금은 확인하지 않은 동일 공고 자료가 있다고 주장하지 않는다.

## 결과 상태

- 최상위 `SELECTED`: 적어도 한 대상 모집 단위가 후보를 선정함.
- `NO_CANDIDATES`: 비교 가능한 대상은 있지만 적격 후보가 없음.
- `NOT_COMPARABLE`: 현재 추출 없음, IT 모집 단위 없음, 필수·보조 근거 부족, 직무 불명/모호 등.
- `DATA_ERROR`: 조회 범위에 복수의 현재 추출 결과가 있음. 후보를 반환하지 않음.
- 존재하지 않는 공고는 기존 `NotFoundException`, 0 이하 ID는 `IllegalArgumentException`.

모집 단위별 상태·사유가 별도로 있으므로 일부 대상만 비교 불가여도 나머지 결과는 유지된다. 최상위 reason=NONE인 다중 모집 단위 응답은 units의 reason을 확인한다. 후보별 confidence, featureMode, evidenceCount, requiredEvidenceCount, supportingEvidenceCount, evidenceFlags를 제공한다. 제외 후보의 exclusionReasons에는 한 가지 대표 사유만이 아닌 모든 미충족 통과 조건을 반환한다. 응답 policy.thresholds에 실제 적용한 최소 coverage·교집합·근거 수를 포함한다. 역할 판별 근거는 기존 role.evidence로 유지한다. 다른 직무처럼 탐색 범위 밖인 모든 모집 단위를 응답에 나열하지는 않는다.

## 확장 지점과 후속 작업

`PostingSimilarityScorer`가 계산 인터페이스이고 현재 구현체는 `KeywordPostingSimilarityScorer` 하나다. 향후 다른 방식의 점수를 추가해도 필수 자격 검사·단계 확장·회사 제한은 선정 서비스에 남겨야 한다. 임베딩 저장, 모델 호출, 의존성은 없다. 대규모 데이터에서는 전체 타사 특징을 메모리로 읽는 MVP 조회를 직무별 색인/특징 캐시 등으로 개선할 필요가 있다.

현재 [Comparison Candidates API](comparison-candidates-api.md)는 읽기 전용 controller와 요청 검증을 통해 지정 모집 단위의 결과를 노출한다. 크롤러 연결은 후보 공고 ID·회사 ID·직무 코드·선정 단계·정책 버전을 수집 대상으로 전달하는 별도 작업이다. 기존 same-company trigger와 Repository 조건은 그대로이므로 지금 결과를 기존 posting_pass_material에 바로 INSERT하면 안 된다. 자료 provenance·직무별 수집 상태·새 연결 제약은 별도 승인된 변경이 필요하다.

## 검증

- Java 21에서 `gradlew.bat test`로 단위·기존 Backend 회귀 테스트를 실행한다.
- PostgreSQL Repository 테스트는 `POSTING_SIMILARITY_TEST_URL`을 명시했을 때만 실행한다. URL은 loopback과 `extcrawler_test_similarity_[a-z0-9]+` 이름만 허용한다. 사용자·비밀번호도 전용 실행 환경변수로만 전달한다.
- `db/tests/prepare_posting_similarity.py`는 `POSTING_SIMILARITY_TEST_DSN`의 새 빈 로컬 테스트 DB에만 실제 public DDL과 합성 fixture를 적용한다. 기존 데이터가 있으면 중단하며 DB를 삭제·초기화하지 않는다.
- 테스트 환경변수를 설정하지 않은 실행에서 PostgreSQL 테스트가 skip되면 PostgreSQL 검증 성공으로 보고하면 안 된다.
- 데이터 오류 테스트 2개는 격리 fixture DB의 트랜잭션 안에서만 unique index를 임시 해제해 손상 상태를 재현하고 항상 rollback한다. 운영·팀·기존 로컬 DB의 index와 trigger에는 접근하지 않는다.
- 정상 Repository/선정 검증은 실제 READ ONLY 트랜잭션과 public 전체 테이블 행 수·해시 전후 비교로 쓰기가 없음을 확인한다.

### 검증 기록

후보의 회사·모집 단위·confidence·근거·정책을 별도 Python 배치에 전달하는 [외부자료 수집 연결](external-pass-collection.md)이 추가됐다. 유사도 계산은 이 Java 서비스에만 있으며 Python에서 재구현하지 않는다. 타사 자료의 출처는 별도 요청 테이블에 남기고 기존 동일 회사 자료 연결 제약은 유지한다.

선정 v2의 전수 통계·수동 점검·v1 대비 변화·잔여 위험은 [공고 유사도 검증 보고서](verification/posting-similarity-verification.md)에 기록한다. 후속 HTTP API·Swagger·팀 DB READ ONLY 및 전후 불변 검증은 [API 검증 보고서](verification/comparison-candidates-api-verification.md)로 구분한다. 선정률을 정확도로 표현하지 않는다.
