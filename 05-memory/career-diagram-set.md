---
name: career-diagram-set
description: "Midterm diagram set 그림 1~9 rebuilt and approved 2026-10-27 by 5-agent review; where it lives, color rule, open decisions"
metadata:
  node_type: memory
  type: project
  originSessionId: 35d2a17e-f172-4742-a028-388b6bb52c36
  modified: 2026-10-27T11:13:51.245Z
---

Final set: `/Users/idongmin/Desktop/capstone1-career/diagram-review-2026-10-27/final/fig1~9.png` (+ .html, links to `../kit`). The folder is untracked in git.

How it was made (2026-10-27): 2 composers + 2 judges + 1 final checker.
- The original claude.ai set was judged 부분 적합 (그림 3 missing because the user pasted 그림 2 twice, old 0.69 → 0.81 mapping, AI in 직무, no 충돌 state, 그림 9 erased Next.js/SQLite as '스택 미정').
- All 9 figures were recomposed. The final checker rejected once, over the 제안 chip color in 그림 6·7·8, then approved.
- `FACTS.md` and `CRITERIA.md` in that folder hold the facts and criteria used. `kit/` renders HTML → PNG with checks.

Color rule in the set:
- 제안·미정 = red `.status.open`
- 계획 = yellow `.status.plan`
- 구현됨 = green
- 실험 = blue

Canonical example: A사 0.75 Middle → Spring LV2 → 0.88 High.

**Why:** the set is for the midterm presentation, so the professor's 4 asks are covered: 1·9 구조, 설계 고민 in every figure, 9 현재 구현 상태, 1 최종 목표.

**How to apply:**
- Edit figures through kit + FACTS; don't hand-draw.
- Items marked 제안/미정 still need team decisions: STAT method, 매핑표, 등급 규칙, default LV for name-only postings, LLM model, Python integration, 직무 기준표 v1, LV2 상한, old LV1~3 code. Don't present them as decided.
- The user has not reviewed the final set yet.

Related: [[career-v2-flow]], [[claude-ai-capstone-status]], [[career-lv-decisions]], [[professor-feedback-midterm]]
