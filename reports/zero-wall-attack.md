# Cracking the zero-wall families — t-20261011-be57 status

Continuation of reports/s6-summary.md. First: WHERE does each family die?
(`tools/stage_diagnosis.py`, seed 7, 10/family; seg/true = pieces found
vs true glyphs; clsFail|segOK = share of correctly-segmented images the
matcher still misreads)

| family | ink? | seg/true | segOK | clsFails when segOK | verdict |
|---|---|---|---|---|---|
| collage | 1.00 | 0.48 | 0/10 | — | SEGMENTATION: scraps rotated/offset break the line model |
| corrosion | 1.00 | 1.02 | 4/10 | 100% | **CLASSIFIER** |
| cross-shadow | 1.00 | 0.81 | 0/10 | — | SEGMENTATION: bands swallow glyphs |
| darts | 1.00 | 0.48 | 0/10 | — | SEGMENTATION collapse |
| dark-on-dark | 1.00 | 0.19 | 0/10 | — | BINARISATION, upstream of everything |

## Shipped: polarity guard (baseline.py)

Diagnosis: on dark-on-dark the autocontrast inverts roles (background ~
13.7 gray → stretched high), Otsu splits with polarity OUT — the "ink
mask" covers **98% of the sheet**. Document ink coverage is ≪50% by
construction, so a post-Otsu mask above half coverage is the background:
invert it. Six lines, one chain, no family branches.

Re-measure over all 13 families (seed 7, 10/family, `baseline.score_all`):

- **zero regressions**: every family's exact bit-identical to the
  pre-guard floor (easy 40, snow 20, split 30, cut 30, spiderweb 10,
  stitch 10, obstruction 10, ...).
- dark-on-dark **char 0.0% → 52.4%**; sample post-guard reads go from
  empty to `CoFmt meteor beacon MLoN 55` vs truth `CoMet meteor beacon
  tALoN 55`. Exact stays 0/10: the vignette (≤25% edge dimming) still
  destroys a few strokes per image at the global threshold — 'M' arrives
  with half its ink and matches F, 'A' minus one leg is a perfect L.
  That residue is information loss at binarisation, not scoring: it is
  what a proper local/adaptive threshold would have to win back, and it
  is the honest next lever for this family.
- overall char 41.4% (was 39.5 in the S6 table); overall exact unchanged
  11.5%.

## Attacked and NOT cracked (reported with numbers, per the honesty rule)

**corrosion — classifier-stage failure.** Microprobe says the true char
is not even top-5 in template scoring: a corroded 'o' matches 'l' at
0.954 with quarter ink mass; 'i' → 'z' @ 0.865. Two rescue attempts,
both measuring **zero** held-out gain:

1. matcher variants (close1/close2/dilate1/dilate2/union/cover, wider
   height windows ±3/±5): nothing lifts corrosion; close2 actively
   breaks easy (33% → 0 on the 3-image probe). `tools/matcher_variants.py`.
2. CNN fine-tune on exactly-aligned corroded glyph crops (labels from
   the generator via floor segmentation — no pseudo-labels): 10 epochs
   drive train loss 8.25 → 2.09, held-out corrosion exact stays 0/10,
   char 17c → 15c, and easy control crashes (58c → 30c at the gentler
   recipe). The corrosion pattern does not generalise across seeds, or
   the stroke information is simply gone. `tools/corrosion_cnn.py`,
   `reports/corrosion-cnn.json`.

**collage / cross-shadow / darts — segmentation walls, mapped, unfixed.**
seg/true 0.48 / 0.81 / 0.48: the floor's line/word model loses half the
glyphs before the matcher ever runs. These need a segmentation rethink
(connected-component tracking under rotation for collage; local
threshold for cross-shadow bands; small-mark filtering that survives
guards for darts) — each is its own job with a measurement harness that
this task now provides (`tools/stage_diagnosis.py`).

## Artifacts

- `tools/stage_diagnosis.py` — the stage-attribution harness (reusable
  for any family/seed).
- `tools/matcher_variants.py`, `tools/corrosion_cnn.py` — the corrosion
  experiments, kept reproducible.
- `reports/stage-diagnosis.json`, `reports/corrosion-cnn.json`,
  `reports/matcher-variants.json` when re-run.
- `baseline.py` polarity guard + regression test in
  `tests/test_baseline.py` (dark-on-dark char-acc ≥ 0.35 over seed-7 0-4).
