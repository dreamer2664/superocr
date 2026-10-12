# S9 — the product path: auto-mode latency, routing, smoke (final)

Task `t-20261012-5c63`. The classifier and its wiring landed first as
**PR #21 (author: cormac)** → `d61917e`; this harness PR is the closing
piece. Credit is split on purpose and stated here: **the classifier is
cormac's, the harness is the lead's**, merge by lead verdict.

## What ships

**Classifier + wiring (PR #21, cormac):** `preclassify.py` — a nearest-centroid
router over structural features (contrast shape, speckle, stripe periodicity,
seam sharpness, blotch energy, half-shift correlation), committed centroids
(`models/preclass_centroids.npz`), `--rebuild` deterministic from a clean
clone; `typer.py` runs the top-ranked chain and falls back to the next
candidate only when a read is unusable.

**Harness (this PR, pericles):** `tests/test_auto_latency.py` (the bars,
pinned), `tools/measure_preclassify.py` (routing measured against the
generator on held-out seeds), this report, the `--family all` escape hatch
(the old exhaustive scan, missing from the merged wiring), a one-line
`tests/test_s10_gate.py` fix (it failed under `tests/run_all.py` — my review
miss on #19: I ran pytest, not the project runner), and a one-line
`preclassify.shortlist()` fix (its "displace the k-th for `easy`" branch was
a no-op).

## The bar: every auto probe under 10 s (measured)

`tools/demo_latency.py` medians, 7 repeats; the bar is now **every** probe,
not the pooled median (cormac's sharpening, kept):

| probe | before S9 (committed) | after (committed, cormac) | lead smoke on merged main |
|---|---|---|---|
| easy | 9239 ms | 736 ms | 598 ms overall, bar MET |
| easy-pinned | 661 ms | 545 ms | — |
| snow | 3921 ms | 245 ms | — |
| obstruction | 3162 ms | 250 ms | — |
| split | 12398 ms | 1195 ms | — |
| strippy | 26019 ms | 4081 ms | — |
| dark-on-dark | 5096 ms | 775 ms | — |

Direct typer calls (this box, one run each) — auto now versus the old scan
(`--family all`):

| probe | auto | old scan | family auto used |
|---|---|---|---|
| easy | 0.69 s | 8.65 s | easy |
| snow | 0.14 s | 3.12 s | snow |
| obstruction | 0.21 s | 2.27 s | obstruction |
| split | 0.90 s | 14.35 s | split |
| strippy | 2.60 s | 42.18 s | strippy |
| dark-on-dark | 0.52 s | 7.50 s | dark-on-dark |

## Routing — measured, not claimed

Lead verification, two held-out protocols neither classifier was tuned on:
top-1 **86.5%** (seed 42, indices 300–315 — cormac's protocol) and **79.8%**
(seed 777, 400–415 — fresh); top-3 98.6% / 94.7%. On the six official probes
the pre-classifier names the true family **first on 6/6** (including
obstruction seed 13, which the lead's own rule-based attempt missed).

`tools/measure_preclassify.py --seed 404` (held-out, 10/family):

| family | routed-first | in-top3 | | family | routed-first | in-top3 |
|---|---|---|---|---|---|---|
| easy | 9/10 | 10/10 | | corrosion | 9/10 | 10/10 |
| snow | 7/10 | 10/10 | | cross-shadow | 6/10 | 6/10 |
| spiderweb | 9/10 | 10/10 | | darts | 6/10 | 10/10 |
| split | 8/10 | 10/10 | | obstruction | 6/10 | 7/10 |
| stitch | 10/10 | 10/10 | | dark-on-dark | 10/10 | 10/10 |
| strippy | 6/10 | 9/10 | | cut | 7/10 | 10/10 |
| collage | 10/10 | 10/10 | | **total** | **103/130 = 79%** | **122/130 = 94%** |

## Disclosed behaviour changes (honest table)

Auto's *reading* can differ from the old scan's, because a different chain
now runs — by design: the old scan's loudest-confidence arbitration was
gameable. Measured on the six probes: identical text on **3 of 6** (easy,
obstruction, dark-on-dark); different on **3 of 6** (snow, split, strippy) —
in every case auto used the *true* family's chain while the old scan used a
wrong one (darts for snow, corrosion for split, dark-on-dark for strippy).
Both readings are inexact at the current floor reader; this task changed
which chain runs, not how well the reader reads. `--family all` restores the
old behaviour exactly, and is pinned by test.

Worst case: if ranked candidates keep returning unusable reads (< 3 glyphs),
auto walks the ranking down — bounded by thirteen chains (the old timing).
No probe comes near that; it exists as the honest safety valve.

## Tests

`python3 -m pytest tests/test_auto_latency.py` — 6 passed (31 s): every probe
under the bar; true family first on all six probes; auto's family is the top
candidate; `all` is still the exhaustive scan; auto is deterministic; the
shortlist keeps `easy` in its last slot when easy ranks next.
`python3 tests/test_preclassify.py` (cormac's) passes as a script; full suite
on the merged branch runs green except the pre-existing regressions this PR
fixes.

## Reproduce

    python3 tools/measure_preclassify.py --probes
    python3 tools/demo_latency.py --repeats 7
    python3 -m pytest tests/test_auto_latency.py
    python3 typer.py mypicture.png --family auto     # or --family all

## Not claimed here

The reader's accuracy is unchanged and far below the 98/100 and 95/100 bars —
S7c/S10 own that lane. Routing misses exist (table above), worst on
cross-shadow and obstruction; when the routed chain is wrong, the reading is
wrong-family, which is exactly what the old gameable arbitration already
produced. The pre-classifier routes; it does not read.
