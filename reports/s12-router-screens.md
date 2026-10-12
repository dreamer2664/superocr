# S12 — the router, wired: official screens (t-20261012-30bf, cormac)

`baseline.py --auto-family` decides the family from the image itself, via the
S9 pre-classifier (`preclassify.rank`), and routes it into the S7c family
parameter. Three reproducible routes exist now: **plain** (no flag — the old
default, untouched), **auto** (`--auto-family` — the product path), and
**oracle** (`--family F` — the diagnostic that tells the reader the answer).
Everything below is measured, and everything single-run is labelled
**screen, not proof**, per the task spec.

Tree: main `3c39dbe` (S7c rev2 #28 + S13 #29 included) + this branch.
The screens were executed at `590628a` + this branch's change; between
`590628a` and `3c39dbe` only `reports/s13-residue.md` and
`tests/test_s13_dod.py` changed, so the routing path is code-identical.
Official suites, seed 1, hash `b2c460d2fb5a`, one run per route.

## The screens (one run each — screens, not proofs)

| route | command | easy | hard |
|---|---|---|---|
| plain | `python3 baseline.py {image}` | **28/100** | **9/100** |
| auto | `python3 baseline.py {image} --auto-family` | **27/100** | **11/100** |
| oracle | `bench_adapter ... --cmd 'baseline.py {image} --family {family}'` | **28/100** | **11/100** |

Reading, honestly: **auto captures the full oracle hard gain (+2: 9 → 11)**
— the wall masks fire on the images where they convert to exacts, and the
five hard images that mis-route into wall families cost zero exacts this
run. **Auto costs one easy exact** (28 → 27): the confusion table below
shows 7 easy images routed to `corrosion` (its `close1` mask is mild but
not free); on this tree `dark-on-dark` is un-wired from dispatch (#28), so
the 5 easy→dark-on-dark misroutes carry no mask at all. Net product-path
trade on this screen: **−1 easy, +2 hard** versus plain.

The plain numbers reproduce the #28/#29 record exactly (28/9 → 11 with
masks), which is also the sanity check that the harness was healthy.

## The router's honest picture on the official suites

`python3 tools/s12_confusion.py` (ground truth = manifest family; the
centroids were built from seed-42 indices 200-207 and have never seen seed 1):

- **easy suite: 87/100 route to `easy`.** Misroutes: corrosion 7,
  dark-on-dark 5 (no mask on this tree), cut 1 (no mask).
- **hard suite: top-1 81/100.** Per-family: stitch 9/9, cut 8/8, collage 8/8,
  obstruction 8/8, dark-on-dark 8/8, split 8/9, spiderweb 7/9, cross-shadow
  7/8, strippy 7/8, snow 4/9, corrosion 4/8, **darts 3/8** (the weakest wall
  route: scatters to snow/spiderweb).
- **Wall families routed-right: 22/32**; non-wall images mis-routed INTO a
  wall family: **5** (the wrong-mask risk this table exists to name).

## What this suggests next (not done here)

1. A **margin guard** — apply a wall mask only when the router's top-1 score
   clearly beats the plain families — targets the −1 easy directly; it is a
   small, measurable change, but it is selection on these very suites, so it
   would need a fresh-seed check before anyone believes it.
2. **Darts routing** (3/8) is the weakest wall route and the biggest single
   routing lever for hard.
3. None of these numbers is claimed as sustained; the three-run proof rule
   applies the moment one of them is.

## Process note, disclosed

The first attempt at these screens ran all three benches in parallel on this
2-core box: 14-16 per-item **timeouts** (plain read easy 24 — visibly wrong),
and two reports collided on the same timestamp. All three runs were discarded
and deleted from the tree, and everything above was rerun **sequentially**
(zero timeouts in all three report JSONs). Parallel benches on a shared
2-core box are not a measurement.
