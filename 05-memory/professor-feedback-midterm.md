---
name: professor-feedback-midterm
description: "Professor feedback before the midterm (recorded 2026-10-20, team agreed to adopt) — deepen 역량 평가→STAT and 공고 similarity instead of adding features; study matching judged off-topic"
metadata:
  node_type: memory
  type: project
  originSessionId: 35d2a17e-f172-4742-a028-388b6bb52c36
  modified: 2026-10-20T07:38:10.247Z
---

Recorded 2026-10-20; the user did not give the feedback date. The team decided to reflect it.

- 스터디 매칭 looks unrelated to 채용공고 분석 + 사용자 역량 평가 → develop 사용자 역량 평가 further instead.
- "여러 기능보다 기존에 있던 기능을 어떻게 더 잘할지 고민을 더 해라" — the project felt like moving on to new features without improving existing ones.
- Wanted flow: user puts in 이력 → system uses LLM + specific rules → builds 내 STAT → 메타인지 ("너는 이런 사람이다", "이대로면 다 떨어진다", which 역량 to strengthen) → compare with 채용공고 (similarity / 합격 가능성 %; e.g. < 0.1 = 큰일).
- STAT and similarity methods need not be complex, but the reasoning must show: on what basis it was judged and what design thought went in — not "just throw it to an LLM".
- 중간발표 (top priority): present 서비스 전체 구조, 설계 과정의 고민, 현재 구현 상황, 최종 목표; contrast with existing services (what they don't cover → what Career 보완).

Professor quote (transcript; "체험 공부" there means 채용공고 per the user's summary): "지원자의 어떤 내 이력들을 막 때려 넣을 거 아니에요. … 나름대로 LLM을 막 써가지고 어떤 특정 룰도 막 써가지고 내 STAT을 얘가 만들어주는 거야. 너는 이런 사람이다. 현실적으로 메타인지 해라. 너 이대로 오면 다 떨어진다. 예를 들어서 이렇게 예측도 해주고 이런 역량 강화해야 되고 이 관점에서 또 체험 공부랑 너 비교하면 similarity가 0.1 미만이면 이제 큰일 났어. 그런 거가 뭔가 좀 더 직접적으로 보여야 되지 않냐는 거죠."

What was presented before this feedback: the 10-14 LV0~5 rubric and the C tool decision with the 36-slot benchmark table ([[career-lv-decisions]]). The team's answer is the v2 flow ([[career-v2-flow]]). The user's own scope for the midterm ("중간까지") = v2 01 자료·목표 → 02 증거 기반 평가 → A 내 STAT.

**Why:** the professor grades the midterm on structure, design reasoning and current implementation, and asked for depth over breadth.
**How to apply:** prioritize depth of 역량 평가/STAT over new features; give every scoring rule a stated rationale that can become a "설계 고민" slide; don't propose study-matching work unless asked.
