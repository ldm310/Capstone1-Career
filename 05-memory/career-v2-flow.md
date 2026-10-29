---
name: career-v2-flow
description: Career v2 service flow (image shared 2026-10-20) — 자료·목표 → per-skill evidence LV → STAT + 공고 적합도 formula → 메타인지 report → re-eval
metadata:
  node_type: memory
  type: project
  originSessionId: 35d2a17e-f172-4742-a028-388b6bb52c36
  modified: 2026-10-27T02:07:07.723Z
---

Source: the "Career 최종 서비스 흐름 · v2" image the user shared on 2026-10-20. Claude drew it as `career_service_flow_v2.png` in the user's claude.ai 캡스톤 chat. It is not saved in the repo, and the image says its skills and numbers are examples. Later proposals in that chat (not yet in the image) would change parts of B and 02: a rubric-based posting→LV mapping, a grade rule on 필수 items instead of the 0.5/0.8 thresholds, A사 0.69 → 0.75, and a risk trigger of "tool signal ≠ LLM judgement". See [[claude-ai-capstone-status]].

- **01 내 자료·목표:** GitHub (본인 commit 기록 + 실제 변경 내용), PDF·MD (이력서·프로젝트·학습 정리·실습 결과), 목표 직무 (image lists 백엔드·AI·데이터, although the 10-08 scope is 데이터·백엔드 only) + 관심 공고 URL·텍스트.
- **02 증거 기반 평가:** ① LLM interprets evidence per L0~L5 criterion and personal contribution, quoting the source → ② rules run automatic checks (citation, code version, missing criteria) and apply cumulative required/prerequisite conditions only to evidence that passed → output = 기술별 LV + 판정 근거 (충족·미충족·미확인 + needed material). Only risk items (근거 충돌, 본인 기여 불명확) go to ③ an extra LLM re-review; resolved → rules re-applied; unresolved → 승급 보류 ('미확인', ask for material / human review). Two LLMs agreeing ≠ correct; misjudgments become regression tests.
- **A 내 STAT** (목표 직무 기준, "나는 어떤 지원자인가"): STAT = share of the role's 5 core skills reaching each stage: 기본 수행 LV0+ / 과제 완성 LV1+ / 신뢰성 LV2+ / 실전 활용 LV3+ / 개선·설계 LV4+. Example Java LV2, Spring LV1, MySQL LV1, Docker LV0, AWS 미확인 → 80/60/20/0/0 %, so 미확인 skills count in the denominator as not reached. Message = the stage where the user gets stuck ("신뢰성에서 막힘" → "과제 완성형 지원자"), not an average. No-evidence skills are 미확인, not a low LV.
- **B 공고 적합도** ("이 공고에 얼마나 가까운가"): LLM turns posting text into 요구 기술·요구 LV·필수/우대 on the same LV scale. 적합도 = Σ(가중치×점수)/Σ가중치; weights 필수 2, 우대 1; score 충족 1, one stage short 0.5, otherwise or 미확인 0. Low < 0.5 ≤ Middle < 0.8 ≤ High (example thresholds). Explicitly not a pass probability.
- **03 메타인지 리포트** (A+B on one screen): ① 나는 이런 지원자 ② 이대로 지원하면 (count of High/Middle/Low among saved postings) ③ 이것부터 강화 (priority = sum of 적합도 gains if that skill rose one stage) ④ 다음 LV에 필요한 증거. The LLM writes sentences only; LV, STAT and 적합도 numbers come from the rules.
- **04 재평가:** a new commit in a linked repo or a new file version → rerun 02 → refresh STAT, 적합도 and priorities, with the change reason, history and a notification. Finishing a study or merely creating commits never auto-promotes.
- **Not in v2:** 스터디 매칭, 포인트·랭킹, 성장 과제. The repo still has code for all three; what happens to it is 미정.

Related: [[professor-feedback-midterm]], [[career-lv-decisions]], [[career-product-context]], [[claude-ai-capstone-status]]
