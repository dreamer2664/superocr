# qcaptcha Screen Solver — test receipt (t-20261014-cc4a, argus)

Machine: Linux sandbox, Python 3.13.16, Pillow 12.3.0, numpy 2.3.5,
Xvfb 1280x800x24 for GUI runs. Run date: 2026-10-14 (ET). Reader path:
shipping lex route (baseline.read_text + lex_projection.fix_line).

## Suites — all green

| suite | command | result |
|---|---|---|
| core | `python3 tests/test_qcaptcha_solver.py` | **15/15 OK** (9.7 s) |
| GUI e2e | `xvfb-run -a -s "-screen 0 1280x800x24" python3 tests/test_qcaptcha_gui.py` | **4/4 OK** (9.6 s) |
| bundle | `python3 tests/test_build_solver_zip.py` | **8/8 OK** (7.8 s) |

The GUI suite runs the chain for real, no fakes: a generated captcha image is
placed on the X display at (40,60), captured from X11 by the app, read via the
shipping route, then delivered with the real backends (xdotool click → xclip
clipboard → Ctrl+V) into a text widget of a different window — the assertion
is on the widget's contents (test_full_chain_screen_to_text_box PASS;
read == independent direct engine read of the same image). Calibration drag
produces the exact region [100,100,200,70]; single click produces a 120×40
box centered on the click.


## v1.0.1 — the ARM capture-error fix (2026-10-14, reported on real hardware)

Field report: ARM -> black frozen screen, then repeated
`ERR capture: no usable screen-capture backend (pillow: Image size
(19906560000 pixels) exceeds …)`.

Root cause: the calibration overlay read its canvas size before the window was
mapped (`winfo_width() == 1`), so the drag->region scale factor was garbage —
the drag "defined" a ~19.9-billion-pixel region, and ARM photographed that
every interval. Fixes (all committed in 26db1de):

- the frozen screenshot is drawn only once the window is really mapped
  (retries ~1 s, then 1:1 fallback); a photo is never computed from an
  unmapped canvas;
- `map_canvas_to_image()` — pure, clamped drag->region mapping, unit-tested
  against the exact garbage shape from the report;
- `config.load()` self-heals: corrupt saved regions are dropped (app opens,
  asks for a fresh calibration; other settings survive);
- capture raises one actionable error for absurd regions ("Re-calibrate (F11)…")
  instead of Pillow's bomb message; Arm re-checks region sanity and re-opens
  the wizard; the arm loop stops after 5 consecutive capture errors with a
  clear note; the status line shows "calibration corrupt — press Calibrate";
- the overlay warns if the frozen screen is all black (permissions hint);
- `--check` now includes a live `capture_test` (grabs 120×60) so capture
  problems are visible without the GUI.

**Suites after the fix: 26 core + 4 GUI e2e + 8 bundle = 38 green** (11 new
regression tests: mapping under unmapped canvas, clamping, config self-heal,
capture guards, loop auto-stop).

**Current artifact: `qcaptcha-solver-26db1deb95e2.zip` — sha256
`854e93a3e3b7f7fa718f129593b76f789fa5410572773818a39ee9a39971e27c`**
(3,343,445 bytes, 43 files, clean build from 26db1deb95e2). Workspace-root copy
`/home/user/qcaptcha-solver-26db1deb95e2.zip`; extracted copy
`/home/user/qcaptcha-app/` (v1.0.1). Stranger run from the extracted folder:
`--check` clean (capture_test honest per machine), `--selftest` 3/3 exact.

## Release artifact — fdf5382 (superseded by v1.0.1)

- **`qcaptcha-solver-fdf5382dde78.zip` — sha256
  `df31d05451ef462be494fa014266d81c47f0776c88d541504799f7efb1f49ce9`**
  (3,340,948 bytes, 43 files, built clean from **fdf5382dde78**;
  MANIFEST.json carries per-file hashes and font provenance).
- Staged at the workspace **root** (a persisted location):
  `/home/user/qcaptcha-solver-fdf5382dde78.zip`; already-extracted copy at
  `/home/user/qcaptcha-app/`.
- Change since the first build: `launcher.py` now checks Pillow/numpy *before
  any import needs them* — missing packages print the exact pip command
  instead of a traceback; `--install-deps` installs them. README corrected
  (it no longer implies auto-install). Suites re-run after the change:
  **27/27 green**.

## Release artifact — first build (superseded)

`qcaptcha-solver-8e51b0d1b242.zip` was staged under `/home/user/dist/`, which
the workspace snapshot does **not** persist (build-output directories are
excluded) — the download disappeared, hence the rebuild above. Kept here for
the record: built from **8e51b0d1b242**, sha256
`5d574cb47c9d9729d6ac1cd3d9ed46dc76b3796b842ceb6896120e2c37157623`.
- Extracted-stranger run: `sh start.sh --check` → no problems, engine found,
  8 fonts; `sh start.sh --selftest --selftest-n 4` → **4/4 exact**
  (SMOKE — in-distribution, small n; not a benchmark, canonical suites are
  evaluation-only); `xvfb-run … sh start.sh` → GUI alive, clean stderr.

## What is NOT proven here

- 98/95 is not met and not claimed by this app (it is a delivery mechanism
  for the current reader).
- Real-browser flows, Windows/macOS permissions dialogs, Wayland injection:
  untested in this sandbox (backends implemented; README documents the
  per-OS permissions).
