---
name: secure-autonomous-experimentation
description: "Use when agents optimize code against automated evaluators."
author: Kevin Rajan (kvnloo), Hermes Agent
version: 2.0.0
license: MIT
platforms: [linux, macos]
metadata:
  hermes:
    tags: [agents, sandboxing, evaluation, autoresearch, security, benchmarks]
    category: software-development
    related_skills: [fail-closed-code-review, multi-agent-release-readiness]
---

# Secure Autonomous Experimentation

Build and review loops where an untrusted proposal agent edits code and an external evaluator decides KEEP or REVERT. Proposal execution, benchmark machinery, baseline state, Git metadata and process lifetime are separate security boundaries. The candidate must never be able to grade itself.

This skill covers the safety boundary. It is not a training-loop recipe and it grants no authority on its own: spending, unattended runs, publication and merge each need explicit approval from whoever owns the repository and budget.

## When to Use

- Autoresearch-style loops (for example [karpathy/autoresearch](https://github.com/karpathy/autoresearch)) or overnight optimization runs.
- Agents proposing performance, visual, model or algorithm changes that an automated gate accepts.
- Tournaments across branches or worktrees with automated acceptance.
- Reviewing an existing loop for ways a proposal could game or corrupt it.

Don't use for: one-off benchmark hygiene (pstack [`benchmark-checklist`](https://github.com/cursor/plugins/tree/main/pstack/skills/benchmark-checklist)), or picking among N human-reviewed candidates (pstack [`arena`](https://github.com/cursor/plugins/tree/main/pstack/skills/arena)).

## Architecture

1. **Separate control state from experiment state.** Each objective gets its own branch, worktree, baseline, history, budget, evaluator and editable-path allowlist.
2. **Commit the control plane first.** Create experiment worktrees only from a committed revision that already contains the orchestrator and evaluator.
3. **Run proposals in a disposable clone.** Never expose the real worktree or shared `.git` as writable. On Linux, Bubblewrap with a read-only root and the disposable clone bind-mounted at the expected path works. Other OSes need an equivalent container or VM.
4. **Contain the whole process tree.** Process-group kills miss `setsid` descendants. Use a private PID namespace (`bwrap --unshare-pid`) or a container, and prove a detached delayed writer dies before import.
5. **Import files, not Git state.** After the proposal exits, require that the sandbox HEAD, branch and index did not change. Enumerate regular files yourself, reject symlinks and policy files, and copy only allowlisted deltas into the real worktree.
6. **Evaluate outside the candidate's write scope and fail closed.** Missing, malformed, stale, foreign or wrong-case evidence rejects the candidate.
7. **Re-baseline every run.** A restarted loop compares against the current accepted tip, not a remembered best score.

## Baseline and Git Integrity

- Store baselines outside candidate-writable paths. An ignored `runs/` directory inside the repo is still writable by the proposal.
- Bind each baseline to repository common-dir, loop id, expected branch and exact HEAD. Hash the bytes before and after untrusted execution.
- `git status` misses ignored files, other refs, hooks, config and index flags such as skip-worktree. Fingerprints built with `--exclude-standard` miss ignored injection.
- Check new paths against the real repository's ignore policy (`git check-ignore --no-index`), never the sandbox's mutable `.gitignore` or `info/exclude`.
- Reject edits to `.gitignore`, `.gitattributes`, `.gitmodules`, evaluator code, benchmark and score definitions, preset routing, profiling and capture code.
- Git only preserves the executable bit. Comparing full permission bits across clones produces false deltas.

## Benchmark Integrity

- Freeze the benchmark identity: case names, full scene or input definitions, setup-function source, dimensions, presets and seeds. Record metadata from trusted tooling, not from candidate output.
- Re-check protected paths and the repo fingerprint after the evaluator or judge runs. A tool-capable judge can write too.
- When a registry of cases can grow, pass the frozen subset explicitly and reject missing cases. Enforce the frozen set for every measured preset, not only their union.
- Pair hard guard metrics with the target metric when objectives conflict. Missing guard evidence fails.
- Source scans for gaming (for example code that branches on "am I being benchmarked") are defense in depth, not a sandbox. Reject environment-conditioned behavior but accept ordinary unconditioned APIs. Pair every rejection rule with a benign acceptance test.
- For browser frame-rate claims, keep raw samples, prove a real GPU and the actual drawing-buffer size, and require a physical-machine baseline plus an independent rerun.
- For stateful ML servers, separate cold load, compile warm-up, resident execution and cache hits, and hash decoded outputs.

## Process and Host Safety

- Wrap proposal, judge, browser and server trees in explicit timeouts. The outer timeout covers every inner allowance plus cleanup.
- Refuse to reuse an occupied or unowned benchmark port. Clear inherited URL and server override variables.
- Kill the full namespace on timeout, signal, readiness failure and normal exit, before inspecting files.
- Treat unrelated host load as an integrity problem. Require several quiet CPU and GPU samples before measuring, monitor during measurement, and invalidate contaminated runs. Kernel reclaim threads such as `kswapd` are pressure signals, not processes to pause. Gate on `/proc/pressure/{memory,io}` where available.
- If you pause competing workloads, prefer cgroup-v2 freezing over `SIGSTOP`, record prior state, and thaw only what you froze. Acquire the recovery journal atomically with owner PID and start time so a second evaluator cannot thaw the first one's workloads.
- Isolate only the measurement windows. Do not hold the machine exclusive while the proposal agent is thinking.

## Required Adversarial Tests

Check these into the repository. One-off shell probes do not count.

- Benign allowlisted edit imports; protected-path edit is rejected.
- Proposal commit, staging or branch change is rejected.
- Ignored-file injection is rejected, including skip-worktree plus an altered sandbox ignore file.
- Symlink in the candidate tree is rejected.
- Baseline tampering in the sandbox cannot touch the real baseline.
- A detached `setsid` child that writes after a delay cannot race the import.
- Benchmark-conditioned code is rejected; the same API used unconditionally is accepted.
- Malformed, stale or foreign evaluator output is rejected.
- A stale or unowned server on the benchmark port is rejected.
- Missing or noisy host telemetry rejects before measurement.

## Procedure

1. Write the threat model: what the proposal can write, run and observe. Done when every boundary above maps to a mechanism.
2. Build the sandbox and import path, then the adversarial tests. Done when every test above passes and the benign case still imports.
3. Run a canary: branch from a coherent committed product revision, baseline one objective, and run one bounded trial to a KEEP or REVERT. Done when the decision and its evidence are on disk.
4. Get explicit approval for the run budget before enabling longer loops.
5. After every hardening edit, re-run all gates. Turn each reviewer-found exploit into a permanent test.

## Pitfalls

- Async exit callbacks can let a Node orchestrator exit before validation finishes. Await child completion and validation at top level.
- Banning every use of `performance`, `window` or timers makes legitimate proposals impossible. Detect conditioned use instead.
- Cloning the sandbox into the source repo's `.git/` interferes with private state. Use a separate temp directory.
- A quiet preflight without continuous monitoring misses load that starts mid-run.

## Verification

- [ ] All adversarial tests pass in CI or a recorded local run.
- [ ] Canary trial produced one KEEP or REVERT with evidence bound to the exact HEAD.
- [ ] No candidate-writable path holds baselines, evaluator code or scores.
- [ ] Budget and unattended-run approval recorded before the loop runs unattended.

## Credits

Distilled from the author's private hardening notes on an autoresearch loop. Inspired by [karpathy/autoresearch](https://github.com/karpathy/autoresearch) (no license declared; referenced, not copied).
