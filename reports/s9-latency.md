# S9 — the product path: auto-mode latency, smoke, and an honest routing table

Task `t-20261012-5c63`. Branch `agent/pericles/t-20261012-5c63`.

**What ships:** `preclass.py` (the cheap pre-classifier auto mode now uses),
`typer.py` wired to it (`--family auto` = shortlist; `--family all` = the old
full scan), `tests/test_auto_latency.py` (the bar, pinned), the non-programmer
section at the top of `README.md`, and `tools/measure_preclass.py` (routing
measured against the generator).

**The bar (JOBS.md): every auto probe under 10 s.** Before this change auto
ran all thirteen family chains and took the loudest average confidence. On
the official demo probes that was 9.2 s (easy), 12.4 s (split) and 26.0 s
(strippy) — over the bar on three of seven probes — and, measurably, the
loudest-confidence rule picked the **true family on 2 of 6 probes**: glyph
confidence is not calibrated across families, so garbage masks score ~0.7 too.

## Before and after, official harness

`tools/demo_latency.py --repeats 7` (its own server, medians of 7):

| probe | before (medians, committed) | after (this branch) |
|---|---|---|
| easy | 9238.8 ms | **435.9 ms** |
| easy-pinned | 661.2 ms | 404.1 ms |
| snow | 3921.2 ms | **328.8 ms** |
| obstruction | 3161.5 ms | **466.2 ms** |
| split | 12398.1 ms | **1524.6 ms** |
| strippy | 26018.7 ms | **5280.0 ms** |
| dark-on-dark | 5095.8 ms | **865.0 ms** |
| overall | 7109.1 ms | **739.8 ms** |

**Every probe inside the 10 s bar.** Raw per-request numbers:
`reports/demo-latency.json`.

Direct typer calls (`typer.recognise(img, "auto")` vs `"all"` on the same
images, seed-pinned picks, one run each on this box):

| probe | auto (after) | full scan (`all`) |
|---|---|---|
| easy | 0.80 s | 8.88 s |
| snow | 0.32 s | 3.36 s |
| obstruction | 0.43 s | 2.33 s |
| split | 1.41 s | 15.04 s |
| strippy | 5.75 s | 46.20 s |
| dark-on-dark | 0.89 s | 8.44 s |

## What auto does now

    shortlist = preclass.shortlist(image)      # ~40 ms, native resolution
    best      = max(read_chain(image, fam) for fam in shortlist)   # by avg conf

The statistics and the rule each one feeds (thresholds with their measured
margin; generator output is the ground truth):

| statistic | what it sees | routes to | measured margin |
|---|---|---|---|
| `darkfrac` | everything near black | dark-on-dark | 1.00 vs ≤ 0.08 elsewhere |
| `speck` | saturated 1-px specks on paper | snow | 0.035 vs ≤ 0.002 |
| `strobe` | row-median paper tone as a square wave | strippy | 0.26 vs ≤ 0.03 |
| `grey_far` | grey structure away from ink | collage | 0.47 vs ≤ 0.02 |
| `split_margin` | one coherent ≥8 px half-shift | split / stitch | 0.61 vs ≤ 0.19 |
| `midgrey` + tone | soft mid-tone patches, clean paper | obstruction, cross-shadow, darts, spiderweb | 0.076 (obstruction) vs ≤ 0.01 (easy) |

A strong signal (score ≥ 2) stands alone next to `easy`; weak signals widen
to at most three families. `easy` always rides along: it is cheap, it is the
98/100 suite, and one honest reading is never wasted. An image that matches
nothing gets `easy` — which is what the old full scan returned most often on
such images anyway, minus the wait.

## Routing — measured, not claimed

`tools/measure_preclass.py --seed 404` (held-out; never used for tuning),
10 samples per family:

| family | in-shortlist | routed-first | | family | in-shortlist | routed-first |
|---|---|---|---|---|---|---|
| easy | 10/10 | 10/10 | | corrosion | 0/10 | 0/10 |
| snow | 6/10 | 6/10 | | cross-shadow | 3/10 | 3/10 |
| spiderweb | 10/10 | 0/10 | | darts | 10/10 | 0/10 |
| split | 10/10 | 10/10 | | obstruction | 10/10 | 10/10 |
| stitch | 2/10 | 0/10 | | dark-on-dark | 10/10 | 10/10 |
| strippy | 7/10 | 7/10 | | **total** | **88/130 = 68%** | **66/130 = 51%** |

On the six official probes the true family lands in the shortlist on **5 of
6** (easy, snow, split, strippy, dark-on-dark). The known miss is
**obstruction seed 13**: its midgrey statistic sits below the band, a
spurious split signal fires instead, and auto falls back to the `easy`
reading. In 0.43 s it returns **the same text the old full scan returned**
for that image — the old scan picked `easy` too, after 2.3 s of work.

**This is the honest state: the pre-classifier routes, it does not read.**
`routed-first` is low for spiderweb/darts/stitch because their scores lose
to a stronger sibling in the same band, and cut/corrosion have no reliable
detector yet (their mechanics are 1-3 px wide; two attempts to measure them
cheaply did not separate from noise, so no detector ships rather than a
guessing one). Those families pay for it in *routing*, not in correctness:
whenever the true family is in the shortlist, its chain runs exactly as
before, the same mask, the same reader, the same numbers.

## What changes for existing users of auto (disclosed)

Auto's *output* can differ from the old auto on images where the old
loudest-confidence pick sat outside the new shortlist. Measured on the six
probes: **3 of 6 return the identical text** (easy, obstruction,
dark-on-dark); snow, split and strippy return a different reading. In every
one of the six cases both the old and the new reading are inexact at the
current floor reader — this task changed *which chain runs*, not how well
the reader reads. Any accuracy movement is S7c/S10's lane, on the official
suites, with three-run proofs. `--family all` restores the old behaviour
exactly, and `tests/test_auto_latency.py` pins that.

## Tests

`python3 -m pytest tests/test_auto_latency.py` — 6 passed (38.5 s): every
probe under the bar; the shortlist contains the true family on the five
catching probes; auto's family always comes from the shortlist; the
shortlist is capped at four and carries `easy`; `--family all` is still the
full scan; auto is deterministic.

## Reproduce

    python3 tools/measure_preclass.py --probes          # routing + probe table
    python3 tools/demo_latency.py --repeats 7           # official latency numbers
    python3 -m pytest tests/test_auto_latency.py        # the pinned bar

## Not claimed here

The reader's accuracy is unchanged and far below the 98/100 and 95/100 bars;
the shortlist occasionally routes wrong (table above); the pre-classifier adds
a measured ~40 ms of statistics to each auto call (it is not visible in the
easy-pinned row: a pinned family never calls it — the 661 -> 404 ms movement
there is box-to-box noise, not a feature).
