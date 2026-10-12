# S24 — the 10 non-corrosion iris hard residuals, classified (t-20261012-c4af)

**Author:** marcus. **Date:** 12 Oct 2026, evening shift. **Assigned by:** pericles, 20:33Z
(iris-lex run-1 hard 84/100; barry owns the 8 corrosion residuals separately).
**Repro:** `python3 tools/s24_iris_residuals.py` (deterministic, offline, stdlib + this repo only).

## Input honesty

The true label lines are read from the canonical seed-1 suite manifest
(`b2c460d2fb5a`). The **got lines are SIMULATED** from the per-item fragments
pericles published on the bus (the real model reads are in his run logs,
`iris-lex-hard-run1.log`). The tool accepts the real reads via `--jsonl` and
recomputes; if any real got line differs materially, the affected row's lane
must be re-read. The classification below is therefore *conditional on the
fragments as published* — every one is consistent with its item's description.

## Result: the merged post-pass repairs 0 of 10 — and the lanes explain why

| item | label | simulated got | after `fix_line` (R1–R5) | lane |
|---|---|---|---|---|
| darts-0001 | `ORCHID fAlCOn` | `ORCHID fAlC0n` | `ORCHID fAlCon` | case-at-repaired-position |
| obstruction-0003 | `MOss Fjord` | `M0ss Fjord` | `Moss Fjord` | case-at-repaired-position |
| snow-0007 | `gLAcier bRoOk 002 Indigo` | `gLAcier bRo0k 002 Indigo` | `gLAcier bRook 002 Indigo` | case-at-repaired-position |
| strippy-0003 | `falcON 005 GLACIER` | `falc0N 005 GLACIER` | `falcoN 005 GLACIER` | case-at-repaired-position |
| cut-0006 | `torque DrIfT OBSIdiAN` | `torque DrIfT OBSidiÁN` | `torque DrIfT OBSidiAN` | case-at-repaired-position (+`I/i`) |
| cut-0002 | `TrAIL fennel FLINT` | `TrAiL fennel FLINT` | unchanged | case-only (R1 immune by design) |
| obstruction-0001 | `FlINT plume` | `FLINT plume` | unchanged | case-only |
| split-0001 | `Comet MEriDIAn` | `Comet MERiDiAn` | unchanged | case-only |
| strippy-0004 | `lUpIne Cedar` | `lupine Cedar` | unchanged | case-only |
| stitch-0007 | `COPPER 008 linen` | `COPPER 0 08 linen` | unchanged | spacing (digit-token split) |

**Tally: 5 case-at-repaired-position · 4 case-only · 1 spacing · 0 post-pass-fixable.**

## Why the homoglyph items still miss even though the projection fires

The projection DOES repair the letter (`0`→`o`, `Á`→`A` — see the out column:
every one is now lexicon-clean). What it cannot repair is the **case of the
repaired position**: the misread destroyed the case evidence in the text layer,
and R4 fills repaired positions with the token's majority case — a coin flip
against labels whose case is drawn **per character, p=0.5** (`generator.case_word`,
line ~110). No lexicon-side rule can recover it; only the pixels carry that bit.
This extends pericles' easy-residual verdict (case_choice cannot fix model case
misreads) to the hard side: **9 of these 10 residuals converge on ONE lane —
per-position case evidence from the image.**

## Fix proposal (next task, cheap measurable first step)

**Case re-score from pixels for suspect positions.** The verify stage already
knows which token positions are suspect (projection fired there, or case
pattern disagrees with nothing — it can flag all case-ambiguous positions).
For each flagged position, crop the character cell and score upper vs lower
with `glyphcnn-v3` (it was trained ON case twins — S16), or with a second
targeted model read of the crop. Pick the argmax case; keep the projected
letters. Measurable on: these 10 items, the 26-item easy case-only class
(S22 map), and the classic floor's case residue — all offline, no new training.

Risks, named: crop alignment on the iris side is not free (the classic reader
has segmentation; the vision model may not expose cell boxes — a coarse
re-read prompt of the single word may be the cheaper variant); CNN case
accuracy on degraded crops is unmeasured — that measurement IS the first step,
before any wiring.

**Spacing (stitch-0007):** no safe text-layer rejoin exists — digit-only tokens
legitimately appear spaced in labels (`002`, `005` above), and R5's orphan rule
excludes digits by design. This one belongs to the verify stage with image
evidence (is the gap a real space?) or stays a known 1-item loss.

## What this does NOT say

- It does not re-open the corrosion 8 (barry's task; my S20 receipts stand:
  classic-side corrosion is a reader wall, and the iris near-misses there are
  digit/letter confusions on noisy crops — his lane).
- It does not claim the iris stack's projection mirror behaves identically to
  `tools/lex_projection.py` — the simulation uses the merged tool. If pericles'
  mirror diverges (e.g. verify undoing a projection), row-level reruns with the
  real logs (`--jsonl`) will show it.
- Easy 96/100 stands as the current stack's easy ceiling (pericles' traced
  verdict, corroborated by this analysis: the case bit is destroyed pre-text).

## Addendum (20:5x Z) — REAL run-log lines received and replayed

Pericles published the actual got/label pairs from `iris-lex-hard-run1.log`
(bus 20:40Z) after the simulation above was written. Replayed via
`--jsonl reports/s24-real-got.jsonl` (committed here): **0/10 repaired to
exact — headline unchanged.** Lane tally refines:

- **5 case-only** (cut-0002, cut-0006, obstruction-0001, split-0001,
  strippy-0004). cut-0006 moves here from case-at-repaired: the log line is
  post-projection (`OBSidiAN`, accent already fixed) and the residual is the
  verify stage echoing the model's wrong case — pericles: "Verify echoes the
  model's wrong read instead of accepting the projection's correction. This is
  a verify-interaction bug in the iris stack, not a lex-projection issue."
- **4 case-at-repaired-position** (darts-0001, obstruction-0003, snow-0007,
  strippy-0003) — exactly as simulated.
- **1 spacing** (stitch-0007) — exactly as simulated.

Transcription note: pericles' message lists split-0001's label as `Comet
MErIDiAn`; the canonical seed-1 manifest (authoritative, used by the tool)
says `Comet MEriDIAn`. The lane is case-only under either spelling.

The convergence stands: 9/10 residuals need per-position case evidence from
pixels; the verify-interaction fix (trust a suspect-reducing projection's
letters) is pericles' lane and would convert the 4 case-at-repaired items
into pure case decisions — the same lane as the other 5.
