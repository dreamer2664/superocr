# S29 — augmented retrain (v4): corrosion + rotation in the training mix (t-20261013-46d0)

**Question.** S24-S28 closed every lane except one: a recognizer trained on
the degradations that kill the current one. v4 = v3's exact protocol
(same net, per_class 311, 34 epochs, seed 11) with the crop renderer extended
by the two S28-named degradations: heavy 6-offset stroke at p=0.35, corrosion
pits (~1/150 ink px, r 1-3, median-3) at p=0.85|heavy, rotation widened
±6→±9°. Everything else imported unchanged from `tools/train_glyphs.py`.

**Training.** `models/glyphcnn-v4.npz`, recipe `recipes/glyphcnn-v4.json`:
val 0.9147 (v3: 0.9394 — the harder mix costs ~2.5 pts of clean val,
expected). Generator-sheet harvesting kept 4/240 (the agreement gate rejects
at the current reader state; synthetic dominates — same caveat as v3's
recipe notes).

## Measurement on the S28 probe populations (both seeds)

| arm | v3 | v4 | bar |
|---|---|---|---|
| corrosion-corroded | 0.297 / 0.365 | **0.439 / 0.520** | 0.85 |
| corrosion-control | 0.737 / 0.818 | 0.845 / 0.878 | — |
| collage-asis (rotated) | 0.260 / 0.273 | **0.292 / 0.221** | 0.85 |
| collage-derotated | 0.682 / 0.714 | 0.701 / 0.714 | — |

Confidence gate: still dead (30-61 wrong predictions at prob ≥ 0.9 per arm).

**Re-verification note**: the collage-asis construction was audited during
this task (a suspected canvas-level mask bug turned out to be a debug
artifact — missing trim offset in an ad-hoc check). Re-measured with the
corrected white-canvas construction: v3 0.260/0.273 and v4 0.292/0.221 —
within noise of the published S28 numbers, which therefore STAND.

## Verdict

**The bar is NOT met — one honest iteration, reported as measured.**

- Corrosion augmentation works in direction (+14/+15 pts on corroded,
  +8-11 on control) but tops out at ~0.5 — half the bar.
- **Rotation does not transfer at all** (0.22-0.29 vs v3's 0.26-0.27)
  despite ±9° at p=0.7 in training — named as the open question: the
  training crop is a tight ink box of a rotated canvas and the probe crop
  is the transformed per-char box cut from the rotated image; the semantics
  look identical yet the transfer is zero, so something subtler (bicubic
  card resampling? per-char box clipping of neighbors' strokes?) separates
  the distributions. A next iteration would match the probe's exact crop
  semantics in training and raise per_class on the corroded/rotated arms.
- v4 costs 2.5 pts of clean val for a partial corrosion gain — NOT a
  shipping candidate as-is.

**State of the 95-bar after S29**: text layer exhausted (S24/S25/S26),
mask layer capped (S27), current CNN no-go (S28), first augmented retrain
no-go (S29: corroded ~0.5, rotated ~0.25). The remaining route is still
retraining — but it needs the crop-semantics fix and a bigger budget on
the hard arms, not just the augmentation flags.

## Files

- `tools/train_glyphs_v4.py` — the v4 trainer (v3 protocol + aug)
- `models/glyphcnn-v4.npz` + `recipes/glyphcnn-v4.json` — weights + recipe
- `tools/s28_v3_dead_families.py` — probe, now with `--weights` (used for
  both models; canvas construction corrected + re-verified)
- `reports/s29-v4-augmented/` — this report
- `reports/s28-v3-dead-families/fixed-{v3,v4}-seed{1,2}/` — the v3/v4
  comparison receipts (re-verification + v4 measurement)
