# GitHub 상태 기록 (조회: 2026-10-27 21:41 KST)

레포: https://github.com/ldm310/Capstone1-Career (공개). gh CLI(인증)로 조회한 값이다. 로컬 폴더 /Users/idongmin/Desktop/capstone1-career는 마지막 fetch가 2026-09-30이라 이와 다를 수 있다.

## 브랜치 최신 commit

| 브랜치 | commit | 작성자 | 날짜 | 메시지 |
| --- | --- | --- | --- | --- |
| develop | f3708a7 | DONGMIN LEE | 2026-09-25 | Initial commit |
| feature/AI | f3708a7 | DONGMIN LEE | 2026-09-25 | Initial commit |
| feature/BE | 0ec467e | Seonye32 | 2026-10-15 | docs: add Swagger API documentation |
| feature/FE | 12e5439 | Seonye32 | 2026-10-27 | 공고 상세 개편, 마이페이지 추가, 내 역량 분석 결과를 한 목록으로 정리 |
| feature/LV-evaluation | 67956e9 | DONGMIN LEE | 2026-10-01 | Add files via upload |
| feature/job-skill | 4957696 | lsy341 | 2026-10-27 | feat: 파이프라인 표를 job 스키마로 분리 |
| feature/lv-evaluation | d950341 | 이동민 | 2026-10-27 | test |
| main | f3708a7 | DONGMIN LEE | 2026-09-25 | Initial commit |

- 로컬 feature/FE(d36bd5d) 대비 GitHub feature/FE: 5개 앞섬, 0개 뒤짐
- main · develop에 없는 commit 수: feature/FE 12개 · feature/BE 8개 · feature/job-skill 6개 · feature/lv-evaluation 13개 (main 기준)

## PR

| 번호 | 제목 | head → base | 상태 | 병합 | 리뷰 수 |
| --- | --- | --- | --- | --- | --- |
| #4 | Feature/lv evaluation | feature/lv-evaluation → main | closed | false | 0 |
| #3 | Add files via upload | feature/LV-evaluation → develop | closed | false | 0 |
| #2 | Feature/fe | feature/FE → main | closed | false | 0 |
| #1 | chore: setup frontend environment | feature/FE → main | closed | false | 0 |

## 도구 신호에 쓸 기록

- GitHub Actions 실행 기록: 0건
- 이슈(PR 제외): 0건
- 배포 기록(deployments): 0건
- PR 리뷰: 위 표 참고

## ldm310 계정 공개 레포 (다른 사람이 볼 때와 같은 목록)

| 레포 | 기본 브랜치 | fork | 브랜치 | main·develop 규칙으로 볼 브랜치 |
| --- | --- | --- | --- | --- |
| 2026ESWContest_free_Ieum | main | false | develop feature/byunghyun feature/dongmin feature/junhyeong main | develop main |
| Auto-Reply | main | false | agent/initial-project-setup main | main |
| Capstone1-Career | main | false | develop feature/AI feature/BE feature/FE feature/LV-evaluation feature/job-skill feature/lv-evaluation main | develop main |
| LangGraph | main | false | main | main |

## API 한도 (직접 조회)

- 토큰 있음: 5000회/시간
- 토큰 없음: 60회/시간

## 오늘 팀원이 올린 commit에서 바뀐 파일

### 12e5439 · Seonye32 · 2026-10-27 · 공고 상세 개편, 마이페이지 추가, 내 역량 분석 결과를 한 목록으로 정리

- modified `README.md` (+11/-7)
- modified `app/(features)/jobs/page.tsx` (+10/-7)
- modified `app/(features)/layout.tsx` (+1/-0)
- added `app/(features)/my-page/page.tsx` (+9/-0)
- modified `app/api/account/route.ts` (+59/-1)
- modified `app/api/jobs/route.ts` (+1/-1)
- added `app/api/saved-jobs/route.ts` (+49/-0)
- added `app/job-detail.css` (+588/-0)
- modified `app/skills.css` (+79/-192)
- removed `components/career/panels/interview.tsx` (+0/-57)
- removed `components/career/panels/plan.tsx` (+0/-118)
- modified `components/career/workspace.tsx` (+1/-11)
- modified `components/growth/growth-hub.tsx` (+114/-243)
- modified `components/growth/learning-path.tsx` (+8/-14)
- modified `components/growth/skill-card-grid.tsx` (+50/-134)
- modified `components/jobs/job-detail.tsx` (+10/-17)
- added `components/jobs/job-summary.tsx` (+253/-0)
- modified `components/landing/live-jobs-section.tsx` (+17/-105)
- modified `components/layout/feature-shell.tsx` (+13/-11)
- modified `components/layout/header.tsx` (+38/-10)
- added `components/my-page/profile-panel.tsx` (+313/-0)
- added `components/my-page/saved-jobs-panel.tsx` (+95/-0)
- modified `lib/dummy-jobs.ts` (+267/-0)
- modified `lib/feature-sections.ts` (+17/-11)
- modified `lib/growth/score.ts` (+0/-15)
- added `lib/saved-jobs.ts` (+82/-0)
- modified `lib/server/demo-account.ts` (+27/-1)
- modified `lib/server/store.ts` (+3/-1)
- added `lib/server/user-data.ts` (+77/-0)
- modified `tests/account-workspace.spec.ts` (+7/-21)
- modified `tests/demo-account.spec.ts` (+11/-10)
- modified `tests/feature-pages.spec.ts` (+28/-38)
- modified `tests/guest-flow.spec.ts` (+4/-8)
- added `tests/my-page.spec.ts` (+107/-0)
- modified `tests/public-jobs.spec.ts` (+13/-13)
- added `types/profile.ts` (+32/-0)
- modified `types/public-job.ts` (+24/-0)

### 4957696 · lsy341 · 2026-10-27 · feat: 파이프라인 표를 job 스키마로 분리

- modified `job-skill/README.md` (+1/-0)
- modified `job-skill/db/schema.sql` (+6/-0)
- modified `job-skill/db_load.py` (+6/-4)
- modified `job-skill/docs/erd-physical.png` (+0/-0)
- modified `job-skill/docs/erd-physical.svg` (+1/-1)
- modified `job-skill/docs/physical-design.md` (+3/-0)
