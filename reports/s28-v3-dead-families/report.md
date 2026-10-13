# S28 — v3 letter identity on the dead families (t-20261013-d3c3)

**Question.** S27 showed corrosion+collage are dead to the classic pipeline
even with truth masks (0/16). S26 closed v3 DIGIT identity under
corrosion-grade noise (34.7%). The one untested instrument on the two dead
families: glyphcnn-v3 LETTER identity — the go/no-go for the image-side lane.

**Method.** Oracle-box probe (s26's renderer verbatim for corrosion: heavy
6-offset stroke, pits on ink, median-3, tight per-char ink boxes; a
fam_collage-style card renderer for rotation: white card, text 24-34px,
rotate ±9° BICUBIC, per-char boxes recorded on the unrotated card and
transformed through the rotation). Crops cut from the reader's own front-end
mask, scored by PieceCNN(glyphcnn-v3). Letters scored, skips counted
honestly. Two seeds (71000, 99000) — stable.

## Result

| arm | seed 71000 | seed 99000 | reading |
|---|---|---|---|
| corrosion-corroded | **0.297** (n=148) | **0.365** | letters under corrosion noise: dead (mirrors S26 digits 0.347) |
| corrosion-control | 0.737 | 0.818 | the recipe itself costs ~20-25 pts before pits |
| collage-asis (rotated crop) | **0.253** (n=154) | **0.273** | v3 cannot read ±9° rotations |
| collage-derotated (perfect de-rotation) | 0.682 | 0.714 | even with the angle GIVEN, ~70% |

Confidence gate (addendum-6 discipline): no separation anywhere —
p_bad means 0.70-0.78 with 32-42 wrong predictions at prob ≥ 0.9 per arm.
The gate is dead here too.

## Verdict

**NO-GO for the image-side lane with the current instrument.** glyphcnn-v3
was trained on twin/residue classes at native raster (S16) — no
corrosion-grade noise, no rotation — and it shows: 25-37% on the degraded
glyphs, ~70% even with perfect de-rotation. Combined with S27 (mask-class
ceiling +19 hard at most, corrosion/collage dead downstream) and S24/S25/S26
(text layer exhausted), the honest state of the 95-bar:

- text layer: exhausted (S24 case, S25 count +2 shipped, S26 digits)
- mask layer: ceiling +19, real number lower (S27)
- current CNN on degraded glyphs: 25-37% (this probe)

**The only remaining route to 95 is a retrained recognizer with
corrosion-grade and rotation augmentation** — the training-data recipe is
now fully specified by measurement (S26's renderer + this probe's collage
renderer, both committed). That is a training-pipeline task (S16-class
work), not a post-pass.

## Files

- `tools/s28_v3_dead_families.py` — the probe
- `reports/s28-v3-dead-families/probe-v1.{json,txt}` — seed 71000 receipts
- `reports/s28-v3-dead-families/seed2/probe-v1.{json,txt}` — seed 99000
  (stability)
