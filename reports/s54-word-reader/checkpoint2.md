# S54 Checkpoint 2 — lex ceiling + context verdict (t-20261013-768c)

Same VAL split (S53 items 1600-1999, 1555 words), same oracle boxes as
C1. Diagnostics only. Files: `tools/s54_c2_lex_ceiling.py`,
`train_glyphs_v7.py` (+`--context-px`), `models/glyphcnn-v8-ctx3.npz`.

## C2a — the composition ceiling, decomposed

| metric | total | reading |
|---|---|---|
| composed (v7b @ truth boxes) | 0.537 | C1 baseline |
| composed, case-insensitive | 0.585 | case owns ~5 pts |
| **+ per-word lex (fix_token, shipping rules)** | **0.664** | **+12.7 pts free** |
| + lex, case-insensitive | 0.767 | letters-after-lex wall ~10 pts |

Per-family (+lex): rotation mild 0.93 / moderate 0.82 / severe 0.77 /
extreme 0.71; corrosion light 0.72 / medium 0.24 / heavy 0.18 / extreme
0.05; overlays 0.77/0.77; combined 0.56; control 0.84.

**The word-level lexicon is the single biggest measured lever on this
lane**: applying the SHIPPING lex rules per word at oracle boxes
converts one-glyph-error words into wins across every winnable family.

## C2b — wider word-context: NO-GO (fairly measured)

- v7 (word-only net) vs v7b (dual) at matched ±1px: 0.664 vs 0.664 +lex
  (lex-ci 0.776 vs 0.767) — no difference.
- v8-ctx3 (NEW net TRAINED on ±3px word-context crops, val 0.777 at
  ctx3): oracle word-read at matched ctx3 = composed 0.511 / +lex 0.654
  / lex-ci 0.764 — **does not beat ±1px**. Wider neighbour ink does not
  add letter identity, even in-distribution.
- (±3/±6 with ±1px-trained nets was out-of-distribution and not
  evidence; that is why v8 was trained.)

This confirms S31's read-level NO-GO at oracle level: glyph-crop context
is exhausted at ±1px.

## Where S54 stands after C2

The word-level reader's measured component stack:

1. **Word segmentation** (S56/achilles) — converts the 63/77 seg-miss
   residue; interface = C1 contract.
2. **Word-level lex projection** — +12.7 pts measured, available
   immediately once (1) exists; no training needed.
3. **Letter identity** — glyph-acc ~0.78; context exhausted (C2b);
   corrosion heavy/extreme walled at 0.22-0.41 (stroke destruction —
   data/restoration lane, not reader architecture).
4. **Case** — ~10 pts, closed lane (S55: random case_word; rules
   unreachable; re-confirmed by composed_ci vs composed).

Remaining word-model candidate: a TRUE whole-word architecture (jointly
normalised word image → position-pooled features → per-position output),
which is a different model class rather than glyph crops with context.
Whether its letter-identity gain over 0.78 glyph-acc justifies the build
is the C2c decision — the C2a/C2b evidence says the cheaper wins are
segmentation + lex first.

Read-level bar unchanged: hard >23/100, zero easy regression (73 floor),
per-family table, honest-no if missed.
