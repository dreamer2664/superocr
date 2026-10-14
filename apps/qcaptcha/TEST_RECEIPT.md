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

## Release artifact

Built from **8e51b0d1b242** (clean tree; this receipt commit is documentation
and does not alter the artifact):

- `qcaptcha-solver-8e51b0d1b242.zip` — sha256
  `5d574cb47c9d9729d6ac1cd3d9ed46dc76b3796b842ceb6896120e2c37157623`
  (3.34 MB, 43 files; MANIFEST.json carries per-file hashes and font provenance)
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
