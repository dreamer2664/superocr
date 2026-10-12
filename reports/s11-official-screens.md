# S11 — the official screens: four reader paths, measured once, labelled

**Task:** t-20261012-2dcb (pericles) · **Commit measured:** `9a3c6f4` (main, "merge PR #22") ·
**Date:** 12 October 2026, 08:30–09:0x UTC · **Report written by:** pericles

## Why this exists

This morning the group's numbers moved twice, and one of them was wrong for hours. A
"22/6" figure — the S5-era classic path — was being quoted as the current floor, and the
official floor reader actually reads **28/9** (scott's correction, measured on merged main).
Chasing a dead number costs a shift. This report re-screens **all four reader paths once, on
one commit, with the exact commands**, so that every number the docs quote has a live receipt.

## What these numbers are — and are not

**These are SCREENS, not PROOFS.** One run of each path (`--runs 1`), on the official suite.
A proof, in this project, is **three runs with identical results** — the rule the S5 report and
the S6/S7 claims were held to. Nothing on this page may be quoted as a proof, and nothing here
is rounded up. Two of the four paths (baseline, reader.py) are the *floor* readers: they are the
thing to beat, not the product.

## Setup (reproduce in three commands)

```
python3 bench.py --suite-dir PATH/TO/suites --reader "python3 baseline.py {image}" \
    --reader-name baseline --runs 1 --no-gallery --report-dir reports/
```

- **Suites:** the official set — 100 `easy` + 100 `hard` images, 12 hard families — generation
  seed 1, identified by the group as hash `b2c460d2fb5a`. Same set as scott's correction.
- **Judge:** `bench.py`, one image at a time, `--runs 1`, galleries off (`--no-gallery`).
- **Note for reproducers:** `baseline.py` takes the image path **positionally**
  (`python3 baseline.py {image}`). `--image` is not accepted; passing it produces a
  silent 0/0 screen, which is how the first attempt at this row was lost this morning.

## The official table (of 100 easy, of 100 hard)

| path | exact matches easy | exact matches hard | easy median / p95 | hard median / p95 |
|---|---|---|---|---|
| **baseline** (`python3 baseline.py {image}`) — the floor to beat, post-#27 (ladder, f12b1da) | **54/100** | **12/100** | 6.23 s / — | 7.17 s / — |
| **reader.py** (`python3 tools/bench_adapter.py {image}`) — the documented path | **3/100** | **2/100** | 0.71 s / 0.87 s | 0.71 s / 1.56 s |
| **CNN v1** (`python3 readers/cnn_reader.py --image {image}`) | **29/100** | **6/100** | 0.18 s / 0.20 s | 0.17 s / 0.21 s |
| **CNN v2** (`python3 readers/cnn_reader.py --image {image} --weights models/glyphcnn-v2.npz`) — best merged | **31/100** | **8/100** | 0.16 s / 0.20 s | 0.17 s / 0.21 s |
| **AUTO** (`python3 baseline.py {image} --auto-family`) — S12 router, product path, post-#27 | **52/100** | **16/100** | 6.13 s / — | 7.16 s / — |
| **plain+lex** (`python3 tools/reader_lex.py {image}`) — S21 post-pass, receipt `reports-s21/` | **66/100** | **19/100** | 3.9 s / — | 4.7 s / — |
| **AUTO+lex** (auto route + S21 post-pass; local mirror wrapper, see note) | **64/100** | **24/100** | 6.42 s / — | 7.10 s / — |

Bars are 98 (easy) / 95 (hard). **No path comes close; the bar is not met.** After #27 the
floor itself is the best merged reader. The reader.py / CNN rows were **re-screened on
current main `79dd4e9` (18:18–18:23 UTC, cormac) and are UNCHANGED**: adapter 3/2,
CNN v1 29/6, CNN v2 31/8 — identical to their `9a3c6f4` numbers (receipts in
`reports/post27-screens/20261012T181[5-3]*`; the standalone readers didn't move with
the floor changes). They now sit far under the floor on both suites.

This screen independently reproduces scott's correction (baseline 28/9) on the merged commit.

### The AUTO row (added with S12, t-20261012-30bf)

The router row was measured on the S12 tree (`3c39dbe` + branch, commit `6102af1`),
not on `9a3c6f4` — the four rows above were one-commit screens, and the two trees
differ by more than docs (24 files, including `baseline.py` +52 and `reader.py` +11;
the only-docs pair is `590628a`→`3c39dbe`, inside the S12 tree). Comparability holds
because the plain row is **re-measured, not assumed**: on the AUTO tree the plain
route reads 28/9 with zero item diffs over all 200 items — the S12 report's own
plain run (`20261012T112433Z`) and marcus's clean-checkout re-run (receipt
`#9e099e2a`, all three routes re-run) agree exactly. Screen, not proof:
one run per route; the AUTO trade on this screen is **−1 easy, +2 hard** versus plain
(full hard oracle gain captured). Latency is median only — the source report predates
the stamps/co-op bench, which records p95; the AUTO median sits above plain (3.88 vs
3.18 s easy) because routing adds the pre-classifier probe and family masks.
Sources: `reports/s12-router-screens.md` + bench reports `20261012T112433Z` (plain),
`20261012T113752Z` (auto), `20261012T115124Z` (oracle) on the S12 branch (#32, merged).

### Post-#27 refresh (main `173254c`, 17:03–17:48 UTC, cormac)

#27 (f12b1da) rewrote `baseline.py` (+312/−18, the S8 ladder), so every baseline-path
number above moved. Both routes re-screened on current main, clean worktree, canonical
suite (hash verified `b2c460d2fb5a`), stamped bench, validator PASS with `--data`
re-hash on both reports (receipts: `reports/post27-screens/`):

- **plain: easy 54/100, hard 12/100** (medians 6.23 / 7.17 s) — matches barry's ladder
  receipts and pericles's delta screen item-exactly on the totals.
- **AUTO: easy 52/100, hard 16/100** (medians 6.13 / 7.16 s) — the router's trade on
  the new tree is **−2 easy, +4 hard**; routing into the improved family chains now
  yields more than the pre-#27 +2. AUTO is the best official-chain hard number on the
  board. Pre-#27 history: plain 28/9, auto 27/11 (S12 receipts above).
- Medians rose with the ladder's extra work (~3.2 → ~6.2 s easy) but stay under the
  10 s demo bar. Screens, not proofs (one run each), as always.
- **#47 (S21 lex-projection, main 79dd4e9) landed after the #27 refresh screens.**
  plain+lex: 66/19 (pericles's stamped receipt `reports-s21/20261012T171659Z`,
  validator PASS on my box with `--data` re-hash). AUTO+lex: **64/24** — screened by
  me with a LOCAL mirror of `tools/reader_lex.py` that routes baseline through
  `--auto-family` (not committed; the wrapper question is pericles's lane — the
  natural follow-up is forwarding extra args in `reader_lex.py`). The stack compounds:
  plain 12 → auto 16 (+4 routing) → plain+lex 19 (+7 lex) → **auto+lex 24 (+12 over
  the floor, hard doubled)**; easy 54 → 66/64. AUTO+lex is the best official-chain
  hard number on the board. Receipt: `reports/post27-screens/20261012T175042Z*`
  (stamped, validator PASS; reader_command names the local wrapper honestly).


## Where the hard points actually are — per family (all four paths)

| hard family | n | baseline | reader.py | CNN v1 | CNN v2 |
|---|---|---|---|---|---|
| collage | 8 | 0/8 | 0/8 | 0/8 | 0/8 |
| corrosion | 8 | 0/8 | 0/8 | 0/8 | 0/8 |
| cross-shadow | 8 | 0/8 | 0/8 | 0/8 | 0/8 |
| cut | 8 | 2/8 | 0/8 | 0/8 | 0/8 |
| dark-on-dark | 8 | 2/8 | 0/8 | 0/8 | 1/8 |
| darts | 8 | 0/8 | 0/8 | 0/8 | 0/8 |
| obstruction | 8 | 1/8 | 1/8 | 0/8 | 1/8 |
| snow | 9 | 2/9 | 1/9 | 3/9 | 3/9 |
| spiderweb | 9 | 1/9 | 0/9 | 0/9 | 0/9 |
| split | 9 | 0/9 | 0/9 | 0/9 | 0/9 |
| stitch | 9 | 1/9 | 0/9 | 0/9 | 0/9 |
| strippy | 8 | 0/8 | 0/8 | 3/8 | 3/8 |

Two facts worth carrying forward:

1. **The floor is not zero on every hard family.** `baseline.py` takes cut 2/8, dark-on-dark 2/8,
   spiderweb 1/9, stitch 1/9, obstruction 1/8 — that is most of its hard score. Any integration
   of a family mask (S7c) that *regresses* those five cells is a regression of the floor itself.
2. **Six families are zero for every measured path** (collage, corrosion, cross-shadow, darts,
   split, stitch), and `cut` is zero for all three reader paths while the floor takes 2/8. The
   "0% walls" the group has been working (S7/S7c) are visible right here, and this table is the
   honest scoreboard to move — beating 31/100 easy, not reaching 98 first.

## What this report retires and replaces

| retired | reason | replacement (this file) |
|---|---|---|
| "22/6" as the floor | S5-era classic path, quoted without provenance; today `bench_adapter` routes to `reader.py` | **28/9** (`baseline.py`, positional arg) |
| "S5 proof: classic 2/100·1/100" read as current | true for commit 0553923, not for main | **3/2** (`reader.py`, this commit) |
| "best merged reader ≈ 22/100 · 6/100" | stale on both numbers | **31/8** (CNN v2) |

Docs corrected in the same change as this report: `JOBS.md` (status table, "where we are",
S8 section) and `README.md` (the reader-numbers paragraph now points here).

## Repro receipts

Machine reports are committed next to this file (same directory), one pair per path, in the
order they were run — each carries its reader command, per-family counts, per-image results and
the failure ids:

| file stem | path |
|---|---|
| `20261012T083023Z` | reader.py (`tools/bench_adapter.py`) |
| `20261012T083259Z` | CNN v1 |
| `20261012T083334Z` | CNN v2 (weights v2) |
| `20261012T084109Z` | baseline (positional arg — the re-run; an earlier attempt with `--image` produced a 0/0 report and was discarded, see above) |

- Four screens, one commit: `9a3c6f4`. The four commands are exactly the rows of the table
  above, run once each, in order.
- Latency column is bench-side wall clock per image (median/p95), not a product claim;
  the demo/probe latency bar is S9's (`reports/s9-latency.md`).
