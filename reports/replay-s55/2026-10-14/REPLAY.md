# S57 — Independent replay of the S55 bench movement (t-20261014-713e)

**Replayer:** scipio (second machine, fresh clone) · **Date:** 2026-10-14
**Verdict: REPRODUCED — per-item identical, zero variance, on all six runs.**

## What was replayed

The S55 3× safety receipts (`reports/s55-bench-seed1-3x/`,
`reports/s55-bench-seed2-3x/`, PR head `39ce621`) claim:

| seed | easy | hard |
|---|---|---|
| 1 | 75/100 ×3 runs | 25/100 ×3 runs |
| 2 | 75/100 ×3 runs | 29/100 ×3 runs |

## How

1. **Clean clone** of superocr; S55 is merged to main, so the replay ran on
   main `9ab638a` (merge of PR #76). Shipping-path source identity vs the
   receipt stamp `39ce621` verified blob-for-blob: `tools/reader_lex.py`,
   `tools/lex_projection.py`, `baseline.py`, `bench.py`,
   `tools/make_suites.py` — all IDENTICAL.
2. **Suites regenerated** with `tools/make_suites.py --seed {1,2}`;
   dir-hashes verified full-sha against `tools/s38_compare.HASHES`:
   seed-1 `b2c460d2fb5a…` ✓, seed-2 `ec64cd63790d…` ✓ (canonical bytes).
3. **Bench**: the exact receipt-stamped reader command
   `python3 tools/reader_lex.py {image}`, `--runs 3` per seed, bars
   untouched (98/95, no override), receipts in this directory.
4. **Per-item diff**: `tools/replay_s57_diff.py` (new, tested 6/6 —
   `tests/test_replay_s57_diff.py`) compared every `(id, got)` pair of each
   replay run against the matching committed run, both suites.
5. **Receipts validated**: all six replay receipts pass
   `tools/validate_report.py --expect-cmd "python3 tools/reader_lex.py {image}"`.

## Result

| seed | run | easy | hard | easy mismatches | hard mismatches |
|---|---|---|---|---|---|
| 1 | r1of3 | 75/100 | 25/100 | 0 | 0 |
| 1 | r2of3 | 75/100 | 25/100 | 0 | 0 |
| 1 | r3of3 | 75/100 | 25/100 | 0 | 0 |
| 2 | r1of3 | 75/100 | 29/100 | 0 | 0 |
| 2 | r2of3 | 75/100 | 29/100 | 0 | 0 |
| 2 | r3of3 | 75/100 | 29/100 | 0 | 0 |

**1200 item comparisons, 0 `(id, got)` mismatches, 0 id-set differences,
counts identical on every run.** The reader is deterministic across
machines, as the receipts claim.

Bench verdicts are FAIL against the 98/95 bars on every run — as in every
reader_lex receipt to date. The wall is unclimbed; nothing here rounds it.
This replay proves reproducibility of the recorded numbers, not bar passage.

## Machine spec (replay side)

- Linux 6.1.158+ x86_64 · 2 vCPU · 2030 MB RAM
- Python 3.13.16 · Pillow 12.3.0 · numpy 2.3.5 · cv2 4.11.0
  (same library versions as the original env stamps)
- Replay branch: `agent/scipio/t-20261014-713e` cut from main `9ab638a`

## Files

- `replay-summary.json` — machine-readable summary (counts, diffs, hashes, spec)
- `seed1-3x/`, `seed2-3x/` — the six replay receipts + partials + stability jsons
- Gallery images generated but not committed (regenerable; same practice as
  the original 3× receipts per `reports/s55-postprocess-audit.md` §7.1)

## Reproduce this replay

```bash
python3 tools/make_suites.py --seed 1 --out data/seed1
python3 tools/make_suites.py --seed 2 --out data/seed2
python3 bench.py --suite-dir data/seed1 --suites easy,hard \
  --reader "python3 tools/reader_lex.py {image}" --runs 3 --seed 1 \
  --report-dir reports/replay-s55/<date>/seed1-3x
python3 bench.py --suite-dir data/seed2 --suites easy,hard \
  --reader "python3 tools/reader_lex.py {image}" --runs 3 --seed 2 \
  --report-dir reports/replay-s55/<date>/seed2-3x
python3 tools/replay_s57_diff.py --replay reports/replay-s55/<date>/seed1-3x \
  --committed reports/s55-bench-seed1-3x --seed 1
python3 tools/replay_s57_diff.py --replay reports/replay-s55/<date>/seed2-3x \
  --committed reports/s55-bench-seed2-3x --seed 2
```
