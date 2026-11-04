# 외부 합격자료 크롤러 (Linkareer MVP)

`feature/external-pass-crawler`의 독립 Python CLI다. 기존 `job-skill/` 모듈을 import하거나 수정하지 않는다. 새 테이블·컬럼·마이그레이션은 만들지 않는다.

## 확인한 기존 구조와 BE 계약

- 기존 사람인 파이프라인은 `job-skill/collect.py → db_queries.py/db_load.py`로 동작하며 psycopg와 `DATABASE_URL`을 사용한다. 확인한 브랜치에서는 `public` 스키마와 RDS/.env 선택 로직을 사용한다.
- 새 크롤러는 기존 파이프라인과 분리된 `DATABASE_URL`을 **명시적으로** 받아 사용한다. .env/RDS를 자동 선택하지 않는다.
- 아래 원격 BE 문서·SQL을 읽고 구현했다.

```powershell
git show origin/feature/BE:backend/docs/external-pass-materials.md
git show origin/feature/BE:db/init/04-external-pass-material.sql
```

- 실제 저장 대상은 `external_data.company_collection`, `pass_material`, `posting_pass_material`이다.
- 공고·회사 조회 기본 스키마는 BE 계약의 `job`이다. `--posting-schema public`은 **BE의 FK도 public을 참조하도록 이미 운영 계약이 정리된 DB에서만** 사용한다. 필수 테이블·컬럼과 실제 FK 참조 스키마를 쓰기 전에 검사한다. 둘이 다르면 `BE_CONTRACT_MISMATCH`로 종료한다. 스키마를 자동 복사·변경하지 않는다.
- SQL 04는 실행자가 해당 환경의 BE 절차에 따라 미리 적용해야 한다. CLI와 테스트 코드 자체에는 DDL이 없다.
- `pass_material.job_family='IT_SW'` CHECK 때문에 비IT 자료를 저장할 수 없다. 비IT/직무 판별 불가 **원본**은 EXCLUDED로 분류해 제외 건수만 보고한다. 저장된 IT 자료가 비IT/불명확 **공고**에 연결될 때는 연결의 `relation_type=EXCLUDED`로 남긴다.
- READY는 자료 1건을 찾았다는 뜻이 아니다. BE 계약의 회사 작업 `minimum_sample_size`(기본 5) 이상이면 READY, 미만이면 INSUFFICIENT다.

## 파일 구조

```text
external_pass_crawler/
  __main__.py                 CLI·설정·출력, dry-run read-only DB 연결
  repository.py               계약 검사·회사 큐·행 잠금·upsert·공고별 연결·상태 저장
  runner.py                   회사별 수집/검증/요약/완료·실패 처리
  classification.py           MVP 표준 직무 코드·분야·관계·엄격한 회사 비교
  privacy.py                  허용 기술명·관찰된 수행 신호를 JSON 문자열로 변환
  models.py / errors.py       입력·출력 자료형과 안전한 오류 코드
  platforms/base.py           플랫폼 Adapter 프로토콜
  platforms/linkareer.py      공개 HTTP 요청·robots·간격·접근 제한
  platforms/linkareer_parser.py  공개 HTML의 SSR 데이터 파싱
tests/fixtures/               합성 공개 HTML 구조 (실제 개인 원문 없음)
tests/test_*.py               Parser/정책/분류/회사 큐/DB 통합 검증
```

## 실행

Python 3.12 이상을 권장한다. Python 3.14 / psycopg 3.3.8에서 검증했다.

```powershell
cd data-pipeline/external-pass-crawler
py -3.14 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

# BE 계약과 회사 ID가 일치하는 DB를 직접 지정한다. 실제 비밀번호를 커밋하지 않는다.
$env:DATABASE_URL = 'postgresql://USER:PASSWORD@HOST:PORT/DBNAME'

# 특정 회사 미리보기: DB에는 어떤 작업/상태/자료/연결도 저장하지 않는다.
.\.venv\Scripts\python.exe -B -m external_pass_crawler --company-id 123 --dry-run

# 특정 회사의 신규 작업만 수집. 이미 완료된 회사는 기존 자료 연결만 보완한다.
.\.venv\Scripts\python.exe -B -m external_pass_crawler --company-id 123

# 공고가 있는 회사들을 PENDING 등록하고 최대 3개 신규 회사 작업을 수행한다.
.\.venv\Scripts\python.exe -B -m external_pass_crawler --max-companies 3
```

macOS/Linux는 `python3 -m venv .venv`와 `.venv/bin/python`으로 바꿔 실행한다.

| 설정 | 기본값 | 설명 |
| --- | --- | --- |
| --company-id | 전체 | 해당 DB의 회사 숫자 ID만 선택 |
| --max-companies | 1 | 이번 실행에서 수집할 회사 작업 수 |
| --request-interval / EXTERNAL_REQUEST_INTERVAL | 2초 | 요청 간 최소 간격, 최소 1초 |
| --timeout / EXTERNAL_TIMEOUT | 20초 | 각 공개 HTTP 요청의 타임아웃 |
| --max-records / EXTERNAL_MAX_RECORDS | 100 | 회사별 검사할 검색 후보 상한 (타사/비IT 포함) |
| --max-pages / EXTERNAL_MAX_PAGES | 5 | 회사별 검색 페이지 상한 |
| --posting-schema | job | job/public 중 실제 BE FK 대상과 동일해야 함 |
| --aliases-file | 없음 | 명시적 회사 ID → 허용 회사명 배열 JSON |

aliases 예: `{"123": ["Example Company", "예시회사"]}`. 기본 회사 비교는 법인 표기·공백·대소문자만 정규화한다. 부분 일치, 계열사 추론, 다른 회사 같은 직무 fallback은 하지 않는다. alias는 검색 결과의 회사 확인에 사용하며 회사 검색은 DB의 회사명으로 수행한다.

`--dry-run`은 PostgreSQL 연결 자체가 read-only다. 새 회사/PENDING 회사는 공개 검색과 분류를 미리 수행하고 건수만 출력한다. 이미 완료/실패/실행 중인 회사는 `reuse_or_in_progress`로 보고하며 재수집하지 않는다.

출력 예시는 원문·이름·연락처 없이 다음과 같다.

```json
{"company_id":123,"status":"INSUFFICIENT","total_materials":2,"examined":20,"foreign_company":3,"excluded":15,"accepted":2,"truncated":false}
```

`truncated=true`면 최대 후보·페이지 한도 때문에 검색 전체를 보지 않은 것이다. INSUFFICIENT는 이 제한 안에서 자료가 부족하다는 의미이며 전체 사이트에 자료가 없다고 단정하지 않는다.

## 회사 단위 데이터 흐름

1. DB 공고를 회사 ID별로 확인하고 `INSERT ... SELECT DISTINCT ... ON CONFLICT(company_id) DO NOTHING`으로 신규 작업만 등록한다.
2. 완료된 회사에 새 공고가 있으면 저장된 같은 회사 자료를 재사용해 관계만 연결한다. 재수집·상태 초기화·attempt 증가를 하지 않는다.
3. PENDING 작업을 `FOR UPDATE SKIP LOCKED`로 한 회사씩 획득하고 RUNNING 변경을 commit한다. 웹 요청 동안 DB 행 잠금을 유지하지 않는다.
4. 공개 검색 HTML → 후보 회사 확인 → 직무 분류 → 공개 상세 HTML → 회사 재확인 → 기술명·관찰된 수행 신호 JSON 문자열을 만든다.
5. 저장 트랜잭션에서 회사 작업을 잠그고 RUNNING·attempt_count를 재확인한다. 다른 시도의 결과를 오래된 워커가 덮어쓰지 못한다.
6. `source_platform='linkareer'` + 외부 숫자 ID로 upsert한다. 동일 출처 ID가 타사에 속해 있으면 전체 저장 트랜잭션을 rollback하고 FAILED 처리한다.
7. 같은 회사의 각 공고와 자료를 연결하고 연결별 relation_type을 upsert한다. 회사 전체 고유 자료 수를 계산해 READY/INSUFFICIENT와 완료 시각을 저장한다.
8. HTTP 제한·레이아웃 변경·DB 저장 오류는 FAILED와 안전한 error_code로 기록한다. 원본 예외 메시지·DSN·HTML은 DB나 로그에 남기지 않는다. DB 연결 자체가 끊겨 FAILED를 기록할 수 없는 경우 CLI 오류로 종료한다.

재시도나 강제 종료된 RUNNING 작업 회수는 자동으로 수행하지 않는다. 운영자가 원인을 확인하고 BE 상태 계약에 맞춰 명시적으로 PENDING으로 재등록해야 한다. 새 공고가 생겼다는 이유로 완료된 회사 작업을 재수집하지 않는다.

## 직무 관계와 개인정보

- MVP 표준 직무는 코드의 역할/분야 사전이다. backend/frontend/mobile/software 등은 software 분야, data_engineer/data_scientist/ml_engineer는 data 분야, devops/security는 infrastructure 분야로 분류한다. 중앙 직무 사전 테이블을 추측하거나 새로 만들지 않는다.
- 공고의 확인된 `site_job_category`와 `title`로 직무를 판별한다. 관계는 EXACT_ROLE → SAME_JOB_FAMILY → SAME_IT_DOMAIN → EXCLUDED 순이다. 검색 후보의 상세 요청도 페이지 내에서 이 우선순위를 적용한다.
- 역할 정보가 비IT·불명확하면 본문에 Python이 있더라도 IT 직무로 승격하지 않는다.
- 직무별 정규식은 보수적인 MVP 규칙이므로 새로운 표현은 사전과 테스트를 보완해야 한다. 회사·직무 오판을 줄이기 위해 퍼지 매칭을 사용하지 않는다.
- 자소서 원문, 작성자명, 학교, 연락처, 프로필, 원본 HTML은 저장하지 않는다. 이름 탐지 정규식만으로 개인정보 제거를 보장할 수 없기 때문에 **content에는 허용 기술명과 수행 신호 코드만 담은 JSON 문자열**을 저장한다. title과 role_name도 표준 역할 코드로 생성한다. 개인 원문은 공개 Parser의 메모리에서만 처리한다.
- `published_at`은 확인된 발행일이 없어 NULL을 유지한다. 합격연도나 createdAt을 임의로 발행 시각으로 만들지 않는다.
- 이 구조는 관찰된 표현을 분류한 것으로 실제 수행 사실을 인증하거나 표준 capability 평가·사용자 LV·합격 확률을 계산하지 않는다. 자세한 원문은 source_url로 확인한다.

### content의 구조화된 수행 신호

BE 계약의 기존 content 타입은 **TEXT NOT NULL**이다. 테이블·컬럼·저장 SQL을 변경하지 않고 아래 JSON을 직렬화한 문자열을 저장한다.

```json
{"technologies":["Spring","Docker"],"projectSignals":["FEATURE_IMPLEMENTATION","TESTING","DEPLOYMENT"]}
```

projectSignals의 허용값은 BASIC_USE, FEATURE_IMPLEMENTATION, INTEGRATION, TESTING, SECURITY_RELIABILITY, DEPLOYMENT, OPERATION, OPTIMIZATION, ARCHITECTURE다. 원문 인용·추가 자유 텍스트·이름·학교·연락처·점수·LV는 포함하지 않는다. 기술이나 신호가 없으면 해당 값은 빈 배열이다.

- 단순 사용 경험은 BASIC_USE로만 기록한다. 기술명 나열이나 Docker 언급만으로 구현·테스트·배포를 추론하지 않는다.
- 기술/프로젝트 문맥에서 수행을 명시한 표현만 기록한다. 예: “기능을 구현했습니다”, “단위 테스트를 작성했습니다”, “서비스를 배포했습니다”.
- 부정·계획·의향·요구·학습 표현, HTML 스크립트·인용 블록은 신호 근거로 사용하지 않는다.
- 규칙은 privacy.py 한 곳에 있다. 문장 단위의 보수적 검사이므로 수행과 부정이 섞인 문장이나 미지원 표현은 누락될 수 있다. 누락을 LV 또는 확인되지 않은 신호로 보충하지 않는다.
- BE API의 content 필드도 기존처럼 문자열이다. 소비자가 JSON을 파싱해 두 배열을 읽어야 한다. 기존 일반 요약문은 자동 변환하지 않으며, 이전 데이터 소비자는 JSON 파싱 실패를 처리해야 한다. 자료를 명시적으로 재수집/upsert할 때 새 형식으로 갱신된다.

## 공개 접근 정책

공개 `https://linkareer.com/robots.txt`를 먼저 확인하고 허용된 `/cover-letter/search`, `/cover-letter/<숫자 ID>` HTML만 요청한다. robots를 읽지 못하면 수집을 시작하지 않는다. robots의 crawl-delay가 설정값보다 크면 그 값을 따른다. 리다이렉트, 로그인, CAPTCHA/챌린지, 401/403/429는 우회·자동 재시도하지 않는다. 브라우저 자동화·로그인 쿠키·비공개 GraphQL API 호출을 사용하지 않는다.

Parser는 공개 HTML의 `__NEXT_DATA__ → __APOLLO_STATE__` 구조만 처리한다. 구조가 달라졌거나 공개 상세 content가 없으면 빈 결과로 오인하지 않고 FAILED로 처리한다. 실제 공개 검색 1페이지와 상세 1건으로 구조를 검증했으며 HTML을 파일에 보관하지 않았다.

## 테스트

네트워크나 DB 없이 합성 HTML fixture·분류·HTTP 정책 테스트:

```powershell
.\.venv\Scripts\python.exe -B -m unittest discover -s tests -v
```

DB 통합 테스트는 `EXTERNAL_TEST_DATABASE_URL`이 없으면 skip한다. 실제 실행하려면 BE SQL 01/04가 적용된 별도의 **로컬 일회용** PostgreSQL DB를 준비한다. 테스트는 host가 127.0.0.1/localhost이며 DB 이름이 `extcrawler_test`로 시작하는 경우만 허용한다. 회사/공고 fixture를 추가하므로 공유·운영 DB를 사용하지 않는다. 테스트 자체는 DDL을 실행하지 않는다.

```powershell
$env:EXTERNAL_TEST_DATABASE_URL = 'postgresql://postgres@127.0.0.1:PORT/extcrawler_test'
.\.venv\Scripts\python.exe -B -m unittest discover -s tests -v
```

검증 범위: 공개 fixture 파싱, 단순 사용과 구현·테스트·배포 구분, 9개 수행 신호의 명시적 관찰, 부정·계획·학습 제외, 개인정보·원문 없는 JSON, 기존 TEXT 저장 왕복, 회사 엄격 일치, 관계 우선순위, robots/403/429/리다이렉트 중단, 요청 간격/타임아웃/한도, 회사별 큐 유일성, 두 연결의 SKIP LOCKED, 상태 전이, 자료 upsert, 타사 출처 ID 충돌 rollback, 새 공고 재사용, stale worker 차단, dry-run 무변경과 DB read-only 강제.

운영 DB에는 SQL을 적용하거나 실수집을 실행하지 않았다. 실제 대상 DB 검증은 DATABASE_URL을 설정한 뒤 dry-run으로 수행한다.
