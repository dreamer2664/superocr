# S6 — fallback: combine, augment, self-train (t-20261011-00c0)

The task card: *"Only if the bar is not met by S1-S3: combine readers,
search augmentations, use unlabelled hard images for self-training.
Document what each added, with numbers."* The bar was not met, so all
three levers were pulled and measured. Every number below is produced by
a tool in this PR, from committed weights, on a deterministic seed —
rerun commands are at the bottom.

Unless stated otherwise: **13 families × 10 images each, seed 7, classic
floor as reference** (the same seed/count shape as `reports/baseline-floor.*`).

## Phase 1 — combine readers (tools/ensemble_select.py)

Three chains, measured per family: the classic floor, main `reader.py`'s
family dispatcher (`strategy`), and the committed glyph CNN (`cnn`).

| family | classic | strategy | cnn | combine picks |
|---|---|---|---|---|
| easy | 40 | 0 | 20 | classic |
| snow | 20 | 0 | 20 | classic |
| spiderweb | 10 | 0 | 0 | classic |
| split | 30 | 0 | 10 | classic |
| stitch | 10 | 10 | 10 | classic (tie) |
| strippy | 0 | 0 | 0 | cnn (char tie) |
| cut | 30 | 0 | 10 | classic |
| collage | 0 | 0 | 0 | classic |
| corrosion | 0 | 0 | 0 | classic |
| cross-shadow | 0 | 0 | 0 | cnn (char tie) |
| darts | 0 | 0 | 0 | cnn (char tie) |
| obstruction | 10 | 0 | 20 | cnn |
| dark-on-dark | 0 | 0 | 10 | cnn |

Best-of-combined **13.1%** exact vs floor-alone 11.5% → **+1.6 points**,
entirely from the CNN on obstruction/dark-on-dark. The strategy chains
contribute only a tie on stitch and trail the floor even on easy — the
dispatcher adds nothing measurable at these settings.
Full table: `reports/ensemble-select.json`.

## Phase 2 — search augmentations (tools/augment_search.py)

Eight deterministic image transforms applied before the classic reader;

| family | identity | autocontrast | equalize | sharpen | median3 | thr176 | thr140 | invert | pick |
|---|---|---|---|---|---|---|---|---|---|
| easy | 40 | 40 | 40 | **60** | 40 | 30 | 40 | 0 | sharpen |
| snow | 20 | 20 | 0 | 0 | 20 | 20 | 20 | 0 | identity |
| spiderweb | 10 | 10 | 0 | 0 | 20 | 0 | **50** | 0 | thr140 |
| split | 30 | 30 | 0 | 30 | 20 | 30 | 30 | 0 | identity |
| stitch | 10 | 10 | 0 | 0 | 10 | 0 | 10 | 0 | identity |
| strippy | 0 | 0 | 0 | 0 | 0 | **10** | 0 | 0 | thr176 |
| cut | 30 | 30 | 0 | 30 | 10 | 20 | 30 | 0 | identity |
| collage | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | identity |
| corrosion | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | identity |
| cross-shadow | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | identity |
| darts | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | identity |
| obstruction | 10 | 10 | 0 | 10 | 10 | 0 | 10 | 0 | identity |
| dark-on-dark | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | identity |

Best-augmented **16.9%** vs 11.5% → **+5.4 points** (spiderweb +40 from a
lower threshold, easy +20 from sharpen, strippy +10 from a higher one).
`invert` helps no family at all. Five families (collage, corrosion,
cross-shadow, darts, dark-on-dark) stay at 0% under every transform —
the wall is distractor multiplicity/layout, not contrast.
Full table: `reports/augment-search.json`.

## Phase 3 — self-train on unlabelled hard images (tools/selftrain_cnn.py)

12 unlabelled hard images/family (seed 71) → 1,967 segmented glyphs →
1,077 kept at softmax ≥ 0.92. Audit against the discarded true labels:
**90.6% of kept pseudo-labels were actually correct** (confidence works).
Fine-tuned a copy of the committed net for 2 epochs on pseudo-labels only,
then re-read the held-out labelled suite (seed 7):

- seed 7: easy flat, snow +20, strippy +20, obstruction +10 → **+3.8 points**
  (7.7% → 11.5%)
- seed 3 replication: **+0.8 points** (8.5% → 9.2%), with easy −10 on
  that seed

Direction is real (positive on both seeds) but small and not stable
enough to ship as weights — the report ships the tool and the numbers,
**not** a second weights file. `--save` exists for whoever has a better
pseudo-label source.
Reports: `reports/selftrain.json` (seed 7).

## Verdict, honestly

| lever | exact gain | call |
|---|---|---|
| combine readers | +1.6 points | technique sound, chains too weak — no mechanism worth shipping |
| augmentations | +5.4 points | real but family-specific; three families move, five are at a hard 0 |
| self-training | +3.8 / +0.8 by seed | direction good, magnitude + stability too small to ship weights |

Stacking all three levers lands around ~20–25% exact on this suite shape,
**far from the 98/95 bar**. S6 as worded is exhausted: the remaining
distance is not in combining or preprocessing what we have — it needs a
reader that solves the zero-wall families' layout/distractor problems,
which these levers demonstrably do not touch.

## Reproduce

```bash
python3 tools/ensemble_select.py --count 10 --seed 7 --out reports/ensemble-select.json
python3 tools/augment_search.py --count 10 --seed 7 --out reports/augment-search.json
python3 tools/selftrain_cnn.py --out reports/selftrain.json
python3 tools/selftrain_cnn.py --seed-eval 3 --out /tmp/selftrain-seed3.json
```
