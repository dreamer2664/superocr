# S54 Checkpoint 1 — word-crop contract + oracle ceiling (t-20261013-768c)

**Status: runnable checkpoint delivered. Diagnostics only — no reader
change, nothing ships from this file.** Tool: `tools/s54_word_crops.py`
@ c032473+; frozen S53 regenerated bit-identical (manifest
`44b79be7ea90551a`); numbers on the held-out VAL split (items 1600-1999,
400 items, 1555 words); canonical suites untouched.

## 1. The word-crop contract (for achilles's S56 segmenter)

- Word crop = axis-aligned bbox of one truth word's `char_boxes`
  (min x0, max x1, min y0, max y1) + 3px context, cut from the reader's
  own `ink_mask` front end.
- Jointly normalised: whole word scaled to height 32px, BILINEAR, aspect
  preserved (one scale for all glyphs — "advances-vs-ink semantics fixed
  once"); per-glyph truth x-offsets recomputed inside the crop.
- Label = the space-split token; spaces known at word level by
  construction.
- 24 sample crops + index: `reports/s54-word-reader/sample/`.

## 2. Oracle word-read ceiling (v7b at truth boxes, ±1px, no lexicon)

| family | word-exact | glyph-acc |
|---|---|---|
| control (undegraded) | 64/82 = **0.780** | 0.931 |
| corrosion light → medium → heavy → extreme | 0.475 / 0.054 / 0.042 / **0.000** | 0.828 / 0.530 / 0.409 / 0.218 |
| rotation mild → extreme | 0.810 → 0.583 | 0.952 → 0.837 |
| overlay light / heavy | 0.647 / 0.677 | 0.866 / 0.864 |
| combined (2-3 stacked) | 0.337 | 0.693 |
| **TOTAL** | **835/1555 = 0.537** | 0.783 |

## 3. What the ceiling says (hypotheses fixed before any training)

1. **The classifier, not segmentation, caps the readable bands.** Even
   with PERFECT word boxes, clean-control words read at only 78%
   (0.931^~6.5 composed) — solo-glyph opinions multiply away. A word
   model must lift per-glyph identity via word context to justify
   itself: **C2 bar = beat 0.537 total and the per-family table above on
   this exact split**, not just beat the shipping route.
2. **Corrosion heavy/extreme is classifier-walled** (glyph-acc 0.41/0.22
   with perfect boxes — stroke destruction, matching S30/S35). No
   segmentation work and no word context fixes 0.22; that band needs
   restoration or heavier training data (real10k's texcorrosion, PR
   #77).
3. **Rotation and overlays are the word-reader's winnable bands**:
   glyph-acc 0.84-0.95 and 0.86 — composed word-exact already 58-81% /
   65-68% with oracle boxes; a word model + real word segmentation has
   genuine headroom to convert.
4. **The read-level bar stays as pre-registered**: shipping-route hard
   exact > 23/100 with zero easy regression (73/100 floor), per-family
   table, honest-no if missed. Oracle numbers are NOT reader results.

## 4. Coverage (the corpus decision)

- S53 (frozen): corrosion ×4, rotation ×4, 4 overlay families ×2,
  combined, control — covers 4 of the 5 wall-family mechanics
  (corrosion, cross-shadow, darts, strippy) + uniform rotation.
- real10k (PR #77, unmerged): texcorrosion/paperdegrade/perspective/
  inkbleed — adds the touching-glyph (inkbleed) and warp (perspective)
  bands. Lands when #77 merges.
- **Collage (per-word DIFFERENTIAL rotation on cards) is in NEITHER
  corpus** — the one wall family with no training coverage. Options:
  corpus-v2 with card-rotation items + per-card transformed boxes (the
  advance-box machinery needs per-card rotation handling), or accept and
  document the gap. Decision needed from brasidas/achilles; v2 generator
  is a bounded add-on to `gen_real_corpus.py` (same infrastructure).

## 5. Next (queued)

- C2: word-model candidate on the contract above (word-image →
  per-position glyph opinions with joint normalisation), measured
  against the C1 composition ceiling on the same split; comparator =
  composition + per-word lexicon repair (to be measured too).
- Ledger review t-20261013-367d / PR #53: queued per brasidas's order,
  after this checkpoint.
- S56 interface: contract above is the spec achilles's segmenter should
  emit (word boxes + per-glyph x-offsets optional).
