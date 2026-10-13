# CAPTCHA Studio

Standalone CAPTCHA generator + OCR tester. Unzip → run → browser opens.
No network needed at runtime; no build step; no CDN assets.

## Requirements

- Python 3.10+ with `numpy` and `Pillow` installed
  (`python3 -m pip install numpy Pillow` if missing — the launcher tells you).

Everything else is bundled: the superocr generator + degradation engine,
the shipping reader (`baseline.read_text → tools/lex_projection.fix_line`),
the glyph CNN (v2) and preclass weights, and eight DejaVu font faces
(license in `fonts/DejaVu-LICENSE.txt`).

## Run

```
python3 run.py            # picks a free port, starts the server, opens the app
python3 selftest.py       # optional CLI check (imports/fonts/determinism/render/reader)
```

The watcher restarts a crashed server automatically (5 tries). Ctrl-C exits.

## What it does

- **Generate** one CAPTCHA at a time with configurable degradation:
  control · corrosion (light/medium/heavy/extreme) · rotation
  (mild/moderate/severe/extreme) · overlays (spiderweb / cross-shadow /
  strippy / darts, light/heavy) · combined (2–3 stacked).
- **Ground truth label** always available (toggleable), plus the render
  parameters and a one-click PNG download. Every item is deterministic:
  the same seed + salt + settings always renders the same image — share the
  numbers to reproduce a CAPTCHA exactly.
- **Test the OCR** on what you generated: the app runs the *shipping*
  reader route (the same semantics as `python3 tools/reader_lex.py {image}`)
  and stamps **EXACT/MISS** with the read, the truth, and timing.
- **Selftest** from the UI (`/api/selftest`) or the CLI: imports, bundled
  fonts, in-process render determinism, a full degradation sweep, and a
  reader round-trip on a control item (must read exactly) + one degraded
  item (must not raise).

## Layout

```
run.py            launcher + watchdog + browser open
server.py         stdlib ThreadingHTTPServer, JSON API
selftest.py       the packaged checks
engine/           vendored superocr modules + models (reader + generator)
fonts/            8 DejaVu faces + license
static/           the one-page app (vanilla JS, offline)
```

## API (for scripters)

- `GET /api/config` — engine/env metadata + degradation catalogue
- `POST /api/generate {degradation_type, severity, overlay_family, seed, salt}`
  → `{png_b64, label, degradation_type, severity, rotation_deg, size…}`
- `POST /api/ocr {image: base64-png}` → `{text, route, reader_ms}`
- `GET /api/selftest` → same checks as `python3 selftest.py`

## Provenance

Engine files are a verbatim vendor of `dreamer2664/superocr` @ `a530a8f`:
`generator.py`, `preclassify.py`, `baseline.py`, `reader.py`,
`readers/{glyphcnn,piece_cnn}.py`, `tools/lex_projection.py`,
`tools/gen_hard_corpus.py`, `models/{glyphcnn-v2,preclass_centroids}.npz`.
Interactive single-item rendering is driven by `(seed, salt, type, severity)`
via `captcha-studio:`-salted SHA-256 RNG instead of corpus indices; the
degradation mechanics and severities are the S53 corpus's own functions.
Fonts are DejaVu (Bitstream Vera derivative license; bundling permitted).
