# Hard-won behaviours and where they live

Each row is a rule learned on real phones, the module that keeps it, and the test that pins it.

| Behaviour | Code | Test |
|---|---|---|
| Exclusive flock per phone, shared outer lock first, proof through `/proc/locks` that this process or a live ancestor owns it | `phone/lock.py` | `test_phone_lock_claims.py` |
| Owner-activity check from `mLastUserActivityTime` vs uptime; unreadable evidence is busy; worker, daily and idle-window rules | `phone/activity.py` | `test_phone_activity.py` |
| Agent-open ledger (`<role>-agent-opened.json`: package to boot id and open uptime) so only an agent-launched foreground is exempt | `phone/activity.py` | `test_phone_activity.py` |
| Fresh-composer navigation from search, drawers, subpages; New chat lives inside Menu; at most six attempts | `phone/adapters/chatgpt.py` `new_chat` | `test_phone_adapters.py` |
| Never discard a human draft; clear only our own `(tag X)` residue; never in preflight | `chatgpt.py` | `test_phone_adapters.py` |
| Overlay dismissal with Back; `Share` is not an overlay | `chatgpt.py` `dismiss_overlays` | `test_phone_adapters.py` |
| Ordinary Chat composer only (`Ask ChatGPT`), never Work or Codex | `chatgpt.py` `send` | `test_phone_adapters.py` |
| Send readiness polled up to 15 s from fresh hierarchies; exact raw description selected; redacted diagnostics on a miss; typed brief cleared | `chatgpt.py` `send` | `test_phone_adapters.py` |
| Send once; after the attempt an RPC failure is `unconfirmed`, never replayed | `chatgpt.py` `launch` | `test_phone_adapters.py` |
| uiautomator recovery: `stop_uiautomator` then `start_uiautomator`, never reinstall; probe the hierarchy RPC, not `deviceInfo` | `phone/device.py` | `test_phone_adapters.py` |
| Samsung swipe-only cover dismissed only when `showing=false` and `inputRestricted=false`; never touch a credential keyguard | `Phone.open_app` | (real device) |
| At-most-once: claim before send, `launched.txt`, `unconfirmed.txt`, failed stays claimed, only `owner_busy` un-claims | `phone/claims.py`, `phone/dispatch.py` | `test_phone_lock_claims.py`, `test_phone_dispatch_cli.py` |
| Restore: adapter fresh composer, then HOME, verified against the home launcher | `Phone.restore` | (real device) |
| Quota pause: one account-wide file, extend never shorten, unreadable is paused, three hour fallback | `phone/quota.py` | `test_phone_lock_claims.py` |
| Dispatch cooldown reserved before transport | `phone/quota.py`, `dispatch.py` | `test_phone_dispatch_cli.py` |
| Open an existing chat by exact title through the drawer Search (reading only) | `chatgpt.py` `open_title` | `test_phone_adapters.py`, real device |
| Long reads: sticky elements removed, overlap deduped, gaps reported | `phone/hierarchy.py` `stitch_pages` | `test_phone_hierarchy.py`, real device |
| Rate-limit words scanned after send, ignoring words in our own text, with redacted evidence | `chatgpt.py` | `test_phone_adapters.py` |
| Pin adb to the local server, drop `ADB_SERVER_SOCKET`, prefer the SDK adb | `phone/config.py` | `test_phone_adb.py` |
| Never probe another role's phone during discovery; identity proven with `getprop ro.serialno`; existing pairing only | `phone/adb.py` | `test_phone_adb.py` |
| Redaction fails closed; raw captures stay in memory | `phone/redact.py` | `test_phone_dispatch_cli.py` |

## Differences from the production launcher (deliberate)

- The S25 idle-worker window was a dated, owner-specific exception. It is now opt-in per role with
  `PHONE_IDLE_WORKER_UNTIL_<ROLE>` and a kill-switch file, so no date is baked into the code.
- Home launchers are discovered from the phone's default HOME activity at runtime, plus a short
  public list and `PHONE_HOME_LAUNCHERS`.
- Effort slider stops are stored as fractions of a 1080x2340 screen, which reproduce the original
  pixel positions there and scale elsewhere.
- Receipts carry a hash of the transport id instead of the serial or address.
- The clipboard Copy path used by the old harvester is blocked. Results come from server-side
  outputs, or from text the app exposes to accessibility. The harvester's drawer navigation relied on a
  `Recents` label that the current app no longer has; `open_title` uses the drawer Search instead.
- `read_long` removes sticky elements (fixed headers, footers, floating chips) before stitching: a
  fixed footer in a real drawer list defeated a plain tail-overlap match and produced duplicates.
- The ledger and quota files are written atomically (write then rename).
