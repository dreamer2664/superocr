# S50 — pattern-based error correction: NO-GO (t-20261013-ef0a)

**Bounded probe, no wiring.** Closed-lane context respected: S22 (lex
re-casing) rejected, S24/S25 closed the case lane. The shipping route
already runs reader_lex = floor + lex-projection, whose R2 normalizes
digit-ish tokens (`OoIlZSB → 0011258`) and whose R3/R4 does
vocab-distance substitution repair.

## The measurement (`tools/s50_confusion_probe.py`)

All 100 hard + 100 easy items read in-process (verified identical to the
reader_lex CLI); every miss char-aligned against truth (Levenshtein
backtrack); one/two-swap fixability under classic confusion sets;
context rules simulated against the SAME reads with regression counting.

### Hard (23 correct / 77 misses)

| class | n |
|---|---|
| one confusion-swap from truth | **3** — all case-only (`o→O`): stitch ×2, obstruction ×1 |
| two confusion-swaps | 0 |
| other damage (seg, length, glyph destruction) | 74 |

Substitution census (top): `?→r` 7, `z→e` 6, `?→e` 6, `o→O` 6, `?→t` 5,
`w→e` 5 — the residue is `?` (unmatchable fragments = segmentation) and
stroke destruction, not visual pair confusions.

- **R-digit** (digit-translate mixed tokens): **0 fixes, 0 breaks** — the
  O/0, l/1, S/5 pattern is EMPTY post-lex; R2 already normalizes.
- **R-case** (Titlecase flip on vocab tokens): **1 fix, 21 breaks**.

### Easy (73 correct / 27 misses)

- one-swap: **2**, both case-only (`p→P`, `s→S`).
- R-digit: 0 fixes, 0 breaks. R-case: 0 fixes, **67 breaks**.

## Verdict

**NO-GO.** The task's premise — common OCR errors follow confusion-pair
patterns — does not survive contact with this reader: after the lex
projection, zero misses are pair-confusion-fixable, and the digit-normal
rule that would implement it has literally nothing to fix (0/104). The
only one-swap residue is CASE (5 items), which:

1. belongs to leonidas's S55 audit (9 case misses there), and
2. is unreachable by rules — the generator's `case_word` RANDOMIZES
   casing, so case has no exploitable prior: my R-case simulation breaks
   21 hard / 67 easy corrects to fix at most 1. This quantifies the
   S22/S24/S25 lane closure with direct receipts.

The 98/95 attack stays where S43/S35/S42 put it: segmentation (63/77),
stroke destruction, and word-level reading (S54).

## Files

- `tools/s50_confusion_probe.py` — the harness (alignment, confusion
  sets, rule simulation with regression counts)
- `reports/s50-confusion/probe.json` — full census + rule scores
