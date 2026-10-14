# S54 receipt refresh — post-S55 lex band (2026-10-14, closeout)

The C1/C2a/C2c receipts were measured before S55's +1 lex-band widening
(39ce621, PR #76) merged to main. This closeout re-ran every receipt on
the rebased branch (current main @9ab638a) so the PR carries numbers
valid at review time. Nothing else changed: corpus, v7b weights, and
all S54 tools are identical.

## Re-verification results (VAL items 1600+, 1555 words)

| receipt | committed (pre-S55) | re-run (post-S55) | note |
|---|---|---|---|
| corpus manifest | 44b79be7…f1372d | 44b79be7…f1372d | bit-identical (frozen S53) |
| C1 composed word-exact | 0.537 | 0.537 (835/1555) | identical |
| C1 glyph-acc | 0.783 | 0.7832 | identical |
| C2a composed / ci | 0.537 / 0.585 | 0.537 / 0.585 | identical (lex not involved) |
| **C2a +lex / lex-ci** | **0.664 / 0.767** | **0.682 / 0.799** | **S55 band: +1.8 / +3.2 pts** |
| C2c v0 +lex / lex-ci (frozen run-3 weights) | 0.436 / 0.482 | 0.460 / 0.518 | same shift, both sides |

## What changes and what doesn't

- **Stronger, not weaker**: the word-level lex recommendation improves —
  with the merged S55 band, applying shipping lex per word at oracle
  word boxes is worth **+14.5 points** over composed (0.537 → 0.682),
  up from +12.7 at measurement time.
- **C2c verdict unchanged**: the whole-word v0 comparator and the v0
  model both benefit from the band widening; the gap is 22.2 pts
  (0.682 vs 0.460) vs 22.8 pts pre-S55. NO-GO stands, further away if
  anything.
- C2b (context NO-GO) is lex-independent (composed metric only) and is
  untouched by S55.

The regenerated `c2_lex_ceiling.json` / `c2c_result.json` in this commit
carry the post-S55 numbers; the original pre-S55 values are preserved in
`checkpoint2.md` / `c2c_result.md` and the git history.
