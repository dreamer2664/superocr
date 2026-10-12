# cross-shadow: root cause found, exactly the wide M (t-20261011-be57, part 2)

Continuation of reports/zero-wall-attack.md. All numbers seed 7, 10/family.

## What the stage map said, and what it missed

stage_diagnosis.py scored cross-shadow as SEGMENTATION failure
(seg/true 0.81 under the floor's otsu path): shadow bands multiply paper
down ×0.25–0.45, the global threshold loses in-band glyphs. True — but
only half the story.

**Part 1 — a local-contrast binarisation recovers the bands.**
`diff = boxmean(img, r=25) − img > 60` (numpy integral-image box blur) is
band-immune; measured standalone on the family: exact 2/10, **char 0.06 →
0.52**. The masks it produces are visually clean even on the heaviest-band
image of the set (see probe evidence in PR discussion; masks saved to
/tmp during investigation).
Variants measured and rejected: threshold sweeps (plateau .44–.52),
top-hat normalisation k∈{25,35,51} (.20–.34, worse), vignette-corrected
diff (empty masks), ratio flat-field (noise amplification), dual-chain
selection by mean template-confidence (never fires: confident-short reads
beat long-right reads) and by confidence-sum (drowns in kind noise —
rescued reads worse than primary, 0.05c).

**Part 2 — the real residue is NOT the bands.** Per-image readouts on the
LD masks showed three images at char 1.00 and a specific signature on the
failures:

    want 'heron COMET MOSS cobalt basil'   got 'heron COAIET AIOSS cobalt basil'
    want 'ember willow Zigzag ...'         got 'eln ber vfi iioIm Zigzag ...'

M → 'AI', m → 'ln', w → 'lm'. **Wide glyphs are over-split by
`reader.split_wide`**: any ink piece wider than 1.35× its height is
recursively cut at its sparsest column — a capital M at w≈25,h≈17 sits at
1.47 and is cut through its legs, and the halves then template-match as
plausible narrow letters. This is family-independent machinery: it will
hit every family with wide/heavy faces, and it also explains part of the
long-standing strippy/cut/stitch plateaus.

**Part 3 — merge-back arbiter, measured, currently NOT shippable.**
Greedy re-merge of adjacent splits when the merged glyph templates at
least as well as its parts (extensions: never merge across the 1.6×
height-mismatch that marks dot-over-stem 'i'/'j' pairs):

- cross-shadow (on LD masks): exact 3/10, **char 0.85** (vs .52 unmerged)
- snow (otsu): char **0.73 → 0.89**, stitch (otsu): exact 1→2, char .67→.81
- easy (otsu): exact 4/10 → **2/10 — regression**, char .78→.85

The pattern is char-up everywhere, exact-down on easy: the arbiter cannot
separate 'M-cut-in-half' from a clean 'il' pair when both sit near
0.8–0.9 confidence; gating merge on low pre-merge confidence destroyed
the win instead (LD-mask pieces are high-confidence). Tightening
(min→mean+0.03→max) does not rescue easy.

## Honest state & next lever (for whoever picks this up)

Ship-ready: nothing beyond PR #14 (polarity guard) this round; the
arbiter loses 2 easy points and that trade is not the honest kind (easy
is the 98-bar suite).

Strong untried lever, with the rationale written down: `split_wide`
already cuts at the **sparsest** column; when that column's ink count is
ZERO the cut was clean whitespace (a true boundary — 'il'), when it is
NONZERO the cut passed through a stroke (suspicious — 'M' legs). Merge
candidates should be exactly the *forced cuts* (colsum[x] > 0 at the
chosen x), evaluated structurally instead of free-floating across all
pairs. `split_wide` would need to expose cut metadata; both reader.py
strategies and baseline.py share the primitive, so the fix belongs in
reader.py with the diagnosis replicated through tools/stage_diagnosis.py.

Reproduce every number above: probes are inline in the git history of
this branch's PR discussion; the LD chain + merge-back prototype lives at
`tools/ld_read.py` (experimental, flagged as such — NOT wired into
baseline.py or reader.py, deliberately).
