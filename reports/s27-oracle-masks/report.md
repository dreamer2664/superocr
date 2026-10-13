# S27 — oracle masks on the six collapse families (t-20261013-3cae)

**Question (from S25).** The six families at ~0 (48/79 hard misses) fail at or
before the mask. How much of that wall is MASK-recoverable (ink survives;
only extraction fails) vs DEAD downstream (even a perfect mask cannot read it
through the unchanged pipeline)? This is the decision data for the room's
next move: better masks (classic, cheap) vs image-side recognition (ML).

**Oracles** (all replays bit-faithful via `rng_for(family, seed, index)` —
labels asserted against the suite manifest before reading):

- **spiderweb, cross-shadow, strippy, darts** — the degradation only
  overlays/dims; the degraded image minus its overlay IS the clean render.
  Oracle = the clean render fed through `baseline.read_text` UNCHANGED (its
  own mask stage on a real undegraded image). This is an UPPER bound on
  mask-recoverability — stronger than a perfect mask on the degraded image.
- **corrosion** — pits ERASE ink. Oracle = the heavy-stroke render minus the
  same pits (rng-replayed), with ONLY the mask stage replaced by ground truth
  (`_family_mask` patched per item, restored immediately); despeck/trim/
  deskew/segment/match all unchanged.
- **collage** — word cards built from scratch at ±9°. Same truth-mask
  treatment (rng-faithful clone of the card layout, binary).

**Two measurement bugs found and fixed along the way (kept for the record):**
(1) a pure 0/255 binary document is degenerate for the reader's own otsu —
the level lands at 0 and the mask comes out EMPTY (autocontrast restretches
any soft-gray attempt back to 0/255), hence the truth-mask patch instead of a
synthetic document; (2) a patch that outlived its item contaminated every
later read (first run's cross-family identical strings) — now restored
per-item.

## Result

| family | misses | oracle-exact | still-miss |
|---|---|---|---|
| strippy | 8 | 6 | 2 |
| spiderweb | 8 | 5 | 3 |
| cross-shadow | 8 | 5 | 3 |
| darts | 8 | 3 | 5 |
| collage | 8 | **0** | 8 |
| corrosion | 8 | **0** | 8 |
| **TOTAL** | **48** | **19** | **29** |

- **Mask-recoverable ceiling: 19/48** (upper bound — clean-render oracle,
  which also removes the pipeline's ~27% intrinsic glyph-error rate from the
  equation; a perfect mask on the real degraded images would do worse).
- **collage + corrosion: 0/16 even with truth masks.** The downstream is the
  blocker: rotated cards defeat the single-angle deskew (collage reads junk
  like `1HglQMgiEf`); heavy-stroke pitted glyphs defeat the templates
  (corrosion `GROVE ember` → `SPuiim ni5tS r`). No mask investment can buy
  these 16.
- Of the 29 still-misses, **0 are case-only** — all glyph-level (over-splits
  like `Wi l l ow SJWLACJYJT`, 1/I confusions like `PRA1RIE`).

## Verdict

- The "better masks, keep the classic pipeline" class of fixes has a measured
  ceiling of **+19 hard at the very most** (21 route + 2 S25 + 19 = 42/100 —
  still 53 short of the 95 bar), and the real achievable number is lower
  (mask extraction on degraded images is exactly the problem that has failed
  twice: S7c wall masks, auto-family routing).
- **collage and corrosion are dead to the classic pipeline entirely** — they
  need image-side recognition (native-raster CNN on rotated/pitted glyphs),
  consistent with S26's closure (digit identity dead under corrosion noise)
  and S25's mode table.
- The 95-bar is not reachable by any text-layer or mask-layer lever measured
  so far (S24, S25, S27). The remaining instrument is trained recognition of
  the degraded glyph itself.

## Files

- `tools/s27_oracle_masks.py` — oracle construction + measurement
- `reports/s27-oracle-masks/rows.jsonl` — per-item: want / oracle_got /
  oracle_exact / oracle_how / route_got
