# S15 — the x-height smalls: breakdown by sub-shape, and the wall named

Task `t-20261012-cf09` (marcus-aurelius). All numbers from the official
suite (seed 1, hash b2c460d2fb5a) benched against main `a7168d5b`
(baseline floor, family=None: easy 28/100, hard 9/100 — anchor reproduced
same session). Rules obeyed: cheap mask/decision levers only, no matcher
templates or CNN changes (scott's lane), bar-glyph case twins excluded
(barry's lane).

**Re-validation after #28/#29 landed (new main `17211ec`):** plain floor
re-benched this session — still easy 28 / hard 9, per-family table identical;
the margin survey below reproduces bit-for-bit on the new tree (254 wrong /
503 correct glyphs). Note for the record: the "28/11 floor" in the JOBS
refresh is the FAMILY-ROUTED baseline (`baseline.py --family {family}` via
bench_adapter, receipt `reports/20261012T091147Z-easy-hard.md` on commit
a77f8025); the PLAIN floor (family=None, the S11 "floor to beat") is 28/9.
Both are honest; they are different readers. This breakdown measures the
plain floor.

## 1. The residue, broken down by sub-shape

Levenshtein-aligned comparison of every failing item (easy 72 + hard 91):

- **hard: 471 substitutions, 420 deletions, 78 insertions.** The deletion
  number looks monstrous but is mostly alignment artefact: rebuilding the
  floor pipeline stage by stage on non-wall hard families shows piece counts
  EQUAL the label lengths (snow 14/14, split 19/19, cut 21/21, dod 20/20,
  stitch 25 pieces / 23 label). Real piece loss happens only in the wall
  families: spiderweb 11 pieces for 11 true glyphs collapsed to 3,
  collage 22 -> 7, cross-shadow 31 -> 9, darts 20 -> 11. That is
  mask/segmentation territory (S14-shaped), not a decision lever.
- **Non-wall hard substitutions scatter.** 255 aligned 1:1 substitution
  records spread over 100+ distinct pairs, the biggest cell x3
  (e->z, holes=3). No dominant remappable class exists. Expected-letter
  losses: e 39, r 35, l 27 (bar-glyph, barry's), o 22, n 22, a 21, t 19 —
  the x-height smalls as predicted by S13, now at sub-shape granularity:
  they are not one confusion, they are all of them at once.

## 2. Why no cheap lever moves it — the score surface is flat

Top-1 vs top-2 template margin for every hard glyph the floor emitted
(non-wall families, 254 wrong + 503 correct):

| margin | wrong glyphs | correct glyphs |
|---|---|---|
| < 0.01 | 73% | 90% |
| < 0.02 | 89% | 97% |
| < 0.05 | 100% | 100% |

EVERY hard-floor match — right or wrong — is a near-tie. Distortion
(pits, bands, strips, dim corners) degrades all template scores toward
the same noise floor, so the winner falls out of tie-break order. Hole
counts and aspect ratios were measured too: masks under distortion are too
fragmented for topology (hole counts scatter -1..5 with no class
signature). A decision rule cannot extract signal that is not in the
pieces; the information was destroyed upstream of scoring.

## 3. Verdict, honestly

The x-height smalls residue on the hard floor is **not a mask/decision
lever**. It is two walls already owned elsewhere:

1. **classifier/training-shaped** (scott's S10 lane): the matcher's score
   surface is flat under distortion; what breaks ties correctly is a net
   that saw the distortions — exactly the gated-CNN pattern barry proved
   worth +4 on easy. The same gate on hard is the natural next probe, but
   it is not cheap and not this lane.
2. **wall-family mask loss** (S14/segmentation lane): four families lose
   most glyphs before scoring; pericles' S14 collage route and the family
   masks already in reader.py are the levers there.

Nothing ships from S15 except this breakdown and the measurement tool
(`tools/s15_margins.py`, run receipts in this file's commit). The plain
floor stands at easy 28 / hard 9 (family-routed: 28 / 11); no number moved,
and the wall is named instead of rounded around.
