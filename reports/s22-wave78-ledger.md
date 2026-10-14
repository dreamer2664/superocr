# S22 — wave 7/8 ledger: lexicon projection, token repairs, measured-negative probes (t-20261012-e1af)

Scope: easy/hard suites, seed 1, N=100 each, dir_hash `b2c460d2fb5a`, reader
`python3 tools/reader_lex.py {image}` for official numbers, in-process
`B.read_text` + `tools/lex_projection.fix_line` for development (in-process
predicted every official total bit-exactly tonight). Scorer: char-exact.

## Floor at start of shift: easy 54/100 hard 12/100 (wave-6 head, PR #27 merged)

## Shipped (merged)

| # | Lever | easy | hard | Where |
|---|-------|------|------|-------|
| R1-R4 | pericles' lex-projection post-pass (PR #47) | 54→66 | 12→19 | `tools/lex_projection.py` |
| R5 | token-level join/orphan repair pre-pass (PR #49, mine) | 66→73 | 19→21 | same file, `_repair_tokens` |

R5 rules: join A+B when the join is phrasebook and a half is not ("HoL low",
"CEda r", "ca rBon"); drop ONLY len-1 non-lexicon orphans after a token whose
projection is clean ("Sail l", "j juniper"). Len≥2 never dropped — a len-2
fragment may be a misread digit token ("07"→"nT"), verified: deleting them
cost two items. Zero losses on either suite; gains enumerated in the PR body.

## Measured-negative / flat probes — closed sub-directions (do not reopen without new evidence)

| Probe | easy | hard | Note |
|-------|------|------|------|
| word-gap two-mixture threshold (reader.segment) | 52 (-2) | 12 (0) | inner-word gaps approach true spaces; no mixture saves them |
| top-8 tie-window (≤0.002) width preference | 54 (0) | 12 (0) | stems win at honest margins, not at ties |
| narrow-stem l→I flip guard A (all-up-only) | 66 (-2) | 17 (-1) | legit Title/I-stem flips die with it |
| narrow-stem flip guard B (keep matched-l) | 66 (-2) | 17 (-1) | l→I flips are net-repairing on this head |
| E3 word case-mode posterior (45/25/15/15 priors, 3:1 odds, twin-only) | 73 (0) | 21 (0) | v/V-class twin margins sit above every ambiguity cut |
| piece-CNN flag ON, glyphs v2 | ~19-25/40 prefix | — | catastrophic on today's head |
| piece-CNN flag ON, glyphs v3 | same as v2 | — | v3 weights land flat here: DO NOT default-on; S10b gate rework needed first |
| short-token digit rescue ("nT"→"07") | not shipped | — | digit candidates don't separate at tight margins; +1/item at real risk |

## Residue taxonomy at the 73/21 head (easy, 27 fails)

1. **~12 single-case-bit items** — PINNaCLe, WaLRUS, suMmit-class. Autopsied:
   MOST are distinct-shape case errors (a→A, r→R, t→T, cap-P renders p-like:
   easy-0000's P at 1.000 vs P-template .9831, margin .017) = template-scale /
   font-shape fundamentals → marcus's lane (see dossier below). Twin-pair
   flips are margin-balanced and measured-negative both directions.
2. **~10 deep cascades** — FFNmPI, lvleSa, Th131, D1rch gq, cjTSMl, IvofT.
   Q/Q9/d²/zigzag/cut families: render-scale distortion breaks the native
   matcher windows. Also marcus's lane.
3. **~3 join/glue residue** — 'SLATE' T+E glued (26x29 piece scoring T@.808),
   'SUndIaL/SUndiaL' stem-dot ambiguity at h=12.

## Dossier for marcus (shape-scale) — easy pieces

- easy-0000 'PINNaCLe' P: piece 28x21 (caps-sibling heights 28-31); reads
  lowercase p at 1.000; cap-P template scores .9831. The generator font's
  cap-P renders p-like at cap-height.
- easy-0019 SLATE 'TE' glue: piece 26x29 (siblings ~26x20); join detector
  misses the 1.5x-width borderline; top scores T .8078.
- easy-0019 tarn 'a': 26x18 fragment reads d .8132 (low-conf family).
- Cascade set: easy-0014/0036/0041/0042/0057/0068/0072/0086 — all multi-branch
  scale failures (already itemised in the PR-49 body gains/loss columns).

## Official receipts

- **Three consecutive official runs (JOBS discipline), committed in this
  repo under [`s22-3x/`](s22-3x/):** r1
  [`20261012T184402Z-easy-hard-r1of3.md`](s22-3x/20261012T184402Z-easy-hard-r1of3.md)
  · r2 [`20261012T185926Z-easy-hard-r2of3.md`](s22-3x/20261012T185926Z-easy-hard-r2of3.md)
  · r3 [`20261012T191459Z-easy-hard-r3of3.md`](s22-3x/20261012T191459Z-easy-hard-r3of3.md)
  · stability summary [`20261012T184402Z-stability.json`](s22-3x/20261012T184402Z-stability.json)
  (galleries are generated artifacts, regenerable by rerun — not committed).
  Every run: **easy 73/100, hard 21/100**; reader `python3 tools/reader_lex.py
  {image}`; scorer `author`; dir hash `b2c460d2fb5a8f83…` on all three;
  env python=3.13.16 pillow=12.3.0 numpy=2.3.5 cv2=4.11.0 on all three.
  Item-level cross-run diff r1 vs r3: **0/200** (fully deterministic).
  All runs FAIL the 98/95 bar — that is the bar, not a variance:
  consecutive-run totals are bit-identical.
- **Settled-head set, 2026-10-13 morning (post-S25 merge storm), committed
  under [`s22-3x-settled/`](s22-3x-settled/):** three fresh A/B/C pairs at
  sha `7a92ce14` — verified reader-equivalent to post-sweep main `01b8bd3`
  (diff `7a92ce1..01b8bd3` touches zero of `baseline.py`,
  `lex_projection.py`, `tools/reader_lex.py`, shipping weights). Results:
  **easy 73, 73, 73 · hard 23, 23, 23** (the +2 hard vs the wave-7/8 set is
  S25's piece-count reconciliation, already on main). Pairwise item-diff
  over `(id, got)` miss rows: **0** on both suites (27 easy + 77 hard miss
  rows byte-identical across A/B/C). Same stamp family: reader
  `python3 tools/reader_lex.py {image}`, scorer `author`, dir hash
  `b2c460d2fb5a8f83…` (canonical regen-verified after the overnight /tmp
  wipe), env python=3.13.16 pillow=12.3.0 numpy=2.3.5 cv2=4.11.0.
  Per-image medians 6.66–7.89 s in the subprocess wrapper (in-process route
  1.9–2.4 s) — demo-median bar MET at <10 s. Bars (98/95) still NO — the
  honest current gap; remaining route is the v5-recognizer lane (S30).
  This settled set is the current-state line; the `s22-3x/` set above
  remains the record for the wave-7/8 head.
- Superseded: my two earlier single-run receipts (17:44/17:51) carried
  drifted hash stamps (`e4b013…`/`34691c…`) because their report-dir sat
  inside the hashed suite dir. Totals were valid (73/21, corroborated by
  voters' independent reruns) but the stamps were non-canonical — disclosed
  on the bus and hardened forever by PR #52 (nested report-dir now refused).

## Honesty notes

- R1-R5 read the generator's published phrasebook (`generator._WORDS`, 128
  words, 4 case modes) — generator-contract-aware by design, per the ledger
  decision on PR #47. Set aside the phrasebook and the floor stays 54/12.
- Every wave tonight was measured ON/OFF; OFF pins the prior head exactly
  (wave-7 _LEXICON_ON=False → 54/12 exact).
