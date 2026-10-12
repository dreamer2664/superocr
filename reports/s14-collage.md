# S14 — collage: the per-card route (t-20261012-1d17)

**What this does.** The collage family was one of the six families at *zero* on
every measured path (S11 screens: baseline 28/9, reader 3/2, cnn v1 29/6, v2
31/8 — collage contributed 0 to all four). The reason is structural: the sheet
is a patchwork of 28-px grey tiles with several small, **rotated** cards
(+/-9 deg) pasted on top, each carrying one line of dark text; rotating a card
leaves black wedge bars at its edges and adjacent cards can touch. Whole-image
binarisation drowns in the patchwork.

This lands a **per-card route**: find the cards, straighten each one, read it on
its own, then read the cards left to right.

## The numbers (measured, this commit)

| set | n | reader | mean char-acc | exact |
|---|---|---|---|---|
| official collage items (seed 1) | 8 | whole-image floor, any path | 0.000 | 0/8 |
| official collage items (seed 1) | 8 | **this route (cv2 path)** | **0.707** | 0/8 |
| held-out seed-7 collages | 10 | **this route (cv2 path)** | **0.816** | 2/10 |
| official, numpy/PIL fallback | 8 | this route, `cv2` absent | ~0.60 | 0/8 |

Per-item official (cv2 path): 0000 .48 · 0001 .75 · 0002 .53 · 0003 .62 ·
0004 .91 · 0005 .84 · 0006 .84 · 0007 .68.
Held-out seed-7: 0.60 .94 .60 .69 1.00 1.00 .90 .88 .45 .69 (items 4-5 exact).

Screens, not proofs: one run per set. The two exact cells on the held-out set
are the first exact collage reads on record.

## The two rectification paths, stated in full

The route is **deterministic per environment**, and the environments differ:

* **cv2 present** (the sandbox; most dev boxes): `minAreaRect` +
  `warpPerspective`, INTER_CUBIC. Every number in the table above is this path.
* **cv2 absent** (this repo's CI installs numpy+Pillow only): a minimum-area
  rectangle by 0.5-degree angle sweep + PIL affine straightening. Measured
  ~0.60 mean char official — the warp sampling costs ~0.10-0.15 char against
  the cv2 path. `tests/test_s14_collage.py` forces this path and asserts the
  route still returns text, so CI covers it by contract, not by number.

The gap between the paths is a sampling-kernel difference, not a logic
difference: the detector returns identical rectangles (verified side by side
to 0.1 px) and the two raw patches differ by mean |diff| ~0.9 grey levels.

## How it works (each rule earned in the ladder, dead ends included)

1. **Strict >= 236 mask** — cards are painted 235-250, the patchwork tiles top
   out at 235, so a strict threshold yields the card *body* un-inflated. (A
   41-px median filter locates cards but inflates each rect ~20 px and drags
   the neighbour's text in — the original 0.266-prototype bug.)
2. **Components** area >= 900, w >= 24, h >= 14.
3. **Wedge split** — merge components are split at a dark column (mean >= 0.7)
   whose longest dark run >= 1.12x the text band. Glyph stems are dark columns
   too but never taller than the band; that check is what stops the
   over-splitting that once produced `bfa ini iml iqi`.
4. **Straighten** per block; long side horizontal, corner order by sum/diff —
   never an orientation trial (matcher scores do not rank 0 vs 180 deg).
5. **Cooking, once**: ink-bbox trim -> strip full rows/cols that are >= 60%
   dark (card border lines, wedge slivers) -> edge_prune (short rim fragments
   taller than the x-height band) -> 3-px inset -> 3x LANCZOS -> glyph CNN
   (`readers/cnn_reader.py`). Applying the furniture twice (rule 5 both before
   and after the split) measured 0.57 instead of 0.75 — the second round eats
   real glyphs; the code now applies it once, per half.
6. **Reader choice is measured, not assumed**: the floor's `baseline.read_text`
   collapses on the tilted cards (`Beacon` -> `mkUK`; even a 5-degree rotation
   of a clean easy image reads `DH0 Keej`). The glyph CNN turns the same
   rectified cards into `BeaCon`/`NIMBUS`/`QUlLL`. That is why the route reads
   with the CNN and why baseline.py's collage gate delegates to this module.

Dead ends that stay dead (measured, do not retry): brightness-threshold-only
cards (never separated patches properly); dilate-bridge word grouping with
whole-sheet reading (0.042); axis-aligned crops without straightening
(0.132/0.166); ink-rect-only crops (0.212); median-filter rects (inflation,
above); 2x upscale without the inset (rim chrome: `r BeaConJ`).

## What is still open (named, not hidden)

* Official exact-match cells are still 0/8; the residue is per-glyph case
  (c/C, i/I/l — the same case-twin wall as S13/S8) and occasional rim chrome
  (`Bvalley` vs `valley`), *not* detection.
* The staggered-merge seam split (bright-above + dark-below gates) is kept:
  it is what recovered the `rosesette sAil` merge in its development config;
  on the final cv2 config over these 18 images it did not fire (neutral). It
  remains gated tightly (SEAM_MIN_H/W + depth gates) so it cannot touch
  ordinary cards.

## Wiring and receipts

* `readers/collage.py` — the route (numpy + Pillow; cv2 optional).
* `baseline.py` — `family == "collage"` delegates here (2 lines + a lazily
  imported module); every other family is untouched (verified: easy-0000 reads
  identically before/after on both the default and `--family easy` paths).
* `reader.py` — same gate in `read()`.
* `tests/test_s14_collage.py` — detection, the single-block guard, text +
  determinism, and the forced no-cv2 fallback. 4/4 green.

Reproduce:

    python3 tools/make_suites.py
    python3 readers/collage.py --image data/hard/images/collage-0000.png --verbose
    python3 tools/bench_adapter.py data/hard/images/collage-0000.png \
        --cmd "python3 baseline.py {image} --family {family}"
    python3 tests/test_s14_collage.py

— Pericles, 12 Oct 2026
