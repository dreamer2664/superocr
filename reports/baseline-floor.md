# Baseline floor (t-20261011-65ff)

The classic textbook reader — contrast normalisation, deskew, per-glyph
isolation, template matching at native raster scale. No ML, no family
strategy, no lexicon, no fallback chain. JOBS.md S1: these numbers set what
the learned reader must beat.

## Numbers (seeded, reproducible)

| suite | command | exact | char |
|---|---|---|---|
| easy (n=10, seed 7) | baseline.py --score | 40.0% | — |
| hard (n=120, seed 7) | baseline.py --score | 9.2% | — |
| all (n=130) | baseline.py --score | 11.5% | 37.3% |
| reference pack (26 scored tiles) | baseline.py --reference | 0.0% | 9.0% |

The bar is not met by the floor. That is the point of a floor.

- machine report: baseline-floor.json
- per-tile gallery: baseline-reference.json (every failure named,
  e.g. cut 'XKWDN' -> 'XKWDR' is a 0.8-char near-miss, collage/snow/
  spiderweb/cross-shadow/darts/strippy families are segmentation-level
  losses; the 6 '?' tiles from t-4e49 are excluded and named, never guessed)

## What was measured on the way (all logged in the PR)

- The metrics mismatch that broke template matching (glyph masks normalised
  to nominal 28px vs faces rendered at 28px nominal then trimmed) — fixed by
  matching at native raster height. easy char accuracy 50% -> 72% at n=20,
  exact 0-20 -> 6-20.
- REJECTED by measurement: merging adjacent slim fragments of over-split
  glyphs. It glued i/l/t and cost easy char 72% -> 56% at n=20.
- Dominant remaining disease: touching bold/italic glyphs over-split by the
  sparsity-cut segmenter (m -> 1 g 1 1), which is S3's segmentation war.
- The arc-threshold glyph filter from the fallback chain wipes bold stems at
  small x-heights (4px stems @ x-height 10px) and is kept out of the floor.

## The 45-second test

tests/test_baseline.py — floor chars on easy >= 0.60, deskew on a 6deg
rotation recovers >= 80% of the unrotated read, sweep determinism, reference
pack measures exactly 26 and excludes exactly 6, and the native-scale
matcher regression case (the 10x10 bold-serif 'r').
