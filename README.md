# kvnloo-skills

Personal Hermes skills. Install a skill by copying its directory into `~/.hermes/skills/<category>/` or a profile's `skills/` tree.

## Skills

| Skill | Category | Description |
|---|---|---|
| [hyprland-ui-testing](linux-system-admin/hyprland-ui-testing/SKILL.md) | linux-system-admin | Test Hyprland UI without disturbing active workspaces. |
| [abab-meta-research](research/abab-meta-research/SKILL.md) | research | Adaptive A/B/C research loop (strategy, evidence, experiment). |
| [repository-architecture-audits](software-development/repository-architecture-audits/SKILL.md) | software-development | Read-only audits of repo architecture, lineage, reachability and extraction boundaries. |
| [secure-autonomous-experimentation](software-development/secure-autonomous-experimentation/SKILL.md) | software-development | Sandbox and evaluator boundaries for agent-driven optimization loops. |
| [fail-closed-code-review](software-development/fail-closed-code-review/SKILL.md) | software-development | Immutable review bound to a file-hash manifest, with a machine-readable verdict. |
| [coding-session-continuity](software-development/coding-session-continuity/SKILL.md) | software-development | Find, attribute and resume prior coding sessions from live repo state. |
| [comparative-visual-build-audits](software-development/comparative-visual-build-audits/SKILL.md) | software-development | Candidate-vs-prior and candidate-vs-target visual verdicts, plus labels-hidden juries. |
| [multi-agent-release-readiness](software-development/multi-agent-release-readiness/SKILL.md) | software-development | Converge many agents' work into one verified release candidate with a ship call. |

The six `software-development` skills are generalized from the author's private skill notes. They link to [pstack](https://github.com/cursor/plugins/tree/main/pstack) (Lauren Tan, MIT) and [superpowers](https://github.com/obra/superpowers) (MIT) for overlapping basics instead of copying them.

`hyprland-ui-testing` started as [NousResearch/hermes-agent#102382](https://github.com/NousResearch/hermes-agent/pull/102382). This repo is the standalone copy.

## Install one skill

```bash
mkdir -p ~/.hermes/skills/linux-system-admin
git clone --depth 1 https://github.com/kvnloo/kvnloo-skills.git /tmp/kvnloo-skills
cp -a /tmp/kvnloo-skills/linux-system-admin/hyprland-ui-testing ~/.hermes/skills/linux-system-admin/
```

New sessions load it with `skill_view(name='hyprland-ui-testing')`.

## Tests

```bash
pytest tests/ -q
```

## License

MIT. Author: Kevin Rajan (kvnloo).
