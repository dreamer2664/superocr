# S10c — CNN-scored cut search for fused joins (12 Oct)

Lane named by the lead after S10b: the **fused joins** — pieces where two
touching glyphs were segmented as one. Barry's taxonomy (PR #27) established
these as the easy-suite war: fused pairs read as a single confident wrong
character (`rf`→`H`, `ft`→`n`, `dg`→`W`, `al`→`b`, `rb`→`I`). His rescue
re-split is the template-side answer; this is the CNN-side scorer: enumerate
candidate cuts, read both halves with glyphcnn-v2, accept a split only when
the halves read confidently and (variant-dependent) better than the fused
piece.

## Status

Measurements running; results land in the sections below. Nothing here is
wired into anything until it survives the held-out seed-2 check.

## Method

* `tools/s10c_fused_scan.py` — enumerate suspect pieces on a suite through the
  floor's own chain (low template confidence or wide aspect), with candidate
  cut columns from the smoothed profile minima; writes JSON.
* `tools/s10c_cnn_cuts.py` — the scorer. Three acceptance variants:
  * `beat-fused`: product of half probabilities must beat the fused piece's
    own CNN probability by a margin (strictest);
  * `halves-only`: both halves at the CNN gate is enough; the product ranks
    the cuts;
  * `precondition`: like `halves-only`, but the fused template score must also
    be below the doubt gate.
* Protocol: select on canonical seed 1 (hash `b2c460d2fb5a`), confirm on
  held-out seed 2 (hash `ec64cd63790d`). Kept / solved / lost per item.

## Results — seed 1 (canonical): NEGATIVE, published as such

All numbers on the canonical easy suite (seed 1, hash `b2c460d2fb5a`),
serialized quiet box. The reference is the **no-cuts base**: the same reader
with the cut search disabled, which reads **38/100** — i.e. the CNN piece
policy itself (matching the S10b flag-ON proof). The question this lane asked:
do CNN-scored cuts add anything ON TOP of that?

| criterion | exact | cuts accepted | solved | lost | net vs base |
|---|---|---|---|---|---|
| none (base) | 38/100 | 0 | — | — | — |
| precondition | 38/100 | 5 | 0 | 0 | **0** |
| top8-contain | 25/100 | 93 | 2 | 15 | **−13** |
| beat-fused | 31/100 | 83 | 0 | 7 | **−7** |
| halves-only | 1/100 | 768 | 0 | 37 | **−37** |

**The lever does not work.** Not one criterion solves more than 2 items while
breaking 7–37; the only criterion that never loses (`precondition`) does so by
accepting just 5 cuts and changing nothing exact. The failure mechanics are
visible in the acceptance rules:

* `beat-fused` passes junk because a fused piece's own CNN probability is
  *low* — the halves beat it trivially (83 cuts accepted, 0 solved);
* `halves-only` splits nearly everything (768 cuts);
* `top8-contain` (the wave-3-style honesty rule) still trades 2 for 15, so
  matcher-shortlist containment does not rescue the idea here;
* `precondition` is inert — the genuinely doubtful pieces are exactly the
  ones where both halves stay unconfident.

No held-out check is run for a negative result: seed 2 can only fail to
improve on this, and no gain is claimed. The remaining under-segmentation
failures after barry's rescue need a stronger idea than cutting plus a
classifier read — plausibly a sequence model over the whole word, or
barry's rescue extended with the CNN as a *tie-break between candidate cuts
that the template side already trusts*, not as the primary acceptance signal.

## Context and target sizing

Barry's PR #27 (template-side rescue) took easy 28 → 40 with zero losses;
most of its repairs were stem-family ties (i/l), with a few genuine joins.
Sizing the remaining opportunity for this lane, text-level and CPU-free, from
the recorded reads:

| | easy failures | fewer chars than label (under-seg signature) |
|---|---|---|
| clean main `a7168d5` | 72 | 20 |
| PR #27 head (wave 2) | 60 | 12 |

The 12 under-segmentation failures at the PR #27 head are this lane's target
list — reads like `Drift → Dri0` ('ft' fused into one piece), `summit →
summU`, `Horizon → HoHzon`. Some of the 12 are drop-deletions rather than
fusions; the scan output separates them by piece geometry. Remaining
same-count failures (44) are substitutions the matcher's top-8 already
contains — barry's lane.
