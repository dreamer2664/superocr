# reference/ — Carlo's sheets, tiled and labeled (t-20261011-4e49)

Carlo's four uploaded sheets are the portrait of what superocr must read. This
folder keeps them, plus the `tiles/` they are cut into and `labels.json` with
the ground truth an agent could certify by eye.

## What is here

| sheet | tiles | labeled | `?` |
|---|---|---|---|
| `captchas1.jpg` (2×7 grid, captioned families) | 14 | 14 | 0 |
| `captchas2.jpg` (tutorial panels with ✓/✗ grades) | 5 | 2 | 3 |
| `captchas3.jpg` (2×6 grid, no captions) | 12 | 9 | 3 |
| `Screenshot 2026-10-09 211136.png` (solver UI) | 1 | 1 | 0 |
| **total** | **32** | **26** | **6** |

## The rule (JOBS.md)

A tile gets a string only when the reading is **certain** — every tile was read
at 4× zoom, and borderline ones again at 8×. Anything remaining ambiguous is
`"label": "?"` with `"scored": false` and an honest note about *why* and which
candidate read was rejected. These six are excluded from scoring, never
guessed.

## The failure gallery (all six `?` tiles)

- `tiles/captchas2/p1-photo.png` — a plate photo inside a tutorial panel; at 4×
  it is a three-glyph blur (529 / 629 / b29 all defensible, none certain).
- `tiles/captchas2/p3-dark.png` — a red-✗ panel; cut-lines plus noise leave two
  glyphs uncertifiable.
- `tiles/captchas2/p4-noise.png` — a red-✗ panel; left glyph clipped by the
  black bar, third glyph 9-vs-P. The tutorial's own answer "XR94" was graded
  wrong, so we excluded that reading instead of repeating it.
- `tiles/captchas3/t06.png` — the strike-through erases crossbars (candidate
  "AAMTIE" noted in labels.json, not certified).
- `tiles/captchas3/t08.png` — wavy small-caps, several glyphs open
  ("test7y7"-ish, not certified).
- `tiles/captchas3/t12.png` — hand-drawn strokes, chars 2/3/5 ambiguous
  ("2G4McG"-ish, not certified).

Span of the gallery: dark-on-dark boards, cut glyphs, strike-through, wavy
small-caps and hand-drawn strokes are the families where *human* certainty runs
out — expect the reader's hardest fights there too.

## How the bench consumes this

`labels.json` is the ground truth. Bench items are the 26 `"scored": true`
tiles; the six `?` tiles may be shown in reports (gallery only) but never
counted. Cases are exact and case-sensitive. Suite/family assignment belongs to
`bench.py` (t-2f3d) — the `family` fields here are best-effort hints.

## Reproducing

    python3 tools/tile_reference.py           # regenerate tiles/ (byte-stable)
    python3 tools/tile_reference.py --check   # verify tiles match the spec
    python3 tests/test_reference_pack.py      # every tile in labels.json exists,
                                              # no orphans, sha manifest fresh

The crop spec (pixel boxes) lives in `tools/tile_reference.py`. Panels on
`captchas2.jpg` exclude the ✓/✗ grade column (x ≥ 495).
