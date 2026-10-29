---
name: career-product-context
description: "Career capstone scope, team roles, and confirmed rules from the Codex history that are not in repo docs"
metadata:
  node_type: memory
  type: project
  originSessionId: 12f3abbf-1028-49c5-9df0-279bb4cfb2cb
  modified: 2026-10-20T07:38:43.319Z
---

- Target: 신입/주니어 developers who failed 서류 screening; goal = find and strengthen 역량 for the next chance (자소서 out of scope). Core features were 역량 점검, 채용공고, 스터디 매칭; after professor feedback (recorded 2026-10-20) the team refocused on 역량 평가→STAT and 공고 적합도, and the v2 flow has no 스터디 매칭 ([[professor-feedback-midterm]], [[career-v2-flow]]). Roles fixed to 데이터·백엔드 since 2026-10-08, expand later (the v2 image also lists AI — unresolved).
- The user's midterm scope: v2 01 자료·목표 → 02 증거 기반 평가 → A 내 STAT. B 공고 적합도 and 03 are downstream and consume per-skill LV.
- Team (2026-10-07 meeting): 동민 (the user) = FE + 사용자 역량 분석 (LV, LLM/agent/LangGraph); 승연 = 채용공고 수집·정형화; 선영 = DB schema (공고·사용자 역량·스터디), L/M/H 산정, how to collect "applied" facts.
- L/M/H: among applicants of the same posting; average of the user's LVs for the skills that posting's 자격요건/우대사항 need (weights later); denotes study-participant level; each tier sees only its own studies; Low→Middle, Middle→High, High also gets roadmaps; solo start allowed; "applied" = user presses 지원했어요 after applying externally. v2 reuses Low/Middle/High as 공고 적합도 bands instead (Low < 0.5 ≤ Middle < 0.8 ≤ High, example); whether the study-tier meaning survives is 미정.
- Re-evaluation: after a study/project the user submits new material → same LV criteria, history kept, no LV-up for participation alone.
- Points (defined for LV1~3): none for pre-existing levels; 10/20/30 for completed gap tasks; ranking = 성장 포인트 랭킹, private users excluded, ties 1·1·2.
- Jobs menu: 4 sub-menus confirmed 2026-09-30 (전체 채용공고 / 캘린더 / 지원한 공고 / 내 역량과 비교), but code has 3 tabs (전체 / 저장한 / 내 역량과 비교).
- LV criteria and tech choices must be defensible to the professor, ideally with benchmark evidence.

Related: [[career-lv-decisions]], [[codex-conversation-export]], [[career-v2-flow]], [[professor-feedback-midterm]]
