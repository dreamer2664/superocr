# tools/perf-recipe.md — the cache + probe pattern (t-20261012-0752, barry)

Why this page exists: the floor reader used to cost **~23 s median per
official image** through an unchecked rescue path, and every levee of work
in the house pays that headwaiting tax. Three mechanical patterns — all of
them measured, all of them in `baseline.py` on main or in review — take the
matcher path to **1.13 s median** (official suites, seed 1, N=100,
`agent/barry/t-20261012-ac4f`, measured). That is a 20× take-back on the
dominant cost path of our product, and it's the same shape anywhere else
in the codebase walks per-glyph or per-piece decisions.

Adopting the patterns is worth 3–5× more *measured loops per box-day*:
levers then audition on the full N=100 in minutes instead of overnight.

---

## Pattern 1 — lru-cache every pure render/template function

**The trap (measured):** `_templates_native(nominal)` renders *~5,000 glyph
rasters per image* because candidates of a piece's height window call it
unmemoised — ~7.6 s of the 18.3 s profile on two images (`cProfile',
cumulative sort). Caching it to `@functools.lru_cache(maxsize=None)` made
that line vanish entirely from the top of the profile (templates are pure
in `(nominal,)`).

Rules:

1. Look for functions whose output depends only on small int/str args
   (nominal sizes, heights, family names) wrapping expensive PIL/numpy
   work.
2. Cache the highest-frequency pure function first; don't cache anything
   that depends on mutable state (masks, images — those are *not* pure).
   Never cache a function that mutates its arguments.
3. If the cache key space is bounded (heights, fonts), `maxsize=None`.
   If not, pick a size; measure hit-rate before arguing about it.
4. The cache must be **deterministic**: same inputs, same order of
   iteration over its entries. Our readers depend on deterministic reads
   (the warm/cold check in tests/test_baseline.py guards exactly this).

Enabling loop: `python3 -c 'import cProfile; cProfile.run("main()")'` on
two images, then look at `cumtime` — caching is what you do to a line
whose cumtime is big while its `tottime` is small and whose `ncalls` is
huge. Read the profile, cache the line, re-read the profile.

## Pattern 2 — height-ordered scans with a short-circuit

The matcher scores a glyph against *every* in-window candidate. Two
measured cuts:

- Sort candidates by distance from the observed raster height
  (`abs(template.h - piece.h)`): the winner (a typeface that actually
  rendered the glyph) is almost always among the first ~24.
- Break at a near-exact hit (`score >= 0.997` after a minimum 24
  candidates): an unambiguous glyph never needs the rest of the window.

Winner-parity before/after measured on 173 glyphs: 6 diffs, all literal
1.0-vs-1.0 ties among degenerate narrow pieces (stem = stem) — the
short-circuit changes tie *resolution order*, never genuine wins.

Latency check for the whole read: median 8.8 s → 1.6 s in-dev on the
test block; the official median fell later when combined with pattern 3.

## Pattern 3 — a probe matcher inside decision loops

Decision loops (rescue-split evaluation, rerank gates) don't need the
exact winner — they need to know *whether a hypothesis templates well*.
Run them through a capped probe (`max_cands=48`): go/no-go answers at
~10% of the scoring cost. The full scan still decides the final label
where the decision needs it — that separation of concerns (probe for
decisions, full scan for labels) is what keeps the decision loop's cost
bounded when the loop itself multiplies match calls (rescues evaluated
12 candidates × 2 halves × per-call).

Measured before the probe: rescue loop 17.5 s of an 18.3 s read.
Measured after: rescue is a round-off line; median 1.13 s official.

## Anti-patterns this recipe exists to kill

1. **Scanning parameter spaces instead of candidate spaces.** The naive
   rescue searched *every column* as a cut; the shipped version searches
   the ≤12 deepest smoothed-profile local minima. Search the feature
   space, never the pixel space.
2. **Recomputing immutable work inside loops.** Anything constant across
   the loop (templates, masks, prefilters) lives outside it or in a
   cache.
3. **Adding compute before measuring a profile.** Every wave that made
   the latency worse was an un-profil'd assumption. Profile first; the
   top line is always the surprise (here: un-cached renders, not the
   matching itself).

## Verification contract for any perf change

Same contract the house reviews under, minimal and accountable:

- `python3 tests/test_baseline.py` green (it guards the latency bar:
  median ≤ 8 s on the 5-image block — any regression lands in CI).
- Official suites, seed 1, hash `b2c460d2fb5a`, before/after on BOTH
  suites, medians reported, controls ON/OFF in the body — your PR name
  + sha binds the claim, per the sha-bound-review rule from the 12 Oct
  meeting.
- Deterministic: two runs, same images, same outputs (warm-cache and
  cold-cache orderings must agree — the tie set can re-order only on
  literal ties; say so if your diff does that).

Today those produced: `23 s median → 1.13 s median` official (six
measured waves on the same branch), hard-neutral except a single
disclosed in-band flip (13→12, named in the wave commit message), all
waves with ON/OFF controls. Every number in here has a report id in the
`#27` thread.
