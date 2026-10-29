# Career

프로젝트 자료(GitHub, Notion, 문서)에서 기술 근거를 찾고, 채용공고 요구 기술과 비교해 준비할 내용을 정리하는 서비스입니다. 별점이나 AI 능력 점수 대신 근거의 출처와 위치를 보여줍니다.

## 실행

Node.js 24 이상과 npm이 필요합니다. 서버 저장소는 Node 내장 SQLite를 사용합니다.

```sh
npm install
npm run dev
```

브라우저에서 http://localhost:3000 을 엽니다.

```sh
npm run typecheck
npm run lint
npm run build
npm start
```

## 백엔드 연결

저장소 루트의 Spring 백엔드(`backend/`)에서 채용공고를 받아옵니다. `frontend/.env.local`에 주소를 적습니다.

```sh
BACKEND_URL=http://localhost:8080
```

- 백엔드는 루트에서 `docker compose up -d`로 띄웁니다. 공고 데이터는 job-skill 파이프라인이 DB에 넣습니다.
- 브라우저는 백엔드를 직접 부르지 않습니다. 프론트 서버(`lib/server/backend-jobs.ts`)가 `GET /api/postings`, `GET /api/postings/{id}`를 불러 공고 형식으로 바꿉니다. 결과는 5분 동안 재사용합니다.
- 진행 중 공고 가운데 데이터, 백엔드 직무만 보여줍니다. 공고 ID는 `be:<postingId>`입니다.
- 추출 결과의 업무, 필수, 우대, 기타가 공고 내용의 주요 업무, 자격요건, 우대사항, 기타가 됩니다. 요건의 기술 이름(사전 이름, 없으면 적힌 이름)이 공고 기술이 됩니다.
- 백엔드에 없는 근무지는 "근무지 원문 확인"으로 두고 상세의 근무지 위치는 숨깁니다.
- `BACKEND_URL`이 없거나, 백엔드가 응답하지 않거나, 공고가 없으면 지금처럼 수집 공고와 더미 공고만 보여줍니다.
- 아직 연결하지 않은 것: 로그인, 내 역량 LV(`/api/users/{id}/capabilities`), 공고 대비 내 LV(`/api/postings/{id}/fit`), 프로젝트 등록. 백엔드에 로그인이 생긴 뒤 연결합니다.

## 데모 계정

| 항목     | 값                  |
| -------- | ------------------- |
| 이메일   | `demo@career.dev`   |
| 비밀번호 | `career-demo-2026`  |
| 이름     | 김커리어            |

로그인하면 내 자료, 분석 결과, 기술 점수, 마이페이지(내 정보, 저장한 공고 3개)가 미리 채워져 있습니다. 데모 계정은 이메일과 비밀번호를 바꿀 수 없습니다. 처음 상태로 되돌리려면 `.career-data/career.sqlite`를 지우고 다시 로그인합니다.

> 데모 비밀번호가 저장소에 공개되어 있습니다. 외부 배포 전에 `lib/server/demo-account.ts`와 로그인 호출부를 제거해야 합니다.

## 화면

| Route                          | 내용                                                     |
| ------------------------------ | -------------------------------------------------------- |
| `/`                            | 홈 대시보드: 인사, 요약 4개, 역량 레이더, 추천 공고 3개  |
| `/jobs`                        | 채용공고 목록, 검색, 저장                                |
| `/jobs?job=<id>`               | 공고 상세: 지원자 비교, 공고 내용 탭                     |
| `/jobs?job=<id>&view=compare`  | 공고 상세의 역량 비교 탭(자동 분석)                      |
| `/my-skills`                   | 내 역량: 분석 결과, 추천 과제                            |
| `/my-data`                     | 내 자료: 자료 추가, 포트폴리오 공유                      |
| `/sign-in`                     | 가입, 로그인                                             |
| `/my-page`                     | 마이페이지: 저장한 공고                                  |
| `/my-page?tab=profile`         | 마이페이지: 내 정보 수정, 비밀번호 변경                  |
| `/postings/<id>`               | 더미 공고의 가짜 원문 페이지                             |
| `/documents/<id>`              | 업로드한 문서 원문, `#L행`으로 위치 확인                 |
| `/share/<token>`               | 공개 포트폴리오                                          |

`/career?tab=...`처럼 예전 주소로 들어오면 `lib/feature-sections.ts`의 `legacyDestination`이 새 화면으로 보냅니다. 메뉴와 탭 정의도 같은 파일에 있습니다.

## 주요 기능

- **계정**: 이메일/비밀번호 가입, scrypt 해시, HttpOnly 세션 쿠키, 계정별 SQLite 저장. 로그인 전에는 게스트 공간을 씁니다.
- **자료 분석**: 공개 GitHub 저장소(소스/설정 파일 최대 20개), Notion 토큰 연결 페이지, PDF/DOCX/MD/TXT 업로드(10MB/파일). 규칙 기반 기술 추출이며 LLM 추론이나 숙련도 인증이 아닙니다.
- **채용공고**: Lever 공개 API(채널코퍼레이션, 매치그룹)의 국내 AI, ML, 데이터 직무를 가져옵니다.
- **공고 상세**: 맨 위에 회사, 제목, 저장, 지원 버튼(D-day)과 경력, 학력, 급여 등 요약 표를 둡니다. 그 아래 나, 전체 지원자 평균, 합격자 평균을 비교하는 레이더를 항상 보여줍니다. 공고 내용 탭 아래에는 근무지 위치, 접수 기간(남은 시간), 기업 정보가 있습니다. 원문에 없는 값은 숨깁니다. 탭은 공고 내용, 역량 비교 순서입니다. 역량 비교는 탭을 열면 바로 분석합니다.
- **내 역량**: 분석 결과는 모든 기술을 한 목록에 점수순으로 보여줍니다. 한 줄에 기술명, LV 1~100, 단계 색으로 차오르는 막대가 있고, 누르면 근거와 단계별 기준이 열립니다. 추천 과제는 직무별 학습 경로와 기술별 다음 과제를 보여줍니다. 진행 중 과제, 주간 계획, 면접 준비 화면은 없앴고 예전 주소는 추천 과제로 보냅니다.
- **마이페이지**: 저장한 공고를 계정별로 서버에 보관합니다(게스트 포함). 저장 시점의 공고 내용을 같이 저장합니다. 내 정보(이름, 이메일, 학력, 경력, 학교, 전공, 희망 근무지, GitHub, 한 줄 소개)와 비밀번호를 바꿀 수 있습니다. 예전 `/jobs?tab=saved`는 `/my-page`로 보냅니다.
- **포트폴리오 공유**: 고른 발췌문과 이름만 공개하는 링크를 만들고 중단할 수 있습니다.

## 기술 점수

`lib/growth/score.ts`

- 점수 = 확인 단계 기본점 + 근거 보너스(최대 24), 1~100으로 자릅니다.
- 단계 기본점: 미확인 6, 1단계 22, 2단계 46, 3단계 70.
- 근거 보너스: 구현 근거 6점, 그 밖의 근거 3점, 프로젝트당 2점.
- 등급: 입문(1), 기초 적용(20), 기능 구현(40), 통합 구현(60), 심화 개선(80). 등급마다 카드 색이 바뀌고 심화 개선은 빛나는 효과가 있습니다.
- `SkillReview.score`가 저장되어 있으면 그 값을 씁니다. 아직 점수를 저장하는 화면은 없습니다.
- 과제 단계(1~3단계)와 점수(1~100)는 별개 값입니다.

## 더미 데이터

- `lib/dummy-jobs.ts`: 더미 공고 6개(클라우드웨이브, 데이터브릿지, 핀테크랩, 쇼핑하우, 로그웍스, 모빌리티원)와 공고 본문, 상세 정보(`details`: 학력, 급여, 주소, 접수 기간, 기업 정보).
- `/api/jobs`는 실제 공고가 6개보다 적으면 더미로 채웁니다. 원본 API가 실패해도 오류 문구를 띄우지 않습니다.
- 더미 공고와 예시 공고는 `dummy: true`이며 원문 링크가 `/postings/<id>`로 갑니다.
- 실제 공고에 링크가 없으면 "원문을 찾을 수 없습니다."를 표시합니다.
- 지원자 비교 레이더의 축은 공고의 기술입니다. 기술이 5개보다 적으면 직무 기본 기술로 채우고, 최대 8개까지 보여줍니다. 값은 모두 LV(1~100)입니다.
- 나는 내 역량과 같은 방식으로 계산한 실제 LV입니다. 자료가 하나도 없으면 예시 값을 쓰고 화면에 그렇게 표시합니다.
- 지원자 평균, 합격자 평균은 `lib/applicant-benchmark.ts`에서 공고 ID로 만든 예시 값입니다. 실제 지원자 통계가 아닙니다.
- 공고 상세의 레이더 아래에 **합격자의 우대사항 충족 현황**이 있습니다. 공통 항목(관련 전공, 프로젝트 또는 실무 경험)과 공고 본문의 우대사항마다 충족한 합격자 수와 비율을 막대로 보여줍니다. 기술이 들어간 항목에는 합격자 평균 LV와 내 LV를 함께 적습니다. 본문이 없는 공고는 공고 기술로 항목을 만듭니다.
- 공고 목록 카드와 마이페이지 저장한 공고에는 한 줄 비교(합격자 평균 LV, 내 LV, 가장 부족한 기술)가 붙습니다. 내 LV는 `lib/my-levels.ts`에서 한 번 불러와 카드끼리 나눠 씁니다.

## API

| API                          | 내용                                       |
| ---------------------------- | ------------------------------------------ |
| `GET /api/jobs`              | 공고 목록, 3개 미만이면 더미 보충          |
| `GET /api/jobs/posting?url=` | 실제 공고 본문을 섹션별로 정리             |
| `POST /api/analyze`          | 자료 또는 공고 분석, 더미 공고는 준비된 본문 사용 |
| `GET/POST /api/account`      | 가입, 로그인, 로그아웃, 현재 사용자와 내 정보, 정보 수정(`update`), 비밀번호 변경(`password`) |
| `GET/POST /api/career`       | 계정 작업 공간                             |
| `GET/POST /api/growth`       | 기술 확인과 과제(`reviews`, `tasks`)       |
| `/api/documents`, `/api/documents/:id` | 문서 업로드, 조회                |
| `/api/share`                 | 포트폴리오 공유 링크                       |
| `/api/guest`                 | 게스트 공간                                |
| `GET/POST /api/saved-jobs`   | 저장한 공고 조회, 저장(`save`), 취소(`remove`) |

개인 API와 문서는 로그인한 소유자만 볼 수 있습니다.

## 구조

```text
app/
  (features)/        # jobs, my-data, my-skills (공통 레이아웃)
  api/               # 위 API
  postings/[id]/     # 더미 공고 원문
  page.tsx           # 홈 대시보드
  readability.css    # 마지막에 불러와 다른 스타일을 덮어씀
components/
  home/              # 홈 대시보드
  jobs/              # 공고 상세, 공고 내용, 역량 비교, 지원자 비교
  growth/            # 내 역량, 기술 카드
  career/            # 내 자료, 작업 공간
  layout/            # 헤더
  shared/            # 로딩 스피너 등
lib/
  server/            # 저장소, 인증, 분석, 데모 계정
  growth/            # 기술 점수, 확인 모델
  dummy-jobs.ts
  feature-sections.ts
tests/               # Playwright, axe 접근성 테스트
```

## 저장과 운영

- DB와 문서는 `.career-data/career.sqlite`에 저장하며 Git에서 제외합니다. `CAREER_DATA_DIR`로 위치를 바꿀 수 있습니다.
- 서버 한 대 구조입니다. 서버리스 임시 디스크에 배포하면 안 됩니다.
- 운영 배포에는 HTTPS, 영구 볼륨, 백업이 필요합니다. 이메일 인증, 비밀번호 복구, OAuth는 연결되어 있지 않습니다.

## 테스트

```sh
npx playwright install chromium
npm run test:e2e
```

결과는 `work/test-results/`에 저장합니다. 테스트는 외부 공고 변동과 분리된 fixture를 씁니다. Chromium 설치가 어려우면 Playwright 설정에 `channel: "msedge"`를 넣어 Edge로 실행할 수 있습니다.

## 출처

- 원문 수집: [GitHub Git trees](https://docs.github.com/en/rest/git/trees), [Notion block children](https://developers.notion.com/reference/get-block-children), [Lever postings API](https://github.com/lever/postings-api)
- 하늘 사진: [CHUTTERSNAP / Unsplash](https://unsplash.com/photos/clouds-during-daytime-M2-_GRvWWg0), `public/images/career-sky.jpg`
