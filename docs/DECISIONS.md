# DECISIONS — the log of what we tried, what it measured, and why it's closed

_The point of this file: nobody re-litigates a closed direction without new
information, and nobody trusts an open claim without a receipt. Keep it updated
on every merge that moves a number or closes a lane. State as of 2026-10-13,
main @ `a530a8f`._

## The bar (do not bend)

easy ≥ **98/100**, hard ≥ **95/100**, **three consecutive runs** each, live
demo median ≤ **10 s**, reproducible from clean clone (JOBS.md / BENCH.md).

## Where we are

| line | easy | hard | receipt |
|---|---|---|---|
| **Shipping floor+R5+lex (settled)** | **73** | **23** (×3) | `reports/s22-3x-settled/20261013T101654Z-*.json` (PR #53 frozen branch `584f8c4`) |
| Same, seed-2 generalization screen | 74 | 29 | `reports/s38-seed2-fresh/20261013T133120Z-easy-hard.json` (merged #68) |
| Text layer iris_lex v1.2 (external lane) | 98 once | ≈87 | bus receipts — easy 98 needs ×3; hard bar not met |

Ladder of the classic stack on seed-1 (S39 measurements): plain floor 54/12 ·
AUTO 52/16 · plain+lex 66/19 · plain+R5 73/21 · AUTO+R5 71/26. The shipping
wrapper (floor+R5+lex) is the 73/23 line above — reads byte-identical to
plain+R5+lex at −68%/−73% median latency (2.15/2.10 s vs 6.69/7.66 s), PR #65.

## Why hard is stuck at 23 — the census (merged, #69)

`reports/s43_failure_analysis.md`: of 77 hard misses, **63 are segmentation /
mask failures**, 9 matching-case, 5 matching-glyph. The lexicon helped 17
items and hurt 0. Six near-zero families (collage, corrosion, cross-shadow,
darts, strippy at 0/8 each; spiderweb 1/9) account for 48/77 — the
segmentation/mask lane owns **82% of the residue**. Any plan to reach hard 95
must attack segmentation on those families, not matching.

Collage lethality is specifically **per-word differential rotation +
patchwork backgrounds** — global transforms don't model it.

## The CNN lane (merged, #66 + #67) — strongest measured movement

- **S53 corpus** (`reports/s53-hard-corpus/`, #66): 2000 generated hard items
  (corrosion 446 / rotation 444 / overlay 888 / combined 111 / control 111),
  per-item rng `sha256("s53-hard:53:{index}")`, manifest sha `44b79be7ea90551a…`,
  binding split train 0–1599 / val 1600–1999, canonical suites eval-only.
- **v7 (word-context crops only)** — honest NEGATIVE control
  (`reports/s30-v7/`): corpus val 0.31→0.79 but clean guard FAILED (easy
  solo-glyph 0.90→0.70 through floor segmentation). Lesson: crop semantics
  must match at BOTH ends — the v6 lesson is symmetric.
- **v7b (dual word+tight distribution)** — clean guard PASSED
  (`reports/s30-v7b/`, #67): crop TOTAL 0.4334→**0.7998**; rotation arm
  0.85–0.96 **without de-rotation** (the S29 wall is down); control
  0.598→0.902; overlay 0.86–0.87; corrosion L/M/H/E 0.79/0.50/0.41/0.22;
  combined 0.252→0.652. Read-level through floor segmentation: easy glyph
  0.9009→0.9235, easy exact 19→31 (raw CNN chain, no lex); hard glyph
  0.7908→0.8095, exact 6→7. Reviewer-reproduced byte-for-byte on the
  canonical suite.
- **Status:** v7b does NOT replace the shipping stack (raw chain 31/100 <
  73/100), and **patch-class integration is closed** — S31/t-becc (PR #72)
  measured both levers NO-GO: slot-swap loses calibrated rescues (−3 easy),
  read-time context windows don't transfer the training-time gains (neutral
  to −8). The remaining CNN-lane route is the **S54/t-768c word-level reader
  redesign** (whole-word jointly-normalised crops + fusion-surviving
  segmentation) — project-scale, with its own held-out protocol.

## Closed directions (measured-no; do not retry without new information)

| direction | result | receipt / note |
|---|---|---|
| **S51 CLAHE pre-step** | net-harmful: easy 73/73/73 (neutral), hard 23→20 (c2) →18 (c4); target dark-on-dark 3/8→3/8→2/8; obstruction collapse 4/8→0/8→1/8 | `reports/s51-clahe.md` + 600 rows (PR #70); OFF-arm 200/200 byte-identical to independent S39 reads |
| **S31 patch-class v7b integration** | both levers NO-GO: slot-swap easy 70(−3)/hard 24(+1); context windows K1 neutral (31/6 raw), K2 −8 easy, v4-K1 −14; K0 control == S30 read-probe exactly | `reports/s31-v7b-integration.md` + 1,200 rows (PR #72); ctx probe re-run by reviewer: 0/800 item-diffs |
| **S37 offline ensemble voting** | neutral-to-harmful: E3a 73/23 (=), E3b 71/23 (−2), E4 73/23 (=); members share the same floor errors — voting combines independent errors, ours are the same error four times; incidental: current single-chain AUTO measures 14/10 (historical 52/16 was the old all-chains auto) | `reports/s37-ensemble.md` + 200 rows × 7 reads (PR #74); off/v7b arms 200/200 identical to S31 + S39 rows |
| S29 rotation transfer (v4) | ZERO transfer to rotated suite items | bus receipt; superseded by v7b (rotation solved by training distribution, not de-rotation) |
| S28 v3 on dead families | NO-GO | probe receipt in reports history |
| S27 truth-mask oracle | 0/16 — even oracle masks don't rescue matching on dead families | `tools/s27_oracle_masks.py` + report |
| S26 digit lane | CLOSED (digits not the bottleneck) | `tools/s26_digit_corrosion_probe.py` |
| S24 real-crop replay | 0/10 | `tools/s24_realcrop_probe.py` |
| S23 homoglyph screen | no gain | `tools/s23_homoglyph_screen.py` |
| S15 topology features | no gain | bus receipt |
| Darts median3/5 filters | no gain | darts remains 0/8 (census) |
| LD threshold 40 | no gain | LD lane closed |
| Dark-on-dark LD | no gain | 3/8 unchanged across arms |
| Opening k≥2 / erode→dilate∩mask | destroys stroke structure | morphology lane closed |
| Iterative reconstruction | no gain | — |
| Flat-field division | no gain | — |
| Margin remap | no gain | — |
| Corrosion close1 variants | no gain | — |
| CNN-fused-join | no gain | — |
| Piece-CNN flag | no gain | `readers/piece_cnn.py` kept as dead lane marker |
| E3 case-mode posterior | no gain | case misses = 9/77 (census) — small pool |
| Wave-8 case-stem | no gain | barry receipt |
| v5 recognizer | LOST: clean collapse (same failure mode as v7) | recipe kept |

Method note: the S51 probe is the **template** for pre-step probes — arms
fixed up-front, deterministic implementation, OFF gate that must reproduce the
settled line exactly or the whole probe is void, all rows committed.

## Delivery lane

- **W1 webapp** (merged #64): local server + browser UI, lex route
  (`/api/ocr route=lex`), gallery, health chip.
- **W2 standalone app** (PR #71, review): downloadable 3.3 MB zip
  (GitHub Release asset, generated not committed), unzip-and-run on
  macOS/Windows/Linux, **real screen reading** (root cause of "screen read
  never worked": the button called `getUserMedia` — the camera — instead of
  `getDisplayMedia`; plus font portability: `available_fonts()` knew only
  Linux paths, so other OSes silently degraded to Pillow's bitmap default =
  garbage reads → bundled DejaVu fallback, system faces still win, canonical
  machines bit-identical). Selftest = drift detection (12 demo items must
  reproduce build-time reads exactly); watchdog auto-restart; crash log;
  INSTALL honesty section. Clean-room verified: selftest 12/12 PASS, warm lex
  ≈0.9 s. The old "instability" was the agent-sandbox preview host being wiped
  (7×) — the bundle runs on the user's machine and is immune.

## Open lanes (2026-10-13 evening)

| lane | what | state |
|---|---|---|
| t-768c / S54 | word-level reader over v7b-class nets (whole-word crops, fusion-surviving segmentation) — the remaining CNN-lane hypothesis after S31 | open, routing (barry offered first) |
| PR #71 / W2 | standalone app (Carlo P1) | review, awaiting ballots |
| PR #74 / S37 | ensemble no-go receipt | review, awaiting ballots |
| PR #73 / S45 | these docs | review, awaiting ballots |
| PR #72 / S31 | v7b integration no-go receipts | 1/2 ballots |
| PR #65 / S39 | fast wrapper (73/23 at −68% latency) | 1 valid ballot, needs 1 more |
| PR #70 / S51 | CLAHE no-ship receipt | 1/2 ballots |
| PR #53 | bench ledger + settled receipts | frozen @584f8c4, needs scott |

## Method laws (why our numbers are trustworthy)

1. **Receipts or it didn't happen** — every claim cites a committed report;
   four stamps enforced by `validate_report.py --strict`.
2. **Selection effect** — clean-item accuracy does not transfer; measure on
   the full canonical suite.
3. **Winner's curse** — sweep winners are inflated; validate on held-out
   seed-2 before shipping (S38).
4. **Name both hard numbers** — seed-1 23 and seed-2 29, always together, in
   any generalization claim.
5. **Negative results are deliverables** — a gated NO-SHIP receipt closes a
   direction cheaply for everyone.
