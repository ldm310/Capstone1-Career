# API 전체 현황 (2026-11-23)

프론트 API도 서버에서 실행되는 Next.js API다. 브라우저는 같은 출처의 Next API를 호출하고,
Next 서버가 Spring 공고 API 또는 사용자용 RDS/SQLite에 연결한다. 브라우저가 RDS에 직접 접속하지 않는다.

- 웹 스테이징: `https://staging.15-164-137-78.sslip.io`
- 로컬 웹: `http://127.0.0.1:3000`
- Spring 스테이징: EC2 내부 `http://127.0.0.1:18081`. 외부 공개 URL로 임의 연결하지 않는다.
- 로그인 쿠키: `career_session`. 변경 요청은 같은 출처의 Origin 검사를 통과해야 한다.
- 일반 회원은 실제 분석/개인 LV/공지 작성의 게스트 세션과 구분된다.

회원 RDS 연결: `CAREER_ACCOUNT_STORE=rds`일 때 기존 사용자용 RDS의
`career_account`(이름, 이메일, 비밀번호 해시, 선택 나이/학교/학과),
`career_account_oauth`(카카오 식별자 연결)를 사용한다. 세션과 분석 파일/작업 공간은 기존 SQLite에 보관한다.
가입·로그인·카카오 로그인·내 정보/비밀번호 변경은 같은 회원 저장소를 사용한다.
새 RDS 인스턴스를 추가하지 않는다. 로컬/스테이징 회원은 `namespace`로 구분한다.

기존 계정 이전은 `node scripts/setup-community.mjs --migrate-accounts`로 명시적으로 실행한다.
이 명령은 회원 ID와 비밀번호 해시를 유지하고, 이미 RDS에 있는 회원의 정보를 덮어쓰지 않는다.
이전 완료 후 해당 환경 `.env`에 `CAREER_ACCOUNT_STORE=rds`를 설정하고 서버를 재시작한다.

## 1. 프론트 서버 API (Next.js)

| 메서드 | 경로 | 역할 | 인증/상태 |
|---|---|---|---|
| GET | `/api/account` | 로그인 사용자, 게스트 여부, 프로필, 데모 여부 | 공개, 비로그인은 user=null |
| POST | `/api/account` | 회원가입, 로그인, 로그아웃, 프로필/비밀번호 변경 | action에 따라 다름 |
| POST | `/api/guest` | 별도 게스트 세션 생성 | 레거시, 실제 역량 추출 권한 없음 |
| GET | `/api/career` | 로그인한 사용자의 workspace | 세션 필요 |
| POST | `/api/career` | 설정/답변/과제/기존 저장 공고 갱신 | 세션 필요, action 사용 |
| POST | `/api/analyze` | 실제 GitHub 코드 규칙 추출 또는 공고 분석 | 일반 회원, LLM 문장 LV 평가 API는 아님 |
| POST | `/api/analysis-preview` | 임의 GitHub 형식 링크로 흐름 미리보기 및 사용자별 예시 LV 저장 | 일반 회원, 외부 GitHub/LLM 호출 없음 |
| POST | `/api/documents` | PDF 업로드, 텍스트와 기술 근거 추출 | 일반 회원, multipart, PDF 10MB 이하 |
| GET | `/api/documents/{id}` | 본인 문서 다운로드 | 본인 세션, view=text로 추출 텍스트 조회 |
| GET | `/api/jobs` | 공고 목록/검색/필터/상세 | 공개, Spring 공고 + 외부 수집 자료 |
| GET | `/api/jobs/posting` | Lever 공고 본문 읽기 | 공개, url 파라미터, 지원 URL만 |
| GET | `/api/jobs/keywords` | 공고의 검수된 역량 문장/카테고리 | 공개, jobId 필요 |
| GET | `/api/jobs/my-levels` | 본인 공고/역량 문장별 RDS LV | 일반 회원, jobId와 version 필요, userId 입력으로 사용자 변경 불가 |
| GET | `/api/jobs/benchmark` | 예시 공고의 가상 지원자/합격자 집계 | 공개 예시 API, 실제 공고는 UNAVAILABLE |
| GET | `/api/skill-categories` | 10개 기술 카테고리와 기타/제외 정책 | 공개, Spring 전달 |
| GET | `/api/saved-jobs` | 본인 저장 공고 | 세션 필요 |
| POST | `/api/saved-jobs` | 공고 저장/저장 해제 | 세션 필요, action=save/remove |
| GET | `/api/notices` | 공지 목록과 관리자 UI 가능 여부 | 공개, offset 페이지 처리 |
| POST | `/api/notices` | 공지 작성 | RDS ADMIN, title/content/pinned |
| PATCH | `/api/notices` | 공지 수정 | RDS ADMIN, id/title/content/pinned |
| DELETE | `/api/notices` | 공지 논리 삭제 | RDS ADMIN, id |
| POST | `/api/admin/activate` | 일회용 링크로 관리자 초기 비밀번호 설정 | 유효 token/password 필요, 재사용 불가 |
| GET | `/api/auth/kakao/status` | 카카오 연결 설정 여부 | 공개, 키/시크릿은 반환하지 않음 |
| GET | `/api/auth/kakao` | 카카오 인가 시작 | 앱 설정 필요, 미설정 시 503 |
| GET | `/api/auth/kakao/callback` | state 확인, 코드 교환, 기존 로컬 로그인 세션 생성 | code/state, 실제 앱 설정 필요 |
| GET | `/api/admin/extraction-reviews` | 현재 추출 결과에 검토 사유가 있는 미검토 공고, 실제 사유, 상태별 건수 | ADMIN 전용, status/q/offset, 조회 시 원본 검토 대상과 동기화 |
| PATCH | `/api/admin/extraction-reviews` | 넘기기 또는 피드백을 남겨 재추출 요청 | ADMIN, 같은 출처 Origin, id/revision/action(PASS 또는 RETRY)/feedback |
| GET | `/api/growth` | 기존 기술 검토/성장 과제 상태 | 세션 필요, 현재 주 화면에서 사용하지 않는 레거시 |
| POST | `/api/growth` | 기존 검토, 과제 시작/제출/일정 | 세션 필요, 문장 LV 확정 모델은 아님 |
| GET | `/api/share` | 본인 공개 공유 링크 | 세션 필요, 레거시 |
| POST | `/api/share` | 선택한 근거의 공개 공유 링크 생성 | 세션 필요, ids 배열, 레거시 |
| DELETE | `/api/share` | 본인 공유 링크 회수 | 세션 필요, token, 레거시 |

### action을 쓰는 요청

| API | action | 본문 주요 필드 |
|---|---|---|
| POST /api/account | register | name, email, password(10~128자) 필수. age(0~120 정수), school, major 선택 |
| POST /api/account | login | email, password |
| POST /api/account | logout | 없음 |
| POST /api/account | update | name, email, profile |
| POST /api/account | password | current, next(10~128자) |
| POST /api/career | preferences | role(data/backend), region, experience, hours, targetDate |
| POST /api/career | tasks | tasks 배열 |
| POST /api/career | answers | answers 객체 |
| POST /api/career | savedJobs | savedJobs 배열, 기존 호환용 |
| POST /api/saved-jobs | save | job 객체 |
| POST /api/saved-jobs | remove | id |
| POST /api/growth | review | skill, name, status(confirmed/edited/excluded/appeal) |
| POST /api/growth | start | skill, level(1~3) |
| POST /api/growth | submit | id, evidence, explanation |
| POST /api/growth | date | id, date(YYYY-MM-DD) |

### 공고 조회 파라미터

`GET /api/jobs`: id, offset, limit(1~24), role(all/data/backend), q, location,
workplace(all/remote/hybrid/on-site), sort(newest/closing/company), experience(쉼표로 복수 선택).
백엔드 공고 ID는 `be:4562`처럼 표시한다.

`GET /api/jobs/keywords?jobId=be:4562`

`GET /api/jobs/my-levels?jobId=be:4562&version=flat-10-infra-review-20261119`

`POST /api/analyze` 본문: kind(github/job), url, text, company, title.
현재 GitHub/PDF 분석은 규칙 기반 근거 추출이며, 다른 담당자가 연결할 실제 역량 문장 LV 평가와 구분한다.

## 2. Spring 백엔드 API

스테이징은 staging-readonly 프로필이므로 GET/HEAD/OPTIONS만 허용한다. POST/PUT은 코드가 있어도 스테이징에서 405다.
Spring API에 웹 세션 기반 사용자 인증/소유권 연결이 완성된 것으로 취급하지 않는다.

| 메서드 | 경로 | 파라미터/본문 | 역할/연동 |
|---|---|---|---|
| GET | `/api/health` | 없음 | 서버 상태 |
| GET | `/api/postings` | keyword, status, page, size(1~100) | 수집 공고 목록, 웹 연결 |
| GET | `/api/postings/{postingId}` | 공고 숫자 ID | 공고/이미지/모집 단위/현재 추출 결과, 웹 연결 |
| GET | `/api/skill-categories` | 없음 | 검수된 카테고리 정책, 웹 연결 |
| GET | `/api/postings/{postingId}/skill-categories` | 공고 숫자 ID | 문장별 분류, 웹 키워드에 연결 |
| GET | `/api/capabilities` | 없음 | 기존 능력 사전 목록 |
| GET | `/api/postings/{postingId}/fit` | userId(숫자) | 기존 능력 ID별 평가 비교, 최신 문장 LV와 별도 |
| GET | `/api/postings/{postingId}/capability-comparison` | userId(숫자) | 기존 사용자/비교 집단 능력 비교 |
| GET | `/api/postings/{postingId}/recruit-units/{recruitUnitId}/comparison-candidates` | 공고/모집 단위 ID | 비교 대상 공고 후보 조회 |
| GET | `/api/postings/{postingId}/recruit-units/{recruitUnitId}/external-pass-collection-status` | 공고/모집 단위 ID | 외부 합격자료 수집 상태 조회, 수집을 실행하지 않음 |
| GET | `/api/postings/{postingId}/external-pass-materials` | page, size(1~100) | 같은 회사에 연결된 외부 합격자료 |
| GET | `/api/postings/{postingId}/external-pass-keywords` | 공고 ID | 외부 자료의 기술 언급과 필수/우대 기술 교집합 |
| POST | `/api/users` | email, name | Spring 기존 사용자 생성, 로그인 API 아님, 스테이징 차단 |
| GET | `/api/users/{userId}` | 숫자 사용자 ID | Spring 기존 사용자 조회 |
| POST | `/api/users/{userId}/projects` | multipart: projectName, repositoryUrl 또는 file(PDF) | 기존 프로젝트 등록, 스테이징 차단 |
| GET | `/api/users/{userId}/projects` | 숫자 사용자 ID | 기존 프로젝트 목록 |
| GET | `/api/users/{userId}/capabilities` | 숫자 사용자 ID | 기존 능력별 최대 확정 점수/LV |
| GET | `/api/projects/{projectId}` | 프로젝트 ID | 기존 프로젝트 상세/평가 |
| PUT | `/api/projects/{projectId}/evaluations` | evaluations:[{capabilityId,confirmedScore(0~100)}] | 기존 평가기 결과 저장, 스테이징 차단 |
| GET | `/api/projects/{projectId}/description-file` | 프로젝트 ID | 프로젝트 PDF 다운로드 |

Spring 문서: `/swagger-ui/index.html`, OpenAPI JSON: `/v3/api-docs` (Spring에 직접 연결할 수 있는 환경에서 사용).

## 3. ID와 저장소

| 데이터 | 현재 저장소 | 주의점 |
|---|---|---|
| 채용공고와 추출 결과 | RDS public posting/recruit_unit/unit_item 등 | Spring이 읽어서 Next가 전달 |
| 회원/카카오 연결 | RDS career_account / career_account_oauth | CAREER_ACCOUNT_STORE=rds, namespace별 분리 |
| 세션/문서/workspace | 각 웹 서버의 SQLite | 회원 정보는 RDS를 기준으로 조회, 파일과 세션은 서버별 보관 |
| 문장별 사용자 LV | RDS career_lv_posting_keyword_level | 세션 subject + namespace + 공고 + 문장 + 분류 버전 |
| 사용자 자료 메타데이터 | RDS career_lv_analysis_source | 실제 PDF 바이트의 저장 위치와 구분 |
| 관리자 권한 | RDS career_lv_member.app_role | MEMBER/ADMIN, 클라이언트 role 입력을 신뢰하지 않음 |
| 공지사항 | RDS career_notice | namespace별 분리, 관리자만 변경 |

웹 사용자 ID(UUID/문자열)와 Spring 기존 사용자 ID(BIGINT)는 별개이며 임의로 바꿔 넣으면 안 된다.
최신 화면의 문장별 LV에는 `/api/jobs/my-levels`를 사용한다. Spring 기존 `/fit`을 최신 문장 평가로 대체해서 설명하지 않는다.

공개 체험 `/experience`, 관리자 설정 화면 `/admin/setup`, 공유 페이지 `/share/{token}`와 PDF 양식 다운로드는 API 목록과 별도인 페이지/정적 경로다.
