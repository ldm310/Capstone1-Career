---
name: claude-ai-capstone-status
description: "Progress, decisions and open items from the user's claude.ai \"캡스톤 프로젝트\" chat (between 2026-10-20 and 10-27) — tool choice, posting→LV mapping, figures, next steps"
metadata:
  node_type: memory
  type: project
  originSessionId: 35d2a17e-f172-4742-a028-388b6bb52c36
  modified: 2026-10-27T02:07:00.600Z
---

Source: a status thread the user copied from the claude.ai 캡스톤 project chat and pasted here on 2026-10-27. The verbatim copy is in `claude-project-export-2026-10-27/claude-ai-capstone-chat-paste.md` at the repo root (untracked, excluded via `.git/info/exclude`). The figures exist only in that claude.ai chat: `career_service_flow_v2.png` (the v2 flow, [[career-v2-flow]]) and diagrams 그림 1~9, from 전체 구조 to 시스템 구성도. The user has not yet said whether those figures are right.

**Confirmed by the user**
- LV0~5 rubric with rule-based cumulative judging ([[career-lv-decisions]]).
- Engine = C: LLM interpretation + rule judging; only risk items get an extra LLM review.
- 4 evidence tools: GitHub Actions run records; PyDriller + git blame (personal contribution); Opengrep/tree-sitter (code structure); Issue·PR·deploy APIs.

**Proposed by Claude, not confirmed**
- STAT: stage reach ratios, "막힘" threshold 50 %, applicant-type names.
- Rubric-based posting→요구 LV mapping, with the rubric's 인정하기 어려운 경우 applied to postings too:

| Posting wording | Required LV |
| --- | --- |
| 사용·활용 경험, 환경 구성, 배포 경험 | LV0 |
| 웹 서비스·기능 개발, CRUD | LV1 |
| 예외 처리, 예외·실패 테스트, 권한·트랜잭션 | LV2 |
| 서비스 운영, 유지보수, 장애 대응 | LV3 |
| 성능 개선, 쿼리 최적화, 병목 분석 | LV4 |
| 아키텍처·고가용성 설계 | LV5 |

  "테스트 작성 경험" alone maps to LV1; a bare "MSA 경험" is not LV5. The LLM only extracts tech names and phrases; the table sets the LV.
- Grade by a rule on 필수 items, with 우대 shown beside the grade. Low splits into '근거 부족' vs '역량 부족'. This replaces the 0.5/0.8 thresholds.
- Evidence grade: 도구 확인 > 코드 + LLM 해석 > 자기 서술; a matching '미확인' policy.
- Risk-item trigger changes to "도구 신호와 LLM 판단이 다른 항목".
- Risk selection sits after ② rule judging, because only a first rule pass shows which items affect promotion.
- Automatic checks (citation, code version, missing criteria) are input conditions of ②, not a separate stage.

**Six weak spots diagnosed:** evaluation-accuracy validation, posting→LV basis, basis for the numbers, evidence trust and personal contribution, '미확인' handling, no role rubric yet.

**Open / not done**
- Team decision: the default 요구 LV when a posting only lists tech names. LV0 follows the rubric literally; LV1 reflects the expectation of project experience.
- Figure fixes not yet made:
  - Add the tool stage to 그림 3 and apply the new risk trigger there.
  - Put the new mapping and grade rule into 그림 6 and the flow; the A사 example goes 0.69 → 0.75.
  - Change "같은 근거면 같은 LV" to "같은 조건 판정이면 같은 LV".
- Real work: backend role rubric v1; a gold set of 10–20 cases with an agreement check; the 기존 서비스 비교 the professor asked for (still empty).
- Next steps recommended there: settle the default LV and the grade rule → fix 그림 3·6 and the flow in one pass → prepare the existing-service comparison.

**Why:** the claude.ai thread and the Claude Code/Codex threads are separate and never synced.
**How to apply:** treat items under "Proposed" as 미정 and confirm before building on them. The figures can't be fetched from here; ask the user for them if needed.
