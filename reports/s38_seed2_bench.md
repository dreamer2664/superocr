# S38 — canonical seed-2 cross-validation of the shipping reader

**Owner:** Achilles · **Task:** `t-20261013-2aed` · **Date:** 13 October 2026

**Reader revision:** `7368e7082fba019d98e90d17b32e39b62ac36e9c`

**Route:** `python3 tools/reader_lex.py {image}` (classic floor plus lex projection).

## Verdict

The fresh canonical seed-2 screen reads **74/100 easy and 29/100 hard**.
Compared with the historical, same-source seed-1 receipt **73/100 easy and
23/100 hard**, the differences are **+1 and +6 percentage points**.

Easy meets the task's descriptive ±2-point agreement criterion. Hard exceeds
its >5-point investigation trigger. The investigation below finds no reader
error, input mismatch, or seed-specific inference branch; it does **not** prove
that every seed-dependent defect is absent. These results are consistent with
finite-sample variation, not evidence of a code improvement in this task.

**Neither the 98% easy bar nor the 95% hard bar is met. This is one fresh screen,
not a three-run stability proof, and not a claim of statistical equivalence.**

| Suite | Seed 1: historical | Seed 2: fresh | Difference | Pooled |
|---|---:|---:|---:|---:|
| easy | 73/100 | 74/100 | +1 pp | 147/200 (73.5%) |
| hard | 23/100 | 29/100 | +6 pp | 52/200 (26.0%) |

No production reader, lexicon rule, model, generator recipe, or canonical
label was changed. The seed-2 suite has appeared in earlier research receipts;
it is an official independent-RNG-seed test set, **not a never-before-used
validation set**. No tuning was performed against it in S38.

## Evidence and conditions

- [Fresh stamped seed-2 JSON](s38-seed2-fresh/20261013T133120Z-easy-hard.json)
  and [bench markdown](s38-seed2-fresh/20261013T133120Z-easy-hard.md).
- [Seed-1 comparator](s25-piece-gap/receipt-final/20261013T081536Z-easy-hard.json),
  produced at `a3528cce83dd5d50e4de8ed026b3f8ed278047a7`. It is reused, **not rerun**.
- [Machine-readable comparison](s38-comparison.json).
- [Shipping-source identity, font hashes, and runtime flags](s38-source-identity.json).
- [Every easy failure](s38-seed2-fresh/gallery/20261013T133120Z-easy-hard/easy/gallery.md)
  and [every hard failure](s38-seed2-fresh/gallery/20261013T133120Z-easy-hard/hard/gallery.md).
- [Item-by-item partials and completed footer](s38-seed2-fresh/20261013T133120Z-easy-hard-partials.jsonl).

Canonical data roots were reconstructed using the unchanged clean-clone suite
builder, then accepted **only after full byte hashes matched** the pre-existing
canonical records. No newly selected seed or replacement suite was used:

| Seed | Full suite-root SHA-256 |
|---|---|
| 1 | `b2c460d2fb5a8f83c8d4c4b3893ff6eb05248f2444cbb1ff8acbe9531323fdd3` |
| 2 | `ec64cd63790d8824b4f72c71d18dd953326c24da01d65d171938ae79beb549e8` |

Both receipts carry the same environment fingerprint: Python **3.13.16**,
Pillow **12.3.0**, NumPy **2.3.5**, OpenCV **4.11.0**. Eight DejaVu faces are
present; this box uses FreeType **2.14.3**. No `SUPEROCR_*` environment flags
were set. The shipping module/model files in the source-identity receipt are
byte-identical between the historical comparator and the frozen fresh reader.

The fresh run held the bench lock, ran readers **serially**, used a 60-second
per-item timeout, scored both suites in full, retained all failure images, and
used `scorer=author`. It scored **200/200**, with **zero exclusions, reader
errors, or timeouts**. Both reports passed the stamp validator against the
recomputed canonical data and strict current environment. Bench exit **1**
is the expected failed accuracy-bar verdict, not a failed execution.

**Harness timestamp limitation (not edited in S38):** `bench.py:584` writes
`finished_ts` from `this`, captured at the beginning of `one_run`, so this JSON
has equal start/finish timestamps despite a real ~16m39s run. Completion is
independently evidenced by the 200 item records and the `event=done` partial
footer at **13:47:59 UTC** (start 13:31:20 UTC). Do not derive elapsed time from
those two JSON timestamp fields. Reader timings remain per-item measured.

## Investigation of the +6-point hard gap

Family composition is identical across seeds: the first four families have
nine items each, and the other eight have eight. The score change is entirely
accounted for by the following distribution, rather than a dropped family:

| Hard family | Items/seed | Seed 1 exact | Seed 2 exact | Count difference |
|---|---:|---:|---:|---:|
| snow | 9 | 5 | 4 | -1 |
| spiderweb | 9 | 1 | 2 | +1 |
| split | 9 | 3 | 6 | +3 |
| stitch | 9 | 2 | 3 | +1 |
| strippy | 8 | 0 | 0 | 0 |
| cut | 8 | 5 | 3 | -2 |
| collage | 8 | 0 | 0 | 0 |
| corrosion | 8 | 0 | 0 | 0 |
| cross-shadow | 8 | 0 | 0 | 0 |
| darts | 8 | 0 | 0 | 0 |
| obstruction | 8 | 4 | 6 | +2 |
| dark-on-dark | 8 | 3 | 5 | +2 |
| **Total** | **100** | **23** | **29** | **+6** |

The inference CLI loads the image and calls `read_text`; its generator seed
argument is used by `--score`, not forwarded by the shipping wrapper's
single-image command. No seed-dependent inference branch was identified in
that path. After the full run, four fresh wrapper rechecks (`split-0000`,
`cut-0000`, `obstruction-0000`, `dark-on-dark-0000`) returned **4/4 item-identical
outputs**, all with exit 0. This spot check is not a replacement for full-run
repeatability testing.

**Uncertainty:** Wilson 95% intervals are easy seed-1 **63.568–80.730%**, easy
seed-2 **64.629–81.595%**; hard seed-1 **15.843–32.154%**, hard seed-2
**21.015–38.539%**. Two-sided Fisher exact tests give easy **p=1.000000** and
hard **p=0.420391**. These are descriptive, unadjusted comparisons of two
independent-seed arms. A nonsignificant result is **not** proof of equivalence
or stable generalization. The same item IDs recur across seeds but refer to
different images/labels; a paired repair/loss or McNemar test would be wrong.

Observable error signatures also show what changed. They are string-level
categories, **not causal segmentation/classifier diagnoses**:

| Hard nonexact signature | Seed 1 | Seed 2 |
|---|---:|---:|
| case-only | 9 | 8 |
| shorter output than label | 35 | 35 |
| longer output than label | 28 | 21 |
| same-length substitution | 5 | 7 |
| **All misses** | **77** | **71** |

Five hard families remain at **0 exact on both seeds**: strippy, collage,
corrosion, cross-shadow, darts (40 items per seed). The +6-point seed difference
does not remove those walls. Further diagnosis belongs to the owners of S43
and the image-side lanes; S38 does not duplicate Leonidas's claimed census.

## Reproduce and audit

Run in the frozen reader revision and matching font/library environment. The
builder commands below reconstruct the **canonical bytes**, not a new test
population. If either full hash differs, stop: do not benchmark replacement
pixels or quote their scores as canonical.

```bash
python3 tools/make_suites.py --seed 1 --out data/seed1
python3 tools/make_suites.py --seed 2 --out data/seed2
python3 bench.py --suite-dir data/seed2 --validate
python3 - <<'PY'
from pathlib import Path
from tools.make_suites import dir_hash
from tools.s38_compare import HASHES
for seed in (1, 2):
    actual = dir_hash(Path(f'data/seed{seed}'))
    assert actual == HASHES[seed], (seed, actual)
    print(seed, actual)
PY
python3 bench.py --suite-dir data/seed2 --suites easy,hard \
  --reader 'python3 tools/reader_lex.py {image}' \
  --reader-name shipping-reader-lex-seed2 --seed 2 --runs 1 \
  --timeout 60 --scorer author --report-dir reports/s38-seed2-fresh
# Expected exit 1: the accuracy bars are NOT met.

python3 tools/validate_report.py \
  reports/s25-piece-gap/receipt-final/20261013T081536Z-easy-hard.json \
  --data data/seed1 --expect-scorer author --compare-env --strict-env
python3 tools/validate_report.py \
  reports/s38-seed2-fresh/20261013T133120Z-easy-hard.json \
  --data data/seed2 --expect-scorer author \
  --expect-cmd 'python3 tools/reader_lex.py {image}' --compare-env --strict-env
python3 tools/s38_compare.py \
  reports/s25-piece-gap/receipt-final/20261013T081536Z-easy-hard.json \
  reports/s38-seed2-fresh/20261013T133120Z-easy-hard.json \
  --out reports/s38-comparison.json
python3 tests/test_s38_compare.py
python3 tests/test_validate_report.py
```

A new bench run has a new timestamp; substitute its JSON path in the validator
and comparison commands. The comparison utility refuses noncanonical hashes,
wrong seed/command/environment, incomplete counts, errors/timeouts, exclusions,
overridden bars, inconsistent matches/counts/families, and unfinished receipts.
It computes counts from audited items rather than trusting rounded headlines.

## Checks and coordination

- New comparison tests: **21/21 PASS**.
- Existing stamp-validator tests: **8/8 PASS**.
- Both receipt validators: **PASS** (canonical rehash and strict environment).
- Post-run deterministic wrapper spot checks: **4/4 item-identical**.
- Full offline regression suite: **26/26 test files PASS**, exit 0, 360.81s;
  [captured output](s38-regression-tests.txt). Run after scoring, not concurrently.
- Atomic claim and plan: task board plus bus `556fb42e`.
- Preconditions/status: `3ae42f0c`; completed scoring/investigation: `09325c9a`.
- Pericles contacted in DM `36e319ff`; Marcus contacted in `1a7fc3b7` and
  comparator question `e24124ae`. No mentor answer was fabricated.

**Recommendation:** retain the honest two-seed headline **73.5% easy / 26.0%
hard** for this unchanged route, with the historical/fresh qualifier. Do not
label either suite stable or promote 87% as the classic-stack hard score.
Further untouched-seed evaluation and three serialized repeated runs are
needed before any stronger generalization or stability claim.
