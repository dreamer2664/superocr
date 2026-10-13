# S26 — v3 digit identity under corrosion-grade noise (t-20261013-1efc)

Measures the gap S24 addendum 4 NAMED: digit-digit confusions on
corrosion-grade noise were unmeasured because the classic front end cannot
align real corrosion items (0/8 reads). Pericles' iris corrosion residuals
are exactly this population: corrosion-0002 (003→802: 0→8, 3→2),
corrosion-0005 (06→98: 0→9, 6→8).

## Method

`tools/s26_digit_corrosion_probe.py` clones `fam_corrosion` from
generator.py — same helpers (`_paper`/`_ink_color`/`_bg_color`/`load_font`),
same 640×180 canvas, heavy 6-offset stroke, 140–260 pits sampled on ink
pixels, paper-coloured patches, MedianFilter(3) — but renders
`make_label`-style FULL labels (2–5 words + forced digit group from the
generator's `_DIGIT_SHAPES`) and records exact per-char ink boxes at draw
time. Fidelity note: the first iteration rendered digit-strings alone; the
full pit budget on 1/6th of the ink destroyed 40% of chars — real items
share the pits across the whole label, so full labels are the honest
population. Two arms, identical rng stream (same font/size/position):
**corroded** (pits on) vs **control** (pits off, everything else identical).
Pieces go through the reader's own mask path (autocontrast → `_family_mask`
→ otsu fallback → despeck → trim; `_family_mask` returns None on real suite
items too — checked — so the fallback IS the real behaviour), cropped at
oracle boxes. Scoring: PieceCNN(glyphcnn-v3) native path. Segmentation is
out of scope (that is S25's lane).

## Results (seed 26000, 400 labels, 740 scored digit chars per arm, 66s)

| arm | digit acc | P(ok) | P(bad) | errors ≥0.9 conf |
|---|---|---|---|---|
| control (recipe, no pits) | **87.7%** (649/740) | 0.970 | 0.851 | 52/91 |
| corroded (+140–260 pits) | **34.7%** (257/740) | 0.927 | 0.836 | 252/483 |

Top corroded confusions: 0→t (44), 0→O (30), 0→Q (27), 0→4 (26), 0→S/6/G/9
(36), 9→2 (8), 6→4 (7), 1→i (7). Zero dominates: pits chop the thin ring
into arcs. Digit-digit confusions of the iris-residual kind (0→9, 9→2,
6→4) are present but the mass is digit→letter.

## Findings

1. **The digit lane on corrosion-grade noise is CLOSED for v3.** 34.7%
   identity at oracle boxes — worse than most heuristics, and the errors are
   confident (252/483 at prob ≥0.9; P(bad) mean 0.836 → no usable gate,
   same verdict as S24 addendum 6).
2. **NEW: the corrosion RECIPE ITSELF costs ~11 points before any pits.**
   Control 87.7% vs addendum-4's 98.4% digits on non-heavy-stroke families.
   Heavy stroke + median-3 collapses counters at size 26–40 (and DejaVu
   Sans Mono's dotted zero merges into an e-like bar). Per-font control:
   SansMono-Bold 98.8% / SansMono 97.8% vs Serif 79.0% / Sans 81.4%.
   Any engine reading corrosion items faces this render degradation, not
   just the pits — consistent with iris reading 0 as 8 (counter collapse).
3. For the iris side: digit-group residuals on corrosion should be treated
   as UNRECOVERABLE by crop-level re-scoring (v3 or anything trained on the
   same distribution). The honest levers are label-level: digit-group shape
   priors (%d/%02d/%03d/%d%d from the generator grammar) and lexicon
   context — not glyph identity.

## Caveats (named, not hidden)

- Oracle boxes: measures CNN identity only; segmentation on corrosion is
  S25/barry's lane and is the harder half.
- Fonts = this box's DejaVu set (8 faces). If the suite-generation box had
  different faces, absolute numbers shift; the control-vs-corroded delta
  (−53 points) is recipe-internal and robust.
- Synthetic clone of fam_corrosion, not real suite items (real corrosion
  items cannot be aligned — the reason this gap existed).
- Mask-binarised input is v3's native path; a grayscale-crop model could
  behave differently (unmeasured, out of scope).

Receipts: `reports/s26-digit-corrosion/probe-v1.{json,txt}` (commit
24b3266, weights sha256:3fd3e6d32a23, seed 26000, 66s).

The bar, for the record: easy ≥98/100, hard ≥95/100, three consecutive
runs, demo median ≤10s, clean-clone reproducible. This task moves no score;
it closes a lane and names a new degradation source.
