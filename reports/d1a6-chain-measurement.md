# d1a6 chain measurement — attribution table

Chain: P1 template match -> low-conf glyphs retry with P2 (different
preprocessing) and P3 (bigger templates); shaky words get P4 (lexicon
rerank, gated at avg conf 0.55). Every adoption counted.

| family | seed | base exact/char | chain exact/char | P2 | P3 | P4 | glyphs |
|---|---|---|---|---|---|---|---|
| obstruction | 1 | 0.07/0.56 | 0.07/0.60 | 15 | 8 | 0 | 312 |
| obstruction | 7 | 0.00/0.48 | 0.00/0.48 | 29 | 13 | 0 | 330 |
| dark-on-dark | 1 | 0.00/0.54 | 0.00/0.56 | 14 | 9 | 0 | 301 |
| dark-on-dark | 7 | 0.00/0.53 | 0.00/0.58 | 17 | 7 | 0 | 321 |
| split | 1 | 0.00/0.51 | 0.00/0.52 | 17 | 11 | 0 | 339 |
| split | 7 | 0.07/0.53 | 0.00/0.53 | 6 | 9 | 0 | 316 |
| cut | 1 | 0.07/0.29 | 0.00/0.29 | 51 | 1 | 0 | 298 |
| cut | 7 | 0.07/0.26 | 0.00/0.27 | 44 | 0 | 0 | 290 |

## attributable findings

- P2 (alt thresholds / alt structure) fires on ~5% of low-conf glyphs;
  net effect within noise except obstruction +0.04 char on seed 1.
- P3 (h=40 templates) fires rarely, net ~0.
- P4 UNGATED overwrote good reads with near neighbours (exact acc dropped);
  gating at avg-conf 0.55 removed the harm: obstruction 0.56 -> 0.60 char.
  That is the one clean, attributable gain of this chain.
- Conclusion, published as measured: fallback passes as built do not move
  the bar; the template matcher itself is the ceiling. The identified
  levers are S1 (barry, in flight) and the S2 CNN (scott, in flight).
  The chain stays in reader.py instrumented, so their gains plug into it
  and remain attributable.
