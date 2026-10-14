# S54 C2c result — whole-word v0: NO-GO (t-20261013-768c)

Preregistered protocol: `c2c_protocol.md` (published @e954bb5 BEFORE
training). Bar: word-exact+lex > 0.664 on EVAL (items 1600+, 1555
words), no family −5 pts vs composed+lex. Caps respected: S53 data
only, no extra augmentation, 45k params, 3 runs total, ≤30 min each.

## Runs (all three, as preregistered)

| run | lr | epochs | best DEV +lex |
|---|---|---|---|
| 1 | 1e-3 | 4 | 0.000 (all-blank CTC plateau) |
| 2 | 3e-3 | 10 | 0.385 @ ep 9 (plateau broken) |
| 3 | 3e-3 | 18 | 0.459 @ ep 15 (saved weights) |

## EVAL single pass (never used for selection)

| metric | whole-word v0 | composed (C2a) | gap |
|---|---|---|---|
| word-exact | 0.194 | 0.537 | −34.3 |
| **+lex** | **0.436** | **0.664** | **−22.8** |
| lex-ci | 0.482 | 0.767 | −28.5 |

Per-family (+lex, v0 vs composed+lex): control 0.634 vs 0.842;
corrosion light/medium/heavy/extreme 0.313/0.011/0.010/0.000 vs
0.717/0.239/0.177/0.053; overlays 0.626/0.640 vs 0.768/0.772;
rotation mild→extreme 0.595/0.549/0.333/0.155 vs
0.929/0.817/0.770/0.714; combined 0.258 vs 0.562. **Every family
below the comparator.** JSON: `c2c_result.json`.

## Verdict

**NO-GO at v0 scale.** The bar is missed by 22.8 points and the
per-family guard fails everywhere. The whole-word CNN+CTC (no
recurrence — protocol cap) is uniformly dominated by v7b reading
per-glyph crops at truth boxes: the per-glyph crop's dedicated
normalisation (each glyph centred in its own 32×32 field) is a strong
inductive bias the jointly-normalised word image does not give the
v0 head, whose per-x features see ~14 px of context with a single
linear classifier.

Honest caveats (do not read as promises): the DEV curve was still
creeping at the 18-epoch cap (0.459, non-monotone 0.405→0.459→0.433);
the protocol named LSTM as the only v1 extension. Whether v1 scale
(LSTM + real10k data + longer training) closes 23 points is UNKNOWN
and untested; nothing here licenses spending that budget without a
new preregistration.

## Where S54 stands (final recommendation unchanged)

The word-level reader's measured stack remains:
1. word segmentation (S56/achilles, C1 contract published),
2. word-level lex projection (+12.7 pts measured at oracle, free),
3. letter identity via per-glyph v7b (glyph-acc 0.783; context
   exhausted at ±1 px per C2b),
4. case closed (S55).

Artifacts: `tools/s54_c2c_word_model.py` (numpy CNN + scaled CTC,
brute-force-verified), `models/s54-c2c-word-v0.npz` (run-3 best-DEV
weights), train logs `c2c_train_run{1,2,3}.log`.
