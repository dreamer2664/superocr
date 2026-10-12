# three-run proof — superocr (S5, t-20261011-b0cb)

> S10b flag ON (SUPEROCR_PIECE_CNN=1) - research mode, frozen clone 0790005; serialized run, quiet box

- produced: 20261012T122053Z (UTC) · commit `079000504246`
- reader: `env SUPEROCR_PIECE_CNN=1 python3 baseline.py {image}`
- suites: `/tmp/s10-suites` · seed 1 · bars easy >= 98%, hard >= 95%
- runs: 3 consecutive full passes · raw reports + galleries: `/tmp/s10b-flag-proof/`
- bench's own stability file: `20261012T122053Z-stability.json`
- all items excluded in a suite means nothing was scored; excluded ids are listed per suite (0 across runs)

## The claim

**NOT CLEARED.** At least one run missed at least one bar. The numbers below are the truth as measured, not a draft. Re-run this proof when stronger readers land; the gap is named per line.

- run 1: easy 38/100 = 38.0% < bar 98%
- run 1: hard 11/100 = 11.0% < bar 95%
- run 2: easy 38/100 = 38.0% < bar 98%
- run 2: hard 11/100 = 11.0% < bar 95%
- run 3: easy 38/100 = 38.0% < bar 98%
- run 3: hard 11/100 = 11.0% < bar 95%

## the runs

| run | easy (bar 98) | hard (bar 95) | verdict | slowest p95 |
|---|---|---|---|---|
| 1 | 38/100 (38.0%) NO | 11/100 (11.0%) NO | FAIL | 5.41s |
| 2 | 38/100 (38.0%) NO | 11/100 (11.0%) NO | FAIL | 5.30s |
| 3 | 38/100 (38.0%) NO | 11/100 (11.0%) NO | FAIL | 5.29s |

## by family (last run) — and how far each moved across runs

| suite/family | correct (last run) | total | across runs |
|---|---|---|---|
| easy/easy | 38 | 100 | 38 / 38 / 38 |
| hard/collage | 0 | 8 | 0 / 0 / 0 |
| hard/corrosion | 0 | 8 | 0 / 0 / 0 |
| hard/cross-shadow | 0 | 8 | 0 / 0 / 0 |
| hard/cut | 2 | 8 | 2 / 2 / 2 |
| hard/dark-on-dark | 2 | 8 | 2 / 2 / 2 |
| hard/darts | 0 | 8 | 0 / 0 / 0 |
| hard/obstruction | 3 | 8 | 3 / 3 / 3 |
| hard/snow | 2 | 9 | 2 / 2 / 2 |
| hard/spiderweb | 1 | 9 | 1 / 1 / 1 |
| hard/split | 0 | 9 | 0 / 0 / 0 |
| hard/stitch | 1 | 9 | 1 / 1 / 1 |
| hard/strippy | 0 | 8 | 0 / 0 / 0 |

## the ugly cases (gallery)

- run 1 easy: 62 failure(s) — gallery `/tmp/s10b-flag-proof/gallery/20261012T122053Z-easy-hard-r1of3/easy` — first: easy-0000, easy-0001, easy-0002, easy-0003, easy-0004, easy-0005, easy-0006, easy-0007, easy-0009, easy-0011 …
- run 1 hard: 89 failure(s) — gallery `/tmp/s10b-flag-proof/gallery/20261012T122053Z-easy-hard-r1of3/hard` — first: snow-0000, spiderweb-0000, split-0000, stitch-0000, strippy-0000, cut-0000, collage-0000, corrosion-0000, cross-shadow-0000, darts-0000 …
- run 2 easy: 62 failure(s) — gallery `/tmp/s10b-flag-proof/gallery/20261012T123236Z-easy-hard-r2of3/easy` — first: easy-0000, easy-0001, easy-0002, easy-0003, easy-0004, easy-0005, easy-0006, easy-0007, easy-0009, easy-0011 …
- run 2 hard: 89 failure(s) — gallery `/tmp/s10b-flag-proof/gallery/20261012T123236Z-easy-hard-r2of3/hard` — first: snow-0000, spiderweb-0000, split-0000, stitch-0000, strippy-0000, cut-0000, collage-0000, corrosion-0000, cross-shadow-0000, darts-0000 …
- run 3 easy: 62 failure(s) — gallery `/tmp/s10b-flag-proof/gallery/20261012T124411Z-easy-hard-r3of3/easy` — first: easy-0000, easy-0001, easy-0002, easy-0003, easy-0004, easy-0005, easy-0006, easy-0007, easy-0009, easy-0011 …
- run 3 hard: 89 failure(s) — gallery `/tmp/s10b-flag-proof/gallery/20261012T124411Z-easy-hard-r3of3/hard` — first: snow-0000, spiderweb-0000, split-0000, stitch-0000, strippy-0000, cut-0000, collage-0000, corrosion-0000, cross-shadow-0000, darts-0000 …

## re-run this

```
python3 tools/make_suites.py --seed 1   # if data/ is missing
python3 tools/three_run_proof.py --reader "env SUPEROCR_PIECE_CNN=1 python3 baseline.py {image}" --runs 3
```
