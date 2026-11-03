# Capstone1 Career

프로젝트에서 확인한 사용자 역량과 채용공고의 요구 역량을 비교하는 서비스입니다. 이 README는 `feature/BE`의 백엔드 개발 현황과 협업 기준을 정리합니다.

## 브랜치 및 PR 규칙

합의한 반영 순서는 **feat → develop → main**입니다.

1. 기능 브랜치에서 작업하고 커밋·push합니다. 현재 백엔드 기능 브랜치는 `feature/BE`입니다.
2. 기능 검토를 위한 PR은 `feature/BE` → `develop` 방향으로 생성합니다.
3. 통합 검증 후 `develop` → `main` PR로 반영합니다.

`feature/BE`에서 `main`으로 바로 병합하지 않습니다. 기능 브랜치 push는 배포 완료나 DB 마이그레이션 적용을 의미하지 않습니다.

PR에는 변경 목적, API·DB 변경, 테스트 결과, 미완료 연동 사항을 적어 주세요. DB 변경이 있으면 기존 DB에 적용하는 방법도 함께 남겨 주세요.

## 저장소 구조와 기술 스택

| 경로 | 역할 |
| --- | --- |
| `backend/` | Java 21, Spring Boot 4.1.1, Spring Data JPA, Gradle 기반 API |
| `frontend/` | Node.js 24 이상, Next.js 16, React 19, TypeScript 기반 웹서비스 |
| `db/init/` | PostgreSQL 초기화 및 추가 테이블 SQL |
| `compose.yaml` | PostgreSQL 17과 백엔드 실행 설정 |
| `backend/docs/capability-comparison.md` | 역량 비교 API 상세, 응답 예시, 데이터 흐름과 한계 |

추출 파이프라인은 별도 `feature/job-skill` 브랜치에서 관리됩니다. 현재 BE는 `job` 스키마를 읽지만 확인한 추출 브랜치 로더는 `public` 스키마를 사용하므로, 실제 연동 전에 배포 DB의 스키마를 확인해야 합니다.

## 개발 시 지켜야 할 데이터 기준

- 기존 채용공고 추출 로직과 `positions`, `required`, `preferred`, `duties`, `other`, `skipped` 출력 계약을 보존합니다.
- 서비스용 변환은 별도 Adapter에서 처리하고 원본 추출 결과를 수정하거나 덮어쓰지 않습니다.
- `requiredSkills`는 필수 비교, `preferredSkills`는 우대 비교에 사용합니다.
- `dutySkills`와 `environmentSkills`는 참고 정보로 표시하며 필수 역량으로 자동 승격하지 않습니다.
- 경력·학력·전공·자격증·어학·병역·근무 조건은 `requiredConditions`로 분리하고 기술 LV 계산에서 제외합니다. 기술과 조건이 함께 있는 문장에서는 기술 정보를 유지합니다.
- 조건 판별 패턴은 `RequiredConditionRules`에서 관리합니다.
- 합격자 비교는 현재 공고의 요구사항과 별도의 참고 자료입니다. PDF 원문이나 키워드를 다시 세지 않고 저장된 capability ID와 사용자 평가로 집계합니다.
- 비교군은 동일 회사 유사 직무 → 전체 시장 동일 직무 → `NONE` 순서로 선택합니다. 기본 최소 표본은 5명입니다.
- 합격 가능성이나 합격 확률은 계산하지 않습니다. 비교 데이터가 부족하면 부족 상태를 반환합니다.
- 로컬 사용자 DB, 업로드 자료, 환경 변수 파일, 빌드 산출물은 커밋 대상에서 제외합니다.

## 백엔드 구현 현황

2026-11-04 기준, 역량 비교 기능 커밋은 `cebf9d0`입니다.

| 항목 | 현재 상태 |
| --- | --- |
| 공고 목록·상세 조회 | 구현됨 |
| 기존 `/fit` API | 필수·우대 capability에 사용자 점수·LV 연결 |
| 사용자·프로젝트·역량 평가 API | 등록·조회·평가 점수 저장 구현됨 |
| 추출 결과 Adapter | 조건 분리, 카테고리 유지, 빈 배열 처리, 동일 항목 중복 제거 구현됨 |
| 신규 역량 비교 API | 모집 단위별 요구사항·사용자 평가·합격자 참고 비교 제공 |
| 비교군 조회·집계 | 인증·합격 단계·기간·직무·경력 필터, 사용자 중복 제거, 보유율·LV 중앙값 구현됨 |
| 비교 기준·합격 이력 테이블 | SQL 및 모델 추가됨. 운영 DB 적용은 별도 필요 |
| 합격 인증 절차·등록 API | 미구현 |
| 프론트의 신규 비교 API 연동 | 미완료. 현재 합격자 비교 화면은 예시 통계 사용 |
| 검증 | H2 PostgreSQL 모드에서 백엔드 전체 테스트 28개 통과. 운영 PostgreSQL 검증은 별도 필요 |

## 주요 API

| 메서드·경로 | 용도 |
| --- | --- |
| `GET /api/postings` | 공고 목록·검색 |
| `GET /api/postings/{postingId}` | 공고 상세·추출 결과 |
| `GET /api/postings/{postingId}/fit?userId={userId}` | 기존 필수·우대 역량 대비 사용자 LV |
| `GET /api/postings/{postingId}/capability-comparison?userId={userId}` | 신규 공고 역량·지원 조건·사용자 Evidence·합격자 참고 비교 |
| `GET /api/capabilities` | 표준 capability 조회 |
| `POST /api/users` | 사용자 생성 |
| `POST /api/users/{userId}/projects` | 프로젝트 등록 |
| `GET /api/users/{userId}/projects` | 사용자 프로젝트 목록 |
| `GET /api/users/{userId}/capabilities` | 사용자 capability별 최고 점수·LV·프로젝트 근거 |
| `PUT /api/projects/{projectId}/evaluations` | 프로젝트 capability 평가 저장 |

신규 비교 응답은 `positions[].posting`에 필수·조건·우대·업무·환경 정보를, `positions[].reference`에 비교군 유형·표본 수·역량 통계를 담습니다. 사용자 평가와 프로젝트 근거는 `userCapabilities`에 있습니다. 전체 JSON 예시는 [상세 문서](backend/docs/capability-comparison.md)를 참고하세요.

## 실행

저장소 루트의 `.env`에 DB 설정을 준비합니다. 비밀번호는 실제 로컬 값을 사용하고 커밋하지 않습니다.

```dotenv
POSTGRES_USER=postgres
POSTGRES_PASSWORD=<로컬 DB 비밀번호>
```

```powershell
docker compose up -d --build
```

백엔드는 `http://localhost:8080`, DB의 호스트 포트는 `5433`입니다. DB 컨테이너 내부 포트는 `5432`입니다.

프론트는 `frontend/.env.local`에 `BACKEND_URL=http://localhost:8080`을 설정한 뒤 실행합니다.

```powershell
cd frontend
npm install
npm run dev
```

프론트 서버가 Spring 공고 목록·상세를 조회합니다. 사용자 로그인·프로젝트·역량 평가 데이터는 아직 별도 SQLite 경로를 사용하며 BE와 통합되지 않았습니다. 상세 내용은 [프론트 README](frontend/README.md)를 참고하세요.

## DB 적용과 저장 구조

초기 SQL 적용 순서는 다음과 같습니다.

1. `db/init/01-job-schema.sql`: 공고·추출 결과·capability·tech
2. `db/init/02-user-skill-schema.sql`: 사용자·프로젝트·capability 평가
3. `db/init/03-capability-comparison.sql`: 비교 기준·합격 이력

Docker의 초기화 SQL은 **새 DB 볼륨을 생성할 때만 자동 실행**됩니다. 기존 DB에는 `03-capability-comparison.sql`을 별도 적용해야 합니다. 기존 데이터를 보존하기 위해 초기화 목적으로 볼륨을 삭제하지 마세요. 적용 명령은 [상세 문서](backend/docs/capability-comparison.md)에 있습니다.

기존 데이터 흐름은 다음과 같습니다.

```text
추출 결과 → extraction_run → recruit_unit → unit_item → requirement → requirement_tech
사용자 → project → user_skill_evaluation → capability
모집 단위 비교 기준 + 인증 합격 이력 + 사용자 평가 → 참고 비교군 집계
```

사용자 LV는 별도 컬럼으로 저장하지 않습니다. `confirmed_score`를 기존 기준에 따라 LV0~LV3로 변환하며, 동일 capability가 여러 프로젝트에서 평가되면 최고 점수를 대표값으로 사용합니다.

## 테스트

Java 21을 준비한 뒤 실행합니다.

```powershell
cd backend
.\gradlew.bat test
```

macOS/Linux에서는 `./gradlew test`를 사용합니다. 결과 보고서는 `backend/build/reports/tests/test/index.html`에 생성됩니다.

추가한 테스트는 조건·기술 혼합 문장 보존, 원본 불변, 필드별 분리, 빈 배열, 중복 제거, 비교군 우선순위·제외 조건·표본 부족·집계, API 응답을 확인합니다.

## 다음 작업과 확인 사항

- 실제 DB의 `job`/`public` 스키마 관계와 신규 SQL 적용 상태 확인
- 표준 직무군·경력 구간 확정 및 모집 단위별 비교 기준 등록
- 검증된 합격 이력 공급과 인증 증빙·검토 상태·검토자·검토 시각 관리 설계
- 프론트 문자열 사용자 ID와 BE 숫자 사용자 ID 연결 및 접근 제어 정리
- 프론트 예시 통계를 실제 비교 API 응답으로 교체
- 프론트의 기술 점수 표시와 BE의 LV0~LV3 의미를 구분해 화면 설계
- 운영 PostgreSQL에서 마이그레이션과 조회 동작 검증

현재 비교 기준이 없으면 `COMPARISON_TARGET_MISSING`, 표본이 부족하면 `INSUFFICIENT_SAMPLE`로 구분합니다. 원본 JSON이 없는 과거 추출의 `skipped`는 복구할 수 없어 `skippedAvailable=false`와 빈 배열을 반환합니다. 역량별 PDF 인용 근거는 현재 평가 DB에 저장되어 있지 않습니다.
