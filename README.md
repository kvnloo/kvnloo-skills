# hyprland-ui-testing

Hermes skill: test GTK, Wayland, and TUI apps on Hyprland without mapping onto the user's focused workspace.

Origin: same skill as [NousResearch/hermes-agent#102382](https://github.com/NousResearch/hermes-agent/pull/102382) (`optional-skills/linux-system-admin/hyprland-ui-testing`). This repo is the standalone copy so it can be installed without waiting on that PR.

## Install (Hermes)

```bash
mkdir -p ~/.hermes/skills/linux-system-admin
git clone https://github.com/kvnloo/hyprland-ui-testing.git ~/.hermes/skills/linux-system-admin/hyprland-ui-testing
```

Or copy `SKILL.md` into `~/.hermes/profiles/<profile>/skills/linux-system-admin/hyprland-ui-testing/SKILL.md`.

New sessions pick it up via `skill_view(name='hyprland-ui-testing')`.

## Tests

```bash
pytest tests/ -q
```

No live Hyprland required for contract tests.

## License

MIT. Author: Kevin Rajan (kvnloo).
