# Career 성장 UI 구현 결과

## 실행

Node.js 24 이상에서 `npm install`, `npm run dev -- --hostname 127.0.0.1 --port 3000`.
- 홈페이지: http://127.0.0.1:3000
- 공통 성장 화면 샘플: /dashboard
- 첫 방문 체험: /onboarding
- 실제 계정: /career

## 사용자 흐름

목표 직무 → GitHub 공개 저장소 / PDF / Markdown 자료 하나 추가 → 발견된 기술 및 원문 확인 → 이름 수정·제외·재검토 요청 → 기술별 다음 과제 확인 → 근거 제출 → 성장 기록과 랭킹.

하늘 인트로와 브랜드는 유지했다. 홈페이지 입력 방식·설명, 자료 추가, 성장 대시보드, 기술 상세, 과제, 공고 비교, 계획, 랭킹 설정을 연결했다. 실제 계정 메뉴는 사이드바로 통합하고 기존 지원·일정·면접·공유 기능은 유지했다. 대시보드는 기술 4개를 우선 보여주고 전체 목록으로 연결한다.

## 파일

새 파일:
- types/growth.ts: 수준·결과 검토·과제·제출·보상·랭킹 타입
- lib/growth/catalog.ts: 기술별 3단계 기준, 별칭, 10/20/30점, 동점 1·1·2위
- lib/growth/model.ts: 자료와 검토 상태 연결
- mock/growth.ts: 분리된 체험 자료
- components/growth/growth-hub.tsx: 실제/체험 공통 성장 화면
- components/growth/detail-dialog.tsx: 키보드 초점과 Escape를 지원하는 기술 상세
- components/growth/job-level-comparison.tsx: 공고 요구와 내 수준 비교
- app/api/growth/route.ts: 로그인 사용자별 검토·과제·제출·설정 저장, 공개 랭킹 조회
- lib/server/job-feed.ts: 수집 공고 SQLite 스냅샷, 5분 갱신, 실패 시 시점 표시
- tests/growth-flow.spec.ts: 새 흐름과 보상 경계 검증

주요 변경 파일:
- components/career/workspace.tsx, panels/sources.tsx, jobs.tsx, preferences.tsx
- components/layout/app-shell.tsx
- components/landing/hero.tsx, sky-hero.tsx, feature-section.tsx
- app/career.css, app/layout.tsx, app/onboarding/page.tsx
- app/(workspace)/dashboard, skills, agent, layout
- app/api/analyze, documents, jobs
- lib/skill-patterns.ts: PostgreSQL 별도 추출
- tests/account-workspace.spec.ts, career-flow.spec.ts: 변경된 사용자 흐름에 맞춘 회귀 검사

## 저장 및 정책

기존 사용자 자료는 삭제하거나 변환하지 않는다. 신규 업로드는 PDF/MD만 허용하고 Notion 직접 연결 입력은 제거했다. 이전 DOCX/TXT 자료는 다운로드할 수 있다.

실제 성장 데이터는 SQLite growth 테이블에 계정별로 저장한다. 과제 시작 당시 수준·자료 ID·보상을 고정하며 중복 시작을 차단한다. 결과 확인·자료 추가·제출만으로 보상을 지급하는 경로는 없다. 개인정보나 원문 없이 공개 참여자의 닉네임·점수·완료 단계 수만 집계한다. 미참여자는 목록과 순위 계산 모두 제외한다.

체험 데이터는 sessionStorage의 별도 키에 저장한다. 계정으로 이전하지 않으며, 실제 API나 랭킹에 샘플 보상을 보내지 않는다. 체험 과제를 제출하면 완료·보상 예시를 확인할 수 있다.

## 실제로 제공되는 것과 연결이 필요한 것

실제 제공: GitHub/문서 기술 패턴 추출, 원문 연결, 기술명 확인·수정·제외, 검토 요청 표시, 과제 시작 및 제출 보관, 목표일, 공개 설정과 실제 공개 사용자 랭킹, 계정 저장, 수집 공고 저장 및 검색.

샘플만 제공: 기준을 충족한 LV1/LV2 판정 예시, 과제 승인 및 포인트 획득 시뮬레이션.

추가 연결 필요:
1. 기준별 원문 근거를 반환하는 실제 수준 평가기. 현재 기술 언급으로 LV를 추정하지 않고 판단 보류한다.
2. 제출 버전의 내용 스냅샷·새 작업 여부·실행 결과를 확인하는 검증 서비스. 현재 시작 시 자료 ID만 고정한다.
3. 검증 결과를 승인하고 지급하는 서버 전용 보상 트랜잭션 및 중복 지급 고유 제약, 정정 원장, 실제 검토 담당자와 이의 처리.
4. 공고 본문의 요구 수준을 근거와 함께 판단하는 평가기. 현재 미명시로 안내하며 임의 비교 판정하지 않는다.

실제 제출은 보관되지만 승인이나 포인트 지급이 되지 않는다는 설명을 제출 전에 보여준다. 무기한 관리자 대기로 위장하지 않는다. 실제 자동 평가나 보상까지 완성한 상태는 아니다.

## 검증

Playwright: 모바일 가로 넘침, 접근성, 샘플 완료/보상 유지, 자료 확인과 보상 분리, 실제 계정 저장/분리, 공개 설정, 원문 링크, 지원·일정·면접·공유, 공고 목록, 하늘 인트로. lint / typecheck / production build도 실행한다.

이 검증은 기능·접근성 검사다. 실제 처음 방문하는 한국어 사용자의 이해도 관찰 테스트를 대신하지 않는다.
