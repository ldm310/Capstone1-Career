# develop의 RDS 공고 연결

develop CD는 웹(3001)과 별도 Spring 서비스 `career-backend-staging`을 연결한다. 백엔드는 EC2 내부 `127.0.0.1:18081`에만 열며, 운영 웹(3000)·main·RDS 스키마를 변경하지 않는다.

## 설정

스테이징 계정을 별도로 사용할 때는 Actions Secrets `STAGING_RDS_HOST`, `STAGING_RDS_PASSWORD`와 Actions Variables `STAGING_RDS_USERNAME`, `STAGING_RDS_DATABASE`, `STAGING_RDS_PORT`를 등록한다. 이 항목들은 스테이징 백엔드 잡에서만 우선 사용한다. 기존 공통 `RDS_PASSWORD`는 다른 계정의 암호로 덮어쓰지 않는다.

기존 저장소 Actions Secrets의 `RDS_HOST`, `RDS_PASSWORD`를 배포 단계에서만 사용한다. 비밀번호를 저장소·명령행·로그·빌드 산출물로 내보내지 않는다. DB·계정 기본값 `career`는 기존 `job-skill/db_load.py`의 RDS 설정과 같다. 별도 계정은 Actions Variables `RDS_DATABASE`, `RDS_USERNAME`, `RDS_PORT`로 선택한다.

런타임 설정은 EC2 `~/career-data-staging/backend.env`에 소유자만 읽는 파일로 저장한다. Secret을 주지 않는 환경에서는 관리자가 사전에 준비한 동일 경로의 설정 파일을 사용할 수 있다. 둘 다 없거나 일부만 주어지면 기존 설정을 변경하지 않고 실패한다. 설정 값이나 개인키를 채팅에 보내지 않는다.

웹은 같은 폴더 `.env`의 `BACKEND_URL=http://127.0.0.1:18081`로 연결한다. 이 주소는 배포 스크립트가 실제 백엔드를 해당 포트에 기동하고 RDS 조회를 확인한 뒤 설정한다.

## 배포 순서

1. GitHub 호스팅 Ubuntu 22.04 x64에서 Java 21 JAR와 독립 Java 런타임을 묶는다. EC2의 기존 Java·Docker 설치를 변경하지 않는다.
2. 기존 `career-ec2` 러너가 배포물을 받아 develop 전용 서비스를 기동한다. main 실행은 스크립트 자체에서도 거부한다. 서비스 포트가 다른 용도로 사용 중이면 중단한다.
3. `docker,rds,staging-readonly` 프로필을 적용한다. Hibernate DDL·SQL 초기화를 끄고 JDBC 연결을 읽기 전용으로 둔다. 스테이징 전용 HTTP 필터는 POST/PUT/PATCH/DELETE를 컨트롤러 전에 405로 거부한다. 일반 프로필의 기존 API는 유지한다.
4. `/api/system/status`뿐 아니라 실제 `/api/postings`의 공고 존재와 카테고리 10개 응답을 확인한다. 실패하면 이전 스테이징 백엔드 판·서비스·기존 설정으로 되돌린다.
5. 웹의 연결 주소를 설정하고 웹을 배포·재시작한다. 같은 커밋으로 재실행해도 빌드는 재사용하고 환경설정을 다시 읽는다.
6. 웹의 `/api/skill-categories`와 `/api/jobs`에서 `be:` 공고가 실제 전달되는지 확인한다. 더미만 6개인 응답을 배포 성공으로 처리하지 않는다.

backend 코드·배포 스크립트 변경도 develop에서 이 경로를 실행한다. frontend만 변경하면 기존 백엔드를 유지하고 웹 연결 검사를 실행한다. RDS 마이그레이션·운영 Airflow 단계는 기존 main 조건을 유지한다.

## 검증

Hikari의 하이픈이 있는 속성은 서비스 `ExecStart`의 정규 명령행 옵션으로만 강제한다. `SPRING_DATASOURCE_HIKARI_CONNECTION_INIT_SQL`처럼 하이픈 위치를 밑줄로 나누면 `connection.init.sql` 중첩 경로로 해석되어 설정 바인딩 중 연결 풀이 먼저 시작되고 `pool is sealed once started` 오류가 발생한다. 잘못된 환경변수와 정규 옵션을 동시에 주어도 실패하므로 중복 환경변수를 제거했다. Spring의 변환 규칙은 [공식 외부 설정 안내](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties.relaxed-binding.environment-variables)를 따른다.

회귀 검사는 잘못된 이름으로 동일한 오류가 발생하고, 정규 옵션만 사용하면 첫 연결 전에 설정이 적용되는지 확인한다. 로컬 PostgreSQL 스냅샷에서는 잘못된 설정의 시작 실패와 수정 후 1,717개 공고 조회·쓰기 차단을 비교 검증했다.

```powershell
python -m unittest discover -s deploy/backend/tests -v
```

CI의 `deployment` 잡에서 설정 원자적 저장, 비밀번호 특수문자 처리, 설정 유실 방지, 실제 공고 없는 헬스 응답 거부, 더미만 있는 웹 응답 거부, main 배포 차단을 검사한다. Java 테스트에서 쓰기 요청이 필터 뒤로 전달되지 않는지 확인한다.

현재 환경의 직접 SSH는 시간 초과여서 EC2 설정 내용을 조회하지 않았다. 이 배포는 서버의 환경변수를 수집하는 진단 작업이 아니라, 명시된 RDS 설정을 전용 서비스에 적용하는 정상 CD 단계다. 실제 복구 완료는 develop 병합 후 CD와 공고 전달 검사 성공으로 판정한다.
# 회원·사용자 LV·공지 RDS 연결

develop 웹 배포는 기존 STAGING_RDS_HOST/PASSWORD와 STAGING_RDS_USERNAME/DATABASE 설정을 재사용한다.
`staging_config.py profile-env`가 스테이징 `.env`에 CAREER_PROFILE_DATABASE_URL/CA_FILE/NAMESPACE와 CAREER_ACCOUNT_STORE=rds, CAREER_DATA_DIR를 저장한다.
연결 문자열은 사용자명과 비밀번호를 URL 인코딩하며 로그에 출력하지 않는다. AWS 공식 CA로 TLS를 검증한다.
기존 BACKEND_URL, 카카오 설정과 다른 환경 값은 보존한다. namespace는 staging이며 production은 변경하지 않는다.

웹 배포 전 06/07/08 사용자용 테이블을 멱등 생성하고 공지 초기 자료를 준비한다.
local-review의 공개 더미 LV만 staging으로 복사하며 로컬 실제 회원/관리자 역할은 복사하지 않는다.
`--migrate-accounts`는 해당 스테이징 서버 SQLite의 기존 회원 ID와 비밀번호 해시, 카카오 연결만 staging namespace로 이전한다. 기존 RDS 회원은 덮어쓰지 않는다.
회원 및 카카오 연결은 RDS career_account/career_account_oauth를 사용하고, 세션과 분석 파일/workspace는 기존 서버 SQLite에 남는다.
GitHub Actions Secrets STAGING_KAKAO_REST_API_KEY와 STAGING_KAKAO_CLIENT_SECRET을 모두 등록하면 카카오 설정도 서버에 적용한다.
콜백은 Variables STAGING_KAKAO_REDIRECT_URI를 사용하며 기본값은 스테이징 주소의 /api/auth/kakao/callback이다. 키가 둘 다 없으면 서버의 기존 카카오 설정을 보존한다.
배포 후 `/api/notices`와 기존 Spring 공고 연결을 모두 확인한다.
