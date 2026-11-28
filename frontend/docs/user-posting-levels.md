# 사용자·공고별 LV 저장 및 화면 검증

2026-11-22 로컬 검수 완료. BE·FE 브랜치 반영 대상이며 스테이징 배포 전이다.

기존 RDS public 스키마에 `career_lv_member`, `career_lv_analysis_source`,
`career_lv_posting_keyword_level`을 추가했다. 기존 채용공고와 profile 테이블은 수정하지 않는다.
스키마 생성 권한이 없는 기존 계정의 public CREATE 권한을 확인해 충돌 없는 접두어를 사용했다.
마이그레이션: `db/migrations/06-user-posting-levels.sql`.

회원 키는 현재 로그인 시스템(Next 서버 SQLite)의 세션 subject다. 기존 Spring profile.app_user의
숫자 ID와 임의로 연결하지 않는다. namespace로 로컬 검수·스테이징·운영의 ID 공간을 구분한다.
현재 RDS 데이터 namespace는 `local-review`, 더미 회원 subject는 `demo-user`다.

LV 기본 저장 단위는 카테고리가 아니라 **사용자 + 공고 + 역량 문장 ID + 분류 버전**이다.
문장 원문·카테고리·0~100 점수·근거 자료 ID·평가 방식·평가 시각을 같이 저장한다.
현재 더미 점수는 화면 확인용 0~100 스케일이며 실제 LV 산정 규칙을 변경하거나 확정한 것이 아니다.
기타·미분류·제외·검토 필요 문장은 더미 LV 대상에서 제외한다.

`GET /api/jobs/my-levels?jobId=...&version=...`는 세션으로 사용자 ID를 결정한다.
query의 userId는 사용하지 않는다. 비로그인·게스트는 401, 다른 회원은 자기 행만 받는다.
응답은 private/no-store. 분류 버전과 원문·카테고리가 현재 공고와 일치할 때만 표시한다.
DB가 연결되지 않거나 실패해도 공개 공고 내용은 계속 볼 수 있다.
브라우저에서 점수를 쓰는 공개 API는 제공하지 않으며 쓰기는 관리자 CLI에서만 수행한다.

더미 계정은 기존 `demo@career.dev` 로그인 계정을 사용한다.
GitHub와 PDF는 실제 다운로드·업로드 없이 `is_simulated=true`로 등록을 가정한다.
DEMO 평가와 CONFIRMED 평가를 구분하고, 더미 점수는 해당 더미 회원에게만 표시한다.
파란 비교 점수 역시 생성한 화면 검증값으로, 실제 지원자·합격자 평균이 아니다.

차트는 공고 요건이 있고 저장 LV가 있는 카테고리만 사용한다. 카테고리 내 문장의 단순 평균을
0~100 공통 축에 표시하며, 점 좌표의 반지름은 `평균 / 100 * 최대 반지름`이다.
중심 0, 바깥선 100, 20 단위 눈금을 사용한다. 파랑=비교 값, 초록=내 LV.
닫힌 다각형·반투명 채움·꼭짓점을 표시하며, 점에서 카테고리 평균을 확인할 수 있다.
카테고리 3개 미만은 다각형을 생략하고 간단한 수치로 표시한다. 미측정 카테고리를 0으로 바꾸지 않는다.
하단 카테고리 표와 막대바는 추가하지 않았다.

서버 환경설정(커밋 금지):

- CAREER_PROFILE_DATABASE_URL: RDS PostgreSQL 연결 문자열
- CAREER_PROFILE_CA_FILE: AWS 공식 RDS CA 번들 경로 (TLS 인증서 검증)
- CAREER_PROFILE_NAMESPACE: 배포 환경별 고유 namespace

관리자가 명시적으로 실행하는 초기화 도구:
`node scripts/setup-user-levels.mjs --env <기존 DB 설정 파일> --apply --seed-demo --configure-local`.
도구는 현재 세션을 생성하거나 실사용자 점수를 수정하지 않는다. 기존 CONFIRMED 행도 덮어쓰지 않는다.
프로덕션 자동 실행 작업에 포함하지 않는다.

검증: 실제 RDS 저장 조회, 재조회 일관성, 공고 간 차이, 구버전 미노출, 익명 401,
다른 회원의 userId 위조 격리, 실제 SVG 반지름 비율, 모바일 너비, 공개 공고 회귀 및 접근성.
실제 RDS 통합 검증은 RUN_RDS_LV_TESTS=1로 명시적으로 켠다.

## 2026-11-23 화면 간소화

- 공고 내용·역량 분석은 URL의 view로 전환하는 실제 탭이다. 해시·스크롤 이동을 제거했다.
- 선택된 탭의 내용만 마운트한다. 공고 내용 탭에서는 개인 분석 API를 호출하지 않는다.
- 역량 분석의 문장별 LV 목록·반복 설명·원문 조회 버튼과 안내를 제거했다. 저장 데이터와 API는 유지한다.
- 차트 점은 즉시 나타나는 LV 툴팁을 제공한다. 키보드 포커스·Enter·Escape·터치도 지원한다.
- 공고 본문의 줄간격, 항목 간격, 여백을 줄였다. 근무지, 접수, 기업 정보는 펼쳐서 표시한다.
- 이번 화면 조정은 로컬 검수 중이며 원격 브랜치에는 아직 반영하지 않았다.

## 2026-11-28 스테이징 LV 서비스(분석 결과로 계산한 LV)

- 서버 설정 `CAREER_LV_STAT=on`(스테이징 웹만, `deploy/web/deploy.sh`)이면 `GET /api/jobs/my-levels`는 그 회원의 분석 결과 파일(`<CAREER_DATA_DIR>/lv-stat/profiles/`, 형식은 `lv-stat/service/CONTRACT.md`)을 먼저 읽는다. 있으면 저장된 LV(RDS)를 읽지 않고 공고 문장마다 그 자리에서 점수를 계산해 같은 모양으로 준다. DB에는 쓰지 않는다.
- 결과 파일이 없으면, 그리고 스위치가 꺼진 운영과 데모 계정은 지금처럼 RDS를 읽는다(`source: "RDS"`).
- 분석 결과로 계산한 답은 `source: "LV_STAT"`이다. 행마다 `usedCodes`(점수를 낸 카테고리, 레이더는 이 축에만 값을 놓음)가 있고 `referenceScore`·`referenceKind`는 null(파란 선 없음), `evaluationKind`는 `CONFIRMED`, `evaluatedAt`은 분석 시각이다. 답에는 `labels`(화면의 라벨 한 줄: 2단계 규칙 · LLM 보충 끔 · 제안 기준 · 본인 확인 안 됨), `identityVerified: false`, `methodVersion`(결과 파일의 method)이 더 있고, `sources`는 분석한 GitHub 계정 하나다.
- 공고 화면: LV_STAT 답은 맞는 행이 없어도 자료 1개로 세서 빈 차트와 라벨을 보인다('분석 자료 미등록'이 아님). RDS 답은 지금처럼 맞는 행이 있을 때만 쓴다. 분류 버전이 없는 공고는 분석 결과(`GET /api/lv-stat/analysis`의 profile)가 있으면 자료 1개로 센다.
