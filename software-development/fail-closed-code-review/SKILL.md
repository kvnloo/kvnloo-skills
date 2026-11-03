---
name: fail-closed-code-review
description: "Use when issuing immutable, machine-readable code verdicts."
version: 2.0.0
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [code-review, fail-closed, immutable, verification, json]
    category: software-development
    related_skills: [secure-autonomous-experimentation, multi-agent-release-readiness]
---

# Fail-Closed Code Review

Produce a final verdict on a change without modifying it. The verdict is bound to a fingerprint of the exact files reviewed, and anything uncertain blocks a pass. The deliverable is a verdict, not a patch.

## When to Use

- The caller asks for a review and says files must not change.
- A gate or pipeline needs a machine-readable pass or fail.
- Other agents may still be writing while you review.
- Reviewing a hosted PR whose branch started from an old base.

Don't use for: reviews that should also fix findings, or multi-model adversarial review (pstack [`interrogate`](https://github.com/cursor/plugins/tree/main/pstack/skills/interrogate)). This skill does not inherit auto-fix or commit steps from any other review skill.

## Invariants

- **Read-only.** No staging, formatting, auto-fix, fixture generation inside the repo, or commands that normally rewrite files. Use check-only formatter modes and disable bytecode and cache writes.
- **Whole change.** Staged, unstaged and untracked files. Plain `git diff` omits untracked files.
- **Fail closed.** A security concern, reproducible logic defect, incomplete scope, unparseable required output or stale evidence blocks a pass.
- **Exact envelope.** If the caller wants JSON only, return one JSON value with no fence and no prose.
- **Tests are evidence, not proof.** Audit lifecycle, ownership and stale async completion separately.
- **Stay in scope.** Keep searches inside the repository under review. Do not widen into home directories, session stores or sibling projects.

## Procedure

1. **Read governing instructions.** Repository and nearest scoped instruction files. Done when listed.
2. **Freeze scope and fingerprint it.**

   ```bash
   git status --short
   git diff HEAD --stat
   git diff HEAD --check
   git ls-files --others --exclude-standard
   # Path-qualified manifest of every changed or untracked file
   { git diff HEAD --name-only -z; git ls-files --others --exclude-standard -z; } |
   while IFS= read -r -d '' f; do
     if [ -e "$f" ] || [ -L "$f" ]; then printf '%s  %s\n' "$(git hash-object -- "$f")" "$f"
     else printf 'DELETED  %s\n' "$f"; fi
   done > "$TMPDIR/review-manifest-1.txt"
   ```

   Save the manifest outside the repo. Status and stat output can stay identical while an untracked file is rewritten, so the manifest is the snapshot identity. Done when HEAD SHA and manifest are recorded.
3. **Hosted PR scope.** Record provider-reported head SHA, base SHA, state and file list, and confirm the remote head yourself. `git diff base..head` can include unrelated commits that landed on base after the merge-base. Review `git diff $(git merge-base base head)..head` and reconcile it with the provider file list.
4. **Read every file in scope.** Tracked diffs file by file; untracked files read directly. Split large diffs rather than truncating.
5. **Trace behavior, not lines.** Reconstruct state ownership and transitions, async operations and their cancellation, resource acquire and release, stale callbacks and identity guards, and error, disable, unmount, retry and re-entry paths. Check whether a flag is used as proof of a stronger fact than it establishes.
6. **Trace derived authority.** For path, credential, permission or capability guards, follow every consumer of the derived value: receipts, markers, logs, cleanup, finalizers, child-process environment, retries. A path validated once can be reused after it changed.
7. **Trace filtered derived state.** When a value filters, deduplicates or clamps rows, freshness, sample count and trust labels must come from the rows that actually contributed. A newer rejected row must not refresh an old valid baseline.
8. **Enumerate state cross-products tests miss**: phase x disable/unmount, before/during/after acquisition, pending response present/absent, old token x replacement token. Prefer a concrete transition trace over speculation.
9. **Run non-mutating checks.** Focused tests first, then typecheck, lint and format-check. Report exact suites and counts. Confirm the runner did not silently ignore a nonexistent test path.
10. **Reproduce cheap exploits.** When a security claim can be shown in a temp directory (symlink input, tampered manifest, caller-controlled key, stale token), run it there and report the trace.
11. **Re-freeze.** Regenerate the manifest as `review-manifest-2.txt` and diff it with the first. If anything changed, re-read those files and rerun affected checks. Repeat until one full pass sees a stable manifest. Re-freeze a hosted PR head the same way.
12. **Emit the verdict** in the caller's schema.

## Verdict Shape

When the caller has no schema, use:

```json
{
  "passed": false,
  "head": "<full sha>",
  "manifest_sha256": "<hash of the final manifest file>",
  "security_concerns": [],
  "logic_errors": ["path:line: defect, preconditions, transition sequence, visible consequence"],
  "suggestions": ["non-blocking improvement"],
  "checks": ["pytest tests/foo.py: 12 passed"],
  "summary": "one grounded sentence"
}
```

Blocking defects go in `logic_errors` or `security_concerns`, never in `suggestions`. Passing checks appear in `checks` and the summary but never override a proven defect.

## Pitfalls

- Reviewing `git diff` only and missing untracked implementation files.
- Treating unchanged `git status` as proof untracked files are unchanged.
- Reusing check output after the tree changed mid-review.
- Treating a stale boolean as resource ownership; assuming an abort clears every related flag.
- Wrapping JSON-only output in a markdown fence.
- Auditing the named operation while side writers (receipts, markers, finalizers) reuse a stale decision.
- Reporting a plausible attack without running the cheap temp-dir reproduction.

## Verification

- [ ] Two manifests captured, compared, and identical for the final pass.
- [ ] Verdict carries the head SHA and final manifest hash.
- [ ] Every blocking item has file:line and a transition trace.
- [ ] `git status` after review matches the first snapshot except for changes made by others, which are named.

## Credits

Distilled from the author's private review notes. For general review practice see [obra/superpowers](https://github.com/obra/superpowers) (MIT) and pstack by Lauren Tan, MIT, [cursor/plugins](https://github.com/cursor/plugins/tree/main/pstack).
