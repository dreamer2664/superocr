# S30 — v7/v7b: corpus retrain of glyphcnn (t-20261013-6d08)

**Lineage.** v5 (de-rotation-aware augs) failed the staged bar; v6
(synthetic word-context rendering) was lost before its first run, but its
postmortem stands: textlength advance boxes include 1-2 px of neighbour
ink, every adjacent pair overlaps after rotation, and solo-glyph training
never sees read-time crop semantics. The S53 corpus (PR #66) carries
per-char truth boxes on 2000 already-degraded sheets — so v7 trains on
exactly what a reader-side classifier sees.

**Protocol (binding, per reports/s53-hard-corpus/report.md).** Corpus
split by item index: train 0-1599, val 1600-1999 (stratified ~80/20 per
arm, verified). Canonical suites (seed 1) used EVAL-ONLY. Class cap
800/train (corpus labels are natural words: 11..2897/class raw).
Fine-tune from glyphcnn-v4, 10 epochs, batch 128, lr 5e-4 → 1e-4 cosine,
seed 7. All deterministic.

## v7 — word-context only (NEGATIVE result, kept honest)

Crops = truth advance-box ±1 px through the reader's ink mask. Held-out
val 0.3126 → **0.7865**; control 0.42 → 0.94. But the clean guard
FAILED: through the floor's tight solo pieces, canonical-easy glyph acc
**0.90 (v4) → 0.70 (v7)**. Crop semantics must match at BOTH ends — the
v6 lesson is symmetric. Receipts: `reports/s30-v7/`.

## v7b — dual distribution (word + tight)

Same run plus the floor's own segmented pieces aligned to truth chars
(corrosion_cnn's harvest, honest count-mismatch skips: 1359 item-skips
across 2000 items — heavy degradation breaks piece counts). 28,277 train
crops.

### Held-out corpus val, per severity (crop-level top-1)

| cell | v4 | v7b |
|---|---|---|
| control (undegraded) | 0.598 | **0.902** |
| corrosion light / medium / heavy / extreme | 0.31/0.20/0.12/0.06 | **0.79/0.50/0.41/0.22** |
| rotation mild → extreme | 0.64/0.59/0.49/0.47 | **0.96/0.93/0.89/0.85** |
| overlay light / heavy | 0.49/0.44 | **0.87/0.86** |
| combined (2-3 stacked) | 0.252 | **0.652** |
| **TOTAL** | 0.4334 | **0.7998** |

### Read-level through floor segmentation (canonical seed-1, eval-only)

| metric | v4 | v7b |
|---|---|---|
| easy glyph acc (aligned) | 0.9009 | **0.9235** |
| easy exact (raw CNN chain, no lex) | 19/100 | **31/100** |
| hard glyph acc (aligned) | 0.7908 | **0.8095** |
| hard exact (raw CNN chain) | 6/100 | 7/100 |

## Verdict (honest)

- **Clean guard PASSED**: 0.9235 ≥ 0.90 — and v7b beats v4 on it, so the
  dual-distribution retrain is a strict improvement, no regression.
- **Crop-level**: every severity cell improves, most by 2-4x. Rotation
  arm 0.85-0.96 ≈ the old de-rotated bar (0.85) now met WITHOUT
  de-rotation; corrosion medium 0.50 approaches the 0.60 target; heavy
  (0.41) and extreme (0.22) still short — those pits (210-650) destroy
  stroke identity at the pixel level and likely need restoration (S20
  lane) or heavier augmentation, not more of the same data.
- **Read-level hard exact barely moves** (6→7): the raw CNN chain has no
  lexicon/projection/case-repair — read-level hard gains must come from
  wiring v7b into a lexicon path or the word-context-cropping reader
  (next iteration), not from the classifier alone.
- The staged bar (derot ≥0.85, corroded ≥0.60) is **met at crop level on
  rotation, partially on corrosion**; v7b does not ship into the reader
  path on its own numbers, but it is the new best CNN checkpoint for any
  integration experiment (beats v4 on every distribution measured).

## Files

- `tools/train_glyphs_v7.py` — trainer (`--modes word,tight --cap 800`)
- `tools/s30_v7_read_probe.py` — read-level v4-vs-v7 probe (floor seg)
- `models/glyphcnn-v7.npz` (word-only, clean-guard FAIL) and
  `models/glyphcnn-v7b.npz` (dual, candidate) + recipes
- `reports/s30-v7/`, `reports/s30-v7b/` — per-severity + read-probe JSON
