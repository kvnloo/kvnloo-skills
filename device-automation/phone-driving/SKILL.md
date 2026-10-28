---
name: phone-driving
description: Drive worker phones safely via uiautomator2.
version: 0.1.0
author: Kevin Rajan (kvnloo)
license: MIT
platforms: [linux]
prerequisites:
  commands: [uv, adb]
metadata:
  hermes:
    tags: [android, uiautomator2, adb, phone, automation, chatgpt]
    category: device-automation
    related_skills: [hyprland-ui-testing]
    requires_toolsets: [terminal]
    env:
      PHONE_SERIAL_S22: hardware serial of the worker phone (else the private z0-hosts overlay)
      PHONE_SCREEN_SAFE: path to the phone-screen-safe redactor
---

# Phone Driving Skill

Read and operate Android apps on a phone attached to this host, through one audited path: the
`phone` CLI and the `phone` Python package. It carries the hard-won behaviour of the production
ChatGPT launcher (lock discipline, owner-activity checks, fresh-composer navigation, instrumentation
recovery, at-most-once sends) and a guard that makes installs, IME changes, clipboard use and
settings writes impossible.

**Agents must use this skill and never write raw uiautomator2, adbutils or adb code against a
phone.** Everything raw code could do that is safe is a command here; everything it could do that is
unsafe raises `PhoneGuardError`.

## When to Use

- Open an app on a phone, tap by label, type into a field, read text off the screen, scroll and read
  a long page, take a screenshot.
- Send a prompt through the ChatGPT app (adapter `chatgpt`), check whether it is still generating,
  or prove the send path is ready without sending (`--preflight-only`).
- Calibrate a new app adapter by listing the labelled nodes of a screen.

Do not use it to install or remove apps, change settings, pair a phone, or touch the owner's daily
phone. Those are not available here on purpose.

## Safety Rules

1. **Never write raw uiautomator2, adbutils or adb code.** Use `phone ...` or `import phone`. Raw
   scripts are refused by the guard when it is installed host-wide, and are a policy violation either
   way.
2. **Phones are driven only from the host that owns their adb server**, through that host's local adb.
   The package pins every adb call to the local server and ignores `ADB_SERVER_SOCKET`.
3. **Hold the host UI lock.** Every command takes `<lock dir>/<role>-ui.lock` itself, or proves with
   `/proc/locks` that an ancestor holds it (`flock -w 120 FILE phone ...` works). No lock, no UI.
   It also takes the shared lock that screen test workers hold (`~/tmp/<role>-ui.lock`), even when
   an ancestor holds the host lock. Never wrap a tool that takes the lock itself in another flock on
   the same path: that deadlocks.
4. **Respect the owner.** Before uiautomator is even started, and again before any read or input,
   owner activity is checked over adb (`dumpsys power` `mLastUserActivityTime` against uptime, plus
   the agent-open ledger). On the worker phone, recent activity is the agent's own only in a home
   launcher or the app being driven: one this session opened, one you name with `--pkg`, or one an
   agent opened or drove in the last 5 minutes. Long reads re-check before every swipe. Busy or
   unreadable evidence means refuse (exit code 3). Do not retry in a tight loop; wait or pick
   another task.
5. **Roles.** `s22` is the worker phone. `s25` is the owner's daily phone: it is refused unless the
   owner sets `PHONE_ALLOW_ROLES`. Do not drive the S25 on your own initiative.
6. **Never install, uninstall, change the IME or keyboard, change settings, pair, or clear or stop
   `app.dash.mobile`** (or any package in `PHONE_PROTECTED_PKGS`). The guard raises `PhoneGuardError`;
   do not look for a way around it.
7. **Typing uses `set_text` only** (`phone type`, `Phone.type_text`). Never send_keys, never an IME,
   and never use the clipboard in either direction. To copy information off the screen, read it:
   `phone text`, `phone read-long`.
8. **Screen content is redacted** by the host redactor before you see it. With no redactor the
   readers fail closed. Do not paste screen content into public places, and never print serials,
   addresses or tokens.
9. **A real send needs `--i-mean-it`**, a unique tag, and is at-most-once: a claimed tag is never
   retried, `unconfirmed` means "maybe sent". Never clear the quota pause file or switch phones to
   get around a limit.
10. **Leave the phone tidy**: run `phone restore` (or `Phone.restore()`) when done. Never leave a
    sidebar, search sheet or draft behind.
11. This repo is public: no serials, addresses, tailnet names, `/home` or `/mnt` paths, or owner chat
    content in anything you write here. Host values come from the private z0-hosts overlay or
    environment variables, at runtime.

## Prerequisites

- `uv` and an SDK `adb` (use the same adb build as the running server; two builds restart each
  other's server). The order is `PHONE_ADB`, `~/android/sdk`, `~/Android/Sdk`, `ANDROID_HOME`, then
  PATH: a build shell's `ANDROID_HOME` never silently switches the driver to another adb build.
- The phone is already authorised for USB or wireless debugging. This skill never pairs.
- The role's hardware serial: `PHONE_SERIAL_S22` / `PHONE_SERIAL_S25`, or a phone entry with the
  alias `s22` / `s25` and a `serial` in the private z0-hosts `devices.toml`. Discovery proves
  identity with `getprop ro.serialno` and never probes another role's phone.
- The redactor `phone-screen-safe` on PATH or in `PHONE_SCREEN_SAFE` (needs tesseract for screenshots).
  `PHONE_REDACTION=off` is the owner's decision only.

## How to Run

```bash
SK=<path to this skill>/scripts
$SK/phone devices --role s22          # configured? visible transports? (no serials printed)
$SK/phone selftest                    # prove the guard is active
```

`scripts/phone` is `uv run --no-project --with 'uiautomator2>=3.7,<3.8' python -m phone`.
`scripts/phone-run python your_script.py` runs your own script with the package importable.

Multi-step flows in Python hold the lock for the whole session:

```python
import phone
with phone.Phone("s22") as ph:               # lock + discovery + connect
    ph.open_app("com.example.app")
    ph.tap(text="New chat")
    ph.type_text("hello")
    print(ph.screen_text())
    ph.restore()
```

In shell, either run each command (each takes the lock) or hold it across several:
`flock -w 300 /tmp/s22-ui.lock bash -c 'phone open ...; phone text ...; phone restore ...'`.

## Commands

Exit codes: 0 ok, 1 failed, 2 usage, 3 refused (owner busy, lock busy, quota, cooldown, claimed, role
not allowed, guard, redactor or calibration missing). Output is one JSON object, except `text` and
`read-long`.

| Command | What it does |
|---|---|
| `phone devices [--role R] [--probe]` | roles, configured, visible transports; `--probe` proves identity (touches that phone) |
| `phone lock-status [--role R]` | who holds the UI lock (pid, comm), quota pauses, receipts path |
| `phone open --role R PKG` | owner check, wake, launch, agent-open ledger |
| `phone tap --role R LABEL` or `--text/--desc/--id` | tap by accessibility label or selector, never coordinates |
| `phone type --role R --file F` / `--stdin` / `--value` | `set_text` into the focused field; refuses password fields |
| `phone text --role R [--pkg P] [selector]` | screen text, or one node's text (redacted) |
| `phone read-long --role R [--container-id ID] [--from-top]` | scroll a container, stitch pages, dedupe overlap |
| `phone nodes --role R [--pkg P]` | labelled nodes with tap centres, for calibration |
| `phone ocr --role R` | OCR of a redacted screenshot, for text the accessibility tree does not expose |
| `phone shot --role R OUT.png` | redacted screenshot |
| `phone home`, `phone back`, `phone scroll DIR` | navigation |
| `phone restore --role R [--adapter A]` | adapter fresh screen, then the home screen |
| `phone chat ADAPTER state\|read --role R [--title T] [--long] [--from-top]` | adapter state; visible text. `--title` first opens that chat by exact title through the drawer search (reading only) |
| `phone chat ADAPTER send --role R --tag T --file F --i-mean-it` | one send, at-most-once |
| `phone chat ADAPTER send ... --preflight-only` | readiness only: types, detects Send, clears; never sends |
| `phone selftest` | guard self-test |
| `phone receipts [--limit N]` | recent receipts (no text, no serials) |

## Examples

Read what an app is showing, without touching anything else:

```bash
phone open --role s22 com.example.app
phone text --role s22 --pkg com.example.app
phone read-long --role s22 --max-steps 20 --from-top > page.txt
phone restore --role s22
```

Read an existing ChatGPT chat by its exact title (nothing is sent), then tidy up:

```bash
phone chat chatgpt read --role s22 --title "Exact chat title" --long --from-top
phone restore --role s22 --adapter chatgpt
```

Prove the ChatGPT send path is ready (never sends):

```bash
phone chat chatgpt send --role s22 --tag READY-1 --value "readiness check" --preflight-only
```

Send one brief (the first line must carry `(tag TAG)`; it is added when missing):

```bash
phone chat chatgpt send --role s22 --tag FIX-142 --file brief.txt --effort "Extra High" --i-mean-it
# status: sent | unconfirmed | failed | owner_busy | rate_limited
```

Calibrate a new app: open it on the worker phone, then list its labelled nodes on each screen:

```bash
phone nodes --role s22 --pkg com.example.app
```

## Adapters

- **chatgpt** (`com.openai.chatgpt`): the proven launcher flow. Open the app, reach a fresh empty
  composer from any state (at most six attempts, search and drawers unwound, human drafts preserved,
  only our own `(tag X)` residue cleared), `set_text`, wait up to 15 s for an enabled Send, tap Send
  once, confirm only that the send left the composer, scan for rate-limit text, restore a fresh
  composer. Briefs go to ordinary Chat only (the composer must carry `Ask ChatGPT`). A rate limit
  extends `<lock dir>/chatgpt-quota-pause` by three hours (never shortens it). Reply text is read from the
  accessibility tree only when the app exposes it; the old clipboard Copy path is blocked, so collect
  results server side.
- **deepseek** (`com.deepseek.chat`): **not calibrated**. Every operation raises
  `CalibrationRequired`. Probe with `phone nodes`, then follow `references/calibration.md`.

## Guard

Importing `phone` activates `phone.guard` (stdlib only). It blocks, with `PhoneGuardError`:
adbutils `install`, `install_remote`, `uninstall`, `server_kill`; uiautomator2 `_setup_ime`,
`send_keys`, `set_input_ime`, the clipboard getter and setter, `set_clipboard`, `app_install`,
`app_uninstall`, `app_stop_all`, `freeze_rotation`, `set_orientation`; any shell command (matched by
basename, so `/system/bin/pm` counts) with `pm install|uninstall|clear|grant...`,
`cmd package ...`, `ime enable|set|disable|reset`, `settings put|delete|reset`, `device_config` and
`appops` writes, `setprop`, `service call`, `svc` toggles, or a stop of a protected package
(`am`/`cmd activity` `force-stop|kill|stop-app`, `am kill-all`). The same policy runs at the adb
wire level (`AdbConnection.send_command`: `shell:`, `shell,v2:`, `exec:`, `abb_exec:`), so lower-level
adbutils helpers cannot skip it, and on the uiautomator2 HTTP request under `jsonrpc_call`. adb binary
calls with `install`, `uninstall`, `pair`, `abb`, `kill-server` are blocked, also through
`bash -c "..."` or wrappers such as `timeout` and `flock`.

`phone selftest` (or `python -m phone.guard selftest`) proves it. `scripts/install-guard.sh` can also
install the guard as a `sitecustomize` hook in each Python's stdlib directory so raw scripts are
covered. It writes nothing without `--apply`; read its header for the blast radius first. The owner
decides whether to run it.

## Pitfalls

- `RemoteDisconnected`, `NullPointerException` or `ApplicationSharedMemory` from uiautomator2: the
  package recovers once with `stop_uiautomator()` / `start_uiautomator()` (reads and pre-send steps).
  It never reinstalls anything. After a Send attempt it never replays.
- `unconfirmed` is not `failed`. It means the send may have happened. Inspect the chat before any new
  tag is enqueued; never re-send the same text blindly.
- A Samsung swipe-only cover can hide the app while it reports resumed. The driver dismisses it only
  when Android says it is non-blocking; with a credential keyguard it stops and asks for a person.
- Normal reply `Share` controls are not overlays. Pressing Back on them exits ChatGPT.
- `New chat` is inside `Menu` on the ChatGPT home screen, and it retains an unsent draft.
- If another driver holds the lock, `phone` waits `--lock-wait` seconds (default 120) and refuses.
- An app an agent opened stops counting as "being driven" after 5 minutes without agent input; a
  later `phone tap` then refuses with `WrongForeground` or `OwnerBusy`. Re-run `phone open`, or name
  the app with `--pkg`. This is what keeps the owner's own use of that app from being overridden.
- Hierarchy dumps can fail on animated screens; `wait_idle` and a retry usually fix it.
- Drawer layouts change with app versions (the old `Recents` label is gone), so chats are opened by
  exact title through Search, never by drawer position. A title the drawer truncates with an
  ellipsis cannot be matched; use the full title.
- A chat read only sees what the app exposes to accessibility. Check `complete` and `gaps` in the
  result: `complete: false` or `gaps > 0` means part of the page may be missing.
