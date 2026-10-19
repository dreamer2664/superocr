# qcaptcha — the phone pipeline (USB debugging)

When the captcha is on a **phone**, a desktop app cannot see it or type into it.
This pipeline talks to the phone itself over ADB: it takes the screenshot **from
the phone**, reads the widget tree **from the phone**, and types the answer
**into the phone**. No screen-mirroring, no window focus games.

```
phone screen ──screencap──▶ picture of the captcha
phone widgets ─uiautomator─▶ exact boxes + the text field
answer ──────input text───▶ typed into the app, then verified by re-reading the field
```

---

## 1. One-time phone setup (30 seconds)

1. **Settings → About phone → tap "Build number" 7 times** → Developer options appear.
2. **Settings → System/Developer options → USB debugging → ON**.
3. Plug the phone into the computer with a **data** cable (not a charge-only one).
4. A prompt appears on the phone: **"Allow USB debugging?"** → tick *Always*
   and **Allow**. (If it never appears: change the cable, or revoke USB
   debugging authorizations in Developer options and replug.)

> Android 11+ also supports **wireless debugging** (Developer options → Wireless
> debugging → Pair device with pairing code), but USB is the least surprising.

## 2. One-time computer setup

The pipeline needs Google's `adb` tool (part of *platform-tools*):

| Your system | Install | 
|---|---|
| Linux | `sudo apt install adb` |
| macOS | `brew install --cask android-platform-tools` |
| Windows | download *platform-tools* from developer.android.com, unzip, add the folder to PATH |

Then check that the computer sees the phone:

```bash
adb devices          # your phone should be listed as:  <SERIAL>   device
```

If it says `unauthorized`, accept the prompt on the phone. If it says nothing,
it is the cable/driver/authorization — fix that first.

## 3. The commands (inside the app folder)

```bash
sh start.sh --phone-check                  # is everything wired? (JSON report)
sh start.sh --phone-study                  # ← RUN THIS FIRST: captures the screen
                                           #   + widget tree. Types NOTHING.
sh start.sh --phone-once                   # read one captcha (types nothing)
sh start.sh --phone-once --phone-type      # read + type the answer into the field
sh start.sh --phone-arm                    # watch: solve + type every new captcha
                                           #   as it appears (Ctrl-C stops)
```

Useful extras: `--adb /path/to/adb` · `--serial SERIAL` (when several devices
are plugged in) · `--study-dir DIR` · `--no-shot` (do not save the screenshot —
privacy) · `--reader gemini|local`.

## 4. What `--phone-study` produces (and what to send back)

A folder (default `./qcaptcha-phone-study/`):

| File | What it is | Safe to share? |
|---|---|---|
| `REPORT.md` | device, foreground app, the boxes the analyzer found, every widget with bounds, and what it thinks the captcha/field are | **yes** |
| `study.json` | the same, machine-readable (full widget list) | **yes** |
| `captcha_crop.png` | the exact crop a reader would look at | **yes** |
| `ui.xml` | the raw hierarchy dump | **yes** |
| `screenshot.png` | the whole screen | your call — may contain personal data (omit with `--no-shot`) |

With those files in hand the app can be tuned to the **real** screen: exact
widget ids, exact boxes, whether the captcha lives in a normal ImageView or
inside a WebView (which changes the strategy), and what the field looks like.

## 5. How the solver decides

1. **Widget tree first** — `uiautomator` gives exact bounds for the captcha
   image and the text field on most native apps. No guessing, no calibration.
2. **Vision fallback** — if the captcha is inside a WebView / canvas (nothing
   in the widget tree), a full screenshot goes to Gemini (`solve_page`: boxes +
   answer in one request, needs keys). The study report tells you which case
   you are in.
3. **Type, then verify** — it taps the field's centre, types with
   `input text`, then **re-dumps the UI and checks what the field actually
   contains**. A typed answer that did not land is reported, not pretended.

## 6. Safety rails

* Nothing is typed unless you explicitly ask (`--phone-type`, `--phone-arm`).
* `--phone-study` and `--phone-once` never touch input.
* The same captcha is never typed twice (pixel fingerprint).
* Everything is logged to `~/.qcaptcha-history.csv` (`target=phone`,
  `verified` column tells you whether the text really landed).
* Serials are masked in every output (`FAKE…` style).

## 7. Common errors

| Message | Meaning / fix |
|---|---|
| `adb not found at 'adb'` | platform-tools not installed / not on PATH (step 2) |
| `no authorised device: … is 'unauthorized'` | accept the USB-debugging prompt on the phone |
| `several devices connected (…) — choose one with --serial` | pass `--serial <SERIAL>` |
| `uiautomator dump returned no hierarchy XML` | screen locked, or an app that blocks dumps — unlock / try again; vision fallback still works |
| `screencap produced no PNG` | screen locked, or capture blocked — unlock the phone |
| `no captcha found (widget tree had none and vision is unavailable: no keys)` | the captcha is inside a WebView — add Gemini keys (Keys… dialog on the desktop app, or `~/.qcaptcha-keys.json`) |
| `typed but not verified: field does not match the read` | the tap missed or the field rejects the paste (some keyboards autocomplete) — re-run `--phone-study` and send the report |
