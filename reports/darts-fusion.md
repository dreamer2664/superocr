# darts: fusion diagnosis + rejected levers (t-20261011-be57 addendum)

Seed 7, N=10 unless noted. Continues reports/zero-wall-attack.md.

## The failure is fusion, not junk

Darts (36–70 semi-transparent gray chevrons, 1–2px strokes, s∈[8,22])
bridge glyphs into **mega-blobs spanning words and lines**. Concretely
(seed 7, index 0, label `clover forge umber SUMMIT QuiLL 15`, 29 true
glyphs): 2 word-rows, **7 pieces**, the largest 176×192 px ≈ the whole
text zone. split_wide correctly refuses to split them (w≈h ≪ 1.35×h).
Downstream: guards keep the blobs, matchers template whole lines as one
glyph, char ≈ 0.02.

## Measured lever table (all honestly negative or partial)

| lever | char | verdict |
|---|---|---|
| floor otsu (pre/post polarity) | 0.02 | baseline |
| median3 / median5 gray prefilter | 0.02 / 0.07 | no |
| local-diff th40 (± median) | 0.02 / 0.06 | no |
| mask opening k=1 / k=2 | **0.10** / 0.08 | k1 partial, k2 damages glyphs |
| marker reconstruction erode-k → dilate-(k+2) ∩ mask, k=2 | **0.21** | best partial; k=3 kills glyphs (0.00) |

## Documented next lever (not built)

The fusion seams are dart-thin (1–2px) but pixel-connected; separating
needs *shape* information, not blur/erosion:

1. **Connected-component geometry filter**: blobs whose bbox spans >~2.5×
   the median x-height AND whose ink-fraction is low (dart webs are
   sparse) are dart-fused; apply colsum-veto splitting with horizontal
   band priors before split_wide, or
2. **dart-model subtraction**: generate the dart layer's stroke envelope
   (long thin quadrilaterals at random angles detectable via Hough-lite
   on the mask's thin pixel set — pixels that die under erode-1 is exactly
   the set the reconstruction probe exposed) and subtract before
   binarisation commits to a mask.

Both need a measurement harness that already exists
(tools/stage_diagnosis.py) and the honesty of the lever table above.

Probes in this file's git history (PR discussion); partials reproducible
through the inline scripts quoted there.
