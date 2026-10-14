# S54 C2c preregistration — bounded whole-word prototype (t-20261013-768c)

Published BEFORE training per brasidas GO (DM 00:12 Oct 14). Comparator
and caps fixed here; deviations must be reported as deviations.

## Frame

Diagnostic frame identical to C1/C2: oracle WORD boxes stand in for word
segmentation (S56's job). At read/eval time the model receives ONLY the
jointly-normalised word crop (C1 contract: merged truth word box +3px
ink_mask, WORD_H=32, BILINEAR, aspect preserved). **No oracle glyph
positions, no glyph count, no per-glyph boxes at read time.** Truth
glyph boxes are used ONLY for training-data construction (allowed: GT
in training) and for the composed comparator.

## Data (cap)

- Source: frozen S53 hard2000 corpus ONLY (manifest sha256
  44b79be7ea90551a864689971184d91000499c7d4f81f6bc94fe251248f1372d,
  seed 53). No real10k (sits on unmerged #77; no branch mixing).
- Splits (by item, frozen):
  - TRAIN: items 0-1399 (word crops + labels; GT boxes allowed here)
  - DEV: items 1400-1599 (model selection, early stop, any tuning)
  - EVAL: items 1600-1999 = C1/C2 VAL (1555 words) — NEVER used for
    selection; single pass at the end, reported as-is.
- Augmentation budget: NONE beyond what the corpus generator already
  applies (degradation families are the augmentation). No extra affine/
  noise/elastic. If a run needs augmentation to compete, that is a
  finding, not a knob to hide.
- Max crop width 256px (longer tokens: right-crop, flagged in report;
  expected rare).

## Model (cap)

- Architecture: small CNN over the whole word crop (32×W grayscale) →
  feature map → per-x-position softmax over ALPHABET+blank (ALPHABET =
  the 62 shipped glyph classes) → CTC decode (greedy collapse).
  No LSTM in v0 (keeps the numpy trainer tractable and the runtime cap
  honest); LSTM is a named v1 extension only if v0 clears the bar.
- Parameters budget: ≤ 400k (comparable to v7b ~330k).
- CTC loss: standard forward-backward, implemented in-repo (numpy),
  unit-checked against a hand-computed 2-step example before training.

## Runtime (cap)

- Single training run ≤ 30 minutes wall on the night sandbox (typical
  v7 run: ~5 min). Max 3 runs TOTAL for v0 (selection on DEV only).
- Smoke mode mandatory before any full run: 20 optimisation steps on
  64 crops, loss must decrease and decode must emit ≤ 3 distinct
  symbols on ≥ 1 crop (sanity that gradients flow).

## Success bar (named BEFORE training)

Primary: **word-exact+lex on EVAL > 0.664** (the composed+lex
comparator, C2a) with the per-family table showing no family below
composed+lex by more than 5 points. Secondary (informational):
lex-ci vs 0.767.

If the bar is missed: honest NO-GO on the whole-word lane at v0 scale,
receipts published; the word-reader recommendation stands at
seg (S56) + word-level lex + case-closed.

Read-level bar unchanged and NOT claimed by C2c: hard >23/100, zero
easy regression (73 floor) — that requires S56 integration and the
3-run non-regression protocol, out of scope here.

## Comparators on EVAL (fixed by C2a, same words)

composed 0.537 / composed-ci 0.585 / composed+lex 0.664 / lex-ci 0.767.
Per-family table from c2_lex_ceiling.json is the reference.

## Deliverables

1. tools/s54_c2c_word_model.py (data prep + model + CTC + smoke/train/eval)
2. models/s54-c2c-word-v0.npz + recipe (only if trained)
3. reports/s54-word-reader/c2c_result.{json,md} (EVAL single-pass,
   per-family table, honest verdict vs bar)
