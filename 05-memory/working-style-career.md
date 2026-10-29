---
name: working-style-career
description: How this user wants Claude to work on the Career capstone (from the Codex history and 2026-10-20 instructions)
metadata:
  node_type: memory
  type: feedback
  originSessionId: 12f3abbf-1028-49c5-9df0-279bb4cfb2cb
  modified: 2026-10-20T06:38:19.865Z
---

- Never decide FE/policy details alone — ask. Keep undecided items explicitly 미정 instead of filling defaults.
- Reply in Korean, 핵심적으로; they often ask for an 객관적 judgment and want to be told plainly when an idea is wrong.
- Judge UX from a first-time, non-developer user's view.
- Cost: free tier / existing subscription quota only; stop at once on billing or limit ambiguity; no paid-API switch, no limit workarounds.
- No fabricated evidence: no fake GitHub URLs, no success logs for unrun tests, no expected-LV hints in mock inputs; mock/execution results are not accuracy — mark unmeasured metrics N/A.
- Preserve data: archive and verify before any deletion, and ask first.

**Why:** explicit instructions plus repeated corrections in the Codex history (e.g., a mock benchmark table read as a tool ranking; scenario labels leaking into mock inputs).
**How to apply:** default to asking and preserving; label synthetic vs real; report exactly what was and wasn't run.

Related: [[career-lv-decisions]]
