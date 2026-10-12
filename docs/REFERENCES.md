# Source decisions

The machine inventory selects these skills. A local reference preserves the source in place and does not establish ownership or a commit pin. Paths in the manifest use portable home-relative discovery directories. No Hermes agent-written skill graduates.

| Skill | Classification | Reason |
| --- | --- | --- |
| `abab-meta-research` | In repo | Existing public collection skill. |
| `hyprland-ui-testing` | In repo | Existing public skill; compositor-specific. |
| `asd-ste100` | Local reference | Authorship is not established; preserve the installed source. |
| `7dps` | Local reference | Owner-added is not authorship evidence; no public import. |
| `fframes-video` | Local reference | Authorship is not established; no public import. |
| `kevin-ste-gitops` | Local reference | Authorship is not established; project-specific history requires review. |
| `focus-safe-desktop-automation` | Local reference | Agent-written; use the maintained Sway-only source without graduation. |
| `sway-only-desktop-automation` | Local reference | Agent-written safety alias; remains local. |
| `qmd` | Local reference | Tool-generated bootstrap; qmd owns its text. |
| `no-mistakes` | Local reference | Third-party source; an installed skill commit was not established. |
| `agentsview-finding-history` | Local reference | Tool-generated; use agentsview skills install for updates. |
| `workspace-copilot` | Local reference | Product-owned; retain its existing link, not a public copy. |
| `comfyui` | Local reference | Hub-installed, differing copies; authorship and pin unresolved. |
| `review-security` | Local reference | Cursor-owned built-in; requires cursor-agent. |
| `review-bugbot` | Local reference | Cursor-owned built-in; requires cursor-agent. |
| `agent-reach` | Pinned outside | Third-party public fork, pinned to the inventoried checkout. |
| `ctx` | Pinned outside | Tool-owned public fork, pinned to the inventoried checkout. |
| `hyperframes` | Pinned outside | Upstream skill; pinned public checkout, opt-in. |
| `hyperframes-animation` | Pinned outside | Upstream skill; pinned public checkout, opt-in. |
| `hyperframes-audio` | Pinned outside | Upstream skill; pinned public checkout, opt-in. |
| `hyperframes-cli` | Pinned outside | Upstream skill; pinned public checkout, opt-in. |
| `hyperframes-core` | Pinned outside | Upstream skill; pinned public checkout, opt-in. |
| `hyperframes-creative` | Pinned outside | Upstream skill; pinned public checkout, opt-in. |
| `hyperframes-keyframes` | Pinned outside | Upstream skill; pinned public checkout, opt-in. |
| `hyperframes-registry` | Pinned outside | Upstream skill; pinned public checkout, opt-in. |
| `media-use` | Pinned outside | Upstream skill; pinned public checkout, opt-in. |
| `general-video` | Pinned outside | Upstream skill; pinned public checkout, opt-in. |
| `motion-graphics` | Pinned outside | Upstream skill; pinned public checkout, opt-in. |
| `product-launch-video` | Pinned outside | Upstream skill; pinned public checkout, opt-in. |
| `jev-browser-use` | Pinned outside | Product-owned Jev skill; pinned checkout, retain bare name. |
| `jev-compaction` | Pinned outside | Product-owned Jev skill; pinned checkout, retain bare name. |
| `jev-computer-use` | Pinned outside | Product-owned Jev skill; pinned checkout, retain bare name. |
| `jev-frontier-work` | Pinned outside | Product-owned Jev skill; pinned checkout, retain bare name. |
| `jev-mailbox` | Pinned outside | Product-owned Jev skill; pinned checkout, retain bare name. |
| `jev-memory` | Pinned outside | Product-owned Jev skill; pinned checkout, retain bare name. |
| `jev-model-routing` | Pinned outside | Product-owned Jev skill; pinned checkout, retain bare name. |
| `jev-setup` | Pinned outside | Product-owned Jev skill; pinned checkout, retain bare name. |
| `jev-skill-select` | Pinned outside | Product-owned Jev skill; pinned checkout, retain bare name. |
| `frontier-kb` | Pinned outside | Product-owned skill; pinned public checkout. |
| `design-taste-frontend` | Local reference | Third-party hub skill; commit provenance was not established. |
| `high-end-visual-design` | Local reference | Third-party hub skill; commit provenance was not established. |
| `minimalist-ui` | Local reference | Third-party hub skill; commit provenance was not established. |
| `redesign-existing-projects` | Local reference | Third-party hub skill; commit provenance was not established. |
| `architect` | Local reference | Third-party or unresolved loose authorship; opt-in pstack reference. |
| `arena` | Local reference | Third-party or unresolved loose authorship; opt-in pstack reference. |
| `automate-me` | Local reference | Third-party or unresolved loose authorship; opt-in pstack reference. |
| `babysit` | Local reference | Third-party or unresolved loose authorship; opt-in pstack reference. |
| `blast-radius` | Local reference | Third-party or unresolved loose authorship; opt-in pstack reference. |
| `bro` | Local reference | Third-party or unresolved loose authorship; opt-in pstack reference. |
| `create-verification-skill` | Local reference | Third-party or unresolved loose authorship; opt-in pstack reference. |
| `deslop` | Local reference | Third-party or unresolved loose authorship; opt-in pstack reference. |
| `figure-it-out` | Local reference | Third-party or unresolved loose authorship; opt-in pstack reference. |
| `fix-ci` | Local reference | Third-party or unresolved loose authorship; opt-in pstack reference. |
| `fix-merge-conflicts` | Local reference | Third-party or unresolved loose authorship; opt-in pstack reference. |
| `get-pr-comments` | Local reference | Third-party or unresolved loose authorship; opt-in pstack reference. |
| `how` | Local reference | Third-party or unresolved loose authorship; opt-in pstack reference. |
| `interrogate` | Local reference | Third-party or unresolved loose authorship; opt-in pstack reference. |
| `maintain-verification-skill` | Local reference | Third-party or unresolved loose authorship; opt-in pstack reference. |
| `make-pr-easy-to-review` | Local reference | Third-party or unresolved loose authorship; opt-in pstack reference. |
| `no-comments` | Local reference | Third-party or unresolved loose authorship; opt-in pstack reference. |
| `poteto-mode` | Local reference | Third-party or unresolved loose authorship; opt-in pstack reference. |
| `principle-boundary-discipline` | Local reference | Third-party or unresolved loose authorship; opt-in pstack reference. |
| `principle-build-the-lever` | Local reference | Third-party or unresolved loose authorship; opt-in pstack reference. |
| `principle-encode-lessons-in-structure` | Local reference | Third-party or unresolved loose authorship; opt-in pstack reference. |
| `principle-exhaust-the-design-space` | Local reference | Third-party or unresolved loose authorship; opt-in pstack reference. |
| `principle-experience-first` | Local reference | Third-party or unresolved loose authorship; opt-in pstack reference. |
| `principle-fix-root-causes` | Local reference | Third-party or unresolved loose authorship; opt-in pstack reference. |
| `principle-foundational-thinking` | Local reference | Third-party or unresolved loose authorship; opt-in pstack reference. |
| `principle-guard-the-context-window` | Local reference | Third-party or unresolved loose authorship; opt-in pstack reference. |
| `principle-laziness-protocol` | Local reference | Third-party or unresolved loose authorship; opt-in pstack reference. |
| `principle-make-operations-idempotent` | Local reference | Third-party or unresolved loose authorship; opt-in pstack reference. |
| `principle-migrate-callers-then-delete-legacy-apis` | Local reference | Third-party or unresolved loose authorship; opt-in pstack reference. |
| `principle-minimize-reader-load` | Local reference | Third-party or unresolved loose authorship; opt-in pstack reference. |
| `principle-model-the-domain` | Local reference | Third-party or unresolved loose authorship; opt-in pstack reference. |
| `principle-never-block-on-the-human` | Local reference | Third-party or unresolved loose authorship; opt-in pstack reference. |
| `principle-outcome-oriented-execution` | Local reference | Third-party or unresolved loose authorship; opt-in pstack reference. |
| `principle-prove-it-works` | Local reference | Third-party or unresolved loose authorship; opt-in pstack reference. |
| `principle-redesign-from-first-principles` | Local reference | Third-party or unresolved loose authorship; opt-in pstack reference. |
| `principle-separate-before-serializing-shared-state` | Local reference | Third-party or unresolved loose authorship; opt-in pstack reference. |
| `principle-sequence-verifiable-units` | Local reference | Third-party or unresolved loose authorship; opt-in pstack reference. |
| `principle-subtract-before-you-add` | Local reference | Third-party or unresolved loose authorship; opt-in pstack reference. |
| `principle-type-system-discipline` | Local reference | Third-party or unresolved loose authorship; opt-in pstack reference. |
| `recall` | Local reference | Third-party or unresolved loose authorship; opt-in pstack reference. |
| `reflect` | Local reference | Third-party or unresolved loose authorship; opt-in pstack reference. |
| `setup-pstack` | Local reference | Third-party or unresolved loose authorship; opt-in pstack reference. |
| `show-me-your-work` | Local reference | Third-party or unresolved loose authorship; opt-in pstack reference. |
| `swarm` | Local reference | Third-party or unresolved loose authorship; opt-in pstack reference. |
| `tdd` | Local reference | Third-party or unresolved loose authorship; opt-in pstack reference. |
| `teach` | Local reference | Third-party or unresolved loose authorship; opt-in pstack reference. |
| `technical-writing` | Local reference | Third-party or unresolved loose authorship; opt-in pstack reference. |
| `thermo-nuclear-code-quality-review` | Local reference | Third-party or unresolved loose authorship; opt-in pstack reference. |
| `typescript-best-practices` | Local reference | Third-party or unresolved loose authorship; opt-in pstack reference. |
| `unslop` | Local reference | Third-party or unresolved loose authorship; opt-in pstack reference. |
| `what-did-i-get-done` | Local reference | Third-party or unresolved loose authorship; opt-in pstack reference. |
| `why` | Local reference | Third-party or unresolved loose authorship; opt-in pstack reference. |

| `comfy-debug` | Local reference | Loose creative skill; authorship and commit provenance are not established. |
| `blender-materials` | Local reference | Loose creative skill; authorship and commit provenance are not established. |
| `blender-modeling` | Local reference | Loose creative skill; authorship and commit provenance are not established. |
| `ffmpeg` | Local reference | Loose creative skill; authorship and commit provenance are not established. |
| `tencent-hunyuan3d` | Local reference | Loose creative skill; authorship and commit provenance are not established. |

## Excluded from this migration

Hermes bundled skills and agent-written project skills keep their existing lifecycle. Backup-only and archived skills are not reinstalled. Account-synced, plugin-managed, system skills and Cursor built-ins beyond the two requested review references remain harness-owned. The loose skill-doctor is deferred as recommended. Product adapters and marketplace-only product skills stay with their products; this installer does not edit settings or enable plugins.

Commit pins come from the offline inventory and repository map. Local copies may differ from those commits. The installer requires clean pinned checkouts in the declared source directories, reports absent or drifting checkouts, and fetches nothing. Pins for no-mistakes, the four design skills and the pstack family could not be established offline.
