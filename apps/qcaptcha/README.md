# qcaptcha — the superocr Screen Solver

**A native desktop app. You click twice to calibrate; it reads the captcha on
your screen and types the answer into the text box for you.**

This is the piece a browser tab cannot do: reading your screen *and* reaching
into another window's text box. No cloud, no account, no OCR service — the
reader runs locally on your machine, on the same code path as the official
receipts (`baseline.read_text` + `lex_projection.fix_line`).

Not affiliated with any captcha provider. Use it on systems you own or are
authorised to automate. The reader is good on its own training distribution
(the generated suite families) and honest about the rest — see "Honest
limits" below.

---

## Quick start (downloaded bundle)

1. Unzip. Requirements: **Python 3.10+** and `pip install -r requirements.txt`
   (Pillow + numpy; the launcher offers to do this for you).
2. Launch:
   - **Windows:** double-click `start.bat`
   - **macOS:** `sh start.command` — first run: right-click → Open. Grant
     **Screen Recording** (capture) and **Accessibility** (typing) when asked.
   - **Linux:** `sh start.sh` — needs an X11 session (XWayland is fine for
     capture; **input injection does not work on native Wayland**). If
     `xdotool` is missing: `sudo apt install xdotool` (or `pip install pynput`).
3. A small **panel** appears. Press **Calibrate**:
   - Step 1/2: the screen freezes (dimmed). **Drag a box over the captcha
     image** — or single-click it for a default-size box. Enter to keep.
   - Step 2/2: **click the text box** you want the answer typed into. Enter.
4. Press **Arm ▶**. Every poll interval the app photographs the captcha
   region, reads it, and pastes the answer into the text box.
   - **F9** arm/disarm · **F10** read once · **F11** recalibrate
   - The panel is always-on-top: **park it where it does not cover the
     captcha** (it warns you if it does). Its position is remembered.

Odd failures type `?` or nothing: `?` means the reader looked at pixels it
could not parse — most often the panel or another window slid over the
captcha region, or the page scrolled. Recalibrate (F11) after changing
layout; regions are fixed pixel boxes, so scrolling or resizing invalidates
them.

## From a source checkout

```bash
python3 apps/qcaptcha/launcher.py --check        # environment + engine report
python3 apps/qcaptcha/launcher.py --selftest     # wiring + smoke read (no GUI)
python3 apps/qcaptcha/launcher.py                # the app
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
| `qcaptcha/engine.py` | the shipping reader bridge (no new OCR code) |
| `qcaptcha/solver.py` | capture→read→clean→deliver cycle; history CSV |
| `qcaptcha/overlay.py` | panel UI + frozen-screen click/drag calibration |
| `launcher.py` | preflight, `--selftest`, `--once`, GUI entry |

History: every read lands in `~/.qcaptcha-history.csv` (timestamp, text,
confidence, ms, delivered, mode). Nothing leaves your machine.

## Honest limits (read this)

- **In-distribution reads only.** The reader is strong on the repo's DejaVu
  CAPTCHA families and weak on arbitrary UI text, other fonts, rotation and
  heavy interference. A smoke selftest (6 samples, in-distribution) is
  **not** a benchmark; the 98/95 targets are **not met** — this app does not
  change that either way. It is a delivery mechanism for the reader as it is.
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
python3 tests/test_qcaptcha_solver.py                     # headless core (15 tests)
xvfb-run -a -s "-screen 0 1280x800x24" \
  python3 tests/test_qcaptcha_gui.py                      # real GUI e2e (4 tests)
```

The GUI test does the full chain on a virtual display: puts a captcha image
on screen, captures it from X11, reads it through the engine, injects a
click + Ctrl+V with the real `xdotool`/`xclip` backends, and verifies the
text landed in another window's text widget.
