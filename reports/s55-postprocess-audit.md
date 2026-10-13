# S55 — post-processing audit of the 14 non-segmentation S43 misses

Task `t-20261013-90e8` (Pericles directive `#0f86380a`, plan `#b58f4d16`).
Branch `agent/leonidas/t-20261013-90e8`. All measurements reproducible with
`tools/s55_postprocess_harness.py` (+ `tools/s55_seed_screen.py` for the
fresh-seed screen). Production change: ONE line in `tools/lex_projection.py`
(R3 band, see §3) — `baseline.py` untouched.

## Verdict up front

- **Case lane (9 items): stays closed — no code change.** The audit found
  no new instrument and no exploitable bias (§2). This re-confirms S22/S24
  with per-item evidence from the S43 census itself.
- **Glyph lane (5 items): one generic rule ships.** Widening the lex R3
  band by +1 (candidate B) passes the full canonical seed-1 gate with
  zero broken rows, is non-negative on every guard set including a fresh
  seed-3 screen, and recovers stitch-0001. Shipped in
  `tools/lex_projection.py` with the measured note in the R3 docstring.
- The other four glyph targets are **provably unreachable** by any
  text-only lex rule: they are distance ties or beyond any band that
  survives the full gate (§4). They need image-side evidence, which is
  segmentation/reader territory, not post-processing.

## 1. Target set (pinned, recomputed — not hand-copied)

Targets = the 14 S43 misses whose primary class is `matching-case` (9) or
`matching-glyph` (5), taken from the committed census
(`reports/s43_failure_analysis.json`, PR #69 @ `865abc5`). The harness
asserts the count and classes before measuring anything, and pins
candidate A by reproducing the canonical shipping numbers (easy 73 /
hard 23) from the post27 floor receipt.

## 2. Case lane — audit of the 9 items / 11 flipped positions

Every flipped position in the 9 case items is a size-twin letter decision
(`SAME_SHAPE`-class: c/o/s/u/w/r/y/i), and the flips run in **both
directions** (8 need lower→upper, 3 need upper→lower):

| item | got → label (flipped token) | direction |
|---|---|---|
| snow-0001 | `IsLAND`→`ISLAND`, `PLuME`→`PLUME` | up, up |
| cut-0001 | `indigo`→`Indigo` | up |
| split-0003 | `cIPHER`→`CIPHER` | up |
| stitch-0003 | `oRChid`→`ORChid` | up |
| obstruction-0003 | `Moss`→`MOss` | up |
| stitch-0004 | `ivorY`→`ivory` | down |
| stitch-0007 | `CoPPER`→`COPPER` | up |
| dark-on-dark-0007 | `bRASs`→`brASs` | down |
| stitch-0008 | `Wren`→`wren`, `lagoOn`→`lagOOn` | down, up |

Consequences, each measured rather than asserted:

- **No threshold/bias rule exists.** A global case bias trades the 8 up-
  flips against the 3 down-flips; `_case_of`'s height-ratio thresholds in
  `baseline.py` cannot be re-tuned from receipts (they contain no glyph
  height data), and the only image-side instrument ever measured on this
  residue — the S24 Addendum 5 blind CNN crop re-score — went **net
  −20 positions (fixes 8 / breaks 28)**, with Addendum 6 showing the CNN
  confidence gate has no signal and token-majority casing scores 5/18.
- **Token-majority re-case, re-measured here as candidate D** (the
  strongest text-only case rule available), recovers exactly 1 of the 14
  targets (stitch-0007) and is catastrophic on full suites: seed-1
  73/23 → **15/5**, seed-2 similar (harness `diffs_vs_A`: ~90 broken rows
  per set). Suite labels are per-letter mixed case by design, so any
  token-level flattening destroys far more than it fixes. **Rejected.**
- R1's design rule (never re-case a clean token) stands. The case lane
  re-opens only with a NEW image-side instrument measured positive on
  this residue — none was found in this audit, so none is claimed.

## 3. Glyph lane — candidate measurement (full suites, never the 14 alone)

Candidates (rule classes only, no per-item rules; variant equivalence to
shipping asserted inside the harness):

| candidate | seed-1 easy/hard | seed-2 v2 raw | seed-2 v3 raw | seed-3 fresh screen | targets |
|---|---|---|---|---|---|
| A shipping (pinned) | 73/23 | 74/29 | 75/28 | 68/100, 42/120 | 0/14 |
| **B R3 band +1 (all lengths)** | **75/25** | **75/29** | **76/30** | **70/100, 43/120** | **1/14** |
| C R3 band +1 (len ≥ 6 only) | 73/24 | 75/29 | 76/30 | 68/100, 42/120 | 1/14 |
| D A + case-majority | 15/5 | 14/13 | 14/12 | 14/100, 11/120 | 1/14 |

(Seed-2 arms are the S23 v2/v3 raw reader rows; extra seed-1 v2/v3 arms:
B 75/25 and 75/26 vs A 73/23 and 73/24. Seed-3: fresh plain-reader rows
generated for this audit, `reports/s55_seed3_floor_rows.json`, 100 easy +
120 hard, a seed used in no tuning receipt.)

Candidate B fix/break detail (harness `diffs_vs_A`): seed-1 fixes
easy-0002, easy-0036, dark-on-dark-0005, stitch-0001 — **zero breaks on
either suite**; seed-2 v3 fixes cut-0006, easy-0057, obstruction-0007 —
zero breaks; seed-3 fixes easy-0021, easy-0033, strippy-0002 — zero
breaks. B dominates the narrower C on seed-1 (the len<6 widening earns
easy-0002/easy-0036/dark-on-dark-0005) with no measured cost anywhere, so
B — not C — is the shipped form. The uniqueness margin (≥1 over the
runner-up) is unchanged, which is what keeps the wider band honest:
ambiguous tokens stay untouched (see §4).

**Shipped change** (`tools/lex_projection.py`, R3):
`band = max(1, round(len/3))` → `max(1, round(len/3)) + 1`, with the
measurement recorded in the module docstring. Canonical end-to-end
confirmation (reader_lex bench, suite hashes verified against
`s38_compare.HASHES` before running): seed-1 `reports/s55-bench-seed1/`
and seed-2 `reports/s55-bench-seed2/` — results in §5.

## 4. Why the other four glyph targets cannot be text-fixed

Verified by running the shipped lex on each token (distances from the
harness / `lex_projection._ed`):

| item | token → label | nearest vocab (distance) | why no rule reaches it |
|---|---|---|---|
| snow-0003 | `rert` → reef | crest 2, **reef 2 (tie)**, band(len4)=2 even widened | tie: projecting is a coin flip; the margin rule correctly abstains |
| split-0006 | `cafmon` → carBon | canyon 2, **carbon 2, salmon 2 (tie)** | 3-way tie; also the label's own case pattern (`carBon`) differs from the token's, so even a lucky glyph pick misses exact |
| strippy-0005 | `zztlz` → sable (line `zztlz 1 rIJJz tiiz`) | best distance 4 | multi-glyph garble; no band that reaches 4 survives the full gate |
| dark-on-dark-0000 | `Vi ULL … nnA` → `VIOLET … 006` | tokenisation itself is split (`Vi`/`ULL`) | segmentation failure inside a glyph-classified row; lex operates on whole tokens |

And stitch-0001, the one recovery: `njMDRA` → tundra is distance 3 at
length 6 (old band 2, widened band 3), unique with margin 1 — exactly the
class of “one edit beyond the old band, still unambiguous” that B admits.

## 5. End-to-end bench confirmation

Stamped `reader_lex` benches on canonical suite bytes (dir hashes
verified against `tools/s38_compare.HASHES` before running:
seed-1 `b2c460d2…`, seed-2 `ec64cd63…`; both receipts pass
`tools/validate_report.py`):

| bench | before (shipping) | after (S55) | receipt |
|---|---|---|---|
| seed-1 easy | 73/100 | **75/100** | `reports/s55-bench-seed1/20261013T211005Z-easy-hard.json` |
| seed-1 hard | 23/100 | **25/100** | (same receipt) |
| seed-2 easy | 74/100 | **75/100** | `reports/s55-bench-seed2/20261013T213310Z-easy-hard.json` |
| seed-2 hard | 29/100 | **29/100** | (same receipt) |

The end-to-end numbers match the offline harness exactly on seed-1
(75/25) and are non-negative on seed-2 (+1 easy, hard unchanged), closing
the gate Pericles set: full canonical seed-1 gain, zero regression, plus
seed-2 screen. ("FAIL" verdicts in the bench reports are against the
98/95 accuracy bars, as with every reader_lex receipt to date.)
Regression pins: `tests/test_s55_lex_band.py` (6/6) and the pre-existing
`tests/test_s25_count_repairs.py` (5/5) both pass.

## 6. What this does NOT do

- No change to `baseline.py` (`_case_of` untouched): no measured case
  instrument exists, per §2 and the S22/S24 record.
- 13 of the 14 targets remain missed, honestly: 9 case items await an
  image-side instrument that beats the S24 gate; 4 glyph items need
  reader/segmentation evidence, not text rules.
- Measured canonical movement from the shipped line (§5): seed-1
  73/23 → **75/25**, seed-2 74/29 → **75/29**.
