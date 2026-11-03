---
name: coding-session-continuity
description: "Use when recovering and resuming prior coding sessions."
version: 2.0.0
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [session-recovery, coding-agents, git, provenance, continuity]
    category: software-development
    related_skills: [repository-architecture-audits, multi-agent-release-readiness]
---

# Coding Session Continuity

Find prior coding work, prove who and what produced it, and resume from the live repository state instead of from memory. The core is harness-neutral. Optional adapters for specific history tools are in [references/history-adapters.md](references/history-adapters.md).

## When to Use

- The user remembers prior work but cannot find the conversation, or thinks it started in another directory.
- The user asks which agent, harness or model did some work.
- The user asks what is "running" or what happened "last".
- Resuming interrupted work without losing decisions or uncommitted state.

Don't use for: catching up on the current conversation only (pstack [`recall`](https://github.com/cursor/plugins/tree/main/pstack/skills/recall) reconstructs your own recent context).

## Core Rule: Four Separate Identities

Recover provenance from primary artifacts, never from code style or model folklore. Report these separately:

- **Harness:** the CLI, IDE extension or app that ran the session.
- **Model and provider:** what generated tokens and who billed them. A harness routed through another vendor's provider is still that harness.
- **Git authorship:** commit author and co-author trailers. Imported or filtered donor history carries old trailers.
- **Working directory:** where the session started, which can differ from the repositories it read.

Reading a `CLAUDE.md` is not running Claude Code. A co-author trailer is not proof of which harness made a later commit.

## Procedure

1. **Freeze the present.** Record repo root, branch, worktrees, status, recent commits and relevant untracked files. Do not clean, stash or checkout. The best continuation point may exist only in dirty files. Done when the snapshot is saved.
2. **Search history with high-signal anchors**, in this order: exact repo path or distinctive path segment; commit SHA or subject; unique symbol, file or test name; distinctive user phrase; harness or model names last. Use search only to get an exact session id, then read that session. Done when you have a session id or have exhausted all five anchor types.
3. **Do not trust truncated output.** A search whose result was compacted or elided is not evidence for the missing detail. Rerun it narrower. Keep exact ids, paths and timestamps so the investigation survives your own context compaction.
4. **Rebuild the session tree.** For the root and each child or delegated session: harness, model and provider, starting directory, parent id, tool calls that actually wrote files, ran agents, committed or verified, and how it ended. Classify agent use from real invocations, not prose mentions.
5. **Correlate with Git.** Use commit times, reflog, worktrees and dirty paths. Separate commits made by the session, imported donor history, repos only read as references, and files written after the last commit. Attribute a dirty file to the session only when a logged write, patch or hash proves it.
6. **Resolve "last" and "running" carefully.**
   - Rank by message and tool timestamps, not session end time. One shutdown can stamp many old sessions at once.
   - Report the literal newest record and the newest substantive human-directed task separately. Collapse automated runs and child sessions into their root.
   - When "last session" is ambiguous across surfaces (CLI, desktop, chat apps), report both the newest across all surfaces and the newest interrupted one on the current surface.
   - A resumable session row or an unset end time is not execution. Confirm a live process, worker heartbeat or new artifacts before saying "running".
   - Repeated automatic retries that fail before any tool call are churn, not progress. Stop them through the task system's normal block mechanism and record the failure.
7. **Check store freshness.** For every history store used, record its newest timestamp. A mirror or "global" ledger can stop ingesting while the native store continues. State which stores were not inspected.
8. **Look outside chat history** when the user says context lives in product docs, task boards or branch inventories. Read those inventories first, then open only matching worktrees. Separate authoritative stores (task files, databases, briefs) from projections (dashboards, canvases).
9. **Write a continuation brief** with: original goal and constraints, key decisions, verified commits and gates, files changed since the last commit, the last successful action and the interruption point, pending tasks, blockers, and the session link or log path. Label each line confirmed, inferred or unknown.
10. **Reconcile before resuming.** Re-read every relevant file and rerun status and tests before editing. Do not replay stale patches. Keep inherited uncommitted code: add characterization tests for it rather than deleting it to get a clean start.

## Working Alongside Other Sessions

- Inspect user-owned sessions and processes only enough to judge collision risk. Do not focus, resume, kill or reconfigure them unless asked.
- If the user wants work added to a session they own, use that harness's queue or append mechanism against the root session, not a child. Treat "queued" as queued, not read. See the adapter reference.
- If you can finish a bounded task with your own tools, do it in a non-overlapping worktree instead of blocking on an unavailable helper harness.
- If the user wants work on a specific checkout (for example "stay on main"), honor it. Isolation on another branch is a temporary integration lane, not a new product line.

## Pitfalls

- Searching by folder name only. Generated titles are generic and sessions touch many repos.
- Treating a search snippet as the whole log.
- Inferring harness from commit trailers or code style.
- Assuming the inspected sibling repo was the starting directory.
- Calling a session-derived status view the real task board. Query the board itself and label any reconstruction.
- Dumping raw transcripts. Extract the brief and redact credentials.
- Importing or copying history into a new memory store by default. Read in place.

## Verification

- [ ] Root session and children identified by exact id.
- [ ] Harness, model and provider, directory and Git authorship reported separately.
- [ ] At least two independent anchors tie the transcript to the repo (for example a commit and a written file).
- [ ] Every store used has a freshness timestamp; uninspected stores are named.
- [ ] Any "running" claim has live process or artifact evidence.
- [ ] The brief names the exact stopping point and the next executable step.
- [ ] Status and baseline tests rerun before the first new edit.

## Credits

Distilled from the author's private recovery notes. Related: pstack by Lauren Tan, MIT, [cursor/plugins](https://github.com/cursor/plugins/tree/main/pstack).
