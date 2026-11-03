---
name: multi-agent-release-readiness
description: "Use when converging multi-agent work into one release."
author: Kevin Rajan (kvnloo), Hermes Agent
version: 2.0.0
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [release, production-readiness, multi-agent, worktrees, verification]
    category: software-development
    related_skills: [fail-closed-code-review, repository-architecture-audits, coding-session-continuity]
---

# Multi-Agent Release Readiness

Turn a busy repository (many agents, branches, worktrees and loops) into one release candidate with independent evidence and a ship or no-ship call. The rule during a release window is convergence: stop starting unmeasured work, select the best existing work, integrate through one spine, verify independently, park the rest.

This skill grants no authority. Deploying, merging to a protected branch, deleting work and spending budget need explicit approval from the release owner.

## When to Use

- "Get this to production-ready" in a repo with several agents or worktrees in flight.
- A deadline release where many lanes claim to be done.
- Workers keep returning `NOT READY` and re-dispatching the same prompt is not converging.

Don't use for: fanning out new parallel work (pstack [`swarm`](https://github.com/cursor/plugins/tree/main/pstack/skills/swarm)), or ordering a single agent's steps (pstack [`principle-sequence-verifiable-units`](https://github.com/cursor/plugins/tree/main/pstack/skills/principle-sequence-verifiable-units)).

## Outcomes

Exactly one of `SHIP`, `SHIP WITH KNOWN LIMITATIONS`, or `NO-SHIP`. A trusted no-ship beats an unverified release. Agents return `NO-SHIP` rather than weakening a mandatory gate.

## Procedure

1. **Establish live truth.** Check pause or stop controls. Read the authoritative priority and claim stores. Inventory branches, worktrees, owners, active agents, loops and dirty state. Mark which dashboards are projections. Done when every worktree has an owner or "unknown". Never infer readiness from commit count, agent count or a badge.
2. **Write the goal as a contract**: objective and deadline, exact scope, definition of production-ready, mandatory gates, critical user journeys, roles and authority, WIP caps, integration order, non-goals, no-ship conditions, rollback plan, and decisions reserved for the release owner.
3. **Declare the base.** State base ref, resolved commit, visible product state and dirty-state policy. "Do not develop in a dirty tree" means isolate from the chosen base, not swap it for `main`. Capture baseline screenshots or journey results for parity.
4. **Create one clean integration worktree** from that exact commit. `git worktree add` does not change your directory: run the next Git command with `git -C <target>` after asserting root, branch and HEAD. Ignore nested worktree roots in the parent and stage explicit paths; check staged modes for accidental `160000` gitlinks.
5. **Run the red baseline.** Run the canonical gates before admitting more work. Each failure becomes one atomic blocker.
6. **Admit proven value only.** Treat dirty worktrees as donors, not spines. Measure divergence, split changes into coherent slices, cherry-pick clean commits or apply reviewed patches slice by slice, and record provenance. Copy only reviewed untracked source, tests and contracts; leave claim files, caches and build output. Rerun each donor's focused tests on the spine: lane-green is provenance, not candidate-green.
7. **Heal blockers.** One writer per hotspot, atomic claims, independent verification, bounded retries.
8. **Full verification** on the frozen candidate SHA. Leave enough budget to rerun everything after the last change.
9. **Hand off** a short decision pack: candidate SHA, gate results with commands, known limitations, rollback, and the ship recommendation.

## Gates

- **G0 control safety:** stop authority works, no self-certification, no uncontrolled loop writes.
- **G1 convergence:** one candidate branch, one integrator, every worktree marked `merge`, `keep`, `park` or `discard`. Never delete unmerged work to tidy the inventory.
- **G2 build and static:** clean-install production build plus canonical type, lint, schema and unit checks for every component.
- **G3 critical journeys:** automated browser or integration runs of primary paths at supported breakpoints, including blank-screen and fatal-console checks.
- **G4 operational safety:** no P0 security, secret, data-loss or destructive-default risk.
- **G5 truthfulness:** no claims for mocked, unreachable or worktree-only features; measured performance claims only.
- **G6 release evidence:** immutable SHA, commands and results, limitations, rollback and lineage.

## Roles

Planner (ordering, WIP caps, no product code); scouts (read-only); workers (one atomic task in an isolated worktree); verifier (independent evidence; workers never self-certify); integrator (sole writer to the candidate branch); release owner (ship call, destructive operations, deployment). Add workers only when verification and integration can absorb the output.

## Change Control

- **Plan changes.** Before deviating from the agreed base, merge order or preview target: quote the decision, state the deviation and its visible consequence, offer the least-destructive alternative, and wait for approval.
- **Moving base.** A branch name is not a baseline. Record ref and commit at approval. Before each wave, check whether the ref advanced; if so, report old and new commit and the overlap, and ask whether the contract means the pinned commit or the new head.
- **Checkpoints.** Commit after each verified slice and before handing a tree to another agent. No catch-all commits, no empty commits to satisfy a clean-revision gate. If no checkpoint was made, say so.

## Previews and Servers

- Never point a reviewer at a worktree agents are still editing. Hot reload will change the page under them. Serve from a frozen revision and show its SHA and dirty fingerprint.
- Exercise the exact action you want reviewed before sharing the link.
- A fixed port can already be held by a healthy server from the wrong worktree. Before trusting it, resolve the listener PID, command and working directory, and compare the served entry-asset hash with the candidate build. Stop a listener only after identifying its owner.
- If a functional run passes from a dirty tree but the clean-revision gate fails, report functional evidence and keep the gate red.

## Closure-Loop Breaker

After the first incomplete "finish and verify everything" pass, stop re-sending the same prompt:

1. Turn every remaining item into a gate row: exact command, expected evidence, owner, and whether code may change.
2. Separate repair (owns one red gate) from verification (no feature changes).
3. Run cheap deterministic gates first.
4. After two incomplete passes on one lane, the integrator runs the remaining gates directly, splits them, or reports the concrete blocker.
5. Count unresolved gates and unverified changed files, not finished workers.
6. If an approval policy blocks a verifier, do not change product code to satisfy it. Report the boundary.

Within a single run: get the canonical toolchain working before broad edits, finish vertical slices (test, code, integration, focused test, typecheck), reserve the last quarter of the budget for proof, and freeze expansion at the first budget warning.

## Progress Ladder

Report each layer separately: designed, dispatched, implemented in a lane, lane-verified, integrated, candidate-verified, previewable (with URL and contents), committed or promoted. Lead with the integration worktree's real state. "Implemented but not typechecked" is never "integration-ready".

## Pitfalls

- Creating another queue or control plane during a release window.
- Spawning more variants while unverified inventory grows.
- Calling builds green while core journeys are untested.
- Reporting fixture-driven browser runs as live API evidence. Assert nonzero fixture counts; a loop over zero rows is not a pass.
- Treating the last CSS edit as harmless. Rerun visual journeys after it.
- Quoted and unquoted YAML timestamps parse as different types. Compare parsed values when editing work-graph metadata.

## Verification

- [ ] Candidate SHA frozen; every mandatory gate rerun on it with commands recorded.
- [ ] Every worktree has a disposition; no unmerged work deleted.
- [ ] Each admitted slice has provenance and was retested on the spine.
- [ ] Verdict is one of the three outcomes, with rollback and limitations.

## Credits

Distilled from the author's private release notes. Related: pstack by Lauren Tan, MIT, [cursor/plugins](https://github.com/cursor/plugins/tree/main/pstack); [obra/superpowers](https://github.com/obra/superpowers) (MIT) for worktree and verification basics.
