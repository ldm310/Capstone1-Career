# 유사 공고 기반 외부 합격자료 수집과 상태 조회

현재 키워드 기반 [선정 서비스](posting-similarity.md)와 [비교 후보 API](comparison-candidates-api.md)를 그대로 사용한다. Python은 유사도·순위·직무군 확장을 다시 계산하지 않는다. 실제 환경의 적용·수집 여부는 [검증 보고서](verification/external-pass-collection-verification.md)와 구분한다.

## 처리 흐름

1. 기존 Daily가 채용공고와 현재 추출을 DB에 저장한다. 저장 실패 공고는 완료로 취급하지 않는다.
2. 별도 배치가 명시한 대상 모집 단위 또는 `--since` 이후의 **커밋된 현재 IT 모집 단위**를 읽는다.
3. Backend 비교 후보 GET을 호출하고 ID·정책·confidence·featureMode·근거·회사 제한을 검증한다.
4. 동일 회사·동일 표준 직무로 현재 공고에 직접 연결된 자료가 있으면 우선 사용한다.
5. 없으면 선정된 타사 후보의 출처를 저장하고 HIGH 회사부터 처리한다. HIGH가 모두 완료된 뒤 실제 동일 직무 자료가 2건 미만일 때만 LOW를 처리한다.
6. 이미 READY·INSUFFICIENT·FAILED인 회사는 재크롤링하지 않는다. 기존 자료를 후보 회사의 공고와 재연결한다. RUNNING은 대기하고 PENDING은 행 잠금으로 한 번만 획득한다.
7. 실제 자료는 자료 회사의 후보 공고에 연결한다. 타사 자료를 목표 공고의 기존 동일 회사 연결 테이블에 직접 삽입하지 않는다.
8. 프론트의 상태 GET은 읽기만 한다. 등록·재시도·크롤링은 별도 배치에만 있다.

`--since`는 페이지당 최대 `--max-targets`개(기본 50, 최대 100)를 처리한다. 대량 유입 시 같은 시간 창을 재실행하거나 대상을 명시해 남은 모집 단위를 처리해야 한다. 이 버전은 영구 dispatch cursor를 제공하지 않는다. 같은 요청·회사 작업의 재실행은 중복 자료나 회사 재수집을 만들지 않는다.

## DB 계약과 migration

기본 자료 계약의 원본은 `db/init/04-external-pass-material.sql`이다. 팀 계정에는 새 스키마 생성이나 기존 공고 쓰기 권한이 없으므로 새 배포는 이 계약과 migration 07을 **새로 소유하는 public 테이블**로 설치한다. `storage.py`의 고정 이름 목록으로만 변환하며 기존 pipeline 식별자·값은 바꾸지 않는다. `role_name`에는 표준 직무 코드(`backend` 등)를 저장한다. 기존 자유 텍스트 직무를 임의 변환하지 않으며 새 비교에서는 코드가 정확히 같은 자료만 센다.

추가 구조 `db/migrations/07-external-pass-collection-requests.sql`:

| 객체 | 역할 |
|---|---|
| `public.external_pass_company_collection` | 회사별 공유 수집 상태·시각·실행 횟수·안전한 오류 코드 |
| `public.external_pass_material` | 회사 FK, 출처 ID, 표준 직무, 개인정보 없는 기술 JSON |
| `public.external_pass_posting_material` | 자료 회사의 공고에만 허용하는 명시적 자료 연결 |
| `public.external_pass_collection_request` | 목표 공고·모집 단위, 표준 직무, 정책 버전, 선정 상태, 요청 출처, 직접 자료 사용 여부 |
| `public.external_pass_collection_candidate` | 후보 공고·모집 단위·회사, confidence, featureMode, evidenceCount, 기존 rank, 요청·재사용 여부 |
| `public.external_pass_schema_migration` | 설치한 migration 버전·checksum·적용 시각 |

별도 출처 테이블은 **타사 비교**와 기존 **동일 회사 자료 연결**의 의미를 분리하기 위해 필요하다. 모든 외부 FK는 실제 `public` 객체를 참조한다. Trigger는 목표·후보 모집 단위 소속, 현재 IT 후보, 후보 회사, 타사 조건, 동일 표준 직무를 검사한다. 기존 public 테이블·index·trigger·행은 수정하지 않는다.

정식 적용 진입점은 다음 CLI 하나다. DB 연결은 실행 환경이 주입한다.

```sh
python -m external_pass_crawler.migrate
```

설치기는 public CREATE와 기존 회사·공고·추출·모집 단위의 SELECT/REFERENCES를 검사한 뒤 `public-07`을 **한 트랜잭션**에서 적용한다. 기존 public 테이블·행·정의는 수정하지 않는다. `tech_capability`에는 FK를 만들지 않는다. 기존 테이블에 UPDATE 권한이 필요한 명시적 행 잠금도 사용하지 않는다. 새 소유 테이블의 작업 잠금은 유지한다.

일부만 설치된 구조, 다른 소유자의 동명 테이블, 함수·index 이름 충돌, checksum 불일치는 전체 rollback한다. 적용 전후 **신규 소유 테이블을 제외한 기존 public 전체**의 행 수·내용 해시를 비교한다. 재실행은 기존 소유 테이블과 행을 유지한다. Backend 시작이나 GET은 설치를 실행하지 않는다.

과거 `external_data` 저장소는 회귀 호환 읽기만 유지한다. 새 public 저장소를 우선 사용하며 과거 저장소에 데이터가 남아 있으면 설치기가 자동 복사·숨김을 하지 않고 명시적 데이터 migration을 요구한다. 빈 과거 구조는 그대로 보존한다. 두 저장소에 동시에 쓰지 않는다.

## 수집 정책

| 항목 | 정책 | 이유 |
|---|---|---|
| 대상 우선순위 | 직접 연결 → 타사 동일 직무 HIGH → 부족하면 LOW | 근거 수준과 실제 확보 자료 수를 함께 반영 |
| 확장 | SAME_JOB_FAMILY 자동 확장 없음 | 현재 승인된 키워드 정책 유지 |
| 회사 일치 | 법인 표기·공백·대소문자 정규화 후 정확 일치, 명시적 alias만 허용 | 부분 일치·계열사 오연결 방지 |
| 직무 | IT 단일 직무만 인정, 모호하거나 판별 불가면 제외 | 임의 직무 승격 방지 |
| 접근 | 공개 robots.txt, 공개 검색·상세만 | 공개 접근 정책 준수 |
| 차단 | robots 차단·401·403·429·CAPTCHA면 배치 전체 즉시 중단 | 재시도·다른 회사 요청을 통한 우회 방지 |
| 요청 간격 | 기본 2초, robots crawl-delay가 더 길면 적용 | 부하 제한 |
| 동시성 | DB session advisory lock으로 기존·신규 CLI 합쳐 1개 | 중복 외부 요청 방지 |
| 회사당 한도 | 최대 5페이지·후보 100건 | 무제한 탐색 방지 |
| 배치 한도 | 실제 수집을 시작할 회사 최대 3곳 | 신규 회사도 최대 3곳으로 제한 |
| 회사 순서 | HIGH 우선, 같은 confidence는 기존 rank | BE 선정 순위 유지 |
| 재사용 | READY는 재수집 없이 연결만 보완 | 같은 회사 자료 공유 |
| 재시도 | INSUFFICIENT·FAILED 자동 재등록 없음 | 부족·실패 원인 확인 후 별도 운영 결정 |
| stale worker | attemptCount와 RUNNING을 잠금 안에서 재검사 | 이전 워커의 결과 덮어쓰기 방지 |
| 이전 접근 차단 | 저장된 ACCESS_RESTRICTED가 있으면 신규 회사 요청도 중단 | 운영 확인 전 플랫폼 재접근 방지 |

실패 회사의 자동 초기화 명령은 제공하지 않는다. 안전한 오류 코드와 접근 정책을 운영자가 검토한 뒤 별도 절차로 재시도해야 한다. LOW는 참고 자료이며 추천·적합 판정으로 표현하지 않는다.

## 개인정보와 저장 내용

링커리어 Adapter·Parser가 공통 privacy 모듈을 사용한다. 기존 회사 CLI와 후보 배치는 원문을 메모리에서만 처리하고 content에 기술명·technologySignals·projectSignals를 담은 JSON 문자열을 저장한다. 이름·학교·연락처·프로필은 이 요약에 포함하지 않는다. 제목은 표준 직무로 생성하고 source_url은 링커리어 공개 원문 확인용 URL이다. 아래 일일 수집은 별도 본문 저장 경로를 사용한다.

```json
{
  "technologies": ["Python", "Spring"],
  "technologySignals": [{"technology": "Spring", "signals": ["FEATURE_IMPLEMENTATION", "TESTING"]}],
  "projectSignals": ["FEATURE_IMPLEMENTATION", "TESTING"]
}
```

기술 단순 언급을 숙련도·실제 사용·검증된 보유로 바꾸지 않는다. 기술 사전 매핑은 기존 [키워드 API](external-pass-keywords.md)의 name 우선·alias 후순위 정확 매칭을 사용한다. 매핑되지 않은 항목은 해당 후보 공고의 `external-pass-keywords` 응답에서 unmappedKeywords로 확인한다. LV·점수·합격 확률은 생성하지 않는다.

## 배치와 Docker 실행

필요한 환경변수는 런타임에서만 제공한다.

| 변수 | 용도 |
|---|---|
| `DATABASE_URL` | Python CLI용 명시적 DB 연결 |
| `BACKEND_URL` | 새 비교 후보 API가 배포된 Backend |
| `EXTERNAL_DATABASE_URL` | Compose·Airflow에서 위 DB 연결에 전달하는 전용 비밀값 |
| `EXTERNAL_BACKEND_URL` | Compose·Airflow의 Backend 주소 |
| `EXTERNAL_CRAWLER_DIR` | Airflow worker에 읽기 전용으로 mount한 크롤러 패키지 경로 |

```sh
# 저장소 루트에서 실행. 실제 비밀값은 명령 본문이나 파일에 넣지 않는다.
docker compose -f compose.yaml -f compose.external-pass.yaml --profile external-pass build external-pass-batch

# 배치 등록 dry-run: BE 응답만 확인하고 DB·크롤링은 실행하지 않는다.
docker compose -f compose.yaml -f compose.external-pass.yaml --profile external-pass run --rm external-pass-batch \
  --target-posting-id 1447 --target-recruit-unit-id 2509 --dry-run

# 실제 회사 작업 등록·수집: 권한과 공개 접근 조건을 충족한 실행 환경에서만 사용한다.
docker compose -f compose.yaml -f compose.external-pass.yaml --profile external-pass run --rm external-pass-batch \
  --target-posting-id 1447 --target-recruit-unit-id 2509

# 사이트에 접근하지 않고 신규 소유 테이블에 출처와 PENDING 작업만 등록한다.
docker compose -f compose.yaml -f compose.external-pass.yaml --profile external-pass run --rm external-pass-batch \
  --target-posting-id 1447 --target-recruit-unit-id 2509 --register-only

# DB 설치 전용 실행: Backend API 또는 수집 실행과 분리한다.
docker compose -f compose.yaml -f compose.external-pass.yaml --profile external-pass run --rm \
  --entrypoint python external-pass-batch -m external_pass_crawler.migrate
```

이미지는 비root 사용자·읽기 전용 파일시스템으로 실행한다. Dockerfile 전용 ignore 목록으로 필요한 소스·SQL만 build context에 전달하며 env·work·IDE·Frontend·빌드 결과물은 제외한다. 기본 회사 CLI의 `--dry-run --max-records 3 --max-pages 1`은 공개 자료 최대 3건을 읽고 개인정보 없는 요약만 검증하며 DB는 READ ONLY다. 실제 접근 제한이 있으면 dry-run도 즉시 중단한다.

## Airflow 연결

동반 DAG `data-pipeline/external-pass-crawler/airflow/dags/external_pass_after_daily.py`는 기존 `daily_collect.load_db`의 성공을 기다린 뒤 별도 배치를 실행한다. 기존 Daily·OCR·LLM·저장 형식은 수정하지 않는다. 동반 DAG는 기본 paused이고 catchup=false, max_active_runs=1이다. 설치 환경에 표준 provider, 크롤러 패키지, 전용 연결 설정이 있어야 한다. 코드 추가만으로 기존 운영 Airflow에 배포·활성화되지는 않는다.

두 DAG는 같은 KST 일별 schedule과 logical date를 사용해야 한다. 수동 Daily 실행은 companion을 자동 trigger하지 않으므로 저장 성공 후 명시적 대상 또는 `--since` CLI를 실행한다. 센서의 동작은 [Airflow ExternalTaskSensor 공식 문서](https://airflow.apache.org/docs/apache-airflow-providers-standard/stable/_api/airflow/providers/standard/sensors/external_task/index.html)를 따른다.

## 상태 API

`GET /api/postings/{postingId}/recruit-units/{recruitUnitId}/external-pass-collection-status`

READ ONLY·REPEATABLE READ로 선정 결과·요청·회사 상태·자료 수를 읽는다. 자료 총수는 동일 회사·동일 표준 직무·허용 관계를 만족하는 **고유 material ID 수**다. 동일 회사의 여러 후보 공고에 같은 자료가 연결돼도 총수에는 한 번만 센다.

```json
{
  "postingId": 1, "recruitUnitId": 11,
  "candidateSelectionStatus": "SELECTED", "collectionStatus": "READY", "source": "CANDIDATES",
  "selectedCandidateCount": 1, "highCandidateCount": 1, "lowCandidateCount": 0,
  "requestedCompanyCount": 1, "readyCompanyCount": 1, "materialCount": 5,
  "lastRequestedAt": "2026-11-08T00:00:00+09:00", "startedAt": "2026-11-08T00:00:00+09:00",
  "completedAt": "2026-11-08T00:00:10+09:00", "retryable": false, "safeErrorCode": null,
  "userMessage": "합격자료 비교가 준비되었습니다.", "policyVersion": "keyword-mvp-2",
  "candidates": [{"companyId": 2, "candidatePostingId": 3, "candidateRecruitUnitId": 31,
    "standardRoleCode": "backend", "confidence": "HIGH", "collectionStatus": "READY",
    "materialCount": 5, "reused": true, "relationType": "EXACT_ROLE"}]
}
```

예시는 합성 값이다. 상태는 NOT_REQUESTED → PENDING → RUNNING → READY/INSUFFICIENT/FAILED 순이다. READY 등은 해당 회사의 전체 자료 상태이고 API 최상위 READY는 실제 해당 직무의 자료가 2건 이상 준비됐다는 뜻이다. HIGH가 미요청·대기·실행 중이면 이전 LOW 자료로 준비 완료를 선언하지 않는다. `retryable=false`는 API가 자동 재시도를 제공하지 않는다는 뜻이다.

## 로컬 일일 수집

수집은 로컬 Docker, 저장은 기존 RDS에서 수행한다. 매일 **KST 09:00**에 실행하며 PC와 Docker가 켜져 있어야 한다. 9시 이전 시작 시 정시까지 기다리고, 9시 이후 시작 시 당일 누락 실행을 보완한다. 당일 종료한 배치는 재시작해도 중복 실행하지 않는다.

1. 진행 중인 공고의 현재 IT 모집 단위를 전체 스캔한다. 과거 공고도 포함한다.
2. 링커리어 자료 연결 없음, 회사 자료 2건 미만, 기존 자료 본문 누락 중 하나에 해당하면 회사별로 묶는다.
3. 본문 보완 → 신규 회사 → 가장 오래 확인한 회사 순으로 처리한다. 실제 요청은 회사별 KST 하루 한 번이다.
4. 공개 검색·상세의 회사·직무를 확인하고, 본문·기술 요약·공고 연결·완료 상태를 한 트랜잭션에서 저장한다.
5. 자료가 없거나 부족하면 다음 날 다시 확인한다. 일일 작업 소유 RUNNING이 6시간 넘게 중단됐을 때만 회수한다. 다른 CLI 작업은 회수하지 않는다.

기본 한도는 하루 30개 회사, 회사당 2페이지·후보 40건이다. 미처리 대상은 다음 날 순환한다. `remaining_backlog=true`는 회사 한도, `truncated=true`는 페이지·후보 상한을 뜻한다. 접근 제한 즉시 중단과 전체 크롤러 공통 advisory lock은 유지한다. API의 `retryable=false`는 사용자 요청에 의한 재시도가 없다는 뜻이며 일일 배치의 다음 날 재확인과 구분한다.

| 추가 테이블 | 역할 |
|---|---|
| `public.external_pass_material_body` | material ID별 줄글·SHA-256·추출 상태·시각 |
| `public.external_pass_daily_company` | 출처·회사별 실제 시도 시각 |
| `public.external_pass_daily_run` | KST 날짜별 실행 상태·안전한 집계 |

본문은 HTML·스크립트와 직접 연락처·식별번호 형태를 제거·마스킹하고 `PENDING`으로 저장한다. 별도 작성자 프로필은 수집하지 않는다. 완전한 익명화는 아니므로 서술에 포함된 경력·학교명 등은 남을 수 있다. 본문은 기존 API·로그에 노출하지 않는다. 동일 해시면 추출 상태를 유지하고, 본문이 바뀌면 다시 PENDING으로 설정한다. 임베딩 추출은 이후 단계다.

기존 회사 전체 READY 기준과 비교 API의 최소 표본은 **2건 이상**이다. 비교 API는 동일 표준 직무 자료만 세므로 서로 다른 직무 두 건을 같은 직무 두 건으로 보지 않는다. 기존 SQL 04·07은 checksum을 유지하고 public-08로 전환한다.

```powershell
python deploy/external-pass/manage_daily.py --env-file <비공개-env-파일> build
python deploy/external-pass/manage_daily.py --env-file <비공개-env-파일> migrate
python deploy/external-pass/manage_daily.py --env-file <비공개-env-파일> scan
python deploy/external-pass/manage_daily.py --env-file <비공개-env-파일> once --company-id 1721
python deploy/external-pass/manage_daily.py --env-file <비공개-env-파일> once --company-id <확인한-회사-ID> --company-search-name NHN
python deploy/external-pass/manage_daily.py --env-file <비공개-env-파일> start
python deploy/external-pass/manage_daily.py --env-file <비공개-env-파일> status
python deploy/external-pass/manage_daily.py --env-file <비공개-env-파일> logs
```

env 파일은 `DATABASE_URL` 또는 `EXTERNAL_DATABASE_URL`을 제공한다. 비밀값은 인자·로그·커밋에 포함하지 않는다. `migrate`만 DDL을 수행하며 GET·서비스 시작은 자동 migration을 하지 않는다. `scan`은 DB 읽기만 하고 크롤링·저장을 수행하지 않는다. 서비스는 비root·읽기 전용 파일시스템·`restart: unless-stopped`로 실행한다.

`--company-search-name`은 공식 자료로 확인한 동일 법인의 검색용 별칭을 단일 회사 실행에 명시하는 옵션이다. 회사 ID는 환경별로 확인해야 한다. 별칭은 검색어와 회사 정확 일치 허용 목록에 함께 쓰며, 검색 결과와 상세의 회사가 원래 회사 또는 지정 별칭과 일치해야 한다. `NHN AD`, `NHN클라우드` 등 계열사는 `NHN`과 일치하지 않는다. 자동 별칭 추론·일일 서비스의 전체 회사 별칭 적용은 제공하지 않는다. 회사별 당일 재시도 제한·페이지/후보 상한·접근 차단 중단은 그대로 적용한다. `--dry-run`은 DB 대상 스캔만 하므로 별칭 검색의 실제 결과를 미리 조회하지 않는다.

일일 수집 결과에 `examined`(검색 후보 검사), `foreign_company`(검색 또는 상세의 타사), `excluded`(비IT·모호한 직무)를 추가했다. `accepted`와 함께 자료 부족이 검색 결과 부재인지 회사/직무 제외인지 구분하는 데 사용한다. 기존 일일 기록에는 새 집계가 없을 수 있다.

400은 잘못된 ID·소속 불일치, 404는 공고·모집 단위 없음, 409는 선정 데이터 오류·미적용 스키마·현재 선정과 불일치하는 오래된 요청이다. 후보 없음과 비교 불가는 200이며 candidateSelectionStatus와 userMessage로 설명한다. 모든 응답은 Swagger에 등록한다.

## 검증과 확장

`python db/tests/verify_external_collection.py --java-home <Java 21 경로>`는 새 PostgreSQL 18 컨테이너에서 migration·크롤러·Backend 전체를 검증하고 임시 DB를 제거한다. 실제 팀 DB 설정을 읽지 않는다. PostgreSQL 선택 테스트를 skip한 결과를 전체 검증으로 보고하지 않는다.

검증 실행에 `--owned-public --with-http-smoke`를 추가하면 신규 소유 public 저장소와 실제 HTTP 연결까지 확인한다. 테스트에는 public CREATE·SELECT·REFERENCES만 주고 기존 공고 INSERT/UPDATE와 tech_capability REFERENCES를 주지 않은 역할의 설치·저장 검증이 포함된다.

기존 공고·추출 테이블에 대한 이 계정의 쓰기는 금지돼 있다. 오늘 공고의 증분 반영은 기존 Daily 운영 계정이 수행해야 하며 이 기능이 pipeline 테이블을 복사하거나 대신 수정하지 않는다. 수집 runtime 배포, 실제 운영 Daily 접근과 대량 dispatch cursor가 별도 운영 과제다. 임베딩은 추가하지 않았다. 이후 `PostingSimilarityScorer` 구현을 추가하는 지점에서 검토하되 후보 통과 조건·HIGH/LOW·회사 제한·수집 provenance 계약은 유지한다.
