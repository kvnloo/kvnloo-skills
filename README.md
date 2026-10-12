# kvnloo-skills

Kevin's shared skills for Claude Code, Codex, Hermes profiles `clean` and `chiefstaff`, and other agents that read `~/.agents/skills`. One checkout holds the public skills. The installer makes absolute links to skill directories and keeps a journal of every displaced path. It uses Python 3.11+ and the standard library, with no network calls.

## Install

From this checkout:

```sh
python3 install.py --apply
```

Review first with `python3 install.py --plan`. Limit either command with `--harness claude`, `codex`, `hermes-clean`, `hermes-chiefstaff`, or `agents`. Installation needs no harness settings changes. A fresh checkout contains only the two existing public skills; absent external sources are reported as `UNAVAILABLE` and skipped.

| Harness | Default skill directory |
| --- | --- |
| Claude Code | `~/.claude-home/skills` |
| Codex and agents | `~/.agents/skills` |
| Hermes clean | `~/.hermes/profiles/clean/skills` |
| Hermes chiefstaff | `~/.hermes/profiles/chiefstaff/skills` |

Codex and agents are two names for the same destination, so a full apply creates each physical link once. The plan reports each harness separately and gives unique totals. Nothing is added to the legacy `.codex/skills` directory. Existing duplicates there remain for the later migration step.

The installer reads `CLAUDE_CONFIG_DIR` and `HERMES_HOME` environment overrides without reading config files. `HOME` sets the home directory; an explicit `--home /tmp/skills-test-home` also ignores those harness overrides so tests cannot reach real directories. Hermes categorized skills keep their existing path and bare name. Duplicate paths for one Hermes name are reported as an error. The installer leaves `.usage.json` and curator archives untouched.

### Packs and private skills

Only `default` installs automatically. Add packs with repeated flags:

```sh
python3 install.py --plan --pack desktop --pack creative
python3 install.py --apply --pack pstack
```

Available packs are `desktop`, `creative`, `personal`, `workstation`, `design`, `video`, `z0`, and `pstack`. A pack selects manifest entries; it does not fetch dependencies. `hyprland-ui-testing` stays in the flat tree but belongs to `desktop`. Its procedure has Hyprland assumptions. The maintained local focus-safety reference has a stricter Sway-only procedure; review which policy applies before using GUI skills.

The private overlay is a local directory, `~/.local/share/kvnloo-skills-private/skills/<name>/SKILL.md`. Include it explicitly with `--private`. It is never copied into this repository. Name collisions with the public manifest are refused. Omit the flag for credential-free cloud use.

## Manifest schema

`stack.toml` is TOML read by `tomllib`. It has `schema_version = 1` and these tables:

| Table | Fields | Meaning |
| --- | --- | --- |
| `[harnesses.<name>]` | `directory` | A home-relative discovery directory. All five harness names are required. |
| `[skills.<name>]` | `source`, `harnesses`, `pack`, optional `reason`, `upstream` | One skill, destination selection, pack and provenance explanation. |
| `[sources.<id>]` | `repository`, `commit`, `checkout` | A public repository URL, full 40-character commit and local checkout location. |
| `[tools.<name>]` | `version`, `check`, `install` | Human-readable dependency plan. Commands are printed, never executed. |

Skill sources have three forms:

```toml
[skills.example]
source = "skills/example"
harnesses = ["claude", "codex", "agents", "hermes-clean", "hermes-chiefstaff"]
pack = "default"
```

- `skills/example` links a directory within this repository.
- `git:source-id:skills/example` links a clean checkout of `[sources.source-id]` at its exact commit. Prepare that checkout at the declared location yourself. Dirty, missing or mismatched checkouts are reported and skipped; the installer never fetches or resets them.
- `local:~/.agents/skills/example` links an existing machine skill. This is deliberately unpinned. Ownership and provenance remain unresolved unless its `reason` says otherwise. A source already at its destination is kept in place and never linked to itself. Existing links resolving to the desired source are also kept without claiming ownership.

External skills stay outside the public tree. Available pins come from the offline inventory and repository map; they do not prove that loose copies match upstream. [Source decisions](docs/REFERENCES.md) lists every selected skill and explains exclusions and missing pins. The two public skills are [abab-meta-research](skills/abab-meta-research/SKILL.md) and [hyprland-ui-testing](skills/hyprland-ui-testing/SKILL.md). The compatibility link at `research/abab-meta-research` remains for existing consumers.

`python3 install.py --tools` prints the tool plan, including qmd's stable npm prefix, fff's runtime dependency, ctx, agent-reach, agentsview, Jev, no-mistakes, gh, jq, rg, ffmpeg and auxiliary dependencies. It executes no checks or installs. OS-package versions and unavailable source pins are explicitly unresolved; no version is invented.

## Add a skill

1. Establish authorship and permission to publish. Hermes agent-written skills do not graduate in this migration.
2. Put public-safe content in `skills/<name>/SKILL.md`, with matching `name` and a concise `description`. Keep any helper scripts and references inside that directory.
3. Add `[skills.<name>]` to `stack.toml`, with its source, harnesses and pack. Reference third-party and product-owned skills rather than copying them.
4. Run the tests and public-safety check, then review `--plan`.

## Undo and status

```sh
python3 install.py --status
python3 install.py --uninstall
```

Uninstall also accepts `--harness`. It restores original paths recorded in `~/.local/state/kvnloo-skills/links.json` and each `backup-<date>/manifest.json`. Real folders, ordinary files and foreign symlinks move into `backup-<date>/originals/` before replacement. Uninstall moves managed links into `removed-links/` and moves the originals back. Original bytes, permissions and internal symlinks survive. No displaced object is deleted. State files are atomically rewritten; empty directories created by installation remain.

A second apply is a no-op. Managed targets changed by the user are refused rather than replaced. Restore conflicts and missing original backups are errors. Do not edit or remove the backup manifests; keep them until you no longer need undo. Moving the checkout or changing a managed source requires uninstalling its existing links first.

## Public safety and tests

```sh
python3 -m unittest discover -s tests -v
python3 scripts/check-public-safe
```

The check scans every tracked working-tree file, filename and symlink target, including its own script and tests. It rejects machine paths, emails, private host suffixes, IP addresses, common token formats, private keys and private skill names. It reports locations and categories without printing matches. Symlinks outside the repo are rejected without reading their contents.

Copy `.public-safe-patterns.example` to the gitignored `.public-safe-patterns.local` and replace the placeholders with private repository names, hostnames and other local identifiers, one literal per line. The local file is never scanned as content; tracking it causes failure. Generic checks run in CI; machine-specific checks require that local file. The checker is a publication guard, not proof that every possible secret format is detected. It checks the current tracked tree, not Git history or credentials.

Tests use temporary fake homes and repositories. CI runs the stdlib suite, public check and a fake-home plan on Python 3.11 and 3.13. The existing assertion-based skill tests are included in the unittest runner.

## Defaults Kevin can change

- One flat `skills/<name>` layout with the research compatibility link.
- Local directory for the private overlay, with explicit opt-in.
- Skills directories only; no settings, config, marketplace registration or plugins changed.
- Pstack is opt-in. There is no auto-update timer.
- Unestablished authorship stays a local reference. Tool and product skills stay with their owners.
- Hermes skills keep their names, counters and lifecycle. No agent-written skills graduate.
- Source checkouts and tools require separate preparation. No network activity or executable tool installs occur here.

Live harness loading, legacy duplicate removal, second-machine installation, product PRs, registry changes, Boat trials and graduation remain later steps. This repository's tests verify filesystem behavior; they do not claim any harness has loaded the migrated skills.

## License

MIT. Author: Kevin Rajan (kvnloo). Referenced outside skills keep their own licenses.
