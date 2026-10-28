# kvnloo-skills

Personal Hermes skills. Install a skill by copying its directory into `~/.hermes/skills/<category>/` or a profile's `skills/` tree.

## Skills

| Skill | Category | Description |
|---|---|---|
| [hyprland-ui-testing](linux-system-admin/hyprland-ui-testing/SKILL.md) | linux-system-admin | Test Hyprland UI without disturbing active workspaces. |
| [abab-meta-research](research/abab-meta-research/SKILL.md) | research | Adaptive A/B/C research loop (strategy, evidence, experiment). |
| [phone-driving](device-automation/phone-driving/SKILL.md) | device-automation | Drive worker Android phones safely via uiautomator2 (locks, owner checks, redaction, install/IME/settings guard). |

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

The `phone-driving` tests also need uiautomator2 for the guard checks (they skip what they cannot run):

```bash
uv run --no-project --with 'uiautomator2>=3.7,<3.8' --with pytest python -m pytest tests/ -q
```

## License

MIT. Author: Kevin Rajan (kvnloo).
