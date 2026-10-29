---
name: career-evidence-scope
description: User decision 2026-10-27 — evaluate only main + develop of each repo; tool-signal proposal keyed by commit SHA; GitHub API facts checked; consent model
metadata:
  node_type: memory
  type: project
  originSessionId: 35d2a17e-f172-4742-a028-388b6bb52c36
  modified: 2026-10-27T12:22:55.168Z
---

**Decision (user, 2026-10-27):** when analyzing a person's GitHub (many repos), evaluate only the commits on main and develop of each repo and ignore other branches. The user's reason: code merged into main/develop = project completion, and feature branches are full of dummy data and noise. Unmerged work is therefore not evaluated.

**Implementation notes I proposed (not decided):**
- Treat "main" as the repo's default branch, since some repos default to master.
- Dedupe commit SHAs that appear on both branches.
- Take reviews and CI results from the PRs merged into main/develop.
- With squash merges, attribute contributions by PR.
- Filter fork repos to the user's own commits.
- Pick one evaluation snapshot per repo (main vs develop latest) — 미정.

**Tool-signal composition (my proposal this session, not confirmed):**
- Hub = repo + commit SHA + file·line.
- PyDriller + git blame → own changes and surviving lines (L0-02 · L1-02~03 · L3-04).
- Actions → same-SHA test pass/fail (L0-03 · L1-04 · L2-04 · L3-05).
- Opengrep/tree-sitter → exception, validation, transaction and failure-test locations (L2-03, supports L2-04).
- Issue·PR·deploy API → issue → PR → deploy chain (L1-01 · L3-02~05).
- Missing records → 미확인 + request more material, never 미충족.

**Checked 2026-10-27:**
- Team repo ldm310/Capstone1-Career (public): main and develop hold only the Initial commit f3708a7. The 4 PRs were all closed unmerged with 0 reviews; 0 Actions runs, 0 issues, 0 deployments.
- The ldm310 account has 4 public repos.
- GitHub REST limit: 60/h without a token, 5000/h with one.

**Why:** this scope defines what evidence the LV engine reads, so it shapes the collector design and the midterm demo. Our own repo would have nothing to evaluate until the feature branches are merged.

**How to apply:**
- Build the collector on default branch + develop only.
- Analyze only accounts the person connected or entered (consent), and never run fetched code.
- Remind the team to merge their branches before the demo.

Related: [[career-lv-decisions]], [[claude-ai-capstone-status]], [[career-diagram-set]], [[working-style-career]]
