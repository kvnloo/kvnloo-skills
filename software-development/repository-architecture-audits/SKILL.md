---
name: repository-architecture-audits
description: "Use when auditing repo architecture, lineage or donors."
version: 2.0.0
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [architecture, git, lineage, extraction, audit, worktrees]
    category: software-development
    related_skills: [coding-session-continuity, multi-agent-release-readiness]
---

# Repository Architecture Audits

Read-only, evidence-backed audits of repository architecture, feature lineage, API boundaries, extraction seams and multi-worktree donor sets. The output is a report that separates what Git objects prove from what the working tree shows and from what you infer. The audit changes nothing unless the caller grants write scope.

## When to Use

- "Which branch or worktree has the real version of feature X?"
- Planning to extract an app, package or feature into its own repository.
- Several branches, worktrees or agents touched the same product and you need the canonical root.
- Docs claim a subsystem (workers, lanes, plugins, presets) exists and you need to know whether production reaches it.
- Choosing which of several overlapping systems should own a concern.

Don't use for: a quick "how does this function work" walkthrough (use pstack [`how`](https://github.com/cursor/plugins/tree/main/pstack/skills/how)), or "what will this change break" (pstack [`blast-radius`](https://github.com/cursor/plugins/tree/main/pstack/skills/blast-radius)).

## Core Rule: Committed Evidence Is Not Working-Tree Evidence

When the question is about committed architecture, treat the index and working tree as untrusted. When the caller wants worktree-only work preserved, treat dirty and untracked state as a separate evidence class, fingerprint it, and recover it before use.

- Read committed files with `git show <ref>:<path>` and enumerate with `git ls-tree -r --name-only <ref>`.
- `git log --all --follow -- <path>` finds history across refs. It does not prove ancestry.
- Prove ancestry with `git merge-base --is-ancestor`, `git merge-base` and `git branch -a --contains <sha>`.
- Several feature refs can point at one commit. Say so instead of inventing separate lineages.
- A branch name or commit subject is a clue. Changed paths and object contents are proof.
- For many refs or files, write a small script around Git plumbing so the evidence is reproducible.

## Procedure

1. **Freeze the starting state.** Record `git status --short --branch`, HEAD, local and remote refs and `git worktree list --porcelain`. Do not clean, stash, checkout or fetch without permission. Done when the snapshot is saved in your notes.
2. **Read the rules.** Read repository instruction files (`AGENTS.md`, `CLAUDE.md`, `CONTRIBUTING.md`, org docs). Note archived roots and declared sources of truth. Done when every instruction file found is listed.
3. **Keep read-only honest.** Package managers and test runners write caches, virtualenvs, bytecode and generated manifests that `git status` hides. If execution is required, run it in a disposable clone or temp worktree. Statically inspect any `measure`, `smoke` or `test` command for writes before running it. Done when each skipped or isolated command has a stated reason.
4. **Inventory app roots across refs.** Find `package.json`, lockfiles, framework configs, HTML/JS entrypoints, static dashboards and archived ancestors. For each root, record the entry chain: route or HTML, module entry, mounted root component, build config input. Done when every candidate root has a chain or a reason it is not an app.
5. **Map tooling and contracts.** Record build and test commands, runtime versions, offline versus live tests, and whether live tests skip silently. Inventory routes, browser APIs, API clients, schemas and dev-server proxy plugins. A dev-server plugin that touches files, Git or processes is backend code, not frontend.
6. **Check reachability, not declaration.** For every claimed subsystem, search production code for constructors and imports. A tested module with no production caller is a prototype. Check release allowlists and packaging metadata: exclusion from the shipped artifact outranks README prose. A status present in a schema but with no supported writer is dormant.
7. **Find the critical path.** Reconstruct the product transaction from the mission or definition of done. Mark each link `reachable`, `stub`, `documented-only` or `unmeasured`. The first non-reachable link is the boundary. Hardening fixtures or reports past that boundary is not forward progress.
8. **Trace lifecycle state end to end** when a feature reacts to completion, failure or review. Keep these layers separate: authoritative workflow state, immutable occurrence identity (event or revision id), delivery cursors, presentation receipts (seen, dismissed, snoozed) and transport. A delivery cursor is not a read receipt. Key repeatable attention items by occurrence, not only by entity id.
9. **Decide authority before extraction** when several systems overlap. Give each one role: authority, executor, projection or donor. Build a concern-by-concern authority matrix (tasks, runs, approvals, workspaces, telemetry). Reject duplicate ledgers. Give every donor family a decision: `COPY`, `REIMPLEMENT`, `EVIDENCE_ONLY` or `DO_NOT_COPY`. An absent license grants no redistribution right.
10. **Compute the extraction boundary.** From each target entrypoint, take the transitive local-import closure. Sort files into: source to extract, shared deps to vendor or publish, tests and schemas to keep, server code to leave behind, monorepo state imports to replace with configured contracts, and unrelated roots to exclude. File counts are sizing evidence, not architecture proof.
11. **Preserve dirty donors before copying.** See [references/dirty-donor-recovery.md](references/dirty-donor-recovery.md). Done when every selected donor has a verified patch, untracked archive and manifest.
12. **Verify non-mutation.** Re-read status and HEAD for every repository you touched. If other agents moved state during the audit, report the final observed state and say the changes were observed, not authored.

## Large Donor Sets

When one pass cannot cover the universe, freeze a timestamped manifest first, then run two independent paths: a deterministic census (refs, unique tips, worktrees, dirty paths) and read-only reviewers assigned explicit, non-overlapping members from that frozen manifest. Never let each reviewer recompute its own live shard. Validate novelty with tip deltas and blob identities, not keyword counts. Ingest reports as they finish so a session limit cannot strand evidence.

## Report Shape

Lead with the canonical app root, the best evidence ref and full SHA, whether it is integrated or divergent, and the recommended extraction boundary. Then cover tooling, surfaces, contracts, lineage, exclusions and what was not inspected. Label every claim as observed in Git objects, observed in the working tree, or inferred.

## Pitfalls

- Using current file content as committed evidence when the tree is dirty.
- Calling an open or draft PR shipped because its description diagnoses the gap. Check ancestry and release tags.
- Inferring state transitions from a screenshot. A visible `Done` label proves layout, not the trigger or persistence.
- Treating a healthy endpoint as provenance. Identify the listener process, its working directory and served revision.
- Copying a whole product app when one entry and its import closure are enough.
- Collecting every file and running out of budget before writing the report. Draft findings as you go.

## Verification

- [ ] Starting and final status, HEAD and worktree list recorded for every repository.
- [ ] Every ancestry claim backed by `merge-base` or `--contains`, not by `log --all`.
- [ ] Every "exists" claim backed by a production caller or packaging entry.
- [ ] Extraction boundary lists files in all six categories.
- [ ] No repository was modified, or each modification is listed with its authorization.

## Credits

Method distilled from the author's private audit notes and rewritten for public use. Related public skills: pstack by Lauren Tan, MIT, [cursor/plugins](https://github.com/cursor/plugins/tree/main/pstack).
