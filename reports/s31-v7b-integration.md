# S31 — v7b reader integration: both levers measured, both NO-GO as patches

**Owner:** barry · **Task:** `t-20261013-becc` · **Date:** 13 October 2026 (afternoon)
**Base:** stacked on v7b head `3bfbde4` (PR #67 — merge #67 first; this PR adds
probe tools + rows + this report only, zero reader-path change).

## Verdict

The two integration levers named in the task were built and measured
separately on canonical seed-1 (eval-only, dir hash `b2c460d2fb5a8f83…`
re-verified). **Neither moves the shipping number upward; both lose or tie.**

| lever | change | easy | hard | verdict |
|---|---|---:|---:|---|
| control (shipping route) | — | 73 | 23 | reference (OFF gates PASS in both probes) |
| **L2** weights-in-slot | v7b replaces v2 behind the existing rerank gates | **70 (−3)** | **24 (+1)** | NO-GO |
| **L1** context windows | floor's own pieces, ±K px context crops at read time, v7b | K1: **31/100 (=)**, **6/100 (−1)** raw chain · K2: **23 (−8)**, **5 (−2)** | NO-GO |

(Shipping-route numbers include `fix_line`; L1 raw-chain numbers do not, and
its control arm reproduces S30's read-probe exactly — easy 31, hard 7 — so
the harness is the floor, not an approximation.)

Read-level conclusion: the v7-word-context crop gains (corpus val 0.79 vs
solo 0.70) **do not transfer through read-time context windows.** The
remaining upside inside the CNN lane is a reader-side redesign (net
consumes whole-word or jointly-normalised crops), which is a new project,
not a patch. The bar route stays: trained recognizer + redesigned reader
interface, or the S20-class upstream/restoration lanes.

## Lever 2 (`tools/s31_v7b_slot_probe.py`, rows [`s31-slot-rows.jsonl`](s31-slot-rows.jsonl))

Same floor, same gates (margin 0.01 / conf 0.85, stem always), same
`fix_line` — only the CNN opinion's weights differ
(`baseline._CNN = GlyphCNN.load("models/glyphcnn-v7b.npz")` injected in the
probe process; tree untouched).

- OFF gate: easy **73/100**, hard **23/100** — the settled line, exactly.
- v7b-slot: easy **70/100**, hard **24/100**.
- Flips: gained `obstruction-0003`; lost `easy-0004`, `easy-0082`,
  `easy-0092`. All three easy losses are rerank-margin case/glyph orders
  where v2's calibration inside the existing gates walks the read back to
  ground truth and v7b's opinion doesn't. A weights swap without
  re-calibrating the gates loses more calibrated rescues than it wins.

## Lever 1 (`tools/s31_v7b_context_probe.py`, rows [`s31-ctx-rows.jsonl`](s31-ctx-rows.jsonl))

One variable isolated: the pieces are the floor's own, bit-exact
(`corrosion_cnn.floor_pieces`, 800-item control reproduces S30 exactly);
only the crop window changes, box = placed location ±K on all four sides.
Placement: exact (row,col) equality search in the mask; **10,713 placed,
57 virtual** (merge_forced's abut-aligned packs have no exact sheet
location — they are disclosed and receive the tight crop in every arm, a
small common-mode conservatism, never a false positive).

| arm | easy exact | hard exact | easy char | hard char |
|---|---:|---:|---:|---:|
| ctrl-v7b-K0 (literal S30) | 31 | 7 | 0.745 | 0.330 |
| ctx-v7b-K1 | 31 | 6 | 0.742 | 0.329 |
| ctx-v7b-K2 | 23 | 5 | 0.722 | 0.327 |
| ctx-v4-K1 (contrast) | 17 | 6 | 0.724 | 0.320 |

- K1 is neutral (−1 flip: split-0002, noise scale). K2 actively hurts
  (−8 easy: eleven flips down, one up). More context = more neighbour
  strokes = more confusion — the opposite of the training-time effect.
- The v4 contrast arm collapses (−14 easy): v7b tolerates context better
  than v4 (as its training would predict) — so the direction is real, the
  magnitude is just worthless at read level.

Why it doesn't transfer (mechanism reading, consistent with the v6/v7
postmortems): training crops were **truth advance-boxes** — font-geometry
windows whose edges usually fall in gaps or skim neighbours; read-time
windows grown from **floor ink-bounds pieces** cut through neighbour strokes
mid-glyph on fused lines — the hard suite's exact pathology. The nets see
different "context" than they trained on, again. Second cause: on the
families that fail, segmentation already broke (63/77 = 82% of the residue,
leonidas's S43 census) — there is no intact piece to give context to.

## What this closes / what stays open

- Closes: weights-swap-of-the-day integrations for v7b; context-window
  patch readers for the current chain. This pairs with S51 (CLAHE no),
  S30 read-level (net alone no), S43 (segmentation owns the residue).
- Open (not this task): a word-level reader interface over v7b-class nets
  (whole-word crops, jointly normalised — needs new segmentation that
  survives the five walls); S20-class stroke restoration upstream of the
  floor. Both are project-scale and belong in fresh tasks with their own
  held-out protocols.

## Repro

```
python3 tools/s31_v7b_slot_probe.py    --suites <seed1> --out s31-slot-rows.jsonl   # ~15 min
python3 tools/s31_v7b_context_probe.py --suites <seed1> --out s31-ctx-rows.jsonl    # ~2 min
```

Both write per-item rows; the tables above are derived from the committed
copies. Deterministic reader + deterministic transforms -> item-diff 0
under re-run, same property class as s22-3x-settled.
