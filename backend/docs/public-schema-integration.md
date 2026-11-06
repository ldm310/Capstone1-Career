# public 스키마 통합

공고·회사·추출 결과·사전의 공식 스키마는 `public`이다. Backend의 `domain.job`은 Java 패키지 이름이며 DB 스키마가 아니다. JPA의 10개 공고 관련 엔티티는 `public`을 명시하고 Repository의 JPQL도 이 매핑을 따른다. 외부 키워드는 `public.tech`, `public.requirement_tech` 및 현재 추출 실행을 읽는다.

`profile`은 사용자·프로젝트·평가, `external_data`는 외부 합격자료·수집 상태·공고 연결만 소유한다. capability/tech/company/posting/recruit_unit 참조는 public의 기존 ID를 사용한다. job-skill과 Airflow는 수정하거나 연결하지 않는다.

2026-11-06 실제 확인: RDS에는 job 테이블이 없고 public 공고 1,945건이 있다. 로컬 career-db에는 데이터가 없는 옛 job 테이블 12개가 있었으며, 백업·복제 검증 후 `06`으로 public에 이동했다. 로컬의 job 참조 FK는 0개다. 8080 Backend는 RDS public 조회를 유지한다. RDS에는 아직 profile/external_data 테이블이 없으므로 로컬 확장 테이블을 전환한 것과 RDS의 외부 합격자료 기능 활성화는 별개다.

## 컬럼 계약

이번 변경에서는 팀 DB에 SQL을 실행하지 않는다. 비교 기준은 기존 조사 결과와 저장소의 현재 `job-skill/db/schema.sql`이다. 실제 운영 컬럼 전체를 다시 조회한 결과는 아니므로 운영 적용 전 별도 확인이 필요하다.

- 기존 JPA 매핑 필드는 최신 public DDL에 모두 존재한다. JSONB `extraction_run.llm_output_raw`, TEXT[] `tech.aliases`, SMALLINT 연수·순서, TIMESTAMPTZ 수집·실행 시각을 유지한다.
- `posting.body_html`, `posting.recheck_due` 등 Backend에서 사용하지 않는 컬럼은 부분 매핑으로 유지한다. 삭제된 `posting.raw_path`, `posting_image.file_path/ocr_path`를 JPA에 추가하지 않는다.
- 신규 설치용 `01-job-schema.sql`은 최신 파이프라인 DDL을 반영했다. `dictionary_version.first_used_at`, `tech_capability.is_primary`, `exclude_word`, `dictionary_change`와 사전 보호 트리거도 포함한다. 파이프라인 원본 파일은 수정하지 않는다.
- PostgreSQL 회귀 테스트는 이 DDL로 만든 public을 Hibernate `validate`로 검증한다. H2의 엔티티 자동 생성만으로 PostgreSQL 호환성을 판정하지 않는다.

## 설치 SQL과 기존 데이터

`db/init/01-job-schema.sql`은 **빈 신규 DB 전용**이다. 기존 public 테이블이 있는 DB에서는 실행하지 않는다. init 디렉터리는 새 빈 Docker 볼륨에서만 자동 실행된다. 초기화를 위해 기존 볼륨을 삭제하지 않는다.

기존 public 데이터가 있고 확장 테이블이 없는 환경은 별도 승인된 적용 단계에서 `02-user-skill-schema.sql`, `03-capability-comparison.sql`, `04-external-pass-material.sql`만 검토한다. 02/03/04는 public 공고·사전 테이블을 생성·변경·복사하지 않는다. 04는 최초 확장 설치용이며 반복 실행용이 아니다. 이 작업에서는 팀 DB에 적용하지 않는다.

## 과거 로컬 DB의 FK 전환

`db/migrations/05-public-schema-integration.sql`은 수동 실행하는 과거 **로컬** DB 전용이다. 애플리케이션 시작 시 자동 실행하지 않는다.

- source 테이블이 없으면 건너뛴다. source가 있는데 필요한 public 대상·컬럼이 없으면 전체 롤백한다. job만 있는 DB를 자동으로 public으로 복제하거나 이동하지 않는다.
- 알려진 external_data/profile FK와 두 확장 스키마에서 job을 참조하는 추가 capability/tech 등의 단일 컬럼 FK를 처리한다. 알려진 FK가 빠져 있으면 public FK를 추가한다. 지원하지 않는 복합·예상 밖 참조는 중단한다.
- 사용 중인 ID가 public에 없으면 중단한다. job FK 전환 시 참조되는 job/public 행의 모든 공통 컬럼도 비교한다. 같은 숫자 ID라도 값이 다르면 중단한다. 시각·별칭 등의 차이도 충돌로 간주하는 보수적 검사다. job/public 상위 계보가 동일한지는 별도 검토가 필요하다.
- 기존 FK의 ON DELETE/UPDATE, MATCH, 지연 검사 설정을 유지하며 모든 FK를 검증한다. 이미 public인 FK는 검증만 한다. 재실행할 수 있다.
- 회사 일치 검사 함수의 조회 대상도 `public.posting`으로 바꾼다. FK만 바꾸고 이 함수에 job 조회를 남겨두지 않는다. 기존 함수의 소유자·권한과 트리거 연결을 유지한다.
- public/job/profile/external_data 행·ID·시퀀스를 수정하지 않고, 테이블을 삭제·이동·복사하지 않는다. job 테이블은 남겨둔다. 충돌 해결·데이터 정리는 이 migration 범위가 아니다.
- 단일 트랜잭션이며 확장 테이블은 배타 잠금, 참조 테이블은 쓰기 차단 잠금을 사용한다. lock timeout 5초, statement timeout 60초로 실패 시 롤백한다. 로컬에서도 서비스 쓰기를 멈춘 상태로 검토해야 한다.

외부 크롤러 기본 `--posting-schema`는 public이다. 기존 `job` 옵션은 과거 격리 로컬 DB 진단 호환성만 유지하며, 선택한 스키마와 실제 FK가 다르면 수집 전 실패한다.

## 회귀 테스트

### public이 비어 있는 옛 로컬 DB 전환 (2026-11-06)

`05`는 이미 양쪽에 동일한 ID가 있는 경우의 FK 전환 전용이다. 옛 로컬 DB에 `job` 테이블만 있고 public 대상이 없는 경우에는 `06-local-job-tables-to-public.sql`로 원본 테이블을 public으로 이동한다. 테이블을 새로 만들거나 행을 복사하지 않으므로 ID·데이터·시퀀스와 기존 FK 연결을 보존한다. `external_data.check_material_company()`의 공고 조회도 public으로 변경한다. 대상 이름 충돌·예상 밖 객체·남은 job 참조가 있으면 트랜잭션을 롤백한다. 빈 job 네임스페이스는 남겨 두며 코드의 `domain/job` 폴더는 Java 패키지이므로 변경하지 않는다.

로컬 쓰기 작업을 중지한 상태에서 저장소 루트에서 실행한다. RDS 접속 설정을 사용하지 않고 `career-db` PostgreSQL 컨테이너의 로컬 소켓만 사용한다.

```powershell
# 전체 백업 + 임시 복제 DB 검증만
python deploy/backend/migrate_local_public.py
# 같은 검증 후 실제 로컬 DB도 전환
python deploy/backend/migrate_local_public.py --apply
```

백업과 전후 행 해시·시퀀스 상태, 검증 결과는 `work/local-public-migration-*/`에 저장된다. 임시 복제 DB에만 합성 공고·합격자료를 넣어 데이터 보존, 회사 일치 트리거, 반복 실행, 이름 충돌 시 중단을 검증한다. 로컬 데이터를 RDS에 업로드하는 스크립트는 아니다. RDS는 기존 public을 그대로 사용한다.

### 기존 스키마 회귀 검증

1. Backend 전체: Java 21에서 `backend/gradlew.bat test`. 기본 H2 테스트에서는 job 스키마를 만들지 않는다.
2. 외부 크롤러 전체: 해당 폴더에서 `python -m unittest discover -s tests -v`. DB 테스트까지 실행하려면 `EXTERNAL_TEST_DATABASE_URL`에 **localhost/127.0.0.1의 extcrawler_test 접두사 격리 DB**를 지정하고 01/04를 적용한다. 합성 fixture만 사용하며 실제 수집은 하지 않는다.
3. SQL 보존 테스트: psycopg 설치 후 `PUBLIC_SCHEMA_TEST_DSN`에 같은 로컬 제한을 만족하는 테스트 DSN을 지정하고 `python db/tests/test_public_schema_integration.py -v`. 테스트별 일회용 DB를 생성·삭제하므로 해당 테스트 계정에 CREATEDB가 필요하다. 운영 env 파일은 읽지 않는다.
4. 실제 PostgreSQL Backend: 빈 격리 DB에서 위 Python 스크립트의 `--prepare-backend`로 fixture를 준비하고 `PUBLIC_SCHEMA_TEST_URL=jdbc:postgresql://127.0.0.1:<테스트포트>/extcrawler_test...`, `PUBLIC_SCHEMA_TEST_USER`, `PUBLIC_SCHEMA_TEST_PASSWORD`를 지정해 `PublicSchemaPostgresTest`를 실행한다. URL은 loopback·테스트 DB 이름만 허용한다. ddl-auto는 validate, 초기화는 never, 조회는 readOnly다.

SQL 테스트는 신규 설치, 확장 테이블 없는 상태, 전환 재실행, ID 충돌, public 대상 ID 누락, 모든 테이블 행 수·JSONB 기반 전체 행 해시·시퀀스 보존을 검사한다. Java PostgreSQL 테스트는 job 부재, public 공고 조회, 외부 자료 조회, Java 기술 교집합과 조회 전후 public 행 수·전체 행 해시 보존을 검사한다.
