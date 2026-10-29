# Career GitHub → STAT 인계 묶음 (2026-10-27)

새 작업 폴더에서 "GitHub 데이터 → 증거 → 기술별 LV → 내 STAT"을 이어서 만들기 위한 자료 묶음이다.
이 폴더를 새 작업 폴더로 그대로 써도 되고, 새 폴더 안에 통째로 복사해도 된다.

## 먼저 읽을 것

1. `HANDOFF.md` — 결정 · 공식 · 도구 신호 설계 · 현재 코드 상태 · 미정 · 다음 할 일을 담은 핵심 문서
2. `CLAUDE.md` — 이 폴더에서 Claude Code가 자동으로 읽는 작업 규칙. HANDOFF.md를 불러온다.

## 폴더

| 폴더 | 내용 |
| --- | --- |
| `01-decisions/` | `RUBRIC_SOURCE.md`(LV0~5 기준표 원문 · 31개 조건) · `PRODUCT_DECISIONS_2026-10-07.md`(제품 방향 결정 기록) · `lv-generalization-2026-10-10-LATEST_SUMMARY.md`(판정 방식 비교 논의) · `claude-ai-capstone-chat-2026-10-27.md`(claude.ai 대화 원문 — 도구 4개 확정 맥락) |
| `02-experiment/` | 레포 밖 합성 실험(정확도 N/A). `benchmark/bench.py`(Assessment 스키마 · `level_of` 규칙 판정 · 인용 검사 · 선별 재검토) · `rubric.py`(31개 조건 · POLICY · 위험 8개) · `README.md` · `VALIDATION.md` · `GEMINI.md` · `LIVE_PREFLIGHT.md` · `plan.json` · `test_bench.py` · `requirements.txt`, `SNAPSHOT_36.md`(A~E 실측 표), `career-mock20-README.md` · `USERS_20.md`(합성 20명) |
| `03-diagrams/` | 최종 그림 1~9(`final/figN.png` · `figN.html`) · `kit/`(HTML 렌더링 도구 · 폰트) · `FACTS.md`(그림 작업용 사실 자료) · `CRITERIA.md`(판정 기준) |
| `04-repo/` | GitHub에서 받은 코드 사본: `feature-FE@12e5439/`(현재 수집기 `lib/server/analyze.ts` · `lib/skill-patterns.ts` · SQLite 스키마 · 타입 · 문서), `feature-BE@0ec467e/`(Spring 백엔드 전체 Java 코드 — Skill · UserSkill · SkillLevel · SkillEvidence · 평가 서비스), `feature-job-skill@4957696/`(공고 파이프라인 README · `capabilities.json` 표준화 사전 · `db/schema.sql` · 설계 문서), `REMOTE_STATE.md`(브랜치 · PR · Actions/이슈/배포 수 · 계정 레포 · API 한도) |
| `05-memory/` | capstone1-career 세션의 Claude 메모리 사본(`MEMORY.md` 색인 + 10개). 새 폴더에서는 자동으로 읽히지 않으니 필요하면 직접 연다. |

## 넣지 않은 것

- 비밀값이 든 자료: Codex 대화 기록(`codex-conversation-export-2026-10-20/`), 실험 폴더 `.env`
- 큰 자료: 서비스 레포 전체, 실험 폴더 전체(219MB), 합성 제출물 20개(원본 경로에서 사용)
- 원본 위치는 `HANDOFF.md` 14장에 있다.

## 주의

- `04-repo/` 사본은 2026-10-27 21:41 기준 GitHub 상태다. 이후 팀원이 올린 변경은 들어 있지 않다.
- `03-diagrams/kit/render.cjs`는 Playwright를 `/Users/idongmin/Desktop/capstone1-career`의 `node_modules`에서 불러온다. 다른 곳에서 렌더링하려면 경로를 바꾼다.
