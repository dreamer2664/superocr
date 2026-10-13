# S35 — multi-scale template matching: NO-GO (t-20261013-0a21)

**Bounded probe, no wiring** (per lead's queue note). Question: corrosion
erosion changes glyph size — does rescaling the crop (±10%/±20%) or
widening the height window (±1→±2 px) recover template matches on
corroded glyphs?

## Setup

`tools/s35_multiscale_probe.py` — four matchers on the same crops:

| matcher | what it does |
|---|---|
| base | shipping `match_native` scan (candidate window: template height within ±1 px) |
| tol2 | same scan, window ±2 px |
| ms10 | crop rescaled ×{0.90, 1.00, 1.10}, best score across scales |
| ms20 | crop rescaled ×{0.80, 0.90, 1.00, 1.10, 1.20} |

Three arms:
- **generated/corrosion (floor)** — 40 fresh seed-71 fam_corrosion
  renders (no eval-suite contamination), floor-segmented pieces aligned
  to truth, 220 crops: the honest read-time distribution;
- **corpus truth** — S53 corpus corrosion arm, 30 items/severity, crops
  cut at truth char_boxes (2354 crops): the matcher in isolation, no
  segmentation confound;
- **corpus floor** — same items through floor segmentation where counts
  align (204 crops): read-time on the corpus distribution.

## Results (top-1, ms/crop)

| arm | base | tol2 | ms10 | ms20 |
|---|---|---|---|---|
| generated floor (n=220) | 0.3227 (91ms) | 0.3227 | **0.3000** | **0.2955** |
| corpus truth (n=2354) | 0.1963 (44ms) | 0.1984 (+1.1%) | 0.2077 (+5.8%) | 0.2128 (+8.4%) |
| corpus floor (n=204) | 0.1863 (34ms) | 0.1863 | 0.1912 (+2.6%) | 0.1814 (−2.6%) |

Shipping `read_text` on generated corrosion: 2.14 s/read; ms20 wiring
would add ~3-4 s/read (5× the per-crop scan) — under the 10 s bar but
buying nothing at read level.

## Verdict

**NO-GO.** The >5% gate passes only in the isolation arm (truth boxes)
and only in relative terms (+1.1 to +1.7 points absolute, on a 0.20
base). Through real segmentation the multi-scale delta is noise, and on
the read-time generated arm it is NEGATIVE (−7 to −8%): rescaling
amplifies pit noise and the short-circuit score threshold prefers
confident wrong matches at off-scales.

**Mechanism finding (the useful residue):** the matcher's corrosion
failure is NOT a scale-window problem — widening the window (tol2) moves
nothing on any arm, and the height-matched candidate set already contains
the right nominal sizes (it scans nominals h..2h+4). What kills the match
is stroke destruction (S30: heavy/extreme corrosion at 0.41/0.22 even
with perfect boxes and a retrained CNN) and segmentation (S43: 63/77 =
82% of hard misses). This probe closes the last cheap template-lane
hypothesis and re-concentrates the 98/95 attack on marcus's S54
word-level reader, achilles's segmentation work, and leonidas's
post-processing lane.

## Files

- `tools/s35_multiscale_probe.py` — the probe (deterministic, no wiring)
- `reports/s35-multiscale/probe.json` — full numbers incl. per-severity cells
