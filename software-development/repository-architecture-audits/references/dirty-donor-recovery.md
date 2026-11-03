# Dirty donor recovery before extraction

Use this when the code you want to extract lives partly in dirty worktrees, staged changes or untracked files. Preserve it first, then extract from the preserved copy. Never extract by checking out or rewriting a donor worktree.

## Inventory and cache identity

For each entry in `git worktree list --porcelain`, record path, branch or detached state, full HEAD, `git status --porcelain=v1 -z --untracked-files=all`, and tracked and untracked paths.

Key cached analysis by content, not by branch name:

```text
object_fingerprint = hash(HEAD + dirty_fingerprint + classifier_version)
dirty_fingerprint  = hash(porcelain records
                          + git diff --binary HEAD
                          + path/size/mtime of every untracked file
                          + content hash of extraction-relevant untracked files)
```

Plain porcelain groups untracked directories into one line. Use `--untracked-files=all` when recovery must be exact.

## Recovery package

Write it outside both the donor and the target repository:

```text
manifest.json
git/all-refs.bundle
donors/<slug>/manifest.json
donors/<slug>/tracked.patch       # git diff --binary --full-index HEAD -- .
donors/<slug>/untracked.tar.gz
```

For each selected donor:

1. Recompute HEAD and the dirty fingerprint and compare them with the inventory. Stop on mismatch.
2. Capture tracked and staged changes together with `git diff --binary --full-index HEAD -- .`.
3. Archive untracked files individually. Reject absolute paths, `..`, cache and build trees, and credential-shaped paths (`.env`, private keys, token stores).
4. Record SHA-256, size, mode and kind for every payload, plus every skipped entry and why.

`git bundle create all-refs.bundle --all` followed by `git bundle verify` preserves committed reachability. Prove each selected donor HEAD appears among the bundle's advertised object ids. Registered worktree HEADs can keep detached commits reachable that no branch contains.

## Verify the recovery

"Archive created" is not verification. For every donor, in a fresh temp directory:

1. Make a no-checkout clone of the source repository and check out the recorded HEAD detached.
2. Run `git apply --check tracked.patch`. `--numstat` only proves the patch parses.
3. Open the untracked tarball without extracting it. Reject unsafe member paths and compare names and hashes with the manifest.
4. Confirm the HEAD is in the verified bundle.
5. Recompute the source repository's status hash and compare it with the pre-recovery baseline.

If cleanup of a temp path is denied, report the exact remaining path.

## Filtered history

1. Create a temporary bare repository and fetch selected donor refs from the bundle under stable names.
2. Compute the target entrypoints' transitive local-import closure.
3. Run `git filter-repo --refs ... --path ...` on only those refs and paths. Check that every selected ref survived and that no unrelated product leaked in.
4. Fetch the filtered refs into the new repository under an archive namespace such as `refs/archive/source/*`. Keep the working branch empty until scope is locked.

Dirty payloads have no commit history. Port them as small target-side commits whose messages or provenance files record donor worktree, source HEAD, dirty fingerprint, source path and adaptation notes.

## Extraction order that holds up

1. Lock a capability ledger: visible routes, hidden or conditional routes, accepted, deferred and rejected features, backend ownership and acceptance evidence.
2. Port pure domain and navigation models test-first.
3. Build a fixture-only shell that proves routing and layout.
4. Scan for forbidden coupling: monorepo paths, local state directories, filesystem or process imports, old dev-server endpoints.
5. Define browser-safe backend contracts, then migrate one vertical slice at a time against the real backend.
6. When touch, pen, voice or viewport behavior is in scope, test on the real target device. Browser unit tests do not cover it.
