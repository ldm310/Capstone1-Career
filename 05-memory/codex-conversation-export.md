---
name: codex-conversation-export
description: "Where the prior Codex capstone conversations live, how they are structured, and the gap only the compacted records fill"
metadata:
  node_type: memory
  type: reference
  originSessionId: 12f3abbf-1028-49c5-9df0-279bb4cfb2cb
  modified: 2026-10-20T06:38:02.165Z
---

Prior Codex conversations for this capstone were exported by the user on 2026-10-20 to `codex-conversation-export-2026-10-20/` at the repo root (untracked). The user asked to keep it unmodified and to consult it during future development. It is the source of truth; memories are only pointers into it.

- `conversations/01..07-*.md`: user/assistant text only. 01 = FE/requirements thread (09-30→10-08); 02–06 = LV-criteria/benchmark thread (10-13→10-15); 07 = move to Claude (10-20).
- `originals/*.jsonl`: raw rollouts incl. tool calls; SHA-256 in `manifest.json` (all 7 verified OK on 2026-10-20).
- Gap: earlier messages whose session files no longer exist survive ONLY inside `compacted` records (`payload.replacement_history` / `guardian_history`) of originals 01, 02, 05 — 55 user msgs from 09-26→09-30, 74 user + 18 assistant msgs from 10-01→10-13. Other assistant replies of those periods are lost (compaction summaries are encrypted). Parse read-only to recover.
- Messages embed base64 screenshots; strip them before reading.
- Originals 02/05 contain a local CLIProxyAPI token and a Codex auth-file path with the user's email — never commit/push this folder (origin is GitHub `ldm310/Capstone1-Career`).

Related: [[career-lv-decisions]], [[career-product-context]]
