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



## v1.1.0 — Gemini for reading AND auto-calibration (2026-10-14, Carlo's keys)

Directive: "use these gemini keys for both calibration and reading."
Keys: 55 supplied in chat; validated live this session — **44 answered 200,
11 were per-minute 429 at sweep time** (quotas reset; the pool rotates, so
this is the designed-for condition). Keys were never written to any repo,
bundle, log or wire; the shipped zip was scanned for key material: **0 hits**.

### Reading (live, real API)
| family | exact | notes |
|---|---|---|
| easy (10 generated) | **10/10** | ~2.0 s median per read, rotation in use |
| snow (6 generated, hard family) | **5/6** | the miss: first character edge-clipped ('Stalactite' → 'talactite'; honest image-edge case). The offline reader gets 0/8 on snow. |

Found live and fixed: Gemini 3 *thinks by default* and that consumed the
output budget → truncated reads ('sUM' for 'sUMMiT 34 DELTA'). Fix:
`thinkingConfig.thinkingBudget = 0` (with a 400-tolerant retry).

### Auto-calibration (live, Xvfb synthetic page 1280×800)
One screenshot → `detect_regions()` (0-1000 normalized box_2d JSON):
* captcha box IoU vs ground truth **0.988** (truth [40,60,520,150])
* input box IoU **0.908** (truth [40,300,520,46])
Also verified from the **built bundle**: `--detect` returned captcha
[40,60,519,150] and input [41,302,517,42].

### Key hygiene / rotation
* key sent only in `x-goog-api-key` header (never a URL); `mask`/`scrub`
  applied to every message; unit-tested that raw keys never appear in errors.
* 429/403 parks the key 65 s; 503 parks the model 20 s; 404 parks the model
  600 s; round-robin pool; model chain starts `gemini-3-flash-preview`
  (`gemini-flash-latest`/`3.5` were transiently 503 during this session;
  `gemini-2.5-flash`/`-lite` are 404 for new keys).
* Keys file: `~/.qcaptcha-keys.json` (mode 600) or env; the app's **Keys…**
  dialog can save/test them (Test = live 200-probe per key, masked output).

### Suites after v1.1.0
**26 core + 7 GUI (3 new auto-cal overlay) + 17 gemini (15 unit + 2 live) +
8 bundle = 58 green**, plus 2 live-gated runs verified separately
(QCAPTCHA_LIVE=1: real read + real detect e2e).

### Artifact
**`qcaptcha-solver-acd5488cee74.zip` — sha256
`f178b5c9b42372f37457a843cfcb416baf67d9f8af3be378c8678fff29d13a71`**
(3,355,973 bytes, 45 files, clean build from `acd5488cee74`). Workspace root
copy + extracted `/home/user/qcaptcha-app/`. Stranger run from the extracted
folder: `--check` clean (55 keys masked, no problems), live `--selftest`
3/4 exact (miss = capital-I vs lowercase-l ambiguity), `--detect` matched
both boxes.

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
