# S39 — latency: profile, memoize, verify (t-20261013-cbe7)

**Claim:** the shipping reader (`tools/reader_lex.py` → `baseline.read_text` +
`fix_line`) gets **68–73 % faster** (wrapper median 6.69/7.66 s → 2.10/2.04 s
easy/hard) with **zero change to any read**: per-item `(image, got)` diff vs
the settled 3× receipts = **0/200** over three consecutive full-suite runs.
Task bar was −30 %; delivered −68 %. Accuracy bar (98/95) unchanged and still
NOT met — this is a latency receipt, not an accuracy one: easy 73/100, hard
23/100, exactly as settled.

## Stamps

| stamp | value |
|---|---|
| reader | `python3 tools/reader_lex.py {image}` (unchanged wrapper command) |
| scorer | author (manifest `label` == wrapper stdout, byte compare) |
| suites | canonical seed-1, dir_hash `b2c460d2fb5a…` (validator `--data` PASS against settled receipts) |
| env | python 3.13.16 · pillow 12.3.0 · numpy 2.3.5 · Linux x86_64 (identical to the settled-run env) |
| base sha | `7368e70` (main after #64 merge) |
| before-numbers source | `reports/s22-3x-settled/` @ PR #53 head `584f8c4` (sha `7a92ce14` reader-equivalent) |

## Profile (where the 6–8 s actually went)

cProfile over 3 hard images (13.0 s cumulative, before):

| stage | cum s | share | what it is |
|---|---|---|---|
| `_templates_native` via `_cands_for_height` | 7.4 | 57 % | PIL font-rendering the template pyramid: 8 faces × 62 chars × ~34 nominal sizes per glyph height. 30,752 font renders in 3 images. |
| `sorted()` in the 3 match sites | 2.6 | 20 % | same ~2k-candidate list re-sorted per glyph call in `match_native`/`_scan_native`/`_match_probe` |
| `_score_glyph` | 2.8 | 21 % | IoU-with-tolerance scoring (124,528 calls) |
| `trim` | 1.4 | 11 % | `np.where` materializing every ink-pixel coordinate (31,215 calls) |

The in-memory `lru_cache` on `_templates_native` never helps the bench: every
image is a **fresh process**, so every read re-rendered the pyramid. Subprocess
overhead itself is negligible (bare `python3 -c "import numpy, PIL.Image"` =
0.12 s), which is why S48-style parallelization was the wrong lever.

## Changes (pure memoization — no math touched)

1. **Disk-backed template cache** (`baseline.py`): `.template-cache/t-<stamp>-<nominal>.pkl`
   (gitignored). Stamp = sha256(Pillow ver, numpy ver, face paths with
   size+mtime, `R.CHARS`) — any environment change invalidates. Atomic
   tmp+rename writes; load validates types/shapes; **any cache error falls
   through to rendering**, and a corrupt file is healed on the next save. A
   broken cache can never break or change a read.
2. **`_sorted_cands(h)`** (`baseline.py`): the height-ordered candidate list,
   sorted once per height (lru 256), shared by all three match sites. Same
   key, same stable order — pinned by test.
3. **`trim` via projections** (`reader.py`): `flatnonzero(any(axis))` instead
   of `np.where` — same bbox, no coordinate materialization. Pinned
   bit-identical vs the old implementation on 200 seeded random masks.

`tests/test_s39_template_cache.py` (11 checks): round-trip bit-identity
(memory vs disk vs fresh render, key order included), corrupt-cache fallback +
self-heal, sorted-cache order/identity equivalence, trim equivalence, seeded
read smoke. **Full suite: 26/26 files pass.**

## Verification (three consecutive runs, both canonical suites, wrapper command)

| run | easy | hard | per-item got-diff vs settled | easy median/p95/max s | hard median/p95/max s |
|---|---|---|---|---|---|
| 1 | 73/100 | 23/100 | 0/200 | 2.15 / 3.20 / 3.40 | 2.10 / 3.69 / 4.82 |
| 2 | 73/100 | 23/100 | 0/200 | 2.12 / 3.08 / 3.36 | 2.00 / 3.60 / 4.74 |
| 3 | 73/100 | 23/100 | 0/200 | 2.10 / 3.15 / 3.99 | 2.04 / 3.58 / 4.94 |
| settled (before, 3×) | 73/73/73 | 23/23/23 | — | median 6.69 | median 7.66 |

Determinism is exact, not statistical: all 600 reads across 3 runs are
byte-identical to the settled receipts' reads.

## Cold-clone behaviour

`.template-cache/` does not exist in a clean clone. First ever read on a
machine pays the pyramid build **once**: measured 5.12 s (vs 5.93 s for the
same image before the change — cold-with-build still beats old-warm because
the sort/trim savings apply immediately). Second read: 2.13 s, fully cached.
Cache footprint after one hard image: 21 MB, 35 nominal files (grows to ≤62
files as new glyph heights appear; bounded by the nominal 10–71 window).

## Side effects

* Webapp `route=lex` (in-process) benefits on server start: the first request
  no longer renders the pyramid (~4 s saved cold); warm-request numbers in
  `reports/webapp-latency-lex.json` stand.
* The demo-median bar (<10 s) had 2.3–3.3 s of headroom before; it now has
  ~7.9 s — room for the v5 recognizer lane without breaking the demo.

## Bars

easy 73 / hard 23 — **98/95 NOT met** (unchanged; this task changed no read).
Three consecutive runs: **MET** (bit-identical). Demo median ≤10 s: **MET**
with wider margin. Clean-clone reproducible: **MET** (cache self-builds;
verification numbers above are from the wrapper command on canonical suites).
