# S20 — corrosion: the cheap restoration sweep, measured flat (t-20261012-7c1b)

**Task:** t-20261012-7c1b (marcus-aurelius). **Suite:** official hard, seed 1,
hash `b2c460d2fb5a`, the 8 `corrosion-*` items. All numbers from
`tools/s20_restoration_probe.py` (committed, reproducible from a clean clone)
plus one follow-up probe recorded below. Screens, not proofs; N=8.

## Failure anatomy (floor path, item-level)

The floor reads the corrosion eight at **0/8 exact, 0.407 mean char** — the
damage shatters strokes into garbage glyphs rather than nudging confusables:
`PARCHMENT → JVACJmENT`, `EMBER → aeRR`, `GROVE ember → 47jdjW lvJJ9 n`.
Some words survive partially (`07 summit Fennel SAGE → 07 stGw4it FWnnel SAm`).
This is edge-erosion and stroke fragmentation, matching the S7 diagnosis
(stroke-level damage).

## The pinned-mask oracle

`python3 baseline.py <img> --family corrosion` (the S7c chain, close1 mask
primary) reads the same eight: **0/8 exact** — outputs differ from plain in a
few cells (`Ul low → Ullow`) but nothing crosses exact. The existing mask is
not the lever.

## Restoration probes (pre-classification, end-to-end official path)

`read_text(restored_img, family=None)` on each variant:

| variant | exact | mean char | note |
|---|---:|---:|---|
| identity (control) | 0/8 | 0.407 | — |
| median3 | 0/8 | 0.351 | worse |
| median5 | 0/8 | 0.330 | worse |
| gray-close k=2 | 0/8 | 0.361 | corrosion-0002 spikes .44 → .75; 0005 collapses .40 → .07 |
| gray-close k=3 | 0/8 | 0.301 | worse |
| gray-close k=4 | 0/8 | 0.221 | worse |
| median3 + gray-close2 | 0/8 | 0.350 | worse |
| interior-hole fill ≤ 4/9/16 px | 0/8 | 0.407 | bit-identical to control at all three thresholds — the post-otsu mask carries no enclosed small holes; the damage is edge-erosion, not interior pits |

## What this says

1. **Global morphological restoration is flat-to-negative**: the pits (1–3 px)
   sit at the same scale as thin strokes, so any kernel big enough to heal a
   pit distorts a stroke; the per-item split in gray-close2 (one item +0.31
   char, another −0.33) is the scale conflict made visible.
2. **Interior-hole filling changes nothing**: the corrosion mask has no small
   enclosed background components to fill — the strokes are eroded from the
   edges and split, not holed.
3. The cheap imaging lane is therefore **measured dead for this family**, with
   receipts. The remaining task approaches stand: (2) family-conditioned CNN
   trained on corrosion-degraded glyphs (scott's v3 pipeline already carries
   corrosion confusables in its target list) and (3) multi-read consensus.
   Neither is a mask-layer lever; both are training/ensemble lanes.

Corrosion remains the one wall both readers fail (classic 0/8, vision 0/8,
S19). It blocks hard-95 alone if unresolvable; this report bounds where the
answer is NOT.
