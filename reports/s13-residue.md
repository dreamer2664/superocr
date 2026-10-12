# S13 — the dark-on-dark resolution + the small-letter residue, quantified

Task `t-20261012-44c0` (marcus-aurelius). All numbers from the official
suite (seed 1, hash b2c460d2fb5a) and its committed bench reports; nothing
rounded, everything reproducible from a clean clone.

## (a) dark-on-dark: resolved by un-wiring, measured item by item

S7c rev-1 wired the sigma-25 mask into the floor and dropped the dod cell
2/8 -> 1/8 (dod-0001 -> 'HazH...'). Rev-2 (PR #28) pulled the mask from the
floor dispatch; this section proves that is the final state.

Sweep through the EXACT bench pipeline (baseline.read_text per suite image,
53 variants: sigma {13,16,18,20,22,25,26,28,30,40} x thr_mult
{0.3,0.4,0.42,0.46,0.5,0.54,0.58,0.6,0.7} plus band-pass residuals
(8-30, 13-40, 20-60)):

| variant class | best exact on dod-8 | dod-0001 | floor items kept/lost |
|---|---|---|---|
| floor otsu+polarity (rev-2 ships) | **2/8**, char 0.731 | **EXACT** | — |
| sigma-25 family (S7's winner on seed-7 samples) | 0/8 | miss | — |
| best of the 53-variant sweep (sigma 13/16, thr 0.5-0.7) | 2/8, char 0.727 | EXACT | 2/0 — ties the floor, never beats it |

No mask variant beats the floor on the official eight; the seed-7 generator
sample that won S7 (char 0.351 -> 0.596) does not transfer to the seed-1
official suite — a sample mismatch, named here so nobody re-runs this sweep.
The sigma-25 mask stays wired in reader.py (family chain) for the record.
dod-0001 reads exact under the floor: 'walrus BrooK cOmeT Penguin Hazel'.
Regression lock: tests/test_s13_dod.py pins exactly that through
baseline.read_text, regenerated in-process from the generator (seed 1,
index 1 — byte-match to suite item dod-0001 verified).

## (b) the small-letter residue, quantified (hard 89 + easy 60 failures)

From the rev-2 three-run bench report (20261012T091147Z), naive aligned
comparison of expected vs read across all 113 failing items: 1,062
char-level mismatches. The binding residue, by count:

| confusion class | top pairs (expected -> got) | count |
|---|---|---|
| bar-glyph case/shape (l/i/L/I/1) | l->i x19, I->i x7, L->I x5, c->C x4 | **35** |
| x-height smalls (the S7 wall) | r->a x8, r->o x7, a->r x7, o->n x6, e->n x6, e->l/t/r x15, a->l/I/B x18 | **75+** |
| caps under distortion | E->T x5, R->n x4 | 9 |

(Counts are lower bounds: insertion/deletion errors shift the alignment.)

Failures by family: easy 60, spiderweb 6, split 6, strippy 6, collage 6,
corrosion 6, snow 5, stitch 5, darts 5, cut 4, obstruction 4. Item ids are
in the bench reports next to this file.

## (c) levers, honestly assessed

- The bar-glyph class (35) is case-twin policy: barry's S8 lane, handed
  over with these counts. scott's S10b datum already says geometry beats
  the classifier on case; l/i additionally needs a dot detector (i/j), and
  L/I a height-vs-cap rule that survives dim masks.
- The x-height smalls (75+) are the classifier-shaped wall named in S7:
  r/o/e/a/n confuse because pits, bands and dim corners destroy the exact
  stroke topology the templates score. That is S10-shaped (training-side),
  not a mask-layer lever; nothing cheap measured here.
- No code ships from S13 beyond the dod regression lock: every candidate
  lever was either another agent's lane or measured flat. The floor stands
  at easy 28/100, hard 11/100 pending PR #28's merge.

## (d) ledger absorptions (post-S13, appended as they are named)

- **2026-10-12 — snow-0001** ('beacon ISLAND jAspEr PLUME', snow family):
  the one hard item the S8 easy ladder traded away. barry's wave 6
  (band-gated thin otsu, #27 head ef6f180) moved easy 51 -> 54 and hard
  13 -> 12; barry's commit message flagged the -1 for this ledger, and
  scott's item-level second look names the cell as snow-0001 (the
  wave-3/4-vs-head attribution on the PR: main 9 -> wave 3/4 13 -> head 12).
  Note the sources diverge on the family — barry's commit message guessed
  'a single obstruction-family read' while scott's item-level delta names
  snow-0001; the item-level attribution is the one recorded here.
  Absorbed so the hard-side residue table counts it: one exact lost
  on the snow family, paid for +3 easy exacts, disclosed by the author in
  the same breath as the gain. sha-bound: ef6f180.
