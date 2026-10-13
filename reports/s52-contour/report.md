# S52 — contour features for glyph disambiguation: NO-GO (t-20261013-7c60)

**Bounded probe, no wiring.** Premise under test: pixel-template matching
confuses similar glyphs; stroke-width / curvature / aspect contour
features could re-rank them.

## 1. The confusion inventory (both suites, floor-aligned glyphs, template scan)

| suite | aligned | wrong | rank-errors (truth in top-8) | truth absent |
|---|---|---|---|---|
| hard | 588 | 110 | **24** | 86 |
| easy | 1503 | 156 | **74** | 82 |

The premise's pairs DO appear (hard: `z→e`, `l→I`, `O→0`, `P→p`; easy:
`l→i` ×20, `s→S` ×19, `l→I` ×4, `O→0` ×4) — but the rerankable surface
is small, and on hard 86/110 wrong glyphs don't contain the truth in the
top-8 at all (stroke destruction / segmentation — not a ranking problem).

## 2. Feature discriminability on 62,545 corpus truth crops

Features: stroke width (BFS distance transform), compactness
(perimeter²/area), aspect, hole count (Euler), ink density, fill ratio.
Nearest-centroid classifier, clean-ish corpus cells:

- **overall accuracy: 0.119** (62 classes; chance ≈ 0.02, majority ≈ 0.03)
- On the template lane's ACTUAL confusion pairs, the features are
  **below the majority-class baseline on every pair tested**:

| pair | feature acc | majority baseline | n |
|---|---|---|---|
| l→I | 0.133 | 0.777 | 4299 |
| s→S | 0.136 | 0.653 | 3276 |
| l→i | 0.091 | 0.518 | 6452 |
| O→0 (via n→o family) | 0.175 | 0.503 | 5898 |
| v→V | 0.034 | 0.644 | 881 |

## Verdict

**NO-GO — and instructively so.** The pairs templates confuse are
precisely the pairs with near-identical coarse geometry (`l/I/i` share
aspect, holes, stroke width; `s/S` and `O/0` are the same shapes), so
contour features carry no signal where it's needed — worse than
majority on every target pair. The pixel template's IoU on the actual
raster already subsumes every geometric measurement these features
encode. Similar-glyph disambiguation needs CONTEXT (case logic = S55,
word-level = S54) or higher-resolution raster evidence, not coarser
features.

With S35 (scale) and S50 (confusion patterns) this closes the third and
last "improve the template matcher" hypothesis. The classic lane is
fully scoped: its residue is structural (segmentation 63/77, stroke
destruction), and the 98/95 attack belongs to S54 (word-level reader),
achilles's preprocessing, and leonidas's post-processing.

## Files

- `tools/s52_contour_probe.py` — inventory + features + discriminability
- `reports/s52-contour/probe.json` — full numbers
