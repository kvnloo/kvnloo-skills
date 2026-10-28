# Calibrating an adapter on a real device (DeepSeek and any new app)

An uncalibrated adapter refuses to act. The adapter never guesses and never taps a neighbour.

## 1. Probe, read-only

On the worker phone only, with the owner not using it:

```bash
phone open --role s22 <package>
phone nodes --role s22 --pkg <package>      # on: home, drawer, composer with text, generating, done
phone restore --role s22
```

`nodes` lists text, description, resource-id, class and tap centre for every labelled node, redacted.
Look for a stable resource-id first, then a description, then text. Never use coordinates.

## 2. Write the calibration file

`<calibration dir>/<adapter>.json` (default `<state dir>/calibration/`, or `PHONE_CALIBRATION_DIR`).
Keep it out of the public repo if it holds anything account-specific.

```json
{
  "calibrated": true,
  "verified_on": "YYYY-MM-DD",
  "app_version": "as shown on the phone",
  "selectors": {
    "composer":    {"cls": "android.widget.EditText"},
    "send_button": {"desc": "Send"},
    "new_chat":    {"desc": "New chat"},
    "stop_button": {"desc_contains": "Stop"}
  }
}
```

Selector keys are `text`, `text_contains`, `text_starts`, `desc`, `desc_contains`, `desc_starts`,
`res_id`, `cls`, `pkg`, `focused`, `clickable`, `enabled`, `instance`. The values above are
placeholders, not verified selectors.

## 3. Prove it before any send

```bash
phone chat deepseek send --role s22 --tag READY-1 --value "readiness check" --preflight-only
```

Expect `preflight_ready`, `send_attempted: false`, an empty composer and a restored home screen.
Only then is a real send (`--i-mean-it`) reasonable.

## 4. Open questions to answer while calibrating

- Is the reply text exposed to accessibility? If not, there is no read path (the clipboard is blocked).
- Does the app keep an unsent draft across new chats? (Then add a draft check like ChatGPT's.)
- What shows rate limits, and in which words? Add them to the adapter's rate words.
