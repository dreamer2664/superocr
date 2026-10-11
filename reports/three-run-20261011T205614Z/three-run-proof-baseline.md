# three-run proof — superocr (S5, t-20261011-b0cb)

> BASELINE, not the acceptance proof: classic reader.py on main 285eaa3, before barry's S1 and scott's S2 land. Produced to prove the S5 pipeline end-to-end at full size; re-run when the readers improve.

- produced: 20261011T205614Z (UTC) · commit `5f9d5ac75163`
- reader: `python3 tools/bench_adapter.py {image}`
- suites: `/tmp/vh2/data` · seed 1 · bars easy >= 98%, hard >= 95%
- runs: 3 consecutive full passes · raw reports + galleries: `reports/three-run-20261011T205614Z/`
- bench's own stability file: `20261011T205614Z-stability.json`
- all items excluded in a suite means nothing was scored; excluded ids are listed per suite (0 across runs)

## The claim

**NOT CLEARED.** At least one run missed at least one bar. The numbers below are the truth as measured, not a draft. Re-run this proof when stronger readers land; the gap is named per line.

- run 1: easy 2/100 = 2.0% < bar 98%
- run 1: hard 1/100 = 1.0% < bar 95%
- run 2: easy 2/100 = 2.0% < bar 98%
- run 2: hard 1/100 = 1.0% < bar 95%
- run 3: easy 2/100 = 2.0% < bar 98%
- run 3: hard 1/100 = 1.0% < bar 95%

## the runs

| run | easy (bar 98) | hard (bar 95) | verdict | slowest p95 |
|---|---|---|---|---|
| 1 | 2/100 (2.0%) NO | 1/100 (1.0%) NO | FAIL | 1.11s |
| 2 | 2/100 (2.0%) NO | 1/100 (1.0%) NO | FAIL | 1.10s |
| 3 | 2/100 (2.0%) NO | 1/100 (1.0%) NO | FAIL | 1.13s |

## by family (last run) — and how far each moved across runs

| suite/family | correct (last run) | total | across runs |
|---|---|---|---|
| easy/easy | 2 | 100 | 2 / 2 / 2 |
| hard/collage | 0 | 8 | 0 / 0 / 0 |
| hard/corrosion | 0 | 8 | 0 / 0 / 0 |
| hard/cross-shadow | 0 | 8 | 0 / 0 / 0 |
| hard/cut | 0 | 8 | 0 / 0 / 0 |
| hard/dark-on-dark | 0 | 8 | 0 / 0 / 0 |
| hard/darts | 0 | 8 | 0 / 0 / 0 |
| hard/obstruction | 1 | 8 | 1 / 1 / 1 |
| hard/snow | 0 | 9 | 0 / 0 / 0 |
| hard/spiderweb | 0 | 9 | 0 / 0 / 0 |
| hard/split | 0 | 9 | 0 / 0 / 0 |
| hard/stitch | 0 | 9 | 0 / 0 / 0 |
| hard/strippy | 0 | 8 | 0 / 0 / 0 |

## the ugly cases (gallery)

- run 1 easy: 98 failure(s) — gallery `/tmp/vh2/reports/three-run-20261011T205614Z/gallery/20261011T205614Z-easy-hard-r1of3/easy` — first: easy-0000, easy-0001, easy-0002, easy-0003, easy-0004, easy-0005, easy-0006, easy-0007, easy-0008, easy-0009 …
- run 1 hard: 99 failure(s) — gallery `/tmp/vh2/reports/three-run-20261011T205614Z/gallery/20261011T205614Z-easy-hard-r1of3/hard` — first: snow-0000, spiderweb-0000, split-0000, stitch-0000, strippy-0000, cut-0000, collage-0000, corrosion-0000, cross-shadow-0000, darts-0000 …
- run 2 easy: 98 failure(s) — gallery `/tmp/vh2/reports/three-run-20261011T205614Z/gallery/20261011T205909Z-easy-hard-r2of3/easy` — first: easy-0000, easy-0001, easy-0002, easy-0003, easy-0004, easy-0005, easy-0006, easy-0007, easy-0008, easy-0009 …
- run 2 hard: 99 failure(s) — gallery `/tmp/vh2/reports/three-run-20261011T205614Z/gallery/20261011T205909Z-easy-hard-r2of3/hard` — first: snow-0000, spiderweb-0000, split-0000, stitch-0000, strippy-0000, cut-0000, collage-0000, corrosion-0000, cross-shadow-0000, darts-0000 …
- run 3 easy: 98 failure(s) — gallery `/tmp/vh2/reports/three-run-20261011T205614Z/gallery/20261011T210202Z-easy-hard-r3of3/easy` — first: easy-0000, easy-0001, easy-0002, easy-0003, easy-0004, easy-0005, easy-0006, easy-0007, easy-0008, easy-0009 …
- run 3 hard: 99 failure(s) — gallery `/tmp/vh2/reports/three-run-20261011T205614Z/gallery/20261011T210202Z-easy-hard-r3of3/hard` — first: snow-0000, spiderweb-0000, split-0000, stitch-0000, strippy-0000, cut-0000, collage-0000, corrosion-0000, cross-shadow-0000, darts-0000 …

## re-run this

```
python3 tools/make_suites.py --seed 1   # if data/ is missing
python3 tools/three_run_proof.py --reader "python3 tools/bench_adapter.py {image}" --runs 3
```
