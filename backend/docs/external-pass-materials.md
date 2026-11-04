# 외부 합격자료 저장·조회 계약

BE는 외부 자료를 조회하며, 별도 data-pipeline이 DB에 자료·공고 연결·수집 상태를 저장한다. BE에는 크롤러, 외부 플랫폼 HTTP 호출, 수집 시작/수정 API를 추가하지 않았다. 기존 공고 수집·추출 테이블과 내부 합격자 비교 API는 변경하지 않는다.

## 기존 구조와 충돌 지점

- 기존 공고의 회사 기준은 `job.posting.company_id → job.company.id`다. 회사 이름 문자열이나 직무 이름만으로 연결하지 않는다.
- `profile.successful_application`은 서비스 사용자와 역량 평가를 연결하는 내부 합격 이력이다. 외부 자료는 사용자 평가나 인증 완료 자료로 간주하지 않고 별도 `external_data` 스키마에 저장한다.
- 기존 `/capability-comparison`의 시장 비교군 fallback은 새 API에서 호출하지 않는다. 다른 회사의 같은 직무 자료는 반환하지 않는다.
- 추출 브랜치의 `public` 스키마와 BE의 `job` 스키마가 다를 수 있다. pipeline은 이 문서의 BE DB와 회사 ID를 사용해야 한다. 서로 다른 DB의 숫자 ID를 그대로 복사하면 안 된다.
- 신규 SQL은 기존 공고 테이블에 컬럼·색인·트리거를 추가하지 않는다. 공고 회사가 나중에 정정되면 기존 연결을 파이프라인이 다시 구성해야 한다. 조회 시 현재 회사 ID를 재검사하므로 과거 연결의 타사 자료는 노출되지 않는다.

## 테이블

| 테이블 | 역할·주요 컬럼 |
| --- | --- |
| `external_data.pass_material` | 회사 ID, source_platform, external_record_id, job_family, role_name, title, content, source_url, published_at, collected_at, updated_at |
| `external_data.company_collection` | company_id PK로 회사별 작업 1개: status, minimum_sample_size(기본 5), attempt_count, requested_at, started_at, completed_at, updated_at, error_code, error_message |
| `external_data.posting_pass_material` | posting_id, material_id, relation_type, linked_at; 공고와 자료의 다대다 연결 |

`pass_material`은 IT·SW 자료만 수용하며 `job_family='IT_SW'` CHECK가 있다. 직무의 세부 표기는 `role_name`에 저장한다. 이는 표준 capability 또는 LV가 아니며 이 API에서는 역량 집계를 수행하지 않는다. content는 표시 가능한 텍스트로 저장하고 프론트에서는 텍스트로 렌더링한다.

출처 ID 중복은 `UNIQUE(source_platform, external_record_id)`로 차단한다. 플랫폼 키는 공백 없는 소문자 키(예: `example_platform`)를 합의해 사용한다. 외부 ID는 플랫폼 내 안정적인 원본 식별자이며 양끝 공백을 허용하지 않는다. 회사나 공고 ID를 중복 키에 넣지 않는다. 동일 플랫폼의 기존 레코드 회사는 변경할 수 없으므로 잘못된 회사 매핑은 별도로 검토해야 한다.

연결은 `UNIQUE(posting_id, material_id)`이며, PostgreSQL 트리거가 공고 회사와 외부 자료 회사를 검사한다. 자료의 company_id 변경도 트리거가 차단한다. 연결의 posting_id는 기존 job.posting을 직접 참조한다. 공고 삭제 시 해당 연결만 삭제되며 회사 수집 작업과 공용 외부 자료는 보존된다. 연결된 자료의 삭제는 RESTRICT다.

`relation_type`은 외부 자료 자체가 아니라 **공고-자료 연결에만** 저장한다. 허용값은 EXACT_ROLE(동일 직무), SAME_JOB_FAMILY(동일 직무군), SAME_IT_DOMAIN(동일 IT 영역), EXCLUDED(비교 제외)다. 같은 자료를 공고 A에는 EXACT_ROLE, 공고 B에는 SAME_IT_DOMAIN 또는 EXCLUDED로 연결할 수 있다. NOT NULL과 CHECK로 값을 강제하므로 pipeline이 각 연결에 명시해야 한다. EXCLUDED는 DB에 남지만 일반 조회 목록과 전체 건수에서는 제외한다. SAME_IT_DOMAIN도 동일 회사 제약을 충족해야 한다.

## 수집 상태와 소유권

data-pipeline이 작업 생성과 모든 상태 변경을 담당한다. BE의 조회는 DB에 쓰지 않는다.

| 상태 | 의미 |
| --- | --- |
| PENDING | 작업 등록, 워커 대기 |
| RUNNING | 워커가 작업을 가져가 수집·저장 중 |
| READY | 회사 전체의 수집된 IT_SW 자료 수가 minimum_sample_size 이상 |
| INSUFFICIENT | 정상 수집 완료, 회사 전체 자료가 최소 개수 미만(0개 포함) |
| FAILED | 소스 접근·파싱 등으로 수집 실패 |

작업 행이 없으면 회사의 수집 미요청 상태이며 API의 `collection=null`로 표시한다. 조회가 임의로 PENDING 작업을 만들지 않는다. 같은 회사의 공고들은 하나의 작업 상태·시각·attempt_count를 공유한다. 이미 READY 등으로 저장된 회사에 새 공고가 생겨도 작업을 재등록하거나 상태를 초기화하지 않고 수집된 자료를 연결만 한다. 재시도가 필요한 경우에만 pipeline이 명시적으로 terminal 상태 → PENDING → RUNNING 순서로 기존 회사 작업을 재사용한다. 이전 시도의 상세 이력은 별도 보관하지 않는다.

회사 수집 READY와 특정 공고의 연결 자료 충분 여부는 다르다. 회사 자료가 충분해도 특정 공고의 유효 연결은 0개일 수 있다. 공고별 건수는 materials.totalElements로 확인하며, 이를 이유로 회사 전체를 다시 수집하지 않는다.

RUNNING에는 started_at이 필요하고 completed_at은 비워야 한다. READY/INSUFFICIENT/FAILED에는 completed_at이 필요하다. FAILED에는 error_code가 필요하다. SQL CHECK가 상태값과 이 필드들을 검증한다. **전체 상태 전이 순서와 READY/INSUFFICIENT의 개수 판정은 pipeline 책임**이며 DB가 자동으로 상태를 바꾸지 않는다.

워커는 작업 행 잠금으로 중복 실행을 막는다. 요청 등록 예시:

```sql
INSERT INTO external_data.company_collection(company_id)
SELECT company_id FROM job.posting WHERE id=:posting_id
ON CONFLICT (company_id) DO NOTHING;
```

워커 작업 획득 예시(짧은 트랜잭션으로 실행하고 commit 후 수집):

```sql
WITH next_job AS (
    SELECT company_id FROM external_data.company_collection
    WHERE status='PENDING'
    ORDER BY requested_at, company_id
    FOR UPDATE SKIP LOCKED LIMIT 1
)
UPDATE external_data.company_collection c
SET status='RUNNING', started_at=now(), completed_at=NULL,
    attempt_count=attempt_count+1, updated_at=now(), error_code=NULL, error_message=NULL
FROM next_job WHERE c.company_id=next_job.company_id
RETURNING c.*;
```

동일 출처 자료 재수집은 upsert하고 ID를 보존한다. `:변수`는 pipeline DB 드라이버의 바인딩 자리표시자 예시다.

```sql
INSERT INTO external_data.pass_material AS current_material
    (company_id,source_platform,external_record_id,role_name,title,content,source_url,published_at)
VALUES (:company_id,:source_platform,:external_record_id,:role_name,:title,:content,:source_url,:published_at)
ON CONFLICT(source_platform,external_record_id) DO UPDATE
SET role_name=excluded.role_name, title=excluded.title, content=excluded.content,
    source_url=excluded.source_url, published_at=excluded.published_at, updated_at=now()
WHERE current_material.company_id=excluded.company_id
RETURNING id;
```

RETURNING이 0행이면 같은 외부 ID에 대한 회사 매핑 충돌로 처리하고, 다른 회사의 기존 자료 ID를 연결하지 않는다.

저장·연결·완료 처리는 다음 순서로 같은 트랜잭션에서 수행한다.

1. 대상 company_collection 행을 `FOR UPDATE`로 잠그고 status가 RUNNING인지 확인한다.
2. 회사의 IT·SW 자료를 한 번 수집한 결과로 저장한다. 새 공고가 생겼다는 이유로 같은 회사를 다시 수집하지 않는다.
3. `posting_pass_material(posting_id,material_id,relation_type)`로 공고별 관계를 연결한다. 중복이면 `ON CONFLICT(posting_id,material_id) DO UPDATE SET relation_type=excluded.relation_type`로 해당 공고의 관계만 갱신한다. 이미 수집된 회사 자료에서 새 공고의 연결만 구성하는 작업은 크롤링 없이 별도로 수행할 수 있다.
4. `pass_material`에서 해당 company_id의 IT_SW 자료 수를 세고 minimum_sample_size 이상이면 READY, 그 외에는 INSUFFICIENT로 갱신한다. completed_at·updated_at을 갱신하고 commit한다. 여러 공고에 연결된 같은 자료는 이 계산에서 한 번만 센다.

실패 시 저장 트랜잭션을 rollback하고 별도 트랜잭션에서 FAILED·error_code·completed_at·updated_at을 저장한다. error_message에는 운영용 상세 내용을 저장할 수 있지만 API에는 공개하지 않는다. RUNNING 상태에서 멈춘 워커의 타임아웃 판정·재투입도 pipeline에서 구현한다.

재시도 중이거나 실패한 경우 이전 성공분의 연결이 남을 수 있다. API는 연결된 자료와 현재 수집 상태를 그대로 반환하므로 프론트는 상태를 표시하고 자료 건수만으로 READY라고 판단하지 않는다. GET의 materials.totalElements는 전체 페이지에 걸친 동일 회사 IT_SW 자료 건수이며, 중복 인물을 식별한 사람 수는 아니다.

## 조회 API

`GET /api/postings/{postingId}/external-pass-materials?page=0&size=20`

page는 0 이상, size는 1~100, postingId는 양수다. 존재하지 않는 공고는 404, 잘못된 파라미터는 400이다. 공고의 회사 ID로 공유 수집 상태를 조회한다. 자료는 EXCLUDED를 제외한 명시적 연결만 수집 시각 내림차순·ID 내림차순으로 반환한다. 같은 회사라도 연결되지 않은 자료는 자동으로 추가하지 않는다.

```json
{
  "postingId": 1,
  "companyId": 10,
  "collection": {
    "companyId": 10,
    "status": "INSUFFICIENT",
    "minimumSampleSize": 5,
    "attemptCount": 1,
    "requestedAt": "2026-11-05T09:00:00+09:00",
    "startedAt": "2026-11-05T09:01:00+09:00",
    "completedAt": "2026-11-05T09:02:00+09:00",
    "updatedAt": "2026-11-05T09:02:00+09:00",
    "errorCode": null
  },
  "materials": {
    "content": [{
      "materialId": 100,
      "companyId": 10,
      "sourcePlatform": "example_platform",
      "externalRecordId": "record-123",
      "jobFamily": "IT_SW",
      "roleName": "백엔드 개발자",
      "title": "개발 직군 합격 후기",
      "content": "프로젝트 경험과 준비 과정에 대한 외부 자료",
      "sourceUrl": "https://example.com/records/123",
      "publishedAt": null,
      "collectedAt": "2026-11-05T09:01:30+09:00",
      "updatedAt": "2026-11-05T09:01:30+09:00",
      "relationType": "EXACT_ROLE"
    }],
    "page": 0, "size": 20, "totalElements": 1, "totalPages": 1
  }
}
```

## 적용과 테스트

`db/init/04-external-pass-material.sql`을 기존 BE DB에 한 번 적용한다. 아직 운영에 적용하지 않은 로컬 초안을 수정한 것이므로 별도 후속 마이그레이션은 추가하지 않았다. 이전 공고 단위 초안을 다른 환경에 적용했다면 이 파일을 재실행하지 말고 회사별 상태 병합과 기존 연결의 관계 분류를 위한 별도 데이터 마이그레이션이 필요하다. 새 Docker DB에는 init 마운트로 자동 적용되지만 기존 볼륨에는 다시 실행되지 않는다. 기존 데이터를 삭제할 필요는 없다. 이번 작업에서는 운영 DB에 적용하지 않았다.

```powershell
Get-Content -Raw -Encoding utf8 db/init/04-external-pass-material.sql | docker compose exec -T db psql -U postgres -d career -v ON_ERROR_STOP=1
cd backend
.\gradlew.bat test
```

DB 사용자가 postgres가 아니면 명령의 사용자를 바꾼다. pipeline용 DB 사용자에게는 job.company/job.posting의 SELECT, external_data 스키마의 USAGE, 새 테이블의 SELECT/INSERT/UPDATE/DELETE와 identity sequence의 USAGE를 필요한 범위에서 부여한다. 회사 검사 트리거는 고정 search_path와 완전히 한정된 테이블명을 사용하는 SECURITY DEFINER 함수로 실행하므로 pipeline에 기존 공고의 UPDATE 권한을 줄 필요가 없다. 함수 소유자는 마이그레이션 관리 계정으로 유지한다. BE에는 SELECT만 부여하면 된다.

H2 API 테스트는 페이지 처리, 5개 상태, 미요청, 404/400, 중복, 다른 회사·비IT_SW 자료의 방어적 제외, 기존 추출 불변을 확인한다. PostgreSQL 고유 트리거와 CHECK는 `db/tests/04-external-pass-material.sql`로 따로 검증한다. 테스트 SQL은 init/01과 init/04를 적용한 격리 DB에서 실행하며 테스트 데이터는 rollback한다.

## 추가 파일

- `db/init/04-external-pass-material.sql`: 저장 구조, 제약, 회사 일치 트리거
- `db/tests/04-external-pass-material.sql`: PostgreSQL 제약 검증
- `domain/external/CollectionStatus.java`, `MaterialRelationType.java`: 수집 상태·공고별 관계 enum
- `domain/external/ExternalPassMaterial.java`, `CompanyCollection.java`, `PostingPassMaterial.java`: 읽기 전용 JPA 모델
- `domain/external/ExternalPassMaterialRepository.java`, `CompanyCollectionRepository.java`: 공고별 연결 자료와 회사별 수집 상태 조회
- `domain/external/ExternalPassMaterialService.java`, `ExternalPassMaterialResponse.java`: 공고 존재 확인과 응답 구성
- `api/posting/ExternalPassMaterialController.java`: 페이지 처리를 지원하는 GET API
- `api/posting/ExternalPassMaterialControllerTest.java` (test): API 통합 테스트
- 루트 README: 기능 안내

프론트 연결과 크롤링은 이번 범위에 포함하지 않는다. 외부 자료를 내부 사용자 평가·capability LV로 자동 변환하지 않는다.
