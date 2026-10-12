# three-run proof — superocr (S5, t-20261011-b0cb)

> S10 candidate v2 (D: per-class 200 synthetic + 400 generator sheets, seed 11, 34 epochs): three consecutive runs on the official suites. Candidate, not shipped - comparison baseline is the committed net at 29/6 (S5 three-run).

- produced: 20261012T074804Z (UTC) · commit `4b0d28a0cb07`
- reader: `python3 readers/cnn_reader.py --image {image} --weights /tmp/s10-D.npz`
- suites: `/home/user/superocr/data` · seed 1 · bars easy >= 98%, hard >= 95%
- runs: 3 consecutive full passes · raw reports + galleries: `reports/three-run-20261012T074804Z/`
- bench's own stability file: `20261012T074804Z-stability.json`
- all items excluded in a suite means nothing was scored; excluded ids are listed per suite (0 across runs)

## The claim

**NOT CLEARED.** At least one run missed at least one bar. The numbers below are the truth as measured, not a draft. Re-run this proof when stronger readers land; the gap is named per line.

- run 1: easy 31/100 = 31.0% < bar 98%
- run 1: hard 8/100 = 8.0% < bar 95%
- run 2: easy 31/100 = 31.0% < bar 98%
- run 2: hard 8/100 = 8.0% < bar 95%
- run 3: easy 31/100 = 31.0% < bar 98%
- run 3: hard 8/100 = 8.0% < bar 95%

## the runs

| run | easy (bar 98) | hard (bar 95) | verdict | slowest p95 |
|---|---|---|---|---|
| 1 | 31/100 (31.0%) NO | 8/100 (8.0%) NO | FAIL | 0.31s |
| 2 | 31/100 (31.0%) NO | 8/100 (8.0%) NO | FAIL | 0.34s |
| 3 | 31/100 (31.0%) NO | 8/100 (8.0%) NO | FAIL | 0.32s |

## by family (last run) — and how far each moved across runs

| suite/family | correct (last run) | total | across runs |
|---|---|---|---|
| easy/easy | 31 | 100 | 31 / 31 / 31 |
| hard/collage | 0 | 8 | 0 / 0 / 0 |
| hard/corrosion | 0 | 8 | 0 / 0 / 0 |
| hard/cross-shadow | 0 | 8 | 0 / 0 / 0 |
| hard/cut | 0 | 8 | 0 / 0 / 0 |
| hard/dark-on-dark | 1 | 8 | 1 / 1 / 1 |
| hard/darts | 0 | 8 | 0 / 0 / 0 |
| hard/obstruction | 1 | 8 | 1 / 1 / 1 |
| hard/snow | 3 | 9 | 3 / 3 / 3 |
| hard/spiderweb | 0 | 9 | 0 / 0 / 0 |
| hard/split | 0 | 9 | 0 / 0 / 0 |
| hard/stitch | 0 | 9 | 0 / 0 / 0 |
| hard/strippy | 3 | 8 | 3 / 3 / 3 |

## the ugly cases (gallery)

- run 1 easy: 69 failure(s) — gallery `/home/user/superocr/reports/three-run-20261012T074804Z/gallery/20261012T074804Z-easy-hard-r1of3/easy` — first: easy-0001, easy-0002, easy-0003, easy-0005, easy-0007, easy-0008, easy-0009, easy-0010, easy-0011, easy-0012 …
- run 1 hard: 92 failure(s) — gallery `/home/user/superocr/reports/three-run-20261012T074804Z/gallery/20261012T074804Z-easy-hard-r1of3/hard` — first: snow-0000, spiderweb-0000, split-0000, stitch-0000, strippy-0000, cut-0000, collage-0000, corrosion-0000, cross-shadow-0000, darts-0000 …
- run 2 easy: 69 failure(s) — gallery `/home/user/superocr/reports/three-run-20261012T074804Z/gallery/20261012T074853Z-easy-hard-r2of3/easy` — first: easy-0001, easy-0002, easy-0003, easy-0005, easy-0007, easy-0008, easy-0009, easy-0010, easy-0011, easy-0012 …
- run 2 hard: 92 failure(s) — gallery `/home/user/superocr/reports/three-run-20261012T074804Z/gallery/20261012T074853Z-easy-hard-r2of3/hard` — first: snow-0000, spiderweb-0000, split-0000, stitch-0000, strippy-0000, cut-0000, collage-0000, corrosion-0000, cross-shadow-0000, darts-0000 …
- run 3 easy: 69 failure(s) — gallery `/home/user/superocr/reports/three-run-20261012T074804Z/gallery/20261012T074945Z-easy-hard-r3of3/easy` — first: easy-0001, easy-0002, easy-0003, easy-0005, easy-0007, easy-0008, easy-0009, easy-0010, easy-0011, easy-0012 …
- run 3 hard: 92 failure(s) — gallery `/home/user/superocr/reports/three-run-20261012T074804Z/gallery/20261012T074945Z-easy-hard-r3of3/hard` — first: snow-0000, spiderweb-0000, split-0000, stitch-0000, strippy-0000, cut-0000, collage-0000, corrosion-0000, cross-shadow-0000, darts-0000 …

## re-run this

```
python3 tools/make_suites.py --seed 1   # if data/ is missing
python3 tools/three_run_proof.py --reader "python3 readers/cnn_reader.py --image {image} --weights /tmp/s10-D.npz" --runs 3
```
