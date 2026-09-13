# kvnloo-skills

Personal Hermes skills. Install a skill by copying its directory into `~/.hermes/skills/<category>/` or a profile's `skills/` tree.

## Skills

| Skill | Category | Description |
|---|---|---|
| [hyprland-ui-testing](linux-system-admin/hyprland-ui-testing/SKILL.md) | linux-system-admin | Test Hyprland UI without disturbing active workspaces. |

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
