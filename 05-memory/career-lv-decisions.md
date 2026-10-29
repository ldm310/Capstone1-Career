---
name: career-lv-decisions
description: "Latest LV scheme and LV-judging tool decision (2026-10-14/15) — newer than repo docs/code, which still use LV1~3"
metadata:
  node_type: memory
  type: project
  originSessionId: 12f3abbf-1028-49c5-9df0-279bb4cfb2cb
  modified: 2026-10-20T07:38:36.865Z
---

State as of 2026-10-15 (Codex thread 2; see [[codex-conversation-export]] conversations 03–06 and compacted records):

- Team switched LV1~3 → **LV0~5** on 2026-10-07. Latest candidate (10-14, not validated): one common LV per selected role, cumulative, final LV computed by rules: LV0 기본 수행 → LV1 과제 완성 → LV2 신뢰성 확보 → LV3 실제 활용·변경 대응 → LV4 측정 기반 개선 → LV5 복합 문제 설계. 31 criteria L0-01…L5-07 (4/4/5/5/6/7). Criterion states 충족/미충족/근거 부족/충돌; no evidence = "LV 근거 부족", never LV0/null. Conditional-required checks (A-01…A-08) are selected by rules before judging, applicability recorded separately. Deploy/maintenance sits mainly in LV3+. Must generalize to later roles (AI, infra) via role-specific evidence rules.
- Full rubric text (sections 2–9: criteria with 확인할 근거 / 인정하기 어려운 경우 / 직무 예시, the cumulative rule, the LV2-cap caveat, rule-vs-LLM scope) is in `~/Desktop/experiments/lv-evaluation/career-mock20-v1/benchmark/RUBRIC_SOURCE.md`. On 2026-10-20 the user re-shared the same 10-14 text (headed "이동민 (10-14)") as what was presented to the professor; spot-checked identical.
- Open: whether the team accepts that no real-use evidence caps LV at 2; point values for LV0~5 (v2 has no points, see [[career-v2-flow]]).
- Tool decision as presented to the professor (labelled "Tool 결정"; benchmark never proved it the accuracy winner): **C = LLM evidence interpretation + Python rule judge**, plus selective LLM re-review only for promotion-affecting conflicts / unclear personal contribution / re-eval contradictions; unresolved → hold and ask for material or human review; confirmed misjudgments → regression tests. Plain Python fixed workflow; no Multi-agent/LangGraph yet.
- Benchmark A–E is outside the repo: `~/Desktop/experiments/lv-evaluation/career-mock20-v1` (older 50/100 sets archived in `archive/2026-10-15-legacy-50-100`). Last run: Gemini 3.5 Flash-Lite free tier, 36/100 evaluations; accuracy N/A (no human gold answers). The presented table is `benchmark/runs/gemini35-lite-schema-20-r1/SNAPSHOT_36.md` (synthetic mock20; 7 users for A/C/D/E, 8 for B). In it E made the same 14 logical calls as D (157k vs 161k tokens) because the experiment's review selection takes every unknown/conflict item and every met L3+ item, so every user got reviewed. C left 3/7 users' LV on hold.
- The experiment gives one LV per user per role; v2 needs a separate LV per skill ([[career-v2-flow]]), so the judge cannot be ported unchanged.
- Repo still on the old scheme: `types/growth.ts` `Level = 1 | 2 | 3`, `lib/growth/catalog.ts` rewards `{1:10, 2:20, 3:30}`, `docs/career-product-requirements.md` (10-08) marks LV criteria 미정.

**Why:** the FE thread and the LV thread were separate Codex sessions and never synced.
**How to apply:** new evaluation/STAT code follows the v2 flow (LV0~5 per skill); before changing the existing LV1~3 growth tasks, points or study-tier code, ask the user — don't silently rewrite them.
