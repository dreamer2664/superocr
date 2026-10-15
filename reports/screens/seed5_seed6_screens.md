# S72 — seed-5 + seed-6 held-out screens (t-20261014-937a)

Fresh out-of-sample screens in the exact S55 workflow
(`tools/s55_seed_screen.py`): seeds 5 and 6 appear in no tuning receipt;
canonical seeds 1/2/3/4/53 untouched. These are SCREENS (10 rows per
hard family = 120 hard items; the canonical hard suite is 100 items
with a different family mix) — not headline numbers, no 98/95 claim.

## Commands (exact)

```bash
python3 tools/s55_seed_screen.py --seed 5 --count 10
python3 tools/s55_seed_screen.py --seed 6 --count 10
```

Raw plain-floor rows: `reports/s55_seed5_floor_rows.json`,
`reports/s55_seed6_floor_rows.json` (reader = `baseline.read_text`).
Paired rows (raw floor + current shipping `fix_line`, post-S55 band
as merged in 39ce621): `reports/screens/seed5.jsonl` (sha256-16
`5b41f69ff77ee394`), `reports/screens/seed6.jsonl` (`d82ea87532d5aaa7`).

## Results (shipping reader_lex = floor + current fix_line)

| seed | easy | hard (120 items, 10/family) | lex fixes | lex breaks |
|---|---|---|---|---|
| 5 | **76/100** | **46/120** (38.3%) | 43 | 0 |
| 6 | **80/100** | **40/120** (33.3%) | 33 | 0 |

Context: settled canonical benches are easy 75 / hard 25 (seed-1) and
75/29 (seed-2) at the canonical hard mix. The screens sit in the same
band on easy; hard percentages are NOT comparable to the canonical 100
(family mix differs — this screen oversamples the dead families per
family count). Lex repair never broke a correct raw read on either seed
(0 breaks, 76 total fixes).

Note for readers of the harness output: `s55_postprocess_harness`'s
`A_shipping` pins the PRE-S55 band (it is the audit's baseline), so its
seed-5 A line reads 73/45; the current shipping route (fix_line ==
merged band, equal to the harness's `B_band+1_all`) gives the 76/46 and
80/40 above. Both are reproduced by the committed rows.

## Use

Out-of-sample material for future probes (S70 case instrument etc.):
220 items per seed with raw floor output + shipping output + labels.
No tuning was performed on these rows; they are held-out by
construction.
