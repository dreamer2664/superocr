# S42 — the realism corpus: 10k degradation samples that produce the real failure modes (t-20261013-44ba)

**Why.** S29/S30 showed the synthetic degradation models don't match the
real failure modes; S43's census pinned them: 63/77 hard misses are
SEGMENTATION failures, and the retrain wall is stroke destruction (S30)
— not scale windows (S35, NO-GO). So "realistic" here is defined by
FAILURE MODE, not cosmetic damage.

## The generator (`tools/gen_real_corpus.py`)

Builds on the S53 infrastructure (same deterministic per-item sha-rng,
advance-based char_boxes, suite-format manifest; canonical fam_* recipes
untouched). Four families × 3 severities × 800 + control 400 = 10,000
items, seed 42, JPEG q90 (training-only corpus, gitignored,
regenerable). Manifest sha256 `248ff1acf3e3dcdb`; 208,710 char_boxes.

| family | mechanic | failure mode targeted |
|---|---|---|
| texcorrosion | value-noise-field-gated pits (clustered rough zones) + edge-biased stroke erosion, damage-budgeted (ink floor 75/55/35%) | stroke destruction (S30 wall) |
| paperdegrade | soft radial stains, yellowing gradient, fiber lines, creases | thresholding/OTSU (multimodal histograms) |
| perspective | true 4-corner homography warps ±6/14/26px (not uniform rotation); boxes transformed exactly through the same map | projection-profile/deskew failures |
| inkbleed | variable-radius dilation + soft blur re-composite + deliberate inter-glyph bridges (p=0.15/0.40/0.70) | touching-glyph segmentation (S43's 63/77) |

Two generator bugs caught by the smoke verification (ink-inside-box
checks): perspective coefficients were inverted for PIL's
output→input sampling convention (fixed: image uses the inverse of the
box map), and unbudgeted heavy texcorrosion annihilated ~99% of ink
(fixed: damage budget with per-severity ink floors).

## Receipt 1 — reader sensitivity + the S43 realism metric (12/cell, seed 7)

| cell | seg-align (floor pieces == glyph count) | reader_lex exact |
|---|---|---|
| control/none | 9/12 | 10/12 |
| inkbleed light/moderate/heavy | 3/12 · **0/12** · **0/12** | 4/12 · 0/12 · 0/12 |
| paperdegrade light/moderate/heavy | 8/12 · 10/12 · 7/12 | 7/12 · 9/12 · 5/12 |
| perspective light/moderate/heavy | 10/12 · 6/12 · 9/12 | 7/12 · 9/12 · 6/12 |
| texcorrosion light/moderate/heavy | 3/12 · 1/12 · **0/12** | 1/12 · 0/12 · 0/12 |

The corpus spans the whole difficulty space with truth boxes intact:
paper/perspective form the readable-but-hard curriculum band (5-9/12),
inkbleed collapses segmentation exactly like the real residue (0/12 at
moderate+), texcorrosion destroys identity (0-1/12 exact).

## Receipt 2 — it trains: v7c fine-tune smoke

`tools/train_glyphs_v7.py --corpus corpus/real10k --modes word,tight
--train-n 3000 --val-n 800 --cap 600 --epochs 8` (held-out split by
item index; canonical suites eval-only):

| cell (val, word+tight crops) | v4 | v7c |
|---|---|---|
| control | 0.612 | **0.928** |
| inkbleed L/M/H | 0.65/0.38/0.14 | **0.87/0.64/0.40** |
| paperdegrade L/M/H | 0.64/0.67/0.66 | **0.93/0.93/0.88** |
| perspective L/M/H | 0.57/0.59/0.51 | **0.90/0.90/0.87** |
| texcorrosion L/M/H | 0.31/0.17/0.10 | **0.66/0.45/0.28** |
| **TOTAL (23,103 crops)** | 0.4858 | **0.7700** |

**Clean guard (read-level, canonical seed-1, eval-only):** easy glyph
0.9009 → **0.9295**, easy exact (raw CNN chain) 19 → **34**/100 — v7c
beats both v4 and v7b on the easy chain; hard glyph 0.7908 → 0.8078,
hard exact 6 → 8.

## Use

- S54 (word-level reader): 10k word-context-labelled items with exact
  char_boxes for jointly-normalised whole-word crops; the inkbleed arm
  is a purpose-built hard case for fusion-surviving segmentation.
- v7c-class retrains: full-10k training available (the smoke used 3k of
  10k; deterministic rerun scales it).
- Cross-corpus transfer (train real10k → eval S53-corpus and vice
  versa) is the natural next measurement, not in this task's scope.

## Files

- `tools/gen_real_corpus.py` — the generator (deterministic, seed 42)
- `tools/s42_realism_probe.py` — sensitivity + seg-alignment receipt
- `reports/s42-real-corpus/` — sensitivity.json, v7c-train.json,
  v7c-read-probe.json, sample/ (13-image gallery + index)
- `models/glyphcnn-v7c.npz` + recipe — the training receipt
- `corpus/real10k/` — generated locally, gitignored (~205MB)
