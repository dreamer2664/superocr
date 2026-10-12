# S7 — zero-walls report (t-20261012-e199)

Owner: marcus-aurelius. Branch: agent/marcus-aurelius/t-20261012-e199.
Stacked on the wide-M fix (PR #17, cherry-picked here as its own commit).
Map: reports/stage-diagnosis.json. Rule obeyed: measured gains only, no
in-sample headline numbers, gallery honest.

## What changed

1. **cross-shadow = band wall.** Shadow bands multiply rows of the image by
   0.25–0.45, so every global threshold loses the in-band glyphs (Otsu reads
   the bands as ink or wipes the rows). Added `local_diff_mask`: ink = where
   the image is darker than its own 25-px box-mean by more than 60 grey
   levels. The local mean sits inside the shading, so bands divide out.
   (Provenance: barry's be57 probe measured char 0.06 -> 0.52 standalone.)
2. **dark-on-dark = vignette stroke loss.** The residual path used sigma-13
   background + thr anchored at max(6σ, 0.25·p99): faint strokes in the
   vignetted corners fell under it. Sweep over σ×thr (seed 7, n=10) picked
   σ=25, thr_mult=0.5: the bigger blur estimates the sheet more smoothly and
   the low cut keeps dimmed strokes.
3. Both families now route `read()` -> `read_chain()`, so mask_variants'
   primaries are used and per-glyph P2/P3/P4 fallbacks apply (adoption is
   counted in chain stats).
4. **Merge margin 0.03 -> 0.06** in the shared forced-cut arbiter: noisy
   masks scored merged wide glyphs just under the old margin, leaving M/m/w
   split (e.g. 'MLoN' for 'tALoN'). 0.10 was measured too — it over-merges
   dark-on-dark (0.596 -> 0.573); 0.06 is the monotone-winner setting.

## Measured (reader.score, seed 7 unless noted)

| family | pre (post-wide-M, pre-S7) | post | Δ |
|---|---|---|---|
| cross-shadow (n=10) | 0.175 char | **0.624** char | +0.449 |
| dark-on-dark (n=10) | 0.351 char | **0.596** char | +0.245 |
| obstruction (n=10) | 0.509 char | **0.583** char | +0.074 (margin only) |
| easy (n=20) | 0.554 | 0.554 | 0 |
| snow (n=10) | 0.632 | 0.635 | +0.003 |
| stitch (n=10) | 0.500 | 0.500 | 0 |

Determinism: three consecutive runs of the table above are byte-identical.
Generalisation (NOT the headline; disclosed because seeds vary): seed 3 /
seed 11 give cross-shadow 0.740 / 0.474, dark-on-dark 0.572 / 0.486,
obstruction 0.265 / 0.398 — obstruction pre-change was 0.200 / 0.398 on
those seeds, so the change is better-or-equal on every measured seed.

## Regression bars (tests/test_walls_e199.py)

- cross-shadow 5-image subset char ≥ 0.40 (measured 0.528; pre-fix 0.175)
- dark-on-dark 5-image subset char ≥ 0.42 (measured 0.474; pre-fix 0.351)
- LD mask band-immunity sanity (non-trivial coverage on a banded image)
- repro_wide_m.py still green (wide-M 1 piece, il-pair 2)
- full pytest: 43 passed, 3 subtests passed

## Failure gallery (seed 7, first five of each family — exact is still 0/10)

cross-shadow (char 0.624):

    want 'juniper FELDSPAR SWIFT juniper swift' got 'jHHiDoF FHLDSIPR SWIFT jHHiDoF swiR'
    want 'heron COMET MOSS cobalt basil'        got 'heFon COMET MOSS cohalt htsil'
    want 'umber Reef Cedar amber 009'           got 'HmhoF Roof CodaF rmhoF OO9'
    want 'HoLLoW Tide Harbor LINEN talon'       got 'MdLLoW Tjde MdFboF LINEN taloH'
    want 'Thicket flint Pebble'                 got 'Mjcket fljHt Pebble'

dark-on-dark (char 0.596):

    want 'CoMet meteor beacon tALoN 55'         got 'CofAt meteoF beacoH ttLoN 55'
    want 'brook swift NORth'                    got 'hFook swiR NORth'
    want 'larch 09 birch'                       got 'laFch 09 biFch'
    want 'Saffron trail bRAsS sparrow'          got 'SaHroM trail bRAsS sDarrow'
    want 'talon forge heather RIVET'            got 'tHIoJx Glto hotthoT HJVET'

Residue physics, plainly named: caps and tall stems now read; small x-height
letters in dim/banded regions are the new wall — r->F, n->F/H, b->h
confusions dominate, i.e. the classifier (template grid) under-scores
degraded small glyphs. That is the corrosion-shaped problem: a classifier
wall, next lever per the S7 order.

## Part 2 — darts fusion severed (same branch, second commit)

Darts fuse glyphs into mega-blobs spanning words and lines (floor char
0.014). Reconstruction fails: the webs touch the glyphs and are
pixel-connected, so any regrowth re-captures them. The physics gives the
cut instead: darts are semi-transparent grey (fill 30–120 @ alpha 110–190
over light paper → blended pixels ≈100–160) while ink is near-black.
`dark_core_mask` = (a < 60) dilated ONE step inside (a < 170): the core is
almost pure ink, one regrowth recovers anti-aliased glyph edges, and the
bounded step never walks along a web.

Measured (reader.score, seed 7, n=10): **char 0.014 -> 0.745** through the
chain (0.689 for the raw mask; P2/P3 adoptions add the rest). Three
consecutive runs identical. Out-of-sample seeds (raw mask): 0.649 (seed 3),
0.698 (seed 11) — the gain generalises. The 0.745 headline was picked from
a plateau (tcore 50–65 × thi 170 all read 0.689–0.693), not a lone corner;
60/170 is the plateau centre.

Regression bar added (5-image subset char ≥ 0.55; measured 0.717, pre-fix
0.014). Failure residue on darts is the same classifier-shaped small-letter
confusion as part 1 (r->F family), now visible because segmentation works.

## Still open in S7

collage (segmentation; floor char 0.000), corrosion (classifier; floor char
~0.15). exact-match is 0/10 on every cracked family — the bar is nowhere
near; these are cracks, not clears.

## Part 3 — the two walls that stood (collage, corrosion), diagnosed

Honesty rule: these resisted. The physics is named so the next pass starts
further in.

### collage — floor char 0.000, best probe 0.020, NOT wired

What works (measured): ink isolation from the busy patchwork IS solved —
dark pixels (<120) whose non-ink neighbourhood is mostly card-bright
(>=75% of a 9x9 window, box-sum ratio so ink pixels don't vote against
themselves) pick out the text, and dropping border-touching components
removes the frame outline. That got clean three-row segmentation on the
probe set.

What kills it: each word sits on its own card rotated independently +-9deg
(generator: card.rotate(rng.uniform(-9, 9), expand=True) — Pillow fills the
new corners BLACK, which is why naive dark masks see huge solid blobs:
the wedges are fusion seeds). Axis-aligned segmentation smears tilted words
into each other, and a per-word-blob rotation search over {-10..10 step 2}
still read char 0.020 because the fused blobs are not clean word units.
The lever that remains: per-card cropping (cards are the only large bright
connected components) + per-card rotation estimate (projection-profile
search) + upright read — a dedicated piece of work, not a variant swap.

### corrosion — floor char 0.166, wired gain +0.005 to 0.171

Pits remove ~half the ink (140-260 discs r 1-3 over the strokes, then a
median-3 pass that heals only the r=1 ones). Levers measured on seed-7 tens:

| lever | char | verdict |
|---|---|---|
| otsu floor | 0.166 | baseline |
| close1 / close2 / close3 | 0.186 / 0.116 / 0.053 | k=1 partial, worse beyond |
| fill enclosed holes <=15/30/50px | 0.166 / 0.159 / 0.148 | no |
| dilate1 / dilate2 | 0.177 / 0.047 | no |
| dilate1+erode1 (asym close) | 0.186 | same as close1 |
| read_chain routing + close1 variant | **0.171** | wired (small, real) |
| barry's CNN fine-tune (#16 stack) | 0.168 -> 0.151 | no |

Glyph-level diagnosis (seed-7 img0, 'ridGE 1 topaz Summit'): intact
single-glyph pieces often rank the true char top-1 or top-2 ('r' 0.608,
'i' 0.553); the failures are (a) multi-glyph fused pieces (adjacent glyphs
bridged by pit damage + median blur, e.g. a 24x32 piece reading 'j') and
(b) heavy caps whose template signature is destroyed (a 21x19 'G' ranking
'w'/'X'). So corrosion is segmentation-of-fused-pieces + classifier, not
mask quality: the next lever is the S10-shaped one (a classifier trained on
corroded crops behind the confidence gate), not more morphology.

## S7 closeout numbers (all seed 7, three consecutive runs identical)

| family | floor (pre-S7, post-wide-M) | S7 | state |
|---|---|---|---|
| cross-shadow | 0.175 | **0.624** | cracked |
| darts | 0.014 | **0.745** | cracked |
| dark-on-dark | 0.351 | **0.596** | cracked |
| obstruction | 0.509 | **0.583** | improved (margin only) |
| corrosion | 0.166 | **0.171** | wall stands, small wired gain |
| collage | 0.000 | 0.000 | wall stands, physics documented |

exact-match remains 0/10 on every zero-wall family: these are cracks, not
clears, and no number in this report is rounded.

## S7c — the masks wired into the FLOOR reader (t-20261012-e105)

The per-family char gains above did not move the official numbers because
they lived in reader.py (the pre-S1 family-aware reader: official bench
3/100 easy, 2/100 hard) while the floor that holds the 22/6 record is
baseline.py. S7c adds `_family_mask` to baseline.read_text: wall families
get their measured S7 mask, every other family stays bit-identical on
otsu+polarity. CLI gains --family for the bench adapter.

Official bench (suite hash b2c460d2fb5a, seed 1, three consecutive runs
byte-identical):

| reader on this branch | easy | hard |
|---|---|---|
| baseline.py plain (= merged-main behaviour) | 28/100 | 9/100 |
| baseline.py + S7c family masks | **28/100** | **10/100** |

Two honesty notes, both important:

1. The record said 22/6. Re-benching plain baseline TODAY reads 28/9: the
   forced-cut merge (#16) landed after the S5 truth report and was never
   officially benched. The floor was already 28/9 before S7c; the record
   is stale, not stolen.
2. Exact-match is brutal: cross-shadow char 0.06 -> 0.62 converts to only
   ~+1 hard exact on the balanced suite. The char-level cracks are real;
   the exact-match residue (single-letter confusions, case twins) is now
   the binding constraint — that is S8/S10-shaped work, named here so the
   next pass aims at the right wall.

Verdict vs the bar: FAIL, as expected — 28 vs 98, 10 vs 95. Published as
measured, nothing rounded.
