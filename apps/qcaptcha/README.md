# qcaptcha — the superocr Screen Solver

**A native desktop app. Calibrate with one click (Gemini finds the boxes) or
two drags (manual); it reads the captcha on your screen and types the answer
into the text box for you.**

This is the piece a browser tab cannot do: reading your screen *and* reaching
into another window's text box.

**How it works while armed (v1.2.0):** every cycle takes one screenshot, asks
Gemini for the captcha box, the text box **and the answer in a single request**
— so a captcha that changes size or moves between refreshes needs **no
recalibration, ever**. A pixel-hash check means the same captcha is never
answered twice. Manual calibration is just a hint and a fallback.

**Two reading backends:**
* **Gemini (default)** — your own Google Gemini API keys, vision OCR. Best
  accuracy on hard/arbitrary captchas (~2 s per read; live-verified 10/10 on
  the easy family, 5/6 on the snow family in this repo's tests).
* **local (offline)** — the superocr reader already in this bundle
  (`baseline.read_text` + `lex_projection.fix_line`, the shipping route).
  No network, weaker on hard families. Switch with `--reader local`.

Not affiliated with any captcha provider. Use it on systems you own or are
authorised to automate. The reader is good on its own training distribution
(the generated suite families) and honest about the rest — see "Honest
limits" below.

---

## Quick start (downloaded bundle)

1. Unzip. Requirements: **Python 3.10+** with **Pillow + numpy**:
   `python3 -m pip install --user -r requirements.txt`
   (Windows: `py -3 -m pip install --user -r requirements.txt`).
   If packages are missing, the launcher tells you exactly what to run.
2. Launch:
   - **Windows:** double-click `start.bat`
   - **macOS:** `sh start.command` — first run: right-click → Open. Grant
     **Screen Recording** (capture) and **Accessibility** (typing) when asked.
   - **Linux:** `sh start.sh` — needs an X11 session (XWayland is fine for
     capture; **input injection does not work on native Wayland**). If
     `xdotool` is missing: `sudo apt install xdotool` (or `pip install pynput`).
3. A small **panel** appears. Put your Gemini keys in first (one time):
   press **Keys…**, paste one key per line, **Save + Test**. Keys are stored
   locally in `~/.qcaptcha-keys.json` (mode 600) — never in any repository or
   log. No keys yet? Everything still works with the offline reader
   (`--reader local`), just weaker.
4. Calibrate — two ways:
   * **Auto (Gemini)**: one screenshot, Gemini proposes the captcha box and
     the text box, drawn on a dimmed freeze of your screen.
     **Enter** accepts · **drag** redraws (first drag = captcha, second =
     text box) · **Esc** cancels to manual.
   * **Calibrate** (manual):
   - Step 1/2: the screen freezes (dimmed). **Drag a box over the captcha
     image** — or single-click it for a default-size box. Enter to keep.
   - Step 2/2: **click the text box** you want the answer typed into. Enter.
5. Press **Preview** to see exactly the crop that will be read (catches any
   mis-calibration instantly).
6. Press **Arm ▶**. From here on the app re-finds the boxes itself for every
   captcha — you do not need to recalibrate when the captcha changes size or
   moves. If nothing appears in the text box, press **Type test**: it clicks the
   text box and types a harmless string, proving (or diagnosing) that typing
   into other windows works on this machine. Every poll interval the app photographs the captcha
   region, reads it, and pastes the answer into the text box.
   - **F9** arm/disarm · **F10** read once · **F11** recalibrate
   - The panel is always-on-top: **park it where it does not cover the
     captcha** (it warns you if it does). Its position is remembered.

Odd failures type `?` or nothing: `?` means the reader looked at pixels it
could not parse — most often the panel or another window slid over the
captcha region, or the page scrolled. Recalibrate (F11) after changing
layout; regions are fixed pixel boxes, so scrolling or resizing invalidates
them.

## Gemini keys — where they live

* App dialog: **Keys…** → paste → Save (writes `~/.qcaptcha-keys.json`, 600).
* Or by hand: `~/.qcaptcha-keys.json` = `{"gemini": ["key1", "key2", ...]}`
* Or environment: `QCAPTCHA_GEMINI_KEYS` (comma/newline separated) /
  `GEMINI_API_KEY`.
* Keys are sent only in the `x-goog-api-key` **header** (never a URL), rotated
  round-robin, parked 65 s when the per-minute quota answers 429, and scrubbed
  from every error message. They are never written into this repo or any log.
* The pool is a pool for a reason: each key has its own per-minute limit.

## From a source checkout

```bash
python3 apps/qcaptcha/launcher.py --check            # environment report
python3 apps/qcaptcha/launcher.py --selftest         # smoke read (uses the
                                                     # configured backend)
python3 apps/qcaptcha/launcher.py --type-test          # click the text box + type
                                                     # a test string (no clipboard)
python3 apps/qcaptcha/launcher.py --detect           # live auto-calibration:
                                                     # prints the boxes Gemini
                                                     # finds on your screen
python3 apps/qcaptcha/launcher.py --reader local     # force the offline reader
python3 apps/qcaptcha/launcher.py                    # the app
python3 apps/qcaptcha/launcher.py --once --no-paste --config ~/.qcaptcha.json
```

Build the downloadable bundle:

```bash
git fetch origin '+refs/pull/84/head:refs/tmp/pr84'   # for the bundled fonts (see below)
python3 tools/build_solver_zip.py --out /tmp/dist
```

## Files and what they are

| file | role |
|---|---|
| `qcaptcha/config.py` | regions + settings, `~/.qcaptcha.json`, atomic writes |
| `qcaptcha/capture.py` | screen capture (Pillow ImageGrab; `mss` fallback) |
| `qcaptcha/injection.py` | focus click + clipboard paste / typing, per-OS backends |
| `qcaptcha/engine.py` | the offline reader bridge (shipping route) |
| `qcaptcha/gemini.py` | Gemini client: key pool/rotation, read + region detect |
| `qcaptcha/readers.py` | LocalReader / GeminiReader — one interface, two backends |
| `qcaptcha/solver.py` | capture→read→clean→deliver cycle; history CSV |
| `qcaptcha/overlay.py` | panel UI + frozen-screen click/drag calibration |
| `launcher.py` | preflight, `--selftest`, `--once`, GUI entry |

History: every read lands in `~/.qcaptcha-history.csv` (timestamp, text,
confidence, ms, delivered, mode). Nothing leaves your machine.

## Honest limits (read this)

- **Two different qualities, stated plainly.** The Gemini backend reads
  arbitrary captchas much better than the offline one (the offline reader is
  strong only on this repo's DejaVu families — the 98/95 targets are NOT met
  by it). Selftests are smoke tests, not benchmarks. With Gemini, reads go to
  Google's API with your keys; with `--reader local` nothing leaves your
  machine, and the accuracy is what the repo's receipts say it is.
- **Fixed pixel regions.** Calibration is manual by design (you asked for
  click-to-calibrate). If the page scrolls or resizes, recalibrate.
- **The panel must not cover the captcha** (it is photographed too otherwise).
  The status line warns if it does.
- **Wayland:** capture may work; keystroke injection relies on X11
  (`xdotool`) or `pynput` with XWayland. Native Wayland injection is not
  supported in v1.
- **macOS** needs Screen Recording + Accessibility permissions for the
  terminal app that launches it.
- Windows: works from a plain Python install; no extra permissions.

## Bundled fonts

The bundle ships the same eight DejaVu faces the suite uses, with the license,
and patches `generator.py` so they are used when (and only when) the system
has no DejaVu tree — the same behaviour W2 PR #82 introduced for the browser
bundle. Source-provided fonts always win; the patch is idempotent and marked.
The bundle manifest records exactly which source provided each font.

## Tests

```bash
python3 tests/test_qcaptcha_solver.py                     # headless core (26 tests)
python3 tests/test_qcaptcha_gemini.py                     # rotation/parsing (15 unit; 2 live with QCAPTCHA_LIVE=1)
xvfb-run -a -s "-screen 0 1280x800x24" \
  python3 tests/test_qcaptcha_gui.py                      # real GUI e2e (7 tests)
python3 tests/test_build_solver_zip.py                    # bundle integrity (8 tests)
```

The GUI test does the full chain on a virtual display: puts a captcha image
on screen, captures it from X11, reads it through the engine, injects a
click + Ctrl+V with the real `xdotool`/`xclip` backends, and verifies the
text landed in another window's text widget.
